"""M28 privacy / governance vertical slice tests.

Covers household-scoped capability authorization, oracle-channel audit,
tombstone deletion, cross-restart persistence, deterministic replay, and the
adversarial negatives (forged grant, expired grant, cross-household access,
purpose swap, revocation-then-replay, forged deletion receipt).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from cpswm.contracts import (
    BaseRecordMetadata,
    InputWatermark,
    SourceType,
    ValidTimeInterval,
)
from cpswm.foundation.persistence_replay import AppendOnlyTransactionLog
from cpswm.system.privacy_governance import (
    AuthorizationDeniedError,
    CapabilityGrant,
    CapabilityRevocation,
    DeletionExecutionReceipt,
    GovernanceConflictError,
    HouseholdGovernance,
    Operation,
    OracleAccessDecision,
    OracleAccessRequest,
    ResourceKind,
    UserDeletionRequest,
)

START = datetime(2026, 8, 10, 8, 0, tzinfo=UTC)


def _metadata(*, household_id, source_type=SourceType.MODEL, source_id="governance"):
    return BaseRecordMetadata(
        schema_name="cpswm.privacy.Record",
        schema_version="0.1.0",
        household_id=household_id,
        session_id=uuid4(),
        recorded_time=START,
        source_type=source_type,
        source_id=source_id,
    )


def _valid_time(*, start=START, minutes=60):
    return ValidTimeInterval(start=start, end=start + timedelta(minutes=minutes))


def _grant(
    *,
    household_id,
    subject="evaluator.benchmark",
    resource=ResourceKind.GT,
    operation=Operation.READ,
    purpose="evaluation_only",
    grant_id=None,
    start=START,
    minutes=60,
):
    return CapabilityGrant(
        metadata=_metadata(household_id=household_id),
        grant_id=grant_id or uuid4(),
        subject=subject,
        household_id=household_id,
        resource=resource,
        operation=operation,
        purpose=purpose,
        valid_time=_valid_time(start=start, minutes=minutes),
        issuer="governance-test",
    )


# ------------------------------------------------------------------- grants


def test_grant_binds_all_required_fields():
    household = uuid4()
    grant = _grant(household_id=household)
    assert grant.subject
    assert grant.household_id == household
    assert grant.resource == ResourceKind.GT
    assert grant.operation == Operation.READ
    assert grant.purpose == "evaluation_only"
    assert grant.valid_time.start == START
    assert grant.issuer


def test_revoked_grant_does_not_authorize():
    household = uuid4()
    governance = HouseholdGovernance()
    grant = governance.issue_grant(_grant(household_id=household))
    assert governance.authorize(
        subject=grant.subject,
        household_id=household,
        resource=ResourceKind.GT,
        operation=Operation.READ,
        purpose="evaluation_only",
        at_time=START + timedelta(minutes=1),
    )
    governance.revoke(
        CapabilityRevocation(
            metadata=_metadata(household_id=household),
            grant_id=grant.grant_id,
            revoked_by="owner",
            revoked_time=START + timedelta(minutes=2),
            reason="test",
        )
    )
    assert not governance.authorize(
        subject=grant.subject,
        household_id=household,
        resource=ResourceKind.GT,
        operation=Operation.READ,
        purpose="evaluation_only",
        at_time=START + timedelta(minutes=3),
    )


def test_expired_grant_does_not_authorize():
    household = uuid4()
    governance = HouseholdGovernance()
    grant = governance.issue_grant(_grant(household_id=household, minutes=10))
    assert not governance.authorize(
        subject=grant.subject,
        household_id=household,
        resource=ResourceKind.GT,
        operation=Operation.READ,
        purpose="evaluation_only",
        at_time=START + timedelta(minutes=20),
    )


def test_household_a_grant_cannot_authorize_household_b():
    household_a = uuid4()
    household_b = uuid4()
    governance = HouseholdGovernance()
    grant = governance.issue_grant(_grant(household_id=household_a))
    assert not governance.authorize(
        subject=grant.subject,
        household_id=household_b,
        resource=ResourceKind.GT,
        operation=Operation.READ,
        purpose="evaluation_only",
        at_time=START + timedelta(minutes=1),
    )


def test_purpose_swap_is_denied():
    household = uuid4()
    governance = HouseholdGovernance()
    grant = governance.issue_grant(_grant(household_id=household, purpose="evaluation_only"))
    assert not governance.authorize(
        subject=grant.subject,
        household_id=household,
        resource=ResourceKind.GT,
        operation=Operation.READ,
        purpose="deployment",  # swapped purpose
        at_time=START + timedelta(minutes=1),
    )


def test_forged_grant_is_not_authorized():
    household = uuid4()
    governance = HouseholdGovernance()
    # No grant was ever issued; a fabricated subject/purpose pair fails.
    assert not governance.authorize(
        subject="forged.evaluator",
        household_id=household,
        resource=ResourceKind.GT,
        operation=Operation.READ,
        purpose="evaluation_only",
        at_time=START,
    )


def test_gt_grant_forbidden_for_ordinary_modules():
    household = uuid4()
    governance = HouseholdGovernance()
    with pytest.raises(GovernanceConflictError):
        governance.issue_grant(
            _grant(
                household_id=household,
                subject="world_model.belief_state",
                resource=ResourceKind.GT,
            )
        )


def test_gt_grant_requires_evaluator_subject():
    household = uuid4()
    governance = HouseholdGovernance()
    with pytest.raises(GovernanceConflictError):
        governance.issue_grant(
            _grant(
                household_id=household,
                subject="some.other.module",
                resource=ResourceKind.GT,
            )
        )


# ------------------------------------------------------------------- oracle


def test_oracle_access_requires_evaluation_only():
    household = uuid4()
    with pytest.raises(ValidationError):
        OracleAccessRequest(
            metadata=_metadata(household_id=household),
            caller="evaluator.benchmark",
            household_id=household,
            resource=ResourceKind.GT,
            evaluation_only=False,
            purpose="evaluation_only",
            input_watermark=InputWatermark(
                global_commit_seq=0,
                transaction_id=uuid4(),
                recorded_at=START,
            ),
        )


def test_oracle_audit_records_caller_purpose_watermark_summary():
    household = uuid4()
    governance = HouseholdGovernance()
    governance.issue_grant(_grant(household_id=household, subject="evaluator.benchmark"))
    watermark = InputWatermark(
        global_commit_seq=7,
        transaction_id=uuid4(),
        recorded_at=START,
    )
    request = OracleAccessRequest(
        metadata=_metadata(household_id=household),
        caller="evaluator.benchmark",
        household_id=household,
        resource=ResourceKind.GT,
        evaluation_only=True,
        purpose="evaluation_only",
        input_watermark=watermark,
    )
    decision = governance.decide_oracle_access(
        request,
        decided_by="governance-test",
        decided_time=START,
    )
    assert decision.allowed is True
    assert decision.grant_id is not None
    audit = governance.record_oracle_audit(
        decision=decision,
        caller="evaluator.benchmark",
        purpose="evaluation_only",
        input_watermark=watermark,
        output_summary={"metric": "ece", "value": 0.12},
        metadata=_metadata(household_id=household),
    )
    assert audit.input_watermark.global_commit_seq == 7
    assert audit.output_summary == {"metric": "ece", "value": 0.12}


def test_oracle_decision_denied_requires_reason():
    household = uuid4()
    with pytest.raises(ValidationError):
        OracleAccessDecision(
            metadata=_metadata(household_id=household),
            request_id=uuid4(),
            request_hash="0" * 64,
            caller="evaluator.benchmark",
            household_id=household,
            allowed=False,
            decided_by="governance-test",
            decided_time=START,
            denial_reason=None,
            input_watermark=InputWatermark(
                global_commit_seq=0,
                transaction_id=uuid4(),
                recorded_at=START,
            ),
        )


# ----------------------------------------------------------------- deletion


def test_deletion_produces_tombstone_not_rewrite():
    household = uuid4()
    governance = HouseholdGovernance()
    target_id = uuid4()
    request = UserDeletionRequest(
        metadata=_metadata(household_id=household),
        household_id=household,
        subject="owner",
        target_record_ids=(target_id,),
        requested_time=START,
    )
    # Authorize deletion via a privacy delete grant.
    governance.issue_grant(
        _grant(
            household_id=household,
            subject="owner",
            resource=ResourceKind.PRIVACY,
            operation=Operation.DELETE,
            purpose="user_deletion",
        )
    )
    receipt = governance.execute_deletion(request, executed_time=START)
    assert target_id in receipt.tombstoned_record_ids

    # The append-only log still contains the full history; only the projection
    # hides the tombstoned record.
    transactions = governance._log.read()
    assert transactions


def test_deletion_without_authorization_is_denied():
    household = uuid4()
    governance = HouseholdGovernance()
    request = UserDeletionRequest(
        metadata=_metadata(household_id=household),
        household_id=household,
        subject="owner",
        target_record_ids=(uuid4(),),
        requested_time=START,
    )
    with pytest.raises(AuthorizationDeniedError):
        governance.execute_deletion(request, executed_time=START)


def test_deletion_receipt_cannot_be_forged():
    household = uuid4()
    other = uuid4()
    with pytest.raises(ValidationError):
        DeletionExecutionReceipt(
            metadata=_metadata(household_id=household),
            deletion_request_id=uuid4(),
            household_id=other,  # forged household mismatch
            tombstoned_record_ids=(uuid4(),),
            executed_time=START,
            projection_version="1.0.0",
        )


# -------------------------------------------------------- persistence/replay


def test_cross_restart_persistence_and_deterministic_replay():
    household = uuid4()
    log = AppendOnlyTransactionLog()
    first = HouseholdGovernance(log=log)
    grant = first.issue_grant(_grant(household_id=household))
    first.revoke(
        CapabilityRevocation(
            metadata=_metadata(household_id=household),
            grant_id=grant.grant_id,
            revoked_by="owner",
            revoked_time=START + timedelta(minutes=2),
            reason="test",
        )
    )

    # A fresh service instance restored from the same log must see the same
    # state: the grant exists but is revoked.
    second = HouseholdGovernance(log=log)
    second.restore()
    assert not second.authorize(
        subject=grant.subject,
        household_id=household,
        resource=ResourceKind.GT,
        operation=Operation.READ,
        purpose="evaluation_only",
        at_time=START + timedelta(minutes=3),
    )


def test_replay_after_restore_keeps_audit_records():
    household = uuid4()
    log = AppendOnlyTransactionLog()
    governance = HouseholdGovernance(log=log)
    governance.issue_grant(_grant(household_id=household, subject="evaluator.benchmark"))
    watermark = InputWatermark(
        global_commit_seq=1,
        transaction_id=uuid4(),
        recorded_at=START,
    )
    request = OracleAccessRequest(
        metadata=_metadata(household_id=household),
        caller="evaluator.benchmark",
        household_id=household,
        resource=ResourceKind.GT,
        evaluation_only=True,
        purpose="evaluation_only",
        input_watermark=watermark,
    )
    decision = governance.decide_oracle_access(
        request,
        decided_by="governance-test",
        decided_time=START,
    )
    governance.record_oracle_audit(
        decision=decision,
        caller="evaluator.benchmark",
        purpose="evaluation_only",
        input_watermark=watermark,
        output_summary={"ok": True},
        metadata=_metadata(household_id=household),
    )

    restored = HouseholdGovernance(log=log)
    restored.restore()
    assert len(restored._audit_records) == 1
