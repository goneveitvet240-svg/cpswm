"""阶段 0 acceptance: the protocol is frozen, identified, and reproducible.

完成标准: "同一个事件流和同一个配置重复运行" -> identical step output.  That is
:func:`test_repeated_runs_are_step_for_step_identical`; everything else in this
file exists so that a *passing* determinism test actually means something —
a frozen label space, a pinned formula, an honest config identity, and no path
by which a label could reach a model.
"""

from __future__ import annotations

from dataclasses import fields, replace

import pytest

from cpswm.system.continual.project_one_regime_loop import HabitStateConclusion
from cpswm.system.evaluation_operations.project_one_dataset import (
    FORBIDDEN_RECORD_FIELDS,
    ProjectOneDatasetRecord,
)
from cpswm.system.evaluation_operations.project_one_methods import build_first_batch
from cpswm.system.evaluation_operations.project_one_protocol import (
    PROTOCOL_VERSION,
    SIGMOID_RESIDUAL_FLOOR,
    DecisionChainAblation,
    ProjectOneDecision,
    ProjectOneProtocolConfig,
    ProjectOneStepTrace,
    ResidualCalibration,
    SignalAblation,
    calibrated_residual,
    habit_signal,
    normalized_predictive_surprise,
    residual_severity,
)
from cpswm.system.evaluation_operations.project_one_runner import ProjectOneRunner
from cpswm.system.evaluation_operations.project_one_scenarios import LOCATIONS, build_stream


def _arms() -> tuple[object, ...]:
    return build_first_batch(
        locations=LOCATIONS,
        owner_id="owner",
        household_id="household-1",
        object_id="cup-17",
    )


# ---------------------------------------------------------------------------
# 1. The label space is exactly four outcomes, and matches the frozen spine
# ---------------------------------------------------------------------------


def test_the_decision_space_has_exactly_four_outcomes() -> None:
    assert [decision.value for decision in ProjectOneDecision] == [
        "stable",
        "insufficient_evidence",
        "short_term_disturbance",
        "habit_change",
    ]


def test_every_spine_conclusion_maps_onto_a_protocol_decision() -> None:
    """If the spine grows a fifth conclusion, this fails instead of silently coercing."""

    for conclusion in HabitStateConclusion:
        assert ProjectOneDecision.from_conclusion(conclusion).value == conclusion.value
    assert {decision.value for decision in ProjectOneDecision} == {
        conclusion.value for conclusion in HabitStateConclusion
    }


# ---------------------------------------------------------------------------
# 2. All six intermediates are recorded on every step
# ---------------------------------------------------------------------------


REQUIRED_TRACE_FIELDS = {
    "dirichlet_surprise",
    "rls_residual",
    "habit_signal",
    "change_probability",
    "ccrr_decision",
    "active_regime",
}


def test_the_trace_carries_every_required_intermediate() -> None:
    assert {field.name for field in fields(ProjectOneStepTrace)} == REQUIRED_TRACE_FIELDS


def test_the_chain_arm_emits_a_full_trace_on_every_step() -> None:
    stream, truth = build_stream("permanent_change")
    arm = _arms()[0]
    result = ProjectOneRunner().run_arm(arm, stream, truth)  # type: ignore[arg-type]
    assert result.failure is None
    assert len(result.predictions) == len(stream)
    for prediction in result.predictions:
        assert prediction.trace is not None


def test_a_trace_rejects_an_out_of_range_probability() -> None:
    with pytest.raises(ValueError, match="change_probability"):
        ProjectOneStepTrace(
            dirichlet_surprise=0.1,
            rls_residual=0.1,
            habit_signal=0.1,
            change_probability=1.5,
            ccrr_decision="stay",
            active_regime="stable",
        )


# ---------------------------------------------------------------------------
# 3. Config identity
# ---------------------------------------------------------------------------


def test_identical_configs_share_a_hash_and_different_ones_do_not() -> None:
    base = ProjectOneProtocolConfig()
    assert base.config_hash() == ProjectOneProtocolConfig().config_hash()
    assert base.config_hash() != replace(base, confirmation_window=5).config_hash()
    assert base.config_hash() != replace(base, ablation=SignalAblation.NO_RLS).config_hash()


def test_the_config_hash_covers_every_field() -> None:
    """A field that does not move the hash is a field that can drift unnoticed."""

    base = ProjectOneProtocolConfig()
    alternatives = {
        "minimum_baseline_observations": 4,
        "confirmation_window": 3,
        "habit_change_probability_threshold": 0.6,
        "transient_disturbance_probability_threshold": 0.6,
        "owner_evidence_threshold": 0.6,
        "forgetting_factor": 0.99,
        "context_confirmation_max_distance": 0.3,
        "dirichlet_surprise_weight": 0.2,
        "rls_residual_weight": 0.2,
        "rls_regularization": 2.0,
        "ablation": SignalAblation.RLS_ONLY,
        "residual_calibration": ResidualCalibration.LOGIT,
        "decision_chain_ablation": DecisionChainAblation.NO_CCRR,
        "protocol_version": "other@0.0",
    }
    assert set(alternatives) == {field.name for field in fields(ProjectOneProtocolConfig)}
    for name, value in alternatives.items():
        assert replace(base, **{name: value}).config_hash() != base.config_hash(), name


def test_every_accepted_protocol_config_is_accepted_by_the_frozen_loop() -> None:
    """The protocol must not be laxer than the thing it projects onto.

    A config this module accepts but ``PrototypeLoopConfig`` rejects would only
    move the failure to run time, in the middle of a tuning sweep.
    """

    base = ProjectOneProtocolConfig()
    for window in (2, 3, 5):
        replace(base, confirmation_window=window).loop_config()
    with pytest.raises(ValueError, match="confirmation_window"):
        replace(base, confirmation_window=1)


