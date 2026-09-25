"""Full native continuation with explicitly assumed semantic/conditional models."""

import sys
from contextlib import contextmanager
from copy import deepcopy
from datetime import timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from run_correction_replay_comparison import (
    NEGATIVE_ABSENT_LIKELIHOOD,
    NEGATIVE_PRESENT_LIKELIHOOD,
    NEGATIVE_SEARCH_OUTCOME,
    apply_feedback,
    build,
    build_execution_feedback_bundle,
    ingest,
)
from test_native_joint_production import JointFixture

from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_particle_workspace import native_content_sha256


def corrected(path, joint=None):
    joint = JointFixture() if joint is None else joint
    probe, producer, stream, store, builder = build(
        path, seed=171, source=content_sha256("joint-full-replay-test"), joint_producer=joint
    )
    ingest(probe, producer, stream, produce_joint=True)
    core = stream._system.core
    old_view = stream.current_joint_decision_view()
    invalid_dates = {d.after.detection_time.date() for d in probe.observed_days()[:7]}
    targets = [
        (rid, event)
        for rid, event in core._committed_events.items()
        if event.evidence.event_time.date() in invalid_dates
    ]
    bundles = [
        build_execution_feedback_bundle(
            probe,
            revision_id=rid,
            location_id=event.location_id,
            belief_snapshot_id=event.belief_snapshot_id,
            when=event.evidence.event_time,
            opportunity_id=event.evidence.observation_opportunity_id,
            outcome_distribution=NEGATIVE_SEARCH_OUTCOME,
            present_likelihood=NEGATIVE_PRESENT_LIKELIHOOD,
            absent_likelihood=NEGATIVE_ABSENT_LIKELIHOOD,
        )
        for rid, event in targets
    ]
    apply_feedback(
        stream, bundles, probe.observed_days()[11].after.detection_time + timedelta(hours=2)
    )
    assert core._particle_workspace.invalidated_revisions
    return probe, producer, stream, store, builder, joint, old_view


def test_replay_restores_actual_joint_readout_without_ledger_write(tmp_path):
    _, _, stream, store, _, joint, before = corrected(tmp_path / "online.db")
    try:
        core = stream._system.core
        old_runtime = core._particle_workspace.runtime_id
        old_workspace = deepcopy(core._particle_workspace)
        old_sources = {r.state.revision_id for r in old_workspace.records.values()} & set(
            core._observed_events
        )
        ledger_before = core._hybrid_loop.ledger.export_state()
        with pytest.raises(ValueError, match="full particle revision replay"):
            stream.produce_joint_posterior()
        stream.replay_joint_posterior()
        view = stream.current_joint_decision_view()
        assert view.atoms and view.unresolved_probability > 0
        assert view.runtime_id != old_runtime
        assert core._hybrid_loop.ledger.export_state() == ledger_before
        assert joint.calls == len(old_sources)
        assert not core._particle_workspace.invalidated_revisions
        archive = core._particle_replay_generations[-1]
        assert native_content_sha256(vars(archive.old_workspace)) == native_content_sha256(
            vars(old_workspace)
        )
        assert {
            r.state.revision_id for r in core._particle_workspace.records.values()
        } == old_sources
        assert all(len(a.statistics.evidence_cluster_ids) == len(old_sources) for a in view.atoms)
        assert view != before
        stream.produce_joint_posterior()  # idempotent ordinary production resumes
        assert stream.current_joint_decision_view() == view
    finally:
        store.close()


@pytest.fixture(scope="module")
def corrected_checkpoint(tmp_path_factory):
    folder = tmp_path_factory.mktemp("joint-replay-base")
    values = corrected(folder / "base.db")
    values[3].close()
    return folder / "base.db", values


def restore_copy(corrected_checkpoint, path, joint=None):
    import sqlite3

    from run_correction_replay_comparison import OracleProducer

    from cpswm.system.continuous_state_store import ContinuousStateStore
    from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput

    base, values = corrected_checkpoint
    with sqlite3.connect(base) as old, sqlite3.connect(path) as new:
        old.backup(new)
    store = ContinuousStateStore(
        path,
        source_identity=content_sha256("joint-full-replay-test"),
        dependency_identity=content_sha256(sys.version),
    )
    joint = JointFixture() if joint is None else joint
    stream = ContinuousEvidenceInput.resume(
        store,
        producer=OracleProducer(),
        context_builder=values[4],
        joint_producer=joint,
    )
    return stream, store, joint


