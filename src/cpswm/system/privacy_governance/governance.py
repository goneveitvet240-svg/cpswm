"""M28 household-scoped capability authorization and data governance.

This is a vertical slice, not a production security system and not a GDPR
compliance claim.  It provides:

* household-scoped :class:`CapabilityGrant` issuance and revocation;
* deterministic ``authorize`` checks (revoked/expired/forged grants fail);
* a hard rule that ordinary M10-M27 subjects cannot receive ``gt.*`` grants;
* evaluator-only oracle access with request/decision/audit records;
* tombstone-based deletion that never rewrites the append-only M03 log.

Persistence uses the M03 :class:`AppendOnlyTransactionLog` so a governance
history survives restart and can be replayed deterministically.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import TypeAdapter

from cpswm.contracts.base import BaseRecordMetadata, require_aware
from cpswm.foundation.persistence_replay import AppendOnlyTransactionLog, CommittedTransaction

from .contracts import (
    CapabilityGrant,
    CapabilityRevocation,
    DataRetentionPolicy,
    DeletionExecutionReceipt,
    Operation,
    OracleAccessAuditRecord,
    OracleAccessDecision,
    OracleAccessRequest,
    ResourceKind,
    UserDeletionRequest,
)

#: Subjects that are ordinary perception / world-model / language / action
#: modules.  They must never hold a ``gt.*`` grant (技术框架 §9.8).
FORBIDDEN_GT_SUBJECT_PREFIXES = (
    "perception_mapping.",
    "world_model.",
    "language_query.",
    "action.",
)

_EVALUATOR_SUBJECT_PREFIXES = ("evaluator.", "benchmark.", "oracle_adapter.")


class AuthorizationDeniedError(PermissionError):
    """An authorization check failed."""


class GovernanceConflictError(ValueError):
    """A governance record conflicts with an existing one."""


def decode_governance_record(payload: Any, schema_name: str | None = None) -> Any:
    """Decode a persisted governance record from its JSON payload.

    The payload is a ``model_dump(mode="json")`` dict.  The record type is
    recovered from the payload's discriminating fields rather than trusting the
    schema name, so a mislabeled record cannot be silently re-typed on restore.
    """

    if not isinstance(payload, dict):
        raise GovernanceConflictError("governance payload must be an object")

    if "revocation_id" in payload and "grant_id" in payload and "revoked_by" in payload:
        return TypeAdapter(CapabilityRevocation).validate_python(payload)
    if "receipt_id" in payload and "tombstoned_record_ids" in payload:
        return TypeAdapter(DeletionExecutionReceipt).validate_python(payload)
    if "audit_id" in payload and "decision_id" in payload and "output_summary" in payload:
        return TypeAdapter(OracleAccessAuditRecord).validate_python(payload)
    if "policy_id" in payload and "retention_seconds" in payload:
        return TypeAdapter(DataRetentionPolicy).validate_python(payload)
    if "evaluation_only" in payload and "request_id" in payload:
        return TypeAdapter(OracleAccessRequest).validate_python(payload)
    if "decision_id" in payload and "allowed" in payload and "decided_by" in payload:
        return TypeAdapter(OracleAccessDecision).validate_python(payload)
    if "deletion_request_id" in payload and "subject" in payload:
        return TypeAdapter(UserDeletionRequest).validate_python(payload)
    if "grant_id" in payload and "operation" in payload and "issuer" in payload:
        return TypeAdapter(CapabilityGrant).validate_python(payload)
    raise GovernanceConflictError(
        f"unknown governance record schema {schema_name or '<unnamed>'!r}"
    )


class HouseholdGovernance:
    """Household-scoped capability and deletion authority."""

    def __init__(self, log: AppendOnlyTransactionLog | None = None) -> None:
        self._log = log or AppendOnlyTransactionLog()
        self._grants: dict[UUID, CapabilityGrant] = {}
        self._revocations: dict[UUID, CapabilityRevocation] = {}
        self._requests: dict[UUID, OracleAccessRequest] = {}
        self._decisions: dict[UUID, OracleAccessDecision] = {}
        self._grant_seqs: dict[UUID, int] = {}
        self._request_seqs: dict[UUID, int] = {}
        self._decision_seqs: dict[UUID, int] = {}
        self._retention: list[DataRetentionPolicy] = []
        self._tombstones: dict[UUID, set[UUID]] = {}
        self._audit_records: list[OracleAccessAuditRecord] = []

    # ------------------------------------------------------------------ grants

    def issue_grant(self, grant: CapabilityGrant) -> CapabilityGrant:
        self._validate_gt_grant(grant)
        if grant.grant_id in self._grants:
            if self._grants[grant.grant_id] != grant:
                raise GovernanceConflictError("grant_id already issued with different content")
            return grant
        seq = self._append(grant, f"grant:{grant.grant_id}")
        self._grants[grant.grant_id] = grant
        self._grant_seqs[grant.grant_id] = seq
        return grant

    def revoke(self, revocation: CapabilityRevocation) -> CapabilityRevocation:
        grant = self._grants.get(revocation.grant_id)
        if grant is None:
            raise GovernanceConflictError(f"cannot revoke unknown grant {revocation.grant_id}")
        if revocation.metadata.household_id != grant.household_id:
            raise GovernanceConflictError("revocation household does not match the grant household")
        if revocation.revoked_time < grant.valid_time.start:
            raise GovernanceConflictError("revocation cannot precede the grant's validity start")
        existing = self._revocations.get(revocation.grant_id)
        if existing is not None:
            if existing != revocation:
                raise GovernanceConflictError("grant already revoked with different content")
            return existing
        self._append(revocation, f"revocation:{revocation.revocation_id}")
        self._revocations[revocation.grant_id] = revocation
        return revocation

    def authorize(
        self,
        *,
        subject: str,
        household_id: UUID,
        resource: ResourceKind,
        operation: Operation,
        purpose: str,
        at_time: datetime,
    ) -> bool:
        return (
            self._find_authorizing_grant(
                subject=subject,
                household_id=household_id,
                resource=resource,
                operation=operation,
                purpose=purpose,
                at_time=at_time,
            )
            is not None
        )

    def authorize_or_raise(self, **kwargs: Any) -> None:
        if not self.authorize(**kwargs):
            raise AuthorizationDeniedError("no active grant authorizes this access")

    def _find_authorizing_grant(
        self,
        *,
        subject: str,
        household_id: UUID,
        resource: ResourceKind,
        operation: Operation,
        purpose: str,
        at_time: datetime,
    ) -> CapabilityGrant | None:
        at_time = require_aware(at_time, "at_time")
        for grant in self._grants.values():
            if grant.subject != subject:
                continue
            if grant.household_id != household_id:
                continue
            if grant.resource != resource or grant.operation != operation:
                continue
            if not grant.valid_time.contains(at_time):
                continue
            if grant.grant_id in self._revocations:
                continue
            if grant.purpose != purpose:
                # A purpose swap (same grant, different purpose) is denied.
                continue
            return grant
        return None

    # ----------------------------------------------------------------- oracle

    def decide_oracle_access(
        self,
        request: OracleAccessRequest,
        *,
        decided_by: str,
        decided_time: datetime,
    ) -> OracleAccessDecision:
        """Decide oracle access *from an active grant* -- never from a caller
        flag.  The caller cannot pass ``allowed``; it is derived by re-running
        the grant policy.
        """

        decided_time = require_aware(decided_time, "decided_time")
        if not request.evaluation_only:
            raise GovernanceConflictError("oracle access must be evaluation-only")

        grant = self._find_authorizing_grant(
            subject=request.caller,
            household_id=request.household_id,
            resource=ResourceKind.GT,
            operation=Operation.READ,
            purpose="evaluation_only",
            at_time=decided_time,
        )
        allowed = grant is not None
        decision = OracleAccessDecision(
            metadata=request.metadata.model_copy(update={"record_id": uuid4()}),
            request_id=request.request_id,
            request_hash=request.fingerprint(),
            grant_id=grant.grant_id if grant is not None else None,
            caller=request.caller,
            household_id=request.household_id,
            allowed=allowed,
            decided_by=decided_by,
            decided_time=decided_time,
            denial_reason=None if allowed else "no active grant authorizes oracle access",
            input_watermark=request.input_watermark,
        )
        request_seq = self._append(request, f"oracle-request:{request.request_id}")
        self._requests[request.request_id] = request
        self._request_seqs[request.request_id] = request_seq
        decision_seq = self._append(decision, f"oracle-decision:{decision.decision_id}")
        self._decisions[decision.decision_id] = decision
        self._decision_seqs[decision.decision_id] = decision_seq
        return decision

    def verify_oracle_receipt(self, receipt: OracleAccessDecision) -> bool:
        """Verify an oracle decision receipt's full provenance.

        The receipt must be an allowed decision that exists (field-for-field)
        in the append-only log, its request must exist with a matching
        fingerprint, and the authorizing grant must match the caller,
        household, resource, operation, and purpose and still be active at
        ``decided_time``.
        """

        if not isinstance(receipt, OracleAccessDecision):
            return False
        if not receipt.allowed:
            return False
        stored = self._decisions.get(receipt.decision_id)
        if stored is None or stored != receipt:
            return False
        request = self._requests.get(receipt.request_id)
        if request is None or request.fingerprint() != receipt.request_hash:
            return False
        if request.caller != receipt.caller or request.household_id != receipt.household_id:
            return False
        if receipt.grant_id is None:
            return False
        grant = self._grants.get(receipt.grant_id)
        if grant is None or grant.grant_id in self._revocations:
            return False
        if grant.subject != receipt.caller or grant.household_id != receipt.household_id:
            return False
        if grant.resource != ResourceKind.GT or grant.operation != Operation.READ:
            return False
        if grant.purpose != receipt.purpose:
            return False
        return grant.valid_time.contains(receipt.decided_time)

    def record_oracle_audit(
        self,
        *,
        decision_id: UUID,
        output_summary: Any,
        metadata: BaseRecordMetadata,
    ) -> OracleAccessAuditRecord:
        """Record an oracle audit bound to a stored decision.

        Caller, purpose, watermark, and household are taken from the stored
        decision -- never from the caller.
        """

        decision = self._decisions.get(decision_id)
        if decision is None:
            raise GovernanceConflictError("unknown oracle decision")
        if not decision.allowed:
            raise GovernanceConflictError("cannot audit a denied oracle access")
        if metadata.household_id != decision.household_id:
            raise GovernanceConflictError("audit metadata household does not match decision")
        record = OracleAccessAuditRecord(
            metadata=metadata,
            decision_id=decision.decision_id,
            caller=decision.caller,
            purpose=decision.purpose,
            input_watermark=decision.input_watermark,
            output_summary=output_summary,
        )
        self._append(record, f"oracle-audit:{record.audit_id}")
        self._audit_records.append(record)
        return record

    # -------------------------------------------------------------- retention

    def set_retention_policy(self, policy: DataRetentionPolicy) -> DataRetentionPolicy:
        self._append(policy, f"retention:{policy.policy_id}")
        self._retention.append(policy)
        return policy

    # --------------------------------------------------------------- deletion

    def execute_deletion(
        self,
        request: UserDeletionRequest,
        *,
        executed_time: datetime,
        projection_version: str = "1.0.0",
    ) -> DeletionExecutionReceipt:
        # A deletion is authorized only if the requester holds an active delete
        # grant, or the request carries a matching authorization grant id.
        self._authorize_deletion(request)
        tombstoned = self._tombstones.setdefault(request.household_id, set())
        new_ids = set(request.target_record_ids) - tombstoned
        tombstoned.update(new_ids)
        receipt = DeletionExecutionReceipt(
            metadata=request.metadata,
            deletion_request_id=request.deletion_request_id,
            household_id=request.household_id,
            tombstoned_record_ids=tuple(sorted(new_ids)),
            executed_time=executed_time,
            projection_version=projection_version,
        )
        self._append(receipt, f"deletion-receipt:{receipt.receipt_id}")
        return receipt

    def redacted_projection(
        self,
        transactions: tuple[CommittedTransaction, ...],
        *,
        household_id: UUID,
    ) -> tuple[CommittedTransaction, ...]:
        """Project the append-only log without the tombstoned records.

        The log is never rewritten; this returns a derived projection in which
        tombstoned record IDs are removed.
        """

        tombstoned = self._tombstones.get(household_id, set())
        projected: list[CommittedTransaction] = []
        for transaction in transactions:
            if transaction.household_id != household_id:
                continue
            surviving = tuple(
                record
                for record in transaction.records
                if record.envelope.record_id not in tombstoned
            )
            if not surviving:
                continue
            projected.append(
                CommittedTransaction(
                    transaction_id=transaction.transaction_id,
                    global_commit_seq=transaction.global_commit_seq,
                    household_id=transaction.household_id,
                    trace_id=transaction.trace_id,
                    idempotency_key=transaction.idempotency_key,
                    request_sha256=transaction.request_sha256,
                    committed_at=transaction.committed_at,
                    records=surviving,
                )
            )
        return tuple(projected)

    # ------------------------------------------------------------- internals

    def _validate_gt_grant(self, grant: CapabilityGrant) -> None:
        if grant.resource != ResourceKind.GT:
            return
        if grant.operation != Operation.READ:
            raise GovernanceConflictError("gt.* grants are read-only")
        if grant.purpose != "evaluation_only":
            raise GovernanceConflictError("gt.* grants require purpose=evaluation_only")
        if grant.subject.startswith(FORBIDDEN_GT_SUBJECT_PREFIXES):
            raise GovernanceConflictError(
                f"ordinary module subject {grant.subject!r} cannot hold a gt.* grant"
            )
        if not grant.subject.startswith(_EVALUATOR_SUBJECT_PREFIXES):
            raise GovernanceConflictError(
                "gt.* grants require an evaluator/benchmark/oracle-adapter subject"
            )

    def _authorize_deletion(self, request: UserDeletionRequest) -> None:
        # Deletion is strictly PRIVACY + DELETE + user_deletion: the grant must
        # match the subject, the household, the validity interval, and the
        # exact purpose.  No other grant shape can authorize a deletion.
        grant: CapabilityGrant | None = None
        if request.authorization_grant_id is not None:
            grant = self._grants.get(request.authorization_grant_id)
        else:
            grant = self._find_authorizing_grant(
                subject=request.subject,
                household_id=request.household_id,
                resource=ResourceKind.PRIVACY,
                operation=Operation.DELETE,
                purpose="user_deletion",
                at_time=request.requested_time,
            )

        if grant is None or grant.grant_id in self._revocations:
            raise AuthorizationDeniedError("no active grant authorizes this deletion")
        if grant.subject != request.subject:
            raise AuthorizationDeniedError("deletion grant subject does not match request")
        if grant.household_id != request.household_id:
            raise AuthorizationDeniedError("deletion grant belongs to another household")
        if grant.resource != ResourceKind.PRIVACY or grant.operation != Operation.DELETE:
            raise AuthorizationDeniedError("deletion requires a PRIVACY + DELETE grant")
        if grant.purpose != "user_deletion":
            raise AuthorizationDeniedError("deletion requires purpose=user_deletion")
        if not grant.valid_time.contains(request.requested_time):
            raise AuthorizationDeniedError("deletion grant is expired for the request time")

    def _append(self, record: Any, idempotency_key: str) -> int:
        result = self._log.append([record], idempotency_key=idempotency_key)
        return result.watermark.global_commit_seq

    def restore(self) -> None:
        """Rebuild in-memory state from the append-only log (cross-restart).

        Grant policy is re-executed on every restored grant.  Oracle decisions
        are only trusted when their request and grant also exist in the log, in
        the order ``grant -> request -> decision``, and every binding field
        matches -- a decision injected into the log without a matching request
        or grant is rejected.
        """

        self._grants.clear()
        self._revocations.clear()
        self._requests.clear()
        self._decisions.clear()
        self._grant_seqs.clear()
        self._request_seqs.clear()
        self._decision_seqs.clear()
        self._retention.clear()
        self._tombstones.clear()
        self._audit_records.clear()
        for transaction in self._log.read():
            seq = transaction.global_commit_seq
            for record in transaction.records:
                payload = record.envelope.payload
                decoded = decode_governance_record(payload, record.envelope.schema_name)
                if isinstance(decoded, CapabilityGrant):
                    self._validate_restored_grant(decoded)
                    self._grants[decoded.grant_id] = decoded
                    self._grant_seqs[decoded.grant_id] = seq
                elif isinstance(decoded, CapabilityRevocation):
                    self._validate_restored_revocation(decoded)
                    self._revocations[decoded.grant_id] = decoded
                elif isinstance(decoded, OracleAccessRequest):
                    self._requests[decoded.request_id] = decoded
                    self._request_seqs[decoded.request_id] = seq
                elif isinstance(decoded, OracleAccessDecision):
                    self._validate_restored_decision(decoded, seq)
                    self._decisions[decoded.decision_id] = decoded
                    self._decision_seqs[decoded.decision_id] = seq
                elif isinstance(decoded, DataRetentionPolicy):
                    self._retention.append(decoded)
                elif isinstance(decoded, DeletionExecutionReceipt):
                    bucket = self._tombstones.setdefault(decoded.household_id, set())
                    bucket.update(decoded.tombstoned_record_ids)
                elif isinstance(decoded, OracleAccessAuditRecord):
                    self._audit_records.append(decoded)

    def _validate_restored_decision(
        self,
        decision: OracleAccessDecision,
        decision_seq: int,
    ) -> None:
        request = self._requests.get(decision.request_id)
        if request is None:
            raise GovernanceConflictError(
                f"restored decision {decision.decision_id} references an unknown request"
            )
        request_seq = self._request_seqs.get(decision.request_id, -1)
        if request_seq >= decision_seq:
            raise GovernanceConflictError(
                f"restored decision {decision.decision_id} precedes its request in the log"
            )
        if request.fingerprint() != decision.request_hash:
            raise GovernanceConflictError(
                f"restored decision {decision.decision_id} request hash does not match"
            )
        if request.caller != decision.caller or request.household_id != decision.household_id:
            raise GovernanceConflictError(
                f"restored decision {decision.decision_id} caller/household does not match request"
            )
        if decision.grant_id is None:
            raise GovernanceConflictError(f"restored decision {decision.decision_id} has no grant")
        grant = self._grants.get(decision.grant_id)
        if grant is None:
            raise GovernanceConflictError(
                f"restored decision {decision.decision_id} references an unknown grant"
            )
        grant_seq = self._grant_seqs.get(decision.grant_id, -1)
        if grant_seq >= request_seq:
            raise GovernanceConflictError(
                f"restored decision {decision.decision_id} grant does not precede its request"
            )
        if grant.subject != decision.caller or grant.household_id != decision.household_id:
            raise GovernanceConflictError(
                f"restored decision {decision.decision_id} grant subject/household mismatch"
            )
        if grant.resource != ResourceKind.GT or grant.operation != Operation.READ:
            raise GovernanceConflictError(
                f"restored decision {decision.decision_id} grant is not a gt read"
            )
        if grant.purpose != decision.purpose:
            raise GovernanceConflictError(
                f"restored decision {decision.decision_id} grant purpose mismatch"
            )
        if not grant.valid_time.contains(decision.decided_time):
            raise GovernanceConflictError(
                f"restored decision {decision.decision_id} grant is not valid at decided_time"
            )

    def _validate_restored_grant(self, grant: CapabilityGrant) -> None:
        if grant.household_id != grant.metadata.household_id:
            raise GovernanceConflictError(
                f"restored grant {grant.grant_id} has a mismatched household"
            )
        self._validate_gt_grant(grant)

    def _validate_restored_revocation(self, revocation: CapabilityRevocation) -> None:
        grant = self._grants.get(revocation.grant_id)
        if grant is None:
            raise GovernanceConflictError(
                f"restored revocation references unknown grant {revocation.grant_id}"
            )
        if revocation.metadata.household_id != grant.household_id:
            raise GovernanceConflictError(
                f"restored revocation {revocation.revocation_id} has a mismatched household"
            )
        if revocation.revoked_time < grant.valid_time.start:
            raise GovernanceConflictError(
                f"restored revocation {revocation.revocation_id} precedes its grant validity"
            )

    @property
    def active_grants(self) -> tuple[CapabilityGrant, ...]:
        return tuple(
            grant for grant in self._grants.values() if grant.grant_id not in self._revocations
        )


__all__ = [
    "FORBIDDEN_GT_SUBJECT_PREFIXES",
    "AuthorizationDeniedError",
    "GovernanceConflictError",
    "HouseholdGovernance",
    "decode_governance_record",
]
