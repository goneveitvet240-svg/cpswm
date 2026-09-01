"""Executable reference cores for the six external Structure-Two arms.

These cores expose real method-specific state transitions.  They are not, by
themselves, full published-protocol reproductions or efficacy evidence.
"""

from __future__ import annotations

from collections.abc import Mapping
from itertools import product
from math import isfinite, log, sqrt
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from cpswm.contracts.base import ContractModel
from cpswm.system.evaluation_operations.oam_phm_external_evidence import (
    OStarReferenceBelief,
    OStarReferenceConfig,
)
from cpswm.system.evaluation_operations.structure_two_counterfactual_executor_v0_7 import (
    CounterfactualExecutionReceipt,
    verify_counterfactual_execution,
)
from cpswm.system.evaluation_operations.structure_two_external_inputs_v0_6 import (
    ActiveDreamingAdaptationInput,
    AMGAdaptationInput,
    AutoDreamerAdaptationInput,
    BrainctlAdaptationInput,
    OStarAdaptationInput,
    TrustMemAdaptationInput,
)
from cpswm.system.evaluation_operations.structure_two_signed_gate_b_v0_6 import (
    MechanismExecutionLogEntry,
    MechanismTransitionReceipt,
)
from cpswm.system.reproducibility import content_sha256

PROTOCOL_ID = "structure-two-external-reference-cores@0.6"


class ReferenceCoreTransition(ContractModel):
    event: str = Field(min_length=1)
    input_state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ReferenceCoreResult(ContractModel):
    protocol: Literal["structure-two-external-reference-cores@0.6"] = (
        "structure-two-external-reference-cores@0.6"
    )
    arm: str = Field(min_length=1)
    output: dict[str, Any]
    transitions: tuple[ReferenceCoreTransition, ...] = Field(min_length=1)
    claim_boundary: str = (
        "Executable method-specific reference core only; not a full native-protocol "
        "reproduction, independently reviewed adaptation, or efficacy result."
    )

    @property
    def content_sha256(self) -> str:
        return content_sha256(self)


def _transition(event: str, before: Any, after: Any) -> ReferenceCoreTransition:
    before_hash = content_sha256(before)
    after_hash = content_sha256(after)
    if before_hash == after_hash:
        raise ValueError(f"reference-core event {event} did not change state")
    return ReferenceCoreTransition(
        event=event,
        input_state_sha256=before_hash,
        output_state_sha256=after_hash,
    )


def execution_log_entries_from_reference_core(
    result: ReferenceCoreResult,
    *,
    invocation_prefix: str,
    implementation_bundle_sha256: str,
) -> tuple[MechanismExecutionLogEntry, ...]:
    """Build one continuous execution-state chain over real core transitions."""

    if not invocation_prefix:
        raise ValueError("mechanism receipt invocation prefix must be non-empty")
    entries: list[MechanismExecutionLogEntry] = []
    chain_state_sha256 = content_sha256(
        {"arm": result.arm, "invocation_prefix": invocation_prefix, "state": "start"}
    )
    for index, item in enumerate(result.transitions):
        core_transition_sha256 = content_sha256(item)
        output_state_sha256 = content_sha256(
            {
                "previous_state_sha256": chain_state_sha256,
                "core_transition_sha256": core_transition_sha256,
                "sequence_index": index,
            }
        )
        entries.append(
            MechanismExecutionLogEntry(
                sequence_index=index,
                invocation_id=f"{invocation_prefix}:{index}",
                event=item.event,
                component_id=f"{result.arm}:reference-core@0.6",
                input_state_sha256=chain_state_sha256,
                output_state_sha256=output_state_sha256,
                implementation_bundle_sha256=implementation_bundle_sha256,
                core_transition_sha256=core_transition_sha256,
                core_transition_payload=item.model_dump(mode="json"),
            )
        )
        chain_state_sha256 = output_state_sha256
    return tuple(entries)


