"""Adapters for data the project did not generate.

Every real source lands here and leaves as a ``ProjectOneStream`` plus a
separate ``ProjectOneTruthSet``.  Adding a source therefore costs one adapter,
never a change to the decision chain -- which is the property that makes a
"does it survive real data?" result attributable to the data rather than to a
quiet edit somewhere in the method.
"""

from __future__ import annotations

from .findingdory import (
    FINDINGDORY_ADAPTER_VERSION,
    FINDINGDORY_SCHEMA_FIELDS,
    FINDINGDORY_UNAVAILABLE_FIELDS,
    FindingDoryAdaptationRecord,
    FindingDoryMetadataAudit,
    FindingDoryMetadataBatch,
    FindingDoryMetadataRow,
    adapt_findingdory_rows,
    load_findingdory_jsonl,
)
from .jsonl_adapter import (
    JSONL_ADAPTER_VERSION,
    REQUIRED_EVENT_FIELDS,
    UNKNOWN_LOCATION,
    JSONLAdapter,
    JSONLLoadReport,
    JSONLRejection,
    UnknownLocationPolicy,
)

__all__ = [
    "FINDINGDORY_ADAPTER_VERSION",
    "FINDINGDORY_SCHEMA_FIELDS",
    "FINDINGDORY_UNAVAILABLE_FIELDS",
    "JSONL_ADAPTER_VERSION",
    "REQUIRED_EVENT_FIELDS",
    "UNKNOWN_LOCATION",
    "FindingDoryAdaptationRecord",
    "FindingDoryMetadataAudit",
    "FindingDoryMetadataBatch",
    "FindingDoryMetadataRow",
    "JSONLAdapter",
    "JSONLLoadReport",
    "JSONLRejection",
    "UnknownLocationPolicy",
    "adapt_findingdory_rows",
    "load_findingdory_jsonl",
]
