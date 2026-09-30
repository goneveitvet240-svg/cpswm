"""Controlled residual algebra and pinned-model attacks, not independent calibration."""

from __future__ import annotations

import copy
import json
import math
from dataclasses import replace
from uuid import UUID

import numpy as np
import pytest

from cpswm.perception_mapping import position_observation_model as task
from cpswm.system.reproducibility import canonical_json, content_sha256
from cpswm.system.structure_two_conditional_updates import rebuild_conditional_state
from cpswm.system.structure_two_particle_workspace import ConditionalAnalyticState

DOMAIN = "unity-rgbd-world-m-fixed-grid@1"
STAMP = "2026-10-01T00:00:00+00:00"
BIAS = np.asarray([-0.3, 1.4, 2.1])
NOISE = np.asarray([[2.0, 0.5, -0.2], [0.5, 1.3, 0.25], [-0.2, 0.25, 0.8]])
CLUSTER = UUID(int=8)
SOURCES = (UUID(int=9),)


def digest(label):
    return content_sha256(label)


def training_arrays():
    # Six ± points make the sample covariance exactly NOISE with ddof=1.
    columns = math.sqrt(5 / 2) * np.linalg.cholesky(NOISE)
    residuals = np.asarray([BIAS + sign * columns[:, i] for i in range(3) for sign in (-1, 1)])
    members = [
        dict(
            measurement_id=digest(["seed", i]),
            house_index=1,
            frame_sha256=digest("same-frame"),
            object_sha256=digest("same-object"),
            input_sha256=digest("same-input"),
            label_sha256=digest("same-offline-label"),
            split="train",
        )
        for i in range(6)
    ]
    return residuals, members


def fitted(estimator="soft_affinity", reference_kind="sdk_transform_position_m"):
    residuals, members = training_arrays()
    return task.fit(
        residuals,
        members,
        estimator=estimator,
        reference_kind=reference_kind,
        domain_id=DOMAIN,
        estimator_pin=digest([estimator, "readout-definition"]),
    )


def prior_state():
    # Exact symmetric inverse of independent 2x2 position/rotation blocks.
    sigma = np.diag([3.0, 4.0, 5.0, 2.0, 2.0, 2.0])
    precision = np.zeros((6, 6))
    for i, c in enumerate((0.5, 0.6, 0.7)):
        a, b = sigma[i, i], sigma[i + 3, i + 3]
        sigma[i, i + 3] = sigma[i + 3, i] = c
        det = a * b - c * c
        precision[i, i], precision[i + 3, i + 3] = b / det, a / det
        precision[i, i + 3] = precision[i + 3, i] = -c / det
    mean = np.asarray([0.3, -0.2, 0.4, 0.1, 0.3, -0.1])
    prior = ConditionalAnalyticState(
        locations=(UUID(int=1), UUID(int=2)),
        alpha=(2.0, 3.0),
        a=((2.0, 0.3), (0.3, 1.5)),
        b=(0.4, 0.2),
        information=tuple(tuple(v for v in row.tolist()) for row in precision),
        information_vector=tuple((precision @ mean).tolist()),
    )
    return prior, mean, sigma


def inputs(model):
    prior, mean, sigma = prior_state()
    z = mean[:3] + np.asarray([0.2, 0.6, -0.7])
    xyz = np.asarray([10.0, -4.0, 3.0])
    public = dict(
        measurement_id=digest("test-measurement"),
        estimator=model["estimator"],
        estimator_pin=model["estimator_pin"],
        domain_id=DOMAIN,
        frame_id="unity-scene-world-x-right-y-up-z-forward",
        action_id=str(UUID(int=5)),
        valid_at=STAMP,
        world_point_m=(xyz + np.asarray(model["bias"]) + z).tolist(),
    )
    reference = dict(
        reference_id=digest("explicit-hypothesis-reference"),
        reference_kind=model["reference_kind"],
        domain_id=DOMAIN,
        frame_id=public["frame_id"],
        valid_at=STAMP,
        xyz_m=xyz.tolist(),
    )
    return prior, mean, sigma, public, reference, z


