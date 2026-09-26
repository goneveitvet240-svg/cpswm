"""Source-bound inspection of the author's full HFD training split.

Author labels are retained as single-annotator evidence. Nothing here converts
them into exact contact/release truth, identities, calibrated factors or runtime
authority. Published training bytes, not a caller's receipt, are the input root.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import stat
import tarfile
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any

import numpy as np

from cpswm.data_preflight.hocap_joint_supervision import pinned_bytes, strict_json
from cpswm.data_preflight.public_evidence_registry import ENROLLED_SOURCE_SHA256S
from cpswm.data_preflight.public_handover_evidence import inspect_hfd_trial

ARCHIVE_BYTES = 9185706983
ARCHIVE_MD5 = "14232fcd1b34030b77db48d8c771710d"
RECORD = "https://zenodo.org/records/10708763"
ARRAYS = (
    "head_cam_ts",
    "wrench_ts",
    "human_activity",
    "robot_actions",
    "wrench",
    "wrench_resampled",
)
REQUIRED = frozenset([*(f"{name}.npy" for name in ARRAYS), "head_cam.mp4", "task_info.json"])
MAX_MEMBER_BYTES = 512 * 1024 * 1024
MAX_SELECTED_BYTES = 16 * 1024**3


def encoded(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode()


def file_hashes(path: Path) -> dict[str, Any]:
    md5, sha = hashlib.md5(), hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(4 * 1024 * 1024):
            size += len(chunk)
            md5.update(chunk)
            sha.update(chunk)
    return {"bytes": size, "md5": md5.hexdigest(), "sha256": sha.hexdigest()}


def file_identity(path: Path) -> tuple[int, ...]:
    state = path.stat()
    return state.st_dev, state.st_ino, state.st_size, state.st_mtime_ns, state.st_ctime_ns


def packet_inventory(root: Path) -> dict[str, tuple[int, ...]]:
    if root.is_symlink():
        raise ValueError("packet root cannot be a symbolic link")
    result = {}
    for path in root.rglob("*"):
        state = path.lstat()
        if stat.S_ISLNK(state.st_mode):
            raise ValueError("packet aliases and symbolic links are not accepted")
        if stat.S_ISREG(state.st_mode):
            if state.st_nlink != 1:
                raise ValueError("packet hard-link aliases are not accepted")
            result[str(path.relative_to(root))] = file_identity(path)
        elif not stat.S_ISDIR(state.st_mode):
            raise ValueError("packet special files are not regular evidence artifacts")
    return result


def check_members(root: Path, members: dict[str, dict[str, Any]]) -> None:
    for relative, expected in members.items():
        actual = file_hashes(root / relative)
        if actual["bytes"] != expected["bytes"] or actual["sha256"] != expected["sha256"]:
            raise ValueError("staged member differs from source-derived artifact bytes")


def canonical_member(member: tarfile.TarInfo) -> tuple[str, ...]:
    name = member.name
    if "\\" in name or name.startswith("/") or ".." in name.split("/"):
        raise ValueError("unsafe author archive member path")
    if not (member.isfile() or member.isdir()) or member.size < 0:
        raise ValueError("archive links and special members are not evidence")
    parts = PurePosixPath(name).parts
    if not parts or any(p in {"", ".", ".."} for p in parts):
        raise ValueError("invalid author member identity")
    if member.size > MAX_MEMBER_BYTES:
        raise ValueError("author archive member exceeds inspection resource budget")
    return parts


def load_author_metadata(root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    inputs = {
        name: pinned_bytes(root, name, ENROLLED_SOURCE_SHA256S[name])
        for name in (
            "training_labels.tar.gz",
            "handover-record.json",
            "class_names.json",
            "datasheet.pdf",
        )
    }
    record = strict_json(inputs["handover-record.json"])
    entry = next(f for f in record["files"] if f["key"] == "training_set.tar.gz")
    if entry["size"] != ARCHIVE_BYTES or entry["checksum"] != "md5:" + ARCHIVE_MD5:
        raise ValueError("author record does not match the fixed full training archive")
    outcomes = {}
    with tarfile.open(fileobj=io.BytesIO(inputs["training_labels.tar.gz"])) as archive:
        for member in archive:
            parts = canonical_member(member)
            if member.isdir():
                continue
            if (
                len(parts) != 2
                or parts[0] != "training_labels"
                or not re.fullmatch(r"trial\d{4}\.json", parts[1])
            ):
                raise ValueError("unexpected training outcome member")
            trial = PurePosixPath(parts[1]).stem
            if trial in outcomes:
                raise ValueError("duplicate author outcome identity")
            stream = archive.extractfile(member)
            assert stream is not None
            row = strict_json(stream.read())
            if (
                set(row) != {"task", "robot", "outcome"}
                or type(row["outcome"]) is not int
                or row["outcome"] not in range(4)
            ):
                raise ValueError("invalid author outcome schema")
            outcomes[trial] = row
    if len(outcomes) != 337 or sum(row["outcome"] == 0 for row in outcomes.values()) != 90:
        raise ValueError("published training label coverage changed")
    return outcomes, {name: hashlib.sha256(raw).hexdigest() for name, raw in inputs.items()}


def stream_members(
    archive_path: Path,
    outcomes: dict[str, dict[str, Any]],
    destination: Path | None,
) -> dict[str, dict[str, Any]]:
    """Read the full archive once, copy only declared raw modalities, never extractall."""
    selected: dict[str, dict[str, Any]] = {}
    seen: set[tuple[str, ...]] = set()
    trials: set[str] = set()
    total = 0
    with tarfile.open(archive_path, mode="r|gz") as archive:
        for member in archive:
            parts = canonical_member(member)
            if parts[0] != "training_set":
                raise ValueError("unexpected training archive root")
            if member.isdir():
                continue
            if parts in seen:
                raise ValueError("duplicate author archive member")
            seen.add(parts)
            if len(seen) > 1_000_000 or len(parts) < 3 or not re.fullmatch(r"trial\d{4}", parts[1]):
                raise ValueError("invalid training archive trial or member count")
            trial = parts[1]
            if trial not in outcomes:
                raise ValueError("training video has no enrolled outcome")
            trials.add(trial)
            if len(parts) != 3 or parts[2] not in REQUIRED:
                continue
            total += member.size
            if total > MAX_SELECTED_BYTES:
                raise ValueError("selected raw modalities exceed inspection resource budget")
            relative = f"raw/{trial}/{parts[2]}"
            stream = archive.extractfile(member)
            assert stream is not None
            writer = None
            sha, count = hashlib.sha256(), 0
            try:
                if destination is not None:
                    target = destination / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    writer = target.open("xb")
                while chunk := stream.read(1024 * 1024):
                    sha.update(chunk)
                    count += len(chunk)
                    if writer is not None:
                        writer.write(chunk)
            finally:
                if writer is not None:
                    writer.close()
            if count != member.size:
                raise ValueError("short author member")
            selected[relative] = {
                "archive_member": member.name,
                "bytes": count,
                "sha256": sha.hexdigest(),
            }
    if trials != set(outcomes) or set(selected) != {
        f"raw/{trial}/{name}" for trial in outcomes for name in REQUIRED
    }:
        raise ValueError("full training member/outcome coverage is incomplete")
    return selected


def inspect_trial(root: Path, trial: str, outcome: dict[str, Any]) -> tuple[bytes, dict[str, Any]]:
    import cv2

    arrays = {
        name: np.load(root / "raw" / trial / f"{name}.npy", allow_pickle=False) for name in ARRAYS
    }
    info = strict_json((root / "raw" / trial / "task_info.json").read_bytes())
    rows, summary = inspect_hfd_trial(arrays, info, outcome)
    reader = cv2.VideoCapture(str(root / "raw" / trial / "head_cam.mp4"))
    frames, shape = 0, None
    try:
        while True:
            ok, frame = reader.read()
            if not ok:
                break
            current = list(frame.shape)
            if shape is not None and current != shape:
                raise ValueError("video resolution changes within a training trial")
            shape = current
            frames += 1
    finally:
        reader.release()
    if frames != len(rows):
        raise ValueError("decoded video count differs from author timestamps and labels")
    return b"".join(encoded(row) for row in rows), {
        "trial": trial,
        **summary,
        "decoded_frames": frames,
        "frame_shape": shape,
    }


def build_report(
    root: Path,
    outcomes: dict[str, dict[str, Any]],
    *,
    write_rows: bool,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    accepted, rejected, artifacts = [], [], {}
    for trial, outcome in sorted(outcomes.items()):
        try:
            rows, summary = inspect_trial(root, trial, outcome)
        except (ValueError, OSError) as error:
            rejected.append({"trial": trial, "author_outcome": outcome, "reason": str(error)})
            continue
        relative = f"evaluator/{trial}/author_rows.jsonl"
        if write_rows:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(rows)
        elif not (root / relative).is_file() or (root / relative).read_bytes() != rows:
            raise ValueError("exported labels differ from source-derived author rows")
        artifacts[relative] = {"bytes": len(rows), "sha256": hashlib.sha256(rows).hexdigest()}
        accepted.append(summary)
    counts = Counter((row["metadata"]["task"], row["outcome"]) for row in accepted)
    return {
        "trials": accepted,
        "quarantined_trials": rejected,
        "enrolled_trials": len(outcomes),
        "accepted_trials": len(accepted),
        "accepted_frames": sum(row["frames"] for row in accepted),
        "accepted_success_trials": sum(row["outcome"] == 0 for row in accepted),
        "accepted_outcome_counts": [
            {"task": key[0], "outcome": key[1], "trials": count}
            for key, count in sorted(counts.items())
        ],
        "author_annotation_reviewers": 1,
        "independent_reannotation": False,
        "exact_contact_release_gold": False,
        "global_person_identity_gold": False,
        "our_frontend_pose_calibration": False,
        "full_proposal_training_ready": False,
        "new_optimizer_steps": 0,
        "native_publication_authorized": False,
        "runtime_label_injection": False,
        "validation_or_test_split_read": False,
    }, artifacts


def inspect_full_training(
    archive: Path, metadata: Path, output: Path, *, verify: bool = False
) -> dict[str, Any]:
    outcomes, metadata_sha = load_author_metadata(metadata)
    identity = file_identity(archive)
    hashes = file_hashes(archive)
    if hashes["bytes"] != ARCHIVE_BYTES or hashes["md5"] != ARCHIVE_MD5:
        raise ValueError("full training archive differs from published author bytes")
    if not verify:
        output.mkdir(parents=True, exist_ok=False)
    members = stream_members(archive, outcomes, None if verify else output)
    before = packet_inventory(output)
    check_members(output, members)
    report, row_files = build_report(output, outcomes, write_rows=not verify)
    manifest = {
        "format": "hfd-full-training-evidence@1",
        "record": RECORD,
        "license": "CC BY 4.0",
        "author_archive": hashes,
        "metadata_sha256s": metadata_sha,
        "raw_members": members,
        "evaluator_files": row_files,
        "report": report,
    }
    if (
        file_identity(archive) != identity
        or file_hashes(archive) != hashes
        or load_author_metadata(metadata)[1] != metadata_sha
    ):
        raise ValueError("source changed during full training inspection")
    payload = encoded(manifest)
    expected_files = {*members, *row_files}
    if verify:
        expected_files.add("manifest.json")
    after = packet_inventory(output)
    if set(after) != expected_files or any(
        after.get(name) != identity for name, identity in before.items()
    ):
        raise ValueError("packet artifacts changed, escaped or have undeclared/missing members")
    check_members(output, {**members, **row_files})
    # Content hashing is itself a custody interval. Detect both rewritten bytes
    # and new artifacts introduced after the previous directory inventory.
    if packet_inventory(output) != after:
        raise ValueError("packet artifacts changed during final content verification")
    if verify:
        if (output / "manifest.json").read_bytes() != payload:
            raise ValueError("packet differs from full source-derived reconstruction")
    else:
        pending = output / ".manifest.pending"
        with pending.open("xb") as writer:
            writer.write(payload)
            writer.flush()
            os.fsync(writer.fileno())
        pending.replace(output / "manifest.json")
    return manifest
