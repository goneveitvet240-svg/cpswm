"""Fixed feature-group controls on the same pinned RGB-D candidate pairs.

RGB features still share depth-validity gating; geometry features still share
RGB detector boxes. This is not a comparison of independent sensor systems.
The historical program is reconstructed from explicit caller arguments, never
executed from a saved ledger's argv. Historical private audits are not process
isolation; only train labels reach the fixed fitting interfaces.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

import numpy as np
from diagnose_offline_frontend import digest, inventory, require, source_identity
from run_instance_affinity import array_bytes, encoded, save_or_verify, scores
from verify_offline_factor_capture import _json

from cpswm.data_preflight import instance_affinity as baseline
from cpswm.data_preflight import instance_affinity_controls as controls
from cpswm.system.reproducibility import content_sha256

ROOT = Path(__file__).resolve().parents[1]
METHODS = (*controls.MODES, "training_frequency_constant")
CLASSES = ("all", "same_instance", "different_instance")


def verify_parent(directory, *, ledger_pin, source):
    require(not directory.is_symlink() and not source.is_symlink(), "symlink parent path")
    ledger = directory / "case-results.json"
    require(not ledger.is_symlink() and digest(ledger) == ledger_pin, "parent ledger pin differs")
    cases = _json(ledger)
    require(
        type(cases) is list
        and len(cases) == 2
        and [c["phase"] for c in cases] == ["run", "verify"]
        and all(type(c["exit_code"]) is int and c["exit_code"] == 0 for c in cases)
        and len({c["source_sha"] for c in cases}) == 1
        and re.fullmatch("[0-9a-f]{40}", cases[0]["source_sha"]) is not None,
        "parent requires a complete successful run and fresh refit ledger",
    )
    actual = inventory(directory / "experiment")
    expected_names = {"report.json", "model.json"} | {
        f"frames/{i:03d}/{name}"
        for i in range(96)
        for name in (
            "features.npy",
            "pairs.npy",
            "valid.npy",
            "targets.npy",
            "scores.npy",
            "public.json",
            "supervision.json",
        )
    }
    require(set(actual) == expected_names, "parent must retain all 96 frame members")
    require(all(c["output_sha256"] == actual for c in cases), "parent output bytes differ")
    report = _json(directory / "experiment/report.json")
    require(
        report["source_files"] == source_identity(source)
        and report["members"] == {k: v for k, v in actual.items() if k != "report.json"}
        and report["scope"] == "RENDERED_INSTANCE_AFFINITY_DEVELOPMENT_BASELINE"
        and report["training_performed"] is True
        and all(
            report[k] is False
            for k in (
                "calibration_performed",
                "world_instance_identity_assigned",
                "observation_likelihood_written",
                "online_memory_write",
                "full_mask_predicted",
                "formal_position_reference_selected",
                "independent_acceptance",
            )
        ),
        "parent source, members or authority differs",
    )
    require(
        len(report["frames"]) == 96
        and [(f["house_index"], f["sdk_index"], f["split"], f["prefix"]) for f in report["frames"]]
        == [
            (h, t + 4, "train" if h <= 8 else "validation", f"frames/{(h - 1) * 8 + t:03d}")
            for h in range(1, 13)
            for t in range(8)
        ]
        and len({f["action_id"] for f in report["frames"]}) == 96,
        "parent partition or action schedule differs",
    )
    baseline.restore(_json(directory / "experiment/model.json"), report["model_sha256"])
    return report, dict(
        ledger_sha256=ledger_pin,
        actual_source_sha=cases[0]["source_sha"],
        source_files=report["source_files"],
        output_files=actual,
    )


def fresh_parent(args, expected_binding):
    source = args.affinity_source.resolve()
    script = source / "tools/run_instance_affinity.py"
    require(script.is_file() and not script.is_symlink(), "historical CLI missing")
    command = [str(args.historical_python.absolute()), str(script)]
    for name in (
        "collection",
        "capture_source",
        "archive",
        "sdk_python",
        "binary",
        "frontends",
        "frontend_source",
    ):
        value = getattr(args, name)
        value = value.absolute() if name == "sdk_python" else value.resolve()
        command.extend(["--" + name.replace("_", "-"), str(value)])
    command.extend(
        [
            "--output",
            str(args.affinity_results.resolve() / "experiment"),
            "--inventory-sha256",
            args.inventory_sha256,
            "--frontend-ledger-sha256",
            args.frontend_ledger_sha256,
            "--verify",
        ]
    )
    environment = os.environ.copy()
    environment.update(
        PYTHONPATH=os.pathsep.join(str(source / name) for name in ("src", "tools")),
        OPENBLAS_NUM_THREADS="1",
    )
    # The caller selected this interpreter and separately pinned historical source.
    result = subprocess.run(command, cwd=source, env=environment, check=False, timeout=1800)
    require(result.returncode == 0, "historical affinity fresh refit failed")
    _, after = verify_parent(
        args.affinity_results, ledger_pin=args.affinity_ledger_sha256, source=args.affinity_source
    )
    require(after == expected_binding, "parent changed during fresh refit")


def load_public(directory, report):
    records = []
    for frame in report["frames"]:
        path = directory / frame["prefix"]
        arrays = {
            name: np.load(path / f"{name}.npy", allow_pickle=False)
            for name in ("features", "pairs", "valid")
        }
        baseline._features(arrays["features"])
        n = len(arrays["features"])
        require(
            arrays["pairs"].dtype == np.int64 and arrays["pairs"].shape == (n, 4),
            "invalid public pair array",
        )
        require(
            arrays["valid"].dtype == np.bool_ and arrays["valid"].shape == (n,),
            "invalid public depth validity",
        )
        require(
            np.all(arrays["features"][~arrays["valid"]] == 0), "invalid public rows are not zero"
        )
        public = _json(path / "public.json")
        records.append(
            dict(
                prefix=frame["prefix"],
                action_id=frame["action_id"],
                house_index=frame["house_index"],
                split=frame["split"],
                public=public,
                **arrays,
            )
        )
    return records


def load_targets(directory, record):
    y = np.load(directory / record["prefix"] / "targets.npy", allow_pickle=False)
    require(
        y.dtype == np.int8
        and y.shape == record["valid"].shape
        and np.isin(y, (-1, 0, 1)).all()
        and np.all(y[~record["valid"]] == -1),
        "invalid matched supervision",
    )
    return y


def class_scores(targets, predictions):
    y = np.asarray(targets)
    p = np.asarray(predictions)
    result = {"all": scores(y, p)}
    for name, value in (("same_instance", 1), ("different_instance", 0)):
        keep = y == value
        result[name] = scores(y[keep], p[keep])
    return result


def summarize(records):
    y = np.concatenate([r["targets"] for r in records])
    valid = np.concatenate([r["valid"] for r in records])
    return dict(
        frames=len(records),
        zero_candidate_frames=sum(not r["public"]["candidates"] for r in records),
        frames_without_supervision=sum(not np.any(r["targets"] != -1) for r in records),
        unique_pairs=len(y),
        public_valid_pairs=int(valid.sum()),
        positive_pairs=int(np.sum(y == 1)),
        negative_pairs=int(np.sum(y == 0)),
        void_pairs=int(np.sum(y == -1)),
        methods={
            method: class_scores(y, np.concatenate([r["predictions"][method] for r in records]))
            for method in METHODS
        },
    )


def house_macro(houses):
    return {
        method: {
            group: dict(
                houses=sum(h["methods"][method][group]["pairs"] > 0 for h in houses),
                **{
                    metric: float(
                        np.mean(
                            [
                                h["methods"][method][group][metric]
                                for h in houses
                                if h["methods"][method][group]["pairs"] > 0
                            ]
                        )
                    )
                    if any(h["methods"][method][group]["pairs"] > 0 for h in houses)
                    else None
                    for metric in ("bce", "brier")
                },
            )
            for group in CLASSES
        }
        for method in METHODS
    }


def build(directory, parent_report, parent_binding):
    before = source_identity(ROOT)
    records = load_public(directory, parent_report)
    training = [r for r in records if r["split"] == "train"]
    for record in training:
        record["targets"] = load_targets(directory, record)
    x = np.concatenate([r["features"] for r in training])
    y = np.concatenate([r["targets"] for r in training])
    models, artifacts = {}, {}
    prevalence = None
    for mode in controls.MODES:
        model = controls.fit(x, y, mode, partition="train")
        pin = controls.checkpoint_sha256(model)
        model = controls.restore(json.loads(encoded(model)), pin)
        models[mode] = dict(checkpoint=model, sha256=pin)
        constant = model["inner_checkpoint"]["prevalence"]
        require(prevalence is None or constant == prevalence, "control prevalence differs")
        prevalence = constant
        artifacts[f"models/{mode}.json"] = encoded(model)
        for record in records:
            values = controls.predict(model, record["features"], record["valid"])
            p = np.asarray([np.nan if v is None else v for v in values], dtype=np.float64)
            valid = record["valid"]
            require(
                np.isfinite(p[valid]).all()
                and ((p[valid] >= 0) & (p[valid] <= 1)).all()
                and np.isnan(p[~valid]).all(),
                "invalid public control score",
            )
            record.setdefault("predictions", {})[mode] = p
            artifacts[f"{record['prefix']}/{mode}.npy"] = array_bytes(p)
    require(
        encoded(models["combined"]["checkpoint"]["inner_checkpoint"])
        == (directory / "model.json").read_bytes(),
        "combined differs from parent model",
    )
    for record in records:
        require(
            artifacts[f"{record['prefix']}/combined.npy"]
            == (directory / record["prefix"] / "scores.npy").read_bytes(),
            "combined differs from parent scores",
        )
        record["predictions"]["training_frequency_constant"] = np.where(
            record["valid"], prevalence, np.nan
        )
    print(json.dumps(dict(phase="all_public_predictions", frames=96, models=3)), flush=True)
    for record in records:
        if record["split"] == "validation":
            record["targets"] = load_targets(directory, record)
    by_house = {
        str(h): summarize([r for r in records if r["house_index"] == h]) for h in range(1, 13)
    }
    by_split = {
        s: summarize([r for r in records if r["split"] == s]) for s in ("train", "validation")
    }
    for split, row in by_split.items():
        row["house_macro"] = house_macro(
            [by_house[str(h)] for h in range(1, 13) if (h <= 8) == (split == "train")]
        )
    require(source_identity(ROOT) == before, "source changed during controls")
    report = dict(
        schema="instance-affinity-feature-controls@1",
        source_files=before,
        parent_binding=parent_binding,
        modes=list(controls.MODES),
        training_performed=True,
        combined_exact_parent_model_and_predictions=True,
        scope="FIXED_CANDIDATE_PAIR_FEATURE_GROUP_DEVELOPMENT_CONTROLS",
        model_pins={k: v["sha256"] for k, v in models.items()},
        runtime_authority=False,
        calibrated=False,
        observation_likelihood_written=False,
        frames=[
            {k: r[k] for k in ("prefix", "action_id", "house_index", "split")}
            | dict(summary=summarize([r]))
            for r in records
        ],
        by_house=by_house,
        by_split=by_split,
        overall=summarize(records),
        members={name: hashlib.sha256(raw).hexdigest() for name, raw in artifacts.items()},
        interpretation=(
            "Feature groups share RGB detector proposals and RGB-D validity. "
            "Correlated pairs on exposed development houses; no threshold selection, "
            "independent sensor-system comparison, calibration, complete mask, "
            "world identity, position reference or action-loop benefit."
        ),
    )
    artifacts["report.json"] = encoded(report)
    return artifacts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
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
    for name in ("affinity-ledger-sha256", "inventory-sha256", "frontend-ledger-sha256"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    require(not args.output.is_symlink(), "symlink output")
    output = args.output.resolve()
    for source in (
        args.affinity_results,
        args.affinity_source,
        args.collection,
        args.capture_source,
        args.frontends,
        args.frontend_source,
        ROOT,
    ):
        require(
            not output.is_relative_to(source.resolve())
            and not source.resolve().is_relative_to(output),
            "inputs and output must be disjoint",
        )
    require(args.verify or not output.exists(), "refuse to overwrite control results")
    report, binding = verify_parent(
        args.affinity_results, ledger_pin=args.affinity_ledger_sha256, source=args.affinity_source
    )
    fresh_parent(args, binding)
    artifacts = build(args.affinity_results / "experiment", report, binding)
    _, after = verify_parent(
        args.affinity_results, ledger_pin=args.affinity_ledger_sha256, source=args.affinity_source
    )
    require(content_sha256(after) == content_sha256(binding), "parent changed during controls")
    save_or_verify(output, artifacts, verify=args.verify)
    print(
        json.dumps(
            dict(complete=True, models=3, training_performed=True, natural_factor_completed=False)
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
