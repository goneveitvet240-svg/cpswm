"""Run the scoped Project One SHIFT ATG-2 and ATG-3 gates."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from cpswm.system.evaluation_operations.online_shift_attribution import (  # noqa: E402
    OnlineShiftSplit,
    OnlineShiftSuiteGenerator,
)
from cpswm.system.evaluation_operations.project_one_ablation_v0_2 import (  # noqa: E402
    ProjectOneProtocolPilotReportV2,
)
from cpswm.system.evaluation_operations.project_one_shift_gates import (  # noqa: E402
    ProjectOneShiftGateConfig,
    ProjectOneShiftGateReport,
    ProjectOneShiftGateRunner,
)
from cpswm.system.evaluation_operations.report_output import (  # noqa: E402
    ProtectedReportOutputError,
    write_report_atomic,
)
from cpswm.system.evaluation_operations.sealed_test_split import (  # noqa: E402
    SealedTestSplit,
)
from cpswm.system.reproducibility import content_sha256  # noqa: E402

DEFAULT_CONFIG = REPOSITORY_ROOT / "benchmarks/project_one_ablation/project_one_shift_gates_v1.json"
DEFAULT_TOPOLOGY_REPORT = (
    REPOSITORY_ROOT
    / "benchmarks/project_one_ablation/project_one_protocol_pilot_report_v0.2.fixture.json"
)
DEFAULT_OUTPUT = REPOSITORY_ROOT / "output/project_one_shift_gate_report_v1.json"

SNAPSHOT_PATHS = (
    "apps/evaluation_runner/run_project_one_shift_gates.py",
    "benchmarks/project_one_ablation/project_one_shift_gates_v1.json",
    "benchmarks/project_one_ablation/project_one_protocol_pilot_v0.2.json",
    "benchmarks/project_one_ablation/project_one_protocol_pilot_report_v0.2.fixture.json",
    "src/cpswm/system/evaluation_operations/fair_ablation.py",
    "src/cpswm/system/evaluation_operations/online_shift_attribution.py",
    "src/cpswm/system/evaluation_operations/project_one_ablation_v0_2.py",
    "src/cpswm/system/evaluation_operations/project_one_shift_gates.py",
    "src/cpswm/system/evaluation_operations/sealed_test_split.py",
    "src/cpswm/system/evaluation_operations/shift_baselines.py",
    "src/cpswm/world_model/habits_transitions/cause_factorized_bocpd.py",
    "src/cpswm/world_model/habits_transitions/joint_cause_bocpd.py",
    "tests/test_atg1_multi_round_adversarial.py",
    "tests/test_project_one_shift_gates.py",
)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def code_snapshot_sha256() -> str:
    return content_sha256(
        {relative: _sha256_file(REPOSITORY_ROOT / relative) for relative in SNAPSHOT_PATHS}
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run independent validation tuning and receipt-gated frozen TEST for "
            "the executable SHIFT three-arm comparison."
        )
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--topology-report", type=Path, default=DEFAULT_TOPOLOGY_REPORT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = ProjectOneShiftGateConfig.model_validate_json(
        args.config.resolve().read_text(encoding="utf-8")
    )
    topology_bytes = args.topology_report.resolve().read_bytes()
    if hashlib.sha256(topology_bytes).hexdigest() != config.atg1_report_file_sha256:
        raise ValueError("configured ATG-1 report file hash mismatch")
    topology = ProjectOneProtocolPilotReportV2.model_validate_json(topology_bytes)
    suite = OnlineShiftSuiteGenerator().generate(config.suite)
    validation = tuple(
        case for case in suite.cases if case.evaluator_truth.split == OnlineShiftSplit.VALIDATION
    )
    test = tuple(
        case for case in suite.cases if case.evaluator_truth.split == OnlineShiftSplit.TEST
    )
    sealed_test = SealedTestSplit(
        test,
        experiment_id=topology.manifest.experiment_id,
        test_split_sha256=content_sha256(test),
        required_validation_split_sha256=content_sha256(validation),
        required_receipt_scope="project-one-shift-atg3",
    )
    runner = ProjectOneShiftGateRunner()
    snapshot_hash = code_snapshot_sha256()
    atg2 = runner.run_atg2(
        topology,
        validation,
        code_snapshot_sha256=snapshot_hash,
        budget=config.tuning_budget,
    )
    atg3 = runner.run_atg3(
        topology,
        atg2,
        sealed_test,
        expected_code_snapshot_sha256=snapshot_hash,
        bootstrap_samples=config.bootstrap_samples,
    )
    payload = {
        "protocol_version": config.protocol_version,
        "atg1_topology_report": topology,
        "atg2": atg2,
        "atg3": atg3,
    }
    report = ProjectOneShiftGateReport(
        **payload,
        report_sha256=content_sha256(payload),
    )
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


if __name__ == "__main__":
    raise SystemExit(main())
