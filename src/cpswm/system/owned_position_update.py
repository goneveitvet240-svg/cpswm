"""Owned single-frame position transactions; physical delivery survives computation failure."""

from __future__ import annotations

import inspect
from copy import deepcopy
from dataclasses import replace
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
    return type(profile) is dict and profile.get("profile") in (
        "owned-single-position-raw@1",
        "natural-candidate-single-position-raw@1",
        "appearance-geometry-single-pair-raw@1",
        "natural-target-temporal-joint-raw@1",
    )


def uses_temporal(stream: ContinuousEvidenceInput) -> bool:
    profile = stream._system.core._particle_workspace.raw_candidate_profile
    return type(profile) is dict and profile.get("profile") == "natural-target-temporal-joint-raw@1"


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


def _original_update(stream: ContinuousEvidenceInput, action_id: UUID) -> NativeObservationUpdate:
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


def uses_association(stream: ContinuousEvidenceInput) -> bool:
    profile = stream._system.core._particle_workspace.raw_candidate_profile
    return (
        type(profile) is dict and profile.get("profile") == "appearance-geometry-single-pair-raw@1"
    )


def reference_for(
    stream: ContinuousEvidenceInput, action_id: UUID
) -> NativeObservationUpdate | None:
    """Most recent complete earlier owned capture, same original semantic base.

    Selection depends only on original acquisition history at query decision time,
    never detector scores, future captures or a submitted reference descriptor.
    """
    from cpswm.system.structure_two_continuous_input import ObservationDelivery

    query = _original_update(stream, action_id)
    command = stream._observation_commands[action_id][0]
    options = []
    for key, status in stream._observation_status.items():
        if (
            key == action_id
            or type(status) is not ObservationDelivery
            or not status.success
            or status.received_at > query.decision_time
            or key not in stream._system.core._particle_observation_issues
        ):
            continue
        ref = _original_update(stream, key)
        if (
            ref.semantic_revision_id == query.semantic_revision_id
            and ref.issued_source_id == query.issued_source_id
            and ref.original_runtime_id == query.original_runtime_id
            and ref.original_parent_sha256 == query.original_parent_sha256
            and set(ref.packet["observation_ids"]) <= {str(k) for k in command.source_ids}
        ):
            options.append(ref)
    return max(options, key=lambda r: (r.received_at, str(r.action_id))) if options else None


def accepted_update(stream: ContinuousEvidenceInput, action_id: UUID) -> NativeObservationUpdate:
    update = _original_update(stream, action_id)
    if uses_association(stream):
        reference = reference_for(stream, action_id)
        if reference is None:
            raise ValueError("association query requires an earlier owned reference capture")
        update = replace(update, reference=reference)
    return update


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
    if expected != core._particle_observation_update_anchors or (
        len(expected) > 1 and not uses_temporal(stream)
    ):
        raise ValueError("position consumption catalogue closure differs")
    withdrawals = getattr(stream, "_position_withdrawals", {})
    expected_withdrawals = {}
    for action_id, record in withdrawals.items():
        withdrawn_update = stream._position_consumptions.get(action_id)
        if (
            withdrawn_update is None
            or type(record) is not tuple
            or len(record) != 4
            or record[0] != withdrawn_update.logical_key
            or record[1] != native_content_sha256(withdrawn_update)
            or type(record[2]) is not str
            or not record[2].strip()
        ):
            raise ValueError("position withdrawal lacks original consumed dependency")
        expected_withdrawals[withdrawn_update.logical_key] = native_content_sha256(record)
    if expected_withdrawals != core._particle_observation_withdrawals:
        raise ValueError("position withdrawal catalogue differs")
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
            if action_id in stream._position_withdrawals:
                raise ValueError("position observation was withdrawn")
            if uses_temporal(stream) and stream._position_consumptions:
                first = min(
                    stream._position_consumptions,
                    key=lambda k: (stream._position_consumptions[k].received_at, str(k)),
                )
                if first in stream._position_withdrawals:
                    raise ValueError("sequence anchor withdrawn; new semantic anchor required")
            if action_id in stream._position_consumptions:
                update = stream._position_consumptions[action_id]
                if update.semantic_revision_id not in core._observed_events:
                    raise ValueError("consumed observation semantic anchor was withdrawn")
                core.prepared_particle_location_marginal()
                return deepcopy(update)
            if stream._position_consumptions and not uses_temporal(stream):
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


def withdraw(stream: ContinuousEvidenceInput, action_id: UUID, *, reason: str) -> None:
    """Atomic position-only tombstone and full retained-history recomputation."""
    if type(action_id) is not UUID or type(reason) is not str or not reason.strip():
        raise ValueError("withdrawal requires action UUID and a nonempty audit reason")
    if not uses_temporal(stream):
        raise ValueError("capture withdrawal requires the temporal profile")
    core = stream._system.core
    with stream._lock, core._execution_lock:
        stream._enter()
        checkpoint = None
        previous = deepcopy(stream._position_withdrawals)
        try:
            verify_journal(stream)
            if action_id not in stream._position_consumptions:
                raise ValueError("only originally consumed captures can be withdrawn")
            if action_id in previous:
                if previous[action_id][2] != reason:
                    raise ValueError("withdrawal audit reason conflicts with original")
                core.prepared_particle_location_marginal()
                return
            checkpoint = core._capture_revision_transaction(include_operator_state=True)
            keys = sorted(
                stream._position_consumptions,
                key=lambda k: (stream._position_consumptions[k].received_at, str(k)),
            )
            excluded = keys if keys[0] == action_id else [action_id]
            for key in excluded:
                if key in stream._position_withdrawals:
                    continue
                update = stream._position_consumptions[key]
                record = (
                    update.logical_key,
                    native_content_sha256(update),
                    reason,
                    stream._last_cutoff,
                )
                stream._position_withdrawals[key] = record
                core._particle_observation_withdrawals[update.logical_key] = native_content_sha256(
                    record
                )
            # Reentrant lock stays held; replay owns the inner computation and
            # persistence transaction. No partial tombstone is published.
            stream._busy = False
            stream.replay_joint_posterior()
        except BaseException:
            if checkpoint is not None and not stream._durability_failed:
                core._restore_revision_transaction(checkpoint)
                stream._position_withdrawals = previous
            raise
        finally:
            stream._busy = False
