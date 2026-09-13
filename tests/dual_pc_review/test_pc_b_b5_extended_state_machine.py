"""PC-B regressions for coherent workspace resealing and core-owned anchors."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest
import test_structure_two_formal_revision_lineage as old
from test_structure_two_w3_deferred_cancellation import pending
from test_structure_two_w3_native_particles import candidates

from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_particle_workspace import native_content_sha256
from cpswm.system.structure_two_semantic_identity import semantic_memory_state


def _reseal_stored_propensity(core) -> tuple[object, float, float]:
    workspace = core._particle_workspace
    cluster, body = next(iter(workspace.input_bodies.items()))
    frames, cause_snapshot = deepcopy(body.source_frame)
    revision_id = next(iter(frames))
    row = frames[revision_id]
    forged_propensity = float(row[2]) + 0.125
    frames[revision_id] = (row[0], row[1], forged_propensity, row[3], row[4])
    forged_frame = (frames, cause_snapshot)
    forged_body = replace(body, source_frame=forged_frame)
    fingerprint = native_content_sha256(forged_body)
    source_frame_sha256 = native_content_sha256(forged_frame)

    workspace.input_bodies[cluster] = forged_body
    workspace.input_journal[cluster] = fingerprint
    for particle_id, record in tuple(workspace.records.items()):
        if record.evidence_cluster_id == cluster:
            workspace.records[particle_id] = replace(
                record,
                source_frame=forged_frame,
                source_frame_sha256=source_frame_sha256,
                input_fingerprint_sha256=fingerprint,
            )
    return revision_id, core._observed_events[revision_id].propensity_weight, forged_propensity


def _assert_anchor_rejection(call) -> None:
    try:
        call()
    except ValueError as error:
        assert "core runtime acceptance binding anchors" in str(error)
    else:
        raise AssertionError("coherently resealed workspace crossed a core read boundary")


def test_core_anchor_rejects_coherently_resealed_non_noop_source_frame() -> None:
    core = old._legacy_history(1).system.core
    core.stage_prepared_particle_candidates(**candidates(core))
    workspace = core._particle_workspace
    ledger_before = content_sha256(core._hybrid_loop.ledger.export_state())

    revision_id, runtime_propensity, forged_propensity = _reseal_stored_propensity(core)
    assert revision_id in core._event_histories
    assert runtime_propensity != forged_propensity
    # The attack is internally coherent and therefore reaches the missing
    # cross-object trust boundary rather than failing on an incidental hash.
    assert workspace.state_payload()

    _assert_anchor_rejection(core.prepared_particle_location_marginal)
    _assert_anchor_rejection(core.semantic_memory_identity)
    assert content_sha256(core._hybrid_loop.ledger.export_state()) == ledger_before


def test_core_anchor_legal_multigeneration_and_replay_control() -> None:
    probe = old._legacy_history(1)
    core = probe.system.core
    first_arguments = candidates(core)
    first = core.stage_prepared_particle_candidates(**first_arguments)
    assert first.particle_weights
    assert core.stage_prepared_particle_candidates(**first_arguments) == first
    assert core._particle_input_anchors == core._particle_workspace.input_journal
    assert core.prepared_particle_location_marginal()[1] > 0.0

    core.process_transition(probe.transition_for(probe.observed_days()[1]))
    second = core.stage_prepared_particle_candidates(**candidates(core, step=1))
    assert second.particle_weights
    assert len(core._particle_input_anchors) == 2
    assert core._particle_input_anchors == core._particle_workspace.input_journal
    assert core.prepared_particle_location_marginal()[1] > 0.0
    assert core.semantic_memory_identity()


def _cancellation_runtime_shape(core) -> tuple[object, ...]:
    def event_rows(values):
        return tuple(
            sorted((str(key), native_content_sha256(value)) for key, value in values.items())
        )

    return (
        core.observation_count,
        content_sha256(core.current_snapshot),
        content_sha256(core._hybrid_loop.ledger.export_state()),
        event_rows(core._observed_events),
        event_rows(core._committed_events),
        event_rows(core._fast_action_events),
        tuple(native_content_sha256(item) for item in core._quarantined_events),
        event_rows(core._derived_event_archive),
        tuple(
            sorted(
                (str(key), value.value)
                for key, value in core._derived_event_lifecycle.items()
            )
        ),
        tuple(
            sorted(
                (str(key), native_content_sha256(value))
                for key, value in core._write_eligibility.items()
            )
        ),
        core.revision_transactions,
        core._correction_cancellations,
        dict(core._deferred_project_one_requests),
        dict(core._deferred_correction_restore),
        dict(core._deferred_correction_restore_anchors),
        dict(core._correction_cancellation_anchors),
    )


def test_staged_cancellation_restore_reseal_is_rejected_before_ledger_mutation() -> None:
    args = pending()
    probe, core = args[0], args[0].system.core
    fingerprint, restoration = next(iter(core._deferred_correction_restore.items()))
    original_anchor = core._deferred_correction_restore_anchors[fingerprint]
    action_before = core.action_location_distribution(core.current_snapshot)
    restore_events, _restore_fast = restoration
    forged = ((*restore_events, restore_events[0]), ())
    assert native_content_sha256(forged) != original_anchor
    core._deferred_correction_restore[fingerprint] = forged
    before = _cancellation_runtime_shape(core)
    receipts_before = core.application_receipts_for_feedback(args[3].source_feedback_record_id)

    with pytest.raises(ValueError, match="correction restoration.*acceptance anchor"):
        core.process_transition(probe.transition_for(probe.observed_days()[12]))
    assert _cancellation_runtime_shape(core) == before
    with pytest.raises(ValueError, match="correction restoration.*acceptance anchor"):
        core.apply_project_one_stat_request(args[3])
    assert core.application_receipts_for_feedback(args[3].source_feedback_record_id) == (
        receipts_before
    )

    # Restore the exact accepted input and prove the legal non-empty path still works.
    core._deferred_correction_restore[fingerprint] = restoration
    assert core.action_location_distribution(core.current_snapshot) == action_before
    core.process_transition(probe.transition_for(probe.observed_days()[12]))
    assert len(core._correction_cancellations) == 1
    semantic_memory_state(core)


def test_published_cancellation_reseal_is_rejected_by_durable_core_anchor() -> None:
    args = pending()
    probe, core = args[0], args[0].system.core
    core.process_transition(probe.transition_for(probe.observed_days()[12]))
    cancellation = core._correction_cancellations[0]
    forged = replace(
        cancellation,
        rationale="coherently resealed but unaccepted cancellation rationale",
        restore_fast_events=(),
    )
    forged = replace(forged, body_sha256=native_content_sha256(forged.body()))
    forged.validate_content()
    assert native_content_sha256(forged.body()) != core._correction_cancellation_anchors[
        cancellation.request_fingerprint
    ]
    core._correction_cancellations = (forged,)
    before = _cancellation_runtime_shape(core)
    receipts_before = core.application_receipts_for_feedback(
        cancellation.request.source_feedback_record_id
    )

    with pytest.raises(ValueError, match="cancellation.*acceptance anchor"):
        semantic_memory_state(core)
    with pytest.raises(ValueError, match="cancellation.*acceptance anchor"):
        core.action_location_distribution(core.current_snapshot)
    with pytest.raises(ValueError, match="cancellation.*acceptance anchor"):
        core.apply_project_one_stat_request(cancellation.request)
    assert _cancellation_runtime_shape(core) == before
    assert core.application_receipts_for_feedback(
        cancellation.request.source_feedback_record_id
    ) == receipts_before
