"""Causal visual association and calibrated, reversible interaction evidence.

Track IDs are sequence-local perceptual hypotheses, never household identities.
Calibration labels live outside method observations. Ambiguous association and
missing object/hand evidence stay unresolved rather than becoming memory facts.
"""

from __future__ import annotations

import math
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import UTC
from itertools import combinations
from threading import RLock
from typing import Literal
from uuid import UUID, uuid5

import numpy as np
from scipy.optimize import minimize  # type: ignore[import-untyped]
from scipy.special import expit  # type: ignore[import-untyped]

from cpswm.contracts.base import require_aware
from cpswm.perception_mapping.natural_vision import VisualFrame
from cpswm.system.reproducibility import content_sha256


def _box(box: tuple[float, float, float, float]) -> None:
    if len(box) != 4 or not all(math.isfinite(v) for v in box):
        raise ValueError("nonfinite visual box")
    if not box[0] < box[2] or not box[1] < box[3]:
        raise ValueError("degenerate visual box")


def box_iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    _box(a)
    _box(b)
    overlap = max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(
        0.0, min(a[3], b[3]) - max(a[1], b[1])
    )
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - overlap
    return overlap / union


@dataclass(frozen=True)
class AssociationConfig:
    minimum_iou: float = 0.3
    ambiguity_margin: float = 0.15
    maximum_gap_seconds: float = 1.0

    def __post_init__(self) -> None:
        if not (
            0 < self.minimum_iou <= 1
            and 0 < self.ambiguity_margin <= 1
            and math.isfinite(self.maximum_gap_seconds)
            and self.maximum_gap_seconds > 0
        ):
            raise ValueError("invalid association configuration")


@dataclass(frozen=True)
class AssociatedDetection:
    candidate_id: UUID
    track_id: UUID
    category: str
    box_xyxy: tuple[float, float, float, float]
    detector_score: float
    status: str
    alternatives: tuple[tuple[UUID, float], ...]
    # IoU alternatives are geometric scores, not calibrated probabilities.


@dataclass(frozen=True)
class AssociatedFrame:
    observation_id: UUID
    sequence_id: str
    media_time: float
    visual_sha256: str
    detections: tuple[AssociatedDetection, ...]


