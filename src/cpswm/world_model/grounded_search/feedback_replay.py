"""Deterministic replay of canonical M27 feedback into target-presence memory.

The online direction-three loop appends observations and action feedback to M03.
This module is the restart boundary: it rebuilds the derived target/location
belief from the canonical log and the exact persisted outcome-model binding.
It never treats a failure as a fact and never silently substitutes a new model.
"""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from pydantic import Field, model_validator

from cpswm.contracts import (
    ActionOutcomeLikelihoodModel,
    ContractModel,
    ExecutionFeedbackRecord,
    InputWatermark,
    ObservationOpportunityRecord,
    RobotActionType,
)
from cpswm.contracts.base import Probability
from cpswm.foundation.persistence_replay import AppendOnlyTransactionLog

from .adapters import ActionOutcomeModelProvider
from .execution_feedback import ExecutionFeedbackProjector


class TargetPresencePrior(ContractModel):
    """Snapshot-bound replay starting point for one object/location proposition."""

    household_id: UUID
    target_entity_id: UUID
    location_id: UUID
    probability: Probability


class TargetPresenceReplayStep(ContractModel):
    global_commit_seq: int = Field(gt=0)
    feedback_record_id: UUID
    household_id: UUID
    target_entity_id: UUID
    location_id: UUID
    prior_probability: Probability
    posterior_probability: Probability
    likelihood_ratio: float | None = Field(default=None, ge=0.0)
    outcome_model_version: str = Field(min_length=1)
    outcome_calibration_domain: str = Field(min_length=1)


class TargetPresenceReplayProjection(ContractModel):
    household_id: UUID
    target_entity_id: UUID
    location_id: UUID
    initial_probability: Probability
    current_probability: Probability
    applied_feedback_record_ids: tuple[UUID, ...]


class DirectionThreeFeedbackReplayReport(ContractModel):
    """A fully bound derived projection; safe to compare across restarts."""

    input_watermark: InputWatermark
    input_log_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    projections: tuple[TargetPresenceReplayProjection, ...]
    steps: tuple[TargetPresenceReplayStep, ...]
    ignored_non_search_feedback_ids: tuple[UUID, ...] = ()

    @model_validator(mode="after")
    def _step_bindings(self) -> DirectionThreeFeedbackReplayReport:
        seen: set[UUID] = set()
        last_seq = 0
        for step in self.steps:
            if step.feedback_record_id in seen:
                raise ValueError("feedback replay steps must be idempotent by record ID")
            if step.global_commit_seq < last_seq:
                raise ValueError("feedback replay steps must follow canonical commit order")
            seen.add(step.feedback_record_id)
            last_seq = step.global_commit_seq
        return self


class DirectionThreeFeedbackReplaySpec(ContractModel):
    initial_priors: tuple[TargetPresencePrior, ...]
    outcome_models: tuple[ActionOutcomeLikelihoodModel, ...]
    through_commit_seq: int | None = Field(default=None, ge=0)
    household_id: UUID | None = None


class BoundActionOutcomeModelRegistry:
    """Resolve the exact model persisted on each canonical feedback record."""

    def __init__(self, models: Iterable[ActionOutcomeLikelihoodModel]) -> None:
        self._models: dict[tuple[object, str, str], ActionOutcomeLikelihoodModel] = {}
        for model in models:
            model = ActionOutcomeLikelihoodModel.model_validate(model.model_dump(mode="python"))
            key = (model.action_type, model.model_version, model.calibration_domain)
            if key in self._models:
                raise ValueError("bound action-outcome model registry keys must be unique")
            self._models[key] = model

    def model_for(self, feedback: ExecutionFeedbackRecord) -> ActionOutcomeLikelihoodModel:
        if (
            feedback.action_outcome_model_version is None
            or feedback.action_outcome_calibration_domain is None
        ):
            raise LookupError("canonical feedback has no persisted outcome-model binding")
        key = (
            feedback.action_type,
            feedback.action_outcome_model_version,
            feedback.action_outcome_calibration_domain,
        )
        try:
            return self._models[key]
        except KeyError as exc:
            raise LookupError(
                "no action-outcome model matches the canonical feedback binding"
            ) from exc


