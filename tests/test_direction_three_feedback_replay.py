from __future__ import annotations

from uuid import uuid4

import pytest

from cpswm.contracts import (
    ActionOutcomeLikelihoodModel,
    EntityType,
    ExecutionFeedbackRecord,
    ObservationOpportunityRecord,
    RobotActionOutcome,
    RobotActionType,
    SourceType,
)
from cpswm.foundation.persistence_replay import AppendOnlyTransactionLog
from cpswm.world_model.grounded_search import (
    CanonicalExecutionFeedbackReplayer,
    OracleActionOutcomeModelProvider,
    TargetPresencePrior,
)


def _model(*, version: str = "search-outcome@0.1") -> ActionOutcomeLikelihoodModel:
    return ActionOutcomeLikelihoodModel(
        action_type=RobotActionType.SEARCH,
        p_outcome_given_target_present={
            RobotActionOutcome.NOT_FOUND: 0.2,
            RobotActionOutcome.UNKNOWN: 0.8,
        },
        p_outcome_given_target_absent={
            RobotActionOutcome.NOT_FOUND: 0.8,
            RobotActionOutcome.UNKNOWN: 0.2,
        },
        calibration_domain="household-search-v1",
        model_version=version,
    )


def _canonical_log(metadata_factory, interval, entity_factory):
    action_id = uuid4()
    target = entity_factory(EntityType.OBJECT_INSTANCE)
    location_id = uuid4()
    model = _model()
    opportunity_metadata = metadata_factory(
        schema_name="cpswm.ObservationOpportunityRecord",
        source_type=SourceType.SENSOR,
    )
    opportunity = ObservationOpportunityRecord(
        metadata=opportunity_metadata,
        observation_action_id=action_id,
        opportunity_time=interval.start,
        selected=True,
        selection_probability=1.0,
        p_visible_given_state=0.9,
        p_detect_given_visible=0.9,
        likelihood_model_id=model.model_version,
    )
    feedback = ExecutionFeedbackRecord(
        metadata=opportunity_metadata.model_copy(
            update={
                "record_id": uuid4(),
                "schema_name": "cpswm.ExecutionFeedbackRecord",
                "source_type": SourceType.ACTION,
                "source_id": "test-executor",
            }
        ),
        action_id=action_id,
        action_type=RobotActionType.SEARCH,
        target_entity=target,
        attempted_location_id=location_id,
        valid_time=interval,
        outcome_distribution={RobotActionOutcome.NOT_FOUND: 1.0},
        observation_opportunity_id=opportunity.metadata.record_id,
        action_outcome_model_version=model.model_version,
        action_outcome_calibration_domain=model.calibration_domain,
    )
    log = AppendOnlyTransactionLog()
    log.append((opportunity, feedback), idempotency_key="search-failure-1")
    prior = TargetPresencePrior(
        household_id=feedback.metadata.household_id,
        target_entity_id=target.entity_id,
        location_id=location_id,
        probability=0.8,
    )
    return log, prior, model, feedback


def test_canonical_failure_replay_rebuilds_probabilistic_long_term_projection(
    metadata_factory, interval, entity_factory
):
    log, prior, model, feedback = _canonical_log(metadata_factory, interval, entity_factory)

    report = CanonicalExecutionFeedbackReplayer().replay(
        log,
        initial_priors=(prior,),
        outcome_model_provider=OracleActionOutcomeModelProvider({RobotActionType.SEARCH: model}),
    )

    assert report.input_watermark.global_commit_seq == 1
    assert report.projections[0].initial_probability == 0.8
    assert report.projections[0].current_probability == pytest.approx(0.5)
    assert report.projections[0].applied_feedback_record_ids == (feedback.metadata.record_id,)
    assert report.steps[0].likelihood_ratio == pytest.approx(0.25)


def test_feedback_projection_is_identical_after_log_dump_and_restart(
    metadata_factory, interval, entity_factory, tmp_path
):
    log, prior, model, _feedback = _canonical_log(metadata_factory, interval, entity_factory)
    provider = OracleActionOutcomeModelProvider({RobotActionType.SEARCH: model})
    before = CanonicalExecutionFeedbackReplayer().replay(
        log, initial_priors=(prior,), outcome_model_provider=provider
    )
    path = tmp_path / "direction-three-canonical.json"
    log.dump(path)

    restored = AppendOnlyTransactionLog.load(path)
    after = CanonicalExecutionFeedbackReplayer().replay(
        restored, initial_priors=(prior,), outcome_model_provider=provider
    )

    assert before == after


def test_replay_rejects_model_drift_from_canonical_feedback(
    metadata_factory, interval, entity_factory
):
    log, prior, _model_used, _feedback = _canonical_log(metadata_factory, interval, entity_factory)
    drifted = _model(version="search-outcome@9")

    with pytest.raises(ValueError, match="version differs"):
        CanonicalExecutionFeedbackReplayer().replay(
            log,
            initial_priors=(prior,),
            outcome_model_provider=OracleActionOutcomeModelProvider(
                {RobotActionType.SEARCH: drifted}
            ),
        )


def test_replay_rejects_feedback_without_snapshot_bound_prior(
    metadata_factory, interval, entity_factory
):
    log, _prior, model, _feedback = _canonical_log(metadata_factory, interval, entity_factory)

    with pytest.raises(ValueError, match="no snapshot-bound initial"):
        CanonicalExecutionFeedbackReplayer().replay(
            log,
            initial_priors=(),
            outcome_model_provider=OracleActionOutcomeModelProvider(
                {RobotActionType.SEARCH: model}
            ),
        )
