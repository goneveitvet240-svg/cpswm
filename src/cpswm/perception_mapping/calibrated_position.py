"""Training-partition Gaussian position prior and residual development model.

Both distributions are in camera coordinates. Group-balanced empirical moments
are fitted without a covariance floor. Fitted does not mean calibrated coverage,
natural identity, or task benefit. Evaluation truth is never an inference input.
"""

from __future__ import annotations

from collections import Counter
from math import cos, radians, sin
from typing import Annotated, Literal, Self

import numpy as np
from pydantic import Field, model_validator

from cpswm.contracts.base import ContractModel
from cpswm.system.reproducibility import content_sha256

Finite = Annotated[float, Field(allow_inf_nan=False)]
Point = tuple[Finite, Finite, Finite]
Matrix = tuple[Point, Point, Point]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Reference = Literal["sdk_aabb_center_m", "sdk_transform_position_m"]
Estimator = Literal["soft_affinity", "uniform", "bare_seed"]


class CameraCoordinates(ContractModel):
    position_m: Point
    yaw_degrees: Finite
    pitch_degrees: Finite

    def rotation(self) -> np.ndarray:
        yaw, pitch = radians(self.yaw_degrees), radians(self.pitch_degrees)
        ry = np.array(((cos(yaw), 0.0, sin(yaw)), (0.0, 1.0, 0.0), (-sin(yaw), 0.0, cos(yaw))))
        rx = np.array(
            ((1.0, 0.0, 0.0), (0.0, cos(pitch), -sin(pitch)), (0.0, sin(pitch), cos(pitch)))
        )
        return np.asarray(ry @ rx, dtype=np.float64)

    def local(self, point: Point) -> np.ndarray:
        return self.rotation().T @ (np.asarray(point) - self.position_m)


class TrainingRow(ContractModel):
    partition: Literal["train"]
    house_index: int = Field(ge=1, le=8, strict=True)
    object_key: str = Field(min_length=1)
    frame_key: str = Field(min_length=1)
    measurement_key: str = Field(min_length=1)
    public_sha256: Digest
    label_sha256: Digest
    readout_sha256: Digest
    camera: CameraCoordinates
    observed_world_m: Point
    reference_world_m: Point


class Gaussian3(ContractModel):
    mean: Point
    covariance: Matrix

    @model_validator(mode="after")
    def positive(self) -> Self:
        c = np.asarray(self.covariance)
        if not np.array_equal(c, c.T):
            raise ValueError("covariance must be symmetric")
        try:
            np.linalg.cholesky(c)
        except np.linalg.LinAlgError as error:
            raise ValueError("rank-deficient covariance; no synthetic floor") from error
        return self


class PositionCalibration(ContractModel):
    schema_id: Literal["camera-position-prior-error-development@1"]
    estimator: Estimator
    reference: Reference
    parent_artifact_sha256: Digest
    training_rows_sha256: Digest
    readout_sha256: Digest
    weighting: Literal["equal-house-object-frame-measurement-population-moments"]
    row_count: int = Field(ge=4)
    house_count: int = Field(ge=1)
    object_count: int = Field(ge=1)
    object_frame_count: int = Field(ge=1)
    prior: Gaussian3
    residual: Gaussian3
    coverage_calibrated: Literal[False] = False
    natural_identity_authority: Literal[False] = False

    @property
    def digest(self) -> str:
        return content_sha256(self.model_dump(mode="json"))


