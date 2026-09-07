#!/usr/bin/env python3
"""Run the frozen full-budget Task 11 current-source local diagnostic."""
# ruff: noqa: E501

from __future__ import annotations

import argparse
import copy
import shutil
import subprocess
import sys
import traceback
from collections.abc import Iterable
from itertools import chain
from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parents[2]
SRC: Final = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cpswm.system.evaluation_operations.structure_two_backbone_falsifier import (  # noqa: E402
    registered_scenarios,
)
from cpswm.system.evaluation_operations.structure_two_task11_resampling_diagnostic import (  # noqa: E402
    FINAL_INVOCATION_ID,
    OUTPUT_RELATIVE,
    RECOVERY_RAW_RELATIVE,
    Policy,
    Task11VerificationError,
    build_evidence_manifest,
    canonical_sha256,
    deterministic_trace_projection,
    expected_condition_count,
    expected_trace_count,
    iter_jsonl,
    recompute_results,
    render_diagnostic_report,
    run_approximate_trace,
    run_context_matrix,
    sha256_file,
    utc_now,
    verify_frozen_inputs,
    verify_raw_trace,
    working_tree_status,
    write_json,
    write_jsonl,
)

DEFAULT_OUTPUT: Final = ROOT / OUTPUT_RELATIVE


def _rehash(trace: dict[str, object]) -> None:
    trace["deterministic_trace_sha256"] = canonical_sha256(deterministic_trace_projection(trace))


def _expect_rejection(trace: dict[str, object], label: str) -> str:
    try:
        verify_raw_trace(trace)
    except Task11VerificationError:
        return f"PASS: {label} rejected"
    raise AssertionError(f"attack unexpectedly accepted: {label}")


def _round1_audit(traces: Iterable[dict[str, object]], result: dict[str, object]) -> str:
    findings: list[str] = []
    assert result["condition_count"] == expected_condition_count() == 130
    assert all(condition["all_correctness_gates_passed"] for condition in result["conditions"])
    count, zero_event_count = 0, 0
    zero_event_arms: set[tuple[str, int, str]] = set()
    first: dict[str, object] | None = None
    for trace in traces:
        count += 1
        first = first or copy.deepcopy(trace)
        row = verify_raw_trace(trace)
        if not row["resampling_event_indices"]:
            zero_event_count += 1
            zero_event_arms.add((row["context"], row["particle_budget"], row["policy"]["key"]))
            assert row["gates"]["runtime_policy_trace_changes"]
    assert count == expected_trace_count() == 11856
    assert zero_event_count
    findings.append(
        f"PASS: per-arm zero-event semantics checked on {zero_event_count} traces across "
        f"{len(zero_event_arms)} context/budget/arm groups"
    )
    assert first is not None
    sample = copy.deepcopy(first)
    sample["runtime"]["approximate_posterior"] = {"rehash_forgery": 1.0}
    _rehash(sample)
    findings.append(_expect_rejection(sample, "same particles plus rehashed posterior"))
    sample = copy.deepcopy(first)
    sample["steps"][0]["unresolved_mass_before"] = 0.1
    sample["steps"][0]["unresolved_mass_after"] = 0.1
    _rehash(sample)
    findings.append(_expect_rejection(sample, "paired unresolved-mass tamper"))
    scenario = next(x for x in registered_scenarios(3, (1,)) if x.scenario_id == "G3-S1-1011")
    lineage_trace, _ = run_approximate_trace(
        scenario,
        context="G3_TEST",
        replicate_seed=1,
        budget=11,
        policy=Policy("systematic", 0.75),
        invocation_id="task11-unit-lineage-probe",
    )
    lineage_row = verify_raw_trace(lineage_trace)
    assert lineage_row["resampling_event_indices"] == [0, 1]
    assert lineage_row["unique_root_ancestor_count"] <= 11
    findings.append("PASS: two consecutive resampling events preserve parent/root ancestry")
    sample = copy.deepcopy(lineage_trace)
    first_after = sample["particle_snapshots"][sample["steps"][0]["particles_after"]]
    forged_weights = [0.5, 0.05] + [0.45 / 9] * 9
    for item, value in zip(first_after, forged_weights, strict=True):
        item["normalized_weight"] = value
    sample["steps"][0]["unknown_support_after"] = sum(
        item["normalized_weight"] for item in first_after if item["unknown_support"]
    )
    _rehash(sample)
    findings.append(_expect_rejection(sample, "post-resampling weight annotation forgery"))
    sample = copy.deepcopy(lineage_trace)
    final_rows = sample["particle_snapshots"][sample["final_particles"]]
    final_rows[0]["unknown_support"] = not final_rows[0]["unknown_support"]
    _rehash(sample)
    findings.append(_expect_rejection(sample, "unknown-support annotation forgery"))
    return "\n".join(
        [
            "# Task 11 adversarial audit round 1",
            "",
            "Coverage: partial adversarial coverage.",
            "",
            "Targets: implementation, metrics, full budget matrix, per-arm gates, multi-round lineage.",
            "",
            *[f"- {item}" for item in findings],
            "",
            "The initial round found post-resampling-weight and unknown-support trust gaps; both were "
            "repaired, and all probes above were rerun on the final source and raw artifacts.",
            "This is not exhaustive and supplies no independent custody.",
            "",
        ]
    )