def condition(model, public, reference, prior, *, pin=None, cluster=CLUSTER, sources=SOURCES):
    return task.condition(
        model,
        task.checkpoint_sha256(model) if pin is None else pin,
        public,
        reference,
        prior,
        evidence_cluster_id=cluster,
        source_record_ids=sources,
    )


@pytest.mark.parametrize("estimator", task.ESTIMATORS)
@pytest.mark.parametrize("reference_kind", task.REFERENCES)
def test_four_models_recover_full_covariance_from_related_same_frame_seeds(
    estimator, reference_kind
):
    model = fitted(estimator, reference_kind)
    np.testing.assert_allclose(model["bias"], BIAS, atol=1e-14)
    np.testing.assert_allclose(model["covariance"], NOISE, atol=1e-14)
    assert model["training"]["denominators"] == dict(
        seed_rows=6, frames=1, object_frames=1, objects=1, houses=1
    )
    assert model["independent_samples_assumed"] is False
    assert model["calibrated"] is False and model["runtime_authority"] is False
    restored = task.restore(json.loads(canonical_json(model)), task.checkpoint_sha256(model))
    assert restored == model
    prior, _, _, public, reference, _ = inputs(restored)
    measurement, diagnostic = condition(restored, public, reference, prior)
    assert measurement.information_weight == 1.0
    assert math.isfinite(diagnostic["observation_log_likelihood"])


def test_predictive_density_and_update_match_independent_closed_matrix_formula():
    model = fitted()
    prior, mean, sigma, public, reference, z = inputs(model)
    measurement, diagnostic = condition(model, public, reference, prior)
    h = np.column_stack((np.eye(3), np.zeros((3, 3))))
    s = sigma[:3, :3] + NOISE
    innovation = z - mean[:3]
    expected_logpdf = -0.5 * (
        math.log((2 * math.pi) ** 3 * np.linalg.det(s)) + innovation @ np.linalg.inv(s) @ innovation
    )
    np.testing.assert_allclose(measurement.measurement, z, atol=1e-14)
    np.testing.assert_array_equal(measurement.observation_matrix, h)
    np.testing.assert_allclose(measurement.noise_covariance, NOISE, atol=1e-14)
    np.testing.assert_allclose(diagnostic["predictive_covariance"], s, atol=1e-14)
    assert diagnostic["observation_log_likelihood"] == pytest.approx(expected_logpdf, abs=1e-14)
    assert not np.allclose(measurement.noise_covariance, diagnostic["predictive_covariance"])
    updated = rebuild_conditional_state(prior, (measurement,))
    expected_precision = np.asarray(prior.information) + h.T @ np.linalg.inv(NOISE) @ h
    expected_natural = np.asarray(prior.information_vector) + h.T @ np.linalg.inv(NOISE) @ z
    np.testing.assert_allclose(updated.information, expected_precision, atol=1e-14)
    np.testing.assert_allclose(updated.information_vector, expected_natural, atol=1e-14)
    assert updated.alpha == prior.alpha and updated.a == prior.a and updated.b == prior.b
    delta = np.asarray(updated.information) - np.asarray(prior.information)
    np.testing.assert_array_equal(delta[3:], np.zeros((3, 6)))
    np.testing.assert_array_equal(delta[:, 3:], np.zeros((6, 3)))
    np.testing.assert_array_equal(
        np.asarray(updated.information_vector)[3:], np.asarray(prior.information_vector)[3:]
    )
    posterior_mean = np.linalg.solve(updated.information, updated.information_vector)
    assert np.linalg.norm(posterior_mean[3:] - mean[3:]) > 1e-3
    assert rebuild_conditional_state(prior, ()) == prior
    with pytest.raises(ValueError, match="already consumed"):
        condition(model, public, reference, updated)
    with pytest.raises(ValueError, match="repeated evidence cluster"):
        rebuild_conditional_state(prior, (measurement, measurement))


