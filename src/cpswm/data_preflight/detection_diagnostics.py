"""Evaluator-only stage opportunities, not causal attribution or semantic calibration."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class MissMechanism:
    mechanism: str
    best_roi_iou: float
    best_native_iou: float
    best_kept_iou: float
    max_localizing_roi_score: float | None
    localizing_roi_count: int
    localizing_native_count: int
    excluded_person_localizes: bool


def overlaps(boxes: NDArray[np.float64], target: tuple[float, ...]) -> NDArray[np.float64]:
    if boxes.ndim != 2 or boxes.shape[1] != 4 or len(target) != 4:
        raise ValueError("boxes must be Nx4")
    if not np.isfinite(boxes).all() or not np.isfinite(target).all():
        raise ValueError("nonfinite box")
    if target[2] <= target[0] or target[3] <= target[1]:
        raise ValueError("degenerate target")
    if np.any(boxes[:, 2:] < boxes[:, :2]):
        raise ValueError("inverted box")
    intersection = np.maximum(
        0, np.minimum(boxes[:, 2:], target[2:]) - np.maximum(boxes[:, :2], target[:2])
    ).prod(axis=1)
    area = (boxes[:, 2:] - boxes[:, :2]).prod(axis=1)
    target_area = (target[2] - target[0]) * (target[3] - target[1])
    return np.asarray(intersection / (area + target_area - intersection), dtype=np.float64)


def classify_miss(
    target: tuple[float, ...],
    *,
    matched: bool,
    roi_boxes: NDArray[np.float64],
    roi_scores: NDArray[np.float64],
    native_boxes: NDArray[np.float64],
    native_scores: NDArray[np.float64],
    person_boxes: NDArray[np.float64],
    native_threshold: float,
    application_threshold: float = 0.5,
    iou_threshold: float = 0.5,
) -> MissMechanism:
    """Disjoint hierarchy; native means after RoI score/size/NMS/top-k.

    roi_* must exclude background/person/N/A. Never infer pre-RPN absence from
    this record. Tiny low-score localizers remain reported, not promoted.
    """
    if not 0 <= native_threshold <= application_threshold <= 1 or not 0 < iou_threshold <= 1:
        raise ValueError("invalid thresholds")
    for boxes, scores in ((roi_boxes, roi_scores), (native_boxes, native_scores)):
        if scores.ndim != 1 or len(scores) != len(boxes) or not np.isfinite(scores).all():
            raise ValueError("invalid score shape or value")
        if np.any((scores < 0) | (scores > 1)):
            raise ValueError("scores outside probability interval")
    r = overlaps(roi_boxes, target)
    n = overlaps(native_boxes, target)
    p = overlaps(person_boxes, target)
    good_roi, good_native = r >= iou_threshold, n >= iou_threshold
    kept = native_scores >= application_threshold
    if matched:
        if not np.any(good_native & kept):
            raise ValueError("matched target has no qualifying kept candidate")
        mechanism = "matched"
    elif np.any(good_native & kept):
        mechanism = "one_to_one_assignment_competition"
    elif np.any(good_native):
        mechanism = "application_score_filter"
    elif np.any(good_roi & (roi_scores > native_threshold)):
        mechanism = "native_size_nms_topk_filter"
    elif np.any(good_roi):
        mechanism = "roi_score_below_native_floor"
    elif np.any(r > 0):
        mechanism = "roi_localization_below_iou_threshold"
    else:
        mechanism = "no_overlapping_roi_candidate"
    return MissMechanism(
        mechanism,
        float(r.max(initial=0)),
        float(n.max(initial=0)),
        float(n[kept].max(initial=0)),
        float(roi_scores[good_roi].max()) if np.any(good_roi) else None,
        int(good_roi.sum()),
        int(good_native.sum()),
        bool(np.any(p >= iou_threshold)),
    )
