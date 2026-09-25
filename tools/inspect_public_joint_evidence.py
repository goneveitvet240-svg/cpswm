"""Verify public receipts, build evaluator-only data and descriptive pose residuals."""

import argparse
import hashlib
import io
import json
import tarfile
from pathlib import Path, PurePosixPath

import cv2
import numpy as np

from cpswm.data_preflight.hocap_joint_supervision import strict_json
from cpswm.data_preflight.public_evidence_registry import (
    ENROLLMENT_REVIEW,
    enrolled_source_snapshot,
)
from cpswm.data_preflight.public_handover_evidence import (
    inspect_hfd_trial,
    inspect_rpl_archive,
    pose_residuals,
)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, allow_nan=False) + "\n" for r in rows))


def run(source: Path, output: Path):
    snapshot = enrolled_source_snapshot(source)
    output.mkdir(parents=True, exist_ok=False)
    source_hashes = {}

    def author_bytes(name, sha=None, md5=None):
        if name not in snapshot:
            raise ValueError("source not in enrolled author registry")
        b = snapshot[name]
        if sha is not None and hashlib.sha256(b).hexdigest() != sha:
            raise ValueError("source SHA256 differs from receipt")
        if md5 is not None and hashlib.md5(b).hexdigest() != md5:
            raise ValueError("author MD5 mismatch: " + name)
        source_hashes[name] = hashlib.sha256(b).hexdigest()
        return b

    ope_receipts = strict_json(author_bytes("ope-receipts.json"))
    poses = {}
    for r in ope_receipts:
        if r["status"] != "downloaded":
            raise ValueError("missing author pose artifact")
        poses[r["name"]] = strict_json(author_bytes(r["name"] + ".json", sha=r["sha256"]))
    residuals, pose_summary = pose_residuals(poses["ope_gt"], poses["ope_demo"])
    jsonl(output / "evaluator/pose_residuals.jsonl", residuals)
    write(output / "pose_summary.json", pose_summary)
    rpl = strict_json(author_bytes("rpl/receipts.json"))
    for r in rpl:
        b = author_bytes("rpl/" + r["path"], sha=r["sha256"])
        if hashlib.sha1(f"blob {len(b)}\0".encode() + b).hexdigest() != r["git_blob"]:
            raise ValueError("RPL author blob mismatch")
    rpl_bytes = author_bytes("rpl/one_saved_handover_New.zip")
    sensors, rpl_summary = inspect_rpl_archive(rpl_bytes)
    jsonl(output / "evaluator/rpl_sensor_rows.jsonl", sensors)
    write(output / "rpl_summary.json", rpl_summary)
    record = strict_json(author_bytes("handover-record.json"))
    files = {f["key"]: f for f in record["files"]}
    # Pin the full author metadata, not just a freshly computed local hash.
    for name in ("datasheet.pdf", "training_labels.tar.gz", "class_names.json"):
        author_bytes(name, md5=files[name]["checksum"].removeprefix("md5:"))
    payload = author_bytes(
        "sample_training_set.verified.tar.gz",
        md5=files["sample_training_set.tar.gz"]["checksum"].removeprefix("md5:"),
    )
    with tarfile.open(fileobj=io.BytesIO(author_bytes("training_labels.tar.gz"))) as labels:
        outcomes = {}
        for m in labels:
            if m.isfile():
                outcomes[PurePosixPath(m.name).stem] = strict_json(labels.extractfile(m).read())
    summaries = []
    with tarfile.open(fileobj=io.BytesIO(payload)) as archive:
        members = {m.name: m for m in archive if m.isfile()}
        trials = sorted({n.split("/")[1] for n in members})
        if trials != ["trial0000", "trial0002"]:
            raise ValueError("unexpected sample selection")
        for trial in trials:
            prefix = f"sample_training_set/{trial}/"
            arrays = {}
            for name in (
                "head_cam_ts",
                "wrench_ts",
                "human_activity",
                "robot_actions",
                "wrench",
                "wrench_resampled",
            ):
                b = archive.extractfile(members[prefix + name + ".npy"]).read()
                arrays[name] = np.load(io.BytesIO(b), allow_pickle=False)
            info = strict_json(archive.extractfile(members[prefix + "task_info.json"]).read())
            rows, summary = inspect_hfd_trial(arrays, info, outcomes[trial])
            video = archive.extractfile(members[prefix + "head_cam.mp4"]).read()
            video_path = output / "raw" / trial / "head_cam.mp4"
            video_path.parent.mkdir(parents=True, exist_ok=True)
            video_path.write_bytes(video)
            reader = cv2.VideoCapture(str(video_path))
            count, shape = 0, None
            try:
                while True:
                    ok, frame = reader.read()
                    if not ok:
                        break
                    shape = list(frame.shape)
                    count += 1
            finally:
                reader.release()
            if count != len(rows):
                raise ValueError("decoded video count differs from author label/timestamp count")
            jsonl(output / "evaluator" / trial / "author_rows.jsonl", rows)
            summaries.append(
                {
                    "trial": trial,
                    **summary,
                    "decoded_frames": count,
                    "frame_shape": shape,
                    "video_sha256": hashlib.sha256(video).hexdigest(),
                }
            )
    if enrolled_source_snapshot(source) != snapshot:
        raise ValueError("public source changed during inspection")
    result = {
        "enrollment_review_commit": ENROLLMENT_REVIEW,
        "enrolled_source_snapshot_verified": True,
        "annotation_truth_independently_verified": False,
        "pose": pose_summary,
        "rpl": rpl_summary,
        "hfd_trials": summaries,
        "source_sha256s": source_hashes,
        "runtime_label_injection": False,
        "native_proposal_supervision_complete": False,
        "natural_closed_loop_verified": False,
    }
    write(output / "summary.json", result)
    print(
        json.dumps(
            {
                "pose_pairs": len(residuals),
                "rpl_samples": len(sensors),
                "hfd_frames": sum(s["frames"] for s in summaries),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.source, args.output)
