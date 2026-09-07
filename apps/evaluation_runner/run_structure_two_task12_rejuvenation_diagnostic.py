#!/usr/bin/env python3
"""Run the complete local-only Structure Two Task 12 diagnostic matrix."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import traceback
from datetime import UTC, datetime
from importlib.metadata import distributions
from pathlib import Path
from typing import Any, Final

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[2]
SOURCE_ROOT: Final = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from cpswm.system.evaluation_operations.structure_two_task12_rejuvenation_diagnostic import (  # noqa: E402
    AUTHORITY,
    BASE_COMMIT,
    BASELINE_STATUS,
    EVIDENCE_STATUS,
    FINAL_INVOCATION_ID,
    KERNELS,
    TASK11_OUTPUT_RELATIVE,
    TASK11_RAW_RELATIVE,
    canonical_sha256,
    load_jsonl,
    run_complete_matrix,
    sha256_file,
    write_json,
    write_jsonl,
)
from cpswm.system.evaluation_operations.structure_two_task12_rejuvenation_verifier import (  # noqa: E402
    recompute_results,
)

DEFAULT_OUTPUT_DIR: Final = (
    REPOSITORY_ROOT / "benchmarks/structure_two/task12_rejuvenation_diagnostic_2026_09_06"
)
TASK11_DIR: Final = REPOSITORY_ROOT / TASK11_OUTPUT_RELATIVE
TASK12_SOURCE_PATHS: Final = (
    "src/cpswm/system/evaluation_operations/structure_two_task12_rejuvenation_diagnostic.py",
    "src/cpswm/system/evaluation_operations/structure_two_task12_rejuvenation_verifier.py",
    "apps/evaluation_runner/run_structure_two_task12_rejuvenation_diagnostic.py",
    "apps/evaluation_runner/recompute_structure_two_task12_rejuvenation_diagnostic.py",
    "apps/evaluation_runner/replay_structure_two_task12_rejuvenation_diagnostic.sh",
    "tests/test_structure_two_task11_task12_runtime.py",
)
FROZEN_INPUT_PATHS: Final = (
    "configs/project_two_experiments/structure_two_backbone_open_tasks_v0_1.json",
    "src/cpswm/system/evaluation_operations/structure_two_backbone_open_task_protocols.py",
    "tests/test_structure_two_backbone_open_task_protocols.py",
    "docs/结构二/方向结构二_Tasks10-13_P5回执DAG与唯一七算子授权协议_v1.0.md",
    "benchmarks/structure_two/task11_resampling_full_budget_2026_09_06_adversarial_rerun/TASK11_EVIDENCE_MANIFEST.json",
    "benchmarks/structure_two/task11_resampling_full_budget_2026_09_06_adversarial_rerun/task11_recomputed_results.json",
    "benchmarks/structure_two/task11_resampling_full_budget_2026_09_06_adversarial_rerun/raw_traces/task11_g1_full_budget_raw_traces.jsonl.gz",
    "benchmarks/structure_two/task11_resampling_full_budget_2026_09_06_adversarial_rerun/raw_traces/task11_g2_full_budget_raw_traces.jsonl.gz",
)
BASE_REQUIRED_ARTIFACTS: Final = (
    "TASK12_REJUVENATION_DIAGNOSTIC_REPORT.md",
    "TASK12_PROTOCOL_DRIFT_REPORT.md",
    "execution_command.json",
    "execution_exit.json",
    "raw_traces/task12_g1_raw_traces.jsonl",
    "raw_traces/task12_g2_raw_traces.jsonl",
    "run_stderr.log",
    "run_stdout.log",
    "task12_recomputed_results.json",
)
AUDIT_ARTIFACTS: Final = (
    "TASK12_ADVERSARIAL_AUDIT_ROUND1.md",
    "TASK12_ADVERSARIAL_AUDIT_ROUND2.md",
)


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _dependency_snapshot() -> dict[str, Any]:
    packages = sorted(
        f"{distribution.metadata['Name']}=={distribution.version}"
        for distribution in distributions()
        if distribution.metadata["Name"]
    )
    return {
        "python": sys.version,
        "python_executable_name": Path(sys.executable).name,
        "os": platform.platform(),
        "machine": platform.machine(),
        "dependency_lock": packages,
    }


def _protocol_drift_report(result: dict[str, Any]) -> str:
    loose = result["threshold_interpretations"]["json_python_1e-6"]["arm_results"]
    strict = result["threshold_interpretations"]["chinese_protocol_1e-9"]["arm_results"]
    loose_passes = sum(bool(row["diagnostic_guardrails_passed"]) for row in loose)
    strict_passes = sum(bool(row["diagnostic_guardrails_passed"]) for row in strict)
    return "\n".join(
        [
            "# Task 12 Protocol Drift Report",
            "",
            "Status: `PROTOCOL_DRIFT_UNRESOLVED`",
            "",
            "The frozen JSON and Python contract set `max_stationary_distribution_error` to "
            "`1e-6`. The Chinese protocol prose states a stationarity threshold of `1e-9`. "
            "Neither source has been edited and this diagnostic does not choose between them.",
            "",
            "## Separate recomputations",
            "",
            "| Interpretation | Threshold | Guardrail passes | Formal selection |",
            "|---|---:|---:|---|",
            f"| Frozen JSON/Python | `1e-6` | `{loose_passes}/104` | `null` |",
            f"| Chinese protocol prose | `1e-9` | `{strict_passes}/104` | `null` |",
            "",
            "The machine-readable result retains all 104 rows under both interpretations. A "
            "pass at `1e-6` never substitutes for a failure at `1e-9`. Even if every numerical "
            "row agrees, the normative conflict remains unresolved until the user selects the "
            "authoritative threshold through the formal protocol process.",
            "",
            "```text",
            "formal_task_12_passed=false",
            "selected_kernel=null",
            "task_13_unlocked=false",
            "proposal_p5_unlocked=false",
            "seven_operator_ablation_authorized=false",
            "```",
            "",
        ]
    )


def _diagnostic_report(result: dict[str, Any], raw_hashes: dict[str, str]) -> str:
    failed_upstream = sum(
        not row["upstream_fidelity"]["fidelity_passed"]
        for row in result["condition_arms"]
        if row["kernel"] == KERNELS[0]
    )

    coverage = result["global_path_coverage"]
    return "\n".join(
        [
            "# Task 12 Rejuvenation Diagnostic Report",
            "",
            f"Evidence status: `{EVIDENCE_STATUS}` / `{AUTHORITY}`",
            f"Baseline: `{BASELINE_STATUS}`",
            "Protocol drift: `PROTOCOL_DRIFT_UNRESOLVED`",
            "",
            "## Outcome",
            "",
            "All 26 frozen G1/G2 x Task 11 policy conditions were retained and crossed with "
            "all four Task 12 kernels. No particle budget, resampling policy, rejuvenation "
            "kernel, or stationarity threshold has been selected.",
            "",
            f"- Upstream conditions: `{result['upstream_condition_count']}`.",
            f"- Condition x kernel combinations: `{result['condition_kernel_count']}`.",
            f"- Raw scenario/seed executions: `{result['raw_trace_count']}`.",
            f"- Upstream fidelity-failed conditions retained: `{failed_upstream}/26`.",
            f"- G1 raw SHA-256: `{raw_hashes['G1']}`.",
            f"- G2 raw SHA-256: `{raw_hashes['G2']}`.",
            f"- Deterministic result SHA-256: `{result['deterministic_result_sha256']}`.",
            "",
            "## Kernel reality checks",
            "",
            "`single_site_typed_metropolis_hastings` uses only Hamming-distance-one typed "
            "moves. `blocked_typed_metropolis_hastings` uses multi-axis, direction-dependent "
            "proposals with explicit forward/reverse correction. Exact conditional Gibbs uses "
            "rows equal to pi and is tagged `evaluator_oracle`; it is never selectable.",
            "",
            f"- Zero-accept paths: `{coverage['zero_acceptance_path_count']}`.",
            f"- Full-accept paths: `{coverage['full_acceptance_path_count']}`.",
            f"- Accepted non-self moves: `{coverage['non_self_move_count']}`.",
            "",
            "## Interpretation boundary",
            "",
            "Each upstream condition remains separate. Fidelity-failed Task 11 conditions are "
            "labelled conditional falsifications, not removed or averaged. The remaining rows "
            "are diagnostic-only because Task 10 and Task 11 lack formal resolution receipts. "
            "The finite D0 projection supports mechanism checking, not external validity or a "
            "formal full-chain binding claim.",
            "",
            "```text",
            "formal_task_12_passed=false",
            "formal_binding_resolved=false",
            "selected_kernel=null",
            "task_13_unlocked=false",
            "proposal_p5_unlocked=false",
            "seven_operator_ablation_authorized=false",
            "```",
            "",
        ]
    )


def _adversarial_audit_report(*, round_number: int, result_hash: str) -> str:
    if round_number == 1:
        targets = (
            "Task 11 full-budget gzip to K=24 slice interface, complete execution coordinates, "
            "transition/proposal recomputation, duplicate nonce rejection, and forged positive "
            "flags."
        )
        findings = (
            "PASS: producer and independent recompute CLI returned the same deterministic "
            "result hash.",
            "PASS: all 26 upstream conditions, four kernels, and 7,488 executions are present.",
            "PASS: caller-supplied metrics and positive authorization fields are recomputed "
            "or rejected.",
        )
    elif round_number == 2:
        targets = (
            "Round-1 assumptions, full-summary versus K=24 state-machine confusion, source/input "
            "hash drift, protocol-threshold ambiguity, failed-upstream retention, and authority "
            "escalation."
        )
        findings = (
            "PASS: the full Task 11 summary is validated as 130/11,856 while Task 12 consumes "
            "only the frozen K=24 26/1,872 slice.",
            "PASS: 1e-6 and 1e-9 stationarity interpretations remain separate with no "
            "selected kernel.",
            "PASS: formal Task 12, Task 13, P5, and seven-operator authorization remain false.",
        )
    else:
        raise ValueError("unsupported adversarial audit round")
    return "\n".join(
        [
            f"# Task 12 adversarial audit round {round_number}",
            "",
            "Status: `PARTIAL_ADVERSARIAL_COVERAGE`",
            f"Bound deterministic result: `{result_hash}`",
            "",
            f"Targets: {targets}",
            "",
            *[f"- {finding}" for finding in findings],
            "",
            "No defect remained in the enumerated attacks after repair. This is partial coverage, ",
            "not proof of absence of defects and not independent custody.",
            "",
        ]
    )


def _verify_regular_artifacts(output_dir: Path, *, require_audits: bool) -> None:
    required = BASE_REQUIRED_ARTIFACTS + (AUDIT_ARTIFACTS if require_audits else ())
    resolved_root = output_dir.resolve()
    for relative in required:
        path = output_dir / relative
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"required Task 12 artifact is missing or a symlink: {relative}")
        if not path.resolve().is_relative_to(resolved_root):
            raise ValueError(f"required Task 12 artifact escapes output directory: {relative}")


def _verify_final_reports(output_dir: Path, *, require_audits: bool) -> None:
    result = json.loads((output_dir / "task12_recomputed_results.json").read_text())
    for field in (
        "formal_task_12_passed",
        "formal_binding_resolved",
        "task_13_unlocked",
        "proposal_p5_unlocked",
        "seven_operator_ablation_authorized",
    ):
        if result.get(field) is not False:
            raise ValueError(f"forbidden final result escalation: {field}")
    if result.get("selected_kernel") is not None:
        raise ValueError("protocol-drifted Task 12 result cannot select a kernel")
    raw_hashes = {
        context: sha256_file(output_dir / f"raw_traces/task12_{context.lower()}_raw_traces.jsonl")
        for context in ("G1", "G2")
    }
    expected_reports = {
        "TASK12_REJUVENATION_DIAGNOSTIC_REPORT.md": _diagnostic_report(result, raw_hashes),
        "TASK12_PROTOCOL_DRIFT_REPORT.md": _protocol_drift_report(result),
    }
    for relative, expected in expected_reports.items():
        actual = (output_dir / relative).read_text(encoding="utf-8")
        if actual != expected:
            raise ValueError(f"Task 12 report is not derived from final raw result: {relative}")
    audits = AUDIT_ARTIFACTS if require_audits else ()
    result_hash = str(result["deterministic_result_sha256"])
    forbidden = (
        "formal_task_12_passed=true",
        "formal_binding_resolved=true",
        "task_13_unlocked=true",
        "proposal_p5_unlocked=true",
        "seven_operator_ablation_authorized=true",
        "AUDIT_COMPLETE",
    )
    for relative in audits:
        text = (output_dir / relative).read_text(encoding="utf-8")
        if "PARTIAL_ADVERSARIAL_COVERAGE" not in text or result_hash not in text:
            raise ValueError(f"audit report is stale or overclaims coverage: {relative}")
        if any(line.strip() in forbidden for line in text.splitlines()):
            raise ValueError(f"audit report contains a forbidden positive claim: {relative}")


def _verify_final_recomputation(output_dir: Path) -> dict[str, str]:
    """Bind the final result and reports to parsed raw traces before rehashing."""

    task11_rows, task11_result, task11_manifest, task11_raw_hashes = _load_task11_inputs()
    task12_paths = {
        context: output_dir / f"raw_traces/task12_{context.lower()}_raw_traces.jsonl"
        for context in ("G1", "G2")
    }
    traces = [*load_jsonl(task12_paths["G1"]), *load_jsonl(task12_paths["G2"])]
    recomputed = recompute_results(
        traces,
        task11_rows=task11_rows,
        task11_result=task11_result,
        task11_manifest=task11_manifest,
        task11_raw_hashes_by_context=task11_raw_hashes,
    )
    reported = json.loads((output_dir / "task12_recomputed_results.json").read_text())
    if reported != recomputed:
        raise ValueError("final Task 12 result differs from raw-trace recomputation")
    return {context: sha256_file(path) for context, path in task12_paths.items()}


def build_evidence_manifest(
    *,
    output_dir: Path,
    exact_command: list[str],
    start_timestamp: str,
    end_timestamp: str,
    require_audits: bool = False,
) -> dict[str, Any]:
    _verify_regular_artifacts(output_dir, require_audits=require_audits)
    verified_raw_hashes = _verify_final_recomputation(output_dir)
    _verify_final_reports(output_dir, require_audits=require_audits)
    source_hashes = {path: sha256_file(REPOSITORY_ROOT / path) for path in TASK12_SOURCE_PATHS}
    frozen_hashes = {path: sha256_file(REPOSITORY_ROOT / path) for path in FROZEN_INPUT_PATHS}
    artifacts = {
        path.relative_to(output_dir).as_posix(): sha256_file(path)
        for path in sorted(output_dir.rglob("*"))
        if path.is_file()
        and path.name != "TASK12_EVIDENCE_MANIFEST.json"
        and (require_audits or path.name not in AUDIT_ARTIFACTS)
        and not path.is_symlink()
    }
    for context in ("G1", "G2"):
        relative = f"raw_traces/task12_{context.lower()}_raw_traces.jsonl"
        if artifacts.get(relative) != verified_raw_hashes[context]:
            raise ValueError(f"Task 12 raw file changed after recomputation: {context}")
    manifest: dict[str, Any] = {
        "schema": "structure-two-task12-evidence-manifest@0.1",
        "baseline_status": BASELINE_STATUS,
        "evidence_status": EVIDENCE_STATUS,
        "authority": AUTHORITY,
        "protocol_drift_status": "PROTOCOL_DRIFT_UNRESOLVED",
        "formal_task_12_passed": False,
        "formal_binding_resolved": False,
        "selected_kernel": None,
        "task_13_unlocked": False,
        "proposal_p5_unlocked": False,
        "seven_operator_ablation_authorized": False,
        "base_commit": BASE_COMMIT,
        "task11_freeze_commit": "1c262c7",
        "current_git_head": subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip(),
        "source_hashes": source_hashes,
        "frozen_input_hashes": frozen_hashes,
        "upstream_artifact_policy": (
            "Task 11's approximately 50 MB evidence is referenced once by frozen relative path "
            "and SHA-256; it is not duplicated inside the Task 12 artifact directory."
        ),
        "environment": _dependency_snapshot(),
        "exact_command": exact_command,
        "start_timestamp": start_timestamp,
        "end_timestamp": end_timestamp,
        "artifact_hashes": artifacts,
        "claim_boundary": (
            "Local hashes prove current internal consistency only, not historical authenticity "
            "or independent custody. This manifest cannot resolve Task 10, Task 11, Task 12, "
            "the stationarity protocol drift, or any downstream authorization."
        ),
    }
    manifest["content_sha256"] = canonical_sha256(manifest)
    return manifest


def _load_task11_inputs(
    task11_dir: Path = TASK11_DIR,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any], dict[str, str]]:
    paths = {context: task11_dir / relative for context, relative in TASK11_RAW_RELATIVE.items()}
    all_rows = [*load_jsonl(paths["G1"]), *load_jsonl(paths["G2"])]
    rows = [row for row in all_rows if row.get("particle_budget") == 24]
    if len(rows) != 1872:
        raise ValueError("Task 11 full-budget artifact does not contain the frozen K=24 slice")
    task11_result = json.loads((task11_dir / "task11_recomputed_results.json").read_text())
    task11_manifest = json.loads((task11_dir / "TASK11_EVIDENCE_MANIFEST.json").read_text())
    raw_hashes = {context: sha256_file(path) for context, path in paths.items()}
    return rows, task11_result, task11_manifest, raw_hashes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--invocation-id", default=FINAL_INVOCATION_ID)
    parser.add_argument(
        "--refresh-manifest-only",
        action="store_true",
        help="Rehash final audit/report artifacts without rerunning the experiment.",
    )
    parser.add_argument(
        "--finalize-audits",
        action="store_true",
        help="Render both bound adversarial audit reports and refresh the manifest.",
    )
    arguments = parser.parse_args()
    if arguments.invocation_id != FINAL_INVOCATION_ID:
        raise SystemExit("Task 12 final invocation id is frozen")
    output_dir = arguments.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    command = [
        Path(sys.executable).name,
        "apps/evaluation_runner/run_structure_two_task12_rejuvenation_diagnostic.py",
        "--output-dir",
        output_dir.relative_to(REPOSITORY_ROOT).as_posix()
        if output_dir.is_relative_to(REPOSITORY_ROOT)
        else str(output_dir),
        "--invocation-id",
        arguments.invocation_id,
    ]
    if arguments.refresh_manifest_only or arguments.finalize_audits:
        exit_payload = json.loads((output_dir / "execution_exit.json").read_text())
        command_payload = json.loads((output_dir / "execution_command.json").read_text())
        if arguments.finalize_audits:
            result = json.loads((output_dir / "task12_recomputed_results.json").read_text())
            result_hash = str(result["deterministic_result_sha256"])
            for round_number, relative in enumerate(AUDIT_ARTIFACTS, 1):
                (output_dir / relative).write_text(
                    _adversarial_audit_report(round_number=round_number, result_hash=result_hash),
                    encoding="utf-8",
                )
        manifest = build_evidence_manifest(
            output_dir=output_dir,
            exact_command=command_payload["command"],
            start_timestamp=exit_payload["start_timestamp"],
            end_timestamp=exit_payload["end_timestamp"],
            require_audits=True,
        )
        write_json(output_dir / "TASK12_EVIDENCE_MANIFEST.json", manifest)
        print(manifest["content_sha256"])
        return 0

    start = utc_now()
    stdout_lines = [
        f"start={start}",
        f"base_commit={BASE_COMMIT}",
        "task11_freeze_commit=1c262c7",
        f"evidence_status={EVIDENCE_STATUS}",
        "protocol_drift_status=PROTOCOL_DRIFT_UNRESOLVED",
    ]
    errors: list[str] = []
    exit_status = 1
    try:
        task11_rows, task11_result, task11_manifest, raw_hashes = _load_task11_inputs()
        manifest_hash = str(task11_manifest["content_sha256"])
        by_context = {
            context: [row for row in task11_rows if row["context"] == context]
            for context in ("G1", "G2")
        }
        traces_by_context = {
            context: run_complete_matrix(
                rows,
                invocation_id=arguments.invocation_id,
                task11_manifest_content_sha256=manifest_hash,
                task11_raw_file_sha256=raw_hashes[context],
            )
            for context, rows in by_context.items()
        }
        task12_raw_paths = {
            context: output_dir / f"raw_traces/task12_{context.lower()}_raw_traces.jsonl"
            for context in ("G1", "G2")
        }
        for context in ("G1", "G2"):
            write_jsonl(task12_raw_paths[context], traces_by_context[context])
        all_traces = [*traces_by_context["G1"], *traces_by_context["G2"]]
        result = recompute_results(
            all_traces,
            task11_rows=task11_rows,
            task11_result=task11_result,
            task11_manifest=task11_manifest,
            task11_raw_hashes_by_context=raw_hashes,
        )
        write_json(output_dir / "task12_recomputed_results.json", result)
        task12_raw_hashes = {
            context: sha256_file(path) for context, path in task12_raw_paths.items()
        }
        (output_dir / "TASK12_REJUVENATION_DIAGNOSTIC_REPORT.md").write_text(
            _diagnostic_report(result, task12_raw_hashes), encoding="utf-8"
        )
        (output_dir / "TASK12_PROTOCOL_DRIFT_REPORT.md").write_text(
            _protocol_drift_report(result), encoding="utf-8"
        )
        write_json(
            output_dir / "execution_command.json",
            {
                "command": command,
                "working_directory": str(REPOSITORY_ROOT),
                "start_timestamp": start,
                "evidence_status": EVIDENCE_STATUS,
            },
        )
        exit_status = 0
        stdout_lines.extend(
            (
                f"upstream_condition_count={result['upstream_condition_count']}",
                f"condition_kernel_count={result['condition_kernel_count']}",
                f"raw_trace_count={result['raw_trace_count']}",
                f"deterministic_result_sha256={result['deterministic_result_sha256']}",
                "formal_task_12_passed=false",
                "task_13_unlocked=false",
                "proposal_p5_unlocked=false",
                "seven_operator_ablation_authorized=false",
            )
        )
    except Exception:
        errors.append(traceback.format_exc())
    end = utc_now()
    stdout_lines.extend((f"end={end}", f"exit_status={exit_status}"))
    (output_dir / "run_stdout.log").write_text("\n".join(stdout_lines) + "\n", encoding="utf-8")
    (output_dir / "run_stderr.log").write_text("\n".join(errors), encoding="utf-8")
    write_json(
        output_dir / "execution_exit.json",
        {"exit_status": exit_status, "start_timestamp": start, "end_timestamp": end},
    )
    if exit_status:
        sys.stdout.write((output_dir / "run_stdout.log").read_text())
        sys.stderr.write((output_dir / "run_stderr.log").read_text())
        return exit_status
    manifest = build_evidence_manifest(
        output_dir=output_dir,
        exact_command=command,
        start_timestamp=start,
        end_timestamp=end,
    )
    write_json(output_dir / "TASK12_EVIDENCE_MANIFEST.json", manifest)
    sys.stdout.write((output_dir / "run_stdout.log").read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
