"""Three-dimensional development errors conditional on correct seed association.

Fitting accepts related seeds, not independent calibration samples. Restoring a
checkpoint authenticates its retained external pin, not the claimed training
history. Public observations contain no object identity or private position.
This arithmetic helper cannot grant natural-world identity or publication rights.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import fields
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

import numpy as np

from cpswm.system.reproducibility import canonical_json, content_sha256
from cpswm.system.structure_two_conditional_updates import ConditionalMeasurement

if TYPE_CHECKING:
    from cpswm.system.structure_two_particle_workspace import ConditionalAnalyticState

ESTIMATORS = ("soft_affinity", "uniform")
REFERENCES = ("sdk_transform_position_m", "sdk_aabb_center_m")
SCHEMA = "empirical-position-residual-development@1"
SCOPE = "UNCALIBRATED_DEVELOPMENT_POSITION_GIVEN_CORRECT_SEED_ASSOCIATION"
CONFIG = {
    "residual_dimension": 3,
    "state_dimension": 6,
    "minimum_rows": 4,
    "covariance_ddof": 1,
    "covariance": "full_without_noise_floor",
    "sampling": "equal_weight_eligible_unique_public_measurements",
    "information_weight": 1.0,
}
H = ((1.0, 0.0, 0.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0, 0.0, 0.0), (0.0, 0.0, 1.0, 0.0, 0.0, 0.0))


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _keys(value: Any, expected: set[str], name: str) -> None:
    _require(
        type(value) is dict and all(type(key) is str for key in value) and set(value) == expected,
        f"invalid {name} fields",
    )


def _digest(value: Any) -> None:
    _require(
        type(value) is str and re.fullmatch("[0-9a-f]{64}", value) is not None,
        "lowercase SHA256 required",
    )


def _text(value: Any, name: str) -> None:
    _require(type(value) is str and bool(value) and value == value.strip(), f"invalid {name}")


def _definition(estimator: Any, reference_kind: Any, domain_id: Any, estimator_pin: Any) -> None:
    _require(type(estimator) is str and estimator in ESTIMATORS, "invalid estimator")
    _require(type(reference_kind) is str and reference_kind in REFERENCES, "invalid reference kind")
    _text(domain_id, "measurement domain")
    _digest(estimator_pin)


def _vector(value: Any, size: int, name: str, *, strict_float: bool = True) -> np.ndarray:
    _require(
        type(value) is list if strict_float else type(value) in (list, tuple),
        f"invalid {name} vector",
    )
    _require(
        len(value) == size
        and all(type(v) is float if strict_float else type(v) in (int, float) for v in value),
        f"invalid {name} vector",
    )
    try:
        result = np.asarray(value, dtype=np.float64)
    except (ValueError, TypeError, OverflowError) as error:
        raise ValueError(f"invalid {name} vector") from error
    _require(bool(np.isfinite(result).all()), f"nonfinite {name}")
    return result


def _matrix(value: Any, size: int, name: str, *, strict_float: bool = True) -> np.ndarray:
    _require(
        (type(value) is list if strict_float else type(value) in (list, tuple))
        and len(value) == size,
        f"invalid {name} matrix",
    )
    result = np.stack([_vector(row, size, name, strict_float=strict_float) for row in value])
    _require(np.array_equal(result, result.T), f"{name} must be exactly symmetric")
    try:
        np.linalg.cholesky(result)
    except np.linalg.LinAlgError as error:
        raise ValueError(f"{name} must be positive definite; no noise floor") from error
    return result


def _array_sha256(value: np.ndarray) -> str:
    return content_sha256(
        dict(
            dtype=value.dtype.str,
            shape=list(value.shape),
            bytes_sha256=hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest(),
        )
    )


def _members(members: Any, n: int) -> tuple[dict[str, int], dict[str, str]]:
    _require(type(members) is list and len(members) == n, "members must match residual rows")
    keys = {
        "measurement_id",
        "house_index",
        "frame_sha256",
        "object_sha256",
        "input_sha256",
        "label_sha256",
        "split",
    }
    identities: dict[str, set[Any]] = {
        key: set()
        for key in (
            "measurements",
            "frames",
            "object_frames",
            "objects",
            "houses",
            "inputs",
            "labels",
        )
    }
    frame_bindings: dict[str, tuple[int, str]] = {}
    object_bindings: dict[str, int] = {}
    for row in members:
        _keys(row, keys, "training member")
        _require(type(row["split"]) is str and row["split"] == "train", "member is not train")
        house = row["house_index"]
        _require(
            type(house) is int and 1 <= house <= 8, "member house is outside fixed train split"
        )
        for name in (
            "measurement_id",
            "frame_sha256",
            "object_sha256",
            "input_sha256",
            "label_sha256",
        ):
            _digest(row[name])
        _require(
            row["measurement_id"] not in identities["measurements"],
            "repeated public measurement identity",
        )
        frame, obj = row["frame_sha256"], row["object_sha256"]
        binding = (house, row["input_sha256"])
        _require(
            frame_bindings.setdefault(frame, binding) == binding, "frame crosses house or input"
        )
        _require(object_bindings.setdefault(obj, house) == house, "object identity crosses house")
        for key, value in dict(
            measurements=row["measurement_id"],
            frames=frame,
            object_frames=content_sha256([frame, obj]),
            objects=obj,
            houses=house,
            inputs=row["input_sha256"],
            labels=row["label_sha256"],
        ).items():
            identities[key].add(value)
    denominators = {
        "seed_rows": n,
        **{key: len(identities[key]) for key in ("frames", "object_frames", "objects", "houses")},
    }
    return denominators, {key: content_sha256(sorted(value)) for key, value in identities.items()}


def fit(
    residuals: np.ndarray,
    members: list[dict[str, Any]],
    *,
    estimator: str,
    reference_kind: str,
    domain_id: str,
    estimator_pin: str,
    partition: str = "train",
) -> dict[str, Any]:
    """Fixed ddof=1 moments of signed world-metre residuals, without IID claims.

    The caller must reconstruct residuals and claimed member identities from
    pinned public readouts and eligible offline labels; hashes alone cannot do so.
    """
    _require(type(partition) is str and partition == "train", "fit accepts only train")
    _definition(estimator, reference_kind, domain_id, estimator_pin)
    _require(
        type(residuals) is np.ndarray
        and residuals.dtype in (np.dtype("float32"), np.dtype("float64"))
        and residuals.ndim == 2
        and residuals.shape[1] == 3
        and len(residuals) >= 4
        and bool(np.isfinite(residuals).all()),
        "at least four finite Nx3 float residuals required",
    )
    denominators, identities = _members(members, len(residuals))
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            values = residuals.astype(np.float64, copy=True)
            bias = values.mean(axis=0)
            centered = values - bias
            rank = int(np.linalg.matrix_rank(centered))
            _require(rank == 3, "residual rank below three; no covariance fabricated")
            covariance = centered.T @ centered / (len(values) - 1)
    except (FloatingPointError, np.linalg.LinAlgError) as error:
        raise ValueError("residual fit numerical failure") from error
    model = dict(
        schema=SCHEMA,
        scope=SCOPE,
        estimator=estimator,
        reference_kind=reference_kind,
        domain_id=domain_id,
        estimator_pin=estimator_pin,
        config=dict(CONFIG),
        bias=bias.tolist(),
        covariance=covariance.tolist(),
        residual_rank=rank,
        training=dict(
            partition="train",
            residuals_sha256=_array_sha256(residuals),
            members_sha256=content_sha256(members),
            denominators=denominators,
            identity_sha256=identities,
        ),
        independent_samples_assumed=False,
        calibrated=False,
        runtime_authority=False,
        natural_world_identity_authority=False,
    )
    _parameters(model)
    return model


def _parameters(model: Any) -> tuple[np.ndarray, np.ndarray]:
    _keys(
        model,
        {
            "schema",
            "scope",
            "estimator",
            "reference_kind",
            "domain_id",
            "estimator_pin",
            "config",
            "bias",
            "covariance",
            "residual_rank",
            "training",
            "independent_samples_assumed",
            "calibrated",
            "runtime_authority",
            "natural_world_identity_authority",
        },
        "position checkpoint",
    )
    _definition(
        model["estimator"], model["reference_kind"], model["domain_id"], model["estimator_pin"]
    )
    _require(
        type(model["schema"]) is str
        and model["schema"] == SCHEMA
        and type(model["scope"]) is str
        and model["scope"] == SCOPE
        and type(model["residual_rank"]) is int
        and model["residual_rank"] == 3
        and all(
            model[key] is False
            for key in (
                "independent_samples_assumed",
                "calibrated",
                "runtime_authority",
                "natural_world_identity_authority",
            )
        ),
        "checkpoint definition or authority differs",
    )
    config = model["config"]
    _keys(config, set(CONFIG), "fixed config")
    _require(
        all(type(config[key]) is type(value) for key, value in CONFIG.items())
        and content_sha256(config) == content_sha256(CONFIG),
        "fixed residual config differs",
    )
    training = model["training"]
    _keys(
        training,
        {"partition", "residuals_sha256", "members_sha256", "denominators", "identity_sha256"},
        "training",
    )
    _require(
        type(training["partition"]) is str and training["partition"] == "train",
        "checkpoint is not train",
    )
    _digest(training["residuals_sha256"])
    _digest(training["members_sha256"])
    denominators = training["denominators"]
    _keys(
        denominators, {"seed_rows", "frames", "object_frames", "objects", "houses"}, "denominator"
    )
    _require(
        all(type(value) is int and value > 0 for value in denominators.values())
        and denominators["seed_rows"] >= 4
        and 1 <= denominators["houses"] <= 8
        and denominators["houses"]
        <= denominators["frames"]
        <= denominators["object_frames"]
        <= denominators["seed_rows"]
        and denominators["houses"] <= denominators["objects"] <= denominators["object_frames"],
        "invalid related-seed denominators",
    )
    identities = training["identity_sha256"]
    _keys(
        identities,
        {"measurements", "frames", "object_frames", "objects", "houses", "inputs", "labels"},
        "identity digests",
    )
    for digest in identities.values():
        _digest(digest)
    return _vector(model["bias"], 3, "bias"), _matrix(model["covariance"], 3, "residual covariance")


def checkpoint_sha256(model: dict[str, Any]) -> str:
    _parameters(model)
    return content_sha256(model)


def restore(model: dict[str, Any], externalpin: str) -> dict[str, Any]:
    """Require an external content pin; do not infer authentic fitting from self-signing."""
    _digest(externalpin)
    _require(checkpoint_sha256(model) == externalpin, "external position model pin differs")
    return cast(dict[str, Any], json.loads(canonical_json(model)))


def _time(value: Any) -> datetime:
    _require(type(value) is str, "UTC ISO timestamp required")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError("UTC ISO timestamp required") from error
    _require(
        parsed.tzinfo is not None and parsed.utcoffset() == timedelta(0), "UTC timestamp required"
    )
    return parsed


def _prior(supplied: ConditionalAnalyticState) -> ConditionalAnalyticState:
    from cpswm.system.structure_two_particle_workspace import ConditionalAnalyticState

    _require(
        type(supplied) is ConditionalAnalyticState
        and set(vars(supplied)) == {f.name for f in fields(ConditionalAnalyticState)},
        "invalid conditional prior",
    )
    for name in ("locations", "evidence_cluster_ids"):
        value = getattr(supplied, name)
        _require(
            type(value) in (tuple, list) and all(type(v) is UUID for v in value),
            "invalid prior identities",
        )
    _vector(supplied.alpha, len(supplied.locations), "prior alpha", strict_float=False)
    _require(type(supplied.b) in (tuple, list) and bool(supplied.b), "invalid prior RLS vector")
    _vector(supplied.b, len(supplied.b), "prior RLS natural vector", strict_float=False)
    _matrix(supplied.a, len(supplied.b), "prior RLS precision", strict_float=False)
    _vector(supplied.information_vector, 6, "prior Gaussian natural vector", strict_float=False)
    _matrix(supplied.information, 6, "prior Gaussian precision", strict_float=False)
    return ConditionalAnalyticState(
        locations=tuple(supplied.locations),
        alpha=tuple(supplied.alpha),
        a=tuple(tuple(row) for row in supplied.a),
        b=tuple(supplied.b),
        information=tuple(tuple(row) for row in supplied.information),
        information_vector=tuple(supplied.information_vector),
        evidence_cluster_ids=tuple(supplied.evidence_cluster_ids),
    )


def condition(
    model: dict[str, Any],
    externalpin: str,
    public_observation: dict[str, Any],
    reference: dict[str, Any],
    prior: ConditionalAnalyticState,
    *,
    evidence_cluster_id: UUID,
    source_record_ids: tuple[UUID, ...],
) -> tuple[ConditionalMeasurement, dict[str, Any]]:
    """Score against the pre-update prior; return a position-only measurement.

    Reference is an explicitly associated hypothesis's local origin, never an
    online SDK truth join. Prior provenance and the supplied association must be
    checked by the owning producer; this pure helper cannot authenticate them.
    """
    model = restore(model, externalpin)
    bias, covariance = _parameters(model)
    prior = _prior(prior)
    _require(
        type(evidence_cluster_id) is UUID and evidence_cluster_id not in prior.evidence_cluster_ids,
        "invalid or already consumed evidence cluster",
    )
    _require(
        type(source_record_ids) is tuple
        and bool(source_record_ids)
        and all(type(value) is UUID for value in source_record_ids)
        and len(set(source_record_ids)) == len(source_record_ids),
        "invalid or repeated source records",
    )
    obs = public_observation
    _keys(
        obs,
        {
            "measurement_id",
            "estimator",
            "estimator_pin",
            "domain_id",
            "frame_id",
            "action_id",
            "valid_at",
            "world_point_m",
        },
        "public observation",
    )
    _digest(obs["measurement_id"])
    _text(obs["frame_id"], "observation frame")
    _definition(obs["estimator"], model["reference_kind"], obs["domain_id"], obs["estimator_pin"])
    try:
        _require(
            type(obs["action_id"]) is str and str(UUID(obs["action_id"])) == obs["action_id"],
            "canonical action UUID required",
        )
    except (ValueError, TypeError, AttributeError) as error:
        raise ValueError("canonical action UUID required") from error
    stamp = _time(obs["valid_at"])
    point = _vector(obs["world_point_m"], 3, "world point")
    _keys(
        reference,
        {"reference_id", "reference_kind", "domain_id", "frame_id", "valid_at", "xyz_m"},
        "local hypothesis reference",
    )
    _digest(reference["reference_id"])
    _text(reference["frame_id"], "reference frame")
    xyz = _vector(reference["xyz_m"], 3, "reference translation")
    _require(
        all(
            type(reference[key]) is str and reference[key] == model[key]
            for key in ("reference_kind", "domain_id")
        )
        and all(obs[key] == model[key] for key in ("estimator", "estimator_pin", "domain_id"))
        and reference["frame_id"] == obs["frame_id"]
        and _time(reference["valid_at"]) == stamp,
        "observation/reference outside fitted estimator, domain, frame or epoch",
    )
    h = np.asarray(H)
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            z = point - xyz - bias
            precision = np.asarray(prior.information, dtype=np.float64)
            mu = np.linalg.solve(precision, np.asarray(prior.information_vector, dtype=np.float64))
            projected = h @ np.linalg.solve(precision, h.T)
            # Symmetry is mathematical; averaging only cancels solve roundoff.
            s = (projected / 2 + projected.T / 2) + covariance
            chol = np.linalg.cholesky(s)
            innovation = z - h @ mu
            whitened = np.linalg.solve(chol, innovation)
            mahalanobis = float(whitened @ whitened)
            logdet = float(2 * np.log(np.diag(chol)).sum())
            logpdf = float(-0.5 * (3 * math.log(2 * math.pi) + logdet + mahalanobis))
    except (FloatingPointError, np.linalg.LinAlgError) as error:
        raise ValueError("predictive Gaussian numerical failure") from error
    _require(
        all(bool(np.isfinite(v).all()) for v in (z, mu, s, innovation))
        and all(math.isfinite(v) for v in (mahalanobis, logdet, logpdf)),
        "nonfinite predictive Gaussian",
    )
    measurement = ConditionalMeasurement(
        evidence_cluster_id=evidence_cluster_id,
        source_record_ids=tuple(source_record_ids),
        observation_model_id=SCHEMA + ":" + externalpin,
        location_mass=(0.0,) * len(prior.alpha),
        rls_features=(0.0,) * len(prior.b),
        rls_target=0.0,
        rls_weight=0.0,
        measurement=tuple(z.tolist()),
        observation_matrix=H,
        noise_covariance=tuple(tuple(row) for row in covariance.tolist()),
        information_weight=1.0,
    )
    diagnostic = dict(
        schema="position-predictive-development@1",
        scope=SCOPE,
        model_sha256=externalpin,
        prior_sha256=content_sha256(prior),
        public_observation_sha256=content_sha256(obs),
        reference_sha256=content_sha256(reference),
        evidence_cluster_id=str(evidence_cluster_id),
        source_record_ids=[str(v) for v in source_record_ids],
        local_measurement=z.tolist(),
        prior_mean=mu.tolist(),
        innovation=innovation.tolist(),
        predictive_covariance=s.tolist(),
        log_determinant=logdet,
        squared_mahalanobis=mahalanobis,
        observation_log_likelihood=logpdf,
        information_weight=1.0,
        association_assumption="seed_correctly_associated_by_controlled_hypothesis",
        calibrated=False,
        runtime_authority=False,
        natural_world_identity_authority=False,
    )
    return measurement, json.loads(canonical_json(diagnostic))
