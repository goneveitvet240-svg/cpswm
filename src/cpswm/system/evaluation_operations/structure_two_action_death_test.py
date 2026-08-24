"""Legacy structure-two action-level proxy death test (v0.1).

The authoritative v0.2 matched benchmark is implemented by
``ProjectTwoActionBenchmarkV02`` and is the target of the application runner.
This module's original runner is retained only for regression compatibility.

Structure-two action-level matched death test: PCHMP x CCRR x RGRC vs
four reference baselines (AMG / O-STaR / DynaMem / STAR).

This is the *research gate* the structure-two specification demands after the
hidden-event death tests (§4.7 #2 x #5 were only "representation repaired").
A belief model is only a paper contribution if it changes embodied action.

The baselines are reduced-skill re-implementations that share the same
robot-visible contracts and the same deterministic scenario: each baseline is a
minimal, documented strawman of its family (e.g. DynaMem keeps only the latest
state; STAR keeps unpruned frequency counts; AMG keeps a stateless MAP chain).
No baseline sees ground truth. The legacy new-method arm below contains a
stand-in owner-attribution write gate and is therefore classified as a
``reduced-skill proxy`` by v0.2, never as the full project-two arm. Claims from
this legacy class are limited to what this action-level,
single-household scenario can support.

Equivariance scope (honest boundary): every method is invariant to the *order*
of the ``locations`` tuple (tuple-order invariance, tested).  The baselines are
label-permutation equivariant after their first observation (their state is
relational: counts and last-observed location).  The new method's habit signal
and context fingerprint are derived from absolute location UUIDs, and the
shared "no information" fallback is a single point; neither can covary with an
arbitrary relabelling of location labels.  This is a documented limitation of
absolute position features plus single-point prediction, not a hidden shortcut.
"""

from __future__ import annotations

import hashlib
import random
import secrets
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from math import isclose
from typing import Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import Field, model_validator

from cpswm.contracts import (
    ActorEvidenceTrack,
    ActorResponsibilityEvidence,
    BaseRecordMetadata,
    EventMechanism,
    EventMechanismEvidence,
    HiddenEventEvidenceTrack,
    ObservationDetectionResult,
    ObservationOutcome,
    RoleBindingEvidence,
    SourceType,
    ordered_role_key,
    parse_ordered_role_key,
)
from cpswm.contracts.base import ContractModel
from cpswm.system.counterfactual_event_hypergraph import (
    DamenHogg2012AMGMatchedEvidenceBaseline,
    OpenWorldRoleConditionedReversibleEventRevisionEngine,
    ProvenanceConstrainedMessagePassing,
)
from cpswm.system.reproducibility import content_sha256
from cpswm.world_model.habits_transitions import (
    CauseSignalFrame,
    ChangeCause,
    ContextConditionedRegimeReactivator,
    JointCauseFactorizedBOCPD,
    RegimeDecisionKind,
    RegimeLibraryEntry,
)

SCHEMA_VERSION = "0.1.0"
MODEL_VERSION = "structure-two-action-death-test@0.1"


def _public_deterministic_uuid(seed: int, *parts: object) -> UUID:
    """The *public* seed->UUID mapping this benchmark must no longer use.

    It is kept only to demonstrate the attack: anyone who knows the seed can
    reproduce every UUID (and hence the truth) from ``uuid5(NAMESPACE_URL,
    "structure-two-action:{seed}:...")``.  Sealed generation uses
    :func:`_sealed_uuid` instead.
    """

    key = f"structure-two-action:{seed}:" + ":".join(str(part) for part in parts)
    return uuid5(NAMESPACE_URL, key)


def _sealed_uuid(sealed_secret: str, seed: int, *parts: object) -> UUID:
    """A seed-derived UUID bound to a secret only the evaluator holds.

    Without ``sealed_secret`` there is no public, enumerable mapping from
    ``seed`` to the generated UUIDs, so a model that only sees the visible
    payload cannot recover the generating seed (or the truth).
    """

    key = content_sha256(f"{sealed_secret}|{seed}|" + "|".join(str(part) for part in parts))
    return UUID(key[:32])


def new_sealed_secret() -> str:
    """A fresh high-entropy evaluator secret (kept private, never sent to models)."""

    return secrets.token_hex(32)


def adversarial_seed_oracle(visible: VisibleActionCase, *, max_seed: int = 99_999) -> int | None:
    """The cheating probe: try to recover the generating seed from the public
    UUID mapping.  Returns the recovered seed, or ``None`` when the evaluator is
    sealed (visible UUIDs do not follow the public mapping).
    """

    for seed in range(max_seed + 1):
        if _public_deterministic_uuid(seed, "object") == visible.object_instance_id:
            return seed
    return None


def _position_value(location: UUID) -> float:
    """A location-order-independent [0, 1] feature for one location UUID.

    This is the location-permutation-equivariant replacement for the former
    ``locations.index(location)`` signal: it depends only on the UUID, never on
    the order of the ``locations`` tuple.
    """

    return float((location.int & 0xFFFF) / 65536.0)


