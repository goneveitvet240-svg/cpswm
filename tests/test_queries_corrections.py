from uuid import uuid4

import pytest
from pydantic import ValidationError

from cpswm.contracts import (
    AuthorityLevel,
    AuthorityScope,
    CorrectionMode,
    EntityType,
    ProjectionLag,
    QueryCandidate,
    QueryConsistencyMode,
    RetrievalBudget,
    RetrievalCoverage,
    SourceType,
    UserCorrectionEvent,
    WorldModelQuery,
    WorldModelQueryResult,
)
from cpswm.contracts.queries import QueryConstraint


def test_retrieval_budget_requires_at_least_one_limit():
    with pytest.raises(ValidationError):
        RetrievalBudget()


def test_watermark_query_requires_watermark(metadata_factory):
    with pytest.raises(ValidationError):
        WorldModelQuery(
            metadata=metadata_factory(schema_name="cpswm.WorldModelQuery"),
            constraints=(QueryConstraint(field="category", operator="eq", value="cup"),),
            consistency_mode=QueryConsistencyMode.AT_INPUT_WATERMARK,
            retrieval_budget=RetrievalBudget(max_events=100),
        )


def test_budget_exhaustion_must_be_explicit():
    coverage = RetrievalCoverage(
        events_scanned=100,
        events_available=1000,
        budget_exhausted=True,
        exhaustion_reasons=("max_events",),
    )
    assert coverage.events_scanned < coverage.events_available
    with pytest.raises(ValidationError):
        RetrievalCoverage(events_scanned=100, budget_exhausted=True)


def test_query_result_ranks_are_contiguous(metadata_factory, entity_factory):
    candidate = QueryCandidate(
        rank=2,
        entity=entity_factory(EntityType.OBJECT_INSTANCE),
        posterior_probability=0.7,
    )
    with pytest.raises(ValidationError):
        WorldModelQueryResult(
            metadata=metadata_factory(schema_name="cpswm.WorldModelQueryResult"),
            query_id=uuid4(),
            projection_id=uuid4(),
            candidates=(candidate,),
            retrieval_coverage=RetrievalCoverage(events_scanned=10),
        )


def test_projection_lag_cannot_be_negative_direction():
    with pytest.raises(ValidationError):
        ProjectionLag(projection_commit_seq=11, latest_normative_commit_seq=10)


def test_user_correction_is_not_execution_feedback(
    metadata_factory, interval, entity_factory, evidence_ref, household_id
):
    correction = UserCorrectionEvent(
        metadata=metadata_factory(
            schema_name="cpswm.UserCorrectionEvent", source_type=SourceType.USER
        ),
        actor=entity_factory(EntityType.PERSON),
        authority_level=AuthorityLevel.AUTHORIZED_CORRECTOR,
        authority_scope=AuthorityScope(household_id=household_id),
        correction_mode=CorrectionMode.SUPERSEDE,
        target_record_ids=(uuid4(),),
        replacement_payload={"location": "Kitchen"},
        user_statement_ref=evidence_ref,
        valid_time=interval,
    )
    dumped = correction.model_dump()
    assert "authority_level" in dumped
    assert "evidence_reliability" not in dumped
    assert "posterior_probability" not in dumped


def test_user_correction_must_come_from_user(
    metadata_factory, interval, entity_factory, evidence_ref, household_id
):
    with pytest.raises(ValidationError):
        UserCorrectionEvent(
            metadata=metadata_factory(
                schema_name="cpswm.UserCorrectionEvent", source_type=SourceType.ACTION
            ),
            actor=entity_factory(EntityType.PERSON),
            authority_level=AuthorityLevel.AUTHORIZED_CORRECTOR,
            authority_scope=AuthorityScope(household_id=household_id),
            correction_mode=CorrectionMode.RETRACT,
            target_record_ids=(uuid4(),),
            user_statement_ref=evidence_ref,
            valid_time=interval,
        )
