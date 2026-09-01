"""Fast end-to-end prototype spine shared by structure one and structure two.

This module intentionally composes existing project components instead of
creating a second world-model stack.  It is a prototype integration surface,
not evidence that the formal M01-M32 maturity gates have passed.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from math import exp, isfinite, log, tanh
from typing import TYPE_CHECKING
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

    def __post_init__(self) -> None:
        for actor, probability in self.actor_prior.items():
            _require_probability(probability, f"actor_prior[{actor!r}]")
        _require_probability(self.unresolved_probability, "unresolved_probability")


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
        ] = defaultdict(list)
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

    def _new_habit_model(self) -> HierarchicalDirichletHabitModel:
        return HierarchicalDirichletHabitModel(
            locations=self.locations,
            resident_actor_keys=(self.owner_key,),
        )

    def _new_regime_bank(self, embedding_dim: int | None = None) -> RLSRegimeBank:
        dimension = embedding_dim or len(self.locations)
        return RLSRegimeBank(
            head_factory=lambda: RLSHabitScoreHead(
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

    @property
    def fast_action_verification_receipts(self) -> tuple[FastActionVerificationReceipt, ...]:
        return tuple(self._fast_action_verification_receipts)

    def rls_regime_snapshot(self, regime_id: str) -> dict[str, object]:
        return self._regimes.regime_snapshot(regime_id)

    def hybrid_alpha(self, location_id: UUID) -> float:
        key = self._hybrid_loop._key(location_id)
        return self._hybrid_loop.ledger.projection(key).alpha

    def is_committed_revision(self, revision_id: UUID) -> bool:
        return revision_id in self._committed_events

    def is_quarantined_revision(self, revision_id: UUID) -> bool:
        return any(event.revision_id == revision_id for event in self._quarantined_events)

    def application_receipts_for_feedback(
        self, feedback_record_id: UUID
    ) -> tuple[ProjectOneRequestApplicationReceipt, ...]:
        return tuple(self._project_one_application_receipts.get(feedback_record_id, ()))

    def retry_deferred_project_one_requests(
        self, revision_id: UUID
    ) -> tuple[ProjectOneRequestApplicationReceipt, ...]:
        """Retry every request waiting on one newly promoted event exactly once."""

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
        self, revision_ids: set[UUID], *, rationale: str
    ) -> tuple[ProjectOneRequestApplicationReceipt, ...]:
        """Close deferred requests when CCRR explicitly discards quarantine."""

        pending = [
            (fingerprint, request)
            for fingerprint, (
                request,
                waiting_revision_id,
                _mode,
            ) in self._deferred_project_one_requests.items()
            if waiting_revision_id in revision_ids
        ]
        receipts = []
        for fingerprint, request in pending:
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

    def process_transition(self, transition: PrototypeTransition) -> PrototypeStepResult:
        """Commit one ordinary transition as an all-or-nothing model transaction."""

        checkpoint = self._capture_revision_transaction()
        try:
            return self._process_transition(transition)
        except Exception:
            self._restore_revision_transaction(checkpoint)
            raise

    def _process_transition(self, transition: PrototypeTransition) -> PrototypeStepResult:
        self._validate_transition(transition)
        propensity = self._corrector.weight_for_opportunity(transition.opportunity)
        history = self._event_engine.branch(
            before=transition.before,
            after=transition.after,
            actor_prior=dict(transition.actor_prior),
            unresolved_probability=transition.unresolved_probability,
        )
        event_posterior, receipted_history = self._message_passing.consume(
            history, transition.evidence
        )
        actor_posterior = self._actor_posterior(receipted_history, event_posterior)

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
        assessment = self._automatic_regimes.observe(
            frame=regime_frame,
            state_key=f"{location_id}|{transition.context_key}",
            context_features=(
                *(1.0 if index == location_index else 0.0 for index in range(len(self.locations))),
                tanh(transition.context_value),
            ),
            owner_probability=owner_mass,
            evidence_source_record_ids=evidence.source_record_ids,
        )
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
        )
        self._observed_events[current_event.revision_id] = current_event
        self._fast_action_events[current_event.revision_id] = current_event

        promoted_audits: dict[UUID, HabitUpdateAudit] = {}
        if assessment.conclusion is HabitStateConclusion.HABIT_CHANGE:
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
                promoted_audits[promoted.revision_id] = self._commit_event(promoted)
            self._quarantined_events.clear()
        elif assessment.conclusion is HabitStateConclusion.SHORT_TERM_DISTURBANCE:
            self._reject_deferred_project_one_requests(
                {item.revision_id for item in self._quarantined_events},
                rationale="CCRR classified the quarantined event as a short-term disturbance",
            )
            self._quarantined_events.clear()
        elif (
            assessment.conclusion is HabitStateConclusion.INSUFFICIENT_EVIDENCE
            and not assessment.allow_long_term_write
        ):
            if assessment.ccrr_decision is None:
                self._quarantined_events.append(current_event)
            else:
                self._reject_deferred_project_one_requests(
                    {item.revision_id for item in self._quarantined_events},
                    rationale="CCRR closed quarantine without promoting the corrected event",
                )
                self._quarantined_events.clear()

        if assessment.allow_long_term_write or not self._rgrc_gate_enabled:
            if current_event.revision_id in self._committed_events:
                habit_update = promoted_audits.get(current_event.revision_id)
                if habit_update is None:
                    habit_update = self._habit.update_audited(evidence, weight_multiplier=0.0)
            else:
                habit_update = self._commit_event(current_event)
        else:
            habit_update = self._habit.update_audited(evidence, weight_multiplier=0.0)
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
                self._revision_feedback_bindings[revision_id] = (
                    event.location_id,
                    belief_snapshot.snapshot_id,
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
        return PrototypeStepResult(
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

    def _commit_event(self, event: _CommittedPrototypeEvent) -> HabitUpdateAudit:
        """Promote one accepted/quarantined event into all three model stores."""

        if event.revision_id in self._committed_events:
            raise ValueError("prototype event revision is already committed")
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
        return replace(
            event,
            hybrid_revision_id=hybrid_revision_id,
            hybrid_parent_revision_id=parent_revision_id,
        )

    def _retract_event_hybrid(self, event: _CommittedPrototypeEvent) -> None:
        self._hybrid_loop.retract_revision(event.hybrid_revision_id or event.revision_id)

    def _transition_fault_hook(self, stage: str) -> None:
        """No-op fault-injection seam for ordinary-transition rollback tests."""

    def apply_event_revision_outcome(
        self, outcome: EventRevisionOutcome
    ) -> PrototypeRevisionResult:
        """Apply one all-or-nothing revision across Hybrid, Dirichlet, and RLS."""

        checkpoint = self._capture_revision_transaction()
        try:
            return self._apply_event_revision_outcome(outcome)
        except Exception:
            self._restore_revision_transaction(checkpoint)
            raise

    def _apply_event_revision_outcome(
        self, outcome: EventRevisionOutcome
    ) -> PrototypeRevisionResult:
        """Apply project-two retract/correct via existing reversible components."""

        original = self._committed_events.get(outcome.superseded_revision_id)
        if original is None:
            raise KeyError("superseded revision is not a committed prototype event")
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
            if original.derived_from_revision_id is not None:
                corrected_derived = self._committed_events[outcome.corrected_revision_id]
                self._derived_event_archive[outcome.corrected_revision_id] = corrected_derived
                self._derived_event_lifecycle[outcome.corrected_revision_id] = (
                    DerivedEvidenceLifecycle.ACTIVE
                )
            self._observed_events.pop(outcome.superseded_revision_id, None)
            if original.regime_frame is not None:
                self._observed_events[outcome.corrected_revision_id] = self._committed_events[
                    outcome.corrected_revision_id
                ]
            for revision_id in dependent_revision_ids:
                self._retract_event_hybrid(self._committed_events[revision_id])
                del self._committed_events[revision_id]
                self._observed_events.pop(revision_id, None)
            snapshot = self._hybrid_loop.publish_snapshot()
            corrected_event = self._committed_events[outcome.corrected_revision_id]
            self._committed_events[outcome.corrected_revision_id] = replace(
                corrected_event,
                belief_snapshot_id=snapshot.snapshot_id,
            )
            self._revision_feedback_bindings[outcome.corrected_revision_id] = (
                corrected_event.location_id,
                snapshot.snapshot_id,
            )
            operations = (PrototypeStatisticOperation.CORRECT,)
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

    def _capture_revision_transaction(self) -> dict[str, object]:
        return {
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
            "hybrid_export": self._hybrid_loop.ledger.export_state(),
            "belief_snapshot": self.current_snapshot,
        }

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

    def apply_project_one_stat_request(
        self, request: ProjectOneStatRequest
    ) -> ProjectOneRequestApplicationReceipt:
        """Apply/defer/reject one request with exactly-once receipt semantics."""

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
                and receipt.status is ProjectOneRequestApplicationStatus.APPLIED
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
        request_checkpoint = self._capture_revision_transaction()
        old_snapshot = self.current_snapshot
        before = self.committed_weight_semantics(request.superseded_revision_id)
        hybrid_before = self.hybrid_alpha(request.location_id)
        result = self.apply_event_revision_outcome(
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
        history = self._project_one_application_receipts[request.source_feedback_record_id]
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
            attempt_number=len(
                self._project_one_application_receipts[applied.source_feedback_record_id]
            )
            + 1,
            old_belief_snapshot_id=self.current_snapshot.snapshot_id,
            new_belief_snapshot_id=self.current_snapshot.snapshot_id,
            ccrr_decision="replay_noop",
            rationale="request fingerprint was already applied exactly once",
        )
        self._project_one_application_receipts[applied.source_feedback_record_id].append(receipt)
        return receipt

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
        """Keep a refused correction's action consequence, never its statistic.

        Applied requests release their entry: the long-term statistic now carries
        the correction, and counting it twice would let one piece of evidence move
        the planner twice.
        """

        if status is ProjectOneRequestApplicationStatus.APPLIED:
            self._action_scoped_negatives.pop(fingerprint, None)
            return
        if status is ProjectOneRequestApplicationStatus.REPLAY_NOOP:
            return
        location_id = getattr(request, "location_id", None)
        delta = float(getattr(request, "owner_mass_delta", 0.0))
        if location_id is None or delta >= 0.0:
            return
        self._action_scoped_negatives[fingerprint] = (location_id, delta)

    def action_scoped_negative_ledger(self) -> dict[str, tuple[UUID, float]]:
        """Audit view: every refused correction still influencing the next action."""

        return dict(self._action_scoped_negatives)

    def pending_correction_mass(self) -> dict[UUID, float]:
        """Owner-mass delta of corrections that have not reached the statistics.

        Two disjoint sources, both honest:

        * deferred requests -- the revision was accepted and only its statistic
          write waits on CCRR promotion;
        * action-scoped negatives -- CCRR refused the statistic write outright,
          but the execution failure that produced the request still happened.

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

    def process_execution_feedback(
        self,
        *,
        feedback: ExecutionFeedbackRecord,
        binding: DecisionContextBinding,
        likelihood_model: ActionOutcomeLikelihoodModel,
        policy: ExecutionFeedbackInterpretationPolicy | None = None,
    ) -> PrototypeRevisionResult:
        """Project likelihood evidence and apply a pluggable statistic policy."""

        bound_revision_id = self._validate_feedback_revision_binding(
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
            result = self.apply_event_revision_outcome(
                EventRevisionOutcome(
                    kind=EventRevisionKind.CORRECT,
                    superseded_revision_id=interpretation.target_revision_id,
                    corrected_revision_id=uuid4(),
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
        self._hybrid_loop.commit_execution_feedback(projected)
        return result

    def _validate_feedback_revision_binding(
        self,
        *,
        feedback: ExecutionFeedbackRecord,
        binding: DecisionContextBinding,
    ) -> UUID:
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
        if binding.decision_context.revisions.belief_snapshot_id != expected_snapshot_id:
            raise ValueError("feedback revision snapshot does not match the committed event")
        return revision_id

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
        self._revision_feedback_bindings[reinforced_revision] = (
            reinforced.location_id,
            snapshot.snapshot_id,
        )
        return snapshot

    def _rebuild_personalized_models(self) -> BeliefSnapshot:
        previous_committed = dict(self._committed_events)
        (
            recomputed_active_regime,
            replayed_regimes,
            committed_observation_ids,
            quarantined_observation_ids,
        ) = self._recompute_active_regime()
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
        for revision_id in restored_derived_ids:
            restored = replace(
                self._committed_events[revision_id],
                belief_snapshot_id=snapshot.snapshot_id,
            )
            self._committed_events[revision_id] = restored
            self._derived_event_archive[revision_id] = restored
            self._revision_feedback_bindings[revision_id] = (
                restored.location_id,
                snapshot.snapshot_id,
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
    ) -> tuple[str, dict[UUID, str], set[UUID], list[UUID]]:
        """Fresh replay the observation log into regime and storage classifications."""

        self._automatic_regimes = self._new_automatic_regime_router()
        replay_habit = self._new_habit_model()
        replay_regimes = self._new_regime_bank()
        previous_location: UUID | None = None
        replayed_regimes: dict[UUID, str] = {}
        committed_revision_ids: set[UUID] = set()
        pending_events: list[_CommittedPrototypeEvent] = []
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
            )
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
        return (
            self._automatic_regimes.ccrr.active_regime(
                object_instance_id=self.object_instance_id,
                actor_id=self.owner_key,
            ),
            replayed_regimes,
            committed_revision_ids,
            [event.revision_id for event in pending_events],
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