def test_preupdate_uncertainty_and_complete_normalizer_affect_scores():
    model = fitted()
    prior, _, _, public, reference, _ = inputs(model)
    measurement, result = condition(model, public, reference, prior)
    # Score at the predictive mean: differing prior uncertainty changes the normalizer.
    public["world_point_m"] = (
        np.asarray(reference["xyz_m"]) + model["bias"] + np.asarray(result["prior_mean"])[:3]
    ).tolist()
    _, first = condition(model, public, reference, prior)
    broad = replace(
        prior,
        information=tuple(tuple(v / 2 for v in row) for row in prior.information),
        information_vector=tuple(v / 2 for v in prior.information_vector),
    )
    _, second = condition(model, public, reference, broad)
    assert first["squared_mahalanobis"] < 1e-25 and second["squared_mahalanobis"] < 1e-25
    assert first["observation_log_likelihood"] > second["observation_log_likelihood"]
    # A fixed-prior public change alters both observation density and natural update.
    public["world_point_m"][0] += 4.0
    corrected, changed = condition(model, public, reference, prior)
    assert changed["observation_log_likelihood"] != result["observation_log_likelihood"]
    weights = np.exp(
        np.asarray([result["observation_log_likelihood"], changed["observation_log_likelihood"]])
    )
    weights /= weights.sum()
    assert not np.allclose(weights, [0.5, 0.5])
    assert rebuild_conditional_state(prior, (measurement,)) != rebuild_conditional_state(
        prior, (corrected,)
    )


def test_positive_log_density_is_not_misread_as_invalid_probability():
    residuals, members = training_arrays()
    residuals = (residuals - BIAS) * 1e-4
    model = task.fit(
        residuals,
        members,
        estimator="uniform",
        reference_kind=task.REFERENCES[0],
        domain_id=DOMAIN,
        estimator_pin=digest("small-residual-estimator"),
    )
    prior, _, _, public, reference, _ = inputs(model)
    prior = replace(
        prior,
        information=tuple(tuple(row) for row in (np.eye(6) * 1e8).tolist()),
        information_vector=(0.0,) * 6,
    )
    public["world_point_m"] = (np.asarray(reference["xyz_m"]) + model["bias"]).tolist()
    _, result = condition(model, public, reference, prior)
    assert result["observation_log_likelihood"] > 0
    assert result["squared_mahalanobis"] < 1e-12


@pytest.mark.parametrize("pin", [None, False, "", "A" * 64, "0" * 64])
def test_external_pin_is_strict_and_required(pin):
    with pytest.raises(ValueError):
        task.restore(fitted(), pin)


@pytest.mark.parametrize(
    "field,value",
    [
        ("estimator", "selected-best"),
        ("reference_kind", "source-placement"),
        ("domain_id", ""),
        ("estimator_pin", "unpinned"),
    ],
)
def test_fit_definition_cannot_change_to_unknown_domain_or_estimator(field, value):
    residuals, members = training_arrays()
    options = dict(
        estimator="uniform",
        reference_kind=task.REFERENCES[0],
        domain_id=DOMAIN,
        estimator_pin=digest("known-estimator"),
    )
    options[field] = value
    with pytest.raises(ValueError):
        task.fit(residuals, members, **options)


@pytest.mark.parametrize("dtype", [np.float32, np.float64])
def test_training_and_restore_detach_all_mutable_inputs(dtype):
    x, members = training_arrays()
    x = x.astype(dtype)
    model = task.fit(
        x,
        members,
        estimator="uniform",
        reference_kind=task.REFERENCES[1],
        domain_id=DOMAIN,
        estimator_pin=digest("uniform-definition"),
    )
    pin = task.checkpoint_sha256(model)
    x[:] = 900.0
    members[0]["measurement_id"] = "0" * 64
    assert task.checkpoint_sha256(model) == pin
    restored = task.restore(model, pin)
    restored["bias"][0] = 900.0
    restored["training"]["denominators"]["houses"] = 8
    assert task.checkpoint_sha256(model) == pin
    prior, _, _, public, reference, _ = inputs(model)
    measurement, diagnostic = condition(model, public, reference, prior)
    before = canonical_json([measurement, diagnostic])
    public["world_point_m"][:] = [900.0] * 3
    reference["xyz_m"][:] = [900.0] * 3
    model["covariance"][0][0] = 900.0
    assert canonical_json([measurement, diagnostic]) == before


