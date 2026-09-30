"""Controlled numeric consequences, with no private label input or native receipt claims."""

import copy
import json
import math
from uuid import UUID

import numpy as np
import position_factor_diagnostic as task
import pytest
from test_position_observation_model import fitted

from cpswm.perception_mapping import position_observation_model as position
from cpswm.system.reproducibility import canonical_json, content_sha256


def fixture():
    models = {e + "/" + r: fitted(e, r) for e in position.ESTIMATORS for r in position.REFERENCES}
    pins = {name: position.checkpoint_sha256(model) for name, model in models.items()}
    records = [
        dict(
            house_index=i // 8 + 1,
            sdk_index=i % 8 + 4,
            action_id=str(UUID(int=i + 100)),
            observations=[],
        )
        for i in range(96)
    ]
    for seed_index, available in enumerate((False, True, True)):
        seed = content_sha256(["controlled-public-seed", seed_index])
        for estimator in position.ESTIMATORS:
            model = models[estimator + "/" + position.REFERENCES[0]]
            point = [2.0, -1.0, 0.5] if estimator == "soft_affinity" else [2.5, -0.5, 0.3]
            if seed_index == 2:
                point = [0.0, 0.0, 0.0]
            records[2]["observations"].append(
                dict(
                    measurement_id=seed,
                    seed_id=seed,
                    estimator=estimator,
                    estimator_pin=model["estimator_pin"],
                    domain_id=task.DOMAIN,
                    frame_id="unity-scene-world-x-right-y-up-z-forward",
                    action_id=records[2]["action_id"],
                    valid_at="2026-10-01T00:00:00Z",
                    world_point_m=point if available else None,
                    available=available,
                    reason=None if available else "invalid_depth",
                )
            )
    return models, pins, records


def independent_weights(logs):
    values = np.asarray([logs[name] for name in task.BRANCHES])
    weights = np.exp(values - max(values))
    return weights / weights.sum()


def test_complete_four_model_path_matches_independent_density_weights_and_updates():
    models, pins, records = fixture()
    result = task.diagnose(models, records, model_pins=pins)
    assert result["frames"] == 96 and result["private_labels_accepted"] is False
    assert result["native_receipts_produced"] is result["owner_pipeline_executed"] is False
    assert result["natural_world_identity_authority"] is result["runtime_authority"] is False
    h = np.column_stack((np.eye(3), np.zeros((3, 3))))
    for name, row in result["combinations"].items():
        assert row["status"] == "controlled_numeric_diagnostic"
        assert row["selected"]["frame_ordinal"] == 2 and row["selected"]["seed_ordinal"] == 1
        assert row["selected"]["observation_ordinal"] == (
            2 if name.startswith("soft_affinity") else 3
        )
        point = np.asarray(row["selected"]["observation"]["world_point_m"])
        covariance = np.asarray(models[name]["covariance"])
        z = point - np.asarray(models[name]["bias"])
        predictive = np.eye(3) + covariance
        sign, logdet = np.linalg.slogdet(predictive)
        assert sign == 1
        known = -0.5 * (3 * math.log(2 * math.pi) + logdet + z @ np.linalg.solve(predictive, z))
        broad = 100 * np.eye(3)
        sign, logdet = np.linalg.slogdet(broad)
        unknown = -0.5 * (
            3 * math.log(2 * math.pi) + logdet + point @ np.linalg.solve(broad, point)
        )
        expected_logs = dict(known=known, unknown=unknown, aggregate=unknown)
        for branch in task.BRANCHES:
            assert row["log_factors"][branch] == pytest.approx(expected_logs[branch], abs=1e-14)
        np.testing.assert_allclose(
            list(row["normalized_weights"][branch] for branch in task.BRANCHES),
            independent_weights(expected_logs),
            atol=1e-14,
        )
        assert row["normalized_weights"]["unknown"] == row["normalized_weights"]["aggregate"]
        delta = h.T @ np.linalg.solve(covariance, h)
        natural = h.T @ np.linalg.solve(covariance, z)
        np.testing.assert_allclose(row["delta_information"], delta, atol=1e-14)
        np.testing.assert_allclose(row["delta_information_vector"], natural, atol=1e-14)
        np.testing.assert_allclose(
            row["known_after"]["mean"], np.linalg.solve(np.eye(6) + delta, natural), atol=1e-14
        )
        assert row["known_before"] == row["no_factor"]["known_state"] == row["retracted"]
        assert row["no_factor"]["normalized_weights"] == {key: 1 / 3 for key in task.BRANCHES}
        assert (
            row["replay_matches"] and row["duplicate_rejected"] and row["duplicate_state_unchanged"]
        )
        assert len(row["known_after"]["evidence_cluster_ids"]) == 1
        assert row["known_before"]["alpha"] == row["known_after"]["alpha"]
        assert row["known_before"]["a"] == row["known_after"]["a"]
        assert row["known_before"]["b"] == row["known_after"]["b"]


