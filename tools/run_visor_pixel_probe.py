"""Prepare source-derived masks or run/replay the fixed RGB-only learning probe."""

import argparse
import json
import shutil
import tempfile
from pathlib import Path

import torch

from cpswm.data_preflight.full_hfd_training import encoded
from cpswm.data_preflight.visor_candidate_alignment import SCOPE, sha
from cpswm.data_preflight.visor_contact_supervision import _verify_artifacts
from cpswm.data_preflight.visor_pixel_probe import (
    extract_rgb,
    fit,
    labels_from_png,
    state_digest,
    tensor_digest,
)
from cpswm.data_preflight.visor_pixel_supervision import load_component, prepare
from cpswm.perception_mapping.natural_vision import FasterNaturalAppearanceDetector


def probe(source, contact_packet, pixel_packet, weights):
    torch.set_num_threads(2)
    torch.use_deterministic_algorithms(True)
    batch = load_component(source, contact_packet, pixel_packet)
    detector = FasterNaturalAppearanceDetector(
        weights_path=weights,
        **dict(zip(("household_id", "session_id", "trace_id"), SCOPE, strict=True)),
    )
    model = detector._model
    before = state_digest(model)
    features, targets, receipts = [], [], []
    for (row, rgb), label in zip(batch["inputs"], batch["targets"], strict=True):
        feature = extract_rgb(model, rgb)
        if feature["feature"].requires_grad:
            raise ValueError("backbone features must be frozen")
        features.append(feature)
        targets.append(labels_from_png(label))
        receipts.append(
            {
                "input": row,
                "feature_sha256": tensor_digest(feature["feature"]),
                "feature_shape": list(feature["feature"].shape),
                "original": feature["original"],
                "resized": feature["resized"],
                "padded": feature["padded"],
            }
        )
        print(json.dumps({"features_done": len(features), "planned": 16}), flush=True)
    result, checkpoint = fit(features, targets, batch["manifest_sha256"])
    after = state_digest(model)
    if before != after or any(p.grad is not None for p in model.parameters()):
        raise ValueError("frozen original detector changed")
    result.update(
        inputs=receipts,
        original_detector_before=before,
        original_detector_after=after,
        backbone_weights_sha256=detector.weights_sha256,
        environment={"torch": detector._versions[0], "torchvision": detector._versions[1]},
        original_detector_unchanged=True,
        targets_read_by_backbone=False,
        verification_extra_sgd_updates=2,
        source_packet_summary=batch["summary"],
    )
    return {"head.json": checkpoint, "report.json": encoded(result)}


def run_probe(source, contact_packet, pixel_packet, weights, output, verify=False):
    if output.is_symlink() or (output.exists() and not verify):
        raise FileExistsError(output)
    for parent in (source, contact_packet, pixel_packet):
        if output.resolve().is_relative_to(parent.resolve()) or parent.resolve().is_relative_to(
            output.resolve()
        ):
            raise ValueError("output must be disjoint from input packets")
    artifacts = probe(source, contact_packet, pixel_packet, weights)
    if verify:
        _verify_artifacts(output, artifacts)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".pixel-probe-", dir=output.parent))
        try:
            for name, raw in artifacts.items():
                (staging / name).write_bytes(raw)
            if output.exists():
                raise FileExistsError(output)
            staging.rename(output)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    result = json.loads(artifacts["report.json"])
    compact = {
        k: result[k]
        for k in [
            "optimizer_steps",
            "verification_extra_sgd_updates",
            "restored_full_outputs_equal",
            "restored_next_update_equal",
            "original_detector_unchanged",
        ]
    }
    for name, indices in [("train", range(8)), ("neighbor_diagnostic", range(8, 16))]:
        compact[name] = {
            stage: sum(result[stage][i]["objective"] for i in indices) / 8
            for stage in ["before", "after"]
        }
    print(
        json.dumps(
            {
                "summary": compact,
                "report_sha256": sha(artifacts["report.json"]),
                "head_sha256": sha(artifacts["head.json"]),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="stage", required=True)
    for stage in ("prepare", "probe"):
        p = sub.add_parser(stage)
        for name in ("source", "contact-packet", "output"):
            p.add_argument("--" + name, type=Path, required=True)
        p.add_argument("--verify", action="store_true")
        if stage == "probe":
            for name in ("pixel-packet", "weights"):
                p.add_argument("--" + name, type=Path, required=True)
    args = vars(parser.parse_args())
    stage = args.pop("stage")
    if stage == "prepare":
        result = prepare(**args)
        print(json.dumps(result["summary"], indent=2))
    else:
        run_probe(**args)