def _position_fingerprint(location: UUID) -> tuple[float, ...]:
    """A centered, multi-component, order-independent context fingerprint.

    SHA-256 bytes are centered to [-0.5, 0.5] so two distinct locations have
    (with overwhelming probability) near-zero cosine similarity.  This is the
    location-permutation-equivariant replacement for the former one-hot index.
    """

    digest = hashlib.sha256(location.bytes).digest()
    return tuple((byte - 128.0) / 128.0 for byte in digest[:16])


class ActionTaskType(StrEnum):
    PUT_BACK = "put_back"
    SEARCH = "search"


class ActionBaselineMethod(StrEnum):
    AMG_2012 = "damen_hogg_2012_amg"
    O_STAR = "o_star_dirichlet"
    DYNAMEM = "dynamem_latest_state"
    STAR = "star_retrieval"
    PCHMP_CCRR_RGRC = "pchmp_ccrr_rgrc"


class ActionDayObservation(ContractModel):
    """Robot-visible inputs for one day; deliberately contains no truth."""

    day: int = Field(ge=0)
    before: ObservationDetectionResult | None = None
    after: ObservationDetectionResult | None = None
    actor_evidence: ActorResponsibilityEvidence | None = None
    mechanism_evidence: EventMechanismEvidence | None = None
    role_evidence: RoleBindingEvidence | None = None

    @model_validator(mode="after")
    def validate_observation(self) -> ActionDayObservation:
        if self.after is not None and self.before is None:
            raise ValueError("an after endpoint requires a before endpoint")
        if self.after is None and any(
            item is not None
            for item in (self.actor_evidence, self.mechanism_evidence, self.role_evidence)
        ):
            raise ValueError("evidence without an observed transition is not robot-visible")
        return self


class ActionDayTruth(ContractModel):
    """Evaluator-only truth for one day."""

    day: int = Field(ge=0)
    true_location_after: UUID
    true_owner_habit_location: UUID
    true_actor: str = Field(min_length=1)
    mechanism: EventMechanism


class VisibleActionCase(ContractModel):
    """Model-visible inputs only; this contract structurally excludes truth.

    ``case_id`` is an opaque UUID so a model cannot recover the generating seed
    from the case identity, and the seed lives only in the evaluator envelope
    (:class:`ActionGeneratedCase`), which models never receive.
    """

    case_id: UUID
    object_instance_id: UUID
    owner_actor: str = Field(min_length=1)
    guest_actor: str = Field(min_length=1)
    locations: tuple[UUID, ...] = Field(min_length=2)
    days: tuple[ActionDayObservation, ...] = Field(min_length=1)


class ActionGeneratedCase(ContractModel):
    """An evaluator case: a visible slice plus evaluator-only truth and seed."""

    seed: int = Field(ge=0)
    visible: VisibleActionCase
    truth_by_day: dict[int, ActionDayTruth]

    @model_validator(mode="after")
    def validate_binding(self) -> ActionGeneratedCase:
        if set(self.truth_by_day) != {obs.day for obs in self.visible.days}:
            raise ValueError("truth must cover exactly the observed days")
        return self


class ActionSuite(ContractModel):
    generator_version: str = Field(min_length=1)
    cases: tuple[ActionGeneratedCase, ...] = Field(min_length=1)


class ActionMethodPrediction(ContractModel):
    case_id: UUID
    method: ActionBaselineMethod
    day: int = Field(ge=0)
    put_back_location: UUID
    search_location: UUID


class ActionDayResult(ContractModel):
    case_id: UUID
    method: ActionBaselineMethod
    day: int = Field(ge=0)
    put_back_correct: bool
    search_correct: bool
    search_cost: int = Field(ge=1)


class ActionMethodReport(ContractModel):
    method: ActionBaselineMethod
    case_count: int = Field(ge=0)
    put_back_error_rate: float = Field(ge=0.0, le=1.0)
    search_error_rate: float = Field(ge=0.0, le=1.0)
    mean_search_cost: float = Field(ge=0.0)
    guest_day_put_back_error_days: int = Field(ge=0)
    total_put_back_errors: int = Field(ge=0)
    total_search_errors: int = Field(ge=0)


class StructureTwoActionDeathTestReport(ContractModel):
    generator_version: str = Field(min_length=1)
    method_reports: tuple[ActionMethodReport, ...]
    case_results: tuple[ActionDayResult, ...]
    scientific_status: str


# --- scenario generation -----------------------------------------------------


