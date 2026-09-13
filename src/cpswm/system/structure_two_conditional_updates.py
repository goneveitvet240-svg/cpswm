"""Pure per-particle analytic updates, not a second long-term commit authority.

Measurements and priors must come from a bound observation model. This module
does not infer continuous measurements from location UUIDs, choose a noise
model, or grant RGRC eligibility. Removal rebuilds from the retained inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import TYPE_CHECKING
from uuid import UUID

import numpy as np
from numpy.typing import NDArray

if TYPE_CHECKING:
    from cpswm.system.structure_two_particle_workspace import ConditionalAnalyticState


def _vector(value: tuple[float, ...], size: int, name: str) -> NDArray[np.float64]:
    result = np.asarray(value, dtype=float)
    if result.shape != (size,) or not np.isfinite(result).all():
        raise ValueError(f"invalid {name}")
    return result


@dataclass(frozen=True)
class ConditionalMeasurement:
    """A model-bound observation's three contributions; zero blocks are explicit.

    Linear Gaussian observation: z = H theta + epsilon, epsilon ~ N(0, R).
    ``information_weight`` is explicit, never synthesized to make a block nonzero.
    RLS and Gaussian observation dimensions need not be equal.
    """

    evidence_cluster_id: UUID
    source_record_ids: tuple[UUID, ...]
    observation_model_id: str
    location_mass: tuple[float, ...]
    rls_features: tuple[float, ...]
    rls_target: float
    rls_weight: float
    measurement: tuple[float, ...]
    observation_matrix: tuple[tuple[float, ...], ...]
    noise_covariance: tuple[tuple[float, ...], ...]
    information_weight: float

    def detached(self) -> ConditionalMeasurement:
        # Deeply detach even callers that supplied mutable lists to dataclass fields.
        return ConditionalMeasurement(
            evidence_cluster_id=self.evidence_cluster_id,
            source_record_ids=tuple(self.source_record_ids),
            observation_model_id=self.observation_model_id,
            location_mass=tuple(self.location_mass),
            rls_features=tuple(self.rls_features),
            rls_target=self.rls_target,
            rls_weight=self.rls_weight,
            measurement=tuple(self.measurement),
            observation_matrix=tuple(tuple(row) for row in self.observation_matrix),
            noise_covariance=tuple(tuple(row) for row in self.noise_covariance),
            information_weight=self.information_weight,
        )


def rebuild_conditional_state(
    prior: ConditionalAnalyticState,
    measurements: tuple[ConditionalMeasurement, ...],
) -> ConditionalAnalyticState:
    """Compute all five natural parameters together, with no mutation or forgetting.

    Replay/retraction is performed by passing the retained measurement sequence.
    Duplicate clusters are rejected rather than counted twice. This is arithmetic
    validation, not validation that an observation/model is independently trusted.
    """
    # The existing workspace imports the broad evaluation package. Do not load
    # that dependency while importing this arithmetic module.
    from cpswm.system.structure_two_particle_workspace import ConditionalAnalyticState

    # Revalidate and detach the prior at the public boundary.
    initial = ConditionalAnalyticState(
        locations=tuple(prior.locations),
        alpha=tuple(prior.alpha),
        a=tuple(tuple(row) for row in prior.a),
        b=tuple(prior.b),
        information=tuple(tuple(row) for row in prior.information),
        information_vector=tuple(prior.information_vector),
        evidence_cluster_ids=tuple(prior.evidence_cluster_ids),
    )
    alpha = np.array(initial.alpha, dtype=float)
    a, b = np.array(initial.a, dtype=float), np.array(initial.b, dtype=float)
    precision = np.array(initial.information, dtype=float)
    natural = np.array(initial.information_vector, dtype=float)
    clusters = list(initial.evidence_cluster_ids)
    dim = len(initial.b)
    gaussian_dim = len(initial.information_vector)
    for supplied in measurements:
        item = supplied.detached()
        if (
            not isinstance(item.evidence_cluster_id, UUID)
            or item.evidence_cluster_id in clusters
            or not item.source_record_ids
            or any(not isinstance(key, UUID) for key in item.source_record_ids)
            or len(set(item.source_record_ids)) != len(item.source_record_ids)
            or not item.observation_model_id.strip()
        ):
            raise ValueError("missing source/model or repeated evidence cluster")
        numeric = (item.rls_target, item.rls_weight, item.information_weight)
        if not all(isfinite(v) for v in numeric) or min(numeric[1:]) < 0:
            raise ValueError("invalid conditional observation weight or target")
        mass = _vector(item.location_mass, len(alpha), "location mass")
        if np.any(mass < 0):
            raise ValueError("location contribution must be non-negative")
        x = _vector(item.rls_features, dim, "RLS features")
        z = _vector(item.measurement, len(item.measurement), "measurement")
        h = np.asarray(item.observation_matrix, dtype=float)
        covariance = np.asarray(item.noise_covariance, dtype=float)
        m = len(z)
        if (
            not m
            or h.shape != (m, gaussian_dim)
            or covariance.shape != (m, m)
            or not np.isfinite(h).all()
            or not np.isfinite(covariance).all()
            or not np.array_equal(covariance, covariance.T)
        ):
            raise ValueError("invalid Gaussian observation dimensions or covariance")
        try:
            np.linalg.cholesky(covariance)
            # Solve; do not construct an explicit covariance inverse.
            whitened_h = np.linalg.solve(covariance, h)
            whitened_z = np.linalg.solve(covariance, z)
        except np.linalg.LinAlgError as error:
            raise ValueError("noise covariance must be positive definite") from error
        with np.errstate(over="ignore", invalid="ignore"):
            alpha = alpha + mass
            a = a + item.rls_weight * np.outer(x, x)
            b = b + item.rls_weight * x * item.rls_target
            delta_precision = item.information_weight * (h.T @ whitened_h)
            # Floating roundoff in the solve must not break exact matrix symmetry.
            precision = precision + (delta_precision / 2 + delta_precision.T / 2)
            natural = natural + item.information_weight * (h.T @ whitened_z)
        clusters.append(item.evidence_cluster_id)
    # Constructor rejects overflow/non-PD results before any state is returned.
    return ConditionalAnalyticState(
        locations=initial.locations,
        alpha=tuple(float(v) for v in alpha),
        a=tuple(tuple(float(v) for v in row) for row in a),
        b=tuple(float(v) for v in b),
        information=tuple(tuple(float(v) for v in row) for row in precision),
        information_vector=tuple(float(v) for v in natural),
        evidence_cluster_ids=tuple(clusters),
    )
