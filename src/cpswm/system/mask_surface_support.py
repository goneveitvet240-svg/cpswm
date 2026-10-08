"""Owned reversible surface support, without fictitious object-centre factors.

The existing semantic hypotheses remain conditional. Public masked features form
an explicitly set-valued observation state; new views never imply independent
position precision, and mask scores never become Bayesian identity likelihoods.
The owner journals raw captures; canonical replay reconstructs the support set.
"""

from __future__ import annotations

import inspect
import json
from datetime import datetime
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import UUID

from cpswm.perception_mapping import (
    appearance_geometry_association,
    mask_surface_sequence,
    natural_mask_surface,
    surface_action_model,
)
from cpswm.perception_mapping.adapters.rgbd_capture import RawModalityObservation
from cpswm.perception_mapping.mask_surface_sequence import MaskSurfaceSequence
from cpswm.perception_mapping.natural_mask_surface import NaturalMaskSurfaceDetector
from cpswm.perception_mapping.unity_rgbd import decode_unity_rgbd
from cpswm.system.controlled_position_producer import _helper_code_sha256, _require, packet_binding
from cpswm.system.native_joint_production import NativeJointContext
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_conditional_updates import ConditionalMeasurement
from cpswm.system.structure_two_particle_workspace import ConditionalAnalyticState
from cpswm.system.temporal_target_position import TemporalTargetPositionProducer

PROFILE = "owned-mask-surface-support-raw@1"


class MaskSurfaceSupportProducer(TemporalTargetPositionProducer):
    profile_id = PROFILE

    def _validate_configuration(self) -> None:
        c = self.configuration
        _require(type(c) is dict and "mask_weights_path" in c, "mask checkpoint required")
        _require(
            type(c["mask_weights_path"]) is str and Path(c["mask_weights_path"]).is_absolute(),
            "absolute mask checkpoint required",
        )
        from cpswm.system.surface_episode import policy_configuration

        policy_configuration(c["pipeline"])
        self.configuration = {
            k: v for k, v in c.items() if k not in ("mask_weights_path", "pipeline")
        }
        try:
            super()._validate_configuration()
        finally:
            self.configuration = c

    def _content_binding(self) -> str:
        pin = sha256(Path(self.configuration["mask_weights_path"]).read_bytes()).hexdigest()
        _require(pin == NaturalMaskSurfaceDetector.weights_sha256, "mask checkpoint differs")
        from cpswm.perception_mapping import natural_vision, unity_rgbd, visual_target_tracking
        from cpswm.system import surface_episode

        _require(
            MaskSurfaceSequence is mask_surface_sequence.MaskSurfaceSequence
            and NaturalMaskSurfaceDetector is natural_mask_surface.NaturalMaskSurfaceDetector
            and vars(mask_surface_sequence)["NaturalMaskSurfaceDetector"]
            is NaturalMaskSurfaceDetector
            and vars(mask_surface_sequence)["select_surface"] is natural_mask_surface.select_surface
            and vars(mask_surface_sequence)["InitializedPixelTargetTracker"]
            is visual_target_tracking.InitializedPixelTargetTracker
            and vars(mask_surface_sequence)["decode_rgb"] is natural_vision.decode_rgb
            and vars(mask_surface_sequence)["decode_unity_rgbd"] is unity_rgbd.decode_unity_rgbd
            and vars(mask_surface_sequence)["appearance_geometry_association"]
            is appearance_geometry_association
            and decode_unity_rgbd is unity_rgbd.decode_unity_rgbd,
            "surface helper alias changed",
        )
        modules = (
            appearance_geometry_association,
            mask_surface_sequence,
            natural_mask_surface,
            surface_episode,
            surface_action_model,
        )
        bodies: list[tuple[str, ...]] = []
        for module in modules:
            for name, value in sorted(vars(module).items()):
                if inspect.isfunction(value):
                    bodies.append((module.__name__, name, _helper_code_sha256(value.__code__)))
                elif inspect.isclass(value) and value.__module__ == module.__name__:
                    for key, item in sorted(vars(value).items()):
                        body = (
                            item.fget
                            if isinstance(item, property)
                            else (
                                item.__func__
                                if isinstance(item, (staticmethod, classmethod))
                                else item
                            )
                        )
                        if inspect.isfunction(body):
                            bodies.append(
                                (module.__name__, name, key, _helper_code_sha256(body.__code__))
                            )
        return content_sha256(
            (
                PROFILE,
                super()._content_binding(),
                pin,
                bodies,
                mask_surface_sequence.MINIMUM_POINTS,
                natural_mask_surface.MASK_THRESHOLD,
                _helper_code_sha256(inspect.unwrap(_infer_prefix).__code__),
                tuple(
                    (m.__name__, sha256(Path(str(m.__file__)).read_bytes()).hexdigest())
                    for m in (
                        appearance_geometry_association,
                        mask_surface_sequence,
                        natural_mask_surface,
                        surface_episode,
                        surface_action_model,
                    )
                ),
                sha256(Path(__file__).read_bytes()).hexdigest(),
            )
        )

    def _sequence(self, context: NativeJointContext) -> dict[str, Any]:
        update = context.observation_update
        assert update is not None
        captures = [*getattr(self, "_captures", []), update]
        _require(
            len({c.logical_key for c in captures}) == len(captures), "capture already consumed"
        )
        _require(
            all(c.semantic_revision_id == update.semantic_revision_id for c in captures),
            "surface sequence crosses semantic revision",
        )
        lookup = {str(r.envelope().identity.observation_id): r for r in context.visible_prefix}
        _require(len(lookup) == len(context.visible_prefix), "duplicate raw identity")
        frames = []
        for capture in captures:
            keys = capture.packet["observation_ids"]
            _require(all(k in lookup for k in keys), "surface raw prefix missing")
            rows = tuple(lookup[k] for k in keys)
            _require(packet_binding(rows) == capture.packet, "surface packet differs")
            camera, _ = decode_unity_rgbd(rows, cutoff=capture.received_at)
            _require(
                capture.decision_time <= camera.capture_time <= capture.received_at,
                "surface capture epoch differs",
            )
            frames.append((rows, capture.received_at, str(capture.action_id)))
        result = json.loads(
            _infer_prefix(
                self.configuration["mask_weights_path"], self.binding_sha256, tuple(frames)
            )
        )
        result["captures"] = captures
        return dict(result)

    def _condition_observation(
        self,
        sequence: dict[str, Any],
        key: str,
        prior: ConditionalAnalyticState,
        cluster: UUID,
        record_id: UUID,
    ) -> tuple[ConditionalMeasurement, dict[str, Any]]:
        # Physical support is journalled and replayed, not fed into the inherited
        # static-centre Gaussian. Neither repeated nor distinct features increase
        # object-centre confidence without an explicitly fitted observation model.
        return self._neutral(prior, cluster, record_id), dict(
            model=PROFILE,
            log_ratio=0.0,
            position_information_added=False,
            observations=sequence["history"][key],
            semantics="correlated-surface-support-set; no-centre-likelihood",
        )


