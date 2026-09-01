"""Canonical validation for the Structure-Two Gate B v0.6 DRAFT."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from cpswm.system.evaluation_operations.structure_two_stratified_gate_b_v0_6 import (
    ComparisonPair,
    MechanismRequirement,
)

PROTOCOL_ID = "structure-two-stratified-mechanism-action-gate-b@0.6"
EXPECTED_ARMS = (
    "corrected_amg",
    "o_star_matched",
    "sequential_no_consolidation",
    "active_dreaming_matched",
    "auto_dreamer_matched",
    "trustmem_matched",
    "brainctl_matched",
    "care_no_action_regret",
    "care_wm",
    "full_rerun",
)
CANONICAL_MECHANISM_EVENTS: Mapping[str, tuple[str, ...]] = {
    "corrected_amg": ("global_multi_event_map_inference",),
    "o_star_matched": (
        "dirichlet_hit_or_miss_update",
        "stay_leak_transition",
        "cost_aware_search",
    ),
    "sequential_no_consolidation": ("typed_particle_update_without_consolidation",),
    "active_dreaming_matched": (
        "failure_clustered",
        "counterfactual_scenario_executed_with_attested_receipt",
        "semantic_rule_committed_after_attested_execution",
    ),
    "auto_dreamer_matched": (
        "offline_region_selected",
        "provenance_trajectory_inspected",
        "replacement_set_committed",
    ),
    "trustmem_matched": (
        "coverage_verified",
        "preservation_verified",
        "faithfulness_verified",
    ),
    "brainctl_matched": (
        "source_trust_scored",
        "two_stage_write_gate_executed",
        "memory_tier_routed",
    ),
    "care_no_action_regret": ("confidence_only_reversible_escrow",),
    "care_wm": ("future_action_regret_decision", "reversible_ledger_update"),
    "full_rerun": ("complete_visible_history_recomputed",),
}
CANONICAL_COMPONENT_IDS: Mapping[str, str] = {
    "corrected_amg": "corrected_amg:reference-core@0.6",
    "o_star_matched": "o_star_matched:reference-core@0.6",
    "sequential_no_consolidation": "sequential_no_consolidation:core@0.6",
    "active_dreaming_matched": "active_dreaming_matched:reference-core@0.6",
    "auto_dreamer_matched": "auto_dreamer_matched:reference-core@0.6",
    "trustmem_matched": "trustmem_matched:reference-core@0.6",
    "brainctl_matched": "brainctl_matched:reference-core@0.6",
    "care_no_action_regret": "care_no_action_regret:core@0.6",
    "care_wm": "care_wm:core@0.6",
    "full_rerun": "full_rerun:core@0.6",
}
CANONICAL_COMPARISONS: Mapping[str, tuple[str, str]] = {
    "event-inference-adaptation": (
        "corrected_amg",
        "hidden-event and actor-attribution action adaptation",
    ),
    "object-search-adaptation": (
        "o_star_matched",
        "embodied object-search action adaptation",
    ),
    "no-consolidation-ablation": (
        "sequential_no_consolidation",
        "reversible consolidation ablation",
    ),
    "active-dreaming-adaptation": (
        "active_dreaming_matched",
        "failure-driven memory-consolidation adaptation",
    ),
    "auto-dreamer-adaptation": (
        "auto_dreamer_matched",
        "offline memory-consolidation adaptation",
    ),
    "trustmem-adaptation": (
        "trustmem_matched",
        "verified memory-transition adaptation",
    ),
    "brainctl-adaptation": (
        "brainctl_matched",
        "memory-admission and lifecycle-control adaptation",
    ),
    "action-regret-ablation": (
        "care_no_action_regret",
        "embodied action-regret decision ablation",
    ),
    "full-rerun-control": (
        "full_rerun",
        "incremental reversible update versus complete replay",
    ),
}
CANONICAL_COMPARISON_IDS = frozenset(CANONICAL_COMPARISONS)
MIN_ACTION_DISAGREEMENT_RATE = 0.01
MIN_EVENT_STEP_FRACTION = 0.001
MIN_EVENT_EPISODE_FRACTION = 0.05


def validate_structure_two_gate_b_v0_6_draft(
    payload: Mapping[str, Any],
) -> tuple[tuple[ComparisonPair, ...], tuple[MechanismRequirement, ...]]:
    if payload.get("protocol") != PROTOCOL_ID:
        raise ValueError("v0.6 Gate B protocol mismatch")
    if payload.get("status") != "DEVELOPMENT_NOT_FROZEN":
        raise ValueError("v0.6 DRAFT has an invalid development status")
    if tuple(payload.get("expected_arms", ())) != EXPECTED_ARMS:
        raise ValueError("v0.6 DRAFT changed or reordered the complete ten-arm set")
    rows = payload.get("comparison_pairs")
    if not isinstance(rows, list):
        raise ValueError("v0.6 DRAFT comparison pairs are missing")
    ids = {str(item.get("comparison_id")) for item in rows if isinstance(item, dict)}
    if len(rows) != len(CANONICAL_COMPARISON_IDS) or ids != CANONICAL_COMPARISON_IDS:
        raise ValueError("v0.6 DRAFT comparison set is incomplete or changed")
    comparisons: list[ComparisonPair] = []
    compared_arms: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("v0.6 DRAFT comparison row is invalid")
        left = str(row.get("left_arm"))
        right = str(row.get("right_arm"))
        comparison_id = str(row.get("comparison_id"))
        expected_right, expected_domain = CANONICAL_COMPARISONS[comparison_id]
        if left != "care_wm" or right != expected_right or row.get("domain") != expected_domain:
            raise ValueError("v0.6 DRAFT changed a canonical comparison relation")
        compared_arms.add(right)
        threshold = float(row.get("min_action_disagreement_rate", -1.0))
        if threshold != MIN_ACTION_DISAGREEMENT_RATE:
            raise ValueError("v0.6 DRAFT action-disagreement threshold changed")
        comparisons.append(
            ComparisonPair(
                comparison_id=comparison_id,
                domain=expected_domain,
                left_arm=left,
                right_arm=right,
                min_action_disagreement_rate=threshold,
            )
        )
    if compared_arms != set(EXPECTED_ARMS) - {"care_wm"}:
        raise ValueError("v0.6 DRAFT does not compare every non-candidate arm")
    raw_events = payload.get("mechanism_requirements")
    if not isinstance(raw_events, dict) or set(raw_events) != set(EXPECTED_ARMS):
        raise ValueError("v0.6 DRAFT mechanism arm set is incomplete")
    for arm, expected_events in CANONICAL_MECHANISM_EVENTS.items():
        if tuple(raw_events.get(arm, ())) != expected_events:
            raise ValueError(f"v0.6 DRAFT changed canonical mechanism events for {arm}")
    thresholds = payload.get("mechanism_activation_thresholds")
    if not isinstance(thresholds, dict) or (
        float(thresholds.get("min_event_step_fraction", -1.0)) != MIN_EVENT_STEP_FRACTION
        or float(thresholds.get("min_event_episode_fraction", -1.0)) != MIN_EVENT_EPISODE_FRACTION
    ):
        raise ValueError("v0.6 DRAFT mechanism activation thresholds changed")
    requirements = tuple(
        MechanismRequirement(
            arm=arm,
            required_events=CANONICAL_MECHANISM_EVENTS[arm],
            min_event_step_fraction=MIN_EVENT_STEP_FRACTION,
            min_event_episode_fraction=MIN_EVENT_EPISODE_FRACTION,
        )
        for arm in EXPECTED_ARMS
    )
    policy = payload.get("external_fidelity_policy")
    if (
        not isinstance(policy, dict)
        or policy.get("protocol") != "structure-two-external-adapter-fidelity-gate@0.2"
        or not all(
            policy.get(key) is True
            for key in (
                "native_reproduction_required",
                "cross_domain_adaptation_contract_required",
                "independent_reviewer_attestation_required",
                "gate_b_pass_does_not_authorize_external_method_efficacy",
            )
        )
    ):
        raise ValueError("v0.6 DRAFT weakened the external fidelity policy")
    return tuple(comparisons), requirements


def load_structure_two_gate_b_v0_6_draft(
    path: Path,
) -> tuple[dict[str, Any], tuple[ComparisonPair, ...], tuple[MechanismRequirement, ...]]:
    payload = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    comparisons, requirements = validate_structure_two_gate_b_v0_6_draft(payload)
    return payload, comparisons, requirements


__all__ = [
    "CANONICAL_COMPARISONS",
    "CANONICAL_COMPARISON_IDS",
    "CANONICAL_COMPONENT_IDS",
    "CANONICAL_MECHANISM_EVENTS",
    "EXPECTED_ARMS",
    "MIN_ACTION_DISAGREEMENT_RATE",
    "MIN_EVENT_EPISODE_FRACTION",
    "MIN_EVENT_STEP_FRACTION",
    "PROTOCOL_ID",
    "load_structure_two_gate_b_v0_6_draft",
    "validate_structure_two_gate_b_v0_6_draft",
]
