"""Run authority-separated Project One SHIFT ATG-2 and ATG-3 gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from pydantic import TypeAdapter

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from cpswm.system.evaluation_operations.online_shift_attribution import (  # noqa: E402
    OnlineShiftGeneratedCase,
    OnlineShiftSplit,
)
from cpswm.system.evaluation_operations.project_one_ablation_v0_2 import (  # noqa: E402
    ProjectOneProtocolPilotConfigV2,
    ProjectOneProtocolPilotRunnerV2,
)
from cpswm.system.evaluation_operations.project_one_shift_authority import (  # noqa: E402
    ShiftExperimentAuthority,
)
from cpswm.system.evaluation_operations.project_one_shift_gates import (  # noqa: E402
    MeasuredTuningBudget,
    ProjectOneShiftGateConfig,
    ProjectOneShiftGateReport,
    ProjectOneShiftGateRunner,
    ShiftATG2Draft,
    generate_frozen_shift_suite,
)
from cpswm.system.evaluation_operations.report_output import (  # noqa: E402
    ProtectedReportOutputError,
    write_report_atomic,
)
from cpswm.system.evaluation_operations.sealed_test_split import (  # noqa: E402
    SealedSplitMetadata,
    SealedTestSplit,
    split_artifact_manifest_sha256,
)
from cpswm.system.reproducibility import content_sha256  # noqa: E402

DEFAULT_CONFIG = REPOSITORY_ROOT / "benchmarks/project_one_ablation/project_one_shift_gates_v2.json"
DEFAULT_BASE_ATG1_CONFIG = (
    REPOSITORY_ROOT / "benchmarks/project_one_ablation/project_one_protocol_pilot_v0.2.json"
)
DEFAULT_OUTPUT = REPOSITORY_ROOT / "output/project_one_shift_gate_report_v2.json"
DEFAULT_EVENT_LOG = REPOSITORY_ROOT / "output/project_one_shift_gate_events_v2.json"

SNAPSHOT_PATHS = (
    "apps/evaluation_runner/run_project_one_shift_gates.py",
    "benchmarks/project_one_ablation/project_one_shift_gates_v2.json",
    "benchmarks/project_one_ablation/project_one_protocol_pilot_v0.2.json",
    "src/cpswm/system/evaluation_operations/fair_ablation.py",
    "src/cpswm/system/evaluation_operations/online_shift_attribution.py",
    "src/cpswm/system/evaluation_operations/project_one_ablation_v0_2.py",
    "src/cpswm/system/evaluation_operations/project_one_shift_authority.py",
    "src/cpswm/system/evaluation_operations/project_one_shift_gates.py",
    "src/cpswm/system/evaluation_operations/sealed_test_split.py",
    "src/cpswm/system/evaluation_operations/shift_baselines.py",
    "src/cpswm/world_model/habits_transitions/cause_factorized_bocpd.py",
    "src/cpswm/world_model/habits_transitions/joint_cause_bocpd.py",
    "tests/test_atg1_multi_round_adversarial.py",
    "tests/test_project_one_shift_gates.py",
)

CASES_ADAPTER = TypeAdapter(tuple[OnlineShiftGeneratedCase, ...])


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def code_snapshot_sha256() -> str:
    return content_sha256(
        {relative: _sha256_file(REPOSITORY_ROOT / relative) for relative in SNAPSHOT_PATHS}
    )


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _validate_event_log_path(path: Path) -> Path:
    resolved = path.resolve(strict=False)
    repository = REPOSITORY_ROOT.resolve()
    output_root = (repository / "output").resolve()
    if _is_within(resolved, repository) and not _is_within(resolved, output_root):
        raise ProtectedReportOutputError("repository event log is allowed only under output/")
    return resolved


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run validation-only tuning in a child process, then independently "
            "authorize and evaluate the frozen SHIFT TEST split."
        )
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--base-atg1-config", type=Path, default=DEFAULT_BASE_ATG1_CONFIG)
    parser.add_argument("--authority-key-file", type=Path)
    parser.add_argument("--event-log", type=Path, default=DEFAULT_EVENT_LOG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--tuning-worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--worker-topology", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--worker-validation", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--worker-budget", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--worker-code-snapshot", help=argparse.SUPPRESS)
    parser.add_argument("--worker-output", type=Path, help=argparse.SUPPRESS)
    return parser.parse_args()


def _run_tuning_worker(args: argparse.Namespace) -> int:
    required = (
        args.worker_topology,
        args.worker_validation,
        args.worker_budget,
        args.worker_code_snapshot,
        args.worker_output,
    )
    if any(item is None for item in required):
        raise ValueError("tuning worker requires topology, validation, budget, code, and output")
    from cpswm.system.evaluation_operations.project_one_ablation_v0_2 import (
        ProjectOneProtocolPilotReportV2,
    )

    topology = ProjectOneProtocolPilotReportV2.model_validate_json(
        args.worker_topology.read_text(encoding="utf-8")
    )
    validation = CASES_ADAPTER.validate_json(args.worker_validation.read_text(encoding="utf-8"))
    budget = MeasuredTuningBudget.model_validate_json(
        args.worker_budget.read_text(encoding="utf-8")
    )
    draft = ProjectOneShiftGateRunner().run_atg2(
        topology,
        validation,
        code_snapshot_sha256=args.worker_code_snapshot,
        budget=budget,
    )
    args.worker_output.write_text(draft.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return 0


def _load_authority_key(path: Path | None) -> bytes:
    if path is None:
        raise ValueError("--authority-key-file is required and is never passed to tuning")
    resolved = path.resolve(strict=True)
    if resolved.stat().st_mode & 0o077:
        raise PermissionError("authority key file permissions must be 0600 or stricter")
    return resolved.read_bytes()


def _build_topology(config: ProjectOneShiftGateConfig, base_path: Path, suite):
    base_bytes = base_path.resolve().read_bytes()
    if hashlib.sha256(base_bytes).hexdigest() != config.base_atg1_config_file_sha256:
        raise ValueError("base ATG-1 config file hash mismatch")
    base = ProjectOneProtocolPilotConfigV2.model_validate_json(base_bytes)
    train = tuple(
        case for case in suite.cases if case.evaluator_truth.split == OnlineShiftSplit.TRAIN
    )
    validation = tuple(
        case for case in suite.cases if case.evaluator_truth.split == OnlineShiftSplit.VALIDATION
    )
    test = tuple(
        case for case in suite.cases if case.evaluator_truth.split == OnlineShiftSplit.TEST
    )
    split_values = {
        "experiment_id": "project-one-shift-gates-v2",
        "train_split_sha256": content_sha256(train),
        "validation_split_sha256": content_sha256(validation),
        "test_split_sha256": content_sha256(test),
        "observation_trace_sha256": content_sha256(tuple(case.model_input for case in suite.cases)),
        "train_case_count": len(train),
        "validation_case_count": len(validation),
        "test_case_count": len(test),
    }
    metadata = SealedSplitMetadata(
        artifact_manifest_sha256=split_artifact_manifest_sha256(**split_values),
        artifact_manifest_case_count=len(suite.cases),
        **split_values,
    )
    topology_config = ProjectOneProtocolPilotConfigV2(
        comparison_budgets=base.comparison_budgets,
        split_metadata=metadata,
    )
    return (
        ProjectOneProtocolPilotRunnerV2().run(topology_config),
        validation,
        test,
    )


def _run_evaluator(args: argparse.Namespace) -> int:
    if args.authority_key_file is None:
        raise ValueError("--authority-key-file is required")
    protected_inputs = {
        args.config.resolve(strict=False),
        args.base_atg1_config.resolve(strict=False),
        args.authority_key_file.resolve(strict=False),
    }
    event_log_path = _validate_event_log_path(args.event_log)
    output_path = args.output.resolve(strict=False)
    if event_log_path in protected_inputs or output_path in protected_inputs:
        raise ProtectedReportOutputError(
            "report/event-log paths must not alias config, topology config, or signing key"
        )
    if event_log_path == output_path:
        raise ProtectedReportOutputError("report output and event log must be different files")
    config = ProjectOneShiftGateConfig.model_validate_json(
        args.config.resolve().read_text(encoding="utf-8")
    )
    suite = generate_frozen_shift_suite(config.suite)
    topology, validation, test = _build_topology(config, args.base_atg1_config, suite)
    snapshot_hash = code_snapshot_sha256()

    with tempfile.TemporaryDirectory(prefix="project-one-shift-tuning-") as directory:
        exchange = Path(directory)
        topology_path = exchange / "topology.json"
        validation_path = exchange / "validation.json"
        budget_path = exchange / "budget.json"
        draft_path = exchange / "atg2-draft.json"
        topology_path.write_text(topology.model_dump_json(), encoding="utf-8")
        validation_path.write_text(
            json.dumps(
                CASES_ADAPTER.dump_python(validation, mode="json"),
                sort_keys=True,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        budget_path.write_text(config.tuning_budget.model_dump_json(), encoding="utf-8")
        completed = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--tuning-worker",
                "--worker-topology",
                str(topology_path),
                "--worker-validation",
                str(validation_path),
                "--worker-budget",
                str(budget_path),
                "--worker-code-snapshot",
                snapshot_hash,
                "--worker-output",
                str(draft_path),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"validation-only tuning worker failed: {completed.stderr}")
        draft = ShiftATG2Draft.model_validate_json(draft_path.read_text(encoding="utf-8"))

    authority = ShiftExperimentAuthority(
        key=_load_authority_key(args.authority_key_file),
        key_id=config.authority_key_id,
        log_path=event_log_path,
    )
    atg2 = authority.commit_atg2(draft)
    sealed_test = SealedTestSplit(
        test,
        experiment_id=topology.manifest.experiment_id,
        test_split_sha256=content_sha256(test),
        required_validation_split_sha256=content_sha256(validation),
        required_receipt_scope="project-one-shift-atg3",
    )
    atg3 = ProjectOneShiftGateRunner().run_atg3(
        topology,
        atg2,
        sealed_test,
        authority=authority,
        expected_code_snapshot_sha256=snapshot_hash,
        power_analysis=config.power_analysis,
        bootstrap_samples=config.bootstrap_samples,
    )
    atg3_completion = authority.commit_atg3(atg3)
    payload = {
        "protocol_version": "project-one-shift-gates@2",
        "frozen_suite_config": config.suite,
        "atg1_topology_report": topology,
        "atg2": atg2,
        "atg3": atg3,
        "atg3_completion_commit": atg3_completion,
    }
    report = ProjectOneShiftGateReport(
        **payload,
        report_sha256=content_sha256(payload),
    )
    if not authority.verify_complete_report(report):
        raise RuntimeError("independent authority rejected the completed gate report")
    rendered = report.model_dump_json(indent=2) + "\n"
    try:
        write_report_atomic(
            rendered,
            output_path=args.output,
            config_path=args.config,
            repository_root=REPOSITORY_ROOT,
            force=args.force,
        )
    except (FileExistsError, ProtectedReportOutputError) as exc:
        print(f"refusing report output: {exc}", file=sys.stderr)
        return 2
    print(rendered)
    return 0


def main() -> int:
    args = parse_args()
    return _run_tuning_worker(args) if args.tuning_worker else _run_evaluator(args)


if __name__ == "__main__":
    raise SystemExit(main())
