"""Typed, content-bound adaptation inputs for the six external v0.6 arms."""

from __future__ import annotations

from math import isfinite
from typing import Literal, Self

from pydantic import Field, model_validator

from cpswm.contracts.base import ContractModel, Probability
from cpswm.system.reproducibility import content_sha256

PROTOCOL_ID = "structure-two-external-adaptation-inputs@0.6"


def _validate_vector(vector: tuple[float, ...], *, field_name: str) -> None:
    if not vector or any(not isfinite(value) for value in vector):
        raise ValueError(f"{field_name} must be a non-empty finite vector")


class AMGEventEvidence(ContractModel):
    event_id: str = Field(min_length=1)
    source_likelihood: Probability
    actor_likelihoods: dict[str, Probability] = Field(min_length=1)
    mechanism_likelihoods: dict[str, Probability] = Field(min_length=1)
    ordered_role_likelihoods: dict[str, Probability] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_likelihood_support(self) -> Self:
        if set(self.mechanism_likelihoods) != {"direct", "handoff"}:
            raise ValueError("AMG mechanisms must be exactly direct and handoff")
        values = (
            self.source_likelihood,
            *self.actor_likelihoods.values(),
            *self.mechanism_likelihoods.values(),
            *self.ordered_role_likelihoods.values(),
        )
        if any(value <= 0.0 or value >= 1.0 for value in values):
            raise ValueError("AMG likelihoods must be open probabilities")
        expected_roles = {
            f"{left}->{right}"
            for left in self.actor_likelihoods
            for right in self.actor_likelihoods
            if left != right
        }
        if set(self.ordered_role_likelihoods) != expected_roles:
            raise ValueError("AMG ordered roles must cover every distinct actor pair")
        return self


class AMGCrossEventConstraint(ContractModel):
    kind: Literal["same_responsible_actor", "different_responsible_actor"]
    left_event_id: str = Field(min_length=1)
    right_event_id: str = Field(min_length=1)


