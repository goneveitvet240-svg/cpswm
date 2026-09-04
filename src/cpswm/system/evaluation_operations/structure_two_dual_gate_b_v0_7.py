"""Invalidated historical dual-readout Gate B protocol for Structure Two.

Gate B v0.7 is deliberately conjunctive: a declared comparison must expose a
material difference in a canonical belief distribution *and* in the action
policy/selected action, while every arm must execute its registered mechanism.

This module is retained only for diagnostic and historical-reproduction use.
Gate B v0.7 was invalidated on 2026-09-05 and superseded for every future run by
the comparator-typed v0.8 protocol.  No v0.7 result may become authorization.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from itertools import product
from pathlib import Path
from typing import Any, Final, Literal, cast

from cpswm.system.reproducibility import content_sha256

PROTOCOL_ID: Final = "structure-two-stratified-mechanism-dual-readout-gate-b@0.7"
PROTOCOL_STATUS: Final = "INVALIDATED_SUPERSEDED_FOR_FUTURE"
SUPERSEDED_BY_PROTOCOL_ID: Final = "structure-two-comparator-typed-dual-gate-b@0.8"
BELIEF_SCHEMA_ID: Final = "structure-two-common-joint-belief-readout@0.7"
ACTION_SCHEMA_ID: Final = "structure-two-common-action-policy-readout@0.7"
PROBABILITY_NORMALIZATION_TOLERANCE: Final = 1e-9
NUMERICAL_NOISE_FLOOR: Final = 1e-6

MIN_BELIEF_STEP_TV: Final = 0.01
MIN_MEAN_BELIEF_TV: Final = 0.01
MIN_BELIEF_MATERIAL_STEP_FRACTION: Final = 0.05
MIN_ACTION_STEP_TV: Final = 0.01
MIN_MEAN_ACTION_TV: Final = 0.01
MIN_ACTION_MATERIAL_STEP_FRACTION: Final = 0.01
MIN_SELECTED_ACTION_DISAGREEMENT_RATE: Final = 0.01
MIN_MECHANISM_STEP_FRACTION: Final = 0.001
MIN_MECHANISM_EPISODE_FRACTION: Final = 0.05

BELIEF_ONTOLOGY_AXES: Final[Mapping[str, tuple[str, ...]]] = {
    "location": tuple(f"location_{index}" for index in range(6)),
    "instance_identity": ("target_instance", "decoy_instance", "unknown_instance"),
    "object_state": ("stationary", "in_use", "carried", "stored"),
    "responsible_actor": ("owner", "family", "guest", "robot", "unknown"),
    "event_class": (
        "direct_observation",
        "pickup_carry_place",
        "pickup_carry_handoff_place",
        "other_hidden_event",
    ),
    "regime_state": ("stay", "create", "reactivate"),
    "change_cause": ("observation", "actor", "identity", "habit", "noise"),
}


def _belief_support() -> tuple[str, ...]:
    axis_names = tuple(BELIEF_ONTOLOGY_AXES)
    labels = [
        "resolved|"
        + "|".join(f"{name}={value}" for name, value in zip(axis_names, values, strict=True))
        for values in product(*(BELIEF_ONTOLOGY_AXES[name] for name in axis_names))
    ]
    labels.append("unresolved")
    return tuple(sorted(labels))


BELIEF_SUPPORT: Final = _belief_support()
ACTION_ONTOLOGY: Final[Mapping[str, tuple[str, ...]]] = {
    "put_back_location": tuple(
        f"put_back:location_{location}:responsible_{actor}"
        for location in range(6)
        for actor in ("owner", "family", "guest", "robot", "unknown")
    ),
    "search_location": tuple(f"search:location_{location}" for location in range(6)),
    "verification_or_abstention": ("verify:physical", "ask:user", "hold:unresolved"),
}
ACTION_SUPPORT: Final = tuple(
    sorted(value for values in ACTION_ONTOLOGY.values() for value in values)
)
BELIEF_SUPPORT_MANIFEST_SHA256: Final = content_sha256(
    {
        "schema_id": BELIEF_SCHEMA_ID,
        "ontology_axes": BELIEF_ONTOLOGY_AXES,
        "support": BELIEF_SUPPORT,
    }
)
ACTION_SUPPORT_MANIFEST_SHA256: Final = content_sha256(
    {
        "schema_id": ACTION_SCHEMA_ID,
        "ontology": ACTION_ONTOLOGY,
        "support": ACTION_SUPPORT,
    }
)

EXPECTED_ARMS: Final = (
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

CANONICAL_COMPARISONS: Final[Mapping[str, tuple[str, str]]] = {
    "event-inference-adaptation": (
        "corrected_amg",
        "hidden-event and actor-attribution dual-readout adaptation",
    ),
    "object-search-adaptation": (
        "o_star_matched",
        "embodied object-search dual-readout adaptation",
    ),
    "no-consolidation-ablation": (
        "sequential_no_consolidation",
        "reversible consolidation dual-readout ablation",
    ),
    "active-dreaming-adaptation": (
        "active_dreaming_matched",
        "failure-driven memory-consolidation dual-readout adaptation",
    ),
    "auto-dreamer-adaptation": (
        "auto_dreamer_matched",
        "offline memory-consolidation dual-readout adaptation",
    ),
    "trustmem-adaptation": (
        "trustmem_matched",
        "verified memory-transition dual-readout adaptation",
    ),
    "brainctl-adaptation": (
        "brainctl_matched",
        "memory-admission and lifecycle-control dual-readout adaptation",
    ),
    "action-regret-ablation": (
        "care_no_action_regret",
        "embodied action-regret decision dual-readout ablation",
    ),
    "full-rerun-control": (
        "full_rerun",
        "incremental reversible update versus complete replay",
    ),
}

CANONICAL_MECHANISM_EVENTS: Final[Mapping[str, tuple[str, ...]]] = {
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

CANONICAL_COMPONENT_IDS: Final[Mapping[str, str]] = {
    "corrected_amg": "corrected_amg:reference-core@0.7",
    "o_star_matched": "o_star_matched:reference-core@0.7",
    "sequential_no_consolidation": "sequential_no_consolidation:core@0.7",
    "active_dreaming_matched": "active_dreaming_matched:reference-core@0.7",
    "auto_dreamer_matched": "auto_dreamer_matched:reference-core@0.7",
    "trustmem_matched": "trustmem_matched:reference-core@0.7",
    "brainctl_matched": "brainctl_matched:reference-core@0.7",
    "care_no_action_regret": "care_no_action_regret:core@0.7",
    "care_wm": "care_wm:core@0.7",
    "full_rerun": "full_rerun:core@0.7",
}


class ReadoutStage(StrEnum):
    """Only a decision made before evaluator/sealed truth is scoreable."""

    PRE_ACTION_PRE_EVALUATOR_TRUTH = "pre_action_pre_evaluator_truth"
    POST_ACTION_OBSERVATION = "post_action_observation"
    POST_EVALUATOR_TRUTH = "post_evaluator_truth"


class ActionSelectionRule(StrEnum):
    """Frozen deterministic policy; stochastic action draws are not scoreable."""

    DETERMINISTIC_ARGMAX_LEXICAL = "deterministic_argmax_lexical_tie_break"


def _validate_sha256(value: str, label: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")


def _validate_metadata(metadata: tuple[tuple[str, str], ...]) -> None:
    keys = [key for key, _ in metadata]
    if len(keys) != len(set(keys)):
        raise ValueError("trace metadata keys must be unique")


@dataclass(frozen=True, slots=True)
class CanonicalProbabilityDistribution:
    """A dense probability vector over an explicit, canonical support.

    Zero-mass entries must remain present.  The scorer never silently fills a
    missing entry and never renormalizes caller-provided values.
    """

    schema_id: str
    support: tuple[str, ...]
    probabilities: tuple[float, ...]

    def __post_init__(self) -> None:
        if self.schema_id not in {BELIEF_SCHEMA_ID, ACTION_SCHEMA_ID}:
            raise ValueError("probability distribution uses an unknown schema")
        expected_support = BELIEF_SUPPORT if self.schema_id == BELIEF_SCHEMA_ID else ACTION_SUPPORT
        if self.support != expected_support:
            raise ValueError("probability support does not match the frozen semantic ontology")
        if not self.support or len(self.support) != len(self.probabilities):
            raise ValueError("probability distribution must densely cover a non-empty support")
        if any(not label for label in self.support) or len(self.support) != len(set(self.support)):
            raise ValueError("probability support labels must be non-empty and unique")
        if self.support != tuple(sorted(self.support)):
            raise ValueError("probability support must use canonical lexical order")
        if any(not math.isfinite(value) or value < 0.0 for value in self.probabilities):
            raise ValueError("probabilities must be finite and non-negative")
        if not math.isclose(
            sum(self.probabilities),
            1.0,
            rel_tol=0.0,
            abs_tol=PROBABILITY_NORMALIZATION_TOLERANCE,
        ):
            raise ValueError("probability distribution must already be normalized")

    @property
    def support_sha256(self) -> str:
        return (
            BELIEF_SUPPORT_MANIFEST_SHA256
            if self.schema_id == BELIEF_SCHEMA_ID
            else ACTION_SUPPORT_MANIFEST_SHA256
        )


@dataclass(frozen=True, slots=True)
class InformationSetBinding:
    """Hashes of the information available before an action is selected."""

    visible_input_sha256: str
    visible_history_sha256: str
    observation_policy_sha256: str

    def __post_init__(self) -> None:
        _validate_sha256(self.visible_input_sha256, "visible input")
        _validate_sha256(self.visible_history_sha256, "visible history")
        _validate_sha256(self.observation_policy_sha256, "observation policy")


@dataclass(frozen=True, slots=True)
class BudgetEnvelope:
    """Preregistered limits, not method-dependent realized usage."""

    compute_unit_limit: int
    active_observation_limit: int
    physical_verification_limit: int
    action_cost_limit: float
    privacy_cost_limit: float

    def __post_init__(self) -> None:
        integer_limits = (
            self.compute_unit_limit,
            self.active_observation_limit,
            self.physical_verification_limit,
        )
        if any(type(value) is not int or value < 0 for value in integer_limits):
            raise ValueError("integer budget limits must be non-negative")
        if any(
            isinstance(value, bool) or not math.isfinite(value) or value < 0.0
            for value in (self.action_cost_limit, self.privacy_cost_limit)
        ):
            raise ValueError("cost budget limits must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class MechanismReceipt:
    event: str
    component_id: str
    input_state_sha256: str
    output_state_sha256: str

    def __post_init__(self) -> None:
        if not self.event or not self.component_id:
            raise ValueError("mechanism receipt event and component must be non-empty")
        _validate_sha256(self.input_state_sha256, "mechanism input state")
        _validate_sha256(self.output_state_sha256, "mechanism output state")
        if self.input_state_sha256 == self.output_state_sha256:
            raise ValueError("mechanism receipt must bind an observable state transition")


@dataclass(frozen=True, slots=True)
class DualGateStep:
    step_id: str
    information_set: InformationSetBinding
    budget: BudgetEnvelope
    readout_stage: ReadoutStage
    evaluator_truth_accessed: bool
    belief: CanonicalProbabilityDistribution
    action_policy: CanonicalProbabilityDistribution
    selected_action: str
    action_selection_rule: ActionSelectionRule = ActionSelectionRule.DETERMINISTIC_ARGMAX_LEXICAL
    mechanism_receipts: tuple[MechanismReceipt, ...] = ()

    def __post_init__(self) -> None:
        if not self.step_id:
            raise ValueError("dual-gate step ID must be non-empty")
        if self.belief.schema_id != BELIEF_SCHEMA_ID:
            raise ValueError("belief readout uses the wrong canonical schema")
        if self.action_policy.schema_id != ACTION_SCHEMA_ID:
            raise ValueError("action readout uses the wrong canonical schema")
        if self.selected_action not in self.action_policy.support:
            raise ValueError("selected action is absent from the complete action support")
        if self.action_selection_rule is not ActionSelectionRule.DETERMINISTIC_ARGMAX_LEXICAL:
            raise ValueError("Gate B rejects a stochastic or caller-selected action rule")
        maximum = max(self.action_policy.probabilities)
        expected_action = next(
            label
            for label, probability in zip(
                self.action_policy.support,
                self.action_policy.probabilities,
                strict=True,
            )
            if probability == maximum
        )
        if self.selected_action != expected_action:
            raise ValueError("selected action violates deterministic argmax with lexical tie-break")


@dataclass(frozen=True, slots=True)
class DualGateEpisode:
    episode_id: str
    steps: tuple[DualGateStep, ...]

    def __post_init__(self) -> None:
        if not self.episode_id or not self.steps:
            raise ValueError("dual-gate episodes require an ID and at least one step")
        step_ids = [step.step_id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("dual-gate step IDs must be unique within an episode")


@dataclass(frozen=True, slots=True)
class DualGateArmTrace:
    arm: str
    episodes: tuple[DualGateEpisode, ...]
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.arm or not self.episodes:
            raise ValueError("dual-gate arm traces require an arm and episodes")
        episode_ids = [episode.episode_id for episode in self.episodes]
        if len(episode_ids) != len(set(episode_ids)):
            raise ValueError("dual-gate episode IDs must be unique")
        _validate_metadata(self.metadata)


@dataclass(frozen=True, slots=True)
class DualGateComparison:
    comparison_id: str
    domain: str
    left_arm: str
    right_arm: str
    min_belief_step_tv: float = MIN_BELIEF_STEP_TV
    min_mean_belief_tv: float = MIN_MEAN_BELIEF_TV
    min_belief_material_step_fraction: float = MIN_BELIEF_MATERIAL_STEP_FRACTION
    min_action_step_tv: float = MIN_ACTION_STEP_TV
    min_mean_action_tv: float = MIN_MEAN_ACTION_TV
    min_action_material_step_fraction: float = MIN_ACTION_MATERIAL_STEP_FRACTION
    min_selected_action_disagreement_rate: float = MIN_SELECTED_ACTION_DISAGREEMENT_RATE

    def __post_init__(self) -> None:
        if not self.comparison_id or not self.domain:
            raise ValueError("comparison ID and domain must be non-empty")
        if self.left_arm == self.right_arm:
            raise ValueError("a dual-gate comparison requires two different arms")
        tv_thresholds = (
            self.min_belief_step_tv,
            self.min_mean_belief_tv,
            self.min_action_step_tv,
            self.min_mean_action_tv,
        )
        if any(
            not math.isfinite(value) or value <= NUMERICAL_NOISE_FLOOR or value > 1.0
            for value in tv_thresholds
        ):
            raise ValueError("TV materiality thresholds must exceed the numerical noise floor")
        fractions = (
            self.min_belief_material_step_fraction,
            self.min_action_material_step_fraction,
            self.min_selected_action_disagreement_rate,
        )
        if any(not math.isfinite(value) or value <= 0.0 or value > 1.0 for value in fractions):
            raise ValueError("dual-gate step-fraction thresholds must lie in (0, 1]")


@dataclass(frozen=True, slots=True)
class MechanismRequirement:
    arm: str
    required_event_components: tuple[tuple[str, str], ...]
    min_step_fraction: float = MIN_MECHANISM_STEP_FRACTION
    min_episode_fraction: float = MIN_MECHANISM_EPISODE_FRACTION

    def __post_init__(self) -> None:
        if not self.arm or not self.required_event_components:
            raise ValueError("each arm requires at least one registered mechanism event")
        if len(self.required_event_components) != len(set(self.required_event_components)):
            raise ValueError("registered mechanism event/component pairs must be unique")
        if any(not event or not component for event, component in self.required_event_components):
            raise ValueError("registered mechanism event/component values must be non-empty")
        if not math.isfinite(self.min_step_fraction) or not (0.0 < self.min_step_fraction <= 1.0):
            raise ValueError("mechanism step fraction must lie in (0, 1]")
        if not math.isfinite(self.min_episode_fraction) or not (
            0.0 < self.min_episode_fraction <= 1.0
        ):
            raise ValueError("mechanism episode fraction must lie in (0, 1]")


@dataclass(frozen=True, slots=True)
class FrozenDualGateProtocol:
    content_sha256: str
    expected_arms: tuple[str, ...]
    comparisons: tuple[DualGateComparison, ...]
    mechanism_requirements: tuple[MechanismRequirement, ...]
    status: Literal["INVALIDATED_SUPERSEDED_FOR_FUTURE"] = "INVALIDATED_SUPERSEDED_FOR_FUTURE"
    new_trace_set_present: Literal[False] = False
    formal_gate_b_passed: Literal[False] = False
    seven_operator_ablation_authorized: Literal[False] = False

    def __post_init__(self) -> None:
        _validate_sha256(self.content_sha256, "invalidated Gate B v0.7 content")
        if self.status != PROTOCOL_STATUS:
            raise ValueError("invalidated Gate B v0.7 status cannot be changed")
        if (
            self.new_trace_set_present
            or self.formal_gate_b_passed
            or self.seven_operator_ablation_authorized
        ):
            raise ValueError("invalidated Gate B v0.7 object cannot expose a positive path")


def _canonical_comparison_rows() -> list[dict[str, Any]]:
    return [
        {
            "comparison_id": comparison_id,
            "domain": domain,
            "left_arm": "care_wm",
            "right_arm": right_arm,
            "belief_thresholds": {
                "min_step_total_variation": MIN_BELIEF_STEP_TV,
                "min_mean_total_variation": MIN_MEAN_BELIEF_TV,
                "min_material_step_fraction": MIN_BELIEF_MATERIAL_STEP_FRACTION,
            },
            "action_thresholds": {
                "min_step_total_variation": MIN_ACTION_STEP_TV,
                "min_mean_total_variation": MIN_MEAN_ACTION_TV,
                "min_material_step_fraction": MIN_ACTION_MATERIAL_STEP_FRACTION,
                "min_selected_action_disagreement_rate": (MIN_SELECTED_ACTION_DISAGREEMENT_RATE),
            },
        }
        for comparison_id, (right_arm, domain) in CANONICAL_COMPARISONS.items()
    ]


def _canonical_mechanism_rows() -> dict[str, Any]:
    return {
        arm: {
            "required_event_components": [
                {"event": event, "component_id": CANONICAL_COMPONENT_IDS[arm]} for event in events
            ],
            "min_step_fraction": MIN_MECHANISM_STEP_FRACTION,
            "min_episode_fraction": MIN_MECHANISM_EPISODE_FRACTION,
        }
        for arm, events in CANONICAL_MECHANISM_EVENTS.items()
    }


def canonical_frozen_protocol_payload_v0_7() -> dict[str, Any]:
    """Return the exact machine-readable v0.7 freeze declaration."""

    return {
        "protocol": PROTOCOL_ID,
        "status": PROTOCOL_STATUS,
        "frozen_on": "2026-09-04",
        "invalidated_on": "2026-09-05",
        "superseded_by": SUPERSEDED_BY_PROTOCOL_ID,
        "positive_authorization_paths_disabled": True,
        "supersedes_for_future_runs": ("structure-two-stratified-mechanism-action-gate-b@0.6"),
        "preserves_historical_results": True,
        "gate_semantics": {
            "composition": "belief AND action AND mechanism",
            "belief_cannot_substitute_for_action": True,
            "action_cannot_substitute_for_belief": True,
            "mechanism_cannot_substitute_for_either_readout": True,
        },
        "probability_contract": {
            "belief_schema_id": BELIEF_SCHEMA_ID,
            "action_schema_id": ACTION_SCHEMA_ID,
            "dense_complete_support_required": True,
            "finite_nonnegative_probabilities_required": True,
            "normalization_tolerance": PROBABILITY_NORMALIZATION_TOLERANCE,
            "numerical_noise_floor": NUMERICAL_NOISE_FLOOR,
            "silent_renormalization_forbidden": True,
        },
        "ontology_contract": {
            "belief_axes": {name: list(values) for name, values in BELIEF_ONTOLOGY_AXES.items()},
            "belief_support_size": len(BELIEF_SUPPORT),
            "belief_support_manifest_sha256": BELIEF_SUPPORT_MANIFEST_SHA256,
            "action_categories": {name: list(values) for name, values in ACTION_ONTOLOGY.items()},
            "action_support_size": len(ACTION_SUPPORT),
            "action_support_manifest_sha256": ACTION_SUPPORT_MANIFEST_SHA256,
            "exact_frozen_support_required": True,
        },
        "action_selection_contract": {
            "rule": ActionSelectionRule.DETERMINISTIC_ARGMAX_LEXICAL.value,
            "tie_break": "lexicographically_smallest_action_label",
            "stochastic_action_draws_forbidden": True,
            "caller_selected_rng_forbidden": True,
            "selected_disagreement_requires_material_action_tv_same_step": True,
        },
        "alignment_contract": {
            "same_episode_and_step_order_required": True,
            "same_information_set_required": True,
            "same_budget_envelope_required": True,
            "same_probability_support_required": True,
            "scoreable_readout_stage": ReadoutStage.PRE_ACTION_PRE_EVALUATOR_TRUTH.value,
            "evaluator_truth_access_forbidden": True,
        },
        "metadata_policy": {
            "metadata_excluded_from_semantic_metrics": True,
            "file_hash_difference_is_not_semantic_difference": True,
            "renaming_cannot_satisfy_either_readout_gate": True,
        },
        "expected_arms": list(EXPECTED_ARMS),
        "comparison_pairs": _canonical_comparison_rows(),
        "mechanism_requirements": _canonical_mechanism_rows(),
        "official_execution": {
            "new_trace_set_present": False,
            "independent_attestation_present": False,
            "formal_gate_b_passed": False,
            "seven_operator_ablation_authorized": False,
        },
        "external_fidelity_policy": {
            "separate_external_fidelity_gate_required": True,
            "gate_b_pass_does_not_establish_efficacy_superiority": True,
        },
        "claim_boundary": (
            "Gate B v0.7 is invalidated and superseded for every future run. Diagnostic "
            "satisfaction is historical information only and cannot be reported as a formal "
            "Gate B pass or as authorization for seven-operator ablation."
        ),
    }


def validate_frozen_protocol_payload_v0_7(payload: Mapping[str, Any]) -> None:
    """Reject any weakening or caller-selected mutation of the frozen protocol."""

    if dict(payload) != canonical_frozen_protocol_payload_v0_7():
        raise ValueError("Gate B v0.7 payload differs from the canonical frozen protocol")


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key, value in pairs:
        if key in payload:
            raise ValueError(f"duplicate JSON key in Gate B v0.7 config: {key}")
        payload[key] = value
    return payload


def load_frozen_protocol_v0_7(path: Path) -> FrozenDualGateProtocol:
    payload = cast(
        object,
        json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_json_keys),
    )
    if not isinstance(payload, dict):
        raise ValueError("Gate B v0.7 protocol must be a JSON object")
    validate_frozen_protocol_payload_v0_7(payload)
    comparisons = tuple(
        DualGateComparison(
            comparison_id=comparison_id,
            domain=domain,
            left_arm="care_wm",
            right_arm=right_arm,
        )
        for comparison_id, (right_arm, domain) in CANONICAL_COMPARISONS.items()
    )
    requirements = tuple(
        MechanismRequirement(
            arm=arm,
            required_event_components=tuple(
                (event, CANONICAL_COMPONENT_IDS[arm]) for event in events
            ),
        )
        for arm, events in CANONICAL_MECHANISM_EVENTS.items()
    )
    return FrozenDualGateProtocol(
        content_sha256=content_sha256(payload),
        expected_arms=EXPECTED_ARMS,
        comparisons=comparisons,
        mechanism_requirements=requirements,
    )


def _total_variation(
    left: CanonicalProbabilityDistribution,
    right: CanonicalProbabilityDistribution,
) -> float:
    if left.schema_id != right.schema_id or left.support != right.support:
        raise ValueError("compared probability distributions do not share canonical support")
    return 0.5 * sum(
        abs(left_value - right_value)
        for left_value, right_value in zip(left.probabilities, right.probabilities, strict=True)
    )


def _semantic_step_payload(step: DualGateStep) -> dict[str, Any]:
    return {
        "step_id": step.step_id,
        "information_set": step.information_set,
        "budget": step.budget,
        "readout_stage": step.readout_stage,
        "evaluator_truth_accessed": step.evaluator_truth_accessed,
        "belief": step.belief,
        "action_policy": step.action_policy,
        "selected_action": step.selected_action,
        "action_selection_rule": step.action_selection_rule,
        "mechanism_receipts": step.mechanism_receipts,
    }


def semantic_trace_sha256(trace: DualGateArmTrace) -> str:
    """Hash score-relevant semantics only; caller metadata is intentionally excluded."""

    return content_sha256(
        {
            "arm": trace.arm,
            "episodes": [
                {
                    "episode_id": episode.episode_id,
                    "steps": [_semantic_step_payload(step) for step in episode.steps],
                }
                for episode in trace.episodes
            ],
        }
    )


def _validate_trace_timing(trace: DualGateArmTrace) -> None:
    for episode in trace.episodes:
        for step in episode.steps:
            if step.readout_stage is not ReadoutStage.PRE_ACTION_PRE_EVALUATOR_TRUTH:
                raise ValueError("Gate B rejects a post-action or post-truth readout")
            if step.evaluator_truth_accessed:
                raise ValueError("Gate B rejects any readout that accessed evaluator truth")


def _validate_global_alignment(traces: Sequence[DualGateArmTrace]) -> None:
    reference = traces[0]
    reference_episode_ids = tuple(episode.episode_id for episode in reference.episodes)
    for trace in traces:
        _validate_trace_timing(trace)
        if tuple(episode.episode_id for episode in trace.episodes) != reference_episode_ids:
            raise ValueError("dual-gate traces have different episode order")
        for reference_episode, episode in zip(reference.episodes, trace.episodes, strict=True):
            if tuple(step.step_id for step in episode.steps) != tuple(
                step.step_id for step in reference_episode.steps
            ):
                raise ValueError("dual-gate traces have different step order")
            for reference_step, step in zip(reference_episode.steps, episode.steps, strict=True):
                if step.information_set != reference_step.information_set:
                    raise ValueError("dual-gate traces use different information sets")
                if step.budget != reference_step.budget:
                    raise ValueError("dual-gate traces use different budget envelopes")
                if step.belief.support != reference_step.belief.support:
                    raise ValueError("dual-gate belief support is incomplete or misaligned")
                if step.action_policy.support != reference_step.action_policy.support:
                    raise ValueError("dual-gate action support is incomplete or misaligned")


def _flatten(trace: DualGateArmTrace) -> tuple[DualGateStep, ...]:
    return tuple(step for episode in trace.episodes for step in episode.steps)


def _comparison_score(
    left: DualGateArmTrace,
    right: DualGateArmTrace,
    comparison: DualGateComparison,
) -> dict[str, Any]:
    left_steps = _flatten(left)
    right_steps = _flatten(right)
    if not left_steps or len(left_steps) != len(right_steps):
        raise ValueError("dual-gate comparison has no aligned scored steps")
    belief_tvs = [
        _total_variation(left_step.belief, right_step.belief)
        for left_step, right_step in zip(left_steps, right_steps, strict=True)
    ]
    action_tvs = [
        _total_variation(left_step.action_policy, right_step.action_policy)
        for left_step, right_step in zip(left_steps, right_steps, strict=True)
    ]
    step_count = len(left_steps)
    mean_belief_tv = sum(belief_tvs) / step_count
    belief_fraction = (
        sum(value >= comparison.min_belief_step_tv for value in belief_tvs) / step_count
    )
    mean_action_tv = sum(action_tvs) / step_count
    action_fraction = (
        sum(value >= comparison.min_action_step_tv for value in action_tvs) / step_count
    )
    selected_disagreement = (
        sum(
            action_tv >= comparison.min_action_step_tv
            and left_step.selected_action != right_step.selected_action
            for action_tv, left_step, right_step in zip(
                action_tvs,
                left_steps,
                right_steps,
                strict=True,
            )
        )
        / step_count
    )
    belief_passed = (
        mean_belief_tv >= comparison.min_mean_belief_tv
        and belief_fraction >= comparison.min_belief_material_step_fraction
    )
    action_passed = (
        mean_action_tv >= comparison.min_mean_action_tv
        and action_fraction >= comparison.min_action_material_step_fraction
        and selected_disagreement >= comparison.min_selected_action_disagreement_rate
    )
    return {
        "comparison_id": comparison.comparison_id,
        "domain": comparison.domain,
        "left_arm": comparison.left_arm,
        "right_arm": comparison.right_arm,
        "scored_steps": step_count,
        "mean_belief_total_variation": mean_belief_tv,
        "belief_material_step_fraction": belief_fraction,
        "mean_action_total_variation": mean_action_tv,
        "action_material_step_fraction": action_fraction,
        "selected_action_disagreement_rate": selected_disagreement,
        "belief_thresholds": {
            "min_step_total_variation": comparison.min_belief_step_tv,
            "min_mean_total_variation": comparison.min_mean_belief_tv,
            "min_material_step_fraction": comparison.min_belief_material_step_fraction,
        },
        "action_thresholds": {
            "min_step_total_variation": comparison.min_action_step_tv,
            "min_mean_total_variation": comparison.min_mean_action_tv,
            "min_material_step_fraction": comparison.min_action_material_step_fraction,
            "min_selected_action_disagreement_rate": (
                comparison.min_selected_action_disagreement_rate
            ),
        },
        "belief_passed": belief_passed,
        "action_passed": action_passed,
        "dual_readout_passed": belief_passed and action_passed,
    }


def _mechanism_score(
    trace: DualGateArmTrace,
    requirement: MechanismRequirement,
) -> dict[str, Any]:
    total_steps = sum(len(episode.steps) for episode in trace.episodes)
    per_event: dict[str, dict[str, Any]] = {}
    for event, component_id in requirement.required_event_components:
        step_hits = 0
        episode_hits = 0
        for episode in trace.episodes:
            local_hits = 0
            for step in episode.steps:
                present = any(
                    receipt.event == event and receipt.component_id == component_id
                    for receipt in step.mechanism_receipts
                )
                step_hits += int(present)
                local_hits += int(present)
            episode_hits += int(local_hits > 0)
        step_fraction = step_hits / total_steps
        episode_fraction = episode_hits / len(trace.episodes)
        per_event[event] = {
            "component_id": component_id,
            "step_hits": step_hits,
            "episode_hits": episode_hits,
            "step_fraction": step_fraction,
            "episode_fraction": episode_fraction,
            "passed": (
                step_fraction >= requirement.min_step_fraction
                and episode_fraction >= requirement.min_episode_fraction
            ),
        }
    return {
        "arm": trace.arm,
        "per_event": per_event,
        "passed": all(bool(result["passed"]) for result in per_event.values()),
    }


def score_dual_gate_b_v0_7_diagnostic(
    traces: Sequence[DualGateArmTrace],
    *,
    expected_arms: Sequence[str],
    comparison_pairs: Sequence[DualGateComparison],
    mechanism_requirements: Sequence[MechanismRequirement],
) -> dict[str, Any]:
    """Score v0.7 conditions without authorizing a formal Gate B pass."""

    expected = tuple(expected_arms)
    if not expected or len(expected) != len(set(expected)):
        raise ValueError("expected dual-gate arm set must be non-empty and unique")
    by_arm = {trace.arm: trace for trace in traces}
    if len(by_arm) != len(traces) or set(by_arm) != set(expected):
        raise ValueError("dual-gate trace set must exactly match the expected arms")
    comparisons = tuple(comparison_pairs)
    if not comparisons or len({item.comparison_id for item in comparisons}) != len(comparisons):
        raise ValueError("dual-gate comparisons must be non-empty with unique IDs")
    requirements = {item.arm: item for item in mechanism_requirements}
    if len(requirements) != len(tuple(mechanism_requirements)) or set(requirements) != set(
        expected
    ):
        raise ValueError("every dual-gate arm needs exactly one mechanism requirement")
    participating: set[str] = set()
    for comparison in comparisons:
        if comparison.left_arm not in by_arm or comparison.right_arm not in by_arm:
            raise ValueError("dual-gate comparison names an unknown arm")
        participating.update((comparison.left_arm, comparison.right_arm))
    if participating != set(expected):
        raise ValueError("every expected arm must participate in a frozen comparison")

    ordered_traces = tuple(by_arm[arm] for arm in expected)
    _validate_global_alignment(ordered_traces)
    comparison_results = [
        _comparison_score(by_arm[item.left_arm], by_arm[item.right_arm], item)
        for item in comparisons
    ]
    mechanism_results = [_mechanism_score(by_arm[arm], requirements[arm]) for arm in expected]
    belief_passed = all(bool(item["belief_passed"]) for item in comparison_results)
    action_passed = all(bool(item["action_passed"]) for item in comparison_results)
    mechanism_passed = all(bool(item["passed"]) for item in mechanism_results)
    diagnostic_conditions_passed = belief_passed and action_passed and mechanism_passed
    report: dict[str, Any] = {
        "protocol": PROTOCOL_ID,
        "protocol_status": PROTOCOL_STATUS,
        "trace_execution_status": "V0_7_INVALIDATED_NO_AUTHORIZATION",
        "protocol_invalidated": True,
        "superseded_by": SUPERSEDED_BY_PROTOCOL_ID,
        "belief_support_manifest_sha256": BELIEF_SUPPORT_MANIFEST_SHA256,
        "action_support_manifest_sha256": ACTION_SUPPORT_MANIFEST_SHA256,
        "action_selection_rule": ActionSelectionRule.DETERMINISTIC_ARGMAX_LEXICAL.value,
        "semantic_trace_sha256_by_arm": {
            arm: semantic_trace_sha256(by_arm[arm]) for arm in expected
        },
        "information_set_alignment_passed": True,
        "budget_alignment_passed": True,
        "pre_truth_readout_passed": True,
        "comparison_pair_results": comparison_results,
        "mechanism_activation_results": mechanism_results,
        "diagnostic_belief_gate_passed": belief_passed,
        "diagnostic_action_gate_passed": action_passed,
        "diagnostic_mechanism_gate_passed": mechanism_passed,
        "diagnostic_dual_conditions_passed": diagnostic_conditions_passed,
        # Formal promotion requires a separately implemented, independently
        # attested execution path.  Callers cannot turn this diagnostic into it.
        "formal_gate_b_passed": False,
        "gate_b_passed": False,
        "seven_operator_ablation_authorized": False,
        "claim_boundary": (
            "This historical diagnostic can test the old numerical conditions, but Gate B "
            "v0.7 is invalidated and superseded by v0.8. No v0.7 trace or attestation can "
            "establish a formal Gate B pass, efficacy, or seven-operator authorization."
        ),
    }
    report["content_sha256"] = content_sha256(report)
    return report


def score_frozen_dual_gate_b_v0_7_diagnostic(
    traces: Sequence[DualGateArmTrace],
    *,
    protocol: FrozenDualGateProtocol,
) -> dict[str, Any]:
    """Score only the exact loaded freeze, while retaining the formal false boundary."""

    canonical = canonical_frozen_protocol_payload_v0_7()
    expected_protocol = FrozenDualGateProtocol(
        content_sha256=content_sha256(canonical),
        expected_arms=EXPECTED_ARMS,
        comparisons=tuple(
            DualGateComparison(
                comparison_id=comparison_id,
                domain=domain,
                left_arm="care_wm",
                right_arm=right_arm,
            )
            for comparison_id, (right_arm, domain) in CANONICAL_COMPARISONS.items()
        ),
        mechanism_requirements=tuple(
            MechanismRequirement(
                arm=arm,
                required_event_components=tuple(
                    (event, CANONICAL_COMPONENT_IDS[arm]) for event in events
                ),
            )
            for arm, events in CANONICAL_MECHANISM_EVENTS.items()
        ),
    )
    if protocol != expected_protocol:
        raise ValueError("diagnostic scorer rejected a noncanonical Gate B v0.7 freeze")
    return score_dual_gate_b_v0_7_diagnostic(
        traces,
        expected_arms=protocol.expected_arms,
        comparison_pairs=protocol.comparisons,
        mechanism_requirements=protocol.mechanism_requirements,
    )


__all__ = [
    "ACTION_ONTOLOGY",
    "ACTION_SCHEMA_ID",
    "ACTION_SUPPORT",
    "ACTION_SUPPORT_MANIFEST_SHA256",
    "BELIEF_ONTOLOGY_AXES",
    "BELIEF_SCHEMA_ID",
    "BELIEF_SUPPORT",
    "BELIEF_SUPPORT_MANIFEST_SHA256",
    "CANONICAL_COMPARISONS",
    "CANONICAL_COMPONENT_IDS",
    "CANONICAL_MECHANISM_EVENTS",
    "EXPECTED_ARMS",
    "PROTOCOL_ID",
    "PROTOCOL_STATUS",
    "SUPERSEDED_BY_PROTOCOL_ID",
    "ActionSelectionRule",
    "BudgetEnvelope",
    "CanonicalProbabilityDistribution",
    "DualGateArmTrace",
    "DualGateComparison",
    "DualGateEpisode",
    "DualGateStep",
    "FrozenDualGateProtocol",
    "InformationSetBinding",
    "MechanismReceipt",
    "MechanismRequirement",
    "ReadoutStage",
    "canonical_frozen_protocol_payload_v0_7",
    "load_frozen_protocol_v0_7",
    "score_dual_gate_b_v0_7_diagnostic",
    "score_frozen_dual_gate_b_v0_7_diagnostic",
    "semantic_trace_sha256",
    "validate_frozen_protocol_payload_v0_7",
]
