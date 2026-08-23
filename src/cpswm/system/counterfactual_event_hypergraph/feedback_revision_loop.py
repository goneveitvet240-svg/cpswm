"""Project-two core loop: execution feedback as reversible counterfactual evidence.

This orchestrator closes the open-world hidden-event loop *by reusing* the existing
stack -- it builds no second event-reasoning engine:

    ExecutionFeedbackRecord
      -> ExecutionFeedbackProjector          (typed, likelihood-aware, de-duplicated)
      -> ActorResponsibilityEvidence         (likelihood ratios from the outcome model)
      -> ProvenanceConstrainedMessagePassing (re-propagate the joint posterior)
      -> ORRER.revise_actor_responsibility   (one reversible, parent-linked revision)
      -> EventRevisionOutcome                (before/after posteriors + owner-mass delta)
      -> ProjectOneStatRequest               (explicit retract/correct for project one)

Design invariants honoured here:

* Feedback is *evidence with strength*, never a hard fact: a failed search lowers
  the relevant hypotheses by a likelihood ratio derived from the
  :class:`ActionOutcomeLikelihoodModel`, and never forces a posterior to zero.
* Open-world mass is preserved: unknown-actor and unresolved mass are never
  drained to make room for a known actor; unexplained feedback grows them.
* Every ingestion appends a new parent-linked revision; the prior revision stays
  fully traceable (the ORRER history is append-only).
* Project one is only ever handed an *explicit* :class:`EventRevisionOutcome` /
  :class:`ProjectOneStatRequest`, consumed via :func:`apply_project_one_request`;
  this module never touches project one's Dirichlet/RLS state directly.

Two revision modes: a presence outcome (search) drives **event-existence
confidence** (chains vs unresolved) and cannot move owner-vs-guest odds on its own;
supplying ``actor_likelihood_ratios`` (an actor-discriminating channel) drives true
**actor-responsibility** revision where relative odds change. The two multiply.

Deliberately retained (kept as interfaces, not deleted, and NOT faked):
* place/transfer feedback is *isolated* (raises :class:`UnsupportedFeedbackRouteError`)
  until a real location/mechanism/role likelihood model exists -- it is never folded
  into a presence ratio;
* `REINFORCE` has no project-one positive-reinforcement interface yet (explicit
  no-op in the adapter);
* real perception, signatures, adversarial firewalls, a production project-one
  outbox, and re-move-after-event handling remain to be wired.  The actor evidence
  is bound to the CHEH destination endpoint time (an engine constraint), so a
  *delayed* search that post-dates a later move is a known limitation.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from math import isclose, isfinite
from uuid import UUID, uuid4

from cpswm.contracts import (
    ActionOutcomeLikelihoodModel,
    ActorEvidenceTrack,
    ActorResponsibilityEvidence,
    BaseRecordMetadata,
    DecisionContextBinding,
    EventMechanism,
    EventMechanismEvidence,
    EvidenceRef,
    ExecutionFeedbackRecord,
    HiddenEventEvidenceTrack,
    RoleBindingEvidence,
    SourceType,
)
from cpswm.system.continual.execution_feedback_projector import ProjectionInputConflictError

from .contracts import (
    EventHypothesisHistory,
    EventHypothesisRevision,
)
from .engine import OpenWorldRoleConditionedReversibleEventRevisionEngine
from .hypothesis_message_passing import MessagePassingResult, ProvenanceConstrainedMessagePassing

# Project-one's abstract "no chain explains this" actor bucket.
UNKNOWN_ACTOR = "unknown_actor"
_PROBABILITY_FLOOR = 1e-6


class FeedbackProvenanceError(ValueError):
    """The feedback cannot be bound to this hidden-event set (firewall reject)."""


class UnsupportedFeedbackRouteError(ValueError):
    """A place/transfer route needs a transition model to revise multiple axes."""


class StaleFeedbackError(ValueError):
    """A later move happened before this feedback observed; it cannot revise this event."""


class LineageConflictError(ValueError):
    """A replayed feedback was presented against an incompatible history lineage."""


class HypothesisPosteriorInconsistencyError(RuntimeError):
    """PCHMP re-propagation and the ORRER revision disagreed on the posterior."""


@dataclass(frozen=True, slots=True)
class ActorDiscriminationEvidence:
    """A provenance-carrying, actor-discriminating likelihood channel.

    ``ratios`` maps a *known* responsible actor key to a strictly-positive, finite
    likelihood ratio; ``unknown_actor`` may be included.  ``model_version`` and
    ``source_record_id`` are mandatory -- an unsourced/unversioned channel is
    rejected, because a discriminating claim must be attributable.
    """

    ratios: Mapping[str, float]
    model_version: str
    source_record_id: UUID


@dataclass(frozen=True, slots=True)
class TransitionRevisionModel:
    """Location/mechanism/role/actor likelihoods for a place/transfer revision.

    Supplying this promotes a place/transfer feedback from *isolated* to a genuine
    multi-axis revision: mechanism (direct vs handoff), ordered handoff role, and
    (optionally) actor responsibility are each revised as reversible ORRER steps.
    """

    mechanism_posterior: Mapping[EventMechanism, float]
    mechanism_prior: Mapping[EventMechanism, float]
    ordered_role_posterior: Mapping[str, float]
    ordered_role_prior: Mapping[str, float]
    model_version: str
    source_record_id: UUID
    actor: ActorDiscriminationEvidence | None = None


class ProjectOneRequestKind(StrEnum):
    RETRACT = "retract"
    CORRECT = "correct"
    REINFORCE = "reinforce"


@dataclass(frozen=True, slots=True)
class ProjectOneStatRequest:
    """The explicit, auditable instruction project one may consume.

    Project one decides whether/how to act; this is a request, not a mutation.
    """

    kind: ProjectOneRequestKind
    superseded_revision_id: UUID
    corrected_revision_id: UUID
    event_hypothesis_id: UUID
    owner_key: str
    object_instance_id: UUID
    location_id: UUID
    owner_mass_before: float
    owner_mass_after: float
    owner_mass_delta: float
    source_feedback_record_id: UUID


@dataclass(frozen=True, slots=True)
class EventRevisionOutcome:
    """The full, reversible result of folding one feedback record into the chain."""

    superseded_revision_id: UUID
    corrected_revision_id: UUID
    hypothesis_posterior_before: dict[UUID, float]
    hypothesis_posterior_after: dict[UUID, float]
    actor_posterior_before: dict[str, float]
    actor_posterior_after: dict[str, float]
    unresolved_before: float
    unresolved_after: float
    owner_mass_before: float
    owner_mass_after: float
    source_feedback_record_id: UUID
    presence_likelihood_ratio: float
    repropagated_posterior: dict[UUID, float]
    project_one_requests: tuple[ProjectOneStatRequest, ...]
    is_replay: bool
    reason: str
    # Every source record that fed this revision: the feedback plus any actor /
    # transition-model source records, so the revision is auditable end-to-end.
    evidence_source_record_ids: tuple[UUID, ...] = ()
    # Set when a place/transfer landed at a location other than the event's
    # recorded destination -- the destination project one should move the habit to.
    corrected_destination_location_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class _CachedRevision:
    """Cached first application of one feedback record, for self-consistent replay."""

    input_fingerprint: str
    revised_history: EventHypothesisHistory
    outcome: EventRevisionOutcome


def _actor_posterior(revision: EventHypothesisRevision) -> dict[str, float]:
    """Marginalize hypothesis posteriors over the responsible actor.

    Unresolved mass is reported under the open-world ``unknown_actor`` key so the
    distribution always sums to one and never hides open-world uncertainty.
    """

    posterior: dict[str, float] = {}
    for hypothesis in revision.hypotheses:
        posterior[hypothesis.responsible_actor_key] = (
            posterior.get(hypothesis.responsible_actor_key, 0.0) + hypothesis.posterior_probability
        )
    posterior[UNKNOWN_ACTOR] = posterior.get(UNKNOWN_ACTOR, 0.0) + revision.unresolved_probability
    return posterior


def _hypothesis_posterior(revision: EventHypothesisRevision) -> dict[UUID, float]:
    return {item.hypothesis_id: item.posterior_probability for item in revision.hypotheses}


def _clamp_probability(value: float) -> float:
    return min(max(value, _PROBABILITY_FLOOR), 1.0 - _PROBABILITY_FLOOR)


def _bayes_factor(*, prior: float, posterior: float) -> float:
    """Presence Bayes factor P(obs|present)/P(obs|absent) from a prior/posterior."""

    prior = _clamp_probability(prior)
    posterior = _clamp_probability(posterior)
    return (posterior / (1.0 - posterior)) / (prior / (1.0 - prior))


class ProjectTwoFeedbackRevisionLoop:
    """Turn execution feedback into a reversible ORRER revision + project-one request."""

    def __init__(
        self,
        *,
        projector,
        engine: OpenWorldRoleConditionedReversibleEventRevisionEngine | None = None,
        message_passing: ProvenanceConstrainedMessagePassing | None = None,
        retraction_threshold: float = 0.0,
    ) -> None:
        # `projector` is an ExecutionFeedbackProjector; typed loosely to avoid a
        # continual<->cheh import cycle.
        self._projector = projector
        self._engine = engine or OpenWorldRoleConditionedReversibleEventRevisionEngine()
        self._message_passing = message_passing or ProvenanceConstrainedMessagePassing()
        self._retraction_threshold = retraction_threshold
        # feedback record id -> cached first application, for self-consistent replay.
        self._outcomes: dict[UUID, _CachedRevision] = {}

    def ingest_feedback(
        self,
        *,
        history: EventHypothesisHistory,
        feedback: ExecutionFeedbackRecord,
        binding: DecisionContextBinding,
        likelihood_model: ActionOutcomeLikelihoodModel,
        owner_key: str,
        actor_evidence: ActorDiscriminationEvidence | None = None,
        next_move_time: datetime | None = None,
        transition_model: TransitionRevisionModel | None = None,
    ) -> tuple[EventHypothesisHistory, EventRevisionOutcome]:
        """Fold one feedback record into the hidden-event chain as new evidence.

        Search (target-presence) feedback revises **event-existence confidence**;
        supplying ``actor_evidence`` adds a provenance-carrying actor-discriminating
        channel so owner/guest relative odds move.  A place/transfer feedback needs
        a ``transition_model`` and then revises mechanism, ordered role, and actor
        as reversible steps.

        ``next_move_time`` is the time of the *next* known move of the object; if
        the feedback observes after it, the observation describes a later world
        state and cannot revise this event (:class:`StaleFeedbackError` -- route it
        to the newer event instead).  Replay is idempotent, but replaying against an
        incompatible history raises :class:`LineageConflictError`; forgery is
        rejected by the projector.
        """

        record_id = feedback.metadata.record_id
        current = history.latest
        self._check_provenance(current, feedback, binding, next_move_time)
        input_fingerprint = _loop_input_fingerprint(
            owner_key=owner_key,
            actor_evidence=actor_evidence,
            transition_model=transition_model,
            next_move_time=next_move_time,
        )

        # --- 1. project & validate (dedup + forgery/input-conflict) via projector ---
        # prepare validates and detects replay/forgery WITHOUT consuming the key, so
        # a forged replay never bypasses the projector by hitting a loop-side cache.
        projected = self._projector.prepare_execution_feedback(
            feedback=feedback,
            binding=binding,
            likelihood_model=likelihood_model,
        )
        if projected.is_replay:
            cached = self._outcomes.get(record_id)
            if cached is None:
                raise FeedbackProvenanceError(
                    "replayed feedback has no committed outcome in this loop instance"
                )
            # Idempotent only against the lineage it was first applied to.
            if current.revision_id not in (
                cached.outcome.superseded_revision_id,
                cached.outcome.corrected_revision_id,
            ):
                raise LineageConflictError(
                    "replayed feedback presented against an incompatible history lineage"
                )
            # Same feedback + different actor/transition evidence is a conflict, not a replay.
            if cached.input_fingerprint != input_fingerprint:
                raise ProjectionInputConflictError(
                    "replayed feedback presented with different actor/transition evidence"
                )
            # Return the revised history (with the corrected revision), self-consistent
            # with the outcome regardless of which lineage head was presented.
            return cached.revised_history, _as_replay(cached.outcome)

        corrected_destination: UUID | None = None
        if projected.target_presence_update is not None:
            # A search must concern this event's destination.
            if feedback.attempted_location_id != current.destination_location_id:
                raise FeedbackProvenanceError(
                    "search feedback location does not match the hidden-event destination"
                )
            (
                revised_history,
                corrected,
                presence_ratio,
                repropagated,
                source_records,
            ) = self._revise_presence(history, current, projected, likelihood_model, actor_evidence)
        else:
            if transition_model is None:
                raise UnsupportedFeedbackRouteError(
                    "place/transfer feedback requires a TransitionRevisionModel to revise "
                    "mechanism/role/actor; it is not folded into a presence ratio"
                )
            # A place/transfer that landed somewhere other than the recorded
            # destination is a location signal: project one must move the habit.
            if feedback.attempted_location_id != current.destination_location_id:
                corrected_destination = feedback.attempted_location_id
            (
                revised_history,
                corrected,
                presence_ratio,
                repropagated,
                source_records,
            ) = self._revise_transition(history, current, transition_model)

        outcome = self._build_outcome(
            superseded=current,
            corrected=corrected,
            feedback=feedback,
            owner_key=owner_key,
            ratio=presence_ratio,
            repropagated=repropagated,
            source_records=source_records,
            corrected_destination=corrected_destination,
        )
        # Commit the projector idempotency key only once the revision succeeded.
        self._projector.commit_execution_feedback(projected)
        self._outcomes[record_id] = _CachedRevision(
            input_fingerprint=input_fingerprint,
            revised_history=revised_history,
            outcome=_copy_outcome(outcome, is_replay=False),
        )
        return revised_history, outcome

    def _revise_presence(
        self, history, current, projected, likelihood_model, actor_evidence
    ) -> tuple[
        EventHypothesisHistory,
        EventHypothesisRevision,
        float,
        MessagePassingResult,
        tuple[UUID, ...],
    ]:
        presence_ratio = self._presence_ratio(projected)
        evidence = self._actor_evidence(
            current,
            presence_ratio=presence_ratio,
            actor_evidence=actor_evidence,
            base_model_version=likelihood_model.model_version,
        )
        repropagated = self._message_passing.infer(history, [evidence])
        revised_history = self._engine.revise_actor_responsibility(
            history, evidence, retraction_threshold=self._retraction_threshold
        )
        corrected = revised_history.latest
        self._assert_consistent(repropagated, corrected)
        sources = () if actor_evidence is None else (actor_evidence.source_record_id,)
        return revised_history, corrected, presence_ratio, repropagated, sources

    def _revise_transition(
        self,
        history: EventHypothesisHistory,
        current: EventHypothesisRevision,
        model: TransitionRevisionModel,
    ) -> tuple[
        EventHypothesisHistory,
        EventHypothesisRevision,
        float,
        MessagePassingResult,
        tuple[UUID, ...],
    ]:
        """Multi-axis place/transfer revision: mechanism, then role, then actor.

        Each axis is a separate reversible, parent-linked ORRER revision, so the
        chain records *why* it moved on every axis and can be undone per axis.  The
        parent lineage of every appended revision is verified step by step.
        """

        if not model.model_version.strip():
            raise ValueError("transition model must carry a model version")
        mechanism = self._mechanism_evidence(current, model)
        role = self._role_evidence(current, model)
        evidences: list[object] = [mechanism, role]
        actor = None
        if model.actor is not None:
            actor = self._actor_evidence(
                current,
                presence_ratio=1.0,
                actor_evidence=model.actor,
                base_model_version=model.model_version,
            )
            evidences.append(actor)

        # Joint re-propagation over all axes must equal the sequential revision.
        repropagated = self._message_passing.infer(history, evidences)
        working = self._engine.revise_event_mechanism(
            history, mechanism, retraction_threshold=self._retraction_threshold
        )
        self._assert_child_of(working.latest, current)
        parent = working.latest
        working = self._engine.revise_role_binding(
            working, role, retraction_threshold=self._retraction_threshold
        )
        self._assert_child_of(working.latest, parent)
        if actor is not None:
            parent = working.latest
            working = self._engine.revise_actor_responsibility(
                working, actor, retraction_threshold=self._retraction_threshold
            )
            self._assert_child_of(working.latest, parent)
        corrected = working.latest
        self._assert_consistent(repropagated, corrected)
        sources = tuple(
            dict.fromkeys(
                (
                    model.source_record_id,
                    *(() if model.actor is None else (model.actor.source_record_id,)),
                )
            )
        )
        return working, corrected, 1.0, repropagated, sources

    @staticmethod
    def _assert_child_of(child: EventHypothesisRevision, parent: EventHypothesisRevision) -> None:
        if child.parent_revision_id != parent.revision_id:
            raise HypothesisPosteriorInconsistencyError(
                "multi-axis revision broke the parent lineage chain"
            )

    def _transition_metadata(
        self, current: EventHypothesisRevision, schema_name: str
    ) -> BaseRecordMetadata:
        return BaseRecordMetadata(
            record_id=uuid4(),
            schema_name=schema_name,
            schema_version=self._engine.schema_version,
            household_id=current.household_id,
            session_id=current.session_id,
            trace_id=current.trace_id,
            recorded_time=current.interval_end,
            source_type=SourceType.MODEL,
            source_id="project-two-feedback-loop",
        )

    def _mechanism_evidence(
        self, current: EventHypothesisRevision, model: TransitionRevisionModel
    ) -> EventMechanismEvidence:
        return EventMechanismEvidence(
            metadata=self._transition_metadata(current, "cpswm.EventMechanismEvidence"),
            source_detection_result_id=current.source_detection_result_ids[1],
            object_instance_id=current.object_instance_id,
            evidence_time=current.interval_end,
            mechanism_posterior=dict(model.mechanism_posterior),
            reference_mechanism_prior=dict(model.mechanism_prior),
            evidence_cluster_id=uuid4(),
            effective_sample_weight=1.0,
            evidence_track=HiddenEventEvidenceTrack.CONTROLLED_NOISE,
            evidence_model_id=model.model_version,
            evidence_refs=(
                EvidenceRef(
                    evidence_type="transition_model",
                    source_record_id=model.source_record_id,
                ),
            ),
        )

    def _role_evidence(
        self, current: EventHypothesisRevision, model: TransitionRevisionModel
    ) -> RoleBindingEvidence:
        return RoleBindingEvidence(
            metadata=self._transition_metadata(current, "cpswm.RoleBindingEvidence"),
            source_detection_result_id=current.source_detection_result_ids[1],
            object_instance_id=current.object_instance_id,
            evidence_time=current.interval_end,
            ordered_role_posterior=dict(model.ordered_role_posterior),
            reference_ordered_role_prior=dict(model.ordered_role_prior),
            evidence_cluster_id=uuid4(),
            effective_sample_weight=1.0,
            evidence_track=HiddenEventEvidenceTrack.CONTROLLED_NOISE,
            evidence_model_id=model.model_version,
            evidence_refs=(
                EvidenceRef(
                    evidence_type="transition_model",
                    source_record_id=model.source_record_id,
                ),
            ),
        )

    def _check_provenance(
        self,
        current: EventHypothesisRevision,
        feedback: ExecutionFeedbackRecord,
        binding: DecisionContextBinding,
        next_move_time: datetime | None,
    ) -> None:
        """Bind the feedback to this exact hidden event: object, place, HST, causality."""

        if feedback.target_entity is None:
            raise FeedbackProvenanceError("feedback has no target entity to bind")
        if feedback.target_entity.entity_id != current.object_instance_id:
            raise FeedbackProvenanceError(
                "feedback target object does not match the hidden-event set"
            )
        for field_name in ("household_id", "session_id", "trace_id"):
            if getattr(feedback.metadata, field_name) != getattr(current, field_name):
                raise FeedbackProvenanceError(f"feedback {field_name} does not match the event set")
            if getattr(binding, f"subject_{field_name}") != getattr(current, field_name):
                raise FeedbackProvenanceError(f"binding {field_name} does not match the event set")
        # (Location is checked per-route: a search must match the destination; a
        # place elsewhere is a location signal, not a provenance error.)
        # Causal window: feedback must observe the world *after* the event closed.
        if feedback.valid_time.start < current.interval_end:
            raise FeedbackProvenanceError(
                "feedback precedes the hidden-event end; not a valid post-event observation"
            )
        # A subsequent move already happened during or before the feedback's
        # observation window: the window is contaminated by the newer world state,
        # so the feedback cannot revise this event.
        if next_move_time is not None:
            window_end = feedback.valid_time.end or feedback.valid_time.start
            if window_end >= next_move_time or feedback.valid_time.start >= next_move_time:
                raise StaleFeedbackError(
                    "feedback window crosses a subsequent move; revise the newer event instead"
                )

    def _presence_ratio(self, projected) -> float:
        """Presence Bayes factor for a target-presence route (caller guarantees one)."""

        update = projected.target_presence_update
        assert update is not None  # routing guaranteed by ingest_feedback
        return _bayes_factor(
            prior=update.prior_target_present,
            posterior=update.posterior_target_present,
        )

    def _assert_consistent(
        self, repropagated: MessagePassingResult, corrected: EventHypothesisRevision
    ) -> None:
        after = {
            item.hypothesis_id: item.posterior_probability for item in corrected.active_hypotheses
        }
        for hypothesis_id, mass in repropagated.posterior_by_hypothesis_id.items():
            if not isclose(mass, after.get(hypothesis_id, 0.0), rel_tol=0.0, abs_tol=1e-9):
                raise HypothesisPosteriorInconsistencyError(
                    "PCHMP re-propagation disagrees with the ORRER revision posterior"
                )
        if not isclose(
            repropagated.unresolved_probability,
            corrected.unresolved_probability,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise HypothesisPosteriorInconsistencyError(
                "PCHMP and ORRER disagree on unresolved mass"
            )

    def _actor_evidence(
        self,
        current: EventHypothesisRevision,
        *,
        presence_ratio: float,
        actor_evidence: ActorDiscriminationEvidence | None,
        base_model_version: str,
    ) -> ActorResponsibilityEvidence:
        """Encode presence x per-actor evidence as firewall-legal actor evidence.

        Each responsible known actor carries ``presence_ratio`` (all assert the
        object reached the destination) multiplied by its own discriminating factor
        (default 1.0); the ``unknown_actor`` bucket carries a neutral ratio so a
        failed observation shifts mass toward open-world uncertainty.  When the
        per-actor factors differ, owner/guest relative odds genuinely change.
        """

        responsible = {item.responsible_actor_key for item in current.hypotheses}
        support = sorted(responsible | {UNKNOWN_ACTOR})
        factors = self._validated_actor_factors(actor_evidence, support)
        model_id = base_model_version
        if actor_evidence is not None:
            model_id = f"{model_id}+{actor_evidence.model_version}"
        uniform = 1.0 / len(support)
        reference_actor_prior = {actor: uniform for actor in support}
        raw = {
            actor: (
                uniform * factors.get(actor, 1.0)
                if actor == UNKNOWN_ACTOR
                else uniform * presence_ratio * factors.get(actor, 1.0)
            )
            for actor in support
        }
        total = sum(raw.values())
        if total <= 0.0:
            raise ValueError("actor evidence collapsed to zero mass")
        actor_posterior = {actor: value / total for actor, value in raw.items()}

        destination_detection_id = current.source_detection_result_ids[1]
        evidence_time: datetime = current.interval_end
        metadata = BaseRecordMetadata(
            record_id=uuid4(),
            schema_name="cpswm.ActorResponsibilityEvidence",
            schema_version=self._engine.schema_version,
            household_id=current.household_id,
            session_id=current.session_id,
            trace_id=current.trace_id,
            recorded_time=evidence_time,
            source_type=SourceType.MODEL,
            source_id="project-two-feedback-loop",
        )
        evidence_refs: tuple[EvidenceRef, ...] = ()
        if actor_evidence is not None:
            evidence_refs = (
                EvidenceRef(
                    evidence_type="actor_discrimination",
                    source_record_id=actor_evidence.source_record_id,
                ),
            )
        return ActorResponsibilityEvidence(
            metadata=metadata,
            source_detection_result_id=destination_detection_id,
            object_instance_id=current.object_instance_id,
            evidence_time=evidence_time,
            actor_posterior=actor_posterior,
            reference_actor_prior=reference_actor_prior,
            evidence_cluster_id=uuid4(),
            effective_sample_weight=1.0,
            evidence_track=ActorEvidenceTrack.CONTROLLED_NOISE,
            evidence_model_id=model_id,
            evidence_refs=evidence_refs,
        )

    @staticmethod
    def _validated_actor_factors(
        actor_evidence: ActorDiscriminationEvidence | None, support: list[str]
    ) -> dict[str, float]:
        """Validate an actor-discriminating channel: sourced, versioned, finite, >0, known."""

        if actor_evidence is None:
            return {}
        if not actor_evidence.model_version.strip():
            raise ValueError("actor discrimination evidence must carry a model version")
        known = set(support)
        factors: dict[str, float] = {}
        for actor, value in actor_evidence.ratios.items():
            if actor not in known:
                raise ValueError(f"actor likelihood ratio names an unknown actor: {actor!r}")
            numeric = float(value)
            if not isfinite(numeric):
                raise ValueError("actor likelihood ratios must be finite (no NaN/inf)")
            if numeric <= 0.0:
                raise ValueError("actor likelihood ratios must be strictly positive")
            factors[actor] = numeric
        return factors

    def _build_outcome(
        self,
        *,
        superseded: EventHypothesisRevision,
        corrected: EventHypothesisRevision,
        feedback: ExecutionFeedbackRecord,
        owner_key: str,
        ratio: float,
        repropagated: MessagePassingResult,
        source_records: tuple[UUID, ...],
        corrected_destination: UUID | None,
    ) -> EventRevisionOutcome:
        actor_before = _actor_posterior(superseded)
        actor_after = _actor_posterior(corrected)
        owner_before = actor_before.get(owner_key, 0.0)
        owner_after = actor_after.get(owner_key, 0.0)
        delta = owner_after - owner_before
        # Where project one should hold the habit: the corrected destination when a
        # place landed elsewhere, otherwise the event's recorded destination.
        request_location = corrected_destination or corrected.destination_location_id

        requests: tuple[ProjectOneStatRequest, ...] = ()
        # A moved destination is itself an actionable location correction, even when
        # the owner mass is unchanged.
        if abs(delta) > _PROBABILITY_FLOOR or corrected_destination is not None:
            if corrected_destination is not None or delta < 0.0:
                kind = (
                    ProjectOneRequestKind.RETRACT
                    if owner_after <= 0.0 and corrected_destination is None
                    else ProjectOneRequestKind.CORRECT
                )
            else:
                kind = ProjectOneRequestKind.REINFORCE
            requests = (
                ProjectOneStatRequest(
                    kind=kind,
                    superseded_revision_id=superseded.revision_id,
                    corrected_revision_id=corrected.revision_id,
                    event_hypothesis_id=corrected.hypothesis_set_id,
                    owner_key=owner_key,
                    object_instance_id=corrected.object_instance_id,
                    location_id=request_location,
                    owner_mass_before=owner_before,
                    owner_mass_after=owner_after,
                    owner_mass_delta=delta,
                    source_feedback_record_id=feedback.metadata.record_id,
                ),
            )

        return EventRevisionOutcome(
            superseded_revision_id=superseded.revision_id,
            corrected_revision_id=corrected.revision_id,
            hypothesis_posterior_before=_hypothesis_posterior(superseded),
            hypothesis_posterior_after=_hypothesis_posterior(corrected),
            actor_posterior_before=actor_before,
            actor_posterior_after=actor_after,
            unresolved_before=superseded.unresolved_probability,
            unresolved_after=corrected.unresolved_probability,
            owner_mass_before=owner_before,
            owner_mass_after=owner_after,
            source_feedback_record_id=feedback.metadata.record_id,
            presence_likelihood_ratio=ratio,
            repropagated_posterior=dict(repropagated.posterior_by_hypothesis_id),
            project_one_requests=requests,
            is_replay=False,
            reason="execution feedback folded as reversible actor-responsibility evidence",
            evidence_source_record_ids=(feedback.metadata.record_id, *source_records),
            corrected_destination_location_id=corrected_destination,
        )


def _copy_outcome(outcome: EventRevisionOutcome, *, is_replay: bool) -> EventRevisionOutcome:
    """Return an independent copy so mutating one outcome cannot pollute the other.

    Every mutable mapping is copied, so a caller that mutates the first returned
    outcome's dicts can never change the cached copy served on replay (and vice
    versa).  ``project_one_requests`` is a tuple of frozen dataclasses (immutable).
    """

    return EventRevisionOutcome(
        superseded_revision_id=outcome.superseded_revision_id,
        corrected_revision_id=outcome.corrected_revision_id,
        hypothesis_posterior_before=dict(outcome.hypothesis_posterior_before),
        hypothesis_posterior_after=dict(outcome.hypothesis_posterior_after),
        actor_posterior_before=dict(outcome.actor_posterior_before),
        actor_posterior_after=dict(outcome.actor_posterior_after),
        unresolved_before=outcome.unresolved_before,
        unresolved_after=outcome.unresolved_after,
        owner_mass_before=outcome.owner_mass_before,
        owner_mass_after=outcome.owner_mass_after,
        source_feedback_record_id=outcome.source_feedback_record_id,
        presence_likelihood_ratio=outcome.presence_likelihood_ratio,
        repropagated_posterior=dict(outcome.repropagated_posterior),
        project_one_requests=outcome.project_one_requests,
        is_replay=is_replay,
        reason=outcome.reason,
        evidence_source_record_ids=outcome.evidence_source_record_ids,
        corrected_destination_location_id=outcome.corrected_destination_location_id,
    )


def _as_replay(outcome: EventRevisionOutcome) -> EventRevisionOutcome:
    return _copy_outcome(outcome, is_replay=True)


def _loop_input_fingerprint(
    *,
    owner_key: str,
    actor_evidence: ActorDiscriminationEvidence | None,
    transition_model: TransitionRevisionModel | None,
    next_move_time: datetime | None,
) -> str:
    """Fingerprint the loop-level inputs the projector does not already cover.

    The projector fingerprints the feedback, context, and likelihood model; this
    covers the actor-discrimination channel, the transition model, the owner key,
    and the move window, so a replay of the same feedback with *different* such
    inputs is detected as a conflict.
    """

    def _actor(evidence: ActorDiscriminationEvidence | None) -> object:
        if evidence is None:
            return None
        return {
            "ratios": {actor: repr(float(v)) for actor, v in sorted(evidence.ratios.items())},
            "model_version": evidence.model_version,
            "source_record_id": str(evidence.source_record_id),
        }

    payload = {
        "owner_key": owner_key,
        "next_move_time": None if next_move_time is None else next_move_time.isoformat(),
        "actor_evidence": _actor(actor_evidence),
        "transition_model": None
        if transition_model is None
        else {
            "mechanism_posterior": {
                m.value: repr(float(v))
                for m, v in sorted(
                    transition_model.mechanism_posterior.items(), key=lambda kv: kv[0].value
                )
            },
            "mechanism_prior": {
                m.value: repr(float(v))
                for m, v in sorted(
                    transition_model.mechanism_prior.items(), key=lambda kv: kv[0].value
                )
            },
            "ordered_role_posterior": {
                k: repr(float(v))
                for k, v in sorted(transition_model.ordered_role_posterior.items())
            },
            "ordered_role_prior": {
                k: repr(float(v)) for k, v in sorted(transition_model.ordered_role_prior.items())
            },
            "model_version": transition_model.model_version,
            "source_record_id": str(transition_model.source_record_id),
            "actor": _actor(transition_model.actor),
        },
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def apply_project_one_request(request: ProjectOneStatRequest, loop) -> bool:
    """Consume a project-two request into a project-one owner-habit loop.

    Project one keys its ledger by the CHEH revision id, so the request's
    superseded/corrected revision ids map directly onto the loop's retract/replace
    operations.  Returns True when project-one state was changed.

    A ``CorePrototypeSpine``-compatible consumer handles every request kind as a
    revision transaction across Dirichlet, RLS, and Hybrid RGRC.  The narrower
    Hybrid-only adapter below remains for legacy coordinator-loop callers.
    """

    from cpswm.system.continual.hybrid_event_to_task_loop import OwnerPlacementInput

    apply_all = getattr(loop, "apply_project_one_stat_request", None)
    if apply_all is not None:
        apply_all(request)
        return True

    if request.kind is ProjectOneRequestKind.RETRACT:
        loop.retract_revision(request.superseded_revision_id)
        return True
    # CORRECT lowers and REINFORCE raises owner mass; both are a reversible replace
    # of the superseded revision with the corrected owner mass -- a real update.
    loop.apply_orrer_revision(
        superseded_revision_id=request.superseded_revision_id,
        corrected=OwnerPlacementInput(
            event_hypothesis_id=request.event_hypothesis_id,
            revision_id=request.corrected_revision_id,
            destination_location_id=request.location_id,
            owner_mass=request.owner_mass_after,
            source_record_id=request.source_feedback_record_id,
            parent_revision_id=request.superseded_revision_id,
        ),
    )
    return True


__all__ = [
    "UNKNOWN_ACTOR",
    "ActorDiscriminationEvidence",
    "EventRevisionOutcome",
    "FeedbackProvenanceError",
    "HypothesisPosteriorInconsistencyError",
    "LineageConflictError",
    "ProjectOneRequestKind",
    "ProjectOneStatRequest",
    "ProjectTwoFeedbackRevisionLoop",
    "StaleFeedbackError",
    "TransitionRevisionModel",
    "UnsupportedFeedbackRouteError",
    "apply_project_one_request",
]
