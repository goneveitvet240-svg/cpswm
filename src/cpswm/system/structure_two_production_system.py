"""Public production assembly for the seven Structure-Two operators.

The project historically had two separate integration surfaces: the reusable
``CorePrototypeSpine`` for the memory/revision path and evaluator-local glue for
CIAV/OPCEU.  This module owns one public runtime object that constructs both.
It deliberately delegates to the existing implementations instead of copying
their algorithms.
"""

from __future__ import annotations

import hashlib
import importlib
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from threading import RLock, get_ident
from time import perf_counter_ns
from typing import Any, Final, cast, overload
from uuid import NAMESPACE_URL, UUID, uuid5

from cpswm.contracts import (
    ActiveObservationPlan,
    ActorEvidenceTrack,
    ActorResponsibilityEvidence,
    EvidenceFactorConsumptionTrace,
    ObservationDetectionResult,
    ObservationOutcome,
    SourceType,
)
from cpswm.system.continual.execution_feedback_projector import ExecutionFeedbackProjector
from cpswm.system.continual.project_one_regime_loop import PrototypeLoopConfig
from cpswm.system.counterfactual_event_hypergraph import (
    OpenWorldRoleConditionedReversibleEventRevisionEngine,
    ProjectTwoFeedbackRevisionLoop,
    ProvenanceConstrainedMessagePassing,
)
from cpswm.system.prototype_spine import (
    ActionReadoutConfig,
    CorePrototypeSpine,
    FastActionVerificationReceipt,
    PrototypeStepResult,
    PrototypeTransition,
    _message_passing_state_descriptor,
    _TransitionTraceRecorder,
)
from cpswm.system.reproducibility import content_sha256, content_uuid
from cpswm.system.structure_two_adaptive_runtime import (
    AdaptiveAuthorizationPolicy,
    AdaptiveCIAVRuntimeInput,
    AdaptiveDebtStatus,
    AdaptiveExecutionContext,
    AdaptivePathSelectionReceipt,
    AdaptiveRouterFeatures,
    AdaptiveStepResult,
    select_adaptive_path,
    select_evaluation_direct_p5,
)
from cpswm.system.structure_two_execution import (
    STRUCTURE_TWO_OPERATOR_ORDER,
    AdaptiveInferenceDebtCertificate,
    RuntimeOperatorName,
    StructureTwoExecutionPlan,
    TraceSink,
    UnsupportedStructureTwoExecutionPlan,
    _restore_runtime_rlock_depth,
    _runtime_rlock_depth,
    bind_runtime_callable,
    registered_adaptive_execution_plan,
    seal_adaptive_inference_debt,
)
from cpswm.world_model.grounded_search import (
    CauseInformationActiveVerificationPlanner,
    CIAVOPCEUObservationLoop,
    StructureTwoCauseBelief,
)
from cpswm.world_model.grounded_search.ciav_opceu_loop import CIAVOPCEUReceipt
from cpswm.world_model.habits_transitions import PropensityCorrectionMode

PRODUCTION_SYSTEM_VERSION: Final = "structure-two-production-system@0.2"
PRODUCTION_OPERATOR_ORDER: Final = STRUCTURE_TWO_OPERATOR_ORDER
PRODUCTION_FEEDBACK_EDGE: Final = "ciav->opceu->orrer_cheh->pchmp->cf_bocpd->ccrr->rgrc"
REGISTERED_OPERATOR_OVERRIDE_TYPES: Final = {
    "pchmp": frozenset(
        {
            "cpswm.system.evaluation_operations.project_two_ablation.PriorOnlyMessagePassing",
            "cpswm.system.evaluation_operations.project_two_ablation.IndependentEvidenceMessagePassing",
            "cpswm.system.evaluation_operations.project_two_ablation.EvaluatorNoDedupMessagePassing",
            "cpswm.system.evaluation_operations.project_two_ablation.EvaluatorNoProvenanceFirewallMessagePassing",
        }
    )
}


@dataclass(frozen=True, slots=True)
class ProductionOperatorBinding:
    operator: str
    implementation_symbols: tuple[str, ...]
    source_paths: tuple[str, ...]
    consumes: tuple[str, ...]
    produces: tuple[str, ...]


@dataclass(slots=True)
class _AdaptiveDebtEntry:
    certificate: AdaptiveInferenceDebtCertificate
    transition: PrototypeTransition
    primary_result: PrototypeStepResult | None
    deferred_ciav_input: AdaptiveCIAVRuntimeInput
    origin_core_checkpoint: Mapping[str, object]
    post_origin_core_state_sha256: str | None = None
    status: AdaptiveDebtStatus = AdaptiveDebtStatus.PENDING
    settled_step: int | None = None


@dataclass(frozen=True, slots=True)
class _AdaptiveDebtEntrySnapshot:
    """Rollback state that preserves the live entry and origin-lock identities."""

    entry: _AdaptiveDebtEntry
    certificate: AdaptiveInferenceDebtCertificate
    transition: PrototypeTransition
    primary_result: PrototypeStepResult | None
    deferred_ciav_input: AdaptiveCIAVRuntimeInput
    origin_core_checkpoint: Mapping[str, object]
    post_origin_core_state_sha256: str | None
    status: AdaptiveDebtStatus
    settled_step: int | None


def _snapshot_adaptive_ciav_input(
    value: AdaptiveCIAVRuntimeInput,
) -> AdaptiveCIAVRuntimeInput:
    """Detach mutable caller containers while retaining the bound realizer."""

    return AdaptiveCIAVRuntimeInput(
        actions=tuple(deepcopy(value.actions)),
        consolidation_decision_utilities={
            decision_id: dict(row)
            for decision_id, row in value.consolidation_decision_utilities.items()
        },
        terminal_decision_utilities={
            decision_id: dict(row) for decision_id, row in value.terminal_decision_utilities.items()
        },
        privacy_budget=float(value.privacy_budget),
        opportunity_time=value.opportunity_time,
        actor_likelihoods_by_outcome={
            outcome: dict(row) for outcome, row in value.actor_likelihoods_by_outcome.items()
        },
        expected_detected_location_id=value.expected_detected_location_id,
        selection_probability=float(value.selection_probability),
        p_visible_given_state=float(value.p_visible_given_state),
        p_detect_given_visible=float(value.p_detect_given_visible),
        realizer=value.realizer,
        identity_switch_probability=float(value.identity_switch_probability),
        minimum_net_value=float(value.minimum_net_value),
    )


def _snapshot_adaptive_context(
    context: AdaptiveExecutionContext,
) -> AdaptiveExecutionContext:
    """Create the runtime-owned context used after any untrusted callback runs."""

    features = AdaptiveRouterFeatures.model_validate(
        context.router_features.model_dump(mode="python", round_trip=True, warnings=False)
    )
    ciav_input = (
        _snapshot_adaptive_ciav_input(context.ciav_input)
        if context.ciav_input is not None
        else None
    )
    return AdaptiveExecutionContext(
        router_features=features,
        step_index=int(context.step_index),
        debt_expiry_steps=int(context.debt_expiry_steps),
        ciav_input=ciav_input,
    )


def _snapshot_adaptive_selection(
    selection: AdaptivePathSelectionReceipt,
) -> AdaptivePathSelectionReceipt:
    """Detach the caller-owned selection receipt before callbacks can run."""

    return AdaptivePathSelectionReceipt.model_validate(
        selection.model_dump(mode="python", round_trip=True, warnings=False)
    )


PRODUCTION_OPERATOR_BINDINGS: Final = (
    ProductionOperatorBinding(
        operator="opceu",
        implementation_symbols=(
            "cpswm.world_model.habits_transitions.propensity_correction.ObservationPropensityCorrector",
        ),
        source_paths=("src/cpswm/world_model/habits_transitions/propensity_correction.py",),
        consumes=("observation_opportunity", "visibility_and_detection_propensity"),
        produces=("propensity_weight", "negative_evidence_strength"),
    ),
    ProductionOperatorBinding(
        operator="orrer_cheh",
        implementation_symbols=(
            "cpswm.system.counterfactual_event_hypergraph.engine.OpenWorldRoleConditionedReversibleEventRevisionEngine",
            "cpswm.system.counterfactual_event_hypergraph.feedback_revision_loop.ProjectTwoFeedbackRevisionLoop",
        ),
        source_paths=(
            "src/cpswm/system/counterfactual_event_hypergraph/engine.py",
            "src/cpswm/system/counterfactual_event_hypergraph/feedback_revision_loop.py",
        ),
        consumes=("before_after_observation", "execution_feedback"),
        produces=("reversible_event_hypotheses", "revision_lineage"),
    ),
    ProductionOperatorBinding(
        operator="pchmp",
        implementation_symbols=(
            "cpswm.system.counterfactual_event_hypergraph.hypothesis_message_passing.ProvenanceConstrainedMessagePassing",
        ),
        source_paths=(
            "src/cpswm/system/counterfactual_event_hypergraph/hypothesis_message_passing.py",
        ),
        consumes=("event_hypothesis_set", "provenance_scoped_evidence"),
        produces=("event_posterior", "actor_role_posterior"),
    ),
    ProductionOperatorBinding(
        operator="cf_bocpd",
        implementation_symbols=(
            "cpswm.world_model.habits_transitions.joint_cause_bocpd.JointCauseFactorizedBOCPD",
        ),
        source_paths=("src/cpswm/world_model/habits_transitions/joint_cause_bocpd.py",),
        consumes=("cause_signal_frame", "prefix_online_history"),
        produces=("joint_cause_run_length_posterior",),
    ),
    ProductionOperatorBinding(
        operator="ccrr",
        implementation_symbols=(
            "cpswm.system.continual.project_one_regime_loop.AutomaticCFBOCPDCCRRRouter",
            "cpswm.world_model.habits_transitions.context_conditioned_regime.ContextConditionedRegimeReactivator",
        ),
        source_paths=(
            "src/cpswm/system/continual/project_one_regime_loop.py",
            "src/cpswm/world_model/habits_transitions/context_conditioned_regime.py",
        ),
        consumes=("cause_run_length_posterior", "context_fingerprint"),
        produces=("stay_create_reactivate_or_unresolved_decision",),
    ),
    ProductionOperatorBinding(
        operator="rgrc",
        implementation_symbols=(
            "cpswm.system.prototype_spine.CorePrototypeSpine",
            "cpswm.system.continual.hybrid_statistics.HybridStatisticLedger",
        ),
        source_paths=(
            "src/cpswm/system/prototype_spine.py",
            "src/cpswm/system/continual/hybrid_statistics.py",
        ),
        consumes=("authorized_evidence_cluster_statistic_bundle", "regime_decision"),
        produces=("quarantine_promote_retract_replay_ledger", "belief_snapshot"),
    ),
    ProductionOperatorBinding(
        operator="ciav",
        implementation_symbols=(
            "cpswm.world_model.grounded_search.active_verification.CauseInformationActiveVerificationPlanner",
            "cpswm.world_model.grounded_search.ciav_opceu_loop.CIAVOPCEUObservationLoop",
        ),
        source_paths=(
            "src/cpswm/world_model/grounded_search/active_verification.py",
            "src/cpswm/world_model/grounded_search/ciav_opceu_loop.py",
        ),
        consumes=("cause_belief", "task_utility", "privacy_and_action_costs"),
        produces=("verification_plan", "robot_visible_observation_evidence"),
    ),
)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _runtime_type_symbol(value: object) -> str:
    value_type = type(value)
    return f"{value_type.__module__}.{value_type.__qualname__}"


