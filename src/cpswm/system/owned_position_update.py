"""Owned single-frame position transactions; physical delivery survives computation failure."""

from __future__ import annotations

import inspect
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

from cpswm.system.native_joint_production import NativeJointContext, NativeObservationUpdate
from cpswm.system.structure_two_particle_workspace import native_content_sha256

if TYPE_CHECKING:
    from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput


def implementation_binding() -> str:
    from cpswm.system.controlled_position_producer import _helper_code_sha256

    return native_content_sha256(
        (
            sha256(Path(__file__).read_bytes()).hexdigest(),
            tuple(
                (name, _helper_code_sha256(value.__code__))
                for name, value in sorted(globals().items())
                if inspect.isfunction(value) and value.__module__ == __name__
            ),
        )
    )


def enabled(stream: ContinuousEvidenceInput) -> bool:
    profile = stream._system.core._particle_workspace.raw_candidate_profile
    return type(profile) is dict and profile.get("profile") == "owned-single-position-raw@1"


def delivery_pin(delivery: Any) -> str:
    return native_content_sha256(
        (
            delivery.action_id,
            delivery.success,
            delivery.error,
            delivery.received_at,
            tuple(
                (
                    r.envelope_json,
                    sha256(r.payload_bytes).hexdigest(),
                    r.capture_receipt_sha256,
                    r.archive_sampling_json,
                    r.depth_unit,
                )
                for r in delivery.observations
            ),
        )
    )


def issue_anchor(stream: ContinuousEvidenceInput, command: Any) -> tuple[Any, ...]:
    core = stream._system.core
    source = core.current_posterior_projection_source()
    batch = core._particle_workspace.batch
    if batch is None:
        raise ValueError("owned position command requires an actual Native parent")
    return (
        stream._observation_commands[command.action_id][1],
        source.source_id,
        source.body_sha256,
        source.history_after.latest.revision_id,
        core._particle_workspace.runtime_id,
        batch.evidence_cluster_id,
        native_content_sha256(batch),
        stream._observation_native_origins[command.action_id],
    )


def accepted_update(stream: ContinuousEvidenceInput, action_id: UUID) -> NativeObservationUpdate:
    """Rebuild only from original independently retained issue/delivery anchors."""
    from cpswm.system.controlled_position_producer import packet_binding
    from cpswm.system.reproducibility import content_sha256
    from cpswm.system.structure_two_continuous_input import ObservationDelivery

    core = stream._system.core
    issue = core._particle_observation_issues.get(action_id)
    command, pin = stream._observation_commands[action_id]
    delivery = stream._observation_status[action_id]
    if (
        issue is None
        or issue[0] != pin
        or pin != content_sha256(command)
        or command.action_id != action_id
        or type(delivery) is not ObservationDelivery
        or not delivery.success
        or delivery.error
        or delivery.action_id != action_id
        or delivery_pin(delivery) != core._particle_observation_deliveries.get(action_id)
        or stream._observation_native_origins.get(action_id) != issue[7]
    ):
        raise ValueError("owned observation differs from original issue/delivery acceptance")
    for raw in delivery.observations:
        env = raw.envelope()
        if (
            stream._raw.get(env.identity.observation_id) != raw
            or env.metadata.source_id != str(action_id)
            or (env.identity.household_id, env.identity.session_id, env.identity.trace_id)
            != stream._scope
            or not command.decision_time
            <= env.capture_time
            <= env.arrival_time
            <= delivery.received_at
        ):
            raise ValueError("owned observation raw bytes or historical timing changed")
    packet = packet_binding(delivery.observations)
    if packet["action_id"] != str(action_id):
        raise ValueError("owned packet action differs")
    digest = delivery_pin(delivery)
    return NativeObservationUpdate(
        content_sha256(("owned-position-logical@1", action_id, pin, digest)),
        action_id,
        issue[3],
        issue[1],
        issue[2],
        issue[4],
        issue[5],
        issue[6],
        pin,
        digest,
        packet,
        command.decision_time,
        delivery.received_at,
    )


def verify_journal(stream: ContinuousEvidenceInput) -> None:
    if not enabled(stream):
        return
    core = stream._system.core
    expected = {}
    for action_id, update in stream._position_consumptions.items():
        original = accepted_update(stream, action_id)
        if type(update) is not NativeObservationUpdate or original != update:
            raise ValueError("position consumption differs from accepted original")
        expected[update.logical_key] = native_content_sha256(update)
    if expected != core._particle_observation_update_anchors or len(expected) > 1:
        raise ValueError("position consumption catalogue closure differs")
    workspaces = [g.old_workspace for g in core._particle_replay_generations]
    for workspace in (*workspaces, core._particle_workspace):
        for context in workspace.raw_contexts.values():
            update = context.observation_update
            if update is not None and expected.get(update.logical_key) != native_content_sha256(
                update
            ):
                raise ValueError("raw context has no original accepted observation")


