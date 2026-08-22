"""M28 privacy, authorization, and data governance vertical slice."""

from .contracts import (
    CapabilityGrant,
    CapabilityRevocation,
    CapabilityStatus,
    DataRetentionPolicy,
    DeletionExecutionReceipt,
    Operation,
    OracleAccessAuditRecord,
    OracleAccessDecision,
    OracleAccessRequest,
    ResourceKind,
    UserDeletionRequest,
)
from .governance import (
    FORBIDDEN_GT_SUBJECT_PREFIXES,
    AuthorizationDeniedError,
    GovernanceConflictError,
    HouseholdGovernance,
    decode_governance_record,
)

__all__ = [
    "FORBIDDEN_GT_SUBJECT_PREFIXES",
    "AuthorizationDeniedError",
    "CapabilityGrant",
    "CapabilityRevocation",
    "CapabilityStatus",
    "DataRetentionPolicy",
    "DeletionExecutionReceipt",
    "GovernanceConflictError",
    "HouseholdGovernance",
    "Operation",
    "OracleAccessAuditRecord",
    "OracleAccessDecision",
    "OracleAccessRequest",
    "ResourceKind",
    "UserDeletionRequest",
    "decode_governance_record",
]