class StructureTwoActionScenarioGenerator:
    """Deterministic household action scenario generator.

    Timeline (per object, ``duration_days``):

    * days 0..abrupt-1: stable regime at ``loc_0``;
    * guest days (inclusive window): guest relocates the object to ``loc_guest``
      (direct or handoff) while the owner's true habit stays at ``loc_0``;
    * abrupt..recurrence-1: owner habit shifts to ``loc_1``;
    * recurrence..end: owner resumes ``loc_0`` (the CCRR reactivation signal).

    Selective observation drops a deterministic fraction of transition days.

    UUIDs are bound to ``sealed_secret``: an evaluator that keeps the secret
    private produces a sealed artifact whose visible UUIDs cannot be inverted
    to the generating seed (see :func:`adversarial_seed_oracle`).
    """

    generator_version = "structure-two-action-scenario@0.1"

    def __init__(
        self,
        *,
        duration_days: int = 32,
        guest_window: tuple[int, int] = (7, 14),
        abrupt_day: int = 17,
        recurrence_day: int = 26,
        observation_coverage: float = 0.7,
        sealed_secret: str = "structure-two-action-dev-secret-v0.1",
        include_open_world_unknown_events: bool = False,
    ) -> None:
        if duration_days < 10:
            raise ValueError("duration_days must be at least 10")
        if not 0.0 < observation_coverage <= 1.0:
            raise ValueError("observation_coverage must lie in (0, 1]")
        if not guest_window[0] < guest_window[1] < abrupt_day < recurrence_day < duration_days:
            raise ValueError("scenario windows must be strictly ordered")
        if not sealed_secret.strip():
            raise ValueError("sealed_secret must be non-empty")
        self.duration_days = duration_days
        self.guest_window = guest_window
        self.abrupt_day = abrupt_day
        self.recurrence_day = recurrence_day
        self.observation_coverage = observation_coverage
        self.sealed_secret = sealed_secret
        self.include_open_world_unknown_events = include_open_world_unknown_events

    def generate(self, seed: int) -> ActionGeneratedCase:
        rng = random.Random(f"structure-two-action-{seed}")
        owner = "owner"
        guest = "guest"
        secret = self.sealed_secret
        object_id = _sealed_uuid(secret, seed, "object")
        household_id = _sealed_uuid(secret, seed, "household")
        session_id = _sealed_uuid(secret, seed, "session")
        trace_id = _sealed_uuid(secret, seed, "trace")
        locations = tuple(_sealed_uuid(secret, seed, "location", i) for i in range(4))
        loc_0, loc_1, loc_guest, loc_decoy = locations

        observations: list[ActionDayObservation] = []
        truth: dict[int, ActionDayTruth] = {}
        for day in range(self.duration_days):
            in_guest_window = self.guest_window[0] <= day <= self.guest_window[1]
            if day < self.abrupt_day:
                owner_habit = loc_0
            elif day < self.recurrence_day:
                owner_habit = loc_1
            else:
                owner_habit = loc_0

            # Every day is a real relocation: the object is taken from its
            # overnight decoy spot to the daytime spot (owner habit location or
            # the guest's location).  This guarantees before != after on every
            # observed day while keeping the owner habit location meaningful.
            if self.include_open_world_unknown_events and day == 1:
                true_actor = "unknown_actor"
                true_location = loc_guest
                mechanism = EventMechanism.UNKNOWN_MECHANISM
            elif in_guest_window:
                true_actor = guest
                true_location = loc_guest
                mechanism = (
                    EventMechanism.HANDOFF_RELOCATION
                    if rng.random() < 0.5
                    else (EventMechanism.DIRECT_RELOCATION)
                )
            else:
                true_actor = owner
                true_location = owner_habit
                mechanism = EventMechanism.DIRECT_RELOCATION

            truth[day] = ActionDayTruth(
                day=day,
                true_location_after=true_location,
                true_owner_habit_location=owner_habit,
                true_actor=true_actor,
                mechanism=mechanism,
            )

            # Selective observation: guest days are slightly more likely to be
            # missed (the observation process is not uniform).
            if in_guest_window:
                observed = rng.random() < self.observation_coverage * 0.8
            else:
                observed = rng.random() < self.observation_coverage
            if not observed:
                observations.append(ActionDayObservation(day=day))
                continue

            base = datetime(2026, 1, 1, 8, 0, tzinfo=UTC) + timedelta(days=day)
            before = self._detection(
                object_id=object_id,
                location_id=loc_decoy,
                at=base,
                record_id=_sealed_uuid(secret, seed, day, "before"),
                household_id=household_id,
                session_id=session_id,
                trace_id=trace_id,
            )
            after = self._detection(
                object_id=object_id,
                location_id=true_location,
                at=base + timedelta(minutes=10),
                record_id=_sealed_uuid(secret, seed, day, "after"),
                household_id=household_id,
                session_id=session_id,
                trace_id=trace_id,
            )
            actor_evidence = self._actor_evidence(
                before=before,
                after=after,
                true_actor=true_actor,
                owner=owner,
                guest=guest,
                at=base + timedelta(minutes=10),
                trace_id=trace_id,
                evidence_cluster_id=_sealed_uuid(secret, seed, day, "actor-cluster"),
                evidence_record_id=_sealed_uuid(secret, seed, day, "actor-record"),
            )
            mechanism_evidence = None
            role_evidence = None
            if mechanism in {
                EventMechanism.HANDOFF_RELOCATION,
                EventMechanism.UNKNOWN_MECHANISM,
            }:
                mechanism_evidence = self._mechanism_evidence(
                    after=after,
                    mechanism=mechanism,
                    at=base + timedelta(minutes=10),
                    trace_id=trace_id,
                    evidence_cluster_id=_sealed_uuid(secret, seed, day, "mechanism-cluster"),
                    evidence_record_id=_sealed_uuid(secret, seed, day, "mechanism-record"),
                )
                if mechanism == EventMechanism.HANDOFF_RELOCATION:
                    role_evidence = self._role_evidence(
                        after=after,
                        owner=owner,
                        guest=guest,
                        true_actor=true_actor,
                        at=base + timedelta(minutes=10),
                        trace_id=trace_id,
                        evidence_cluster_id=_sealed_uuid(secret, seed, day, "role-cluster"),
                        evidence_record_id=_sealed_uuid(secret, seed, day, "role-record"),
                    )
            observations.append(
                ActionDayObservation(
                    day=day,
                    before=before,
                    after=after,
                    actor_evidence=actor_evidence,
                    mechanism_evidence=mechanism_evidence,
                    role_evidence=role_evidence,
                )
            )
        return ActionGeneratedCase(
            seed=seed,
            visible=VisibleActionCase(
                case_id=_sealed_uuid(secret, seed, "case-id"),
                object_instance_id=object_id,
                owner_actor=owner,
                guest_actor=guest,
                locations=locations,
                days=tuple(observations),
            ),
            truth_by_day=truth,
        )

    @staticmethod
    def _detection(
        *,
        object_id: UUID,
        location_id: UUID,
        at: datetime,
        record_id: UUID,
        household_id: UUID,
        session_id: UUID,
        trace_id: UUID,
    ) -> ObservationDetectionResult:
        return ObservationDetectionResult(
            metadata=BaseRecordMetadata(
                schema_name="cpswm.ObservationDetectionResult",
                schema_version=SCHEMA_VERSION,
                record_id=record_id,
                household_id=household_id,
                session_id=session_id,
                trace_id=trace_id,
                recorded_time=at,
                source_type=SourceType.SIMULATION,
                source_id="structure-two-action-scenario",
                model_version=MODEL_VERSION,
            ),
            observation_opportunity_id=record_id,
            outcome=ObservationOutcome.DETECTED,
            detected_object_instance_id=object_id,
            detected_location_id=location_id,
            detection_time=at,
        )

    @staticmethod
    def _actor_evidence(
        *,
        before: ObservationDetectionResult,
        after: ObservationDetectionResult,
        true_actor: str,
        owner: str,
        guest: str,
        at: datetime,
        trace_id: UUID,
        evidence_cluster_id: UUID,
        evidence_record_id: UUID,
    ) -> ActorResponsibilityEvidence:
        assert after.detected_object_instance_id is not None
        if true_actor == "unknown_actor":
            posterior = {owner: 0.1, guest: 0.1, "unknown_actor": 0.8}
        else:
            posterior = {
                owner: 0.80 if true_actor == owner else 0.15,
                guest: 0.15 if true_actor == owner else 0.80,
                "unknown_actor": 0.05,
            }
        return ActorResponsibilityEvidence(
            metadata=BaseRecordMetadata(
                schema_name="cpswm.ActorResponsibilityEvidence",
                schema_version=SCHEMA_VERSION,
                record_id=evidence_record_id,
                household_id=before.metadata.household_id,
                session_id=before.metadata.session_id,
                trace_id=trace_id,
                recorded_time=at,
                source_type=SourceType.SIMULATION,
                source_id="structure-two-action-scenario",
                model_version=MODEL_VERSION,
            ),
            source_detection_result_id=after.metadata.record_id,
            object_instance_id=after.detected_object_instance_id,
            evidence_time=at,
            actor_posterior=posterior,
            reference_actor_prior={owner: 1 / 3, guest: 1 / 3, "unknown_actor": 1 / 3},
            evidence_cluster_id=evidence_cluster_id,
            evidence_track=ActorEvidenceTrack.CONTROLLED_NOISE,
            evidence_model_id="structure-two-action-actor-model@0.1",
        )

    @staticmethod
    def _mechanism_evidence(
        *,
        after: ObservationDetectionResult,
        mechanism: EventMechanism,
        at: datetime,
        trace_id: UUID,
        evidence_cluster_id: UUID,
        evidence_record_id: UUID,
    ) -> EventMechanismEvidence:
        assert after.detected_object_instance_id is not None
        if mechanism is EventMechanism.UNKNOWN_MECHANISM:
            posterior = {
                EventMechanism.DIRECT_RELOCATION: 0.1,
                EventMechanism.HANDOFF_RELOCATION: 0.1,
                EventMechanism.UNKNOWN_MECHANISM: 0.8,
            }
        else:
            posterior = {
                EventMechanism.DIRECT_RELOCATION: (
                    0.1 if mechanism == EventMechanism.HANDOFF_RELOCATION else 0.9
                ),
                EventMechanism.HANDOFF_RELOCATION: (
                    0.9 if mechanism == EventMechanism.HANDOFF_RELOCATION else 0.1
                ),
            }
        return EventMechanismEvidence(
            metadata=BaseRecordMetadata(
                schema_name="cpswm.EventMechanismEvidence",
                schema_version=SCHEMA_VERSION,
                record_id=evidence_record_id,
                household_id=after.metadata.household_id,
                session_id=after.metadata.session_id,
                trace_id=trace_id,
                recorded_time=at,
                source_type=SourceType.SIMULATION,
                source_id="structure-two-action-scenario",
                model_version=MODEL_VERSION,
            ),
            source_detection_result_id=after.metadata.record_id,
            object_instance_id=after.detected_object_instance_id,
            evidence_time=at,
            mechanism_posterior=posterior,
            reference_mechanism_prior={key: 1.0 / len(posterior) for key in posterior},
            evidence_cluster_id=evidence_cluster_id,
            evidence_track=HiddenEventEvidenceTrack.CONTROLLED_NOISE,
            evidence_model_id="structure-two-action-mechanism-model@0.1",
        )

    @staticmethod
    def _role_evidence(
        *,
        after: ObservationDetectionResult,
        owner: str,
        guest: str,
        true_actor: str,
        at: datetime,
        trace_id: UUID,
        evidence_cluster_id: UUID,
        evidence_record_id: UUID,
    ) -> RoleBindingEvidence:
        assert after.detected_object_instance_id is not None
        roles = {
            ordered_role_key(owner, guest): 0.8 if true_actor == guest else 0.2,
            ordered_role_key(guest, owner): 0.2 if true_actor == guest else 0.8,
        }
        return RoleBindingEvidence(
            metadata=BaseRecordMetadata(
                schema_name="cpswm.RoleBindingEvidence",
                schema_version=SCHEMA_VERSION,
                record_id=evidence_record_id,
                household_id=after.metadata.household_id,
                session_id=after.metadata.session_id,
                trace_id=trace_id,
                recorded_time=at,
                source_type=SourceType.SIMULATION,
                source_id="structure-two-action-scenario",
                model_version=MODEL_VERSION,
            ),
            source_detection_result_id=after.metadata.record_id,
            object_instance_id=after.detected_object_instance_id,
            evidence_time=at,
            ordered_role_posterior=roles,
            reference_ordered_role_prior={
                ordered_role_key(owner, guest): 0.5,
                ordered_role_key(guest, owner): 0.5,
            },
            evidence_cluster_id=evidence_cluster_id,
            evidence_track=HiddenEventEvidenceTrack.CONTROLLED_NOISE,
            evidence_model_id="structure-two-action-role-model@0.1",
        )


