"""Likelihood-aware execution-feedback projection and routing (总纲 §2.11/§2.12).

Review fix #4 (round 3): an uncertain action outcome must not be written into
long-term memory directly, its prior must be *bound to the snapshot node* it came
from, and de-duplication must cover the full projection inputs.

* **Prior is snapshot-bound** (P0-1): read from a :class:`TargetPresenceBeliefRef`
  on the bound decision context; the projector checks the ref's object, location,
  and belief_snapshot_id match the feedback/context (the ``node_content_hash``
  vs live-map reconciliation lands at #4 tail).
* **De-dup covers projection inputs** (P0-2): a ``feedback_content_hash`` proves
  source integrity; a ``projection_input_hash`` also covers the context hash, the
  likelihood model, and the projector version.  Same feedback with different
  projection inputs is hard-rejected, never silently replayed.
* **Honest transition semantics** (P0-3): the likelihood model here is a
  target-presence likelihood, so place/transfer output is reported as
  ``reported_action_success_probability`` and a ``TransitionCandidate`` label,
  *not* a transition posterior.  A slip is a NEGATIVE candidate.

This entry point projects/routes only; it does not write a presence log, map, or
ORRER outbox (that lands after the map/ORRER core is handed over).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from math import isfinite
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
    TargetPresenceBeliefRef,
)
from cpswm.contracts.base import ContractModel

PROJECTOR_VERSION = "execution-feedback-projector@0.2"
_FEEDBACK_SCHEMA = "cpswm.ExecutionFeedbackRecord"
_BINDING_SCHEMA = "cpswm.DecisionContextBinding"

_TARGET_PRESENCE_ACTIONS = frozenset(
    {RobotActionType.SEARCH, RobotActionType.NAVIGATE, RobotActionType.GRASP}
)
_LOCATION_TRANSITION_ACTIONS = frozenset({RobotActionType.PLACE, RobotActionType.TRANSFER})


class FeedbackRoute(StrEnum):
    TARGET_PRESENCE = "target_presence"
    LOCATION_TRANSITION = "location_transition"


class TransitionCandidate(StrEnum):
    POSITIVE_CANDIDATE = "positive_candidate"
    NEGATIVE_CANDIDATE = "negative_candidate"
    UNRESOLVED = "unresolved"


class ProjectionInputConflictError(ValueError):
    """Same feedback record replayed with different projection inputs."""


@dataclass(frozen=True, slots=True)
class LocationTransitionEvidence:
    """A place/transfer outcome as a *candidate* transition (not a posterior).

    Named honestly: it reports the action's own success/slip probabilities, not a
    P(transition | outcome).  A slip is a NEGATIVE candidate and can never feed a
    habit.  A true transition posterior needs a location-transition likelihood
    model (#4 tail).
    """

    feedback_record_id: UUID
    location_id: UUID
    reported_action_success_probability: float
    reported_slip_probability: float
    candidate: TransitionCandidate
    # Direction comes from the candidate; magnitude comes from the calibrated
    # outcome model.  This is the factor downstream ORRER must consume.
    candidate_likelihood_ratio: float = 1.0
    likelihood_model_version: str = "legacy-unversioned"

    def __post_init__(self) -> None:
        for name in (
            "reported_action_success_probability",
            "reported_slip_probability",
        ):
            value = getattr(self, name)
            if not isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must lie in [0, 1]")
        if not isfinite(self.candidate_likelihood_ratio) or self.candidate_likelihood_ratio <= 0.0:
            raise ValueError("candidate_likelihood_ratio must be finite and positive")
        if not self.likelihood_model_version.strip():
            raise ValueError("location transition evidence requires a model version")


@dataclass(frozen=True, slots=True)
class ProjectedFeedbackEvidence:
    """The routed, likelihood-aware result of one execution feedback record."""

    feedback_record_id: UUID
    feedback_content_hash: str
    projection_input_hash: str
    route: FeedbackRoute
    target_presence_update: FeedbackBeliefUpdate | None
    location_transition: LocationTransitionEvidence | None
    requires_actor_responsibility: bool
    updates_owner_habit_directly: bool
    is_replay: bool
    rationale: str


def _canonical_hash(model: ContractModel) -> str:
    return hashlib.sha256(
        json.dumps(model.model_dump(mode="json"), sort_keys=True).encode("utf-8")
    ).hexdigest()


class ExecutionFeedbackProjector:
    """Project execution feedback into typed, de-duplicated belief evidence."""

    def __init__(self) -> None:
        # record_id -> (feedback_content_hash, projection_input_hash, result)
        self._seen: dict[UUID, tuple[str, str, ProjectedFeedbackEvidence]] = {}

    def project_execution_feedback(
        self,
        *,
        feedback: ExecutionFeedbackRecord,
        binding: DecisionContextBinding,
        likelihood_model: ActionOutcomeLikelihoodModel,
    ) -> ProjectedFeedbackEvidence:
        """Compatibility one-shot API: prepare and immediately commit replay state."""

        projected = self.prepare_execution_feedback(
            feedback=feedback,
            binding=binding,
            likelihood_model=likelihood_model,
        )
        self.commit_execution_feedback(projected)
        return projected

    def prepare_execution_feedback(
        self,
        *,
        feedback: ExecutionFeedbackRecord,
        binding: DecisionContextBinding,
        likelihood_model: ActionOutcomeLikelihoodModel,
    ) -> ProjectedFeedbackEvidence:
        """Validate and project without consuming the idempotency key."""

        # Re-validate all three contracts at the trust boundary (schema).
        feedback = ExecutionFeedbackRecord.model_validate(feedback.model_dump())
        binding = DecisionContextBinding.model_validate(binding.model_dump())
        likelihood_model = ActionOutcomeLikelihoodModel.model_validate(
            likelihood_model.model_dump()
        )

        self._check_schema_and_binding(feedback, binding)
        if likelihood_model.action_type != feedback.action_type:
            raise ValueError("likelihood model action type must match the feedback")
        if set(feedback.outcome_distribution) - set(
            likelihood_model.p_outcome_given_target_present
        ):
            raise ValueError("likelihood model must cover every observed outcome")

        context = binding.decision_context
        belief = self._resolve_prior(feedback, binding)

        record_id = feedback.metadata.record_id
        feedback_hash = _canonical_hash(feedback)
        projection_input_hash = hashlib.sha256(
            json.dumps(
                {
                    "feedback_content_hash": feedback_hash,
                    "context_hash": context.context_hash,
                    "likelihood_hash": _canonical_hash(likelihood_model),
                    "projector_version": PROJECTOR_VERSION,
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()

        cached = self._seen.get(record_id)
        if cached is not None:
            cached_feedback_hash, cached_input_hash, result = cached
            if cached_feedback_hash != feedback_hash:
                raise ValueError(
                    "feedback record id reused with different content (collision/forgery)"
                )
            if cached_input_hash != projection_input_hash:
                raise ProjectionInputConflictError(
                    "feedback replayed with different projection inputs "
                    "(context/likelihood/version)"
                )
            return _as_replay(result)

        if feedback.action_type in _LOCATION_TRANSITION_ACTIONS:
            projected = self._location_transition(
                feedback,
                likelihood_model,
                feedback_hash,
                projection_input_hash,
            )
        else:
            projected = ProjectedFeedbackEvidence(
                feedback_record_id=record_id,
                feedback_content_hash=feedback_hash,
                projection_input_hash=projection_input_hash,
                route=FeedbackRoute.TARGET_PRESENCE,
                target_presence_update=self._target_presence_update(
                    feedback, likelihood_model, belief.prior_probability
                ),
                location_transition=None,
                requires_actor_responsibility=False,
                updates_owner_habit_directly=False,
                is_replay=False,
                rationale="find/observe outcome updates target presence only; not owner habit",
            )
        return projected

    def commit_execution_feedback(self, projected: ProjectedFeedbackEvidence) -> None:
        """Consume a prepared projection only after downstream statistics commit."""

        if projected.is_replay:
            return
        record_id = projected.feedback_record_id
        cached = self._seen.get(record_id)
        if cached is not None:
            cached_feedback_hash, cached_input_hash, _result = cached
            if cached_feedback_hash != projected.feedback_content_hash:
                raise ValueError(
                    "feedback record id reused with different content (collision/forgery)"
                )
            if cached_input_hash != projected.projection_input_hash:
                raise ProjectionInputConflictError(
                    "feedback projection inputs changed before commit"
                )
            return
        self._seen[record_id] = (
            projected.feedback_content_hash,
            projected.projection_input_hash,
            projected,
        )

    def _check_schema_and_binding(
        self, feedback: ExecutionFeedbackRecord, binding: DecisionContextBinding
    ) -> None:
        if feedback.metadata.schema_name != _FEEDBACK_SCHEMA:
            raise ValueError(f"feedback schema_name must be {_FEEDBACK_SCHEMA}")
        if binding.metadata.schema_name != _BINDING_SCHEMA:
            raise ValueError(f"binding schema_name must be {_BINDING_SCHEMA}")
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
        # Whole feedback interval must lie within the decision validity window.
        ctx_time = context.valid_time
        fb_time = feedback.valid_time
        start_ok = fb_time.start >= ctx_time.start
        end_ok = ctx_time.end is None or (fb_time.end is not None and fb_time.end <= ctx_time.end)
        if not (start_ok and end_ok):
            raise ValueError("feedback interval must lie within the decision context valid time")

    def _resolve_prior(
        self, feedback: ExecutionFeedbackRecord, binding: DecisionContextBinding
    ) -> TargetPresenceBeliefRef:
        context = binding.decision_context
        belief = context.target_presence_belief
        if belief is None:
            raise ValueError("bound decision context must carry a target_presence_belief")
        # P0-1: the prior must belong to *this* object/location/snapshot.
        assert feedback.target_entity is not None
        if belief.object_instance_id != feedback.target_entity.entity_id:
            raise ValueError("target-presence belief object does not match the feedback target")
        if belief.location_id != feedback.attempted_location_id:
            raise ValueError("target-presence belief location does not match the feedback location")
        if belief.belief_snapshot_id != context.revisions.belief_snapshot_id:
            raise ValueError("target-presence belief snapshot does not match the decision snapshot")
        return belief

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
        self,
        feedback: ExecutionFeedbackRecord,
        likelihood_model: ActionOutcomeLikelihoodModel,
        feedback_hash: str,
        projection_input_hash: str,
    ) -> ProjectedFeedbackEvidence:
        if feedback.attempted_location_id is None:
            raise ValueError("place/transfer feedback must record an attempted location")
        success = feedback.outcome_distribution.get(RobotActionOutcome.SUCCESS, 0.0)
        slipped = feedback.outcome_distribution.get(RobotActionOutcome.OBJECT_SLIPPED, 0.0)
        if slipped >= success:
            candidate = TransitionCandidate.NEGATIVE_CANDIDATE
        elif success > 0.5:
            candidate = TransitionCandidate.POSITIVE_CANDIDATE
        else:
            candidate = TransitionCandidate.UNRESOLVED
        present_ll = sum(
            probability * likelihood_model.p_outcome_given_target_present[outcome]
            for outcome, probability in feedback.outcome_distribution.items()
        )
        absent_ll = sum(
            probability * likelihood_model.p_outcome_given_target_absent[outcome]
            for outcome, probability in feedback.outcome_distribution.items()
        )
        raw_ratio = present_ll / absent_ll if absent_ll > 0.0 else 1.0 / 1e-6
        strength = max(raw_ratio, 1.0 / max(raw_ratio, 1e-6))
        candidate_ratio = (
            strength
            if candidate is TransitionCandidate.POSITIVE_CANDIDATE
            else 1.0 / strength
            if candidate is TransitionCandidate.NEGATIVE_CANDIDATE
            else 1.0
        )
        transition = LocationTransitionEvidence(
            feedback_record_id=feedback.metadata.record_id,
            location_id=feedback.attempted_location_id,
            reported_action_success_probability=success,
            reported_slip_probability=slipped,
            candidate=candidate,
            candidate_likelihood_ratio=candidate_ratio,
            likelihood_model_version=likelihood_model.model_version,
        )
        return ProjectedFeedbackEvidence(
            feedback_record_id=feedback.metadata.record_id,
            feedback_content_hash=feedback_hash,
            projection_input_hash=projection_input_hash,
            route=FeedbackRoute.LOCATION_TRANSITION,
            target_presence_update=None,
            location_transition=transition,
            requires_actor_responsibility=True,
            updates_owner_habit_directly=False,
            is_replay=False,
            rationale="place/transfer: reported-success candidate; owner-habit attribution "
            "requires actor responsibility; a slip is a negative candidate",
        )


def _as_replay(evidence: ProjectedFeedbackEvidence) -> ProjectedFeedbackEvidence:
    return ProjectedFeedbackEvidence(
        feedback_record_id=evidence.feedback_record_id,
        feedback_content_hash=evidence.feedback_content_hash,
        projection_input_hash=evidence.projection_input_hash,
        route=evidence.route,
        target_presence_update=evidence.target_presence_update,
        location_transition=evidence.location_transition,
        requires_actor_responsibility=evidence.requires_actor_responsibility,
        updates_owner_habit_directly=evidence.updates_owner_habit_directly,
        is_replay=True,
        rationale="replayed feedback record with identical projection inputs; no-op",
    )