class CausalInstanceAssociator:
    """Conservative mutual-best association; preserve ambiguous/new-instance branches.

    Same-category IoU is a development association baseline. It does not implement
    cross-session re-identification. Occlusion beyond maximum_gap terminates an
    association rather than reusing an unverified identity.
    """

    def __init__(self, config: AssociationConfig | None = None) -> None:
        self.config = deepcopy(config or AssociationConfig())
        self._lock = RLock()
        self._last: AssociatedFrame | None = None
        self._scope: tuple[object, ...] | None = None
        self._seen: dict[UUID, tuple[str, AssociatedFrame]] = {}

    def update(self, frame: VisualFrame, *, sequence_id: str, media_time: float) -> AssociatedFrame:
        with self._lock:
            return deepcopy(
                self._update(deepcopy(frame), sequence_id=sequence_id, media_time=media_time)
            )

    def _update(
        self, frame: VisualFrame, *, sequence_id: str, media_time: float
    ) -> AssociatedFrame:
        if not sequence_id.strip() or not math.isfinite(media_time) or media_time < 0:
            raise ValueError("explicit sequence and finite media time required")
        if frame.width <= 0 or frame.height <= 0:
            raise ValueError("invalid frame dimensions")
        if (
            not require_aware(frame.capture_time, "capture").astimezone(UTC)
            <= require_aware(frame.arrival_time, "arrival").astimezone(UTC)
            <= require_aware(frame.inference_cutoff, "cutoff").astimezone(UTC)
        ):
            raise ValueError("invalid visual time order")
        fingerprint = content_sha256((frame, sequence_id, media_time))
        existing = self._seen.get(frame.observation_id)
        if existing:
            if existing[0] != fingerprint:
                raise ValueError("observation identity changed")
            return existing[1]
        scope = (
            frame.household_id,
            frame.session_id,
            frame.trace_id,
            frame.sensor_id,
            frame.frame_id,
            frame.width,
            frame.height,
            frame.model_id,
            frame.weights_sha256,
            frame.minimum_score,
            frame.torch_version,
            frame.torchvision_version,
        )
        if self._scope is not None and scope != self._scope:
            raise ValueError("association cannot cross camera or session scope")
        previous = self._last
        if previous and (sequence_id != previous.sequence_id or media_time <= previous.media_time):
            raise ValueError("sequence changed or media time did not advance")
        if len({d.candidate_id for d in frame.candidates}) != len(frame.candidates):
            raise ValueError("duplicate visual candidate")
        for detection in frame.candidates:
            _box(detection.box_xyxy)
            if not detection.category.strip() or not (
                0 <= detection.box_xyxy[0] < detection.box_xyxy[2] <= frame.width
                and 0 <= detection.box_xyxy[1] < detection.box_xyxy[3] <= frame.height
            ):
                raise ValueError("box outside visual frame")
            if (
                not math.isfinite(detection.detector_score)
                or not 0 <= detection.detector_score <= 1
            ):
                raise ValueError("invalid detector score")
        old = (
            previous.detections
            if previous and media_time - previous.media_time <= self.config.maximum_gap_seconds
            else ()
        )
        scores = np.array(
            [
                [box_iou(d.box_xyxy, p.box_xyxy) if d.category == p.category else 0.0 for p in old]
                for d in frame.candidates
            ]
        )
        rows = []
        for i, detection in enumerate(frame.candidates):
            alternatives = tuple(
                sorted(
                    (
                        (p.track_id, float(scores[i, j]))
                        for j, p in enumerate(old)
                        if scores[i, j] >= self.config.minimum_iou
                    ),
                    key=lambda pair: (-pair[1], str(pair[0])),
                )
            )
            status = "NEW_UNVERIFIED"
            track_id = uuid5(frame.observation_id, "track:" + str(detection.candidate_id))
            if alternatives:
                chosen = alternatives[0]
                j = next(j for j, p in enumerate(old) if p.track_id == chosen[0])
                row_second = alternatives[1][1] if len(alternatives) > 1 else 0.0
                column = sorted(scores[:, j], reverse=True)
                column_second = float(column[1]) if len(column) > 1 else 0.0
                if (
                    chosen[1] - row_second >= self.config.ambiguity_margin
                    and chosen[1] - column_second >= self.config.ambiguity_margin
                    and chosen[1] == float(column[0])
                ):
                    track_id = chosen[0]
                    status = "ASSOCIATED_GEOMETRIC"
                else:
                    status = "AMBIGUOUS_NEW_BRANCH"
            rows.append(
                AssociatedDetection(
                    detection.candidate_id,
                    track_id,
                    detection.category,
                    detection.box_xyxy,
                    detection.detector_score,
                    status,
                    alternatives,
                )
            )
        result = AssociatedFrame(
            frame.observation_id, sequence_id, media_time, content_sha256(frame), tuple(rows)
        )
        self._scope = scope
        self._last = result
        self._seen[frame.observation_id] = (fingerprint, result)
        return result


@dataclass(frozen=True)
class CalibrationExample:
    sample_id: str
    sequence_id: str
    input_sha256: str
    model_signature: str
    score: float
    label: bool
    annotation_sha256: str
    annotation_source: str

    def __post_init__(self) -> None:
        if not all(
            (self.sample_id, self.sequence_id, self.model_signature, self.annotation_source)
        ):
            raise ValueError("calibration labels require explicit provenance")
        if self.annotation_source not in {"independent_annotation", "dataset_annotation"}:
            raise ValueError("predictions and synthetic labels cannot calibrate real evidence")
        for digest in (self.input_sha256, self.annotation_sha256):
            if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
                raise ValueError("calibration provenance requires SHA256")
        if (
            type(self.label) is not bool
            or not math.isfinite(self.score)
            or not 0 <= self.score <= 1
        ):
            raise ValueError("invalid calibration label or score")


