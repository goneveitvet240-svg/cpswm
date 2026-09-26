"""Uncalibrated image measurements for proposal input, never semantic facts."""

from __future__ import annotations

import json
import math
from dataclasses import asdict
from datetime import datetime
from typing import Any, Literal, Self, cast
from uuid import UUID

from pydantic import Field, model_validator

from cpswm.contracts.base import ContractModel, require_aware
from cpswm.data_preflight.proposal_hand_perception import ProposalHandObservation
from cpswm.perception_mapping.interaction_evidence import (
    AssociatedFrame,
    CausalInstanceAssociator,
    InteractionReadout,
    role_readout,
)
from cpswm.perception_mapping.natural_hands import HandFrame
from cpswm.perception_mapping.natural_vision import VisualFrame


class PixelCandidate(ContractModel):
    candidate_id: UUID
    category: str = Field(min_length=1)
    detector_score: float = Field(ge=0, le=1)
    box_xyxy: tuple[float, float, float, float]


class PixelIdentityBinding(ContractModel):
    key: str
    kind: Literal["actor", "instance"]
    observation_id: UUID
    candidate_id: UUID
    association_status: str


def pixel_causal_readouts(
    observations: tuple[ProposalPixelObservation, ...],
    cutoff: datetime,
) -> tuple[tuple[AssociatedFrame, InteractionReadout], ...]:
    """One rebuilt association history for identity, roles and hand/object joins."""

    groups: dict[tuple[str, str, int, int, str], list[ProposalPixelObservation]] = {}
    for pixel in observations:
        if pixel.arrival_time <= cutoff:
            groups.setdefault(
                (
                    pixel.sensor_id,
                    pixel.frame_id,
                    pixel.width,
                    pixel.height,
                    pixel.archive_sequence_id or "capture-clock",
                ),
                [],
            ).append(pixel)
    readouts = []
    for key, pixels in sorted(groups.items()):
        associator = CausalInstanceAssociator()
        previous_time: float | None = None
        previous: AssociatedFrame | None = None

        def clock(pixel: ProposalPixelObservation) -> float:
            return (
                pixel.capture_time.timestamp()
                if pixel.archive_media_time is None
                else pixel.archive_media_time
            )

        for pixel in sorted(pixels, key=lambda p: (clock(p), str(p.observation_id))):
            media_time = clock(pixel)
            if previous_time is not None and media_time <= previous_time:
                associator = CausalInstanceAssociator()
                previous = None
            frame = associator.update(
                pixel.visual_frame(), sequence_id=str(key), media_time=media_time
            )
            previous_time = media_time
            readouts.append((frame, role_readout(previous, frame)))
            previous = frame
    return tuple(readouts)


def pixel_hypothesis_bindings(
    observations: tuple[ProposalPixelObservation, ...],
    cutoff: datetime,
) -> tuple[PixelIdentityBinding, ...]:
    return tuple(
        PixelIdentityBinding(
            key="perceptual-track:" + str(track),
            kind="actor" if row.category == "person" else "instance",
            observation_id=frame.observation_id,
            candidate_id=row.candidate_id,
            association_status=row.status,
        )
        for frame, _ in pixel_causal_readouts(observations, cutoff)
        for row in frame.detections
        for track in sorted({row.track_id, *(t for t, _ in row.alternatives)}, key=str)
    )


