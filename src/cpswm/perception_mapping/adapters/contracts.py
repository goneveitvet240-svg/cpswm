"""M05 unified observation entry contracts.

``ObservationEnvelope`` is the single robot-visible format that every device,
simulator, and offline dataset must be converted into before any downstream
M06-M10 module may read it.  It intentionally binds *identity, sensor, clock,
frame, payload, source, and oracle-channel* information together so that
cross-household, cross-session, or cross-frame mixing is caught at the boundary
rather than silently corrupting later memory.

Design rules enforced here (mirroring `技术框架_模块划分与接口_v1.1.md` §9.8):

* the envelope never carries semantic labels -- that is M10's job;
* the envelope never carries ground truth -- ``oracle_channel`` is the only
  privileged marker, and it requires an explicit authorization record;
* raw ``source_time`` is preserved; M06 time sync adds an aligned copy and
  never overwrites it.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import Field, ValidationInfo, field_validator, model_validator

from cpswm.contracts.base import (
    BaseRecordMetadata,
    ContractModel,
    SourceType,
    require_aware,
)
from cpswm.system.privacy_governance.contracts import OracleAccessDecision


class SensorModality(StrEnum):
    """One sensor modality accepted at the M05 boundary."""

    RGB = "rgb"
    DEPTH = "depth"
    POINT_CLOUD = "point_cloud"
    LIDAR = "lidar"
    IMU = "imu"
    ODOMETRY = "odometry"
    ARM_STATE = "arm_state"
    AUDIO = "audio"
    EVENT = "event"


class SensorRef(ContractModel):
    """A concrete physical or simulated sensor instance."""

    sensor_id: str = Field(min_length=1)
    modality: SensorModality


class ObservationIdentity(ContractModel):
    """The household/session/trace/observation identity of one observation.

    ``observation_id`` is the M02-scoped identity of this single observation;
    it must be unique within the household/session/trace it names.
    """

    observation_id: UUID = Field(default_factory=uuid4)
    household_id: UUID
    session_id: UUID
    trace_id: UUID


class PayloadRef(ContractModel):
    """Reference to the raw payload plus its content hash and byte size.

    The payload bytes themselves live in M03's raw store; the envelope only
    carries the reference.  ``payload_sha256`` and ``size_bytes`` are both
    re-verified on replay, so a tampered, mis-routed, or truncated payload
    cannot be silently accepted.
    """

    payload_id: UUID = Field(default_factory=uuid4)
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    payload_uri: str | None = None
    size_bytes: int = Field(ge=0)


class ObservationEnvelope(ContractModel):
    """Unified raw observation produced by M05.

    ``metadata`` reuses M01's :class:`BaseRecordMetadata`; the envelope-specific
    identity, sensor, clock, frame, and payload binding live alongside it.

    The normal perception payload and the oracle payload are *separate* fields:
    a non-oracle envelope carries ``payload`` only, while an oracle envelope
    carries ``oracle_payload`` only and an M28 decision receipt in
    ``oracle_authorization``.
    """

    metadata: BaseRecordMetadata
    identity: ObservationIdentity
    sensor: SensorRef
    capture_time: datetime
    arrival_time: datetime
    clock_domain: str = Field(min_length=1)
    frame_id: str = Field(min_length=1)
    payload: PayloadRef | None = None
    oracle_payload: PayloadRef | None = None
    oracle_channel: bool = False
    oracle_authorization: OracleAccessDecision | None = None

    @field_validator("capture_time", "arrival_time")
    @classmethod
    def validate_times_aware(cls, value: datetime, info: ValidationInfo) -> datetime:
        return require_aware(value, info.field_name or "timestamp")

    @model_validator(mode="after")
    def validate_envelope(self) -> ObservationEnvelope:
        if self.arrival_time < self.capture_time:
            raise ValueError("arrival_time must not precede capture_time")
        if self.identity.household_id != self.metadata.household_id:
            raise ValueError("observation identity household does not match metadata")
        if self.identity.session_id != self.metadata.session_id:
            raise ValueError("observation identity session does not match metadata")
        if self.identity.trace_id != self.metadata.trace_id:
            raise ValueError("observation identity trace does not match metadata")

        if self.oracle_channel:
            if self.oracle_authorization is None:
                raise ValueError("oracle_channel requires an oracle_authorization receipt")
            if self.metadata.source_type not in {SourceType.SIMULATION, SourceType.IMPORT}:
                raise ValueError(
                    "oracle-channel observations may only originate from simulation or import"
                )
            if not self.oracle_authorization.allowed:
                raise ValueError("oracle_authorization receipt is not allowed")
            if self.oracle_authorization.purpose != "evaluation_only":
                raise ValueError("oracle_authorization receipt purpose must be evaluation_only")
            if self.oracle_authorization.household_id != self.identity.household_id:
                raise ValueError("oracle_authorization household does not match observation")
            if self.oracle_payload is None:
                raise ValueError("an oracle-channel envelope requires oracle_payload")
            if self.payload is not None:
                raise ValueError("an oracle-channel envelope cannot carry a normal payload")
        else:
            if self.oracle_authorization is not None:
                raise ValueError("a non-oracle envelope cannot carry oracle_authorization")
            if self.oracle_payload is not None:
                raise ValueError("a non-oracle envelope cannot carry oracle_payload")
            if self.payload is None:
                raise ValueError("a non-oracle envelope requires a normal payload")

        if self.metadata.source_type == SourceType.SENSOR and self.oracle_channel:
            raise ValueError("a physical sensor observation cannot be an oracle channel")
        return self

    def active_payload(self) -> PayloadRef | None:
        """Return the payload that applies to this envelope's channel."""

        return self.oracle_payload if self.oracle_channel else self.payload

    def verify_payload(self, payload_bytes: bytes) -> bool:
        """Return whether ``payload_bytes`` matches the bound hash and size."""

        reference = self.active_payload()
        if reference is None:
            return False
        return (
            content_hash_bytes(payload_bytes) == reference.payload_sha256
            and len(payload_bytes) == reference.size_bytes
        )


def content_hash_bytes(value: bytes) -> str:
    """SHA-256 hex digest of raw bytes."""

    return hashlib.sha256(value).hexdigest()


__all__ = [
    "ObservationEnvelope",
    "ObservationIdentity",
    "PayloadRef",
    "SensorModality",
    "SensorRef",
]
