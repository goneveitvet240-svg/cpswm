from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from cpswm.contracts import (
    BaseRecordMetadata,
    EntityRef,
    EntityType,
    EvidenceRef,
    SourceType,
    ValidTimeInterval,
)


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 8, 10, 8, 0, tzinfo=UTC)


@pytest.fixture
def household_id():
    return uuid4()


@pytest.fixture
def session_id():
    return uuid4()


@pytest.fixture
def metadata_factory(household_id, session_id, now):
    def make(
        *,
        schema_name: str = "test.Record",
        source_type: SourceType = SourceType.MODEL,
        source_id: str = "test-source",
    ) -> BaseRecordMetadata:
        return BaseRecordMetadata(
            schema_name=schema_name,
            schema_version="0.1.0",
            household_id=household_id,
            session_id=session_id,
            recorded_time=now,
            source_type=source_type,
            source_id=source_id,
            model_version="test-model@1",
        )

    return make


@pytest.fixture
def interval(now):
    return ValidTimeInterval(start=now, end=now + timedelta(minutes=5))


@pytest.fixture
def entity_factory():
    def make(entity_type: EntityType = EntityType.OBJECT_INSTANCE) -> EntityRef:
        return EntityRef(entity_id=uuid4(), entity_type=entity_type)

    return make


@pytest.fixture
def evidence_ref():
    return EvidenceRef(
        evidence_type="synthetic_observation",
        source_record_id=uuid4(),
        locator="frame:17",
    )
