"""Automatic CF-BOCPD -> CCRR routing for the project-one prototype spine.

CF-BOCPD proposes a candidate.  CCRR alone may confirm/create/reactivate a
regime.  A candidate is quarantined until a configurable number of matching
prefix-online observations has arrived, so one anomalous location can never
switch the long-term state by itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from math import dist, isfinite
from uuid import UUID

from cpswm.world_model.habits_transitions import (
    CauseSignalFrame,
    ChangeCause,
    ContextConditionedRegimeReactivator,
    JointCauseFactorizedBOCPD,
    JointCauseSnapshot,
    RegimeDecision,
    RegimeDecisionKind,
    RegimeLibraryEntry,
)


class HabitStateConclusion(StrEnum):
    STABLE = "stable"
    HABIT_CHANGE = "habit_change"
    SHORT_TERM_DISTURBANCE = "short_term_disturbance"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class PrototypeStatisticOperation(StrEnum):
    REINFORCE = "reinforce"
    QUARANTINE = "quarantine"
    RETRACT = "retract"
    CORRECT = "correct"


class DerivedEvidenceReactivationPolicy(StrEnum):
    REQUIRE_FRESH_FEEDBACK = "require_fresh_feedback"
    RESTORE_PRIOR_DERIVED = "restore_prior_derived"


@dataclass(frozen=True, slots=True)
class PrototypeLoopConfig:
    """Explicit prototype choices; none of these values is a paper claim."""

    minimum_baseline_observations: int = 3
    confirmation_window: int = 2
    habit_change_probability_threshold: float = 0.5
    transient_disturbance_probability_threshold: float = 0.5
    owner_evidence_threshold: float = 0.5
    feedback_failure_strength: float = 0.25
    feedback_success_strength: float = 0.25
    feedback_decision_margin: float = 0.15
    forgetting_factor: float = 1.0
    context_confirmation_max_distance: float = 0.25
    dirichlet_surprise_weight: float = 0.1
    rls_residual_weight: float = 0.1
    derived_reactivation_policy: DerivedEvidenceReactivationPolicy = (
        DerivedEvidenceReactivationPolicy.REQUIRE_FRESH_FEEDBACK
    )

    def __post_init__(self) -> None:
        if self.minimum_baseline_observations < 1:
            raise ValueError("minimum_baseline_observations must be positive")
        if self.confirmation_window < 2:
            raise ValueError("confirmation_window must be at least two")
        for name in (
            "habit_change_probability_threshold",
            "transient_disturbance_probability_threshold",
            "owner_evidence_threshold",
            "feedback_failure_strength",
            "feedback_success_strength",
            "feedback_decision_margin",
            "dirichlet_surprise_weight",
            "rls_residual_weight",
        ):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must lie in [0, 1]")
        if not 0.0 < self.forgetting_factor <= 1.0:
            raise ValueError("forgetting_factor must lie in (0, 1]")
        if (
            not isfinite(self.context_confirmation_max_distance)
            or self.context_confirmation_max_distance < 0.0
        ):
            raise ValueError("context_confirmation_max_distance must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class AutomaticRegimeAssessment:
    conclusion: HabitStateConclusion
    old_regime: str
    new_regime: str
    change_probability: float
    ccrr_decision: RegimeDecision | None
    evidence_source_record_ids: tuple[UUID, ...]
    statistic_operations: tuple[PrototypeStatisticOperation, ...]
    snapshot: JointCauseSnapshot
    candidate_change_time: datetime | None
    decision_time: datetime
    allow_long_term_write: bool
    rationale: str

    def __post_init__(self) -> None:
        if not isfinite(self.change_probability) or not 0.0 <= self.change_probability <= 1.0:
            raise ValueError("change_probability must lie in [0, 1]")


@dataclass(slots=True)
class _PendingCandidate:
    state_key: str
    context_features: tuple[float, ...]
    snapshot: JointCauseSnapshot
    evidence_source_record_ids: tuple[UUID, ...]
    confirmations: int = 1


class AutomaticCFBOCPDCCRRRouter:
    """Prefix-online candidate/confirmation state machine for one habit stream."""

    def __init__(
        self,
        *,
        object_instance_id: UUID,
        actor_id: str,
        owner_actor_id: str,
        config: PrototypeLoopConfig,
        bocpd: JointCauseFactorizedBOCPD | None = None,
        ccrr: ContextConditionedRegimeReactivator | None = None,
    ) -> None:
        self.object_instance_id = object_instance_id
        self.actor_id = actor_id
        self.owner_actor_id = owner_actor_id
        self.config = config
        self.bocpd = bocpd or JointCauseFactorizedBOCPD()
        self.ccrr = ccrr or ContextConditionedRegimeReactivator(
            change_threshold=config.habit_change_probability_threshold
        )
        self._observation_count = 0
        self._last_observation_time: datetime | None = None
        self._pending: _PendingCandidate | None = None
        self._seeded = False

    @property
    def observation_count(self) -> int:
        return self._observation_count

    def observe(
        self,
        *,
        frame: CauseSignalFrame,
        state_key: str,
        context_features: tuple[float, ...],
        owner_probability: float,
        evidence_source_record_ids: tuple[UUID, ...],
        identity_switch_probability: float = 0.0,
    ) -> AutomaticRegimeAssessment:
        if not state_key.strip():
            raise ValueError("state_key must be non-empty")
        for name, value in (
            ("owner_probability", owner_probability),
            ("identity_switch_probability", identity_switch_probability),
        ):
            if not isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must lie in [0, 1]")
        if (
            self._last_observation_time is not None
            and frame.timestamp <= self._last_observation_time
        ):
            raise ValueError("automatic regime observations must be strictly chronological")
        self._observation_count += 1
        self._last_observation_time = frame.timestamp
        snapshot = self.bocpd.observe_online(frame)
        old_regime = self.ccrr.active_regime(
            object_instance_id=self.object_instance_id,
            actor_id=self.actor_id,
        )
        if not self._seeded:
            self.ccrr.add_regime(
                RegimeLibraryEntry(
                    regime_id=old_regime,
                    actor_id=self.actor_id,
                    object_instance_id=self.object_instance_id,
                    context_fingerprint=context_features,
                    cause_origin=ChangeCause.HABIT,
                    created_at=frame.timestamp,
                ),
                make_active=True,
            )
            self._seeded = True

        habit_probability = min(
            1.0,
            max(
                0.0,
                snapshot.segment_change_probability
                * snapshot.segment_cause_posterior.get(ChangeCause.HABIT, 0.0),
            ),
        )
        noise_probability = min(
            1.0,
            max(0.0, snapshot.transient_noise_probability),
        )
        if self._observation_count <= self.config.minimum_baseline_observations:
            return self._assessment(
                HabitStateConclusion.STABLE,
                old_regime,
                old_regime,
                habit_probability,
                None,
                evidence_source_record_ids,
                (PrototypeStatisticOperation.REINFORCE,),
                snapshot,
                None,
                True,
                "collecting the configured baseline prefix",
            )

        if self._pending is not None:
            candidate = self._pending
            matches_candidate = (
                state_key == candidate.state_key
                and dist(context_features, candidate.context_features)
                <= self.config.context_confirmation_max_distance
                and owner_probability >= self.config.owner_evidence_threshold
                and noise_probability < self.config.transient_disturbance_probability_threshold
            )
            if not matches_candidate:
                self._pending = None
                allow_current = (
                    noise_probability < self.config.transient_disturbance_probability_threshold
                )
                return self._assessment(
                    HabitStateConclusion.SHORT_TERM_DISTURBANCE,
                    old_regime,
                    old_regime,
                    max(candidate.snapshot.transient_noise_probability, habit_probability),
                    None,
                    candidate.evidence_source_record_ids + evidence_source_record_ids,
                    (
                        PrototypeStatisticOperation.REINFORCE
                        if allow_current
                        else PrototypeStatisticOperation.QUARANTINE,
                    ),
                    snapshot,
                    candidate.snapshot.timestamp,
                    allow_current,
                    "candidate did not persist through the confirmation window",
                )
            candidate.confirmations += 1
            if candidate.confirmations < self.config.confirmation_window:
                return self._assessment(
                    HabitStateConclusion.INSUFFICIENT_EVIDENCE,
                    old_regime,
                    old_regime,
                    habit_probability,
                    None,
                    candidate.evidence_source_record_ids + evidence_source_record_ids,
                    (PrototypeStatisticOperation.QUARANTINE,),
                    snapshot,
                    candidate.snapshot.timestamp,
                    False,
                    "candidate is still inside the confirmation window",
                )
            decision = self.ccrr.decide(
                object_instance_id=self.object_instance_id,
                actor_id=self.actor_id,
                owner_actor_id=self.owner_actor_id,
                snapshot=candidate.snapshot,
                context_features=context_features,
                identity_switch_probability=identity_switch_probability,
                now=frame.timestamp,
            )
            self._pending = None
            new_regime = self.ccrr.active_regime(
                object_instance_id=self.object_instance_id,
                actor_id=self.actor_id,
            )
            if decision.kind in {
                RegimeDecisionKind.CREATE,
                RegimeDecisionKind.REACTIVATE,
            }:
                return self._assessment(
                    HabitStateConclusion.HABIT_CHANGE,
                    old_regime,
                    new_regime,
                    min(
                        1.0,
                        max(
                            0.0,
                            candidate.snapshot.segment_change_probability
                            * candidate.snapshot.segment_cause_posterior.get(
                                ChangeCause.HABIT,
                                0.0,
                            ),
                        ),
                    ),
                    decision,
                    candidate.evidence_source_record_ids + evidence_source_record_ids,
                    (PrototypeStatisticOperation.REINFORCE,),
                    snapshot,
                    candidate.snapshot.timestamp,
                    True,
                    "CCRR confirmed a persistent candidate",
                )
            return self._assessment(
                HabitStateConclusion.INSUFFICIENT_EVIDENCE,
                old_regime,
                old_regime,
                habit_probability,
                decision,
                candidate.evidence_source_record_ids + evidence_source_record_ids,
                (PrototypeStatisticOperation.QUARANTINE,),
                snapshot,
                candidate.snapshot.timestamp,
                False,
                "CCRR refused to change the active regime",
            )

        if noise_probability >= self.config.transient_disturbance_probability_threshold:
            return self._assessment(
                HabitStateConclusion.SHORT_TERM_DISTURBANCE,
                old_regime,
                old_regime,
                noise_probability,
                None,
                evidence_source_record_ids,
                (PrototypeStatisticOperation.QUARANTINE,),
                snapshot,
                frame.timestamp,
                False,
                "CF-BOCPD transient-noise state dominated",
            )
        if (
            owner_probability >= self.config.owner_evidence_threshold
            and habit_probability >= self.config.habit_change_probability_threshold
        ):
            self._pending = _PendingCandidate(
                state_key=state_key,
                context_features=context_features,
                snapshot=snapshot,
                evidence_source_record_ids=evidence_source_record_ids,
            )
            return self._assessment(
                HabitStateConclusion.INSUFFICIENT_EVIDENCE,
                old_regime,
                old_regime,
                habit_probability,
                None,
                evidence_source_record_ids,
                (PrototypeStatisticOperation.QUARANTINE,),
                snapshot,
                frame.timestamp,
                False,
                "CF-BOCPD proposed a candidate; CCRR awaits persistence evidence",
            )
        return self._assessment(
            HabitStateConclusion.STABLE,
            old_regime,
            old_regime,
            habit_probability,
            None,
            evidence_source_record_ids,
            (PrototypeStatisticOperation.REINFORCE,),
            snapshot,
            None,
            True,
            "no candidate crossed the configured gate",
        )

    @staticmethod
    def _assessment(
        conclusion,
        old_regime,
        new_regime,
        change_probability,
        ccrr_decision,
        evidence_source_record_ids,
        statistic_operations,
        snapshot,
        candidate_change_time,
        allow_long_term_write,
        rationale,
    ) -> AutomaticRegimeAssessment:
        return AutomaticRegimeAssessment(
            conclusion=conclusion,
            old_regime=old_regime,
            new_regime=new_regime,
            change_probability=change_probability,
            ccrr_decision=ccrr_decision,
            evidence_source_record_ids=tuple(dict.fromkeys(evidence_source_record_ids)),
            statistic_operations=statistic_operations,
            snapshot=snapshot,
            candidate_change_time=candidate_change_time,
            decision_time=snapshot.timestamp,
            allow_long_term_write=allow_long_term_write,
            rationale=rationale,
        )
