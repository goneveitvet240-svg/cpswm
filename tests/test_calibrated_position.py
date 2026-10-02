"""Independent analytic checks and training/evaluation boundary attacks."""

import numpy as np
import pytest

from cpswm.perception_mapping.calibrated_position import (
    CameraCoordinates,
    Gaussian3,
    TrainingRow,
    fit,
    posterior,
    restore,
    world_prior,
)


def rows():
    rng = np.random.default_rng(702)
    camera = CameraCoordinates(position_m=(2.0, 3.0, 4.0), yaw_degrees=30.0, pitch_degrees=10.0)
    result = []
    for house in (1, 2):
        for obj in range(5):
            point = rng.normal(size=3) + np.array((2.0, 1.0, 3.0))
            error = rng.normal(size=3) * 0.1
            result.append(
                TrainingRow(
                    partition="train",
                    house_index=house,
                    object_key=str(obj),
                    frame_key=f"frame-{house}",
                    measurement_key=f"{house}-{obj}",
                    public_sha256="a" * 64,
                    label_sha256="b" * 64,
                    readout_sha256="d" * 64,
                    camera=camera,
                    observed_world_m=tuple(point + error),
                    reference_world_m=tuple(point),
                )
            )
    return tuple(result)


def fitted(data=None):
    return fit(
        data or rows(),
        estimator="bare_seed",
        reference="sdk_aabb_center_m",
        parent_artifact_sha256="c" * 64,
    )


def test_fit_matches_independent_group_balanced_moments_and_roundtrip():
    data = rows()
    model = fitted(data)
    q = data[0].camera.rotation()
    refs = np.array([q.T @ (np.asarray(r.reference_world_m) - r.camera.position_m) for r in data])
    errors = np.array([q.T @ (np.asarray(r.observed_world_m) - r.reference_world_m) for r in data])
    assert model.prior.mean == pytest.approx(refs.mean(axis=0))
    np.testing.assert_allclose(model.prior.covariance, np.cov(refs, rowvar=False, bias=True))
    np.testing.assert_allclose(model.residual.covariance, np.cov(errors, rowvar=False, bias=True))
    assert restore(type(model).model_validate_json(model.model_dump_json()), model.digest) == model
    assert not model.coverage_calibrated and not model.natural_identity_authority


def test_duplicate_dense_object_frame_does_not_dominate_other_objects():
    data = rows()
    extra = tuple(data[0].model_copy(update={"measurement_key": f"extra-{i}"}) for i in range(50))
    a, b = fitted(data), fitted((*data, *extra))
    np.testing.assert_allclose(a.prior.mean, b.prior.mean, atol=1e-12)
    np.testing.assert_allclose(a.residual.mean, b.residual.mean, atol=1e-12)
    np.testing.assert_allclose(a.residual.covariance, b.residual.covariance, atol=1e-12)


@pytest.mark.parametrize(
    "update",
    [
        {"partition": "validation"},
        {"house_index": 9},
        {"house_index": True},
        {"observed_world_m": (float("nan"), 0.0, 0.0)},
    ],
)
def test_forged_complete_validation_row_cannot_enter_fit(update):
    data = list(rows())
    data[0] = data[0].model_copy(update=update)
    with pytest.raises(ValueError):
        fitted(tuple(data))
    assert fitted().row_count == 10


def test_duplicate_measurement_conflicting_frame_and_rank_deficiency_rejected():
    data = rows()
    with pytest.raises(ValueError, match="distinct"):
        fitted((*data, data[0]))
    with pytest.raises(ValueError, match="conflicting"):
        fitted((data[0].model_copy(update={"public_sha256": "d" * 64}), *data[1:]))
    flat = tuple(r.model_copy(update={"observed_world_m": r.reference_world_m}) for r in data)
    with pytest.raises(ValueError, match="rank-deficient"):
        fitted(flat)


def test_full_joint_posterior_matches_independent_block_matrix():
    model = fitted()
    poses = (
        rows()[0].camera,
        CameraCoordinates(position_m=(2.0, 3.0, 4.0), yaw_degrees=40.0, pitch_degrees=10.0),
    )
    y = np.array(((1.0, 2.0, 3.0), (1.1, 2.2, 2.9)))
    actual = posterior(
        model, model.digest, poses, tuple(map(tuple, y)), use_prior=True, use_error=True, rho=0.5
    )
    p = world_prior(model, model.digest, poses[0])
    h = np.vstack([c.rotation().T for c in poses])
    z = np.concatenate(
        [c.rotation().T @ point - model.residual.mean for c, point in zip(poses, y, strict=True)]
    )
    noise = np.block(
        [
            [np.asarray(model.residual.covariance), 0.5 * np.asarray(model.residual.covariance)],
            [0.5 * np.asarray(model.residual.covariance), np.asarray(model.residual.covariance)],
        ]
    )
    # Covariance-form Kalman update, independent of implementation information form.
    cov = np.asarray(p.covariance)
    gain = np.linalg.solve(h @ cov @ h.T + noise, h @ cov).T
    expected = np.asarray(p.mean) + gain @ (z - h @ p.mean)
    np.testing.assert_allclose(actual.mean, expected, rtol=0, atol=1e-11)
    np.testing.assert_allclose(actual.covariance, cov - gain @ h @ cov, rtol=0, atol=1e-11)


def test_old_control_preserves_zero_prior_shrinkage():
    model = fitted()
    pose = rows()[0].camera
    r = posterior(
        model, model.digest, (pose,), ((2.0, 4.0, 6.0),), use_prior=False, use_error=False, rho=0.5
    )
    assert r.mean == pytest.approx((1.0, 2.0, 3.0))


def test_calibrated_prediction_translates_and_yaw_rotates_with_scene():
    model = fitted()
    pose = rows()[0].camera
    y = np.array((3.0, 2.0, 6.0))
    original = posterior(
        model, model.digest, (pose,), (tuple(y),), use_prior=True, use_error=True, rho=0.5
    )
    q = CameraCoordinates(
        position_m=(0.0, 0.0, 0.0), yaw_degrees=90.0, pitch_degrees=0.0
    ).rotation()
    offset = np.array((7.0, 9.0, 11.0))
    moved = pose.model_copy(
        update={
            "position_m": tuple(q @ pose.position_m + offset),
            "yaw_degrees": pose.yaw_degrees + 90.0,
        }
    )
    transformed = posterior(
        model,
        model.digest,
        (moved,),
        (tuple(q @ y + offset),),
        use_prior=True,
        use_error=True,
        rho=0.5,
    )
    np.testing.assert_allclose(transformed.mean, q @ original.mean + offset, atol=1e-11)
    np.testing.assert_allclose(transformed.covariance, q @ original.covariance @ q.T, atol=1e-11)


def test_complete_model_forgery_fails_external_pin_and_legal_retry_succeeds():
    model = fitted()
    bad = model.model_copy(
        update={"prior": Gaussian3(mean=(99.0, 99.0, 99.0), covariance=model.prior.covariance)}
    )
    with pytest.raises(ValueError, match="external pin"):
        restore(bad, model.digest)
    assert restore(model, model.digest) == model


@pytest.mark.parametrize("rho", [1.0, -0.1, float("nan"), 0])
def test_invalid_temporal_fraction_fails_closed(rho):
    model = fitted()
    with pytest.raises(ValueError):
        posterior(
            model,
            model.digest,
            (rows()[0].camera,),
            ((1.0, 2.0, 3.0),),
            use_prior=True,
            use_error=True,
            rho=rho,
        )
