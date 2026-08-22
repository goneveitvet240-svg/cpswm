"""M22 user-correction contract tests."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from cpswm.contracts import (
    AuthorityLevel,
    AuthorityScope,
    BaseRecordMetadata,
    CorrectionMode,
    EntityRef,
    EntityType,
    EvidenceRef,
    SourceType,
    UserCorrectionEvent,
    ValidTimeInterval,
)

START = datetime(2026, 8, 10, 8, 0, tzinfo=UTC)


def _metadata(household_id, source_type=SourceType.USER):
    return BaseRecordMetadata(
        schema_name="cpswm.correction.UserCorrectionEvent",
        schema_version="0.1.0",
        household_id=household_id,
        session_id=uuid4(),
        recorded_time=START,
        source_type=source_type,
        source_id="m22-test",
    )


def test_user_correction_event_requires_user_source():
    household = uuid4()
    with pytest.raises(ValidationError):
        UserCorrectionEvent(
            metadata=_metadata(household, source_type=SourceType.MODEL),
            actor=EntityRef(entity_id=uuid4(), entity_type=EntityType.PERSON),
            authority_level=AuthorityLevel.HOUSEHOLD_OWNER,
            authority_scope=AuthorityScope(household_id=household),
            correction_mode=CorrectionMode.CONFIRM,
            target_record_ids=(uuid4(),),
            user_statement_ref=EvidenceRef(
                evidence_type="user_statement",
                source_record_id=uuid4(),
            ),
            valid_time=ValidTimeInterval(start=START, end=None),
        )


def test_user_correction_event_requires_targets_for_retract():
    household = uuid4()
    with pytest.raises(ValidationError):
        UserCorrectionEvent(
            metadata=_metadata(household),
            actor=EntityRef(entity_id=uuid4(), entity_type=EntityType.PERSON),
            authority_level=AuthorityLevel.HOUSEHOLD_OWNER,
            authority_scope=AuthorityScope(household_id=household),
            correction_mode=CorrectionMode.RETRACT,
            target_record_ids=(),
            user_statement_ref=EvidenceRef(
                evidence_type="user_statement",
                source_record_id=uuid4(),
            ),
            valid_time=ValidTimeInterval(start=START, end=None),
        )
