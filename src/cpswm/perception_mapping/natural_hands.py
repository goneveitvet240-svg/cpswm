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
from cpswm.perception_mapping.natural_vision import VisualFrame, decode_rgb
from cpswm.system.reproducibility import content_sha256

ROI_PROFILE = "full_plus_top4_person_margin015_v1"
HandBinding = tuple[str, str, int, float, float] | tuple[str, str, int, float, float, str]

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
    region_id: UUID | None = None
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
class HandRegion:
    region_id: UUID
    xyxy: tuple[int, int, int, int]
    person_candidate_id: UUID | None


def person_regions(visual: VisualFrame) -> tuple[HandRegion, ...]:
    """Deterministic crop proposal only; person box is not ownership evidence."""
    if visual.width <= 0 or visual.height <= 0:
        raise ValueError("invalid ROI image dimensions")
    if len({d.candidate_id for d in visual.candidates}) != len(visual.candidates):
        raise ValueError("duplicate visual candidate identity")
    regions = [
        HandRegion(
            uuid5(visual.observation_id, ROI_PROFILE + ":full"),
            (0, 0, visual.width, visual.height),
            None,
        )
    ]
    people = sorted(
        (d for d in visual.candidates if d.category == "person"),
        key=lambda d: (-d.detector_score, str(d.candidate_id)),
    )[:4]
    for person in people:
        x1, y1, x2, y2 = person.box_xyxy
        if not (
            all(math.isfinite(v) for v in (x1, y1, x2, y2, person.detector_score))
            and 0 <= x1 < x2 <= visual.width
            and 0 <= y1 < y2 <= visual.height
            and 0 <= person.detector_score <= 1
        ):
            raise ValueError("invalid ROI person candidate")
        mx, my = (x2 - x1) * 0.15, (y2 - y1) * 0.15
        box = (
            max(0, math.floor(x1 - mx)),
            max(0, math.floor(y1 - my)),
            min(visual.width, math.ceil(x2 + mx)),
            min(visual.height, math.ceil(y2 + my)),
        )
        if box[2] - box[0] < 2 or box[3] - box[1] < 2:
            continue
        regions.append(
            HandRegion(
                uuid5(visual.observation_id, ROI_PROFILE + ":" + str(person.candidate_id)),
                box,
                person.candidate_id,
            )
        )
    return tuple(regions)


@dataclass(frozen=True)
class HandFrame:
    observation_id: UUID
    capture_time: datetime
    input_sha256: str
    capture_receipt_sha256: str
    model_binding: HandBinding
    width: int
    height: int
    candidates: tuple[HandCandidate, ...]
    semantic_status: str = "UNCALIBRATED_HANDS_NO_PERSON_CONTACT_OR_METRIC_POSE"
    visual_source_sha256: str | None = None
    regions_evaluated: tuple[HandRegion, ...] = ()
    # ROI observations can overlap: raw regional candidates are NOT unique hands.


