"""Public-data adapter for isolated learned object mapping; no SDK imports."""

from __future__ import annotations

import atexit
import io
import json
import subprocess
import tempfile
from copy import deepcopy
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from threading import RLock
from typing import Any, cast

import numpy as np

from cpswm.perception_mapping.adapters.rgbd_capture import RawModalityObservation
from cpswm.perception_mapping.natural_mask_surface import MaskSurfaceFrame
from cpswm.perception_mapping.natural_vision import decode_rgb
from cpswm.perception_mapping.unity_rgbd import decode_unity_rgbd
from cpswm.system.reproducibility import content_sha256


class MappingClient:
    def __init__(self, python: str | Path, weights: str | Path) -> None:
        self.lock = RLock()
        self.temp = tempfile.TemporaryDirectory(prefix="cpswm-object-map-")
        self.root = Path(self.temp.name)
        self.log = (self.root / "worker.log").open("w")
        self.process = subprocess.Popen(
            [
                str(python),
                str(
                    Path(__file__).resolve().parents[3]
                    / "tools/external_components/object_mapping_worker.py"
                ),
                str(weights),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.log,
            text=True,
        )
        atexit.register(self.close)
        self._wait("READY")

    def _wait(self, expected: str) -> None:
        assert self.process.stdout is not None
        for line in self.process.stdout:
            if line.strip() == expected:
                return
            if line.strip() == "ERROR":
                break
        raise RuntimeError((self.root / "worker.log").read_text()[-6000:])

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=15)
        self.log.close()
        self.temp.cleanup()

    def run(self, frames: list[dict[str, Any]], spatial: str = "iou") -> dict[str, Any]:
        with self.lock:
            return self._run(frames, spatial)

    def _run(self, frames: list[dict[str, Any]], spatial: str) -> dict[str, Any]:
        source, output = self.root / "input.json", self.root / "output.json"
        source.write_text(json.dumps(dict(frames=frames, spatial=spatial)))
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps(dict(input=str(source), output=str(output))) + "\n")
        self.process.stdin.flush()
        self._wait("DONE")
        return cast(dict[str, Any], json.loads(output.read_text()))


def prepare_frame(
    root: Path,
    rows: tuple[RawModalityObservation, ...],
    cutoff: datetime,
    frame: MaskSurfaceFrame,
) -> dict[str, Any]:
    camera, depth = decode_unity_rgbd(rows, cutoff=cutoff)
    _, rgb = decode_rgb(rows[0], cutoff=cutoff)
    masks = np.load(io.BytesIO(frame.masks_npy), allow_pickle=False)
    candidates = [deepcopy(c) for c in frame.record["candidates"] if c["detector_score"] >= 0.5]
    arrays: dict[str, Any] = dict(rgb=rgb)
    for index, candidate in enumerate(candidates):
        probability = masks[candidate["native_index"]]
        valid = (
            (probability >= 0.5)
            & np.isfinite(depth)
            & (depth > 0)
            & (depth < camera.far_plane_m - camera.near_plane_m)
        )
        vs, us = np.where(valid)
        points = [
            camera.world_point(int(u), int(v), float(depth[v, u]))
            for v, u in zip(vs, us, strict=True)
        ]
        arrays[f"points_{index}"] = np.array(points, dtype=np.float64).reshape(-1, 3)
        arrays[f"colors_{index}"] = rgb[vs, us].astype(np.float64) / 255.0
    key = content_sha256((frame.record["payload_sha256"], candidates))
    path = Path(root) / f"{key}.npz"
    np.savez_compressed(path, **arrays)
    return dict(arrays=str(path), candidates=candidates)


def records_from_mapping(
    detectors: list[dict[str, Any]],
    prepared: list[dict[str, Any]],
    output: dict[str, Any],
) -> list[dict[str, Any]]:
    """Current-view readouts only; remembered geometry never gets a new timestamp."""
    all_anchors: dict[str, tuple[int, dict[str, Any]]] = {}
    records: list[dict[str, Any]] = []
    for index, step in enumerate(output["steps"]):
        for candidate in prepared[index]["candidates"]:
            all_anchors.setdefault(candidate["candidate_id"], (index, candidate))
        tracks = []
        mapped = {o["anchor_id"]: o for o in step["objects"]}
        # Initial candidates stay explicit even if cloud rejection leaves no map object.
        anchors = set(mapped) | {c["candidate_id"] for c in prepared[0]["candidates"]}
        for anchor in sorted(anchors):
            birth, initial = all_anchors[anchor]
            obj = mapped.get(anchor)
            current = [] if obj is None else [o for o in obj["observations"] if o["frame"] == index]
            # Multiple observations may legitimately merge in the original algorithm.
            # One fixed readout rule: highest detector score, then native index.
            rows = [prepared[index]["candidates"][o["candidate"]] for o in current]
            chosen = (
                min(rows, key=lambda c: (-c["detector_score"], c["native_index"])) if rows else None
            )
            tracks.append(
                dict(
                    anchor_id=anchor,
                    category=initial["category"],
                    birth_frame=birth,
                    query_eligible=birth == 0,
                    current_candidate_id=None if chosen is None else chosen["candidate_id"],
                    world_point_m=None if chosen is None else chosen["world_point_m"],
                    selected_pixel_uv=None if chosen is None else chosen["selected_pixel_uv"],
                    selected_feature_ids=[],
                    identity_status="PROVISIONAL",
                    status="CG_MATCHED_CURRENT"
                    if chosen is not None
                    else "CG_NOT_OBSERVED_CURRENT",
                    map_object=obj,
                    matches_current_frame=len(rows),
                )
            )
        records.append(
            dict(
                detector=detectors[index],
                tracks=tracks,
                profile="experimental-conceptgraph-mapping@1",
                association=step["association"],
                cloud_diagnostics=step["diagnostics"],
                model_sha256=output["model_sha256"],
                spatial=output["spatial"],
            )
        )
    return records