# --- method implementations ---------------------------------------------------


def _fallback_location(locations: tuple[UUID, ...]) -> UUID:
    """Order-independent default location: the UUID-smallest location.

    This makes every baseline's "no information yet" fallback invariant to the
    order of the ``locations`` tuple (tuple-order invariance).  It is *not*
    label-permutation equivariant: a single-point fallback that depends only on
    location labels cannot covary with an arbitrary relabelling of those labels.
    """

    return min(locations, key=str)


@dataclass(slots=True)
class _OwnerHabitState:
    """Per-regime owner-habit soft counts (CCRR stage memory).

    The key CCRR behaviour: counts are stored **per regime**, so a ``create``
    decision archives the old stage and starts a fresh one (fast adaptation to
    a new habit), while a ``reactivate`` decision swaps back to an archived
    stage and immediately reuses its counts (fast recovery of an old habit).
    A single flat count vector cannot do this.
    """

    owner: str
    guest: str
    locations: tuple[UUID, ...]
    active_regime_id: str = "stable"
    regimes: dict[str, dict[UUID, float]] = field(default_factory=dict)
    last_location: UUID | None = None
    guest_recent_location: UUID | None = None

    def __post_init__(self) -> None:
        self.regimes.setdefault("stable", {})

    def _active_counts(self) -> dict[UUID, float]:
        return self.regimes.setdefault(self.active_regime_id, {})

    def owner_posterior(self) -> dict[UUID, float]:
        counts = self._active_counts()
        total = sum(counts.values())
        if total <= 0.0:
            uniform = 1.0 / len(self.locations)
            return {location: uniform for location in self.locations}
        return {location: counts.get(location, 0.0) / total for location in self.locations}

    def argmax_owner(self) -> UUID:
        posterior = self.owner_posterior()
        # Tie-break on the location UUID itself so the argmax is invariant to
        # the order of the ``locations`` tuple (location permutation
        # equivariance).
        return max(
            self.locations,
            key=lambda location: (posterior[location], str(location)),
        )

    def write_owner(self, location: UUID) -> None:
        counts = self._active_counts()
        counts[location] = counts.get(location, 0.0) + 1.0


