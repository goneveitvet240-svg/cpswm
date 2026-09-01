"""Official, method-injectable runtime wiring for Structure One."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from cpswm.contracts import (
    ActionOutcomeLikelihoodModel,
    DecisionContextBinding,
    ExecutionFeedbackRecord,
)
from cpswm.contracts.base import EvidenceRef
from cpswm.contracts.grounded_search import CompiledSemanticQuery
from cpswm.system.continual.execution_feedback_projector import (
    ExecutionFeedbackProjector,
)
from cpswm.system.structure_one_ingress import (
    ActorInputAuthority,
    EvidenceAuthority,
    FactEligibility,
    IngressStatus,
    StructureOneCertifiedIngress,
    StructureOneContentKind,
    StructureOneIngressReceipt,
    StructureOneModule,
    StructureOneWriteRequest,
)


class ObjectIdentityBackend(Protocol):
    def resolve(self, observation: object) -> object: ...


class CommonsenseProvider(Protocol):
    def describe(self, entity: object) -> object: ...


class HiddenEventBackend(Protocol):
    def infer(self, observation: object) -> Sequence[object]: ...


class StructureOneQueryEngine(Protocol):
    def execute(self, query: CompiledSemanticQuery) -> object: ...


class StructureOneQueryCompiler(Protocol):
    def compile(
        self,
        utterance: str,
        *,
        input_evidence_refs: tuple[EvidenceRef, ...] = (),
    ) -> CompiledSemanticQuery: ...


class AssistancePlanner(Protocol):
    def plan(self, query: CompiledSemanticQuery, query_result: object) -> object: ...


@dataclass(frozen=True, slots=True)
class StructureOneReadiness:
    certified_ingress: bool
    deterministic_m21_baseline: bool
    unresolved_design_choices: tuple[str, ...]
    unwired_runtime_backends: tuple[str, ...]

    @property
    def fully_operational(self) -> bool:
        return not self.unresolved_design_choices and not self.unwired_runtime_backends


@dataclass(frozen=True, slots=True)
class FeedbackIngressResult:
    projected_evidence: object
    receipt: StructureOneIngressReceipt


class StructureOneRuntime:
    """Single certified runtime without selecting unresolved research methods."""

    def __init__(
        self,
        *,
        ingress: StructureOneCertifiedIngress,
        query_compiler: StructureOneQueryCompiler,
        identity_backend: ObjectIdentityBackend | None = None,
        commonsense_provider: CommonsenseProvider | None = None,
        hidden_event_backend: HiddenEventBackend | None = None,
        query_engine: StructureOneQueryEngine | None = None,
        assistance_planner: AssistancePlanner | None = None,
        feedback_projector: ExecutionFeedbackProjector | None = None,
    ) -> None:
        self.ingress = ingress
        self.query_compiler = query_compiler
        self.identity_backend = identity_backend
        self.commonsense_provider = commonsense_provider
        self.hidden_event_backend = hidden_event_backend
        self.query_engine = query_engine
        self.assistance_planner = assistance_planner
        self.feedback_projector = feedback_projector or ExecutionFeedbackProjector()

    def readiness(self) -> StructureOneReadiness:
        unresolved: list[str] = []
        unwired: list[str] = []
        if self.identity_backend is None:
            unresolved.append("cross_day_object_identity_method")
        if self.commonsense_provider is None:
            unresolved.append("commonsense_and_object_property_source")
        if self.hidden_event_backend is None:
            unresolved.append("hidden_event_inference_method")
        if not self.ingress.has_backend(StructureOneModule.HABIT_LEDGER):
            unresolved.append("formal_habit_backend_replacement")
        if self.query_engine is None:
            unwired.append("world_model_query_engine")
        if self.assistance_planner is None:
            unwired.append("search_place_ask_planner")
        if not self.ingress.has_backend(StructureOneModule.BELIEF_STATE):
            unwired.append("belief_state_backend")
        if not self.ingress.has_backend(StructureOneModule.HIDDEN_EVENT_LEDGER):
            unwired.append("hidden_event_ledger_backend")
        return StructureOneReadiness(
            certified_ingress=True,
            deterministic_m21_baseline=True,
            unresolved_design_choices=tuple(unresolved),
            unwired_runtime_backends=tuple(unwired),
        )

    def submit(
        self, request: StructureOneWriteRequest, payload: object
    ) -> StructureOneIngressReceipt:
        return self.ingress.submit(request, payload)

    def compile_query(
        self,
        utterance: str,
        *,
        input_evidence_refs: tuple[EvidenceRef, ...] = (),
    ) -> CompiledSemanticQuery:
        return self.query_compiler.compile(utterance, input_evidence_refs=input_evidence_refs)

    def answer_query(self, query: CompiledSemanticQuery) -> object:
        if self.query_engine is None:
            raise RuntimeError("world_model_query_engine is an unresolved runtime binding")
        return self.query_engine.execute(query)

    def plan_assistance(self, query: CompiledSemanticQuery) -> object:
        if self.query_engine is None:
            raise RuntimeError("world_model_query_engine is an unresolved runtime binding")
        if self.assistance_planner is None:
            raise RuntimeError("search_place_ask_planner is an unresolved method choice")
        result = self.query_engine.execute(query)
        return self.assistance_planner.plan(query, result)

    def infer_hidden_events(
        self,
        observation: object,
        *,
        source_record_ids: tuple[UUID, ...],
        actor_input_authority: ActorInputAuthority = ActorInputAuthority.ROBOT_POSTERIOR,
    ) -> tuple[StructureOneIngressReceipt, ...]:
        if self.hidden_event_backend is None:
            raise RuntimeError("hidden_event_inference_method is unresolved")
        receipts: list[StructureOneIngressReceipt] = []
        for candidate in self.hidden_event_backend.infer(observation):
            receipts.append(
                self.ingress.submit(
                    StructureOneWriteRequest(
                        target_module=StructureOneModule.HIDDEN_EVENT_LEDGER,
                        content_kind=StructureOneContentKind.INFERRED_EVENT,
                        authority=EvidenceAuthority.ROBOT_INFERENCE,
                        fact_eligibility=FactEligibility.HYPOTHESIS_ONLY,
                        source_record_ids=source_record_ids,
                        actor_input_authority=actor_input_authority,
                    ),
                    candidate,
                )
            )
        return tuple(receipts)

    def ingest_execution_feedback(
        self,
        feedback: ExecutionFeedbackRecord,
        *,
        binding: DecisionContextBinding,
        likelihood: ActionOutcomeLikelihoodModel,
    ) -> FeedbackIngressResult:
        prepared = self.feedback_projector.prepare_execution_feedback(
            feedback=feedback,
            binding=binding,
            likelihood_model=likelihood,
        )
        projected = prepared
        target = (
            StructureOneModule.BELIEF_STATE
            if prepared.route.value == "target_presence"
            else StructureOneModule.HIDDEN_EVENT_LEDGER
        )
        eligibility = (
            FactEligibility.EVIDENCE
            if target is StructureOneModule.BELIEF_STATE
            else FactEligibility.HYPOTHESIS_ONLY
        )
        receipt = self.ingress.submit(
            StructureOneWriteRequest(
                target_module=target,
                content_kind=StructureOneContentKind.EXECUTION_FEEDBACK,
                authority=EvidenceAuthority.EXECUTION_FEEDBACK,
                fact_eligibility=eligibility,
                source_record_ids=(feedback.metadata.record_id,),
                actor_input_authority=ActorInputAuthority.ROBOT_POSTERIOR,
            ),
            projected,
        )
        if receipt.status is IngressStatus.APPLIED:
            self.feedback_projector.commit_execution_feedback(prepared)
        return FeedbackIngressResult(projected_evidence=projected, receipt=receipt)
