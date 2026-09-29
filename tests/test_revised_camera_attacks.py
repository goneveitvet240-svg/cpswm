"""Second review: complete resealing, dependency change and failed-replay effects."""

from dataclasses import replace
from datetime import timedelta

import pytest
from test_continuous_camera_collection import Camera, Model
from test_joint_camera_feedback import setup
from test_native_joint_full_replay import (
    corrected_checkpoint as _checkpoint_fixture,
)
from test_native_joint_full_replay import fixture_method_profile, restore_copy
from test_native_joint_production import JointFixture

from cpswm.system.revised_camera_collection import collect_revised_posterior_step
from cpswm.system.structure_two_particle_workspace import native_content_sha256

corrected_checkpoint = _checkpoint_fixture


def camera_for(checkpoint):
    probe = checkpoint[1][0]
    return Camera(probe.transition_for(probe.observed_days()[11]))


def test_complete_resealed_native_source_cannot_replay_or_dispatch(corrected_checkpoint, tmp_path):
    stream, store, joint = restore_copy(corrected_checkpoint, tmp_path / "db")
    try:
        core = stream._system.core
        workspace = core._particle_workspace
        source = next(
            s
            for s in workspace.posterior_sources.values()
            if s.history_after.latest.revision_id in core._observed_events
        )
        forged = replace(source, snapshot_id=core.current_snapshot.snapshot_id)
        forged = replace(forged, body_sha256=native_content_sha256(forged.body()))
        forged.validate_content()
        workspace.posterior_sources[source.source_id] = forged
        ledger = core._hybrid_loop.ledger.export_state()
        producer = joint.checkpoint_state()
        camera = camera_for(corrected_checkpoint)
        with pytest.raises(ValueError, match="core acceptance anchors"):
            collect_revised_posterior_step(
                stream,
                model=Model(stream),
                executor=camera,
                decision_time=stream._last_arrival + timedelta(seconds=2),
            )
        assert camera.calls == 0 and joint.checkpoint_state() == producer
        assert core._hybrid_loop.ledger.export_state() == ledger
        assert not core._particle_replay_generations
    finally:
        store.close()


def test_mid_replay_failure_has_no_action_and_valid_retry_preserves_ledger(
    corrected_checkpoint, tmp_path
):
    stream, store, joint = restore_copy(corrected_checkpoint, tmp_path / "db")
    try:
        core = stream._system.core
        ledger = core._hybrid_loop.ledger.export_state()
        old = native_content_sha256(vars(core._particle_workspace))
        camera = camera_for(corrected_checkpoint)

        def fail(frame):
            if (
                frame.f_code is JointFixture.produce.__code__
                and frame.f_locals["self"] is joint
                and joint.calls == 2
            ):
                raise RuntimeError("injected replay interruption")

        with fixture_method_profile(fail), pytest.raises(RuntimeError, match="interruption"):
            collect_revised_posterior_step(
                stream,
                model=Model(stream),
                executor=camera,
                decision_time=stream._last_arrival + timedelta(seconds=2),
            )
        assert camera.calls == 0 and native_content_sha256(vars(core._particle_workspace)) == old
        assert core._hybrid_loop.ledger.export_state() == ledger
        result = collect_revised_posterior_step(
            stream,
            model=Model(stream),
            executor=camera,
            decision_time=stream._last_arrival + timedelta(seconds=2),
        )
        assert result.replayed and camera.calls == 1
        assert core._hybrid_loop.ledger.export_state() == ledger
    finally:
        store.close()


def test_changed_measurement_model_fails_before_any_state_or_action(tmp_path):
    stream, store, transition, _, when = setup(tmp_path / "db")
    try:
        model = Model(stream)
        model.sources = model.sources.model_copy(update={"calibration_data_sha256": "d" * 64})
        camera = Camera(transition)
        before = native_content_sha256(stream._system.core._particle_workspace.state_payload())
        with pytest.raises(ValueError, match="model sources changed"):
            collect_revised_posterior_step(
                stream, model=model, executor=camera, decision_time=when + timedelta(seconds=2)
            )
        assert camera.calls == 0
        assert (
            native_content_sha256(stream._system.core._particle_workspace.state_payload()) == before
        )
    finally:
        store.close()
