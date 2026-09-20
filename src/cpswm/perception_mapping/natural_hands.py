"""Pinned CPU pixel hand candidates. Handedness is not person identity or contact.

IMAGE mode is deliberately stateless: replay/recovery never relies on opaque
video-tracker state or fabricated physical timestamps. Model-local 3D outputs are
not exported as camera/world measurements. No author annotation is an input.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

from cpswm.perception_mapping.adapters.rgbd_capture import RawModalityObservation
from cpswm.perception_mapping.natural_vision import decode_rgb

HAND_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/1/hand_landmarker.task"
)
HAND_MODEL_SHA256 = "fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1"


@dataclass(frozen=True)
class HandCandidate:
    candidate_id: UUID
    landmarks_xy_pixels: tuple[tuple[float, float], ...]
    handedness: str
    handedness_score: float
    # Both fields are uncalibrated model predictions, never actor probabilities.

    def __post_init__(self) -> None:
        if (
            len(self.landmarks_xy_pixels) != 21
            or any(
                len(p) != 2 or not all(math.isfinite(v) for v in p)
                for p in self.landmarks_xy_pixels
            )
            or self.handedness not in {"Left", "Right"}
            or not math.isfinite(self.handedness_score)
            or not 0 <= self.handedness_score <= 1
        ):
            raise ValueError("invalid raw hand landmarks or handedness")


@dataclass(frozen=True)
class HandFrame:
    observation_id: UUID
    capture_time: datetime
    input_sha256: str
    capture_receipt_sha256: str
    model_binding: tuple[str, str, int, float, float]
    width: int
    height: int
    candidates: tuple[HandCandidate, ...]
    semantic_status: str = "UNCALIBRATED_HANDS_NO_PERSON_CONTACT_OR_METRIC_POSE"


class NaturalHandDetector:
    def __init__(
        self, *, model_path: Path, scope: tuple[UUID, UUID, UUID], num_hands: int = 4
    ) -> None:
        if type(num_hands) is not int or not 1 <= num_hands <= 8:
            raise ValueError("bounded positive hand count required")
        payload = model_path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != HAND_MODEL_SHA256:
            raise ValueError("hand model differs from pinned official artifact")
        import mediapipe as mp  # type: ignore[import-untyped]

        self._mp = mp
        self._scope = tuple(scope)
        self.binding = (HAND_MODEL_SHA256, str(mp.__version__), num_hands, 0.5, 0.5)
        options = mp.tasks.vision.HandLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(
                model_asset_buffer=payload, delegate=mp.tasks.BaseOptions.Delegate.CPU
            ),
            running_mode=mp.tasks.vision.RunningMode.IMAGE,
            num_hands=num_hands,
            min_hand_detection_confidence=0.5,
            min_hand_presence_confidence=0.5,
        )
        self._model: Any = mp.tasks.vision.HandLandmarker.create_from_options(options)

    def infer(self, raw: RawModalityObservation, *, cutoff: datetime) -> HandFrame:
        env, pixels = decode_rgb(raw, cutoff=cutoff)
        assert env.payload is not None  # validated by decode_rgb
        if (
            env.identity.household_id,
            env.identity.session_id,
            env.identity.trace_id,
        ) != self._scope:
            raise ValueError("hand detector scope mismatch")
        result = self._model.detect(
            self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=pixels)
        )
        if len(result.hand_landmarks) != len(result.handedness):
            raise ValueError("hand model output cardinality mismatch")
        height, width = pixels.shape[:2]
        candidates = []
        for i, (landmarks, sides) in enumerate(
            zip(result.hand_landmarks, result.handedness, strict=True)
        ):
            if not sides:
                raise ValueError("missing handedness output")
            candidates.append(
                HandCandidate(
                    uuid5(env.identity.observation_id, f"hand:{HAND_MODEL_SHA256}:{i}"),
                    tuple((float(p.x) * width, float(p.y) * height) for p in landmarks),
                    sides[0].category_name,
                    float(sides[0].score),
                )
            )
        return HandFrame(
            env.identity.observation_id,
            env.capture_time,
            env.payload.payload_sha256,
            raw.capture_receipt_sha256,
            self.binding,
            width,
            height,
            tuple(candidates),
        )

    def close(self) -> None:
        self._model.close()
