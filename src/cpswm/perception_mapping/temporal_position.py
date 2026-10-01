"""Explicit shared-bias Gaussian development model for a static target sequence.

R is the one-frame marginal covariance, rho*R is a sequence-shared bias.
Conditional innovations exactly factor the declared joint likelihood. This
identity is not empirical calibration or evidence that a tracked surface is a
static object centre. The owner authenticates raw inputs and association.
"""

from __future__ import annotations

from dataclasses import replace
from math import log, pi
from typing import Any
from uuid import UUID

import numpy as np
from numpy.typing import NDArray

from cpswm.perception_mapping import position_observation_model as position
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_conditional_updates import ConditionalMeasurement
from cpswm.system.structure_two_particle_workspace import ConditionalAnalyticState

MODEL = "static-target-shared-bias-development@1"


def covariance(n: int, marginal: Any, rho: float) -> NDArray[np.float64]:
    if type(n) is not int or n < 1 or type(rho) is not float or not 0 <= rho < 1:
        raise ValueError("positive count and explicit finite shared fraction in [0,1) required")
    r = np.asarray(marginal, dtype=float)
    if r.shape != (3, 3) or not np.isfinite(r).all() or not np.array_equal(r, r.T):
        raise ValueError("finite symmetric 3D covariance required")
    np.linalg.cholesky(r)
    return np.asarray(np.kron(rho * np.ones((n, n)) + (1 - rho) * np.eye(n), r), dtype=np.float64)


def logpdf(y: NDArray[np.float64], mean: NDArray[np.float64], cov: NDArray[np.float64]) -> float:
    c = np.linalg.cholesky((cov + cov.T) / 2)
    v = np.linalg.solve(c, y - mean)
    return float(-0.5 * (len(y) * log(2 * pi) + 2 * np.log(np.diag(c)).sum() + v @ v))


def innovation(
    values: NDArray[np.float64], marginal: Any, rho: float
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
    """Return y_eff, H_eff, R_eff for p(y_last | theta, y_previous)."""
    values = np.asarray(values, dtype=float)
    if values.ndim != 2 or values.shape[1] != 3 or not np.isfinite(values).all():
        raise ValueError("finite Nx3 observations required")
    n = len(values)
    c = covariance(n, marginal, rho)
    h = np.asarray(position.H)
    if n == 1:
        return values[0], h, c
    k = np.linalg.solve(c[:-3, :-3], c[:-3, -3:]).T
    r = c[-3:, -3:] - k @ c[:-3, -3:]
    return values[-1] - k @ values[:-1].ravel(), h - k @ np.tile(h, (n - 1, 1)), (r + r.T) / 2


def condition(
    model: dict[str, Any],
    pin: str,
    observations: list[dict[str, Any]],
    prior: ConditionalAnalyticState,
    *,
    rho: float,
    evidence_cluster_id: UUID,
    source_record_ids: tuple[UUID, ...],
) -> tuple[ConditionalMeasurement, dict[str, Any]]:
    if not observations or len({o["measurement_id"] for o in observations}) != len(observations):
        raise ValueError("nonempty unique measurement prefix required")
    # Apply the existing complete schema/domain/pin validation to every member.
    measure = None
    for obs in observations:
        reference = dict(
            reference_id=content_sha256((MODEL, "controlled-origin-zero", pin)),
            reference_kind=model["reference_kind"],
            domain_id=obs["domain_id"],
            frame_id=obs["frame_id"],
            valid_at=obs["valid_at"],
            xyz_m=[0.0, 0.0, 0.0],
        )
        measure, _ = position.condition(
            model,
            pin,
            obs,
            reference,
            prior,
            evidence_cluster_id=evidence_cluster_id,
            source_record_ids=source_record_ids,
        )
    values = np.asarray([o["world_point_m"] for o in observations]) - np.asarray(model["bias"])
    z, h, r = innovation(values, model["covariance"], rho)
    j = np.asarray(prior.information)
    mu = np.linalg.solve(j, prior.information_vector)
    likelihood = logpdf(z, h @ mu, r + h @ np.linalg.solve(j, h.T))

    # A single persistent broad latent position is used for the background too.
    # Its likelihood is conditioned on the same prefix, not restarted per frame.
    def background(v: NDArray[np.float64]) -> float:
        if not len(v):
            return 0.0
        c = covariance(len(v), model["covariance"], rho) + np.kron(
            np.ones((len(v), len(v))), 100 * np.eye(3)
        )
        return logpdf(v.ravel(), np.zeros(v.size), c)

    bg = background(values) - background(values[:-1])
    assert measure is not None
    result = replace(
        measure,
        measurement=tuple(z.tolist()),
        observation_matrix=tuple(map(tuple, h.tolist())),
        noise_covariance=tuple(map(tuple, r.tolist())),
        observation_model_id=MODEL + ":" + content_sha256((pin, rho)),
    )
    return result, dict(
        model=MODEL,
        shared_fraction=rho,
        prefix_length=len(values),
        observation_log_likelihood=likelihood,
        background_log_likelihood=bg,
        log_ratio=likelihood - bg,
        conditional_measurement=z.tolist(),
        observation_matrix=h.tolist(),
        noise_covariance=r.tolist(),
        calibrated=False,
    )
