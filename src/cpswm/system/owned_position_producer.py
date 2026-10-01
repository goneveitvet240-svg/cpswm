"""Explicit single owner-issued measurement development profile, neutral semantics.

Uses the existing declared controlled identity, Gaussian prior, readout and
unknown density. A second measurement is unsupported, not assumed independent.
The exact canonical class is registered with complete raw-base reconstruction.
"""

from __future__ import annotations

from copy import deepcopy
from math import isfinite
from typing import Any
from uuid import UUID

from cpswm.data_preflight import instance_affinity
from cpswm.perception_mapping import position_observation_model as position
from cpswm.system.controlled_position_producer import (
    ControlledPositionProducer,
    _require,
    _uuid,
    implementation_binding,
)
from cpswm.system.native_joint_production import (
    NativeJointContext,
    NativeObservationUpdate,
    ProducedJointCandidates,
)
from cpswm.system.reproducibility import content_sha256, content_uuid

PROFILE = "owned-single-position-raw@1"


class OwnedPositionProducer(ControlledPositionProducer):
    def __init__(
        self,
        *,
        configuration: dict[str, Any],
        affinity_model: dict[str, Any],
        affinity_pin: str,
        position_model: dict[str, Any],
        position_pin: str,
    ) -> None:
        self.configuration = deepcopy(configuration)
        self.affinity_model = instance_affinity.restore(affinity_model, affinity_pin)
        self.affinity_pin = affinity_pin
        self.position_model = position.restore(position_model, position_pin)
        self.position_pin = position_pin
        self._implementation = implementation_binding()
        self._validate_configuration()
        self._binding = self._content_binding()
        self.calls = 0
        self.consumed_keys: list[str] = []
        self.last_diagnostic: dict[str, Any] | None = None

    def _validate_configuration(self) -> None:
        c = self.configuration
        _require(
            type(c) is dict
            and set(c) == {"semantic_record_id", "candidate", "seed_uv", "enabled"}
            and _uuid(c["semantic_record_id"])
            and type(c["enabled"]) is bool,
            "invalid owned position configuration",
        )
        seed, candidate = c["seed_uv"], c["candidate"]
        _require(
            type(seed) is list
            and len(seed) == 2
            and all(type(v) is int and v >= 0 for v in seed)
            and type(candidate) is dict
            and set(candidate) == {"method", "id", "box"}
            and type(candidate["method"]) is str
            and bool(candidate["method"])
            and _uuid(candidate["id"])
            and type(candidate["box"]) is list
            and len(candidate["box"]) == 4
            and all(type(v) is float and isfinite(v) for v in candidate["box"]),
            "one declared controlled candidate and public seed required",
        )

    def _content_binding(self) -> str:
        from cpswm.system.owned_position_update import implementation_binding as owner_binding

        return content_sha256((PROFILE, super()._content_binding(), owner_binding()))

    def _active(self, context: NativeJointContext) -> bool:
        return context.observation_update is not None and bool(self.configuration["enabled"])

    def _packet(self, context: NativeJointContext) -> dict[str, Any]:
        update = context.observation_update
        _require(type(update) is NativeObservationUpdate, "owned observation context required")
        assert update is not None
        return update.packet

    def _position_record_ids(self, context: NativeJointContext) -> tuple[UUID, ...]:
        return tuple(UUID(v) for v in self._packet(context)["observation_ids"])

    def _cluster(self, context: NativeJointContext, binding: str) -> UUID:
        update = context.observation_update
        return content_uuid(
            PROFILE,
            (
                context.source.source_id,
                binding,
                "semantic" if update is None else update.logical_key,
            ),
        )

    def _validate_packet_epoch(
        self, context: NativeJointContext, camera: Any, rows: Any, expected: dict[str, Any]
    ) -> None:
        update = context.observation_update
        assert update is not None
        meta = context.source.transition.after.metadata
        _require(
            expected["scope"] == [str(meta.household_id), str(meta.session_id), str(meta.trace_id)]
            and camera.action_id == update.action_id
            and update.decision_time <= camera.capture_time <= update.received_at
            and update.received_at == context.cutoff
            and all(row.envelope().arrival_time <= update.received_at for row in rows),
            "owned packet outside command scope or historical cutoff",
        )

    def produce(self, context: NativeJointContext) -> ProducedJointCandidates:
        update = context.observation_update
        if update is not None:
            _require(
                type(update) is NativeObservationUpdate
                and self._selected(context.source)
                and update.semantic_revision_id == context.source.history_after.latest.revision_id
                and context.previous_batch is not None,
                "observation update requires its selected live semantic source and actual parent",
            )
        return super().produce(context)

    def recompute_updates(
        self, context: NativeJointContext, predecessors: tuple[NativeJointContext, ...]
    ) -> ProducedJointCandidates:
        _require(self.calls == 0 and not self.consumed_keys, "verifier must start fresh")
        prior = [c.observation_update for c in predecessors if c.observation_update is not None]
        _require(len(prior) <= 1, "single measurement profile has duplicate ancestry")
        _require(
            not prior or context.observation_update is None,
            "second measurement is unsupported by the single measurement profile",
        )
        if prior and self.configuration["enabled"]:
            self.consumed_keys = [self._measurement_key()]
        return self.produce(context)