def test_first_available_public_order_is_used_even_when_later_seed_is_closer():
    models, pins, records = fixture()
    records[2]["observations"][2]["world_point_m"] = [500.0, 400.0, 300.0]
    first = task.diagnose(models, records, model_pins=pins)
    row = first["combinations"][task.COMBINATIONS[0]]
    assert (
        row["selected"]["observation"]["measurement_id"]
        == records[2]["observations"][2]["measurement_id"]
    )
    assert row["normalized_weights"]["known"] < row["no_factor"]["normalized_weights"]["known"]
    # Supplied canonical order remains explicit; the owning driver authenticates it.
    observations = records[2]["observations"]
    records[2]["observations"] = observations[:2] + observations[4:] + observations[2:4]
    second = task.diagnose(models, records, model_pins=pins)
    moved = second["combinations"][task.COMBINATIONS[0]]
    assert moved["selected"]["observation"]["measurement_id"] == observations[4]["measurement_id"]
    assert moved["normalized_weights"] != row["normalized_weights"]
    assert second["public_records_sha256"] != first["public_records_sha256"]


def test_fit_failed_and_empty_public_are_explicit_without_fabricating_factors():
    models, pins, records = fixture()
    name = task.COMBINATIONS[0]
    models[name] = pins[name] = None
    result = task.diagnose(models, records, model_pins=pins)
    assert result["combinations"][name]["status"] == "fit_failed"
    assert result["combinations"][name]["selected"]["seed_ordinal"] == 1
    assert result["combinations"][name]["factor_applied"] is False
    assert result["combinations"][name]["posterior"] is None
    for record in records:
        record["observations"] = []
    empty = task.diagnose(models, records, model_pins=pins)
    for key, row in empty["combinations"].items():
        assert row["status"] == ("fit_failed" if key == name else "no_available_public_observation")
        assert (
            row["selected"] is None and row["posterior"] is None and row["factor_applied"] is False
        )


@pytest.mark.parametrize(
    "attack",
    [
        "record_labels",
        "observation_label",
        "private_late_frame",
        "short_schedule",
        "wrong_schedule",
        "bool_house",
        "duplicate_action",
        "duplicate_seed",
        "unpaired",
        "availability_int",
        "availability_mismatch",
        "hidden_point",
        "pin_change",
        "wrong_action",
        "nonfinite_point",
    ],
)
def test_entire_public_input_is_checked_before_selection(attack):
    models, pins, records = fixture()
    observations = records[2]["observations"]
    if attack == "record_labels":
        records[2]["labels"] = {"eligible": True}
    elif attack == "observation_label":
        observations[2]["targets"] = [0.0] * 3
    elif attack == "private_late_frame":
        records[-1]["labels"] = "not silently ignored"
    elif attack == "short_schedule":
        records.pop()
    elif attack == "wrong_schedule":
        records[0]["sdk_index"] = 5
    elif attack == "bool_house":
        records[0]["house_index"] = True
    elif attack == "duplicate_action":
        records[-1]["action_id"] = records[0]["action_id"]
    elif attack == "duplicate_seed":
        observations.extend(copy.deepcopy(observations[-2:]))
    elif attack == "unpaired":
        observations.pop()
    elif attack == "availability_int":
        observations[0]["available"] = 0
    elif attack == "availability_mismatch":
        observations[0].update(available=True, reason=None, world_point_m=[0.0] * 3)
    elif attack == "hidden_point":
        observations[0]["world_point_m"] = [0.0] * 3
    elif attack == "pin_change":
        observations[-1]["estimator_pin"] = content_sha256("another-estimator")
    elif attack == "wrong_action":
        observations[-1]["action_id"] = str(UUID(int=9999))
    elif attack == "nonfinite_point":
        observations[-1]["world_point_m"][0] = np.nan
    with pytest.raises(ValueError):
        task.diagnose(models, records, model_pins=pins)


def test_valid_resigned_model_changes_complete_diagnostic_but_original_pin_rejects():
    models, pins, records = fixture()
    first = task.diagnose(models, records, model_pins=pins)
    changed = copy.deepcopy(models)
    name = task.COMBINATIONS[0]
    changed[name]["bias"][0] += 4.0
    with pytest.raises(ValueError, match="external position model pin"):
        task.diagnose(changed, records, model_pins=pins)
    newpins = dict(pins, **{name: position.checkpoint_sha256(changed[name])})
    new = task.diagnose(changed, records, model_pins=newpins)
    assert (
        new["combinations"][name]["normalized_weights"]
        != first["combinations"][name]["normalized_weights"]
    )
    assert new["combinations"][name]["known_after"] != first["combinations"][name]["known_after"]
    assert task.diagnose(models, records, model_pins=pins) == first


def test_model_group_and_failure_pin_are_strict():
    models, pins, records = fixture()
    names = task.COMBINATIONS[:2]
    models[names[0]], models[names[1]] = models[names[1]], models[names[0]]
    pins[names[0]], pins[names[1]] = pins[names[1]], pins[names[0]]
    with pytest.raises(ValueError, match="model differs"):
        task.diagnose(models, records, model_pins=pins)
    models, pins, records = fixture()
    models[names[0]] = None
    with pytest.raises(ValueError, match="failed fit"):
        task.diagnose(models, records, model_pins=pins)


def test_result_is_json_portable_detached_and_inputs_unchanged():
    models, pins, records = fixture()
    before = canonical_json([models, pins, records])
    result = task.diagnose(models, records, model_pins=pins)
    assert canonical_json([models, pins, records]) == before
    snapshot = canonical_json(result)
    models[task.COMBINATIONS[0]]["bias"][0] = 900.0
    records[2]["observations"][2]["world_point_m"][0] = 900.0
    assert canonical_json(result) == snapshot
    assert json.loads(json.dumps(result, allow_nan=False)) == result