class NaturalHandDetector:
    def __init__(
        self,
        *,
        model_path: Path,
        scope: tuple[UUID, UUID, UUID],
        num_hands: int = 4,
        person_rois: bool = False,
    ) -> None:
        if type(num_hands) is not int or not 1 <= num_hands <= 8:
            raise ValueError("bounded positive hand count required")
        if type(person_rois) is not bool:
            raise ValueError("person_rois must be boolean")
        payload = model_path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != HAND_MODEL_SHA256:
            raise ValueError("hand model differs from pinned official artifact")
        import mediapipe as mp  # type: ignore[import-untyped]

        self._mp = mp
        self._scope = tuple(scope)
        self.uses_person_regions = person_rois
        base: tuple[str, str, int, float, float] = (
            HAND_MODEL_SHA256,
            str(mp.__version__),
            num_hands,
            0.5,
            0.5,
        )
        self.binding: HandBinding = (*base, ROI_PROFILE) if person_rois else base
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
        if self.uses_person_regions:
            raise ValueError("ROI hand inference requires source-bound visual candidates")
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

    def infer_with_visual(
        self, raw: RawModalityObservation, visual: VisualFrame, *, cutoff: datetime
    ) -> HandFrame:
        if not self.uses_person_regions:
            raise ValueError("ROI profile is not enabled")
        env, pixels = decode_rgb(raw, cutoff=cutoff)
        assert env.payload is not None
        if (
            (env.identity.household_id, env.identity.session_id, env.identity.trace_id)
            != self._scope
            or (visual.household_id, visual.session_id, visual.trace_id) != self._scope
            or visual.observation_id != env.identity.observation_id
            or visual.input_sha256 != env.payload.payload_sha256
            or visual.receipt_sha256 != raw.capture_receipt_sha256
            or visual.capture_time != env.capture_time
            or (
                None
                if visual.archive_sequence_id is None and visual.archive_media_time is None
                else (visual.archive_sequence_id, visual.archive_media_time)
            )
            != raw.archive_timeline()
            or visual.sensor_id != env.sensor.sensor_id
            or visual.frame_id != env.frame_id
            or visual.arrival_time != env.arrival_time
            or not env.arrival_time <= visual.inference_cutoff <= cutoff
            or (visual.height, visual.width) != pixels.shape[:2]
        ):
            raise ValueError("ROI visual source differs from raw observation")
        import numpy as np

        regions = person_regions(visual)
        candidates = []
        for region in regions:
            x1, y1, x2, y2 = region.xyxy
            crop = np.ascontiguousarray(pixels[y1:y2, x1:x2])
            result = self._model.detect(
                self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=crop)
            )
            if (
                len(result.hand_landmarks) != len(result.handedness)
                or len(result.hand_landmarks) > self.binding[2]
            ):
                raise ValueError("ROI hand cardinality mismatch")
            for i, (landmarks, sides) in enumerate(
                zip(result.hand_landmarks, result.handedness, strict=True)
            ):
                if not sides:
                    raise ValueError("missing ROI handedness")
                candidates.append(
                    HandCandidate(
                        uuid5(region.region_id, f"hand:{HAND_MODEL_SHA256}:{i}"),
                        tuple(
                            (x1 + float(p.x) * (x2 - x1), y1 + float(p.y) * (y2 - y1))
                            for p in landmarks
                        ),
                        sides[0].category_name,
                        float(sides[0].score),
                        region.region_id,
                    )
                )
        return HandFrame(
            env.identity.observation_id,
            env.capture_time,
            env.payload.payload_sha256,
            raw.capture_receipt_sha256,
            self.binding,
            visual.width,
            visual.height,
            tuple(candidates),
            visual_source_sha256=content_sha256(visual),
            regions_evaluated=regions,
        )

    def close(self) -> None:
        self._model.close()


def validate_hand_regions(frame: HandFrame, visual: VisualFrame) -> None:
    """Restore derived ROI provenance; never promote crop ownership into a role."""
    if len(frame.model_binding) == 6:
        if frame.model_binding[-1] != ROI_PROFILE or frame.visual_source_sha256 != content_sha256(
            visual
        ):
            raise ValueError("ROI hand source/configuration differs")
        expected = person_regions(visual)
        if frame.regions_evaluated != expected:
            raise ValueError("ROI regions differ from visual candidates")
        ids = {r.region_id for r in expected}
        if len(ids) != len(expected) or any(c.region_id not in ids for c in frame.candidates):
            raise ValueError("ROI candidate region identity differs")
        expected_candidates = []
        for region in expected:
            count = sum(c.region_id == region.region_id for c in frame.candidates)
            if count > frame.model_binding[2]:
                raise ValueError("ROI candidate count exceeds configured capacity")
            expected_candidates.extend(
                (uuid5(region.region_id, f"hand:{HAND_MODEL_SHA256}:{i}"), region.region_id)
                for i in range(count)
            )
        if [(c.candidate_id, c.region_id) for c in frame.candidates] != expected_candidates:
            raise ValueError("ROI candidate identity/order differs from region derivation")

    elif (
        frame.visual_source_sha256 is not None
        or frame.regions_evaluated
        or any(c.region_id is not None for c in frame.candidates)
    ):
        raise ValueError("full-frame profile cannot claim ROI evidence")
