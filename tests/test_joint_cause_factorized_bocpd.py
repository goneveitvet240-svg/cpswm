"""Tests for the real joint CF-BOCPD (结构二 §4.7#2) and its write gate.

These pin the two properties that separate it from the independent-per-cause
baseline in ``cause_factorized_bocpd`` (kept as the "多独立 BOCPD" control):

* one coupled, jointly normalized posterior over (run length, cause);
* a cause-specific reset matrix that lets an owner-habit change reset only the
  habit block while observation/actor blocks carry forward — and a write gate
  that only opens the habit long-term block for a habit-attributed change.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from cpswm.world_model.habits_transitions import (
    CauseGatedHabitConsolidation,
    CauseResetMatrix,
    CauseSignalFrame,
    ChangeCause,
    JointCauseFactorizedBOCPD,
)

BASE = datetime(2026, 8, 1, tzinfo=UTC)


def _frames(habit_levels, *, obs=0.2, actor=0.2, noise=0.1):
    """A stream where only the habit signal moves unless overridden."""

    return tuple(
        CauseSignalFrame(
            timestamp=BASE + timedelta(days=index),
            signals={
                ChangeCause.OBSERVATION: obs,
                ChangeCause.ACTOR: actor,
                ChangeCause.HABIT: level,
                ChangeCause.NOISE: noise,
            },
        )
        for index, level in enumerate(habit_levels)
    )


# --- coupled joint posterior --------------------------------------------------


def test_joint_posterior_is_one_coupled_normalized_distribution():
    model = JointCauseFactorizedBOCPD()
    result = model.run(_frames([0.2, 0.2, 0.2, 0.9, 0.9]), warmup_steps=1)
    for snapshot in result.snapshots:
        total = sum(snapshot.joint_run_length_cause_posterior.values())
        assert total == pytest.approx(1.0, abs=1e-9)
        assert sum(snapshot.joint_run_length_cause_set_posterior.values()) == pytest.approx(
            1.0, abs=1e-9
        )
        assert sum(snapshot.active_regime_cause_set_posterior.values()) == pytest.approx(
            1.0, abs=1e-9
        )
        # Fix 1/2: the three step events partition the mass, and every field is
        # accounted from the same pruned+renormalized beam.
        partition = (
            snapshot.continue_probability
            + snapshot.segment_change_probability
            + snapshot.transient_noise_probability
        )
        assert partition == pytest.approx(1.0, abs=1e-9)


# --- selective reset ----------------------------------------------------------


def test_habit_change_is_attributed_to_habit_not_observation():
    model = JointCauseFactorizedBOCPD()
    result = model.run(_frames([0.2, 0.2, 0.2, 0.9, 0.9, 0.9]), warmup_steps=2)
    assert result.detected_change_time_by_cause[ChangeCause.HABIT] is not None
    # The surprise is explained away by the habit block, so no other cause fires.
    assert result.detected_change_time_by_cause[ChangeCause.OBSERVATION] is None
    assert result.detected_change_time_by_cause[ChangeCause.ACTOR] is None
    assert (
        result.peak_change_cause_probability[ChangeCause.HABIT]
        > result.peak_change_cause_probability[ChangeCause.OBSERVATION]
    )


def test_reset_matrix_resets_only_the_habit_block_on_a_habit_change():
    model = JointCauseFactorizedBOCPD()
    result = model.run(_frames([0.2, 0.2, 0.2, 0.9, 0.9, 0.9, 0.9]), warmup_steps=2)
    final = result.snapshots[-1].block_reference
    # Habit block tracked the new regime; observation/actor blocks did not move.
    assert final[ChangeCause.HABIT] > 0.6
    assert final[ChangeCause.OBSERVATION] == pytest.approx(0.2, abs=0.05)
    assert final[ChangeCause.ACTOR] == pytest.approx(0.2, abs=0.05)


def test_simultaneous_observation_and_habit_change_is_an_explicit_joint_state():
    frames = tuple(
        CauseSignalFrame(
            timestamp=BASE + timedelta(days=index),
            signals={
                ChangeCause.OBSERVATION: 0.2 if index < 3 else 0.9,
                ChangeCause.ACTOR: 0.2,
                ChangeCause.HABIT: 0.2 if index < 3 else 0.9,
                ChangeCause.NOISE: 0.1,
            },
        )
        for index in range(8)
    )
    result = JointCauseFactorizedBOCPD(beam_width=64).run(frames, warmup_steps=2)
    joint_causes = frozenset({ChangeCause.OBSERVATION, ChangeCause.HABIT})
    shift = result.snapshots[3]
    assert shift.segment_cause_set_posterior[joint_causes] > 0.9
    assert shift.segment_cause_posterior[ChangeCause.OBSERVATION] > 0.9
    assert shift.segment_cause_posterior[ChangeCause.HABIT] > 0.9
    # R_{observation,habit} is the union selective reset: both changed blocks
    # follow the new regime while the actor block is preserved.
    final = result.snapshots[-1].block_reference
    assert final[ChangeCause.OBSERVATION] > 0.7
    assert final[ChangeCause.HABIT] > 0.7
    assert final[ChangeCause.ACTOR] == pytest.approx(0.2, abs=0.05)


def test_active_regime_cause_persists_after_instantaneous_event_probability_decays():
    result = JointCauseFactorizedBOCPD(beam_width=64).run(
        _frames([0.2, 0.2, 0.2, 0.9, 0.9, 0.9, 0.9, 0.9]), warmup_steps=2
    )
    event = result.snapshots[3]
    stable_new_regime = result.snapshots[-1]
    assert event.segment_change_probability > 0.9
    assert stable_new_regime.segment_change_probability < 0.1
    assert stable_new_regime.active_regime_cause_posterior[ChangeCause.HABIT] > 0.9


def test_noise_cause_resets_no_block():
    matrix = CauseResetMatrix()
    assert matrix.blocks_reset_by(ChangeCause.NOISE) == frozenset()
    assert matrix.blocks_reset_by(ChangeCause.HABIT) == frozenset({ChangeCause.HABIT})
    assert matrix.blocks_reset_by_causes(
        frozenset({ChangeCause.OBSERVATION, ChangeCause.HABIT})
    ) == frozenset({ChangeCause.OBSERVATION, ChangeCause.HABIT})


def test_reset_matrix_rejects_a_noise_reset():
    with pytest.raises(ValueError, match="noise cause must not reset"):
        CauseResetMatrix(
            {
                ChangeCause.OBSERVATION: frozenset({ChangeCause.OBSERVATION}),
                ChangeCause.ACTOR: frozenset({ChangeCause.ACTOR}),
                ChangeCause.HABIT: frozenset({ChangeCause.HABIT}),
                ChangeCause.NOISE: frozenset({ChangeCause.HABIT}),
            }
        )


# --- write gate (task 4: cause posterior -> RGRC write control) --------------


def test_habit_change_opens_the_habit_block():
    model = JointCauseFactorizedBOCPD()
    gate = CauseGatedHabitConsolidation(change_threshold=0.3)
    result = model.run(_frames([0.2, 0.2, 0.2, 0.9, 0.9, 0.9]), warmup_steps=2)
    weights = [gate.habit_consolidation_weight(snapshot) for snapshot in result.snapshots]
    assert max(weights) > 0.0  # the habit block did open at the change
    decisions = [gate.decide(snapshot) for snapshot in result.snapshots]
    assert any(d.habit_block_writable for d in decisions)


def test_observation_change_never_opens_the_habit_block():
    model = JointCauseFactorizedBOCPD()
    gate = CauseGatedHabitConsolidation(change_threshold=0.3)
    # Only the observation signal shifts; habit stays flat.
    frames = tuple(
        CauseSignalFrame(
            timestamp=BASE + timedelta(days=index),
            signals={
                ChangeCause.OBSERVATION: 0.2 if index < 3 else 0.9,
                ChangeCause.ACTOR: 0.2,
                ChangeCause.HABIT: 0.3,
                ChangeCause.NOISE: 0.1,
            },
        )
        for index in range(6)
    )
    result = model.run(frames, warmup_steps=2)
    for snapshot in result.snapshots:
        decision = gate.decide(snapshot)
        assert not decision.habit_block_writable
        assert gate.habit_consolidation_weight(snapshot) == 0.0
    # The observation block is the one that may be rewritten.
    assert result.detected_change_time_by_cause[ChangeCause.OBSERVATION] is not None


# --- measure 1: per-hypothesis structure and beam budget ---------------------


def test_beam_width_caps_persistent_state():
    model = JointCauseFactorizedBOCPD(beam_width=8)
    result = model.run(_frames([0.2, 0.9, 0.2, 0.9, 0.2, 0.9, 0.2]), warmup_steps=1)
    for snapshot in result.snapshots:
        assert snapshot.beam_size <= 8


def test_history_conditioning_makes_a_long_stable_segment_confident():
    # A long stable habit segment should leave almost no change mass, because the
    # per-segment predictive tightens as its sufficient statistics accumulate.
    model = JointCauseFactorizedBOCPD()
    stable = model.run(_frames([0.2] * 10), warmup_steps=2)
    assert stable.snapshots[-1].segment_change_probability < 0.1
    # The habit block reference converged to the observed level.
    assert stable.snapshots[-1].block_reference[ChangeCause.HABIT] == pytest.approx(0.2, abs=0.03)


# --- measure 2: real gated write path with before/after hashing --------------


def _run_and_write(frames, proposed_update, *, change_threshold=0.3):
    from cpswm.world_model.habits_transitions import (
        CauseGatedHabitConsolidation,
        GatedHabitRegimeWriter,
        HabitRegimeParameters,
    )

    model = JointCauseFactorizedBOCPD()
    result = model.run(frames, warmup_steps=2)
    writer = GatedHabitRegimeWriter(CauseGatedHabitConsolidation(change_threshold=change_threshold))
    params = HabitRegimeParameters({"kitchen": 0.0, "desk": 0.0})
    initial_hash = params.parameter_hash()
    for snapshot in result.snapshots:
        params, _ = writer.propose_habit_update(params, snapshot, proposed_update)
    return writer, params, initial_hash


def _single_signal_shift(cause, *, days=7, low=0.2, high=0.9):
    def level(index, target):
        base = {
            ChangeCause.OBSERVATION: 0.2,
            ChangeCause.ACTOR: 0.2,
            ChangeCause.HABIT: 0.3,
            ChangeCause.NOISE: 0.1,
        }
        base[target] = low if index < 3 else high
        return base

    return tuple(
        CauseSignalFrame(timestamp=BASE + timedelta(days=index), signals=level(index, cause))
        for index in range(days)
    )


@pytest.mark.parametrize("cause", [ChangeCause.OBSERVATION, ChangeCause.ACTOR, ChangeCause.NOISE])
def test_non_habit_shift_leaves_habit_parameters_byte_identical(cause):
    writer, params, initial_hash = _run_and_write(_single_signal_shift(cause), {"kitchen": 1.0})
    # Every write attempt was rejected and no audit changed the hash.
    assert all(not audit.accepted for audit in writer.audit_log)
    assert all(not audit.parameters_changed for audit in writer.audit_log)
    # The long-term habit parameters are completely, byte-for-byte unchanged.
    assert params.parameter_hash() == initial_hash


def test_habit_shift_does_write_habit_parameters():
    writer, params, initial_hash = _run_and_write(
        _frames([0.2, 0.2, 0.2, 0.9, 0.9, 0.9]), {"kitchen": 1.0}
    )
    assert any(audit.accepted and audit.parameters_changed for audit in writer.audit_log)
    assert params.parameter_hash() != initial_hash
    accepted = [audit for audit in writer.audit_log if audit.accepted]
    assert all(audit.attributed_cause is ChangeCause.HABIT for audit in accepted)


# --- noise refinement: transient-outlier state (review 2026-08-21) ------------


def _burst_frames():
    """Stable habit at 0.2, a one-day burst on day 5, then recovery."""

    def signals(index):
        burst = index == 5
        return {
            ChangeCause.OBSERVATION: 0.2,
            ChangeCause.ACTOR: 0.2,
            ChangeCause.HABIT: 0.9 if burst else 0.2,
            ChangeCause.NOISE: 0.85 if burst else 0.1,
        }

    return tuple(
        CauseSignalFrame(timestamp=BASE + timedelta(days=index), signals=signals(index))
        for index in range(10)
    )


def test_noise_burst_raises_noise_cause_posterior():
    model = JointCauseFactorizedBOCPD()
    result = model.run(_burst_frames(), warmup_steps=2)
    burst = result.snapshots[5]
    assert burst.transient_noise_probability > 0.5


def test_noise_burst_does_not_raise_habit_observation_or_actor():
    model = JointCauseFactorizedBOCPD()
    burst = model.run(_burst_frames(), warmup_steps=2).snapshots[5]
    # The burst is explained by transient noise, not by a segment change: the
    # substantive segment-change mass stays well below the noise mass.
    assert burst.transient_noise_probability > burst.segment_change_probability
    for cause in (ChangeCause.HABIT, ChangeCause.OBSERVATION, ChangeCause.ACTOR):
        segment_score = burst.segment_change_probability * burst.segment_cause_posterior.get(
            cause, 0.0
        )
        assert segment_score < burst.transient_noise_probability


def test_noise_burst_leaves_all_long_term_parameters_unchanged():
    from cpswm.world_model.habits_transitions import (
        CauseGatedHabitConsolidation,
        GatedHabitRegimeWriter,
        HabitRegimeParameters,
    )

    model = JointCauseFactorizedBOCPD()
    result = model.run(_burst_frames(), warmup_steps=2)
    writer = GatedHabitRegimeWriter(CauseGatedHabitConsolidation(change_threshold=0.3))
    params = HabitRegimeParameters({"kitchen": 0.0, "desk": 0.0})
    initial_hash = params.parameter_hash()
    for snapshot in result.snapshots:
        params, _ = writer.propose_habit_update(params, snapshot, {"kitchen": 1.0})
    assert all(not audit.accepted for audit in writer.audit_log)
    assert params.parameter_hash() == initial_hash


def test_regime_recovers_after_noise_disappears():
    model = JointCauseFactorizedBOCPD()
    burst = model.run(_burst_frames(), warmup_steps=2)
    # Control: the same stream with no burst at all.  Recovery means the burst
    # left the habit regime as if it never happened, so the final habit block
    # reference matches the control (up to the one outlier day it did not absorb).
    control = model.run(_frames([0.2] * 10), warmup_steps=2)
    assert burst.snapshots[-1].block_reference[ChangeCause.HABIT] == pytest.approx(
        control.snapshots[-1].block_reference[ChangeCause.HABIT], abs=0.01
    )
