"""Detached readout and evaluator boundaries; controlled truth, no benefit claim."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import numpy as np
import pytest

from cpswm.system.evaluation_operations.structure_two_selected_method import (
    OrderedActorRole,
    TypedParticleState,
)
from cpswm.system.structure_two_joint_consumption import JointDecisionAtom, JointDecisionView
from cpswm.system.structure_two_particle_workspace import ConditionalAnalyticState
from cpswm.system.target_position_report import (
    CameraAttempt,
    EvaluationTruth,
    ReportRun,
    ReportTask,
    TargetPositionReport,
    assess_report,
    compare_report_runs,
    report_from_view,
    summarize_reports,
    verify_report,
)

OBS = (UUID(int=20),)


def task(index=1):
    return ReportTask(
        task_id=UUID(int=index),
        scene_id="controlled-scene",
        frame_id="world-metres",
        target_description="the designated instance",
        valid_at=datetime(2026, 10, 2, tzinfo=UTC),
        initial_input_sha256="a" * 64,
        allowed_actions_sha256="b" * 64,
        action_budget=4,
        position_origin_m=(10.0, 20.0, 30.0),
    )


def view():
    # Non-diagonal precision prevents mistaking natural parameters for positions.
    j = np.eye(6) * 2
    j[0, 1] = j[1, 0] = 0.5
    mu = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    stats = ConditionalAnalyticState(
        (UUID(int=1),),
        (1.0,),
        ((1.0,),),
        (0.0,),
        tuple(map(tuple, j)),
        tuple(j @ mu),
        (UUID(int=2),),
    )
    state = TypedParticleState(
        particle_id=UUID(int=5),
        parent_particle_id=None,
        parent_revision_id=None,
        source_snapshot_id=UUID(int=4),
        event_hypothesis_id=UUID(int=6),
        revision_id=UUID(int=7),
        ordered_actor_roles=tuple(
            OrderedActorRole(role=r, actor_key="owner")
            for r in ("pickup_actor", "carrier", "placer")
        ),
        instance_association_key="controlled-instance",
        change_cause="unresolved",
        regime_decision="unresolved",
        regime_id=None,
        run_length=1,
        statistic_state_ref=stats.reference,
        ledger_lineage_ref="hybrid-ledger:" + "c" * 64,
    )
    atom = JointDecisionAtom(
        UUID(int=5), 0.6, state.model_dump_json(), (), stats, "d" * 64, "c" * 64
    )
    return JointDecisionView(UUID(int=3), UUID(int=4), UUID(int=2), (atom,), 0.4)


def report(t=None, v=None):
    return report_from_view(t or task(), v or view(), particle_id=UUID(int=5), observation_ids=OBS)


def truth(r, **changes):
    values = dict(
        task_sha256=r.task_sha256,
        report_sha256=r.digest,
        annotation_artifact_sha256="f" * 64,
        target_instance_id="actual-target",
        reported_instance_id="actual-target",
        lower_m=(10.0, 21.0, 32.0),
        upper_m=(12.0, 23.0, 34.0),
    )
    values.update(changes)
    return EvaluationTruth(**values)


def test_correlated_statistics_readout_roundtrip_and_independent_label():
    t, v = task(), view()
    r = report(t, v)
    assert r.point_m == pytest.approx((11.0, 22.0, 33.0))
    assert TargetPositionReport.model_validate_json(r.model_dump_json()) == r
    verify_report(t, v, r, observation_ids=OBS)
    score = assess_report(t, r, truth(r))
    assert score.identity_correct and score.position_correct and score.joint_success
    # The semantic hypothesis string is deliberately not the evaluator label.
    assert r.instance_hypothesis != truth(r).target_instance_id


@pytest.mark.parametrize(
    "point,identity,expected",
    [
        ((10.0, 21.0, 32.0), "actual-target", (True, True, True)),
        ((12.0, 23.0, 34.0), "actual-target", (True, True, True)),
        ((12.00001, 22.0, 33.0), "actual-target", (True, False, False)),
        ((11.0, 22.0, 33.0), "wrong-instance", (False, True, False)),
        ((11.0, 22.0, 33.0), None, (None, True, None)),
    ],
)
def test_joint_score_requires_both_actual_identity_and_geometry(point, identity, expected):
    r = report().model_copy(update={"point_m": point})
    s = assess_report(task(), r, truth(r, reported_instance_id=identity))
    assert (s.identity_correct, s.position_correct, s.joint_success) == expected


@pytest.mark.parametrize(
    "field,value",
    [
        ("point_m", (0.0, 0.0, 0.0)),
        ("observation_ids", (UUID(int=21),)),
        ("source_view_sha256", "0" * 64),
        ("instance_hypothesis", "another"),
    ],
)
def test_complete_forged_report_rejected_then_legal_retry(field, value):
    t, v, r = task(), view(), report()
    forged = TargetPositionReport.model_validate(r.model_copy(update={field: value}).model_dump())
    with pytest.raises(ValueError, match="differs"):
        verify_report(t, v, forged, observation_ids=OBS)
    verify_report(t, v, r, observation_ids=OBS)


def test_withdrawal_or_new_view_rejects_old_report():
    t, v, r = task(), view(), report()
    after = replace(v, atoms=(), unresolved_probability=1.0)
    with pytest.raises(ValueError, match="absent"):
        verify_report(t, after, r, observation_ids=())
    unknown = report_from_view(t, after, particle_id=None, observation_ids=())
    verify_report(t, after, unknown, observation_ids=())
    assert assess_report(t, unknown, None).joint_success is False


@pytest.mark.parametrize(
    "changes",
    [
        {"frame_id": "other-frame"},
        {"scene_id": "other-scene"},
        {"valid_at": datetime(2026, 10, 2, tzinfo=UTC) + timedelta(seconds=1)},
        {"action_budget": 5},
        {"allowed_actions_sha256": "0" * 64},
    ],
)
def test_other_task_frame_time_or_budget_cannot_reuse_report(changes):
    t = task().model_copy(update=changes)
    with pytest.raises(ValueError, match="another task"):
        assess_report(t, report(), truth(report()))


def test_truth_rebinding_required_and_no_truth_is_not_success():
    r = report()
    with pytest.raises(ValueError, match="does not bind"):
        assess_report(task(), r, truth(r, report_sha256="0" * 64))
    assert assess_report(task(), r, None).joint_success is None
    assert assess_report(task(), r, truth(r, reported_instance_id=None)).identity_correct is None


def test_full_manifest_denominator_retains_failures_and_missing_truth():
    tasks = tuple(task(i) for i in range(1, 5))
    reports = tuple(report(t) for t in tasks)
    rows = (
        (reports[0], truth(reports[0])),
        (None, None),
        (reports[2], None),
        (reports[3], truth(reports[3], reported_instance_id="wrong")),
    )
    result = summarize_reports(tasks, rows)
    assert result["task_count"] == 4 and result["joint_success"] == 1
    assert result["joint_success_rate"] == 0.25 and result["unadjudicated"] == 1
    with pytest.raises(ValueError, match="manifest"):
        summarize_reports(tasks, rows[:1])
    with pytest.raises(ValueError, match="manifest"):
        summarize_reports((tasks[0], tasks[0]), rows[:2])


@pytest.mark.parametrize(
    "changes",
    [
        {"lower_m": (12.0, 23.0, 34.0)},
        {"upper_m": (9.0, 20.0, 31.0)},
        {"upper_m": (float("inf"), 23.0, 34.0)},
    ],
)
def test_invalid_truth_geometry_rejected_even_if_constructed(changes):
    g = truth(report()).model_copy(update=changes)
    with pytest.raises(ValueError):
        assess_report(task(), report(), g)


def test_nan_or_unknown_with_fabricated_point_cannot_be_scored():
    for changes in ({"point_m": (float("nan"), 1.0, 2.0)}, {"status": "unknown"}):
        with pytest.raises(ValueError):
            assess_report(task(), report().model_copy(update=changes), None)


def test_unknown_hypothesis_report_can_be_verified():
    v = view()
    state = TypedParticleState.model_validate_json(v.atoms[0].state_json)
    unknown = state.model_copy(update={"instance_association_key": "unknown_instance"})
    v = replace(v, atoms=(replace(v.atoms[0], state_json=unknown.model_dump_json()),))
    r = report_from_view(task(), v, particle_id=UUID(int=5), observation_ids=OBS)
    assert r.status == "unknown" and r.point_m is None
    verify_report(task(), v, r, observation_ids=OBS)


def runs(policy, count, *, failed=False):
    return (
        ReportRun(
            task=task(),
            policy_id=policy,
            report=report(),
            stop_reason="policy_stop",
            attempts=tuple(
                CameraAttempt(
                    action_id=UUID(int=100 + i),
                    action="RotateRight",
                    degrees=1.0,
                    success=not failed,
                    elapsed_seconds=2.0,
                )
                for i in range(count)
            ),
        ),
    )


def test_paired_budget_preserves_early_stop_failures_and_overruns():
    result = compare_report_runs(
        runs("active", 1),
        runs("fixed", 4, failed=True),
        first_truth=(truth(report()),),
        second_truth=(truth(report()),),
    )
    assert result["paired_design_and_count_budget_valid"]
    assert result["groups"][1]["actions"] == 4
    assert result["groups"][1]["failed_actions"] == 4
    assert result["groups"][1]["cumulative_degrees"] == 4.0
    over = compare_report_runs(
        runs("active", 5),
        runs("fixed", 4),
        first_truth=(None,),
        second_truth=(None,),
    )
    assert over["paired_design_and_count_budget_valid"] is False
    assert over["groups"][0]["score"]["task_count"] == 1
    assert over["groups"][0]["over_budget_task_ids"] == [str(task().task_id)]


def test_paired_comparison_rejects_budget_changes_and_duplicate_dispatches():
    changed = runs("fixed", 1)[0].model_copy(
        update={
            "task": task().model_copy(update={"action_budget": 5}),
            "report": None,
        }
    )
    with pytest.raises(ValueError, match="paired tasks"):
        compare_report_runs(
            runs("active", 1), (changed,), first_truth=(None,), second_truth=(None,)
        )
    duplicate = runs("fixed", 1)[0]
    duplicate = duplicate.model_copy(update={"attempts": duplicate.attempts * 2})
    with pytest.raises(ValueError, match="duplicate physical"):
        compare_report_runs(
            runs("active", 1), (duplicate,), first_truth=(None,), second_truth=(None,)
        )
