"""Empirical joint-success action table, fit only from declared development data.

An outcome is the isolated evaluator's identity AND AABB decision. Counts are
not calibrated probabilities or independent-frame sample sizes. Missing cells
stay unsupported; no invented likelihoods or bonus for mere detector confidence.
"""

from __future__ import annotations

from typing import Any

from cpswm.system.reproducibility import content_sha256

SCHEMA = "surface-action-joint-frequency-development@1"


def state_key(category: str, ordinal: int, status: str) -> str:
    return content_sha256((category, ordinal, status))


def fit(rows: list[dict[str, Any]], *, training_manifest: str) -> dict[str, Any]:
    if not rows or len(training_manifest) != 64:
        raise ValueError("nonempty declared training rows and manifest required")
    cells: dict[str, dict[str, Any]] = {}
    seen = set()
    for r in rows:
        if set(r) != {
            "category",
            "ordinal",
            "status",
            "action",
            "degrees",
            "joint_success",
            "source_pair",
        }:
            raise ValueError("malformed development transition")
        if (
            type(r["joint_success"]) is not bool
            or type(r["ordinal"]) is not int
            or r["ordinal"] < 0
        ):
            raise ValueError("explicit adjudicated joint outcome required")
        key = state_key(r["category"], r["ordinal"], r["status"])
        action = content_sha256((r["action"], r["degrees"]))
        duplicate = (key, action, r["source_pair"])
        if duplicate in seen:
            continue
        seen.add(duplicate)
        cell = cells.setdefault(key, {}).setdefault(
            action, dict(action=r["action"], degrees=r["degrees"], count=0, successes=0)
        )
        cell["count"] += 1
        cell["successes"] += int(r["joint_success"])
    model = dict(
        schema=SCHEMA,
        training_manifest=training_manifest,
        cells=cells,
        unique_transition_count=len(seen),
        calibrated=False,
    )
    return model


def validate(model: dict[str, Any], pin: str) -> dict[str, Any]:
    if (
        content_sha256(model) != pin
        or set(model)
        != {"schema", "training_manifest", "cells", "unique_transition_count", "calibrated"}
        or model["schema"] != SCHEMA
        or model["calibrated"] is not False
    ):
        raise ValueError("empirical model pin/schema differs")
    for group in model["cells"].values():
        for action, c in group.items():
            if (
                set(c) != {"action", "degrees", "count", "successes"}
                or type(c["count"]) is not int
                or type(c["successes"]) is not int
                or not 0 <= c["successes"] <= c["count"]
                or c["count"] < 1
                or action != content_sha256((c["action"], c["degrees"]))
            ):
                raise ValueError("invalid empirical outcome counts")
    return model


def forecast(
    model: dict[str, Any], *, category: str, ordinal: int, status: str, action: str, degrees: float
) -> dict[str, Any] | None:
    c = (
        model["cells"]
        .get(state_key(category, ordinal, status), {})
        .get(content_sha256((action, degrees)))
    )
    if c is None:
        return None
    return dict(probability=c["successes"] / c["count"], support_count=c["count"], calibrated=False)