def pixel_model_inputs(
    observations: tuple[ProposalPixelObservation, ...],
    cutoff: datetime,
) -> list[dict[str, Any]]:
    from cpswm.perception_mapping.hand_object_evidence import measure_hand_object_evidence

    readouts = {a.observation_id: (a, r) for a, r in pixel_causal_readouts(observations, cutoff)}
    result = []
    for pixel in observations:
        if pixel.arrival_time > cutoff:
            continue
        associated, interaction = readouts[pixel.observation_id]
        payload = pixel.model_input()
        payload["person_identity_pairs"] = [
            {
                **{k: v for k, v in asdict(p).items() if k != "track_ids"},
                "actor_keys": ["perceptual-track:" + str(t) for t in p.track_ids],
            }
            for p in interaction.person_identity_pairs
        ]
        payload["conditional_roles"] = [
            {
                **{
                    k: v
                    for k, v in asdict(r).items()
                    if k not in {"actor_track_id", "recipient_track_id", "object_track_id"}
                },
                "actor_key": "perceptual-track:" + str(r.actor_track_id),
                "recipient_key": "perceptual-track:" + str(r.recipient_track_id),
                "instance_key": "perceptual-track:" + str(r.object_track_id),
            }
            for r in interaction.role_alternatives
        ]
        payload["interaction_unresolved_reasons"] = interaction.unresolved_reasons
        if pixel.hand_observation is not None:
            measured = measure_hand_object_evidence(
                pixel.visual_frame(), pixel.hand_observation.hand_frame(), associated
            )
            payload["hand_object_measurements"] = [
                {
                    **{
                        k: v
                        for k, v in asdict(r).items()
                        if k not in {"compatible_person_tracks", "object_track_id"}
                    },
                    "compatible_person_keys": [
                        "perceptual-track:" + str(t) for t in r.compatible_person_tracks
                    ],
                    "instance_key": "perceptual-track:" + str(r.object_track_id),
                }
                for r in measured.measurements
            ]
            payload["hand_object_status"] = measured.status
        result.append(payload)
    # Converts only local UUIDs/tuples. Custody and author metadata are excluded.
    return cast(list[dict[str, Any]], json.loads(json.dumps(result, default=str, allow_nan=False)))


class ProposalPixelObservation(ContractModel):
    observation_id: UUID
    household_id: UUID
    session_id: UUID
    trace_id: UUID
    sensor_id: str
    frame_id: str
    capture_time: datetime
    arrival_time: datetime
    inference_cutoff: datetime
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_id: str = Field(min_length=1)
    weights_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    torch_version: str
    torchvision_version: str
    minimum_score: float = Field(ge=0, le=1)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    candidates: tuple[PixelCandidate, ...]
    calibration_status: Literal["UNCALIBRATED_CANDIDATES_ONLY"]
    identity_status: Literal["UNRESOLVED"]
    pose_status: Literal["NOT_ESTIMATED"]
    negative_observation_authorized: Literal[False]
    resize_roundoff_clamps: int = Field(ge=0)
    hand_observation: ProposalHandObservation | None = None
    archive_sequence_id: str | None = None
    archive_media_time: float | None = Field(default=None, ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def valid_frame(self) -> Self:
        for field in ("capture_time", "arrival_time", "inference_cutoff"):
            require_aware(getattr(self, field), field)
        if not self.capture_time <= self.arrival_time <= self.inference_cutoff:
            raise ValueError("invalid pixel observation time order")
        if len({c.candidate_id for c in self.candidates}) != len(self.candidates):
            raise ValueError("duplicate pixel candidate")
        for candidate in self.candidates:
            x1, y1, x2, y2 = candidate.box_xyxy
            if not all(math.isfinite(v) for v in candidate.box_xyxy) or not (
                0 <= x1 < x2 <= self.width and 0 <= y1 < y2 <= self.height
            ):
                raise ValueError("pixel box outside source frame")
        if self.hand_observation is not None:
            self.hand_observation.validate_visual(self.visual_frame())
        return self

    @classmethod
    def from_frame(
        cls,
        frame: VisualFrame,
        hands: HandFrame | None = None,
    ) -> ProposalPixelObservation:
        return cls.model_validate(
            {
                **asdict(frame),
                "hand_observation": None
                if hands is None
                else ProposalHandObservation.from_frame(hands),
            }
        )

    def visual_frame(self) -> VisualFrame:
        from cpswm.perception_mapping.natural_vision import DetectionCandidate

        data = self.model_dump(exclude={"hand_observation"})
        data["candidates"] = tuple(DetectionCandidate(**v) for v in data["candidates"])
        return VisualFrame(**data)

    def model_input(self) -> dict[str, Any]:
        # Hashes, download metadata, source identifiers and future records do not
        # become hidden labels. Perception identities remain explicitly local.
        payload = self.model_dump(
            mode="json",
            include={
                "observation_id",
                "capture_time",
                "arrival_time",
                "width",
                "height",
                "archive_media_time",
                "candidates",
                "calibration_status",
                "identity_status",
                "pose_status",
            },
        )

        if self.hand_observation is not None:
            payload["hands"] = self.hand_observation.model_input()
        return payload
