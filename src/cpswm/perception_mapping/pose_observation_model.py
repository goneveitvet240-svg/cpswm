"""Empirical local-pose measurement model and reversible conditional consumption.

The input is a pose estimator's measurement, never a location UUID converted to
a pose. Independent labels are used only in fitting/evaluation. This module does
not supply a pixel pose estimator, authenticate labels, select a scientific
calibration threshold, or authorize a long-term memory write.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from math import log, pi
from typing import TYPE_CHECKING
from uuid import UUID

import numpy as np
from numpy.typing import NDArray

from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_conditional_updates import (
    ConditionalMeasurement,
    rebuild_conditional_state,
)
from cpswm.system.structure_two_pose import PoseState, pose_residual

if TYPE_CHECKING:
    from cpswm.system.structure_two_particle_workspace import ConditionalAnalyticState


def _digest(value: str) -> None:
    if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("SHA256 required")


def _chart(reference: PoseState) -> tuple[str, tuple[float, ...]]:
    # Revalidate externally mutated Pydantic instances; q and -q name one chart.
    reference = PoseState.model_validate(reference.model_dump())
    p = reference.pose
    q = np.asarray((p.qx, p.qy, p.qz, p.qw), dtype=float)
    q = q / np.linalg.norm(q)
    if next(x for x in q if x != 0) < 0:
        q = -q
    return p.frame_id, tuple(float(x) for x in q)


@dataclass(frozen=True)
class PoseObservation:
    source_record_id: UUID
    input_sha256: str
    sequence_id: str
    estimator_id: str
    calibration_domain: str
    reference: PoseState
    observed: PoseState

    def residual(self) -> tuple[float, ...]:
        _digest(self.input_sha256)
        if not isinstance(self.source_record_id, UUID) or not all(
            s.strip() for s in (self.sequence_id, self.estimator_id, self.calibration_domain)
        ):
            raise ValueError("pose input requires source, sequence, estimator and domain")
        return pose_residual(self.reference, self.observed)


@dataclass(frozen=True)
class PoseLabel:
    observation: PoseObservation
    truth: PoseState
    annotation_sha256: str
    annotation_source: str

    def error(self) -> NDArray[np.float64]:
        _digest(self.annotation_sha256)
        if self.annotation_source not in {"independent_annotation", "dataset_annotation"}:
            raise ValueError("pose calibration requires independently supplied labels")
        observed = np.asarray(self.observation.residual())
        truth = np.asarray(pose_residual(self.observation.reference, self.truth))
        with np.errstate(over="ignore", invalid="ignore"):
            error = np.asarray(observed - truth, dtype=np.float64)
        if not np.isfinite(error).all():
            raise ValueError("pose calibration residual overflow")
        return error


def _validated_rows(rows: tuple[PoseLabel, ...]) -> tuple[PoseLabel, ...]:
    result = deepcopy(tuple(rows))
    if not result:
        raise ValueError("nonempty pose calibration data required")
    ids, hashes = set(), set()
    first = result[0].observation
    for item in result:
        item.error()
        observation = item.observation
        if observation.source_record_id in ids or observation.input_sha256 in hashes:
            raise ValueError("repeated pose input cannot count as another calibration sample")
        ids.add(observation.source_record_id)
        hashes.add(observation.input_sha256)
        if (
            observation.estimator_id != first.estimator_id
            or observation.calibration_domain != first.calibration_domain
            or _chart(observation.reference) != _chart(first.reference)
        ):
            raise ValueError("calibration rows cross estimator, domain or local chart")
    return result


@dataclass(frozen=True)
class GaussianPoseObservationModel:
    """z = local_pose + bias + error, with fitted full 6x6 residual covariance.

    This local additive error model must be assessed on held-out sequences. It
    cannot represent symmetric/multimodal orientation or extrapolate to a new
    chart/domain. No diagonal noise, epsilon floor, or pseudo-label is supplied.
    """

    estimator_id: str
    calibration_domain: str
    chart: tuple[str, tuple[float, ...]]
    bias: tuple[float, ...]
    covariance: tuple[tuple[float, ...], ...]
    fit_record_ids: tuple[UUID, ...]
    fit_input_sha256s: tuple[str, ...]
    fit_sequences: tuple[str, ...]
    fit_annotation_sha256s: tuple[str, ...]

    @classmethod
    def fit(cls, supplied: tuple[PoseLabel, ...]) -> GaussianPoseObservationModel:
        rows = _validated_rows(supplied)
        if len(rows) < 7:
            raise ValueError("full six-dimensional covariance needs at least seven samples")
        errors = np.stack([x.error() for x in rows])
        with np.errstate(over="ignore", invalid="ignore"):
            bias = errors.mean(axis=0)
            covariance = np.cov(errors, rowvar=False, ddof=1)
        if not np.isfinite(bias).all() or not np.isfinite(covariance).all():
            raise ValueError("pose error estimation overflow")
        if np.linalg.matrix_rank(errors - bias) < 6:
            raise ValueError("pose residuals do not identify full covariance; no noise fabricated")
        first = rows[0].observation
        result = cls(
            first.estimator_id,
            first.calibration_domain,
            _chart(first.reference),
            tuple(map(float, bias)),
            tuple(tuple(map(float, row)) for row in covariance),
            tuple(x.observation.source_record_id for x in rows),
            tuple(x.observation.input_sha256 for x in rows),
            tuple(sorted({x.observation.sequence_id for x in rows})),
            tuple(x.annotation_sha256 for x in rows),
        )
        result._parameters()
        return result

    def _parameters(self) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
        bias, covariance = np.asarray(self.bias), np.asarray(self.covariance)
        if (
            bias.shape != (6,)
            or covariance.shape != (6, 6)
            or not np.isfinite(bias).all()
            or not np.isfinite(covariance).all()
            or not np.array_equal(covariance, covariance.T)
        ):
            raise ValueError("invalid fitted pose model")
        try:
            np.linalg.cholesky(covariance)
        except np.linalg.LinAlgError as error:
            raise ValueError("pose covariance must be positive definite") from error
        return bias, covariance

    @property
    def model_id(self) -> str:
        self._parameters()
        return "empirical-local-pose@1:" + content_sha256(self)

    def measurement(self, supplied: PoseObservation) -> tuple[float, ...]:
        observation = deepcopy(supplied)
        residual = np.asarray(observation.residual())
        if (
            observation.estimator_id != self.estimator_id
            or observation.calibration_domain != self.calibration_domain
            or _chart(observation.reference) != self.chart
        ):
            raise ValueError("observation outside fitted estimator, domain or pose chart")
        bias, _ = self._parameters()
        corrected = residual - bias
        if not np.isfinite(corrected).all() or np.linalg.norm(corrected[3:]) >= pi:
            raise ValueError("bias-corrected pose outside local chart")
        return tuple(map(float, corrected))

    def evaluate(self, supplied: tuple[PoseLabel, ...]) -> dict[str, object]:
        rows = _validated_rows(supplied)
        if (
            set(self.fit_record_ids) & {x.observation.source_record_id for x in rows}
            or set(self.fit_input_sha256s) & {x.observation.input_sha256 for x in rows}
            or set(self.fit_sequences) & {x.observation.sequence_id for x in rows}
        ):
            raise ValueError("pose evaluation must use held-out sequences and inputs")
        try:
            with np.errstate(over="raise", invalid="raise", divide="raise"):
                errors = np.stack(
                    [
                        np.asarray(self.measurement(x.observation))
                        - np.asarray(pose_residual(x.observation.reference, x.truth))
                        for x in rows
                    ]
                )
                _, covariance = self._parameters()
                mahalanobis = np.sum(errors * np.linalg.solve(covariance, errors.T).T, axis=1)
                _, logdet = np.linalg.slogdet(covariance)
                nll = 0.5 * (6 * log(2 * pi) + logdet + mahalanobis)
                values = {
                    "mean_nll": float(nll.mean()),
                    "mean_squared_mahalanobis": float(mahalanobis.mean()),
                    "position_rmse_m": float(np.sqrt(np.mean(errors[:, :3] ** 2))),
                    "orientation_chart_rmse_rad": float(np.sqrt(np.mean(errors[:, 3:] ** 2))),
                }
        except FloatingPointError as error:
            raise ValueError("pose evaluation overflow") from error
        if not all(np.isfinite(value) for value in values.values()):
            raise ValueError("pose evaluation has nonfinite metrics")
        return {
            "model_id": self.model_id,
            "samples": len(rows),
            "sequences": len({x.observation.sequence_id for x in rows}),
            **values,
            "evaluation_sha256": content_sha256(rows),
            "source_authentication_verified": False,
            "scientific_acceptance": "NOT_DECIDED",
        }


@dataclass(frozen=True)
class ConditionalContribution:
    """Other RB-block terms from the particle's configured observation model.

    Do not derive these from Gaussian pose confidence or use uncalibrated detector
    confidence as responsibility. Zero blocks remain zero. Their provenance is
    separate from pose error calibration.
    """

    model_id: str
    source_record_ids: tuple[UUID, ...]
    location_mass: tuple[float, ...]
    rls_features: tuple[float, ...]
    rls_target: float
    rls_weight: float
    pose_information_weight: float


@dataclass(frozen=True)
class ConditionalPoseInput:
    evidence_cluster_id: UUID
    observation: PoseObservation
    contribution: ConditionalContribution


class PoseConditionalHistory:
    """One particle/epoch's retained measurements, rebuilt on correction/retraction.

    Output is the existing ConditionalAnalyticState consumed by native prepared
    particles. This object owns no core ledger and never grants RGRC authority.
    New epochs require a dynamics model; changing a reference requires rebuilding
    all observations, their calibration and the prior in the new chart.
    """

    def __init__(
        self,
        *,
        model: GaussianPoseObservationModel,
        reference: PoseState,
        prior: ConditionalAnalyticState,
    ) -> None:
        self._model = deepcopy(model)
        self._model._parameters()
        self._reference = PoseState.model_validate(reference.model_dump())
        if _chart(reference) != model.chart or len(prior.information_vector) != 6:
            raise ValueError("prior must use the model's six-dimensional pose chart")
        self._prior = rebuild_conditional_state(prior, ())
        self._inputs: dict[UUID, ConditionalPoseInput] = {}
        self._state = self._prior

    def _rebuild(self, values: dict[UUID, ConditionalPoseInput]) -> ConditionalAnalyticState:
        measurements = []
        seen: set[UUID] = set()
        pixels: set[str] = set()
        for key, item in values.items():
            # Compare physical references, including UTC epochs and quaternion
            # sign equivalence, using the same geometry as the measurement.
            reference_delta = pose_residual(self._reference, item.observation.reference)
            if any(x != 0 for x in reference_delta):
                raise ValueError("retained pose input changed reference, object or epoch")
            c = item.contribution
            if not c.model_id.strip() or not c.source_record_ids:
                raise ValueError("conditional terms require their own model and sources")
            if len(set(c.source_record_ids)) != len(c.source_record_ids):
                raise ValueError("duplicate conditional source")
            sources = set(c.source_record_ids) | {item.observation.source_record_id}
            if seen & sources or item.observation.input_sha256 in pixels:
                raise ValueError("one observation cannot be counted in multiple evidence clusters")
            seen.update(sources)
            pixels.add(item.observation.input_sha256)
            measurements.append(
                ConditionalMeasurement(
                    key,
                    tuple(sorted(sources, key=str)),
                    self._model.model_id + "/conditional:" + c.model_id,
                    c.location_mass,
                    c.rls_features,
                    c.rls_target,
                    c.rls_weight,
                    self._model.measurement(item.observation),
                    tuple(tuple(float(i == j) for j in range(6)) for i in range(6)),
                    self._model.covariance,
                    c.pose_information_weight,
                )
            )
        return rebuild_conditional_state(self._prior, tuple(measurements))

    def upsert(self, supplied: ConditionalPoseInput) -> ConditionalAnalyticState:
        item = deepcopy(supplied)
        values = {**self._inputs, item.evidence_cluster_id: item}
        state = self._rebuild(values)
        self._inputs, self._state = values, state
        return self.state

    def retract(self, evidence_cluster_id: UUID) -> ConditionalAnalyticState:
        if evidence_cluster_id not in self._inputs:
            raise ValueError("cannot retract a pose cluster absent from retained history")
        values = {k: v for k, v in self._inputs.items() if k != evidence_cluster_id}
        state = self._rebuild(values)
        self._inputs, self._state = values, state
        return self.state

    @property
    def state(self) -> ConditionalAnalyticState:
        return deepcopy(self._state)

    @property
    def retained_inputs(self) -> tuple[ConditionalPoseInput, ...]:
        return deepcopy(tuple(self._inputs.values()))
