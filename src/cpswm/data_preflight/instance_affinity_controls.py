"""Fixed feature-group controls for the offline rendered-instance affinity model.

Source digests bind the declared original arrays; checkpoint restoration alone
does not verify that those arrays produced the fitted parameters. Scores remain
uncalibrated, with no runtime, target-selection, or observation-likelihood authority.
"""

from __future__ import annotations

import json
import re
from typing import Any, cast

import numpy as np

from cpswm.data_preflight import instance_affinity as base
from cpswm.system.reproducibility import canonical_json, content_sha256

MODES = ("rgb_only", "geometry_only", "combined")
ACTIVE_COLUMNS = {
    "rgb_only": (0, 1, 2),
    "geometry_only": (3, 4, 5, 6, 7),
    "combined": tuple(range(8)),
}
SCHEMA = "offline-instance-affinity-feature-controls@1"
SCOPE = "UNCALIBRATED_RENDERED_INSTANCE_PAIR_FEATURE_CONTROLS_ONLY"
CONFIG = {
    "projection": "zero_disabled_columns",
    "sample_selection": "unchanged",
    "inner_schema": base.SCHEMA,
}


def _columns(mode: str) -> tuple[int, ...]:
    base._require(type(mode) is str and mode in MODES, "invalid feature-control mode")
    return ACTIVE_COLUMNS[mode]


def project(features: np.ndarray, mode: str) -> np.ndarray:
    """Validate all original columns, then copy and zero disabled columns.

    Preserve the original float32/float64 dtype so combined-mode fitting also
    preserves the original model's input-content digest exactly.
    """
    active = _columns(mode)
    base._features(features)
    projected = features.copy()
    projected[:, [index for index in range(8) if index not in active]] = 0
    return projected


def fit(
    features: np.ndarray, targets: np.ndarray, mode: str, *, partition: str = "train"
) -> dict[str, Any]:
    """Use the unchanged train-only fitter and record both source and model digests."""
    inner = base.fit(project(features, mode), targets, partition=partition)
    wrapper = dict(
        schema=SCHEMA,
        scope=SCOPE,
        mode=mode,
        active_columns=list(_columns(mode)),
        config=dict(CONFIG),
        training_features_sha256=base._array_sha256(features),
        training_targets_sha256=base._array_sha256(targets),
        inner_checkpoint=inner,
        inner_sha256=base.checkpoint_sha256(inner),
        runtime_authority=False,
        calibrated=False,
    )
    _validate_wrapper(wrapper)
    return wrapper


def _validate_wrapper(wrapper: Any) -> None:
    keys = {
        "schema",
        "scope",
        "mode",
        "active_columns",
        "config",
        "training_features_sha256",
        "training_targets_sha256",
        "inner_checkpoint",
        "inner_sha256",
        "runtime_authority",
        "calibrated",
    }
    base._require(type(wrapper) is dict and set(wrapper) == keys, "invalid control fields")
    active = _columns(wrapper["mode"])
    base._require(
        type(wrapper["schema"]) is str
        and wrapper["schema"] == SCHEMA
        and type(wrapper["scope"]) is str
        and wrapper["scope"] == SCOPE
        and wrapper["runtime_authority"] is False
        and wrapper["calibrated"] is False
        and type(wrapper["active_columns"]) is list
        and all(type(index) is int for index in wrapper["active_columns"])
        and wrapper["active_columns"] == list(active)
        and type(wrapper["config"]) is dict
        and set(wrapper["config"]) == set(CONFIG)
        and all(type(wrapper["config"][key]) is str for key in CONFIG)
        and wrapper["config"] == CONFIG,
        "control definition, fixed config or authority differs",
    )
    for field in ("training_features_sha256", "training_targets_sha256"):
        base._require(
            type(wrapper[field]) is str
            and re.fullmatch("[0-9a-f]{64}", wrapper[field]) is not None,
            "invalid original training content digest",
        )
    inner = base.restore(wrapper["inner_checkpoint"], wrapper["inner_sha256"])
    base._require(
        wrapper["training_targets_sha256"] == inner["training_targets_sha256"],
        "original and inner target digests differ",
    )
    if wrapper["mode"] == "combined":
        base._require(
            wrapper["training_features_sha256"] == inner["training_features_sha256"],
            "combined original and inner feature digests differ",
        )
    disabled = [index for index in range(8) if index not in active]
    base._require(
        all(
            inner["mean"][index] == 0.0
            and inner["weights"][index] == 0.0
            and inner["scale"][index] == 1.0
            for index in disabled
        ),
        "disabled columns must have zero mean/weight and unit scale",
    )


def checkpoint_sha256(wrapper: dict[str, Any]) -> str:
    _validate_wrapper(wrapper)
    return content_sha256(wrapper)


def restore(wrapper: dict[str, Any], externalpin: str) -> dict[str, Any]:
    """Validate structure and independently retained pin, not the fitting history."""
    base._require(
        type(externalpin) is str and re.fullmatch("[0-9a-f]{64}", externalpin) is not None,
        "invalid external control pin",
    )
    base._require(checkpoint_sha256(wrapper) == externalpin, "external control pin differs")
    return cast(dict[str, Any], json.loads(canonical_json(wrapper)))


def predict(wrapper: dict[str, Any], features: np.ndarray, valid: np.ndarray) -> list[float | None]:
    """Predict uncalibrated scores, rejecting nonzero invalid rows before projection."""
    _validate_wrapper(wrapper)
    original = base._features(features)
    base._require(
        type(valid) is np.ndarray and valid.dtype == np.bool_ and valid.shape == (len(original),),
        "valid must be a boolean row mask",
    )
    base._require(
        bool(np.all(original[~valid] == 0)),
        "invalid original feature rows must be zero placeholders",
    )
    return base.predict(wrapper["inner_checkpoint"], project(features, wrapper["mode"]), valid)
