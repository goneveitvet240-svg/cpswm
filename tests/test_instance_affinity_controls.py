"""Controlled numerical and complete-checkpoint tests; no real-data model selection."""

from __future__ import annotations

import copy
import json

import numpy as np
import pytest

from cpswm.data_preflight import instance_affinity as base
from cpswm.data_preflight import instance_affinity_controls as controls
from cpswm.system.reproducibility import canonical_json, content_sha256


def training_arrays(dtype=np.float64):
    features = np.zeros((80, 8), dtype=dtype)
    nuisance = np.tile(np.linspace(0.02, 0.15, 20), 4)
    different = np.asarray([0] * 40 + [1] * 40)
    features[:, 0] = nuisance + 0.75 * different
    features[:, 1] = 0.2
    features[:, 2] = nuisance
    features[:, 3] = 0.1 + 0.6 * different
    features[:, 4] = nuisance
    features[:, 5] = 0.1 + 2.0 * different + nuisance
    features[:, 6] = 0.1 + different + nuisance
    features[:, 7] = 0.3 + 3.0 * different + nuisance
    targets = np.asarray([1] * 40 + [0] * 40, dtype=np.int8)
    return features, targets


@pytest.fixture
def models():
    features, targets = training_arrays()
    return {mode: controls.fit(features, targets, mode) for mode in controls.MODES}


@pytest.mark.parametrize("mode", controls.MODES)
def test_three_modes_fit_restore_and_predict_meaningful_scores(mode, models):
    features, targets = training_arrays()
    wrapper = models[mode]
    pin = controls.checkpoint_sha256(wrapper)
    restored = controls.restore(json.loads(json.dumps(wrapper)), pin)
    assert restored == wrapper
    assert restored is not wrapper
    assert wrapper["runtime_authority"] is False and wrapper["calibrated"] is False
    inner = restored["inner_checkpoint"]
    assert inner["config"] == base.CONFIG
    assert inner["class_counts"] == [40, 40]
    assert inner["optimization_loss"][-1] < inner["optimization_loss"][0]
    scores = np.asarray(controls.predict(restored, features, np.ones(len(features), dtype=bool)))
    assert np.all(scores[targets == 1] > 0.8)
    assert np.all(scores[targets == 0] < 0.2)
    disabled = sorted(set(range(8)) - set(wrapper["active_columns"]))
    assert all(inner["mean"][i] == inner["weights"][i] == 0.0 for i in disabled)
    assert all(inner["scale"][i] == 1.0 for i in disabled)
    assert controls.predict(restored, np.zeros((2, 8)), np.zeros(2, dtype=bool)) == [None, None]
    assert controls.predict(restored, np.zeros((0, 8)), np.zeros(0, dtype=bool)) == []


@pytest.mark.parametrize("dtype", [np.float32, np.float64])
@pytest.mark.parametrize("noncontiguous", [False, True])
def test_combined_exact_original_checkpoint_bytes_and_predictions(dtype, noncontiguous):
    features, targets = training_arrays(dtype)
    if noncontiguous:
        features = np.asfortranarray(features)
        assert not features.flags.c_contiguous
    original = base.fit(features, targets)
    wrapper = controls.fit(features, targets, "combined")
    assert canonical_json(wrapper["inner_checkpoint"]) == canonical_json(original)
    assert wrapper["inner_sha256"] == base.checkpoint_sha256(original)
    valid = np.ones(len(features), dtype=bool)
    assert controls.predict(wrapper, features, valid) == base.predict(original, features, valid)
    assert controls.project(features, "combined").dtype == features.dtype


@pytest.mark.parametrize("mode", ["rgb_only", "geometry_only"])
def test_disabled_source_changes_preserve_fit_and_prediction_but_change_source_digest(mode):
    features, targets = training_arrays()
    altered = features.copy()
    disabled = sorted(set(range(8)) - set(controls.ACTIVE_COLUMNS[mode]))
    altered[:, disabled] = 0.75
    original = controls.fit(features, targets, mode)
    changed = controls.fit(altered, targets, mode)
    assert original["training_features_sha256"] != changed["training_features_sha256"]
    assert canonical_json(original["inner_checkpoint"]) == canonical_json(
        changed["inner_checkpoint"]
    )
    valid = np.ones(len(features), dtype=bool)
    assert controls.predict(original, features, valid) == controls.predict(original, altered, valid)
    with pytest.raises(ValueError, match="external control pin"):
        controls.restore(changed, controls.checkpoint_sha256(original))


