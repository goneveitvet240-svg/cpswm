"""Evaluator-only matching against author HO-Cap manipulation-target masks.

Unmatched detections are not necessarily nonexistent objects: this dataset does
not annotate every object in the room. This evaluates localization of annotated
manipulation targets, not class correctness, identity, role or contact.
"""

from __future__ import annotations

import io
import math
import zipfile
from dataclasses import dataclass
from uuid import UUID

import numpy as np

from cpswm.perception_mapping.interaction_evidence import box_iou
from cpswm.perception_mapping.natural_vision import DetectionCandidate


@dataclass(frozen=True)
class AnnotatedTarget:
    name: str
    box_xyxy: tuple[float, float, float, float] | None


@dataclass(frozen=True)
class CandidateTargetMatch:
    candidate_id: UUID
    score: float
    matched_target: str | None
    overlaps: tuple[tuple[str, float], ...]
    ambiguous: bool


def read_author_targets(annotation: bytes) -> tuple[AnnotatedTarget, ...]:
    if not 0 < len(annotation) <= 4 * 1024 * 1024:
        raise ValueError("bounded author annotation required")
    with zipfile.ZipFile(io.BytesIO(annotation)) as archive:
        for key in ("seg_mask.npy", "obj_class_names.npy"):
            infos = [i for i in archive.infolist() if i.filename == key]
            if len(infos) != 1 or not 0 < infos[0].file_size <= 2 * 1024 * 1024:
                raise ValueError("missing, duplicate or oversized annotation array")
    with np.load(io.BytesIO(annotation), allow_pickle=False) as archive:
        mask, names = archive["seg_mask"], archive["obj_class_names"]
    if (
        mask.shape != (480, 640)
        or mask.dtype != np.uint8
        or names.ndim != 1
        or names.dtype.kind != "U"
        or not 0 < len(names) <= 255
        or len(set(names.tolist())) != len(names)
        or int(mask.max()) > len(names)
    ):
        raise ValueError("invalid author segmentation mapping")
    result = []
    for index, name in enumerate(names.tolist(), start=1):
        if name in {"LEFT_HAND", "RIGHT_HAND"}:
            continue
        if not name or name.endswith("_HAND"):
            raise ValueError("unknown annotation category")
        y, x = np.nonzero(mask == index)
        box = (
            None
            if len(x) == 0
            else (float(x.min()), float(y.min()), float(x.max() + 1), float(y.max() + 1))
        )
        result.append(AnnotatedTarget(name, box))
    return tuple(result)


def match_targets(
    candidates: tuple[DetectionCandidate, ...],
    targets: tuple[AnnotatedTarget, ...],
    *,
    iou_threshold: float = 0.5,
) -> tuple[tuple[CandidateTargetMatch, ...], tuple[str, ...]]:
    """Score-ranked one-to-one localization matching; retain every IoU alternative.

    The 0.5 threshold defines this development measurement, not a memory gate.
    Report all undetected visible targets, including frames with zero candidates.
    """
    if not math.isfinite(iou_threshold) or not 0 < iou_threshold <= 1:
        raise ValueError("invalid matching threshold")
    if len({c.candidate_id for c in candidates}) != len(candidates):
        raise ValueError("duplicate candidate identity")
    if len({t.name for t in targets}) != len(targets):
        raise ValueError("duplicate annotated target")
    for c in candidates:
        if (
            not isinstance(c.candidate_id, UUID)
            or not math.isfinite(c.detector_score)
            or not 0 <= c.detector_score <= 1
            or not c.category
        ):
            raise ValueError("invalid candidate")
        if not (
            0 <= c.box_xyxy[0] < c.box_xyxy[2] <= 640 and 0 <= c.box_xyxy[1] < c.box_xyxy[3] <= 480
        ):
            raise ValueError("candidate outside annotation image")
        box_iou(c.box_xyxy, c.box_xyxy)
    visible = {t.name: t.box_xyxy for t in targets if t.box_xyxy is not None}
    for box in visible.values():
        box_iou(box, box)
    claimed: set[str] = set()
    rows = []
    for c in sorted(candidates, key=lambda c: (-c.detector_score, str(c.candidate_id))):
        if c.category == "person":
            continue
        overlaps = tuple(
            sorted(
                ((name, box_iou(c.box_xyxy, box)) for name, box in visible.items()),
                key=lambda x: (-x[1], x[0]),
            )
        )
        eligible = [(n, s) for n, s in overlaps if s >= iou_threshold]
        matched = next((n for n, _ in eligible if n not in claimed), None)
        if matched is not None:
            claimed.add(matched)
        rows.append(
            CandidateTargetMatch(
                c.candidate_id, c.detector_score, matched, overlaps, len(eligible) > 1
            )
        )
    return tuple(rows), tuple(sorted(set(visible) - claimed))