class AMGAdaptationInput(ContractModel):
    arm: Literal["corrected_amg"] = "corrected_amg"
    events: tuple[AMGEventEvidence, ...] = Field(min_length=1)
    hierarchy_edges: tuple[tuple[str, str], ...] = Field(min_length=1)
    cross_event_constraints: tuple[AMGCrossEventConstraint, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_event_references(self) -> Self:
        event_ids = {item.event_id for item in self.events}
        if len(event_ids) != len(self.events):
            raise ValueError("AMG event ids must be unique")
        if any(
            parent not in event_ids or child not in event_ids
            for parent, child in self.hierarchy_edges
        ):
            raise ValueError("AMG hierarchy edges must reference declared events")
        if any(
            item.left_event_id not in event_ids
            or item.right_event_id not in event_ids
            or item.left_event_id == item.right_event_id
            for item in self.cross_event_constraints
        ):
            raise ValueError("AMG cross-event constraints must reference two declared events")
        return self


class OStarSceneNode(ContractModel):
    node_id: str = Field(min_length=1)
    node_type: Literal["room", "furniture", "compartment", "object"]
    parent_id: str | None = None


class OStarObservation(ContractModel):
    target_id: str = Field(min_length=1)
    location_id: str = Field(min_length=1)
    outcome: Literal["hit", "miss"]
    opportunistic: bool = False


class OStarAdaptationInput(ContractModel):
    arm: Literal["o_star_matched"] = "o_star_matched"
    scene_nodes: tuple[OStarSceneNode, ...] = Field(min_length=2)
    feasible_target_locations: dict[str, tuple[str, ...]] = Field(min_length=1)
    llm_day_zero_priors: dict[str, dict[str, Probability]] = Field(min_length=1)
    observations: tuple[OStarObservation, ...] = Field(min_length=1)
    navigation_and_inspection_costs: dict[str, float] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_scene(self) -> Self:
        node_ids = {item.node_id for item in self.scene_nodes}
        if len(node_ids) != len(self.scene_nodes):
            raise ValueError("O-STaR scene node ids must be unique")
        if any(
            item.parent_id is not None and item.parent_id not in node_ids
            for item in self.scene_nodes
        ):
            raise ValueError("O-STaR parent ids must reference scene nodes")
        if set(self.feasible_target_locations) != set(self.llm_day_zero_priors):
            raise ValueError("O-STaR target sets for geometry and priors must match")
        for target, locations in self.feasible_target_locations.items():
            if not locations or not set(locations).issubset(node_ids):
                raise ValueError("O-STaR feasible locations must be non-empty scene-node subsets")
            if not set(locations).issubset(self.llm_day_zero_priors[target]):
                raise ValueError("O-STaR priors must cover every feasible location")
        feasible_locations = {
            location
            for locations in self.feasible_target_locations.values()
            for location in locations
        }
        if set(self.navigation_and_inspection_costs) != feasible_locations:
            raise ValueError("O-STaR costs must exactly cover feasible locations")
        if any(
            value <= 0.0 or not isfinite(value)
            for value in self.navigation_and_inspection_costs.values()
        ):
            raise ValueError("O-STaR costs must be finite and positive")
        if not any(item.opportunistic for item in self.observations):
            raise ValueError("O-STaR input must contain opportunistic non-target observations")
        return self


class FailureEpisode(ContractModel):
    episode_id: str = Field(min_length=1)
    content: str = Field(min_length=1)
    embedding: tuple[float, ...]
    outcome: Literal["FAILURE"] = "FAILURE"

    @model_validator(mode="after")
    def validate_embedding(self) -> Self:
        _validate_vector(self.embedding, field_name="failure embedding")
        return self


class CounterfactualScenario(ContractModel):
    scenario_id: str = Field(min_length=1)
    cluster_hint: str = Field(min_length=1)
    executable_payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ActiveDreamingAdaptationInput(ContractModel):
    arm: Literal["active_dreaming_matched"] = "active_dreaming_matched"
    episodic_failures: tuple[FailureEpisode, ...] = Field(min_length=2)
    semantic_memory_before: tuple[str, ...]
    counterfactual_scenarios: tuple[CounterfactualScenario, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_dimensions(self) -> Self:
        dimensions = {len(item.embedding) for item in self.episodic_failures}
        if len(dimensions) != 1:
            raise ValueError("Active Dreaming failure embeddings must have one dimension")
        scenario_ids = tuple(item.scenario_id for item in self.counterfactual_scenarios)
        if len(set(scenario_ids)) != len(scenario_ids):
            raise ValueError("Active Dreaming scenario ids must be unique")
        cluster_hints = tuple(item.cluster_hint for item in self.counterfactual_scenarios)
        if len(set(cluster_hints)) != len(cluster_hints):
            raise ValueError("Active Dreaming cluster hints must be unique")
        return self


class ProvenanceTrajectory(ContractModel):
    trajectory_id: str = Field(min_length=1)
    source_memory_ids: tuple[str, ...] = Field(min_length=1)
    downstream_reward: float
    counterfactual_masking_utility: float


class TypedMemory(ContractModel):
    memory_id: str = Field(min_length=1)
    memory_type: Literal["episodic", "semantic", "procedural"]
    content: str = Field(min_length=1)
    supersedes: tuple[str, ...] = ()


class AutoDreamerAdaptationInput(ContractModel):
    arm: Literal["auto_dreamer_matched"] = "auto_dreamer_matched"
    session_ids: tuple[str, ...] = Field(min_length=2)
    typed_memory_bank: tuple[TypedMemory, ...] = Field(min_length=1)
    provenance_trajectories: tuple[ProvenanceTrajectory, ...] = Field(min_length=1)
    offline_boundary_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    replacement_candidates: tuple[TypedMemory, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_provenance_references(self) -> Self:
        bank_ids = tuple(item.memory_id for item in self.typed_memory_bank)
        if len(set(bank_ids)) != len(bank_ids):
            raise ValueError("Auto-Dreamer frozen memory-bank ids must be unique")
        trajectory_ids = tuple(item.trajectory_id for item in self.provenance_trajectories)
        if len(set(trajectory_ids)) != len(trajectory_ids):
            raise ValueError("Auto-Dreamer trajectory ids must be unique")
        unknown_sources = {
            memory_id
            for trajectory in self.provenance_trajectories
            for memory_id in trajectory.source_memory_ids
            if memory_id not in bank_ids
        }
        if unknown_sources:
            raise ValueError(
                "Auto-Dreamer trajectories reference unknown frozen memories: "
                f"{sorted(unknown_sources)}"
            )
        replacement_ids = tuple(item.memory_id for item in self.replacement_candidates)
        if len(set(replacement_ids)) != len(replacement_ids):
            raise ValueError("Auto-Dreamer replacement memory ids must be unique")
        if set(replacement_ids) & set(bank_ids):
            raise ValueError("Auto-Dreamer replacement ids must be new")
        unknown_superseded = {
            memory_id
            for candidate in self.replacement_candidates
            for memory_id in candidate.supersedes
            if memory_id not in bank_ids
        }
        if unknown_superseded:
            raise ValueError(
                "Auto-Dreamer replacements supersede unknown frozen memories: "
                f"{sorted(unknown_superseded)}"
            )
        return self


class TrustMemStateItem(ContractModel):
    memory_id: str = Field(min_length=1)
    content: str = Field(min_length=1)
    evidence_ids: tuple[str, ...] = ()


class TrustMemTransition(ContractModel):
    transition_id: str = Field(min_length=1)
    operation: Literal["WRITE", "REVISE", "PRUNE"]
    chunk_evidence: tuple[str, ...] = Field(min_length=1)
    previous_memory_state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposed_memory_state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    previous_memory_state: tuple[TrustMemStateItem, ...]
    proposed_memory_state: tuple[TrustMemStateItem, ...]
    required_evidence_ids: tuple[str, ...] = Field(min_length=1)
    protected_memory_ids: tuple[str, ...]
    downstream_task_outcome: float

    @model_validator(mode="after")
    def validate_bound_states(self) -> Self:
        previous_ids = tuple(item.memory_id for item in self.previous_memory_state)
        proposed_ids = tuple(item.memory_id for item in self.proposed_memory_state)
        if len(set(previous_ids)) != len(previous_ids) or len(set(proposed_ids)) != len(
            proposed_ids
        ):
            raise ValueError("TRUSTMEM state memory ids must be unique")
        if content_sha256(self.previous_memory_state) != self.previous_memory_state_sha256:
            raise ValueError("TRUSTMEM previous state hash does not match its content")
        if content_sha256(self.proposed_memory_state) != self.proposed_memory_state_sha256:
            raise ValueError("TRUSTMEM proposed state hash does not match its content")
        if self.previous_memory_state_sha256 == self.proposed_memory_state_sha256:
            raise ValueError("TRUSTMEM candidate transition must change memory state")
        if not set(self.protected_memory_ids).issubset(previous_ids):
            raise ValueError("TRUSTMEM protected ids must exist in the previous state")
        if len(set(self.chunk_evidence)) != len(self.chunk_evidence):
            raise ValueError("TRUSTMEM chunk evidence ids must be unique")
        if not set(self.required_evidence_ids).issubset(self.chunk_evidence):
            raise ValueError("TRUSTMEM required evidence must exist in chunk evidence")
        return self


class TrustMemAdaptationInput(ContractModel):
    arm: Literal["trustmem_matched"] = "trustmem_matched"
    candidate_transitions: tuple[TrustMemTransition, ...] = Field(min_length=3)

    @model_validator(mode="after")
    def validate_operations(self) -> Self:
        if {item.operation for item in self.candidate_transitions} != {"WRITE", "REVISE", "PRUNE"}:
            raise ValueError("TRUSTMEM input must contain WRITE, REVISE, and PRUNE candidates")
        return self


class BrainctlAdaptationInput(ContractModel):
    arm: Literal["brainctl_matched"] = "brainctl_matched"
    content: str = Field(min_length=1)
    candidate_embedding: tuple[float, ...]
    neighbor_embeddings: tuple[tuple[float, ...], ...]
    source: Literal["human_verified", "mcp_tool", "llm_inference", "external_doc"]
    source_trust: Probability
    category: str = Field(min_length=1)
    scope: str = Field(min_length=1)
    confidence: Probability
    future_utility: Probability = 0.5
    temporal_recency: Probability = 1.0
    recall_rate: Probability
    arousal_gain: float = Field(ge=0.5, le=2.0)
    valence_scale: float = Field(ge=0.0, le=2.0)
    lifecycle_state: Literal["new", "active", "superseded", "quarantined", "retired"]
    supersedes_id: str | None = None

    @model_validator(mode="after")
    def validate_embeddings_and_lifecycle(self) -> Self:
        _validate_vector(self.candidate_embedding, field_name="brainctl candidate embedding")
        if any(len(item) != len(self.candidate_embedding) for item in self.neighbor_embeddings):
            raise ValueError("brainctl neighbor embeddings must match candidate dimensions")
        for item in self.neighbor_embeddings:
            _validate_vector(item, field_name="brainctl neighbor embedding")
        if self.lifecycle_state == "superseded" and self.supersedes_id is None:
            raise ValueError("brainctl superseded lifecycle needs a supersedes id")
        source_trust_weights = {
            "human_verified": 1.0,
            "mcp_tool": 0.85,
            "llm_inference": 0.7,
            "external_doc": 0.5,
        }
        if self.source_trust != source_trust_weights[self.source]:
            raise ValueError("brainctl source trust must match the official source class")
        return self


class CompleteExternalAdaptationInputsV06(ContractModel):
    protocol: Literal["structure-two-external-adaptation-inputs@0.6"] = (
        "structure-two-external-adaptation-inputs@0.6"
    )
    corrected_amg: AMGAdaptationInput
    o_star_matched: OStarAdaptationInput
    active_dreaming_matched: ActiveDreamingAdaptationInput
    auto_dreamer_matched: AutoDreamerAdaptationInput
    trustmem_matched: TrustMemAdaptationInput
    brainctl_matched: BrainctlAdaptationInput

    @property
    def content_sha256(self) -> str:
        return content_sha256(self)


__all__ = [
    "PROTOCOL_ID",
    "AMGAdaptationInput",
    "AMGCrossEventConstraint",
    "AMGEventEvidence",
    "ActiveDreamingAdaptationInput",
    "AutoDreamerAdaptationInput",
    "BrainctlAdaptationInput",
    "CompleteExternalAdaptationInputsV06",
    "CounterfactualScenario",
    "FailureEpisode",
    "OStarAdaptationInput",
    "OStarObservation",
    "OStarSceneNode",
    "ProvenanceTrajectory",
    "TrustMemAdaptationInput",
    "TrustMemStateItem",
    "TrustMemTransition",
    "TypedMemory",
]
