"""Executable audit counterexamples; all fixtures use already-opened D0 seeds."""

from __future__ import annotations

import gzip
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from cpswm.contracts import ProjectTwoDatasetSplit
from cpswm.system.evaluation_operations import structure_two_comparison_audit as audit
from cpswm.system.reproducibility import content_sha256, content_uuid

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def material():
    dataset = (
        audit.D0SyntheticReplayExperimentConfig.load(ROOT / audit.DATA_CONFIG)
        .build_adapter()
        .build()
    )
    training = audit.base._learned_training_material(dataset)
    model = audit.base._fit_learned_model(
        training, {"base_width": 8, "learning_rate": 0.05, "l2": 0.0}
    )
    return dataset, training, model


@pytest.fixture
def example(material):
    dataset, training, model = material
    episode = dataset.visible_episodes(ProjectTwoDatasetSplit.TEST)[0]
    states = audit.make_states(episode, model, training, 1.0, 0.2)
    schedule = audit.base._episode_schedule_commitment(episode)
    for index, step in enumerate(episode.steps):
        packet = audit.base._packet_for_step(episode, step, schedule_commitment_sha256=schedule)
        for state in states:
            state.consume_matched_ciav_packet(packet, step, step_index=index)
        if packet.realized_detected_location_id is not None:
            return episode, step, index, packet, states
    raise AssertionError("fixture has no detection")


@pytest.mark.parametrize(
    "left,right,expected",
    [(0, 0, "both_correct"), (0, 1, "p5_wins"), (1, 0, "p5_loses"), (1, 1, "both_wrong")],
)
def test_error_partition(left, right, expected):
    assert audit.category(left, right) == expected
    with pytest.raises(ValueError, match="binary"):
        audit.category(2, 0)


@pytest.mark.parametrize("arm_index", range(3))
def test_real_observation_fixed_legal_search_posterior_changes_action(example, arm_index):
    _, step, index, packet, states = example
    posterior = states[arm_index].predict_location_posteriors(packet)
    result = audit.sensitivity(posterior, step, index, content_uuid(audit.AUDIT_ID, "test"))
    assert result["search_changed"] and result["put_back_unchanged"]
    with pytest.raises(ValueError, match="sum to one"):
        audit.with_distributions(posterior, current=dict.fromkeys(posterior.location_support, 0.0))


def test_amg_native_search_order_is_discarded_by_adapter(example, monkeypatch):
    _, step, index, packet, states = example
    amg = states[2]
    run_id = content_uuid(audit.AUDIT_ID, "test")
    before = audit.decode(amg.predict_location_posteriors(packet), step, index, run_id)
    native = amg.state.predict()
    swapped = replace(native, search_order=tuple(reversed(native.search_order)))
    assert swapped.search_order[0] != native.search_order[0]
    monkeypatch.setattr(amg.state, "predict", lambda: swapped)
    after = audit.decode(amg.predict_location_posteriors(packet), step, index, run_id)
    assert [x.location_id for x in before.search_plan] == [x.location_id for x in after.search_plan]
    # With exactly the same decoder and support, a rank-to-mass diagnostic can see it.
    mass = audit.base._normalise(
        {
            loc: float(len(swapped.search_order) - rank)
            for rank, loc in enumerate(swapped.search_order)
        },
        amg.locations,
    )
    changed = audit.decode(
        audit.with_distributions(amg.predict_location_posteriors(packet), current=mass),
        step,
        index,
        run_id,
    )
    assert changed.search_plan[0].location_id == swapped.search_order[0]


def test_learned_joint_changes_do_not_route_into_search_but_habit_head_is_live(example):
    _, step, index, packet, states = example
    learned = states[1]
    run_id = content_uuid(audit.AUDIT_ID, "test")
    before = learned.predict_location_posteriors(packet)
    learned.last_joint = np.eye(9)[-1]
    after = learned.predict_location_posteriors(packet)
    assert before.current_location_distribution == after.current_location_distribution
    target = next(
        loc
        for loc in learned.locations
        if loc != audit.decode(before, step, index, run_id).put_back_action.location_id
    )
    learned.habit_counts[target] += 100
    changed = audit.decode(learned.predict_location_posteriors(packet), step, index, run_id)
    assert changed.put_back_action.location_id == target
    assert changed.search_plan[0].location_id == packet.realized_detected_location_id


