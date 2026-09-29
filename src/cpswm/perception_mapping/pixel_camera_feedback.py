"""Uncalibrated RGB category measurements for explicitly configured camera models.

This maps a detector's output to a measurement alphabet, never to object-instance
identity, reliable physical absence, hand contact, person roles or memory rights.
"""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from cpswm.data_preflight.typed_proposal_networks import architecture_fingerprint
from cpswm.perception_mapping.adapters.rgbd_capture import RawModalityObservation
from cpswm.perception_mapping.natural_vision import (
    FasterNaturalAppearanceDetector,
    NaturalAppearanceDetector,
    VisualFrame,
)
from cpswm.perception_mapping.unity_rgbd import public_rgb_observations
from cpswm.system.joint_camera_policy import CameraModelSources
from cpswm.system.native_joint_production import python_dependency_implementation_binding
from cpswm.system.reproducibility import content_sha256


class PixelCategoryOutcomeDecoder:
    """Explicit pinned detector, using its existing default development threshold."""

    def __init__(
        self,
        *,
        weights_path: Path,
        household_id: UUID,
        session_id: UUID,
        trace_id: UUID,
        category: str,
        sources: CameraModelSources,
        detector_kind: Literal["ssdlite", "fasterrcnn"] = "ssdlite",
    ) -> None:
        classes = {
            "ssdlite": NaturalAppearanceDetector,
            "fasterrcnn": FasterNaturalAppearanceDetector,
        }
        if detector_kind not in classes:
            raise ValueError("explicit supported pixel detector required")
        self.detector_kind = detector_kind
        self._detector = classes[detector_kind](
            weights_path=weights_path,
            household_id=household_id,
            session_id=session_id,
            trace_id=trace_id,
        )
        if category not in self._detector._categories:
            raise ValueError("requested camera category is not in the detector label space")
        if detector_kind == "fasterrcnn":
            # Torchvision creates ROI pyramid scales and LevelMapper lazily.
            # Initialize deterministic geometry before freezing, not on a
            # supplied observation. The black tensor provides no evidence.
            torch = self._detector._torch
            with torch.inference_mode():
                self._detector._model([torch.zeros(3, 320, 320)])
        self.category = category
        self.sources = CameraModelSources.model_validate(sources.model_dump())
        self._parameters = self._model_fingerprint()
        self._implementation = python_dependency_implementation_binding(
            self._detector, required_methods=("infer",)
        )
        self._configuration = self._configuration_digest()

    def _model_fingerprint(self) -> str:
        import torch

        digest = sha256()
        digest.update(architecture_fingerprint(self._detector._model).encode())
        for name, value in self._detector._model.state_dict().items():
            digest.update(
                content_sha256(
                    (name, str(value.dtype), tuple(value.shape), str(value.device))
                ).encode()
            )
            digest.update(
                value.detach().contiguous().reshape(-1).view(torch.uint8).cpu().numpy().tobytes()
            )
        for name, module in self._detector._model.named_modules():
            for index, value in enumerate(getattr(module, "cell_anchors", ())):
                digest.update(
                    content_sha256((name, index, str(value.dtype), tuple(value.shape))).encode()
                )
                digest.update(
                    value.detach()
                    .contiguous()
                    .reshape(-1)
                    .view(torch.uint8)
                    .cpu()
                    .numpy()
                    .tobytes()
                )
        return digest.hexdigest()

    def _configuration_digest(self) -> str:
        # Include native detection/resize/RPN/ROI settings and CNN geometry, not
        # only weights. Values are primitive configuration, never model outputs.
        omitted = object()

        def plain(value: Any) -> Any:
            if value is None or type(value) in (str, int, float, bool):
                return value
            if type(value) in (tuple, list):
                items = [plain(v) for v in value]
                return omitted if any(v is omitted for v in items) else items
            if type(value) is dict and all(type(k) in (str, int) for k in value):
                mapped = {str(k): plain(v) for k, v in value.items()}
                return omitted if any(v is omitted for v in mapped.values()) else mapped
            return omitted

        settings = {}
        for name, module in self._detector._model.named_modules():
            values = {k: plain(v) for k, v in vars(module).items()}
            settings[name] = {k: v for k, v in values.items() if v is not omitted}
            for helper in ("box_coder", "proposal_matcher", "fg_bg_sampler", "map_levels"):
                item = getattr(module, helper, None)
                if item is not None:
                    values = {k: plain(v) for k, v in vars(item).items()}
                    settings[name + ":" + helper] = {
                        k: v for k, v in values.items() if v is not omitted
                    }
        return content_sha256(
            (
                "pixel-category-camera-measurement@2",
                self.detector_kind,
                self._detector.model_id,
                self._detector.weights_sha256,
                self._detector._versions,
                self._detector._torch.get_num_threads(),
                self._detector._torch.get_num_interop_threads(),
                self._detector._torch.are_deterministic_algorithms_enabled(),
                self._detector._torch.get_float32_matmul_precision(),
                self._detector._scope,
                self._detector._minimum_score,
                self._detector._categories,
                settings,
                self.category,
                self.sources,
            )
        )

    @property
    def binding_sha256(self) -> str:
        if (
            self._configuration_digest() != self._configuration
            or self._model_fingerprint() != self._parameters
            or any(m.training for m in self._detector._model.modules())
            or python_dependency_implementation_binding(self._detector, required_methods=("infer",))
            != self._implementation
        ):
            raise ValueError("pixel camera decoder weights, code or configuration changed")
        return content_sha256((self._configuration, self._implementation, self._parameters))

    def measurements(
        self, observations: tuple[RawModalityObservation, ...], *, cutoff: datetime
    ) -> tuple[VisualFrame, ...]:
        _ = self.binding_sha256
        from cpswm.perception_mapping import unity_rgbd

        if public_rgb_observations is not unity_rgbd.public_rgb_observations:
            raise ValueError("pixel camera modality adapter changed")
        pixels = public_rgb_observations(observations, cutoff=cutoff)
        frames = tuple(self._detector.infer(x, cutoff=cutoff) for x in pixels)
        _ = self.binding_sha256
        return frames

    def decode(
        self, observations: tuple[RawModalityObservation, ...], *, cutoff: datetime
    ) -> str | None:
        if not observations:
            return None
        frames = self.measurements(observations, cutoff=cutoff)
        detected = any(c.category == self.category for frame in frames for c in frame.candidates)
        return "category_candidate" if detected else "no_category_candidate"