def _authority_descriptor(authority: object | None) -> dict[str, object] | None:
    if authority is None:
        return None
    state: dict[str, object] = {}
    for name, value in vars(authority).items():
        if isinstance(value, bytes):
            state[name] = hashlib.sha256(value).hexdigest()
        elif isinstance(value, (str, int, float, bool, UUID)) or value is None:
            state[name] = value
        else:
            state[name] = {"type": _runtime_type_symbol(value)}
    return {
        "type": _runtime_type_symbol(authority),
        "key_id": getattr(authority, "key_id", None),
        "formal_grade": getattr(authority, "formal_grade", None),
        "public_key_sha256": getattr(authority, "public_key_sha256", None),
        "attribute_names": sorted(vars(authority)),
        "state": state,
    }


def _evidence_factor_trace_state(
    trace: EvidenceFactorConsumptionTrace,
) -> dict[str, object]:
    return {
        "attribute_names": sorted(vars(trace)),
        "receipts": trace.receipts,
        "factors": sorted(trace._factors.items()),
        "idempotency": sorted(trace._idempotency.items()),
        "likelihood_consumptions": sorted(trace._likelihood_consumptions),
        "cluster_likelihood_models": sorted(
            (str(key), value) for key, value in trace._cluster_likelihood_models.items()
        ),
        "record_payload_hashes": sorted(
            (str(key), value) for key, value in trace._record_payload_hashes.items()
        ),
        "audit": trace.audit_payload(),
    }


def _resolve_symbol(qualified_name: str) -> type[Any]:
    module_name, symbol_name = qualified_name.rsplit(".", 1)
    symbol = getattr(importlib.import_module(module_name), symbol_name, None)
    if not isinstance(symbol, type):
        raise ValueError(f"production operator symbol is not a class: {qualified_name}")
    return symbol


def build_production_assembly_manifest(repository_root: Path) -> dict[str, Any]:
    """Bind the complete operator graph, transitive sources, and environment lock."""

    root = repository_root.resolve()
    runtime = StructureTwoProductionSystem(
        owner_key="production-manifest-owner",
        object_instance_id=UUID("00000000-0000-4000-8000-000000000201"),
        locations=(
            UUID("00000000-0000-4000-8000-000000000211"),
            UUID("00000000-0000-4000-8000-000000000212"),
            UUID("00000000-0000-4000-8000-000000000213"),
        ),
        authorization_scope_id=UUID("00000000-0000-4000-8000-000000000221"),
    )
    runtime.verify_runtime_assembly()
    runtime_instances = runtime.runtime_operator_instances()
    rows: list[dict[str, Any]] = []
    for binding in PRODUCTION_OPERATOR_BINDINGS:
        if len(binding.implementation_symbols) != len(binding.source_paths):
            raise ValueError(f"production binding arity mismatch: {binding.operator}")
        sources = []
        runtime_types = [
            f"{type(item).__module__}.{type(item).__qualname__}"
            for item in runtime_instances[binding.operator]
        ]
        for qualified_name, source_path_text in zip(
            binding.implementation_symbols,
            binding.source_paths,
            strict=True,
        ):
            symbol = _resolve_symbol(qualified_name)
            if f"{symbol.__module__}.{symbol.__qualname__}" not in runtime_types:
                raise ValueError(f"production runtime does not own bound symbol: {qualified_name}")
            source_path = Path(source_path_text)
            resolved = (root / source_path).resolve()
            if (
                source_path.is_absolute()
                or ".." in source_path.parts
                or not resolved.is_relative_to(root)
                or not resolved.is_file()
            ):
                raise ValueError(f"production source is not repository-local: {source_path}")
            sources.append({"path": source_path_text, "sha256": _file_sha256(resolved)})
        rows.append(
            {
                "operator": binding.operator,
                "runtime_types": runtime_types,
                "sources": sources,
                "consumes": list(binding.consumes),
                "produces": list(binding.produces),
            }
        )
    backbone_paths = (
        "src/cpswm/system/structure_two_production_system.py",
        "src/cpswm/system/structure_two_execution.py",
        "src/cpswm/system/prototype_spine.py",
        "src/cpswm/system/continual/project_one_regime_loop.py",
    )
    transitive_source_paths = tuple(
        path.relative_to(root).as_posix() for path in sorted((root / "src/cpswm").rglob("*.py"))
    )
    for relative in transitive_source_paths:
        source = root / relative
        if not source.resolve().is_relative_to(root) or any(
            p.is_symlink() for p in (source, *source.parents) if p.is_relative_to(root)
        ):
            raise ValueError("production transitive source must be a local regular file")
    transitive_source_rows = [
        {"path": path, "sha256": _file_sha256(root / path)} for path in transitive_source_paths
    ]
    environment_lock_paths = ("pyproject.toml", "uv.lock")
    if any(not (root / path).is_file() for path in environment_lock_paths):
        raise FileNotFoundError("production environment lock source is missing")
    if any((root / path).is_symlink() for path in environment_lock_paths):
        raise ValueError("production environment lock refuses symlinks")
    environment_lock_rows = [
        {"path": path, "sha256": _file_sha256(root / path)} for path in environment_lock_paths
    ]
    manifest: dict[str, Any] = {
        "system_version": PRODUCTION_SYSTEM_VERSION,
        "assembly_class": (
            "cpswm.system.structure_two_production_system.StructureTwoProductionSystem"
        ),
        "operator_order": list(PRODUCTION_OPERATOR_ORDER),
        "operators": rows,
        "forward_edges": [
            f"{left}->{right}" for left, right in pairwise(PRODUCTION_OPERATOR_ORDER)
        ],
        "feedback_edge": PRODUCTION_FEEDBACK_EDGE,
        "single_runtime_object_owns_all_operator_instances": True,
        "runtime_assembly_verified": True,
        "backbone_sources": [
            {"path": path, "sha256": _file_sha256(root / path)} for path in backbone_paths
        ],
        # Freezing the entire package is intentionally stricter than a hand-maintained
        # direct-import list: Structure One and other transitive method dependencies
        # cannot change while leaving the Structure Two assembly identity unchanged.
        "transitive_source_bundle": {
            "scope": "all_repository_cpswm_python_sources",
            "files": transitive_source_rows,
            "content_sha256": content_sha256(transitive_source_rows),
        },
        "environment_lock_bundle": {
            "scope": "project_and_resolved_python_dependency_lock",
            "files": environment_lock_rows,
            "content_sha256": content_sha256(environment_lock_rows),
        },
    }
    manifest["content_sha256"] = content_sha256(manifest)
    return manifest


def verify_production_assembly_manifest(manifest: Mapping[str, Any], repository_root: Path) -> None:
    """Fail closed on schema, wiring, symbol, path, or checked-out byte drift."""

    expected = build_production_assembly_manifest(repository_root)
    if dict(manifest) != expected:
        raise ValueError("Structure-Two production assembly manifest mismatch")