class _AMGMethod:
    """Damen-Hogg 2012 AMG adaptation: MAP event chain, no habit / no regime."""

    name = ActionBaselineMethod.AMG_2012

    def __init__(self, case: VisibleActionCase) -> None:
        self.case = case
        self.engine = OpenWorldRoleConditionedReversibleEventRevisionEngine()
        self.amg = DamenHogg2012AMGMatchedEvidenceBaseline()
        self.last_location: UUID | None = None
        self.owner_habit_location: UUID | None = None

    def observe(self, obs: ActionDayObservation) -> None:
        if obs.after is None or obs.before is None:
            return
        self.last_location = obs.after.detected_location_id
        # AMG has no habit memory; it commits to the MAP event chain's final
        # placement actor.  If the MAP places by the owner, record the location
        # as the (stateless) owner belief; otherwise ignore it.
        if obs.actor_evidence is not None:
            actor_likelihoods = {
                actor: posterior / obs.actor_evidence.reference_actor_prior[actor]
                for actor, posterior in obs.actor_evidence.actor_posterior.items()
            }
            mechanism_likelihoods = {
                EventMechanism.DIRECT_RELOCATION: 0.5,
                EventMechanism.HANDOFF_RELOCATION: 0.5,
            }
            if obs.mechanism_evidence is not None:
                mechanism_likelihoods = obs.mechanism_evidence.mechanism_posterior
            role_likelihoods = {
                (self.case.owner_actor, self.case.guest_actor): 0.5,
                (self.case.guest_actor, self.case.owner_actor): 0.5,
            }
            if obs.role_evidence is not None:
                role_likelihoods = {
                    parse_ordered_role_key(key): value
                    for key, value in obs.role_evidence.ordered_role_posterior.items()
                }
            try:
                prediction = self.amg.predict_matched(
                    before=obs.before,
                    after=obs.after,
                    actor_event_likelihoods=actor_likelihoods,
                    mechanism_likelihoods=mechanism_likelihoods,
                    handoff_role_likelihoods=role_likelihoods,
                )
                if prediction.selected_sequence.responsible_actor_key == self.case.owner_actor:
                    self.owner_habit_location = obs.after.detected_location_id
            except ValueError:
                pass

    def predict(self, task: ActionTaskType) -> UUID:
        if task == ActionTaskType.SEARCH:
            if self.last_location is not None:
                return self.last_location
            return _fallback_location(self.case.locations)
        if self.owner_habit_location is not None:
            return self.owner_habit_location
        return _fallback_location(self.case.locations)


