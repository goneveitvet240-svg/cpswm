"""Reproducible selective observations for long-horizon habit experiments.

This module is a simulator adapter: it may use privileged presence flags to
sample an observation, but its output contains only robot-visible semantics and
never carries ground-truth identifiers.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from cpswm.contracts import (
    BaseRecordMetadata,
    ObservationDetectionResult,
    ObservationOpportunityRecord,
    ObservationOutcome,
)


class SelectiveObservationSample(BaseModel):
    """Explicit random input for deterministic replay of one observation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    selected: bool
    target_present: bool
    detection_draw: float = Field(ge=0.0, le=1.0)


def simulate_location_observation(
    *,
    metadata: BaseRecordMetadata,
    observation_opportunity: ObservationOpportunityRecord,
    sample: SelectiveObservationSample,
    detected_object_instance_id: UUID,
    detected_location_id: UUID,
    minimum_verification_strength: float = 0.5,
) -> ObservationDetectionResult:
    """Project one privileged simulation state into a robot-visible outcome.

    ``detection_draw`` is supplied by the caller rather than sampled internally,
    so M31 can replay exactly the same observation stream for every baseline.
    A selected but low-quality view is ``AMBIGUOUS`` and cannot be converted into
    negative evidence. A high-quality non-detection is ``VERIFIED_ABSENCE``;
    its likelihood still permits false negatives during Bayesian updating.
    """

    if not 0.0 <= minimum_verification_strength <= 1.0:
        raise ValueError("minimum_verification_strength must be in [0, 1]")

    if sample.selected != observation_opportunity.selected:
        raise ValueError("sample.selected must match the observation opportunity")

    detection_opportunity = observation_opportunity.p_detect_given_state_action
    if not observation_opportunity.selected:
        outcome = ObservationOutcome.NOT_OBSERVED
    elif detection_opportunity < minimum_verification_strength:
        outcome = ObservationOutcome.AMBIGUOUS
    elif sample.target_present and sample.detection_draw < detection_opportunity:
        outcome = ObservationOutcome.DETECTED
    else:
        outcome = ObservationOutcome.VERIFIED_ABSENCE

    detected = outcome == ObservationOutcome.DETECTED
    return ObservationDetectionResult(
        metadata=metadata,
        observation_opportunity_id=observation_opportunity.metadata.record_id,
        outcome=outcome,
        detected_object_instance_id=detected_object_instance_id if detected else None,
        detected_location_id=detected_location_id if detected else None,
        detection_time=observation_opportunity.opportunity_time if detected else None,
        negative_evidence_strength=(
            detection_opportunity
            if outcome == ObservationOutcome.VERIFIED_ABSENCE
            else 0.0
        ),
    )
