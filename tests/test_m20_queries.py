"""M20 budgeted world-model query contract tests."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from cpswm.contracts import (
    BaseRecordMetadata,
    QueryConsistencyMode,
    RetrievalBudget,
    SourceType,
    WorldModelQuery,
)
from cpswm.contracts.queries import QueryConstraint


def _metadata(household_id):
    return BaseRecordMetadata(
        schema_name="cpswm.query.WorldModelQuery",
        schema_version="0.1.0",
        household_id=household_id,
        session_id=uuid4(),
        recorded_time=datetime(2026, 8, 10, 8, 0, tzinfo=UTC),
        source_type=SourceType.MODEL,
        source_id="m20-test",
    )


def test_retrieval_budget_requires_at_least_one_limit():
    with pytest.raises(ValidationError):
        RetrievalBudget()


def test_world_model_query_binds_budget_and_constraints():
    household = uuid4()
    query = WorldModelQuery(
        metadata=_metadata(household),
        constraints=(QueryConstraint(field="located_at", operator="==", value="kitchen"),),
        consistency_mode=QueryConsistencyMode.LATEST_COMPLETE_PROJECTION,
        retrieval_budget=RetrievalBudget(max_events=10),
    )
    assert query.retrieval_budget.max_events == 10
    assert query.constraints[0].field == "located_at"


def test_world_model_query_rejects_empty_constraints():
    household = uuid4()
    with pytest.raises(ValidationError):
        WorldModelQuery(
            metadata=_metadata(household),
            constraints=(),
            consistency_mode=QueryConsistencyMode.LATEST_COMPLETE_PROJECTION,
            retrieval_budget=RetrievalBudget(max_events=10),
        )
