"""Causal masked optical-flow support with conservative object continuity.

Natural masks initialize separate provisional tracks. A lost first-frame track
may be reinitialized only by the existing appearance/geometry development gate
and a unique one-to-one relation. Later-category births never acquire an earlier
task reference. Missing/ambiguous support remains explicit. This does not publish
world identity, memory, or object-centre position factors.
"""

from __future__ import annotations

import io
from copy import deepcopy
from datetime import datetime
from math import ceil, floor
from typing import Any

import numpy as np

from cpswm.perception_mapping import appearance_geometry_association
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

PROFILE = "natural-mask-conservative-object-continuity@3"
MINIMUM_POINTS = 4  # Same minimum flow support as the existing public pixel tracker.


def _appearance(rgb: np.ndarray, candidate: dict[str, Any]) -> tuple[float, ...]:
    """Use the already registered development histogram; no mask score becomes identity."""
    x0, y0, x1, y1 = candidate["box_xyxy"]
    crop = rgb[floor(y0) : ceil(y1), floor(x0) : ceil(x1)]
    if crop.size == 0:
        raise ValueError("candidate appearance crop is empty")
    bins = appearance_geometry_association.CONFIG["histogram_bins"]
    histogram = np.concatenate(
        [np.histogram(crop[:, :, channel], bins=bins, range=(0, 256))[0] for channel in range(3)]
    ).astype(np.float64)
    histogram /= histogram.sum()
    return tuple(float(value) for value in histogram)


def _descriptor(rgb: np.ndarray, candidate: dict[str, Any], *, birth_frame: int) -> dict[str, Any]:
    point = candidate["world_point_m"]
    return dict(
        category=candidate["category"],
        reference_appearance=_appearance(rgb, candidate),
        last_world_point_m=None if point is None else tuple(float(value) for value in point),
        reference_features={},
        reference_feature_cohort_ids=(),
        reference_geometry_readout=False,
        birth_frame=birth_frame,
    )


def _rounded_points(
    points_uv: tuple[tuple[float, float], ...], *, width: int, height: int
) -> tuple[tuple[int, int], ...]:
    return tuple(
        sorted(
            {
                (int(np.rint(x)), int(np.rint(y)))
                for x, y in points_uv
                if 0 <= np.rint(x) < width and 0 <= np.rint(y) < height
            }
        )
    )


def _reference_feature_rows(
    camera: Any,
    depth: np.ndarray,
    probability: np.ndarray,
    point_ids: tuple[int, ...],
    points_uv: tuple[tuple[float, float], ...],
    reference_features: dict[int, tuple[float, float, float]],
) -> list[dict[str, Any]]:
    """Audit public RGB-D geometry for stable feature ids inside one candidate mask."""
    rows = []
    scale = float(appearance_geometry_association.CONFIG["geometry_scale_m"])
    for feature_id, (u_float, v_float) in zip(point_ids, points_uv, strict=True):
        u, v = int(np.rint(u_float)), int(np.rint(v_float))
        item: dict[str, Any] = dict(
            feature_id=feature_id,
            tracked_pixel_uv=[float(u_float), float(v_float)],
            pixel_uv=[u, v],
            inside_image=0 <= u < camera.width and 0 <= v < camera.height,
            inside_candidate_mask=False,
            valid_depth=False,
            reference_available=feature_id in reference_features,
            current_world_point_m=None,
            reference_world_point_m=None,
            residual_m=None,
            passes_geometry=False,
        )
        if not item["inside_image"]:
            rows.append(item)
            continue
        item["inside_candidate_mask"] = bool(probability[v, u] >= MASK_THRESHOLD)
        z = float(depth[v, u])
        item["valid_depth"] = bool(
            np.isfinite(z) and 0 < z < camera.far_plane_m - camera.near_plane_m
        )
        if not item["inside_candidate_mask"] or not item["valid_depth"]:
            rows.append(item)
            continue
        current = tuple(float(value) for value in camera.world_point(u, v, z))
        item["current_world_point_m"] = list(current)
        reference = reference_features.get(feature_id)
        if reference is not None:
            residual = float(np.linalg.norm(np.asarray(reference) - np.asarray(current)))
            item.update(
                reference_world_point_m=list(reference),
                residual_m=residual,
                passes_geometry=residual <= scale,
            )
        rows.append(item)
    return rows


def _passing_reference_features(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        (row for row in rows if row["passes_geometry"]),
        key=lambda row: (row["residual_m"], row["feature_id"], row["pixel_uv"]),
    )


