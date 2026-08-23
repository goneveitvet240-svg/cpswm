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

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from math import isclose
from uuid import UUID, uuid4

from cpswm.contracts import (
    ActionOutcomeLikelihoodModel,
    ActorEvidenceTrack,
    ActorResponsibilityEvidence,
    BaseRecordMetadata,
    DecisionContextBinding,
    ExecutionFeedbackRecord,
    SourceType,
)

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
    """The projected route has no honest hidden-event evidence mapping yet."""


class HypothesisPosteriorInconsistencyError(RuntimeError):
    """PCHMP re-propagation and the ORRER revision disagreed on the posterior."""


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
        # feedback record id -> outcome, for idempotent replay.
        self._outcomes: dict[UUID, EventRevisionOutcome] = {}

    def ingest_feedback(
        self,
        *,
        history: EventHypothesisHistory,
        feedback: ExecutionFeedbackRecord,
        binding: DecisionContextBinding,
        likelihood_model: ActionOutcomeLikelihoodModel,
        owner_key: str,
        actor_likelihood_ratios: Mapping[str, float] | None = None,
    ) -> tuple[EventHypothesisHistory, EventRevisionOutcome]:
        """Fold one feedback record into the hidden-event chain as new evidence.

        Two revision modes, combinable:

        * **event-existence confidence** (default) -- a presence outcome (search)
          re-weights every responsible known actor by the *same* presence Bayes
          factor, shifting mass between the explained chains and unresolved/unknown.
          It cannot, by itself, change owner-vs-guest relative odds.
        * **actor responsibility** -- when ``actor_likelihood_ratios`` is supplied
          (an actor-discriminating observation channel), each known actor is
          re-weighted by its *own* ratio, so owner/guest/robot/unknown relative
          odds do change.  The two are multiplied when both are present.

        A replayed feedback record is idempotent; forgery (same record id, different
        content/inputs) is rejected by the projector before any mutation.
        """

        record_id = feedback.metadata.record_id
        current = history.latest
        self._check_provenance(current, feedback, binding)

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
            return history, _as_replay(cached)

        presence_ratio = self._presence_ratio(projected)

        # --- 2. actor evidence: presence (event-existence) x per-actor discrimination ---
        evidence = self._actor_evidence(
            current,
            presence_ratio=presence_ratio,
            actor_factors=actor_likelihood_ratios,
            likelihood_model=likelihood_model,
        )

        # --- 3. re-propagate the joint posterior (firewall + single-consumption) ---
        repropagated: MessagePassingResult = self._message_passing.infer(history, [evidence])

        # --- 4. one reversible, parent-linked ORRER revision ---
        revised_history = self._engine.revise_actor_responsibility(
            history, evidence, retraction_threshold=self._retraction_threshold
        )
        corrected = revised_history.latest

        # --- 5. PCHMP and ORRER must agree, or we refuse a contradictory output ---
        self._assert_consistent(repropagated, corrected)

        # --- 6. assemble the reversible outcome + explicit project-one request ---
        outcome = self._build_outcome(
            superseded=current,
            corrected=corrected,
            feedback=feedback,
            owner_key=owner_key,
            ratio=presence_ratio,
            repropagated=repropagated,
        )
        # Commit the projector idempotency key only once the revision succeeded.
        self._projector.commit_execution_feedback(projected)
        self._outcomes[record_id] = outcome
        return revised_history, outcome

    def _check_provenance(
        self,
        current: EventHypothesisRevision,
        feedback: ExecutionFeedbackRecord,
        binding: DecisionContextBinding,
    ) -> None:
        """Bind the feedback to this exact hidden event: object, place, HST, causality."""

        if feedback.target_entity is None:
            raise FeedbackProvenanceError("feedback has no target entity to bind")
        if feedback.target_entity.entity_id != current.object_instance_id:
            raise FeedbackProvenanceError(
                "feedback target object does not match the hidden-event set"
            )
        if feedback.attempted_location_id != current.destination_location_id:
            raise FeedbackProvenanceError(
                "feedback location does not match the hidden-event destination"
            )
        for field_name in ("household_id", "session_id", "trace_id"):
            if getattr(feedback.metadata, field_name) != getattr(current, field_name):
                raise FeedbackProvenanceError(f"feedback {field_name} does not match the event set")
            if getattr(binding, f"subject_{field_name}") != getattr(current, field_name):
                raise FeedbackProvenanceError(f"binding {field_name} does not match the event set")
        # Causal window: feedback must observe the world *after* the event closed.
        if feedback.valid_time.start < current.interval_end:
            raise FeedbackProvenanceError(
                "feedback precedes the hidden-event end; not a valid post-event observation"
            )

    def _presence_ratio(self, projected) -> float:
        """Presence Bayes factor for a target-presence route.

        Place/transfer feedback is deliberately *isolated*: the projector reports it
        only as an action success/slip candidate, not a transition/presence/actor
        posterior, so folding it in as a presence ratio would silently mislabel a
        gripper slip as reduced historical responsibility.  Until a real
        location/mechanism/role likelihood model is wired, that route is rejected.
        """

        update = projected.target_presence_update
        if update is not None:
            return _bayes_factor(
                prior=update.prior_target_present,
                posterior=update.posterior_target_present,
            )
        raise UnsupportedFeedbackRouteError(
            "place/transfer feedback has no honest hidden-event mapping yet "
            "(needs a location/mechanism/role likelihood model); route isolated"
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
        actor_factors: Mapping[str, float] | None,
        likelihood_model: ActionOutcomeLikelihoodModel,
    ) -> ActorResponsibilityEvidence:
        """Encode presence x per-actor evidence as firewall-legal actor evidence.

        Each responsible known actor carries ``presence_ratio`` (all assert the
        object reached the destination) multiplied by its own discriminating factor
        (default 1.0); the ``unknown_actor`` bucket carries a neutral ratio so a
        failed observation shifts mass toward open-world uncertainty.  When the
        per-actor factors differ, owner/guest relative odds genuinely change.
        """

        factors = dict(actor_factors or {})
        if any(value < 0.0 for value in factors.values()):
            raise ValueError("actor likelihood ratios cannot be negative")
        responsible = {item.responsible_actor_key for item in current.hypotheses}
        support = sorted(responsible | {UNKNOWN_ACTOR})
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
            evidence_model_id=likelihood_model.model_version,
        )

    def _build_outcome(
        self,
        *,
        superseded: EventHypothesisRevision,
        corrected: EventHypothesisRevision,
        feedback: ExecutionFeedbackRecord,
        owner_key: str,
        ratio: float,
        repropagated: MessagePassingResult,
    ) -> EventRevisionOutcome:
        actor_before = _actor_posterior(superseded)
        actor_after = _actor_posterior(corrected)
        owner_before = actor_before.get(owner_key, 0.0)
        owner_after = actor_after.get(owner_key, 0.0)
        delta = owner_after - owner_before

        requests: tuple[ProjectOneStatRequest, ...] = ()
        if abs(delta) > _PROBABILITY_FLOOR:
            if delta < 0.0:
                kind = (
                    ProjectOneRequestKind.RETRACT
                    if owner_after <= 0.0
                    else (ProjectOneRequestKind.CORRECT)
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
                    location_id=corrected.destination_location_id,
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
        )


