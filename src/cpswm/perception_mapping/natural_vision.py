"""Pixel-derived, uncalibrated detection candidates for natural-appearance input.

No object/person identity, role, negative observation, pose, or memory authority
is inferred from detector categories. Weights are local and pinned; inference
never downloads models or reads simulator annotations. This is the visual front
end, not the calibrated GroundedTransition producer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cpswm.perception_mapping.hand_object_evidence import HandObjectEvidence
    from cpswm.perception_mapping.interaction_evidence import AssociatedFrame, InteractionReadout
    from cpswm.perception_mapping.natural_hands import HandFrame, NaturalHandDetector

import hashlib
import io
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid5

import numpy as np
from numpy.typing import NDArray

from cpswm.contracts.base import SourceType, require_aware
from cpswm.perception_mapping.adapters.contracts import ObservationEnvelope, SensorModality
from cpswm.perception_mapping.adapters.rgbd_capture import RawModalityObservation

WEIGHTS_URL = "https://download.pytorch.org/models/ssdlite320_mobilenet_v3_large_coco-a79551df.pth"
WEIGHTS_SHA256 = "a79551df90c79834bcd3bb3845ef9d966b5449a3a9b2833ae8404778ca5d65d2"
MODEL_ID = "torchvision/ssdlite320_mobilenet_v3_large/COCO_V1"
MAX_RGB_BYTES = 4096 * 4096 * 3 + 65536


@dataclass(frozen=True)
class DetectionCandidate:
    candidate_id: UUID
    category: str
    detector_score: float
    box_xyxy: tuple[float, float, float, float]
    # A candidate ID identifies a frame detection, never a persistent world entity.


@dataclass(frozen=True)
class VisualFrame:
    observation_id: UUID
    household_id: UUID
    session_id: UUID
    trace_id: UUID
    sensor_id: str
    frame_id: str
    capture_time: datetime
    arrival_time: datetime
    inference_cutoff: datetime
    input_sha256: str
    receipt_sha256: str
    model_id: str
    weights_sha256: str
    torch_version: str
    torchvision_version: str
    minimum_score: float
    width: int
    height: int
    candidates: tuple[DetectionCandidate, ...]
    calibration_status: str = "UNCALIBRATED_CANDIDATES_ONLY"
    identity_status: str = "UNRESOLVED"
    pose_status: str = "NOT_ESTIMATED"
    negative_observation_authorized: bool = False
    resize_roundoff_clamps: int = 0
    archive_sequence_id: str | None = None
    archive_media_time: float | None = None


def decode_rgb(
    raw: RawModalityObservation, *, cutoff: datetime
) -> tuple[ObservationEnvelope, NDArray[np.uint8]]:
    """Validate the wire boundary and NPY allocation bounds before loading pixels."""
    when = require_aware(cutoff, "cutoff").astimezone(UTC)
    if type(raw) is not RawModalityObservation or type(raw.payload_bytes) is not bytes:
        raise ValueError("immutable raw observation required")
    env = raw.envelope()
    if env.oracle_channel or env.sensor.modality is not SensorModality.RGB:
        raise ValueError("only non-oracle RGB is accepted")
    if env.metadata.source_type not in {
        SourceType.SENSOR,
        SourceType.SIMULATION,
        SourceType.IMPORT,
    }:
        raise ValueError("RGB requires a sensor or archive source")
    if raw.depth_unit is not None:
        raise ValueError("RGB cannot carry a depth unit")
    if len(raw.capture_receipt_sha256) != 64 or any(
        ch not in "0123456789abcdef" for ch in raw.capture_receipt_sha256
    ):
        raise ValueError("invalid capture receipt digest")
    if not env.capture_time.astimezone(UTC) <= env.arrival_time.astimezone(UTC) <= when:
        raise ValueError("capture or arrival is outside visible cutoff")
    if not 0 < len(raw.payload_bytes) <= MAX_RGB_BYTES:
        raise ValueError("RGB payload exceeds allocation bound")
    stream = io.BytesIO(raw.payload_bytes)
    version = np.lib.format.read_magic(stream)
    if version == (1, 0):
        shape, fortran, dtype = np.lib.format.read_array_header_1_0(stream)
    elif version == (2, 0):
        shape, fortran, dtype = np.lib.format.read_array_header_2_0(stream)
    else:
        raise ValueError("unsupported NPY wire version")
    if (
        dtype != np.dtype("uint8")
        or fortran
        or len(shape) != 3
        or shape[2] != 3
        or not all(type(n) is int and 0 < n <= 4096 for n in shape[:2])
        or math.prod(shape) != len(raw.payload_bytes) - stream.tell()
    ):
        raise ValueError("RGB must be bounded HWC uint8 with exact payload size")
    if raw.archive_sampling_json is not None:
        import json

        crop = json.loads(raw.archive_sampling_json)["crop_xywh"]
        if (crop[3], crop[2]) != shape[:2]:
            raise ValueError("archive crop differs from RGB payload dimensions")
    pixels: NDArray[np.uint8] = np.load(io.BytesIO(raw.payload_bytes), allow_pickle=False)
    return env, pixels


class NaturalAppearanceDetector:
    """CPU development detector with offline, full-digest checked official weights.

    minimum_score is a recorded development filtering setting, NOT a calibrated
    acceptance threshold. The model sees only pixels. Torchvision still performs
    its native NMS/top-k postprocessing; returned boxes are not full hypotheses.
    """

    model_id = MODEL_ID
    weights_sha256 = WEIGHTS_SHA256

    @staticmethod
    def _build_model_and_categories() -> tuple[Any, tuple[str, ...]]:
        from torchvision.models.detection import (  # type: ignore[import-untyped]
            SSDLite320_MobileNet_V3_Large_Weights,
            ssdlite320_mobilenet_v3_large,
        )

        model = ssdlite320_mobilenet_v3_large(weights=None, weights_backbone=None)
        return model, tuple(SSDLite320_MobileNet_V3_Large_Weights.COCO_V1.meta["categories"])

    def __init__(
        self,
        *,
        weights_path: Path,
        household_id: UUID,
        session_id: UUID,
        trace_id: UUID,
        minimum_score: float = 0.5,
    ) -> None:
        if type(minimum_score) not in {int, float} or not math.isfinite(minimum_score):
            raise ValueError("minimum score must be finite")
        if not 0 <= minimum_score <= 1:
            raise ValueError("minimum score must lie in [0,1]")
        weight_bytes = weights_path.read_bytes()
        if hashlib.sha256(weight_bytes).hexdigest() != self.weights_sha256:
            raise ValueError("weights differ from pinned official artifact")
        # Optional heavy dependency: raw validation remains usable without torch.
        import torch
        import torchvision  # type: ignore[import-untyped]

        self._torch = torch
        self._versions = (str(torch.__version__), str(torchvision.__version__))
        self._scope = (household_id, session_id, trace_id)
        self._minimum_score = float(minimum_score)
        # No default backbone download; state_dict comes from the exact hashed bytes.
        self._model, self._categories = self._build_model_and_categories()
        self._model.load_state_dict(
            torch.load(io.BytesIO(weight_bytes), weights_only=True, map_location="cpu"), strict=True
        )
        self._model.eval()
        self._model.requires_grad_(False)

    def infer(self, raw: RawModalityObservation, *, cutoff: datetime) -> VisualFrame:
        env, pixels = decode_rgb(raw, cutoff=cutoff)
        scope = (env.identity.household_id, env.identity.session_id, env.identity.trace_id)
        if scope != self._scope:
            raise ValueError("visual observation belongs to another scope")
        torch = self._torch
        tensor = torch.from_numpy(pixels.copy()).permute(2, 0, 1).float().div(255.0)
        with torch.inference_mode():
            prediction = self._model([tensor])[0]
        height, width = pixels.shape[:2]
        prediction, roundoff_clamps = self._normalize_resize_roundoff(prediction, width, height)
        candidates = self._validate_prediction(
            prediction, env.identity.observation_id, width, height
        )
        timeline = raw.archive_timeline()
        return VisualFrame(
            env.identity.observation_id,
            *scope,
            env.sensor.sensor_id,
            env.frame_id,
            env.capture_time.astimezone(UTC),
            env.arrival_time.astimezone(UTC),
            require_aware(cutoff, "cutoff").astimezone(UTC),
            hashlib.sha256(raw.payload_bytes).hexdigest(),
            raw.capture_receipt_sha256,
            self.model_id,
            self.weights_sha256,
            *self._versions,
            self._minimum_score,
            width,
            height,
            candidates,
            resize_roundoff_clamps=roundoff_clamps,
            archive_sequence_id=None if timeline is None else timeline[0],
            archive_media_time=None if timeline is None else timeline[1],
        )

    def _normalize_resize_roundoff(
        self,
        prediction: dict[str, Any],
        width: int,
        height: int,
    ) -> tuple[dict[str, Any], int]:
        """Clamp at most two float32 ULPs introduced by native image rescaling.

        Native Faster R-CNN can return y2=480.0000305 for a 480px image.
        This is representation repair, not a relaxed geometric validity gate.
        Every repaired box is counted even if later removed by score filtering.
        """
        boxes = prediction["boxes"]
        if boxes.ndim != 2 or boxes.shape[1] != 4 or boxes.dtype != self._torch.float32:
            raise ValueError("invalid detector box tensor")
        bounds = boxes.new_tensor([width, height, width, height])
        tolerance = 2 * float(np.spacing(np.float32(max(width, height))))
        if (
            not self._torch.isfinite(boxes).all()
            or (boxes < -tolerance).any()
            or (boxes > bounds + tolerance).any()
        ):
            raise ValueError("invalid detector candidate outside numerical resize bound")
        changed = ((boxes < 0) | (boxes > bounds)).any(dim=1)
        normalized = self._torch.minimum(boxes.clamp_min(0), bounds)
        return dict(prediction, boxes=normalized), int(changed.sum().item())

    def _validate_prediction(
        self, prediction: dict[str, Any], observation_id: UUID, width: int, height: int
    ) -> tuple[DetectionCandidate, ...]:
        boxes, scores, labels = (
            prediction[k].detach().cpu().tolist() for k in ("boxes", "scores", "labels")
        )
        if not len(boxes) == len(scores) == len(labels):
            raise ValueError("detector output length mismatch")
        candidates = []
        for index, (box, score, label) in enumerate(zip(boxes, scores, labels, strict=True)):
            if (
                len(box) != 4
                or not all(math.isfinite(x) for x in (*box, score))
                or not 0 <= score <= 1
                or type(label) is not int
                or not 0 < label < len(self._categories)
                or self._categories[label] == "N/A"
                or not 0 <= box[0] < box[2] <= width
                or not 0 <= box[1] < box[3] <= height
            ):
                raise ValueError("invalid detector candidate")
            if score >= self._minimum_score:
                key = f"{self.weights_sha256}:{self._minimum_score}:{index}:{label}:{box}:{score}"
                candidates.append(
                    DetectionCandidate(
                        uuid5(observation_id, key),
                        self._categories[label],
                        float(score),
                        tuple(box),
                    )
                )
        return tuple(candidates)


class FasterNaturalAppearanceDetector(NaturalAppearanceDetector):
    """Pinned higher-resolution COCO alternative for small-object development.

    Uses the official native 800/1333 transform and the same raw-only boundary.
    Scores remain uncalibrated; this model does not estimate roles or 6D poses.
    """

    model_id = "torchvision/fasterrcnn_resnet50_fpn_v2/COCO_V1"
    weights_sha256 = "dd69338a24b8d7381807e247652bdc356325bcbaf1cd3e092e00e0a1a58706bf"
    weights_url = "https://download.pytorch.org/models/fasterrcnn_resnet50_fpn_v2_coco-dd69338a.pth"

    @staticmethod
    def _build_model_and_categories() -> tuple[Any, tuple[str, ...]]:
        from torchvision.models.detection import (
            FasterRCNN_ResNet50_FPN_V2_Weights,
            fasterrcnn_resnet50_fpn_v2,
        )

        model = fasterrcnn_resnet50_fpn_v2(weights=None, weights_backbone=None)
        return model, tuple(FasterRCNN_ResNet50_FPN_V2_Weights.COCO_V1.meta["categories"])


class NaturalVisionEvidenceProducer:
    """Connect pixel inference to the continuous stream without inventing semantics.

    The stream invokes this producer on its delivered prefix. Candidates are
    retained atomically and replayed inputs are not inferred again. No calibrated
    instance/role/pose bridge exists yet, so infer returns None and the memory
    core remains unchanged. This is an explicit capability boundary.
    """

    def __init__(
        self, detector: NaturalAppearanceDetector, hand_detector: NaturalHandDetector | None = None
    ) -> None:
        from threading import RLock

        self._detector = detector
        if hand_detector is not None and hand_detector._scope != detector._scope:
            raise ValueError("visual and hand detector scopes differ")
        self._hand_detector = hand_detector
        self._hand_frames: tuple[HandFrame, ...] = ()
        self._prefix: tuple[RawModalityObservation, ...] = ()
        self._frames: tuple[VisualFrame, ...] = ()
        self._cutoff: datetime | None = None
        # Load configured association types before a fresh process decodes its
        # checkpoint. The checkpoint itself is never allowed to import code.
        self._interactions: tuple[tuple[AssociatedFrame, InteractionReadout], ...] = (
            self._recompute_interactions(())
        )
        self._lock = RLock()
        self._busy = False

    def checkpoint_state(self) -> dict[str, Any]:
        from copy import deepcopy

        with self._lock:
            return deepcopy(
                {
                    "scope": self._detector._scope,
                    "detector_binding": (
                        self._detector.weights_sha256,
                        self._detector._versions,
                        self._detector._minimum_score,
                    ),
                    "interactions": self._interactions,
                    "prefix": self._prefix,
                    "frames": self._frames,
                    "cutoff": self._cutoff,
                    "hand_binding": None
                    if self._hand_detector is None
                    else self._hand_detector.binding,
                    "hand_frames": self._hand_frames,
                }
            )

    def restore_state(self, state: dict[str, Any]) -> None:
        from copy import deepcopy
        from dataclasses import replace

        from cpswm.perception_mapping.natural_hands import HandCandidate, HandFrame

        with self._lock:
            if self._busy:
                raise RuntimeError("cannot restore during visual inference")
            # Stage the entire checkpoint. Nothing is assigned until every dependency
            # and derived record has been validated, including failure/retry paths.
            candidate = deepcopy(state)
            required = {"scope", "detector_binding", "interactions", "prefix", "frames", "cutoff"}
            if self._hand_detector is not None:
                required |= {"hand_binding", "hand_frames"}
            if not required <= candidate.keys():
                raise ValueError("incomplete perception checkpoint")
            expected_hand = None if self._hand_detector is None else self._hand_detector.binding
            if candidate.get("hand_binding") != expected_hand:
                raise ValueError("checkpoint hand model configuration changed")
            if candidate["scope"] != self._detector._scope:
                raise ValueError("perception restore requires a matching detector scope")
            if candidate["detector_binding"] != (
                self._detector.weights_sha256,
                self._detector._versions,
                self._detector._minimum_score,
            ):
                raise ValueError("checkpoint detector configuration changed")
            prefix, frames, cutoff = candidate["prefix"], candidate["frames"], candidate["cutoff"]
            hands = candidate.get("hand_frames", ())
            if any(type(value) is not tuple for value in (prefix, frames, hands)):
                raise ValueError("checkpoint evidence must be immutable tuples")
            if prefix and cutoff is None:
                raise ValueError("nonempty checkpoint requires a causal cutoff")
            if cutoff is not None:
                require_aware(cutoff, "checkpoint cutoff")
            rgb = []
            seen = set()
            for raw in prefix:
                if type(raw) is not RawModalityObservation:
                    raise ValueError("invalid checkpoint raw observation")
                env = raw.envelope()
                if (
                    env.identity.observation_id in seen
                    or env.oracle_channel
                    or env.metadata.source_type
                    not in {SourceType.SENSOR, SourceType.SIMULATION, SourceType.IMPORT}
                    or (env.identity.household_id, env.identity.session_id, env.identity.trace_id)
                    != self._detector._scope
                    or not env.capture_time <= env.arrival_time <= cutoff
                ):
                    raise ValueError("checkpoint prefix identity/scope/time mismatch")
                seen.add(env.identity.observation_id)
                if env.sensor.modality is SensorModality.RGB:
                    _, pixels = decode_rgb(raw, cutoff=cutoff)
                    rgb.append((raw, env, pixels.shape))
            if len(frames) != len(rgb):
                raise ValueError("checkpoint visual coverage differs from raw prefix")
            for frame, (raw, env, shape) in zip(frames, rgb, strict=True):
                if (
                    type(frame) is not VisualFrame
                    or env.payload is None
                    or frame.observation_id != env.identity.observation_id
                    or (frame.household_id, frame.session_id, frame.trace_id)
                    != self._detector._scope
                    or frame.sensor_id != env.sensor.sensor_id
                    or frame.frame_id != env.frame_id
                    or frame.capture_time != env.capture_time
                    or frame.arrival_time != env.arrival_time
                    or not env.arrival_time <= frame.inference_cutoff <= cutoff
                    or frame.input_sha256 != env.payload.payload_sha256
                    or frame.receipt_sha256 != raw.capture_receipt_sha256
                    or (
                        None
                        if frame.archive_sequence_id is None and frame.archive_media_time is None
                        else (frame.archive_sequence_id, frame.archive_media_time)
                    )
                    != raw.archive_timeline()
                    or (frame.height, frame.width) != shape[:2]
                    or frame.model_id != self._detector.model_id
                    or frame.weights_sha256 != self._detector.weights_sha256
                    or (frame.torch_version, frame.torchvision_version) != self._detector._versions
                    or frame.minimum_score != self._detector._minimum_score
                    or frame.calibration_status != "UNCALIBRATED_CANDIDATES_ONLY"
                    or frame.identity_status != "UNRESOLVED"
                    or frame.pose_status != "NOT_ESTIMATED"
                    or frame.negative_observation_authorized is not False
                ):
                    raise ValueError("checkpoint visual/raw/model binding mismatch")
            expected_count = len(frames) if self._hand_detector is not None else 0
            if len(hands) != expected_count:
                raise ValueError("checkpoint hand coverage differs from visual history")
            for hand, visual in zip(hands, frames[:expected_count], strict=True):
                if (
                    type(hand) is not HandFrame
                    or hand.model_binding != expected_hand
                    or hand.observation_id != visual.observation_id
                    or hand.capture_time != visual.capture_time
                    or hand.input_sha256 != visual.input_sha256
                    or hand.capture_receipt_sha256 != visual.receipt_sha256
                    or (hand.width, hand.height) != (visual.width, visual.height)
                    or hand.semantic_status != "UNCALIBRATED_HANDS_NO_PERSON_CONTACT_OR_METRIC_POSE"
                    or type(hand.candidates) is not tuple
                    or any(type(h) is not HandCandidate for h in hand.candidates)
                    or len({h.candidate_id for h in hand.candidates}) != len(hand.candidates)
                ):
                    raise ValueError("checkpoint hand/raw/model binding mismatch")
                for detection in hand.candidates:
                    if type(detection) is not HandCandidate:
                        raise ValueError("invalid checkpoint hand candidate")
                    replace(detection)  # revalidate dataclass contents after deserialization
            interactions = self._recompute_interactions(frames)
            if interactions != candidate["interactions"]:
                raise ValueError("checkpoint interactions differ from visual history")
            self._prefix, self._frames, self._cutoff = prefix, frames, cutoff
            self._hand_frames, self._interactions = hands, interactions

    def hand_object_evidence(self) -> tuple[HandObjectEvidence, ...]:
        """Derived image measurements from the same retained raw-prefix inference.

        Checkpoints retain source frames, not a second mutable relation ledger.
        No hand detector means no measurements, never inferred absence of contact.
        """
        from cpswm.perception_mapping.hand_object_evidence import measure_hand_object_evidence

        with self._lock:
            if self._hand_detector is None:
                return ()
            hands = {h.observation_id: h for h in self._hand_frames}
            associations = {a.observation_id: a for a, _ in self._interactions}
            identities = {f.observation_id for f in self._frames}
            if (
                len(hands) != len(self._hand_frames)
                or len(associations) != len(self._interactions)
                or len(identities) != len(self._frames)
                or set(hands) != identities
                or set(associations) != identities
            ):
                raise ValueError("derived hand/object observation coverage differs")
            return tuple(
                measure_hand_object_evidence(
                    visual, hands[visual.observation_id], associations[visual.observation_id]
                )
                for visual in self._frames
            )

    def hand_frames(self) -> tuple[HandFrame, ...]:
        from copy import deepcopy

        with self._lock:
            return deepcopy(self._hand_frames)

    def interactions(self) -> tuple[tuple[AssociatedFrame, InteractionReadout], ...]:
        from copy import deepcopy

        with self._lock:
            return deepcopy(self._interactions)

    @staticmethod
    def _recompute_interactions(
        frames: tuple[VisualFrame, ...],
    ) -> tuple[tuple[AssociatedFrame, InteractionReadout], ...]:
        from cpswm.perception_mapping.interaction_evidence import (
            CausalInstanceAssociator,
            role_readout,
        )

        # Late frames trigger recomputation from the retained original observations.
        # Separate sensors never share instance identities. Equal capture times do
        # not establish temporal contact/release and therefore start a new segment.
        groups: dict[tuple[str, str, int, int, str], list[VisualFrame]] = {}
        for frame in frames:
            key = (
                frame.sensor_id,
                frame.frame_id,
                frame.width,
                frame.height,
                frame.archive_sequence_id or "capture-clock",
            )
            groups.setdefault(key, []).append(frame)
        result = []
        for key, values in sorted(groups.items()):
            associator = CausalInstanceAssociator()
            previous = None

            def observation_time(f: VisualFrame) -> float:
                return (
                    f.capture_time.timestamp()
                    if f.archive_media_time is None
                    else f.archive_media_time
                )

            for frame in sorted(values, key=lambda f: (observation_time(f), str(f.observation_id))):
                time = observation_time(frame)
                if previous is not None and time <= previous.media_time:
                    associator = CausalInstanceAssociator()
                    previous = None
                associated = associator.update(frame, sequence_id=str(key), media_time=time)
                result.append((associated, role_readout(previous, associated)))
                previous = associated
        return tuple(result)

    def frames(self) -> tuple[VisualFrame, ...]:
        from copy import deepcopy

        with self._lock:
            return deepcopy(self._frames)

    def infer(
        self, visible_prefix: tuple[RawModalityObservation, ...], *, cutoff: datetime
    ) -> None:
        from copy import deepcopy

        with self._lock:
            if self._busy:
                raise RuntimeError("reentrant visual producer")
            self._busy = True
            try:
                when = require_aware(cutoff, "cutoff").astimezone(UTC)
                if self._cutoff is not None and when < self._cutoff:
                    raise ValueError("visual cutoff moved backwards")
                prefix = deepcopy(visible_prefix)
                if prefix[: len(self._prefix)] != self._prefix:
                    raise ValueError("visual history changed or was truncated")
                ids = set()
                selected = []
                for index, raw in enumerate(prefix):
                    if (
                        type(raw) is not RawModalityObservation
                        or type(raw.payload_bytes) is not bytes
                    ):
                        raise ValueError("immutable raw observation required")
                    env = raw.envelope()
                    if env.identity.observation_id in ids:
                        raise ValueError("duplicate visual observation identity")
                    ids.add(env.identity.observation_id)
                    if (
                        env.oracle_channel
                        or env.metadata.source_type
                        not in {SourceType.SENSOR, SourceType.SIMULATION, SourceType.IMPORT}
                        or (
                            env.identity.household_id,
                            env.identity.session_id,
                            env.identity.trace_id,
                        )
                        != self._detector._scope
                        or not env.capture_time.astimezone(UTC)
                        <= env.arrival_time.astimezone(UTC)
                        <= when
                    ):
                        raise ValueError("invalid visual prefix scope or time")
                    if index >= len(self._prefix) and env.sensor.modality is SensorModality.RGB:
                        decode_rgb(raw, cutoff=when)
                        selected.append(raw)
                # A failed batch may have consumed computation, never committed evidence.
                frames = tuple(self._detector.infer(raw, cutoff=when) for raw in selected)
                hand_frames = (
                    ()
                    if self._hand_detector is None
                    else tuple(self._hand_detector.infer(raw, cutoff=when) for raw in selected)
                )
                all_frames = self._frames + frames
                interactions = self._recompute_interactions(all_frames)
                self._frames = all_frames
                self._hand_frames += hand_frames
                self._interactions = interactions
                self._prefix, self._cutoff = prefix, when
                return None
            finally:
                self._busy = False
