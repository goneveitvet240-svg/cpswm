"""Pixel-derived, uncalibrated detection candidates for natural-appearance input.

No object/person identity, role, negative observation, pose, or memory authority
is inferred from detector categories. Weights are local and pinned; inference
never downloads models or reads simulator annotations. This is the visual front
end, not the calibrated GroundedTransition producer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cpswm.perception_mapping.interaction_evidence import AssociatedFrame, InteractionReadout

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
    pixels: NDArray[np.uint8] = np.load(io.BytesIO(raw.payload_bytes), allow_pickle=False)
    return env, pixels


class NaturalAppearanceDetector:
    """CPU development detector with offline, full-digest checked official weights.

    minimum_score is a recorded development filtering setting, NOT a calibrated
    acceptance threshold. The model sees only pixels. Torchvision still performs
    its native NMS/top-k postprocessing; returned boxes are not full hypotheses.
    """

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
        if hashlib.sha256(weight_bytes).hexdigest() != WEIGHTS_SHA256:
            raise ValueError("weights differ from pinned official artifact")
        # Optional heavy dependency: raw validation remains usable without torch.
        import torch
        import torchvision  # type: ignore[import-untyped]
        from torchvision.models.detection import (  # type: ignore[import-untyped]
            SSDLite320_MobileNet_V3_Large_Weights,
            ssdlite320_mobilenet_v3_large,
        )

        self._torch = torch
        self._versions = (str(torch.__version__), str(torchvision.__version__))
        self._scope = (household_id, session_id, trace_id)
        self._minimum_score = float(minimum_score)
        self._categories = tuple(SSDLite320_MobileNet_V3_Large_Weights.COCO_V1.meta["categories"])
        # No default backbone download; state_dict comes from the exact hashed bytes.
        self._model = ssdlite320_mobilenet_v3_large(weights=None, weights_backbone=None)
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
        candidates = self._validate_prediction(
            prediction, env.identity.observation_id, width, height
        )
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
            MODEL_ID,
            WEIGHTS_SHA256,
            *self._versions,
            self._minimum_score,
            width,
            height,
            candidates,
        )

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
                key = f"{WEIGHTS_SHA256}:{self._minimum_score}:{index}:{label}:{box}:{score}"
                candidates.append(
                    DetectionCandidate(
                        uuid5(observation_id, key),
                        self._categories[label],
                        float(score),
                        tuple(box),
                    )
                )
        return tuple(candidates)


class NaturalVisionEvidenceProducer:
    """Connect pixel inference to the continuous stream without inventing semantics.

    The stream invokes this producer on its delivered prefix. Candidates are
    retained atomically and replayed inputs are not inferred again. No calibrated
    instance/role/pose bridge exists yet, so infer returns None and the memory
    core remains unchanged. This is an explicit capability boundary.
    """

    def __init__(self, detector: NaturalAppearanceDetector) -> None:
        from threading import RLock

        self._detector = detector
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
                        WEIGHTS_SHA256,
                        self._detector._versions,
                        self._detector._minimum_score,
                    ),
                    "interactions": self._interactions,
                    "prefix": self._prefix,
                    "frames": self._frames,
                    "cutoff": self._cutoff,
                }
            )

    def restore_state(self, state: dict[str, Any]) -> None:
        from copy import deepcopy

        with self._lock:
            if state["scope"] != self._detector._scope:
                raise ValueError("perception restore requires a matching detector scope")
            if state["detector_binding"] != (
                WEIGHTS_SHA256,
                self._detector._versions,
                self._detector._minimum_score,
            ):
                raise ValueError("checkpoint detector configuration changed")
            self._interactions = deepcopy(state["interactions"])
            self._prefix, self._frames, self._cutoff = deepcopy(
                (state["prefix"], state["frames"], state["cutoff"])
            )

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
        groups: dict[tuple[str, str, int, int], list[VisualFrame]] = {}
        for frame in frames:
            key = (frame.sensor_id, frame.frame_id, frame.width, frame.height)
            groups.setdefault(key, []).append(frame)
        result = []
        for key, values in sorted(groups.items()):
            associator = CausalInstanceAssociator()
            previous = None
            for frame in sorted(values, key=lambda f: (f.capture_time, str(f.observation_id))):
                time = frame.capture_time.timestamp()
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
                all_frames = self._frames + frames
                interactions = self._recompute_interactions(all_frames)
                self._frames = all_frames
                self._interactions = interactions
                self._prefix, self._cutoff = prefix, when
                return None
            finally:
                self._busy = False
