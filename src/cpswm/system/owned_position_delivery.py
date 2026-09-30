"""Read-only current-owner RGB-D descriptions, never new consumption authority.

Only the first modeled command based on the still-current native base is covered.
Changed source/batch/generation and feedback-conditioned priors are stale here.
The trusted boundary is the original owner journal: replacing that entire journal
is not authenticated by a detached descriptor. No sensor action, posterior update,
new durable format, candidate selection or natural instance identity is added.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel

from cpswm.contracts.base import require_aware
from cpswm.perception_mapping.adapters.rgbd_capture import RawModalityObservation
from cpswm.perception_mapping.unity_rgbd import (
    CameraSelfPose,
    decode_unity_rgbd,
    implementation_binding,
)
from cpswm.system.joint_camera_policy import JointCameraProblem
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_continuous_input import (
    ContinuousEvidenceInput,
    ObservationCommand,
    ObservationDelivery,
)
from cpswm.system.structure_two_particle_workspace import native_content_sha256


@dataclass(frozen=True)
class RGBDMemberDescription:
    observation_id: UUID
    envelope_json: str
    payload_sha256: str
    payload_size: int
    capture_receipt_sha256: str
    depth_unit: str | None
    archive_sampling_json: str | None


@dataclass(frozen=True)
class CurrentOwnedRGBDDescriptor:
    schema: str
    action_id: UUID
    scope: tuple[UUID, UUID, UUID]
    command_sha256: str
    delivery_sha256: str
    decision_time: datetime
    received_at: datetime
    members: tuple[RGBDMemberDescription, ...]
    camera: CameraSelfPose
    native_origin_sha256: str
    runtime_id: UUID
    snapshot_id: UUID
    evidence_cluster_id: UUID
    source_id: UUID
    source_body_sha256: str
    semantic_revision_id: UUID
    parent_batch_sha256: str
    parent_input_sha256: str
    previous_weight_evidence_sha256: str
    parent_log_weights: tuple[tuple[UUID, float], ...]
    aggregate_log_weight: float
    decoder_binding_sha256: str
    implementation_sha256: str
    posterior_updated: bool = False
    consumption_authority: bool = False

    @property
    def content_sha256(self) -> str:
        return content_sha256(self)


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _same_typed(left, right):
    """Reject bool/int, tuple/list and subclass substitutions before equality."""
    if type(left) is not type(right):
        return False
    if is_dataclass(left):
        return all(_same_typed(getattr(left, f.name), getattr(right, f.name)) for f in fields(left))
    if isinstance(left, BaseModel):
        return _same_typed(left.model_dump(mode="python"), right.model_dump(mode="python"))
    if type(left) is tuple or type(left) is list:
        return len(left) == len(right) and all(
            _same_typed(a, b) for a, b in zip(left, right, strict=True)
        )
    if type(left) is dict:
        return list(left) == list(right) and all(_same_typed(left[k], right[k]) for k in left)
    return left == right


def describe_current_owned_rgbd(
    stream: ContinuousEvidenceInput, action_id: UUID
) -> CurrentOwnedRGBDDescriptor:
    """Rebuild from original issued/accepted inputs under both owner locks.

    Existing owner guards may reverify neural proofs; this performs no new model
    training, visual candidate inference, publication, command or persistence.
    No caller-provided packet, prior, cutoff or source is accepted.
    """
    _require(type(stream) is ContinuousEvidenceInput, "descriptor requires the actual owner")
    _require(type(action_id) is UUID, "action identity must be an exact UUID")
    with stream._lock, stream._system.core._execution_lock:
        stream._enter()
        try:
            _require(
                set(stream._observation_commands) == set(stream._observation_status)
                and set(stream._observation_native_origins) <= set(stream._observation_commands),
                "owner command/status/origin closure differs",
            )
            _require(action_id in stream._observation_commands, "action was not issued by owner")
            command, command_pin = stream._observation_commands[action_id]
            delivery = stream._observation_status[action_id]
            _require(
                type(command) is ObservationCommand
                and type(command.action_id) is UUID
                and command.action_id == action_id
                and content_sha256(command) == command_pin
                and command.reason.startswith("joint-ciav@1:")
                and action_id in stream._observation_native_origins,
                "action is not an original modeled owner command",
            )
            _require(
                type(delivery) is ObservationDelivery
                and type(delivery.action_id) is UUID
                and delivery.action_id == action_id
                and type(delivery.success) is bool
                and delivery.success
                and type(delivery.error) is str
                and delivery.error == ""
                and type(delivery.observations) is tuple
                and len(delivery.observations) == 3,
                "action has no complete successful RGB-D delivery",
            )
            stream._check_observation_decoder()
            _require(stream._observation_decoder is not None, "modeled decoder is unavailable")
            base = stream._native_joint_decision_view()
            origin = stream._observation_native_origins[action_id]
            _require(
                type(origin) is str
                and origin == base.content_sha256
                and command.snapshot_id == base.snapshot_id,
                "issued native origin is stale",
            )
            problem = JointCameraProblem.model_validate_json(
                command.reason.removeprefix("joint-ciav@1:")
            )
            _require(
                problem.source_belief_sha256 == origin
                and problem.model_sources == stream._observation_decoder.sources
                and problem.source_observation_ids == command.source_ids,
                "only the unchanged native-base decision is supported",
            )
            _, selected = problem.select(base, stream._system.cause_information_planner)
            _require(
                selected is not None
                and selected.action == command.action
                and selected.degrees == command.degrees,
                "command differs from the original selected action",
            )
            require_aware(command.decision_time, "decision")
            require_aware(delivery.received_at, "received")
            _require(
                stream._last_arrival is not None
                and command.decision_time <= delivery.received_at <= stream._last_arrival,
                "delivery is beyond owner received history",
            )
            _require(
                type(command.source_ids) is tuple
                and command.source_ids
                and all(type(key) is UUID for key in command.source_ids)
                and len(set(command.source_ids)) == len(command.source_ids)
                and set(command.source_ids) <= set(stream._raw),
                "issued source observations are missing or duplicate",
            )
            for key in command.source_ids:
                env = stream._raw[key].envelope()
                _require(
                    env.identity.observation_id == key
                    and env.arrival_time <= command.decision_time,
                    "command cites observations unavailable at decision",
                )
            members = []
            for raw in delivery.observations:
                _require(
                    type(raw) is RawModalityObservation
                    and type(raw.payload_bytes) is bytes
                    and type(raw.envelope_json) is str
                    and type(raw.capture_receipt_sha256) is str
                    and (raw.depth_unit is None or type(raw.depth_unit) is str)
                    and (
                        raw.archive_sampling_json is None or type(raw.archive_sampling_json) is str
                    ),
                    "invalid delivered raw type",
                )
                env = raw.envelope()
                key = env.identity.observation_id
                _require(
                    key not in command.source_ids
                    and key in stream._raw
                    and _same_typed(stream._raw[key], raw)
                    and (env.identity.household_id, env.identity.session_id, env.identity.trace_id)
                    == stream._scope
                    and env.metadata.source_id == str(action_id)
                    and command.decision_time
                    <= env.capture_time
                    <= env.arrival_time
                    <= delivery.received_at,
                    "RGB-D differs from original owner bytes/scope/action/time",
                )
                members.append(
                    RGBDMemberDescription(
                        key,
                        raw.envelope_json,
                        sha256(raw.payload_bytes).hexdigest(),
                        len(raw.payload_bytes),
                        raw.capture_receipt_sha256,
                        raw.depth_unit,
                        raw.archive_sampling_json,
                    )
                )
            camera, _ = decode_unity_rgbd(delivery.observations, cutoff=delivery.received_at)
            _require(camera.action_id == action_id, "camera action differs from owner command")
            core = stream._system.core
            workspace = core._particle_workspace
            profile = workspace.raw_candidate_profile
            _require(
                type(profile) is dict and profile.get("profile") == "controlled-position-raw@1",
                "descriptor requires the protected canonical raw profile",
            )
            batch = workspace.batch
            body = workspace._validated_input_body(base.evidence_cluster_id)
            _require(body.neural_evidence is not None, "parent has no verified neural source")
            actual = body.neural_evidence.base_candidates
            source = core.current_posterior_projection_source()
            _require(
                actual.source_posterior_id == source.source_id
                and actual.source_body_sha256 == source.body_sha256
                and workspace.posterior_sources[source.source_id].body_sha256 == source.body_sha256,
                "parent input source is stale or differs from current source",
            )
            previous = workspace.previous_weight_evidence(batch)
            _require(previous is not None, "parent weight evidence is unavailable")
            logs, aggregate = previous.normalized_logs()
            return CurrentOwnedRGBDDescriptor(
                "current-owned-rgbd-description@1",
                action_id,
                stream._scope,
                command_pin,
                content_sha256(
                    (
                        delivery.action_id,
                        delivery.success,
                        delivery.error,
                        delivery.received_at,
                        tuple(members),
                    )
                ),
                command.decision_time,
                delivery.received_at,
                tuple(members),
                camera,
                origin,
                workspace.runtime_id,
                base.snapshot_id,
                base.evidence_cluster_id,
                source.source_id,
                source.body_sha256,
                source.history_after.latest.revision_id,
                native_content_sha256(batch),
                native_content_sha256(body),
                native_content_sha256(previous),
                tuple(sorted(logs.items(), key=lambda row: str(row[0]))),
                aggregate,
                stream._observation_decoder_binding,
                content_sha256(
                    (sha256(Path(__file__).read_bytes()).hexdigest(), implementation_binding())
                ),
            )
        finally:
            stream._busy = False


def require_current_owned_descriptor(
    stream: ContinuousEvidenceInput, descriptor: CurrentOwnedRGBDDescriptor
) -> CurrentOwnedRGBDDescriptor:
    """Reject a complete resealed derived value against fresh original-owner data."""
    _require(type(descriptor) is CurrentOwnedRGBDDescriptor, "invalid descriptor type")
    expected = describe_current_owned_rgbd(stream, descriptor.action_id)
    _require(_same_typed(expected, descriptor), "descriptor differs from fresh original owner")
    return expected
