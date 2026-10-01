"""Uncalibrated, conditional appearance/geometry routing for a single frame pair.

These normalized energies are development branch gates, not learned identity
probabilities. All reference candidates are possible initial target anchors;
that initial semantic association remains controlled. No detector score enters
an energy. Geometry and position are one declared composite model, not two
independently calibrated measurements. Missing support grants no absence fact.
"""

from __future__ import annotations

from math import exp, log
from typing import Any

import numpy as np

from cpswm.perception_mapping.natural_vision import decode_rgb as decode_rgb
from cpswm.system.natural_candidate_position import OBSERVATION_KEYS as OBSERVATION_KEYS

MODEL = "appearance-rgb-histogram-surface-geometry-development@1"
CONFIG = dict(histogram_bins=8, appearance_scale=0.25, geometry_scale_m=0.5, unknown_logit=-2.0)


def logsum(values: list[float]) -> float:
    top = max(values)
    return top + log(sum(exp(v - top) for v in values))


def candidates(readout: dict[str, Any], raw: Any, cutoff: Any) -> list[dict[str, Any]]:
    """Every detector candidate; one deterministic surface representative each."""
    _, rgb = decode_rgb(raw, cutoff=cutoff)
    surface = readout["surface"]
    rows = []
    for candidate in readout["frame"].candidates:
        x0, y0, x1, y1 = candidate.box_xyxy
        crop = rgb[int(y0) : int(np.ceil(y1)), int(x0) : int(np.ceil(x1))]
        if not crop.size:
            raise ValueError("candidate appearance crop is empty")
        histogram = np.concatenate(
            [
                np.histogram(crop[:, :, c], bins=CONFIG["histogram_bins"], range=(0, 256))[0]
                for c in range(3)
            ]
        ).astype(np.float64)
        histogram /= histogram.sum()
        eligible = [
            seed
            for seed in surface["seeds"]
            if seed["valid"]
            and any(p["id"] == str(candidate.candidate_id) for p in seed["sources"])
        ]
        observation = None
        if eligible:
            seed = min(eligible, key=lambda s: tuple(s["pixel_uv"]))
            # The protected natural readout's selected estimator is fixed by model.
            estimator = readout["selected"]["observation"]["estimator"]
            value = next(
                o
                for o in surface["observations"]
                if o["seed_id"] == seed["seed_id"] and o["estimator"] == estimator
            )
            observation = {k: value[k] for k in OBSERVATION_KEYS}
        rows.append(
            dict(
                id=str(candidate.candidate_id),
                category=candidate.category,
                histogram=histogram.tolist(),
                observation=observation,
            )
        )
    return sorted(rows, key=lambda row: row["id"])


def associate(reference: list[dict[str, Any]], query: list[dict[str, Any]]) -> dict[str, Any]:
    """Keep query alternatives and all reference comparisons; no argmax collapse.

    Divide by *all* reference/query counts before normalization so duplicating
    equally plausible candidates does not create extra total known mass. Unknown
    always has finite log support. Category mismatch/invalid depth routes unknown.
    """
    if not reference or not query:
        raise ValueError("association support unavailable; no negative evidence authorized")
    pairs, branches = [], []
    divisor = log(len(reference)) + log(len(query))
    for q in query:
        scores = []
        for r in reference:
            compatible = r["category"] == q["category"] and all(
                c["observation"] is not None for c in (r, q)
            )
            item = dict(reference_id=r["id"], query_id=q["id"], compatible=compatible)
            if compatible:
                appearance = float(
                    np.linalg.norm(np.sqrt(r["histogram"]) - np.sqrt(q["histogram"])) / np.sqrt(2.0)
                )
                distance = float(
                    np.linalg.norm(
                        np.asarray(r["observation"]["world_point_m"])
                        - np.asarray(q["observation"]["world_point_m"])
                    )
                )
                score = -0.5 * (
                    (appearance / CONFIG["appearance_scale"]) ** 2
                    + (distance / CONFIG["geometry_scale_m"]) ** 2
                )
                scores.append(score)
                item.update(
                    appearance_distance=appearance, surface_distance_m=distance, log_energy=score
                )
            pairs.append(item)
        if scores:
            branches.append(
                dict(
                    query_id=q["id"],
                    log_energy=logsum(scores) - divisor,
                    observation=q["observation"],
                )
            )
    denominator = logsum([float(CONFIG["unknown_logit"]), *(b["log_energy"] for b in branches)])
    for b in branches:
        b["log_gate"] = b["log_energy"] - denominator
    return dict(
        model=MODEL,
        config=dict(CONFIG),
        comparisons=pairs,
        branches=branches,
        unknown_log_gate=float(CONFIG["unknown_logit"]) - denominator,
        calibration="UNCALIBRATED_COMPOSITE_DEVELOPMENT_ENERGY",
        initial_anchor="ALL_REFERENCE_CANDIDATES_CONTROLLED_SEMANTIC_TARGET_SUPPORT",
        detector_scores_used=False,
        reference_is_likelihood=False,
    )
