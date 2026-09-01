"""Stratified mechanism-and-action distinguishability Gate B for Structure Two.

The v0.5 all-pairs gate treated methods from different native domains as if
every pair had to disagree on the same action stream.  That condition is not a
scientific fidelity check: unrelated methods may legitimately emit the same
action, while two differently named adapters may hide the same implementation.

v0.6 keeps the complete arm set but evaluates only preregistered, scientifically
interpretable comparison pairs.  Every arm must additionally expose observable
mechanism events.  Method labels, thresholds, or artificial output noise cannot
satisfy the mechanism-activation part of the gate.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from cpswm.system.reproducibility import content_sha256

PROTOCOL_ID = "structure-two-stratified-mechanism-action-gate-b@0.6"


@dataclass(frozen=True, slots=True)
class StratifiedArmTrace:
    arm: str
    episode_actions: tuple[tuple[str, tuple[str, ...]], ...]
    episode_mechanism_events: tuple[tuple[str, tuple[tuple[str, ...], ...]], ...]


@dataclass(frozen=True, slots=True)
class ComparisonPair:
    comparison_id: str
    domain: str
    left_arm: str
    right_arm: str
    min_action_disagreement_rate: float = 0.01


@dataclass(frozen=True, slots=True)
class MechanismRequirement:
    arm: str
    required_events: tuple[str, ...]
    min_event_step_fraction: float = 0.001
    min_event_episode_fraction: float = 0.05


def _aligned(
    trace: StratifiedArmTrace,
) -> tuple[tuple[str, tuple[str, ...], tuple[tuple[str, ...], ...]], ...]:
    action_ids = tuple(item[0] for item in trace.episode_actions)
    event_ids = tuple(item[0] for item in trace.episode_mechanism_events)
    if action_ids != event_ids:
        raise ValueError(f"arm {trace.arm} action/mechanism episode order mismatch")
    rows: list[tuple[str, tuple[str, ...], tuple[tuple[str, ...], ...]]] = []
    for (episode_id, actions), (_, events) in zip(
        trace.episode_actions, trace.episode_mechanism_events, strict=True
    ):
        if len(actions) != len(events):
            raise ValueError(f"arm {trace.arm} action/mechanism step count mismatch")
        rows.append((episode_id, actions, events))
    return tuple(rows)


def _action_disagreement(left: StratifiedArmTrace, right: StratifiedArmTrace) -> float:
    left_rows = _aligned(left)
    right_rows = _aligned(right)
    if tuple(row[0] for row in left_rows) != tuple(row[0] for row in right_rows):
        raise ValueError("comparison pair episode order mismatch")
    disagreements = 0
    total = 0
    for left_row, right_row in zip(left_rows, right_rows, strict=True):
        if len(left_row[1]) != len(right_row[1]):
            raise ValueError("comparison pair action step count mismatch")
        disagreements += sum(a != b for a, b in zip(left_row[1], right_row[1], strict=True))
        total += len(left_row[1])
    if total == 0:
        raise ValueError("comparison pair has no scored actions")
    return disagreements / total


def _mechanism_score(
    trace: StratifiedArmTrace, requirement: MechanismRequirement
) -> dict[str, Any]:
    rows = _aligned(trace)
    if not requirement.required_events:
        raise ValueError(f"arm {trace.arm} has no preregistered mechanism events")
    per_event: dict[str, dict[str, float | int | bool]] = {}
    for required in requirement.required_events:
        step_hits = 0
        episode_hits = 0
        total_steps = 0
        for _, _, step_events in rows:
            local_hits = sum(required in events for events in step_events)
            step_hits += local_hits
            episode_hits += int(local_hits > 0)
            total_steps += len(step_events)
        step_fraction = step_hits / total_steps if total_steps else 0.0
        episode_fraction = episode_hits / len(rows) if rows else 0.0
        per_event[required] = {
            "step_hits": step_hits,
            "episode_hits": episode_hits,
            "step_fraction": step_fraction,
            "episode_fraction": episode_fraction,
            "passed": (
                step_fraction >= requirement.min_event_step_fraction
                and episode_fraction >= requirement.min_event_episode_fraction
            ),
        }
    return {
        "arm": trace.arm,
        "required_events": requirement.required_events,
        "thresholds": {
            "min_event_step_fraction": requirement.min_event_step_fraction,
            "min_event_episode_fraction": requirement.min_event_episode_fraction,
        },
        "per_event": per_event,
        "passed": all(bool(item["passed"]) for item in per_event.values()),
    }


def run_stratified_gate_b(
    traces: Sequence[StratifiedArmTrace],
    *,
    expected_arms: Sequence[str],
    comparison_pairs: Sequence[ComparisonPair],
    mechanism_requirements: Sequence[MechanismRequirement],
) -> dict[str, Any]:
    """Score preregistered comparison pairs plus per-arm mechanism activation."""

    expected = tuple(expected_arms)
    if not expected or len(expected) != len(set(expected)):
        raise ValueError("expected arm set must be non-empty and unique")
    by_arm = {trace.arm: trace for trace in traces}
    if len(by_arm) != len(traces) or set(by_arm) != set(expected):
        raise ValueError("trace set must exactly match the expected arm set")
    requirements = {item.arm: item for item in mechanism_requirements}
    if len(requirements) != len(mechanism_requirements) or set(requirements) != set(expected):
        raise ValueError("every expected arm needs exactly one mechanism requirement")
    if not comparison_pairs:
        raise ValueError("at least one preregistered comparison pair is required")
    comparison_ids = [item.comparison_id for item in comparison_pairs]
    if len(comparison_ids) != len(set(comparison_ids)):
        raise ValueError("comparison ids must be unique")
    participating: set[str] = set()
    comparisons: list[dict[str, Any]] = []
    for pair in comparison_pairs:
        if (
            pair.left_arm == pair.right_arm
            or pair.left_arm not in by_arm
            or pair.right_arm not in by_arm
        ):
            raise ValueError("comparison pair names invalid arms")
        if not (0.0 < pair.min_action_disagreement_rate <= 1.0):
            raise ValueError("comparison disagreement threshold must be in (0, 1]")
        participating.update((pair.left_arm, pair.right_arm))
        rate = _action_disagreement(by_arm[pair.left_arm], by_arm[pair.right_arm])
        comparisons.append(
            {
                "comparison_id": pair.comparison_id,
                "domain": pair.domain,
                "left_arm": pair.left_arm,
                "right_arm": pair.right_arm,
                "action_disagreement_rate": rate,
                "min_action_disagreement_rate": pair.min_action_disagreement_rate,
                "passed": rate >= pair.min_action_disagreement_rate,
            }
        )
    if participating != set(expected):
        raise ValueError("every expected arm must participate in a declared comparison")
    activations = [_mechanism_score(by_arm[arm], requirements[arm]) for arm in expected]
    comparison_passed = all(bool(item["passed"]) for item in comparisons)
    mechanism_passed = all(bool(item["passed"]) for item in activations)
    report: dict[str, Any] = {
        "protocol": PROTOCOL_ID,
        "expected_arms": expected,
        "comparison_pair_results": comparisons,
        "mechanism_activation_results": activations,
        "declared_comparisons_passed": comparison_passed,
        "all_arm_mechanisms_activated": mechanism_passed,
        "gate_b_passed": comparison_passed and mechanism_passed,
        "claim_boundary": (
            "Passing establishes action distinguishability only for declared same-question "
            "comparisons and observable activation of preregistered mechanisms. It does not "
            "establish native-method fidelity or efficacy superiority."
        ),
    }
    report["content_sha256"] = content_sha256(report)
    return report


__all__ = [
    "PROTOCOL_ID",
    "ComparisonPair",
    "MechanismRequirement",
    "StratifiedArmTrace",
    "run_stratified_gate_b",
]
