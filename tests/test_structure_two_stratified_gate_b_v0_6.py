from __future__ import annotations

import pytest

from cpswm.system.evaluation_operations.structure_two_stratified_gate_b_v0_6 import (
    ComparisonPair,
    MechanismRequirement,
    StratifiedArmTrace,
    run_stratified_gate_b,
)


def _trace(arm: str, actions: tuple[str, ...], event: str) -> StratifiedArmTrace:
    return StratifiedArmTrace(
        arm=arm,
        episode_actions=(("episode-1", actions),),
        episode_mechanism_events=(("episode-1", tuple((event,) for _ in actions)),),
    )


def _requirement(arm: str, event: str) -> MechanismRequirement:
    return MechanismRequirement(
        arm=arm,
        required_events=(event,),
        min_event_step_fraction=0.25,
        min_event_episode_fraction=1.0,
    )


def test_unrelated_identical_arms_do_not_fail_a_stratified_gate() -> None:
    traces = (
        _trace("candidate", ("a", "a", "a", "a"), "candidate_update"),
        _trace("event_baseline", ("b", "a", "a", "a"), "global_map"),
        _trace("search_baseline", ("a", "a", "a", "a"), "cost_aware_search"),
    )
    report = run_stratified_gate_b(
        traces,
        expected_arms=("candidate", "event_baseline", "search_baseline"),
        comparison_pairs=(
            ComparisonPair("event", "event inference", "candidate", "event_baseline", 0.25),
            ComparisonPair("search", "object search", "candidate", "search_baseline", 0.25),
        ),
        mechanism_requirements=(
            _requirement("candidate", "candidate_update"),
            _requirement("event_baseline", "global_map"),
            _requirement("search_baseline", "cost_aware_search"),
        ),
    )
    assert report["gate_b_passed"] is False
    by_id = {item["comparison_id"]: item for item in report["comparison_pair_results"]}
    assert by_id["event"]["passed"] is True
    assert by_id["search"]["passed"] is False


def test_identical_arms_outside_a_declared_pair_are_not_compared() -> None:
    traces = (
        _trace("candidate", ("a", "a", "a", "a"), "candidate_update"),
        _trace("left", ("b", "a", "a", "a"), "left_core"),
        _trace("right", ("b", "a", "a", "a"), "right_core"),
    )
    report = run_stratified_gate_b(
        traces,
        expected_arms=("candidate", "left", "right"),
        comparison_pairs=(
            ComparisonPair("left", "domain-left", "candidate", "left", 0.25),
            ComparisonPair("right", "domain-right", "candidate", "right", 0.25),
        ),
        mechanism_requirements=(
            _requirement("candidate", "candidate_update"),
            _requirement("left", "left_core"),
            _requirement("right", "right_core"),
        ),
    )
    assert report["gate_b_passed"] is True


def test_missing_mechanism_activation_fails_even_when_actions_differ() -> None:
    traces = (
        _trace("candidate", ("a", "a", "a", "a"), "candidate_update"),
        _trace("baseline", ("b", "b", "b", "b"), "wrapper_called"),
    )
    report = run_stratified_gate_b(
        traces,
        expected_arms=("candidate", "baseline"),
        comparison_pairs=(ComparisonPair("pair", "one-domain", "candidate", "baseline", 0.25),),
        mechanism_requirements=(
            _requirement("candidate", "candidate_update"),
            _requirement("baseline", "official_core_executed"),
        ),
    )
    assert report["declared_comparisons_passed"] is True
    assert report["all_arm_mechanisms_activated"] is False
    assert report["gate_b_passed"] is False


def test_trace_alignment_mismatch_fails_closed() -> None:
    broken = StratifiedArmTrace(
        arm="broken",
        episode_actions=(("episode-1", ("a",)),),
        episode_mechanism_events=(("episode-2", (("core",),)),),
    )
    with pytest.raises(ValueError, match="episode order mismatch"):
        run_stratified_gate_b(
            (broken, _trace("other", ("b",), "other_core")),
            expected_arms=("broken", "other"),
            comparison_pairs=(ComparisonPair("pair", "domain", "broken", "other"),),
            mechanism_requirements=(
                _requirement("broken", "core"),
                _requirement("other", "other_core"),
            ),
        )
