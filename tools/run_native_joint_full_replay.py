"""Controlled native correction -> full replay -> recovery -> camera dispatch.

All semantic input, conditional measurements, and camera transport are explicitly
assumed fixtures. This artifact demonstrates wiring and state consequences only;
it is not a natural-data experiment or an independent calibration result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import timedelta
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "tools")]
from run_correction_replay_comparison import OracleProducer  # noqa: E402
from test_continuous_camera_collection import Camera, Model  # noqa: E402
from test_native_joint_full_replay import corrected  # noqa: E402
from test_native_joint_production import JointFixture  # noqa: E402

from cpswm.system.continuous_camera_collection import collect_posterior_step  # noqa: E402
from cpswm.system.continuous_state_codec import StateCodec  # noqa: E402
from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput  # noqa: E402
from cpswm.system.structure_two_particle_workspace import native_content_sha256  # noqa: E402


def run(output: Path):
    output.mkdir(parents=True, exist_ok=False)
    files = {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for folder in ("src", "tests", "tools")
        for path in sorted((ROOT / folder).rglob("*.py"))
    }
    _, _, stream, store, builder, joint, before = corrected(output / "online.db")
    try:
        core = stream._system.core
        old = core._particle_workspace
        invalidated = tuple(sorted(old.invalidated_revisions, key=str))
        ledger = core._hybrid_loop.ledger.export_state()
        snapshot_id = core.current_snapshot.snapshot_id
        old_calls = joint.calls
        original_schedule = {r.state.revision_id for r in old.records.values()}
        retained_schedule = original_schedule & set(core._observed_events)
        cutoff_before = stream._last_cutoff
        arrival = stream._last_arrival
        errors = {}
        for name, call in [
            ("produce", stream.produce_joint_posterior),
            ("readout", stream.current_joint_decision_view),
        ]:
            try:
                call()
            except ValueError as error:
                errors[name] = str(error)
            else:
                raise AssertionError("invalidated history was reused")
        start = perf_counter()
        stream.replay_joint_posterior()
        replay_seconds = perf_counter() - start
        view = stream.current_joint_decision_view()
        fresh_joint = JointFixture()
        recovered = ContinuousEvidenceInput.resume(
            store,
            producer=OracleProducer(),
            context_builder=builder,
            joint_producer=fresh_joint,
        )
        restored = recovered.current_joint_decision_view()
        assert restored == view and fresh_joint.checkpoint_state() == joint.checkpoint_state()
        camera = Camera(core.current_posterior_projection_source().transition)
        action = collect_posterior_step(
            recovered,
            model=Model(recovered),
            executor=camera,
            decision_time=recovered._last_cutoff + timedelta(hours=3),
        )
        record_revisions = {r.state.revision_id for r in core._particle_workspace.records.values()}
        result = {
            "track": "CONTROLLED_SEMANTIC_CONDITIONAL_AND_TRANSPORT_FIXTURES",
            "seed": 171,
            "old_joint_calls": old_calls,
            "old_native_records": len(core._particle_replay_generations[-1].old_workspace.records),
            "invalidated_revisions": list(map(str, invalidated)),
            "before_replay_rejections": errors,
            "retained_semantic_revisions": len(core._observed_events),
            "recomputed_joint_sources": joint.calls,
            "retained_joint_source_count": len(retained_schedule),
            "unconsumed_intermediate_sources_not_added": len(
                set(core._observed_events) - retained_schedule
            ),
            "retained_source_closure_exact": record_revisions == retained_schedule,
            "replay_seconds": replay_seconds,
            "ledger_unchanged_by_replay_and_camera": (
                recovered._system.core._hybrid_loop.ledger.export_state() == ledger
            ),
            "semantic_snapshot_unchanged_by_replay": core.current_snapshot.snapshot_id
            == snapshot_id,
            "knowledge_cutoff_before": cutoff_before.isoformat(),
            "feedback_arrival": arrival.isoformat(),
            "replay_cutoff": stream._last_cutoff.isoformat(),
            "current_native_records": len(core._particle_workspace.records),
            "current_atoms": len(view.atoms),
            "atom_history_lengths": [len(a.event_chain_json) for a in view.atoms],
            "conditional_history_lengths": [
                len(a.statistics.evidence_cluster_ids) for a in view.atoms
            ],
            "pose_dimensions": [len(a.statistics.information_vector) for a in view.atoms],
            "conditional_states_changed": [
                a.statistics != b.statistics for a, b in zip(view.atoms, before.atoms, strict=True)
            ],
            "old_generation_preserved_sha256": core._particle_replay_generations[-1].content_sha256,
            "exact_restored_view": restored == view,
            "controlled_camera_command": action.command.action,
            "controlled_transport_dispatches": camera.calls,
            "actual_simulator_dispatches": 0,
            "natural_semantic_transitions": 0,
            "empirical_calibration_established": False,
            "learned_six_operation_kernel_bound": False,
            "full_prepared_joint_replay_bound": True,
            "independent_auditors": 0,
            "source_files": files,
            "source_unchanged": all(
                hashlib.sha256((ROOT / n).read_bytes()).hexdigest() == h for n, h in files.items()
            ),
        }
        for name, value in [
            ("before-view", before),
            ("after-view", view),
            ("controlled-command", action.command),
        ]:
            (output / f"{name}.json").write_text(StateCodec().dumps(value) + "\n")
        result["ledger_sha256"] = native_content_sha256(ledger)
        (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        assert result["retained_source_closure_exact"]
        assert result["ledger_unchanged_by_replay_and_camera"] and result["exact_restored_view"]
        assert result["source_unchanged"] and result["controlled_transport_dispatches"] == 1
        print(json.dumps({k: v for k, v in result.items() if k != "source_files"}, indent=2))
    finally:
        store.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output)
