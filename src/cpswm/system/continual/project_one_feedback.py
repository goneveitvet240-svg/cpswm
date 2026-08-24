"""Pluggable feedback and project-two revision contracts for the prototype."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from cpswm.contracts import ExecutionFeedbackRecord

from .execution_feedback_projector import ProjectedFeedbackEvidence
from .project_one_regime_loop import PrototypeLoopConfig, PrototypeStatisticOperation


class EventRevisionKind(StrEnum):
    RETRACT = "retract"
    CORRECT = "correct"


@dataclass(frozen=True, slots=True)
class EventRevisionOutcome:
    """Minimal adapter accepted from project two; no project-two model is duplicated."""

    kind: EventRevisionKind
    superseded_revision_id: UUID
    evidence_source_record_ids: tuple[UUID, ...]
    rationale: str
    corrected_revision_id: UUID | None = None
    corrected_location_id: UUID | None = None
    corrected_owner_mass: float | None = None

    def __post_init__(self) -> None:
        if not self.evidence_source_record_ids or not self.rationale.strip():
            raise ValueError("event revision requires evidence sources and rationale")
        corrected = (
            self.corrected_revision_id,
            self.corrected_location_id,
            self.corrected_owner_mass,
        )
        if self.kind is EventRevisionKind.CORRECT:
            if any(value is None for value in corrected):
                raise ValueError("correct outcome requires revision, location, and owner mass")
            assert self.corrected_owner_mass is not None
            if not 0.0 <= self.corrected_owner_mass <= 1.0:
                raise ValueError("corrected_owner_mass must lie in [0, 1]")
        elif any(value is not None for value in corrected):
            raise ValueError("retract outcome cannot carry corrected statistics")


@dataclass(frozen=True, slots=True)
class FeedbackInterpretation:
    operation: PrototypeStatisticOperation
    evidence_strength: float
    rationale: str
    target_revision_id: UUID | None = None
    corrected_location_id: UUID | None = None


class ExecutionFeedbackInterpretationPolicy(Protocol):
    def interpret(
        self,
        *,
        feedback: ExecutionFeedbackRecord,
        projected: ProjectedFeedbackEvidence,
    ) -> FeedbackInterpretation: ...


class DefaultPrototypeFeedbackPolicy:
    """Conservative default: likelihood evidence, never a one-shot truth label."""

    def __init__(self, config: PrototypeLoopConfig) -> None:
        self.config = config

    def interpret(
        self,
        *,
        feedback: ExecutionFeedbackRecord,
        projected: ProjectedFeedbackEvidence,
    ) -> FeedbackInterpretation:
        raw_revision = feedback.diagnostics.get("source_revision_id")
        target_revision = UUID(raw_revision) if isinstance(raw_revision, str) else None
        update = projected.target_presence_update
        if update is None or target_revision is None:
            return FeedbackInterpretation(
                operation=PrototypeStatisticOperation.QUARANTINE,
                evidence_strength=0.0,
                rationale="feedback lacks a source revision or direct presence likelihood",
            )
        delta = update.posterior_target_present - update.prior_target_present
        if delta >= self.config.feedback_decision_margin:
            return FeedbackInterpretation(
                operation=PrototypeStatisticOperation.REINFORCE,
                evidence_strength=min(self.config.feedback_success_strength, abs(delta)),
                target_revision_id=target_revision,
                rationale=(
                    "likelihood-weighted success reinforces the explicitly cited "
                    "owner-attributed revision"
                ),
            )
        # Negative evidence is deliberately quarantined by default.  A caller
        # may plug in a calibrated policy that emits RETRACT or CORRECT.
        return FeedbackInterpretation(
            operation=PrototypeStatisticOperation.QUARANTINE,
            evidence_strength=min(self.config.feedback_failure_strength, abs(delta)),
            target_revision_id=target_revision,
            rationale="negative/weak feedback is evidence, not ground truth",
        )
