"""Adversarial round one: chronology, dependency roots, atomic failure, forgery."""

import sys

# Pytest discovers the imported fixture; test arguments intentionally name it.
# ruff: noqa: F811
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "tools")]
from test_native_joint_full_replay import corrected_checkpoint, restore_copy  # noqa: E402,F401
from test_native_joint_production import JointFixture  # noqa: E402

from cpswm.system.structure_two_particle_workspace import native_content_sha256  # noqa: E402


class ClockFixture(JointFixture):
    def __init__(self):
        super().__init__()
        self.contexts = []

    def produce(self, context):
        self.contexts.append(deepcopy(context))
        return super().produce(context)


def test_replay_knowledge_clock_covers_feedback_arrival(corrected_checkpoint, tmp_path):
    producer = ClockFixture()
    stream, store, _ = restore_copy(corrected_checkpoint, tmp_path / "clock.db", producer)
    try:
        assert stream._last_arrival > stream._last_cutoff
        arrival = stream._last_arrival
        stream.replay_joint_posterior()
        assert producer.contexts and all(c.cutoff == arrival for c in producer.contexts)
        assert stream._last_cutoff == arrival
        assert all(c.source.producer_context[1].basis_sha256 for c in producer.contexts)
        # A command cannot backdate the newly incorporated correction.
        from test_joint_camera_policy import problem_for

        with pytest.raises(ValueError, match="predates"):
            stream.prepare_posterior_observation(
                problem_for(stream, arrival), decision_time=arrival - timedelta(seconds=1)
            )
        assert not stream._observation_commands
    finally:
        store.close()


def test_initial_model_state_cannot_be_resealed_as_a_new_prior(corrected_checkpoint, tmp_path):
    stream, store, producer = restore_copy(corrected_checkpoint, tmp_path / "initial.db")
    try:
        original = native_content_sha256(vars(stream._system.core._particle_workspace))
        stream._joint_initial_state["calls"] += 100
        before = producer.checkpoint_state()
        with pytest.raises(ValueError, match="initial-state binding"):
            stream.replay_joint_posterior()
        assert producer.checkpoint_state() == before
        assert native_content_sha256(vars(stream._system.core._particle_workspace)) == original
    finally:
        store.close()


class IncorrectRestoreFixture(JointFixture):
    bad_restore = False

    def restore_state(self, state):
        if self.bad_restore:
            self.calls = -99
        else:
            super().restore_state(state)


def test_incorrect_restore_fails_closed_before_any_action(corrected_checkpoint, tmp_path):
    producer = IncorrectRestoreFixture()
    stream, store, _ = restore_copy(corrected_checkpoint, tmp_path / "reset.db", producer)
    try:
        original = native_content_sha256(vars(stream._system.core._particle_workspace))
        producer.bad_restore = True
        with pytest.raises(ValueError, match="rollback did not restore"):
            stream.replay_joint_posterior()
        assert native_content_sha256(vars(stream._system.core._particle_workspace)) == original
        with pytest.raises(RuntimeError, match="durable state failed"):
            stream.current_joint_decision_view()
        assert not stream._observation_commands
    finally:
        store.close()


def test_missing_live_source_cannot_shrink_replay_history(corrected_checkpoint, tmp_path):
    stream, store, producer = restore_copy(corrected_checkpoint, tmp_path / "missing.db")
    try:
        core = stream._system.core
        source = next(
            s
            for s in core._particle_workspace.posterior_sources.values()
            if s.history_after.latest.revision_id in core._observed_events
        )
        del core._particle_workspace.posterior_sources[source.source_id]
        before = producer.checkpoint_state()
        with pytest.raises(ValueError, match="acceptance anchors"):
            stream.replay_joint_posterior()
        assert producer.checkpoint_state() == before
        assert core._particle_workspace.invalidated_revisions
    finally:
        store.close()


def test_complete_resealed_archived_generation_blocks_native_and_stream_readout(
    corrected_checkpoint, tmp_path
):
    stream, store, _ = restore_copy(corrected_checkpoint, tmp_path / "archive.db")
    try:
        stream.replay_joint_posterior()
        core = stream._system.core
        generation = core._particle_replay_generations[-1]
        altered = deepcopy(generation.old_workspace)
        altered.invalidated_revisions.clear()
        forged = replace(generation, old_workspace=altered, removed_revision_ids=())
        assert forged.content_sha256 != generation.content_sha256  # complete, internally hashable
        core._particle_replay_generations = (*core._particle_replay_generations[:-1], forged)
        for read in (stream.current_joint_decision_view, core.prepared_particle_location_marginal):
            with pytest.raises(ValueError, match="archive differs"):
                read()
        assert not stream._observation_commands
    finally:
        store.close()