@pytest.mark.parametrize("field", ["bias", "covariance"])
def test_valid_complete_model_substitution_changes_results_but_original_pin_rejects(field):
    original = fitted()
    pin = task.checkpoint_sha256(original)
    prior, _, _, public, reference, _ = inputs(original)
    original_measurement, original_result = condition(original, public, reference, prior)
    forged = copy.deepcopy(original)
    if field == "bias":
        forged[field][0] += 2.0
    else:
        forged[field] = (np.asarray(forged[field]) * 2).tolist()
    selfpin = task.checkpoint_sha256(forged)
    assert task.restore(forged, selfpin) == forged  # Self-signing does not prove fitting.
    modified_measurement, modified_result = condition(forged, public, reference, prior, pin=selfpin)
    assert (
        modified_result["observation_log_likelihood"]
        != original_result["observation_log_likelihood"]
    )
    assert rebuild_conditional_state(prior, (modified_measurement,)) != rebuild_conditional_state(
        prior, (original_measurement,)
    )
    with pytest.raises(ValueError, match="external position model pin"):
        task.restore(forged, pin)
    with pytest.raises(ValueError, match="external position model pin"):
        condition(forged, public, reference, prior, pin=pin)
    assert task.restore(original, pin) == original


@pytest.mark.parametrize(
    "attack",
    ["too_few", "rank_zero", "rank_two", "nan", "int_dtype", "float16", "shape", "overflow"],
)
def test_bad_residuals_do_not_gain_fabricated_covariance(attack):
    x, members = training_arrays()
    if attack == "too_few":
        x, members = x[:3], members[:3]
    elif attack == "rank_zero":
        x[:] = BIAS
    elif attack == "rank_two":
        x[:, 2] = 0.0
    elif attack == "nan":
        x[0, 0] = np.nan
    elif attack == "int_dtype":
        x = x.astype(np.int64)
    elif attack == "float16":
        x = x.astype(np.float16)
    elif attack == "shape":
        x = x[:, :2]
    elif attack == "overflow":
        x[:] = 1e308
    with pytest.raises(ValueError):
        task.fit(
            x,
            members,
            estimator="uniform",
            reference_kind=task.REFERENCES[0],
            domain_id=DOMAIN,
            estimator_pin=digest("fixed"),
        )


@pytest.mark.parametrize(
    "attack",
    [
        "duplicate",
        "validation",
        "house9",
        "bool_house",
        "extra",
        "frame_house",
        "frame_input",
        "object_house",
    ],
)
def test_member_claims_are_strict_without_demanding_unique_frame_inputs(attack):
    x, rows = training_arrays()
    if attack == "duplicate":
        rows[1]["measurement_id"] = rows[0]["measurement_id"]
    elif attack == "validation":
        rows[1]["split"] = "validation"
    elif attack == "house9":
        rows[1]["house_index"] = 9
    elif attack == "bool_house":
        rows[1]["house_index"] = True
    elif attack == "extra":
        rows[1]["private_object_id"] = "forbidden-extra"
    elif attack == "frame_house":
        rows[1]["house_index"] = 2
    elif attack == "frame_input":
        rows[1]["input_sha256"] = digest("different-input")
    elif attack == "object_house":
        rows[1]["house_index"] = 2
        rows[1]["frame_sha256"] = digest("different-frame")
    with pytest.raises(ValueError):
        task.fit(
            x,
            rows,
            estimator="uniform",
            reference_kind=task.REFERENCES[0],
            domain_id=DOMAIN,
            estimator_pin=digest("fixed"),
        )


@pytest.mark.parametrize("partition", ["validation", "test", True, None])
def test_only_train_partition_is_accepted(partition):
    x, rows = training_arrays()
    with pytest.raises(ValueError, match="only train"):
        task.fit(
            x,
            rows,
            estimator="uniform",
            reference_kind=task.REFERENCES[0],
            domain_id=DOMAIN,
            estimator_pin=digest("fixed"),
            partition=partition,
        )