class CanonicalExecutionFeedbackReplayer:
    """Rebuild target-presence projections from an M03 canonical transaction log."""

    def __init__(self, *, projector: ExecutionFeedbackProjector | None = None) -> None:
        self._projector = projector or ExecutionFeedbackProjector()

    def replay(
        self,
        canonical_log: AppendOnlyTransactionLog,
        *,
        initial_priors: Iterable[TargetPresencePrior],
        outcome_model_provider: ActionOutcomeModelProvider,
        through_commit_seq: int | None = None,
        household_id: UUID | None = None,
    ) -> DirectionThreeFeedbackReplayReport:
        watermark = (
            canonical_log.latest_watermark()
            if through_commit_seq is None
            else canonical_log.watermark_at(through_commit_seq)
        )
        transactions = canonical_log.read(
            through_commit_seq=watermark.global_commit_seq,
            household_id=household_id,
        )
        priors = tuple(initial_priors)
        state: dict[tuple[UUID, UUID, UUID], float] = {}
        initial: dict[tuple[UUID, UUID, UUID], float] = {}
        applied: dict[tuple[UUID, UUID, UUID], list[UUID]] = {}
        for prior in priors:
            key = (prior.household_id, prior.target_entity_id, prior.location_id)
            if key in state:
                raise ValueError("initial target-presence priors must be unique")
            if household_id is not None and prior.household_id != household_id:
                raise ValueError("initial prior is outside the requested household")
            state[key] = prior.probability
            initial[key] = prior.probability
            applied[key] = []

        opportunities: dict[UUID, ObservationOpportunityRecord] = {}
        steps: list[TargetPresenceReplayStep] = []
        ignored: list[UUID] = []
        seen_feedback: set[UUID] = set()
        for transaction in transactions:
            for committed in transaction.records:
                envelope = committed.envelope
                if envelope.schema_name == "cpswm.ObservationOpportunityRecord":
                    opportunity = ObservationOpportunityRecord.model_validate(envelope.payload)
                    opportunities[opportunity.metadata.record_id] = opportunity
                    continue
                if envelope.schema_name != "cpswm.ExecutionFeedbackRecord":
                    continue
                feedback = ExecutionFeedbackRecord.model_validate(envelope.payload)
                if feedback.metadata.record_id in seen_feedback:
                    raise ValueError("canonical log contains duplicate execution feedback")
                seen_feedback.add(feedback.metadata.record_id)
                if feedback.action_type is not RobotActionType.SEARCH:
                    ignored.append(feedback.metadata.record_id)
                    continue
                if feedback.target_entity is None or feedback.attempted_location_id is None:
                    raise ValueError("search replay requires a bound target and location")
                if (
                    feedback.action_outcome_model_version is None
                    or feedback.action_outcome_calibration_domain is None
                ):
                    raise ValueError(
                        "canonical search feedback is missing its outcome-model binding"
                    )
                opportunity_id = feedback.observation_opportunity_id
                if opportunity_id is None:
                    raise ValueError("search replay is missing its observation opportunity ID")
                bound_opportunity = opportunities.get(opportunity_id)
                if bound_opportunity is None:
                    raise ValueError(
                        "canonical search feedback references an unavailable "
                        "observation opportunity"
                    )
                self._validate_opportunity_binding(feedback, bound_opportunity)

                key = (
                    feedback.metadata.household_id,
                    feedback.target_entity.entity_id,
                    feedback.attempted_location_id,
                )
                if key not in state:
                    raise ValueError(
                        "canonical feedback has no snapshot-bound initial target-presence prior"
                    )
                model = outcome_model_provider.model_for(feedback)
                if model.model_version != feedback.action_outcome_model_version:
                    raise ValueError("replay outcome model version differs from canonical feedback")
                if model.calibration_domain != feedback.action_outcome_calibration_domain:
                    raise ValueError("replay calibration domain differs from canonical feedback")
                update = self._projector.update_target_presence(state[key], feedback, model)
                steps.append(
                    TargetPresenceReplayStep(
                        global_commit_seq=transaction.global_commit_seq,
                        feedback_record_id=feedback.metadata.record_id,
                        household_id=key[0],
                        target_entity_id=key[1],
                        location_id=key[2],
                        prior_probability=state[key],
                        posterior_probability=update.posterior_target_present,
                        likelihood_ratio=update.likelihood_ratio,
                        outcome_model_version=model.model_version,
                        outcome_calibration_domain=model.calibration_domain,
                    )
                )
                state[key] = update.posterior_target_present
                applied[key].append(feedback.metadata.record_id)

        projections = tuple(
            TargetPresenceReplayProjection(
                household_id=key[0],
                target_entity_id=key[1],
                location_id=key[2],
                initial_probability=initial[key],
                current_probability=state[key],
                applied_feedback_record_ids=tuple(applied[key]),
            )
            for key in sorted(state, key=lambda item: tuple(map(str, item)))
        )
        return DirectionThreeFeedbackReplayReport(
            input_watermark=watermark,
            input_log_sha256=canonical_log.fingerprint(
                through_commit_seq=watermark.global_commit_seq
            ),
            projections=projections,
            steps=tuple(steps),
            ignored_non_search_feedback_ids=tuple(ignored),
        )

    @staticmethod
    def _validate_opportunity_binding(
        feedback: ExecutionFeedbackRecord,
        opportunity: ObservationOpportunityRecord,
    ) -> None:
        if opportunity.observation_action_id != feedback.action_id:
            raise ValueError("replayed observation opportunity binds a different action")
        if not opportunity.selected:
            raise ValueError("replayed search opportunity was not actually selected")
        if opportunity.likelihood_model_id != feedback.action_outcome_model_version:
            raise ValueError("observation opportunity model differs from canonical feedback")
        for name in ("household_id", "session_id", "trace_id"):
            if getattr(opportunity.metadata, name) != getattr(feedback.metadata, name):
                raise ValueError(f"replayed observation opportunity {name} differs from feedback")
        if opportunity.opportunity_time > feedback.metadata.recorded_time:
            raise ValueError("execution feedback cannot precede its observation opportunity")
