"""Run source-bound feature/bias controls and full separate-video diagnostics."""

import argparse
import json
import shutil
import tempfile
from pathlib import Path

import torch

from cpswm.data_preflight.full_hfd_training import encoded
from cpswm.data_preflight.visor_candidate_alignment import SCOPE, sha
from cpswm.data_preflight.visor_contact_supervision import _verify_artifacts
from cpswm.data_preflight.visor_control_data import derive_component, require_disjoint
from cpswm.data_preflight.visor_feature_control import measure, summarize, train_controls
from cpswm.data_preflight.visor_pixel_probe import (
    extract_rgb,
    labels_from_png,
    state_digest,
    tensor_digest,
)
from cpswm.data_preflight.visor_pixel_supervision import load_component
from cpswm.perception_mapping.natural_vision import FasterNaturalAppearanceDetector


def compute(source, contact_packet, pixel_packet, diagnostic_source, weights):
    torch.set_num_threads(2)
    torch.use_deterministic_algorithms(True)
    train = load_component(source, contact_packet, pixel_packet, count=8)
    dev = derive_component(diagnostic_source)
    require_disjoint(train["inputs"], dev["inputs"])
    detector = FasterNaturalAppearanceDetector(
        weights_path=weights,
        **dict(zip(("household_id", "session_id", "trace_id"), SCOPE, strict=True)),
    )
    model = detector._model
    before = state_digest(model)
    features = [extract_rgb(model, rgb) for _, rgb in train["inputs"]]
    targets = [labels_from_png(t) for t in train["targets"]]
    heads, artifacts, report = train_controls(features, targets)
    rows = {
        "train": {
            name: [measure(head, f, t) for f, t in zip(features, targets, strict=True)]
            for name, head in heads.items()
        },
        "separate_video": {name: [] for name in heads},
        "cyclic_wrong_image": {name: [] for name in heads if name.startswith("feature_")},
    }
    receipts = {
        "train": [
            {"input": r, "feature_sha256": tensor_digest(f["feature"])}
            for (r, _), f in zip(train["inputs"], features, strict=True)
        ],
        "separate_video": [],
    }
    # No diagnostic input/label is passed to the optimizer or analytic constant.
    del features, targets
    first_feature, previous_target = None, None
    for i, ((row, rgb), label) in enumerate(zip(dev["inputs"], dev["targets"], strict=True)):
        feature = extract_rgb(model, rgb)
        target = labels_from_png(label)
        for name, head in heads.items():
            rows["separate_video"][name].append(measure(head, feature, target))
            if previous_target is not None and name in rows["cyclic_wrong_image"]:
                rows["cyclic_wrong_image"][name].append(measure(head, feature, previous_target))
        if first_feature is None:
            first_feature = feature
        previous_target = target
        receipts["separate_video"].append(
            {"input": row, "feature_sha256": tensor_digest(feature["feature"])}
        )
        print(
            json.dumps({"diagnostic_frames_done": i + 1, "total": len(dev["inputs"])}), flush=True
        )
    for name in rows["cyclic_wrong_image"]:
        rows["cyclic_wrong_image"][name].append(
            measure(heads[name], first_feature, previous_target)
        )
    after = state_digest(model)
    if before != after or any(p.grad is not None for p in model.parameters()):
        raise ValueError("original frozen detector changed")
    report.update(
        rows=rows,
        summary={
            group: {name: summarize(r) for name, r in arms.items()} for group, arms in rows.items()
        },
        inputs=receipts,
        train_manifest_sha256=train["manifest_sha256"],
        diagnostic_manifest_sha256=dev["manifest_sha256"],
        diagnostic_source_report=dev["source_report"],
        diagnostic_source_pins=dev["source_pins"],
        diagnostic_pixel_summary=dev["summary"],
        checkpoint_digests={name: sha(raw) for name, raw in artifacts.items()},
        original_detector_before=before,
        original_detector_after=after,
        original_detector_unchanged=True,
        backbone_weights_sha256=detector.weights_sha256,
        environment={"torch": detector._versions[0], "torchvision": detector._versions[1]},
        diagnostic_wrong_image_policy="target_i_with_RGB_(i+1)_mod_N; complete_video_no_self_pairs",
        formal_validation=False,
        independent_subject=False,
        model_selected=False,
        native_proposal_training_steps=0,
        runtime_authorized=False,
    )
    artifacts["diagnostic-pixel-manifest.json"] = dev["pixel_manifest"]
    artifacts["report.json"] = encoded(report)
    return artifacts


def run(source, contact_packet, pixel_packet, diagnostic_source, weights, output, verify=False):
    if output.is_symlink() or (output.exists() and not verify):
        raise FileExistsError(output)
    for parent in (source, contact_packet, pixel_packet, diagnostic_source, weights):
        if output.resolve().is_relative_to(parent.resolve()) or parent.resolve().is_relative_to(
            output.resolve()
        ):
            raise ValueError("output must be disjoint from all input sources")
    artifacts = compute(source, contact_packet, pixel_packet, diagnostic_source, weights)
    if verify:
        _verify_artifacts(output, artifacts)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".feature-control-", dir=output.parent))
        try:
            for name, raw in artifacts.items():
                (staging / name).write_bytes(raw)
            if output.exists():
                raise FileExistsError(output)
            staging.rename(output)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    print(
        json.dumps({"report_sha256": sha(artifacts["report.json"]), "verified": verify}), flush=True
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "source",
        "contact-packet",
        "pixel-packet",
        "diagnostic-source",
        "weights",
        "output",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    run(**vars(parser.parse_args()))
