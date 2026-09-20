"""Source-bound hand/person/object image-space measurements.

Pixel overlap is not contact. These measurements preserve every compatible
person hypothesis and every object distance, without manufacturing role odds,
metric poses, world identity, or a semantic transition.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from uuid import UUID

from cpswm.perception_mapping.interaction_evidence import AssociatedFrame
from cpswm.perception_mapping.natural_hands import HandFrame
from cpswm.perception_mapping.natural_vision import VisualFrame
from cpswm.system.reproducibility import content_sha256


@dataclass(frozen=True)
class HandObjectMeasurement:
    hand_candidate_id: UUID
    compatible_person_tracks: tuple[UUID, ...]
    person_assignment_status: str
    object_track_id: UUID
    object_candidate_id: UUID
    object_category: str
    minimum_landmark_to_box_px: float
    landmarks_inside_object_box: int
    object_association_status: str
    # No probability field: neither detector confidence nor geometry is calibrated.


@dataclass(frozen=True)
class HandObjectEvidence:
    observation_id: UUID
    visual_sha256: str
    hands_sha256: str
    association_sha256: str
    input_sha256: str
    capture_receipt_sha256: str
    measurements: tuple[HandObjectMeasurement, ...]
    status: str = "IMAGE_GEOMETRY_ONLY_CONTACT_ROLE_AND_POSE_UNRESOLVED"


def measure_hand_object_evidence(
    visual: VisualFrame, hands: HandFrame, associated: AssociatedFrame
) -> HandObjectEvidence:
    if (
        visual.observation_id != hands.observation_id
        or visual.observation_id != associated.observation_id
        or content_sha256(visual) != associated.visual_sha256
        or visual.input_sha256 != hands.input_sha256
        or visual.receipt_sha256 != hands.capture_receipt_sha256
        or visual.capture_time != hands.capture_time
        or (visual.width, visual.height) != (hands.width, hands.height)
    ):
        raise ValueError("hand/object measurements require the same source frame")
    # An associated frame must contain exactly these visual candidates; callers
    # cannot swap boxes while retaining an old claimed visual fingerprint.
    original = {d.candidate_id: d for d in visual.candidates}
    if len(original) != len(associated.detections) or len(
        {d.candidate_id for d in associated.detections}
    ) != len(original):
        raise ValueError("association coverage differs")
    if len({d.track_id for d in associated.detections}) != len(associated.detections):
        raise ValueError("duplicate association track")
    for d in associated.detections:
        if d.status not in {"NEW_UNVERIFIED", "ASSOCIATED_GEOMETRIC", "AMBIGUOUS_NEW_BRANCH"}:
            raise ValueError("invalid geometric association status")
        source = original.get(d.candidate_id)
        if source is None or (source.category, source.box_xyxy, source.detector_score) != (
            d.category,
            d.box_xyxy,
            d.detector_score,
        ):
            raise ValueError("association candidate differs from visual source")
    if len({h.candidate_id for h in hands.candidates}) != len(hands.candidates):
        raise ValueError("duplicate hand candidate")
    people = [d for d in associated.detections if d.category == "person"]
    objects = [d for d in associated.detections if d.category != "person"]
    rows = []
    for hand in hands.candidates:
        hand.__post_init__()
        points = hand.landmarks_xy_pixels
        # An out-of-frame wrist is unresolved, never clipped into a person box.
        wrist_x, wrist_y = points[0]
        persons = tuple(
            sorted(
                (
                    p.track_id
                    for p in people
                    if p.box_xyxy[0] <= wrist_x <= p.box_xyxy[2]
                    and p.box_xyxy[1] <= wrist_y <= p.box_xyxy[3]
                ),
                key=str,
            )
        )
        status = (
            "UNKNOWN"
            if not persons
            else "ONE_GEOMETRIC_CANDIDATE"
            if len(persons) == 1
            else "AMBIGUOUS"
        )
        for obj in objects:
            x1, y1, x2, y2 = obj.box_xyxy
            distance = min(
                math.hypot(max(x1 - x, 0, x - x2), max(y1 - y, 0, y - y2)) for x, y in points
            )
            inside = sum(x1 <= x <= x2 and y1 <= y <= y2 for x, y in points)
            rows.append(
                HandObjectMeasurement(
                    hand.candidate_id,
                    persons,
                    status,
                    obj.track_id,
                    obj.candidate_id,
                    obj.category,
                    distance,
                    inside,
                    obj.status,
                )
            )
    return HandObjectEvidence(
        visual.observation_id,
        content_sha256(visual),
        content_sha256(hands),
        content_sha256(associated),
        visual.input_sha256,
        visual.receipt_sha256,
        tuple(rows),
    )