def mechanism_receipts_from_reference_core(
    result: ReferenceCoreResult,
    *,
    invocation_prefix: str,
    implementation_bundle_sha256: str,
) -> tuple[MechanismTransitionReceipt, ...]:
    """Bind reference-core transitions to their execution-log entries."""

    entries = execution_log_entries_from_reference_core(
        result,
        invocation_prefix=invocation_prefix,
        implementation_bundle_sha256=implementation_bundle_sha256,
    )
    return tuple(
        MechanismTransitionReceipt(
            invocation_id=f"{invocation_prefix}:{index}",
            event=entry.event,
            component_id=entry.component_id,
            input_state_sha256=entry.input_state_sha256,
            output_state_sha256=entry.output_state_sha256,
            implementation_bundle_sha256=implementation_bundle_sha256,
            core_transition_sha256=entry.core_transition_sha256,
            execution_log_entry_sha256=entry.content_sha256,
        )
        for index, entry in enumerate(entries)
    )


def _log_odds(value: float) -> float:
    return log(value) - log(1.0 - value)


def run_amg_reference_core(inputs: AMGAdaptationInput) -> ReferenceCoreResult:
    """Enumerate a constrained joint actor/mechanism parse across all events."""

    local_candidates: list[tuple[dict[str, Any], ...]] = []
    for event in inputs.events:
        candidates: list[dict[str, Any]] = []
        source_score = _log_odds(event.source_likelihood)
        for actor, actor_likelihood in event.actor_likelihoods.items():
            candidates.append(
                {
                    "event_id": event.event_id,
                    "mechanism": "direct",
                    "responsible_actor": actor,
                    "ordered_role": None,
                    "score": source_score
                    + _log_odds(event.mechanism_likelihoods["direct"])
                    + _log_odds(actor_likelihood),
                }
            )
        for role, role_likelihood in event.ordered_role_likelihoods.items():
            sender, recipient = role.split("->", maxsplit=1)
            candidates.append(
                {
                    "event_id": event.event_id,
                    "mechanism": "handoff",
                    "responsible_actor": recipient,
                    "ordered_role": role,
                    "score": source_score
                    + _log_odds(event.mechanism_likelihoods["handoff"])
                    + _log_odds(event.actor_likelihoods[sender])
                    + _log_odds(event.actor_likelihoods[recipient])
                    + _log_odds(role_likelihood),
                }
            )
        local_candidates.append(tuple(candidates))

    def satisfies_constraints(parse: tuple[dict[str, Any], ...]) -> bool:
        by_event = {str(item["event_id"]): item for item in parse}
        for constraint in inputs.cross_event_constraints:
            left = by_event[constraint.left_event_id]["responsible_actor"]
            right = by_event[constraint.right_event_id]["responsible_actor"]
            if constraint.kind == "same_responsible_actor" and left != right:
                return False
            if constraint.kind == "different_responsible_actor" and left == right:
                return False
        return True

    joint_candidates = tuple(
        parse for parse in product(*local_candidates) if satisfies_constraints(parse)
    )
    if not joint_candidates:
        raise ValueError("AMG cross-event constraints remove every joint parse")
    selected = max(
        joint_candidates,
        key=lambda parse: (
            sum(float(item["score"]) for item in parse),
            tuple(str(item["event_id"]) for item in parse),
            tuple(str(item["responsible_actor"]) for item in parse),
        ),
    )
    output = {
        "selected_parse": selected,
        "joint_candidate_count": len(joint_candidates),
        "log_unnormalized_posterior": sum(float(item["score"]) for item in selected),
        "hierarchy_edges": inputs.hierarchy_edges,
    }
    transition = _transition(
        "global_multi_event_map_inference",
        {"selected_parse": None, "candidate_count": len(joint_candidates)},
        output,
    )
    return ReferenceCoreResult(
        arm=inputs.arm,
        output=output,
        transitions=(transition,),
    )


