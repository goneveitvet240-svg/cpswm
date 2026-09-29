"""Same-history source correction, stale plans and subsequent action effects."""

from datetime import timedelta

import pytest
from history_loop_scenario import correction_bundles
from run_correction_replay_comparison import apply_feedback, build, ingest
from test_continuous_camera_collection import Camera, Model
from test_native_joint_full_replay import corrected_checkpoint as _checkpoint_fixture
from test_native_joint_full_replay import restore_copy
from test_native_joint_production import JointFixture

from cpswm.system.reproducibility import content_sha256
from cpswm.system.revised_camera_collection import collect_revised_posterior_step

corrected_checkpoint = _checkpoint_fixture


def test_accepted_correction_replays_then_dispatches_and_resumes_once(
    corrected_checkpoint, tmp_path
):
    stream, store, joint = restore_copy(corrected_checkpoint, tmp_path / "db")
    try:
        core = stream._system.core
        camera = Camera(
            corrected_checkpoint[1][0].transition_for(
                corrected_checkpoint[1][0].observed_days()[11]
            )
        )
        result = collect_revised_posterior_step(
            stream,
            model=Model(stream),
            executor=camera,
            decision_time=stream._last_arrival + timedelta(seconds=2),
        )
        assert result.replayed and result.invalidated_revisions
        assert result.previous_runtime_id != result.current_runtime_id
        assert result.ledger_before_replay_sha256 == result.ledger_after_replay_sha256
        assert result.collection.delivery.success and camera.calls == 1
        assert joint.calls == 11 and len(core._particle_replay_generations) == 1
        second = collect_revised_posterior_step(
            stream,
            model=Model(stream),
            executor=camera,
            decision_time=result.collection.delivery.received_at + timedelta(seconds=2),
        )
        assert not second.replayed and len(core._particle_replay_generations) == 1
        assert camera.calls == 2 and len(stream.observation_history()) == 2
    finally:
        store.close()


def test_backdated_decision_rejects_before_replay_or_effect(corrected_checkpoint, tmp_path):
    stream, store, joint = restore_copy(corrected_checkpoint, tmp_path / "db")
    try:
        camera = Camera(
            corrected_checkpoint[1][0].transition_for(
                corrected_checkpoint[1][0].observed_days()[11]
            )
        )
        before = joint.checkpoint_state()
        with pytest.raises(ValueError, match="predates"):
            collect_revised_posterior_step(
                stream,
                model=Model(stream),
                executor=camera,
                decision_time=stream._last_arrival - timedelta(seconds=1),
            )
        assert camera.calls == 0 and joint.checkpoint_state() == before
        assert not stream._system.core._particle_replay_generations
    finally:
        store.close()


def test_uncertain_physical_effect_blocks_replay_and_redispatch(corrected_checkpoint, tmp_path):
    stream, store, joint = restore_copy(corrected_checkpoint, tmp_path / "db")
    try:
        camera = Camera(
            corrected_checkpoint[1][0].transition_for(
                corrected_checkpoint[1][0].observed_days()[11]
            )
        )
        camera.crash = True
        when = stream._last_arrival + timedelta(seconds=2)
        command = stream.prepare_observation(
            action="Pass",
            degrees=0,
            reason="explicit uncertain-effect fixture",
            source_ids=tuple(
                x.envelope().identity.observation_id for x in stream.visible_prefix(cutoff=when)
            ),
            decision_time=when,
        )
        with pytest.raises(OSError):
            stream.execute_observation(command, executor=camera)
        before = joint.checkpoint_state()
        with pytest.raises(RuntimeError, match="uncertain"):
            collect_revised_posterior_step(
                stream,
                model=Model(stream),
                executor=camera,
                decision_time=when + timedelta(seconds=2),
            )
        assert camera.calls == 1 and joint.checkpoint_state() == before
        assert not stream._system.core._particle_replay_generations
    finally:
        store.close()


def test_old_ready_plan_cancelled_and_new_owned_plan_executed(tmp_path):
    probe, backend, stream, store, _ = build(
        tmp_path / "db",
        seed=171,
        source=content_sha256("same-history-ready-fixture"),
        joint_producer=JointFixture(),
    )
    try:
        ingest(probe, backend, stream, produce_joint=True)
        model = Model(stream)
        when = stream._last_cutoff + timedelta(seconds=1)
        _, old = stream.prepare_posterior_observation(
            model.problem(
                stream.current_joint_decision_view(),
                stream.visible_prefix(cutoff=when),
                decision_time=when,
            ),
            decision_time=when,
        )
        apply_feedback(stream, correction_bundles(probe, stream), when + timedelta(seconds=1))
        camera = Camera(probe.transition_for(probe.observed_days()[11]))
        result = collect_revised_posterior_step(
            stream,
            model=model,
            executor=camera,
            decision_time=stream._last_arrival + timedelta(seconds=2),
        )
        assert result.cancelled_command_ids == (old.action_id,)
        assert result.collection.command.action_id != old.action_id and camera.calls == 1
        assert stream._observation_status[old.action_id] == "CANCELLED_STALE_JOINT"
        with pytest.raises(ValueError):
            stream.execute_observation(old, executor=camera)
        assert camera.calls == 1
    finally:
        store.close()