_CLIENTS: dict[str, MappingClient] = {}
_CLIENT_LOCK = RLock()


def validate_configuration(value: Any) -> str:
    if type(value) is not dict or set(value) not in (
        {"python", "weights", "spatial"},
        {"python", "weights", "spatial", "readout"},
    ):
        raise ValueError("explicit isolated Python, pinned weights and spatial mode required")
    if value["spatial"] not in ("iou", "overlap_aabb"):
        raise ValueError("unsupported object mapping mode")
    if value.get("readout", "cg_only") not in ("cg_only", "reference_feature_fallback"):
        raise ValueError("unsupported object readout")
    for key in ("python", "weights"):
        if (
            type(value[key]) is not str
            or not Path(value[key]).is_absolute()
            or not Path(value[key]).is_file()
        ):
            raise ValueError("absolute existing object mapping resource required")
    resource = Path(value["weights"])
    metadata = resource.stat()
    pin = _model_digest(
        str(resource),
        (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_size,
            metadata.st_mtime_ns,
            metadata.st_ctime_ns,
        ),
    )
    if pin != "9a78ef8e8c73fd0df621682e7a8e8eb36c6916cb3c16b291a082ecd52ab79cc4":
        raise ValueError("OpenCLIP checkpoint differs")
    root = Path(__file__).resolve().parents[3] / "tools/external_components"
    return content_sha256(
        (
            value,
            pin,
            [
                (p.name, file_sha(p))
                for p in (
                    Path(__file__),
                    root / "object_mapping_worker.py",
                    root / "conceptgraph_object_kernel.py",
                )
            ],
        )
    )


@lru_cache(maxsize=4)
def _model_digest(path: str, metadata: tuple[int, ...]) -> str:
    # A process-local digest cache, invalidated by identity/size/mtime/ctime.
    # Worker startup independently rehashes all bytes. No disk feature cache is trusted.
    return file_sha(path)


def file_sha(path: str | Path) -> str:
    from hashlib import file_digest

    with Path(path).open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


class ExternalObjectSequence:
    """Optional same-profile support producer; no added identity likelihood."""

    def __init__(self, detector: Any, configuration: dict[str, Any]) -> None:
        self.detector = detector
        self.configuration = configuration
        key = content_sha256(configuration)
        with _CLIENT_LOCK:
            if key not in _CLIENTS:
                _CLIENTS[key] = MappingClient(configuration["python"], configuration["weights"])
            self.client = _CLIENTS[key]
        self.prepared: list[dict[str, Any]] = []
        self.detectors: list[dict[str, Any]] = []
        self.reference = None
        if configuration.get("readout") == "reference_feature_fallback":
            from cpswm.perception_mapping.mask_surface_sequence import MaskSurfaceSequence

            self.reference = MaskSurfaceSequence(detector)

    def observe(
        self,
        rows: tuple[RawModalityObservation, ...],
        *,
        cutoff: datetime,
    ) -> tuple[dict[str, Any], MaskSurfaceFrame]:
        frame = self.detector.infer_surface(rows, cutoff=cutoff)
        self.prepared.append(prepare_frame(self.client.root, rows, cutoff, frame))
        self.detectors.append(frame.record)
        mapped = self.client.run(self.prepared, self.configuration["spatial"])
        record = records_from_mapping(self.detectors, self.prepared, mapped)[-1]
        if self.reference is not None:
            reference, _ = self.reference.observe(rows, cutoff=cutoff)
            record = reference_fallback(record, reference)
        return record, frame


def reference_fallback(mapped: dict[str, Any], reference: dict[str, Any]) -> dict[str, Any]:
    """Preserve a reference point within a shared mask, or fill absent map support.

    One coarse mask can contain several objects. A matched mask alone does not
    authorize replacing the original feature-supported point by a different surface.
    This experimental hybrid does not use evaluation identities.
    """
    result = deepcopy(mapped)
    lookup = {t["anchor_id"]: t for t in reference["tracks"]}
    for track in result["tracks"]:
        support = lookup.get(track["anchor_id"])
        if (
            support
            and support["world_point_m"] is not None
            and (
                track["world_point_m"] is None
                or (
                    track.get("current_candidate_id") is not None
                    and track["current_candidate_id"] == support.get("current_candidate_id")
                )
            )
        ):
            old = deepcopy(track)
            track.update(deepcopy(support))
            track["status"] = "CG_REFERENCE_GEOMETRY_FALLBACK"
            track["map_status_before_fallback"] = old["status"]
            track["map_object"] = old["map_object"]
    result["readout"] = "reference_feature_fallback"
    return result