class _OStarMethod:
    """O-STaR adaptation: Dirichlet location counts, no actor isolation."""

    name = ActionBaselineMethod.O_STAR

    def __init__(self, case: VisibleActionCase) -> None:
        self.case = case
        self.counts: dict[UUID, float] = {location: 1.0 for location in case.locations}
        self.last_location: UUID | None = None

    def observe(self, obs: ActionDayObservation) -> None:
        if obs.after is None:
            return
        location = obs.after.detected_location_id
        if location is not None:
            self.last_location = location
            self.counts[location] += 1.0

    def predict(self, task: ActionTaskType) -> UUID:
        if task == ActionTaskType.SEARCH:
            if self.last_location is not None:
                return self.last_location
            return _fallback_location(self.case.locations)
        return max(
            self.counts,
            key=lambda location: (self.counts[location], str(location)),
        )


class _DynaMemMethod:
    """DynaMem adaptation: latest observed state only, no habit model."""

    name = ActionBaselineMethod.DYNAMEM

    def __init__(self, case: VisibleActionCase) -> None:
        self.case = case
        self.last_location: UUID | None = None

    def observe(self, obs: ActionDayObservation) -> None:
        if obs.after is not None:
            self.last_location = obs.after.detected_location_id

    def predict(self, task: ActionTaskType) -> UUID:
        del task
        if self.last_location is not None:
            return self.last_location
        return _fallback_location(self.case.locations)


class _STARMethod:
    """STAR adaptation: frequency retrieval over all observed placements."""

    name = ActionBaselineMethod.STAR

    def __init__(self, case: VisibleActionCase) -> None:
        self.case = case
        self.counts: dict[UUID, float] = {location: 0.0 for location in case.locations}
        self.last_location: UUID | None = None

    def observe(self, obs: ActionDayObservation) -> None:
        if obs.after is None:
            return
        location = obs.after.detected_location_id
        if location is not None:
            self.last_location = location
            self.counts[location] += 1.0

    def predict(self, task: ActionTaskType) -> UUID:
        if task == ActionTaskType.SEARCH:
            if self.last_location is not None:
                return self.last_location
            return _fallback_location(self.case.locations)
        if sum(self.counts.values()) <= 0.0:
            return _fallback_location(self.case.locations)
        return max(
            self.counts,
            key=lambda location: (self.counts[location], str(location)),
        )


