"""Exact HFD frame correspondence, with author supervision outside runtime inputs.

This is a spent-training development adapter. Original decode indices, not an FPS
resampling grid, bind RGB to author rows. Import clocks are not physical exposure
clocks. No author phase is translated into a full proposal target or contact gold.
"""

from __future__ import annotations

import hashlib
import io
import re
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import numpy as np

from cpswm.contracts.base import BaseRecordMetadata, SourceType, require_aware
from cpswm.data_preflight.full_hfd_training import (
    RECORD,
    encoded,
    inspect_full_training,
    packet_inventory,
)
from cpswm.data_preflight.hocap_joint_supervision import pinned_bytes, strict_json
from cpswm.perception_mapping.adapters.contracts import (
    ObservationEnvelope,
    ObservationIdentity,
    PayloadRef,
    SensorModality,
    SensorRef,
)
from cpswm.perception_mapping.adapters.rgbd_capture import RawModalityObservation
from cpswm.system.reproducibility import content_sha256

POLICY = "first_lexical_trial_per_author_direction_outcome;four_uniform_original_indices@1"
TIME_SEMANTICS = "original_frame_author_clock_unverified_exposure"


def uniform_indices(count: int) -> tuple[int, ...]:
    if type(count) is not int or count < 2:
        raise ValueError("at least two original frames required")
    return tuple(sorted({i * (count - 1) // 3 for i in range(4)}))


def select_trials(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Deterministic development stratification, explicitly uses author outcomes."""
    selected: dict[tuple[str, int], dict[str, Any]] = {}
    for row in sorted(manifest["report"]["trials"], key=lambda r: r["trial"]):
        key = (row["metadata"]["task"], row["outcome"])
        selected.setdefault(key, row)
    return [selected[key] for key in sorted(selected)]


def decode_original_frames(
    video: bytes, *, indices: tuple[int, ...], count: int, shape: tuple[int, ...]
) -> dict[int, bytes]:
    """Sequentially decode frozen bytes; never seek by time or codec frame hints."""
    import cv2

    if (
        not indices
        or indices != tuple(sorted(set(indices)))
        or any(type(i) is not int or not 0 <= i < count for i in indices)
    ):
        raise ValueError("invalid original frame indices")
    if len(shape) != 3 or shape[2] != 3 or min(shape) <= 0 or np.prod(shape) > 4096**2 * 3:
        raise ValueError("unsupported frame shape")
    result = {}
    with tempfile.TemporaryDirectory(prefix="cpswm-hfd-decode-") as tmp:
        frozen = Path(tmp) / "source.mp4"
        frozen.write_bytes(video)
        reader = cv2.VideoCapture(str(frozen))
        index = 0
        try:
            while True:
                ok, pixels = reader.read()
                if not ok:
                    break
                if index >= count or pixels.shape != shape or pixels.dtype != np.uint8:
                    raise ValueError("decoded frame differs from source-derived count/shape")
                if index in indices:
                    payload = io.BytesIO()
                    np.save(payload, cv2.cvtColor(pixels, cv2.COLOR_BGR2RGB), allow_pickle=False)
                    result[index] = payload.getvalue()
                index += 1
        finally:
            reader.release()
    if index != count or set(result) != set(indices):
        raise ValueError("incomplete original video decode")
    return result


def make_observation(
    payload: bytes,
    *,
    video_sha: str,
    clock_sha: str,
    index: int,
    count: int,
    clock: float,
    origin: float,
    shape: tuple[int, ...],
    imported_at: datetime,
) -> RawModalityObservation:
    when = require_aware(imported_at, "imported_at").astimezone(UTC)
    household = uuid5(NAMESPACE_URL, "hfd-author-training-development")
    session = uuid5(household, video_sha + clock_sha)
    trace = uuid5(session, POLICY)
    observation = uuid5(session, f"head_cam/original/{index}")
    receipt = {
        "source_url": RECORD,
        "source_sha256": video_sha,
        "source_clock_sha256": clock_sha,
        "crop_xywh": [0, 0, shape[1], shape[0]],
        "original_frame_index": index,
        "source_frame_count": count,
        "author_clock_seconds": clock,
        "author_clock_origin_seconds": origin,
        "media_time_seconds": clock - origin,
        "time_semantics": TIME_SEMANTICS,
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "observation_id": str(observation),
    }
    env = ObservationEnvelope(
        metadata=BaseRecordMetadata(
            record_id=uuid5(observation, "metadata"),
            schema_name="hfd_original_frame_import",
            schema_version="1.0.0",
            household_id=household,
            session_id=session,
            trace_id=trace,
            recorded_time=when,
            source_type=SourceType.IMPORT,
            source_id=RECORD,
        ),
        identity=ObservationIdentity(
            observation_id=observation, household_id=household, session_id=session, trace_id=trace
        ),
        sensor=SensorRef(sensor_id="hfd-head-rgb", modality=SensorModality.RGB),
        capture_time=when,
        arrival_time=when,
        clock_domain="archive-import-acquisition-utc",
        frame_id="original-head-camera-pixels",
        payload=PayloadRef(
            payload_id=observation,
            payload_sha256=receipt["payload_sha256"],
            size_bytes=len(payload),
        ),
    )
    raw = RawModalityObservation(
        env.model_dump_json(), payload, content_sha256(receipt), None, encoded(receipt).decode()
    )
    raw.envelope()
    return raw


def alignment_artifacts(
    intake: Path,
    manifest: dict[str, Any],
    *,
    imported_at: datetime,
) -> tuple[dict[str, bytes], dict[str, Any]]:
    """Consume a source-reconstructed manifest; never a self-certified receipt."""
    when = require_aware(imported_at, "imported_at").astimezone(UTC)
    files: dict[str, bytes] = {}
    runtime_index: list[dict[str, Any]] = []
    evaluator: list[dict[str, Any]] = []
    selected_rows: list[dict[str, Any]] = []
    for row in select_trials(manifest):
        trial = row["trial"]
        video_name, clock_name = f"raw/{trial}/head_cam.mp4", f"raw/{trial}/head_cam_ts.npy"
        label_name = f"evaluator/{trial}/author_rows.jsonl"
        video_sha = manifest["raw_members"][video_name]["sha256"]
        clock_sha = manifest["raw_members"][clock_name]["sha256"]
        video = pinned_bytes(intake, video_name, video_sha)
        times = np.load(io.BytesIO(pinned_bytes(intake, clock_name, clock_sha)), allow_pickle=False)
        labels = [
            strict_json(line)
            for line in pinned_bytes(
                intake, label_name, manifest["evaluator_files"][label_name]["sha256"]
            ).splitlines()
        ]
        raw_times_name = f"raw/{trial}/wrench_ts.npy"
        raw_times = np.load(
            io.BytesIO(
                pinned_bytes(
                    intake, raw_times_name, manifest["raw_members"][raw_times_name]["sha256"]
                )
            ),
            allow_pickle=False,
        )
        count, shape = row["decoded_frames"], tuple(row["frame_shape"])
        if len(times) != count or len(labels) != count:
            raise ValueError("source clock/label count mismatch")
        indices = uniform_indices(count)
        frames = decode_original_frames(video, indices=indices, count=count, shape=shape)
        # This sequence key depends only on raw sensor sources, not trial answers.
        sequence = hashlib.sha256((video_sha + clock_sha).encode()).hexdigest()
        for i in indices:
            label = labels[i]
            if label["frame_index"] != i or label["timestamp_seconds"] != float(times[i]):
                raise ValueError("author row is not the same original frame and clock")
            raw = make_observation(
                frames[i],
                video_sha=video_sha,
                clock_sha=clock_sha,
                index=i,
                count=count,
                clock=float(times[i]),
                origin=float(times[0]),
                shape=shape,
                imported_at=when + timedelta(microseconds=indices.index(i)),
            )
            env = raw.envelope()
            key = f"{sequence}/{i:06d}"
            base = f"runtime/{key}"
            if base + ".npy" in files:
                raise ValueError("duplicate sensor source across selected author trials")
            files[base + ".npy"] = raw.payload_bytes
            files[base + ".envelope.json"] = raw.envelope_json.encode()
            assert raw.archive_sampling_json is not None
            files[base + ".receipt.json"] = raw.archive_sampling_json.encode()
            runtime_index.append(
                {
                    "key": key,
                    "observation_id": str(env.identity.observation_id),
                    "payload_sha256": hashlib.sha256(raw.payload_bytes).hexdigest(),
                    "receipt_sha256": raw.capture_receipt_sha256,
                }
            )
            evaluator.append(
                {
                    "key": key,
                    "observation_id": str(env.identity.observation_id),
                    "payload_sha256": hashlib.sha256(raw.payload_bytes).hexdigest(),
                    "source_video_sha256": video_sha,
                    "trial": trial,
                    "author_frame": label,
                    "author_outcome": row["outcome"],
                    "author_task": row["metadata"]["task"],
                    "author_robot": row["metadata"]["robot"],
                    "wrench_kind": row["wrench_kind"],
                    "within_raw_wrench_time_range": bool(raw_times[0] <= times[i] <= raw_times[-1]),
                    "all_zero_resampled_wrench": all(v == 0 for v in label["wrench_resampled"]),
                    "human_phase_boundaries": row["human_phase_boundaries"],
                    "temporal_error_bound_seconds": None,
                    "independent_human_review": False,
                    "actor_identity": None,
                    "full_proposal_target": None,
                    "full_proposal_training_ready": False,
                    "native_publication_authorized": False,
                }
            )
        selected_rows.append(
            {
                "trial": trial,
                "task": row["metadata"]["task"],
                "outcome": row["outcome"],
                "source_frames": count,
                "selected_original_indices": list(indices),
            }
        )
    runtime_index.sort(key=lambda r: r["key"])
    files["runtime/index.jsonl"] = b"".join(encoded(r) for r in runtime_index)
    runtime_manifest = {
        "format": "hfd-original-runtime-inputs@1",
        "intake_manifest_sha256": hashlib.sha256(encoded(manifest)).hexdigest(),
        "files": {
            name.removeprefix("runtime/"): hashlib.sha256(raw).hexdigest()
            for name, raw in sorted(files.items())
        },
    }
    files["runtime/manifest.json"] = encoded(runtime_manifest)
    files["evaluator/author_supervision.jsonl"] = b"".join(encoded(r) for r in evaluator)
    report = {
        "format": "hfd-original-frame-alignment@1",
        "policy": POLICY,
        "intake_manifest_sha256": hashlib.sha256(encoded(manifest)).hexdigest(),
        "imported_at": when.isoformat(),
        "selection_uses_author_outcomes_for_development_stratification": True,
        "enrolled_trials": manifest["report"]["enrolled_trials"],
        "accepted_trials": manifest["report"]["accepted_trials"],
        "accepted_source_frames": manifest["report"]["accepted_frames"],
        "quarantined_trials": manifest["report"]["quarantined_trials"],
        "selected_trials": selected_rows,
        "selected_frames": len(runtime_index),
        "sampled_accuracy_or_population_estimate": False,
        "retrospective_sampling_not_online_policy": True,
        "runtime_event_clock": "import_order_not_physical_event_duration",
        "pixel_annotation_overlay_audit": "NOT_ESTABLISHED_BY_THIS_ADAPTER",
        "complete_proposal_targets": 0,
        "full_proposal_training_ready": False,
        "independent_contact_identity_pose_calibration": False,
        "native_publication_authorized": False,
        "files": {
            name: {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
            for name, raw in sorted(files.items())
        },
    }
    return files, report


def align_hfd_training(
    *,
    archive: Path,
    metadata: Path,
    intake: Path,
    output: Path,
    imported_at: datetime,
    verify: bool = False,
) -> dict[str, Any]:
    """Reconstruct source roots on every call; a resealed output is not authority."""
    if not verify and output.exists():
        raise FileExistsError(output)
    before = packet_inventory(output) if verify else None
    manifest = inspect_full_training(archive, metadata, intake, verify=True)
    files, report = alignment_artifacts(intake, manifest, imported_at=imported_at)
    files["manifest.json"] = encoded(report)
    if verify:
        if set(packet_inventory(output)) != set(files):
            raise ValueError("alignment package member coverage differs")
        for name, expected in files.items():
            if (output / name).read_bytes() != expected:
                raise ValueError("alignment artifact differs from original source: " + name)
        if packet_inventory(output) != before:
            raise ValueError("alignment package changed during verification")
    else:
        output.mkdir(parents=True, exist_ok=False)
        # Manifest is last. A partial package is never accepted by reconstruction.
        for name, payload in files.items():
            path = output / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(payload)
    return report


def load_runtime_observations(
    root: Path,
    *,
    manifest_sha256: str,
) -> tuple[tuple[str, RawModalityObservation], ...]:
    """Load only the runtime subtree, pinned by the source-reconstructing caller.

    A digest obtained from this same untrusted package is not source verification.
    This function validates the selected bytes, not external annotation accuracy.
    """
    before = packet_inventory(root)
    manifest = strict_json(pinned_bytes(root, "manifest.json", manifest_sha256))
    if set(manifest) != {"format", "intake_manifest_sha256", "files"} or (
        manifest["format"] != "hfd-original-runtime-inputs@1"
    ):
        raise ValueError("unexpected runtime manifest")
    index = [
        strict_json(line)
        for line in pinned_bytes(root, "index.jsonl", manifest["files"]["index.jsonl"]).splitlines()
    ]
    if not 1 <= len(index) <= 256:
        raise ValueError("runtime sample exceeds local development budget")
    files = {"manifest.json", "index.jsonl"}
    observed: list[tuple[str, RawModalityObservation]] = []
    keys: set[str] = set()
    ids: set[str] = set()
    previous: dict[str, int] = {}
    from cpswm.perception_mapping.natural_vision import decode_rgb

    for row in index:
        key = row.get("key")
        if (
            set(row) != {"key", "observation_id", "payload_sha256", "receipt_sha256"}
            or not isinstance(key, str)
            or re.fullmatch(r"[0-9a-f]{64}/[0-9]{6}", key) is None
            or key in keys
        ):
            raise ValueError("invalid or duplicate runtime original frame key")
        keys.add(key)
        data = {}
        for suffix in (".npy", ".envelope.json", ".receipt.json"):
            name = key + suffix
            files.add(name)
            data[suffix] = pinned_bytes(root, name, manifest["files"][name])
        raw = RawModalityObservation(
            data[".envelope.json"].decode(),
            data[".npy"],
            row["receipt_sha256"],
            None,
            data[".receipt.json"].decode(),
        )
        env = raw.envelope()
        _, pixels = decode_rgb(raw, cutoff=env.arrival_time)
        receipt = strict_json(data[".receipt.json"])
        if receipt["time_semantics"] != TIME_SEMANTICS:
            raise ValueError("resampled frames cannot join original author indices")
        sequence = hashlib.sha256(
            (receipt["source_sha256"] + receipt["source_clock_sha256"]).encode()
        ).hexdigest()
        frame = receipt["original_frame_index"]
        if (
            key != f"{sequence}/{frame:06d}"
            or str(env.identity.observation_id) != row["observation_id"]
            or row["observation_id"] in ids
            or hashlib.sha256(raw.payload_bytes).hexdigest() != row["payload_sha256"]
            or receipt["crop_xywh"] != [0, 0, pixels.shape[1], pixels.shape[0]]
            or frame <= previous.get(sequence, -1)
        ):
            raise ValueError("runtime key/pixels/receipt correspondence differs")
        ids.add(row["observation_id"])
        previous[sequence] = frame
        observed.append((key, raw))
    if files != set(before) or set(manifest["files"]) != files - {"manifest.json"}:
        raise ValueError("unexpected or missing runtime member")
    if packet_inventory(root) != before:
        raise ValueError("runtime source changed during admission")
    return tuple(observed)
