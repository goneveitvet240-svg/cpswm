"""Likelihood-aware execution-feedback projection and routing (总纲 §2.11/§2.12).

Review fix #4 (hardened): an uncertain action outcome must not be written into
long-term memory directly.  The projector re-validates all three input contracts,
checks surface / household-session-trace / target object / context hash / valid
time, reads its prior from the *bound snapshot* (never a caller argument), and
de-duplicates by ``(record_id, content_hash)`` so a forged replay is caught.

Routing:

* find/observe (search/navigate/grasp) -> a **target-presence** update only; it
  can never increase an owner habit;
* place/transfer -> a distinct :class:`LocationTransitionEvidence` scored by a
  transition-success likelihood, where a *slip* is never a positive transition;
  owner-habit attribution still requires actor responsibility.

The entry point is named :meth:`project_execution_feedback`: it *projects and
routes* evidence.  It does not itself write a presence log, map, or ORRER outbox
(that wiring lands after the map/ORRER core files are handed over).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from cpswm.contracts import (
    ActionOutcomeLikelihoodModel,
    DecisionContextBinding,
    DecisionSurface,
    EntityType,
    ExecutionFeedbackRecord,
    FeedbackBeliefUpdate,
    RobotActionOutcome,
    RobotActionType,
)

_TARGET_PRESENCE_ACTIONS = frozenset(
    {RobotActionType.SEARCH, RobotActionType.NAVIGATE, RobotActionType.GRASP}
)
_LOCATION_TRANSITION_ACTIONS = frozenset({RobotActionType.PLACE, RobotActionType.TRANSFER})


class FeedbackRoute(StrEnum):
    TARGET_PRESENCE = "target_presence"
    LOCATION_TRANSITION = "location_transition"


@dataclass(frozen=True, slots=True)
class LocationTransitionEvidence:
    """A place/transfer outcome scored as a candidate location transition.

    A slip is explicitly *not* a positive transition: the object did not end up
    placed, so ``is_positive_transition`` is false and cannot feed a habit.
    """

    feedback_record_id: UUID
    location_id: UUID
    transition_success_probability: float
    slipped_probability: float
    is_positive_transition: bool


@dataclass(frozen=True, slots=True)
class ProjectedFeedbackEvidence:
    """The routed, likelihood-aware result of one execution feedback record."""

    feedback_record_id: UUID
    content_hash: str
    route: FeedbackRoute
    target_presence_update: FeedbackBeliefUpdate | None
    location_transition: LocationTransitionEvidence | None
    requires_actor_responsibility: bool
    updates_owner_habit_directly: bool
    is_replay: bool
    rationale: str


def _feedback_content_hash(feedback: ExecutionFeedbackRecord) -> str:
    return hashlib.sha256(feedback.model_dump_json().encode("utf-8")).hexdigest()


class ExecutionFeedbackProjector:
    """Project execution feedback into typed, de-duplicated belief evidence."""

    def __init__(self) -> None:
        self._seen: dict[UUID, ProjectedFeedbackEvidence] = {}

    def project_execution_feedback(
        self,
        *,
        feedback: ExecutionFeedbackRecord,
        binding: DecisionContextBinding,
        likelihood_model: ActionOutcomeLikelihoodModel,
    ) -> ProjectedFeedbackEvidence:
        # Re-validate all three contracts at the trust boundary (schema).
        feedback = ExecutionFeedbackRecord.model_validate(feedback.model_dump())
        binding = DecisionContextBinding.model_validate(binding.model_dump())
        likelihood_model = ActionOutcomeLikelihoodModel.model_validate(
            likelihood_model.model_dump()
        )

        self._check_binding(feedback, binding)
        if likelihood_model.action_type != feedback.action_type:
            raise ValueError("likelihood model action type must match the feedback")
        if set(feedback.outcome_distribution) - set(
            likelihood_model.p_outcome_given_target_present
        ):
            raise ValueError("likelihood model must cover every observed outcome")

        context = binding.decision_context
        prior = context.target_presence_prior
        if prior is None:
            raise ValueError("bound decision context must carry a target_presence_prior")

        record_id = feedback.metadata.record_id
        content_hash = _feedback_content_hash(feedback)
        cached = self._seen.get(record_id)
        if cached is not None:
            if cached.content_hash != content_hash:
                raise ValueError(
                    "feedback record id reused with different content (collision/forgery)"
                )
            return _as_replay(cached)

        if feedback.action_type in _LOCATION_TRANSITION_ACTIONS:
            projected = self._location_transition(feedback, content_hash)
        else:
            projected = ProjectedFeedbackEvidence(
                feedback_record_id=record_id,
                content_hash=content_hash,
                route=FeedbackRoute.TARGET_PRESENCE,
                target_presence_update=self._target_presence_update(
                    feedback, likelihood_model, prior
                ),
                location_transition=None,
                requires_actor_responsibility=False,
                updates_owner_habit_directly=False,
                is_replay=False,
                rationale="find/observe outcome updates target presence only; not owner habit",
            )
        self._seen[record_id] = projected
        return projected

    def _check_binding(
        self, feedback: ExecutionFeedbackRecord, binding: DecisionContextBinding
    ) -> None:
        if binding.surface is not DecisionSurface.EXECUTION_FEEDBACK:
            raise ValueError("feedback binding surface must be execution_feedback")
        if binding.subject_record_id != feedback.metadata.record_id:
            raise ValueError("decision-context binding must reference this feedback record")
        for name in ("household_id", "session_id", "trace_id"):
            if getattr(binding.metadata, name) != getattr(feedback.metadata, name):
                raise ValueError(f"binding {name} does not match the feedback record")
        if feedback.target_entity is None or feedback.target_entity.entity_type != (
            EntityType.OBJECT_INSTANCE
        ):
            raise ValueError("feedback must bind an object-instance target entity")
        context = binding.decision_context
        if not context.verify_hash():
            raise ValueError("bound decision context hash is invalid")
        if not context.valid_time.contains(feedback.valid_time.start):
            raise ValueError("feedback occurred outside the decision context valid time")

    def _target_presence_update(
        self,
        feedback: ExecutionFeedbackRecord,
        likelihood_model: ActionOutcomeLikelihoodModel,
        prior: float,
    ) -> FeedbackBeliefUpdate:
        present_ll = sum(
            probability * likelihood_model.p_outcome_given_target_present[outcome]
            for outcome, probability in feedback.outcome_distribution.items()
        )
        absent_ll = sum(
            probability * likelihood_model.p_outcome_given_target_absent[outcome]
            for outcome, probability in feedback.outcome_distribution.items()
        )
        numerator = prior * present_ll
        denominator = numerator + (1.0 - prior) * absent_ll
        posterior = numerator / denominator if denominator > 0.0 else prior
        likelihood_ratio = present_ll / absent_ll if absent_ll > 0.0 else None
        return FeedbackBeliefUpdate(
            feedback_record_id=feedback.metadata.record_id,
            prior_target_present=prior,
            posterior_target_present=posterior,
            likelihood_ratio=likelihood_ratio,
            outcome_model_version=likelihood_model.model_version,
        )

    def _location_transition(
        self, feedback: ExecutionFeedbackRecord, content_hash: str
    ) -> ProjectedFeedbackEvidence:
        if feedback.attempted_location_id is None:
            raise ValueError("place/transfer feedback must record an attempted location")
        success = feedback.outcome_distribution.get(RobotActionOutcome.SUCCESS, 0.0)
        slipped = feedback.outcome_distribution.get(RobotActionOutcome.OBJECT_SLIPPED, 0.0)
        # A slip is never a positive transition: the object was not placed.
        transition = LocationTransitionEvidence(
            feedback_record_id=feedback.metadata.record_id,
            location_id=feedback.attempted_location_id,
            transition_success_probability=success,
            slipped_probability=slipped,
            is_positive_transition=success > 0.5 and success > slipped,
        )
        return ProjectedFeedbackEvidence(
            feedback_record_id=feedback.metadata.record_id,
            content_hash=content_hash,
            route=FeedbackRoute.LOCATION_TRANSITION,
            target_presence_update=None,
            location_transition=transition,
            requires_actor_responsibility=True,
            updates_owner_habit_directly=False,
            is_replay=False,
            rationale="place/transfer: candidate location transition; owner-habit "
            "attribution requires actor responsibility; a slip is not a transition",
        )


def _as_replay(evidence: ProjectedFeedbackEvidence) -> ProjectedFeedbackEvidence:
    return ProjectedFeedbackEvidence(
        feedback_record_id=evidence.feedback_record_id,
        content_hash=evidence.content_hash,
        route=evidence.route,
        target_presence_update=evidence.target_presence_update,
        location_transition=evidence.location_transition,
        requires_actor_responsibility=evidence.requires_actor_responsibility,
        updates_owner_habit_directly=evidence.updates_owner_habit_directly,
        is_replay=True,
        rationale="replayed feedback record; no-op",
    )
