"""Strict raw hand observation envelope for uncalibrated proposal features.

Custody/model hashes validate joins but are never neural features. Model output
consistency does not authenticate its execution or establish contact/person truth.
"""

from __future__ import annotations

import math
from dataclasses import asdict
from datetime import datetime
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from cpswm.contracts.base import ContractModel, require_aware
from cpswm.perception_mapping.natural_hands import (
    HAND_MODEL_SHA256,
    HandBinding,
    HandCandidate,
    HandFrame,
    HandRegion,
    validate_hand_regions,
)
from cpswm.perception_mapping.natural_vision import VisualFrame


class ProposalHandCandidate(ContractModel):
    candidate_id: UUID
    landmarks_xy_pixels: tuple[tuple[float, float], ...] = Field(min_length=21, max_length=21)
    handedness: Literal["Left", "Right"]
    handedness_score: float = Field(ge=0, le=1, allow_inf_nan=False)
    region_id: UUID | None = None

    @model_validator(mode="after")
    def finite_landmarks(self) -> Self:
        if any(not math.isfinite(v) for point in self.landmarks_xy_pixels for v in point):
            raise ValueError("nonfinite proposal hand landmark")
        return self


class ProposalHandRegion(ContractModel):
    region_id: UUID
    xyxy: tuple[int, int, int, int]
    person_candidate_id: UUID | None


class ProposalHandObservation(ContractModel):
    observation_id: UUID
    capture_time: datetime
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    capture_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_binding: HandBinding
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    candidates: tuple[ProposalHandCandidate, ...]
    semantic_status: Literal["UNCALIBRATED_HANDS_NO_PERSON_CONTACT_OR_METRIC_POSE"]
    visual_source_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    regions_evaluated: tuple[ProposalHandRegion, ...] = ()

    @model_validator(mode="after")
    def valid_hand(self) -> Self:
        require_aware(self.capture_time, "hand capture")
        binding = self.model_binding
        if (
            binding[0] != HAND_MODEL_SHA256
            or not binding[1].strip()
            or not 1 <= binding[2] <= 8
            or any(not math.isfinite(v) or not 0 <= v <= 1 for v in binding[3:5])
        ):
            raise ValueError("invalid or unpinned proposal hand configuration")
        if len({c.candidate_id for c in self.candidates}) != len(self.candidates):
            raise ValueError("duplicate proposal hand candidate")
        if len(binding) == 5 and len(self.candidates) > binding[2]:
            raise ValueError("hand candidate count exceeds configured full-frame capacity")
        return self

    @classmethod
    def from_frame(cls, frame: HandFrame) -> ProposalHandObservation:
        return cls.model_validate(asdict(frame))

    def hand_frame(self) -> HandFrame:
        data = self.model_dump()
        data["candidates"] = tuple(HandCandidate(**r) for r in data["candidates"])
        data["regions_evaluated"] = tuple(HandRegion(**r) for r in data["regions_evaluated"])
        return HandFrame(**data)

    def validate_visual(self, visual: VisualFrame) -> None:
        if (
            self.observation_id != visual.observation_id
            or self.capture_time != visual.capture_time
            or self.input_sha256 != visual.input_sha256
            or self.capture_receipt_sha256 != visual.receipt_sha256
            or (self.width, self.height) != (visual.width, visual.height)
        ):
            raise ValueError("proposal hands require the same visual source frame")
        validate_hand_regions(self.hand_frame(), visual)

    def model_input(self) -> dict[str, Any]:
        return self.model_dump(
            mode="json",
            include={
                "candidates",
                "regions_evaluated",
                "semantic_status",
            },
        )
