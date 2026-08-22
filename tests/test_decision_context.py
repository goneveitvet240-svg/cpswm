"""DecisionContext enforced consistency + invalidation (结构二 §4.6, 总纲 §2.12).

Rebuilt 2026-08-22 to the review gate: mandatory consistency fields + content
hash + valid_time/staleness + enum cause + immutable versions + binding
household/session/trace checks + snapshot-isolation relevant-change detection.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from cpswm.contracts import (
    AttributedCause,
    DecisionContext,
    DecisionContextBinding,
    DecisionSurface,
    MapConsistencyRevisions,
    RelevantChange,
    ValidTimeInterval,
    detect_relevant_change,
)

NOW = datetime(2026, 8, 22, 9, 0, tzinfo=UTC)


def _revisions(**overrides):
    base = {
        "belief_snapshot_id": uuid4(),
        "projection_id": uuid4(),
        "projection_version": 3,
        "static_map_revision": 10,
        "dynamic_map_revision": 42,
        "event_history_revision": 7,
        "input_watermark": 100,
    }
    base.update(overrides)
    return MapConsistencyRevisions(**base)


def _context(revisions=None, **overrides):
    fields = {
        "decision_id": uuid4(),
        "decision_time": NOW,
        "valid_time": ValidTimeInterval(start=NOW, end=NOW + timedelta(minutes=5)),
        "staleness_budget_seconds": 120.0,
        "revisions": revisions or _revisions(),
        "attributed_cause": AttributedCause.HABIT,
        "authorization_scope_id": uuid4(),
        "habit_regime_model_version": "hier-dirichlet@0.1",
        "model_versions": (("cf_bocpd", "joint-cause-factorized-bocpd@0.3"),),
        "code_version": "git:deadbeef",
        "rationale": "habit regime change attributed and consolidated",
    }
    fields.update(overrides)
    return DecisionContext.create(**fields)


# --- P0: consistency fields are mandatory + hash-bound ------------------------


def test_context_requires_all_consistency_fields():
    # Missing revisions / authorization / model version -> cannot construct.
    with pytest.raises(ValidationError):
        DecisionContext.create(
            decision_id=uuid4(),
            decision_time=NOW,
            valid_time=ValidTimeInterval(start=NOW),
            staleness_budget_seconds=1.0,
            rationale="x",
            code_version="git:x",
            # no revisions / authorization_scope_id / habit_regime_model_version / model_versions
        )


def test_tampered_persisted_context_is_rejected_on_reload():
    context = _context()
    assert context.verify_hash()
    # Edit a persisted context's content but keep its old hash -> reload rejects.
    tampered = context.model_dump(mode="json")
    tampered["rationale"] = "silently changed"
    with pytest.raises(ValidationError, match="context_hash"):
        DecisionContext.model_validate(tampered)
    # A clean round-trip reloads fine.
    assert DecisionContext.model_validate(context.model_dump(mode="json")).verify_hash()


def test_attributed_cause_rejects_free_text():
    with pytest.raises(ValidationError):
        _context(attributed_cause="whatever-i-want")


def test_model_versions_must_be_sorted_and_unique():
    with pytest.raises(ValidationError, match="sorted"):
        _context(model_versions=(("z", "1"), ("a", "1")))
    with pytest.raises(ValidationError, match="unique"):
        _context(model_versions=(("a", "1"), ("a", "2")))


def test_naive_decision_time_rejected():
    with pytest.raises(ValidationError, match="decision_time"):
        _context(decision_time=datetime(2026, 8, 22, 9, 0))


# --- binding: household/session/trace consistency ----------------------------


def test_binding_requires_matching_household_session_trace(metadata_factory):
    metadata = metadata_factory(schema_name="cpswm.DecisionContextBinding")
    ok = DecisionContextBinding(
        metadata=metadata,
        surface=DecisionSurface.TASK_REQUEST,
        subject_record_id=uuid4(),
        subject_household_id=metadata.household_id,
        subject_session_id=metadata.session_id,
        subject_trace_id=metadata.trace_id,
        decision_context=_context(),
    )
    assert ok.surface is DecisionSurface.TASK_REQUEST

    with pytest.raises(ValidationError, match="household"):
        DecisionContextBinding(
            metadata=metadata,
            surface=DecisionSurface.MAP_SNAPSHOT,
            subject_record_id=uuid4(),
            subject_household_id=uuid4(),  # mismatch
            subject_session_id=metadata.session_id,
            subject_trace_id=metadata.trace_id,
            decision_context=_context(),
        )


# --- snapshot-isolation relevant-change detection ----------------------------


def test_target_object_move_forces_replan():
    context = _context()
    decision = detect_relevant_change(
        context,
        current=context.revisions,
        target_object_moved=True,
        robot_pose_graph_corrected=False,
        planned_path_blocked=False,
        only_irrelevant_updates=False,
        elapsed_seconds=1.0,
    )
    assert decision is RelevantChange.REPLAN


def test_pose_correction_and_path_block_force_replan():
    context = _context()
    for pose, path in ((True, False), (False, True)):
        assert (
            detect_relevant_change(
                context,
                current=context.revisions,
                target_object_moved=False,
                robot_pose_graph_corrected=pose,
                planned_path_blocked=path,
                only_irrelevant_updates=False,
                elapsed_seconds=1.0,
            )
            is RelevantChange.REPLAN
        )


def test_irrelevant_dynamic_update_allows_continue():
    context = _context()
    current = _revisions(
        belief_snapshot_id=context.revisions.belief_snapshot_id,
        projection_id=context.revisions.projection_id,
        static_map_revision=context.revisions.static_map_revision,
        dynamic_map_revision=context.revisions.dynamic_map_revision + 1,  # bumped
    )
    decision = detect_relevant_change(
        context,
        current=current,
        target_object_moved=False,
        robot_pose_graph_corrected=False,
        planned_path_blocked=False,
        only_irrelevant_updates=True,  # only unrelated rooms/objects changed
        elapsed_seconds=1.0,
    )
    assert decision is RelevantChange.CONTINUE


def test_relevant_dynamic_update_forces_replan():
    context = _context()
    current = _revisions(
        belief_snapshot_id=context.revisions.belief_snapshot_id,
        projection_id=context.revisions.projection_id,
        static_map_revision=context.revisions.static_map_revision,
        dynamic_map_revision=context.revisions.dynamic_map_revision + 1,
    )
    assert (
        detect_relevant_change(
            context,
            current=current,
            target_object_moved=False,
            robot_pose_graph_corrected=False,
            planned_path_blocked=False,
            only_irrelevant_updates=False,  # a relevant object changed
            elapsed_seconds=1.0,
        )
        is RelevantChange.REPLAN
    )


def test_staleness_budget_exceeded_forces_cancel():
    context = _context(staleness_budget_seconds=30.0)
    decision = detect_relevant_change(
        context,
        current=context.revisions,
        target_object_moved=True,  # even a replan trigger is overridden by staleness
        robot_pose_graph_corrected=False,
        planned_path_blocked=False,
        only_irrelevant_updates=False,
        elapsed_seconds=45.0,
    )
    assert decision is RelevantChange.CANCEL


def test_unchanged_snapshot_continues():
    context = _context()
    assert (
        detect_relevant_change(
            context,
            current=context.revisions,
            target_object_moved=False,
            robot_pose_graph_corrected=False,
            planned_path_blocked=False,
            only_irrelevant_updates=False,
            elapsed_seconds=1.0,
        )
        is RelevantChange.CONTINUE
    )