class _PchmpCcrrRgrcMethod:
    """New method: PCHMP joint event posterior -> CF-BOCPD cause -> CCRR regime
    -> owner-attribution write gate (a stand-in for full Hybrid RGRC)."""

    name = ActionBaselineMethod.PCHMP_CCRR_RGRC

    def __init__(self, case: VisibleActionCase) -> None:
        self.case = case
        self.orrer = OpenWorldRoleConditionedReversibleEventRevisionEngine()
        self.pchmp = ProvenanceConstrainedMessagePassing()
        self.bocpd = JointCauseFactorizedBOCPD()
        self.reactor = ContextConditionedRegimeReactivator()
        self.state = _OwnerHabitState(
            owner=case.owner_actor,
            guest=case.guest_actor,
            locations=case.locations,
        )
        self._frames: list[CauseSignalFrame] = []
        self._base = datetime(2026, 1, 1, 8, 0, tzinfo=UTC)
        # The default stage is seeded lazily on the first owner placement so
        # its context fingerprint is learned from observation, not assumed.
        self._stable_seeded = False

    def observe(self, obs: ActionDayObservation) -> None:
        if obs.after is None or obs.before is None:
            return
        owner = self.case.owner_actor
        guest = self.case.guest_actor
        location = obs.after.detected_location_id
        if location is None:
            return

        # 1. Branch a counterfactual hypothesis set and pass the *incremental*
        #    evidence through PCHMP (the evidence is not first consumed by an
        #    ORRER revise call, so it is not double-counted).
        actor_prior = {owner: 0.4, guest: 0.3, "unknown_actor": 0.3}
        try:
            history = self.orrer.branch(
                before=obs.before,
                after=obs.after,
                actor_prior=actor_prior,
                unresolved_probability=0.1,
            )
            evidence: list[
                ActorResponsibilityEvidence | EventMechanismEvidence | RoleBindingEvidence
            ] = []
            if obs.actor_evidence is not None:
                evidence.append(obs.actor_evidence)
            if obs.mechanism_evidence is not None:
                evidence.append(obs.mechanism_evidence)
            if obs.role_evidence is not None:
                evidence.append(obs.role_evidence)
            posterior = self.pchmp.infer(history, evidence)
        except ValueError:
            return

        # 2. Derive the owner- vs guest-attributed placement from the PCHMP
        #    joint posterior.
        owner_mass = 0.0
        guest_mass = 0.0
        for hypothesis in history.latest.hypotheses:
            mass = posterior.posterior_by_hypothesis_id.get(hypothesis.hypothesis_id, 0.0)
            if hypothesis.responsible_actor_key == owner:
                owner_mass += mass
            elif hypothesis.responsible_actor_key == guest:
                guest_mass += mass
        attributed_owner = owner_mass >= guest_mass

        # 3. Build the location-order-independent cause signal frame.  The
        #    habit channel is the position feature of an owner-attributed
        #    placement (a full-scale jump when the owner's habit location
        #    changes or returns); guest placements hold the habit channel and
        #    raise the actor channel instead.
        position_value = _position_value(location)
        if attributed_owner:
            habit_signal = position_value
            actor_signal = 0.1
        else:
            habit_signal = self._frames[-1].signals[ChangeCause.HABIT] if self._frames else 0.0
            actor_signal = 0.9
        frame = CauseSignalFrame(
            timestamp=self._base + timedelta(days=obs.day),
            signals={
                ChangeCause.OBSERVATION: 0.3,
                ChangeCause.ACTOR: actor_signal,
                ChangeCause.HABIT: habit_signal,
                ChangeCause.NOISE: 0.1,
            },
        )
        self._frames.append(frame)
        warmup = 2 if len(self._frames) > 2 else 0
        result = self.bocpd.run(self._frames, warmup_steps=warmup)
        snapshot = result.snapshots[-1]

        # 4. Seed the default stage from the first observed owner placement so
        #    its context fingerprint is learned, not assumed.
        if attributed_owner and not self._stable_seeded:
            self.reactor.add_regime(
                RegimeLibraryEntry(
                    regime_id="stable",
                    actor_id=owner,
                    object_instance_id=self.case.object_instance_id,
                    context_fingerprint=_position_fingerprint(location),
                    cause_origin=ChangeCause.HABIT,
                    created_at=frame.timestamp,
                ),
                make_active=True,
            )
            self._stable_seeded = True

        # 5. CCRR regime decision: score against an immutable view then apply
        #    under the reactor's compare-and-swap (score-then-apply is atomic).
        context_features = _position_fingerprint(location)
        view = self.reactor.view(object_instance_id=self.case.object_instance_id, actor_id=owner)
        decision = self.reactor.score_decision(
            owner_actor_id=owner,
            snapshot=snapshot,
            context_features=context_features,
            now=frame.timestamp,
            view=view,
        )
        self.reactor.apply_decision(decision)

        # 6. Owner-attribution write gate (a stand-in for full Hybrid RGRC):
        #    only owner-attributed placements under a non-unresolved regime
        #    decision write to the active owner stage.  STAY keeps the active
        #    stage; REACTIVATE/CREATE switch it first.
        if attributed_owner:
            self.state.last_location = location
            if decision.kind == RegimeDecisionKind.UNRESOLVED:
                # Unresolved: quarantine the placement (do not write).
                pass
            else:
                if decision.kind == RegimeDecisionKind.REACTIVATE:
                    assert decision.reactivated_regime_id is not None
                    self.state.active_regime_id = decision.reactivated_regime_id
                elif decision.kind == RegimeDecisionKind.CREATE:
                    assert decision.created_regime_id is not None
                    self.state.active_regime_id = decision.created_regime_id
                self.state.write_owner(location)
        else:
            self.state.guest_recent_location = location
            self.state.last_location = location

    def predict(self, task: ActionTaskType) -> UUID:
        if task == ActionTaskType.SEARCH:
            if self.state.last_location is not None:
                return self.state.last_location
            return self.state.argmax_owner()
        return self.state.argmax_owner()


class _ActionMethod(Protocol):
    """Uniform observe/predict surface shared by every method implementation."""

    def observe(self, obs: ActionDayObservation) -> None: ...

    def predict(self, task: ActionTaskType) -> UUID: ...


_METHOD_FACTORIES: dict[ActionBaselineMethod, Callable[[VisibleActionCase], _ActionMethod]] = {
    ActionBaselineMethod.AMG_2012: _AMGMethod,
    ActionBaselineMethod.O_STAR: _OStarMethod,
    ActionBaselineMethod.DYNAMEM: _DynaMemMethod,
    ActionBaselineMethod.STAR: _STARMethod,
    ActionBaselineMethod.PCHMP_CCRR_RGRC: _PchmpCcrrRgrcMethod,
}


