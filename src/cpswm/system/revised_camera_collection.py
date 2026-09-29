"""Explicit source-revision recovery followed by ordinary model-selected collection.

Only already accepted semantic corrections can trigger replay here. Pixel labels
never become retraction evidence. Replay is durable before external execution;
its receipt describes local state transitions, not empirical task success.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from cpswm.system.continuous_camera_collection import (
    CollectionStep,
    ContinuousCameraModel,
    collect_posterior_step,
)
from cpswm.system.joint_camera_policy import CameraModelSources
from cpswm.system.structure_two_continuous_input import (
    ContinuousEvidenceInput,
    ObservationExecutor,
    _utc,
)
from cpswm.system.structure_two_particle_workspace import native_content_sha256


@dataclass(frozen=True)
class RevisedCollectionStep:
    collection: CollectionStep
    replayed: bool
    invalidated_revisions: tuple[UUID, ...]
    previous_runtime_id: UUID
    current_runtime_id: UUID
    ledger_before_replay_sha256: str
    ledger_after_replay_sha256: str
    cancelled_command_ids: tuple[UUID, ...]


def collect_revised_posterior_step(
    stream: ContinuousEvidenceInput,
    *,
    model: ContinuousCameraModel,
    executor: ObservationExecutor,
    decision_time: datetime,
) -> RevisedCollectionStep:
    """Reconcile a valid source invalidation, then continue the same action history.

    External effects with uncertain outcomes must be reconciled by their owner
    first. A past decision time or changed measurement model fails before replay.
    Stale READY commands are cancelled by replay, never retargeted or dispatched.
    Other replay/production errors propagate; there is no reset or scan fallback.
    """
    with stream._lock, stream._system.core._execution_lock:
        when = _utc(decision_time)
        if stream._execution_lane != "registered_p5_first":
            raise ValueError("revised collection requires registered P5-first")
        stream._require_resolved_dispatches()
        if any(t is not None and when < t for t in (stream._last_arrival, stream._last_cutoff)):
            raise ValueError("revised decision predates delivered evidence")
        sources = CameraModelSources.model_validate(model.sources.model_dump())
        stream._check_observation_decoder()
        if (
            stream._observation_decoder is not None
            and sources != stream._observation_decoder.sources
        ):
            raise ValueError("revised collection measurement model sources changed")
        core = stream._system.core
        old_runtime = core._particle_workspace.runtime_id
        invalidated = tuple(sorted(core._particle_workspace.invalidated_revisions, key=str))
        ready = {key for key, status in stream._observation_status.items() if status == "READY"}
        ledger_before = native_content_sha256(core._hybrid_loop.ledger.export_state())
        if invalidated:
            stream.replay_joint_posterior()
        current_runtime = core._particle_workspace.runtime_id
        ledger_after = native_content_sha256(core._hybrid_loop.ledger.export_state())
        if ledger_before != ledger_after:
            raise ValueError("joint replay changed the semantic ledger")
        cancelled = tuple(
            sorted(
                (
                    key
                    for key in ready
                    if stream._observation_status[key] == "CANCELLED_STALE_JOINT"
                ),
                key=str,
            )
        )
        result = collect_posterior_step(stream, model=model, executor=executor, decision_time=when)
        return RevisedCollectionStep(
            result,
            bool(invalidated),
            invalidated,
            old_runtime,
            current_runtime,
            ledger_before,
            ledger_after,
            cancelled,
        )