@contextmanager
def fixture_method_profile(callback):
    """Fault/observation seam without changing the registered model implementation."""
    previous = sys.getprofile()
    codes = {JointFixture.produce.__code__, JointFixture.restore_state.__code__}

    def profile(frame, event, value):
        if event == "return" and frame.f_code in codes:
            callback(frame)

    sys.setprofile(profile)
    try:
        yield
    finally:
        sys.setprofile(previous)


def test_partial_generation_failure_restores_all_owned_state(corrected_checkpoint, tmp_path):
    joint = JointFixture()
    stream, store, _ = restore_copy(corrected_checkpoint, tmp_path / "fail.db", joint)
    try:
        core = stream._system.core
        workspace_before = native_content_sha256(vars(core._particle_workspace))
        ledger_before = core._hybrid_loop.ledger.export_state()
        producer_before = deepcopy(joint.checkpoint_state())
        publication_before = (
            stream._joint_published_batch_sha256,
            stream._joint_published_source_sha256,
        )

        def interrupt(frame):
            if (
                frame.f_code is JointFixture.produce.__code__
                and frame.f_locals["self"] is joint
                and joint.calls == 2
            ):
                raise RuntimeError("injected middle-of-replay failure")

        with (
            fixture_method_profile(interrupt),
            pytest.raises(RuntimeError, match="middle-of-replay"),
        ):
            stream.replay_joint_posterior()
        assert native_content_sha256(vars(core._particle_workspace)) == workspace_before
        assert (
            not core._particle_replay_generations and not core._particle_replay_generation_anchors
        )
        assert joint.checkpoint_state() == producer_before
        assert core._hybrid_loop.ledger.export_state() == ledger_before
        assert (
            stream._joint_published_batch_sha256,
            stream._joint_published_source_sha256,
        ) == publication_before
        with pytest.raises(ValueError):
            stream.current_joint_decision_view()
        stream.replay_joint_posterior()
        assert stream.current_joint_decision_view().atoms
    finally:
        store.close()


def test_complete_resealed_producer_source_rejected_by_original_acceptance(
    corrected_checkpoint, tmp_path
):
    from dataclasses import replace

    stream, store, joint = restore_copy(corrected_checkpoint, tmp_path / "forge.db")
    try:
        core = stream._system.core
        workspace = core._particle_workspace
        live = set(core._observed_events)
        source = next(
            s
            for s in workspace.posterior_sources.values()
            if s.history_after.latest.revision_id in live
        )
        # A complete valid typed source, with recomputed body hash, not an absent-field attack.
        forged = replace(source, snapshot_id=core.current_snapshot.snapshot_id)
        forged = replace(forged, body_sha256=native_content_sha256(forged.body()))
        forged.validate_content()
        assert forged != source
        workspace.posterior_sources[source.source_id] = forged
        before = joint.checkpoint_state()
        with pytest.raises(ValueError, match="core acceptance anchors"):
            stream.replay_joint_posterior()
        assert joint.checkpoint_state() == before
        assert workspace.invalidated_revisions and not core._particle_replay_generations
    finally:
        store.close()


def test_replayed_joint_state_recovers_and_drives_one_controlled_camera_action(
    corrected_checkpoint, tmp_path
):
    from run_correction_replay_comparison import OracleProducer
    from test_continuous_camera_collection import Camera, Model

    from cpswm.system.continuous_camera_collection import collect_posterior_step
    from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput

    stream, store, joint = restore_copy(corrected_checkpoint, tmp_path / "recover.db")
    try:
        stream.replay_joint_posterior()
        before = stream.current_joint_decision_view()
        producer_state = joint.checkpoint_state()
        recovered_joint = JointFixture()
        recovered = ContinuousEvidenceInput.resume(
            store,
            producer=OracleProducer(),
            context_builder=corrected_checkpoint[1][4],
            joint_producer=recovered_joint,
        )
        assert recovered.current_joint_decision_view() == before
        assert recovered_joint.checkpoint_state() == producer_state
        core = recovered._system.core
        ledger_before = core._hybrid_loop.ledger.export_state()
        latest = core.current_posterior_projection_source().transition
        camera = Camera(latest)
        decision_time = recovered._last_cutoff + timedelta(hours=3)
        result = collect_posterior_step(
            recovered,
            model=Model(recovered),
            executor=camera,
            decision_time=decision_time,
        )
        assert camera.calls == 1 and result.command.action == "RotateLeft"
        assert result.delivery is not None and result.delivery.success
        assert len(recovered._observation_commands) == 1
        assert core._hybrid_loop.ledger.export_state() == ledger_before
        assert len(core._particle_replay_generations) == 1
        # Delivered pixels are admitted but the oracle has no new semantic transition.
        assert recovered.current_joint_decision_view() == before
    finally:
        store.close()
