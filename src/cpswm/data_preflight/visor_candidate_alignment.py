"""Offline all-pairs geometry. No assignment threshold, identity or contact authority.

The prediction digest must come from the caller's frozen execution receipt, not
from the prediction file. It binds bytes, not an independent model attestation.
"""

from __future__ import annotations

import hashlib
import io
import math
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import numpy as np
from PIL import Image, ImageDraw

from cpswm.contracts.base import BaseRecordMetadata, SourceType, require_aware
from cpswm.data_preflight.full_hfd_training import encoded, packet_inventory
from cpswm.data_preflight.hocap_joint_supervision import strict_json
from cpswm.data_preflight.visor_contact_supervision import (
    HANDS,
    _derive,
    _source_bytes,
    _verify_artifacts,
)
from cpswm.perception_mapping.adapters.contracts import (
    ObservationEnvelope,
    ObservationIdentity,
    PayloadRef,
    SensorModality,
    SensorRef,
)
from cpswm.perception_mapping.adapters.rgbd_capture import RawModalityObservation
from cpswm.perception_mapping.natural_hands import HAND_MODEL_SHA256, ROI_PROFILE
from cpswm.perception_mapping.natural_vision import FasterNaturalAppearanceDetector

PROFILE = {
    "object_model": FasterNaturalAppearanceDetector.model_id,
    "object_weights": FasterNaturalAppearanceDetector.weights_sha256,
    "minimum_score": 0.5,
    "hand_weights": HAND_MODEL_SHA256,
    "hand_regions": ROI_PROFILE,
    "hands_per_region": 4,
    "hand_detection_confidence": 0.5,
    "hand_presence_confidence": 0.5,
}
SCOPE = tuple(uuid5(NAMESPACE_URL, "visor-rgb-component:" + name) for name in ("h", "s", "t"))


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def runtime_frames(runtime: Path, manifest_sha256: str) -> list[tuple[dict[str, Any], bytes]]:
    """Read only the RGB subtree into immutable byte snapshots, before inference."""
    before = packet_inventory(runtime)
    raw = (runtime / "manifest.json").read_bytes()
    if sha(raw) != manifest_sha256:
        raise ValueError("runtime differs from external manifest pin")
    manifest = strict_json(raw)
    if set(manifest) != {"format", "frames"} or manifest["format"] != "visor_rgb_only_v1":
        raise ValueError("invalid RGB-only manifest")
    rows = manifest["frames"]
    if type(rows) is not list or not 1 <= len(rows) <= 1000:
        raise ValueError("invalid frame count")
    result, members = [], {"manifest.json"}
    for i, row in enumerate(rows):
        if (
            set(row) != {"key", "ordinal", "rgb", "rgb_sha256", "pixel_sha256", "width", "height"}
            or type(row["ordinal"]) is not int
            or row["ordinal"] != i
            or any(type(row[n]) is not int or not 0 < row[n] <= 4096 for n in ("width", "height"))
            or any(
                not isinstance(row[n], str) or not re.fullmatch(r"[0-9a-f]{64}", row[n])
                for n in ("key", "rgb_sha256", "pixel_sha256")
            )
            or row["key"] != sha(encoded({"ordinal": i, "rgb_sha256": row["rgb_sha256"]}))
            or row["rgb"] != "runtime/frames/" + row["key"] + ".jpg"
        ):
            raise ValueError("invalid RGB frame identity")
        relative = row["rgb"].removeprefix("runtime/")
        image_bytes = (runtime / relative).read_bytes()
        if len(image_bytes) > 4 * 1024**2 or sha(image_bytes) != row["rgb_sha256"]:
            raise ValueError("RGB differs from source pin")
        with Image.open(io.BytesIO(image_bytes)) as image:
            if (
                image.format != "JPEG"
                or image.mode != "RGB"
                or image.size != (row["width"], row["height"])
            ):
                raise ValueError("unexpected RGB format or dimensions")
            if sha(image.tobytes()) != row["pixel_sha256"]:
                raise ValueError("RGB pixels differ from source")
        members.add(relative)
        result.append((row, image_bytes))
    if set(before) != members or packet_inventory(runtime) != before:
        raise ValueError("RGB inventory changed or has extra/missing members")
    return result


