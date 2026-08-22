"""Budgeted M20 world-model query contracts."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import Field, JsonValue, model_validator

from .base import (
    BaseRecordMetadata,
    ContractModel,
    EntityRef,
    EvidenceRef,
    InputWatermark,
    NonNegativeInt,
    PositiveInt,
    Probability,
    ValidTimeInterval,
)


class QueryConsistencyMode(StrEnum):
    LATEST_COMPLETE_PROJECTION = "latest_complete_projection"
    AT_INPUT_WATERMARK = "at_input_watermark"
    HISTORICAL_VALID_TIME = "historical_valid_time"


class EvidencePathNodeKind(StrEnum):
    CANDIDATE = "candidate"
    EVENT = "event"
    ACTOR_EVIDENCE = "actor_evidence"
    OBSERVATION_OPPORTUNITY = "observation_opportunity"
    CHANGE_POINT = "change_point"
    REVISION = "revision"
    SOURCE = "source"


class EvidencePathRelation(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    DERIVED_FROM = "derived_from"
    ATTRIBUTED_TO = "attributed_to"
    REVISED_BY = "revised_by"


class EvidencePathNode(ContractModel):
    node_id: UUID
    node_kind: EvidencePathNodeKind
    claim_code: str = Field(min_length=1)
    source_record_id: UUID | None = None
    evidence_refs: tuple[EvidenceRef, ...] = ()

    @model_validator(mode="after")
    def require_auditable_leaf(self) -> EvidencePathNode:
        if self.node_kind == EvidencePathNodeKind.SOURCE:
            if self.source_record_id is None and not self.evidence_refs:
                raise ValueError("source evidence-path nodes require a record or evidence ref")
        return self


class EvidencePathEdge(ContractModel):
    source_node_id: UUID
    target_node_id: UUID
    relation: EvidencePathRelation


class AuditableEvidencePath(ContractModel):
    path_id: UUID
    candidate_rank: PositiveInt
    root_candidate_node_id: UUID
    nodes: tuple[EvidencePathNode, ...] = Field(min_length=2)
    edges: tuple[EvidencePathEdge, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_graph(self) -> AuditableEvidencePath:
        node_by_id = {node.node_id: node for node in self.nodes}
        if len(node_by_id) != len(self.nodes):
            raise ValueError("evidence-path node IDs must be unique")
        root = node_by_id.get(self.root_candidate_node_id)
        if root is None or root.node_kind != EvidencePathNodeKind.CANDIDATE:
            raise ValueError("evidence path requires a candidate root node")
        adjacency: dict[UUID, set[UUID]] = {node_id: set() for node_id in node_by_id}
        for edge in self.edges:
            if edge.source_node_id not in node_by_id or edge.target_node_id not in node_by_id:
                raise ValueError("evidence-path edges must reference declared nodes")
            adjacency[edge.source_node_id].add(edge.target_node_id)

        visiting: set[UUID] = set()
        visited: set[UUID] = set()

        def visit(node_id: UUID) -> None:
            if node_id in visiting:
                raise ValueError("evidence path must be acyclic")
            if node_id in visited:
                return
            visiting.add(node_id)
            for child_id in adjacency[node_id]:
                visit(child_id)
            visiting.remove(node_id)
            visited.add(node_id)

        visit(self.root_candidate_node_id)
        if visited != set(node_by_id):
            raise ValueError("every evidence-path node must be reachable from the candidate")
        for node_id, children in adjacency.items():
            node = node_by_id[node_id]
            if not children and node.source_record_id is None and not node.evidence_refs:
                raise ValueError("terminal evidence-path nodes require traceable evidence")
        return self

    @property
    def source_record_ids(self) -> frozenset[UUID]:
        direct = {node.source_record_id for node in self.nodes if node.source_record_id is not None}
        referenced = {
            reference.source_record_id for node in self.nodes for reference in node.evidence_refs
        }
        return frozenset(direct | referenced)


class BaselineClosureGate(ContractModel):
    """Evidence-backed gate that prevents M20-M22 from outrunning the baseline."""

    habit_replay_stable: bool
    actor_contamination_bounded: bool
    cheh_provenance_complete: bool
    shift_attribution_validated: bool
    utility_policy_noninferior: bool
    schemas_frozen: bool
    evidence_refs: tuple[EvidenceRef, ...] = Field(min_length=1)

    @property
    def passed(self) -> bool:
        return all(
            (
                self.habit_replay_stable,
                self.actor_contamination_bounded,
                self.cheh_provenance_complete,
                self.shift_attribution_validated,
                self.utility_policy_noninferior,
                self.schemas_frozen,
            )
        )


class AuditedEvidenceClaim(ContractModel):
    statement: str = Field(min_length=1)
    supporting_node_ids: tuple[UUID, ...] = Field(min_length=1)
    contradicting_node_ids: tuple[UUID, ...] = ()


class AuditableQueryExplanation(ContractModel):
    evidence_path: AuditableEvidencePath
    claims: tuple[AuditedEvidenceClaim, ...] = Field(min_length=1)
    renderer_model_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def bind_claims_to_path(self) -> AuditableQueryExplanation:
        node_ids = {node.node_id for node in self.evidence_path.nodes}
        cited = {
            node_id
            for claim in self.claims
            for node_id in (*claim.supporting_node_ids, *claim.contradicting_node_ids)
        }
        if not cited.issubset(node_ids):
            raise ValueError("explanation claims may cite only evidence-path nodes")
        return self


class RetrievalBudget(ContractModel):
    max_events: PositiveInt | None = None
    max_relations: PositiveInt | None = None
    max_vector_candidates: PositiveInt | None = None
    max_wall_time_ms: PositiveInt | None = None
    max_memory_bytes: PositiveInt | None = None

    @model_validator(mode="after")
    def require_a_limit(self) -> RetrievalBudget:
        if all(value is None for value in self.__dict__.values()):
            raise ValueError("retrieval_budget must set at least one finite limit")
        return self


class RetrievalCoverage(ContractModel):
    events_scanned: NonNegativeInt = 0
    events_available: NonNegativeInt | None = None
    relations_scanned: NonNegativeInt = 0
    relations_available: NonNegativeInt | None = None
    vector_candidates_scanned: NonNegativeInt = 0
    vector_candidates_available: NonNegativeInt | None = None
    wall_time_ms: NonNegativeInt = 0
    peak_memory_bytes: NonNegativeInt = 0
    budget_exhausted: bool = False
    exhaustion_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_coverage(self) -> RetrievalCoverage:
        pairs = (
            (self.events_scanned, self.events_available, "events"),
            (self.relations_scanned, self.relations_available, "relations"),
            (
                self.vector_candidates_scanned,
                self.vector_candidates_available,
                "vector_candidates",
            ),
        )
        for scanned, available, name in pairs:
            if available is not None and scanned > available:
                raise ValueError(f"{name}_scanned cannot exceed {name}_available")
        if self.budget_exhausted and not self.exhaustion_reasons:
            raise ValueError("budget exhaustion must include at least one reason")
        if not self.budget_exhausted and self.exhaustion_reasons:
            raise ValueError("non-exhausted query cannot include exhaustion reasons")
        return self


class QueryConstraint(ContractModel):
    field: str = Field(min_length=1)
    operator: str = Field(min_length=1)
    value: JsonValue


class WorldModelQuery(ContractModel):
    metadata: BaseRecordMetadata
    constraints: tuple[QueryConstraint, ...] = Field(min_length=1)
    consistency_mode: QueryConsistencyMode
    retrieval_budget: RetrievalBudget
    at_input_watermark: InputWatermark | None = None
    historical_valid_time: ValidTimeInterval | None = None

    @model_validator(mode="after")
    def validate_consistency_target(self) -> WorldModelQuery:
        if (
            self.consistency_mode == QueryConsistencyMode.AT_INPUT_WATERMARK
            and self.at_input_watermark is None
        ):
            raise ValueError("at_input_watermark mode requires an input watermark")
        if (
            self.consistency_mode == QueryConsistencyMode.HISTORICAL_VALID_TIME
            and self.historical_valid_time is None
        ):
            raise ValueError("historical_valid_time mode requires a valid-time interval")
        return self


class QueryCandidate(ContractModel):
    rank: PositiveInt
    entity: EntityRef
    posterior_probability: Probability
    evidence_refs: tuple[EvidenceRef, ...] = ()
    evidence_path_id: UUID | None = None


class ProjectionLag(ContractModel):
    projection_commit_seq: NonNegativeInt
    latest_normative_commit_seq: NonNegativeInt

    @model_validator(mode="after")
    def validate_order(self) -> ProjectionLag:
        if self.projection_commit_seq > self.latest_normative_commit_seq:
            raise ValueError("projection cannot be ahead of normative inputs")
        return self


class WorldModelQueryResult(ContractModel):
    metadata: BaseRecordMetadata
    query_id: UUID
    projection_id: UUID
    candidates: tuple[QueryCandidate, ...]
    retrieval_coverage: RetrievalCoverage
    projection_lag: ProjectionLag | None = None
    evidence_paths: tuple[AuditableEvidencePath, ...] = ()
    baseline_closure_gate: BaselineClosureGate | None = None

    @model_validator(mode="after")
    def validate_ranking(self) -> WorldModelQueryResult:
        ranks = [candidate.rank for candidate in self.candidates]
        if ranks != list(range(1, len(ranks) + 1)):
            raise ValueError("candidate ranks must be contiguous and start at 1")
        candidate_path_ids = {
            candidate.evidence_path_id
            for candidate in self.candidates
            if candidate.evidence_path_id is not None
        }
        declared_path_ids = {path.path_id for path in self.evidence_paths}
        if len(declared_path_ids) != len(self.evidence_paths):
            raise ValueError("query evidence path IDs must be unique")
        if candidate_path_ids != declared_path_ids:
            raise ValueError("candidate and declared evidence-path bindings must match")
        if self.evidence_paths:
            if self.baseline_closure_gate is None or not self.baseline_closure_gate.passed:
                raise ValueError("auditable query paths require a passed baseline closure gate")
            if len(candidate_path_ids) != len(self.candidates):
                raise ValueError("every returned candidate requires an auditable evidence path")
            path_by_id = {path.path_id: path for path in self.evidence_paths}
            for candidate in self.candidates:
                assert candidate.evidence_path_id is not None
                path = path_by_id[candidate.evidence_path_id]
                if path.candidate_rank != candidate.rank:
                    raise ValueError("evidence path rank does not match its candidate")
                cited_records = {
                    reference.source_record_id for reference in candidate.evidence_refs
                }
                if not cited_records.issubset(path.source_record_ids):
                    raise ValueError("candidate evidence refs must be present in its audit path")
        elif self.baseline_closure_gate is not None:
            raise ValueError("baseline closure gate is only attached to auditable query paths")
        return self
