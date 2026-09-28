"""Optional diagnostic observer: public transport unchanged, instance truth private."""

import argparse
import json
from pathlib import Path

import numpy as np
import unity_camera_feedback_worker as transport


def export_instances(event, directory, index, identity):
    directory.mkdir(parents=True, exist_ok=True)
    shape = event.frame.shape[:2]
    segmentation = np.asarray(event.instance_segmentation_frame)
    if segmentation.dtype != np.uint8 or segmentation.shape != (*shape, 3):
        raise ValueError("actual instance segmentation has invalid shape or type")
    objects = sorted(event.metadata["objects"], key=lambda value: value["objectId"])
    if len({obj["objectId"] for obj in objects}) != len(objects):
        raise ValueError("duplicate SDK instance identity")
    arrays, catalog = {}, []
    for i, obj in enumerate(objects):
        key = f"mask_{i:04d}"
        mask = np.asarray(event.instance_masks.get(obj["objectId"], np.zeros(shape, dtype=bool)))
        if mask.dtype != bool or mask.shape != shape:
            raise ValueError("actual SDK instance mask has invalid shape or type")
        arrays[key] = mask
        catalog.append(
            dict(
                array_key=key,
                object_id=obj["objectId"],
                object_type=obj["objectType"],
                asset_id=obj.get("assetId"),
            )
        )
    np.save(directory / f"{index:03d}-segmentation.npy", segmentation, allow_pickle=False)
    np.savez_compressed(directory / f"{index:03d}-masks.npz", **arrays)
    (directory / f"{index:03d}.json").write_text(
        json.dumps(
            dict(action_id=identity, catalog=catalog, colors=event.metadata["colors"]), indent=2
        )
        + "\n"
    )


def wrap_response(responder, log_dir):
    index = 0

    def observe(identity, event):
        nonlocal index
        response = responder(identity, event)
        export_instances(event, log_dir / "evaluator_only/instances", index, identity)
        index += 1
        return response

    return observe


if __name__ == "__main__":
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--log-dir", type=Path, required=True)
    args, _ = parser.parse_known_args()
    transport.method_response = wrap_response(transport.method_response, args.log_dir)
    transport.main()
