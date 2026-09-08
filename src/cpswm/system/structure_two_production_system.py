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
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any, Final
from uuid import UUID

from cpswm.contracts import EvidenceFactorConsumptionTrace
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
    PrototypeStepResult,
    PrototypeTransition,
)
from cpswm.system.reproducibility import content_sha256
from cpswm.world_model.grounded_search import (
    CauseInformationActiveVerificationPlanner,
    CIAVOPCEUObservationLoop,
)
from cpswm.world_model.habits_transitions import PropensityCorrectionMode

PRODUCTION_SYSTEM_VERSION: Final = "structure-two-production-system@0.2"
PRODUCTION_OPERATOR_ORDER: Final = (
    "opceu",
    "orrer_cheh",
    "pchmp",
    "cf_bocpd",
    "ccrr",
    "rgrc",
    "ciav",
)
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
            "cpswm.world_model.habits_transitions.context_conditioned_regime.ContextConditionedRegimeReactivator",
        ),
        source_paths=("src/cpswm/world_model/habits_transitions/context_conditioned_regime.py",),
        consumes=("cause_run_length_posterior", "context_fingerprint"),
        produces=("stay_create_reactivate_or_unresolved_decision",),
    ),
    ProductionOperatorBinding(
        operator="rgrc",
        implementation_symbols=("cpswm.system.continual.hybrid_statistics.HybridStatisticLedger",),
        source_paths=("src/cpswm/system/continual/hybrid_statistics.py",),
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


def _resolve_symbol(qualified_name: str) -> type[Any]:
    module_name, symbol_name = qualified_name.rsplit(".", 1)
    symbol = getattr(importlib.import_module(module_name), symbol_name, None)
    if not isinstance(symbol, type):
        raise ValueError(f"production operator symbol is not a class: {qualified_name}")
    return symbol


def build_production_assembly_manifest(repository_root: Path) -> dict[str, Any]:
    """Bind the complete operator graph to live instances and source bytes."""

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
        "src/cpswm/system/prototype_spine.py",
    )
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
    ) -> None:
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
        self.feedback_revision_loop = ProjectTwoFeedbackRevisionLoop(
            projector=ExecutionFeedbackProjector(),
            retraction_threshold=feedback_retraction_threshold,
            reactivation_threshold=feedback_reactivation_threshold,
        )
        self.cause_information_planner = CauseInformationActiveVerificationPlanner()
        self.ciav_opceu_loop = CIAVOPCEUObservationLoop(evidence_factor_trace)

    def process_transition(self, transition: PrototypeTransition) -> PrototypeStepResult:
        return self.core.process_transition(transition)

    def runtime_operator_instances(self) -> dict[str, tuple[object, ...]]:
        """Audit view proving the seven names resolve to live objects in this runtime."""

        router = self.core._automatic_regimes
        return {
            "opceu": (self.core._corrector,),
            "orrer_cheh": (self.core._event_engine, self.feedback_revision_loop),
            "pchmp": (self.core._message_passing,),
            "cf_bocpd": (router.bocpd,),
            "ccrr": (router.ccrr,),
            "rgrc": (self.core._hybrid_loop.ledger,),
            "ciav": (self.cause_information_planner, self.ciav_opceu_loop),
        }

    def bind_evidence_factor_trace(self, trace: EvidenceFactorConsumptionTrace) -> None:
        """Bind CIAV/OPCEU to the same evidence trace used by the main runtime."""

        self.ciav_opceu_loop = CIAVOPCEUObservationLoop(trace)

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