def test_learned_conditional_head_axis_order_and_update_are_wired(example):
    _, step, index, packet, states = example
    learned = states[1]
    expected = float(learned.last_joint @ learned.theta.reshape(-1))
    assert 0 <= expected <= 1
    old_count = learned.habit_counts[packet.realized_detected_location_id]
    # The same legitimate packet is sufficient for an isolated recurrence test.
    learned.consume_matched_ciav_packet(packet, step, step_index=index)
    added = float(learned.last_joint @ learned.theta.reshape(-1))
    assert learned.habit_counts[packet.realized_detected_location_id] == pytest.approx(
        old_count + added
    )
    assert learned.seen_counts[packet.realized_detected_location_id] >= 2
    assert np.isclose(learned.last_joint.sum(), 1.0)


def test_feature_bottleneck_ignores_ordered_role_evidence(material):
    dataset, _, _ = material
    episode = next(
        e
        for e in dataset.visible_episodes(ProjectTwoDatasetSplit.TEST)
        if any(s.ordered_role_evidence is not None for s in e.steps)
    )
    index, step = next(
        (i, s) for i, s in enumerate(episode.steps) if s.ordered_role_evidence is not None
    )
    no_role = type(step).model_validate(step.model_dump() | {"ordered_role_evidence": None})
    args = {"step_index": index, "last_observed": None, "seen_counts": {}}
    assert audit.base._feature_row(episode, step, **args) == audit.base._feature_row(
        episode, no_role, **args
    )


def test_full_episode_support_contains_future_visible_locations(material):
    dataset, _, _ = material
    episode = dataset.visible_episodes(ProjectTwoDatasetSplit.TEST)[0]
    assert not episode.known_location_ids
    index = next(i for i, s in enumerate(episode.steps) if s.after is not None)
    prefix = episode.model_copy(update={"steps": episode.steps[: index + 1]})
    assert set(audit.base._locations(prefix)) < set(audit.base._locations(episode))


def test_training_material_reads_only_training_truth(material, monkeypatch):
    dataset, training, _ = material
    original = dataset.truth_for
    allowed = {e.episode_id for e in dataset.visible_episodes(ProjectTwoDatasetSplit.TRAIN)}
    accessed = set()

    def checked(episode_id):
        assert episode_id in allowed
        accessed.add(episode_id)
        return original(episode_id)

    # Patch class method: dataset itself is immutable.
    monkeypatch.setattr(type(dataset), "truth_for", lambda self, episode_id: checked(episode_id))
    fresh = audit.base._learned_training_material(dataset)
    assert accessed == allowed == set(training.training_episode_ids)
    np.testing.assert_array_equal(fresh.raw, training.raw)


def test_truth_barrier_rejects_early_duplicate_and_wrong_step(example):
    episode, step, index, packet, states = example
    gate = audit.CommitBarrier(episode.episode_id, step.step_id)
    accesses = []
    fake_dataset = SimpleNamespace(
        truth_for=lambda key: (
            accesses.append(key) or SimpleNamespace(truth_by_step={step.step_id: "truth"})
        )
    )
    with pytest.raises(ValueError, match="all three"):
        gate.release(fake_dataset)
    assert not accesses
    run_id = content_uuid(audit.AUDIT_ID, "test")
    for state in states:
        posterior = state.predict_location_posteriors(packet)
        action = audit.decode(posterior, step, index, run_id)
        gate.commit(posterior, action)
        with pytest.raises(ValueError, match="duplicate"):
            gate.commit(posterior, action)
    assert gate.release(fake_dataset) == "truth"
    assert accesses == [episode.episode_id]
    with pytest.raises(ValueError, match="all three"):
        gate.release(fake_dataset)
    bad = audit.CommitBarrier(episode.episode_id, content_uuid(audit.AUDIT_ID, "wrong-step"))
    with pytest.raises(ValueError, match="mismatched"):
        bad.commit(posterior, action)


