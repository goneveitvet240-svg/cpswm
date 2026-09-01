"""Runnable direction-structure-three decision vertical slice."""

from __future__ import annotations

from dataclasses import dataclass
from math import isclose, nextafter
from uuid import UUID

from pydantic import BaseModel, ValidationError

from cpswm.contracts import ObservationOpportunityRecord
from cpswm.contracts.grounded_search import (
    ActionOutcomeLikelihoodModel,
    ActiveObservationPlan,
    CandidateKind,
    ChannelEvidence,
    ExecutionFeedbackRecord,
    GroundedObjectCandidate,
    GroundedSearchResult,
    JointCandidateEvidence,
    JointPosteriorRequest,
    ObservationActionCandidate,
    ResponsePolicy,
    RobotActionType,
    VerificationObservation,
)
from cpswm.foundation.persistence_replay import AppendOnlyTransactionLog

from .active_verification import ActionUtilityPlanner, InformationGainPlanner
from .adapters import (
    GROUNDED_SEARCH_SCHEMA_VERSION,
    ActionOutcomeModelProvider,
    GroundedTaskExecution,
    GroundedTaskExecutor,
    ObservationActionProvider,
    VerificationObservationProvider,
)
from .execution_feedback import ExecutionFeedbackProjector
from .joint_posterior import JointPosteriorFusion


@dataclass(frozen=True, slots=True)
class GroundedSearchCycle:
    search_result: GroundedSearchResult
    observation_plan: ActiveObservationPlan | None


@dataclass(frozen=True, slots=True)
class GroundedSearchClosedLoop:
    """Auditable S3-1 trace across belief, observation, action, and writeback."""

    cycles: tuple[GroundedSearchCycle, ...]
    verification_observations: tuple[VerificationObservation, ...]
    execution_feedback: tuple[ExecutionFeedbackRecord, ...]
    observation_commit_sequences: tuple[int, ...]
    feedback_commit_sequences: tuple[int, ...]
    selected_target_candidate_id: UUID | None
    termination_reason: str