def _store_reference_features(
    evidence: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    selected_pixel_uv: list[int],
) -> None:
    valid = [row for row in rows if row["inside_candidate_mask"] and row["valid_depth"]]
    evidence["reference_features"] = {
        row["feature_id"]: tuple(row["current_world_point_m"]) for row in valid
    }
    if not evidence["reference_feature_cohort_ids"] and len(valid) >= MINIMUM_POINTS:
        selected_u, selected_v = selected_pixel_uv
        local = sorted(
            valid,
            key=lambda row: (
                (row["pixel_uv"][0] - selected_u) ** 2 + (row["pixel_uv"][1] - selected_v) ** 2,
                row["feature_id"],
                row["pixel_uv"],
            ),
        )[:MINIMUM_POINTS]
        evidence["reference_feature_cohort_ids"] = tuple(row["feature_id"] for row in local)


def _comparison(
    anchor: str, evidence: dict[str, Any], candidate: dict[str, Any], appearance: tuple[float, ...]
) -> dict[str, Any]:
    """Pairwise development energy with the existing UNKNOWN logit as the only gate."""
    item = dict(
        anchor_id=anchor,
        candidate_id=candidate["candidate_id"],
        category=candidate["category"],
        compatible=False,
        accepted_energy=False,
    )
    point = candidate["world_point_m"]
    if evidence["category"] != candidate["category"] or point is None:
        return item
    reference_point = evidence["last_world_point_m"]
    if reference_point is None:
        return item
    reference_appearance = np.asarray(evidence["reference_appearance"], dtype=np.float64)
    query_appearance = np.asarray(appearance, dtype=np.float64)
    appearance_distance = float(
        np.linalg.norm(np.sqrt(reference_appearance) - np.sqrt(query_appearance)) / np.sqrt(2.0)
    )
    surface_distance = float(
        np.linalg.norm(np.asarray(reference_point) - np.asarray(point, dtype=np.float64))
    )
    config = appearance_geometry_association.CONFIG
    energy = -0.5 * (
        (appearance_distance / config["appearance_scale"]) ** 2
        + (surface_distance / config["geometry_scale_m"]) ** 2
    )
    item.update(
        compatible=True,
        appearance_distance=appearance_distance,
        surface_distance_m=surface_distance,
        log_energy=energy,
        accepted_energy=energy > config["unknown_logit"],
    )
    return item


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
        self._evidence: dict[str, dict[str, Any]] = {}
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
        evidence = deepcopy(self._evidence)
        candidate_appearance = {
            candidate["candidate_id"]: _appearance(rgb, candidate) for candidate in active
        }
        active_by_id = {candidate["candidate_id"]: candidate for candidate in active}
        original_categories = {category for category, _ in tracks.values()}
        if self._index == 0:
            for candidate in active:
                x0, y0, x1, y1 = candidate["box_xyxy"]
                box = (floor(x0), floor(y0), ceil(x1), ceil(y1))
                tracker = InitializedPixelTargetTracker(
                    box,
                    initial_mask=masks[candidate["native_index"]] >= MASK_THRESHOLD,
                    initial_frame_index=self._index,
                )
                tracks[candidate["candidate_id"]] = (candidate["category"], tracker)
                evidence[candidate["candidate_id"]] = _descriptor(
                    rgb, candidate, birth_frame=self._index
                )
        rows = []
        for anchor, (category, tracker) in sorted(tracks.items()):
            measured = tracker.update(rgb, frame_index=self._index)
            points = _rounded_points(tracker.points_uv, width=camera.width, height=camera.height)
            support = []
            for candidate in active:
                if candidate["category"] != category:
                    continue
                probability = masks[candidate["native_index"]]
                feature_rows = _reference_feature_rows(
                    camera,
                    depth,
                    probability,
                    tracker.point_ids,
                    tracker.points_uv,
                    evidence[anchor]["reference_features"],
                )
                passing = _passing_reference_features(feature_rows)
                if evidence[anchor]["reference_geometry_readout"]:
                    supported = tuple(tuple(row["pixel_uv"]) for row in passing)
                else:
                    supported = tuple(
                        (x, y) for x, y in points if probability[y, x] >= MASK_THRESHOLD
                    )
                if len(supported) >= MINIMUM_POINTS:
                    support.append((candidate, supported, feature_rows, passing))
            row = dict(
                anchor_id=anchor,
                category=category,
                flow=measured.__dict__,
                flow_points_uv=tracker.points_uv,
                flow_feature_ids=tracker.point_ids,
                selected_feature_ids=(),
                mask_support=[
                    dict(
                        candidate_id=c["candidate_id"],
                        points_uv=p,
                        reference_feature_verification=feature_rows,
                    )
                    for c, p, feature_rows, _ in support
                ],
                current_candidate_id=None,
                selected_pixel_uv=None,
                world_point_m=None,
                surface=None,
                identity_status="UNRESOLVED",
                birth_frame=evidence[anchor]["birth_frame"],
                query_eligible=evidence[anchor]["birth_frame"] == 0,
                reidentification=None,
            )
            if measured.status == "LOST":
                row["status"] = "LOST_NO_REINITIALIZATION"
            elif not support:
                row["status"] = "UNKNOWN_NO_CURRENT_MASK_SUPPORT"
            elif len(support) > 1:
                row["status"] = "UNKNOWN_AMBIGUOUS_CURRENT_MASK_SUPPORT"
            else:
                candidate, pixels, feature_rows, passing = support[0]
                use_geometry = evidence[anchor]["reference_geometry_readout"]
                selected_support = (tuple(passing[0]["pixel_uv"]),) if use_geometry else pixels
                point = select_surface(
                    camera,
                    depth,
                    masks[candidate["native_index"]],
                    support_uv=selected_support,
                )
                row.update(
                    status="FLOW_AND_MASK_SUPPORTED"
                    if point["status"] == "SURFACE_CANDIDATE"
                    else point["status"],
                    current_candidate_id=candidate["candidate_id"],
                    selected_pixel_uv=point["selected_pixel_uv"],
                    world_point_m=point["world_point_m"],
                    surface=point,
                    selected_feature_ids=(passing[0]["feature_id"],)
                    if use_geometry
                    else tuple(
                        key
                        for key, (x, y) in zip(tracker.point_ids, tracker.points_uv, strict=True)
                        if point["selected_pixel_uv"] == [int(np.rint(x)), int(np.rint(y))]
                    ),
                    identity_status=(
                        "CONDITIONAL_REFERENCE_FEATURE_GEOMETRY_CONTINUITY"
                        if use_geometry
                        else "UNRESOLVED"
                    ),
                )
            rows.append(row)

        # A live track owns every mask it currently supports, including ambiguous
        # alternatives. A lost track cannot steal one of those masks.
        unavailable = {
            support["candidate_id"]
            for row in rows
            if row["flow"]["status"] != "LOST"
            for support in row["mask_support"]
        }
        comparisons = []
        eligible_by_anchor: dict[str, list[str]] = {}
        eligible_by_candidate: dict[str, list[str]] = {}
        lost_rows = [row for row in rows if row["flow"]["status"] == "LOST"]
        for row in lost_rows:
            anchor = row["anchor_id"]
            eligible_by_anchor[anchor] = []
            for candidate in active:
                item = _comparison(
                    anchor,
                    evidence[anchor],
                    candidate,
                    candidate_appearance[candidate["candidate_id"]],
                )
                lost_tracker = tracks[anchor][1]
                cohort = set(evidence[anchor]["reference_feature_cohort_ids"])
                cohort_references = {
                    feature_id: point
                    for feature_id, point in evidence[anchor]["reference_features"].items()
                    if feature_id in cohort
                }
                feature_rows = _reference_feature_rows(
                    camera,
                    depth,
                    masks[candidate["native_index"]],
                    lost_tracker.direct_point_ids,
                    lost_tracker.direct_points_uv,
                    cohort_references,
                )
                passing = _passing_reference_features(feature_rows)
                item.update(
                    reference_feature_verification=feature_rows,
                    verified_reference_feature_count=len(passing),
                    minimum_reference_feature_count=MINIMUM_POINTS,
                    geometry_scale_m=appearance_geometry_association.CONFIG["geometry_scale_m"],
                    accepted_reference_feature_geometry=len(passing) >= MINIMUM_POINTS,
                )
                if candidate["candidate_id"] in unavailable:
                    item["unavailable_to_lost_track"] = True
                    item["accepted_energy"] = False
                item["accepted_reidentification"] = bool(
                    item["accepted_energy"] and item["accepted_reference_feature_geometry"]
                )
                comparisons.append(item)
                if item["accepted_reidentification"]:
                    eligible_by_anchor[anchor].append(candidate["candidate_id"])
                    eligible_by_candidate.setdefault(candidate["candidate_id"], []).append(anchor)

        accepted_reidentifications: set[str] = set()
        for row in lost_rows:
            anchor = row["anchor_id"]
            options = eligible_by_anchor[anchor]
            anchor_comparisons = [item for item in comparisons if item["anchor_id"] == anchor]
            detail = dict(
                model=appearance_geometry_association.MODEL,
                config=dict(appearance_geometry_association.CONFIG),
                comparisons=anchor_comparisons,
                detector_scores_used_in_energy=False,
                calibration="UNCALIBRATED_COMPOSITE_DEVELOPMENT_ENERGY",
            )
            if len(options) != 1:
                energy_options = [
                    item
                    for item in anchor_comparisons
                    if item["accepted_energy"] and not item.get("unavailable_to_lost_track")
                ]
                if len(options) > 1:
                    detail["status"] = "UNKNOWN_AMBIGUOUS_REIDENTIFICATION"
                elif energy_options:
                    detail["status"] = "UNKNOWN_NO_REFERENCE_FEATURE_GEOMETRY"
                else:
                    detail["status"] = "UNKNOWN_NO_REIDENTIFICATION_SUPPORT"
                row["status"] = detail["status"]
                row["reidentification"] = detail
                continue
            candidate_id = options[0]
            if len(eligible_by_candidate[candidate_id]) != 1:
                detail["status"] = "UNKNOWN_SHARED_REIDENTIFICATION_CANDIDATE"
                row["status"] = detail["status"]
                row["reidentification"] = detail
                continue
            candidate = active_by_id[candidate_id]
            comparison = next(
                item for item in anchor_comparisons if item["candidate_id"] == candidate_id
            )
            verified = _passing_reference_features(comparison["reference_feature_verification"])[
                :MINIMUM_POINTS
            ]
            seed_points = tuple(tuple(row["tracked_pixel_uv"]) for row in verified)
            seed_ids = tuple(row["feature_id"] for row in verified)
            x_values = [point[0] for point in seed_points]
            y_values = [point[1] for point in seed_points]
            x0 = max(0, floor(min(x_values)))
            y0 = max(0, floor(min(y_values)))
            x1 = min(camera.width, ceil(max(x_values)) + 1)
            y1 = min(camera.height, ceil(max(y_values)) + 1)
            tracker = InitializedPixelTargetTracker(
                (x0, y0, x1, y1),
                initial_mask=masks[candidate["native_index"]] >= MASK_THRESHOLD,
                initial_points_uv=seed_points,
                initial_point_ids=seed_ids,
                initial_frame_index=self._index,
            )
            measured = tracker.update(rgb, frame_index=self._index)
            detail["candidate_id"] = candidate_id
            if measured.status == "LOST":
                detail["status"] = "UNKNOWN_REIDENTIFICATION_NO_FLOW_SUPPORT"
                row.update(
                    status=detail["status"],
                    flow=measured.__dict__,
                    flow_points_uv=(),
                    flow_feature_ids=(),
                    reidentification=detail,
                )
                continue
            pixels = tuple(tuple(row["pixel_uv"]) for row in verified)
            if len(pixels) < MINIMUM_POINTS:
                detail["status"] = "UNKNOWN_REIDENTIFICATION_NO_MASK_SUPPORT"
                row["status"] = detail["status"]
                row["reidentification"] = detail
                continue
            point = select_surface(
                camera,
                depth,
                masks[candidate["native_index"]],
                support_uv=(tuple(verified[0]["pixel_uv"]),),
            )
            detail["status"] = "ACCEPTED_UNIQUE_REIDENTIFICATION"
            detail["selected_feature_id"] = verified[0]["feature_id"]
            detail["reinitialized_feature_ids"] = list(seed_ids)
            row.update(
                status=(
                    "REIDENTIFIED_FLOW_AND_MASK_SUPPORTED"
                    if point["status"] == "SURFACE_CANDIDATE"
                    else point["status"]
                ),
                flow=measured.__dict__,
                flow_points_uv=tracker.points_uv,
                flow_feature_ids=tracker.point_ids,
                mask_support=[
                    dict(
                        candidate_id=candidate_id,
                        points_uv=pixels,
                        reference_feature_verification=comparison["reference_feature_verification"],
                    )
                ],
                current_candidate_id=candidate_id,
                selected_pixel_uv=point["selected_pixel_uv"],
                world_point_m=point["world_point_m"],
                surface=point,
                selected_feature_ids=(verified[0]["feature_id"],),
                identity_status="CONDITIONAL_REFERENCE_FEATURE_GEOMETRY_ASSOCIATION",
                reidentification=detail,
            )
            tracks[anchor] = (row["category"], tracker)
            evidence[anchor]["reference_geometry_readout"] = True
            accepted_reidentifications.add(candidate_id)

        # A category absent from every previous track may enter after frame zero.
        # The birth is observable but cannot satisfy a first-frame ordinal query.
        late_births = []
        if self._index > 0:
            late_categories = {c["category"] for c in active} - original_categories
            for candidate in active:
                if candidate["category"] not in late_categories:
                    continue
                anchor = candidate["candidate_id"]
                x0, y0, x1, y1 = candidate["box_xyxy"]
                tracker = InitializedPixelTargetTracker(
                    (floor(x0), floor(y0), ceil(x1), ceil(y1)),
                    initial_mask=masks[candidate["native_index"]] >= MASK_THRESHOLD,
                    initial_frame_index=self._index,
                )
                measured = tracker.update(rgb, frame_index=self._index)
                evidence[anchor] = _descriptor(rgb, candidate, birth_frame=self._index)
                tracks[anchor] = (candidate["category"], tracker)
                birth_points = tuple(
                    sorted(
                        {
                            (int(np.rint(x)), int(np.rint(y)))
                            for x, y in tracker.points_uv
                            if masks[candidate["native_index"]][int(np.rint(y)), int(np.rint(x))]
                            >= MASK_THRESHOLD
                        }
                    )
                )
                point = (
                    select_surface(
                        camera,
                        depth,
                        masks[candidate["native_index"]],
                        support_uv=birth_points,
                    )
                    if len(birth_points) >= MINIMUM_POINTS
                    else dict(
                        status="UNKNOWN_LATE_BIRTH_NO_FLOW_SUPPORT",
                        selected_pixel_uv=None,
                        world_point_m=None,
                    )
                )
                rows.append(
                    dict(
                        anchor_id=anchor,
                        category=candidate["category"],
                        flow=measured.__dict__,
                        flow_points_uv=tracker.points_uv,
                        flow_feature_ids=tracker.point_ids,
                        selected_feature_ids=tuple(
                            key
                            for key, (x, y) in zip(
                                tracker.point_ids, tracker.points_uv, strict=True
                            )
                            if point["selected_pixel_uv"] == [int(np.rint(x)), int(np.rint(y))]
                        ),
                        mask_support=(
                            [dict(candidate_id=anchor, points_uv=birth_points)]
                            if birth_points
                            else []
                        ),
                        current_candidate_id=(
                            anchor if point["world_point_m"] is not None else None
                        ),
                        selected_pixel_uv=point["selected_pixel_uv"],
                        world_point_m=point["world_point_m"],
                        surface=point,
                        status=(
                            "LATE_BIRTH_FLOW_AND_MASK_SUPPORTED"
                            if point["status"] == "SURFACE_CANDIDATE"
                            else point["status"]
                        ),
                        identity_status="PROVISIONAL_LATE_BIRTH",
                        birth_frame=self._index,
                        query_eligible=False,
                        reidentification=None,
                    )
                )
                late_births.append(anchor)

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
        for row in rows:
            candidate_id = row["current_candidate_id"]
            if candidate_id is None or row["world_point_m"] is None:
                continue
            candidate = active_by_id[candidate_id]
            current_tracker = tracks[row["anchor_id"]][1]
            feature_rows = _reference_feature_rows(
                camera,
                depth,
                masks[candidate["native_index"]],
                current_tracker.point_ids,
                current_tracker.points_uv,
                {},
            )
            _store_reference_features(
                evidence[row["anchor_id"]],
                feature_rows,
                selected_pixel_uv=row["selected_pixel_uv"],
            )
            evidence[row["anchor_id"]]["last_world_point_m"] = tuple(row["world_point_m"])
        signature = content_sha256(
            camera.model_dump(mode="json", exclude={"action_id", "capture_time"})
        )
        result = dict(
            profile=PROFILE,
            frame_index=self._index,
            duplicate_sensor_content=signature in self._signatures,
            detector=frame.record,
            tracks=rows,
            late_births=late_births,
            reidentification_comparisons=comparisons,
            accepted_reidentifications=sorted(accepted_reidentifications),
            identity_status="UNRESOLVED",
            point_semantics="visible-surface-feature-may-change; not-static-object-centre",
            memory_update_authorized=False,
            negative_observation_authorized=False,
        )
        self._tracks, self._evidence = tracks, evidence
        self._index += 1
        self._observations.update(ids)
        self._signatures.add(signature)
        self._scene, self._last_capture = scene, camera.capture_time
        return result, frame.masks_npy
