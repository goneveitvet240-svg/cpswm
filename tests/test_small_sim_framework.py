from __future__ import annotations

from dataclasses import replace

import pytest

from cpswm.simulation.contracts import CommandQueue, Observation, Visibility
from cpswm.simulation.memory import SimulationMemory
from cpswm.simulation.runner import SimulationController, run_episode
from cpswm.simulation.scenarios import CONDITIONS, make_scenario
from cpswm.simulation.world import REGIONS, EventWorld, MujocoWorld


def observation(**kwargs):
    return replace(
        Observation(
            "episode",
            "source",
            "event",
            0,
            0,
            "target",
            Visibility.OBSERVED,
            "left",
            (("owner", 1.0),),
        ),
        **kwargs,
    )


@pytest.mark.parametrize("arm", sorted(SimulationMemory.ARMS))
def test_six_cases_keep_memory_feedback_and_expected_failures(arm):
    for condition in CONDITIONS:
        result = run_episode(make_scenario(condition), arm)
        expected = not (
            arm == "ordinary_memory" and condition in {"identity_correction", "delayed_attribution"}
        )
        assert result["evaluation"]["task_success"] == expected
        assert result["memory"]["event_count"] > 4
        assert 1 <= result["inspection_count"] <= 3
        assert result["memory"]["current_location"] == result["final_observed_location"]
        if condition == "execution_failure":
            assert result["execution_outcomes"] == ["failed", "succeeded"]
        if arm.startswith("native"):
            assert result["memory"]["particles"] == 24
            assert len(result["memory"]["operators"]) == 7


def test_real_native_core_and_factorized_control_have_matching_input_and_budget():
    scenario = make_scenario("delayed_attribution")
    memories = [
        SimulationMemory(scenario.episode_id, tuple(REGIONS), arm)
        for arm in ("native_joint", "native_factorized")
    ]
    for memory in memories:
        for obs in (*scenario.history, *scenario.corrections):
            memory.ingest(obs, obs.available_at)
        memory.runtime.verify_internal_contracts()
        assert memory.destination() == "left"
    for a, b in zip(
        memories[0].runtime.fairness_receipts, memories[1].runtime.fairness_receipts, strict=True
    ):
        assert a.robot_visible_input_sha256 == b.robot_visible_input_sha256
        assert a.target_score_evaluations == b.target_score_evaluations == 24


@pytest.mark.parametrize(
    "change",
    [
        {"episode_id": "other"},
        {"object_id": "other"},
        {"available_at": 1},
        {"location": "unmapped"},
        {"revises": "missing"},
    ],
)
def test_bad_evidence_is_rejected_without_mutation(change):
    m = SimulationMemory("episode", tuple(REGIONS), "source_replay")
    before = m.audit()
    with pytest.raises(ValueError):
        m.ingest(observation(**change), 0)
    assert m.audit() == before and not m.sources


def test_duplicate_and_disguised_duplicate_rejected():
    m = SimulationMemory("episode", tuple(REGIONS), "source_replay")
    m.ingest(observation(), 0)
    before = m.audit()
    for obs in [observation(), observation(source_id="different-source")]:
        with pytest.raises(ValueError):
            m.ingest(obs, 0)
        assert m.audit() == before


def test_failed_native_conversion_is_atomic(monkeypatch):
    m = SimulationMemory("episode", tuple(REGIONS))
    before = m.audit()

    def fail(_):
        raise RuntimeError("inference unavailable")

    monkeypatch.setattr(m, "_rebuild_native", fail)
    with pytest.raises(RuntimeError):
        m.ingest(observation(), 0)
    assert m.audit() == before and not m.sources and not m.active_sources


def test_predictions_and_robot_actions_do_not_train_owner_habits():
    m = SimulationMemory("episode", tuple(REGIONS))
    m.ingest(observation(), 0)
    before = m.destination_distribution()
    for tick, extra in enumerate(
        [
            {"visibility": Visibility.PREDICTED},
            {"robot_generated": True},
        ],
        1,
    ):
        m.ingest(
            observation(
                source_id=str(tick),
                event_id=str(tick),
                occurred_at=tick,
                available_at=tick,
                location="right",
                **extra,
            ),
            tick,
        )
    assert m.destination_distribution() == before
    assert m.runtime.step_index == 1


def test_correction_chain_and_restore_rebuild_same_posterior():
    m = SimulationMemory("episode", tuple(REGIONS))
    first = observation()
    m.ingest(first, 0)
    before = m.destination_distribution()
    second = replace(
        first, source_id="rev2", revises="source", available_at=2, actors=(("guest", 1.0),)
    )
    m.ingest(second, 2)
    assert m.destination_distribution() != before
    third = replace(first, source_id="rev3", revises="rev2", available_at=3)
    m.ingest(third, 3)
    # New source IDs may change sampling; deterministic one-actor support gives exact readout.
    assert m.destination_distribution() == pytest.approx(before)
    assert len(m.records) == 1 and len(m.sources) == 3
    m.runtime.verify_internal_contracts()


def test_ordinary_memory_can_receive_revision_chains_without_applying_them():
    m = SimulationMemory("episode", tuple(REGIONS), "ordinary_memory")
    m.ingest(observation(), 0)
    before = m.destination_distribution()
    m.ingest(
        observation(source_id="rev2", revises="source", available_at=1, actors=(("guest", 1.0),)), 1
    )
    m.ingest(observation(source_id="rev3", revises="rev2", available_at=2), 2)
    assert len(m.sources) == 3 and m.destination_distribution() == before