@pytest.mark.parametrize("mode", controls.MODES)
def test_void_does_not_enter_scaling_or_optimization(mode, models):
    features, targets = training_arrays()
    void = np.asarray([[0.9] * 5 + [1e100] * 3])
    wrapper = controls.fit(np.concatenate((features, void)), np.append(targets, np.int8(-1)), mode)
    fitted = wrapper["inner_checkpoint"]
    previous = models[mode]["inner_checkpoint"]
    for field in ("mean", "scale", "weights", "bias", "prevalence", "optimization_loss"):
        assert fitted[field] == previous[field]
    assert fitted["rows_total"] == 81 and fitted["rows_fit"] == 80 and fitted["rows_void"] == 1
    assert wrapper["training_targets_sha256"] == fitted["training_targets_sha256"]
    assert wrapper["training_features_sha256"] != models[mode]["training_features_sha256"]


@pytest.mark.parametrize("partition", ["validation", "test", "TRAIN", "", None, True])
def test_training_partition_cannot_be_changed(partition):
    features, targets = training_arrays()
    with pytest.raises(ValueError, match="train partition"):
        controls.fit(features, targets, "combined", partition=partition)


@pytest.mark.parametrize("mode,column", [("rgb_only", 5), ("geometry_only", 0)])
@pytest.mark.parametrize("bad_value", [np.nan, np.inf, -0.1])
def test_invalid_original_values_cannot_hide_in_disabled_columns(mode, column, bad_value, models):
    features, targets = training_arrays()
    features[0, column] = bad_value
    for operation in (
        lambda: controls.project(features, mode),
        lambda: controls.fit(features, targets, mode),
        lambda: controls.predict(models[mode], features, np.ones(len(features), dtype=bool)),
    ):
        with pytest.raises(ValueError, match="features must"):
            operation()


@pytest.mark.parametrize("mode,column", [("rgb_only", 3), ("geometry_only", 0)])
def test_out_of_range_normalized_disabled_feature_is_not_erased(mode, column):
    features, _ = training_arrays()
    features[0, column] = 1.01
    with pytest.raises(ValueError, match="features must"):
        controls.project(features, mode)


@pytest.mark.parametrize("mode,column", [("rgb_only", 5), ("geometry_only", 0), ("combined", 7)])
def test_invalid_row_must_be_zero_before_projection(mode, column, models):
    features = np.zeros((2, 8))
    features[0, column] = 0.25
    with pytest.raises(ValueError, match="invalid original feature rows"):
        controls.predict(models[mode], features, np.asarray([False, True]))
    features[0, column] = 0.0
    result = controls.predict(models[mode], features, np.asarray([False, True]))
    assert result[0] is None and type(result[1]) is float


@pytest.mark.parametrize(
    "bad",
    [
        np.zeros((2, 8), dtype=np.int64),
        np.zeros((2, 8), dtype=np.float16),
        np.zeros((2, 7)),
        np.zeros(8),
        [[0.0] * 8],
    ],
)
def test_wrong_feature_shapes_and_types_rejected(bad):
    with pytest.raises(ValueError, match="features must"):
        controls.project(bad, "rgb_only")


@pytest.mark.parametrize(
    "bad", [[True, True], np.ones(2, dtype=np.int8), np.ones((2, 1), dtype=bool)]
)
def test_valid_mask_is_strict(bad, models):
    with pytest.raises(ValueError, match="boolean row mask"):
        controls.predict(models["combined"], np.zeros((2, 8)), bad)


@pytest.mark.parametrize("bad", ["rgb", None, 0, True, ["combined"]])
def test_mode_is_strict(bad):
    features, targets = training_arrays()
    with pytest.raises(ValueError, match="mode"):
        controls.project(features, bad)
    with pytest.raises(ValueError, match="mode"):
        controls.fit(features, targets, bad)


@pytest.mark.parametrize("mode", controls.MODES)
def test_projection_fitting_prediction_and_restore_do_not_alias_inputs(mode, models):
    features, targets = training_arrays(np.float32)
    original_features, original_targets = features.copy(), targets.copy()
    features.setflags(write=False)
    targets.setflags(write=False)
    projected = controls.project(features, mode)
    assert projected.dtype == features.dtype
    assert not np.shares_memory(features, projected)
    projected[:] = 0
    wrapper = controls.fit(features, targets, mode)
    valid = np.ones(len(features), dtype=bool)
    controls.predict(wrapper, features, valid)
    np.testing.assert_array_equal(features, original_features)
    np.testing.assert_array_equal(targets, original_targets)
    assert valid.all()
    restored = controls.restore(models[mode], controls.checkpoint_sha256(models[mode]))
    restored["active_columns"].append(9)
    restored["config"]["sample_selection"] = "changed"
    restored["inner_checkpoint"]["weights"][0] += 100.0
    assert 9 not in models[mode]["active_columns"]
    assert models[mode]["config"] == controls.CONFIG
    assert (
        models[mode]["inner_checkpoint"]["weights"][0] != restored["inner_checkpoint"]["weights"][0]
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema", "foreign"),
        ("scope", "RUNTIME"),
        ("mode", "rgb"),
        ("active_columns", [True, 1, 2]),
        ("active_columns", (0, 1, 2)),
        ("active_columns", [2, 1, 0]),
        ("active_columns", [0, 1, 2, 3]),
        ("runtime_authority", 0),
        ("runtime_authority", True),
        ("calibrated", 0),
        ("calibrated", True),
        ("training_features_sha256", "A" * 64),
        ("training_features_sha256", None),
        ("training_targets_sha256", "0" * 64),
        ("inner_sha256", "0" * 64),
        ("inner_checkpoint", {}),
        ("extra", "metadata"),
        ("config", {**controls.CONFIG, "sample_selection": "balanced"}),
        ("config", {**controls.CONFIG, "extra": False}),
    ],
)
def test_malformed_wrapper_rejected_even_with_recomputed_outer_pin(field, value, models):
    forged = copy.deepcopy(models["rgb_only"])
    forged[field] = value
    with pytest.raises(ValueError):
        controls.restore(forged, content_sha256(forged))