@dataclass(frozen=True)
class CalibrationArtifact:
    model_signature: str
    fit_sequences: tuple[str, ...]
    fit_inputs: tuple[str, ...]
    slope: float
    intercept: float
    sample_count: int
    fit_evidence_sha256: str
    # Fitting alone grants no memory/promotion authority. Provenance describes
    # caller-supplied labels; hashes are integrity, not proof of annotation truth.

    def __post_init__(self) -> None:
        if (
            not self.model_signature
            or not self.fit_sequences
            or not self.fit_inputs
            or self.sample_count < 4
            or not math.isfinite(self.slope)
            or self.slope < 0
            or not math.isfinite(self.intercept)
        ):
            raise ValueError("invalid calibration artifact")

    def probability(self, score: float, *, model_signature: str) -> float:
        if model_signature != self.model_signature:
            raise ValueError("calibration belongs to another model/feature definition")
        if not math.isfinite(score) or not 0 <= score <= 1:
            raise ValueError("invalid raw score")
        clipped = min(1 - 1e-6, max(1e-6, score))
        return float(expit(self.slope * math.log(clipped / (1 - clipped)) + self.intercept))


def fit_calibration(examples: tuple[CalibrationExample, ...]) -> CalibrationArtifact:
    examples = tuple(replace(e) for e in deepcopy(examples))
    if len(examples) < 4 or len({e.label for e in examples}) != 2:
        raise ValueError("calibration needs positive and negative independent labels")
    if len({e.sample_id for e in examples}) != len(examples):
        raise ValueError("duplicate calibration sample")
    if len({e.model_signature for e in examples}) != 1:
        raise ValueError("mixed calibration model signatures")
    x = np.array(
        [
            math.log(min(1 - 1e-6, max(1e-6, e.score)) / (1 - min(1 - 1e-6, max(1e-6, e.score))))
            for e in examples
        ]
    )
    y = np.array([float(e.label) for e in examples])

    def loss(theta: np.ndarray) -> float:
        z = theta[0] * x + theta[1]
        return float(np.mean(np.logaddexp(0, z) - y * z) + 1e-3 * np.sum(theta**2))

    fitted = minimize(
        loss, np.array([1.0, 0.0]), method="L-BFGS-B", bounds=((0.0, None), (None, None))
    )
    if not fitted.success or not np.isfinite(fitted.x).all():
        raise ValueError("calibration optimization failed")
    return CalibrationArtifact(
        examples[0].model_signature,
        tuple(sorted({e.sequence_id for e in examples})),
        tuple(sorted({e.input_sha256 for e in examples})),
        float(fitted.x[0]),
        float(fitted.x[1]),
        len(examples),
        content_sha256(examples),
    )


def evaluate_calibration(
    artifact: CalibrationArtifact, examples: tuple[CalibrationExample, ...]
) -> dict[str, float | int]:
    artifact = replace(deepcopy(artifact))
    examples = tuple(replace(e) for e in deepcopy(examples))
    if not examples:
        raise ValueError("held-out evaluation is empty")
    if any(
        e.sequence_id in artifact.fit_sequences or e.input_sha256 in artifact.fit_inputs
        for e in examples
    ):
        raise ValueError("calibration fit/holdout leakage")
    if len({e.sample_id for e in examples}) != len(examples):
        raise ValueError("duplicate evaluation sample")
    p = np.array(
        [artifact.probability(e.score, model_signature=e.model_signature) for e in examples]
    )
    y = np.array([float(e.label) for e in examples])
    raw = np.array([e.score for e in examples])
    return {
        "count": len(examples),
        "raw_brier": float(np.mean((raw - y) ** 2)),
        "calibrated_brier": float(np.mean((p - y) ** 2)),
        "nll": float(
            -np.mean(y * np.log(np.clip(p, 1e-12, 1)) + (1 - y) * np.log(np.clip(1 - p, 1e-12, 1)))
        ),
    }


@dataclass(frozen=True)
class PersonIdentityPair:
    """Two detection tracks with both physical-person explanations still open.

    These are pairwise alternatives, not independently selectable assignments:
    a future joint identity partition must enforce equivalence/transitivity.
    Box overlap is a measurement, never a same-person or distinct-person gate.
    """

    pair_id: UUID
    track_ids: tuple[UUID, UUID]
    candidate_ids: tuple[UUID, UUID]
    observation_id: UUID
    box_iou: float
    hypotheses: tuple[str, str] = ("same_person_multiple_detections", "distinct_people")
    status: Literal["UNRESOLVED_GEOMETRY_ONLY"] = "UNRESOLVED_GEOMETRY_ONLY"


