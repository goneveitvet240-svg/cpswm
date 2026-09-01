"""Unit tests for the method-free benchmark-target gates."""

from __future__ import annotations

import pytest

from cpswm.system.evaluation_operations.task_nontriviality_gates import (
    ArmPredictionTrace,
    GateAThresholds,
    TargetStep,
    TargetStream,
    run_gate_a,
    run_gate_b,
    summarise_gate_reports,
)

CANDIDATES = ("a", "b", "c")


def _sticky_stream(stream_id: str, moves: list[tuple[str, bool, bool]]) -> TargetStream:
    """Build a stream whose target follows 'adopt on trigger, else persist'."""

    steps: list[TargetStep] = []
    current = CANDIDATES[0]
    for index, (observed, trigger, visible) in enumerate(moves):
        if trigger:
            current = observed
        steps.append(
            TargetStep(
                context_key=f"ctx{index % 2}",
                candidates=CANDIDATES,
                observed_value=observed,
                visible_trigger=visible,
                target=current,
                true_trigger=trigger,
            )
        )
    return TargetStream(stream_id=stream_id, stratum="s", steps=tuple(steps))


def test_gate_a_fails_a_target_that_is_its_own_update_law() -> None:
    moves = [("a", True, True), ("b", False, False), ("b", True, True), ("c", False, False)] * 4
    report = run_gate_a([_sticky_stream("e1", moves)], target_name="sticky")
    assert report["gate_a_passed"] is False
    assert report["criteria"]["a1_trivial_ceiling_leaves_headroom"] is False
    assert report["criteria"]["a2_update_law_is_not_trivial"] is False
    assert report["trivial_ceiling_error"] == pytest.approx(0.0)
    conditional = report["conditional_update_law_recurrence"]
    assert conditional["observed_step_rate"] == pytest.approx(1.0)


def test_gate_a_passes_a_target_with_dynamics_the_rules_cannot_reach() -> None:
    # The target alternates independently of any observation or trigger.
    steps = tuple(
        TargetStep(
            context_key=f"ctx{index % 3}",
            candidates=CANDIDATES,
            observed_value=CANDIDATES[index % 3],
            visible_trigger=False,
            target=CANDIDATES[(index * 2 + 1) % 3],
            true_trigger=False,
        )
        for index in range(60)
    )
    report = run_gate_a(
        [TargetStream(stream_id="e1", stratum="s", steps=steps)],
        target_name="rotating",
    )
    assert report["criteria"]["a1_trivial_ceiling_leaves_headroom"] is True
    assert report["criteria"]["a2_update_law_is_not_trivial"] is True


def test_gate_a_reports_trigger_inference_share_when_the_trigger_is_hidden() -> None:
    # Same law, but the visible trigger is always wrong, so inference matters.
    moves = [("a", True, False), ("b", False, True), ("c", True, False)] * 8
    report = run_gate_a([_sticky_stream("e1", moves)], target_name="hidden-trigger")
    assert report["update_law_error_with_true_trigger"] == pytest.approx(0.0)
    assert report["trivial_ceiling_error"] > 0.0
    assert report["trigger_inference_share_of_remaining_error"] == pytest.approx(1.0)


def test_gate_a_classification_kind_binds_only_headroom_and_lookup() -> None:
    steps = tuple(
        TargetStep(
            context_key="c",
            candidates=("x", "y"),
            observed_value="bucket",
            visible_trigger=False,
            target="x" if index % 2 else "y",
            true_trigger=False,
        )
        for index in range(40)
    )
    report = run_gate_a(
        [TargetStream(stream_id="e1", stratum="s", steps=steps)],
        target_name="balanced-labels",
        target_kind="classification",
    )
    assert report["binding_criteria"] == [
        "a1_trivial_ceiling_leaves_headroom",
        "a5_target_is_not_a_single_feature_lookup",
    ]
    assert report["gate_a_passed"] is True


def test_gate_a_rejects_an_unknown_target_kind() -> None:
    stream = _sticky_stream("e1", [("a", True, True)])
    with pytest.raises(ValueError):
        run_gate_a([stream], target_name="x", target_kind="nonsense")