@pytest.mark.parametrize("field,value", [("mean", 0.25), ("scale", 2.0), ("weights", 0.25)])
@pytest.mark.parametrize("mode,column", [("rgb_only", 5), ("geometry_only", 0)])
def test_disabled_parameter_attack_rejected_after_complete_inner_and_outer_resigning(
    field, value, mode, column, models
):
    forged = copy.deepcopy(models[mode])
    forged["inner_checkpoint"][field][column] = value
    forged["inner_sha256"] = base.checkpoint_sha256(forged["inner_checkpoint"])
    with pytest.raises(ValueError, match="disabled columns"):
        controls.restore(forged, content_sha256(forged))


def test_coherent_mode_relabel_cannot_retain_incompatible_fitted_model(models):
    forged = copy.deepcopy(models["combined"])
    forged["mode"] = "rgb_only"
    forged["active_columns"] = [0, 1, 2]
    with pytest.raises(ValueError, match="disabled columns"):
        controls.restore(forged, content_sha256(forged))


@pytest.mark.parametrize(
    "field,value",
    [
        ("runtime_authority", True),
        ("runtime_authority", 0),
        ("calibrated", True),
        ("training_partition", "validation"),
        ("config", {**base.CONFIG, "l2_weights_only": 0.0}),
        ("weights", [0] * 8),
        ("extra", "private-instance-id"),
    ],
)
def test_inner_definition_attack_rejected_with_all_digests_recomputed(field, value, models):
    forged = copy.deepcopy(models["rgb_only"])
    forged["inner_checkpoint"][field] = value
    forged["inner_sha256"] = content_sha256(forged["inner_checkpoint"])
    with pytest.raises(ValueError):
        controls.restore(forged, content_sha256(forged))


def test_combined_original_content_digest_must_equal_inner_content_digest(models):
    forged = copy.deepcopy(models["combined"])
    forged["training_features_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="combined original"):
        controls.restore(forged, content_sha256(forged))


def test_full_valid_model_substitution_changes_scores_but_original_external_pin_rejects(models):
    features, _ = training_arrays()
    original = models["rgb_only"]
    pin = controls.checkpoint_sha256(original)
    forged = copy.deepcopy(original)
    forged["inner_checkpoint"]["weights"][0] *= -1
    forged["inner_sha256"] = base.checkpoint_sha256(forged["inner_checkpoint"])
    forged_pin = controls.checkpoint_sha256(forged)
    valid = np.ones(len(features), dtype=bool)
    assert controls.predict(forged, features, valid) != controls.predict(original, features, valid)
    # Structural validation plus a new attacker-provided pin cannot prove fitting history.
    assert controls.restore(forged, forged_pin) == forged
    with pytest.raises(ValueError, match="external control pin"):
        controls.restore(forged, pin)
    with pytest.raises(ValueError, match="external control pin"):
        controls.restore(models["geometry_only"], pin)
    assert controls.restore(original, pin) == original


@pytest.mark.parametrize("pin", [None, False, "", "A" * 64, "x" * 64, "0" * 64])
def test_external_pin_is_required_and_exact(pin, models):
    with pytest.raises(ValueError, match="external control pin"):
        controls.restore(models["combined"], pin)


@pytest.mark.parametrize(
    "bad_targets",
    [
        np.zeros(80, dtype=np.int8),
        np.full(80, -1, dtype=np.int8),
        np.zeros(80),
        np.zeros(79, dtype=np.int8),
    ],
)
def test_original_target_validation_and_both_class_requirement_preserved(bad_targets):
    features, _ = training_arrays()
    with pytest.raises(ValueError):
        controls.fit(features, bad_targets, "combined")
