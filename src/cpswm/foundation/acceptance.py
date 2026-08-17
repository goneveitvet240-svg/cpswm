"""Deterministic Step 1 acceptance handler used by restart replay tests."""

from __future__ import annotations

from datetime import datetime

from cpswm.contracts import BaseRecordMetadata, ContractModel, SourceType

from .identity_time_frames import FrameRegistry, FrameTransform, Vector3
from .runtime_orchestration import ExecutionContext, HandlerOutput, RuntimeMessage


class AlignedPointRecord(ContractModel):
    metadata: BaseRecordMetadata
    source_frame_id: str
    target_frame_id: str
    point: Vector3
    transform_version: str


class AlignmentHandler:
    """Register a supplied M02 transform and align one observed point."""

    def __init__(self) -> None:
        self.frames = FrameRegistry()

    def __call__(self, message: RuntimeMessage, context: ExecutionContext) -> HandlerOutput:
        if not isinstance(message.payload, dict):
            raise ValueError("alignment message payload must be an object")
        transform = FrameTransform.model_validate(message.payload["transform"])
        if transform.household_id != message.household_id:
            raise ValueError("alignment transform belongs to another household")
        self.frames.register(transform)
        observed_time = datetime.fromisoformat(str(message.payload["observed_time"]))
        resolved = self.frames.lookup(
            source_frame_id=str(message.payload["source_frame_id"]),
            target_frame_id=str(message.payload["target_frame_id"]),
            household_id=message.household_id,
            at_time=observed_time,
        )
        point = self.frames.transform_point(
            Vector3.model_validate(message.payload["point"]), resolved
        )
        record = AlignedPointRecord(
            metadata=BaseRecordMetadata(
                record_id=context.deterministic_uuid("aligned-point"),
                schema_name="cpswm.AlignedPointRecord",
                schema_version=message.schema_version,
                household_id=message.household_id,
                session_id=message.session_id,
                recorded_time=context.now,
                source_type=SourceType.MODEL,
                source_id=context.handler_name,
                trace_id=message.trace_id,
            ),
            source_frame_id=resolved.source_frame_id,
            target_frame_id=resolved.target_frame_id,
            point=point,
            transform_version=resolved.transform_version,
        )
        return HandlerOutput(records=(record,))