def test_gate_a_thresholds_are_explicit_and_reported() -> None:
    stream = _sticky_stream("e1", [("a", True, True), ("b", False, False)] * 6)
    limits = GateAThresholds(min_trivial_ceiling_error=0.0, max_law_recurrence=1.0)
    report = run_gate_a([stream], target_name="x", thresholds=limits)
    assert report["thresholds"]["min_trivial_ceiling_error"] == 0.0
    assert report["criteria"]["a1_trivial_ceiling_leaves_headroom"] is True


def test_gate_b_detects_arms_with_identical_prediction_sequences() -> None:
    shared = (("ep1", ("a>b", "b>c")),)
    report = run_gate_b(
        [
            ArmPredictionTrace(arm="left", episode_predictions=shared),
            ArmPredictionTrace(arm="right", episode_predictions=shared),
            ArmPredictionTrace(arm="other", episode_predictions=(("ep1", ("a>b", "c>c")),)),
        ]
    )
    assert report["gate_b_passed"] is False
    assert report["identical_arm_groups"] == [["left", "right"]]
    assert report["distinguishable_arm_count"] == 2
    assert report["pairwise_identical"]["left|right"] is True
    assert report["pairwise_identical"]["other|right"] is False


def test_gate_b_passes_when_every_arm_differs() -> None:
    report = run_gate_b(
        [
            ArmPredictionTrace(arm="left", episode_predictions=(("ep1", ("a>b",)),)),
            ArmPredictionTrace(arm="right", episode_predictions=(("ep1", ("b>a",)),)),
        ]
    )
    assert report["gate_b_passed"] is True


def test_gate_b_rejects_a_one_token_difference_below_a_positive_threshold() -> None:
    report = run_gate_b(
        [
            ArmPredictionTrace(
                arm="left",
                episode_predictions=(("e1", tuple("a" for _ in range(100))),),
            ),
            ArmPredictionTrace(
                arm="right",
                episode_predictions=(("e1", ("b", *("a" for _ in range(99)))),),
            ),
        ],
        min_pairwise_prediction_disagreement_rate=0.02,
        min_episode_fraction_with_multiple_arm_trajectories=1.0,
    )
    assert report["criteria"]["b1_no_two_arms_produce_identical_predictions"] is True
    assert report["criteria"]["b2_every_arm_pair_has_preregistered_disagreement"] is False
    assert report["gate_b_passed"] is False


def test_gate_b_requires_differences_to_cover_enough_episodes() -> None:
    report = run_gate_b(
        [
            ArmPredictionTrace(
                arm="left",
                episode_predictions=(("e1", ("a",)), ("e2", ("a",))),
            ),
            ArmPredictionTrace(
                arm="right",
                episode_predictions=(("e1", ("b",)), ("e2", ("a",))),
            ),
        ],
        min_pairwise_prediction_disagreement_rate=0.1,
        min_episode_fraction_with_multiple_arm_trajectories=0.75,
    )
    assert report["minimum_pairwise_prediction_disagreement_rate"] == 0.5
    assert report["episode_fraction_with_multiple_arm_trajectories"] == 0.5
    assert (
        report["criteria"]["b3_multiple_arm_trajectories_cover_preregistered_episode_fraction"]
        is False
    )
    assert report["gate_b_passed"] is False
    assert report["identical_arm_groups"] == []


def test_gate_b_requires_at_least_two_arms() -> None:
    with pytest.raises(ValueError):
        run_gate_b([ArmPredictionTrace(arm="only", episode_predictions=())])


def test_gate_a_requires_at_least_one_stream() -> None:
    with pytest.raises(ValueError):
        run_gate_a([], target_name="x")


def test_summary_hash_is_deterministic_and_excludes_itself() -> None:
    payload = {"a": {"x": 1}, "b": [1, 2, 3]}
    first = summarise_gate_reports(payload)
    second = summarise_gate_reports(payload)
    assert first["content_sha256"] == second["content_sha256"]
    assert summarise_gate_reports(first)["content_sha256"] == first["content_sha256"]