def run_o_star_reference_core(
    inputs: OStarAdaptationInput,
    *,
    target_id: str,
    config: OStarReferenceConfig,
) -> ReferenceCoreResult:
    if target_id not in inputs.feasible_target_locations:
        raise KeyError(f"unknown O-STaR target: {target_id}")
    feasible = frozenset(inputs.feasible_target_locations[target_id])
    belief = OStarReferenceBelief.initialize(
        llm_prior=inputs.llm_day_zero_priors[target_id],
        geometrically_feasible_locations=feasible,
        config=config,
    )
    transitions: list[ReferenceCoreTransition] = []
    for observation in inputs.observations:
        if observation.target_id != target_id:
            continue
        before = belief
        belief = (
            belief.observe_hit(observation.location_id, config)
            if observation.outcome == "hit"
            else belief.observe_miss(observation.location_id, config)
        )
        transitions.append(_transition("dirichlet_hit_or_miss_update", before, belief))
        before = belief
        belief = belief.stay_and_leak(config)
        if before != belief:
            transitions.append(_transition("stay_leak_transition", before, belief))
    before_order = {"posterior": belief.posterior, "selected": None}
    order = belief.cost_aware_order(
        {
            location: inputs.navigation_and_inspection_costs[location]
            for location in belief.location_order
        }
    )
    after_order = {"posterior": belief.posterior, "selected": order[0]}
    transitions.append(_transition("cost_aware_search", before_order, after_order))
    return ReferenceCoreResult(
        arm=inputs.arm,
        output={"target_id": target_id, "posterior": belief.posterior, "search_order": order},
        transitions=tuple(transitions),
    )