# --- evaluation ---------------------------------------------------------------


class StructureTwoActionDeathTest:
    """Run the action-level matched death test over generated cases."""

    def __init__(
        self,
        generator: StructureTwoActionScenarioGenerator | None = None,
    ) -> None:
        self.generator = generator or StructureTwoActionScenarioGenerator()

    def run(
        self,
        seeds: tuple[int, ...],
        *,
        methods: tuple[ActionBaselineMethod, ...] = (
            ActionBaselineMethod.AMG_2012,
            ActionBaselineMethod.O_STAR,
            ActionBaselineMethod.DYNAMEM,
            ActionBaselineMethod.STAR,
            ActionBaselineMethod.PCHMP_CCRR_RGRC,
        ),
    ) -> StructureTwoActionDeathTestReport:
        cases = tuple(self.generator.generate(seed) for seed in seeds)
        day_results: list[ActionDayResult] = []
        method_reports: list[ActionMethodReport] = []

        for method in methods:
            case_results: list[ActionDayResult] = []
            per_case_error: Counter[UUID] = Counter()
            per_case_search_error: Counter[UUID] = Counter()
            search_cost_total = 0.0
            search_days = 0
            guest_day_put_back_error_days = 0
            for case in cases:
                state = _METHOD_FACTORIES[method](case.visible)
                for obs in case.visible.days:
                    state.observe(obs)
                    truth = case.truth_by_day[obs.day]
                    put_back = state.predict(ActionTaskType.PUT_BACK)
                    search = state.predict(ActionTaskType.SEARCH)
                    put_back_correct = put_back == truth.true_owner_habit_location
                    search_correct = search == truth.true_location_after
                    # Search cost: visit locations in belief order until found.
                    search_cost = self._search_cost(
                        state, truth.true_location_after, case.visible.locations
                    )
                    search_days += 1
                    search_cost_total += search_cost
                    if not put_back_correct:
                        per_case_error[case.visible.case_id] += 1
                    if not search_correct:
                        per_case_search_error[case.visible.case_id] += 1
                    # Guest-day put-back error: a day the guest actually moved
                    # the object and this method's put-back missed the owner
                    # habit location.
                    if truth.true_actor == case.visible.guest_actor and not put_back_correct:
                        guest_day_put_back_error_days += 1
                    result = ActionDayResult(
                        case_id=case.visible.case_id,
                        method=method,
                        day=obs.day,
                        put_back_correct=put_back_correct,
                        search_correct=search_correct,
                        search_cost=search_cost,
                    )
                    case_results.append(result)
                    day_results.append(result)
            total_days = len(case_results)
            total_put_back_errors = sum(per_case_error.values())
            total_search_errors = sum(per_case_search_error.values())
            method_reports.append(
                ActionMethodReport(
                    method=method,
                    case_count=len(cases),
                    put_back_error_rate=(total_put_back_errors / total_days if total_days else 0.0),
                    search_error_rate=(total_search_errors / total_days if total_days else 0.0),
                    mean_search_cost=search_cost_total / search_days if search_days else 0.0,
                    guest_day_put_back_error_days=guest_day_put_back_error_days,
                    total_put_back_errors=total_put_back_errors,
                    total_search_errors=total_search_errors,
                )
            )
        return StructureTwoActionDeathTestReport(
            generator_version=self.generator.generator_version,
            method_reports=tuple(method_reports),
            case_results=tuple(day_results),
            scientific_status=self._scientific_status(method_reports),
        )

    @staticmethod
    def _search_cost(state: object, target: UUID, locations: tuple[UUID, ...]) -> int:
        """Cost: number of locations visited before finding the target.

        Baselines that only track the last location visit exactly one location;
        belief-based methods visit in descending belief order.
        """

        belief_order = list(locations)
        if isinstance(state, _PchmpCcrrRgrcMethod):
            posterior = state.state.owner_posterior()
            belief_order = sorted(
                locations,
                key=lambda location: (-posterior.get(location, 0.0), str(location)),
            )
        elif isinstance(state, (_OStarMethod, _STARMethod)):
            belief_order = sorted(
                locations,
                key=lambda location: (-state.counts.get(location, 0.0), str(location)),
            )
        for index, location in enumerate(belief_order, start=1):
            if location == target:
                return index
        return len(locations)

    @staticmethod
    def _scientific_status(reports: list[ActionMethodReport]) -> str:
        new = next(
            (report for report in reports if report.method == ActionBaselineMethod.PCHMP_CCRR_RGRC),
            None,
        )
        if new is None:
            return "new method not run"
        baselines = [
            report for report in reports if report.method != ActionBaselineMethod.PCHMP_CCRR_RGRC
        ]
        if not baselines:
            return "no baselines run"
        best_baseline_put_back = min(report.put_back_error_rate for report in baselines)
        if new.put_back_error_rate < best_baseline_put_back - 1e-9:
            return "new method strictly better on put-back error"
        if isclose(new.put_back_error_rate, best_baseline_put_back, rel_tol=0.0, abs_tol=1e-9):
            return "new method ties the best baseline on put-back error"
        return "new method worse than the best baseline on put-back error"
