"""Causal pixel tracking from an explicit first-frame development annotation.

This is an image-space measurement, not a physical contact, household identity,
6D pose or habit observation. No later annotation is read by the tracker. A lost
track stays lost until an explicitly new initialization; it never follows a label.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import isfinite
from typing import Any

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class TargetTrackMeasurement:
    frame_index: int
    input_sha256: str
    box_xyxy: tuple[float, float, float, float] | None
    surviving_points: int
    forward_backward_error_px: float | None
    status: str


class InitializedPixelTargetTracker:
    """Sparse forward/backward optical flow with a frozen initial target crop.

    Thresholds are engineering defaults, not calibrated event probabilities.
    Only translation is estimated. Rotation, scale, occlusion and nonrigidity
    may cause failure and must be evaluated separately.
    """

    def __init__(self, box_xyxy: tuple[int, int, int, int]) -> None:
        if len(box_xyxy) != 4 or not all(isfinite(v) for v in box_xyxy):
            raise ValueError("finite initialization box required")
        x1, y1, x2, y2 = box_xyxy
        if not 0 <= x1 < x2 or not 0 <= y1 < y2:
            raise ValueError("invalid initialization box")
        self._box = (float(x1), float(y1), float(x2), float(y2))
        self._gray: Any = None
        self._points: Any = None
        self._index = -1
        self._shape: tuple[int, ...] | None = None
        self._lost = False

    def update(self, rgb: NDArray[np.uint8], *, frame_index: int) -> TargetTrackMeasurement:
        import cv2

        if (
            rgb.dtype != np.uint8
            or rgb.ndim != 3
            or rgb.shape[2] != 3
            or min(rgb.shape[:2]) < 8
            or frame_index != self._index + 1
        ):
            raise ValueError("ordered uint8 RGB frames required")
        if self._shape is not None and rgb.shape != self._shape:
            raise ValueError("camera dimensions changed")
        h, w = rgb.shape[:2]
        if self._index == -1 and (self._box[2] > w or self._box[3] > h):
            raise ValueError("initialization outside image")
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        digest = sha256(rgb.tobytes()).hexdigest()
        points = self._points
        box = self._box
        fb_error: float | None = None
        if self._index == -1:
            mask = np.zeros(gray.shape, dtype=np.uint8)
            x1, y1, x2, y2 = (int(v) for v in box)
            mask[y1:y2, x1:x2] = 255
            points = cv2.goodFeaturesToTrack(
                gray, maxCorners=80, qualityLevel=0.03, minDistance=5, mask=mask
            )
        elif not self._lost:
            new, ok, _ = cv2.calcOpticalFlowPyrLK(self._gray, gray, points, np.empty_like(points))
            if new is None or ok is None:
                points = None
            else:
                old, back_ok, _ = cv2.calcOpticalFlowPyrLK(
                    gray, self._gray, new, np.empty_like(new)
                )
                if old is None or back_ok is None:
                    points = None
                else:
                    errors = np.linalg.norm(old - points, axis=2).reshape(-1)
                    good = (
                        ok.reshape(-1).astype(bool)
                        & back_ok.reshape(-1).astype(bool)
                        & np.isfinite(errors)
                        & (errors <= 1.5)
                        & np.isfinite(new).all(axis=(1, 2))
                        & (new[:, 0, 0] >= 0)
                        & (new[:, 0, 0] < w)
                        & (new[:, 0, 1] >= 0)
                        & (new[:, 0, 1] < h)
                    )
                    if np.count_nonzero(good) < 4:
                        points = None
                    else:
                        delta = np.median((new - points)[good], axis=0)[0]
                        dx, dy = (float(v) for v in delta)
                        box = (box[0] + dx, box[1] + dy, box[2] + dx, box[3] + dy)
                        fb_error = float(np.median(errors[good]))
                        points = new[good]
        count = 0 if points is None else len(points)
        lost = (
            self._lost or count < 4 or not (0 <= box[0] < box[2] <= w and 0 <= box[1] < box[3] <= h)
        )
        self._gray, self._points, self._box = gray, points, box
        self._index, self._shape, self._lost = frame_index, rgb.shape, lost
        return TargetTrackMeasurement(
            frame_index,
            digest,
            None if lost else box,
            count,
            fb_error,
            "LOST" if lost else "INITIALIZED_PIXEL_TRACK_NOT_WORLD_IDENTITY",
        )