def person_identity_pairs(current: AssociatedFrame) -> tuple[PersonIdentityPair, ...]:
    """Retain both alternatives for every pair without choosing a new prior."""
    people = sorted(
        (d for d in current.detections if d.category == "person"), key=lambda d: str(d.track_id)
    )
    if len({d.track_id for d in people}) != len(people):
        raise ValueError("duplicate person track in one frame")
    return tuple(
        PersonIdentityPair(
            uuid5(current.observation_id, f"person-pair:{a.track_id}:{b.track_id}"),
            (a.track_id, b.track_id),
            (a.candidate_id, b.candidate_id),
            current.observation_id,
            box_iou(a.box_xyxy, b.box_xyxy),
        )
        for a, b in combinations(people, 2)
    )


@dataclass(frozen=True)
class RoleAlternative:
    object_track_id: UUID
    actor_track_id: UUID
    recipient_track_id: UUID
    evidence_observation_ids: tuple[UUID, UUID]
    identity_pair_id: UUID
    required_identity_hypothesis: Literal["distinct_people"] = "distinct_people"
    explanation: str = "conditional_possible_transfer_or_joint_manipulation"
    # This is pixel-box temporal evidence, not a role posterior or contact proof.


@dataclass(frozen=True)
class InteractionReadout:
    observation_id: UUID
    role_alternatives: tuple[RoleAlternative, ...]
    unresolved_reasons: tuple[str, ...]
    next_observation_request: str
    memory_write_authorized: bool = False
    person_identity_pairs: tuple[PersonIdentityPair, ...] = ()


def _near(person: AssociatedDetection, obj: AssociatedDetection) -> bool:
    # Box overlap only proposes alternatives. It never certifies grasp/contact.
    return box_iou(person.box_xyxy, obj.box_xyxy) > 0


def role_readout(previous: AssociatedFrame | None, current: AssociatedFrame) -> InteractionReadout:
    """Enumerate both ordered roles when box motion permits multiple explanations.

    Object class is never inferred from person motion. Identity breaks remove the
    corresponding temporal role evidence. The non-transfer explanation remains
    explicit. Every role is conditional on two physically distinct people, which
    separate track IDs do not establish. Same-person alternatives remain in the
    readout, including for disjoint body-part boxes. Hands, release and independent
    calibration are required downstream.
    """
    people = tuple(d for d in current.detections if d.category == "person")
    objects = tuple(d for d in current.detections if d.category != "person")
    pairs = person_identity_pairs(current)
    pair_index = {frozenset(p.track_ids): p.pair_id for p in pairs}
    reasons = ["contact_and_release_not_observed", "role_likelihood_not_calibrated"]
    alternatives = []
    if len(people) < 2:
        reasons.append("fewer_than_two_person_candidates")
    else:
        reasons.append("physical_person_identity_not_resolved")
    if not objects:
        reasons.append("no_object_candidate")
    if previous is not None:
        if previous.sequence_id != current.sequence_id or previous.media_time >= current.media_time:
            raise ValueError("role evidence requires ordered same-sequence frames")
        old = {d.track_id: d for d in previous.detections}
        for obj in objects:
            if obj.track_id not in old or obj.status != "ASSOCIATED_GEOMETRIC":
                continue
            for actor in people:
                if actor.track_id not in old or actor.status != "ASSOCIATED_GEOMETRIC":
                    continue
                for recipient in people:
                    if (
                        recipient.track_id == actor.track_id
                        or recipient.track_id not in old
                        or recipient.status != "ASSOCIATED_GEOMETRIC"
                    ):
                        continue
                    if _near(old[actor.track_id], old[obj.track_id]) and _near(recipient, obj):
                        alternatives.append(
                            RoleAlternative(
                                obj.track_id,
                                actor.track_id,
                                recipient.track_id,
                                (previous.observation_id, current.observation_id),
                                pair_index[frozenset((actor.track_id, recipient.track_id))],
                            )
                        )
    if not alternatives:
        reasons.append("no_stable_ordered_role_evidence")
    request = "observe_hands_and_object" if objects else "obtain_closer_object_view"
    return InteractionReadout(
        current.observation_id,
        tuple(alternatives),
        tuple(reasons),
        request,
        person_identity_pairs=pairs,
    )