@pytest.mark.parametrize(
    "attack",
    [
        "extra",
        "schema",
        "authority",
        "iid",
        "rank_bool",
        "config_bool",
        "config_floor",
        "integer_bias",
        "covariance_asymmetric",
        "covariance_singular",
        "denominator_bool",
        "hash",
        "train_partition",
    ],
)
def test_malformed_checkpoints_rejected_even_after_resigning(attack):
    forged = fitted()
    if attack == "extra":
        forged["extra"] = 0
    elif attack == "schema":
        forged["schema"] = "production"
    elif attack == "authority":
        forged["runtime_authority"] = 0
    elif attack == "iid":
        forged["independent_samples_assumed"] = True
    elif attack == "rank_bool":
        forged["residual_rank"] = True
    elif attack == "config_bool":
        forged["config"]["covariance_ddof"] = True
    elif attack == "config_floor":
        forged["config"]["noise_floor"] = 1e-9
    elif attack == "integer_bias":
        forged["bias"][0] = 0
    elif attack == "covariance_asymmetric":
        forged["covariance"][0][1] += 0.1
    elif attack == "covariance_singular":
        forged["covariance"] = np.zeros((3, 3)).tolist()
    elif attack == "denominator_bool":
        forged["training"]["denominators"]["houses"] = True
    elif attack == "hash":
        forged["training"]["residuals_sha256"] = "A" * 64
    elif attack == "train_partition":
        forged["training"]["partition"] = "validation"
    with pytest.raises(ValueError):
        task.restore(forged, content_sha256(forged))


@pytest.mark.parametrize(
    "attack",
    [
        "extra_private",
        "world_nan",
        "world_bool",
        "wrong_shape",
        "wrong_estimator",
        "wrong_pin",
        "wrong_domain",
        "bad_action",
        "naive_time",
        "nonutc_time",
        "reference_kind",
        "reference_frame",
        "reference_epoch",
        "reference_extra",
    ],
)
def test_public_observation_and_local_reference_are_strict(attack):
    model = fitted()
    prior, _, _, public, reference, _ = inputs(model)
    if attack == "extra_private":
        public["object_instance_id"] = "sdk-truth"
    elif attack == "world_nan":
        public["world_point_m"][0] = np.nan
    elif attack == "world_bool":
        public["world_point_m"][0] = True
    elif attack == "wrong_shape":
        public["world_point_m"].append(0.0)
    elif attack == "wrong_estimator":
        public["estimator"] = "uniform"
    elif attack == "wrong_pin":
        public["estimator_pin"] = digest("another-readout")
    elif attack == "wrong_domain":
        public["domain_id"] = "other-coordinate-contract"
    elif attack == "bad_action":
        public["action_id"] = "not-an-action"
    elif attack == "naive_time":
        public["valid_at"] = "2026-10-01T00:00:00"
    elif attack == "nonutc_time":
        public["valid_at"] = "2026-10-01T01:00:00+01:00"
    elif attack == "reference_kind":
        reference["reference_kind"] = task.REFERENCES[1]
    elif attack == "reference_frame":
        reference["frame_id"] = "another-world"
    elif attack == "reference_epoch":
        reference["valid_at"] = "2026-10-01T00:00:01Z"
    elif attack == "reference_extra":
        reference["truth_authority"] = True
    with pytest.raises(ValueError):
        condition(model, public, reference, prior)


@pytest.mark.parametrize(
    "attack",
    [
        "bad_cluster",
        "duplicate_sources",
        "empty_sources",
        "prior_bool",
        "prior_shape",
        "prior_extra",
        "prior_asymmetric",
    ],
)
def test_condition_revalidates_prior_and_source_ownership_claims(attack):
    model = fitted()
    prior, _, _, public, reference, _ = inputs(model)
    kwargs = {}
    if attack == "bad_cluster":
        kwargs["cluster"] = str(UUID(int=8))
    elif attack == "duplicate_sources":
        kwargs["sources"] = (UUID(int=9), UUID(int=9))
    elif attack == "empty_sources":
        kwargs["sources"] = ()
    elif attack == "prior_bool":
        object.__setattr__(prior, "information_vector", (True,) * 6)
    elif attack == "prior_shape":
        object.__setattr__(prior, "information_vector", (0.0,) * 3)
    elif attack == "prior_extra":
        object.__setattr__(prior, "extra", "hidden")
    elif attack == "prior_asymmetric":
        matrix = [list(row) for row in prior.information]
        matrix[0][1] += 0.1
        object.__setattr__(prior, "information", matrix)
    with pytest.raises(ValueError):
        condition(model, public, reference, prior, **kwargs)
