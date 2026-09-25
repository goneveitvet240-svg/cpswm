"""Configured joint proposal production at the continuous collection boundary.

The dependency receives detached live evidence/ancestry, never a mutable core.
It must supply its selected full-axis kernel and calibrated conditional models.
No default priors, marginal products, neural weights or semantic truth are made
up here. Its declared artifact identity is not independent trust or calibration.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Any, Protocol
from uuid import UUID

from cpswm.perception_mapping.adapters.rgbd_capture import RawModalityObservation
from cpswm.system.evaluation_operations.structure_two_selected_method import (
    ParticleRevisionBatch,
    ParticleRevisionReceipt,
)
from cpswm.system.structure_two_particle_workspace import (
    ConditionalAnalyticState,
    NativeParticleRecord,
    NativePosteriorSource,
    native_content_sha256,
)


@dataclass(frozen=True)
class NativeJointContext:
    source: NativePosteriorSource
    previous_batch: ParticleRevisionBatch | None
    records: tuple[NativeParticleRecord, ...]
    ledger_head_sha256: str
    visible_prefix: tuple[RawModalityObservation, ...]
    cutoff: datetime

    @property
    def content_sha256(self) -> str:
        return native_content_sha256(
            (
                self.source,
                self.previous_batch,
                self.records,
                self.ledger_head_sha256,
                tuple(
                    (
                        raw.envelope_json,
                        raw.capture_receipt_sha256,
                        sha256(raw.payload_bytes).hexdigest(),
                        raw.depth_unit,
                    )
                    for raw in self.visible_prefix
                ),
                self.cutoff,
            )
        )


@dataclass(frozen=True)
class ProducedJointCandidates:
    context_sha256: str
    source_posterior_id: UUID
    source_body_sha256: str
    dependency_sha256: str
    receipts: tuple[ParticleRevisionReceipt, ...]
    statistics: dict[UUID, ConditionalAnalyticState]
    unresolved_log_weight: float


class NativeJointProducer(Protocol):
    """Stateful inference dependency; must not execute external actions.

    Binding covers model/kernel/calibration artifacts, not mutable RNG state.
    Checkpoint/restore must preserve that RNG and all inference history. Returned
    values pass the existing native source/statistic/ancestry checks before use.
    The existing prepared-candidate consumer still rejects unbound selected
    neural artifacts; this protocol does not remove or replace that restriction.
    """

    @property
    def binding_sha256(self) -> str: ...

    def produce(self, context: NativeJointContext) -> ProducedJointCandidates: ...

    def checkpoint_state(self) -> dict[str, Any]: ...

    def restore_state(self, state: dict[str, Any]) -> None: ...


def producer_binding(producer: NativeJointProducer | None) -> str | None:
    if producer is None:
        return None
    value = producer.binding_sha256
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise ValueError("joint producer requires a SHA256 dependency binding")
    return value


def producer_implementation_binding(producer: NativeJointProducer | None) -> str | None:
    """Pin actual Python implementations as well as the declared artifact hash.

    This detects a changed factory/callable at recovery and inference. It is not
    evidence that a model's measurements are true or that its declared external
    weights/calibration artifacts have independent custody.
    """
    import inspect
    from pathlib import Path
    from types import CodeType

    from cpswm.system.structure_two_execution import _code_object_sha256

    if producer is None:
        return None
    cls = type(producer)
    class_path = inspect.getsourcefile(cls)
    if class_path is None:
        raise ValueError("joint producer implementation has no inspectable class source")
    methods = []
    for name in ("produce", "checkpoint_state", "restore_state"):
        method = getattr(producer, name, None)
        declared = next((vars(c)[name] for c in cls.__mro__ if name in vars(c)), None)
        if (
            name in getattr(producer, "__dict__", {})
            or not inspect.ismethod(method)
            or method.__self__ is not producer
            or method.__func__ is not declared
        ):
            raise ValueError("joint producer implementation must use declared instance methods")
        code = getattr(method.__func__, "__code__", None)
        path = inspect.getsourcefile(method.__func__)
        if not isinstance(code, CodeType) or path is None:
            raise ValueError("joint producer implementation has no inspectable loaded code")
        methods.append(
            (
                name,
                method.__func__.__module__,
                method.__func__.__qualname__,
                sha256(Path(path).read_bytes()).hexdigest(),
                _code_object_sha256(code),
            )
        )
    return native_content_sha256(
        (
            "joint-producer-implementation@1",
            cls.__module__,
            cls.__qualname__,
            sha256(Path(class_path).read_bytes()).hexdigest(),
            tuple(methods),
        )
    )
