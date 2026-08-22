"""DecisionContext: belief->action traceability for the embodied interface.

结构二 §4.6 requires that a single belief model expose a *traceable* interface to
downstream embodied use: every task request, map snapshot, and execution
feedback should be attributable to the belief state, cause attribution, budget,
and authorization that produced or accompanied it, so an action's provenance can
be audited back to the belief that justified it.

This module adds that context additively: a :class:`DecisionContext` value plus a
:class:`DecisionContextBinding` that attaches one context to a task request, a
map snapshot, or an execution feedback record by id.  It does not mutate the
existing task/map/feedback contracts, so it composes with them without changing
their schemas or hashes.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import Field, field_validator

from .base import BaseRecordMetadata, ContractModel, Probability, require_aware


class DecisionSurface(StrEnum):
    """Which downstream surface a DecisionContext is attached to."""

    TASK_REQUEST = "task_request"
    MAP_SNAPSHOT = "map_snapshot"
    EXECUTION_FEEDBACK = "execution_feedback"


class DecisionContext(ContractModel):
    """The belief-state provenance behind a downstream decision.

    Every field is a *reference* or a summary statistic, never a mutable belief:
    it records which belief informed the decision and how the change was
    attributed, so the decision is auditable without duplicating world state.
    """

    decision_id: UUID
    decision_time: datetime
    #: The belief snapshot / projection this decision read.
    belief_snapshot_id: UUID | None = None
    #: Cause attribution from the joint CF-BOCPD at decision time (if any).
    segment_change_probability: Probability | None = None
    transient_noise_probability: Probability | None = None
    attributed_cause: str | None = None
    #: RGRC event-derived-update ledger marker the decision is consistent with.
    consolidation_ledger_ref: str | None = None
    #: M28 authorization scope that permitted this decision (if any).
    authorization_scope_id: UUID | None = None
    #: Budget ledger reference bounding this decision (if any).
    budget_ref: str | None = None
    model_versions: Mapping[str, str] = Field(default_factory=dict)
    code_version: str | None = None
    rationale: str = Field(min_length=1)

    @field_validator("decision_time")
    @classmethod
    def validate_decision_time(cls, value: datetime) -> datetime:
        return require_aware(value, "decision_time")


class DecisionContextBinding(ContractModel):
    """Append-only binding of one DecisionContext to a downstream record."""

    metadata: BaseRecordMetadata
    surface: DecisionSurface
    #: The task-request / map-snapshot / execution-feedback record id.
    subject_record_id: UUID
    decision_context: DecisionContext

    @classmethod
    def for_task_request(
        cls,
        *,
        metadata: BaseRecordMetadata,
        task_request_id: UUID,
        decision_context: DecisionContext,
    ) -> DecisionContextBinding:
        return cls(
            metadata=metadata,
            surface=DecisionSurface.TASK_REQUEST,
            subject_record_id=task_request_id,
            decision_context=decision_context,
        )

    @classmethod
    def for_map_snapshot(
        cls,
        *,
        metadata: BaseRecordMetadata,
        map_snapshot_id: UUID,
        decision_context: DecisionContext,
    ) -> DecisionContextBinding:
        return cls(
            metadata=metadata,
            surface=DecisionSurface.MAP_SNAPSHOT,
            subject_record_id=map_snapshot_id,
            decision_context=decision_context,
        )

    @classmethod
    def for_execution_feedback(
        cls,
        *,
        metadata: BaseRecordMetadata,
        execution_feedback_id: UUID,
        decision_context: DecisionContext,
    ) -> DecisionContextBinding:
        return cls(
            metadata=metadata,
            surface=DecisionSurface.EXECUTION_FEEDBACK,
            subject_record_id=execution_feedback_id,
            decision_context=decision_context,
        )
