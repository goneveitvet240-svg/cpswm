"""Second review: legal actual checkpoints and complete-but-forged outcome claims."""

import os
from copy import deepcopy
from pathlib import Path

import pytest
import torch
from run_camera_policy_identifiability import (
    ARMS,
    METHODS,
    PATTERNS,
    checkpoint_for,
    run_case,
    same_value,
    summarize,
)


@pytest.fixture(scope="module")
def actual(tmp_path_factory):
    torch.set_num_threads(2)
    root = tmp_path_factory.mktemp("binary-actual-neural")
    default_checkpoints = (
        Path(__file__).resolve().parents[1]
        / "docs/reviews/pc_a/neural_native_loop_2026-09-29/evidence/development-checkpoints"
    )
    # An explicit override remains authoritative and must fail if it is invalid.
    checkpoints = Path(os.environ.get("CPSWM_CHECKPOINTS", str(default_checkpoints)))
    rows = {}
    for arm in ARMS:
        row = run_case(
            root / arm, pattern="01", method=arm, checkpoint=checkpoint_for(checkpoints, arm)
        )
        assert row["neural_calls"] > 0 and row["checkpoint_arm"] == arm
        assert row["checkpoint_manifest_sha256"] and row["feedback_updates"] == 1
        rows[arm] = row
    return rows


def test_actual_three_checkpoints_are_legal_and_keep_same_enumerated_prior(actual):
    prior = actual[ARMS[0]]["initial"]
    for row in actual.values():
        same_value(row, deepcopy(row))
        same_value(row["initial"], prior)
        assert len(row["actions"]) == 1 and row["actions"][0]["heading"] == 315


@pytest.mark.parametrize(
    "attack",
    [
        "normalized_posterior",
        "fake_action_success",
        "checkpoint",
        "extra_natural_claim",
        "boolean_as_count",
        "nan",
        "omit_action",
    ],
)
def test_fully_populated_forged_claim_does_not_match_executed_case(actual, attack):
    expected = actual[ARMS[0]]
    forged = deepcopy(expected)
    if attack == "normalized_posterior":
        for posterior in (forged["final"], forged["actions"][0]["posterior"]):
            posterior["known_instance"] += 0.01
            posterior["aggregate_unresolved"] -= 0.01
        assert sum(forged["final"].values()) == pytest.approx(1)
    elif attack == "fake_action_success":
        forged["actions"][0]["heading"] = 225.0
        forged["actions"][0]["action"] = "RotateLeft"
        forged["actions"][0]["outcome"] = "category_candidate"
    elif attack == "checkpoint":
        forged["checkpoint_manifest_sha256"] = "0" * 64
    elif attack == "extra_natural_claim":
        forged["natural_task_success"] = True
    elif attack == "boolean_as_count":
        forged["camera_calls"] = True
    elif attack == "nan":
        forged["final"]["known_instance"] = float("nan")
    else:
        forged["actions"] = []
        forged["camera_calls"] = forged["feedback_updates"] = 0
    with pytest.raises(ValueError):
        same_value(forged, expected)


@pytest.fixture(scope="module")
def complete(tmp_path_factory):
    root = tmp_path_factory.mktemp("binary-matrix-audit")
    return [run_case(root / p / m, pattern=p, method=m) for p in PATTERNS for m in METHODS]


@pytest.mark.parametrize("attack", ["omit", "duplicate", "prior", "baseline_updates", "no_stop"])
def test_matrix_rejects_selection_bias_and_unfair_controls(complete, attack):
    forged = deepcopy(complete)
    if attack == "omit":
        forged.pop(0)
    elif attack == "duplicate":
        forged[0] = deepcopy(forged[1])
    elif attack == "prior":
        forged[-1]["initial"]["known_instance"] += 0.01
        forged[-1]["initial"]["aggregate_unresolved"] -= 0.01
    elif attack == "baseline_updates":
        row = next(r for r in forged if r["method"] == "no_feedback")
        row["feedback_updates"] = len(row["actions"])
    else:
        forged[0]["stopped"] = False
    with pytest.raises(ValueError):
        summarize(forged)