class DirectionThreePipeline:
    """Fuse evidence and plan verification only when the result requires it."""

    def __init__(
        self,
        *,
        fusion: JointPosteriorFusion | None = None,
        planner: InformationGainPlanner | ActionUtilityPlanner | None = None,
        feedback_projector: ExecutionFeedbackProjector | None = None,
    ) -> None:
        self.fusion = fusion or JointPosteriorFusion()
        self.planner = planner or ActionUtilityPlanner()
        self.feedback_projector = feedback_projector or ExecutionFeedbackProjector()

    def decide(
        self,
        request: JointPosteriorRequest,
        observation_actions: tuple[ObservationActionCandidate, ...] = (),
        *,
        terminal_decision_utilities: dict[UUID, dict[UUID, float]] | None = None,
    ) -> GroundedSearchCycle:
        request = self._validate_request(request)
        result = self._fuse_validated(request)
        if result.response_policy != ResponsePolicy.ACTIVE_VERIFY:
            return GroundedSearchCycle(search_result=result, observation_plan=None)
        observation_actions = self._validate_observation_actions(result, observation_actions)
        plan = self._plan_verification(
            result.posterior_by_candidate_id,
            observation_actions,
            terminal_decision_utilities=terminal_decision_utilities,
        )
        return GroundedSearchCycle(search_result=result, observation_plan=plan)

    def run_closed_loop(
        self,
        request: JointPosteriorRequest,
        *,
        action_provider: ObservationActionProvider,
        observation_provider: VerificationObservationProvider,
        task_executor: GroundedTaskExecutor,
        outcome_model_provider: ActionOutcomeModelProvider,
        canonical_log: AppendOnlyTransactionLog,
        max_cycles: int = 8,
        success_threshold: float = 0.95,
        terminal_decision_utilities: dict[UUID, dict[UUID, float]] | None = None,
    ) -> GroundedSearchClosedLoop:
        """Run the M29-L0 oracle loop through canonical M27 feedback writeback."""

        if max_cycles <= 0:
            raise ValueError("max_cycles must be positive")
        if not 0.0 < success_threshold <= 1.0:
            raise ValueError("success_threshold must be in (0, 1]")

        current_request = self._validate_request(request)
        cycles: list[GroundedSearchCycle] = []
        observations: list[VerificationObservation] = []
        feedback_records: list[ExecutionFeedbackRecord] = []
        observation_commit_sequences: list[int] = []
        commit_sequences: list[int] = []
        used_action_ids: set[UUID] = set()
        executed_action_ids: set[UUID] = set()
        last_target_id: UUID | None = None
        precomputed_result: GroundedSearchResult | None = None

        for _ in range(max_cycles):
            result = precomputed_result or self._fuse_validated(current_request)
            precomputed_result = None
            if result.response_policy == ResponsePolicy.ACTIVE_VERIFY:
                proposed_actions = tuple(action_provider.propose(result))
                proposed_actions = self._validate_observation_actions(result, proposed_actions)
                actions = tuple(
                    action for action in proposed_actions if action.action_id not in used_action_ids
                )
                plan = self._plan_verification(
                    result.posterior_by_candidate_id,
                    actions,
                    terminal_decision_utilities=terminal_decision_utilities,
                )
                cycles.append(GroundedSearchCycle(result, plan))
                if not plan.should_act or plan.selected_action_id is None:
                    return GroundedSearchClosedLoop(
                        tuple(cycles),
                        tuple(observations),
                        tuple(feedback_records),
                        tuple(observation_commit_sequences),
                        tuple(commit_sequences),
                        last_target_id,
                        plan.stop_reason,
                    )
                action = next(item for item in actions if item.action_id == plan.selected_action_id)
                observation = observation_provider.observe(action, result)
                observation = self._validate_verification_observation(
                    current_request, result, action, observation
                )
                next_request = self._request_after_observation(current_request, result, observation)
                # Validate the posterior transition before making canonical
                # evidence visible. A failing update leaves the log untouched.
                next_result = self._fuse_validated(next_request)
                observation_commit = canonical_log.append(
                    [observation],
                    idempotency_key=(
                        f"direction-three-observation:{observation.metadata.record_id}"
                    ),
                )
                observations.append(observation)
                observation_commit_sequences.append(observation_commit.watermark.global_commit_seq)
                used_action_ids.add(action.action_id)
                mark_consumed = getattr(action_provider, "mark_consumed", None)
                if mark_consumed is not None:
                    mark_consumed(action.action_id)
                current_request = next_request
                precomputed_result = next_result
                continue

            cycles.append(GroundedSearchCycle(result, None))
            if result.response_policy == ResponsePolicy.ASK_USER:
                return GroundedSearchClosedLoop(
                    tuple(cycles),
                    tuple(observations),
                    tuple(feedback_records),
                    tuple(observation_commit_sequences),
                    tuple(commit_sequences),
                    None,
                    "clarification_required",
                )
            if result.response_policy == ResponsePolicy.ABSTAIN:
                return GroundedSearchClosedLoop(
                    tuple(cycles),
                    tuple(observations),
                    tuple(feedback_records),
                    tuple(observation_commit_sequences),
                    tuple(commit_sequences),
                    None,
                    "abstained_with_unknown_target",
                )

            target = next(
                candidate
                for candidate in result.candidates
                if candidate.kind == CandidateKind.OBJECT_INSTANCE
            )
            last_target_id = target.candidate_id
            execution = self._validate_task_execution(
                current_request, target, task_executor.execute(target)
            )
            if execution.executed_action_id in executed_action_ids:
                raise ValueError("executed action ID cannot be reused in one closed loop")
            produced_feedback = execution.feedback_records

            replanned = False
            next_request = current_request
            working_result = result
            for feedback in produced_feedback:
                if feedback.action_type != RobotActionType.SEARCH:
                    continue
                model = outcome_model_provider.model_for(feedback)
                model = self._validate_outcome_model(execution, feedback, model)
                update = self.feedback_projector.update_target_presence(
                    working_result.posterior_by_candidate_id[target.candidate_id],
                    feedback,
                    model,
                )
                next_request = self._request_after_presence_update(
                    next_request,
                    working_result,
                    target.candidate_id,
                    update.posterior_target_present,
                )
                # Finish every model check and posterior computation before
                # atomically appending the execution evidence batch.
                working_result = self._fuse_validated(next_request)
                replanned = True

            execution_records = (
                *execution.observation_opportunities,
                *produced_feedback,
            )
            commit = canonical_log.append(
                execution_records,
                idempotency_key=(f"direction-three-execution:{execution.executed_action_id}"),
            )
            executed_action_ids.add(execution.executed_action_id)
            feedback_records.extend(produced_feedback)
            commit_sequences.extend(commit.watermark.global_commit_seq for _ in produced_feedback)
            if any(
                feedback.task_goal_satisfied_probability >= success_threshold
                for feedback in produced_feedback
            ):
                return GroundedSearchClosedLoop(
                    tuple(cycles),
                    tuple(observations),
                    tuple(feedback_records),
                    tuple(observation_commit_sequences),
                    tuple(commit_sequences),
                    last_target_id,
                    "task_success_feedback_committed",
                )
            if replanned:
                current_request = next_request
                precomputed_result = working_result
                continue
            return GroundedSearchClosedLoop(
                tuple(cycles),
                tuple(observations),
                tuple(feedback_records),
                tuple(observation_commit_sequences),
                tuple(commit_sequences),
                last_target_id,
                "task_incomplete_feedback_committed",
            )

        return GroundedSearchClosedLoop(
            tuple(cycles),
            tuple(observations),
            tuple(feedback_records),
            tuple(observation_commit_sequences),
            tuple(commit_sequences),
            last_target_id,
            "maximum_closed_loop_cycles_reached",
        )

    def _plan_verification(
        self,
        prior: dict[UUID, float],
        actions: tuple[ObservationActionCandidate, ...],
        *,
        terminal_decision_utilities: dict[UUID, dict[UUID, float]] | None,
    ) -> ActiveObservationPlan:
        if isinstance(self.planner, ActionUtilityPlanner):
            utilities = terminal_decision_utilities or {
                decision_id: {
                    hypothesis_id: 1.0 if decision_id == hypothesis_id else 0.0
                    for hypothesis_id in prior
                }
                for decision_id in prior
            }
            return self.planner.select(
                prior,
                actions,
                terminal_decision_utilities=utilities,
            )
        return self.planner.select(prior, actions)

    @staticmethod
    def _validate_contract_metadata(
        record: object,
        *,
        expected_schema_name: str,
        record_kind: str,
    ) -> None:
        metadata = getattr(record, "metadata", None)
        if metadata is None:
            raise ValueError(f"{record_kind} requires record metadata")
        if metadata.schema_name != expected_schema_name:
            raise ValueError(f"{record_kind} schema name must be {expected_schema_name}")
        if metadata.schema_version != GROUNDED_SEARCH_SCHEMA_VERSION:
            raise ValueError(
                f"{record_kind} schema version must be {GROUNDED_SEARCH_SCHEMA_VERSION}"
            )

    def _fuse_validated(
        self,
        request: JointPosteriorRequest,
    ) -> GroundedSearchResult:
        """Run a replaceable fusion provider and bind its grounded output."""

        result = self.fusion.fuse(request)
        return self._validate_fusion_result(request, result)

    @classmethod
    def _validate_fusion_result(
        cls,
        request: JointPosteriorRequest,
        result: GroundedSearchResult,
    ) -> GroundedSearchResult:
        cls._reject_model_copy_extras(result, "grounded fusion result")
        try:
            result = GroundedSearchResult.model_validate(result.model_dump(mode="python"))
        except (AttributeError, ValidationError) as exc:
            raise ValueError(f"invalid grounded fusion result: {exc}") from exc
        cls._validate_contract_metadata(
            result,
            expected_schema_name="cpswm.GroundedSearchResult",
            record_kind="grounded fusion result",
        )
        cls._validate_record_scope(
            request,
            result,
            record_kind="grounded fusion result",
        )
        if result.query_id != request.compiled_query.query_id:
            raise ValueError("fusion result query ID must match the request")
        if result.fusion_model_version != request.fusion_model_version:
            raise ValueError("fusion result model version must match the request")

        request_by_id = {candidate.candidate_id: candidate for candidate in request.candidates}
        if set(result.posterior_by_candidate_id) != set(request_by_id):
            raise ValueError("fusion result posterior must cover the request candidates")
        if set(result.hard_constraint_evaluations_by_candidate_id) != set(request_by_id):
            raise ValueError("fusion result hard constraints must cover the request candidates")
        for candidate_id, evaluations in result.hard_constraint_evaluations_by_candidate_id.items():
            if evaluations != request_by_id[candidate_id].hard_constraint_evaluations:
                raise ValueError("fusion result hard constraints must match request evidence")

        returned_ids = [candidate.candidate_id for candidate in result.candidates]
        if len(returned_ids) != len(set(returned_ids)):
            raise ValueError("fusion result candidate IDs must be unique")
        for candidate in result.candidates:
            source = request_by_id.get(candidate.candidate_id)
            if source is None:
                raise ValueError("fusion result introduced a candidate outside the request")
            if (
                candidate.kind != source.kind
                or candidate.entity != source.entity
                or candidate.location_id != source.location_id
            ):
                raise ValueError("fusion result candidate grounding must match the request")
            contribution_channels = [
                contribution.channel for contribution in candidate.contributions
            ]
            if len(contribution_channels) != len(set(contribution_channels)) or set(
                contribution_channels
            ) != set(source.channel_evidence):
                raise ValueError("fusion result contributions must cover each request channel once")

        unknown_id = next(
            candidate.candidate_id
            for candidate in request.candidates
            if candidate.kind == CandidateKind.UNKNOWN
        )
        if not isclose(
            result.unknown_probability,
            result.posterior_by_candidate_id[unknown_id],
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("fusion result unknown probability is not bound")
        return result

    @classmethod
    def _validate_request(cls, request: JointPosteriorRequest) -> JointPosteriorRequest:
        cls._reject_model_copy_extras(request, "joint posterior request")
        try:
            request = JointPosteriorRequest.model_validate(request.model_dump(mode="python"))
        except (AttributeError, ValidationError) as exc:
            raise ValueError(f"invalid joint posterior request: {exc}") from exc
        cls._validate_contract_metadata(
            request,
            expected_schema_name="cpswm.JointPosteriorRequest",
            record_kind="joint posterior request",
        )
        return request

    @staticmethod
    def _validate_record_scope(
        request: JointPosteriorRequest,
        record: (
            VerificationObservation
            | ExecutionFeedbackRecord
            | GroundedSearchResult
            | ObservationOpportunityRecord
        ),
        *,
        record_kind: str,
    ) -> None:
        expected = request.metadata
        actual = record.metadata
        if actual.household_id != expected.household_id:
            raise ValueError(f"{record_kind} household must match the query")
        if actual.session_id != expected.session_id:
            raise ValueError(f"{record_kind} session must match the query")
        if actual.trace_id != expected.trace_id:
            raise ValueError(f"{record_kind} trace must match the query")

    @classmethod
    def _validate_verification_observation(
        cls,
        request: JointPosteriorRequest,
        result: GroundedSearchResult,
        action: ObservationActionCandidate,
        observation: VerificationObservation,
    ) -> VerificationObservation:
        cls._reject_model_copy_extras(observation, "verification observation")
        try:
            observation = VerificationObservation.model_validate(
                observation.model_dump(mode="python")
            )
        except (AttributeError, ValidationError) as exc:
            raise ValueError(f"invalid verification observation: {exc}") from exc
        cls._validate_record_scope(request, observation, record_kind="verification observation")
        cls._validate_contract_metadata(
            observation,
            expected_schema_name="cpswm.VerificationObservation",
            record_kind="verification observation",
        )
        if observation.action_id != action.action_id:
            raise ValueError("verification observation must bind the selected action")
        if observation.observation_likelihood_model_id != action.observation_likelihood_model_id:
            raise ValueError("planned and realized observation models must match")
        if observation.calibration_domain != action.calibration_domain:
            raise ValueError("planned and realized calibration domains must match")
        candidate_ids = set(result.posterior_by_candidate_id)
        if set(observation.candidate_likelihoods) != candidate_ids:
            raise ValueError("verification observation must cover every candidate")
        planned_likelihoods = action.outcome_likelihoods.get(observation.outcome_label)
        if planned_likelihoods is None:
            raise ValueError("realized outcome was absent from the planned observation model")
        if set(planned_likelihoods) != candidate_ids:
            raise ValueError("planned outcome must cover every current candidate")
        if any(
            not isclose(
                planned_likelihoods[candidate_id],
                observation.candidate_likelihoods[candidate_id],
                rel_tol=0.0,
                abs_tol=1e-12,
            )
            for candidate_id in candidate_ids
        ):
            raise ValueError("realized likelihoods differ from the planned observation model")
        return observation

    @staticmethod
    def _validate_observation_actions(
        result: GroundedSearchResult,
        actions: tuple[ObservationActionCandidate, ...],
    ) -> tuple[ObservationActionCandidate, ...]:
        validated: list[ObservationActionCandidate] = []
        for action in actions:
            DirectionThreePipeline._reject_model_copy_extras(action, "provider observation action")
            try:
                action = ObservationActionCandidate.model_validate(action.model_dump(mode="python"))
            except (AttributeError, ValidationError) as exc:
                raise ValueError(f"invalid provider observation action: {exc}") from exc
            for likelihoods in action.outcome_likelihoods.values():
                if set(likelihoods) != set(result.posterior_by_candidate_id):
                    raise ValueError(
                        "provider observation action must cover every current candidate"
                    )
            approval = action.safety_approval
            if approval is not None and (approval.calibration_domain != action.calibration_domain):
                raise ValueError(
                    "observation action safety calibration domain must match the action"
                )
            validated.append(action)
        action_ids = [item.action_id for item in validated]
        if len(action_ids) != len(set(action_ids)):
            raise ValueError("provider observation action IDs must be unique")
        return tuple(validated)

    @classmethod
    def _validate_task_execution(
        cls,
        request: JointPosteriorRequest,
        target: GroundedObjectCandidate,
        execution: GroundedTaskExecution,
    ) -> GroundedTaskExecution:
        cls._reject_model_copy_extras(execution, "grounded task execution")
        try:
            execution = GroundedTaskExecution.model_validate(execution.model_dump(mode="python"))
        except (AttributeError, ValidationError) as exc:
            raise ValueError(f"invalid grounded task execution: {exc}") from exc
        if execution.action_outcome_model_version is not None:
            bound_feedback = tuple(
                feedback.model_copy(
                    update={
                        "action_outcome_model_version": (
                            feedback.action_outcome_model_version
                            or execution.action_outcome_model_version
                        ),
                        "action_outcome_calibration_domain": (
                            feedback.action_outcome_calibration_domain
                            or execution.action_outcome_calibration_domain
                        ),
                    }
                )
                for feedback in execution.feedback_records
            )
            execution = GroundedTaskExecution.model_validate(
                execution.model_copy(update={"feedback_records": bound_feedback}).model_dump(
                    mode="python"
                )
            )
        if execution.selected_target_candidate_id != target.candidate_id:
            raise ValueError("execution must bind the selected target candidate")
        if target.entity is None or execution.target_entity != target.entity:
            raise ValueError("execution target must match the selected candidate entity")
        if target.location_id is None:
            raise ValueError("selected target requires a grounded location before execution")
        if execution.target_location_id != target.location_id:
            raise ValueError("execution location must match the selected candidate location")
        for opportunity in execution.observation_opportunities:
            cls._validate_record_scope(
                request,
                opportunity,
                record_kind="execution observation opportunity",
            )
            cls._validate_contract_metadata(
                opportunity,
                expected_schema_name="cpswm.ObservationOpportunityRecord",
                record_kind="execution observation opportunity",
            )
        for feedback in execution.feedback_records:
            cls._validate_record_scope(request, feedback, record_kind="execution feedback")
            cls._validate_contract_metadata(
                feedback,
                expected_schema_name="cpswm.ExecutionFeedbackRecord",
                record_kind="execution feedback",
            )
        return execution

    @staticmethod
    def _validate_outcome_model(
        execution: GroundedTaskExecution,
        feedback: ExecutionFeedbackRecord,
        model: ActionOutcomeLikelihoodModel,
    ) -> ActionOutcomeLikelihoodModel:
        DirectionThreePipeline._reject_model_copy_extras(model, "action outcome likelihood model")
        try:
            model = ActionOutcomeLikelihoodModel.model_validate(model.model_dump(mode="python"))
        except (AttributeError, ValidationError) as exc:
            raise ValueError(f"invalid action outcome likelihood model: {exc}") from exc
        if model.action_type != execution.executed_action_type:
            raise ValueError("outcome model must bind the executed action type")
        if model.action_type != feedback.action_type:
            raise ValueError("feedback and outcome model action types must match")
        if model.model_version != execution.action_outcome_model_version:
            raise ValueError("outcome model version must match the executed action")
        if model.calibration_domain != execution.action_outcome_calibration_domain:
            raise ValueError("outcome model calibration domain must match the executed action")
        if feedback.action_outcome_model_version != model.model_version:
            raise ValueError("canonical feedback must persist the outcome model version")
        if feedback.action_outcome_calibration_domain != model.calibration_domain:
            raise ValueError("canonical feedback must persist the outcome calibration domain")
        if not set(feedback.outcome_distribution).issubset(
            set(model.p_outcome_given_target_present)
        ):
            raise ValueError("outcome model must cover every realized feedback outcome")
        opportunity_by_id = {
            item.metadata.record_id: item for item in execution.observation_opportunities
        }
        opportunity_id = feedback.observation_opportunity_id
        if opportunity_id is None:
            raise ValueError("search feedback requires an observation opportunity ID")
        opportunity = opportunity_by_id.get(opportunity_id)
        if opportunity is None:
            raise ValueError("search outcome model requires the execution observation opportunity")
        return model

    @staticmethod
    def _reject_model_copy_extras(value: object, path: str) -> None:
        if isinstance(value, BaseModel):
            expected = set(type(value).model_fields)
            unexpected = set(vars(value)) - expected
            if unexpected:
                raise ValueError(
                    f"{path} contains fields outside its contract: {sorted(unexpected)}"
                )
            for field_name in expected:
                DirectionThreePipeline._reject_model_copy_extras(
                    getattr(value, field_name), f"{path}.{field_name}"
                )
        elif isinstance(value, dict):
            for key, nested in value.items():
                DirectionThreePipeline._reject_model_copy_extras(nested, f"{path}[{key!r}]")
        elif isinstance(value, (list, tuple)):
            for index, nested in enumerate(value):
                DirectionThreePipeline._reject_model_copy_extras(nested, f"{path}[{index}]")

    @staticmethod
    def _request_after_observation(
        request: JointPosteriorRequest,
        result: GroundedSearchResult,
        observation: VerificationObservation,
    ) -> JointPosteriorRequest:
        if set(observation.candidate_likelihoods) != set(result.posterior_by_candidate_id):
            raise ValueError("verification observation must cover every candidate")
        candidates: list[JointCandidateEvidence] = []
        for candidate in request.candidates:
            channel_evidence = {
                channel: evidence.model_copy(update={"availability": 0.0})
                for channel, evidence in candidate.channel_evidence.items()
            }
            channel_evidence[observation.evidence_channel] = ChannelEvidence(
                likelihood_given_candidate=observation.candidate_likelihoods[
                    candidate.candidate_id
                ],
                reliability=observation.reliability,
                availability=1.0,
                model_version=observation.observation_likelihood_model_id,
                calibration_domain=observation.calibration_domain,
                evidence_refs=observation.evidence_refs,
            )
            candidates.append(
                candidate.model_copy(
                    update={
                        "prior_probability": result.posterior_by_candidate_id[
                            candidate.candidate_id
                        ],
                        "channel_evidence": channel_evidence,
                    }
                )
            )
        return request.model_copy(update={"candidates": tuple(candidates)})

    @staticmethod
    def _request_after_presence_update(
        request: JointPosteriorRequest,
        result: GroundedSearchResult,
        target_candidate_id: UUID,
        posterior_target_present: float,
    ) -> JointPosteriorRequest:
        old_target_probability = result.posterior_by_candidate_id[target_candidate_id]
        posterior_target_present = min(
            max(posterior_target_present, nextafter(0.0, 1.0)),
            nextafter(1.0, 0.0),
        )
        remaining_old_mass = 1.0 - old_target_probability
        remaining_new_mass = 1.0 - posterior_target_present
        candidates: list[JointCandidateEvidence] = []
        for candidate in request.candidates:
            if candidate.candidate_id == target_candidate_id:
                probability = posterior_target_present
            elif remaining_old_mass <= 0.0:
                probability = remaining_new_mass / (len(request.candidates) - 1)
            else:
                probability = (
                    result.posterior_by_candidate_id[candidate.candidate_id]
                    / remaining_old_mass
                    * remaining_new_mass
                )
            channel_evidence = {
                channel: evidence.model_copy(update={"availability": 0.0})
                for channel, evidence in candidate.channel_evidence.items()
            }
            candidates.append(
                candidate.model_copy(
                    update={
                        "prior_probability": probability,
                        "channel_evidence": channel_evidence,
                    }
                )
            )
        return request.model_copy(update={"candidates": tuple(candidates)})
