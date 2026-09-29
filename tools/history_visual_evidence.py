"""Paired pixel predictions and private instance checks on actual owned histories.

This evaluates observations the policy actually obtained. It does not substitute
pixels for an unexecuted counterfactual action or confer target identity rights.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import torch
from run_history_action_loop import decoder_for, load, source_identity, write
from run_history_action_loop import verify as verify_history
from run_instance_correspondence_diagnostic import reconstruct_catalog
from verify_neural_camera_comparison import bbox_iou, plain, require

from cpswm.perception_mapping.natural_vision import decode_rgb
from cpswm.system.structure_two_continuous_input import ObservationDelivery

FRONTENDS = ("ssdlite", "fasterrcnn")
SCOPE = "SAME_PUBLIC_PIXELS_PRIVATE_INSTANCE_EVALUATION_NOT_IDENTITY_OR_CALIBRATION"


def paired_predictions(records, *, task, weights):
    """Accept only owned public deliveries; no evaluator path or labels."""
    require(bool(records), "no delivered observations to compare")
    for command, delivery in records:
        require(
            type(delivery) is ObservationDelivery
            and delivery.success
            and command.action_id == delivery.action_id
            and len(delivery.observations) == 1,
            "invalid public delivery",
        )
        raw = delivery.observations[0]
        env, pixels = decode_rgb(raw, cutoff=delivery.received_at)
        require(
            env.metadata.source_id == str(command.action_id)
            and command.decision_time <= env.capture_time <= env.arrival_time
            and pixels.shape == (320, 320, 3),
            "public pixels or ownership differ",
        )
    require(len({c.action_id for c, _ in records}) == len(records), "duplicate public action")
    measurements, bindings = {}, {}
    for kind in FRONTENDS:
        decoder, _ = decoder_for(weights[kind], task, kind)
        bindings[kind] = decoder.binding_sha256
        measurements[kind] = [
            plain(asdict(decoder.measurements(d.observations, cutoff=d.received_at)[0]))
            for _, d in records
        ]
    return dict(decoder_bindings=bindings, measurements=measurements)


def evaluate_frame(command, delivery, row, frames, info, masks, segmentation, target_mask, target):
    require(
        info["action_id"] == row["owner"] == str(command.action_id),
        "instance frame owner differs",
    )
    instances = reconstruct_catalog(
        info["catalog"], info["colors"], masks, segmentation, row["metadata"]["objects"]
    )
    require(info["colors"] == row["metadata"]["colors"], "instance color source differs")
    require(
        target_mask.dtype == bool
        and target_mask.shape == (320, 320)
        and segmentation.shape == (320, 320, 3),
        "instance image geometry differs",
    )
    target_rows = [r for r in instances if r["object_id"] == target]
    require(len(target_rows) == 1, "missing private target")
    require(
        np.array_equal(target_mask, masks[target_rows[0]["array_key"]]),
        "instance target mask differs",
    )
    raw = delivery.observations[0]
    matrix = []
    require(set(frames) == set(FRONTENDS), "missing paired frontend")
    for kind in FRONTENDS:
        frame = frames[kind]
        require(
            frame["input_sha256"] == hashlib.sha256(raw.payload_bytes).hexdigest()
            and frame["observation_id"] == str(raw.envelope().identity.observation_id)
            and frame["minimum_score"] == 0.5
            and frame["identity_status"] == "UNRESOLVED"
            and frame["negative_observation_authorized"] is False,
            "prediction input or authority differs",
        )
        for candidate in frame["candidates"]:
            if candidate["category"] != "apple":
                continue
            x1, y1, x2, y2 = candidate["box_xyxy"]
            require(
                np.isfinite([x1, y1, x2, y2, candidate["detector_score"]]).all()
                and 0 <= x1 < x2 <= 320
                and 0 <= y1 < y2 <= 320
                and 0.5 <= candidate["detector_score"] <= 1,
                "invalid candidate geometry or score",
            )
            # Pixel centers, half-open box; all overlaps retained without assignment.
            yy, xx = np.indices((320, 320))
            inside = (xx + 0.5 >= x1) & (xx + 0.5 < x2) & (yy + 0.5 >= y1) & (yy + 0.5 < y2)
            matrix.append(
                dict(
                    frontend=kind,
                    candidate=candidate,
                    overlaps=[
                        dict(
                            object_id=r["object_id"],
                            object_type=r["object_type"],
                            bbox_iou=bbox_iou(candidate["box_xyxy"], r["bbox"]),
                            intersection_pixels=int((masks[r["array_key"]] & inside).sum()),
                            instance_pixels=r["pixels"],
                        )
                        for r in instances
                    ],
                )
            )
    return dict(
        action_id=str(command.action_id),
        sdk_index=row["index"],
        action=[command.action, command.degrees],
        target_id=target,
        target_pixels=int(target_mask.sum()),
        input_sha256=hashlib.sha256(raw.payload_bytes).hexdigest(),
        instances=instances,
        candidate_instance_matrix=matrix,
        automatic_identity_assignment=False,
        natural_identity_labels=0,
    )


def analyze(directory, *, weights, checkpoint, verify=False):
    manifest = json.loads((directory / "manifest.json").read_text())
    source = source_identity()
    require(
        manifest["status"] == "COMPLETE"
        and manifest["private_instance_evaluation"] is True
        and (manifest["source"], manifest["source_files"]) == source,
        "incomplete or changed history",
    )
    verify_history(directory, weights=weights[manifest["detector_kind"]], checkpoint=checkpoint)
    history = load(directory / "owned-history.json")
    records = [(c, d) for c, d in history if type(d) is ObservationDelivery]
    # Produce BOTH predictions before reading any private labels.
    predictions = paired_predictions(records, task=manifest["task"], weights=weights)
    online = manifest["detector_kind"]
    require(
        predictions["decoder_bindings"][online] == manifest["decoder_binding"]
        and predictions["measurements"][online]
        == json.loads((directory / "fresh-measurements.json").read_text()),
        "online detector differs from paired re-inference",
    )
    private = directory / "unity-logs/evaluator_only"
    sdk = [json.loads(p.read_text()) for p in sorted((private / "sdk-events").glob("*.json"))]
    require(
        len(sdk) == 4 + len(records)
        and [r["index"] for r in sdk] == list(range(len(sdk)))
        and len(list((private / "instances").glob("*.json"))) == len(sdk),
        "instance history coverage differs",
    )
    house = json.loads((directory / "evaluator_house.json").read_text())
    target = house["metadata"]["cpswm_diagnostic_target"]
    rows = []
    for i, ((command, delivery), row) in enumerate(zip(records, sdk[4:], strict=True)):
        index = row["index"]
        require(
            (private / f"sdk-events/{index:03d}-rgb.npy").read_bytes()
            == delivery.observations[0].payload_bytes,
            "instance public pixels differ",
        )
        info = json.loads((private / f"instances/{index:03d}.json").read_text())
        with np.load(private / f"instances/{index:03d}-masks.npz", allow_pickle=False) as masks:
            rows.append(
                evaluate_frame(
                    command,
                    delivery,
                    row,
                    {k: predictions["measurements"][k][i] for k in FRONTENDS},
                    info,
                    masks,
                    np.load(
                        private / f"instances/{index:03d}-segmentation.npy", allow_pickle=False
                    ),
                    np.load(private / f"sdk-events/{index:03d}-mask.npy", allow_pickle=False),
                    target,
                )
            )
    result = dict(
        scope=SCOPE,
        online_detector=online,
        source_sha256=source[0],
        frames=rows,
        complete_natural_closed_loop=False,
        empirical_calibration=False,
        counterfactual_action_execution=False,
    )
    require(source_identity() == source, "source changed during visual analysis")
    for name, document in (("paired-predictions", predictions), ("visual-evaluation", result)):
        path = directory / (name + ".json")
        if verify:
            require(json.loads(path.read_text()) == document, "fresh " + name + " differs")
        else:
            require(not path.exists(), "refuse to overwrite prior visual evidence")
            write(path, document)
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=("run", "verify"), required=True)
    for key in ("output", "ssdlite-weights", "fasterrcnn-weights", "checkpoint"):
        p.add_argument("--" + key, type=Path, required=True)
    a = p.parse_args()
    torch.set_num_threads(2)
    result = analyze(
        a.output,
        weights=dict(ssdlite=a.ssdlite_weights, fasterrcnn=a.fasterrcnn_weights),
        checkpoint=a.checkpoint,
        verify=a.mode == "verify",
    )
    print(json.dumps(dict(frames=len(result["frames"]), scope=result["scope"])))