def fit(
    rows: tuple[TrainingRow, ...],
    *,
    estimator: Estimator,
    reference: Reference,
    parent_artifact_sha256: str,
) -> PositionCalibration:
    """Accept training-only rows. Hashes bind their content, not label authority."""
    rows = tuple(TrainingRow.model_validate(r.model_dump()) for r in rows)
    if len(rows) < 4 or len({r.measurement_key for r in rows}) != len(rows):
        raise ValueError("at least four distinct training measurements required")
    rows = tuple(sorted(rows, key=lambda r: r.measurement_key))
    if len({r.readout_sha256 for r in rows}) != 1:
        raise ValueError("training rows mix distinct public readout profiles")
    frame_sources: dict[tuple[int, str], tuple[str, CameraCoordinates]] = {}
    targets: dict[tuple[int, str, str], Point] = {}
    for row in rows:
        frame = row.house_index, row.frame_key
        source = row.public_sha256, row.camera
        if frame_sources.setdefault(frame, source) != source:
            raise ValueError("same frame has conflicting public source or camera")
        target_key = (*frame, row.object_key)
        if targets.setdefault(target_key, row.reference_world_m) != row.reference_world_m:
            raise ValueError("same object-frame has conflicting reference")
    houses = {r.house_index for r in rows}
    objects = {(r.house_index, r.object_key) for r in rows}
    frames = {(r.house_index, r.object_key, r.frame_key) for r in rows}
    objects_per_house = Counter(h for h, _ in objects)
    frames_per_object = Counter((h, o) for h, o, _ in frames)
    rows_per_frame = Counter((r.house_index, r.object_key, r.frame_key) for r in rows)
    weights = np.array(
        [
            1
            / (
                len(houses)
                * objects_per_house[r.house_index]
                * frames_per_object[r.house_index, r.object_key]
                * rows_per_frame[r.house_index, r.object_key, r.frame_key]
            )
            for r in rows
        ]
    )
    target = np.array([r.camera.local(r.reference_world_m) for r in rows])
    observed = np.array([r.camera.local(r.observed_world_m) for r in rows])

    def moments(values: np.ndarray) -> Gaussian3:
        mean = weights @ values
        centred = values - mean
        covariance = (centred * weights[:, None]).T @ centred
        if np.linalg.matrix_rank(covariance) != 3:
            raise ValueError("rank-deficient empirical covariance; no synthetic floor")
        covariance = (covariance + covariance.T) / 2
        return Gaussian3(
            mean=tuple(mean.tolist()), covariance=tuple(map(tuple, covariance.tolist()))
        )

    return PositionCalibration(
        schema_id="camera-position-prior-error-development@1",
        estimator=estimator,
        reference=reference,
        parent_artifact_sha256=parent_artifact_sha256,
        training_rows_sha256=content_sha256([r.model_dump(mode="json") for r in rows]),
        readout_sha256=rows[0].readout_sha256,
        weighting="equal-house-object-frame-measurement-population-moments",
        row_count=len(rows),
        house_count=len(houses),
        object_count=len(objects),
        object_frame_count=len(frames),
        prior=moments(target),
        residual=moments(observed - target),
    )


def restore(model: PositionCalibration, pin: str) -> PositionCalibration:
    model = PositionCalibration.model_validate(model.model_dump())
    if model.digest != pin:
        raise ValueError("position calibration differs from external pin")
    return model


def world_prior(
    model: PositionCalibration,
    pin: str,
    camera: CameraCoordinates,
) -> Gaussian3:
    model = restore(model, pin)
    camera = CameraCoordinates.model_validate(camera.model_dump())
    q = camera.rotation()
    mean = np.asarray(camera.position_m) + q @ model.prior.mean
    cov = q @ np.asarray(model.prior.covariance) @ q.T
    return Gaussian3(
        mean=tuple(mean.tolist()), covariance=tuple(map(tuple, ((cov + cov.T) / 2).tolist()))
    )


def posterior(
    model: PositionCalibration,
    pin: str,
    cameras: tuple[CameraCoordinates, ...],
    observations: tuple[Point, ...],
    *,
    use_prior: bool,
    use_error: bool,
    rho: float,
) -> Gaussian3:
    """Full joint static-position posterior; shared residual bias in camera axes.

    First camera pose sets the exogenous prior. It uses no candidate pixel or target
    label. For old-control arms N(0,I) and zero-bias unit world error are retained.
    Byte-identical input deduplication is the owner's responsibility, not this math.
    """
    model = restore(model, pin)
    if type(use_prior) is not bool or type(use_error) is not bool:
        raise ValueError("calibration arms require explicit booleans")
    cameras = tuple(CameraCoordinates.model_validate(c.model_dump()) for c in cameras)
    if (
        not cameras
        or len(cameras) != len(observations)
        or type(rho) is not float
        or not 0 <= rho < 1
    ):
        raise ValueError("matched nonempty observations and explicit rho in [0,1) required")
    y = np.asarray(observations, dtype=float)
    if y.shape != (len(cameras), 3) or not np.isfinite(y).all():
        raise ValueError("finite three-dimensional observations required")
    prior = (
        world_prior(model, pin, cameras[0])
        if use_prior
        else Gaussian3(
            mean=(0.0, 0.0, 0.0),
            covariance=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        )
    )
    if use_error:
        h = np.vstack([c.rotation().T for c in cameras])
        z = np.concatenate(
            [
                c.rotation().T @ point - model.residual.mean
                for c, point in zip(cameras, y, strict=True)
            ]
        )
        r = np.asarray(model.residual.covariance)
    else:
        h = np.tile(np.eye(3), (len(cameras), 1))
        z = y.ravel()
        r = np.eye(3)
    covariance = np.kron(
        rho * np.ones((len(cameras), len(cameras))) + (1 - rho) * np.eye(len(cameras)), r
    )
    j = np.linalg.inv(np.asarray(prior.covariance))
    b = j @ prior.mean
    precision = j + h.T @ np.linalg.solve(covariance, h)
    natural = b + h.T @ np.linalg.solve(covariance, z)
    cov = np.linalg.inv(precision)
    mean = np.linalg.solve(precision, natural)
    return Gaussian3(
        mean=tuple(mean.tolist()), covariance=tuple(map(tuple, ((cov + cov.T) / 2).tolist()))
    )
