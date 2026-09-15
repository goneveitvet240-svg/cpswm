"""Default collector wiring and recovery with explicit synthetic sensor fixtures."""

from datetime import timedelta

import pytest
from test_continuous_state_recovery import DurableFixtureProducer, store_at
from test_joint_camera_policy import p5_setup, problem_for
from test_structure_two_continuous_input import raw_for

from cpswm.system.continuous_camera_collection import collect_posterior_step
from cpswm.system.joint_camera_policy import CameraModelSources
from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput, ObservationDelivery

SOURCES = CameraModelSources(
    observation_model_id="fixture-not-empirically-calibrated",
    observation_artifact_sha256="a" * 64,
    calibration_domain="component-test",
    calibration_data_sha256="b" * 64,
    utility_definition_id="fixture-atom-classification",
    utility_artifact_sha256="c" * 64,
)


class Model:
    sources = SOURCES
    calls = 0
    informative = True

    def __init__(self, stream):
        self.stream = stream

    def problem(self, view, visible_prefix, *, decision_time, execution_history=()):
        self.calls += 1
        self.history = execution_history
        assert view.content_sha256 == self.stream.current_joint_decision_view().content_sha256
        assert visible_prefix == self.stream.visible_prefix(cutoff=decision_time)
        return problem_for(self.stream, decision_time, self.informative).model_copy(
            update={"model_sources": self.sources}
        )


class Camera:
    calls = 0
    crash = False

    def __init__(self, transition):
        self.transition = transition

    def execute(self, command):
        self.calls += 1
        if self.crash:
            raise OSError("fixture transport lost after possible effect")
        received = command.decision_time + timedelta(seconds=1)
        return ObservationDelivery(
            command.action_id, (raw_for(self.transition, capture=received),), True, "", received
        )


def test_collector_selects_executes_then_advances_same_producer_and_history(tmp_path):
    stream, store, transition, _, start = p5_setup(tmp_path / "db")
    model, camera = Model(stream), Camera(transition)
    result = collect_posterior_step(
        stream, model=model, executor=camera, decision_time=start + timedelta(seconds=2)
    )
    assert result.command.action == "RotateLeft"
    assert camera.calls == model.calls == 1
    assert len(stream.visible_prefix(cutoff=result.delivery.received_at)) == 2
    assert len(stream._producer.checkpoint_state()["output"].source_observation_ids) == 1
    assert result.semantic_receipt is not None  # old fixture transition; no new semantic claim
    assert stream._last_cutoff == result.delivery.received_at
    assert "model_sources" in result.command.reason
    store.close()


def test_ready_command_recovery_executes_saved_decision_once(tmp_path):
    path = tmp_path / "db"
    stream, store, transition, builder, start = p5_setup(path)
    model = Model(stream)
    when = start + timedelta(seconds=2)
    problem = model.problem(
        stream.current_joint_decision_view(), stream.visible_prefix(cutoff=when), decision_time=when
    )
    _, command = stream.prepare_posterior_observation(problem, decision_time=when)
    store.close()
    store = store_at(path)
    stream = ContinuousEvidenceInput.resume(
        store, producer=DurableFixtureProducer(), context_builder=builder
    )
    model, camera = Model(stream), Camera(transition)
    result = collect_posterior_step(
        stream, model=model, executor=camera, decision_time=when + timedelta(seconds=10)
    )
    assert result.recovered_ready_command
    assert result.command.action_id == command.action_id
    assert camera.calls == 1 and model.calls == 0
    assert stream._last_cutoff == result.delivery.received_at
    store.close()


def test_no_information_stops_without_moving_camera(tmp_path):
    stream, store, transition, _, start = p5_setup(tmp_path / "db")
    model, camera = Model(stream), Camera(transition)
    model.informative = False
    result = collect_posterior_step(
        stream, model=model, executor=camera, decision_time=start + timedelta(seconds=2)
    )
    assert result.command is None and result.delivery is None
    assert camera.calls == 0 and not stream._observation_commands
    store.close()


def test_uncertain_effect_cannot_be_retried_through_collector(tmp_path):
    stream, store, transition, _, start = p5_setup(tmp_path / "db")
    model, camera = Model(stream), Camera(transition)
    camera.crash = True
    when = start + timedelta(seconds=2)
    with pytest.raises(OSError):
        collect_posterior_step(stream, model=model, executor=camera, decision_time=when)
    camera.crash = False
    with pytest.raises(RuntimeError, match="uncertain"):
        collect_posterior_step(
            stream, model=model, executor=camera, decision_time=when + timedelta(seconds=1)
        )
    assert camera.calls == 1
    store.close()


def test_recovery_rejects_changed_utility_source_before_effect(tmp_path):
    stream, store, transition, _, start = p5_setup(tmp_path / "db")
    model, camera = Model(stream), Camera(transition)
    when = start + timedelta(seconds=2)
    p = model.problem(
        stream.current_joint_decision_view(), stream.visible_prefix(cutoff=when), decision_time=when
    )
    stream.prepare_posterior_observation(p, decision_time=when)
    model.sources = SOURCES.model_copy(update={"utility_artifact_sha256": "d" * 64})
    with pytest.raises(ValueError, match="sources changed"):
        collect_posterior_step(stream, model=model, executor=camera, decision_time=when)
    assert camera.calls == 0
    store.close()


def test_failed_execution_is_available_to_next_policy_decision(tmp_path):
    stream, store, transition, _, start = p5_setup(tmp_path / "db")

    class AvoidRepeatedFailure(Model):
        def problem(self, view, visible_prefix, *, decision_time, execution_history=()):
            if execution_history:
                assert execution_history[-1][1].success is False
                self.informative = False
            return super().problem(
                view,
                visible_prefix,
                decision_time=decision_time,
                execution_history=execution_history,
            )

    class FailedCamera(Camera):
        def execute(self, command):
            self.calls += 1
            return ObservationDelivery(
                command.action_id,
                (),
                False,
                "blocked view",
                command.decision_time + timedelta(seconds=1),
            )

    model, camera = AvoidRepeatedFailure(stream), FailedCamera(transition)
    first = collect_posterior_step(
        stream, model=model, executor=camera, decision_time=start + timedelta(seconds=2)
    )
    assert first.delivery.success is False
    second = collect_posterior_step(
        stream, model=model, executor=camera, decision_time=start + timedelta(seconds=4)
    )
    assert second.command is None and camera.calls == 1
    assert len(model.history) == 1
    assert stream.observation_history()[0][0] is not first.command
    store.close()