def test_episode_diagnostic_partition_and_search_equality(material):
    dataset, training, model = material
    episode = dataset.visible_episodes(ProjectTwoDatasetSplit.TEST)[0]
    rows, _ = audit.evaluate_episode(
        dataset, episode, audit.make_states(episode, model, training, 1.0, 0.2)
    )
    summary = audit.aggregate(rows)
    assert sum(summary["overall"]["categories"].values()) == 32
    assert summary["search_three_arm_distribution_equal_steps"] == 32
    assert all(r["truth_release"] == "after_all_three_and_alternative_action_commits" for r in rows)
    assert (
        rows[-1]["raw_state"]["learned_habit_counts"]
        != rows[0]["raw_state"]["learned_habit_counts"]
    )
    assert any(r["arms"][audit.P5]["closure"].startswith("negative") for r in rows)


def test_save_refuses_overwrite_and_verifier_rejects_semantic_tampering(tmp_path):
    rows = [{"arms": {audit.P5: {"put_back_error": 0, "provenance": {"run": "first"}}}}]
    payload = {
        key: {}
        for key in (
            "audit_id",
            "data_status",
            "source_bindings",
            "selection",
            "summary",
            "retained_score_mismatches",
            "split_episode_ids",
            "training",
        )
    }
    payload["semantic_steps_sha256"] = content_sha256(audit._semantic_rows(rows))
    audit.save(tmp_path, payload, rows, {})
    audit.verify(tmp_path, payload, rows)
    with pytest.raises(FileExistsError, match="overwrite"):
        audit.save(tmp_path, payload, rows, {})
    rows[0]["arms"][audit.P5]["put_back_error"] = 1
    (tmp_path / "steps.jsonl.gz").write_bytes(gzip.compress((json.dumps(rows[0]) + "\n").encode()))
    with pytest.raises(ValueError, match="semantic commitment"):
        audit.verify(tmp_path, payload, rows)


def test_unavailable_hardware_is_reported_without_losing_diagnostic(monkeypatch):
    import subprocess

    monkeypatch.setattr(audit.platform, "system", lambda: "Darwin")

    def unavailable(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "sysctl")

    monkeypatch.setattr(audit.subprocess, "check_output", unavailable)
    hardware = audit.hardware_info()
    assert hardware["machdep.cpu.brand_string"] == "unavailable: CalledProcessError"
    assert hardware["hw.memsize"] == "unavailable: CalledProcessError"


def test_initial_amg_fallback_encodes_ignorance_as_a_different_point_mass(material):
    dataset, training, model = material
    episode = next(
        e
        for e in dataset.visible_episodes(ProjectTwoDatasetSplit.TEST)
        if e.steps[0].after is None
        and min(audit.base._locations(e), key=str) != audit.base._locations(e)[0]
    )
    states = audit.make_states(episode, model, training, 1.0, 0.2)
    step = episode.steps[0]
    packet = audit.base._packet_for_step(
        episode, step, schedule_commitment_sha256=audit.base._episode_schedule_commitment(episode)
    )
    actions = []
    for state in states:
        state.consume_matched_ciav_packet(packet, step, step_index=0)
        posterior = state.predict_location_posteriors(packet)
        actions.append(audit.decode(posterior, step, 0, content_uuid(audit.AUDIT_ID, "initial")))
    assert actions[0].put_back_action.location_id == min(states[0].locations, key=str)
    assert actions[2].put_back_action.location_id == states[2].locations[0]
    assert actions[0].put_back_action.location_id != actions[2].put_back_action.location_id


def test_verifier_rejects_forged_positive_gate_even_with_intact_steps(tmp_path):
    rows = [{"arms": {}}]
    payload = {
        "semantic_steps_sha256": content_sha256(audit._semantic_rows(rows)),
        "signal_gate_retained_not_reselected": {"passed": False},
    }
    audit.save(tmp_path, payload, rows, {})
    forged = json.loads((tmp_path / "audit.json").read_text())
    forged["signal_gate_retained_not_reselected"]["passed"] = True
    (tmp_path / "audit.json").write_text(json.dumps(forged))
    with pytest.raises(ValueError, match="signal_gate"):
        audit.verify(tmp_path, payload, rows)


def test_same_location_full_p5_observes_but_does_not_commit_long_term(example):
    _, _, _, packet, states = example
    p5 = states[0]
    assert p5.full_p5_transition_count > 0
    assert p5.all_seven_primary_trace_count == p5.full_p5_transition_count
    assert p5.system.core._observed_events
    assert p5.system.core._fast_action_events
    assert not p5.system.core._committed_events
    posterior = p5.predict_location_posteriors(packet)
    assert posterior.current_location_distribution
