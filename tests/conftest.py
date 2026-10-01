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


@pytest.fixture(scope="session")
def current_full_scientific_loop(tmp_path_factory):
    """Use a fully verified current result; never promote historical fixture bytes."""
    import json
    import os
    from pathlib import Path

    from cpswm.system.evaluation_operations.structure_two_full_scientific_loop import (
        run_full_scientific_loop_development,
        verify_full_scientific_loop_result,
    )

    root = Path(__file__).resolve().parents[1]
    override = os.environ.get("S2_CURRENT_FULL_SCIENTIFIC_LOOP")
    if override is not None:
        if not override:
            raise ValueError("explicit current scientific-loop path is empty")
        payload = json.loads(Path(override).read_text())
    else:
        payload = run_full_scientific_loop_development(repository_root=root)
        output = tmp_path_factory.mktemp("current-full-scientific-loop") / "result.json"
        output.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    verify_full_scientific_loop_result(payload, repository_root=root, fresh_replay=True)
    return payload
