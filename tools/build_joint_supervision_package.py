"""Build a reviewable data package; missing supervision never becomes a target."""

import argparse
import hashlib
import json
from pathlib import Path

from cpswm.data_preflight.hocap_joint_supervision import assemble_subset, pinned_bytes, strict_json


def run(spec_path: Path, output: Path) -> dict:
    spec_bytes = spec_path.read_bytes()
    spec = strict_json(spec_bytes)
    if set(spec) != {"hocap_subsets"} or not spec["hocap_subsets"]:
        raise ValueError("pinned HO-Cap subsets required")
    packs = [
        assemble_subset(
            Path(s["root"]),
            raw_sha256=s["raw_sha256"],
            annotation_sha256=s["annotation_sha256"],
            receipts_sha256=s["receipts_sha256"],
        )
        for s in spec["hocap_subsets"]
    ]
    inputs = [r for p in packs for r in p["model_inputs"]]
    labels = [r for p in packs for r in p["evaluator_only"]]
    keys = [(r["sequence_id"], r["camera_id"], r["frame_index"]) for r in inputs]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate frame across subsets; windows are not independent sequences")
    if spec_path.read_bytes() != spec_bytes:
        raise ValueError("source specification changed")
    # All subsets must still match at the common publication boundary.
    for subset, pack in zip(spec["hocap_subsets"], packs, strict=True):
        for name, digest in pack["source_files"].items():
            pinned_bytes(Path(subset["root"]), name, digest)
    output.mkdir(parents=True, exist_ok=False)
    for name, rows in (("model_inputs.jsonl", inputs), ("evaluator_pose_labels.jsonl", labels)):
        (output / name).write_text(
            "".join(json.dumps(r, sort_keys=True, allow_nan=False) + "\n" for r in rows)
        )
    summary = {
        "scope": "AUTHOR_SUPERVISION_PACKAGE_FOR_REVIEW_NOT_TRAINING_AUTHORIZATION",
        "frames": len(inputs),
        "sequences": sorted({k[0] for k in keys}),
        "subjects": sorted({k[0].split("/")[0] for k in keys}),
        "object_pose_rows": sum(len(r["objects"]) for r in labels),
        "visible_object_pose_rows": sum(
            o["visible_mask_pixels"] > 0 for r in labels for o in r["objects"]
        ),
        "maximum_cross_file_pose_error": max(
            o["cross_file_max_abs"] for r in labels for o in r["objects"]
        ),
        "split": "all spent development; no new train/validation/confirmation assignment",
        "proposal_operation_labels": {
            k: 0
            for k in (
                "branch",
                "revise",
                "retract",
                "reactivate",
                "rejuvenate",
                "preserve_unresolved",
            )
        },
        "independently_reviewed": False,
        "full_proposal_training_ready": False,
        "measurement_noise_calibrated": False,
        "natural_semantic_transitions": 0,
        "blockers": sorted({b for p in packs for b in p["blockers"]}),
        "specification_sha256": hashlib.sha256(spec_bytes).hexdigest(),
        "files": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.glob("*.jsonl")
        },
        "subsets": [
            {k: v for k, v in p.items() if k not in {"model_inputs", "evaluator_only"}}
            for p in packs
        ],
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.spec, args.output)
    print(json.dumps({k: v for k, v in result.items() if k != "subsets"}, indent=2))
