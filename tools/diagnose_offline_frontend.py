"""Fixed archived RGB-D inference, followed by private all-instance diagnosis.

No fitting, semantic category mapping, instance assignment or likelihood write.
Historical collection verification runs with its original pinned source bytes.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict, replace
from hashlib import sha256
from pathlib import Path

import numpy as np
from clarification_camera_model import CLARIFICATION_SOURCES
from offline_frontend_evaluation import evaluate_frame, summarize
from verify_offline_factor_capture import _json, _public

from cpswm.perception_mapping.pixel_camera_feedback import PixelCategoryOutcomeDecoder
from cpswm.perception_mapping.unity_rgbd import surface_support
from cpswm.system.owned_visual_support import _frame_support
from cpswm.system.reproducibility import canonical_json, content_sha256

ROOT = Path(__file__).resolve().parents[1]
SCOPE = "FIXED_OFFLINE_PUBLIC_FRONTEND_ALL_INSTANCE_DIAGNOSIS"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def plain(value):
    return json.loads(canonical_json(value))


def inventory(directory):
    paths = sorted(directory.rglob("*"))
    require(not directory.is_symlink(), "symlink input directory")
    require(not any(p.is_symlink() for p in paths), "symlink input entry")
    return {str(p.relative_to(directory)): digest(p) for p in paths if p.is_file()}


def source_identity(root):
    return {
        str(p.relative_to(root)): digest(p)
        for folder in ("src", "tests", "tools")
        for p in sorted((root / folder).rglob("*.py"))
    }


def verify_historical_collection(directory, *, pin, capture_source, archive, sdk_python, binary):
    """Never re-pin the old collection merely because new analysis tools exist."""
    require(digest(directory / "inventory.json") == pin, "collection external pin differs")
    before = inventory(directory)
    require(
        {k: v for k, v in before.items() if k != "inventory.json"}
        == _json(directory / "inventory.json"),
        "collection bytes differ from inventory",
    )
    config = _json(directory / "configuration.json")
    require(
        source_identity(capture_source) == config["source_files"],
        "historical capture source bytes differ",
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(str(capture_source / name) for name in ("src", "tools"))
    result = subprocess.run(
        [
            sys.executable,
            str(capture_source / "tools/collect_offline_factor_data.py"),
            "--verify",
            "--output",
            str(directory),
            "--archive",
            str(archive),
            "--sdk-python",
            str(sdk_python),
            "--binary",
            str(binary),
            "--inventory-sha256",
            pin,
        ],
        cwd=capture_source,
        env=env,
        capture_output=True,
        text=True,
        timeout=240,
    )
    require(result.returncode == 0, "historical collection verifier failed: " + result.stderr)
    status = json.loads(result.stdout)
    require(
        type(status) is dict
        and all(type(value) is bool for value in status.values())
        and status
        == dict(
            complete_twelve_house_runtime_audit=True,
            complete_asset_exposure_audit=True,
            supervision_export_performed=False,
            training_performed=False,
        ),
        "historical collection is not a complete eligible development batch",
    )
    require(inventory(directory) == before, "collection changed during historical verification")
    return before, config


def predict_public_house(directory, decoder):
    """Detector accepts only public observations; no evaluation labels or split."""
    # The capture record supplies hashes, never object labels, to the transport check.
    capture = _json(directory / "capture.json")
    records, _ = _public(directory / "public", capture["provenance"])
    binding = decoder.binding_sha256
    result = []
    for command, delivery, _ in records:
        measured = decoder.measurements(delivery.observations, cutoff=delivery.received_at)
        require(len(measured) == 1, "expected exactly one public frame")
        frame = replace(
            _frame_support(delivery.observations[0], measured[0], delivery.received_at),
            geometry=surface_support(
                delivery.observations, measured[0], cutoff=delivery.received_at
            ),
        )
        require(frame.geometry.camera.action_id == command.action_id, "public action differs")
        result.append((command, delivery, frame))
    require(decoder.binding_sha256 == binding, "decoder changed during public inference")
    return result, binding


def make_decoder(weights, kind, scope):
    return PixelCategoryOutcomeDecoder(
        weights_path=weights,
        detector_kind=kind,
        category="apple",
        household_id=scope[0],
        session_id=scope[1],
        trace_id=scope[2],
        sources=CLARIFICATION_SOURCES,
    )


def diagnose(directory, *, decoder_factory, input_inventory, capture_config, detector_kind):
    """Finish every public prediction before opening any private evaluation labels."""
    before_source = source_identity(ROOT)
    public, inferred = [], []
    for index in range(1, 13):
        house = directory / f"house-{index:02d}"
        record = _json(house / "capture.json")
        _, scope = _public(house / "public", record["provenance"])
        decoder = decoder_factory(scope)
        rows, binding = predict_public_house(house, decoder)
        inferred.append((index, rows))
        public.extend(
            plain(dict(command=asdict(command), frame=asdict(frame), decoder_binding=binding))
            for command, _, frame in rows
        )
        print(
            json.dumps(dict(phase="public", detector=detector_kind, house=index, frames=len(rows))),
            flush=True,
        )
    # Labels below are evaluation inputs; none are passed to decoder_factory or measurements.
    audit = _json(directory / "runtime-partition-audit.json")
    rows = []
    for index, predictions in inferred:
        eligibility = [r for r in audit["instances"] if r["house_index"] == index]
        private = directory / f"house-{index:02d}/unity-logs/evaluator_only"
        for offset, (command, delivery, frame) in enumerate(predictions, start=4):
            sdk = _json(private / f"sdk-events/{offset:03d}.json")
            info = _json(private / f"instances/{offset:03d}.json")
            for n, name in enumerate(("rgb", "depth")):
                require(
                    (private / f"sdk-events/{offset:03d}-{name}.npy").read_bytes()
                    == delivery.observations[n].payload_bytes,
                    "public bytes differ from matching SDK event",
                )
            segmentation = np.load(
                private / f"instances/{offset:03d}-segmentation.npy", allow_pickle=False
            )
            with np.load(
                private / f"instances/{offset:03d}-masks.npz", allow_pickle=False
            ) as masks:
                row = evaluate_frame(
                    command, delivery, frame, sdk, info, masks, segmentation, eligibility
                )
            row.update(house_index=index, split="train" if index <= 8 else "validation")
            rows.append(row)
    require(inventory(directory) == input_inventory, "collection changed during diagnosis")
    require(source_identity(ROOT) == before_source, "diagnostic source changed during run")
    report = dict(
        scope=SCOPE,
        detector_kind=detector_kind,
        collection_inventory_sha256=input_inventory["inventory.json"],
        capture_source_files=capture_config["source_files"],
        diagnostic_source_files=before_source,
        public_predictions_sha256=content_sha256(public),
        frames=rows,
        summary=summarize(rows),
        interpretation=(
            "Pixel overlap is not correct semantic detection or physical surface identity; "
            "SDK-reference displacements are not calibrated localization error."
        ),
        automatic_identity_assignment=False,
        semantic_category_mapping=False,
        formal_position_reference_selected=False,
        training_performed=False,
        calibration_performed=False,
        observation_likelihood_written=False,
        online_memory_write=False,
        independent_label_custody=False,
    )
    return dict(public=public, report=plain(report), inputs=input_inventory)


def save_or_verify(output, documents, *, verify):
    expected = {name + ".json" for name in documents}
    if verify:
        require(output.is_dir() and not output.is_symlink(), "missing diagnosis directory")
        require(
            {p.name for p in output.iterdir()} == expected
            and all(p.is_file() and not p.is_symlink() for p in output.iterdir()),
            "diagnosis file inventory differs",
        )
        for name, value in documents.items():
            require(
                content_sha256(_json(output / (name + ".json"))) == content_sha256(value),
                "fresh " + name + " differs",
            )
    else:
        output.mkdir(parents=True, exist_ok=False)
        for name, value in documents.items():
            (output / (name + ".json")).write_text(
                json.dumps(value, indent=2, allow_nan=False) + "\n"
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "collection",
        "capture-source",
        "archive",
        "sdk-python",
        "binary",
        "weights",
        "output",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--inventory-sha256", required=True)
    parser.add_argument("--detector", choices=("fasterrcnn", "ssdlite"), required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    directory, output = args.collection.resolve(), args.output.resolve()
    require(
        not output.is_relative_to(directory) and not directory.is_relative_to(output),
        "input and output directories must be disjoint",
    )
    require(args.verify or not output.exists(), "refuse to overwrite prior diagnosis")
    before, config = verify_historical_collection(
        directory,
        pin=args.inventory_sha256,
        capture_source=args.capture_source.resolve(),
        archive=args.archive.resolve(),
        sdk_python=args.sdk_python.absolute(),
        binary=args.binary.resolve(),
    )
    import torch

    torch.set_num_threads(2)
    documents = diagnose(
        directory,
        decoder_factory=lambda scope: make_decoder(args.weights, args.detector, scope),
        input_inventory=before,
        capture_config=config,
        detector_kind=args.detector,
    )
    save_or_verify(output, documents, verify=args.verify)
    print(
        json.dumps(
            dict(complete=True, detector=args.detector, frames=len(documents["report"]["frames"]))
        )
    )


if __name__ == "__main__":
    main()
