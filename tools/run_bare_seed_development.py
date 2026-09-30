"""Paired bare depth seed diagnostic; separate from production estimator identities.

Public points are fixed before private joins; only training houses fit the two
bias/covariance models. Correlated seeds and exposed houses are descriptive only.
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import numpy as np
from diagnose_offline_frontend import require, source_identity
from run_instance_affinity import array_bytes, encoded, save_or_verify
from run_soft_position_development import REFERENCES, summarize_rows
from verified_position_parent import add_parent_arguments, verify_position_parent

from cpswm.system.reproducibility import content_sha256

ROOT = Path(__file__).resolve().parents[1]
LABEL_KEYS = {
    "measurement_id",
    "seed_id",
    "eligible",
    "void_reason",
    "object_id",
    "targets",
    "pixel_uv",
    "house_index",
    "split",
    "estimator",
}


def public_points(public):
    """Direct world point from each original grid, without any mask or aggregation."""
    neighborhoods = {n["neighborhood_id"]: n for n in public["neighborhoods"]}
    require(len(neighborhoods) == len(public["neighborhoods"]), "duplicate neighborhood")
    rows = []
    seen = set()
    for seed in public["seeds"]:
        require(
            seed["seed_id"] not in seen and seed["measurement_id"] == seed["seed_id"],
            "duplicate or renamed seed",
        )
        seen.add(seed["seed_id"])
        n = neighborhoods[seed["neighborhood_id"]]
        pixels = [tuple(p) for p in n["pixels_uv"]]
        require(len(set(pixels)) == len(pixels), "duplicate neighborhood pixel")
        index = pixels.index(tuple(seed["pixel_uv"]))
        require(n["valid"][index] is seed["valid"], "seed validity differs")
        point = n["world_points_m"][index]
        require((point is not None) is seed["valid"], "seed point availability differs")
        if point is not None:
            a = np.asarray(point, dtype=float)
            require(a.shape == (3,) and np.isfinite(a).all(), "invalid bare point")
        rows.append(
            dict(
                seed_id=seed["seed_id"],
                measurement_id=seed["measurement_id"],
                neighborhood_id=seed["neighborhood_id"],
                pixel_uv=seed["pixel_uv"],
                available=seed["valid"],
                reason=seed["reason"],
                world_point_m=point,
            )
        )
    return rows


def join_labels(public_rows, labels, house_index, split):
    require(
        labels["house_index"] == house_index and labels["split"] == split,
        "bare label partition differs",
    )
    values = labels["labels"]
    require(len(values) == 2 * len(public_rows), "bare label coverage differs")
    joined = []
    for i, row in enumerate(public_rows):
        a, b = values[2 * i : 2 * i + 2]
        require(
            set(a) == LABEL_KEYS
            and set(b) == LABEL_KEYS
            and a["estimator"] == "soft_affinity"
            and b["estimator"] == "uniform"
            and {k: v for k, v in a.items() if k != "estimator"}
            == {k: v for k, v in b.items() if k != "estimator"},
            "paired estimator label members differ",
        )
        require(
            a["seed_id"] == row["seed_id"]
            and a["measurement_id"] == row["measurement_id"]
            and a["pixel_uv"] == row["pixel_uv"]
            and a["house_index"] == house_index
            and a["split"] == split
            and type(a["eligible"]) is bool
            and (not a["eligible"] or row["available"]),
            "bare seed join differs",
        )
        joined.append({k: v for k, v in a.items() if k != "estimator"})
    return joined


def residual_rows(records, reference):
    rows = []
    for record in records:
        for point, label in zip(record["public"], record["labels"], strict=True):
            if not label["eligible"]:
                continue
            residual = np.asarray(point["world_point_m"]) - np.asarray(label["targets"][reference])
            require(residual.shape == (3,) and np.isfinite(residual).all(), "invalid bare residual")
            rows.append(
                dict(
                    residual=residual.tolist(),
                    member=dict(
                        seed_id=point["seed_id"],
                        measurement_id=point["measurement_id"],
                        frame_sha256=record["frame_sha256"],
                        object_sha256=content_sha256([record["house_index"], label["object_id"]]),
                        house_index=record["house_index"],
                        split=record["split"],
                        pixel_uv=point["pixel_uv"],
                    ),
                )
            )
    return rows


def fit_bare(rows, reference):
    require(
        all(r["member"]["split"] == "train" and 1 <= r["member"]["house_index"] <= 8 for r in rows),
        "bare fit requires original train houses",
    )
    x = np.asarray([r["residual"] for r in rows], dtype=float).reshape(-1, 3)
    reason = None
    if len(x) < 4:
        reason = "fewer_than_four_training_seeds"
    elif not np.isfinite(x).all():
        raise ValueError("nonfinite bare training residual")
    else:
        bias = x.mean(axis=0)
        centered = x - bias
        if np.linalg.matrix_rank(centered) < 3:
            reason = "residual_rank_below_three"
        else:
            covariance = centered.T @ centered / (len(x) - 1)
            try:
                np.linalg.cholesky(covariance)
            except np.linalg.LinAlgError:
                reason = "covariance_not_positive_definite"
            if not np.isfinite(covariance).all():
                reason = "nonfinite_covariance"
    base = dict(
        schema="bare-seed-residual-development@1",
        estimator="bare_seed",
        reference_kind=reference,
        training_seeds=len(x),
        partition="train",
        members_sha256=content_sha256([r["member"] for r in rows]),
        calibrated=False,
        runtime_authority=False,
    )
    if reason is not None:
        return base | dict(status="fit_failed", reason=reason, bias=None, covariance=None)
    return base | dict(
        status="fitted", reason=None, bias=bias.tolist(), covariance=covariance.tolist()
    )


def build(bundle):
    before = source_identity(ROOT)
    records = []
    # All public points first; no private eligibility chooses or removes a seed.
    for ordinal, frame in enumerate(bundle.report["frames"]):
        public = bundle.load_json(f"frames/{ordinal:03d}/public.json")
        records.append(
            dict(
                ordinal=ordinal,
                house_index=frame["house_index"],
                split=frame["split"],
                action_id=frame["action_id"],
                frame_sha256=public["provenance"]["provenance"]["source_sha256"],
                public=public_points(public),
                labels=None,
            )
        )
    for record in records:
        if record["split"] == "train":
            record["labels"] = join_labels(
                record["public"],
                bundle.load_json(f"frames/{record['ordinal']:03d}/labels.json"),
                record["house_index"],
                record["split"],
            )
    training = [r for r in records if r["split"] == "train"]
    artifacts = {}
    models = {}
    for reference in REFERENCES:
        rows = residual_rows(training, reference)
        model = fit_bare(rows, reference)
        models[reference] = model
        artifacts[f"models/{reference}.json"] = encoded(model)
        artifacts[f"training/{reference}/members.json"] = encoded([r["member"] for r in rows])
        artifacts[f"training/{reference}/residuals.npy"] = array_bytes(
            np.asarray([r["residual"] for r in rows], dtype=float).reshape(-1, 3)
        )
    # Corrections for every public point before opening validation labels.
    for record in records:
        for point in record["public"]:
            point["corrected"] = {
                ref: (
                    None
                    if not point["available"] or m["status"] != "fitted"
                    else (np.asarray(point["world_point_m"]) - np.asarray(m["bias"])).tolist()
                )
                for ref, m in models.items()
            }
        artifacts[f"frames/{record['ordinal']:03d}/bare-public.json"] = encoded(record["public"])
    for record in records:
        if record["split"] == "validation":
            record["labels"] = join_labels(
                record["public"],
                bundle.load_json(f"frames/{record['ordinal']:03d}/labels.json"),
                record["house_index"],
                record["split"],
            )
    results = {}
    for reference, model in models.items():
        usable = model if model["status"] == "fitted" else None
        results[reference] = dict(
            by_split={
                s: summarize_rows(
                    residual_rows([r for r in records if r["split"] == s], reference), usable
                )
                for s in ("train", "validation")
            },
            by_house={
                str(h): summarize_rows(
                    residual_rows([r for r in records if r["house_index"] == h], reference), usable
                )
                for h in range(1, 13)
            },
        )
        for split, stats in results[reference]["by_split"].items():
            for estimator in ("soft_affinity", "uniform"):
                matched = bundle.report["results"][estimator + "/" + reference]["by_split"][split]
                require(
                    all(
                        stats[k] == matched[k]
                        for k in ("seeds", "frames", "houses", "objects", "object_frames")
                    ),
                    "paired parent denominator differs",
                )
    frames = []
    for r in records:
        eligible = [
            (p, label)
            for p, label in zip(r["public"], r["labels"], strict=True)
            if label["eligible"]
        ]
        frames.append(
            dict(
                ordinal=r["ordinal"],
                house_index=r["house_index"],
                split=r["split"],
                action_id=r["action_id"],
                seeds=len(r["public"]),
                valid_seeds=sum(p["available"] for p in r["public"]),
                supervised_seeds=len(eligible),
                unique_public_pixels=len({tuple(p["pixel_uv"]) for p in r["public"]}),
                unique_supervised_pixels=len({tuple(p["pixel_uv"]) for p, label in eligible}),
                void_reasons=dict(
                    Counter(label["void_reason"] for label in r["labels"] if not label["eligible"])
                ),
            )
        )
    bundle.assert_unchanged()
    require(source_identity(ROOT) == before, "bare source changed during run")
    import hashlib

    report = dict(
        schema="bare-seed-position-development@1",
        source_files=before,
        parent_binding=bundle.binding,
        frames=frames,
        results=results,
        aggregation_parent_comparison=bundle.report["results"],
        model_status={k: dict(status=v["status"], reason=v["reason"]) for k, v in models.items()},
        runtime_authority=False,
        calibrated=False,
        natural_identity=False,
        formal_reference_selected=False,
        interpretation="Same original seeds and dual references; "
        "correlated/exposed descriptive development. "
        "No estimator selection, online factor change, independent calibration or action benefit.",
        members={k: hashlib.sha256(v).hexdigest() for k, v in artifacts.items()},
    )
    artifacts["report.json"] = encoded(report)
    return artifacts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_parent_arguments(parser)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    require(not args.output.is_symlink(), "symlink bare output")
    output = args.output.resolve()
    for value in (
        args.parent_position_results,
        args.parent_position_source,
        args.collection,
        args.affinity_results,
        args.controls_results,
        args.frontends,
        ROOT,
    ):
        value = value.resolve()
        require(
            not output.is_relative_to(value) and not value.is_relative_to(output),
            "bare input and output must be disjoint",
        )
    require(args.verify or not output.exists(), "refuse bare output overwrite")
    bundle = verify_position_parent(args)
    save_or_verify(output, build(bundle), verify=args.verify)
    print("bare seed paired development complete; no runtime authority", flush=True)


if __name__ == "__main__":
    main()
