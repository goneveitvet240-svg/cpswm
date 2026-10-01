"""Causal, detector-initialized pixel support; never an object identity oracle.

All initial detections remain separate hypotheses. Later detections are logged,
not forcibly matched. A failed track stays unknown, and every frame is retained.
Scores/flow counts are diagnostics, not independent probabilistic evidence.
"""

from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
from math import ceil, floor
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from cpswm.perception_mapping.natural_vision import NaturalAppearanceDetector, decode_rgb
from cpswm.perception_mapping.visual_target_tracking import InitializedPixelTargetTracker
from cpswm.system.reproducibility import content_sha256

PROFILE = "natural-detector-initialized-pixel-sequence@1"
# Frozen engineering guard, not a calibrated identity probability.
MINIMUM_PATCH_CORRELATION = 0.6


def patch(rgb: NDArray[np.uint8], box: tuple[float, ...]) -> NDArray[np.float64]:
    import cv2

    x0, y0, x1, y1 = box
    crop = rgb[floor(y0) : ceil(y1), floor(x0) : ceil(x1)]
    if crop.size == 0:
        raise ValueError("empty natural target crop")
    return cv2.resize(crop, (24, 48)).astype(np.float64)


def correlation(a: NDArray[np.float64], b: NDArray[np.float64]) -> float:
    a, b = a - a.mean(), b - b.mean()
    scale = float(np.linalg.norm(a) * np.linalg.norm(b))
    return 0.0 if scale == 0 else float(np.clip(np.sum(a * b) / scale, -1.0, 1.0))


class NaturalTargetSequence:
    """Replayable public-pixel prefix. No labels, supplied boxes or world IDs.

    The first frame defines a set of target *candidates*, not a semantic target.
    Same bytes do not count as a new visual observation. Repeated raw IDs are
    idempotent only with identical bytes/envelope/cutoff; conflicts are rejected.
    """

    def __init__(self, *, weights_path: Path) -> None:
        self.weights_path = weights_path
        self._detector: NaturalAppearanceDetector | None = None
        self._tracks: dict[str, tuple[InitializedPixelTargetTracker, Any, str]] = {}
        self._lost: set[str] = set()
        self._records: list[dict[str, Any]] = []
        self._seen: dict[str, tuple[str, dict[str, Any]]] = {}
        self._scope: Any = None
        self._last_capture: Any = None
        self._last_arrival: Any = None
        self._shape: Any = None
        self._pixel_hashes: set[str] = set()

    @property
    def records(self) -> tuple[dict[str, Any], ...]:
        from copy import deepcopy

        return tuple(deepcopy(self._records))

    def observe(self, raw: Any, *, cutoff: Any) -> dict[str, Any]:
        from copy import deepcopy

        env, rgb = decode_rgb(raw, cutoff=cutoff)
        key = str(env.identity.observation_id)
        request = content_sha256(
            (
                raw.envelope_json,
                sha256(raw.payload_bytes).hexdigest(),
                raw.capture_receipt_sha256,
                cutoff,
            )
        )
        if key in self._seen:
            old, result = self._seen[key]
            if request != old:
                raise ValueError("reused observation identity differs from original")
            return deepcopy(result)
        scope = (
            env.identity.household_id,
            env.identity.session_id,
            env.identity.trace_id,
            env.sensor.sensor_id,
        )
        if self._scope is not None and (
            scope != self._scope
            or rgb.shape != self._shape
            or env.capture_time <= self._last_capture
            or env.arrival_time < self._last_arrival
        ):
            raise ValueError("sequence scope, dimensions or chronological order changed")
        if self._detector is None:
            self._detector = NaturalAppearanceDetector(
                weights_path=self.weights_path,
                household_id=env.identity.household_id,
                session_id=env.identity.session_id,
                trace_id=env.identity.trace_id,
            )
        frame = self._detector.infer(raw, cutoff=cutoff)
        # Work on copies: a later tracker exception must not partially advance history.
        tracks, lost = deepcopy(self._tracks), set(self._lost)
        index = len(self._records)
        if index == 0:
            for candidate in frame.candidates:
                box = candidate.box_xyxy
                integer_box = (floor(box[0]), floor(box[1]), ceil(box[2]), ceil(box[3]))
                tracks[str(candidate.candidate_id)] = (
                    InitializedPixelTargetTracker(integer_box),
                    patch(rgb, integer_box),
                    candidate.category,
                )
        measured = []
        for anchor, (tracker, initial_patch, category) in sorted(tracks.items()):
            measurement = tracker.update(rgb, frame_index=index)
            similarity = None
            reason = None
            if anchor in lost:
                reason = "previously_lost_no_automatic_reacquisition"
            elif measurement.box_xyxy is None:
                reason = "optical_flow_support_lost"
            else:
                similarity = correlation(initial_patch, patch(rgb, measurement.box_xyxy))
                if similarity < MINIMUM_PATCH_CORRELATION:
                    reason = "initial_appearance_not_supported"
            if reason is not None:
                lost.add(anchor)
            measured.append(
                dict(
                    anchor_id=anchor,
                    category=category,
                    box_xyxy=None if reason else measurement.box_xyxy,
                    status="UNKNOWN" if reason else "PIXEL_SUPPORTED",
                    reason=reason,
                    patch_correlation=similarity,
                    optical_flow=asdict(measurement),
                )
            )
        digest = sha256(rgb.tobytes()).hexdigest()
        result = dict(
            profile=PROFILE,
            frame_index=index,
            observation_id=key,
            input_sha256=digest,
            request_sha256=request,
            duplicate_pixels=digest in self._pixel_hashes,
            capture_time=env.capture_time.isoformat(),
            arrival_time=env.arrival_time.isoformat(),
            detector=asdict(frame),
            tracks=measured,
            status="PIXEL_SUPPORT_AVAILABLE"
            if any(t["status"] == "PIXEL_SUPPORTED" for t in measured)
            else "UNKNOWN",
            identity_status="UNRESOLVED",
            negative_observation_authorized=False,
            independent_evidence_count=None,
            appearance_guard=MINIMUM_PATCH_CORRELATION,
        )
        self._tracks, self._lost = tracks, lost
        self._scope, self._shape = scope, rgb.shape
        self._last_capture, self._last_arrival = env.capture_time, env.arrival_time
        self._pixel_hashes.add(digest)
        self._records.append(deepcopy(result))
        self._seen[key] = (request, deepcopy(result))
        return deepcopy(result)