def observation(
    row: dict[str, Any], image_bytes: bytes, imported_at: datetime
) -> RawModalityObservation:
    """Single-frame import clock only. No archive timeline or fabricated FPS."""
    when = require_aware(imported_at, "imported_at")
    if sha(image_bytes) != row["rgb_sha256"]:
        raise ValueError("frame byte mismatch")
    with Image.open(io.BytesIO(image_bytes)) as image:
        pixels = np.asarray(image).copy()
    if (
        pixels.shape != (row["height"], row["width"], 3)
        or sha(pixels.tobytes()) != row["pixel_sha256"]
    ):
        raise ValueError("frame pixel mismatch")
    buf = io.BytesIO()
    np.save(buf, pixels, allow_pickle=False)
    payload = buf.getvalue()
    h, s, t = SCOPE
    ident = uuid5(t, row["key"])
    env = ObservationEnvelope(
        metadata=BaseRecordMetadata(
            record_id=uuid5(ident, "metadata"),
            schema_name="visor_rgb_component_import",
            schema_version="1.0.0",
            household_id=h,
            session_id=s,
            trace_id=t,
            recorded_time=when,
            source_type=SourceType.IMPORT,
            source_id="visor-rgb-component",
        ),
        identity=ObservationIdentity(
            observation_id=ident, household_id=h, session_id=s, trace_id=t
        ),
        sensor=SensorRef(sensor_id="visor-rgb", modality=SensorModality.RGB),
        capture_time=when,
        arrival_time=when,
        clock_domain="import-time-not-exposure",
        frame_id="original-rgb-pixels",
        payload=PayloadRef(payload_id=ident, payload_sha256=sha(payload), size_bytes=len(payload)),
    )
    raw = RawModalityObservation(env.model_dump_json(), payload, sha(encoded(row)), None)
    raw.envelope()
    return raw


def mask_pixels(segments: list[Any], width: int, height: int) -> np.ndarray:
    """Pillow native polygon union, clipped to the canvas for measurement only.

    Original floating polygons remain unchanged in the source package. This is
    not the author's COCO rasterizer and is not a benchmark mask-IoU metric.
    """
    image = Image.new("1", (width, height))
    draw = ImageDraw.Draw(image)
    for segment in segments:
        draw.polygon([tuple(p) for p in segment], fill=1)
    return np.asarray(image, dtype=bool)


def box_overlap(mask: np.ndarray, box: list[float]) -> dict[str, Any]:
    """Pixel centers in half-open rectangle [x1,x2) x [y1,y2), clipped to image."""
    height, width = mask.shape
    x1, y1, x2, y2 = box
    a, b = max(0, min(width, math.ceil(x1 - 0.5))), max(0, min(height, math.ceil(y1 - 0.5)))
    c, d = max(0, min(width, math.ceil(x2 - 0.5))), max(0, min(height, math.ceil(y2 - 0.5)))
    area = max(0, c - a) * max(0, d - b)
    intersection, mask_area = int(mask[b:d, a:c].sum()), int(mask.sum())
    union = area + mask_area - intersection
    return {
        "intersection_pixels": intersection,
        "box_pixels": area,
        "mask_pixels": mask_area,
        "box_mask_iou": intersection / union if union else None,
        "mask_fraction": intersection / mask_area if mask_area else None,
    }


