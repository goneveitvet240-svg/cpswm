"""Fixed public surface readouts and dual-reference 3D residual development.

No mask selects a public seed or estimator. Labels train/evaluate residuals only;
these conditional errors do not authorize world identity or a natural producer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
from collections import Counter
from pathlib import Path

import numpy as np
from diagnose_offline_frontend import digest, inventory, require, source_identity
from instance_affinity_dataset import public_frame
from position_factor_diagnostic import diagnose
from run_instance_affinity import array_bytes, encoded, save_or_verify, verify_frontends
from run_instance_affinity_controls import verify_parent as verify_affinity
from soft_position_dataset import label_readout, public_readout
from verify_offline_factor_capture import _json, _public

from cpswm.data_preflight import instance_affinity as affinity
from cpswm.data_preflight.soft_surface_position import DOMAIN, ESTIMATORS
from cpswm.perception_mapping import position_observation_model as position
from cpswm.system.reproducibility import content_sha256

ROOT = Path(__file__).resolve().parents[1]
REFERENCES = ("sdk_transform_position_m", "sdk_aabb_center_m")


def verify_controls(directory, *, ledger_pin, source):
    require(not directory.is_symlink() and not source.is_symlink(), "symlink controls path")
    ledger = directory / "case-results.json"
    require(not ledger.is_symlink() and digest(ledger) == ledger_pin, "controls ledger pin differs")
    cases = _json(ledger)
    require(
        type(cases) is list
        and len(cases) == 2
        and [c["phase"] for c in cases] == ["run", "verify"]
        and all(type(c["exit_code"]) is int and c["exit_code"] == 0 for c in cases)
        and len({c["source_sha"] for c in cases}) == 1
        and re.fullmatch("[0-9a-f]{40}", cases[0]["source_sha"]) is not None,
        "controls require successful run and complete fresh replay",
    )
    files = inventory(directory / "experiment")
    modes = ("rgb_only", "geometry_only", "combined")
    names = (
        {"report.json"}
        | {f"models/{m}.json" for m in modes}
        | {f"frames/{i:03d}/{m}.npy" for i in range(96) for m in modes}
    )
    require(
        set(files) == names and all(c["output_sha256"] == files for c in cases),
        "controls output members differ",
    )
    report = _json(directory / "experiment/report.json")
    require(
        report["source_files"] == source_identity(source)
        and report["members"] == {k: v for k, v in files.items() if k != "report.json"}
        and report["schema"] == "instance-affinity-feature-controls@1"
        and report["modes"] == list(modes)
        and report["training_performed"] is True
        and report["combined_exact_parent_model_and_predictions"] is True
        and all(
            report[k] is False
            for k in ("runtime_authority", "calibrated", "observation_likelihood_written")
        ),
        "controls source, definition or authority differs",
    )
    require(
        [(f["house_index"], f["split"], f["prefix"]) for f in report["frames"]]
        == [
            (h, "train" if h <= 8 else "validation", f"frames/{(h - 1) * 8 + t:03d}")
            for h in range(1, 13)
            for t in range(8)
        ]
        and len({f["action_id"] for f in report["frames"]}) == 96,
        "controls fixed frame schedule differs",
    )
    return report, dict(
        ledger_sha256=ledger_pin,
        actual_source_sha=cases[0]["source_sha"],
        source_files=report["source_files"],
        output_files=files,
    )


def fresh_controls(args, expected):
    source = args.controls_source.resolve()
    script = source / "tools/run_instance_affinity_controls.py"
    require(script.is_file() and not script.is_symlink(), "historical controls CLI missing")
    command = [str(args.historical_python.absolute()), str(script)]
    for name in (
        "affinity_results",
        "affinity_source",
        "historical_python",
        "collection",
        "capture_source",
        "archive",
        "sdk_python",
        "binary",
        "frontends",
        "frontend_source",
    ):
        value = getattr(args, name)
        value = value.absolute() if name in ("sdk_python", "historical_python") else value.resolve()
        command.extend(["--" + name.replace("_", "-"), str(value)])
    for name in ("affinity_ledger_sha256", "inventory_sha256", "frontend_ledger_sha256"):
        command.extend(["--" + name.replace("_", "-"), getattr(args, name)])
    command.extend(["--output", str(args.controls_results.resolve() / "experiment"), "--verify"])
    environment = os.environ.copy()
    environment.update(
        PYTHONPATH=os.pathsep.join(str(source / p) for p in ("src", "tools")),
        OPENBLAS_NUM_THREADS="1",
    )
    result = subprocess.run(command, cwd=source, env=environment, check=False, timeout=1800)
    require(result.returncode == 0, "historical controls fresh refit failed")
    _, after = verify_controls(
        args.controls_results, ledger_pin=args.controls_ledger_sha256, source=args.controls_source
    )
    require(after == expected, "controls changed during fresh refit")


def private_readout(directory, record, model, pin, audit):
    private = directory / f"house-{record['house_index']:02d}/unity-logs/evaluator_only"
    offset = record["sdk_index"]
    with np.load(private / f"instances/{offset:03d}-masks.npz", allow_pickle=False) as masks:
        return label_readout(
            record["record"],
            record["public"],
            _json(private / f"sdk-events/{offset:03d}.json"),
            _json(private / f"instances/{offset:03d}.json"),
            masks,
            np.load(private / f"instances/{offset:03d}-segmentation.npy", allow_pickle=False),
            [r for r in audit["instances"] if r["house_index"] == record["house_index"]],
            affinity_model=model,
            affinity_pin=pin,
            sdk_rgb_bytes=(private / f"sdk-events/{offset:03d}-rgb.npy").read_bytes(),
            sdk_depth_bytes=(private / f"sdk-events/{offset:03d}-depth.npy").read_bytes(),
        )


def collect_public(directory, frontends, parent_directory, parent_report, model, pin):
    records = []
    for house in range(1, 13):
        folder = directory / f"house-{house:02d}"
        capture = _json(folder / "capture.json")
        raw, _ = _public(folder / "public", capture["provenance"])
        require(len(raw) == 8, "fixed house must retain eight frames")
        for local, (command, delivery, _) in enumerate(raw):
            ordinal = (house - 1) * 8 + local
            record = public_frame(command, delivery, {m: frontends[m][ordinal] for m in frontends})
            expected = parent_report["frames"][ordinal]
            require(expected["action_id"] == record["action_id"], "parent action differs")
            for name, value in (
                ("features", record["X"]),
                ("pairs", record["pairs"]),
                ("valid", record["valid"]),
            ):
                require(
                    array_bytes(value)
                    == (parent_directory / expected["prefix"] / f"{name}.npy").read_bytes(),
                    "reconstructed public pair inputs differ from fixed parent",
                )
            public = public_readout(record, model, pin)
            require(
                np.array_equal(
                    np.asarray(public["pairs"], dtype=np.int64).reshape(-1, 4), record["pairs"]
                ),
                "readout public pairs differ",
            )
            require(
                array_bytes(
                    np.asarray(
                        [np.nan if p is None else p for p in public["pair_scores"]],
                        dtype=np.float64,
                    )
                )
                == (parent_directory / expected["prefix"] / "scores.npy").read_bytes(),
                "readout scores differ from fixed combined model",
            )
            records.append(
                dict(
                    prefix=expected["prefix"],
                    house_index=house,
                    sdk_index=local + 4,
                    split="train" if house <= 8 else "validation",
                    action_id=record["action_id"],
                    record=record,
                    public=public,
                )
            )
    require(
        len(records) == 96 and len({r["action_id"] for r in records}) == 96,
        "public fixed frame coverage differs",
    )
    print(json.dumps(dict(phase="all_public_surface_readouts", frames=96)), flush=True)
    return records


def paired_rows(records, estimator, reference):
    rows = []
    for record in records:
        public, private = record["public"], record["labels"]
        require(
            (private["house_index"], private["split"]) == (record["house_index"], record["split"]),
            "label partition differs",
        )
        for obs, label in zip(public["observations"], private["labels"], strict=True):
            require(
                (obs["measurement_id"], obs["estimator"])
                == (label["measurement_id"], label["estimator"]),
                "label pairing differs",
            )
            if obs["estimator"] != estimator or not label["eligible"]:
                continue
            require(
                obs["available"] is True and label["void_reason"] is None,
                "labelled seed is not publicly available",
            )
            truth = np.asarray(label["targets"][reference], dtype=np.float64)
            error = np.asarray(obs["world_point_m"], dtype=np.float64) - truth
            require(error.shape == (3,) and np.isfinite(error).all(), "invalid position residual")
            member = dict(
                measurement_id=obs["measurement_id"],
                house_index=record["house_index"],
                frame_sha256=content_sha256(record["record"]["public_metadata"]),
                object_sha256=content_sha256((record["house_index"], label["object_id"])),
                input_sha256=public["input_sha256"],
                label_sha256=content_sha256(
                    (
                        label,
                        private["readout_sha256"],
                        private["instances"],
                        private["private_lineage_sha256"],
                    )
                ),
                split=record["split"],
            )
            rows.append(dict(observation=obs, label=label, member=member, residual=error))
    return rows


def metric(errors, model=None):
    if not len(errors):
        return dict(
            seeds=0,
            euclidean_rmse_m=None,
            axis_rmse_m=None,
            median_euclidean_error_m=None,
            maximum_euclidean_error_m=None,
            mean_nll=None,
            mean_squared_mahalanobis=None,
        )
    errors = np.asarray(errors, dtype=np.float64)
    require(
        errors.ndim == 2 and errors.shape[1] == 3 and np.isfinite(errors).all(),
        "invalid scoring residuals",
    )
    norms = np.linalg.norm(errors, axis=1)
    result = dict(
        seeds=len(errors),
        euclidean_rmse_m=float(np.sqrt(np.mean(norms**2))),
        axis_rmse_m=np.sqrt(np.mean(errors**2, axis=0)).tolist(),
        median_euclidean_error_m=float(np.median(norms)),
        maximum_euclidean_error_m=float(norms.max()),
        mean_nll=None,
        mean_squared_mahalanobis=None,
    )
    if model is not None:
        covariance = np.asarray(model["covariance"], dtype=np.float64)
        square = np.sum(errors * np.linalg.solve(covariance, errors.T).T, axis=1)
        sign, logdet = np.linalg.slogdet(covariance)
        require(sign == 1, "invalid model covariance determinant")
        nll = 0.5 * (3 * math.log(2 * math.pi) + logdet + square)
        require(np.isfinite(nll).all(), "nonfinite residual likelihood")
        result.update(mean_nll=float(nll.mean()), mean_squared_mahalanobis=float(square.mean()))
    return result


def summarize_rows(rows, model):
    errors = np.asarray([r["residual"] for r in rows], dtype=np.float64).reshape(-1, 3)
    members = [r["member"] for r in rows]
    groups = {}
    for row in rows:
        key = (row["member"]["frame_sha256"], row["member"]["object_sha256"])
        groups.setdefault(key, []).append(row["residual"])
    return dict(
        seeds=len(rows),
        frames=len({m["frame_sha256"] for m in members}),
        objects=len({m["object_sha256"] for m in members}),
        object_frames=len(groups),
        houses=len({m["house_index"] for m in members}),
        raw=metric(errors),
        corrected=None if model is None else metric(errors - np.asarray(model["bias"]), model),
        object_frame_metrics=[
            dict(
                frame_sha256=k[0],
                object_sha256=k[1],
                raw=metric(v),
                corrected=None
                if model is None
                else metric(np.asarray(v) - np.asarray(model["bias"]), model),
            )
            for k, v in sorted(groups.items())
        ],
    )


def build(directory, frontends, parent_directory, parent_report, binding, input_inventory):
    before = source_identity(ROOT)
    model_pin = parent_report["model_sha256"]
    model = affinity.restore(_json(parent_directory / "model.json"), model_pin)
    records = collect_public(
        directory, frontends, parent_directory, parent_report, model, model_pin
    )
    audit = _json(directory / "runtime-partition-audit.json")
    for r in records:
        if r["split"] == "train":
            r["labels"] = private_readout(directory, r, model, model_pin, audit)
    training = [r for r in records if r["split"] == "train"]
    models, artifacts, model_status = {}, {}, {}
    for estimator in ESTIMATORS:
        pins = {r["public"]["estimator_pins"][estimator] for r in records}
        require(len(pins) == 1, "readout estimator identity differs across frames")
        estimator_pin = next(iter(pins))
        for reference in REFERENCES:
            name = estimator + "/" + reference
            rows = paired_rows(training, estimator, reference)
            residuals = np.asarray([r["residual"] for r in rows], dtype=np.float64).reshape(-1, 3)
            members = [r["member"] for r in rows]
            artifacts[f"training/{name}/residuals.npy"] = array_bytes(residuals)
            artifacts[f"training/{name}/members.json"] = encoded(members)
            try:
                fitted = position.fit(
                    residuals,
                    members,
                    estimator=estimator,
                    reference_kind=reference,
                    domain_id=DOMAIN,
                    estimator_pin=estimator_pin,
                    partition="train",
                )
            except ValueError as error:
                reason = str(error)
                expected_failure = reason in {
                    "residual rank below three; no covariance fabricated",
                    "residual covariance must be positive definite; no noise floor",
                    "residual fit numerical failure",
                } or (
                    len(rows) < 4 and reason == "at least four finite Nx3 float residuals required"
                )
                if not expected_failure:
                    raise
                models[name] = None
                failure = dict(
                    status="fit_failed",
                    reason=reason,
                    training_seeds=len(rows),
                    residuals_file_sha256=hashlib.sha256(array_bytes(residuals)).hexdigest(),
                    members_sha256=content_sha256(members),
                    calibrated=False,
                    runtime_authority=False,
                )
                model_status[name] = failure
                artifacts[f"models/{name}.json"] = encoded(failure)
                continue
            pin = position.checkpoint_sha256(fitted)
            restored = position.restore(json.loads(encoded(fitted)), pin)
            require(restored == fitted, "residual checkpoint reload differs")
            models[name] = restored
            model_status[name] = dict(status="fitted", sha256=pin, training_seeds=len(rows))
            artifacts[f"models/{name}.json"] = encoded(restored)
    # All public corrected predictions precede validation labels. An offset is
    # conditional on the declared reference; it is not an accepted object centre.
    for record in records:
        corrected = []
        for obs in record["public"]["observations"]:
            for reference in REFERENCES:
                name = obs["estimator"] + "/" + reference
                fitted = models[name]
                point = (
                    None
                    if not obs["available"] or fitted is None
                    else (np.asarray(obs["world_point_m"]) - np.asarray(fitted["bias"])).tolist()
                )
                corrected.append(
                    dict(
                        measurement_id=obs["measurement_id"],
                        estimator=obs["estimator"],
                        reference_kind=reference,
                        available=obs["available"],
                        corrected_world_point_m=point,
                        model_available=fitted is not None,
                        model_sha256=model_status[name].get("sha256"),
                    )
                )
        record["corrected"] = corrected
    public_records = [
        dict(
            house_index=r["house_index"],
            sdk_index=r["sdk_index"],
            action_id=r["action_id"],
            observations=r["public"]["observations"],
        )
        for r in records
    ]
    diagnostic = diagnose(
        models,
        public_records,
        model_pins={name: status.get("sha256") for name, status in model_status.items()},
    )
    artifacts["controlled-position-consumption.json"] = encoded(diagnostic)
    print(
        json.dumps(
            dict(
                phase="fit_and_all_public_position_predictions",
                models_attempted=4,
                models_fitted=sum(m is not None for m in models.values()),
                frames=96,
            )
        ),
        flush=True,
    )
    for r in records:
        if r["split"] == "validation":
            r["labels"] = private_readout(directory, r, model, model_pin, audit)
    summaries = {}
    for estimator in ESTIMATORS:
        for reference in REFERENCES:
            name = estimator + "/" + reference
            summaries[name] = dict(
                by_split={
                    s: summarize_rows(
                        paired_rows([r for r in records if r["split"] == s], estimator, reference),
                        models[name],
                    )
                    for s in ("train", "validation")
                },
                by_house={
                    str(h): summarize_rows(
                        paired_rows(
                            [r for r in records if r["house_index"] == h], estimator, reference
                        ),
                        models[name],
                    )
                    for h in range(1, 13)
                },
            )
    frames = []
    for record in records:
        prefix = record["prefix"]
        for kind in ("public", "labels", "corrected"):
            artifacts[f"{prefix}/{kind}.json"] = encoded(record[kind])
        reasons = Counter(
            label["void_reason"]
            for label in record["labels"]["labels"]
            if label["estimator"] == ESTIMATORS[0] and not label["eligible"]
        )
        frames.append(
            {k: record[k] for k in ("prefix", "house_index", "split", "action_id")}
            | dict(
                candidates=len(record["public"]["candidates"]),
                neighborhoods=len(record["public"]["neighborhoods"]),
                seeds=len(record["public"]["seeds"]),
                public_valid_seeds=sum(s["valid"] for s in record["public"]["seeds"]),
                supervised_seeds=sum(
                    label["eligible"]
                    for label in record["labels"]["labels"]
                    if label["estimator"] == ESTIMATORS[0]
                ),
                void_reasons=dict(reasons),
            )
        )
    require(
        inventory(directory) == input_inventory, "collection changed during position experiment"
    )
    require(source_identity(ROOT) == before, "source changed during position experiment")
    report = dict(
        schema="soft-surface-position-development@1",
        source_files=before,
        parent_binding=binding,
        frames=frames,
        model_status=model_status,
        results=summaries,
        training_attempted=True,
        training_performed=any(m is not None for m in models.values()),
        models_fitted=sum(m is not None for m in models.values()),
        calibrated=False,
        natural_factor_completed=False,
        world_identity_assigned=False,
        formal_position_reference_selected=False,
        orientation_observed=False,
        runtime_authority=False,
        scope="CONDITIONAL_ON_CORRECT_RENDERED_SEED_ASSOCIATION_POSITION_DEVELOPMENT",
        members={name: hashlib.sha256(raw).hexdigest() for name, raw in artifacts.items()},
        interpretation="Correlated public seeds and exposed houses; two named references retained. "
        "No independent calibration, natural association, orientation or task success.",
    )
    artifacts["report.json"] = encoded(report)
    return artifacts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "controls-results",
        "controls-source",
        "affinity-results",
        "affinity-source",
        "historical-python",
        "collection",
        "capture-source",
        "archive",
        "sdk-python",
        "binary",
        "frontends",
        "frontend-source",
        "output",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in (
        "controls-ledger-sha256",
        "affinity-ledger-sha256",
        "inventory-sha256",
        "frontend-ledger-sha256",
    ):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    require(not args.output.is_symlink(), "symlink output")
    output = args.output.resolve()
    for p in (
        args.controls_results,
        args.controls_source,
        args.affinity_results,
        args.affinity_source,
        args.collection,
        args.capture_source,
        args.frontends,
        args.frontend_source,
        ROOT,
    ):
        require(
            not output.is_relative_to(p.resolve()) and not p.resolve().is_relative_to(output),
            "inputs and output must be disjoint",
        )
    require(args.verify or not output.exists(), "refuse to overwrite position experiment")
    controls_report, controls_binding = verify_controls(
        args.controls_results, ledger_pin=args.controls_ledger_sha256, source=args.controls_source
    )
    fresh_controls(args, controls_binding)
    parent_report, parent_binding = verify_affinity(
        args.affinity_results, ledger_pin=args.affinity_ledger_sha256, source=args.affinity_source
    )
    require(parent_binding == controls_report["parent_binding"], "controls affinity parent differs")
    directory = args.collection.resolve()
    before = inventory(directory)
    require(before["inventory.json"] == args.inventory_sha256, "collection pin differs")
    frontends, frontend_binding = verify_frontends(
        args.frontends,
        ledger_pin=args.frontend_ledger_sha256,
        source=args.frontend_source,
        input_inventory=before,
        capture_config=_json(directory / "configuration.json"),
    )
    binding = dict(
        controls=controls_binding,
        affinity=parent_binding,
        frontends=frontend_binding,
        collection_inventory_sha256=args.inventory_sha256,
    )
    artifacts = build(
        directory, frontends, args.affinity_results / "experiment", parent_report, binding, before
    )
    _, after = verify_controls(
        args.controls_results, ledger_pin=args.controls_ledger_sha256, source=args.controls_source
    )
    require(after == controls_binding, "controls changed during position experiment")
    _, after_affinity = verify_affinity(
        args.affinity_results, ledger_pin=args.affinity_ledger_sha256, source=args.affinity_source
    )
    require(after_affinity == parent_binding, "affinity changed during position experiment")
    _, after_frontends = verify_frontends(
        args.frontends,
        ledger_pin=args.frontend_ledger_sha256,
        source=args.frontend_source,
        input_inventory=before,
        capture_config=_json(directory / "configuration.json"),
    )
    require(after_frontends == frontend_binding, "frontends changed during position experiment")
    save_or_verify(output, artifacts, verify=args.verify)
    print(
        json.dumps(
            dict(
                complete=True,
                frames=96,
                models_attempted=4,
                models_fitted=json.loads(artifacts["report.json"])["models_fitted"],
                natural_factor_completed=False,
            )
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