def _as_replay(outcome: EventRevisionOutcome) -> EventRevisionOutcome:
    return EventRevisionOutcome(
        superseded_revision_id=outcome.superseded_revision_id,
        corrected_revision_id=outcome.corrected_revision_id,
        hypothesis_posterior_before=outcome.hypothesis_posterior_before,
        hypothesis_posterior_after=outcome.hypothesis_posterior_after,
        actor_posterior_before=outcome.actor_posterior_before,
        actor_posterior_after=outcome.actor_posterior_after,
        unresolved_before=outcome.unresolved_before,
        unresolved_after=outcome.unresolved_after,
        owner_mass_before=outcome.owner_mass_before,
        owner_mass_after=outcome.owner_mass_after,
        source_feedback_record_id=outcome.source_feedback_record_id,
        presence_likelihood_ratio=outcome.presence_likelihood_ratio,
        repropagated_posterior=outcome.repropagated_posterior,
        project_one_requests=outcome.project_one_requests,
        is_replay=True,
        reason=outcome.reason,
    )


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
    if request.kind is ProjectOneRequestKind.CORRECT:
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
    # REINFORCE: intentionally unmapped for now (see docstring).
    return False


__all__ = [
    "UNKNOWN_ACTOR",
    "EventRevisionOutcome",
    "FeedbackProvenanceError",
    "HypothesisPosteriorInconsistencyError",
    "ProjectOneRequestKind",
    "ProjectOneStatRequest",
    "ProjectTwoFeedbackRevisionLoop",
    "UnsupportedFeedbackRouteError",
    "apply_project_one_request",
]