class StructureTwoProductionSystem:
    """One public runtime that owns all seven production operator instances."""

    system_version = PRODUCTION_SYSTEM_VERSION

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
        feedback_retraction_threshold: float = 0.0,
        feedback_reactivation_threshold: float = 0.5,
        evidence_factor_trace: EvidenceFactorConsumptionTrace | None = None,
        adaptive_authorization_policy: AdaptiveAuthorizationPolicy | None = None,
    ) -> None:
        self._execution_lock = RLock()
        self._execution_contract_active = False
        self._adaptive_debt_ledger: dict[UUID, _AdaptiveDebtEntry] = {}
        self._adaptive_replay_authorized_debt_ids: set[UUID] = set()
        self._adaptive_last_step = -1
        self._adaptive_authorization_policy = adaptive_authorization_policy or (
            AdaptiveAuthorizationPolicy(policy_id="DENY_UNTIL_EXPLICITLY_CONFIGURED")
        )
        self.core = CorePrototypeSpine(
            owner_key=owner_key,
            object_instance_id=object_instance_id,
            locations=locations,
            authorization_scope_id=authorization_scope_id,
            correction_mode=correction_mode,
            loop_config=loop_config,
            event_engine=event_engine,
            message_passing=message_passing,
            rgrc_gate_enabled=rgrc_gate_enabled,
            action_readout=action_readout,
        )
        self.core._external_mutation_guard = self._require_core_public_mutation_permission
        self.feedback_revision_loop = ProjectTwoFeedbackRevisionLoop(
            projector=ExecutionFeedbackProjector(),
            engine=self.core._event_engine,
            message_passing=self.core._message_passing,
            retraction_threshold=feedback_retraction_threshold,
            reactivation_threshold=feedback_reactivation_threshold,
        )
        self.cause_information_planner = CauseInformationActiveVerificationPlanner()
        self.ciav_opceu_loop = CIAVOPCEUObservationLoop(evidence_factor_trace)
        self._assembly_components = (
            self.core,
            self.core._event_engine,
            self.core._message_passing,
            self.feedback_revision_loop,
            self.cause_information_planner,
            self.ciav_opceu_loop,
        )
        self.core._production_operator_contract = self._runtime_operator_instances_for_execution
        self._feedback_input_journal: dict[UUID, str] = {}

    def _require_core_public_mutation_permission(self) -> None:
        """Block public core writes while production inference debt is pending."""

        pending = any(
            entry.status is AdaptiveDebtStatus.PENDING
            for entry in self._adaptive_debt_ledger.values()
        )
        if not pending:
            return
        # Internal nested mutations made by the currently executing adaptive
        # transaction are part of that transaction.  A legacy or direct-core
        # caller reaches this guard before the core execution owner is set.
        if (
            self._execution_contract_active
            and self.core._execution_contract_active
            and self.core._execution_owner_thread_id == get_ident()
        ):
            return
        raise RuntimeError(
            "pending adaptive debt blocks legacy and direct-core mutation; "
            "resolve it through replay_adaptive_debt"
        )

    def process_project_two_feedback(
        self,
        *,
        history: Any,
        feedback: Any,
        binding: Any,
        likelihood_model: Any,
        **revision_options: Any,
    ) -> tuple[Any, Any, tuple[Any, ...]]:
        """Atomically consume the existing CHEH feedback and project-one contracts.

        The supplied history must be bound to a currently published core revision.
        This explicit multi-axis route does not replace the caller-policy route or
        reinterpret an uncalibrated negative observation as a retraction.
        """

        with self._execution_lock, self.core._execution_lock:
            self._require_core_public_mutation_permission()
            if self._execution_contract_active:
                raise RuntimeError("feedback cannot reenter an active production transaction")
            self._runtime_operator_instances_for_execution()
            input_hash = content_sha256(
                (history, feedback, binding, likelihood_model, revision_options)
            )
            previous_input = self._feedback_input_journal.get(feedback.metadata.record_id)
            if previous_input is not None and previous_input != input_hash:
                raise ValueError("replayed multi-axis feedback input content differs")
            revision_id = history.latest.revision_id
            actual_history = self.core._event_histories.get(revision_id)
            if actual_history is None or content_sha256(actual_history) != content_sha256(history):
                raise ValueError("feedback history content was not produced by this runtime")
            if (
                previous_input is None
                and revision_id
                != self.core._validate_feedback_revision_binding(
                    feedback=feedback,
                    binding=binding,
                )
            ):
                raise ValueError("feedback history does not match the bound core revision")
            for instance, method in (
                (self.core._message_passing, "infer"),
                (self.core._event_engine, "revise_actor_responsibility"),
                (self.core._event_engine, "reactivate_with_evidence"),
                (self.core._event_engine, "revise_event_mechanism"),
                (self.core._event_engine, "revise_role_binding"),
                (self.core._event_engine, "revise_destination_location"),
            ):
                bind_runtime_callable(
                    runtime_execution_id=self.core.authorization_scope_id,
                    operator="orrer_cheh",
                    binding_slot=1,
                    binding_kind="direct_operator_callable",
                    instance=instance,
                    callable_name=method,
                    require_declared_member=True,
                )
            core_checkpoint = self.core._capture_revision_transaction(include_operator_state=True)
            wrapper_checkpoint = self._capture_execution_wrapper_state()
            try:
                revised, outcome = self.feedback_revision_loop.ingest_feedback(
                    history=history,
                    feedback=feedback,
                    binding=binding,
                    likelihood_model=likelihood_model,
                    owner_key=self.core.owner_key,
                    **revision_options,
                )
                receipts = tuple(
                    self.core.apply_project_one_stat_request(request)
                    for request in outcome.project_one_requests
                )
                if any(receipt.status.value == "rejected" for receipt in receipts):
                    raise ValueError(
                        "multi-axis statistic revision rejected; transaction rolled back"
                    )
                self.core._event_histories[revised.latest.revision_id] = deepcopy(revised)
                self._feedback_input_journal[feedback.metadata.record_id] = input_hash
                return revised, outcome, receipts
            except BaseException:
                self.core._restore_revision_transaction(core_checkpoint)
                self._restore_execution_wrapper_state(wrapper_checkpoint)
                raise

    def _adaptive_router_state_sha256_unlocked(self) -> str:
        debts = tuple(
            (
                str(debt_id),
                entry.status.value,
                entry.certificate.certificate_sha256,
                entry.settled_step,
            )
            for debt_id, entry in sorted(
                self._adaptive_debt_ledger.items(), key=lambda item: str(item[0])
            )
        )
        return content_sha256(
            {
                "system_version": self.system_version,
                "core_state_sha256": self.core._execution_observable_state_sha256(),
                "adaptive_debts": debts,
                "adaptive_replay_authorized_debt_ids": tuple(
                    sorted(str(item) for item in self._adaptive_replay_authorized_debt_ids)
                ),
                "adaptive_last_step": self._adaptive_last_step,
                "adaptive_authorization_policy": (
                    self._adaptive_authorization_policy.model_dump(mode="json")
                ),
            }
        )

    def adaptive_router_state_sha256(self) -> str:
        """Return the exact pre-path state identity required by router features."""

        if self._execution_contract_active:
            raise RuntimeError("adaptive router state cannot be read during execution")
        with self._execution_lock:
            if self._execution_contract_active:
                raise RuntimeError("adaptive router state cannot be read during execution")
            return self._adaptive_router_state_sha256_unlocked()

    def pending_adaptive_debts(self) -> tuple[AdaptiveInferenceDebtCertificate, ...]:
        """Read-only view of currently unresolved production inference debt."""

        with self._execution_lock:
            return tuple(
                entry.certificate
                for _debt_id, entry in sorted(
                    self._adaptive_debt_ledger.items(), key=lambda item: str(item[0])
                )
                if entry.status is AdaptiveDebtStatus.PENDING
            )

    @property
    def adaptive_authorization_policy_sha256(self) -> str:
        """Expose the immutable local policy identity required by feature snapshots."""

        with self._execution_lock:
            return self._adaptive_authorization_policy.content_sha256

    def bind_adaptive_authorization_policy(
        self,
        policy: AdaptiveAuthorizationPolicy,
    ) -> None:
        """Replace the local adaptive policy only outside an active transaction."""

        if self._execution_contract_active:
            raise RuntimeError("adaptive policy mutation is forbidden during execution")
        checked = AdaptiveAuthorizationPolicy.model_validate(policy.model_dump(mode="json"))
        with self._execution_lock:
            if self._execution_contract_active:
                raise RuntimeError("adaptive policy mutation is forbidden during execution")
            self._adaptive_authorization_policy = checked

    def process_adaptive_transition(
        self,
        transition: PrototypeTransition,
        *,
        context: AdaptiveExecutionContext,
        trace_sink: TraceSink,
    ) -> AdaptiveStepResult:
        """Select and execute one P0--P5 path from a frozen visible feature snapshot."""

        context = _snapshot_adaptive_context(context)
        current_state_sha256 = self.adaptive_router_state_sha256()
        if context.router_features.source_state_sha256 != current_state_sha256:
            raise ValueError("adaptive router feature snapshot is stale or foreign")
        if current_state_sha256 not in set(context.router_features.feature_source_sha256s):
            raise ValueError("adaptive router feature sources do not bind the production state")
        policy = self._adaptive_authorization_policy
        if (
            context.router_features.authorization_policy_sha256 != policy.content_sha256
            or policy.content_sha256 not in set(context.router_features.feature_source_sha256s)
        ):
            raise ValueError("adaptive router features do not bind the active authorization policy")
        if (
            context.router_features.memory_transition_authorized
            != policy.memory_transition_authorized
            or context.router_features.privacy_policy_satisfied != policy.privacy_policy_satisfied
            or context.router_features.safety_context_authorized != policy.safety_context_authorized
        ):
            raise ValueError("adaptive router authorization flags differ from runtime policy")
        pending = self.pending_adaptive_debts()
        if context.router_features.outstanding_debt_count != len(pending):
            raise ValueError("adaptive router debt count differs from the production ledger")
        expected_oldest_age = (
            max(context.step_index - min(item.created_step for item in pending), 0)
            if pending
            else 0
        )
        if context.router_features.oldest_debt_age != expected_oldest_age:
            raise ValueError("adaptive router oldest-debt age differs from the production ledger")
        if pending:
            raise RuntimeError(
                "pending adaptive debt must be resolved through replay_adaptive_debt "
                "before a new transition"
            )
        selection = select_adaptive_path(
            context.router_features,
            ciav_runtime_input_available=context.ciav_input is not None,
            debt_expiry_steps=context.debt_expiry_steps,
        )
        if selection.safe_abstain:
            return AdaptiveStepResult(
                path_selection=selection,
                primary_result=None,
                feedback_result=None,
                fast_verification_receipt=None,
                ciav_plan=None,
                ciav_receipt=None,
                debt_certificates=(),
                safe_abstained=True,
                executed_operator_count=0,
                deferred_operator_count=0,
                elapsed_ns_by_operator={},
            )
        assert selection.selected_path_id is not None
        result = self.process_transition(
            transition,
            execution_plan=registered_adaptive_execution_plan(selection.selected_path_id),
            trace_sink=trace_sink,
            adaptive_context=context,
            adaptive_selection=selection,
        )
        if not isinstance(result, AdaptiveStepResult):
            raise RuntimeError("adaptive production execution returned a legacy result")
        return result

    def process_evaluation_direct_p5_transition(
        self,
        transition: PrototypeTransition,
        *,
        context: AdaptiveExecutionContext,
        trace_sink: TraceSink,
    ) -> AdaptiveStepResult:
        """Run P5 directly as an evaluation-only upper-bound probe.

        This entrypoint deliberately does not alter or impersonate the normal
        adaptive router.  It requires a fresh, debt-free, fully authorized
        context with CIAV input, emits a distinct evaluation-only selection
        receipt, and then executes the same production P5 plan and operator
        instances used by debt replay.
        """

        context = _snapshot_adaptive_context(context)
        current_state_sha256 = self.adaptive_router_state_sha256()
        if context.router_features.source_state_sha256 != current_state_sha256:
            raise ValueError("evaluation-only P5 feature snapshot is stale or foreign")
        if self.pending_adaptive_debts():
            raise RuntimeError(
                "evaluation-only direct P5 cannot run while adaptive debt is pending"
            )
        selection = select_evaluation_direct_p5(
            context.router_features,
            ciav_runtime_input_available=context.ciav_input is not None,
        )
        result = self.process_transition(
            transition,
            execution_plan=registered_adaptive_execution_plan("P5_FULL_EAGER"),
            trace_sink=trace_sink,
            adaptive_context=context,
            adaptive_selection=selection,
            _evaluation_direct_p5=True,
        )
        if not isinstance(result, AdaptiveStepResult):
            raise RuntimeError("evaluation-only P5 execution returned a legacy result")
        return result

    def replay_adaptive_debt(
        self,
        debt_id: UUID,
        *,
        step_index: int,
        ciav_input: AdaptiveCIAVRuntimeInput,
        trace_sink: TraceSink,
    ) -> AdaptiveStepResult:
        """Replay one isolated debt from its exact branch point through P5.

        The current implementation deliberately fails closed if any core state
        changed after the debt-origin transaction or if another debt remains
        pending.  It therefore establishes a production replay path, not the
        long-horizon recovery-equivalence claim required by the experiment.
        """

        ciav_input = _snapshot_adaptive_ciav_input(ciav_input)
        if self._execution_contract_active:
            raise RuntimeError("adaptive debt replay is forbidden during execution")
        with self._execution_lock:
            if self._execution_contract_active:
                raise RuntimeError("adaptive debt replay is forbidden during execution")
            # Validate before restoring the historical branch.  Restoring must
            # not silently erase an injected callable and launder the attempt.
            self._runtime_operator_instances_for_execution()
            entry = self._adaptive_debt_ledger.get(debt_id)
            if entry is None:
                raise KeyError(f"unknown adaptive debt: {debt_id}")
            if entry.status is not AdaptiveDebtStatus.PENDING:
                raise ValueError("adaptive debt is not pending")
            if (
                ciav_input.content_sha256 != entry.certificate.deferred_ciav_input_sha256
                or entry.deferred_ciav_input.content_sha256
                != entry.certificate.deferred_ciav_input_sha256
            ):
                raise ValueError("adaptive debt CIAV input commitment mismatch")
            other_pending = tuple(
                candidate_id
                for candidate_id, candidate in self._adaptive_debt_ledger.items()
                if candidate_id != debt_id and candidate.status is AdaptiveDebtStatus.PENDING
            )
            if other_pending:
                raise RuntimeError("isolated debt replay refuses concurrent pending debt")
            if (
                entry.post_origin_core_state_sha256 is None
                or self.core._execution_observable_state_sha256()
                != entry.post_origin_core_state_sha256
            ):
                raise RuntimeError("adaptive debt replay branch has evolved since deferral")
            if step_index <= self._adaptive_last_step:
                raise ValueError("adaptive debt replay step must increase strictly")

            wrapper_checkpoint = self._capture_execution_wrapper_state()
            current_core_checkpoint = self.core._capture_revision_transaction(
                include_operator_state=True
            )
            try:
                policy = self._adaptive_authorization_policy
                if not (
                    policy.memory_transition_authorized
                    and policy.privacy_policy_satisfied
                    and policy.safety_context_authorized
                ):
                    raise PermissionError(
                        "adaptive debt replay is denied by the active runtime policy"
                    )
                self.core._restore_revision_transaction(entry.origin_core_checkpoint)
                self._adaptive_replay_authorized_debt_ids.add(debt_id)
                restored_state_sha256 = self._adaptive_router_state_sha256_unlocked()
                oldest_age = max(step_index - entry.certificate.created_step, 0)
                features = AdaptiveRouterFeatures(
                    source_state_sha256=restored_state_sha256,
                    authorization_policy_sha256=policy.content_sha256,
                    observation_opportunity_coverage=1.0,
                    evidence_conflict_score=0.0,
                    provenance_dependence_score=0.0,
                    actor_ambiguity=0.0,
                    instance_ambiguity=0.0,
                    unknown_mass=0.0,
                    action_margin=0.0,
                    pending_long_term_commit=True,
                    regime_hazard=1.0,
                    outstanding_debt_count=1,
                    oldest_debt_age=oldest_age,
                    maximum_debt_flip_bound=1.0,
                    state_staleness=oldest_age,
                    memory_transition_authorized=True,
                    privacy_policy_satisfied=True,
                    safety_context_authorized=True,
                    feature_extraction_cost_units=0.0,
                    feature_source_sha256s=(
                        restored_state_sha256,
                        policy.content_sha256,
                        entry.certificate.certificate_sha256,
                    ),
                )
                context = AdaptiveExecutionContext(
                    router_features=features,
                    step_index=step_index,
                    debt_expiry_steps=max(
                        entry.certificate.expiry_step - entry.certificate.created_step,
                        1,
                    ),
                    ciav_input=entry.deferred_ciav_input,
                )
                selection = select_adaptive_path(
                    features,
                    ciav_runtime_input_available=True,
                    debt_expiry_steps=context.debt_expiry_steps,
                )
                if selection.selected_path_id != "P5_FULL_EAGER":
                    raise RuntimeError("debt replay did not fail closed to P5")
                result = self.process_transition(
                    entry.transition,
                    execution_plan=registered_adaptive_execution_plan("P5_FULL_EAGER"),
                    trace_sink=trace_sink,
                    adaptive_context=context,
                    adaptive_selection=selection,
                )
                if not isinstance(result, AdaptiveStepResult):
                    raise RuntimeError("adaptive debt replay returned a legacy result")
                return result
            except BaseException:
                self.core._restore_revision_transaction(current_core_checkpoint)
                self._restore_execution_wrapper_state(wrapper_checkpoint)
                raise

    @overload
    def process_transition(
        self,
        transition: PrototypeTransition,
        *,
        execution_plan: None = None,
        trace_sink: None = None,
        adaptive_context: None = None,
        adaptive_selection: None = None,
        _evaluation_direct_p5: bool = False,
    ) -> PrototypeStepResult: ...

    @overload
    def process_transition(
        self,
        transition: PrototypeTransition,
        *,
        execution_plan: StructureTwoExecutionPlan,
        trace_sink: TraceSink,
        adaptive_context: None = None,
        adaptive_selection: None = None,
        _evaluation_direct_p5: bool = False,
    ) -> PrototypeStepResult: ...

    @overload
    def process_transition(
        self,
        transition: PrototypeTransition,
        *,
        execution_plan: StructureTwoExecutionPlan,
        trace_sink: TraceSink,
        adaptive_context: AdaptiveExecutionContext,
        adaptive_selection: AdaptivePathSelectionReceipt,
        _evaluation_direct_p5: bool = False,
    ) -> AdaptiveStepResult: ...

    @overload
    def process_transition(
        self,
        transition: PrototypeTransition,
        *,
        execution_plan: StructureTwoExecutionPlan | None = None,
        trace_sink: TraceSink | None = None,
        adaptive_context: AdaptiveExecutionContext | None = None,
        adaptive_selection: AdaptivePathSelectionReceipt | None = None,
        _evaluation_direct_p5: bool = False,
    ) -> PrototypeStepResult | AdaptiveStepResult: ...

    def process_transition(
        self,
        transition: PrototypeTransition,
        *,
        execution_plan: StructureTwoExecutionPlan | None = None,
        trace_sink: TraceSink | None = None,
        adaptive_context: AdaptiveExecutionContext | None = None,
        adaptive_selection: AdaptivePathSelectionReceipt | None = None,
        _evaluation_direct_p5: bool = False,
    ) -> PrototypeStepResult | AdaptiveStepResult:
        """Run one transition through the selected Architecture-A interface.

        With both optional arguments omitted this remains the historical,
        untraced compatibility entrypoint.  Supplying either requires both and
        delegates the rollback-guarded plan/trace operation to the real core
        runtime.  Cross-system durable atomicity remains a separate failed gate.
        """

        if self._execution_contract_active:
            raise RuntimeError("reentrant or concurrent production execution is forbidden")
        adaptive = bool(
            execution_plan is not None and execution_plan.lane == "registered_adaptive_path"
        )
        if _evaluation_direct_p5 and not adaptive:
            raise ValueError("evaluation-only P5 authorization requires an adaptive P5 plan")
        if adaptive:
            assert execution_plan is not None
            if adaptive_context is None or adaptive_selection is None:
                raise UnsupportedStructureTwoExecutionPlan(
                    "adaptive execution is not yet production-bound without its "
                    "source-bound context and selection receipt"
                )
            adaptive_context = _snapshot_adaptive_context(adaptive_context)
            adaptive_selection = _snapshot_adaptive_selection(adaptive_selection)
            if (
                adaptive_selection.safe_abstain
                or adaptive_selection.selected_path_id != execution_plan.plan_id
                or adaptive_selection.feature_sha256
                != adaptive_context.router_features.content_sha256
            ):
                raise ValueError("adaptive execution plan does not match its router receipt")
        elif adaptive_context is not None or adaptive_selection is not None:
            raise ValueError("legacy execution cannot accept adaptive routing inputs")
        execution_lock = self._execution_lock
        pre_acquire_depth = _runtime_rlock_depth(execution_lock)
        acquire = getattr(execution_lock, "acquire", None)
        if not callable(acquire) or acquire() is not True:
            raise RuntimeError("production execution lock could not be acquired")
        if self._execution_contract_active:
            _restore_runtime_rlock_depth(
                execution_lock,
                pre_acquire_depth,
                verify_unowned_available=False,
            )
            raise RuntimeError("reentrant or concurrent production execution is forbidden")
        self._execution_contract_active = True
        if execution_plan is None and trace_sink is None:
            try:
                return self.core.process_transition(transition)
            finally:
                self._execution_contract_active = False
                try:
                    _restore_runtime_rlock_depth(
                        execution_lock,
                        pre_acquire_depth,
                        verify_unowned_available=False,
                    )
                except RuntimeError as recovery_error:
                    raise RuntimeError(
                        "production execution lock ownership could not be restored"
                    ) from recovery_error
        checkpoint: Mapping[str, object] | None = None
        try:
            checkpoint = self._capture_execution_wrapper_state()
            result = self.core._process_transition_with_runtime_binding(
                transition,
                execution_plan=execution_plan,
                trace_sink=trace_sink,
                runtime_symbol=f"{type(self).__module__}.{type(self).__qualname__}",
                system_version=self.system_version,
                runtime_operator_instances_provider=lambda: (
                    StructureTwoProductionSystem._runtime_operator_instances_for_execution(self)
                ),
                runtime_guard_components_provider=lambda: (
                    StructureTwoProductionSystem._execution_guard_components(self)
                ),
                runtime_guard_state_provider=lambda: (
                    StructureTwoProductionSystem._execution_guard_state_sha256(self)
                ),
                runtime_lock_components_provider=lambda: {
                    "production_execution": self._execution_lock
                },
                adaptive_executor=(
                    (
                        lambda item, recorder: self._execute_adaptive_plan(
                            item,
                            recorder=recorder,
                            context=cast(AdaptiveExecutionContext, adaptive_context),
                            selection=cast(
                                AdaptivePathSelectionReceipt,
                                adaptive_selection,
                            ),
                            evaluation_direct_p5=_evaluation_direct_p5,
                        )
                    )
                    if adaptive
                    else None
                ),
                allow_runtime_state_change_during_operators=adaptive,
            )
        except BaseException as execution_error:
            if checkpoint is not None:
                self._restore_execution_wrapper_state(checkpoint)
            self._execution_contract_active = False
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
                    "production execution lock ownership could not be restored"
                ) from recovery_error
            raise
        else:
            self._execution_contract_active = False
            try:
                _restore_runtime_rlock_depth(
                    execution_lock,
                    pre_acquire_depth,
                    verify_unowned_available=False,
                )
            except RuntimeError as recovery_error:
                raise RuntimeError(
                    "production execution lock ownership could not be restored"
                ) from recovery_error
            return cast(PrototypeStepResult | AdaptiveStepResult, result)

    def _execute_adaptive_plan(
        self,
        transition: PrototypeTransition,
        *,
        recorder: _TransitionTraceRecorder,
        context: AdaptiveExecutionContext,
        selection: AdaptivePathSelectionReceipt,
        evaluation_direct_p5: bool = False,
    ) -> AdaptiveStepResult:
        features = context.router_features
        step_index = context.step_index
        debt_expiry_steps = context.debt_expiry_steps
        ciav_input = context.ciav_input
        if step_index <= self._adaptive_last_step:
            raise ValueError("adaptive production step indices must increase strictly")
        current_state_sha256 = self._adaptive_router_state_sha256_unlocked()
        if features.source_state_sha256 != current_state_sha256:
            raise ValueError("adaptive router state changed before operator execution")
        policy = self._adaptive_authorization_policy
        sources = set(features.feature_source_sha256s)
        if current_state_sha256 not in sources:
            raise ValueError("adaptive router sources omit the current production state")
        if (
            features.authorization_policy_sha256 != policy.content_sha256
            or policy.content_sha256 not in sources
        ):
            raise ValueError("adaptive router sources omit the active authorization policy")
        if (
            features.memory_transition_authorized != policy.memory_transition_authorized
            or features.privacy_policy_satisfied != policy.privacy_policy_satisfied
            or features.safety_context_authorized != policy.safety_context_authorized
        ):
            raise ValueError("adaptive router authorization differs from runtime policy")
        pending_entries = tuple(
            entry
            for entry in self._adaptive_debt_ledger.values()
            if entry.status is AdaptiveDebtStatus.PENDING
        )
        if features.outstanding_debt_count != len(pending_entries):
            raise ValueError("adaptive router debt count differs from the production ledger")
        expected_oldest_age = (
            max(
                step_index - min(entry.certificate.created_step for entry in pending_entries),
                0,
            )
            if pending_entries
            else 0
        )
        if features.oldest_debt_age != expected_oldest_age:
            raise ValueError("adaptive router oldest-debt age differs from the production ledger")
        pending_ids = {entry.certificate.debt_id for entry in pending_entries}
        if pending_ids and pending_ids != self._adaptive_replay_authorized_debt_ids:
            raise RuntimeError("pending adaptive debt cannot be bypassed by a new path execution")
        if selection.feature_sha256 != features.content_sha256:
            raise ValueError("adaptive selection is not bound to the current feature snapshot")
        ciav_input_sha256 = (
            context.ciav_input.content_sha256 if context.ciav_input is not None else None
        )
        expected_selection = (
            select_evaluation_direct_p5(
                features,
                ciav_runtime_input_available=ciav_input is not None,
            )
            if evaluation_direct_p5
            else select_adaptive_path(
                features,
                ciav_runtime_input_available=ciav_input is not None,
                debt_expiry_steps=debt_expiry_steps,
            )
        )
        if selection != expected_selection:
            expected_kind = (
                "evaluation-only direct P5 authorization"
                if evaluation_direct_p5
                else "fresh deterministic routing pass"
            )
            raise ValueError(f"adaptive selection differs from {expected_kind}")
        path_id = recorder.plan.plan_id
        if path_id != selection.selected_path_id:
            raise ValueError("adaptive recorder plan differs from router selection")
        recorder.bind_adaptive_route(
            router_feature_sha256=features.content_sha256,
            router_source_state_sha256=features.source_state_sha256,
            authorization_policy_sha256=policy.content_sha256,
            path_selection_receipt_sha256=selection.receipt_sha256,
            ciav_input_sha256=ciav_input_sha256,
            step_index=step_index,
            debt_expiry_steps=debt_expiry_steps,
        )

        if path_id == "P0_SAFE_DEFERRED":
            return self._execute_p0_safe_deferred(
                transition,
                recorder=recorder,
                context=context,
                selection=selection,
            )

        origin_core_checkpoint = self.core._capture_revision_transaction(
            include_operator_state=True
        )
        ciav_deferred = recorder.mode_for("ciav") == "deferred_with_valid_debt_certificate"
        transition_sha256 = content_sha256(transition)
        replayable_debt_ids = {
            debt_id
            for debt_id, entry in self._adaptive_debt_ledger.items()
            if entry.status is AdaptiveDebtStatus.PENDING
            and debt_id in self._adaptive_replay_authorized_debt_ids
            and entry.certificate.origin_transition_sha256 == transition_sha256
        }
        primary_result = self.core._process_transition(
            transition,
            trace_recorder=recorder,
            force_long_term_write_blocked=True,
            identity_switch_probability=(
                ciav_input.identity_switch_probability
                if ciav_input is not None
                else transition.identity_switch_probability
            ),
        )
        ciav_plan = None
        ciav_receipt = None
        feedback_result = None
        fast_verification_receipt = None
        if ciav_deferred:
            certificate = self._issue_adaptive_debt(
                transition,
                primary_result=primary_result,
                deferred_operators=("ciav",),
                context=context,
                path_id=path_id,
                origin_core_checkpoint=origin_core_checkpoint,
            )
            recorder.record_deferred(
                "ciav",
                raw_input={
                    "primary_revision_id": str(primary_result.event_revision_id),
                    "ciav_runtime_input_available": ciav_input is not None,
                },
                debt_certificate=certificate,
            )
        else:
            if ciav_input is None:
                raise ValueError("P3/P5 execution requires a bound CIAV runtime input")
            recorder.bind_operator(
                "ciav",
                bind_runtime_callable(
                    runtime_execution_id=recorder.runtime_execution_id,
                    operator="ciav",
                    binding_slot=0,
                    binding_kind="adaptive_composite_stage",
                    instance=self,
                    callable_name="_execute_ciav_operator",
                    require_declared_member=True,
                ),
            )
            started_ns = perf_counter_ns()
            ciav_plan, ciav_receipt = self._execute_ciav_operator(
                transition,
                primary_result=primary_result,
                ciav_input=ciav_input,
            )
            if ciav_input.content_sha256 != ciav_input_sha256:
                raise RuntimeError("CIAV runtime input mutated during realization")
            recorder.record_executed(
                "ciav",
                raw_input={
                    "ciav_input_sha256": ciav_input.content_sha256,
                    "primary_revision_id": str(primary_result.event_revision_id),
                    "primary_actor_posterior": dict(primary_result.actor_posterior),
                    "cause_snapshot_sha256": content_sha256(self.core.current_cause_snapshot),
                },
                output={"plan": ciav_plan, "receipt": ciav_receipt},
                consumes=("ccrr", "rgrc"),
                elapsed_ns=perf_counter_ns() - started_ns,
            )
            if (
                ciav_receipt is not None
                and ciav_receipt.detection.outcome is ObservationOutcome.DETECTED
            ):
                recorder.feedback_observation_acquired = True
                if (
                    ciav_receipt.detection.detected_location_id
                    == transition.after.detected_location_id
                ):
                    recorder.feedback_closure_kind = "same_location_fast_verification"
                    recorder.bind_operator(
                        "opceu",
                        bind_runtime_callable(
                            runtime_execution_id=recorder.runtime_execution_id,
                            operator="opceu",
                            binding_slot=1,
                            binding_kind="adaptive_composite_stage",
                            instance=self.core,
                            callable_name="apply_fast_action_verification",
                            require_declared_member=True,
                        ),
                    )
                    started_ns = perf_counter_ns()
                    fast_verification_receipt = self.core.apply_fast_action_verification(
                        revision_id=primary_result.event_revision_id,
                        verified_owner_probability=ciav_receipt.evidence.actor_posterior.get(
                            self.core.owner_key,
                            0.0,
                        ),
                        source_record_id=ciav_receipt.evidence.metadata.record_id,
                    )
                    recorder.record_executed(
                        "opceu",
                        raw_input={
                            "revision_id": str(primary_result.event_revision_id),
                            "source_record_id": str(ciav_receipt.evidence.metadata.record_id),
                        },
                        output=fast_verification_receipt,
                        phase="feedback_closure",
                        elapsed_ns=perf_counter_ns() - started_ns,
                    )
                else:
                    recorder.feedback_closure_kind = "full_transition"
                    feedback_transition = self._ciav_feedback_transition(
                        transition,
                        ciav_receipt=ciav_receipt,
                        primary_actor_posterior=primary_result.actor_posterior,
                    )
                    feedback_result = self.core._process_transition(
                        feedback_transition,
                        trace_recorder=recorder,
                        trace_phase="feedback_closure",
                        identity_switch_probability=ciav_input.identity_switch_probability,
                    )

        if path_id == "P5_FULL_EAGER":
            for debt_id in replayable_debt_ids:
                entry = self._adaptive_debt_ledger[debt_id]
                recorder.replayed_debt_certificates.append(entry.certificate)
                entry.status = AdaptiveDebtStatus.SETTLED
                entry.settled_step = step_index
                self._adaptive_replay_authorized_debt_ids.discard(debt_id)

        self._adaptive_last_step = step_index
        if recorder.adaptive_step_index != self._adaptive_last_step:
            raise RuntimeError("adaptive trace step differs from committed runtime step")
        return self._adaptive_step_result(
            selection=selection,
            recorder=recorder,
            primary_result=primary_result,
            feedback_result=feedback_result,
            fast_verification_receipt=fast_verification_receipt,
            ciav_plan=ciav_plan,
            ciav_receipt=ciav_receipt,
        )

    def _execute_p0_safe_deferred(
        self,
        transition: PrototypeTransition,
        *,
        recorder: _TransitionTraceRecorder,
        context: AdaptiveExecutionContext,
        selection: AdaptivePathSelectionReceipt,
    ) -> AdaptiveStepResult:
        """Run P0 guards, retain raw evidence, and make no long-term memory write."""

        self.core._validate_transition(transition)
        origin_core_checkpoint = self.core._capture_revision_transaction(
            include_operator_state=True
        )
        certificate = self._issue_adaptive_debt(
            transition,
            primary_result=None,
            deferred_operators=("orrer_cheh", "ciav"),
            context=context,
            path_id="P0_SAFE_DEFERRED",
            origin_core_checkpoint=origin_core_checkpoint,
        )
        started_ns = perf_counter_ns()
        propensity = self.core._corrector.weight_for_opportunity(transition.opportunity)
        recorder.record_executed(
            "opceu",
            raw_input=transition.opportunity,
            output=propensity,
            elapsed_ns=perf_counter_ns() - started_ns,
        )
        recorder.record_deferred(
            "orrer_cheh",
            raw_input={
                "before": transition.before,
                "after": transition.after,
                "actor_prior": dict(transition.actor_prior),
                "unresolved_probability": transition.unresolved_probability,
            },
            debt_certificate=certificate,
        )
        # The frozen P0 consumption graph is
        # ``ccrr <- cf_bocpd`` and ``rgrc <- (pchmp, ccrr)``.  Those declared edges are
        # satisfied by passing the produced upstream payloads into the downstream
        # maintenance callables, so the receipted DAG is a real data dependency rather
        # than a caller-side annotation.
        maintenance_outputs: dict[str, Mapping[str, object]] = {}
        maintenance_calls: tuple[
            tuple[str, str, tuple[object, ...] | None, tuple[RuntimeOperatorName, ...]], ...
        ] = (
            ("pchmp", "_adaptive_pchmp_safety_maintenance", (transition,), ()),
            ("cf_bocpd", "_adaptive_cf_bocpd_safety_maintenance", (), ()),
            ("ccrr", "_adaptive_ccrr_safety_maintenance", None, ("cf_bocpd",)),
            ("rgrc", "_adaptive_rgrc_debt_guard", None, ("pchmp", "ccrr")),
        )
        # The runtime -- not the payloads -- owns the transition, debt and execution
        # identity the maintenance nodes are checked against.  Opening the context
        # here is what makes ``provenance_and_dependency_checks_always_executed``
        # a real check instead of a self-consistent hash comparison.
        self.core.bind_adaptive_maintenance_context(
            runtime_execution_id=recorder.runtime_execution_id,
            transition=transition,
            debt_certificate_sha256=certificate.certificate_sha256,
            origin_transition_sha256=certificate.origin_transition_sha256,
        )
        try:
            for operator, callable_name, fixed_args, consumes in maintenance_calls:
                args = (
                    fixed_args
                    if fixed_args is not None
                    else tuple(maintenance_outputs[name] for name in consumes)
                )
                recorder.bind_operator(
                    operator,
                    bind_runtime_callable(
                        runtime_execution_id=recorder.runtime_execution_id,
                        operator=operator,  # type: ignore[arg-type]
                        binding_slot=0,
                        binding_kind="adaptive_safety_maintenance",
                        instance=self.core,
                        callable_name=callable_name,
                        # These four nodes carry the whole write-safety argument of
                        # the deferred path, so the bound callable must be the
                        # core's own declared member, not merely a function that
                        # matches whatever source file it happens to live in.
                        require_declared_member=True,
                    ),
                )
                started_ns = perf_counter_ns()
                output = getattr(self.core, callable_name)(*args)
                maintenance_outputs[operator] = output
                recorder.record_executed(
                    operator,
                    raw_input={
                        "origin_transition_sha256": certificate.origin_transition_sha256,
                        "debt_certificate_sha256": certificate.certificate_sha256,
                        "consumed_operator_output_sha256s": {
                            name: content_sha256(maintenance_outputs[name]) for name in consumes
                        },
                    },
                    output=output,
                    consumes=consumes,
                    elapsed_ns=perf_counter_ns() - started_ns,
                )
        finally:
            self.core.clear_adaptive_maintenance_context()
        recorder.record_deferred(
            "ciav",
            raw_input={"ciav_runtime_input_available": context.ciav_input is not None},
            debt_certificate=certificate,
        )
        self._adaptive_debt_ledger[
            certificate.debt_id
        ].post_origin_core_state_sha256 = self.core._execution_observable_state_sha256()
        self._adaptive_last_step = context.step_index
        return self._adaptive_step_result(
            selection=selection,
            recorder=recorder,
            primary_result=None,
            feedback_result=None,
            fast_verification_receipt=None,
            ciav_plan=None,
            ciav_receipt=None,
        )

    def _issue_adaptive_debt(
        self,
        transition: PrototypeTransition,
        *,
        primary_result: PrototypeStepResult | None,
        deferred_operators: tuple[RuntimeOperatorName, ...],
        context: AdaptiveExecutionContext,
        path_id: str,
        origin_core_checkpoint: Mapping[str, object],
    ) -> AdaptiveInferenceDebtCertificate:
        if context.ciav_input is None:
            raise ValueError("adaptive CIAV deferral requires an exact runtime-input commitment")
        deferred_ciav_input = _snapshot_adaptive_ciav_input(context.ciav_input)
        certificate = seal_adaptive_inference_debt(
            origin_path_id=path_id,
            origin_transition_sha256=content_sha256(transition),
            origin_state_sha256=context.router_features.source_state_sha256,
            created_step=context.step_index,
            expiry_step=context.step_index + context.debt_expiry_steps,
            deferred_operators=deferred_operators,
            deferred_ciav_input_sha256=deferred_ciav_input.content_sha256,
            raw_evidence_content_sha256s=tuple(
                content_sha256(item)
                for item in (
                    transition.opportunity,
                    transition.before,
                    transition.after,
                    *transition.evidence,
                )
            ),
        )
        if certificate.debt_id in self._adaptive_debt_ledger:
            raise RuntimeError("adaptive inference debt identity was already registered")
        self._adaptive_debt_ledger[certificate.debt_id] = _AdaptiveDebtEntry(
            certificate=certificate,
            transition=deepcopy(transition),
            primary_result=deepcopy(primary_result),
            deferred_ciav_input=deferred_ciav_input,
            origin_core_checkpoint=origin_core_checkpoint,
            post_origin_core_state_sha256=self.core._execution_observable_state_sha256(),
        )
        return certificate

    def _execute_ciav_operator(
        self,
        transition: PrototypeTransition,
        *,
        primary_result: PrototypeStepResult,
        ciav_input: AdaptiveCIAVRuntimeInput,
    ) -> tuple[ActiveObservationPlan, CIAVOPCEUReceipt | None]:
        snapshot = self.core.current_cause_snapshot
        if snapshot is None:
            raise RuntimeError("CIAV requires a current CF-BOCPD cause snapshot")
        assert transition.after.detection_time is not None
        if ciav_input.opportunity_time <= transition.after.detection_time:
            raise ValueError("CIAV opportunity must occur after the primary observation")
        belief = StructureTwoCauseBelief.from_snapshot(
            snapshot,
            identity_switch_probability=ciav_input.identity_switch_probability,
        )
        plan = self.cause_information_planner.select(
            belief,
            ciav_input.actions,
            consolidation_decision_utilities={
                key: dict(value)
                for key, value in ciav_input.consolidation_decision_utilities.items()
            },
            terminal_decision_utilities={
                key: dict(value) for key, value in ciav_input.terminal_decision_utilities.items()
            },
            privacy_budget=ciav_input.privacy_budget,
            minimum_net_value=ciav_input.minimum_net_value,
        )
        if not plan.should_act:
            return plan, None
        selected = next(
            (item for item in ciav_input.actions if item.action_id == plan.selected_action_id),
            None,
        )
        if selected is None:
            raise RuntimeError("CIAV planner selected an action outside the frozen candidate set")
        primary_actor_prior = dict(primary_result.actor_posterior)
        if set(primary_actor_prior) != set(transition.actor_prior):
            raise RuntimeError("primary PCHMP actor posterior support drifted before CIAV")
        receipt = self.ciav_opceu_loop.execute_selected_action(
            action=selected,
            update_id=primary_result.event_revision_id,
            household_id=transition.after.metadata.household_id,
            session_id=transition.after.metadata.session_id,
            trace_id=transition.after.metadata.trace_id,
            opportunity_time=ciav_input.opportunity_time,
            object_instance_id=self.core.object_instance_id,
            actor_keys=tuple(actor for actor in transition.actor_prior if actor != "unknown_actor"),
            # CIAV is a sequential observation after the primary PCHMP pass.
            # A neutral new actor likelihood must preserve that pass's posterior
            # instead of resetting the revision to the pre-evidence prior.
            actor_prior=primary_actor_prior,
            actor_likelihoods_by_outcome={
                outcome: dict(values)
                for outcome, values in ciav_input.actor_likelihoods_by_outcome.items()
            },
            location_keys=tuple(str(item) for item in self.core.locations),
            expected_detected_location_id=ciav_input.expected_detected_location_id,
            selection_probability=ciav_input.selection_probability,
            p_visible_given_state=ciav_input.p_visible_given_state,
            p_detect_given_visible=ciav_input.p_detect_given_visible,
            realizer=ciav_input.realizer,
        )
        return plan, receipt

    def _ciav_feedback_transition(
        self,
        transition: PrototypeTransition,
        *,
        ciav_receipt: CIAVOPCEUReceipt,
        primary_actor_posterior: Mapping[str, float],
    ) -> PrototypeTransition:
        detection = ciav_receipt.detection
        if detection.outcome is not ObservationOutcome.DETECTED or detection.detection_time is None:
            raise ValueError("only a detected CIAV observation can enter the transition closure")
        canonical_detection_id = content_uuid(
            "adaptive-ciav-canonical-detection",
            {
                "ciav_detection_id": detection.metadata.record_id,
                "opportunity_id": ciav_receipt.opportunity.metadata.record_id,
            },
        )
        canonical_detection = ObservationDetectionResult.model_validate(
            detection.model_copy(
                update={
                    "metadata": detection.metadata.model_copy(
                        update={
                            "record_id": canonical_detection_id,
                            "schema_name": "cpswm.ObservationDetectionResult",
                            "schema_version": "0.1.0",
                            "source_id": "structure-two-adaptive-ciav-feedback-closure",
                        }
                    )
                }
            ).model_dump(mode="python", round_trip=True, warnings=False)
        )
        actor_posterior = dict(ciav_receipt.evidence.actor_posterior)
        sequential_prior = dict(primary_actor_posterior)
        if set(sequential_prior) != set(transition.actor_prior) or set(actor_posterior) != set(
            sequential_prior
        ):
            raise ValueError("CIAV actor posterior support differs from its sequential prior")
        evidence_id = content_uuid(
            "adaptive-ciav-actor-evidence",
            {
                "opportunity_id": ciav_receipt.opportunity.metadata.record_id,
                "detection_id": canonical_detection.metadata.record_id,
                "actor_posterior": actor_posterior,
            },
        )
        metadata = ciav_receipt.evidence.metadata.model_copy(
            update={
                "record_id": evidence_id,
                "schema_name": "cpswm.ActorResponsibilityEvidence",
                "recorded_time": canonical_detection.detection_time,
                "source_type": SourceType.MODEL,
                "source_id": "structure-two-adaptive-ciav-feedback-closure",
                "model_version": ciav_receipt.opportunity.likelihood_model_id,
            }
        )
        actor_evidence = ActorResponsibilityEvidence(
            metadata=metadata,
            source_detection_result_id=canonical_detection.metadata.record_id,
            object_instance_id=self.core.object_instance_id,
            evidence_time=canonical_detection.detection_time,
            actor_posterior=actor_posterior,
            reference_actor_prior=sequential_prior,
            evidence_cluster_id=uuid5(NAMESPACE_URL, str(evidence_id)),
            effective_sample_weight=1.0,
            evidence_track=ActorEvidenceTrack.MODEL,
            evidence_model_id=ciav_receipt.opportunity.likelihood_model_id,
        )
        return PrototypeTransition(
            opportunity=ciav_receipt.opportunity,
            before=transition.after,
            after=canonical_detection,
            actor_prior=sequential_prior,
            evidence=(actor_evidence,),
            context_key=transition.context_key,
            context_value=transition.context_value,
            unresolved_probability=transition.unresolved_probability,
        )

    @staticmethod
    def _adaptive_step_result(
        *,
        selection: AdaptivePathSelectionReceipt,
        recorder: _TransitionTraceRecorder,
        primary_result: PrototypeStepResult | None,
        feedback_result: PrototypeStepResult | None,
        fast_verification_receipt: FastActionVerificationReceipt | None,
        ciav_plan: ActiveObservationPlan | None,
        ciav_receipt: CIAVOPCEUReceipt | None,
    ) -> AdaptiveStepResult:
        elapsed: dict[str, int] = {}
        for receipt in recorder.receipts:
            if receipt.status == "executed":
                elapsed[receipt.operator] = elapsed.get(receipt.operator, 0) + receipt.elapsed_ns
        return AdaptiveStepResult(
            path_selection=selection,
            primary_result=primary_result,
            feedback_result=feedback_result,
            fast_verification_receipt=fast_verification_receipt,
            ciav_plan=ciav_plan,
            ciav_receipt=ciav_receipt,
            debt_certificates=tuple(recorder.debt_certificates),
            safe_abstained=False,
            executed_operator_count=sum(item.status == "executed" for item in recorder.receipts),
            deferred_operator_count=sum(item.status == "deferred" for item in recorder.receipts),
            elapsed_ns_by_operator=elapsed,
        )

    def _execution_guard_components(self) -> dict[str, object]:
        feedback_loop = self.feedback_revision_loop
        feedback_message_passing = feedback_loop._message_passing
        components: dict[str, object] = {
            "production_system": self,
            "execution_lock": self._execution_lock,
            "core": self.core,
            "feedback_revision_loop": feedback_loop,
            "feedback_projector": feedback_loop._projector,
            "feedback_engine": feedback_loop._engine,
            "feedback_message_passing": feedback_message_passing,
            "cause_information_planner": self.cause_information_planner,
            "ciav_opceu_loop": self.ciav_opceu_loop,
            "evidence_factor_trace": self.ciav_opceu_loop.trace,
        }
        authority = getattr(feedback_message_passing, "_independence_authority", None)
        if authority is not None:
            components["feedback_independence_authority"] = authority
        return components

    def _execution_guard_state_sha256(self) -> str:
        feedback_loop = self.feedback_revision_loop
        feedback_message_passing = feedback_loop._message_passing
        authority = getattr(feedback_message_passing, "_independence_authority", None)
        return content_sha256(
            {
                "attribute_names": sorted(
                    name
                    for name in self.__dict__
                    if name not in {"_execution_contract_active", "_execution_lock"}
                ),
                "system_version": self.system_version,
                "execution_contract_active": self._execution_contract_active,
                "feedback_input_journal": dict(self._feedback_input_journal),
                "execution_lock": {
                    "type": _runtime_type_symbol(self._execution_lock),
                    "recursion_depth": _runtime_rlock_depth(self._execution_lock),
                },
                "adaptive_runtime": {
                    "debt_ledger_identity": id(self._adaptive_debt_ledger),
                    "replay_authorized_set_identity": id(self._adaptive_replay_authorized_debt_ids),
                    "replay_authorized_debt_ids": tuple(
                        sorted(str(item) for item in self._adaptive_replay_authorized_debt_ids)
                    ),
                    "last_step": self._adaptive_last_step,
                    "authorization_policy": (
                        self._adaptive_authorization_policy.model_dump(mode="json")
                    ),
                    "debts": tuple(
                        (
                            str(debt_id),
                            entry.status.value,
                            entry.certificate.certificate_sha256,
                            entry.settled_step,
                            content_sha256(entry.transition),
                            content_sha256(entry.primary_result),
                        )
                        for debt_id, entry in sorted(
                            self._adaptive_debt_ledger.items(),
                            key=lambda item: str(item[0]),
                        )
                    ),
                },
                "feedback_revision_loop": {
                    "type": _runtime_type_symbol(feedback_loop),
                    "attribute_names": sorted(vars(feedback_loop)),
                    "projector_type": _runtime_type_symbol(feedback_loop._projector),
                    "projector_attribute_names": sorted(vars(feedback_loop._projector)),
                    "projector_seen": sorted(
                        (str(key), value) for key, value in feedback_loop._projector._seen.items()
                    ),
                    "engine_type": _runtime_type_symbol(feedback_loop._engine),
                    "engine_attribute_names": sorted(vars(feedback_loop._engine)),
                    "engine_version": feedback_loop._engine.engine_version,
                    "engine_schema_version": feedback_loop._engine.schema_version,
                    "message_passing_type": _runtime_type_symbol(feedback_message_passing),
                    "message_passing_attribute_names": sorted(vars(feedback_message_passing)),
                    "message_passing_state": _message_passing_state_descriptor(
                        feedback_message_passing
                    ),
                    "message_passing_authority": _authority_descriptor(authority),
                    "retraction_threshold": feedback_loop._retraction_threshold,
                    "reactivation_threshold": feedback_loop._reactivation_threshold,
                    "outcomes": sorted(
                        (str(key), value) for key, value in feedback_loop._outcomes.items()
                    ),
                },
                "cause_information_planner": {
                    "type": _runtime_type_symbol(self.cause_information_planner),
                    "attribute_names": sorted(vars(self.cause_information_planner)),
                    "state": dict(vars(self.cause_information_planner)),
                },
                "ciav_opceu_loop": {
                    "type": _runtime_type_symbol(self.ciav_opceu_loop),
                    "attribute_names": sorted(vars(self.ciav_opceu_loop)),
                    "trace": _evidence_factor_trace_state(self.ciav_opceu_loop.trace),
                },
            }
        )

    def _capture_execution_wrapper_state(self) -> dict[str, object]:
        component_refs = self._execution_guard_components()
        component_refs.pop("production_system")
        component_refs.pop("execution_lock")
        component_refs.pop("core")
        component_states = {
            label: {
                "attribute_names": frozenset(vars(component)),
                "fields": deepcopy(dict(vars(component))),
            }
            for label, component in component_refs.items()
            if label
            not in {
                "feedback_engine",
                "feedback_message_passing",
                "feedback_independence_authority",
            }
        }
        excluded = {
            "core",
            "feedback_revision_loop",
            "cause_information_planner",
            "ciav_opceu_loop",
            "_execution_contract_active",
            "_execution_lock",
            "_adaptive_debt_ledger",
            "_adaptive_replay_authorized_debt_ids",
            "_assembly_components",
        }
        return {
            "attribute_names": frozenset(self.__dict__),
            "execution_lock": self._execution_lock,
            "assembly_components": self._assembly_components,
            "core": self.core,
            "adaptive_debt_ledger": self._adaptive_debt_ledger,
            "adaptive_debt_ledger_state": self._snapshot_adaptive_debt_ledger(
                self._adaptive_debt_ledger
            ),
            "adaptive_replay_authorized_debt_ids": (self._adaptive_replay_authorized_debt_ids),
            "adaptive_replay_authorized_debt_ids_state": frozenset(
                self._adaptive_replay_authorized_debt_ids
            ),
            "component_refs": component_refs,
            "component_states": component_states,
            "fields": deepcopy(
                {name: value for name, value in self.__dict__.items() if name not in excluded}
            ),
        }

    def _restore_execution_wrapper_state(self, checkpoint: Mapping[str, object]) -> None:
        attribute_names = checkpoint["attribute_names"]
        assert isinstance(attribute_names, frozenset)
        for name in tuple(self.__dict__):
            if name not in attribute_names:
                delattr(self, name)
        fields = checkpoint["fields"]
        assert isinstance(fields, dict)
        for name, value in fields.items():
            setattr(self, name, value)
        component_refs = checkpoint["component_refs"]
        component_states = checkpoint["component_states"]
        assert isinstance(component_refs, dict)
        assert isinstance(component_states, dict)
        for label, state in component_states.items():
            component = component_refs[label]
            assert isinstance(state, dict)
            attribute_names = state["attribute_names"]
            component_fields = state["fields"]
            assert isinstance(attribute_names, frozenset)
            assert isinstance(component_fields, dict)
            for name in tuple(vars(component)):
                if name not in attribute_names:
                    delattr(component, name)
            for name, value in component_fields.items():
                setattr(component, name, deepcopy(value))

        feedback_loop = cast(
            ProjectTwoFeedbackRevisionLoop,
            component_refs["feedback_revision_loop"],
        )
        feedback_message_passing = cast(
            ProvenanceConstrainedMessagePassing,
            component_refs["feedback_message_passing"],
        )
        feedback_loop._projector = cast(
            ExecutionFeedbackProjector,
            component_refs["feedback_projector"],
        )
        feedback_loop._engine = cast(
            OpenWorldRoleConditionedReversibleEventRevisionEngine,
            component_refs["feedback_engine"],
        )
        feedback_loop._message_passing = feedback_message_passing
        if "feedback_independence_authority" in component_refs:
            feedback_message_passing._independence_authority = component_refs[
                "feedback_independence_authority"
            ]
        ciav_opceu_loop = cast(CIAVOPCEUObservationLoop, component_refs["ciav_opceu_loop"])
        ciav_opceu_loop.trace = cast(
            EvidenceFactorConsumptionTrace,
            component_refs["evidence_factor_trace"],
        )

        self._execution_lock = checkpoint["execution_lock"]  # type: ignore[assignment]
        self._assembly_components = checkpoint["assembly_components"]  # type: ignore[assignment]
        self.core = checkpoint["core"]  # type: ignore[assignment]
        adaptive_debt_ledger = checkpoint["adaptive_debt_ledger"]
        adaptive_debt_ledger_state = checkpoint["adaptive_debt_ledger_state"]
        assert isinstance(adaptive_debt_ledger, dict)
        assert isinstance(adaptive_debt_ledger_state, dict)
        self._restore_adaptive_debt_ledger(
            adaptive_debt_ledger,
            adaptive_debt_ledger_state,
        )
        self._adaptive_debt_ledger = adaptive_debt_ledger
        adaptive_replay_authorized_debt_ids = checkpoint["adaptive_replay_authorized_debt_ids"]
        adaptive_replay_authorized_debt_ids_state = checkpoint[
            "adaptive_replay_authorized_debt_ids_state"
        ]
        assert isinstance(adaptive_replay_authorized_debt_ids, set)
        assert isinstance(adaptive_replay_authorized_debt_ids_state, frozenset)
        adaptive_replay_authorized_debt_ids.clear()
        adaptive_replay_authorized_debt_ids.update(adaptive_replay_authorized_debt_ids_state)
        self._adaptive_replay_authorized_debt_ids = adaptive_replay_authorized_debt_ids
        self.feedback_revision_loop = feedback_loop
        self.cause_information_planner = component_refs["cause_information_planner"]
        self.ciav_opceu_loop = ciav_opceu_loop

    @staticmethod
    def _snapshot_adaptive_debt_ledger(
        ledger: Mapping[UUID, _AdaptiveDebtEntry],
    ) -> dict[UUID, _AdaptiveDebtEntrySnapshot]:
        """Snapshot mutable fields without copying identity-bearing runtime objects."""

        return {
            debt_id: _AdaptiveDebtEntrySnapshot(
                entry=entry,
                certificate=entry.certificate,
                transition=entry.transition,
                primary_result=entry.primary_result,
                deferred_ciav_input=entry.deferred_ciav_input,
                origin_core_checkpoint=entry.origin_core_checkpoint,
                post_origin_core_state_sha256=entry.post_origin_core_state_sha256,
                status=entry.status,
                settled_step=entry.settled_step,
            )
            for debt_id, entry in ledger.items()
        }

    @staticmethod
    def _restore_adaptive_debt_ledger(
        ledger: dict[UUID, _AdaptiveDebtEntry],
        snapshots: Mapping[UUID, object],
    ) -> None:
        """Restore the original ledger entries in place after a failed transaction."""

        restored: dict[UUID, _AdaptiveDebtEntry] = {}
        for debt_id, value in snapshots.items():
            if not isinstance(debt_id, UUID) or not isinstance(value, _AdaptiveDebtEntrySnapshot):
                raise TypeError("adaptive debt rollback snapshot is malformed")
            entry = value.entry
            entry.certificate = value.certificate
            entry.transition = value.transition
            entry.primary_result = value.primary_result
            entry.deferred_ciav_input = value.deferred_ciav_input
            entry.origin_core_checkpoint = value.origin_core_checkpoint
            entry.post_origin_core_state_sha256 = value.post_origin_core_state_sha256
            entry.status = value.status
            entry.settled_step = value.settled_step
            restored[debt_id] = entry
        ledger.clear()
        ledger.update(restored)

    def _runtime_operator_instances_for_execution(self) -> dict[str, tuple[object, ...]]:
        self.core._check_particle_workspace_binding()
        actual = (
            self.core,
            self.core._event_engine,
            self.core._message_passing,
            self.feedback_revision_loop,
            self.cause_information_planner,
            self.ciav_opceu_loop,
        )
        if any(
            left is not right for left, right in zip(actual, self._assembly_components, strict=True)
        ):
            if self._assembly_components[0]._execution_contract_phase == "sink_commit":
                raise RuntimeError("trace sink replaced an audited runtime component")
            raise ValueError(
                "production assembly component identity was replaced; "
                "override type is not registered or bound"
            )
        if (
            self.feedback_revision_loop._engine is not self.core._event_engine
            or self.feedback_revision_loop._message_passing is not self.core._message_passing
        ):
            raise ValueError("feedback loop engine/message passing must share the production core")
        router = self.core._automatic_regimes
        instances: dict[str, tuple[object, ...]] = {
            "opceu": (self.core._corrector,),
            "orrer_cheh": (self.core._event_engine, self.feedback_revision_loop),
            "pchmp": (self.core._message_passing,),
            "cf_bocpd": (router.bocpd,),
            "ccrr": (router, router.ccrr),
            "rgrc": (self.core, self.core._hybrid_loop.ledger),
            "ciav": (self.cause_information_planner, self.ciav_opceu_loop),
        }
        # Verify the additional declared implementations too.  A binding is not
        # an execution receipt; uncalled nodes remain unexecuted in the trace.
        for operator, instance, method in (
            ("opceu", self.core._corrector, "weight_for_opportunity"),
            ("orrer_cheh", self.core._event_engine, "branch"),
            ("pchmp", self.core._message_passing, "consume"),
            ("cf_bocpd", router.bocpd, "observe_online"),
            ("ccrr", router, "observe"),
            ("rgrc", self.core, "_process_transition"),
            ("orrer_cheh", self.feedback_revision_loop, "ingest_feedback"),
            ("ccrr", router.ccrr, "decide"),
            ("rgrc", self.core._hybrid_loop.ledger, "live_promoted_records_for_revision"),
            ("ciav", self.cause_information_planner, "select"),
            ("ciav", self.ciav_opceu_loop, "execute_selected_action"),
        ):
            bind_runtime_callable(
                runtime_execution_id=self.core.authorization_scope_id,
                operator=cast(RuntimeOperatorName, operator),
                binding_slot=1,
                binding_kind="direct_operator_callable",
                instance=instance,
                callable_name=method,
                require_declared_member=True,
            )
        return instances

    def runtime_operator_instances(self) -> dict[str, tuple[object, ...]]:
        """Audit view proving the seven names resolve to live objects in this runtime."""

        return self._runtime_operator_instances_for_execution()

    def bind_evidence_factor_trace(self, trace: EvidenceFactorConsumptionTrace) -> None:
        """Bind CIAV/OPCEU to the same evidence trace used by the main runtime."""

        if self._execution_contract_active:
            raise RuntimeError("runtime mutation is forbidden during production execution")
        with self._execution_lock:
            if self._execution_contract_active:
                raise RuntimeError("runtime mutation is forbidden during production execution")
            self.ciav_opceu_loop = CIAVOPCEUObservationLoop(trace)
            self._assembly_components = (*self._assembly_components[:-1], self.ciav_opceu_loop)

    def verify_runtime_assembly(
        self, *, allowed_operator_overrides: frozenset[str] = frozenset()
    ) -> None:
        unknown_overrides = allowed_operator_overrides - set(REGISTERED_OPERATOR_OVERRIDE_TYPES)
        if unknown_overrides:
            raise ValueError("Structure-Two runtime declared an unregistered operator override")
        instances = self.runtime_operator_instances()
        if tuple(instances) != PRODUCTION_OPERATOR_ORDER:
            raise ValueError("Structure-Two runtime operator order drifted")
        for binding in PRODUCTION_OPERATOR_BINDINGS:
            if binding.operator in allowed_operator_overrides:
                if len(instances[binding.operator]) != len(binding.implementation_symbols):
                    raise ValueError(
                        f"Structure-Two runtime override changed operator arity: {binding.operator}"
                    )
                actual_override_types = {
                    f"{type(item).__module__}.{type(item).__qualname__}"
                    for item in instances[binding.operator]
                }
                if not actual_override_types.issubset(
                    REGISTERED_OPERATOR_OVERRIDE_TYPES[binding.operator]
                ) or not all(
                    callable(getattr(item, "consume", None)) for item in instances[binding.operator]
                ):
                    raise ValueError("Structure-Two operator override type is not registered")
                continue
            actual = tuple(
                f"{type(item).__module__}.{type(item).__qualname__}"
                for item in instances[binding.operator]
            )
            if actual != binding.implementation_symbols:
                raise ValueError(
                    f"Structure-Two runtime operator instance mismatch: {binding.operator}"
                )

    def __getattr__(self, name: str) -> Any:
        # Compatibility bridge for callers of the former CorePrototypeSpine.
        # All state remains owned by ``core``; no second shadow model is created.
        return getattr(self.core, name)
