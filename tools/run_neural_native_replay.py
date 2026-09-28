"""Actual neural checkpoints -> native state -> correction/replay -> durable recovery.

Explicit controlled-development integration. The small training, candidate model,
semantic observations and conditional measurements are fixtures. No natural task
success, selected production architecture, six-operation kernel or calibration is
asserted by this runner. Every existing architecture arm is retained separately.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from pathlib import Path
from time import perf_counter

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "tools")]
from run_correction_replay_comparison import OracleProducer  # noqa: E402
from test_native_joint_full_replay import corrected  # noqa: E402
from test_native_neural_recovery import OpenWorldJointFixture  # noqa: E402
from test_typed_proposal_training import data  # noqa: E402

from cpswm.data_preflight.proposal_trainer import save_checkpoint, train_proposer  # noqa: E402
from cpswm.data_preflight.typed_proposal_networks import ARMS  # noqa: E402
from cpswm.system.native_neural_production import NeuralNativeProducer  # noqa: E402
from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput  # noqa: E402
from cpswm.system.structure_two_particle_workspace import native_content_sha256  # noqa: E402


def source_files():
    return {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for directory in ("src", "tests", "tools")
        for p in sorted((ROOT / directory).rglob("*.py"))
    }


def run(output: Path, arms: tuple[str, ...]):
    output.mkdir(parents=True, exist_ok=False)
    before_sources = source_files()
    torch.set_num_threads(2)
    sample, support = data()
    rows = []
    for arm in arms:
        folder = output / arm
        folder.mkdir()
        model, training = train_proposer(
            arm=arm,
            samples=(sample,),
            support_provider=lambda context: support,
            seed=0,
            optimizer_steps=2,
            max_seconds=60,
            learning_rate=0.001,
            fixture_diagnostic=True,
        )
        checkpoint = folder / "checkpoint"
        pin = save_checkpoint(model, training, checkpoint)
        producer = NeuralNativeProducer(OpenWorldJointFixture(), checkpoint, manifest_sha256=pin)
        start = perf_counter()
        _, _, stream, store, builder, _, before = corrected(folder / "state.sqlite", producer)
        try:
            core = stream._system.core
            old_runtime = core._particle_workspace.runtime_id
            old_calls = producer.calls
            old_records = len(core._particle_workspace.records)
            invalidated = tuple(sorted(core._particle_workspace.invalidated_revisions, key=str))
            ledger = core._hybrid_loop.ledger.export_state()
            pre_replay_error = None
            try:
                stream.current_joint_decision_view()
            except ValueError as error:
                pre_replay_error = str(error)
            if pre_replay_error is None:
                raise AssertionError("invalidated neural posterior was readable")
            replay_start = perf_counter()
            stream.replay_joint_posterior()
            replay_seconds = perf_counter() - replay_start
            view = stream.current_joint_decision_view()
            fresh = NeuralNativeProducer(OpenWorldJointFixture(), checkpoint, manifest_sha256=pin)
            restored = ContinuousEvidenceInput.resume(
                store, producer=OracleProducer(), context_builder=builder, joint_producer=fresh
            )
            recovered_view = restored.current_joint_decision_view()
            workspace = core._particle_workspace
            q = [
                r.proposal.proposal_log_probability
                for b in workspace.input_bodies.values()
                for r in b.receipts
            ]
            row = {
                "arm": arm,
                "track": "CONTROLLED_NEURAL_NATIVE_ENUMERATION",
                "checkpoint_manifest_sha256": pin,
                "training": training,
                "old_joint_calls": old_calls,
                "old_native_records": old_records,
                "invalidated_revisions": list(map(str, invalidated)),
                "stale_readout_rejected": pre_replay_error,
                "recomputed_sources": producer.calls,
                "new_native_records": len(workspace.records),
                "current_atoms": len(view.atoms),
                "conditional_history_lengths": [
                    len(a.statistics.evidence_cluster_ids) for a in view.atoms
                ],
                "pose_dimensions": [len(a.statistics.information_vector) for a in view.atoms],
                "new_generation": view.runtime_id != old_runtime,
                "joint_view_changed": view != before,
                "ledger_unchanged_by_neural_replay": (
                    restored._system.core._hybrid_loop.ledger.export_state() == ledger
                ),
                "exact_recovered_view": recovered_view == view,
                "exact_recovered_producer": fresh.checkpoint_state() == producer.checkpoint_state(),
                "verified_neural_inputs": sum(
                    b.neural_evidence is not None for b in workspace.input_bodies.values()
                ),
                "neural_log_q_range": [min(q), max(q)],
                "quadrature_equals_log_q": all(
                    r.integration_log_weight == r.proposal.proposal_log_probability
                    for b in workspace.input_bodies.values()
                    for r in b.receipts
                ),
                "ledger_sha256": native_content_sha256(ledger),
                "replay_seconds": replay_seconds,
                "total_seconds": perf_counter() - start,
                "integration_measure": "all_configured_candidates_once__q_over_q",
                "neural_publication_is_development_only": True,
                "learned_six_operation_kernel_bound": False,
                "candidate_measurement_model_empirically_calibrated": False,
                "natural_semantic_transitions": 0,
                "actual_simulator_dispatches": 0,
                "complete_natural_closed_loop": False,
            }
            assert old_calls == 12 and row["recomputed_sources"] == 11
            assert row["exact_recovered_view"] and row["exact_recovered_producer"]
            assert row["ledger_unchanged_by_neural_replay"] and row["quadrature_equals_log_q"]
            (folder / "result.json").write_text(json.dumps(row, indent=2) + "\n")
            rows.append(row)
            print(
                json.dumps(
                    {
                        k: row[k]
                        for k in (
                            "arm",
                            "recomputed_sources",
                            "verified_neural_inputs",
                            "exact_recovered_view",
                            "total_seconds",
                        )
                    }
                ),
                flush=True,
            )
        finally:
            store.close()
    after_sources = source_files()
    result = {
        "source_files": before_sources,
        "source_unchanged": before_sources == after_sources,
        "python": sys.version,
        "platform": platform.platform(),
        "torch": torch.__version__,
        "arms": rows,
        "independent_auditors": 0,
    }
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    assert result["source_unchanged"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--arm", choices=(*ARMS, "all"), default="all")
    args = parser.parse_args()
    run(args.output, ARMS if args.arm == "all" else (args.arm,))
