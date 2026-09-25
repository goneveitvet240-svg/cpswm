"""One controlled P5 + automatic joint history through late correction/recovery.

Traces the actual invalidation consequence with populated native particles. A
missing selected replay kernel is a reported blocker, never silently cleared.
This is controlled semantic input and assumed measurements, not natural vision.
"""

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from run_correction_replay_comparison import (  # noqa: E402
    NEGATIVE_ABSENT_LIKELIHOOD,
    NEGATIVE_PRESENT_LIKELIHOOD,
    NEGATIVE_SEARCH_OUTCOME,
    OracleProducer,
    apply_feedback,
    build,
    build_execution_feedback_bundle,
    ingest,
    summary,
)
from test_native_joint_production import JointFixture  # noqa: E402

from cpswm.system.conditional_revision_replay import (  # noqa: E402
    ConditionalReplayHistory,
    ConditionalReplayStep,
)
from cpswm.system.continuous_state_codec import StateCodec  # noqa: E402
from cpswm.system.continuous_state_store import ContinuousStateStore  # noqa: E402
from cpswm.system.reproducibility import content_sha256  # noqa: E402
from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput  # noqa: E402


class RecordedJointFixture(JointFixture):
    """Same explicit assumed model, now retaining its actual measurement inputs."""

    def __init__(self):
        super().__init__()
        self.replay_history = None

    def build_statistics(self, pid, parent, source, prior, measure, context):
        result = super().build_statistics(pid, parent, source, prior, measure, context)
        if self.replay_history is None:
            self.replay_history = ConditionalReplayHistory(
                prior, self.binding_sha256, measure.observation_model_id
            )
        self.replay_history = self.replay_history.append(
            ConditionalReplayStep(
                pid,
                parent.state.particle_id if parent else None,
                source.history_after.latest.revision_id,
                context.content_sha256,
                measure,
            )
        )
        return result

    def checkpoint_state(self):
        return {
            **super().checkpoint_state(),
            "conditional_history": StateCodec().dumps(self.replay_history),
        }

    def restore_state(self, state):
        super().restore_state(state)
        self.replay_history = StateCodec().loads(state["conditional_history"])


class FixedFixtureReplayModel:
    # These fixture measurements are expressly independent of prior statistics.
    # Natural/model-dependent observations must implement their own recompute.
    binding_sha256 = JointFixture.binding_sha256

    def recompute(self, step, retained_state):
        return step.measurement


