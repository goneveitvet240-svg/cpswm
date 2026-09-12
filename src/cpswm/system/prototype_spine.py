"""Fast end-to-end prototype spine shared by structure one and structure two.

This module intentionally composes existing project components instead of
creating a second world-model stack.  It is a prototype integration surface,
not evidence that the formal M01-M32 maturity gates have passed.
"""

from __future__ import annotations

import hashlib
import json
import marshal
import re
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field, fields, is_dataclass, replace
from datetime import datetime
from enum import StrEnum
from functools import wraps
from math import exp, isfinite, log, tanh
from threading import RLock, get_ident
from time import perf_counter_ns
from typing import TYPE_CHECKING, Any, Concatenate, Final, cast
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import numpy as np

if TYPE_CHECKING:
    from cpswm.system.counterfactual_event_hypergraph.feedback_revision_loop import (
        EventRevisionOutcome as ProjectTwoEventRevisionOutcome,
    )
    from cpswm.system.counterfactual_event_hypergraph.feedback_revision_loop import (
        ProjectOneStatRequest,
    )

from cpswm.contracts import (
    ActionOutcomeLikelihoodModel,
    ActorResponsibilityEvidence,
    DecisionContextBinding,
    EventMechanismEvidence,
    ExecutionFeedbackRecord,
    HabitEvidenceSource,
    HabitLearningEvidence,
    ObservationDetectionResult,
    ObservationOpportunityRecord,
    ProjectOneRequestApplicationReceipt,
    ProjectOneRequestApplicationStatus,
    RoleBindingEvidence,
    SourceType,
    StatisticDelta,
)
from cpswm.system.continual.hybrid_event_to_task_loop import (
    HybridEventToTaskCoordinatorLoop,
    HybridFullRerunEquivalenceReceipt,
    OwnerPlacementInput,
)
from cpswm.system.continual.project_one_feedback import (
    DefaultPrototypeFeedbackPolicy,
    EventRevisionKind,
    EventRevisionOutcome,
    ExecutionFeedbackInterpretationPolicy,
)
from cpswm.system.continual.project_one_regime_loop import (
    AutomaticCFBOCPDCCRRRouter,
    DerivedEvidenceReactivationPolicy,
    HabitStateConclusion,
    PrototypeLoopConfig,
    PrototypeStatisticOperation,
    RegimeStage,
)
from cpswm.system.continual.rls import (
    RLSHabitSample,
    RLSHabitScoreHead,
    RLSRegimeBank,
    RLSRegimeSwitchEvent,
)
from cpswm.system.counterfactual_event_hypergraph import (
    EventHypothesisHistory,
    MessagePassingResult,
    OpenWorldRoleConditionedReversibleEventRevisionEngine,
    ProvenanceConstrainedMessagePassing,
)
from cpswm.system.evaluation_operations.structure_two_selected_method import (
    ParticleRevisionBatch,
    ParticleRevisionReceipt,
)
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_execution import (
    GENESIS_RECEIPT_SHA256,
    LEGACY_CIAV_NOT_APPLICABLE_REASON,
    STRUCTURE_TWO_OPERATOR_ORDER,
    AdaptiveInferenceDebtCertificate,
    AdaptiveMaintenanceContractError,
    ExecutionModeName,
    FeedbackClosureKind,
    OperatorExecutionDirective,
    OperatorInvocationReceipt,
    RuntimeCallableBinding,
    RuntimeOperatorName,
    StructureTwoExecutionPlan,
    StructureTwoExecutionTrace,
    TraceAbortAck,
    TraceCommitAck,
    TraceCompensationError,
    TracePhaseName,
    TraceSink,
    UnsupportedStructureTwoExecutionPlan,
    _restore_runtime_rlock_depth,
    _runtime_rlock_depth,
    bind_runtime_callable,
    seal_execution_trace,
    seal_operator_receipt,
    verify_execution_trace,
    verify_trace_abort_ack,
    verify_trace_commit_ack,
)
from cpswm.system.structure_two_execution import (
    canonical_legacy_ordinary_transition_plan as canonical_legacy_ordinary_transition_plan,
)
from cpswm.system.structure_two_particle_workspace import (
    ConditionalAnalyticState,
    NativeParticleWorkspace,
    NativePosteriorSource,
    native_content_payload,
    native_content_sha256,
)
from cpswm.world_model.grounded_search.concurrent_map_task import BeliefSnapshot, VersionedBeliefMap
from cpswm.world_model.habits_transitions import (
    CauseSignalFrame,
    ChangeCause,
    HabitPrediction,
    HabitUpdateAudit,
    HierarchicalDirichletHabitModel,
    JointCauseSnapshot,
    ObservationPropensityCorrector,
    PropensityCorrectionMode,
    PropensityWeight,
)

StructuredEventEvidence = ActorResponsibilityEvidence | EventMechanismEvidence | RoleBindingEvidence


def _runtime_type_symbol(value: object) -> str:
    value_type = type(value)
    return f"{value_type.__module__}.{value_type.__qualname__}"


def _authority_descriptor(authority: object | None) -> dict[str, object] | None:
    """Describe verifier identity/configuration without exposing key material."""

    if authority is None:
        return None
    primitive_state: dict[str, object] = {}
    for name, value in vars(authority).items():
        if isinstance(value, bytes):
            primitive_state[name] = hashlib.sha256(value).hexdigest()
        elif isinstance(value, (str, int, float, bool, UUID)) or value is None:
            primitive_state[name] = value
        else:
            primitive_state[name] = {"type": _runtime_type_symbol(value)}
    return {
        "type": _runtime_type_symbol(authority),
        "key_id": getattr(authority, "key_id", None),
        "formal_grade": getattr(authority, "formal_grade", None),
        "public_key_sha256": getattr(authority, "public_key_sha256", None),
        "state": primitive_state,
    }


def _message_passing_nested_components(message_passing: object) -> dict[str, object]:
    """Return optional nested PCHMP objects whose identity must survive rollback."""

    components: dict[str, object] = {}
    direct_authority = getattr(message_passing, "_independence_authority", None)
    if direct_authority is not None:
        components["message_passing_direct_independence_authority"] = direct_authority
    delegate = getattr(message_passing, "_delegate", None)
    if delegate is not None:
        components["message_passing_delegate"] = delegate
        delegate_authority = getattr(delegate, "_independence_authority", None)
        if delegate_authority is not None:
            components["message_passing_delegate_independence_authority"] = delegate_authority
    return components


def _message_passing_state_descriptor(message_passing: object) -> dict[str, object]:
    """Describe both native and registered evaluator PCHMP implementations."""

    def component_descriptor(component: object) -> dict[str, object]:
        return {
            "type": _runtime_type_symbol(component),
            "model_version": getattr(component, "model_version", None),
            "attribute_names": (sorted(vars(component)) if hasattr(component, "__dict__") else []),
            "deduplication_enabled": getattr(component, "deduplication_enabled", None),
            "provenance_firewall_enabled": getattr(component, "provenance_firewall_enabled", None),
            "independence_authority": _authority_descriptor(
                getattr(component, "_independence_authority", None)
            ),
        }

    descriptor = component_descriptor(message_passing)
    delegate = getattr(message_passing, "_delegate", None)
    descriptor["delegate"] = component_descriptor(delegate) if delegate is not None else None
    return descriptor


def _auditable_attribute(value: object) -> object:
    if callable(value):
        target = getattr(value, "__func__", value)
        module = getattr(target, "__module__", type(target).__module__)
        qualname = getattr(target, "__qualname__", type(target).__qualname__)
        return {"callable_symbol": f"{module}.{qualname}"}
    return value


def _callable_runtime_state(value: object | None) -> dict[str, object] | None:
    """Describe callable behavior, including code/default/closure configuration."""

    if value is None:
        return None
    target = getattr(value, "__func__", value)
    module = getattr(target, "__module__", type(target).__module__)
    qualname = getattr(target, "__qualname__", type(target).__qualname__)
    code = getattr(target, "__code__", None)
    closure = getattr(target, "__closure__", None)
    freevars = tuple(getattr(code, "co_freevars", ()))
    closure_state: list[dict[str, object]] = []
    for index, cell in enumerate(closure or ()):
        name = freevars[index] if index < len(freevars) else f"cell_{index}"
        try:
            cell_value = cell.cell_contents
        except ValueError:
            cell_state: object = {"empty": True}
        else:
            if isinstance(cell_value, (str, int, float, bool, UUID)) or cell_value is None:
                cell_state = cell_value
            elif is_dataclass(cell_value) and not isinstance(cell_value, type):
                cell_state = {
                    field.name: _auditable_attribute(getattr(cell_value, field.name))
                    for field in fields(cell_value)
                }
            else:
                cell_state = {"type": _runtime_type_symbol(cell_value)}
        closure_state.append({"name": name, "value": cell_state})
    configuration: dict[str, object] | None = None
    if is_dataclass(value) and not isinstance(value, type):
        configuration = {
            field.name: _auditable_attribute(getattr(value, field.name)) for field in fields(value)
        }
    return {
        "type": _runtime_type_symbol(value),
        "callable_symbol": f"{module}.{qualname}",
        "code_sha256": (
            hashlib.sha256(marshal.dumps(code)).hexdigest() if code is not None else None
        ),
        "defaults": repr(getattr(target, "__defaults__", None)),
        "kwdefaults": repr(getattr(target, "__kwdefaults__", None)),
        "closure": closure_state,
        "configuration": configuration,
    }


@dataclass(frozen=True, slots=True)
class _RLSHeadFactory:
    """Explicit immutable replacement for the former mutable closure factory."""

    context_feature_dim: int
    location_embedding_dim: int
    forgetting_factor: float
    ridge: float = 1e-6
    prior_scale: float = 1e4
    model_version: str = "rls-habit-head@0.1"

    def __call__(self) -> RLSHabitScoreHead:
        return RLSHabitScoreHead(
            context_feature_dim=self.context_feature_dim,
            location_embedding_dim=self.location_embedding_dim,
            forgetting_factor=self.forgetting_factor,
            ridge=self.ridge,
            prior_scale=self.prior_scale,
            model_version=self.model_version,
        )


def _restore_reference_state(
    original: object,
    snapshot: object,
    *,
    preserve_attributes: frozenset[str] = frozenset(),
) -> None:
    """Restore mutable contents while retaining an externally visible object identity."""

    if type(original) is not type(snapshot):
        raise TypeError("runtime checkpoint type drifted")
    if isinstance(original, defaultdict) and isinstance(snapshot, defaultdict):
        original.clear()
        original.update(deepcopy(snapshot))
        original.default_factory = snapshot.default_factory
        return
    if isinstance(original, dict) and isinstance(snapshot, dict):
        original.clear()
        original.update(deepcopy(snapshot))
        return
    if isinstance(original, list) and isinstance(snapshot, list):
        original[:] = deepcopy(snapshot)
        return
    if isinstance(original, set) and isinstance(snapshot, set):
        original.clear()
        original.update(deepcopy(snapshot))
        return
    if isinstance(original, np.ndarray) and isinstance(snapshot, np.ndarray):
        if original.shape != snapshot.shape or original.dtype != snapshot.dtype:
            raise TypeError("runtime array checkpoint shape or dtype drifted")
        np.copyto(original, snapshot)
        return
    if is_dataclass(original) and is_dataclass(snapshot):
        for field in fields(original):
            object.__setattr__(original, field.name, deepcopy(getattr(snapshot, field.name)))
        return
    if hasattr(original, "__dict__") and hasattr(snapshot, "__dict__"):
        original_fields = vars(original)
        snapshot_fields = vars(snapshot)
        for name in tuple(original_fields):
            if name not in preserve_attributes and name not in snapshot_fields:
                delattr(original, name)
        for name, value in snapshot_fields.items():
            if name in preserve_attributes:
                continue
            setattr(original, name, deepcopy(value))
        return


