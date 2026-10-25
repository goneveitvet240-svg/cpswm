"""Reproduce PR128 audit findings without changing production or original runs.

Exit zero means the stated probes finished, NOT that the project passed audit.
Physics verification is a separate simulation-environment command.
"""

import argparse
import contextlib
import hashlib
import io
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = "90e6c60009e17226b1a58f31245dcd04b810b23a"


def state_machine():
    from run_current_event import build, dataset_for

    from cpswm.contracts import ProjectTwoDatasetSplit
    from cpswm.simulation.contracts import Observation, Visibility
    from cpswm.simulation.goal_control import GoalPlan, MemoryGoalController
    from cpswm.system.evaluation_operations.structure_two_memory_action import (
        MemoryActionRuntime,
        NativeGoalMemory,
    )
    from cpswm.system.evaluation_operations.structure_two_stateful_full_joint import FullJointArm

    def setup():
        dataset = dataset_for("sparse32", [66001])
        episode = dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)[0]
        state = build(dataset, episode, FullJointArm.STATEFUL_FULL_JOINT)
        old = state.runtime
        state.runtime = MemoryActionRuntime(
            arm=old.arm, config=old.config, neural_model=old.neural_model
        )
        for step in episode.steps[:4]:
            state.observe(step)
            state.predict()
            state.feedback(step)
        runtime = state.runtime
        bindings = {
            key: f"place-{i}" for i, key in enumerate(runtime._last_observation.known_location_ids)
        }
        controller = MemoryGoalController(
            str(episode.episode_id),
            {v: "put target at " + v for v in bindings.values()},
            native_memory=NativeGoalMemory(runtime, bindings),
        )

        def visual(tick, robot=False):
            return Observation(
                str(episode.episode_id),
                f"sam:{tick}",
                f"visual:{tick}",
                tick,
                tick,
                "target",
                Visibility.PREDICTED if robot else Visibility.OBSERVED,
                "image_center",
                origin="sam2.1_tiny_propagation" if robot else "sam2.1_tiny_operator_box",
                robot_generated=robot,
                identity_probability=0.0 if robot else 1.0,
            )

        controller.observe_visual(visual(100), 100)
        plan = GoalPlan.from_payload(controller.plan(100)["plan"])
        return runtime, controller, plan, visual

    # Legal control: settle first, then withdraw; next plan remains usable.
    r, c, p, camera = setup()
    c.record_step(p, 101)
    c.feedback(p, camera(101, True), 1)
    source_id, source = next(iter(r.location_sources.items()))
    r.revise_location_source(source_id, source["sha256"])
    next_plan = c.plan(102)
    assert next_plan["status"] == "ready" and len(c.queue.executed) == 1

    # Same legal withdrawal, now arriving between action and feedback.
    r, c, p, camera = setup()
    c.record_step(p, 101)
    before = c.memory.revision
    source_id, source = next(iter(r.location_sources.items()))
    r.revise_location_source(source_id, source["sha256"])
    r.verify_internal_contracts()
    assert c.memory.revision != before
    errors = {}
    for label, call in (
        ("feedback", lambda: c.feedback(p, camera(101, True), 1)),
        ("plan", lambda: c.plan(102)),
        ("step", lambda: c.record_step(p, 102)),
    ):
        try:
            call()
        except ValueError as error:
            errors[label] = str(error)
    assert set(errors) == {"feedback", "plan", "step"}
    assert c.step_ticks == [101] and c.pending == p and not c.queue.executed
    return {
        "finding": "A1 OPEN: valid live withdrawal strands executed segment",
        "positive_control_settle_then_withdraw": True,
        "runtime_internal_contracts_after_withdrawal": True,
        "errors": errors,
        "unsettled_ticks": c.step_ticks,
        "pending_command": p.command.command_id,
        "completed_commands": len(c.queue.executed),
        "scope": "public in-process live native API; fixed-prefix worker has no update RPC",
    }


