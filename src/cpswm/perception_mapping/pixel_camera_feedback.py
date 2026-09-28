"""Uncalibrated RGB category measurements for explicitly configured camera models.

This maps a detector's output to a measurement alphabet, never to object-instance
identity, reliable physical absence, hand contact, person roles or memory rights.
"""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from pathlib import Path
from uuid import UUID

from cpswm.data_preflight.typed_proposal_networks import architecture_fingerprint
from cpswm.perception_mapping.adapters.rgbd_capture import RawModalityObservation
from cpswm.perception_mapping.natural_vision import NaturalAppearanceDetector, VisualFrame
from cpswm.system.joint_camera_policy import CameraModelSources
from cpswm.system.native_joint_production import python_dependency_implementation_binding
from cpswm.system.reproducibility import content_sha256


class PixelCategoryOutcomeDecoder:
    """Pinned SSDLite inference, using the existing default development threshold."""

    def __init__(
        self,
        *,
        weights_path: Path,
        household_id: UUID,
        session_id: UUID,
        trace_id: UUID,
        category: str,
        sources: CameraModelSources,
    ) -> None:
        self._detector = NaturalAppearanceDetector(
            weights_path=weights_path,
            household_id=household_id,
            session_id=session_id,
            trace_id=trace_id,
        )
        if category not in self._detector._categories:
            raise ValueError("requested camera category is not in the detector label space")
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
        return digest.hexdigest()

    def _configuration_digest(self) -> str:
        return content_sha256(
            (
                "pixel-category-camera-measurement@1",
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
                tuple(
                    (key, getattr(self._detector._model, key))
                    for key in (
                        "score_thresh",
                        "nms_thresh",
                        "detections_per_img",
                        "topk_candidates",
                    )
                ),
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
        frames = tuple(self._detector.infer(x, cutoff=cutoff) for x in observations)
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