def _cosine_distance(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = sqrt(sum(value * value for value in left))
    right_norm = sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 1.0
    return 1.0 - max(-1.0, min(1.0, dot / (left_norm * right_norm)))


def _dbscan_cosine(
    vectors: tuple[tuple[float, ...], ...], *, eps: float = 0.3, min_samples: int = 2
) -> tuple[int, ...]:
    """Small deterministic DBSCAN equivalent to the official Active Dreaming settings."""

    if not 0.0 < eps <= 2.0 or min_samples < 1:
        raise ValueError("DBSCAN parameters are invalid")
    neighbors = tuple(
        tuple(j for j, other in enumerate(vectors) if _cosine_distance(vector, other) <= eps)
        for vector in vectors
    )
    unassigned = -99
    noise = -1
    labels = [unassigned] * len(vectors)
    cluster_id = 0
    for index in range(len(vectors)):
        if labels[index] != unassigned:
            continue
        if len(neighbors[index]) < min_samples:
            labels[index] = noise
            continue
        labels[index] = cluster_id
        queue = list(neighbors[index])
        queued = set(queue)
        cursor = 0
        while cursor < len(queue):
            candidate = queue[cursor]
            cursor += 1
            if labels[candidate] == noise:
                labels[candidate] = cluster_id
            if labels[candidate] != unassigned:
                continue
            labels[candidate] = cluster_id
            if len(neighbors[candidate]) >= min_samples:
                for nested in neighbors[candidate]:
                    if nested not in queued:
                        queued.add(nested)
                        queue.append(nested)
        cluster_id += 1
    return tuple(labels)


def cluster_active_dreaming_failures(
    inputs: ActiveDreamingAdaptationInput,
) -> tuple[int, ...]:
    """Run only the pinned DBSCAN component, without implying scenario execution."""

    return _dbscan_cosine(tuple(item.embedding for item in inputs.episodic_failures))


def run_active_dreaming_reference_core(
    inputs: ActiveDreamingAdaptationInput,
    *,
    abstracted_rule_by_cluster: dict[int, str],
    scenario_execution_receipts: Mapping[str, CounterfactualExecutionReceipt],
    scenario_program_paths: Mapping[str, Path],
    trusted_executor_key_id: str,
    trusted_executor_public_key_sha256: str,
) -> ReferenceCoreResult:
    labels = cluster_active_dreaming_failures(inputs)
    cluster_ids = tuple(sorted(set(labels) - {-1}))
    if not cluster_ids:
        raise ValueError("Active Dreaming produced no non-noise failure cluster")
    if set(abstracted_rule_by_cluster) != set(cluster_ids):
        raise ValueError("Active Dreaming needs one externally produced rule per DBSCAN cluster")
    transitions: list[ReferenceCoreTransition] = []
    clustered_state = {"labels": labels, "clusters": cluster_ids}
    transitions.append(_transition("failure_clustered", {"labels": None}, clustered_state))
    semantic = list(inputs.semantic_memory_before)
    scenario_by_hint = {item.cluster_hint: item for item in inputs.counterfactual_scenarios}
    expected_hints = {str(cluster_id) for cluster_id in cluster_ids}
    if set(scenario_by_hint) != expected_hints:
        raise ValueError("Active Dreaming scenarios must exactly cover DBSCAN clusters")
    expected_scenario_ids = {item.scenario_id for item in inputs.counterfactual_scenarios}
    if set(scenario_execution_receipts) != expected_scenario_ids:
        raise ValueError("Active Dreaming execution receipts must exactly cover scenarios")
    if set(scenario_program_paths) != expected_scenario_ids:
        raise ValueError("Active Dreaming executable paths must exactly cover scenarios")
    committed: list[str] = []
    verified_receipt_count = 0
    for cluster_id in cluster_ids:
        hint = str(cluster_id)
        if hint not in scenario_by_hint:
            raise ValueError("Active Dreaming cluster has no executable counterfactual scenario")
        scenario = scenario_by_hint[hint]
        if scenario.scenario_id not in scenario_execution_receipts:
            raise ValueError("Active Dreaming scenario has no execution receipt")
        if scenario.scenario_id not in scenario_program_paths:
            raise ValueError("Active Dreaming scenario has no executable payload path")
        receipt = scenario_execution_receipts[scenario.scenario_id]
        rule = abstracted_rule_by_cluster[cluster_id]
        if not rule:
            raise ValueError("Active Dreaming abstracted rules must be non-empty")
        cluster_failures = tuple(
            failure
            for failure, label in zip(inputs.episodic_failures, labels, strict=True)
            if label == cluster_id
        )
        verify_counterfactual_execution(
            receipt,
            program_path=scenario_program_paths[scenario.scenario_id],
            expected_payload_sha256=scenario.executable_payload_sha256,
            expected_cluster_id=cluster_id,
            expected_failure_set_sha256=content_sha256(cluster_failures),
            expected_candidate_rule_sha256=content_sha256(rule),
            trusted_executor_key_id=trusted_executor_key_id,
            trusted_executor_public_key_sha256=trusted_executor_public_key_sha256,
        )
        verified_receipt_count += 1
        transitions.append(
            _transition(
                "counterfactual_scenario_executed_with_attested_receipt",
                {"scenario_id": scenario.scenario_id, "executed": False},
                {
                    "scenario_id": scenario.scenario_id,
                    "payload_sha256": scenario.executable_payload_sha256,
                    "execution_receipt_sha256": content_sha256(receipt),
                    "executed": True,
                },
            )
        )
        before = tuple(semantic)
        semantic.append(rule)
        committed.append(rule)
        transitions.append(
            _transition(
                "semantic_rule_committed_after_attested_execution",
                before,
                tuple(semantic),
            )
        )
    return ReferenceCoreResult(
        arm=inputs.arm,
        output={
            "cluster_labels": labels,
            "committed_rules": tuple(committed),
            "verified_execution_receipt_count": verified_receipt_count,
            "scenario_execution_performed_by_resource_bounded_executor": (
                verified_receipt_count == len(cluster_ids) and verified_receipt_count > 0
            ),
            "commit_gate_basis": "cluster_failure_rule_bound_executor_receipt",
        },
        transitions=tuple(transitions),
    )


def run_auto_dreamer_reference_core(
    inputs: AutoDreamerAdaptationInput,
) -> ReferenceCoreResult:
    frozen_memory_ids = {item.memory_id for item in inputs.typed_memory_bank}
    if any(
        memory_id not in frozen_memory_ids
        for trajectory in inputs.provenance_trajectories
        for memory_id in trajectory.source_memory_ids
    ):
        raise ValueError("Auto-Dreamer trajectory escaped the frozen memory bank")
    utility_by_memory: dict[str, float] = {}
    inspected: list[str] = []
    for trajectory in inputs.provenance_trajectories:
        utility = trajectory.downstream_reward + trajectory.counterfactual_masking_utility
        for memory_id in trajectory.source_memory_ids:
            utility_by_memory[memory_id] = utility_by_memory.get(memory_id, 0.0) + utility
        inspected.append(trajectory.trajectory_id)
    working_region = tuple(sorted(key for key, value in utility_by_memory.items() if value > 0.0))
    if not working_region:
        raise ValueError("Auto-Dreamer working region is empty under downstream utility")
    transitions = [
        _transition(
            "offline_region_selected",
            {"working_region": ()},
            {"working_region": working_region},
        ),
        _transition(
            "provenance_trajectory_inspected",
            {"inspected": ()},
            {"inspected": tuple(inspected)},
        ),
    ]
    replacement_set = tuple(
        item for item in inputs.replacement_candidates if set(item.supersedes) & set(working_region)
    )
    if not replacement_set:
        raise ValueError("Auto-Dreamer has no replacement candidate bound to its working region")
    transitions.append(
        _transition(
            "replacement_set_committed",
            {"replacement_ids": ()},
            {"replacement_ids": tuple(item.memory_id for item in replacement_set)},
        )
    )
    return ReferenceCoreResult(
        arm=inputs.arm,
        output={
            "working_region": working_region,
            "replacement_memory_ids": tuple(item.memory_id for item in replacement_set),
        },
        transitions=tuple(transitions),
    )


def run_trustmem_reference_core(
    inputs: TrustMemAdaptationInput,
    *,
    minimum_verifier_score: float = 0.8,
) -> ReferenceCoreResult:
    if not 0.0 <= minimum_verifier_score <= 1.0:
        raise ValueError("TRUSTMEM verifier threshold must be within [0, 1]")
    transitions: list[ReferenceCoreTransition] = []
    accepted: list[str] = []
    for candidate in inputs.candidate_transitions:
        previous_by_id = {item.memory_id: item for item in candidate.previous_memory_state}
        proposed_by_id = {item.memory_id: item for item in candidate.proposed_memory_state}
        proposed_evidence = {
            evidence_id
            for item in candidate.proposed_memory_state
            for evidence_id in item.evidence_ids
        }
        coverage = len(set(candidate.required_evidence_ids) & proposed_evidence) / len(
            set(candidate.required_evidence_ids)
        )
        protected = set(candidate.protected_memory_ids)
        preservation = (
            sum(
                memory_id in proposed_by_id
                and proposed_by_id[memory_id].content == previous_by_id[memory_id].content
                for memory_id in protected
            )
            / len(protected)
            if protected
            else 1.0
        )
        available_evidence = set(candidate.chunk_evidence)
        changed_items = tuple(
            item
            for item in candidate.proposed_memory_state
            if item.memory_id not in previous_by_id
            or previous_by_id[item.memory_id].content != item.content
        )
        faithful_items = sum(
            bool(item.evidence_ids) and set(item.evidence_ids).issubset(available_evidence)
            for item in changed_items
        )
        faithfulness = faithful_items / len(changed_items) if changed_items else 0.0
        checks = (
            ("coverage_verified", coverage),
            ("preservation_verified", preservation),
            ("faithfulness_verified", faithfulness),
        )
        state: dict[str, Any] = {"transition_id": candidate.transition_id, "checks": ()}
        for event, score in checks:
            after = {**state, "checks": (*state["checks"], (event, score))}
            transitions.append(_transition(event, state, after))
            state = after
        verifier_floor = min(
            coverage,
            preservation,
            faithfulness,
        )
        if verifier_floor >= minimum_verifier_score:
            accepted.append(candidate.transition_id)
    return ReferenceCoreResult(
        arm=inputs.arm,
        output={"accepted_transition_ids": tuple(accepted)},
        transitions=tuple(transitions),
    )


_CATEGORY_WEIGHTS = {
    "identity": 1.0,
    "decision": 0.95,
    "lesson": 0.85,
    "convention": 0.80,
    "preference": 0.70,
    "project": 0.65,
    "environment": 0.50,
    "user": 0.50,
    "integration": 0.50,
}

_AMAC_CATEGORY_PRIORS = {
    "identity": 0.9,
    "decision": 0.85,
    "lesson": 0.85,
    "convention": 0.8,
    "preference": 0.75,
    "user": 0.75,
    "project": 0.7,
    "integration": 0.7,
    "environment": 0.6,
}


def run_brainctl_reference_core(inputs: BrainctlAdaptationInput) -> ReferenceCoreResult:
    similarities = tuple(
        1.0 - _cosine_distance(inputs.candidate_embedding, neighbor)
        for neighbor in inputs.neighbor_embeddings
    )
    # Pinned brainctl initializes max_similarity at zero, so negative cosine
    # similarities never increase novelty beyond 1.0.
    novelty = 1.0 - max((0.0, *similarities))
    if inputs.scope.startswith("agent:"):
        scope_weight = 1.0
    elif inputs.scope.startswith("project:"):
        scope_weight = 0.75
    else:
        scope_weight = 0.50
    category_weight = _CATEGORY_WEIGHTS.get(inputs.category, 0.50)
    content_type_prior = _AMAC_CATEGORY_PRIORS.get(inputs.category, 0.50)
    pre_worthiness = (
        0.15 * inputs.future_utility
        + 0.15 * inputs.source_trust
        + 0.20 * novelty
        + 0.10 * inputs.temporal_recency
        + 0.40 * content_type_prior
    )
    long_term_utility = (category_weight * scope_weight * inputs.recall_rate) ** (1.0 / 3.0)
    importance = inputs.confidence
    base_score = novelty * 0.45 + long_term_utility * 0.25 + importance * 0.20 + scope_weight * 0.10
    score = min(1.0, base_score * inputs.arousal_gain)
    if not isfinite(score):
        raise ValueError("brainctl worthiness score is not finite")
    transitions = [
        _transition(
            "source_trust_scored",
            {"source": inputs.source, "trust": None},
            {"source": inputs.source, "trust": inputs.source_trust},
        )
    ]
    accepted = pre_worthiness >= 0.3 and score >= 0.3
    gate_state = {
        "pre_gate": pre_worthiness,
        "write_gate": score,
        "accepted": accepted,
    }
    transitions.append(_transition("two_stage_write_gate_executed", {"accepted": None}, gate_state))
    tier = "SKIP" if not accepted else "CONSTRUCT_ONLY" if score < 0.7 else "FULL_EVOLUTION"
    transitions.append(_transition("memory_tier_routed", {"tier": None}, {"tier": tier}))
    return ReferenceCoreResult(
        arm=inputs.arm,
        output={
            "novelty": novelty,
            "long_term_utility": long_term_utility,
            "pre_worthiness": pre_worthiness,
            "base_score": base_score,
            "worthiness_score": score,
            "write_tier": tier,
            "supersedes_id": inputs.supersedes_id,
            "valence_scale_observed_but_not_applied_by_official_write_gate": (inputs.valence_scale),
        },
        transitions=tuple(transitions),
    )


__all__ = [
    "PROTOCOL_ID",
    "ReferenceCoreResult",
    "ReferenceCoreTransition",
    "cluster_active_dreaming_failures",
    "execution_log_entries_from_reference_core",
    "mechanism_receipts_from_reference_core",
    "run_active_dreaming_reference_core",
    "run_amg_reference_core",
    "run_auto_dreamer_reference_core",
    "run_brainctl_reference_core",
    "run_o_star_reference_core",
    "run_trustmem_reference_core",
]
