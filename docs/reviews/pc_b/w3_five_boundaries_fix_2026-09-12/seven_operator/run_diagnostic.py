"""Run the current production-path seven-operator engineering diagnostic."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[4]
PYTHON = Path(sys.executable).resolve()
R7 = ROOT / "docs" / "reviews" / "pc_a" / "w3_backbone_r7_2026-09-12"


def sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def source_snapshot() -> dict[str, object]:
    files = {
        path.relative_to(ROOT).as_posix(): sha256_bytes(path.read_bytes())
        for path in sorted((ROOT / "src").rglob("*.py"))
    }
    encoded = json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    return {"files": files, "aggregate_sha256": sha256_bytes(encoded)}


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


records: list[dict[str, object]] = []


def run(
    label: str,
    command: list[str],
    *,
    expected_exit_codes: tuple[int, ...] = (0,),
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    started_wall = time.time()
    started = time.perf_counter()
    env = os.environ.copy()
    if environment:
        env.update(environment)
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    stdout_path = OUT / f"{label}.stdout.log"
    stderr_path = OUT / f"{label}.stderr.log"
    stdout_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")
    records.append(
        {
            "label": label,
            "command": command,
            "cwd": str(ROOT),
            "started_unix": started_wall,
            "elapsed_seconds": time.perf_counter() - started,
            "exit_code": completed.returncode,
            "expected_exit_codes": list(expected_exit_codes),
            "outcome_as_expected": completed.returncode in expected_exit_codes,
            "stdout": stdout_path.name,
            "stdout_sha256": sha256_bytes(stdout_path.read_bytes()),
            "stderr": stderr_path.name,
            "stderr_sha256": sha256_bytes(stderr_path.read_bytes()),
        }
    )
    return completed


def compress_trace(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    compressed = gzip.compress(raw, compresslevel=9, mtime=0)
    target = path.with_suffix(path.suffix + ".gz")
    target.write_bytes(compressed)
    path.unlink()
    return {
        "artifact": target.name,
        "uncompressed_bytes": len(raw),
        "uncompressed_sha256": sha256_bytes(raw),
        "gzip_bytes": len(compressed),
        "gzip_sha256": sha256_bytes(compressed),
    }


def main() -> int:
    started = time.time()
    before = source_snapshot()
    head = git("rev-parse", "HEAD")
    production_commit = git("log", "-1", "--format=%H", "--", "src")
    initial_status = git("status", "--short")
    metadata = {
        "classification": "engineering causal diagnostic; not scientific acceptance",
        "started_unix": started,
        "git_head": head,
        "last_commit_touching_src": production_commit,
        "head_vs_production_src_diff_names": git(
            "diff", "--name-only", f"{production_commit}..{head}", "--", "src"
        ).splitlines(),
        "python": sys.version,
        "python_executable": str(PYTHON),
        "platform": platform.platform(),
        "initial_git_status": initial_status.splitlines(),
        "source_before": before,
        "driver_command": [str(PYTHON), str(Path(__file__).resolve())],
    }
    (OUT / "environment_and_source_binding.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    trace_artifacts: dict[str, dict[str, object]] = {}
    ordinary = R7 / "continuous_connections.py"
    openworld = R7 / "continuous_connections_openworld.py"
    for variant in ("base", "null", "opceu", "orrer", "pchmp", "identity", "ciav"):
        raw_output = OUT / f"continuous_current_{variant}.json"
        run(
            f"continuous_{variant}",
            [str(PYTHON), str(ordinary), variant, str(raw_output)],
        )
        if raw_output.exists():
            trace_artifacts[variant] = compress_trace(raw_output)
    raw_output = OUT / "continuous_current_openworld.json"
    run(
        "continuous_openworld",
        [str(PYTHON), str(openworld), "openworld", str(raw_output)],
    )
    if raw_output.exists():
        trace_artifacts["openworld"] = compress_trace(raw_output)

    test_env = {
        "PYTHONHASHSEED": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": os.pathsep.join((str(ROOT / "src"), str(ROOT / "tests"))),
    }
    pytest_base = [
        str(PYTHON),
        "-m",
        "pytest",
        "-o",
        "addopts=",
        "-q",
        "-p",
        "no:cacheprovider",
    ]
    groups = {
        "pytest_operator_causal_matrix": ["tests/test_structure_two_operator_causal_matrix.py"],
        "pytest_history_scenarios": [
            "tests/test_structure_two_backbone_operator_wiring.py::test_positive_observation_different_location_runs_the_full_thirteen_call_closure",
            "tests/test_structure_two_backbone_operator_wiring.py::test_negative_observation_stops_at_seven_receipts_and_leaves_no_partial_closure",
            "tests/test_structure_two_backbone_operator_wiring.py::test_open_actor_support_is_preserved_end_to_end_and_support_drift_is_refused",
            "tests/test_structure_two_backbone_operator_wiring.py::test_unknown_actor_mass_survives_a_full_open_world_timeline",
            "tests/test_structure_two_backbone_operator_wiring.py::test_regime_creation_and_reactivation_happen_on_the_production_direct_p5_path",
            "tests/test_structure_two_backbone_operator_wiring.py::test_p0_defers_orrer_and_ciav_behind_exactly_one_bound_debt_certificate",
            "tests/test_structure_two_backbone_operator_wiring.py::test_expired_debt_replay_runs_p5_settles_once_and_refuses_a_repeat",
            "tests/test_structure_two_backbone_operator_wiring.py::test_direct_p5_and_debt_replay_agree_on_every_semantic_quantity",
            "tests/test_orrer_event_revision.py::test_orrer_enumerates_unknown_actor_in_both_handoff_roles",
            "tests/test_orrer_event_revision.py::test_orrer_reactivates_a_true_handoff_after_wrong_mechanism_pruning",
            "tests/test_structure_two_w3_operator_acceptance.py::test_real_feedback_loop_engine_message_passing_and_statistic_application",
            "tests/test_structure_two_w3_operator_acceptance.py::test_same_class_foreign_extra_instance_is_refused",
        ],
        "pytest_negative_observation": [
            "tests/test_structure_two_ciav_negative_observation_layers.py"
        ],
        "pytest_deferred_cancel_recovery": [
            "tests/test_structure_two_w3_deferred_cancellation.py"
        ],
        "pytest_reference_only_similar_instance_contract": [
            "tests/test_direction_three_oracle_suite.py::test_oracle_suite_covers_complete_s3_1_scenario_semantics"
        ],
    }
    for label, tests in groups.items():
        run(
            label,
            [*pytest_base, f"--junitxml={OUT / (label + '.xml')}", *tests],
            environment=test_env,
        )

    base_trace = OUT / trace_artifacts["base"]["artifact"]
    run(
        "capability_gap_probe",
        [
            str(PYTHON),
            str(OUT / "capability_gap_probe.py"),
            str(base_trace),
            str(OUT / "capability_gaps.json"),
        ],
        expected_exit_codes=(2,),
    )

    after = source_snapshot()
    metadata.update(
        {
            "finished_unix": time.time(),
            "elapsed_seconds": time.time() - started,
            "source_after": after,
            "source_unchanged": before == after,
            "final_git_status": git("status", "--short").splitlines(),
            "trace_artifacts": trace_artifacts,
        }
    )
    (OUT / "environment_and_source_binding.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    all_expected = all(bool(record["outcome_as_expected"]) for record in records)
    summary = {
        "driver_exit_code": 0 if all_expected and before == after else 1,
        "all_command_outcomes_as_expected": all_expected,
        "source_unchanged": before == after,
        "records": records,
    }
    (OUT / "commands.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "git_head": head,
                "production_commit": production_commit,
                "commands": len(records),
                "all_expected": all_expected,
                "source_unchanged": before == after,
            },
            ensure_ascii=False,
        )
    )
    return int(not (all_expected and before == after))


if __name__ == "__main__":
    raise SystemExit(main())