def test_late_correction_does_not_replace_current_physical_location():
    m = SimulationMemory("episode", tuple(REGIONS), "source_replay")
    m.ingest(observation(), 0)
    m.ingest(
        observation(
            source_id="current",
            event_id="current",
            occurred_at=4,
            available_at=4,
            location="center",
            robot_generated=True,
        ),
        4,
    )
    m.ingest(
        observation(source_id="rev", revises="source", available_at=6, actors=(("guest", 1.0),)), 6
    )
    assert m.current_location == "center"


def test_revision_cancels_old_command_and_stale_dispatch_is_rejected():
    c = SimulationController("episode", "source_replay")
    c.observe(observation(), 0)
    stale = c.plan()
    c.observe(observation(source_id="rev", revises="source", available_at=1, location="right"), 1)
    assert c.queue.pending is None
    assert c.queue.history[-1]["event"] == "cancelled"
    with pytest.raises(ValueError):
        c.queue.validate(stale, c.memory.revision)
    assert c.plan().destination == "right"


def test_fully_reconstructed_false_success_is_not_an_owned_execution_receipt():
    q, w = CommandQueue("episode"), EventWorld("episode")
    command = q.submit("target", "left", "revision")
    feedback = w.execute(command, 2, fail=True)
    forged = replace(
        feedback, status="succeeded", observation=replace(feedback.observation, location="left")
    )
    # This forgery has internally consistent public fields, but no owned receipt.
    with pytest.raises(ValueError):
        w.validate_feedback(command, forged)
    w.validate_feedback(command, feedback)
    q.complete(command, feedback, "revision")
    assert q.history[-1]["feedback"]["status"] == "failed"
    with pytest.raises(ValueError):
        w.execute(command, 3)
    with pytest.raises(ValueError):
        q.complete(command, feedback, "revision")


def test_success_cannot_be_inferred_from_command_or_predicted_location():
    q, w = CommandQueue("episode"), EventWorld("episode")
    command = q.submit("target", "left", "revision")
    feedback = w.execute(command, 2)
    predicted = replace(
        feedback, observation=replace(feedback.observation, visibility=Visibility.PREDICTED)
    )
    with pytest.raises(ValueError):
        q.complete(command, predicted, "revision")
    assert q.pending == command and not q.executed
    q.complete(command, feedback, "revision")


def test_evaluator_truth_changes_score_only_not_agent_behaviour():
    original = make_scenario("stable")
    a = run_episode(original, "native_joint")
    b = run_episode(replace(original, expected_destination="right"), "native_joint")
    assert a["journal"] == b["journal"]
    assert a["command_history"] == b["command_history"]
    assert a["evaluation"] != b["evaluation"]


def test_no_real_robot_backend_and_no_output_overwrite(tmp_path):
    scenario = make_scenario("stable")
    with pytest.raises(ValueError):
        run_episode(scenario, "source_replay", "real_robot")
    run_episode(scenario, "source_replay", output=tmp_path / "run")
    with pytest.raises(FileExistsError):
        run_episode(scenario, "source_replay", output=tmp_path / "run")


def test_failed_feedback_commit_recovers_without_reexecuting(monkeypatch):
    c = SimulationController("episode", "native_joint")
    c.observe(observation(), 0)
    w = EventWorld("episode")
    original = c.memory._rebuild_native

    def fail(_):
        raise RuntimeError("temporary inference failure")

    monkeypatch.setattr(c.memory, "_rebuild_native", fail)
    with pytest.raises(RuntimeError):
        c.execute(w, 3)
    assert w.control_steps == 1 and c.pending_outcome is not None
    assert c.queue.pending is not None and not c.memory.feedback
    with pytest.raises(ValueError):
        c.observe(observation(source_id="new", event_id="new"), 4)
    monkeypatch.setattr(c.memory, "_rebuild_native", original)
    feedback = c.execute(w, 5)
    assert feedback.status == "succeeded" and c.pending_outcome is None
    assert w.control_steps == 1 and len(c.memory.feedback) == 1
    assert c.memory.current_location == "left"


def test_feedback_cannot_predate_its_command():
    q, w = CommandQueue("episode"), EventWorld("episode")
    command = q.submit("target", "left", "revision", tick=10)
    with pytest.raises(ValueError):
        q.complete(command, w.execute(command, 9), "revision")
    assert q.pending == command
    assert w.control_steps == 0


def test_actual_mujoco_integration_moves_and_failed_command_does_not_teleport():
    pytest.importorskip("mujoco", reason="optional physics backend; event tests still run")
    w = MujocoWorld("episode")
    q = CommandQueue("episode")
    command = q.submit("target", "left", "r1")
    failed = w.execute(command, 1, fail=True)
    q.complete(command, failed, "r1")
    assert failed.status == "failed" and failed.observation.location == "center"
    command = q.submit("target", "left", "r2")
    succeeded = w.execute(command, 2)
    assert succeeded.status == "succeeded" and succeeded.control_steps == 250
    assert w.data.time == pytest.approx(2.0)
    assert len(w.trajectory) == 50 and w.data.qpos[0] < -0.25
    w.close()
