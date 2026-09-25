"""Second adversarial lens: repeated correction, arithmetic, disk and process boundaries."""

# Pytest discovers this fixture through injection, not a direct Python call.
# ruff: noqa: F811
import json
import subprocess
import sys
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "tools")]
from run_correction_replay_comparison import (  # noqa: E402
    NEGATIVE_ABSENT_LIKELIHOOD,
    NEGATIVE_PRESENT_LIKELIHOOD,
    NEGATIVE_SEARCH_OUTCOME,
    OracleProducer,
    apply_feedback,
    build_execution_feedback_bundle,
)
from test_native_joint_full_replay import corrected_checkpoint, restore_copy  # noqa: E402,F401
from test_native_joint_production import JointFixture  # noqa: E402

from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput  # noqa: E402
from cpswm.system.structure_two_particle_workspace import native_content_sha256  # noqa: E402


def test_second_real_withdrawal_rebuilds_all_three_blocks_from_initial_model(
    corrected_checkpoint, tmp_path
):
    stream, store, producer = restore_copy(corrected_checkpoint, tmp_path / "twice.db")
    try:
        stream.replay_joint_posterior()
        first = stream.current_joint_decision_view()
        from test_continuous_camera_collection import Camera, Model

        from cpswm.system.continuous_camera_collection import collect_posterior_step

        when = stream._last_arrival + timedelta(seconds=1)
        model = Model(stream)
        problem = model.problem(first, stream.visible_prefix(cutoff=when), decision_time=when)
        _, old_command = stream.prepare_posterior_observation(problem, decision_time=when)
        assert old_command is not None
        core = stream._system.core
        # A new, live source, not an artificial invalidation bit.
        rid, event = next(iter(core._committed_events.items()))
        probe = corrected_checkpoint[1][0]
        probe.system = stream._system
        bundle = build_execution_feedback_bundle(
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
        apply_feedback(stream, [bundle], stream._last_arrival + timedelta(seconds=2))
        assert rid not in core._observed_events and core._particle_workspace.invalidated_revisions
        ledger = core._hybrid_loop.ledger.export_state()
        stream.replay_joint_posterior()
        second = stream.current_joint_decision_view()
        assert second.runtime_id != first.runtime_id
        assert len(core._particle_replay_generations) == 2
        assert core._hybrid_loop.ledger.export_state() == ledger
        count = len(core._observed_events)
        assert producer.calls == count
        assert count == len(first.atoms[0].statistics.evidence_cluster_ids) - 1
        x = np.array([1.0, 0.5])
        pose = np.array([0.1, 0.2, 0.3, 0.0, 0.0, 0.0])
        from cpswm.system.evaluation_operations.structure_two_selected_method import (
            TypedParticleState,
        )

        for atom in second.atoms:
            state = TypedParticleState.model_validate_json(atom.state_json)
            index = 0 if state.ordered_actor_roles[0].actor_key == "owner" else 1
            stats = atom.statistics
            expected_alpha = np.ones(len(stats.locations))
            expected_alpha[index] += 0.2 * count
            np.testing.assert_allclose(stats.alpha, expected_alpha, atol=1e-12)
            np.testing.assert_allclose(
                stats.a, np.eye(2) + 0.8 * count * np.outer(x, x), atol=1e-12
            )
            np.testing.assert_allclose(stats.b, 0.8 * 0.3 * count * x, atol=1e-12)
            np.testing.assert_allclose(stats.information, (1 + 0.6 * count) * np.eye(6), atol=1e-12)
            np.testing.assert_allclose(stats.information_vector, 0.6 * count * pose, atol=1e-12)
        assert rid not in {r.state.revision_id for r in core._particle_workspace.records.values()}
        camera = Camera(core.current_posterior_projection_source().transition)
        action = collect_posterior_step(
            stream,
            model=model,
            executor=camera,
            decision_time=stream._last_arrival + timedelta(seconds=3),
        )
        assert camera.calls == 1 and action.command.action_id != old_command.action_id
        assert stream._observation_status[old_command.action_id].startswith("CANCELLED")
        assert old_command.action_id in stream._observation_commands
    finally:
        store.close()


def test_disk_failure_blocks_live_actions_and_restores_last_durable_generation(
    corrected_checkpoint, tmp_path, monkeypatch
):
    stream, store, _ = restore_copy(corrected_checkpoint, tmp_path / "disk.db")
    try:
        old = native_content_sha256(vars(stream._system.core._particle_workspace))
        save = store.save

        def fail(_state):
            raise OSError("injected replay checkpoint failure")

        monkeypatch.setattr(store, "save", fail)
        with pytest.raises(OSError, match="replay checkpoint"):
            stream.replay_joint_posterior()
        with pytest.raises(RuntimeError, match="durable state failed"):
            stream.current_joint_decision_view()
        recovered = ContinuousEvidenceInput.resume(
            store,
            producer=OracleProducer(),
            context_builder=corrected_checkpoint[1][4],
            joint_producer=JointFixture(),
        )
        assert native_content_sha256(vars(recovered._system.core._particle_workspace)) == old
        assert not recovered._system.core._particle_replay_generations
        assert not recovered._observation_commands
        monkeypatch.setattr(store, "save", save)
        recovered.replay_joint_posterior()
        assert len(recovered._system.core._particle_replay_generations) == 1
        assert recovered.current_joint_decision_view().atoms
    finally:
        store.close()


def test_fresh_process_recovers_replay_types_and_exact_view(corrected_checkpoint, tmp_path):
    path = tmp_path / "fresh.db"
    stream, store, producer = restore_copy(corrected_checkpoint, path)
    stream.replay_joint_posterior()
    expected = stream.current_joint_decision_view().content_sha256
    calls = producer.calls
    store.close()
    script = """
import sys, json
sys.path[:0] = ["tests", "tools"]
from test_native_joint_production import JointFixture
from run_correction_replay_comparison import OracleProducer
from cpswm.system.continuous_state_store import ContinuousStateStore
from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput
from cpswm.system.reproducibility import content_sha256
store = ContinuousStateStore(
    sys.argv[1], source_identity=content_sha256("joint-full-replay-test"),
    dependency_identity=content_sha256(sys.version),
)
producer = JointFixture()
stream = ContinuousEvidenceInput.resume(
    store, producer=OracleProducer(), context_builder=lambda *args: None,
    joint_producer=producer,
)
view = stream.current_joint_decision_view()
print(json.dumps({
    "view": view.content_sha256, "calls": producer.calls,
    "archives": len(stream._system.core._particle_replay_generations),
}))
store.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"view": expected, "calls": calls, "archives": 1}


class FalseMeasurementFixture(JointFixture):
    """Intentionally false but fully consistent trusted-fixture model output."""

    def produce(self, context):
        result = super().produce(context)
        statistics = {
            pid: replace(s, alpha=tuple(a + 100.0 for a in s.alpha))
            for pid, s in result.statistics.items()
        }
        receipts = tuple(
            r.model_copy(
                update={
                    "proposal": r.proposal.model_copy(
                        update={
                            "proposed_state": r.proposal.proposed_state.model_copy(
                                update={
                                    "statistic_state_ref": statistics[
                                        r.proposal.proposed_state.particle_id
                                    ].reference
                                }
                            )
                        }
                    )
                }
            )
            for r in result.receipts
        )
        return replace(result, statistics=statistics, receipts=receipts)


def test_complete_false_model_cannot_replace_checkpoint_producer_under_same_claimed_hash(
    corrected_checkpoint, tmp_path
):
    stream, store, _ = restore_copy(corrected_checkpoint, tmp_path / "false-model.db")
    try:
        before = native_content_sha256(vars(stream._system.core._particle_workspace))
        try:
            substituted = ContinuousEvidenceInput.resume(
                store,
                producer=OracleProducer(),
                context_builder=corrected_checkpoint[1][4],
                joint_producer=FalseMeasurementFixture(),
            )
        except ValueError as error:
            assert "implementation" in str(error) or "dependency" in str(error)
            assert native_content_sha256(vars(stream._system.core._particle_workspace)) == before
            assert not stream._observation_commands
            return
        # Exercise the complete positive forgery through real native publication;
        # reject-only tests would miss that its receipts and states are self-consistent.
        ledger = deepcopy(substituted._system.core._hybrid_loop.ledger.export_state())
        substituted.replay_joint_posterior()
        view = substituted.current_joint_decision_view()
        assert all(min(a.statistics.alpha) > 100.0 for a in view.atoms)
        assert substituted._system.core._hybrid_loop.ledger.export_state() == ledger
        pytest.fail(
            "complete false replacement model published under original claimed artifact hash"
        )
    finally:
        store.close()


def test_full_replay_preserves_original_consumed_input_schedule(corrected_checkpoint, tmp_path):
    stream, store, producer = restore_copy(corrected_checkpoint, tmp_path / "schedule.db")
    try:
        core = stream._system.core
        original = {r.state.revision_id for r in core._particle_workspace.records.values()}
        retained = original & set(core._observed_events)
        assert retained and retained < set(core._observed_events)
        assert len(original) == 12 and len(retained) == 11
        stream.replay_joint_posterior()
        actual = {r.state.revision_id for r in core._particle_workspace.records.values()}
        assert actual == retained, (
            "replay added semantic sources never consumed by the joint kernel"
        )
        assert producer.calls == len(retained)
        assert all(
            len(a.statistics.evidence_cluster_ids) == len(retained)
            for a in stream.current_joint_decision_view().atoms
        )
    finally:
        store.close()
