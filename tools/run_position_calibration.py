"""Pinned preparation, training-only fit, public inference, then isolated scoring.

A development conditional-position comparison, never natural task success.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from cpswm.perception_mapping.calibrated_position import (
    CameraCoordinates,
    PositionCalibration,
    TrainingRow,
    fit,
    posterior,
)
from cpswm.perception_mapping.unity_rgbd import CameraSelfPose
from cpswm.system.reproducibility import content_sha256

ESTIMATORS = ("bare_seed", "soft_affinity", "uniform")
REFERENCES = ("sdk_aabb_center_m", "sdk_transform_position_m")
ARMS = {
    "old": (False, False),
    "prior_only": (True, False),
    "error_only": (False, True),
    "both": (True, True),
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text())


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n")


def checked(path, expected):
    if digest(path) != expected:
        raise ValueError(f"input digest differs: {path}")
    return load(path)


def panel(frames):
    if len(frames) != 96 or [f["index"] for f in frames] != list(range(96)):
        raise ValueError("complete ordered 96-frame panel required")


def unique_rows(rows):
    result = {r["key"]: r for r in rows}
    if len(result) != len(rows):
        raise ValueError("duplicate public/evaluation row key")
    return result


def point3(value):
    a = np.asarray(value, dtype=float)
    if a.shape != (3,) or not np.isfinite(a).all():
        raise ValueError("finite three-dimensional point required")
    return a


def prepare(parent, parent_pin, collection, collection_pin, output):
    if output.exists():
        raise ValueError("output must be new")
    ledger = checked(parent / "case-results.json", parent_pin)
    files = {
        str(p.relative_to(parent / "experiment")): digest(p)
        for p in (parent / "experiment").rglob("*")
        if p.is_file()
    }
    if len(ledger) != 2 or any(c["exit_code"] != 0 or c["output_sha256"] != files for c in ledger):
        raise ValueError("parent complete run/replay inventory differs")
    inventory = checked(collection / "inventory.json", collection_pin)
    report = load(parent / "experiment/report.json")
    training = {f"{e}/{r}": [] for e in ESTIMATORS for r in REFERENCES}
    publics, labels = [], []
    for index, frame in enumerate(report["frames"]):
        house, local = index // 8 + 1, index % 8
        split = "train" if house <= 8 else "validation"
        if (frame["house_index"], frame["split"], frame["prefix"]) != (
            house,
            split,
            f"frames/{index:03d}",
        ):
            raise ValueError("fixed development partition differs")
        public = load(parent / "experiment" / frame["prefix"] / "public.json")
        private = load(parent / "experiment" / frame["prefix"] / "labels.json")
        public_pin = content_sha256(public)
        if private["readout_sha256"] != public_pin or (
            private["house_index"],
            private["split"],
        ) != (house, split):
            raise ValueError("parent public/private pairing differs")
        camera = CameraSelfPose.model_validate(public["provenance"]["camera"])
        pose = CameraCoordinates(
            position_m=camera.position_m,
            yaw_degrees=camera.yaw_degrees,
            pitch_degrees=camera.pitch_degrees,
        )
        sdk_rel = f"house-{house:02d}/unity-logs/evaluator_only/sdk-events/{local + 4:03d}.json"
        sdk = checked(collection / sdk_rel, inventory[sdk_rel])
        if sdk["owner"] != str(camera.action_id):
            raise ValueError("SDK event is not the public exposure")
        objects = {o["objectId"]: o for o in sdk["metadata"]["objects"]}
        observations = {(o["estimator"], o["seed_id"]): o for o in public["observations"]}
        annotations = {(r["estimator"], r["seed_id"]): r for r in private["labels"]}
        if (
            len(observations) != len(public["observations"])
            or len(annotations) != len(private["labels"])
            or set(observations) != set(annotations)
        ):
            raise ValueError("complete seed/estimator pairing differs")
        neighborhoods = {n["neighborhood_id"]: n for n in public["neighborhoods"]}
        # Identical public first-valid-seed rule, evaluated without private labels.
        candidate_seeds = {}
        for seed in public["seeds"]:
            if seed["valid"]:
                for source in seed["sources"]:
                    key = (source["method"], source["id"])
                    candidate_seeds.setdefault(key, []).append(
                        (tuple(seed["pixel_uv"]), seed["seed_id"])
                    )
        first_seeds = {min(v)[1] for v in candidate_seeds.values()}
        entries, eval_rows = [], []
        for seed in public["seeds"]:
            n = neighborhoods[seed["neighborhood_id"]]
            bare = n["world_points_m"][n["pixels_uv"].index(seed["pixel_uv"])]
            for estimator in ESTIMATORS:
                obs = observations[
                    ("soft_affinity" if estimator == "bare_seed" else estimator, seed["seed_id"])
                ]
                label = annotations[
                    ("soft_affinity" if estimator == "bare_seed" else estimator, seed["seed_id"])
                ]
                point = bare if estimator == "bare_seed" else obs["world_point_m"]
                readout_pin = (
                    content_sha256(
                        dict(schema="bare-grid-world-point@1", definition=public["definition"])
                    )
                    if estimator == "bare_seed"
                    else public["estimator_pins"][estimator]
                )
                key = f"{estimator}:{seed['seed_id']}"
                entries.append(
                    dict(
                        key=key,
                        estimator=estimator,
                        point_m=point,
                        readout_sha256=readout_pin,
                        fixed_first_seed=seed["seed_id"] in first_seeds,
                    )
                )
                bounds = None
                if label["eligible"]:
                    obj = objects[label["object_id"]]
                    for ref, position in (
                        ("sdk_aabb_center_m", obj["axisAlignedBoundingBox"]["center"]),
                        ("sdk_transform_position_m", obj["position"]),
                    ):
                        if list(position[a] for a in ("x", "y", "z")) != label["targets"][ref]:
                            raise ValueError("SDK reference and pinned label differ")
                    corners = obj["axisAlignedBoundingBox"]["cornerPoints"]
                    bounds = dict(
                        lower=[min(p[i] for p in corners) for i in range(3)],
                        upper=[max(p[i] for p in corners) for i in range(3)],
                    )
                    if house <= 8:
                        for reference in REFERENCES:
                            row = TrainingRow(
                                partition="train",
                                house_index=house,
                                object_key=label["object_id"],
                                frame_key=public["input_sha256"],
                                measurement_key=key,
                                public_sha256=public_pin,
                                label_sha256=content_sha256(label),
                                readout_sha256=readout_pin,
                                camera=pose,
                                observed_world_m=point,
                                reference_world_m=label["targets"][reference],
                            )
                            training[f"{estimator}/{reference}"].append(row.model_dump(mode="json"))
                eval_rows.append(
                    dict(
                        key=key,
                        eligible=label["eligible"],
                        void_reason=label["void_reason"],
                        object_id=label["object_id"],
                        targets=label["targets"],
                        bounds=bounds,
                    )
                )
        publics.append(
            dict(
                index=index,
                camera=pose.model_dump(mode="json"),
                input_sha256=public["input_sha256"],
                candidate_count=len(public["candidates"]),
                entries=entries,
            )
        )
        labels.append(
            dict(
                index=index,
                house_index=house,
                partition=split,
                rows=eval_rows,
                source_sdk_sha256=inventory[sdk_rel],
                eligible_visible_objects=sum(
                    r["eligible"] and r["pixels"] > 0 for r in private["instances"]
                ),
            )
        )
        print(json.dumps(dict(phase="prepared_frame", index=index)), flush=True)
    if len(publics) != 96:
        raise ValueError("complete 96-frame panel required")
    save(output / "training.json", dict(parent_sha256=parent_pin, rows=training))
    save(output / "public.json", publics)
    save(output / "evaluation.json", labels)
    save(
        output / "inputs.json",
        dict(
            parent_ledger_sha256=parent_pin,
            collection_inventory_sha256=collection_pin,
            files={p.name: digest(p) for p in output.glob("*.json")},
        ),
    )
    print(
        json.dumps(
            dict(
                phase="prepared",
                frames=len(publics),
                training_counts={k: len(v) for k, v in training.items()},
            )
        ),
        flush=True,
    )


def train(data, pin, output):
    if output.exists():
        raise ValueError("model output must be new")
    data = checked(data, pin)
    if set(data["rows"]) != {f"{e}/{r}" for e in ESTIMATORS for r in REFERENCES}:
        raise ValueError("complete estimator/reference factorial required")
    results = {}
    for key, rows in sorted(data["rows"].items()):
        estimator, reference = key.split("/")
        try:
            model = fit(
                tuple(TrainingRow.model_validate(r) for r in rows),
                estimator=estimator,
                reference=reference,
                parent_artifact_sha256=data["parent_sha256"],
            )
            results[key] = dict(
                status="FITTED", model=model.model_dump(mode="json"), pin=model.digest
            )
        except ValueError as error:
            results[key] = dict(status="FIT_FAILED", error=str(error))
    save(output, dict(training_file_sha256=pin, results=results))
    print(json.dumps({k: v["status"] for k, v in results.items()}), flush=True)


def predict(public, public_pin, models, model_pin, output):
    if output.exists():
        raise ValueError("predictions output must be new")
    frames = checked(public, public_pin)
    bundle = checked(models, model_pin)
    panel(frames)
    if set(bundle["results"]) != {f"{e}/{r}" for e in ESTIMATORS for r in REFERENCES}:
        raise ValueError("complete estimator/reference model bundle required")
    results = []
    for frame in frames:
        unique_rows(frame["entries"])
        pose = CameraCoordinates.model_validate(frame["camera"])
        rows = []
        # With a fixed camera and prior, the posterior mean is an affine map of y.
        maps = {}
        for key, item in bundle["results"].items():
            if item["status"] != "FITTED":
                if item["status"] != "FIT_FAILED":
                    raise ValueError("unknown model status")
                continue
            model = PositionCalibration.model_validate(item["model"])
            if key != f"{model.estimator}/{model.reference}":
                raise ValueError("model bundle key differs from bound model")
            for arm, (use_prior, use_error) in ARMS.items():

                def mean(
                    point,
                    model=model,
                    pin=item["pin"],
                    pose=pose,
                    use_prior=use_prior,
                    use_error=use_error,
                ):
                    return np.asarray(
                        posterior(
                            model,
                            pin,
                            (pose,),
                            (point,),
                            use_prior=use_prior,
                            use_error=use_error,
                            rho=0.5,
                        ).mean
                    )

                zero = mean((0.0, 0.0, 0.0))
                matrix = np.column_stack([mean(tuple(p)) - zero for p in np.eye(3)])
                maps[key, arm] = (zero, matrix)
        for entry in frame["entries"]:
            if entry["estimator"] not in ESTIMATORS or type(entry["fixed_first_seed"]) is not bool:
                raise ValueError("invalid public estimator or seed selection")
            if entry["point_m"] is not None:
                point3(entry["point_m"])
            predictions = {}
            for reference in REFERENCES:
                key = f"{entry['estimator']}/{reference}"
                item = bundle["results"][key]
                if (
                    item["status"] == "FITTED"
                    and item["model"]["readout_sha256"] != entry["readout_sha256"]
                ):
                    raise ValueError("public readout differs from fitted residual profile")
                predictions[reference] = {}
                for arm in ARMS:
                    if entry["point_m"] is None or (key, arm) not in maps:
                        value = None
                    else:
                        zero, matrix = maps[key, arm]
                        value = (zero + matrix @ entry["point_m"]).tolist()
                    predictions[reference][arm] = value
            rows.append(
                dict(
                    key=entry["key"],
                    estimator=entry["estimator"],
                    fixed_first_seed=entry["fixed_first_seed"],
                    raw_point_m=entry["point_m"],
                    predictions=predictions,
                )
            )
        results.append(dict(index=frame["index"], rows=rows))
    save(output, dict(public_sha256=public_pin, models_sha256=model_pin, frames=results))
    print(json.dumps(dict(phase="public_predictions", frames=len(results))), flush=True)


def evaluate(predictions, prediction_pin, evaluation, evaluation_pin, output):
    scored_output = output.with_name("scored-rows.json")
    if output.exists() or scored_output.exists() or output == scored_output:
        raise ValueError("evaluation report and scored-row outputs must both be new and distinct")
    predictions = checked(predictions, prediction_pin)
    labels = checked(evaluation, evaluation_pin)
    panel(predictions["frames"])
    panel(labels)
    scores = []
    for p, g in zip(predictions["frames"], labels, strict=True):
        truth = unique_rows(g["rows"])
        if p["index"] != g["index"] or set(unique_rows(p["rows"])) != set(truth):
            raise ValueError("prediction/evaluation frame support differs")
        house = g["index"] // 8 + 1
        if (g["house_index"], g["partition"]) != (
            house,
            "train" if house <= 8 else "validation",
        ):
            raise ValueError("evaluation partition differs")
        for row in p["rows"]:
            label = truth[row["key"]]
            if (
                row["estimator"] not in ESTIMATORS
                or type(row["fixed_first_seed"]) is not bool
                or type(label["eligible"]) is not bool
                or set(row["predictions"]) != set(REFERENCES)
            ):
                raise ValueError("invalid prediction/evaluation record")
            if label["eligible"]:
                lower = point3(label["bounds"]["lower"])
                upper = point3(label["bounds"]["upper"])
                if np.any(lower > upper):
                    raise ValueError("inverted evaluation box")
            for ref in REFERENCES:
                if set(row["predictions"][ref]) != set(ARMS):
                    raise ValueError("complete four-arm predictions required")
                if label["eligible"]:
                    point3(label["targets"][ref])
                for arm, point in {"raw": row["raw_point_m"], **row["predictions"][ref]}.items():
                    if point is not None:
                        point3(point)
                    status = (
                        "UNADJUDICATED"
                        if not label["eligible"]
                        else "MISSING"
                        if point is None
                        else "SCORED"
                    )
                    inside = False
                    error = None
                    if status == "SCORED":
                        inside = all(
                            a <= v <= b
                            for v, a, b in zip(
                                point,
                                label["bounds"]["lower"],
                                label["bounds"]["upper"],
                                strict=True,
                            )
                        )
                        error = float(np.linalg.norm(np.asarray(point) - label["targets"][ref]))
                    scores.append(
                        dict(
                            house=g["house_index"],
                            partition=g["partition"],
                            frame=p["index"],
                            key=row["key"],
                            estimator=row["estimator"],
                            reference=ref,
                            arm=arm,
                            fixed_first_seed=row["fixed_first_seed"],
                            object_id=label["object_id"],
                            status=status,
                            inside=inside,
                            error_m=error,
                        )
                    )
    summaries = {}
    for partition in ("train", "validation"):
        for estimator in ESTIMATORS:
            for ref in REFERENCES:
                for arm in ("raw", *ARMS):
                    for selection in ("all_seeds", "fixed_first_seed"):
                        rows = [
                            r
                            for r in scores
                            if r["partition"] == partition
                            and r["estimator"] == estimator
                            and r["reference"] == ref
                            and r["arm"] == arm
                            and (selection == "all_seeds" or r["fixed_first_seed"])
                        ]
                        valid = [r for r in rows if r["status"] == "SCORED"]
                        key = "/".join((partition, estimator, ref, arm, selection))
                        summaries[key] = dict(
                            public_rows=len(rows),
                            adjudicated=len(valid),
                            unadjudicated=sum(r["status"] == "UNADJUDICATED" for r in rows),
                            missing=sum(r["status"] == "MISSING" for r in rows),
                            inside=sum(r["inside"] for r in rows),
                            conditional_inside_rate=None
                            if not valid
                            else sum(r["inside"] for r in valid) / len(valid),
                            inside_over_all_public=None
                            if not rows
                            else sum(r["inside"] for r in rows) / len(rows),
                            rmse_m=None
                            if not valid
                            else float(np.sqrt(np.mean([r["error_m"] ** 2 for r in valid]))),
                            objects=len({(r["house"], r["object_id"]) for r in valid}),
                            object_frames=len(
                                {(r["house"], r["frame"], r["object_id"]) for r in valid}
                            ),
                            houses=sorted({r["house"] for r in valid}),
                        )
    save(
        output,
        dict(
            scope="conditional position diagnostics, not natural joint task success",
            prediction_sha256=prediction_pin,
            evaluation_sha256=evaluation_pin,
            selection="all seeds and separately public first seed; no oracle seed selection",
            frames=len(labels),
            frame_manifest=[
                dict(
                    index=g["index"],
                    house=g["house_index"],
                    partition=g["partition"],
                    public_rows=len(p["rows"]),
                    eligible_visible_objects=g["eligible_visible_objects"],
                )
                for p, g in zip(predictions["frames"], labels, strict=True)
            ],
            no_public_seed_frames=sum(not p["rows"] for p in predictions["frames"]),
            summaries=summaries,
        ),
    )
    save(scored_output, scores)
    print(
        json.dumps(dict(phase="evaluated", frames=len(labels), score_rows=len(scores))), flush=True
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="mode", required=True)
    s = sub.add_parser("prepare")
    s.add_argument("parent", type=Path)
    s.add_argument("collection", type=Path)
    s.add_argument("output", type=Path)
    s.add_argument("--parent-pin", required=True)
    s.add_argument("--collection-pin", required=True)
    s = sub.add_parser("train")
    s.add_argument("data", type=Path)
    s.add_argument("output", type=Path)
    s.add_argument("--pin", required=True)
    s = sub.add_parser("predict")
    s.add_argument("public", type=Path)
    s.add_argument("models", type=Path)
    s.add_argument("output", type=Path)
    s.add_argument("--public-pin", required=True)
    s.add_argument("--model-pin", required=True)
    s = sub.add_parser("evaluate")
    s.add_argument("predictions", type=Path)
    s.add_argument("evaluation", type=Path)
    s.add_argument("output", type=Path)
    s.add_argument("--prediction-pin", required=True)
    s.add_argument("--evaluation-pin", required=True)
    a = p.parse_args()
    if a.mode == "prepare":
        prepare(a.parent, a.parent_pin, a.collection, a.collection_pin, a.output)
    elif a.mode == "train":
        train(a.data, a.pin, a.output)
    elif a.mode == "predict":
        predict(a.public, a.public_pin, a.models, a.model_pin, a.output)
    else:
        evaluate(a.predictions, a.prediction_pin, a.evaluation, a.evaluation_pin, a.output)
