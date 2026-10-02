"""Causal masked optical-flow support with unresolved world identity.

First-frame natural masks initialize separate tracks. Later masks may confirm
pixel support but never move/reinitialize a track. Missing/ambiguous masks and
lost flow remain explicit. This does not publish memory or position factors.
"""

from __future__ import annotations

import io
from copy import deepcopy
from datetime import datetime
from math import ceil, floor
from typing import Any

import numpy as np

from cpswm.perception_mapping.adapters.rgbd_capture import RawModalityObservation
from cpswm.perception_mapping.natural_mask_surface import (
    MASK_THRESHOLD,
    NaturalMaskSurfaceDetector,
    select_surface,
)
from cpswm.perception_mapping.natural_vision import decode_rgb
from cpswm.perception_mapping.unity_rgbd import decode_unity_rgbd
from cpswm.perception_mapping.visual_target_tracking import InitializedPixelTargetTracker
from cpswm.system.reproducibility import content_sha256

PROFILE = "natural-mask-initialized-flow-surface@1"
MINIMUM_POINTS = 4  # Same minimum flow support as the existing public pixel tracker.


class MaskSurfaceSequence:
    def __init__(self, detector: NaturalMaskSurfaceDetector) -> None:
        self.detector = detector
        self._scope = detector._scope
        self._binding = (
            detector.model_id,
            detector.weights_sha256,
            detector._versions,
            detector._minimum_score,
        )
        self._tracks: dict[str, tuple[str, InitializedPixelTargetTracker]] = {}
        self._index = 0
        self._observations: set[str] = set()
        self._signatures: set[str] = set()
        self._last_capture: datetime | None = None
        self._scene: tuple[str, str, int, int] | None = None

    def observe(
        self, observations: tuple[RawModalityObservation, ...], *, cutoff: datetime
    ) -> tuple[dict[str, Any], bytes]:
        if self.detector._scope != self._scope or self._binding != (
            self.detector.model_id,
            self.detector.weights_sha256,
            self.detector._versions,
            self.detector._minimum_score,
        ):
            raise ValueError("sequence detector binding or scope changed")
        camera, depth = decode_unity_rgbd(observations, cutoff=cutoff)
        _, rgb = decode_rgb(observations[0], cutoff=cutoff)
        ids = {str(r.envelope().identity.observation_id) for r in observations}
        if ids & self._observations:
            raise ValueError("sequence cannot consume the same exposure twice")
        scene = (camera.scene_sha256, camera.world_frame, camera.width, camera.height)
        if self._scene is not None and self._scene != scene:
            raise ValueError("sequence scene, world frame or camera dimensions changed")
        if self._last_capture is not None and camera.capture_time <= self._last_capture:
            raise ValueError("sequence capture order must strictly increase")
        frame = self.detector.infer_surface(observations, cutoff=cutoff)
        masks = np.load(io.BytesIO(frame.masks_npy), allow_pickle=False)
        active = [c for c in frame.record["candidates"] if c["detector_score"] >= 0.5]
        # All mutation is staged, including old flow history. Failed inference or
        # readout cannot partially advance one track while leaving others behind.
        tracks = deepcopy(self._tracks)
        if self._index == 0:
            for candidate in active:
                x0, y0, x1, y1 = candidate["box_xyxy"]
                box = (floor(x0), floor(y0), ceil(x1), ceil(y1))
                tracker = InitializedPixelTargetTracker(
                    box, initial_mask=masks[candidate["native_index"]] >= MASK_THRESHOLD
                )
                tracks[candidate["candidate_id"]] = (candidate["category"], tracker)
        rows = []
        for anchor, (category, tracker) in sorted(tracks.items()):
            measured = tracker.update(rgb, frame_index=self._index)
            points = sorted(
                {
                    (int(np.rint(x)), int(np.rint(y)))
                    for x, y in tracker.points_uv
                    if 0 <= np.rint(x) < camera.width and 0 <= np.rint(y) < camera.height
                }
            )
            support = []
            for candidate in active:
                if candidate["category"] != category:
                    continue
                probability = masks[candidate["native_index"]]
                supported = tuple((x, y) for x, y in points if probability[y, x] >= MASK_THRESHOLD)
                if len(supported) >= MINIMUM_POINTS:
                    support.append((candidate, supported))
            row = dict(
                anchor_id=anchor,
                category=category,
                flow=measured.__dict__,
                flow_points_uv=tracker.points_uv,
                flow_feature_ids=tracker.point_ids,
                selected_feature_ids=(),
                mask_support=[
                    dict(candidate_id=c["candidate_id"], points_uv=p) for c, p in support
                ],
                current_candidate_id=None,
                selected_pixel_uv=None,
                world_point_m=None,
                surface=None,
                identity_status="UNRESOLVED",
            )
            if measured.status == "LOST":
                row["status"] = "LOST_NO_REINITIALIZATION"
            elif not support:
                row["status"] = "UNKNOWN_NO_CURRENT_MASK_SUPPORT"
            elif len(support) > 1:
                row["status"] = "UNKNOWN_AMBIGUOUS_CURRENT_MASK_SUPPORT"
            else:
                candidate, pixels = support[0]
                point = select_surface(
                    camera, depth, masks[candidate["native_index"]], support_uv=pixels
                )
                row.update(
                    status="FLOW_AND_MASK_SUPPORTED"
                    if point["status"] == "SURFACE_CANDIDATE"
                    else point["status"],
                    current_candidate_id=candidate["candidate_id"],
                    selected_pixel_uv=point["selected_pixel_uv"],
                    world_point_m=point["world_point_m"],
                    surface=point,
                    selected_feature_ids=tuple(
                        key
                        for key, (x, y) in zip(tracker.point_ids, tracker.points_uv, strict=True)
                        if point["selected_pixel_uv"] == [int(np.rint(x)), int(np.rint(y))]
                    ),
                )
            rows.append(row)
        # Enforce one-to-one current support without silently picking a winner.
        assignments = [
            r["current_candidate_id"] for r in rows if r["current_candidate_id"] is not None
        ]
        for row in rows:
            if (
                row["current_candidate_id"] is not None
                and assignments.count(row["current_candidate_id"]) > 1
            ):
                row.update(
                    status="UNKNOWN_SHARED_CURRENT_MASK",
                    current_candidate_id=None,
                    selected_pixel_uv=None,
                    world_point_m=None,
                    surface=None,
                    selected_feature_ids=(),
                )
        signature = content_sha256(
            camera.model_dump(mode="json", exclude={"action_id", "capture_time"})
        )
        result = dict(
            profile=PROFILE,
            frame_index=self._index,
            duplicate_sensor_content=signature in self._signatures,
            detector=frame.record,
            tracks=rows,
            identity_status="UNRESOLVED",
            point_semantics="visible-surface-feature-may-change; not-static-object-centre",
            memory_update_authorized=False,
            negative_observation_authorized=False,
        )
        self._tracks = tracks
        self._index += 1
        self._observations.update(ids)
        self._signatures.add(signature)
        self._scene, self._last_capture = scene, camera.capture_time
        return result, frame.masks_npy
