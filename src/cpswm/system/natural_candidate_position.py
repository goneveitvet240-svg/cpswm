"""Pixel-derived candidates in the owned single-measurement development profile.

Candidate selection is a public deterministic diagnostic rule, not world identity
inference. The original controlled association, prior and residual assumptions
remain explicit. Detector scores never become likelihoods or identity weights.
"""

from __future__ import annotations

import inspect
from datetime import datetime
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path
from typing import Any

from cpswm.data_preflight import soft_surface_position
from cpswm.perception_mapping import natural_vision, unity_rgbd
from cpswm.perception_mapping.adapters.rgbd_capture import RawModalityObservation
from cpswm.system.controlled_position_producer import _helper_code_sha256, _require, _uuid
from cpswm.system.native_joint_production import NativeJointContext
from cpswm.system.owned_position_producer import OwnedPositionProducer
from cpswm.system.reproducibility import content_sha256

NATURAL_PROFILE = "natural-candidate-single-position-raw@1"
SELECTION = "candidate-method-id-then-valid-grid-uv@1"
OBSERVATION_KEYS = (
    "measurement_id",
    "estimator",
    "estimator_pin",
    "domain_id",
    "frame_id",
    "action_id",
    "valid_at",
    "world_point_m",
)


def implementation_binding() -> str:
    return content_sha256(
        (
            sha256(Path(__file__).read_bytes()).hexdigest(),
            SELECTION,
            OBSERVATION_KEYS,
            tuple(
                (name, _helper_code_sha256(value.__code__))
                for name, value in sorted(globals().items())
                if inspect.isfunction(value) and value.__module__ == __name__
            ),
            version("torch"),
            version("torchvision"),
        )
    )


def candidate_readout(
    rows: tuple[RawModalityObservation, ...],
    *,
    cutoff: datetime,
    weights_path: Path,
    affinity_model: dict[str, Any],
    affinity_pin: str,
    estimator: str,
    raw_sha256: str,
) -> dict[str, Any]:
    """Re-infer from immutable public RGB, then retain every candidate/seed.

    No supplied boxes, scores, SDK labels, world identities or precomputed
    readouts enter this function. Empty and invalid support remain inspectable.
    """
    from cpswm.system.controlled_position_producer import packet_binding

    _require(estimator in soft_surface_position.ESTIMATORS, "unsupported position estimator")
    _require(raw_sha256 == packet_binding(rows)["raw_sha256"], "natural raw provenance differs")
    camera, depth = unity_rgbd.decode_unity_rgbd(rows, cutoff=cutoff)
    env, rgb = natural_vision.decode_rgb(rows[0], cutoff=cutoff)
    detector = natural_vision.NaturalAppearanceDetector(
        weights_path=weights_path,
        household_id=env.identity.household_id,
        session_id=env.identity.session_id,
        trace_id=env.identity.trace_id,
    )
    frame = detector.infer(rows[0], cutoff=cutoff)
    candidates = [
        dict(method=frame.model_id, id=str(c.candidate_id), box=list(c.box_xyxy))
        for c in frame.candidates
    ]
    payloads = [r.envelope().payload for r in rows]
    _require(all(p is not None for p in payloads), "raw candidate payload missing")
    result = soft_surface_position.readout_frame(
        rgb,
        depth,
        camera,
        candidates,
        affinity_model,
        affinity_pin,
        provenance=dict(
            source_sha256=raw_sha256,
            receipt_sha256=rows[0].capture_receipt_sha256,
            observation_ids=[str(r.envelope().identity.observation_id) for r in rows],
            payload_sha256=[p.payload_sha256 for p in payloads if p is not None],
        ),
    )
    selected = None
    for candidate in result["candidates"]:
        eligible = [
            s
            for s in result["seeds"]
            if s["valid"]
            and any(
                (p["method"], p["id"]) == (candidate["method"], candidate["id"])
                for p in s["sources"]
            )
        ]
        if eligible:
            seed = min(eligible, key=lambda s: tuple(s["pixel_uv"]))
            observation = next(
                o
                for o in result["observations"]
                if o["seed_id"] == seed["seed_id"] and o["estimator"] == estimator
            )
            selected = dict(
                candidate=candidate,
                seed_uv=seed["pixel_uv"],
                observation={k: observation[k] for k in OBSERVATION_KEYS},
            )
            break
    return dict(
        frame=frame,
        surface=result,
        selected=selected,
        selection_rule=SELECTION,
        unavailable_reason=None
        if selected is not None
        else "no_detection_candidates"
        if not candidates
        else "no_valid_candidate_depth",
        identity_status="UNRESOLVED",
        association_assumption="CONTROLLED_HYPOTHESIS_ONLY",
        detector_scores_used_as_density=False,
        private_labels_used=False,
    )


class NaturalCandidatePositionProducer(OwnedPositionProducer):
    """Same transaction/density contract, natural public box/seed reconstruction."""

    def _validate_configuration(self) -> None:
        c = self.configuration
        _require(
            type(c) is dict
            and set(c) == {"semantic_record_id", "enabled", "weights_path"}
            and _uuid(c["semantic_record_id"])
            and type(c["enabled"]) is bool
            and type(c["weights_path"]) is str
            and Path(c["weights_path"]).is_absolute(),
            "natural candidate profile requires semantic source and local pinned weights",
        )

    def _content_binding(self) -> str:
        path = Path(self.configuration["weights_path"])
        digest = sha256(path.read_bytes()).hexdigest()
        _require(digest == natural_vision.WEIGHTS_SHA256, "natural detector weights differ")
        return content_sha256(
            (NATURAL_PROFILE, super()._content_binding(), implementation_binding(), digest)
        )

    def _observation_and_diagnostic(
        self, context: NativeJointContext
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        from cpswm.system.controlled_position_producer import packet_binding

        expected = self._packet(context)
        lookup = {str(r.envelope().identity.observation_id): r for r in context.visible_prefix}
        _require(len(lookup) == len(context.visible_prefix), "duplicate visible raw identity")
        _require(all(key in lookup for key in expected["observation_ids"]), "bound packet missing")
        rows = tuple(lookup[key] for key in expected["observation_ids"])
        _require(packet_binding(rows) == expected, "bound packet differs")
        camera, _ = unity_rgbd.decode_unity_rgbd(rows, cutoff=context.cutoff)
        self._validate_packet_epoch(context, camera, rows, expected)
        result = candidate_readout(
            rows,
            cutoff=context.cutoff,
            weights_path=Path(self.configuration["weights_path"]),
            affinity_model=self.affinity_model,
            affinity_pin=self.affinity_pin,
            estimator=self.position_model["estimator"],
            raw_sha256=expected["raw_sha256"],
        )
        selected = result["selected"]
        _require(
            selected is not None, f"natural position unavailable: {result['unavailable_reason']}"
        )
        return selected["observation"], dict(natural_candidates=result)