# Pure process-local memoization: immutable authenticated raw packets in,
# immutable JSON out. No checkpoint/import can preload derived observations.
# A fresh process starts empty; source/model bindings are part of every key.
_Frame = tuple[tuple[RawModalityObservation, ...], datetime, str]


@lru_cache(maxsize=8)
def _infer_prefix(weights_path: str, implementation: str, frames: tuple[_Frame, ...]) -> str:
    sequence = None
    records = []
    history: dict[str, list[dict[str, Any]]] = {}
    signatures: dict[str, set[str]] = {}
    for rows, cutoff, action_id in frames:
        keys = [str(r.envelope().identity.observation_id) for r in rows]
        camera, _ = decode_unity_rgbd(rows, cutoff=cutoff)
        if sequence is None:
            identity = rows[0].envelope().identity
            sequence = MaskSurfaceSequence(
                NaturalMaskSurfaceDetector(
                    weights_path=Path(weights_path),
                    household_id=identity.household_id,
                    session_id=identity.session_id,
                    trace_id=identity.trace_id,
                )
            )
        record, _ = sequence.observe(rows, cutoff=cutoff)
        signature = content_sha256(
            camera.model_dump(mode="json", exclude={"action_id", "capture_time"})
        )
        current = {}
        for track in record["tracks"]:
            anchor = track["anchor_id"]
            history.setdefault(anchor, [])
            signatures.setdefault(anchor, set())
            observation = None
            if track["world_point_m"] is not None and signature not in signatures[anchor]:
                observation = dict(
                    anchor_id=anchor,
                    action_id=action_id,
                    observation_ids=keys,
                    feature_ids=track["selected_feature_ids"],
                    pixel_uv=track["selected_pixel_uv"],
                    world_point_m=track["world_point_m"],
                    sensor_signature=signature,
                    valid_at=camera.capture_time.isoformat(),
                )
                history[anchor].append(observation)
                signatures[anchor].add(signature)
            current[anchor] = observation
        record["new_surface_observations"] = current
        record["unique_surface_counts"] = {k: len(v) for k, v in history.items()}
        record["independent_evidence_count"] = None
        records.append(record)
    return json.dumps(
        dict(records=records, history=history, current=current), sort_keys=True, allow_nan=False
    )