def run(output: Path, seed: int):
    output.mkdir(parents=True, exist_ok=False)
    source_files = {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for folder in ("src", "tests", "tools")
        for p in sorted((ROOT / folder).rglob("*.py"))
    }
    source = content_sha256(source_files)
    joint = RecordedJointFixture()
    probe, producer, stream, store, builder = build(
        output / "online.db", seed=seed, source=source, joint_producer=joint
    )
    restored_store = None
    try:
        steps = ingest(probe, producer, stream, produce_joint=True)
        before = summary(stream)
        view = stream.current_joint_decision_view()
        records = stream._system.core._particle_workspace.records
        ancestry_depth = max(len(r.statistics.evidence_cluster_ids) for r in records.values())
        invalid_dates = {d.after.detection_time.date() for d in probe.observed_days()[:7]}
        targets = [
            (rid, e)
            for rid, e in stream._system.core._committed_events.items()
            if e.evidence.event_time.date() in invalid_dates
        ]
        if not targets:
            raise RuntimeError("fixed invalidation set has no committed target")
        bundles = [
            build_execution_feedback_bundle(
                probe,
                revision_id=rid,
                location_id=e.location_id,
                belief_snapshot_id=e.belief_snapshot_id,
                when=e.evidence.event_time,
                opportunity_id=e.evidence.observation_opportunity_id,
                outcome_distribution=NEGATIVE_SEARCH_OUTCOME,
                present_likelihood=NEGATIVE_PRESENT_LIKELIHOOD,
                absent_likelihood=NEGATIVE_ABSENT_LIKELIHOOD,
            )
            for rid, e in targets
        ]
        received = probe.observed_days()[11].after.detection_time + timedelta(hours=2)
        feedback = apply_feedback(stream, bundles, received)
        after = summary(stream)
        workspace = stream._system.core._particle_workspace
        invalidated = sorted(map(str, workspace.invalidated_revisions))
        if not invalidated:
            raise RuntimeError("this trace did not exercise populated joint invalidation")
        if any(
            rid in stream._system.core._committed_events
            or rid in stream._system.core._observed_events
            for rid, _ in targets
        ):
            raise RuntimeError("old memory contribution survived correction")

        def blocked(s):
            result = {}
            for name, operation in [
                ("produce", s.produce_joint_posterior),
                ("joint_readout", s.current_joint_decision_view),
            ]:
                try:
                    operation()
                except ValueError as error:
                    result[name] = str(error)
                else:
                    raise RuntimeError("invalidated native history was silently reused")
            return result

        rejects = blocked(stream)
        with sqlite3.connect(output / "restored.db") as dest:
            store._db.backup(dest)
        restored_store = ContinuousStateStore(
            output / "restored.db",
            source_identity=source,
            dependency_identity=content_sha256(sys.version),
        )
        restored_joint = RecordedJointFixture()
        restored = ContinuousEvidenceInput.resume(
            restored_store,
            producer=OracleProducer(),
            context_builder=builder,
            joint_producer=restored_joint,
        )
        recovered = summary(restored)
        recovered_rejects = blocked(restored)
        conditional_rows = []
        for atom in view.atoms:
            history = joint.replay_history
            replay = history.replay(
                particle_id=atom.particle_id,
                revoked_revision_ids=frozenset(workspace.invalidated_revisions),
                expected_history_sha256=history.content_sha256,
                model=FixedFixtureReplayModel(),
            )
            recovered_history = restored_joint.replay_history
            recovered_replay = recovered_history.replay(
                particle_id=atom.particle_id,
                revoked_revision_ids=frozenset(workspace.invalidated_revisions),
                expected_history_sha256=recovered_history.content_sha256,
                model=FixedFixtureReplayModel(),
            )
            if replay != recovered_replay:
                raise RuntimeError("conditional replay differs after restore")
            old = atom.statistics
            conditional_rows.append(
                {
                    "particle_id": str(atom.particle_id),
                    "removed_revisions": list(map(str, replay.removed_revisions)),
                    "retained_measurements": len(replay.measurements),
                    "recomputed_suffix_steps": len(replay.recomputed_particles),
                    "dirichlet_changed": old.alpha != replay.state.alpha,
                    "rls_changed": (old.a, old.b) != (replay.state.a, replay.state.b),
                    "gaussian_changed": (old.information, old.information_vector)
                    != (replay.state.information, replay.state.information_vector),
                    "restored_replay_equal": True,
                    "native_publication_authority": replay.native_publication_authority,
                    "ledger_write_authority": replay.ledger_write_authority,
                }
            )
        result = {
            "track": "CONTROLLED_SEMANTIC_AND_CONDITIONAL_MODELS",
            "seed": seed,
            "steps": steps,
            "before": before,
            "after": after,
            "feedback": feedback,
            "committed_targets": len(targets),
            "native_atoms_before": len(view.atoms),
            "native_records_before": len(records),
            "maximum_conditional_ancestry_depth": ancestry_depth,
            "invalidated_revisions": invalidated,
            "joint_producer_calls": joint.calls,
            "post_correction_rejections": rejects,
            "restored_rejections": recovered_rejects,
            "conditional_replay": conditional_rows,
            "restored_semantic_state_equal": after["semantic_sha256"]
            == recovered["semantic_sha256"],
            "restored_producer_state_equal": joint.checkpoint_state()
            == restored_joint.checkpoint_state(),
            "action_readout_changed": before["argmax"] != after["argmax"],
            "post_correction_joint_action_executed": False,
            "full_joint_replay_kernel_bound": False,
            "natural_semantic_transitions": 0,
            "complete_natural_closed_loop": False,
            "source_files": source_files,
            "source_unchanged": all(
                hashlib.sha256((ROOT / n).read_bytes()).hexdigest() == h
                for n, h in source_files.items()
            ),
        }
        (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        if (
            not result["source_unchanged"]
            or not result["restored_semantic_state_equal"]
            or not result["restored_producer_state_equal"]
        ):
            raise RuntimeError("recovery or source invariant failed")
        print(
            json.dumps(
                {
                    k: result[k]
                    for k in [
                        "committed_targets",
                        "native_atoms_before",
                        "maximum_conditional_ancestry_depth",
                        "invalidated_revisions",
                        "action_readout_changed",
                        "restored_semantic_state_equal",
                        "post_correction_rejections",
                    ]
                },
                indent=2,
            )
        )
    finally:
        store.close()
        if restored_store is not None:
            restored_store.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=11, choices=(7, 11, 19))
    args = parser.parse_args()
    run(args.output, args.seed)