def protocol(runs, output):
    from analyze_reliability_replication import analyze
    from verify_reliability_evidence import verify

    original = runs / "reliability-fresh02"
    copied = output / "changed-protocol"
    copied.mkdir()
    for name in ("source.json", "points.jsonl.gz", "completion.json"):
        shutil.copy2(original / name, copied / name)
    manifest = json.loads((copied / "source.json").read_text())
    frozen_blob = subprocess.check_output(
        [
            "git",
            "show",
            manifest["sha"] + ":docs/reviews/pc_a/reliability_net_benefit_2026-10-25/FROZEN.json",
        ],
        cwd=ROOT,
    )
    assert manifest["frozen"] == json.loads(frozen_blob)
    baseline, changed = output / "original-analysis", output / "changed-analysis"
    # Fresh positive and negative all-source verification, including repeat records.
    with contextlib.redirect_stdout(io.StringIO()) as capture:
        analyze(original, baseline)
        verify(original, baseline, runs / "reliability-prefix01", runs / "reliability-fresh01")
        manifest["frozen"]["bootstrap_draws"] = 1
        (copied / "source.json").write_text(json.dumps(manifest, indent=2) + "\n")
        analyze(copied, changed)
        verify(copied, changed, runs / "reliability-prefix01", runs / "reliability-fresh01")
    (output / "protocol.log").write_text(capture.getvalue())
    a, b = (json.loads((p / "summary.json").read_text()) for p in (baseline, changed))
    assert a["errors"] == b["errors"]
    return {
        "finding": "A3 OPEN: unbound frozen configuration changes accepted statistics",
        "original_protocol_matches_git_blob": True,
        "changed_fields": {"frozen.bootstrap_draws": [10000, 1]},
        "positive_and_forged_all_source_verifiers_accepted": True,
        "original_uncertainty": a["uncertainty"]["latest_owner"],
        "changed_uncertainty": b["uncertainty"]["latest_owner"],
        "unchanged_paired_counts": a["paired"]["latest_owner"],
        "point_file_identical": hashlib.sha256((original / "points.jsonl.gz").read_bytes())
        == hashlib.sha256((copied / "points.jsonl.gz").read_bytes()),
    }


def native(smoke, output):
    from verify_native_pi05_probe import verify_core

    original_manifest = json.loads((smoke / "manifest.json").read_text())
    original_summary = json.loads((smoke / "summary.json").read_text())
    assert original_manifest["policy"] == "smoke"
    assert original_summary["pi05_inference_executed"] is False
    positive = verify_core(smoke)
    forged = output / "forged-pi05"
    shutil.copytree(smoke, forged)
    m, s = dict(original_manifest), dict(original_summary)
    m.update(sha="0" * 40, sources={}, policy="pi05-local")
    s["pi05_inference_executed"] = True
    (forged / "manifest.json").write_text(json.dumps(m, indent=2) + "\n")
    (forged / "summary.json").write_text(json.dumps(s, indent=2) + "\n")
    negative = verify_core(forged)
    assert positive == negative and not (forged / "policy_metadata.json").exists()
    return {
        "finding": "A2 OPEN: native verifier accepts bogus source and smoke-to-pi05 relabel",
        "positive_core": positive,
        "forged_core": negative,
        "forged_directory": str(forged),
        "pi05_metadata_exists": False,
        "physics": "run separate verifier on both directories; this command only runs core",
        "scope": "forged claims in a copy; original smoke and prior pi05 runs untouched",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("probe", choices=("state-machine", "protocol", "native"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runs", type=Path)
    parser.add_argument("--smoke", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    if args.probe == "state-machine":
        result = state_machine()
    elif args.probe == "protocol":
        result = protocol(args.runs, args.output)
    else:
        result = native(args.smoke, args.output)
    result["audited_base_sha"] = TARGET
    result["audit_runner_sha"] = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    result["acceptance"] = "findings reproduced; NOT project acceptance"
    (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