def _candidates(record: dict[str, Any]) -> None:
    ids = set()
    for kind in ("hands", "objects"):
        rows = record[kind]
        if type(rows) is not list or len(rows) > (20 if kind == "hands" else 100):
            raise ValueError("unbounded candidate list")
        for row in rows:
            fields = (
                {"id", "points", "side", "score", "region_id"}
                if kind == "hands"
                else {"id", "box", "category", "score"}
            )
            if (
                set(row) != fields
                or not isinstance(row["id"], str)
                or not row["id"]
                or row["id"] in ids
            ):
                raise ValueError("candidate identity/fields invalid")
            ids.add(row["id"])
            if (
                type(row["score"]) not in (int, float)
                or not math.isfinite(row["score"])
                or not 0 <= row["score"] <= 1
            ):
                raise ValueError("candidate score invalid")
            if kind == "hands":
                coords = row["points"]
                if (
                    type(coords) is not list
                    or len(coords) != 21
                    or any(type(p) is not list or len(p) != 2 for p in coords)
                    or row["side"] not in ("Left", "Right")
                    or not isinstance(row["region_id"], str)
                    or not row["region_id"]
                ):
                    raise ValueError("hand structure invalid")
                numbers = [n for p in coords for n in p]
            else:
                numbers = row["box"]
                if (
                    type(numbers) is not list
                    or len(numbers) != 4
                    or not isinstance(row["category"], str)
                    or not row["category"]
                ):
                    raise ValueError("object structure invalid")
            if any(type(n) not in (int, float) or not math.isfinite(n) for n in numbers):
                raise ValueError("non-finite coordinates")
            if kind == "objects":
                x1, y1, x2, y2 = numbers
                if (
                    not 0 <= x1 < x2 <= record["input"]["width"]
                    or not 0 <= y1 < y2 <= record["input"]["height"]
                ):
                    raise ValueError("object box outside image")


def align_frame(
    record: dict[str, Any], author: dict[str, Any], targets: list[Any]
) -> dict[str, Any]:
    """Compute every pair, including zero overlaps; labels stay in evaluator lane."""
    _candidates(record)
    width, height = record["input"]["width"], record["input"]["height"]
    masks, hand_pairs, object_pairs = [], [], []
    for entity in author["annotations"]:
        mask = mask_pixels(entity["segments"], width, height)
        masks.append(
            {
                "id": entity["id"],
                "name": entity["name"],
                "exhaustive": entity["exhaustive"],
                "pixels": int(mask.sum()),
            }
        )
        if entity["name"] in HANDS:
            for hand in record["hands"]:
                points = hand["points"]
                inside = sum(
                    0 <= x < width and 0 <= y < height and bool(mask[math.floor(y), math.floor(x)])
                    for x, y in points
                )
                box = [
                    min(p[0] for p in points),
                    min(p[1] for p in points),
                    max(p[0] for p in points),
                    max(p[1] for p in points),
                ]
                hand_pairs.append(
                    {
                        "candidate_id": hand["id"],
                        "mask_id": entity["id"],
                        "landmarks_in_mask": inside,
                        **box_overlap(mask, box),
                    }
                )
        else:
            for obj in record["objects"]:
                object_pairs.append(
                    {
                        "candidate_id": obj["id"],
                        "candidate_kind": "actor" if obj["category"] == "person" else "instance",
                        "mask_id": entity["id"],
                        **box_overlap(mask, obj["box"]),
                    }
                )
    relations = []
    for target in targets:
        hids = [
            p["candidate_id"]
            for p in hand_pairs
            if p["mask_id"] == target["hand_mask_id"] and p["landmarks_in_mask"] > 0
        ]
        # Contact can point at the other annotated hand; object detector overlap
        # is deliberately undefined for that target type, never counted as a miss.
        object_target = any(
            m["id"] == target["contact_segment_id"] and m["name"] not in HANDS for m in masks
        )
        oids = (
            [
                p["candidate_id"]
                for p in object_pairs
                if p["mask_id"] == target["contact_segment_id"]
                and p["intersection_pixels"] > 0
                and p["candidate_kind"] == "instance"
            ]
            if object_target
            else None
        )
        relations.append(
            {
                **target,
                "hand_positive_geometry_ids": hids,
                "object_positive_geometry_ids": oids,
                "geometric_pair_count": None if oids is None else len(hids) * len(oids),
                "assigned_candidate_label": None,
            }
        )
    return {
        "key": record["input"]["key"],
        "hands": record["hands"],
        "objects": record["objects"],
        "masks": masks,
        "hand_pairs": hand_pairs,
        "object_pairs": object_pairs,
        "relations": relations,
    }