def consume(stream: ContinuousEvidenceInput, action_id: UUID) -> NativeObservationUpdate:
    from cpswm.system.native_joint_production import ProducedJointCandidates
    from cpswm.system.owned_position_delivery import describe_current_owned_rgbd

    if type(action_id) is not UUID or not enabled(stream):
        raise ValueError("explicit canonical owned position profile and action UUID required")
    core = stream._system.core
    with stream._lock, core._execution_lock:
        # Repeat after a successful replay returns the same logical receipt;
        # a withdrawn source cannot silently regain consumption authority.
        stream._enter()
        try:
            verify_journal(stream)
            if action_id in stream._position_consumptions:
                update = stream._position_consumptions[action_id]
                if update.semantic_revision_id not in core._observed_events:
                    raise ValueError("consumed observation semantic anchor was withdrawn")
                core.prepared_particle_location_marginal()
                return deepcopy(update)
            if stream._position_consumptions:
                raise ValueError("second measurement unsupported by single measurement profile")
        finally:
            stream._busy = False
        describe_current_owned_rgbd(stream, action_id)
        if issue_anchor(
            stream, stream._observation_commands[action_id][0]
        ) != core._particle_observation_issues.get(action_id):
            raise ValueError("issued observation parent/source is stale")
        update = accepted_update(stream, action_id)
        if stream._last_cutoff is not None and stream._last_cutoff > update.received_at:
            raise ValueError("owned observation cutoff predates current owner knowledge")
        stream._enter()
        checkpoint = None
        prior_state = None
        previous_owner = (
            dict(stream._position_consumptions),
            stream._joint_published_batch_sha256,
            stream._joint_published_source_sha256,
            stream._last_cutoff,
            dict(stream._observation_status),
        )
        producer = stream._joint_producer
        try:
            if producer is None or not stream._joint_binding_matches(producer):
                raise ValueError("owned position producer dependency changed")
            core._validate_particle_input_anchors()
            checkpoint = core._capture_revision_transaction(include_operator_state=True)
            prior_state = deepcopy(producer.checkpoint_state())
            workspace = core._particle_workspace
            source = core.current_posterior_projection_source()
            context = NativeJointContext(
                source,
                workspace.batch,
                tuple(workspace.records.values()),
                core._hybrid_loop.ledger.export_state().manifest.head_hash,
                stream.visible_prefix(cutoff=update.received_at),
                update.received_at,
                stream._native_visual_source(update.received_at),
                workspace.previous_weight_evidence(workspace.batch),
                update,
            )
            core._particle_observation_update_anchors[update.logical_key] = native_content_sha256(
                update
            )
            core._register_native_raw_context(context, authority=stream._raw_candidate_authority)
            produced = deepcopy(producer.produce(deepcopy(context)))
            if (
                type(produced) is not ProducedJointCandidates
                or produced.context_sha256 != context.content_sha256
                or produced.source_posterior_id != source.source_id
                or produced.source_body_sha256 != source.body_sha256
                or produced.dependency_sha256 != stream._joint_dependency_binding
                or produced.neural_evidence is None
                or produced.neural_evidence.input_context_sha256 != context.content_sha256
                or not stream._joint_binding_matches(producer)
            ):
                raise ValueError("owned position result differs from its admitted context")
            core.stage_prepared_particle_candidates(
                receipts=produced.receipts,
                statistics=produced.statistics,
                unresolved_log_weight=produced.unresolved_log_weight,
                neural_evidence=produced.neural_evidence,
            )
            stream._position_consumptions[action_id] = update
            stream._joint_published_batch_sha256 = native_content_sha256(workspace.batch)
            stream._joint_published_source_sha256 = source.body_sha256
            stream._last_cutoff = update.received_at
            stream._cancel_stale_joint_commands()
            stream._persist()
            return deepcopy(update)
        except BaseException:
            if checkpoint is not None and not stream._durability_failed:
                core._restore_revision_transaction(checkpoint)
                (
                    stream._position_consumptions,
                    stream._joint_published_batch_sha256,
                    stream._joint_published_source_sha256,
                    stream._last_cutoff,
                    stream._observation_status,
                ) = previous_owner
                if producer is not None and prior_state is not None:
                    try:
                        producer.restore_state(prior_state)
                        if native_content_sha256(
                            producer.checkpoint_state()
                        ) != native_content_sha256(prior_state):
                            raise RuntimeError("owned position producer rollback differs")
                    except BaseException:
                        stream._durability_failed = True
                        raise
            raise
        finally:
            stream._busy = False