def _serialized_core_mutation[**P, R](
    method: Callable[Concatenate[CorePrototypeSpine, P], R],
) -> Callable[Concatenate[CorePrototypeSpine, P], R]:
    """Serialize public writes with Architecture-A transition transactions."""

    @wraps(method)
    def wrapped(
        self: CorePrototypeSpine,
        /,
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> R:
        self._require_external_mutation_permission()
        if self._mutation_is_forbidden_during_sink_commit():
            raise RuntimeError("runtime mutation is forbidden during trace sink commit")
        with self._execution_lock:
            # Recheck after taking the core lock.  A production wrapper may
            # have issued adaptive inference debt while this caller waited.
            self._require_external_mutation_permission()
            if self._mutation_is_forbidden_during_sink_commit():
                raise RuntimeError("runtime mutation is forbidden during trace sink commit")
            return method(self, *args, **kwargs)

    return wrapped


def _project_one_request_fingerprint(request: ProjectOneStatRequest) -> str:
    payload = {
        "kind": request.kind.value,
        "superseded_revision_id": str(request.superseded_revision_id),
        "corrected_revision_id": str(request.corrected_revision_id),
        "event_hypothesis_id": str(request.event_hypothesis_id),
        "owner_key": request.owner_key,
        "object_instance_id": str(request.object_instance_id),
        "location_id": str(request.location_id),
        "owner_mass_before": repr(float(request.owner_mass_before)),
        "owner_mass_after": repr(float(request.owner_mass_after)),
        "owner_mass_delta": repr(float(request.owner_mass_delta)),
        "source_feedback_record_id": str(request.source_feedback_record_id),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _require_probability(value: float, name: str) -> None:
    if not isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must lie in [0, 1]")


def _normalized_predictive_surprise(probability: float, class_count: int) -> float:
    """Bound self-information in excess of the uniform K-class reference."""

    _require_probability(probability, "predictive_probability")
    if class_count < 2:
        raise ValueError("class_count must be at least two")
    bounded = max(probability, 1e-12)
    normalized_information = max(0.0, -log(bounded) / log(float(class_count)))
    excess_information = max(0.0, normalized_information - 1.0)
    return 1.0 - exp(-excess_information)


_SHA256_PATTERN: Final = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class _WriteAuthorization:
    """One traceable grant of long-term write eligibility for an observation.

    ``hard_safety_kernel.router_may_grant_long_term_write`` is ``false`` and
    ``maximum_unauthorized_long_term_commits`` is ``0``.  An observation whose
    origin pass had the long-term write administratively blocked therefore needs a
    recorded, verifiable grant from an execution that *was* permitted to write,
    before any later replay may commit it.  The grant names the authority, the
    execution that issued it, and a content hash of its basis, so the promotion can
    be audited afterwards rather than inferred from the fact that a rebuild agreed.
    """

    authority: str
    granting_revision_id: UUID | None
    granted_at_observation_count: int
    basis_sha256: str
    basis_json: str = "{}"


@dataclass(frozen=True, slots=True)
class _ObservationWriteEligibility:
    """Per-observation origin write eligibility, quarantine reason and lineage."""

    revision_id: UUID
    origin_write_blocked: bool
    origin_path: str
    quarantine_reason: str | None = None
    authorizations: tuple[_WriteAuthorization, ...] = ()
    parent_revision_id: UUID | None = None
    correction_evidence_source_record_ids: tuple[UUID, ...] = ()
    parent_eligibility_sha256: str | None = None
    correction_outcome_sha256: str | None = None

    @property
    def write_eligible(self) -> bool:
        """Eligible when the origin was never blocked, or a grant was recorded."""

        return not self.origin_write_blocked or bool(self.authorizations)


@dataclass(frozen=True, slots=True)
class _PublishedRevisionBinding:
    """One feedback binding this runtime really published for a revision.

    Kept as an append-only history so that a feedback bound to a *superseded but
    genuinely published* snapshot can still be verified, instead of being rejected
    merely because an unrelated revision forced a rebuild in the meantime.
    """

    location_id: UUID
    snapshot_id: UUID
    map_version: int
    observation_count: int


@dataclass(frozen=True, slots=True)
class _LateFeedbackRelocation:
    """Audit row for a feedback accepted against a superseded published binding."""

    revision_id: UUID
    feedback_record_id: UUID
    presented_snapshot_id: UUID
    presented_map_version: int
    current_snapshot_id: UUID
    current_map_version: int
    location_id: UUID


@dataclass(frozen=True, slots=True)
class _AdaptiveMaintenanceContext:
    """The runtime's own record of one deferred-path execution.

    Every field is produced by the runtime from the real transition, debt
    certificate and execution identity.  Maintenance payloads are validated
    *against* this record, never against their own self-reported values.
    """

    runtime_execution_id: UUID
    epoch: int
    origin_transition_sha256: str
    evidence_content_sha256s: tuple[str, ...]
    debt_certificate_sha256: str
    message_passing_runtime_type: str
    produced_outputs: dict[str, str] = field(default_factory=dict)

    def record_output(self, operator: str, payload: Mapping[str, object]) -> str:
        """Record what this execution's own upstream node actually produced."""

        digest = content_sha256(payload)
        self.produced_outputs[operator] = digest
        return digest

    def require_produced(self, operator: str, digest: object, *, consumer: str) -> None:
        """Check a declared consumption against this execution's real upstream output."""

        produced = self.produced_outputs.get(operator)
        if produced is None:
            raise AdaptiveMaintenanceContractError(
                f"{consumer} declared consumption of {operator} before it ran in this execution"
            )
        if digest != produced:
            raise AdaptiveMaintenanceContractError(
                f"{consumer} declared consumption of a {operator} output "
                f"this execution never produced"
            )


@dataclass(frozen=True, slots=True)
class PrototypeTransition:
    """One robot-visible transition accepted by the prototype spine."""

    opportunity: ObservationOpportunityRecord
    before: ObservationDetectionResult
    after: ObservationDetectionResult
    actor_prior: Mapping[str, float]
    evidence: tuple[StructuredEventEvidence, ...] = ()
    context_key: str = "default"
    context_value: float = 0.0
    unresolved_probability: float = 0.1
    identity_switch_probability: float = 0.0

    def __post_init__(self) -> None:
        for actor, probability in self.actor_prior.items():
            _require_probability(probability, f"actor_prior[{actor!r}]")
        _require_probability(self.unresolved_probability, "unresolved_probability")
        _require_probability(self.identity_switch_probability, "identity_switch_probability")


@dataclass(frozen=True, slots=True)
class PrototypeStepResult:
    """The inspectable output of every core stage for one transition."""

    propensity: PropensityWeight
    event_history: EventHypothesisHistory
    event_posterior: MessagePassingResult
    actor_posterior: Mapping[str, float]
    habit_update: HabitUpdateAudit
    habit_prediction: HabitPrediction
    active_regime: str
    rls_scores: Mapping[UUID, float]
    belief_snapshot: BeliefSnapshot
    suggested_location_id: UUID
    event_revision_id: UUID
    decision: PrototypeDecisionRecord

    def __post_init__(self) -> None:
        for actor, probability in self.actor_posterior.items():
            _require_probability(probability, f"actor_posterior[{actor!r}]")


@dataclass(slots=True)
class _TransitionTraceRecorder:
    """Transaction-local receipt buffer; it never writes to the external sink."""

    runtime_execution_id: UUID
    plan: StructureTwoExecutionPlan
    bindings: dict[str, RuntimeCallableBinding]
    receipts: list[OperatorInvocationReceipt]
    outputs_by_phase_operator: dict[tuple[str, str], OperatorInvocationReceipt]
    debt_certificates: list[AdaptiveInferenceDebtCertificate]
    replayed_debt_certificates: list[AdaptiveInferenceDebtCertificate]
    feedback_observation_acquired: bool = False
    feedback_closure_kind: FeedbackClosureKind = "none"
    adaptive_router_feature_sha256: str | None = None
    adaptive_router_source_state_sha256: str | None = None
    adaptive_authorization_policy_sha256: str | None = None
    adaptive_path_selection_receipt_sha256: str | None = None
    adaptive_ciav_input_sha256: str | None = None
    adaptive_step_index: int | None = None
    adaptive_debt_expiry_steps: int | None = None

    @classmethod
    def create(
        cls,
        *,
        runtime_execution_id: UUID,
        plan: StructureTwoExecutionPlan,
        bindings: Mapping[str, RuntimeCallableBinding],
    ) -> _TransitionTraceRecorder:
        return cls(
            runtime_execution_id=runtime_execution_id,
            plan=plan,
            bindings=dict(bindings),
            receipts=[],
            outputs_by_phase_operator={},
            debt_certificates=[],
            replayed_debt_certificates=[],
        )

    def _primary_phase(self) -> TracePhaseName:
        return (
            "ordinary_transition"
            if self.plan.lane == "legacy_ordinary_transition"
            else "selected_path"
        )

    def _directive(self, operator: str) -> OperatorExecutionDirective:
        try:
            index = STRUCTURE_TWO_OPERATOR_ORDER.index(operator)
        except ValueError as error:
            raise RuntimeError(f"unknown Structure-Two operator: {operator}") from error
        directive = self.plan.operator_directives[index]
        if directive.operator != operator:
            raise RuntimeError("runtime operator order drifted from the immutable plan")
        return directive

    def mode_for(
        self,
        operator: str,
        *,
        phase: TracePhaseName | None = None,
    ) -> ExecutionModeName:
        resolved_phase = phase or self._primary_phase()
        if resolved_phase == "feedback_closure":
            return "refinement_executed"
        return self._directive(operator).mode

    def bind_operator(self, operator: str, binding: RuntimeCallableBinding) -> None:
        if binding.runtime_execution_id != self.runtime_execution_id:
            raise ValueError("adaptive binding runtime identity mismatch")
        if binding.operator != operator:
            raise ValueError("adaptive binding operator mismatch")
        self.bindings[operator] = binding

    def bind_adaptive_route(
        self,
        *,
        router_feature_sha256: str,
        router_source_state_sha256: str,
        authorization_policy_sha256: str,
        path_selection_receipt_sha256: str,
        ciav_input_sha256: str | None,
        step_index: int,
        debt_expiry_steps: int,
    ) -> None:
        if self.plan.lane != "registered_adaptive_path":
            raise RuntimeError("legacy trace cannot bind adaptive routing evidence")
        if self.adaptive_router_feature_sha256 is not None:
            raise RuntimeError("adaptive routing evidence is already bound")
        self.adaptive_router_feature_sha256 = router_feature_sha256
        self.adaptive_router_source_state_sha256 = router_source_state_sha256
        self.adaptive_authorization_policy_sha256 = authorization_policy_sha256
        self.adaptive_path_selection_receipt_sha256 = path_selection_receipt_sha256
        self.adaptive_ciav_input_sha256 = ciav_input_sha256
        self.adaptive_step_index = step_index
        self.adaptive_debt_expiry_steps = debt_expiry_steps

    def _consumed_output_ids(
        self,
        operators: tuple[str, ...],
        *,
        phase: TracePhaseName,
    ) -> tuple[str, ...]:
        try:
            values: list[str] = []
            for name in operators:
                receipt = self.outputs_by_phase_operator.get((phase, name))
                if receipt is None and phase == "feedback_closure":
                    receipt = self.outputs_by_phase_operator.get(("selected_path", name))
                if receipt is None:
                    receipt = self.outputs_by_phase_operator.get(("ordinary_transition", name))
                if receipt is None:
                    raise KeyError(name)
                values.append(receipt.output_id)
            return tuple(values)
        except KeyError as error:
            raise RuntimeError(
                "operator consumed an output that was not produced in this run"
            ) from error

    def record_executed(
        self,
        operator: str,
        *,
        raw_input: object,
        output: object,
        consumes: tuple[str, ...] = (),
        phase: TracePhaseName | None = None,
        elapsed_ns: int = 0,
    ) -> OperatorInvocationReceipt:
        resolved_phase = phase or self._primary_phase()
        mode = self.mode_for(operator, phase=resolved_phase)
        if mode not in {
            "legacy_default_executed",
            "mandatory_maintenance_executed",
            "refinement_executed",
        }:
            raise RuntimeError("runtime executed an operator marked as deferred or not applicable")
        binding = self.bindings.get(operator)
        if binding is None:
            raise RuntimeError(f"runtime callable binding is missing: {operator}")
        if (
            resolved_phase == "feedback_closure"
            and not consumes
            and operator
            in {
                "opceu",
                "orrer_cheh",
            }
        ):
            consumes = ("ciav",)
        previous = self.receipts[-1].receipt_sha256 if self.receipts else GENESIS_RECEIPT_SHA256
        receipt = seal_operator_receipt(
            runtime_execution_id=self.runtime_execution_id,
            sequence=len(self.receipts),
            plan=self.plan,
            operator=cast(RuntimeOperatorName, operator),
            mode=mode,
            status="executed",
            raw_input=raw_input,
            output=output,
            consumed_output_ids=self._consumed_output_ids(consumes, phase=resolved_phase),
            previous_receipt_sha256=previous,
            phase=resolved_phase,
            elapsed_ns=elapsed_ns,
            binding=binding,
        )
        self.receipts.append(receipt)
        self.outputs_by_phase_operator[(resolved_phase, operator)] = receipt
        return receipt

    def record_deferred(
        self,
        operator: str,
        *,
        raw_input: object,
        debt_certificate: AdaptiveInferenceDebtCertificate,
    ) -> OperatorInvocationReceipt:
        phase = self._primary_phase()
        if phase != "selected_path":
            raise RuntimeError("legacy execution cannot issue adaptive inference debt")
        mode = self.mode_for(operator, phase=phase)
        if mode != "deferred_with_valid_debt_certificate":
            raise RuntimeError("operator is not marked for debt-backed deferral")
        if operator not in debt_certificate.deferred_operators:
            raise RuntimeError("debt certificate does not cover the deferred operator")
        previous = self.receipts[-1].receipt_sha256 if self.receipts else GENESIS_RECEIPT_SHA256
        output = {
            "debt_id": str(debt_certificate.debt_id),
            "certificate_sha256": debt_certificate.certificate_sha256,
            "skipped_as_negative": False,
        }
        receipt = seal_operator_receipt(
            runtime_execution_id=self.runtime_execution_id,
            sequence=len(self.receipts),
            plan=self.plan,
            operator=operator,
            mode=mode,
            status="deferred",
            raw_input=raw_input,
            output=output,
            consumed_output_ids=(),
            previous_receipt_sha256=previous,
            phase="selected_path",
            debt_certificate_sha256=debt_certificate.certificate_sha256,
        )
        self.receipts.append(receipt)
        self.outputs_by_phase_operator[(phase, operator)] = receipt
        if debt_certificate not in self.debt_certificates:
            self.debt_certificates.append(debt_certificate)
        return receipt

    def record_ciav_not_applicable(self, transition: PrototypeTransition) -> None:
        operator = "ciav"
        directive = self._directive(operator)
        mode = directive.mode
        if mode != "not_applicable_with_recomputed_reason":
            raise RuntimeError("ordinary transition cannot satisfy the requested CIAV mode")
        previous = self.receipts[-1].receipt_sha256
        receipt = seal_operator_receipt(
            runtime_execution_id=self.runtime_execution_id,
            sequence=len(self.receipts),
            plan=self.plan,
            operator="ciav",
            mode=mode,
            status="not_applicable",
            raw_input={
                "entrypoint": "CorePrototypeSpine.process_transition",
                "transition_contract": (
                    f"{type(transition).__module__}.{type(transition).__qualname__}"
                ),
            },
            output={"recomputed_reason": LEGACY_CIAV_NOT_APPLICABLE_REASON},
            consumed_output_ids=(),
            previous_receipt_sha256=previous,
            phase="ordinary_transition",
            recomputed_reason=LEGACY_CIAV_NOT_APPLICABLE_REASON,
        )
        self.receipts.append(receipt)
        self.outputs_by_phase_operator[("ordinary_transition", operator)] = receipt


@dataclass(frozen=True, slots=True)
class FastActionVerificationReceipt:
    """Auditable CIAV update that is forbidden from touching slow statistics."""

    receipt_id: UUID
    revision_id: UUID
    source_record_id: UUID
    owner_mass_before: float
    owner_mass_after: float
    changed: bool
    long_term_write: bool = False

    def __post_init__(self) -> None:
        _require_probability(self.owner_mass_before, "owner_mass_before")
        _require_probability(self.owner_mass_after, "owner_mass_after")
        if self.long_term_write:
            raise ValueError("fast action verification cannot authorize a long-term write")


@dataclass(frozen=True, slots=True)
class PrototypeDecisionRecord:
    old_regime: str
    new_regime: str
    change_probability: float
    ccrr_conclusion: str
    conclusion: HabitStateConclusion
    evidence_source_record_ids: tuple[UUID, ...]
    statistic_operations: tuple[PrototypeStatisticOperation, ...]
    map_version: int
    snapshot_id: UUID
    rationale: str

    def __post_init__(self) -> None:
        _require_probability(self.change_probability, "change_probability")


@dataclass(frozen=True, slots=True)
class PrototypeRevisionResult:
    statistic_operations: tuple[PrototypeStatisticOperation, ...]
    evidence_source_record_ids: tuple[UUID, ...]
    map_version: int
    snapshot_id: UUID
    suggested_location_id: UUID
    old_regime: str
    new_regime: str
    change_probability: float
    ccrr_conclusion: str
    rationale: str
    feedback_posterior_probability: float | None = None

    def __post_init__(self) -> None:
        _require_probability(self.change_probability, "change_probability")
        if self.feedback_posterior_probability is not None:
            _require_probability(
                self.feedback_posterior_probability,
                "feedback_posterior_probability",
            )


class DerivedEvidenceLifecycle(StrEnum):
    """Why archived derived evidence is active, recoverable, or permanently dead."""

    ACTIVE = "active"
    SUSPENDED_PARENT_QUARANTINED = "suspended_parent_quarantined"
    TOMBSTONED_EXPLICIT_RETRACT = "tombstoned_explicit_retract"
    TOMBSTONED_CORRECTED = "tombstoned_corrected"
    TOMBSTONED_ANCESTOR_INVALIDATED = "tombstoned_ancestor_invalidated"


class ActionReadout(StrEnum):
    """Which surviving evidence the planner is allowed to read for an action.

    ``HYBRID_ALPHA`` is the frozen v0.2 boundary: a pooled cumulative
    owner-weighted count.  It is kept as the default so every existing reading
    stays byte-reproducible.  The other modes exist because a pooled count
    cannot express *which* owner-attributed evidence currently survives -- which
    is the entire product of the reversible revision machinery.
    """

    HYBRID_ALPHA = "hybrid_alpha"
    REGIME_LOCAL = "regime_local"
    SURVIVING_OWNER_REVISIONS = "surviving_owner_revisions"
    REVISION_AWARE = "revision_aware"
    LATEST_OWNER_EVENT = "latest_owner_event"
    DUAL_TIMESCALE_REVERSIBLE = "dual_timescale_reversible"


@dataclass(frozen=True, slots=True)
class ActionReadoutConfig:
    """Planner read policy over the spine's surviving statistics.

    ``owner_mass_floor`` and ``recency_half_life`` are *readout* parameters: they
    never change what is written to Dirichlet/RLS/Hybrid, only which surviving
    evidence the next action is allowed to weigh.  ``pending_correction_discount``
    closes the quarantine handoff gate on the action side: a correction whose
    long-term write is still deferred behind CCRR quarantine must still be able
    to move the next action, because RGRC quarantine is about writing to long-term
    memory, not about what the robot should do next.
    """

    readout: ActionReadout = ActionReadout.HYBRID_ALPHA
    owner_mass_floor: float = 0.0
    recency_half_life: float = 0.0
    hybrid_alpha_weight: float = 1.0
    regime_local_weight: float = 0.0
    surviving_revision_weight: float = 0.0
    fast_action_weight: float = 0.0
    fast_owner_mass_floor: float = 0.5
    fast_confirmation_observations: int = 1
    unconfirmed_fast_discount: float = 1.0
    pending_correction_discount: float = 1.0
    active_regime_only: bool = False

    def __post_init__(self) -> None:
        if not 0.0 <= self.owner_mass_floor <= 1.0:
            raise ValueError("owner_mass_floor must be a probability")
        if not 0.0 <= self.fast_owner_mass_floor <= 1.0:
            raise ValueError("fast_owner_mass_floor must be a probability")
        if self.fast_confirmation_observations < 1:
            raise ValueError("fast_confirmation_observations must be positive")
        if not 0.0 <= self.unconfirmed_fast_discount <= 1.0:
            raise ValueError("unconfirmed_fast_discount must be in [0, 1]")
        if self.recency_half_life < 0.0:
            raise ValueError("recency_half_life must be non-negative")
        if not 0.0 <= self.pending_correction_discount <= 1.0:
            raise ValueError("pending_correction_discount must be in [0, 1]")
        for name in (
            "hybrid_alpha_weight",
            "regime_local_weight",
            "surviving_revision_weight",
            "fast_action_weight",
        ):
            if getattr(self, name) < 0.0:
                raise ValueError(f"{name} must be non-negative")

    @property
    def component_weights(self) -> dict[str, float]:
        """Resolve the named readout into explicit component weights."""

        if self.readout is ActionReadout.HYBRID_ALPHA:
            return {
                "hybrid_alpha": 1.0,
                "regime_local": 0.0,
                "surviving": 0.0,
                "fast_action": 0.0,
            }
        if self.readout is ActionReadout.REGIME_LOCAL:
            return {
                "hybrid_alpha": 0.0,
                "regime_local": 1.0,
                "surviving": 0.0,
                "fast_action": 0.0,
            }
        if self.readout is ActionReadout.SURVIVING_OWNER_REVISIONS:
            return {
                "hybrid_alpha": 0.0,
                "regime_local": 0.0,
                "surviving": 1.0,
                "fast_action": 0.0,
            }
        if self.readout is ActionReadout.LATEST_OWNER_EVENT:
            return {
                "hybrid_alpha": 0.0,
                "regime_local": 0.0,
                "surviving": 0.0,
                "fast_action": 1.0,
            }
        if self.readout is ActionReadout.DUAL_TIMESCALE_REVERSIBLE:
            return {
                "hybrid_alpha": self.hybrid_alpha_weight,
                "regime_local": self.regime_local_weight,
                "surviving": self.surviving_revision_weight,
                "fast_action": self.fast_action_weight,
            }
        return {
            "hybrid_alpha": self.hybrid_alpha_weight,
            "regime_local": self.regime_local_weight,
            "surviving": self.surviving_revision_weight,
            "fast_action": 0.0,
        }


@dataclass(frozen=True, slots=True)
class _CommittedPrototypeEvent:
    event_hypothesis_id: UUID
    revision_id: UUID
    evidence: HabitLearningEvidence
    propensity_weight: float
    rls_sample: RLSHabitSample
    owner_mass: float
    statistical_owner_weight: float
    source_record_id: UUID
    location_id: UUID
    dirichlet_predictive_surprise: float = 0.0
    rls_residual: float = 0.0
    regime_frame: CauseSignalFrame | None = None
    hybrid_revision_id: UUID | None = None
    hybrid_parent_revision_id: UUID | None = None
    derived_from_revision_id: UUID | None = None
    belief_snapshot_id: UUID | None = None
    identity_switch_probability: float = 0.0


@dataclass(frozen=True, slots=True)
class DeferredCorrectionCancellation:
    """Compensating transaction: retain the failed child and its original parent."""

    request_fingerprint: str
    request: ProjectOneStatRequest
    parent_event: _CommittedPrototypeEvent
    corrected_event: _CommittedPrototypeEvent
    after_operation_count: int
    trigger_revision_id: UUID
    rationale: str
    restore_events: tuple[_CommittedPrototypeEvent, ...]
    restore_fast_events: tuple[_CommittedPrototypeEvent, ...]
    body_sha256: str = ""

    def body(self) -> tuple[Any, ...]:
        return (
            self.request_fingerprint,
            self.request,
            self.parent_event,
            self.corrected_event,
            self.after_operation_count,
            self.trigger_revision_id,
            self.rationale,
            self.restore_events,
            self.restore_fast_events,
        )

    def validate_content(self) -> None:
        request, parent, child = self.request, self.parent_event, self.corrected_event
        if (
            self.body_sha256 != native_content_sha256(self.body())
            or self.request_fingerprint != _project_one_request_fingerprint(request)
            or request.superseded_revision_id != parent.revision_id
            or request.corrected_revision_id != child.revision_id
            or request.event_hypothesis_id != parent.event_hypothesis_id
            or child.event_hypothesis_id != parent.event_hypothesis_id
            or request.owner_mass_before != parent.owner_mass
            or request.owner_mass_after != child.owner_mass
            or request.location_id != child.location_id
            or child.source_record_id != request.source_feedback_record_id
            or self.after_operation_count < 1
            or not self.restore_events
            or self.restore_events[0].revision_id != parent.revision_id
        ):
            raise ValueError("invalid deferred cancellation content or request binding")


class CorePrototypeSpine:
    """Compose the shortest runnable spine of structure one and structure two.

    The prototype covers observation correction, hidden-event hypotheses,
    multi-resident attribution, person-conditioned habit learning, explicit
    automatic CF-BOCPD/CCRR routing, regime-local RLS state, reversible
    consolidation, feedback revision, and map publication.
    """

    model_version = "core-prototype-spine@0.1"

    def __init__(
        self,
        *,
        owner_key: str,
        object_instance_id: UUID,
        locations: Sequence[UUID],
        authorization_scope_id: UUID,
        correction_mode: PropensityCorrectionMode = PropensityCorrectionMode.INVERSE,
        loop_config: PrototypeLoopConfig | None = None,
        event_engine: OpenWorldRoleConditionedReversibleEventRevisionEngine | None = None,
        message_passing: ProvenanceConstrainedMessagePassing | None = None,
        rgrc_gate_enabled: bool = True,
        action_readout: ActionReadoutConfig | None = None,
    ) -> None:
        self.owner_key = owner_key
        self.object_instance_id = object_instance_id
        self.authorization_scope_id = authorization_scope_id
        self.locations = tuple(dict.fromkeys(locations))
        if not owner_key.strip() or len(self.locations) < 2:
            raise ValueError("prototype requires an owner and at least two locations")

        self.loop_config = loop_config or PrototypeLoopConfig()
        self._event_engine = event_engine or OpenWorldRoleConditionedReversibleEventRevisionEngine()
        self._message_passing = message_passing or ProvenanceConstrainedMessagePassing()
        self._rgrc_gate_enabled = rgrc_gate_enabled
        self._corrector = ObservationPropensityCorrector(mode=correction_mode)
        self._habit = self._new_habit_model()
        embedding_dim = len(self.locations)
        self._embeddings = {
            location: np.eye(embedding_dim, dtype=float)[index]
            for index, location in enumerate(self.locations)
        }
        self._regimes = self._new_regime_bank(embedding_dim)
        self._hybrid_loop = HybridEventToTaskCoordinatorLoop(
            owner_key=owner_key,
            object_instance_id=object_instance_id,
            authorization_scope_id=authorization_scope_id,
            model_version=self.model_version,
            code_version="prototype-spine",
        )
        self._switch_sequence = 0
        self._automatic_regimes = self._new_automatic_regime_router()
        self._feedback_policy = DefaultPrototypeFeedbackPolicy(self.loop_config)
        self._committed_events: dict[UUID, _CommittedPrototypeEvent] = {}
        self._observed_events: dict[UUID, _CommittedPrototypeEvent] = {}
        # Fast action memory is deliberately separate from the committed long-term
        # stores.  Every PCHMP-attributed observation enters this reversible ledger
        # immediately, including observations that CF-BOCPD/RGRC quarantine.  A
        # later ORRER correction replaces the lineage head here even when project
        # one correctly refuses the corresponding long-term statistic write.
        self._fast_action_events: dict[UUID, _CommittedPrototypeEvent] = {}
        self._fast_action_verification_receipts: list[FastActionVerificationReceipt] = []
        self._derived_event_archive: dict[UUID, _CommittedPrototypeEvent] = {}
        self._derived_event_lifecycle: dict[UUID, DerivedEvidenceLifecycle] = {}
        self._revision_feedback_bindings: dict[UUID, tuple[UUID, UUID]] = {}
        # Append-only history of every binding this runtime published per revision,
        # so a genuinely late feedback bound to a superseded snapshot stays
        # verifiable without weakening snapshot validation.
        self._revision_binding_history: dict[UUID, tuple[_PublishedRevisionBinding, ...]] = {}
        self._late_feedback_relocations: list[_LateFeedbackRelocation] = []
        # Origin write eligibility, quarantine reason and subsequent authorizations
        # per observation.  A rebuild is not a write authority; it reads this.
        self._write_eligibility: dict[UUID, _ObservationWriteEligibility] = {}
        self._revision_transactions: tuple[EventRevisionOutcome, ...] = ()
        self._correction_cancellations: tuple[DeferredCorrectionCancellation, ...] = ()
        self._deferred_correction_restore: dict[
            str, tuple[tuple[_CommittedPrototypeEvent, ...], tuple[_CommittedPrototypeEvent, ...]]
        ] = {}
        self._revision_parent_events: dict[UUID, _CommittedPrototypeEvent] = {}
        self._hybrid_reinstatement_lineage: dict[UUID, tuple[UUID, UUID | None]] = {}
        self._particle_workspace = NativeParticleWorkspace()
        self._particle_workspace_anchor = self._particle_workspace
        self._event_histories: dict[UUID, EventHypothesisHistory] = {}
        self._production_operator_contract: Callable[[], Mapping[str, Sequence[object]]] | None = (
            None
        )
        self._quarantined_events: list[_CommittedPrototypeEvent] = []
        self._last_context_key = "default"
        self._last_context_value = 0.0
        self._last_household_id: UUID | None = None
        self._last_observed_location: UUID | None = None
        self._last_ccrr_decision = "stay"
        self._last_cause_snapshot: JointCauseSnapshot | None = None
        # fingerprint -> (request, revision whose promotion unblocks it, mode).
        # ``apply_request`` means the original request has not run; ``promotion_finalizes``
        # means the corrected event is already in the CCRR quarantine and its later
        # ordinary promotion is the exactly-once statistic application.
        self._deferred_project_one_requests: dict[str, tuple[ProjectOneStatRequest, UUID, str]] = {}
        self._project_one_application_receipts: dict[
            UUID, list[ProjectOneRequestApplicationReceipt]
        ] = {}
        # Frozen default: the planner reads the pooled hybrid alpha, exactly as
        # the 2026-08-24 D0 report did.  Callers opt into a revision-aware
        # readout explicitly; nothing changes implicitly.
        self._action_readout = action_readout or ActionReadoutConfig()
        # Action-scoped negatives close the quarantine/discard handoff gate.
        # When CCRR refuses a corrected event -- because the underlying
        # observation was a short-term disturbance, or because the superseded
        # revision has already been superseded again -- the *statistic* must not
        # move.  The robot still learned that its own put-back at that location
        # failed.  This ledger keeps that action consequence alive without ever
        # touching Dirichlet/RLS/Hybrid.  fingerprint -> (location, owner-mass delta).
        self._action_scoped_negatives: dict[str, tuple[UUID, float]] = {}
        # Prevent a trace sink from re-entering the same mutable runtime while
        # an outer transition is awaiting its typed commit acknowledgement.
        self._execution_lock = RLock()
        self._execution_contract_active = False
        self._execution_contract_phase = "idle"
        self._execution_owner_thread_id: int | None = None
        # A production owner may install a fail-closed guard here.  Standalone
        # CorePrototypeSpine instances retain their historical behavior.
        self._external_mutation_guard: Callable[[], None] | None = None
        # Trusted, execution-scoped record for deferred-path safety maintenance.
        # Maintenance nodes validate their declared dependencies against this
        # record rather than against the payloads' own self-report.
        self._adaptive_maintenance_context: _AdaptiveMaintenanceContext | None = None
        self._adaptive_maintenance_epoch = 0

    def _require_external_mutation_permission(self) -> None:
        guard = self._external_mutation_guard
        if guard is not None:
            guard()

    def _new_habit_model(self) -> HierarchicalDirichletHabitModel:
        return HierarchicalDirichletHabitModel(
            locations=self.locations,
            resident_actor_keys=(self.owner_key,),
        )

    def _new_regime_bank(self, embedding_dim: int | None = None) -> RLSRegimeBank:
        dimension = embedding_dim or len(self.locations)
        return RLSRegimeBank(
            head_factory=_RLSHeadFactory(
                context_feature_dim=1,
                location_embedding_dim=dimension,
                forgetting_factor=self.loop_config.forgetting_factor,
            )
        )

    def _new_automatic_regime_router(self) -> AutomaticCFBOCPDCCRRRouter:
        return AutomaticCFBOCPDCCRRRouter(
            object_instance_id=self.object_instance_id,
            actor_id=self.owner_key,
            owner_actor_id=self.owner_key,
            config=self.loop_config,
        )

    @property
    def active_regime(self) -> str:
        return self._regimes.active_regime(
            object_instance_id=self.object_instance_id,
            actor_id=self.owner_key,
        )

    @property
    def observation_count(self) -> int:
        return self._automatic_regimes.observation_count

    @property
    def current_snapshot(self) -> BeliefSnapshot:
        return self._hybrid_loop.current_snapshot()

    @property
    def current_cause_snapshot(self) -> JointCauseSnapshot | None:
        """Latest CF-BOCPD posterior available to CIAV after a visible observation."""

        return self._last_cause_snapshot

    def bind_adaptive_maintenance_context(
        self,
        *,
        runtime_execution_id: UUID,
        transition: PrototypeTransition,
        debt_certificate_sha256: str,
        origin_transition_sha256: str,
    ) -> _AdaptiveMaintenanceContext:
        """Open one trusted, execution-scoped context for a deferred path's maintenance.

        ``hard_safety_kernel.provenance_and_dependency_checks_always_executed`` is
        ``true`` for every legal path.  A dependency check is only real if the values
        it compares against come from the runtime, never from the payload's own
        self-report.  This context is the runtime's own record of the transition,
        evidence, debt and execution identity for one deferred path execution; every
        maintenance node validates against it and stamps its output with it.

        The epoch makes a payload produced by a *different* execution of the same
        runtime, or by another runtime that happens to share the same head state,
        detectable even when every other field agrees.
        """

        self._adaptive_maintenance_epoch += 1
        context = _AdaptiveMaintenanceContext(
            runtime_execution_id=runtime_execution_id,
            epoch=self._adaptive_maintenance_epoch,
            origin_transition_sha256=origin_transition_sha256,
            evidence_content_sha256s=tuple(content_sha256(item) for item in transition.evidence),
            debt_certificate_sha256=debt_certificate_sha256,
            message_passing_runtime_type=_runtime_type_symbol(self._message_passing),
        )
        self._adaptive_maintenance_context = context
        return context

    def clear_adaptive_maintenance_context(self) -> None:
        """Close the trusted context.  Maintenance outside a context fails closed."""

        self._adaptive_maintenance_context = None

    def _active_maintenance_context(self, operator: str) -> _AdaptiveMaintenanceContext:
        context = self._adaptive_maintenance_context
        if context is None:
            raise AdaptiveMaintenanceContractError(
                f"{operator} maintenance ran outside a bound adaptive execution context"
            )
        return context

    def _require_maintenance_payload(
        self,
        payload: object,
        *,
        operator: str,
        kind: str,
        required_fields: tuple[str, ...],
        context: _AdaptiveMaintenanceContext,
    ) -> Mapping[str, object]:
        """Validate the shape and node kind of one declared upstream dependency.

        This is the first of three layers.  It only makes the payload safe to read:
        the semantic value checks and then the execution-identity checks
        (:meth:`_require_maintenance_stamp` and
        :meth:`_AdaptiveMaintenanceContext.require_produced`) run afterwards, in
        that order, so a payload that contradicts live runtime state is still
        reported as a semantic contract violation rather than being masked by the
        provenance check.  This method never mutates state.
        """

        if not isinstance(payload, Mapping):
            raise AdaptiveMaintenanceContractError(
                f"{operator} maintenance dependency is not a payload mapping"
            )
        if payload.get("maintenance_kind") != kind:
            raise AdaptiveMaintenanceContractError(
                f"{operator} maintenance dependency is not a {kind} payload"
            )
        expected = {
            "maintenance_kind",
            "runtime_execution_id",
            "maintenance_epoch",
            *required_fields,
        }
        if set(payload) != expected:
            raise AdaptiveMaintenanceContractError(
                f"{operator} maintenance dependency field set drifted from the frozen shape"
            )
        return payload

    @staticmethod
    def _require_maintenance_stamp(
        payload: Mapping[str, object],
        *,
        operator: str,
        context: _AdaptiveMaintenanceContext,
    ) -> None:
        """Check that the dependency was produced by *this* execution.

        A payload whose runtime execution id or epoch differs cannot be substituted
        even when every semantic field agrees -- the round-2 review's
        ``different_runtime_same_head_accepted`` counterexample.
        """

        if payload["runtime_execution_id"] != str(context.runtime_execution_id):
            raise AdaptiveMaintenanceContractError(
                f"{operator} maintenance dependency came from a foreign runtime execution"
            )
        if payload["maintenance_epoch"] != context.epoch:
            raise AdaptiveMaintenanceContractError(
                f"{operator} maintenance dependency came from a different execution epoch"
            )

    @staticmethod
    def _require_sha256_tuple(value: object, *, operator: str, field: str) -> tuple[str, ...]:
        """Reject a dependency field that is not a tuple of content hashes."""

        if not isinstance(value, tuple) or any(
            not isinstance(item, str) or not _SHA256_PATTERN.fullmatch(item) for item in value
        ):
            raise AdaptiveMaintenanceContractError(
                f"{operator} maintenance dependency field {field} is not a content-hash tuple"
            )
        return value

    @staticmethod
    def _require_sha256(value: object, *, operator: str, field: str) -> str:
        if not isinstance(value, str) or not _SHA256_PATTERN.fullmatch(value):
            raise AdaptiveMaintenanceContractError(
                f"{operator} maintenance dependency field {field} is not a content hash"
            )
        return value

    def _adaptive_pchmp_safety_maintenance(
        self, transition: PrototypeTransition
    ) -> dict[str, object]:
        """Preserve raw evidence/provenance without inventing a deferred posterior.

        The evidence hashes are recomputed here from the transition the runtime is
        actually executing, and checked against the trusted context's own record, so
        a caller cannot present a different transition's evidence.
        """

        context = self._active_maintenance_context("pchmp")
        self._validate_transition(transition)
        evidence_hashes = tuple(content_sha256(item) for item in transition.evidence)
        if evidence_hashes != context.evidence_content_sha256s:
            raise AdaptiveMaintenanceContractError(
                "pchmp maintenance ran on a transition other than this execution's"
            )
        payload: dict[str, object] = {
            "maintenance_kind": "pchmp_safety_maintenance",
            "runtime_execution_id": str(context.runtime_execution_id),
            "maintenance_epoch": context.epoch,
            "evidence_content_sha256s": evidence_hashes,
            "unexecuted_inference_encoded_as_negative": False,
            "message_passing_runtime_type": _runtime_type_symbol(self._message_passing),
        }
        context.record_output("pchmp", payload)
        return payload

    def _adaptive_cf_bocpd_safety_maintenance(self) -> dict[str, object]:
        """Expose the unchanged online filter head for a safe deferred path."""

        context = self._active_maintenance_context("cf_bocpd")
        snapshot = self.current_cause_snapshot
        payload: dict[str, object] = {
            "maintenance_kind": "cf_bocpd_safety_maintenance",
            "runtime_execution_id": str(context.runtime_execution_id),
            "maintenance_epoch": context.epoch,
            "observation_count": self.observation_count,
            "current_snapshot_sha256": content_sha256(snapshot) if snapshot else None,
            "posterior_advanced": False,
        }
        context.record_output("cf_bocpd", payload)
        return payload

    def _adaptive_ccrr_safety_maintenance(
        self, cf_bocpd_maintenance: Mapping[str, object]
    ) -> dict[str, object]:
        """Check the CF-BOCPD dependency, then report the unchanged regime head.

        ``ADAPTIVE_PRIMARY_CONSUMPTION_GRAPHS["P0_SAFE_DEFERRED"]`` declares
        ``ccrr <- cf_bocpd``.  The dependency is verified three ways: the payload must
        carry this execution's identity and epoch; its content must equal the CF
        output this execution actually produced; and its values must still agree with
        live runtime state.  A deferred path that claims an advanced CF-BOCPD
        posterior contradicts ``P0_SAFE_DEFERRED``'s frozen ``semantic_purpose``.

        This method reads state and raises; it never writes.
        """

        context = self._active_maintenance_context("ccrr")
        payload = self._require_maintenance_payload(
            cf_bocpd_maintenance,
            operator="ccrr",
            kind="cf_bocpd_safety_maintenance",
            required_fields=(
                "observation_count",
                "current_snapshot_sha256",
                "posterior_advanced",
            ),
            context=context,
        )
        observed = payload["observation_count"]
        if isinstance(observed, bool) or not isinstance(observed, int):
            raise AdaptiveMaintenanceContractError(
                "ccrr maintenance dependency carries a non-integer observation count"
            )
        if observed != self.observation_count:
            raise AdaptiveMaintenanceContractError(
                "ccrr maintenance dependency observation count differs from this runtime"
            )
        snapshot = self.current_cause_snapshot
        expected_snapshot_sha256 = content_sha256(snapshot) if snapshot else None
        recorded_snapshot = payload["current_snapshot_sha256"]
        if recorded_snapshot is not None:
            self._require_sha256(
                recorded_snapshot, operator="ccrr", field="current_snapshot_sha256"
            )
        if recorded_snapshot != expected_snapshot_sha256:
            raise AdaptiveMaintenanceContractError(
                "ccrr maintenance dependency binds a foreign or stale cause snapshot"
            )
        if payload["posterior_advanced"] is not False:
            raise AdaptiveMaintenanceContractError(
                "a deferred path cannot report an advanced CF-BOCPD posterior"
            )
        self._require_maintenance_stamp(payload, operator="ccrr", context=context)
        context.require_produced("cf_bocpd", content_sha256(payload), consumer="ccrr")
        body: dict[str, object] = {
            "maintenance_kind": "ccrr_safety_maintenance",
            "runtime_execution_id": str(context.runtime_execution_id),
            "maintenance_epoch": context.epoch,
            "active_regime": self.active_regime,
            "pending_candidate_sha256": content_sha256(self._automatic_regimes._pending),
            "regime_transition_applied": False,
            "consumed_cf_bocpd_maintenance_sha256": content_sha256(cf_bocpd_maintenance),
        }
        context.record_output("ccrr", body)
        return body

    def _adaptive_rgrc_debt_guard(
        self,
        pchmp_maintenance: Mapping[str, object],
        ccrr_maintenance: Mapping[str, object],
    ) -> dict[str, object]:
        """Check both declared dependencies, then deny the long-term write.

        The frozen P0 graph declares ``rgrc <- (pchmp, ccrr)``.  Each dependency is
        checked for execution identity, for equality with the output this execution
        actually produced, for field types, and against the trusted context:

        * PCHMP's evidence hashes must equal the evidence of *this* transition --
          a well-formed but foreign or malformed hash set is refused;
        * ``unexecuted_inference_encoded_as_negative`` must be ``False``
          (``maximum_unresolved_as_negative_events`` is 0);
        * CCRR's declared CF consumption must name the CF output this execution
          produced, and its regime head must still match the live runtime.

        This method reads state and raises; it never writes, and it never returns
        ``long_term_write_authorized`` other than ``False``.
        """

        context = self._active_maintenance_context("rgrc")
        pchmp = self._require_maintenance_payload(
            pchmp_maintenance,
            operator="rgrc",
            kind="pchmp_safety_maintenance",
            required_fields=(
                "evidence_content_sha256s",
                "unexecuted_inference_encoded_as_negative",
                "message_passing_runtime_type",
            ),
            context=context,
        )
        evidence_hashes = self._require_sha256_tuple(
            pchmp["evidence_content_sha256s"],
            operator="rgrc",
            field="evidence_content_sha256s",
        )
        if evidence_hashes != context.evidence_content_sha256s:
            raise AdaptiveMaintenanceContractError(
                "rgrc maintenance dependency binds evidence from another transition"
            )
        if pchmp["unexecuted_inference_encoded_as_negative"] is not False:
            raise AdaptiveMaintenanceContractError(
                "unexecuted inference cannot be encoded as negative evidence"
            )
        if pchmp["message_passing_runtime_type"] != context.message_passing_runtime_type:
            raise AdaptiveMaintenanceContractError(
                "rgrc maintenance dependency binds a foreign message-passing runtime"
            )
        self._require_maintenance_stamp(pchmp, operator="rgrc", context=context)
        context.require_produced("pchmp", content_sha256(pchmp), consumer="rgrc")
        ccrr = self._require_maintenance_payload(
            ccrr_maintenance,
            operator="rgrc",
            kind="ccrr_safety_maintenance",
            required_fields=(
                "active_regime",
                "pending_candidate_sha256",
                "regime_transition_applied",
                "consumed_cf_bocpd_maintenance_sha256",
            ),
            context=context,
        )
        consumed_cf = self._require_sha256(
            ccrr["consumed_cf_bocpd_maintenance_sha256"],
            operator="rgrc",
            field="consumed_cf_bocpd_maintenance_sha256",
        )
        if ccrr["regime_transition_applied"] is not False:
            raise AdaptiveMaintenanceContractError(
                "a deferred path cannot report an applied regime transition"
            )
        if ccrr["active_regime"] != self.active_regime:
            raise AdaptiveMaintenanceContractError(
                "rgrc maintenance dependency binds a foreign or stale active regime"
            )
        if ccrr["pending_candidate_sha256"] != content_sha256(self._automatic_regimes._pending):
            raise AdaptiveMaintenanceContractError(
                "rgrc maintenance dependency binds a stale CCRR pending candidate"
            )
        self._require_maintenance_stamp(ccrr, operator="rgrc", context=context)
        context.require_produced("ccrr", content_sha256(ccrr), consumer="rgrc")
        context.require_produced("cf_bocpd", consumed_cf, consumer="rgrc")
        body: dict[str, object] = {
            "maintenance_kind": "rgrc_debt_guard",
            "runtime_execution_id": str(context.runtime_execution_id),
            "maintenance_epoch": context.epoch,
            "belief_snapshot_id": str(self.current_snapshot.snapshot_id),
            "committed_revision_count": len(self._committed_events),
            "quarantined_revision_count": len(self._quarantined_events),
            "long_term_write_authorized": False,
            "origin_transition_sha256": context.origin_transition_sha256,
            "debt_certificate_sha256": context.debt_certificate_sha256,
            "consumed_pchmp_maintenance_sha256": content_sha256(pchmp_maintenance),
            "consumed_ccrr_maintenance_sha256": content_sha256(ccrr_maintenance),
        }
        context.record_output("rgrc", body)
        return body

    def _mutation_is_forbidden_during_sink_commit(self) -> bool:
        if not self._execution_contract_active:
            return False
        return bool(
            self._execution_contract_phase != "operators"
            or self._execution_owner_thread_id != get_ident()
        )

    @property
    def fast_action_verification_receipts(self) -> tuple[FastActionVerificationReceipt, ...]:
        return tuple(self._fast_action_verification_receipts)

    def rls_regime_snapshot(self, regime_id: str) -> dict[str, object]:
        return self._regimes.regime_snapshot(regime_id)

    def hybrid_alpha(self, location_id: UUID) -> float:
        key = self._hybrid_loop._key(location_id)
        return self._hybrid_loop.ledger.projection(key).alpha

    def verify_hybrid_full_rerun_equivalence(
        self, *, absolute_tolerance: float = 1e-10
    ) -> HybridFullRerunEquivalenceReceipt:
        """Verify cached Hybrid RGRC state against its append-only replay."""

        return self._hybrid_loop.verify_full_rerun_equivalence(
            location_ids=self.locations,
            absolute_tolerance=absolute_tolerance,
        )

    def is_committed_revision(self, revision_id: UUID) -> bool:
        return revision_id in self._committed_events

    def is_quarantined_revision(self, revision_id: UUID) -> bool:
        return any(event.revision_id == revision_id for event in self._quarantined_events)

    def application_receipts_for_feedback(
        self, feedback_record_id: UUID
    ) -> tuple[ProjectOneRequestApplicationReceipt, ...]:
        return tuple(self._project_one_application_receipts.get(feedback_record_id, ()))

    @_serialized_core_mutation
    def retry_deferred_project_one_requests(
        self, revision_id: UUID
    ) -> tuple[ProjectOneRequestApplicationReceipt, ...]:
        """Retry every request waiting on one newly promoted event exactly once."""

        if self._production_operator_contract is not None:
            self._production_operator_contract()
        checkpoint = self._capture_revision_transaction(include_operator_state=True)
        try:
            return self._retry_deferred_project_one_requests(revision_id)
        except BaseException:
            self._restore_revision_transaction(checkpoint)
            raise

    def _retry_deferred_project_one_requests(
        self, revision_id: UUID
    ) -> tuple[ProjectOneRequestApplicationReceipt, ...]:

        pending = [
            (fingerprint, request, mode)
            for fingerprint, (
                request,
                waiting_revision_id,
                mode,
            ) in self._deferred_project_one_requests.items()
            if waiting_revision_id == revision_id
        ]
        if pending:
            receipts: list[ProjectOneRequestApplicationReceipt] = []
            for fingerprint, request, mode in pending:
                if mode == "apply_request":
                    # This is the one authorized retry transition. Remove the
                    # outbox guard immediately before re-entering application;
                    # ordinary caller replays still observe the guard above.
                    self._deferred_project_one_requests.pop(fingerprint, None)
                    receipts.append(self.apply_project_one_stat_request(request))
                    continue
                event = self._committed_events.get(revision_id)
                if event is None:
                    continue
                semantics = self.committed_weight_semantics(revision_id)
                receipt = self._record_request_receipt(
                    request=request,
                    fingerprint=fingerprint,
                    status=ProjectOneRequestApplicationStatus.APPLIED,
                    old_snapshot=self.current_snapshot,
                    new_snapshot=self.current_snapshot,
                    dirichlet=(
                        StatisticDelta(
                            statistic="owner_training_weight",
                            before=0.0,
                            after=semantics["dirichlet_owner_weight"],
                            delta=semantics["dirichlet_owner_weight"],
                        ),
                    ),
                    rls=(
                        StatisticDelta(
                            statistic="owner_gate",
                            before=0.0,
                            after=semantics["rls_owner_weight"],
                            delta=semantics["rls_owner_weight"],
                        ),
                    ),
                    hybrid=(
                        StatisticDelta(
                            statistic=f"alpha:{event.location_id}",
                            before=0.0,
                            after=self.hybrid_alpha(event.location_id),
                            delta=self.hybrid_alpha(event.location_id),
                        ),
                    ),
                    ccrr_decision=self._last_ccrr_decision,
                    rationale="CCRR promotion finalized the deferred corrected statistic",
                )
                self._deferred_project_one_requests.pop(fingerprint, None)
                self._deferred_correction_restore.pop(fingerprint, None)
                receipts.append(receipt)
            return tuple(receipts)
        # A manual or duplicate promotion notification is an auditable replay noop.
        previous = [
            receipt
            for receipts in self._project_one_application_receipts.values()
            for receipt in receipts
            if receipt.superseded_revision_id == revision_id
            and receipt.status is ProjectOneRequestApplicationStatus.APPLIED
        ]
        return tuple(self._replay_receipt(receipt) for receipt in previous[-1:])

    def _reject_deferred_project_one_requests(
        self, revision_ids: set[UUID], *, rationale: str, trigger_revision_id: UUID
    ) -> tuple[ProjectOneRequestApplicationReceipt, ...]:
        """Close deferred requests when CCRR explicitly discards quarantine."""

        pending = [
            (fingerprint, request, waiting_revision_id, mode)
            for fingerprint, (
                request,
                waiting_revision_id,
                mode,
            ) in self._deferred_project_one_requests.items()
            if waiting_revision_id in revision_ids
        ]
        receipts = []
        for fingerprint, request, child_id, mode in pending:
            if mode == "promotion_finalizes":
                parent = self._revision_parent_events.get(request.superseded_revision_id)
                child = self._observed_events.get(child_id)
                if (
                    parent is None
                    or child is None
                    or child_id != request.corrected_revision_id
                    or child_id in self._committed_events
                    or not self._observation_write_eligible(parent.revision_id)
                    or any(
                        c.corrected_event.revision_id == child_id
                        for c in self._correction_cancellations
                    )
                ):
                    raise ValueError("deferred correction cancellation has no restorable lineage")
                restoration = self._deferred_correction_restore.get(fingerprint)
                if restoration is None or restoration[0][0].revision_id != parent.revision_id:
                    raise ValueError("missing original deferred correction contribution snapshot")
                cancellation = DeferredCorrectionCancellation(
                    fingerprint,
                    request,
                    parent,
                    child,
                    len(self._revision_transactions),
                    trigger_revision_id,
                    rationale,
                    *restoration,
                )
                cancellation = replace(
                    cancellation, body_sha256=native_content_sha256(cancellation.body())
                )
                cancellation.validate_content()
                self._correction_cancellations = (*self._correction_cancellations, cancellation)
                self._observed_events.pop(child_id)
                self._fast_action_events.pop(child_id, None)
                self._particle_workspace.invalidate_revisions({child_id})
                restored = replace(restoration[0][0], belief_snapshot_id=None)
                self._observed_events[parent.revision_id] = restored
                for fast in restoration[1]:
                    self._fast_action_events[fast.revision_id] = fast
                self._revision_fault_hook("cancellation_lineage")
            receipts.append(
                self._record_request_receipt(
                    request=request,
                    fingerprint=fingerprint,
                    status=ProjectOneRequestApplicationStatus.REJECTED,
                    old_snapshot=self.current_snapshot,
                    new_snapshot=self.current_snapshot,
                    ccrr_decision=self._last_ccrr_decision,
                    rationale=rationale,
                )
            )
            self._deferred_project_one_requests.pop(fingerprint, None)
            self._deferred_correction_restore.pop(fingerprint, None)
        return tuple(receipts)

    @property
    def derived_reactivation_policy(self) -> str:
        return self.loop_config.derived_reactivation_policy.value

    def committed_actor_posterior(self, revision_id: UUID) -> Mapping[str, float]:
        return dict(self._committed_events[revision_id].evidence.actor_posterior)

    def committed_weight_semantics(self, revision_id: UUID) -> Mapping[str, float]:
        event = self._committed_events[revision_id]
        dirichlet_owner_weight = (
            event.evidence.effective_training_weight
            * event.propensity_weight
            * event.evidence.actor_posterior.get(self.owner_key, 0.0)
        )
        return {
            "dirichlet_owner_weight": dirichlet_owner_weight,
            "rls_owner_weight": event.rls_sample.gate,
            "hybrid_owner_weight": event.statistical_owner_weight,
        }

    def derived_revision_ids(self, revision_id: UUID) -> tuple[UUID, ...]:
        return tuple(
            item.revision_id
            for item in self._committed_events.values()
            if item.derived_from_revision_id == revision_id
        )

    def derived_revision_lifecycle(self, revision_id: UUID) -> str:
        return self._derived_event_lifecycle[revision_id].value

    @_serialized_core_mutation
    def switch_regime(self, to_regime_id: str, *, event_time: datetime) -> str:
        """Explicit prototype adapter for a later CF-BOCPD/CCRR decision."""

        previous = self.active_regime
        if previous == to_regime_id:
            return previous
        self._switch_sequence += 1
        return self._regimes.mark_regime_switch(
            event=RLSRegimeSwitchEvent(
                object_instance_id=self.object_instance_id,
                actor_id=self.owner_key,
                from_regime_id=previous,
                to_regime_id=to_regime_id,
                event_time=event_time,
                sequence=self._switch_sequence,
            )
        )

    def process_transition(
        self,
        transition: PrototypeTransition,
        *,
        execution_plan: StructureTwoExecutionPlan | None = None,
        trace_sink: TraceSink | None = None,
    ) -> PrototypeStepResult:
        """Commit one transition, optionally through the immutable Architecture-A seam.

        Supplying neither new argument preserves the historical untraced behavior.
        Audited execution is deliberately rollback-guarded: a plan and sink must
        be supplied together, and a missing or mismatched sink acknowledgement
        restores the audited core-state envelope.  This is not a cross-system
        durable transaction guarantee.
        """

        if self._execution_contract_active:
            raise RuntimeError("reentrant or concurrent transition execution is forbidden")
        return cast(
            PrototypeStepResult,
            self._process_transition_with_runtime_binding(
                transition,
                execution_plan=execution_plan,
                trace_sink=trace_sink,
                runtime_symbol=f"{type(self).__module__}.{type(self).__qualname__}",
                system_version=self.model_version,
                runtime_operator_instances_provider=None,
                runtime_guard_components_provider=None,
                runtime_guard_state_provider=None,
                runtime_lock_components_provider=None,
            ),
        )

    def _process_transition_with_runtime_binding(
        self,
        transition: PrototypeTransition,
        *,
        execution_plan: StructureTwoExecutionPlan | None,
        trace_sink: TraceSink | None,
        runtime_symbol: str,
        system_version: str,
        runtime_operator_instances_provider: (Callable[[], Mapping[str, Sequence[object]]] | None),
        runtime_guard_components_provider: Callable[[], Mapping[str, object]] | None,
        runtime_guard_state_provider: Callable[[], str] | None,
        runtime_lock_components_provider: Callable[[], Mapping[str, object]] | None,
        adaptive_executor: (
            Callable[[PrototypeTransition, _TransitionTraceRecorder], object] | None
        ) = None,
        allow_runtime_state_change_during_operators: bool = False,
    ) -> object:
        if self._execution_contract_active:
            raise RuntimeError("reentrant or concurrent transition execution is forbidden")
        # A per-runtime lock closes the stale-checkpoint race between concurrent
        # traced and legacy transitions.  RLock keeps the explicit reentrancy
        # error below observable when a sink calls back on the same thread.
        execution_lock = self._execution_lock
        pre_acquire_depth = _runtime_rlock_depth(execution_lock)
        acquire = getattr(execution_lock, "acquire", None)
        if not callable(acquire) or acquire() is not True:
            raise RuntimeError("core execution lock could not be acquired")
        execution_lock_depth = _runtime_rlock_depth(execution_lock)
        try:
            result = self._process_transition_with_runtime_binding_locked(
                transition,
                execution_plan=execution_plan,
                trace_sink=trace_sink,
                runtime_symbol=runtime_symbol,
                system_version=system_version,
                runtime_operator_instances_provider=runtime_operator_instances_provider,
                runtime_guard_components_provider=runtime_guard_components_provider,
                runtime_guard_state_provider=runtime_guard_state_provider,
                runtime_lock_components_provider=runtime_lock_components_provider,
                adaptive_executor=adaptive_executor,
                allow_runtime_state_change_during_operators=(
                    allow_runtime_state_change_during_operators
                ),
                execution_lock=execution_lock,
                execution_lock_depth=execution_lock_depth,
            )
        except BaseException as execution_error:
            try:
                _restore_runtime_rlock_depth(
                    execution_lock,
                    pre_acquire_depth,
                    verify_unowned_available=False,
                )
            except RuntimeError as recovery_error:
                recovery_error.add_note(
                    f"original execution failure: {type(execution_error).__qualname__}"
                )
                raise RuntimeError(
                    "core execution lock ownership could not be restored"
                ) from recovery_error
            raise
        try:
            _restore_runtime_rlock_depth(
                execution_lock,
                pre_acquire_depth,
                verify_unowned_available=False,
            )
        except RuntimeError as recovery_error:
            raise RuntimeError(
                "core execution lock ownership could not be restored"
            ) from recovery_error
        return result

    def _process_transition_with_runtime_binding_locked(
        self,
        transition: PrototypeTransition,
        *,
        execution_plan: StructureTwoExecutionPlan | None,
        trace_sink: TraceSink | None,
        runtime_symbol: str,
        system_version: str,
        runtime_operator_instances_provider: (Callable[[], Mapping[str, Sequence[object]]] | None),
        runtime_guard_components_provider: Callable[[], Mapping[str, object]] | None,
        runtime_guard_state_provider: Callable[[], str] | None,
        runtime_lock_components_provider: Callable[[], Mapping[str, object]] | None,
        adaptive_executor: (
            Callable[[PrototypeTransition, _TransitionTraceRecorder], object] | None
        ),
        allow_runtime_state_change_during_operators: bool,
        execution_lock: object,
        execution_lock_depth: int,
    ) -> object:
        if self._execution_contract_active:
            raise RuntimeError("reentrant or concurrent transition execution is forbidden")

        if adaptive_executor is None:
            # Direct CorePrototypeSpine calls and both legacy Architecture-A
            # lanes must honor any production-owned inference-debt barrier.
            self._require_external_mutation_permission()

        # Preserve the legacy call path without trace allocation, source hashing,
        # or an extra UUID draw.  This is compatibility behavior, not implicit P5.
        if execution_plan is None and trace_sink is None:
            if self._production_operator_contract is not None:
                self._production_operator_contract()
            checkpoint = self._capture_revision_transaction(include_operator_state=True)
            try:
                return self._process_transition(transition)
            except BaseException:
                self._restore_revision_transaction(checkpoint)
                raise
        if execution_plan is None or trace_sink is None:
            raise ValueError("execution_plan and trace_sink must be supplied together")
        if not isinstance(execution_plan, StructureTwoExecutionPlan):
            raise TypeError("execution_plan must satisfy StructureTwoExecutionPlan")
        checked_plan = StructureTwoExecutionPlan.model_validate(
            execution_plan.model_dump(mode="json")
        )
        adaptive = checked_plan.lane == "registered_adaptive_path"
        if adaptive and adaptive_executor is None:
            raise UnsupportedStructureTwoExecutionPlan(
                "adaptive P0-P5 plans require the production adaptive executor"
            )
        if not isinstance(trace_sink, TraceSink):
            raise TypeError(
                "trace_sink must implement commit(trace) and compensating abort(trace, reason=...)"
            )
        if (
            not self.loop_config.cause_factorized_bocpd_enabled
            or not self.loop_config.ccrr_enabled
            or not self._rgrc_gate_enabled
        ):
            raise UnsupportedStructureTwoExecutionPlan(
                "traced execution requires CF-BOCPD, CCRR, and RGRC gates to be enabled"
            )

        # All contract and source validation happens before the first mutable
        # operator call.  Unsupported plans cannot leave partial model state.
        self._validate_transition(transition)
        runtime_operator_instances = (
            runtime_operator_instances_provider()
            if runtime_operator_instances_provider is not None
            else None
        )
        runtime_execution_id = uuid4()
        bindings = self._execution_callable_bindings(
            runtime_execution_id=runtime_execution_id,
            runtime_operator_instances=runtime_operator_instances,
        )
        recorder = _TransitionTraceRecorder.create(
            runtime_execution_id=runtime_execution_id,
            plan=checked_plan,
            bindings=bindings,
        )
        transition_sha256 = content_sha256(transition)
        initial_state_sha256 = self._execution_observable_state_sha256()
        runtime_identity_guard = self._execution_runtime_identity_guard(
            runtime_operator_instances,
            extra_components=(
                runtime_guard_components_provider()
                if runtime_guard_components_provider is not None
                else None
            ),
        )
        external_runtime_state_guard = (
            runtime_guard_state_provider() if runtime_guard_state_provider is not None else None
        )
        runtime_lock_guard = self._execution_runtime_lock_guard(
            execution_lock=execution_lock,
            execution_lock_depth=execution_lock_depth,
            extra_locks=(
                runtime_lock_components_provider()
                if runtime_lock_components_provider is not None
                else None
            ),
        )
        checkpoint = self._capture_revision_transaction(include_operator_state=True)
        self._execution_contract_active = True
        self._execution_contract_phase = "operators"
        self._execution_owner_thread_id = get_ident()
        trace: StructureTwoExecutionTrace | None = None
        try:
            try:
                if adaptive:
                    assert adaptive_executor is not None
                    result = adaptive_executor(transition, recorder)
                else:
                    result = self._process_transition(transition, trace_recorder=recorder)
                    recorder.record_ciav_not_applicable(transition)
                trace = seal_execution_trace(
                    runtime_execution_id=runtime_execution_id,
                    runtime_symbol=runtime_symbol,
                    system_version=system_version,
                    plan=checked_plan,
                    transition_sha256=transition_sha256,
                    initial_state_sha256=initial_state_sha256,
                    final_state_sha256=self._execution_observable_state_sha256(),
                    final_output_sha256=content_sha256(result),
                    receipts=tuple(recorder.receipts),
                    adaptive_router_feature_sha256=(recorder.adaptive_router_feature_sha256),
                    adaptive_router_source_state_sha256=(
                        recorder.adaptive_router_source_state_sha256
                    ),
                    adaptive_authorization_policy_sha256=(
                        recorder.adaptive_authorization_policy_sha256
                    ),
                    adaptive_path_selection_receipt_sha256=(
                        recorder.adaptive_path_selection_receipt_sha256
                    ),
                    adaptive_ciav_input_sha256=recorder.adaptive_ciav_input_sha256,
                    adaptive_step_index=recorder.adaptive_step_index,
                    adaptive_debt_expiry_steps=recorder.adaptive_debt_expiry_steps,
                    debt_certificates=tuple(recorder.debt_certificates),
                    replayed_debt_certificates=tuple(recorder.replayed_debt_certificates),
                    feedback_observation_acquired=recorder.feedback_observation_acquired,
                    feedback_closure_kind=recorder.feedback_closure_kind,
                )
                verify_execution_trace(trace)
                operator_lock_mutations = self._restore_execution_runtime_lock_guard(
                    runtime_lock_guard
                )
                if operator_lock_mutations:
                    raise RuntimeError(
                        "operator execution mutated runtime-lock ownership: "
                        + ",".join(operator_lock_mutations)
                    )
                if (
                    self._execution_runtime_identity_guard(
                        (
                            runtime_operator_instances_provider()
                            if runtime_operator_instances_provider is not None
                            else runtime_operator_instances
                        ),
                        extra_components=(
                            runtime_guard_components_provider()
                            if runtime_guard_components_provider is not None
                            else None
                        ),
                    )
                    != runtime_identity_guard
                ):
                    raise RuntimeError("operator execution replaced an audited runtime component")
                external_runtime_post_operator_state_guard = (
                    runtime_guard_state_provider()
                    if runtime_guard_state_provider is not None
                    else None
                )
                if (
                    runtime_guard_state_provider is not None
                    and not allow_runtime_state_change_during_operators
                    and external_runtime_post_operator_state_guard != external_runtime_state_guard
                ):
                    raise RuntimeError(
                        "operator execution mutated audited production-wrapper state"
                    )
            except BaseException:
                self._restore_revision_transaction(checkpoint)
                raise

            sink_runtime_identity_guard = self._execution_runtime_identity_guard(
                (
                    runtime_operator_instances_provider()
                    if runtime_operator_instances_provider is not None
                    else runtime_operator_instances
                ),
                extra_components=(
                    runtime_guard_components_provider()
                    if runtime_guard_components_provider is not None
                    else None
                ),
                include_dynamic_operator_state=True,
            )
            trace_snapshot = StructureTwoExecutionTrace.model_validate(
                trace.model_dump(mode="json")
            )
            self._execution_contract_phase = "sink_commit"
            try:
                acknowledgement = trace_sink.commit(trace)
                sink_lock_mutations = self._restore_execution_runtime_lock_guard(runtime_lock_guard)
                if sink_lock_mutations:
                    raise RuntimeError(
                        "trace sink mutated runtime-lock ownership: "
                        + ",".join(sink_lock_mutations)
                    )
                if trace != trace_snapshot:
                    raise RuntimeError("trace sink mutated the sealed execution trace")
                verify_execution_trace(trace)
                if not isinstance(acknowledgement, TraceCommitAck):
                    raise TypeError("trace sink returned no typed commit acknowledgement")
                verify_trace_commit_ack(acknowledgement, trace=trace_snapshot)
                if self._execution_observable_state_sha256() != trace.final_state_sha256:
                    raise RuntimeError("trace sink mutated audited core state during commit")
                if (
                    self._execution_runtime_identity_guard(
                        (
                            runtime_operator_instances_provider()
                            if runtime_operator_instances_provider is not None
                            else runtime_operator_instances
                        ),
                        extra_components=(
                            runtime_guard_components_provider()
                            if runtime_guard_components_provider is not None
                            else None
                        ),
                        include_dynamic_operator_state=True,
                    )
                    != sink_runtime_identity_guard
                ):
                    raise RuntimeError("trace sink replaced an audited runtime component")
                if (
                    runtime_guard_state_provider is not None
                    and runtime_guard_state_provider() != external_runtime_post_operator_state_guard
                ):
                    raise RuntimeError("trace sink mutated audited production-wrapper state")
            except BaseException as commit_error:
                pre_abort_lock_mutations = self._restore_execution_runtime_lock_guard(
                    runtime_lock_guard
                )
                reason = f"{type(commit_error).__module__}.{type(commit_error).__qualname__}"
                abort_error: BaseException | None = None
                try:
                    abort_trace = StructureTwoExecutionTrace.model_validate(
                        trace_snapshot.model_dump(mode="json")
                    )
                    abort_ack = trace_sink.abort(abort_trace, reason=reason)
                    if abort_trace != trace_snapshot:
                        raise RuntimeError("trace sink mutated the compensating abort trace")
                    verify_execution_trace(abort_trace)
                    if not isinstance(abort_ack, TraceAbortAck):
                        raise TypeError("trace sink returned no typed abort acknowledgement")
                    verify_trace_abort_ack(abort_ack, trace=trace_snapshot, reason=reason)
                except BaseException as error:
                    abort_error = error
                abort_lock_mutations = self._restore_execution_runtime_lock_guard(
                    runtime_lock_guard
                )
                all_abort_lock_mutations = tuple(
                    dict.fromkeys((*pre_abort_lock_mutations, *abort_lock_mutations))
                )
                if all_abort_lock_mutations:
                    abort_error = abort_error or RuntimeError(
                        "trace sink abort mutated runtime-lock ownership: "
                        + ",".join(all_abort_lock_mutations)
                    )
                if abort_error is not None:
                    self._restore_revision_transaction(checkpoint)
                    raise TraceCompensationError(
                        "model state rolled back but trace tombstone acknowledgement or "
                        "runtime-lock restoration could not be verified"
                    ) from abort_error
                self._restore_revision_transaction(checkpoint)
                raise
            return result
        finally:
            self._restore_execution_runtime_lock_guard(runtime_lock_guard)
            self._execution_contract_active = False
            self._execution_contract_phase = "idle"
            self._execution_owner_thread_id = None

    def _execution_callable_bindings(
        self,
        *,
        runtime_execution_id: UUID,
        runtime_operator_instances: Mapping[str, Sequence[object]] | None,
    ) -> dict[str, RuntimeCallableBinding]:
        router = self._automatic_regimes
        local_instances: dict[str, Sequence[object]] = {
            "opceu": (self._corrector,),
            "orrer_cheh": (self._event_engine,),
            "pchmp": (self._message_passing,),
            "cf_bocpd": (router.bocpd,),
            "ccrr": (router,),
        }
        selected_instances = runtime_operator_instances or local_instances
        if runtime_operator_instances is not None:
            if tuple(runtime_operator_instances) != STRUCTURE_TWO_OPERATOR_ORDER:
                raise ValueError("production runtime operator mapping order drifted")
            expected_bound_instances: dict[str, Sequence[object]] = {
                "opceu": (self._corrector,),
                "orrer_cheh": (self._event_engine,),
                "pchmp": (self._message_passing,),
                "cf_bocpd": (router.bocpd,),
                "ccrr": (router, router.ccrr),
                "rgrc": (self, self._hybrid_loop.ledger),
            }
            if self._production_operator_contract is not None:
                expected_bound_instances = dict(self._production_operator_contract())
            for operator, expected_instances in expected_bound_instances.items():
                supplied_instances = tuple(runtime_operator_instances.get(operator, ()))
                if len(supplied_instances) != len(expected_instances) or any(
                    supplied is not expected
                    for supplied, expected in zip(
                        supplied_instances,
                        expected_instances,
                        strict=False,
                    )
                ):
                    raise ValueError(
                        f"production runtime mapping is not bound to the called {operator} object"
                    )

        def instance(operator: str) -> object:
            values = selected_instances.get(operator)
            if not values:
                raise ValueError(f"runtime operator instance is missing: {operator}")
            return values[0]

        specifications = (
            ("opceu", instance("opceu"), "weight_for_opportunity", "direct_operator_callable"),
            ("orrer_cheh", instance("orrer_cheh"), "branch", "direct_operator_callable"),
            ("pchmp", instance("pchmp"), "consume", "direct_operator_callable"),
            (
                "cf_bocpd",
                instance("cf_bocpd"),
                "observe_online",
                "direct_operator_callable",
            ),
            # The automatic router is the one callable that realizes the
            # complete CCRR stage and returns AutomaticRegimeAssessment.
            ("ccrr", instance("ccrr"), "observe", "composite_operator_stage"),
            # Ordinary RGRC spans quarantine, promotion, commit, RLS and map
            # publication inside this enclosing runtime call.
            ("rgrc", self, "_process_transition", "enclosing_runtime_stage"),
        )
        return {
            operator: bind_runtime_callable(
                runtime_execution_id=runtime_execution_id,
                operator=operator,  # type: ignore[arg-type]
                binding_slot=0,
                binding_kind=binding_kind,  # type: ignore[arg-type]
                instance=bound_instance,
                callable_name=callable_name,
                require_declared_member=True,
            )
            for operator, bound_instance, callable_name, binding_kind in specifications
        }

    def _execution_runtime_identity_guard(
        self,
        runtime_operator_instances: Mapping[str, Sequence[object]] | None,
        *,
        extra_components: Mapping[str, object] | None = None,
        include_dynamic_operator_state: bool = False,
    ) -> tuple[tuple[str, int, str], ...]:
        """Capture process-local object/callable identities around sink commit."""

        router = self._automatic_regimes
        components: dict[str, object] = {
            "core": self,
            "execution_lock": self._execution_lock,
            "loop_config": self.loop_config,
            "event_engine": self._event_engine,
            "message_passing": self._message_passing,
            "propensity_corrector": self._corrector,
            "habit_model": self._habit,
            "embeddings": self._embeddings,
            "regime_bank": self._regimes,
            "regime_head_factory": self._regimes._head_factory,
            "regime_heads": self._regimes._heads,
            "hybrid_loop": self._hybrid_loop,
            "hybrid_ledger": self._hybrid_loop.ledger,
            "hybrid_map": self._hybrid_loop._map,
            "hybrid_coordinator": self._hybrid_loop._coordinator,
            "hybrid_feedback_projector": self._hybrid_loop._feedback_projector,
            "hybrid_fusion": self._hybrid_loop._fusion,
            "automatic_router": router,
            "bocpd": router.bocpd,
            "bocpd_reset_matrix": router.bocpd._reset_matrix,
            "ccrr": router.ccrr,
            "ccrr_lock": router.ccrr._lock,
            "feedback_policy": self._feedback_policy,
            "action_readout": self._action_readout,
            "hybrid_ledger_lock": self._hybrid_loop.ledger._lock,
            "hybrid_map_lock": self._hybrid_loop._map._lock,
            "project_one_application_receipts": self._project_one_application_receipts,
        }
        for table_name in (
            "_household_counts",
            "_person_counts",
            "_context_counts",
            "_isolated_nonresident_counts",
        ):
            table = getattr(self._habit, table_name)
            components[f"habit.{table_name}"] = table
        if include_dynamic_operator_state:
            components.update(self._execution_dynamic_operator_components())
        components.update(_message_passing_nested_components(self._message_passing))
        if runtime_operator_instances is not None:
            for operator, instances in runtime_operator_instances.items():
                for index, instance in enumerate(instances):
                    components[f"production.{operator}.{index}"] = instance
        if extra_components is not None:
            for name, component in extra_components.items():
                components[f"runtime.{name}"] = component

        for label, instance, callable_name in (
            ("call.opceu", self._corrector, "weight_for_opportunity"),
            ("call.orrer_cheh", self._event_engine, "branch"),
            ("call.pchmp", self._message_passing, "consume"),
            ("call.cf_bocpd", router.bocpd, "observe_online"),
            ("call.ccrr", router, "observe"),
            ("call.rgrc", self, "_process_transition"),
        ):
            method = getattr(instance, callable_name)
            components[label] = getattr(method, "__func__", method)
        return tuple(
            (label, id(component), _runtime_type_symbol(component))
            for label, component in sorted(components.items())
        )

    def _execution_dynamic_operator_components(self) -> dict[str, object]:
        """Enumerate mutable nested objects that exist after operator execution."""

        components: dict[str, object] = {}
        for table_name in (
            "_household_counts",
            "_person_counts",
            "_context_counts",
            "_isolated_nonresident_counts",
        ):
            table = getattr(self._habit, table_name)
            for key, row in sorted(table.items(), key=lambda item: repr(item[0])):
                row_label = content_sha256((table_name, key))
                components[f"habit.{table_name}.row.{row_label}"] = row
        for regime_id, head in sorted(self._regimes._heads.items()):
            head_label = content_sha256(regime_id)
            components[f"rls.head.{head_label}"] = head
            components[f"rls.head.{head_label}.models"] = head._models
            for key, wrapper in sorted(head._models.items(), key=lambda item: repr(item[0])):
                model_label = content_sha256(key)
                model = wrapper.model
                prefix = f"rls.head.{head_label}.model.{model_label}"
                components[f"{prefix}.wrapper"] = wrapper
                components[f"{prefix}.core"] = model
                components[f"{prefix}.config"] = model.config
                components[f"{prefix}.theta"] = model.theta
                components[f"{prefix}.covariance"] = model.covariance
        for key, receipts in sorted(
            self._project_one_application_receipts.items(), key=lambda item: str(item[0])
        ):
            components[f"project_one_application_receipts.row.{key}"] = receipts
        return components

    def _execution_runtime_lock_guard(
        self,
        *,
        execution_lock: object,
        execution_lock_depth: int,
        extra_locks: Mapping[str, object] | None = None,
    ) -> tuple[tuple[str, object, int], ...]:
        router = self._automatic_regimes
        guard = [
            ("core_execution", execution_lock, execution_lock_depth),
            ("ccrr", router.ccrr._lock, _runtime_rlock_depth(router.ccrr._lock)),
            (
                "hybrid_ledger",
                self._hybrid_loop.ledger._lock,
                _runtime_rlock_depth(self._hybrid_loop.ledger._lock),
            ),
            (
                "hybrid_map",
                self._hybrid_loop._map._lock,
                _runtime_rlock_depth(self._hybrid_loop._map._lock),
            ),
        ]
        if extra_locks is not None:
            guard.extend(
                (
                    f"runtime.{label}",
                    lock,
                    _runtime_rlock_depth(lock),
                )
                for label, lock in sorted(extra_locks.items())
            )
        return tuple(guard)

    @staticmethod
    def _restore_execution_runtime_lock_guard(
        guard: tuple[tuple[str, object, int], ...],
    ) -> tuple[str, ...]:
        mutations: list[str] = []
        for label, lock, expected_depth in guard:
            try:
                if _restore_runtime_rlock_depth(lock, expected_depth):
                    mutations.append(label)
            except RuntimeError:
                mutations.append(f"{label}:ownership_unrecoverable")
        return tuple(mutations)

    def _execution_observable_state_sha256(self) -> str:
        """Hash the auditable state envelope without claiming full state custody."""

        router = self._automatic_regimes

        def event_rows(
            values: Mapping[UUID, _CommittedPrototypeEvent],
        ) -> list[tuple[str, str]]:
            return [
                (str(key), repr(value))
                for key, value in sorted(values.items(), key=lambda item: str(item[0]))
            ]

        def count_table_configuration(table: dict[Any, Any]) -> dict[str, object]:
            return {
                "type": _runtime_type_symbol(table),
                "rows": [
                    {
                        "key": key,
                        "type": _runtime_type_symbol(row),
                    }
                    for key, row in sorted(table.items(), key=lambda item: repr(item[0]))
                ],
            }

        def rls_runtime_configuration() -> dict[str, object]:
            heads: list[dict[str, object]] = []
            for regime_id, head in sorted(self._regimes._heads.items()):
                models: list[dict[str, object]] = []
                for key, wrapper in sorted(head._models.items(), key=lambda item: repr(item[0])):
                    model = wrapper.model
                    models.append(
                        {
                            "key": key,
                            "wrapper_attribute_names": sorted(vars(wrapper)),
                            "model_attribute_names": sorted(vars(model)),
                            "model_config": model.config,
                        }
                    )
                heads.append(
                    {
                        "regime_id": regime_id,
                        "attribute_names": sorted(vars(head)),
                        "context_feature_dim": head.context_feature_dim,
                        "location_embedding_dim": head.location_embedding_dim,
                        "model_version": head.model_version,
                        "forgetting_factor": head.forgetting_factor,
                        "ridge": head.ridge,
                        "prior_scale": head.prior_scale,
                        "models": models,
                    }
                )
            return {
                "attribute_names": sorted(vars(self._regimes)),
                "head_factory": _callable_runtime_state(self._regimes._head_factory),
                "heads": heads,
            }

        return content_sha256(
            {
                "runtime_configuration": {
                    "core_attribute_names": sorted(
                        name
                        for name in self.__dict__
                        if name
                        not in {
                            "_execution_contract_active",
                            "_execution_owner_thread_id",
                            "_execution_contract_phase",
                            "_execution_lock",
                        }
                    ),
                    "model_version": self.model_version,
                    "owner_key": self.owner_key,
                    "object_instance_id": self.object_instance_id,
                    "authorization_scope_id": self.authorization_scope_id,
                    "locations": self.locations,
                    "loop_config": self.loop_config,
                    "action_readout": self._action_readout,
                    "rgrc_gate_enabled": self._rgrc_gate_enabled,
                    "embeddings": sorted(
                        (str(location), embedding.tolist())
                        for location, embedding in self._embeddings.items()
                    ),
                    "event_engine": {
                        "type": _runtime_type_symbol(self._event_engine),
                        "engine_version": self._event_engine.engine_version,
                        "schema_version": self._event_engine.schema_version,
                    },
                    "message_passing": _message_passing_state_descriptor(self._message_passing),
                    "propensity_corrector": {
                        "type": _runtime_type_symbol(self._corrector),
                        "state": {
                            name: _auditable_attribute(value)
                            for name, value in vars(self._corrector).items()
                        },
                    },
                    "feedback_policy": {
                        "type": _runtime_type_symbol(self._feedback_policy),
                        "config": getattr(self._feedback_policy, "config", None),
                    },
                    "regime_bank": {
                        "type": _runtime_type_symbol(self._regimes),
                        "default_regime": self._regimes._default_regime,
                        "runtime_configuration": rls_runtime_configuration(),
                    },
                    "automatic_router": {
                        "type": _runtime_type_symbol(router),
                        "object_instance_id": router.object_instance_id,
                        "actor_id": router.actor_id,
                        "owner_actor_id": router.owner_actor_id,
                        "config": router.config,
                        "bocpd_type": _runtime_type_symbol(router.bocpd),
                        "bocpd_model_version": router.bocpd._model_version,
                        "bocpd_hazards": router.bocpd._hazards,
                        "bocpd_event_hazards": sorted(
                            (
                                tuple(sorted(cause.value for cause in causes)),
                                probability,
                            )
                            for causes, probability in router.bocpd._event_hazards.items()
                        ),
                        "bocpd_config": router.bocpd._config,
                        "bocpd_beam_width": router.bocpd._beam_width,
                        "bocpd_maximum_run_length": router.bocpd._maximum_run_length,
                        "bocpd_run_length_clock": router.bocpd._run_length_clock,
                        "bocpd_attribute_names": sorted(vars(router.bocpd)),
                        "bocpd_reset_matrix": {
                            cause.value: sorted(block.value for block in blocks)
                            for cause, blocks in sorted(
                                router.bocpd._reset_matrix._matrix.items(),
                                key=lambda item: item[0].value,
                            )
                        },
                        "ccrr_type": _runtime_type_symbol(router.ccrr),
                        "ccrr_model_config_hash": router.ccrr.model_config_hash,
                        "ccrr_attribute_names": sorted(vars(router.ccrr)),
                        "ccrr_actual_configuration": {
                            "change_threshold": router.ccrr.change_threshold,
                            "similarity_threshold": router.ccrr.similarity_threshold,
                            "attribution_margin": router.ccrr.attribution_margin,
                            "identity_switch_threshold": router.ccrr.identity_switch_threshold,
                            "default_regime_id": router.ccrr.default_regime_id,
                            "model_version": router.ccrr.model_version,
                            "allow_reactivation": router.ccrr.allow_reactivation,
                        },
                    },
                    "hybrid_loop": {
                        "type": _runtime_type_symbol(self._hybrid_loop),
                        "attribute_names": sorted(vars(self._hybrid_loop)),
                        "owner": self._hybrid_loop._owner,
                        "object": self._hybrid_loop._object,
                        "authorization_scope": self._hybrid_loop._auth,
                        "model_version": self._hybrid_loop._model_version,
                        "code_version": self._hybrid_loop._code_version,
                        "regime": self._hybrid_loop._regime,
                        "parameter_block": self._hybrid_loop._block,
                        "coordinator": {
                            "type": _runtime_type_symbol(self._hybrid_loop._coordinator),
                            "soft_relevance_threshold": (
                                self._hybrid_loop._coordinator.soft_relevance_threshold
                            ),
                            "risk_increase_threshold": (
                                self._hybrid_loop._coordinator.risk_increase_threshold
                            ),
                            "maximum_allowed_risk": repr(
                                self._hybrid_loop._coordinator.maximum_allowed_risk
                            ),
                        },
                        "feedback_projector": {
                            "type": _runtime_type_symbol(self._hybrid_loop._feedback_projector),
                            "seen": sorted(
                                (str(key), value)
                                for key, value in (
                                    self._hybrid_loop._feedback_projector._seen.items()
                                )
                            ),
                        },
                        "fusion": {
                            "type": _runtime_type_symbol(self._hybrid_loop._fusion),
                            "probability_floor": (self._hybrid_loop._fusion.probability_floor),
                        },
                    },
                },
                "habit_state_sha256": self._habit.canonical_state_hash(),
                "habit_configuration": {
                    "attribute_names": sorted(vars(self._habit)),
                    "locations": self._habit._locations,
                    "common_prior": sorted(
                        (str(location), probability)
                        for location, probability in self._habit._common_prior.items()
                    ),
                    "common_prior_strength": self._habit._common_prior_strength,
                    "household_weight": self._habit._household_weight,
                    "person_weight": self._habit._person_weight,
                    "context_weight": self._habit._context_weight,
                    "resident_actor_keys": sorted(self._habit._resident_actor_keys or ()),
                    "actor_residual_weight": self._habit._actor_residual_weight,
                    "model_version": self._habit._model_version,
                    "count_tables": {
                        name: count_table_configuration(getattr(self._habit, name))
                        for name in (
                            "_household_counts",
                            "_person_counts",
                            "_context_counts",
                            "_isolated_nonresident_counts",
                        )
                    },
                },
                "rls_regimes": {
                    regime_id: self._regimes.regime_snapshot(regime_id)
                    for regime_id in sorted(self._regimes._heads)
                },
                "rls_active_regime": sorted(
                    (str(key), value) for key, value in self._regimes._active_regime.items()
                ),
                "rls_last_switch": sorted(
                    (str(key), value) for key, value in self._regimes._last_switch_time.items()
                ),
                "rls_processed_switch_event_ids": sorted(
                    (str(key), sorted(str(item) for item in value))
                    for key, value in self._regimes._processed_switch_event_ids.items()
                ),
                "rls_processed_switch_signatures": sorted(
                    (str(key), sorted(value))
                    for key, value in self._regimes._processed_switch_signatures.items()
                ),
                "hybrid_ledger_sha256": content_sha256(self._hybrid_loop.ledger.export_state()),
                "belief_snapshot": self.current_snapshot,
                "active_regime": self.active_regime,
                "observation_count": self.observation_count,
                "last_cause_snapshot": self._last_cause_snapshot,
                "automatic_router": {
                    "last_observation_time": router._last_observation_time,
                    "pending": repr(router._pending),
                    "seeded": router._seeded,
                    "bocpd_online_beam": repr(router.bocpd._online_beam),
                    "bocpd_last_timestamp": router.bocpd._online_last_timestamp,
                    "bocpd_last_opportunity_index": router.bocpd._online_last_opportunity_index,
                    "ccrr_view": router.ccrr.view(
                        object_instance_id=self.object_instance_id,
                        actor_id=self.owner_key,
                    ),
                    "ccrr_library": repr(router.ccrr._library),
                    "ccrr_current_regime": sorted(router.ccrr._current_regime.items()),
                    "ccrr_stream_versions": sorted(router.ccrr._stream_versions.items()),
                    "ccrr_version": router.ccrr._version,
                    "ccrr_pending_tokens": sorted(router.ccrr._pending_tokens.items()),
                },
                "committed_events": event_rows(self._committed_events),
                "write_eligibility": self._write_eligibility,
                "revision_transactions": self._revision_transactions,
                "hybrid_reinstatement_lineage": dict(self._hybrid_reinstatement_lineage),
                "correction_cancellations": native_content_payload(self._correction_cancellations),
                "deferred_correction_restore": native_content_payload(
                    self._deferred_correction_restore
                ),
                "revision_parent_events": event_rows(self._revision_parent_events),
                "prepared_particle_workspace": self._particle_workspace.state_payload(),
                "event_histories": self._event_histories,
                "observed_events": event_rows(self._observed_events),
                "fast_action_events": event_rows(self._fast_action_events),
                "fast_action_verification_receipts": self._fast_action_verification_receipts,
                "quarantined_events": sorted(
                    (str(item.revision_id), repr(item)) for item in self._quarantined_events
                ),
                "derived_event_archive": event_rows(self._derived_event_archive),
                "derived_event_lifecycle": sorted(
                    (str(key), value.value) for key, value in self._derived_event_lifecycle.items()
                ),
                "revision_feedback_bindings": sorted(
                    (str(key), tuple(str(item) for item in value))
                    for key, value in self._revision_feedback_bindings.items()
                ),
                "deferred_project_one_requests": sorted(
                    (key, repr(value)) for key, value in self._deferred_project_one_requests.items()
                ),
                "project_one_application_receipts": sorted(
                    (str(key), tuple(repr(item) for item in value))
                    for key, value in self._project_one_application_receipts.items()
                ),
                "project_one_application_receipts_storage_type": _runtime_type_symbol(
                    self._project_one_application_receipts
                ),
                "action_scoped_negatives": sorted(
                    (key, (str(value[0]), value[1]))
                    for key, value in self._action_scoped_negatives.items()
                ),
                "last_observed_location": self._last_observed_location,
                "last_context_key": self._last_context_key,
                "last_context_value": self._last_context_value,
                "last_household_id": self._last_household_id,
                "switch_sequence": self._switch_sequence,
                "last_ccrr_decision": self._last_ccrr_decision,
            }
        )

    def semantic_memory_identity(self) -> Mapping[str, str]:
        """Expose a semantic digest alongside the unchanged execution binding."""
        from cpswm.system.structure_two_semantic_identity import semantic_memory_identity

        with self._execution_lock:
            return semantic_memory_identity(self)

    @_serialized_core_mutation
    def stage_prepared_particle_candidates(
        self,
        *,
        receipts: tuple[ParticleRevisionReceipt, ...],
        statistics: dict[UUID, ConditionalAnalyticState],
        unresolved_log_weight: float,
    ) -> ParticleRevisionBatch:
        """Consume explicit prepared candidates against this runtime's real evidence.

        This native engineering seam does not generate neural proposals, certify
        caller probabilities/conditional models, commit statistics or replace the
        default CIAV/action policy. Those scientific/assembly bindings stay open.
        """
        if self._production_operator_contract is not None:
            self._production_operator_contract()
        chains = {}
        self._check_particle_workspace_binding()
        frames = {}
        for receipt in receipts:
            rid = receipt.proposal.proposed_state.revision_id
            history = self._event_histories.get(rid)
            event = self._observed_events.get(rid)
            if history is None or event is None:
                raise ValueError("prepared particle has no live production evidence history")
            if receipt.proposal.proposed_state.event_hypothesis_id not in {
                h.hypothesis_id for h in history.latest.hypotheses
            }:
                raise ValueError("candidate chain belongs to another revision")
            chains.update({h.hypothesis_id: h for h in history.latest.hypotheses})
            frames[rid] = (
                history,
                event.evidence,
                event.propensity_weight,
                event.regime_frame,
                event.identity_switch_probability,
            )
        checkpoint = self._capture_revision_transaction(include_operator_state=True)
        try:
            projections = {}
            for receipt in receipts:
                if receipt.evidence_semantics == "posterior_projection_not_likelihood":
                    source_id = receipt.source_posterior_snapshot_id
                    source = (
                        self._particle_workspace.posterior_sources.get(source_id)
                        if source_id is not None
                        else None
                    )
                    if source is None:
                        raise ValueError(
                            "posterior projection consumption is not bound in native runtime"
                        )
                    self._validate_native_posterior_source(source)
                    if (
                        receipt.proposal.proposed_state.revision_id
                        != source.history_after.latest.revision_id
                    ):
                        raise ValueError("posterior projection belongs to another event revision")
                    projections[receipt.proposal.proposed_state.particle_id] = source
            return self._particle_workspace.advance(
                receipts=receipts,
                statistics=statistics,
                chains=chains,
                snapshot_id=self.current_snapshot.snapshot_id,
                allowed_locations=self.locations,
                source_frame=(frames, self.current_cause_snapshot),
                ledger_head_sha256=self._hybrid_loop.ledger.export_state().manifest.head_hash,
                unresolved_log_weight=unresolved_log_weight,
                validated_projections=projections,
            )
        except BaseException:
            self._restore_revision_transaction(checkpoint)
            raise

    def current_posterior_projection_source(self) -> NativePosteriorSource:
        """Inspect the actual current producer output; this call creates no authority."""
        with self._execution_lock:
            self._check_particle_workspace_binding()
            sources = tuple(self._particle_workspace.posterior_sources.values())
            if not sources:
                raise ValueError("no production posterior source")
            source = sources[-1]
            self._validate_native_posterior_source(source)
            return deepcopy(source)

    def _validate_native_posterior_source(self, source: NativePosteriorSource) -> None:
        source.validate_content()
        revision = source.history_after.latest.revision_id
        event = self._observed_events.get(revision)
        if (
            source.runtime_id != self._particle_workspace.runtime_id
            or source.object_instance_id != self.object_instance_id
            or source.locations != self.locations
            or source.snapshot_id != self.current_snapshot.snapshot_id
            or event is None
            or content_sha256(self._event_histories.get(revision))
            != content_sha256(source.history_after)
            or source.transition.after.metadata.record_id != event.source_record_id
            or source.transition.after.detected_location_id != event.location_id
            or source.producer_context[0].applied_weight != event.propensity_weight
            # Cause sets are frozenset mapping keys. Generic repr hashing is
            # order-sensitive across deepcopy/hash seeds; exact typed equality
            # compares every set, posterior value and reference instead. The
            # complete stored source body hash is still verified above.
            or source.producer_context[1].snapshot != self.current_cause_snapshot
        ):
            raise ValueError("posterior source is stale, revoked, or outside runtime dependencies")
        # Verify the full producer chain against runtime-owned history and actual
        # inputs. A resealed receipt or current UUID alone cannot satisfy this.
        branch = self._event_engine.branch(
            before=source.transition.before,
            after=source.transition.after,
            actor_prior=dict(source.transition.actor_prior),
            unresolved_probability=source.transition.unresolved_probability,
            allow_unknown_handoff_roles=True,
        )
        if content_sha256(branch) != content_sha256(source.history_before):
            raise ValueError("posterior source has a false ORRER parent")
        posterior = self._message_passing.infer(branch, source.transition.evidence)
        if content_sha256(posterior) != content_sha256(source.posterior):
            raise ValueError("posterior source does not match its evidence computation")

    def prepared_particle_location_marginal(self) -> tuple[dict[UUID, float], float]:
        """Read the explicit candidate posterior, keeping unknown mass separate."""
        with self._execution_lock:
            self._check_particle_workspace_binding()
            batch = self._particle_workspace.batch
            if batch is None or batch.snapshot_id != self.current_snapshot.snapshot_id:
                raise ValueError("prepared particle source snapshot is stale or missing")
            return self._particle_workspace.location_marginal()

    def _check_particle_workspace_binding(self) -> None:
        if (
            self._particle_workspace is not self._particle_workspace_anchor
            or type(self._particle_workspace) is not NativeParticleWorkspace
        ):
            raise ValueError("native particle workspace identity was replaced")
        for slot, method in enumerate(
            ("advance", "location_marginal", "invalidate_revisions", "publish_posterior"), start=2
        ):
            bind_runtime_callable(
                runtime_execution_id=self.authorization_scope_id,
                operator="orrer_cheh",
                binding_slot=slot,
                binding_kind="direct_operator_callable",
                instance=self._particle_workspace,
                callable_name=method,
                require_declared_member=True,
            )

    def _process_transition(
        self,
        transition: PrototypeTransition,
        *,
        trace_recorder: _TransitionTraceRecorder | None = None,
        trace_phase: TracePhaseName | None = None,
        force_long_term_write_blocked: bool = False,
        identity_switch_probability: float | None = None,
    ) -> PrototypeStepResult:
        self._validate_transition(transition)
        identity_switch_probability = (
            transition.identity_switch_probability
            if identity_switch_probability is None
            else identity_switch_probability
        )
        _require_probability(identity_switch_probability, "identity_switch_probability")
        started_ns = perf_counter_ns()
        propensity = self._corrector.weight_for_opportunity(transition.opportunity)
        if trace_recorder is not None:
            trace_recorder.record_executed(
                "opceu",
                raw_input=transition.opportunity,
                output=propensity,
                phase=trace_phase,
                elapsed_ns=perf_counter_ns() - started_ns,
            )
        started_ns = perf_counter_ns()
        history = self._event_engine.branch(
            before=transition.before,
            after=transition.after,
            actor_prior=dict(transition.actor_prior),
            unresolved_probability=transition.unresolved_probability,
            allow_unknown_handoff_roles=True,
        )
        if trace_recorder is not None:
            trace_recorder.record_executed(
                "orrer_cheh",
                raw_input={
                    "before": transition.before,
                    "after": transition.after,
                    "actor_prior": dict(transition.actor_prior),
                    "unresolved_probability": transition.unresolved_probability,
                    "allow_unknown_handoff_roles": True,
                },
                output=history,
                phase=trace_phase,
                elapsed_ns=perf_counter_ns() - started_ns,
            )
        started_ns = perf_counter_ns()
        event_posterior, receipted_history = self._message_passing.consume(
            history, transition.evidence
        )
        if (
            trace_recorder is not None
            and transition.evidence
            and trace_recorder.mode_for("pchmp", phase=trace_phase) == "refinement_executed"
        ):
            audit = getattr(self._message_passing, "audit_leave_one_cluster_out", None)
            if callable(audit):
                audit(history, transition.evidence)
        actor_posterior = self._actor_posterior(receipted_history, event_posterior)
        self._event_histories[receipted_history.latest.revision_id] = deepcopy(receipted_history)
        if trace_recorder is not None:
            trace_recorder.record_executed(
                "pchmp",
                raw_input={"event_history": history, "evidence": transition.evidence},
                output=(event_posterior, receipted_history),
                consumes=("orrer_cheh",),
                phase=trace_phase,
                elapsed_ns=perf_counter_ns() - started_ns,
            )

        assert transition.after.detected_location_id is not None
        assert transition.after.detection_time is not None
        location_id = transition.after.detected_location_id
        evidence = HabitLearningEvidence(
            metadata=transition.after.metadata.model_copy(
                update={
                    "record_id": uuid4(),
                    "schema_name": "cpswm.HabitLearningEvidence",
                    "source_type": SourceType.INFERENCE,
                    "source_id": "prototype-spine.pchmp",
                    "model_version": self.model_version,
                }
            ),
            object_instance_id=self.object_instance_id,
            location_id=location_id,
            event_time=transition.after.detection_time,
            context_key=transition.context_key,
            actor_posterior=dict(actor_posterior),
            evidence_source=HabitEvidenceSource.INFERRED_EVENT,
            source_record_ids=(
                transition.before.metadata.record_id,
                transition.after.metadata.record_id,
                *(item.metadata.record_id for item in transition.evidence),
            ),
            observation_opportunity_id=transition.opportunity.metadata.record_id,
        )
        owner_mass = actor_posterior.get(self.owner_key, 0.0)
        location_index = self.locations.index(location_id)
        habit_transition = float(
            self._last_observed_location is not None and location_id != self._last_observed_location
        )
        observation_ambiguity = 1.0 - (
            transition.opportunity.p_visible_given_state
            * transition.opportunity.p_detect_given_visible
        )
        prior_habit = self._habit.predict(
            household_id=transition.after.metadata.household_id,
            person_id=self.owner_key,
            object_instance_id=self.object_instance_id,
            context_key=transition.context_key,
        )
        prior_rls = self._regimes.score_candidates(
            object_instance_id=self.object_instance_id,
            actor_id=self.owner_key,
            context_features=np.array([transition.context_value], dtype=float),
            candidate_locations=self.locations,
            location_embeddings=self._embeddings,
            regime_id=self.active_regime,
        )
        dirichlet_predictive_surprise = _normalized_predictive_surprise(
            prior_habit.probabilities[location_id],
            len(self.locations),
        )
        rls_residual = min(1.0, abs(1.0 - prior_rls[location_id]))
        residual_severity = 1.0 - (1.0 - rls_residual) ** 2
        unexpected_move = habit_transition * (
            1.0 - (1.0 - dirichlet_predictive_surprise) * (1.0 - residual_severity)
        )
        habit_signal = max(
            unexpected_move,
            self.loop_config.dirichlet_surprise_weight * dirichlet_predictive_surprise,
            self.loop_config.rls_residual_weight * rls_residual,
        )
        regime_frame = CauseSignalFrame(
            timestamp=transition.after.detection_time,
            signals={
                ChangeCause.OBSERVATION: observation_ambiguity,
                ChangeCause.ACTOR: 1.0 - owner_mass,
                ChangeCause.HABIT: habit_signal,
                ChangeCause.NOISE: max(
                    observation_ambiguity, event_posterior.unresolved_probability
                ),
            },
        )

        regime_observe_started_ns = 0
        cf_finished_ns = 0

        def observe_regime_stage(stage: RegimeStage, payload: object) -> None:
            nonlocal cf_finished_ns
            if trace_recorder is None:
                return
            if stage is RegimeStage.CF_BOCPD_SNAPSHOT:
                cf_finished_ns = perf_counter_ns()
                trace_recorder.record_executed(
                    "cf_bocpd",
                    raw_input=regime_frame,
                    output=payload,
                    consumes=("pchmp",),
                    phase=trace_phase,
                    elapsed_ns=cf_finished_ns - regime_observe_started_ns,
                )
                return
            if stage is RegimeStage.CCRR_ASSESSMENT:
                # The complete router invocation is receipted immediately
                # after ``observe`` returns, so its input/output hashes match
                # the actual composite stage boundary.
                return
            raise RuntimeError(f"unknown automatic regime trace stage: {stage}")

        regime_context_features = (
            *(1.0 if index == location_index else 0.0 for index in range(len(self.locations))),
            tanh(transition.context_value),
        )
        regime_observe_started_ns = perf_counter_ns()
        assessment = self._automatic_regimes.observe(
            frame=regime_frame,
            state_key=f"{location_id}|{transition.context_key}",
            context_features=regime_context_features,
            owner_probability=owner_mass,
            evidence_source_record_ids=evidence.source_record_ids,
            identity_switch_probability=identity_switch_probability,
            stage_observer=observe_regime_stage if trace_recorder is not None else None,
        )
        if trace_recorder is not None:
            trace_recorder.record_executed(
                "ccrr",
                raw_input={
                    "frame": regime_frame,
                    "state_key": f"{location_id}|{transition.context_key}",
                    "context_features": regime_context_features,
                    "owner_probability": owner_mass,
                    "evidence_source_record_ids": evidence.source_record_ids,
                    "identity_switch_probability": identity_switch_probability,
                },
                output=assessment,
                consumes=("pchmp", "cf_bocpd"),
                phase=trace_phase,
                elapsed_ns=perf_counter_ns() - (cf_finished_ns or regime_observe_started_ns),
            )
        started_ns = perf_counter_ns()
        self._last_cause_snapshot = assessment.snapshot
        if assessment.new_regime != self.active_regime:
            self.switch_regime(assessment.new_regime, event_time=transition.after.detection_time)
        self._last_ccrr_decision = (
            assessment.ccrr_decision.kind.value
            if assessment.ccrr_decision is not None
            else (
                "deferred"
                if assessment.conclusion is HabitStateConclusion.INSUFFICIENT_EVIDENCE
                else "stay"
            )
        )
        self._last_observed_location = location_id

        regime = self.active_regime
        rls_sample = RLSHabitSample(
            object_instance_id=self.object_instance_id,
            actor_id=self.owner_key,
            context_features=np.array([transition.context_value], dtype=float),
            target_location_id=location_id,
            candidate_locations=self.locations,
            gate=(owner_mass * propensity.applied_weight),
            forgetting_factor=self.loop_config.forgetting_factor,
            regime_id=regime,
        )
        current_event = _CommittedPrototypeEvent(
            event_hypothesis_id=receipted_history.hypothesis_set_id,
            revision_id=receipted_history.latest.revision_id,
            evidence=evidence,
            propensity_weight=propensity.applied_weight,
            rls_sample=rls_sample,
            owner_mass=owner_mass,
            statistical_owner_weight=(owner_mass * propensity.applied_weight),
            source_record_id=transition.after.metadata.record_id,
            location_id=location_id,
            dirichlet_predictive_surprise=dirichlet_predictive_surprise,
            rls_residual=rls_residual,
            regime_frame=regime_frame,
            identity_switch_probability=identity_switch_probability,
        )
        self._observed_events[current_event.revision_id] = current_event
        self._fast_action_events[current_event.revision_id] = current_event
        # Record the origin write eligibility before any classification.  An
        # administratively blocked write is a different fact from CCRR deferring
        # for want of evidence, and only the runtime knows which one happened.
        self._record_observation_origin(
            current_event,
            write_blocked=force_long_term_write_blocked,
            origin_path=(
                "write_blocked_primary_pass"
                if force_long_term_write_blocked
                else "unblocked_transition"
            ),
        )

        cancellation_count = len(self._correction_cancellations)
        promoted_audits: dict[UUID, HabitUpdateAudit] = {}
        if force_long_term_write_blocked:
            self._quarantined_events.append(current_event)
            self._record_quarantine_reason(
                current_event.revision_id, "long_term_write_administratively_blocked"
            )
        elif assessment.conclusion is HabitStateConclusion.HABIT_CHANGE:
            for quarantined in self._quarantined_events:
                promoted = replace(
                    quarantined,
                    rls_sample=replace(quarantined.rls_sample, regime_id=regime),
                )
                # A delayed feedback replay can reclassify a quarantined event
                # into the committed store before the next online confirmation
                # closes the old quarantine window.  Promotion is exactly-once:
                # never apply its sufficient statistics a second time.
                if promoted.revision_id in self._committed_events:
                    continue
                # This branch only runs when the write was *not* blocked, so this
                # execution is permitted to grant eligibility.  The grant is
                # recorded before the commit, with the CCRR basis it rests on.
                self._grant_write_authorization(
                    promoted.revision_id,
                    authority="ccrr_habit_change_promotion",
                    granting_revision_id=current_event.revision_id,
                    basis={
                        "conclusion": assessment.conclusion.value,
                        "regime": regime,
                        "ccrr_decision": self._last_ccrr_decision,
                        "granting_source_record_ids": tuple(
                            str(item) for item in evidence.source_record_ids
                        ),
                    },
                )
                promoted_audits[promoted.revision_id] = self._commit_event(promoted)
            self._quarantined_events.clear()
        elif assessment.conclusion is HabitStateConclusion.SHORT_TERM_DISTURBANCE:
            self._reject_deferred_project_one_requests(
                {item.revision_id for item in self._quarantined_events},
                rationale="CCRR classified the quarantined event as a short-term disturbance",
                trigger_revision_id=current_event.revision_id,
            )
            self._quarantined_events.clear()
        elif (
            assessment.conclusion is HabitStateConclusion.INSUFFICIENT_EVIDENCE
            and not assessment.allow_long_term_write
        ):
            if assessment.ccrr_decision is None:
                self._quarantined_events.append(current_event)
                self._record_quarantine_reason(
                    current_event.revision_id, "ccrr_insufficient_evidence_deferred"
                )
            else:
                self._reject_deferred_project_one_requests(
                    {item.revision_id for item in self._quarantined_events},
                    rationale="CCRR closed quarantine without promoting the corrected event",
                    trigger_revision_id=current_event.revision_id,
                )
                self._quarantined_events.clear()

        if (
            assessment.allow_long_term_write or not self._rgrc_gate_enabled
        ) and not force_long_term_write_blocked:
            if current_event.revision_id in self._committed_events:
                habit_update = promoted_audits.get(current_event.revision_id)
                if habit_update is None:
                    habit_update = self._habit.update_audited(evidence, weight_multiplier=0.0)
            else:
                self._grant_write_authorization(
                    current_event.revision_id,
                    authority="unblocked_transition_commit",
                    granting_revision_id=current_event.revision_id,
                    basis={
                        "conclusion": assessment.conclusion.value,
                        "allow_long_term_write": assessment.allow_long_term_write,
                        "rgrc_gate_enabled": self._rgrc_gate_enabled,
                        "regime": regime,
                    },
                )
                habit_update = self._commit_event(current_event)
        else:
            habit_update = self._habit.update_audited(evidence, weight_multiplier=0.0)
        if len(self._correction_cancellations) != cancellation_count:
            replay_assessments: list[Any] = []
            restored_snapshot = self._rebuild_personalized_models(
                replay_assessments=replay_assessments
            )
            # Reverse only the descendants captured by the original request.
            # Later observations are retained and decide whether the parent is
            # live; cancellation creates no fresh-feedback/CCRR authority.
            for cancellation in self._correction_cancellations[cancellation_count:]:
                remaining = {e.revision_id: e for e in cancellation.restore_events[1:]}
                while remaining:
                    ready = [
                        e
                        for e in remaining.values()
                        if e.derived_from_revision_id in self._committed_events
                    ]
                    if not ready:
                        for rid in remaining:
                            self._derived_event_lifecycle[rid] = (
                                DerivedEvidenceLifecycle.SUSPENDED_PARENT_QUARANTINED
                            )
                        break
                    for event in ready:
                        self._commit_event(replace(event, belief_snapshot_id=None))
                        remaining.pop(event.revision_id)
            restored_snapshot = self._hybrid_loop.publish_snapshot()
            assessment = replay_assessments[-1]
            self._last_cause_snapshot = assessment.snapshot
            regime = self.active_regime
            for cancellation in self._correction_cancellations[cancellation_count:]:
                rows = self._project_one_application_receipts[
                    cancellation.request.source_feedback_record_id
                ]
                rows[-1] = rows[-1].model_copy(
                    update={"new_belief_snapshot_id": restored_snapshot.snapshot_id}
                )
            self._revision_fault_hook("cancellation_replay")
        rls_scores = self._regimes.score_candidates(
            object_instance_id=self.object_instance_id,
            actor_id=self.owner_key,
            context_features=np.array([transition.context_value], dtype=float),
            candidate_locations=self.locations,
            location_embeddings=self._embeddings,
            regime_id=regime,
        )

        belief_snapshot = self._hybrid_loop.publish_snapshot()
        for revision_id, event in tuple(self._committed_events.items()):
            if event.belief_snapshot_id is None:
                self._committed_events[revision_id] = replace(
                    event,
                    belief_snapshot_id=belief_snapshot.snapshot_id,
                )
                self._publish_revision_binding(
                    revision_id,
                    location_id=event.location_id,
                    snapshot=belief_snapshot,
                )
        habit_prediction = self._habit.predict(
            household_id=transition.after.metadata.household_id,
            person_id=self.owner_key,
            object_instance_id=self.object_instance_id,
            context_key=transition.context_key,
        )
        suggested = max(
            self.locations,
            key=lambda location: (
                habit_prediction.probabilities[location],
                rls_scores[location],
                str(location),
            ),
        )
        self._last_context_key = transition.context_key
        self._last_context_value = transition.context_value
        self._last_household_id = transition.after.metadata.household_id
        ccrr_conclusion = (
            assessment.ccrr_decision.kind.value
            if assessment.ccrr_decision is not None
            else (
                "deferred"
                if assessment.conclusion is HabitStateConclusion.INSUFFICIENT_EVIDENCE
                else (
                    "reject_short_term_disturbance"
                    if assessment.conclusion is HabitStateConclusion.SHORT_TERM_DISTURBANCE
                    else "not_required"
                )
            )
        )
        decision = PrototypeDecisionRecord(
            old_regime=assessment.old_regime,
            new_regime=assessment.new_regime,
            change_probability=assessment.change_probability,
            ccrr_conclusion=ccrr_conclusion,
            conclusion=assessment.conclusion,
            evidence_source_record_ids=assessment.evidence_source_record_ids,
            statistic_operations=assessment.statistic_operations,
            map_version=belief_snapshot.map_version,
            snapshot_id=belief_snapshot.snapshot_id,
            rationale=assessment.rationale,
        )
        result = PrototypeStepResult(
            propensity=propensity,
            event_history=receipted_history,
            event_posterior=event_posterior,
            actor_posterior=actor_posterior,
            habit_update=habit_update,
            habit_prediction=habit_prediction,
            active_regime=regime,
            rls_scores=rls_scores,
            belief_snapshot=belief_snapshot,
            suggested_location_id=suggested,
            event_revision_id=receipted_history.latest.revision_id,
            decision=decision,
        )
        self._particle_workspace.publish_posterior(
            object_instance_id=self.object_instance_id,
            snapshot_id=belief_snapshot.snapshot_id,
            locations=self.locations,
            history_before=history,
            history_after=receipted_history,
            posterior=event_posterior,
            transition=transition,
            producer_context=(propensity, assessment),
        )
        if trace_recorder is not None:
            trace_recorder.record_executed(
                "rgrc",
                raw_input=transition,
                output=result,
                consumes=("opceu", "pchmp", "ccrr"),
                phase=trace_phase,
                elapsed_ns=perf_counter_ns() - started_ns,
            )
        return result

    def _commit_event(self, event: _CommittedPrototypeEvent) -> HabitUpdateAudit:
        """Promote one accepted/quarantined event into all three model stores."""

        if event.revision_id in self._committed_events:
            raise ValueError("prototype event revision is already committed")
        if event.regime_frame is not None and not self._observation_write_eligible(
            event.revision_id
        ):
            raise ValueError("observation commit requires valid write eligibility")
        audit = self._habit.update_audited(
            event.evidence,
            weight_multiplier=event.propensity_weight,
        )
        self._regimes.update(event.rls_sample, self._embeddings)
        self._transition_fault_hook("rls")
        event = self._ingest_event_hybrid(event)
        self._transition_fault_hook("hybrid")
        self._committed_events[event.revision_id] = event
        if event.derived_from_revision_id is not None:
            self._derived_event_archive[event.revision_id] = event
            self._derived_event_lifecycle[event.revision_id] = DerivedEvidenceLifecycle.ACTIVE
        if event.regime_frame is not None:
            self._observed_events[event.revision_id] = event
        if (
            self.loop_config.derived_reactivation_policy
            is DerivedEvidenceReactivationPolicy.RESTORE_PRIOR_DERIVED
        ):
            archived_children = sorted(
                (
                    archived
                    for archived in self._derived_event_archive.values()
                    if archived.derived_from_revision_id == event.revision_id
                    and archived.revision_id not in self._committed_events
                    and self._derived_event_lifecycle.get(archived.revision_id)
                    is DerivedEvidenceLifecycle.SUSPENDED_PARENT_QUARANTINED
                ),
                key=lambda item: (item.evidence.event_time, str(item.revision_id)),
            )
            for archived in archived_children:
                self._commit_event(replace(archived, belief_snapshot_id=None))
        self.retry_deferred_project_one_requests(event.revision_id)
        return audit

    def _ingest_event_hybrid(self, event: _CommittedPrototypeEvent) -> _CommittedPrototypeEvent:
        if event.statistical_owner_weight <= 1e-12:
            return event
        hybrid_revision_id = event.hybrid_revision_id or event.revision_id
        parent_revision_id = event.hybrid_parent_revision_id
        ledger = self._hybrid_loop.ledger
        if hybrid_revision_id in ledger._revision_event:
            if ledger.live_promoted_records_for_revision(hybrid_revision_id):
                return event
            parent_revision_id = hybrid_revision_id
            hybrid_revision_id = uuid4()
        self._hybrid_loop.ingest_owner_placement(
            OwnerPlacementInput(
                event_hypothesis_id=event.event_hypothesis_id,
                revision_id=hybrid_revision_id,
                parent_revision_id=parent_revision_id,
                destination_location_id=event.location_id,
                owner_mass=event.statistical_owner_weight,
                source_record_id=event.source_record_id,
            )
        )
        if hybrid_revision_id != event.revision_id:
            self._hybrid_reinstatement_lineage[hybrid_revision_id] = (
                event.revision_id,
                parent_revision_id,
            )
        return replace(
            event,
            hybrid_revision_id=hybrid_revision_id,
            hybrid_parent_revision_id=parent_revision_id,
        )

    def _retract_event_hybrid(self, event: _CommittedPrototypeEvent) -> None:
        self._hybrid_loop.retract_revision(event.hybrid_revision_id or event.revision_id)

    def _transition_fault_hook(self, stage: str) -> None:
        """No-op fault-injection seam for ordinary-transition rollback tests."""

    @_serialized_core_mutation
    def apply_event_revision_outcome(
        self, outcome: EventRevisionOutcome
    ) -> PrototypeRevisionResult:
        """Apply one all-or-nothing revision across Hybrid, Dirichlet, and RLS."""

        if self._production_operator_contract is not None:
            self._production_operator_contract()
        checkpoint = self._capture_revision_transaction(include_operator_state=True)
        try:
            result = self._apply_event_revision_outcome(outcome)
            if (
                outcome.kind is EventRevisionKind.CORRECT
                and outcome.corrected_revision_id not in self._committed_events
            ):
                raise ValueError("CORRECT not admitted by CCRR; transaction rolled back")
            return result
        except BaseException:
            self._restore_revision_transaction(checkpoint)
            raise

    def _apply_event_revision_outcome(
        self, outcome: EventRevisionOutcome
    ) -> PrototypeRevisionResult:
        """Apply project-two retract/correct via existing reversible components."""

        original = self._committed_events.get(outcome.superseded_revision_id)
        if original is None:
            raise KeyError("superseded revision is not a committed prototype event")
        if outcome.kind is EventRevisionKind.CORRECT:
            if outcome.corrected_revision_id in self._write_eligibility or (
                outcome.corrected_revision_id in self._committed_events
            ):
                raise ValueError("corrected revision identity has already been used")
            if outcome.corrected_location_id not in self.locations:
                raise ValueError("corrected location is outside the prototype candidate set")
            if original.regime_frame is not None and not self._observation_write_eligible(
                original.revision_id
            ):
                raise ValueError("correction parent has no valid write eligibility")
        self._revision_parent_events.setdefault(original.revision_id, original)
        self._particle_workspace.invalidate_revisions({original.revision_id})
        old_regime = self.active_regime
        dependent_revision_ids = self._descendant_revision_ids(outcome.superseded_revision_id)
        if outcome.kind is EventRevisionKind.RETRACT:
            if original.derived_from_revision_id is not None:
                self._derived_event_lifecycle[outcome.superseded_revision_id] = (
                    DerivedEvidenceLifecycle.TOMBSTONED_EXPLICIT_RETRACT
                )
            for revision_id in dependent_revision_ids:
                self._derived_event_lifecycle[revision_id] = (
                    DerivedEvidenceLifecycle.TOMBSTONED_ANCESTOR_INVALIDATED
                )
            for revision_id in (
                outcome.superseded_revision_id,
                *dependent_revision_ids,
            ):
                self._retract_event_hybrid(self._committed_events[revision_id])
                del self._committed_events[revision_id]
                self._observed_events.pop(revision_id, None)
                self._fast_action_events.pop(revision_id, None)
            snapshot = self._hybrid_loop.publish_snapshot()
            operations = (PrototypeStatisticOperation.RETRACT,)
        else:
            assert outcome.corrected_revision_id is not None
            assert outcome.corrected_location_id is not None
            assert outcome.corrected_owner_mass is not None
            if original.derived_from_revision_id is not None:
                self._derived_event_lifecycle[outcome.superseded_revision_id] = (
                    DerivedEvidenceLifecycle.TOMBSTONED_CORRECTED
                )
            for revision_id in dependent_revision_ids:
                self._derived_event_lifecycle[revision_id] = (
                    DerivedEvidenceLifecycle.TOMBSTONED_ANCESTOR_INVALIDATED
                )
            corrected_statistical_weight = (
                outcome.corrected_owner_mass
                * original.evidence.effective_training_weight
                * original.propensity_weight
            )
            original_hybrid_revision_id = original.hybrid_revision_id or original.revision_id
            hybrid_parent_revision_id = (
                original_hybrid_revision_id
                if original.statistical_owner_weight > 1e-12
                else original.hybrid_parent_revision_id
            )
            corrected_placement = OwnerPlacementInput(
                event_hypothesis_id=original.event_hypothesis_id,
                revision_id=outcome.corrected_revision_id,
                parent_revision_id=hybrid_parent_revision_id,
                destination_location_id=outcome.corrected_location_id,
                owner_mass=corrected_statistical_weight,
                source_record_id=outcome.evidence_source_record_ids[0],
            )
            if original.statistical_owner_weight <= 1e-12:
                self._hybrid_loop.ingest_owner_placement(corrected_placement)
                snapshot = self._hybrid_loop.publish_snapshot()
            else:
                snapshot = self._hybrid_loop.apply_orrer_revision(
                    superseded_revision_id=original_hybrid_revision_id,
                    corrected=corrected_placement,
                )
            del self._committed_events[outcome.superseded_revision_id]
            corrected_actor_posterior = self._corrected_actor_posterior(
                original.evidence.actor_posterior,
                corrected_owner_mass=outcome.corrected_owner_mass,
            )
            corrected_evidence = original.evidence.model_copy(
                update={
                    "location_id": outcome.corrected_location_id,
                    "actor_posterior": corrected_actor_posterior,
                    "source_record_ids": tuple(
                        dict.fromkeys(
                            original.evidence.source_record_ids + outcome.evidence_source_record_ids
                        )
                    ),
                }
            )
            self._committed_events[outcome.corrected_revision_id] = replace(
                original,
                revision_id=outcome.corrected_revision_id,
                evidence=corrected_evidence,
                rls_sample=replace(
                    original.rls_sample,
                    target_location_id=outcome.corrected_location_id,
                    gate=corrected_statistical_weight,
                ),
                owner_mass=outcome.corrected_owner_mass,
                statistical_owner_weight=corrected_statistical_weight,
                source_record_id=outcome.evidence_source_record_ids[0],
                location_id=outcome.corrected_location_id,
                hybrid_revision_id=outcome.corrected_revision_id,
                hybrid_parent_revision_id=hybrid_parent_revision_id,
                belief_snapshot_id=None,
            )
            if original.regime_frame is not None:
                parent = self._write_eligibility[original.revision_id]
                # This is a replacement of an already accepted contribution,
                # with explicit evidence, not a new authority over quarantine.
                self._write_eligibility[outcome.corrected_revision_id] = (
                    _ObservationWriteEligibility(
                        revision_id=outcome.corrected_revision_id,
                        origin_write_blocked=True,
                        origin_path="formal_correction_transaction",
                        parent_revision_id=original.revision_id,
                        correction_evidence_source_record_ids=outcome.evidence_source_record_ids,
                        parent_eligibility_sha256=content_sha256(parent),
                        correction_outcome_sha256=content_sha256(outcome),
                        authorizations=(
                            _WriteAuthorization(
                                authority="formal_correction_transaction",
                                granting_revision_id=original.revision_id,
                                granted_at_observation_count=self.observation_count,
                                basis_sha256=content_sha256(outcome),
                            ),
                        ),
                    )
                )
            if original.derived_from_revision_id is not None:
                corrected_derived = self._committed_events[outcome.corrected_revision_id]
                self._derived_event_archive[outcome.corrected_revision_id] = corrected_derived
                self._derived_event_lifecycle[outcome.corrected_revision_id] = (
                    DerivedEvidenceLifecycle.ACTIVE
                )
            self._observed_events.pop(outcome.superseded_revision_id, None)
            if self._fast_action_events.pop(outcome.superseded_revision_id, None) is not None:
                self._fast_action_events[outcome.corrected_revision_id] = self._committed_events[
                    outcome.corrected_revision_id
                ]
            if original.regime_frame is not None:
                self._observed_events[outcome.corrected_revision_id] = self._committed_events[
                    outcome.corrected_revision_id
                ]
            for revision_id in dependent_revision_ids:
                self._retract_event_hybrid(self._committed_events[revision_id])
                del self._committed_events[revision_id]
                self._observed_events.pop(revision_id, None)
                self._fast_action_events.pop(revision_id, None)
            snapshot = self._hybrid_loop.publish_snapshot()
            corrected_event = self._committed_events[outcome.corrected_revision_id]
            self._committed_events[outcome.corrected_revision_id] = replace(
                corrected_event,
                belief_snapshot_id=snapshot.snapshot_id,
            )
            self._publish_revision_binding(
                outcome.corrected_revision_id,
                location_id=corrected_event.location_id,
                snapshot=snapshot,
            )
            operations = (PrototypeStatisticOperation.CORRECT,)
        self._revision_transactions = (*self._revision_transactions, outcome)
        snapshot = self._rebuild_personalized_models()
        return self._revision_result(
            operations=operations,
            evidence_source_record_ids=outcome.evidence_source_record_ids,
            snapshot=snapshot,
            old_regime=old_regime,
            rationale=outcome.rationale,
        )

    def _revision_fault_hook(self, stage: str) -> None:
        """No-op fault-injection seam used to verify transaction rollback."""

    def _capture_revision_transaction(
        self, *, include_operator_state: bool = False
    ) -> dict[str, object]:
        checkpoint: dict[str, object] = {
            "habit": deepcopy(self._habit),
            "regimes": deepcopy(self._regimes),
            "automatic_regimes": deepcopy(self._automatic_regimes),
            "corrector": deepcopy(self._corrector),
            "committed_events": dict(self._committed_events),
            "observed_events": dict(self._observed_events),
            "fast_action_events": dict(self._fast_action_events),
            "fast_action_verification_receipts": list(self._fast_action_verification_receipts),
            "derived_event_archive": dict(self._derived_event_archive),
            "derived_event_lifecycle": dict(self._derived_event_lifecycle),
            "feedback_bindings": dict(self._revision_feedback_bindings),
            "revision_binding_history": dict(self._revision_binding_history),
            "late_feedback_relocations": list(self._late_feedback_relocations),
            "write_eligibility": dict(self._write_eligibility),
            "revision_transactions": self._revision_transactions,
            "hybrid_reinstatement_lineage": dict(self._hybrid_reinstatement_lineage),
            "correction_cancellations": self._correction_cancellations,
            "deferred_correction_restore": dict(self._deferred_correction_restore),
            "revision_parent_events": dict(self._revision_parent_events),
            "particle_workspace": self._particle_workspace,
            "particle_workspace_state": deepcopy(self._particle_workspace),
            "event_histories": dict(self._event_histories),
            "production_operator_contract": self._production_operator_contract,
            "quarantined_events": list(self._quarantined_events),
            "last_observed_location": self._last_observed_location,
            "last_context_key": self._last_context_key,
            "last_context_value": self._last_context_value,
            "last_household_id": self._last_household_id,
            "switch_sequence": self._switch_sequence,
            "last_ccrr_decision": self._last_ccrr_decision,
            "last_cause_snapshot": self._last_cause_snapshot,
            "deferred_project_one_requests": dict(self._deferred_project_one_requests),
            "project_one_application_receipts": deepcopy(self._project_one_application_receipts),
            "action_scoped_negatives": dict(self._action_scoped_negatives),
            "hybrid_export": self._hybrid_loop.ledger.export_state(),
            "belief_snapshot": self.current_snapshot,
        }
        if include_operator_state:
            excluded = {
                "_execution_contract_active",
                "_execution_owner_thread_id",
                "_execution_contract_phase",
                "_execution_lock",
                "_external_mutation_guard",
                "_production_operator_contract",
                "_hybrid_loop",
            }
            runtime_refs = {
                name: value for name, value in self.__dict__.items() if name not in excluded
            }
            nested_component_refs: dict[str, object] = {
                "automatic_bocpd": self._automatic_regimes.bocpd,
                "bocpd_reset_matrix": self._automatic_regimes.bocpd._reset_matrix,
                "automatic_ccrr": self._automatic_regimes.ccrr,
                "regime_head_factory": self._regimes._head_factory,
                "hybrid_coordinator": self._hybrid_loop._coordinator,
                "hybrid_feedback_projector": self._hybrid_loop._feedback_projector,
                "hybrid_fusion": self._hybrid_loop._fusion,
            }
            nested_component_refs.update(_message_passing_nested_components(self._message_passing))
            checkpoint["execution_core_attribute_names"] = frozenset(self.__dict__)
            checkpoint["execution_lock"] = self._execution_lock
            checkpoint["execution_runtime_refs"] = runtime_refs
            # An instrumentation/fault hook may be bound to this very core.
            # Preserve that owner identity rather than recursively copying locks
            # and the enclosing production assembly through a bound method.
            checkpoint["execution_runtime_fields"] = deepcopy(runtime_refs, {id(self): self})
            checkpoint["execution_nested_component_refs"] = nested_component_refs
            checkpoint["execution_nested_component_snapshots"] = {
                name: deepcopy(component) for name, component in nested_component_refs.items()
            }
            habit_table_names = (
                "_household_counts",
                "_person_counts",
                "_context_counts",
                "_isolated_nonresident_counts",
            )
            habit_table_refs = {name: getattr(self._habit, name) for name in habit_table_names}
            checkpoint["execution_habit_table_refs"] = habit_table_refs
            checkpoint["execution_habit_table_snapshots"] = deepcopy(habit_table_refs)
            checkpoint["execution_habit_row_refs"] = {
                (name, key): row
                for name, table in habit_table_refs.items()
                for key, row in table.items()
            }
            checkpoint["execution_rls_heads_ref"] = self._regimes._heads
            checkpoint["execution_rls_head_refs"] = dict(self._regimes._heads)
            checkpoint["execution_rls_head_snapshots"] = deepcopy(self._regimes._heads)
            checkpoint["execution_rls_model_map_refs"] = {
                regime_id: head._models for regime_id, head in self._regimes._heads.items()
            }
            checkpoint["execution_rls_wrapper_refs"] = {
                (regime_id, key): wrapper
                for regime_id, head in self._regimes._heads.items()
                for key, wrapper in head._models.items()
            }
            checkpoint["execution_rls_core_refs"] = {
                compound_key: wrapper.model
                for compound_key, wrapper in cast(
                    dict[object, Any], checkpoint["execution_rls_wrapper_refs"]
                ).items()
            }
            checkpoint["execution_rls_config_refs"] = {
                compound_key: model.config
                for compound_key, model in cast(
                    dict[object, Any], checkpoint["execution_rls_core_refs"]
                ).items()
            }
            checkpoint["execution_rls_theta_refs"] = {
                compound_key: model.theta
                for compound_key, model in cast(
                    dict[object, Any], checkpoint["execution_rls_core_refs"]
                ).items()
            }
            checkpoint["execution_rls_covariance_refs"] = {
                compound_key: model.covariance
                for compound_key, model in cast(
                    dict[object, Any], checkpoint["execution_rls_core_refs"]
                ).items()
            }
            checkpoint["execution_project_receipt_table_ref"] = (
                self._project_one_application_receipts
            )
            checkpoint["execution_project_receipt_table_snapshot"] = deepcopy(
                self._project_one_application_receipts
            )
            checkpoint["execution_project_receipt_row_refs"] = dict(
                self._project_one_application_receipts
            )
            checkpoint["automatic_ccrr_lock"] = self._automatic_regimes.ccrr._lock
            checkpoint["hybrid_loop"] = self._hybrid_loop
            checkpoint["hybrid_ledger"] = self._hybrid_loop.ledger
            checkpoint["hybrid_ledger_lock"] = self._hybrid_loop.ledger._lock
            checkpoint["hybrid_map"] = self._hybrid_loop._map
            checkpoint["hybrid_map_lock"] = self._hybrid_loop._map._lock
            checkpoint["hybrid_loop_attribute_names"] = frozenset(vars(self._hybrid_loop))
            checkpoint["hybrid_loop_fields"] = deepcopy(
                {
                    name: value
                    for name, value in vars(self._hybrid_loop).items()
                    if name not in {"_ledger", "_map"}
                }
            )
        return checkpoint

    def _restore_revision_transaction(self, checkpoint: Mapping[str, object]) -> None:
        self._habit = checkpoint["habit"]  # type: ignore[assignment]
        self._regimes = checkpoint["regimes"]  # type: ignore[assignment]
        self._automatic_regimes = checkpoint["automatic_regimes"]  # type: ignore[assignment]
        self._corrector = checkpoint["corrector"]  # type: ignore[assignment]
        self._committed_events = checkpoint["committed_events"]  # type: ignore[assignment]
        self._observed_events = checkpoint["observed_events"]  # type: ignore[assignment]
        self._fast_action_events = checkpoint["fast_action_events"]  # type: ignore[assignment]
        self._fast_action_verification_receipts = checkpoint["fast_action_verification_receipts"]  # type: ignore[assignment]
        self._derived_event_archive = checkpoint["derived_event_archive"]  # type: ignore[assignment]
        self._derived_event_lifecycle = checkpoint["derived_event_lifecycle"]  # type: ignore[assignment]
        self._revision_feedback_bindings = checkpoint["feedback_bindings"]  # type: ignore[assignment]
        self._revision_binding_history = checkpoint["revision_binding_history"]  # type: ignore[assignment]
        self._late_feedback_relocations = checkpoint["late_feedback_relocations"]  # type: ignore[assignment]
        self._write_eligibility = checkpoint["write_eligibility"]  # type: ignore[assignment]
        self._revision_transactions = checkpoint["revision_transactions"]  # type: ignore[assignment]
        self._hybrid_reinstatement_lineage = checkpoint["hybrid_reinstatement_lineage"]  # type: ignore[assignment]
        self._correction_cancellations = checkpoint["correction_cancellations"]  # type: ignore[assignment]
        self._revision_parent_events = checkpoint["revision_parent_events"]  # type: ignore[assignment]
        self._deferred_correction_restore = checkpoint["deferred_correction_restore"]  # type: ignore[assignment]
        workspace = checkpoint["particle_workspace"]
        _restore_reference_state(workspace, checkpoint["particle_workspace_state"])
        self._particle_workspace = workspace  # type: ignore[assignment]
        self._event_histories = checkpoint["event_histories"]  # type: ignore[assignment]
        self._production_operator_contract = checkpoint["production_operator_contract"]  # type: ignore[assignment]
        self._quarantined_events = checkpoint["quarantined_events"]  # type: ignore[assignment]
        self._last_observed_location = checkpoint["last_observed_location"]  # type: ignore[assignment]
        self._last_context_key = checkpoint["last_context_key"]  # type: ignore[assignment]
        self._last_context_value = checkpoint["last_context_value"]  # type: ignore[assignment]
        self._last_household_id = checkpoint["last_household_id"]  # type: ignore[assignment]
        self._switch_sequence = checkpoint["switch_sequence"]  # type: ignore[assignment]
        self._last_ccrr_decision = checkpoint["last_ccrr_decision"]  # type: ignore[assignment]
        self._last_cause_snapshot = checkpoint["last_cause_snapshot"]  # type: ignore[assignment]
        self._deferred_project_one_requests = checkpoint["deferred_project_one_requests"]  # type: ignore[assignment]
        self._project_one_application_receipts = checkpoint["project_one_application_receipts"]  # type: ignore[assignment]
        self._action_scoped_negatives = checkpoint["action_scoped_negatives"]  # type: ignore[assignment]
        if "execution_runtime_fields" in checkpoint:
            original_names = checkpoint["execution_core_attribute_names"]
            assert isinstance(original_names, frozenset)
            for name in tuple(self.__dict__):
                if name not in original_names:
                    delattr(self, name)
            runtime_fields = checkpoint["execution_runtime_fields"]
            runtime_refs = checkpoint["execution_runtime_refs"]
            assert isinstance(runtime_fields, dict)
            assert isinstance(runtime_refs, dict)
            for name, snapshot_value in runtime_fields.items():
                original_value = runtime_refs[name]
                preserve_attributes: frozenset[str] = frozenset()
                if name == "_habit":
                    preserve_attributes = frozenset(
                        {
                            "_household_counts",
                            "_person_counts",
                            "_context_counts",
                            "_isolated_nonresident_counts",
                        }
                    )
                elif name == "_regimes":
                    preserve_attributes = frozenset({"_head_factory", "_heads"})
                _restore_reference_state(
                    original_value,
                    snapshot_value,
                    preserve_attributes=preserve_attributes,
                )
                setattr(self, name, original_value)
            self._execution_lock = checkpoint["execution_lock"]  # type: ignore[assignment]
            self._hybrid_loop = checkpoint["hybrid_loop"]  # type: ignore[assignment]
            hybrid_loop_attribute_names = checkpoint["hybrid_loop_attribute_names"]
            assert isinstance(hybrid_loop_attribute_names, frozenset)
            for name in tuple(vars(self._hybrid_loop)):
                if name not in hybrid_loop_attribute_names:
                    delattr(self._hybrid_loop, name)
            hybrid_loop_fields = checkpoint["hybrid_loop_fields"]
            assert isinstance(hybrid_loop_fields, dict)
            for name, value in hybrid_loop_fields.items():
                setattr(self._hybrid_loop, name, deepcopy(value))

            nested_refs = checkpoint["execution_nested_component_refs"]
            nested_snapshots = checkpoint["execution_nested_component_snapshots"]
            assert isinstance(nested_refs, dict)
            assert isinstance(nested_snapshots, dict)
            for name, component in nested_refs.items():
                _restore_reference_state(
                    component,
                    nested_snapshots[name],
                    preserve_attributes=(
                        frozenset({"_lock"}) if name == "automatic_ccrr" else frozenset()
                    ),
                )

            habit_table_refs = cast(
                dict[str, dict[Any, Any]], checkpoint["execution_habit_table_refs"]
            )
            habit_table_snapshots = cast(
                dict[str, dict[Any, Any]],
                checkpoint["execution_habit_table_snapshots"],
            )
            habit_row_refs = cast(
                dict[tuple[str, object], dict[Any, Any]],
                checkpoint["execution_habit_row_refs"],
            )
            for table_name, table_ref in habit_table_refs.items():
                table_snapshot = habit_table_snapshots[table_name]
                table_ref.clear()
                for key, row_snapshot in table_snapshot.items():
                    row_ref = habit_row_refs[(table_name, key)]
                    _restore_reference_state(row_ref, row_snapshot)
                    table_ref[key] = row_ref
                setattr(self._habit, table_name, table_ref)

            rls_heads_ref = cast(
                dict[str, RLSHabitScoreHead], checkpoint["execution_rls_heads_ref"]
            )
            rls_head_refs = cast(
                dict[str, RLSHabitScoreHead], checkpoint["execution_rls_head_refs"]
            )
            rls_head_snapshots = cast(
                dict[str, RLSHabitScoreHead], checkpoint["execution_rls_head_snapshots"]
            )
            rls_model_map_refs = cast(
                dict[str, dict[tuple[UUID, str, str, UUID], Any]],
                checkpoint["execution_rls_model_map_refs"],
            )
            rls_wrapper_refs = cast(
                dict[tuple[str, tuple[UUID, str, str, UUID]], Any],
                checkpoint["execution_rls_wrapper_refs"],
            )
            rls_core_refs = cast(
                dict[tuple[str, tuple[UUID, str, str, UUID]], Any],
                checkpoint["execution_rls_core_refs"],
            )
            rls_config_refs = cast(
                dict[tuple[str, tuple[UUID, str, str, UUID]], object],
                checkpoint["execution_rls_config_refs"],
            )
            rls_theta_refs = cast(
                dict[tuple[str, tuple[UUID, str, str, UUID]], np.ndarray],
                checkpoint["execution_rls_theta_refs"],
            )
            rls_covariance_refs = cast(
                dict[tuple[str, tuple[UUID, str, str, UUID]], np.ndarray],
                checkpoint["execution_rls_covariance_refs"],
            )
            rls_heads_ref.clear()
            for regime_id, head_ref in rls_head_refs.items():
                head_snapshot = rls_head_snapshots[regime_id]
                _restore_reference_state(
                    head_ref,
                    head_snapshot,
                    preserve_attributes=frozenset({"_models"}),
                )
                model_map_ref = rls_model_map_refs[regime_id]
                model_map_ref.clear()
                for key, wrapper_snapshot in head_snapshot._models.items():
                    compound_key = (regime_id, key)
                    wrapper_ref = rls_wrapper_refs[compound_key]
                    _restore_reference_state(
                        wrapper_ref,
                        wrapper_snapshot,
                        preserve_attributes=frozenset({"model"}),
                    )
                    model_ref = rls_core_refs[compound_key]
                    model_snapshot = wrapper_snapshot.model
                    _restore_reference_state(
                        model_ref,
                        model_snapshot,
                        preserve_attributes=frozenset({"_config", "theta", "covariance"}),
                    )
                    config_ref = rls_config_refs[compound_key]
                    _restore_reference_state(config_ref, model_snapshot.config)
                    theta_ref = rls_theta_refs[compound_key]
                    covariance_ref = rls_covariance_refs[compound_key]
                    _restore_reference_state(theta_ref, model_snapshot.theta)
                    _restore_reference_state(covariance_ref, model_snapshot.covariance)
                    model_ref._config = config_ref
                    model_ref.theta = theta_ref
                    model_ref.covariance = covariance_ref
                    wrapper_ref.model = model_ref
                    model_map_ref[key] = wrapper_ref
                head_ref._models = model_map_ref
                rls_heads_ref[regime_id] = head_ref
            self._regimes._head_factory = cast(
                Callable[[], RLSHabitScoreHead], nested_refs["regime_head_factory"]
            )
            self._regimes._heads = rls_heads_ref

            project_receipt_table_ref = cast(
                dict[UUID, list[ProjectOneRequestApplicationReceipt]],
                checkpoint["execution_project_receipt_table_ref"],
            )
            project_receipt_table_snapshot = cast(
                dict[UUID, list[ProjectOneRequestApplicationReceipt]],
                checkpoint["execution_project_receipt_table_snapshot"],
            )
            project_receipt_row_refs = cast(
                dict[UUID, list[ProjectOneRequestApplicationReceipt]],
                checkpoint["execution_project_receipt_row_refs"],
            )
            project_receipt_table_ref.clear()
            for key, row_snapshot in project_receipt_table_snapshot.items():
                receipt_row_ref = project_receipt_row_refs[key]
                _restore_reference_state(receipt_row_ref, row_snapshot)
                project_receipt_table_ref[key] = receipt_row_ref
            self._project_one_application_receipts = project_receipt_table_ref

            automatic_bocpd = nested_refs["automatic_bocpd"]
            automatic_bocpd._reset_matrix = nested_refs["bocpd_reset_matrix"]
            automatic_ccrr = nested_refs["automatic_ccrr"]
            automatic_ccrr._lock = checkpoint["automatic_ccrr_lock"]
            self._automatic_regimes.bocpd = automatic_bocpd
            self._automatic_regimes.ccrr = automatic_ccrr
            self._automatic_regimes.config = self.loop_config
            if "message_passing_delegate" in nested_refs:
                cast(Any, self._message_passing)._delegate = nested_refs["message_passing_delegate"]
            if "message_passing_direct_independence_authority" in nested_refs:
                self._message_passing._independence_authority = nested_refs[
                    "message_passing_direct_independence_authority"
                ]
            if "message_passing_delegate_independence_authority" in nested_refs:
                cast(
                    Any, nested_refs["message_passing_delegate"]
                )._independence_authority = nested_refs[
                    "message_passing_delegate_independence_authority"
                ]
            self._feedback_policy.config = self.loop_config

            self._hybrid_loop._coordinator = nested_refs["hybrid_coordinator"]
            self._hybrid_loop._feedback_projector = nested_refs["hybrid_feedback_projector"]
            self._hybrid_loop._fusion = nested_refs["hybrid_fusion"]

            original_ledger = checkpoint["hybrid_ledger"]
            restored_ledger = type(original_ledger).restore_from_export(  # type: ignore[attr-defined]
                checkpoint["hybrid_export"]
            )
            _restore_reference_state(
                original_ledger,
                restored_ledger,
                preserve_attributes=frozenset({"_lock"}),
            )
            original_ledger._lock = checkpoint["hybrid_ledger_lock"]  # type: ignore[attr-defined]
            self._hybrid_loop._ledger = original_ledger  # type: ignore[assignment]

            snapshot = checkpoint["belief_snapshot"]
            assert isinstance(snapshot, BeliefSnapshot)
            restored_map = VersionedBeliefMap(map_id=snapshot.map_id)
            restored_map._nodes = snapshot.node_map()
            restored_map._version = snapshot.map_version
            restored_map._snapshot_id = snapshot.snapshot_id
            original_map = checkpoint["hybrid_map"]
            _restore_reference_state(
                original_map,
                restored_map,
                preserve_attributes=frozenset({"_lock"}),
            )
            original_map._lock = checkpoint["hybrid_map_lock"]  # type: ignore[attr-defined]
            self._hybrid_loop._map = original_map  # type: ignore[assignment]
        else:
            self._hybrid_loop._ledger = type(self._hybrid_loop.ledger).restore_from_export(
                checkpoint["hybrid_export"]  # type: ignore[arg-type]
            )
            snapshot = checkpoint["belief_snapshot"]
            assert isinstance(snapshot, BeliefSnapshot)
            belief_map = VersionedBeliefMap(map_id=snapshot.map_id)
            belief_map._nodes = snapshot.node_map()
            belief_map._version = snapshot.map_version
            belief_map._snapshot_id = snapshot.snapshot_id
            self._hybrid_loop._map = belief_map

    @_serialized_core_mutation
    def apply_project_one_stat_request(
        self, request: ProjectOneStatRequest
    ) -> ProjectOneRequestApplicationReceipt:
        """Apply/defer/reject one request with exactly-once receipt semantics."""

        if self._production_operator_contract is not None:
            self._production_operator_contract()
        checkpoint = self._capture_revision_transaction(include_operator_state=True)
        try:
            return self._apply_project_one_stat_request(request)
        except BaseException:
            self._restore_revision_transaction(checkpoint)
            raise

    def _apply_project_one_stat_request(
        self, request: ProjectOneStatRequest
    ) -> ProjectOneRequestApplicationReceipt:

        from cpswm.system.counterfactual_event_hypergraph.feedback_revision_loop import (
            ProjectOneStatRequest,
        )

        if not isinstance(request, ProjectOneStatRequest):
            raise TypeError("request must be a ProjectOneStatRequest")
        fingerprint = _project_one_request_fingerprint(request)
        prior_receipts = self._project_one_application_receipts.get(
            request.source_feedback_record_id, []
        )
        already_applied = next(
            (
                receipt
                for receipt in prior_receipts
                if receipt.request_fingerprint == fingerprint
                and receipt.status
                in {
                    ProjectOneRequestApplicationStatus.APPLIED,
                    ProjectOneRequestApplicationStatus.REJECTED,
                }
            ),
            None,
        )
        if already_applied is not None:
            return self._replay_receipt(already_applied)
        if fingerprint in self._deferred_project_one_requests:
            previous = next(
                receipt
                for receipt in reversed(prior_receipts)
                if receipt.request_fingerprint == fingerprint
            )
            return self._replay_receipt(previous)
        original = self._committed_events.get(request.superseded_revision_id)
        if request.owner_key != self.owner_key:
            return self._rejected_request(request, fingerprint, "request owner mismatch")
        if request.object_instance_id != self.object_instance_id:
            return self._rejected_request(request, fingerprint, "request object mismatch")
        if request.location_id not in self.locations:
            return self._rejected_request(request, fingerprint, "request location mismatch")
        source = original or self._observed_events.get(request.superseded_revision_id)
        if source is not None:
            if request.event_hypothesis_id != source.event_hypothesis_id:
                return self._rejected_request(request, fingerprint, "event hypothesis mismatch")
            if abs(request.owner_mass_before - source.owner_mass) > 1e-9:
                return self._rejected_request(request, fingerprint, "owner_mass_before mismatch")
        if (
            abs(request.owner_mass_delta - (request.owner_mass_after - request.owner_mass_before))
            > 1e-9
        ):
            return self._rejected_request(request, fingerprint, "owner mass delta mismatch")
        if original is None:
            if self.is_quarantined_revision(request.superseded_revision_id):
                self._deferred_project_one_requests[fingerprint] = (
                    request,
                    request.superseded_revision_id,
                    "apply_request",
                )
                return self._record_request_receipt(
                    request=request,
                    fingerprint=fingerprint,
                    status=ProjectOneRequestApplicationStatus.DEFERRED_DUE_TO_QUARANTINE,
                    old_snapshot=self.current_snapshot,
                    new_snapshot=self.current_snapshot,
                    ccrr_decision="deferred_due_to_quarantine",
                    rationale="superseded event is quarantined; retry is bound to its promotion",
                )
            return self._record_request_receipt(
                request=request,
                fingerprint=fingerprint,
                status=ProjectOneRequestApplicationStatus.REJECTED,
                old_snapshot=self.current_snapshot,
                new_snapshot=self.current_snapshot,
                ccrr_decision=self._last_ccrr_decision,
                rationale=(
                    "superseded revision was already superseded by a later "
                    "correction; the request targets a stale lineage head"
                    if request.superseded_revision_id in self._observed_events
                    or request.superseded_revision_id in self._derived_event_archive
                    else "superseded revision is neither committed nor quarantined"
                ),
            )
        if request.owner_key != self.owner_key:
            return self._rejected_request(request, fingerprint, "request owner mismatch")
        if request.object_instance_id != self.object_instance_id:
            return self._rejected_request(request, fingerprint, "request object mismatch")
        if request.event_hypothesis_id != original.event_hypothesis_id:
            return self._rejected_request(request, fingerprint, "event hypothesis mismatch")
        if abs(request.owner_mass_before - original.owner_mass) > 1e-9:
            return self._rejected_request(request, fingerprint, "owner_mass_before mismatch")
        declared_delta = request.owner_mass_after - request.owner_mass_before
        if abs(request.owner_mass_delta - declared_delta) > 1e-9:
            return self._rejected_request(request, fingerprint, "owner mass delta mismatch")

        # The Project One request is a wider transaction than the internal
        # EventRevisionOutcome call: a CCRR/RGRC rebuild may deliberately drop
        # the corrected event after the revision itself succeeded. Preserve a
        # checkpoint so that this becomes an explicit rejected receipt without
        # leaving a half-applied Dirichlet/RLS/Hybrid mutation.
        request_checkpoint = self._capture_revision_transaction(include_operator_state=True)
        restore_events = tuple(
            self._committed_events[rid]
            for rid in (
                request.superseded_revision_id,
                *self._descendant_revision_ids(request.superseded_revision_id),
            )
        )
        restore_fast = tuple(
            self._fast_action_events[e.revision_id]
            for e in restore_events
            if e.revision_id in self._fast_action_events
        )
        old_snapshot = self.current_snapshot
        before = self.committed_weight_semantics(request.superseded_revision_id)
        hybrid_before = self.hybrid_alpha(request.location_id)
        # Only this transaction owns a durable, typed defer/reject outbox.
        # The public synchronous outcome entry promises an applied revision.
        result = self._apply_event_revision_outcome(
            EventRevisionOutcome(
                kind=EventRevisionKind.CORRECT,
                superseded_revision_id=request.superseded_revision_id,
                corrected_revision_id=request.corrected_revision_id,
                corrected_location_id=request.location_id,
                corrected_owner_mass=request.owner_mass_after,
                evidence_source_record_ids=(request.source_feedback_record_id,),
                rationale=f"project-two {request.kind.value} stat request",
            )
        )
        if request.corrected_revision_id not in self._committed_events:
            if not self.is_quarantined_revision(request.corrected_revision_id):
                ccrr_decision = result.ccrr_conclusion
                self._restore_revision_transaction(request_checkpoint)
                return self._record_request_receipt(
                    request=request,
                    fingerprint=fingerprint,
                    status=ProjectOneRequestApplicationStatus.REJECTED,
                    old_snapshot=old_snapshot,
                    new_snapshot=self.current_snapshot,
                    ccrr_decision=ccrr_decision,
                    rationale=(
                        "CCRR/RGRC rejected the corrected event; the complete "
                        "Project One statistics transaction was rolled back"
                    ),
                )
            self._deferred_project_one_requests[fingerprint] = (
                request,
                request.corrected_revision_id,
                "promotion_finalizes",
            )
            self._deferred_correction_restore[fingerprint] = (restore_events, restore_fast)
            return self._record_request_receipt(
                request=request,
                fingerprint=fingerprint,
                status=ProjectOneRequestApplicationStatus.DEFERRED_DUE_TO_QUARANTINE,
                old_snapshot=old_snapshot,
                new_snapshot=self.current_snapshot,
                ccrr_decision=result.ccrr_conclusion,
                rationale=(
                    "revision was accepted but CCRR quarantined the corrected event; "
                    "its promotion will finalize statistics exactly once"
                ),
            )
        after = self.committed_weight_semantics(request.corrected_revision_id)
        hybrid_after = self.hybrid_alpha(request.location_id)
        self._deferred_project_one_requests.pop(fingerprint, None)
        return self._record_request_receipt(
            request=request,
            fingerprint=fingerprint,
            status=ProjectOneRequestApplicationStatus.APPLIED,
            old_snapshot=old_snapshot,
            new_snapshot=self.current_snapshot,
            dirichlet=(
                StatisticDelta(
                    statistic="owner_training_weight",
                    before=before["dirichlet_owner_weight"],
                    after=after["dirichlet_owner_weight"],
                    delta=after["dirichlet_owner_weight"] - before["dirichlet_owner_weight"],
                ),
            ),
            rls=(
                StatisticDelta(
                    statistic="owner_gate",
                    before=before["rls_owner_weight"],
                    after=after["rls_owner_weight"],
                    delta=after["rls_owner_weight"] - before["rls_owner_weight"],
                ),
            ),
            hybrid=(
                StatisticDelta(
                    statistic=f"alpha:{request.location_id}",
                    before=hybrid_before,
                    after=hybrid_after,
                    delta=hybrid_after - hybrid_before,
                ),
            ),
            ccrr_decision=result.ccrr_conclusion,
            rationale=result.rationale,
        )

    def _record_request_receipt(
        self,
        *,
        request: ProjectOneStatRequest,
        fingerprint: str,
        status: ProjectOneRequestApplicationStatus,
        old_snapshot: BeliefSnapshot,
        new_snapshot: BeliefSnapshot,
        ccrr_decision: str,
        rationale: str,
        dirichlet: tuple[StatisticDelta, ...] = (),
        rls: tuple[StatisticDelta, ...] = (),
        hybrid: tuple[StatisticDelta, ...] = (),
    ) -> ProjectOneRequestApplicationReceipt:
        self._update_action_scoped_negative(request, fingerprint, status)
        history = self._project_one_application_receipts.setdefault(
            request.source_feedback_record_id, []
        )
        receipt = ProjectOneRequestApplicationReceipt(
            receipt_id=uuid5(NAMESPACE_URL, f"{fingerprint}:{len(history) + 1}:{status.value}"),
            request_fingerprint=fingerprint,
            status=status,
            superseded_revision_id=request.superseded_revision_id,
            corrected_revision_id=request.corrected_revision_id,
            source_feedback_record_id=request.source_feedback_record_id,
            evidence_source_record_ids=(request.source_feedback_record_id,),
            attempt_number=len(history) + 1,
            old_belief_snapshot_id=old_snapshot.snapshot_id,
            new_belief_snapshot_id=new_snapshot.snapshot_id,
            dirichlet_deltas=dirichlet,
            rls_deltas=rls,
            hybrid_rgrc_deltas=hybrid,
            ccrr_decision=ccrr_decision,
            rationale=rationale,
        )
        history.append(receipt)
        return receipt

    def _rejected_request(
        self, request: ProjectOneStatRequest, fingerprint: str, rationale: str
    ) -> ProjectOneRequestApplicationReceipt:
        return self._record_request_receipt(
            request=request,
            fingerprint=fingerprint,
            status=ProjectOneRequestApplicationStatus.REJECTED,
            old_snapshot=self.current_snapshot,
            new_snapshot=self.current_snapshot,
            ccrr_decision=self._last_ccrr_decision,
            rationale=rationale,
        )

    def _replay_receipt(
        self, applied: ProjectOneRequestApplicationReceipt
    ) -> ProjectOneRequestApplicationReceipt:
        history = self._project_one_application_receipts.setdefault(
            applied.source_feedback_record_id, []
        )
        receipt = ProjectOneRequestApplicationReceipt(
            receipt_id=uuid5(
                NAMESPACE_URL,
                f"{applied.request_fingerprint}:{applied.attempt_number + 1}:replay_noop",
            ),
            request_fingerprint=applied.request_fingerprint,
            status=ProjectOneRequestApplicationStatus.REPLAY_NOOP,
            superseded_revision_id=applied.superseded_revision_id,
            corrected_revision_id=applied.corrected_revision_id,
            source_feedback_record_id=applied.source_feedback_record_id,
            evidence_source_record_ids=applied.evidence_source_record_ids,
            attempt_number=len(history) + 1,
            old_belief_snapshot_id=self.current_snapshot.snapshot_id,
            new_belief_snapshot_id=self.current_snapshot.snapshot_id,
            ccrr_decision="replay_noop",
            rationale="request fingerprint was already applied exactly once",
        )
        history.append(receipt)
        return receipt

    @_serialized_core_mutation
    def publish_project_two_revision_snapshot(
        self, outcome: ProjectTwoEventRevisionOutcome
    ) -> BeliefSnapshot:
        self._apply_fast_action_revision(outcome)
        payload = {
            "corrected_revision_id": str(outcome.corrected_revision_id),
            "actor_posterior": sorted(outcome.actor_posterior_after.items()),
            "mechanism_posterior": sorted(outcome.mechanism_posterior_after.items()),
            "role_posterior": sorted(outcome.role_posterior_after.items()),
            "location_posterior": sorted(outcome.location_posterior_after.items()),
            "sources": [str(item) for item in outcome.evidence_source_record_ids],
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        return self._hybrid_loop.publish_project_two_revision(
            corrected_revision_id=outcome.corrected_revision_id,
            posterior_content_hash=digest,
            unresolved_probability=min(
                1.0, outcome.unresolved_after + outcome.unknown_mechanism_after
            ),
        )

    @_serialized_core_mutation
    def apply_fast_action_verification(
        self,
        *,
        revision_id: UUID,
        verified_owner_probability: float,
        source_record_id: UUID,
    ) -> FastActionVerificationReceipt:
        """Apply one realized micro-verification only to the reversible fast ledger."""

        _require_probability(verified_owner_probability, "verified_owner_probability")
        event = self._fast_action_events.get(revision_id)
        if event is None:
            raise KeyError(f"unknown fast-action revision {revision_id}")
        before = event.owner_mass
        changed = abs(before - verified_owner_probability) > 1e-12
        if changed:
            self._fast_action_events[revision_id] = replace(
                event,
                owner_mass=verified_owner_probability,
                statistical_owner_weight=verified_owner_probability,
                source_record_id=source_record_id,
            )
        receipt = FastActionVerificationReceipt(
            receipt_id=uuid5(
                NAMESPACE_URL,
                f"ciav:{revision_id}:{source_record_id}:{verified_owner_probability:.17g}",
            ),
            revision_id=revision_id,
            source_record_id=source_record_id,
            owner_mass_before=before,
            owner_mass_after=verified_owner_probability,
            changed=changed,
        )
        self._fast_action_verification_receipts.append(receipt)
        return receipt

    def _apply_fast_action_revision(self, outcome: ProjectTwoEventRevisionOutcome) -> None:
        """Replace one fast-action lineage head without authorizing a slow write.

        ORRER owns revision semantics and RGRC owns long-term write permission.
        The next robot action must not be forced to wait for the latter.  This
        method therefore updates only the fast ledger consumed by the
        dual-timescale readout; Dirichlet, RLS, Hybrid, and CCRR state are
        untouched.
        """

        original = self._fast_action_events.pop(outcome.superseded_revision_id, None)
        if original is None:
            return
        resolved = {
            UUID(key): probability
            for key, probability in outcome.location_posterior_after.items()
            if key != "unresolved_location" and UUID(key) in self.locations
        }
        corrected_location = outcome.corrected_destination_location_id
        if corrected_location is None and resolved:
            corrected_location = max(
                resolved,
                key=lambda location: (resolved[location], str(location)),
            )
        if corrected_location is None:
            corrected_location = original.location_id
        self._fast_action_events[outcome.corrected_revision_id] = replace(
            original,
            revision_id=outcome.corrected_revision_id,
            owner_mass=outcome.owner_mass_after,
            statistical_owner_weight=outcome.owner_mass_after,
            location_id=corrected_location,
            source_record_id=outcome.source_feedback_record_id,
            belief_snapshot_id=None,
        )

    def action_location_distribution(
        self,
        snapshot: BeliefSnapshot,
        *,
        readout: ActionReadoutConfig | None = None,
    ) -> dict[UUID, float]:
        """Planner read boundary: reject any stale/pre-correction snapshot.

        The default readout is the frozen pooled hybrid alpha.  A caller may pass
        an explicit :class:`ActionReadoutConfig` to read the *surviving* revision
        set and the regime-local model instead -- the two things the reversible
        machinery actually maintains and the pooled count cannot express.
        """

        if snapshot.snapshot_id != self.current_snapshot.snapshot_id:
            raise ValueError("planner attempted to read a stale belief snapshot")
        config = readout or self._action_readout
        weights = config.component_weights
        components: list[tuple[float, dict[UUID, float]]] = []
        if weights["hybrid_alpha"] > 0.0:
            components.append((weights["hybrid_alpha"], self._hybrid_alpha_component()))
        if weights["regime_local"] > 0.0:
            components.append((weights["regime_local"], self._regime_local_component()))
        if weights["surviving"] > 0.0:
            components.append(
                (weights["surviving"], self._surviving_owner_revision_component(config))
            )
        fast_weight = weights["fast_action"]
        if (
            fast_weight > 0.0
            and self._fast_action_confirmation_count(config) < config.fast_confirmation_observations
        ):
            fast_weight *= config.unconfirmed_fast_discount
        if fast_weight > 0.0:
            components.append((fast_weight, self._latest_owner_event_component(config)))
        mixed = self._mix_action_components(components)
        return self._apply_pending_correction_discount(mixed, config)

    # -- readout components -------------------------------------------------

    def _hybrid_alpha_component(self) -> dict[UUID, float]:
        """Pooled cumulative owner-weighted mass (the frozen v0.2 boundary)."""

        return {location: max(0.0, self.hybrid_alpha(location)) for location in self.locations}

    def _regime_local_component(self) -> dict[UUID, float]:
        """Current-regime Dirichlet prediction gated by the regime-local RLS head.

        This is the same evidence ``_current_suggestion`` already uses for the
        map's put-back suggestion.  Before this readout existed, the planner in
        the action benchmark could not see it at all.
        """

        if self._last_household_id is None:
            return dict.fromkeys(self.locations, 1.0)
        prediction = self._habit.predict(
            household_id=self._last_household_id,
            person_id=self.owner_key,
            object_instance_id=self.object_instance_id,
            context_key=self._last_context_key,
        )
        scores = self._regimes.score_candidates(
            object_instance_id=self.object_instance_id,
            actor_id=self.owner_key,
            context_features=np.array([self._last_context_value], dtype=float),
            candidate_locations=self.locations,
            location_embeddings=self._embeddings,
        )
        return {
            location: max(0.0, prediction.probabilities.get(location, 0.0))
            * max(0.0, scores.get(location, 0.0))
            for location in self.locations
        }

    def _surviving_owner_revision_component(self, config: ActionReadoutConfig) -> dict[UUID, float]:
        """Mass over locations whose owner-attributed evidence currently survives.

        ``self._committed_events`` is the authoritative surviving set: an explicit
        retract deletes its entry, a correction replaces it with the corrected
        revision, and a rebuild re-commits in ``event_time`` order.  Reading it
        directly is what makes a reversible revision visible to the next action
        instead of being averaged away inside a cumulative count.
        """

        ordered = sorted(
            self._committed_events.values(),
            key=lambda event: (event.evidence.event_time, str(event.revision_id)),
        )
        if config.active_regime_only:
            active = [
                event for event in ordered if event.rls_sample.regime_id == self.active_regime
            ]
            # An empty active regime is a cold start, not evidence of absence.
            ordered = active or ordered
        weights = dict.fromkeys(self.locations, 0.0)
        count = len(ordered)
        for index, event in enumerate(ordered):
            if event.owner_mass < config.owner_mass_floor:
                continue
            if event.location_id not in weights:
                continue
            age = count - 1 - index
            decay = (
                0.5 ** (age / config.recency_half_life) if config.recency_half_life > 0.0 else 1.0
            )
            weights[event.location_id] += max(0.0, event.statistical_owner_weight) * decay
        return weights

    def _latest_owner_event_component(self, config: ActionReadoutConfig) -> dict[UUID, float]:
        """One-step action belief from the latest still-live owner event.

        This is the explicit strong control suggested by the D0 diagnosis.  It
        reads PCHMP owner mass, not evaluator truth, and it is reversible because
        ``_apply_fast_action_revision`` replaces the corresponding ORRER lineage
        head before the next planner read.  It never grants permission to write
        the event into long-term habit statistics.
        """

        eligible = [
            event
            for event in self._fast_action_events.values()
            if event.owner_mass >= config.fast_owner_mass_floor
            and event.location_id in self.locations
        ]
        if not eligible:
            return dict.fromkeys(self.locations, 0.0)
        latest = max(
            eligible,
            key=lambda event: (event.evidence.event_time, str(event.revision_id)),
        )
        return {
            location: (max(latest.owner_mass, 1e-12) if location == latest.location_id else 0.0)
            for location in self.locations
        }

    def _fast_action_confirmation_count(self, config: ActionReadoutConfig) -> int:
        """Consecutive owner-attributed fast events supporting the latest location."""

        ordered = sorted(
            (
                event
                for event in self._fast_action_events.values()
                if event.owner_mass >= config.fast_owner_mass_floor
                and event.location_id in self.locations
            ),
            key=lambda event: (event.evidence.event_time, str(event.revision_id)),
            reverse=True,
        )
        if not ordered:
            return 0
        location = ordered[0].location_id
        confirmations = 0
        for event in ordered:
            if event.location_id != location:
                break
            confirmations += 1
        return confirmations

    def _mix_action_components(
        self, components: Sequence[tuple[float, Mapping[UUID, float]]]
    ) -> dict[UUID, float]:
        mixed = dict.fromkeys(self.locations, 0.0)
        used = 0.0
        for weight, component in components:
            total = sum(max(0.0, value) for value in component.values())
            if total <= 0.0:
                continue
            used += weight
            for location in self.locations:
                mixed[location] += weight * max(0.0, component.get(location, 0.0)) / total
        if used <= 0.0:
            return dict.fromkeys(self.locations, 1.0 / len(self.locations))
        return {location: value / used for location, value in mixed.items()}

    def _update_action_scoped_negative(
        self,
        request: ProjectOneStatRequest,
        fingerprint: str,
        status: ProjectOneRequestApplicationStatus,
    ) -> None:
        """Release legacy action entries without granting rejected requests effects.

        A rejected request may be foreign or fail admission and must not alter
        the next action. A deferred request is already represented exactly once
        by the durable outbox in pending_correction_mass. Explicitly accepted
        feedback/verification uses its own existing fast-memory entry points.
        """

        if status is ProjectOneRequestApplicationStatus.APPLIED:
            self._action_scoped_negatives.pop(fingerprint, None)
            return

    def action_scoped_negative_ledger(self) -> dict[str, tuple[UUID, float]]:
        """Audit view: every refused correction still influencing the next action."""

        return dict(self._action_scoped_negatives)

    def pending_correction_mass(self) -> dict[UUID, float]:
        """Owner-mass delta of corrections that have not reached the statistics.

        Two disjoint sources, both honest:

        * deferred requests -- the revision was accepted and only its statistic
          write waits on CCRR promotion;
        * historical action-scoped entries retained from earlier runtime state.

        New rejected requests cannot create action entries. New deferred requests
        live only in the outbox, preventing double counting of the same delta.

        Neither ever mutates Dirichlet/RLS/Hybrid.  Exposing them lets the planner
        act on a correction while the long-term ledger stays exactly as strict.
        """

        pending: dict[UUID, float] = {}
        for request, _waiting_revision_id, _mode in self._deferred_project_one_requests.values():
            location_id = getattr(request, "location_id", None)
            delta = float(getattr(request, "owner_mass_delta", 0.0))
            if location_id is None:
                continue
            pending[location_id] = pending.get(location_id, 0.0) + delta
        for location_id, delta in self._action_scoped_negatives.values():
            pending[location_id] = pending.get(location_id, 0.0) + delta
        return pending

    def _apply_pending_correction_discount(
        self, distribution: Mapping[UUID, float], config: ActionReadoutConfig
    ) -> dict[UUID, float]:
        if config.pending_correction_discount >= 1.0:
            return dict(distribution)
        pending = self.pending_correction_mass()
        adjusted = {
            location: (
                value * config.pending_correction_discount
                if pending.get(location, 0.0) < 0.0
                else value
            )
            for location, value in distribution.items()
        }
        total = sum(adjusted.values())
        if total <= 0.0:
            return {location: 1.0 / len(self.locations) for location in self.locations}
        return {location: value / total for location, value in adjusted.items()}

    def _descendant_revision_ids(self, revision_id: UUID) -> tuple[UUID, ...]:
        return self._derived_descendants_in(
            self._committed_events,
            {revision_id},
        )

    @staticmethod
    def _derived_descendants_in(
        events: Mapping[UUID, _CommittedPrototypeEvent],
        root_revision_ids: set[UUID],
    ) -> tuple[UUID, ...]:
        """Return every derived descendant, including multi-level feedback chains."""

        descendants: list[UUID] = []
        seen: set[UUID] = set()
        frontier = list(root_revision_ids)
        while frontier:
            parent = frontier.pop()
            children = [
                event.revision_id
                for event in events.values()
                if event.derived_from_revision_id == parent and event.revision_id not in seen
            ]
            seen.update(children)
            descendants.extend(children)
            frontier.extend(children)
        return tuple(descendants)

    def _corrected_actor_posterior(
        self,
        posterior: Mapping[str, float],
        *,
        corrected_owner_mass: float,
    ) -> dict[str, float]:
        """Set owner mass exactly and proportionally preserve all alternatives."""

        remaining_mass = 1.0 - corrected_owner_mass
        alternatives = {
            actor: probability
            for actor, probability in posterior.items()
            if actor != self.owner_key
        }
        alternative_total = sum(alternatives.values())
        corrected = {self.owner_key: corrected_owner_mass}
        if alternative_total > 0.0:
            corrected.update(
                {
                    actor: remaining_mass * probability / alternative_total
                    for actor, probability in alternatives.items()
                }
            )
        elif remaining_mass > 0.0:
            corrected[HierarchicalDirichletHabitModel.UNKNOWN_ACTOR] = remaining_mass
        return corrected

    @_serialized_core_mutation
    def process_execution_feedback(
        self,
        *,
        feedback: ExecutionFeedbackRecord,
        binding: DecisionContextBinding,
        likelihood_model: ActionOutcomeLikelihoodModel,
        policy: ExecutionFeedbackInterpretationPolicy | None = None,
    ) -> PrototypeRevisionResult:
        """Include feedback deduplication and publication in the revision transaction."""

        if self._production_operator_contract is not None:
            self._production_operator_contract()
        checkpoint = self._capture_revision_transaction(include_operator_state=True)
        try:
            return self._process_execution_feedback(
                feedback=feedback,
                binding=binding,
                likelihood_model=likelihood_model,
                policy=policy,
            )
        except BaseException:
            self._restore_revision_transaction(checkpoint)
            raise

    def _process_execution_feedback(
        self,
        *,
        feedback: ExecutionFeedbackRecord,
        binding: DecisionContextBinding,
        likelihood_model: ActionOutcomeLikelihoodModel,
        policy: ExecutionFeedbackInterpretationPolicy | None = None,
    ) -> PrototypeRevisionResult:
        """Project likelihood evidence and apply a pluggable statistic policy."""

        bound_revision_id, relocation = self._resolve_feedback_binding(
            feedback=feedback,
            binding=binding,
        )

        projected = self._hybrid_loop.prepare_execution_feedback(
            feedback=feedback,
            binding=binding,
            likelihood_model=likelihood_model,
        )
        if projected.is_replay:
            return self._revision_result(
                operations=(PrototypeStatisticOperation.QUARANTINE,),
                evidence_source_record_ids=(feedback.metadata.record_id,),
                snapshot=self.current_snapshot,
                old_regime=self.active_regime,
                rationale="identical feedback replay is an idempotent no-op",
                feedback_posterior_probability=(
                    projected.target_presence_update.posterior_target_present
                    if projected.target_presence_update is not None
                    else None
                ),
            )
        interpretation = (policy or self._feedback_policy).interpret(
            feedback=feedback, projected=projected
        )
        if (
            interpretation.target_revision_id is not None
            and interpretation.target_revision_id != bound_revision_id
        ):
            raise ValueError("feedback policy target revision differs from bound revision")
        if interpretation.operation is PrototypeStatisticOperation.RETRACT:
            if interpretation.target_revision_id is None:
                raise ValueError("retract feedback requires target_revision_id")
            result = self.apply_event_revision_outcome(
                EventRevisionOutcome(
                    kind=EventRevisionKind.RETRACT,
                    superseded_revision_id=interpretation.target_revision_id,
                    evidence_source_record_ids=(feedback.metadata.record_id,),
                    rationale=interpretation.rationale,
                )
            )
        elif interpretation.operation is PrototypeStatisticOperation.CORRECT:
            if (
                interpretation.target_revision_id is None
                or interpretation.corrected_location_id is None
            ):
                raise ValueError("correct feedback requires revision and corrected location")
            corrected_revision_id = uuid4()
            result = self.apply_event_revision_outcome(
                EventRevisionOutcome(
                    kind=EventRevisionKind.CORRECT,
                    superseded_revision_id=interpretation.target_revision_id,
                    corrected_revision_id=corrected_revision_id,
                    corrected_location_id=interpretation.corrected_location_id,
                    corrected_owner_mass=interpretation.evidence_strength,
                    evidence_source_record_ids=(feedback.metadata.record_id,),
                    rationale=interpretation.rationale,
                )
            )
        else:
            if interpretation.operation is PrototypeStatisticOperation.REINFORCE:
                if interpretation.target_revision_id is None:
                    raise ValueError("reinforce feedback requires target_revision_id")
                self._reinforce_revision(
                    revision_id=interpretation.target_revision_id,
                    evidence_strength=interpretation.evidence_strength,
                    source_record_id=feedback.metadata.record_id,
                )
            result = self._revision_result(
                operations=(interpretation.operation,),
                evidence_source_record_ids=(feedback.metadata.record_id,),
                snapshot=self.current_snapshot,
                old_regime=self.active_regime,
                rationale=interpretation.rationale,
                feedback_posterior_probability=(
                    projected.target_presence_update.posterior_target_present
                    if projected.target_presence_update is not None
                    else None
                ),
            )
        if relocation is not None:
            # Audited, not silent: a later reader can see exactly which feedback was
            # accepted against which superseded-but-published binding.  Appended only
            # after the statistic transaction succeeded, so a rolled-back revision
            # leaves no relocation row behind.
            self._late_feedback_relocations.append(relocation)
        self._hybrid_loop.commit_execution_feedback(projected)
        return result

    def _validate_feedback_revision_binding(
        self,
        *,
        feedback: ExecutionFeedbackRecord,
        binding: DecisionContextBinding,
    ) -> UUID:
        """Compatibility wrapper: resolve the bound revision, discard the audit row."""

        revision_id, _ = self._resolve_feedback_binding(feedback=feedback, binding=binding)
        return revision_id

    def _resolve_feedback_binding(
        self,
        *,
        feedback: ExecutionFeedbackRecord,
        binding: DecisionContextBinding,
    ) -> tuple[UUID, _LateFeedbackRelocation | None]:
        """Resolve the bound revision, accepting a verifiably published older binding.

        Snapshot validation is not relaxed.  A feedback still has to present a
        binding this runtime really published for *this* revision at *this*
        location; the only change is that the accepted set is the revision's
        published binding history rather than only its newest entry.  An unrelated
        revision's retraction republishes every surviving revision's binding, so
        without this a feedback that was legal when it was issued becomes
        permanently unusable through no fault of its own.

        What is deliberately *not* done: the feedback's own action context is never
        rewritten, an unpublished or foreign snapshot is never accepted, and a
        revision that has itself been retracted is refused with a distinct,
        recoverable error rather than silently relocated.
        """

        raw_revision_id = feedback.diagnostics.get("source_revision_id")
        if not isinstance(raw_revision_id, str):
            raise ValueError("feedback must bind source_revision_id")
        try:
            revision_id = UUID(raw_revision_id)
        except ValueError as exc:
            raise ValueError("feedback source_revision_id must be a UUID") from exc
        event = self._committed_events.get(revision_id)
        archived_binding = self._revision_feedback_bindings.get(revision_id)
        if event is None and archived_binding is None:
            raise ValueError("feedback revision is not a committed event")
        if feedback.target_entity is None or (
            feedback.target_entity.entity_id != self.object_instance_id
        ):
            raise ValueError("feedback revision object does not match the prototype object")
        if event is not None:
            expected_location = event.location_id
            expected_snapshot_id = event.belief_snapshot_id
        else:
            assert archived_binding is not None
            expected_location, expected_snapshot_id = archived_binding
        if feedback.attempted_location_id != expected_location:
            raise ValueError("feedback revision location does not match the committed event")
        if expected_snapshot_id is None:
            raise ValueError("feedback revision has no committed snapshot binding")
        presented_snapshot_id = binding.decision_context.revisions.belief_snapshot_id
        if presented_snapshot_id == expected_snapshot_id:
            return revision_id, None
        superseded = self._match_published_binding(
            revision_id,
            presented_snapshot_id=presented_snapshot_id,
            expected_location=expected_location,
        )
        if superseded is None:
            raise ValueError("feedback revision snapshot does not match the committed event")
        current = self.current_snapshot
        if superseded.map_version >= current.map_version:
            raise ValueError("feedback revision snapshot does not match the committed event")
        if event is None:
            # The revision was retracted after this binding was published.  The
            # binding is genuine, so it is accepted here and the ordinary
            # replay / dead-target handling downstream decides the outcome; there
            # is nothing to relocate onto a revision that no longer exists.
            return revision_id, None
        relocation = _LateFeedbackRelocation(
            revision_id=revision_id,
            feedback_record_id=feedback.metadata.record_id,
            presented_snapshot_id=presented_snapshot_id,
            presented_map_version=superseded.map_version,
            current_snapshot_id=current.snapshot_id,
            current_map_version=current.map_version,
            location_id=expected_location,
        )
        return revision_id, relocation

    def _match_published_binding(
        self,
        revision_id: UUID,
        *,
        presented_snapshot_id: UUID,
        expected_location: UUID,
    ) -> _PublishedRevisionBinding | None:
        """Find a binding this runtime really published for this revision.

        The presented snapshot must appear in the revision's own append-only
        publication history *and* have been published for the same location, so a
        snapshot borrowed from another revision or another location is refused.
        """

        for published in self._revision_binding_history.get(revision_id, ()):
            if (
                published.snapshot_id == presented_snapshot_id
                and published.location_id == expected_location
            ):
                return published
        return None

    def _reinforce_revision(
        self,
        *,
        revision_id: UUID,
        evidence_strength: float,
        source_record_id: UUID,
    ) -> BeliefSnapshot:
        original = self._committed_events.get(revision_id)
        if original is None:
            raise KeyError("reinforced revision is not a committed prototype event")
        strength = min(1.0, max(0.0, evidence_strength))
        if strength <= 0.0:
            return self.current_snapshot
        reinforced_revision = uuid4()
        reinforced_event = uuid4()
        evidence = original.evidence.model_copy(
            update={
                "metadata": original.evidence.metadata.model_copy(
                    update={"record_id": uuid4(), "source_id": "prototype-spine.feedback"}
                ),
                "proposed_training_weight": strength,
                "source_record_ids": tuple(
                    dict.fromkeys((*original.evidence.source_record_ids, source_record_id))
                ),
            }
        )
        sample = replace(
            original.rls_sample,
            gate=original.owner_mass * strength,
        )
        self._commit_event(
            replace(
                original,
                event_hypothesis_id=reinforced_event,
                revision_id=reinforced_revision,
                evidence=evidence,
                propensity_weight=1.0,
                rls_sample=sample,
                owner_mass=original.owner_mass,
                statistical_owner_weight=original.owner_mass * strength,
                source_record_id=source_record_id,
                dirichlet_predictive_surprise=0.0,
                rls_residual=0.0,
                regime_frame=None,
                hybrid_revision_id=None,
                hybrid_parent_revision_id=None,
                derived_from_revision_id=revision_id,
                belief_snapshot_id=None,
            )
        )
        snapshot = self._hybrid_loop.publish_snapshot()
        reinforced = self._committed_events[reinforced_revision]
        self._committed_events[reinforced_revision] = replace(
            reinforced,
            belief_snapshot_id=snapshot.snapshot_id,
        )
        self._publish_revision_binding(
            reinforced_revision,
            location_id=reinforced.location_id,
            snapshot=snapshot,
        )
        return snapshot

    # ------------------------------------------------------------------
    # Write eligibility: origin, quarantine reason, subsequent authorization
    # ------------------------------------------------------------------

    def _record_observation_origin(
        self,
        event: _CommittedPrototypeEvent,
        *,
        write_blocked: bool,
        origin_path: str,
    ) -> None:
        """Record how an observation entered the runtime, once, at creation."""

        existing = self._write_eligibility.get(event.revision_id)
        if existing is not None:
            return
        self._write_eligibility[event.revision_id] = _ObservationWriteEligibility(
            revision_id=event.revision_id,
            origin_write_blocked=write_blocked,
            origin_path=origin_path,
        )

    def _record_quarantine_reason(self, revision_id: UUID, reason: str) -> None:
        record = self._write_eligibility.get(revision_id)
        if record is None or record.quarantine_reason is not None:
            return
        self._write_eligibility[revision_id] = replace(record, quarantine_reason=reason)

    def _grant_write_authorization(
        self,
        revision_id: UUID,
        *,
        authority: str,
        granting_revision_id: UUID | None,
        basis: Mapping[str, object],
    ) -> None:
        """Record a verifiable grant from an execution permitted to write.

        Only callers that are themselves running with the long-term write unblocked
        may grant.  The basis hash lets a later audit recompute what the grant was
        made on, instead of trusting that a rebuild agreed with it.
        """

        record = self._write_eligibility.get(revision_id)
        if record is None:
            raise ValueError("write authorization has no observation origin")
        if record.origin_write_blocked:
            grantor = (
                self._write_eligibility.get(granting_revision_id)
                if granting_revision_id is not None
                else None
            )
            if (
                authority != "ccrr_habit_change_promotion"
                or grantor is None
                or grantor.origin_write_blocked
                or granting_revision_id not in self._observed_events
                or basis.get("conclusion") != HabitStateConclusion.HABIT_CHANGE.value
            ):
                raise ValueError("blocked observation requires a live unblocked CCRR authority")
        basis_json = json.dumps(basis, sort_keys=True)
        grant = _WriteAuthorization(
            authority=authority,
            granting_revision_id=granting_revision_id,
            granted_at_observation_count=self.observation_count,
            basis_sha256=content_sha256(basis),
            basis_json=basis_json,
        )
        if grant in record.authorizations:
            return
        self._write_eligibility[revision_id] = replace(
            record, authorizations=(*record.authorizations, grant)
        )

    def _observation_write_eligible(self, revision_id: UUID) -> bool:
        """Fail closed: an observation with no origin record may not be committed."""

        if any(
            c.corrected_event.revision_id == revision_id for c in self._correction_cancellations
        ):
            return False
        record = self._write_eligibility.get(revision_id)
        if record is None or not record.write_eligible:
            return False
        if record.parent_revision_id is not None:
            parent = self._write_eligibility.get(record.parent_revision_id)
            return (
                parent is not None
                and self._observation_write_eligible(parent.revision_id)
                and content_sha256(parent) == record.parent_eligibility_sha256
                and any(
                    grant.authority == "formal_correction_transaction"
                    and grant.granting_revision_id == record.parent_revision_id
                    and grant.basis_sha256 == record.correction_outcome_sha256
                    for grant in record.authorizations
                )
                and any(
                    outcome.corrected_revision_id == revision_id
                    and outcome.superseded_revision_id == record.parent_revision_id
                    and outcome.evidence_source_record_ids
                    == record.correction_evidence_source_record_ids
                    and content_sha256(outcome) == record.correction_outcome_sha256
                    for outcome in self._revision_transactions
                )
            )
        if not record.origin_write_blocked:
            return True
        for grant in record.authorizations:
            grantor = (
                self._write_eligibility.get(grant.granting_revision_id)
                if grant.granting_revision_id is not None
                else None
            )
            basis = json.loads(grant.basis_json)
            if (
                grant.authority == "ccrr_habit_change_promotion"
                and grantor is not None
                and not grantor.origin_write_blocked
                and grant.granting_revision_id in self._observed_events
                and basis.get("conclusion") == HabitStateConclusion.HABIT_CHANGE.value
                and content_sha256(basis) == grant.basis_sha256
            ):
                return True
        return False

    @property
    def revision_transactions(self) -> tuple[EventRevisionOutcome, ...]:
        """Committed operations only; rolled-back attempts leave no audit record."""

        return self._revision_transactions

    def observation_write_eligibility(self, revision_id: UUID) -> Mapping[str, object] | None:
        """Read-only audit view of one observation's write lineage."""

        record = self._write_eligibility.get(revision_id)
        if record is None:
            return None
        return {
            "revision_id": str(record.revision_id),
            "origin_write_blocked": record.origin_write_blocked,
            "origin_path": record.origin_path,
            "quarantine_reason": record.quarantine_reason,
            "write_eligible": (
                revision_id in self._observed_events
                and self._observation_write_eligible(revision_id)
            ),
            "historical_write_eligible": self._observation_write_eligible(revision_id),
            "parent_revision_id": (
                str(record.parent_revision_id) if record.parent_revision_id is not None else None
            ),
            "parent_eligibility_sha256": record.parent_eligibility_sha256,
            "correction_evidence_source_record_ids": tuple(
                str(item) for item in record.correction_evidence_source_record_ids
            ),
            "correction_outcome_sha256": record.correction_outcome_sha256,
            "active": revision_id in self._observed_events,
            "authorizations": tuple(
                {
                    "authority": grant.authority,
                    "granting_revision_id": (
                        str(grant.granting_revision_id)
                        if grant.granting_revision_id is not None
                        else None
                    ),
                    "granted_at_observation_count": grant.granted_at_observation_count,
                    "basis_sha256": grant.basis_sha256,
                    "basis": json.loads(grant.basis_json),
                }
                for grant in record.authorizations
            ),
        }

    @property
    def late_feedback_relocations(self) -> tuple[_LateFeedbackRelocation, ...]:
        """Every feedback accepted against a superseded but published binding."""

        return tuple(self._late_feedback_relocations)

    def published_revision_bindings(
        self, revision_id: UUID
    ) -> tuple[_PublishedRevisionBinding, ...]:
        """Every binding this runtime published for ``revision_id``, in order."""

        return self._revision_binding_history.get(revision_id, ())

    def _publish_revision_binding(
        self, revision_id: UUID, *, location_id: UUID, snapshot: BeliefSnapshot
    ) -> None:
        """Publish one binding and append it to the revision's verifiable history."""

        self._revision_feedback_bindings[revision_id] = (location_id, snapshot.snapshot_id)
        history = self._revision_binding_history.get(revision_id, ())
        published = _PublishedRevisionBinding(
            location_id=location_id,
            snapshot_id=snapshot.snapshot_id,
            map_version=snapshot.map_version,
            observation_count=self.observation_count,
        )
        if history and history[-1] == published:
            return
        self._revision_binding_history[revision_id] = (*history, published)

    def _rebuild_personalized_models(
        self, *, replay_assessments: list[Any] | None = None
    ) -> BeliefSnapshot:
        previous_committed = dict(self._committed_events)
        (
            recomputed_active_regime,
            replayed_regimes,
            committed_observation_ids,
            quarantined_observation_ids,
        ) = self._recompute_active_regime(replay_assessments=replay_assessments)
        desired_observations = {
            revision_id: self._observed_events[revision_id]
            for revision_id in committed_observation_ids
        }
        demoted_observation_ids = {
            revision_id
            for revision_id, event in previous_committed.items()
            if event.regime_frame is not None and revision_id not in committed_observation_ids
        }
        invalid_derived_ids = set(
            self._derived_descendants_in(
                previous_committed,
                demoted_observation_ids,
            )
        )
        for revision_id in invalid_derived_ids:
            if self._derived_event_lifecycle.get(revision_id) is DerivedEvidenceLifecycle.ACTIVE:
                self._derived_event_lifecycle[revision_id] = (
                    DerivedEvidenceLifecycle.SUSPENDED_PARENT_QUARANTINED
                )
        for revision_id, event in previous_committed.items():
            if revision_id in demoted_observation_ids or revision_id in invalid_derived_ids:
                self._retract_event_hybrid(event)
        for revision_id, event in desired_observations.items():
            if revision_id not in previous_committed and event.statistical_owner_weight > 1e-12:
                event = self._ingest_event_hybrid(event)
                desired_observations[revision_id] = event
                self._observed_events[revision_id] = event
        retained_derived = {
            revision_id: event
            for revision_id, event in previous_committed.items()
            if event.regime_frame is None and revision_id not in invalid_derived_ids
        }
        restored_derived_ids: set[UUID] = set()
        if (
            self.loop_config.derived_reactivation_policy
            is DerivedEvidenceReactivationPolicy.RESTORE_PRIOR_DERIVED
        ):
            available_parents = set(desired_observations) | set(retained_derived)
            pending_restore = {
                revision_id: event
                for revision_id, event in self._derived_event_archive.items()
                if revision_id not in retained_derived
                and self._derived_event_lifecycle.get(revision_id)
                is DerivedEvidenceLifecycle.SUSPENDED_PARENT_QUARANTINED
            }
            restored_one = True
            while restored_one:
                restored_one = False
                for revision_id, event in sorted(
                    tuple(pending_restore.items()),
                    key=lambda item: (
                        item[1].evidence.event_time,
                        str(item[0]),
                    ),
                ):
                    if event.derived_from_revision_id not in available_parents:
                        continue
                    restored = self._ingest_event_hybrid(replace(event, belief_snapshot_id=None))
                    retained_derived[revision_id] = restored
                    self._derived_event_archive[revision_id] = restored
                    self._derived_event_lifecycle[revision_id] = DerivedEvidenceLifecycle.ACTIVE
                    restored_derived_ids.add(revision_id)
                    available_parents.add(revision_id)
                    del pending_restore[revision_id]
                    restored_one = True
        for revision_id in desired_observations:
            # Cancellation restores a previously authorized contribution. Keep
            # its original qualification immutable for historical child hashes.
            if any(
                c.parent_event.revision_id == revision_id for c in self._correction_cancellations
            ):
                continue
            if revision_id in previous_committed:
                continue
            # A rebuild may promote an observation only if it was already write
            # eligible -- ``_recompute_active_regime`` withholds the rest.  Record
            # the promotion basis anyway, so no promotion is unaudited.
            self._grant_write_authorization(
                revision_id,
                authority="ccrr_rebuild_replay_promotion",
                granting_revision_id=None,
                basis={
                    "recomputed_active_regime": recomputed_active_regime,
                    "replayed_regime": replayed_regimes.get(revision_id),
                    "observation_log_revision_ids": tuple(
                        str(item)
                        for item in sorted(
                            self._observed_events,
                            key=lambda key: (
                                self._observed_events[key].evidence.event_time,
                                str(key),
                            ),
                        )
                    ),
                    "observation_log_sha256": content_sha256(
                        tuple(
                            str(item)
                            for item in sorted(
                                self._observed_events,
                                key=lambda key: (
                                    self._observed_events[key].evidence.event_time,
                                    str(key),
                                ),
                            )
                        )
                    ),
                },
            )
        self._committed_events = {**desired_observations, **retained_derived}
        self._quarantined_events = [
            self._observed_events[revision_id] for revision_id in quarantined_observation_ids
        ]
        for revision_id, regime_id in replayed_regimes.items():
            if revision_id in self._observed_events:
                event = self._observed_events[revision_id]
                assigned = replace(
                    event,
                    rls_sample=replace(event.rls_sample, regime_id=regime_id),
                )
                self._observed_events[revision_id] = assigned
            if revision_id in self._committed_events:
                self._committed_events[revision_id] = assigned
        ordered = sorted(
            self._committed_events.values(),
            key=lambda event: (event.evidence.event_time, str(event.revision_id)),
        )
        snapshot = self._hybrid_loop.publish_snapshot()
        # Every committed revision must stay addressable by execution feedback.
        # ``_process_transition`` establishes that invariant after each transition and
        # ``_validate_feedback_revision_binding`` depends on it, but this rebuild
        # reconstructs ``_committed_events`` from ``_observed_events``, whose entries
        # never carry a snapshot id.  Re-bind here so one revision does not make every
        # surviving revision unreachable for later late counter-evidence.
        for revision_id, rebuilt in tuple(self._committed_events.items()):
            if rebuilt.belief_snapshot_id is not None and revision_id not in restored_derived_ids:
                continue
            rebound = replace(rebuilt, belief_snapshot_id=snapshot.snapshot_id)
            self._committed_events[revision_id] = rebound
            if revision_id in self._derived_event_archive:
                self._derived_event_archive[revision_id] = rebound
            self._publish_revision_binding(
                revision_id,
                location_id=rebound.location_id,
                snapshot=snapshot,
            )
        self._revision_fault_hook("hybrid")
        habit = self._new_habit_model()
        for event in ordered:
            habit.update_audited(event.evidence, weight_multiplier=event.propensity_weight)
        self._habit = habit
        self._revision_fault_hook("dirichlet")
        regimes = self._new_regime_bank()
        for event in ordered:
            regimes.update(event.rls_sample, self._embeddings)
        regimes.set_regime(
            object_instance_id=self.object_instance_id,
            actor_id=self.owner_key,
            regime_id=recomputed_active_regime,
        )
        self._regimes = regimes
        self._revision_fault_hook("rls")
        return snapshot

    def _recompute_active_regime(
        self,
        *,
        replay_assessments: list[Any] | None = None,
    ) -> tuple[str, dict[UUID, str], set[UUID], list[UUID]]:
        """Fresh replay the observation log into regime and storage classifications."""

        self._automatic_regimes = self._new_automatic_regime_router()
        replay_habit = self._new_habit_model()
        replay_regimes = self._new_regime_bank()
        previous_location: UUID | None = None
        replayed_regimes: dict[UUID, str] = {}
        committed_revision_ids: set[UUID] = set()
        pending_events: list[_CommittedPrototypeEvent] = []
        withheld_revision_ids: list[UUID] = []
        ordered = sorted(
            self._observed_events.values(),
            key=lambda event: (event.evidence.event_time, str(event.revision_id)),
        )

        def commit_for_replay(event: _CommittedPrototypeEvent, regime_id: str) -> None:
            assigned = replace(
                event,
                rls_sample=replace(event.rls_sample, regime_id=regime_id),
            )
            replayed_regimes[event.revision_id] = regime_id
            if not self._observation_write_eligible(event.revision_id):
                # The origin pass had the long-term write administratively blocked
                # and no verified subsequent authorization has been recorded, so a
                # rebuild may not commit it.  ``router_may_grant_long_term_write``
                # is false and ``maximum_unauthorized_long_term_commits`` is 0; a
                # replay agreeing with itself is not an authorization.  The event
                # keeps its quarantine -- it is withheld, never dropped.
                withheld_revision_ids.append(event.revision_id)
                return
            committed_revision_ids.add(event.revision_id)
            replay_habit.update_audited(
                assigned.evidence,
                weight_multiplier=assigned.propensity_weight,
            )
            replay_regimes.update(assigned.rls_sample, self._embeddings)

        for event in ordered:
            assert event.regime_frame is not None
            location_index = self.locations.index(event.location_id)
            context_value = float(event.rls_sample.context_features[0])
            active_before = self._automatic_regimes.ccrr.active_regime(
                object_instance_id=self.object_instance_id,
                actor_id=self.owner_key,
            )
            habit_prediction = replay_habit.predict(
                household_id=event.evidence.metadata.household_id,
                person_id=self.owner_key,
                object_instance_id=self.object_instance_id,
                context_key=event.evidence.context_key,
            )
            rls_scores = replay_regimes.score_candidates(
                object_instance_id=self.object_instance_id,
                actor_id=self.owner_key,
                context_features=np.array([context_value], dtype=float),
                candidate_locations=self.locations,
                location_embeddings=self._embeddings,
                regime_id=active_before,
            )
            dirichlet_surprise = _normalized_predictive_surprise(
                habit_prediction.probabilities[event.location_id],
                len(self.locations),
            )
            rls_residual = min(1.0, abs(1.0 - rls_scores[event.location_id]))
            location_changed = float(
                previous_location is not None and event.location_id != previous_location
            )
            residual_severity = 1.0 - (1.0 - rls_residual) ** 2
            unexpected_move = location_changed * (
                1.0 - (1.0 - dirichlet_surprise) * (1.0 - residual_severity)
            )
            signals = dict(event.regime_frame.signals)
            signals[ChangeCause.ACTOR] = 1.0 - event.owner_mass
            signals[ChangeCause.HABIT] = max(
                unexpected_move,
                self.loop_config.dirichlet_surprise_weight * dirichlet_surprise,
                self.loop_config.rls_residual_weight * rls_residual,
            )
            event = replace(
                event,
                dirichlet_predictive_surprise=dirichlet_surprise,
                rls_residual=rls_residual,
                regime_frame=CauseSignalFrame(
                    timestamp=event.evidence.event_time,
                    signals=signals,
                ),
            )
            self._observed_events[event.revision_id] = event
            if event.regime_frame is None:
                raise AssertionError("regime frame was just constructed")
            assessment = self._automatic_regimes.observe(
                frame=event.regime_frame,
                state_key=f"{event.location_id}|{event.evidence.context_key}",
                context_features=(
                    *(
                        1.0 if index == location_index else 0.0
                        for index in range(len(self.locations))
                    ),
                    tanh(context_value),
                ),
                owner_probability=event.owner_mass,
                evidence_source_record_ids=event.evidence.source_record_ids,
                identity_switch_probability=event.identity_switch_probability,
            )
            if replay_assessments is not None:
                replay_assessments.append(assessment)
            self._last_ccrr_decision = (
                assessment.ccrr_decision.kind.value
                if assessment.ccrr_decision is not None
                else (
                    "deferred"
                    if assessment.conclusion is HabitStateConclusion.INSUFFICIENT_EVIDENCE
                    else "stay"
                )
            )
            active = self._automatic_regimes.ccrr.active_regime(
                object_instance_id=self.object_instance_id,
                actor_id=self.owner_key,
            )
            if assessment.conclusion is HabitStateConclusion.HABIT_CHANGE:
                for pending in pending_events:
                    commit_for_replay(pending, active)
                pending_events.clear()
                commit_for_replay(event, active)
            elif (
                assessment.conclusion is HabitStateConclusion.INSUFFICIENT_EVIDENCE
                and not assessment.allow_long_term_write
            ):
                pending_events.append(event)
                replayed_regimes[event.revision_id] = assessment.old_regime
            else:
                pending_events.clear()
                if assessment.allow_long_term_write:
                    commit_for_replay(event, active)
            previous_location = event.location_id
        self._last_observed_location = previous_location
        quarantined_revision_ids = [
            *withheld_revision_ids,
            *(
                event.revision_id
                for event in pending_events
                if event.revision_id not in withheld_revision_ids
            ),
        ]
        quarantined_revision_ids.sort(
            key=lambda revision_id: (
                self._observed_events[revision_id].evidence.event_time,
                str(revision_id),
            )
        )
        return (
            self._automatic_regimes.ccrr.active_regime(
                object_instance_id=self.object_instance_id,
                actor_id=self.owner_key,
            ),
            replayed_regimes,
            committed_revision_ids,
            quarantined_revision_ids,
        )

    def _revision_result(
        self,
        *,
        operations: tuple[PrototypeStatisticOperation, ...],
        evidence_source_record_ids: tuple[UUID, ...],
        snapshot: BeliefSnapshot,
        old_regime: str,
        rationale: str,
        feedback_posterior_probability: float | None = None,
    ) -> PrototypeRevisionResult:
        return PrototypeRevisionResult(
            statistic_operations=operations,
            evidence_source_record_ids=evidence_source_record_ids,
            map_version=snapshot.map_version,
            snapshot_id=snapshot.snapshot_id,
            suggested_location_id=self._current_suggestion(),
            old_regime=old_regime,
            new_regime=self.active_regime,
            change_probability=0.0,
            ccrr_conclusion=self._last_ccrr_decision,
            rationale=rationale,
            feedback_posterior_probability=feedback_posterior_probability,
        )

    def _current_suggestion(self) -> UUID:
        if self._last_household_id is None:
            return max(self.locations, key=str)
        prediction = self._habit.predict(
            household_id=self._last_household_id,
            person_id=self.owner_key,
            object_instance_id=self.object_instance_id,
            context_key=self._last_context_key,
        )
        scores = self._regimes.score_candidates(
            object_instance_id=self.object_instance_id,
            actor_id=self.owner_key,
            context_features=np.array([self._last_context_value], dtype=float),
            candidate_locations=self.locations,
            location_embeddings=self._embeddings,
        )
        return max(
            self.locations,
            key=lambda location: (
                prediction.probabilities[location],
                scores[location],
                str(location),
            ),
        )

    def _validate_transition(self, transition: PrototypeTransition) -> None:
        if transition.after.detected_object_instance_id != self.object_instance_id:
            raise ValueError("after detection does not match the prototype object")
        if transition.before.detected_object_instance_id != self.object_instance_id:
            raise ValueError("before detection does not match the prototype object")
        if transition.after.detected_location_id not in self.locations:
            raise ValueError("after location is outside the prototype candidate set")
        if transition.after.observation_opportunity_id != transition.opportunity.metadata.record_id:
            raise ValueError("after detection is not bound to the supplied opportunity")
        if not transition.context_key.strip():
            raise ValueError("context_key must be non-empty")

    @staticmethod
    def _actor_posterior(
        history: EventHypothesisHistory,
        result: MessagePassingResult,
    ) -> dict[str, float]:
        mass: dict[str, float] = defaultdict(float)
        hypotheses = {item.hypothesis_id: item for item in history.latest.hypotheses}
        for hypothesis_id, probability in result.posterior_by_hypothesis_id.items():
            hypothesis = hypotheses[hypothesis_id]
            mass[hypothesis.responsible_actor_key] += probability
        # Full actor marginal: known-mechanism chains plus the actor-conditional
        # mass inside the unknown-mechanism bucket. Only globally unresolved event
        # mass is unattributable and therefore assigned to unknown_actor.
        for actor, conditional in result.unknown_mechanism_actor_posterior.items():
            mass[actor] += result.unknown_mechanism_probability * conditional
        mass[HierarchicalDirichletHabitModel.UNKNOWN_ACTOR] += result.unresolved_probability
        total = sum(mass.values())
        if total <= 0.0:
            return {HierarchicalDirichletHabitModel.UNKNOWN_ACTOR: 1.0}
        return {actor: probability / total for actor, probability in mass.items()}