def evaluate(
    source: Path, packet: Path, prediction: Path, prediction_sha256: str
) -> dict[str, Any]:
    """Rebuild author truth, pin predictions externally, then recompute geometry."""
    artifacts = _derive(_source_bytes(source))
    _verify_artifacts(packet, artifacts)
    inputs = strict_json(artifacts["runtime/manifest.json"])["frames"]
    authors = strict_json(artifacts["supervision/frames.json"])
    targets = strict_json(artifacts["supervision/contact_targets.json"])
    if (
        prediction.is_symlink()
        or prediction.stat().st_nlink != 1
        or prediction.stat().st_size > 64 * 1024**2
    ):
        raise ValueError("prediction must be a bounded unaliased file")
    raw = prediction.read_bytes()
    if sha(raw) != prediction_sha256:
        raise ValueError("prediction differs from external execution pin")
    doc = strict_json(raw)
    if (
        set(doc)
        != {"format", "profile", "runtime_manifest_sha256", "environment", "imported_at", "records"}
        or doc["format"] != "visor_frontend_candidates_v1"
        or doc["profile"] != PROFILE
        or doc["runtime_manifest_sha256"] != sha(artifacts["runtime/manifest.json"])
        or type(doc["records"]) is not list
        or len(doc["records"]) != len(inputs)
    ):
        raise ValueError("prediction profile or full frame closure differs")
    require_aware(datetime.fromisoformat(doc["imported_at"]), "imported_at")
    frames = []
    for row, author, record in zip(inputs, authors, doc["records"], strict=True):
        if (
            set(record) != {"input", "hands", "objects"}
            or record["input"] != row
            or author["key"] != row["key"]
        ):
            raise ValueError("prediction frame identity/order differs")
        frames.append(align_frame(record, author, [t for t in targets if t["key"] == row["key"]]))
    relations = [r for f in frames for r in f["relations"]]
    contacts = [r for r in relations if r["object_positive_geometry_ids"] is not None]
    return {
        "format": "visor_all_pairs_geometry_v2",
        "prediction_sha256": prediction_sha256,
        "runtime_manifest_sha256": doc["runtime_manifest_sha256"],
        "frames": frames,
        "summary": {
            "frames": len(frames),
            "masks": sum(len(f["masks"]) for f in frames),
            "hand_candidates": sum(len(f["hands"]) for f in frames),
            "visual_candidates": sum(len(f["objects"]) for f in frames),
            "person_candidates": sum(
                o["category"] == "person" for f in frames for o in f["objects"]
            ),
            "object_candidates": sum(
                o["category"] != "person" for f in frames for o in f["objects"]
            ),
            "frames_without_hand_candidates": sum(not f["hands"] for f in frames),
            "frames_without_object_candidates": sum(
                not any(o["category"] != "person" for o in f["objects"]) for f in frames
            ),
            "relations": len(relations),
            "states": dict(Counter(r["state"] for r in relations)),
            "hand_geometry_multiplicity": dict(
                Counter(str(len(r["hand_positive_geometry_ids"])) for r in relations)
            ),
            "object_target_relations": len(contacts),
            "contact_object_geometry_multiplicity": dict(
                Counter(str(len(r["object_positive_geometry_ids"])) for r in contacts)
            ),
            "contact_both_have_geometry": sum(bool(r["geometric_pair_count"]) for r in contacts),
            "contact_unique_geometric_pair": sum(r["geometric_pair_count"] == 1 for r in contacts),
            "assigned_candidate_labels": 0,
            "scope": "component_geometry_not_identity_contact_calibration_or_runtime_authority",
        },
    }


def verify_alignment(
    source: Path, packet: Path, prediction: Path, prediction_sha256: str, result: Path
) -> dict[str, Any]:
    """Consume source-recomputed values, never a report's self-declared success."""
    expected = evaluate(source, packet, prediction, prediction_sha256)
    if (
        result.is_symlink()
        or result.stat().st_nlink != 1
        or result.read_bytes() != encoded(expected)
    ):
        raise ValueError("result differs from recomputed alignment")
    return expected
