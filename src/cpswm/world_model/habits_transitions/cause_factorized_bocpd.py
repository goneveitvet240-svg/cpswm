"""Cause-factorized Bayesian online change-point detection.

Each robot-visible cause owns an independent run-length posterior. This keeps
observation, actor, habit, and transient-noise explanations auditable and lets
simultaneous changes survive instead of forcing a categorical four-way choice.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from math import isclose
from typing import Annotated

from pydantic import Field, field_validator, model_validator

from cpswm.contracts.base import ContractModel, Probability, require_aware

StrictlyPositiveLikelihood = Annotated[float, Field(gt=0.0)]


class ChangeCause(StrEnum):
    OBSERVATION = "observation"
    ACTOR = "actor"
    HABIT = "habit"
    NOISE = "noise"


class CauseEvidenceFrame(ContractModel):
    """One time-local set of cause-specific predictive likelihoods."""

    timestamp: datetime
    continuation_likelihoods: dict[ChangeCause, StrictlyPositiveLikelihood]
    changepoint_likelihoods: dict[ChangeCause, StrictlyPositiveLikelihood]
    evidence_record_ids: tuple[str, ...] = Field(min_length=1)

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, value: datetime) -> datetime:
        return require_aware(value, "timestamp")

    @model_validator(mode="after")
    def validate_cause_support(self) -> CauseEvidenceFrame:
        expected = set(ChangeCause)
        if set(self.continuation_likelihoods) != expected:
            raise ValueError("continuation likelihoods must cover every change cause")
        if set(self.changepoint_likelihoods) != expected:
            raise ValueError("changepoint likelihoods must cover every change cause")
        if len(self.evidence_record_ids) != len(set(self.evidence_record_ids)):
            raise ValueError("cause frame evidence IDs must be unique")
        return self


class CauseRunLengthSnapshot(ContractModel):
    timestamp: datetime
    run_length_posterior_by_cause: dict[ChangeCause, dict[int, Probability]]
    changepoint_probability_by_cause: dict[ChangeCause, Probability]
    evidence_record_ids: tuple[str, ...]

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, value: datetime) -> datetime:
        return require_aware(value, "timestamp")

    @model_validator(mode="after")
    def validate_posteriors(self) -> CauseRunLengthSnapshot:
        if set(self.run_length_posterior_by_cause) != set(ChangeCause):
            raise ValueError("run-length posterior must cover every change cause")
        if set(self.changepoint_probability_by_cause) != set(ChangeCause):
            raise ValueError("changepoint posterior must cover every change cause")
        for cause, posterior in self.run_length_posterior_by_cause.items():
            if not posterior or not isclose(
                sum(posterior.values()), 1.0, rel_tol=0.0, abs_tol=1e-6
            ):
                raise ValueError(f"run-length posterior for {cause.value} must sum to one")
            if not isclose(
                posterior.get(0, 0.0),
                self.changepoint_probability_by_cause[cause],
                rel_tol=0.0,
                abs_tol=1e-6,
            ):
                raise ValueError("changepoint probability must equal run-length-zero mass")
        return self


class CauseFactorizedBOCPDResult(ContractModel):
    snapshots: tuple[CauseRunLengthSnapshot, ...] = Field(min_length=1)
    detected_change_time_by_cause: dict[ChangeCause, datetime | None]
    peak_changepoint_probability_by_cause: dict[ChangeCause, Probability]
    model_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_result(self) -> CauseFactorizedBOCPDResult:
        if set(self.detected_change_time_by_cause) != set(ChangeCause):
            raise ValueError("detected times must cover every change cause")
        if set(self.peak_changepoint_probability_by_cause) != set(ChangeCause):
            raise ValueError("peak probabilities must cover every change cause")
        timestamps = {snapshot.timestamp for snapshot in self.snapshots}
        if any(
            timestamp is not None and timestamp not in timestamps
            for timestamp in self.detected_change_time_by_cause.values()
        ):
            raise ValueError("detected change times must come from a posterior snapshot")
        return self


class CauseFactorizedBOCPD:
    """Independent BOCPD filters over explicit causal diagnostic channels."""

    def __init__(
        self,
        *,
        hazard_probability: float | dict[ChangeCause, float] = 0.05,
        maximum_run_length: int = 256,
        model_version: str = "cause-factorized-bocpd@0.1",
    ) -> None:
        if maximum_run_length < 1:
            raise ValueError("maximum_run_length must be positive")
        if isinstance(hazard_probability, dict):
            if set(hazard_probability) != set(ChangeCause):
                raise ValueError("hazard mapping must cover every change cause")
            hazards = dict(hazard_probability)
        else:
            hazards = {cause: float(hazard_probability) for cause in ChangeCause}
        if any(not 0.0 < hazard < 1.0 for hazard in hazards.values()):
            raise ValueError("every BOCPD hazard must lie in (0, 1)")
        self._hazards = hazards
        self._maximum_run_length = maximum_run_length
        self._model_version = model_version
        self.reset()

    def reset(self) -> None:
        self._posterior = {cause: {0: 1.0} for cause in ChangeCause}

    def update(self, frame: CauseEvidenceFrame) -> CauseRunLengthSnapshot:
        updated: dict[ChangeCause, dict[int, float]] = {}
        changepoint: dict[ChangeCause, float] = {}
        for cause in ChangeCause:
            previous = self._posterior[cause]
            hazard = self._hazards[cause]
            cp_likelihood = frame.changepoint_likelihoods[cause]
            continuation_likelihood = frame.continuation_likelihoods[cause]
            next_posterior: dict[int, float] = {0: sum(previous.values()) * hazard * cp_likelihood}
            for run_length, probability in previous.items():
                next_length = min(run_length + 1, self._maximum_run_length)
                next_posterior[next_length] = next_posterior.get(next_length, 0.0) + (
                    probability * (1.0 - hazard) * continuation_likelihood
                )
            total = sum(next_posterior.values())
            if total <= 0.0:
                raise ValueError("BOCPD update produced zero posterior mass")
            normalized = {
                run_length: probability / total
                for run_length, probability in next_posterior.items()
            }
            updated[cause] = normalized
            changepoint[cause] = normalized[0]
        self._posterior = updated
        return CauseRunLengthSnapshot(
            timestamp=frame.timestamp,
            run_length_posterior_by_cause=updated,
            changepoint_probability_by_cause=changepoint,
            evidence_record_ids=frame.evidence_record_ids,
        )

    def run(
        self,
        frames: tuple[CauseEvidenceFrame, ...],
        *,
        detection_threshold: float = 0.5,
        minimum_observations: int = 2,
    ) -> CauseFactorizedBOCPDResult:
        if not frames:
            raise ValueError("CF-BOCPD requires at least one evidence frame")
        if not 0.0 <= detection_threshold <= 1.0:
            raise ValueError("detection_threshold must lie in [0, 1]")
        if minimum_observations < 1:
            raise ValueError("minimum_observations must be positive")
        if minimum_observations > len(frames):
            raise ValueError("minimum_observations cannot exceed the evidence-frame count")
        timestamps = [frame.timestamp for frame in frames]
        if timestamps != sorted(timestamps) or len(timestamps) != len(set(timestamps)):
            raise ValueError("CF-BOCPD frames must have unique increasing timestamps")

        self.reset()
        snapshots = tuple(self.update(frame) for frame in frames)
        detected: dict[ChangeCause, datetime | None] = {}
        peak: dict[ChangeCause, float] = {}
        for cause in ChangeCause:
            eligible = snapshots[minimum_observations - 1 :]
            detected[cause] = next(
                (
                    snapshot.timestamp
                    for snapshot in eligible
                    if snapshot.changepoint_probability_by_cause[cause] >= detection_threshold
                ),
                None,
            )
            peak[cause] = max(
                snapshot.changepoint_probability_by_cause[cause] for snapshot in eligible
            )
        return CauseFactorizedBOCPDResult(
            snapshots=snapshots,
            detected_change_time_by_cause=detected,
            peak_changepoint_probability_by_cause=peak,
            model_version=self._model_version,
        )
