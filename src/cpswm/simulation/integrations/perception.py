"""Causal SAM2 prefix tracking with explicit operator box initialization.

Each inference sees only frames received so far. Rebuilding the short prefix is
slower than a streaming fork but uses the pinned public SAM2 API unmodified.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


def visual_event(
    episode: str,
    tick: int,
    mask: np.ndarray,
    *,
    initialized: bool,
    image_digest: str,
    generation: int = 0,
) -> dict[str, Any]:
    if mask.ndim != 2 or mask.dtype != np.bool_ or type(tick) is not int or tick < 0:
        raise ValueError("expected a boolean image mask and nonnegative integer tick")
    _ys, xs = np.nonzero(mask)
    visible = len(xs) >= 16  # declared engineering filter, not calibrated reliability
    region = None
    if visible:
        idx = min(2, int(float(xs.mean()) / mask.shape[1] * 3))
        region = ("image_left", "image_center", "image_right")[idx]
    return {
        "episode_id": episode,
        "source_id": f"sam2:{generation}:{tick}:{image_digest}",
        "event_id": f"visual:{generation}:{tick}",
        "occurred_at": tick,
        "available_at": tick,
        "object_id": "target",
        "visibility": ("observed" if initialized else "predicted") if visible else "lost",
        "location": region,
        "actors": [["unknown_actor", 1.0]],
        "origin": "sam2.1_tiny_operator_box" if initialized else "sam2.1_tiny_propagation",
        # No person attribution or calibrated cross-session identity from a track ID.
        "identity_probability": 1.0 if initialized else 0.0,
        "robot_generated": False,
    }


class Sam2Tracker:
    def __init__(
        self,
        checkpoint: Path,
        directory: Path,
        box: list[float],
        *,
        device: str = "cpu",
        max_frames: int = 64,
        predictor: Any = None,
    ) -> None:
        if max_frames < 1 or len(box) != 4 or not np.isfinite(box).all():
            raise ValueError("invalid prefix limit or operator box")
        if not (0 <= box[0] < box[2] and 0 <= box[1] < box[3]):
            raise ValueError("box is pixel xyxy in the rotated agent view")
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=False)
        self.box, self.max_frames, self.count = np.asarray(box, np.float32), max_frames, 0
        self.last_tick = -1
        self.checkpoint = checkpoint
        if predictor is None:
            from sam2.build_sam import build_sam2_video_predictor

            predictor = build_sam2_video_predictor(
                "configs/sam2.1/sam2.1_hiera_t.yaml",
                str(checkpoint),
                device=device,
                apply_postprocessing=False,  # no unavailable CUDA connected-component extension
            )
        self.predictor = predictor
        self.shape: tuple[int, ...] | None = None

    def observe(
        self, rgb: np.ndarray, episode: str, tick: int
    ) -> tuple[dict[str, Any], np.ndarray]:
        import torch

        if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[-1] != 3:
            raise ValueError("SAM input must be uint8 HWC RGB")
        if tick <= self.last_tick:
            raise ValueError("tracking requires strictly causal frame order")
        if self.count >= self.max_frames:
            raise RuntimeError(
                "causal prefix limit reached; explicit new operator initialization required"
            )
        if self.shape is not None and rgb.shape != self.shape:
            raise ValueError("camera shape changed within a track")
        if self.box[2] > rgb.shape[1] or self.box[3] > rgb.shape[0]:
            raise ValueError("operator box outside image")
        path = self.directory / f"{self.count:05d}.jpg"
        Image.fromarray(rgb).save(path, quality=95)
        file_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        self.shape = rgb.shape
        # Only the private prefix directory, never the complete future rollout.
        with torch.inference_mode():
            state = self.predictor.init_state(
                str(self.directory), offload_video_to_cpu=True, offload_state_to_cpu=True
            )
            _, _, first_logits = self.predictor.add_new_points_or_box(
                inference_state=state, frame_idx=0, obj_id=1, box=self.box
            )
            logits = first_logits
            if self.count:
                for index, ids, masks in self.predictor.propagate_in_video(
                    state, start_frame_idx=0, max_frame_num_to_track=self.count
                ):
                    if index == self.count:
                        if list(ids) != [1]:
                            raise RuntimeError("unexpected local track association")
                        logits = masks
                        break
                else:
                    raise RuntimeError("SAM did not produce the current frame")
            mask = (logits[0, 0] > 0).cpu().numpy().astype(bool)
            del state
        event = visual_event(
            episode, tick, mask, initialized=self.count == 0, image_digest=file_digest
        )
        self.count += 1
        self.last_tick = tick
        return event, mask