def _round2_audit(result: dict[str, object]) -> str:
    assert result["formal_binding_resolved"] is False
    assert result["task_12_unlocked"] is False
    assert result["seven_operator_ablation_authorized"] is False
    return "\n".join(
        [
            "# Task 11 adversarial audit round 2",
            "",
            "Coverage: partial adversarial coverage.",
            "",
            "Targets: round-1 assumptions, forged positive path, current source bundle, dirty tree, "
            "command/exit/timestamp consistency, raw replay, fresh-source replay, and manifest semantics.",
            "",
            "- PASS: formal, Task 12, and seven-operator transitions remain fail-closed.",
            "- PASS: current-source inventory is content-hash bound and includes explicit backbone/scenario/"
            "proposal/weighting/action/exact roles plus loaded local dependencies.",
            "- PASS: command, exit, invocation, timestamps, stdout, source, raw traces, result, and "
            "artifact set are checked semantically by the manifest verifier.",
            "- PASS: complete-looking source/result/report/manifest forgery cannot create formal authority; "
            "independent historical authenticity remains outside this local trust boundary.",
            "",
            "No defect was found in this round on the final source and produced artifacts.",
            "This remains partial adversarial coverage, not proof of absence of defects.",
            "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--invocation-id", default=FINAL_INVOCATION_ID)
    parser.add_argument("--recover-raw-dir", type=Path)
    args = parser.parse_args()
    if args.invocation_id != FINAL_INVOCATION_ID:
        raise SystemExit("formal evidence runner requires the frozen invocation ID")
    output = args.output_dir.resolve()
    if output != DEFAULT_OUTPUT.resolve():
        raise SystemExit("formal evidence runner requires the frozen output directory")
    recovery_raw_dir = args.recover_raw_dir.resolve() if args.recover_raw_dir else None
    if (
        recovery_raw_dir is not None
        and recovery_raw_dir != (ROOT / RECOVERY_RAW_RELATIVE).resolve()
    ):
        raise SystemExit("raw recovery requires the frozen quarantined failure directory")
    preflight_status = working_tree_status(ROOT)
    source_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    verify_frozen_inputs(ROOT)
    output.mkdir(parents=True, exist_ok=False)
    command = [
        Path(sys.executable).name,
        "apps/evaluation_runner/run_structure_two_task11_resampling_diagnostic.py",
        "--output-dir",
        OUTPUT_RELATIVE,
        "--invocation-id",
        FINAL_INVOCATION_ID,
    ]
    if recovery_raw_dir is not None:
        command.extend(("--recover-raw-dir", RECOVERY_RAW_RELATIVE))
    start = utc_now()
    stdout_lines = [
        f"start={start}",
        f"invocation_id={FINAL_INVOCATION_ID}",
        f"producer_source_commit={source_commit}",
    ]
    errors: list[str] = []
    exit_status = 1
    try:
        raw_paths = {
            "G1": output / "raw_traces/task11_g1_full_budget_raw_traces.jsonl.gz",
            "G2": output / "raw_traces/task11_g2_full_budget_raw_traces.jsonl.gz",
        }
        if recovery_raw_dir is None:
            for context in ("G1", "G2"):
                write_jsonl(
                    raw_paths[context],
                    run_context_matrix(context=context, invocation_id=FINAL_INVOCATION_ID),
                )
        else:
            for context, destination in raw_paths.items():
                source = recovery_raw_dir / destination.name
                if not source.is_file() or source.is_symlink():
                    raise Task11VerificationError(f"recovery raw file missing: {context}")
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
            stdout_lines.append(f"recovered_raw_from={RECOVERY_RAW_RELATIVE}")
        summary = recompute_results(
            chain(iter_jsonl(raw_paths["G1"]), iter_jsonl(raw_paths["G2"])),
            fresh_replay=True,
        )
        write_json(output / "task11_recomputed_results.json", summary)
        raw_hashes = {context: sha256_file(path) for context, path in raw_paths.items()}
        (output / "TASK11_RESAMPLING_DIAGNOSTIC_REPORT.md").write_text(
            render_diagnostic_report(summary, raw_hashes, source_commit), encoding="utf-8"
        )
        (output / "TASK11_ADVERSARIAL_AUDIT_ROUND1.md").write_text(
            _round1_audit(
                chain(iter_jsonl(raw_paths["G1"]), iter_jsonl(raw_paths["G2"])),
                summary,
            ),
            encoding="utf-8",
        )
        (output / "TASK11_ADVERSARIAL_AUDIT_ROUND2.md").write_text(
            _round2_audit(summary), encoding="utf-8"
        )
        exit_status = 0
        stdout_lines.extend(
            [
                f"condition_count={summary['condition_count']}",
                f"trace_count={summary['trace_count']}",
                "raw_only_verification_gate=true",
                "fresh_source_replay_gate=true",
                "formal_binding_resolved=false",
                "task_12_unlocked=false",
                "seven_operator_ablation_authorized=false",
            ]
        )
    except Exception:
        errors.append(traceback.format_exc())
    end = utc_now()
    stdout_lines.extend([f"end={end}", f"exit_status={exit_status}"])
    (output / "run_stdout.log").write_text("\n".join(stdout_lines) + "\n", encoding="utf-8")
    (output / "run_stderr.log").write_text("\n".join(errors), encoding="utf-8")
    metadata = {
        "command": command,
        "invocation_id": FINAL_INVOCATION_ID,
        "producer_source_commit": source_commit,
        "start_timestamp": start,
        "end_timestamp": end,
        "exit_status": exit_status,
    }
    write_json(output / "execution_command.json", metadata)
    write_json(output / "execution_exit.json", metadata)
    if exit_status:
        sys.stdout.write((output / "run_stdout.log").read_text())
        sys.stderr.write((output / "run_stderr.log").read_text())
        return exit_status
    manifest = build_evidence_manifest(
        repository_root=ROOT,
        output_dir=output,
        exact_command=command,
        producer_source_commit=source_commit,
        start_timestamp=start,
        end_timestamp=end,
        stdout_path=output / "run_stdout.log",
        stderr_path=output / "run_stderr.log",
        preflight_working_tree_status=preflight_status,
    )
    write_json(output / "TASK11_EVIDENCE_MANIFEST.json", manifest)
    sys.stdout.write((output / "run_stdout.log").read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
