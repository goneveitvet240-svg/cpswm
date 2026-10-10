"""Pinned RGB instance masks and public depth samples, without world-ID authority.

All native post-NMS proposals are retained, including low-score and unusable
ones. A selected point is a predicted surface candidate, not a verified object
position, an independent evidence factor, or an authorized memory update.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Any
from uuid import uuid5

import numpy as np

from cpswm.perception_mapping.adapters.rgbd_capture import RawModalityObservation
from cpswm.perception_mapping.natural_vision import NaturalAppearanceDetector, decode_rgb
from cpswm.perception_mapping.unity_rgbd import CameraSelfPose, decode_unity_rgbd
from cpswm.system.reproducibility import content_sha256

PROFILE = "natural-mask-surface-development@2"
MASK_THRESHOLD = 0.5
SELECTION = "maximum-mask-probability-valid-depth-tie-lexicographic-u-v"


def select_surface(
    camera: CameraSelfPose,
    depth: np.ndarray,
    probability: np.ndarray,
    *,
    support_uv: tuple[tuple[int, int], ...] | None = None,
) -> dict[str, Any]:
    """Use only public camera/depth and predicted mask; never oracle selection."""
    camera = CameraSelfPose.model_validate(camera.model_dump())
    shape = (camera.height, camera.width)
    if (
        depth.shape != shape
        or depth.dtype != np.float32
        or probability.shape != shape
        or probability.dtype != np.float32
        or not np.isfinite(probability).all()
        or np.any(probability < 0)
        or np.any(probability > 1)
    ):
        raise ValueError("finite float32 mask probabilities and paired float32 depth required")
    mask = probability >= MASK_THRESHOLD
    valid_depth = (
        np.isfinite(depth) & (depth > 0) & (depth < camera.far_plane_m - camera.near_plane_m)
    )
    eligible = mask & valid_depth
    if support_uv is not None:
        allowed = np.zeros(shape, dtype=bool)
        for x, y in support_uv:
            if (
                type(x) is not int
                or type(y) is not int
                or not 0 <= x < camera.width
                or not 0 <= y < camera.height
            ):
                raise ValueError("support must contain in-image integer pixels")
            allowed[y, x] = True
        eligible &= allowed
    from cpswm.perception_mapping.depth_validity import background_continuity

    ambiguous, validity = background_continuity(depth, mask)
    numeric_eligible = eligible.copy()
    common: dict[str, Any] = dict(
        depth_validity=validity,
        numerically_valid_mask_pixels=int(numeric_eligible.sum()),
        separated_depth_pixels=int((eligible & ~ambiguous).sum()),
        mask_pixels=int(mask.sum()),
        valid_mask_pixels=int(eligible.sum()),
        selected_pixel_uv=None,
        world_point_m=None,
        depth_m=None,
        selected_mask_probability=None,
        support_uv=None if support_uv is None else sorted(set(support_uv)),
    )
    if not mask.any():
        return dict(common, status="UNKNOWN_NO_MASK")
    if not eligible.any():
        return dict(
            common,
            status="UNKNOWN_NO_VALID_SUPPORTED_DEPTH"
            if support_uv is not None
            else "UNKNOWN_NO_VALID_DEPTH",
        )
    best = float(probability[eligible].max())
    v, u = np.nonzero(eligible & (probability == best))
    index = int(np.argmin(u * camera.height + v))
    x, y = int(u[index]), int(v[index])
    if ambiguous[y, x]:
        # Do not search boundary artefacts for a conveniently non-planar point.
        # The original deterministic pixel remains the observation under test.
        return dict(common, status="UNKNOWN_BACKGROUND_CONTINUOUS_DEPTH", ambiguous_pixel_uv=[x, y])
    z = float(depth[y, x])
    return dict(
        common,
        status="SURFACE_CANDIDATE",
        selected_pixel_uv=[x, y],
        world_point_m=list(camera.world_point(x, y, z)),
        depth_m=z,
        selected_mask_probability=best,
    )


@dataclass(frozen=True)
class MaskSurfaceFrame:
    record: dict[str, Any]
    # All native post-NMS mask probabilities, including low-score proposals.
    masks_npy: bytes


class NaturalMaskSurfaceDetector(NaturalAppearanceDetector):
    """Official frozen Mask R-CNN V2, native 800/1333 transform, CPU only.

    Detector threshold follows the existing 0.5 development convention. Mask
    threshold and point rule are fixed above, not tuned on evaluation truth.
    Native NMS/top-k still limits the proposal support; masks are uncalibrated.
    """

    model_id = "torchvision/maskrcnn_resnet50_fpn_v2/COCO_V1"
    weights_sha256 = "73cbd0190fcbe3ba339921fbce2c3a0b6bb9126c9a133c85e43a2a8e060a109e"
    weights_url = "https://download.pytorch.org/models/maskrcnn_resnet50_fpn_v2_coco-73cbd019.pth"

    @staticmethod
    def _build_model_and_categories() -> tuple[Any, tuple[str, ...]]:
        from torchvision.models.detection import (  # type: ignore[import-untyped]
            MaskRCNN_ResNet50_FPN_V2_Weights,
            maskrcnn_resnet50_fpn_v2,
        )

        model = maskrcnn_resnet50_fpn_v2(weights=None, weights_backbone=None)
        return model, tuple(MaskRCNN_ResNet50_FPN_V2_Weights.COCO_V1.meta["categories"])

    def infer_surface(
        self, observations: tuple[RawModalityObservation, ...], *, cutoff: datetime
    ) -> MaskSurfaceFrame:
        camera, depth = decode_unity_rgbd(observations, cutoff=cutoff)
        env, pixels = decode_rgb(observations[0], cutoff=cutoff)
        scope = (env.identity.household_id, env.identity.session_id, env.identity.trace_id)
        if scope != self._scope:
            raise ValueError("mask observation belongs to another scope")
        if self._minimum_score != 0.5:
            raise ValueError("this development profile freezes detector threshold at 0.5")
        torch = self._torch
        tensor = torch.from_numpy(pixels.copy()).permute(2, 0, 1).float().div(255.0)
        with torch.inference_mode():
            prediction = self._model([tensor])[0]
        height, width = pixels.shape[:2]
        prediction, clamps = self._normalize_resize_roundoff(prediction, width, height)
        self._validate_prediction(prediction, env.identity.observation_id, width, height)
        masks = prediction["masks"]
        if (
            masks.shape != (len(prediction["boxes"]), 1, height, width)
            or masks.dtype != torch.float32
            or not torch.isfinite(masks).all()
            or (masks < 0).any()
            or (masks > 1).any()
        ):
            raise ValueError("native instance masks differ in shape, dtype or probability range")
        masks_array = masks[:, 0].detach().cpu().numpy().copy()
        mask_wire = io.BytesIO()
        np.save(mask_wire, masks_array, allow_pickle=False)
        mask_bytes = mask_wire.getvalue()
        boxes, scores, labels = (
            prediction[k].detach().cpu().tolist() for k in ("boxes", "scores", "labels")
        )
        rows = []
        for i, (box, score, label) in enumerate(zip(boxes, scores, labels, strict=True)):
            binding = content_sha256((PROFILE, self.weights_sha256, i, box, score, label))
            if score >= self._minimum_score:
                point = select_surface(camera, depth, masks_array[i])
            else:
                point = dict(
                    status="BELOW_DETECTOR_THRESHOLD",
                    mask_pixels=int((masks_array[i] >= MASK_THRESHOLD).sum()),
                    valid_mask_pixels=None,
                    selected_pixel_uv=None,
                    world_point_m=None,
                    depth_m=None,
                    selected_mask_probability=None,
                )
            rows.append(
                dict(
                    candidate_id=str(uuid5(env.identity.observation_id, binding)),
                    native_index=i,
                    category=self._categories[label],
                    detector_score=score,
                    box_xyxy=box,
                    mask_array_sha256=sha256(masks_array[i].tobytes()).hexdigest(),
                    **point,
                )
            )
        record = dict(
            profile=PROFILE,
            model_id=self.model_id,
            weights_sha256=self.weights_sha256,
            torch_version=self._versions[0],
            torchvision_version=self._versions[1],
            minimum_detector_score=self._minimum_score,
            mask_threshold=MASK_THRESHOLD,
            point_selection=SELECTION,
            observation_ids=[str(r.envelope().identity.observation_id) for r in observations],
            payload_sha256=[sha256(r.payload_bytes).hexdigest() for r in observations],
            receipt_sha256=observations[0].capture_receipt_sha256,
            camera=camera.model_dump(mode="json"),
            masks_npy_sha256=sha256(mask_bytes).hexdigest(),
            native_candidate_count=len(rows),
            active_candidate_count=sum(r["detector_score"] >= self._minimum_score for r in rows),
            candidates=rows,
            resize_roundoff_clamps=clamps,
            identity_status="UNRESOLVED",
            calibrated=False,
            negative_observation_authorized=False,
            memory_update_authorized=False,
        )
        return MaskSurfaceFrame(record=record, masks_npy=mask_bytes)