def test_the_protocol_config_projects_onto_the_frozen_loop_config() -> None:
    config = replace(ProjectOneProtocolConfig(), confirmation_window=4, rls_residual_weight=0.3)
    loop = config.loop_config()
    assert loop.confirmation_window == 4
    assert loop.rls_residual_weight == 0.3


def test_the_protocol_version_is_stamped_on_a_run() -> None:
    stream, truth = build_stream("stable_habit")
    report = ProjectOneRunner().run(
        streams=[(stream, truth)],
        build_methods=lambda: _arms()[:1],  # type: ignore[arg-type,return-value]
    )
    assert report.protocol_version == PROTOCOL_VERSION


# ---------------------------------------------------------------------------
# 4. Label isolation
# ---------------------------------------------------------------------------


def test_a_dataset_record_carries_no_truth_field() -> None:
    names = {field.name for field in fields(ProjectOneDatasetRecord)}
    assert not names & FORBIDDEN_RECORD_FIELDS


def test_a_method_never_receives_the_truth_set() -> None:
    """The runner's per-event call takes a record and nothing else."""

    import inspect

    from cpswm.system.evaluation_operations.project_one_methods import CoreHabitChainMethod

    signature = inspect.signature(CoreHabitChainMethod.observe)
    assert list(signature.parameters) == ["self", "event"]
    annotation = signature.parameters["event"].annotation
    assert "TruthSet" not in str(annotation)


# ---------------------------------------------------------------------------
# 5. The pinned signal formulas
# ---------------------------------------------------------------------------


def test_uniform_probability_maps_to_zero_surprise_at_any_cardinality() -> None:
    for cardinality in (2, 4, 8, 37):
        assert normalized_predictive_surprise(1.0 / cardinality, cardinality) == pytest.approx(
            0.0, abs=1e-12
        )


def test_surprise_is_monotone_below_uniform() -> None:
    values = [normalized_predictive_surprise(p, 4) for p in (0.25, 0.10, 0.02, 0.001)]
    assert values == sorted(values)
    assert values[-1] < 1.0, "surprise must not clip flat at the top of its range"


def test_residual_severity_is_the_pinned_quadratic() -> None:
    assert residual_severity(0.0) == 0.0
    assert residual_severity(1.0) == 1.0
    assert residual_severity(0.5) == pytest.approx(0.75)


def test_habit_signal_needs_a_move_and_a_model_error_together() -> None:
    """A move on its own, with a perfectly predicted location, stays at the floor."""

    without_move = habit_signal(
        habit_transition=0.0,
        dirichlet_surprise=0.0,
        rls_residual=0.0,
        dirichlet_surprise_weight=0.1,
        rls_residual_weight=0.1,
    )
    move_but_no_error = habit_signal(
        habit_transition=1.0,
        dirichlet_surprise=0.0,
        rls_residual=0.0,
        dirichlet_surprise_weight=0.1,
        rls_residual_weight=0.1,
    )
    move_and_error = habit_signal(
        habit_transition=1.0,
        dirichlet_surprise=0.8,
        rls_residual=0.0,
        dirichlet_surprise_weight=0.1,
        rls_residual_weight=0.1,
    )
    assert without_move == 0.0
    assert move_but_no_error == 0.0
    assert move_and_error == pytest.approx(0.8)


def test_the_weighted_floors_are_independent_guardrails() -> None:
    """A persistent model error is visible even with no move at all."""

    assert habit_signal(
        habit_transition=0.0,
        dirichlet_surprise=0.9,
        rls_residual=0.0,
        dirichlet_surprise_weight=0.1,
        rls_residual_weight=0.1,
    ) == pytest.approx(0.09)


def test_the_as_is_calibration_reproduces_the_shipped_residual_floor() -> None:
    perfect_score = 1.0 - SIGMOID_RESIDUAL_FLOOR
    assert calibrated_residual(perfect_score, ResidualCalibration.AS_IS) == pytest.approx(
        SIGMOID_RESIDUAL_FLOOR
    )
    assert calibrated_residual(perfect_score, ResidualCalibration.LOGIT) == pytest.approx(
        0.0, abs=1e-3
    )


# ---------------------------------------------------------------------------
# 6. 完成标准: step-for-step determinism
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("scenario", ["stable_habit", "permanent_change", "recurring_regime"])
def test_repeated_runs_are_step_for_step_identical(scenario: str) -> None:
    stream, truth = build_stream(scenario)
    runner = ProjectOneRunner()

    first = runner.run(streams=[(stream, truth)], build_methods=_arms)  # type: ignore[arg-type]
    second = runner.run(streams=[(stream, truth)], build_methods=_arms)  # type: ignore[arg-type]

    assert [result.method for result in first.results] == [
        result.method for result in second.results
    ]
    for left, right in zip(first.results, second.results, strict=True):
        assert left.failure is None and right.failure is None
        assert len(left.predictions) == len(right.predictions)
        for step_left, step_right in zip(left.predictions, right.predictions, strict=True):
            assert step_left.event_id == step_right.event_id
            assert step_left.decision is step_right.decision
            assert step_left.change_probability == step_right.change_probability
            assert step_left.habit_signal == step_right.habit_signal
            assert step_left.rls_residual == step_right.rls_residual
            assert step_left.predicted_regime_id == step_right.predicted_regime_id
            assert dict(step_left.predicted_location_probabilities) == dict(
                step_right.predicted_location_probabilities
            )
        assert left.metrics == right.metrics


def test_the_same_stream_yields_the_same_manifest_hash() -> None:
    first, _ = build_stream("gradual_drift")
    second, _ = build_stream("gradual_drift")
    assert first.manifest.content_hash == second.manifest.content_hash
