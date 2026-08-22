"""Likelihood-aware execution-feedback projection and routing (总纲 §2.11/§2.12).

Review fix #4: an uncertain action outcome must not be written into long-term
memory directly.  This projector turns an :class:`ExecutionFeedbackRecord` into
likelihood-aware evidence (via an :class:`ActionOutcomeLikelihoodModel`) and
routes it by *what the outcome can license*:

* a find/observe outcome (search/navigate/grasp) updates **target presence**
  only -- it must never increase an owner habit;
* a place/transfer outcome is a candidate **location transition**, but *whose*
  habit it feeds still requires actor-responsibility inference, so it is routed
  as ``requires_actor_responsibility`` rather than consolidated directly.

Every projection is de-duplicated by feedback record id: replaying the same
feedback is a no-op (``is_replay=True``).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from cpswm.contracts import (
    ActionOutcomeLikelihoodModel,
    DecisionContextBinding,
    ExecutionFeedbackRecord,
    FeedbackBeliefUpdate,
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
class ProjectedFeedbackEvidence:
    """The routed, likelihood-aware result of one execution feedback record."""

    feedback_record_id: UUID
    route: FeedbackRoute
    target_presence_update: FeedbackBeliefUpdate | None
    location_id: UUID | None
    requires_actor_responsibility: bool
    updates_owner_habit_directly: bool
    is_replay: bool
    rationale: str


class ExecutionFeedbackProjector:
    """Project execution feedback into typed, de-duplicated belief evidence."""

    def __init__(self) -> None:
        self._seen: dict[UUID, ProjectedFeedbackEvidence] = {}

    def project(
        self,
        *,
        feedback: ExecutionFeedbackRecord,
        binding: DecisionContextBinding,
        likelihood_model: ActionOutcomeLikelihoodModel,
        prior_target_present: float,
    ) -> ProjectedFeedbackEvidence:
        if not 0.0 <= prior_target_present <= 1.0:
            raise ValueError("prior_target_present must be a probability")
        if likelihood_model.action_type != feedback.action_type:
            raise ValueError("likelihood model action type must match the feedback")
        if binding.subject_record_id != feedback.metadata.record_id:
            raise ValueError("decision-context binding must reference this feedback record")
        if set(feedback.outcome_distribution) - set(
            likelihood_model.p_outcome_given_target_present
        ):
            raise ValueError("likelihood model must cover every observed outcome")

        record_id = feedback.metadata.record_id
        cached = self._seen.get(record_id)
        if cached is not None:
            # Replaying identical feedback is a no-op.
            return ProjectedFeedbackEvidence(
                feedback_record_id=cached.feedback_record_id,
                route=cached.route,
                target_presence_update=cached.target_presence_update,
                location_id=cached.location_id,
                requires_actor_responsibility=cached.requires_actor_responsibility,
                updates_owner_habit_directly=cached.updates_owner_habit_directly,
                is_replay=True,
                rationale="replayed feedback record; no-op",
            )

        present_ll = sum(
            probability * likelihood_model.p_outcome_given_target_present[outcome]
            for outcome, probability in feedback.outcome_distribution.items()
        )
        absent_ll = sum(
            probability * likelihood_model.p_outcome_given_target_absent[outcome]
            for outcome, probability in feedback.outcome_distribution.items()
        )
        numerator = prior_target_present * present_ll
        denominator = numerator + (1.0 - prior_target_present) * absent_ll
        posterior = numerator / denominator if denominator > 0.0 else prior_target_present
        likelihood_ratio = present_ll / absent_ll if absent_ll > 0.0 else None
        update = FeedbackBeliefUpdate(
            feedback_record_id=record_id,
            prior_target_present=prior_target_present,
            posterior_target_present=posterior,
            likelihood_ratio=likelihood_ratio,
            outcome_model_version=likelihood_model.model_version,
        )

        if feedback.action_type in _LOCATION_TRANSITION_ACTIONS:
            projected = ProjectedFeedbackEvidence(
                feedback_record_id=record_id,
                route=FeedbackRoute.LOCATION_TRANSITION,
                target_presence_update=update,
                location_id=feedback.attempted_location_id,
                requires_actor_responsibility=True,
                updates_owner_habit_directly=False,
                rationale="place/transfer outcome: candidate location transition; "
                "owner-habit attribution requires actor responsibility",
                is_replay=False,
            )
        elif feedback.action_type in _TARGET_PRESENCE_ACTIONS:
            projected = ProjectedFeedbackEvidence(
                feedback_record_id=record_id,
                route=FeedbackRoute.TARGET_PRESENCE,
                target_presence_update=update,
                location_id=feedback.attempted_location_id,
                requires_actor_responsibility=False,
                updates_owner_habit_directly=False,
                rationale="find/observe outcome updates target presence only; not owner habit",
                is_replay=False,
            )
        else:  # pragma: no cover - RobotActionType is exhaustively covered above
            raise ValueError(f"unroutable action type {feedback.action_type}")

        self._seen[record_id] = projected
        return projected
