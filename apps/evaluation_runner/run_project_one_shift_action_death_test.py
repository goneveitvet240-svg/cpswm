"""Run the preregistered Project One SHIFT action-level death test."""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from cpswm.system.evaluation_operations.project_one_shift_action_death_test import (  # noqa: E402
    ProjectOneShiftActionDeathTestConfig,
    ProjectOneShiftActionDeathTestRunner,
)
from cpswm.system.evaluation_operations.report_output import (  # noqa: E402
    write_report_atomic,
)
from cpswm.system.reproducibility import content_sha256  # noqa: E402

DEFAULT_CONFIG = REPOSITORY_ROOT / (
    "benchmarks/project_one_ablation/project_one_shift_action_death_test_v5.json"
)
DEFAULT_OUTPUT = REPOSITORY_ROOT / "output/project_one_shift_action_death_test_v5.json"

SNAPSHOT_PATHS = (
    "apps/evaluation_runner/run_project_one_shift_action_death_test.py",
    "src/cpswm/system/evaluation_operations/online_shift_attribution.py",
    "src/cpswm/system/evaluation_operations/project_one_shift_action_death_test.py",
    "src/cpswm/system/evaluation_operations/project_one_shift_gates.py",
    "src/cpswm/system/evaluation_operations/shift_baselines.py",
    "src/cpswm/world_model/habits_transitions/cause_factorized_bocpd.py",
    "src/cpswm/world_model/habits_transitions/joint_cause_bocpd.py",
    "tests/test_project_one_shift_action_death_test.py",
)


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def code_snapshot_sha256(config_path: Path = DEFAULT_CONFIG) -> str:
    resolved_config = config_path.resolve(strict=True)
    relative_config = str(resolved_config.relative_to(REPOSITORY_ROOT))
    versioned_paths = [relative_config]
    if resolved_config.stem.endswith("_v6"):
        versioned_paths.extend(
            (
                "docs/experiments/project_one_shift_action_death_test_v6_preregistration.md",
                "tests/test_project_one_action_policy_v6.py",
            )
        )
    else:
        versioned_paths.append("docs/reviews/项目一_SHIFT行动级死亡测试预注册_v5.md")
    return content_sha256(
        {
            relative: _file_sha256(REPOSITORY_ROOT / relative)
            for relative in (*SNAPSHOT_PATHS, *versioned_paths)
        }
    )


def git_commit_sha() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the validation-retuned three-arm SHIFT action death test."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = ProjectOneShiftActionDeathTestConfig.model_validate_json(
        args.config.resolve(strict=True).read_text(encoding="utf-8")
    )
    report = ProjectOneShiftActionDeathTestRunner().run(
        config,
        code_snapshot_sha256=code_snapshot_sha256(args.config),
        git_commit_sha=git_commit_sha(),
    )
    write_report_atomic(
        report.model_dump_json(indent=2) + "\n",
        output_path=args.output,
        config_path=args.config,
        repository_root=REPOSITORY_ROOT,
        force=args.force,
    )
    print(f"shared_decision={report.decision.decision.value}")
    print(f"retuned_decision={report.retuned_decision.decision.value}")
    print(f"overall_decision={report.overall_decision.decision.value}")
    print(f"report_sha256={report.report_sha256}")
    print(f"code_snapshot_sha256={report.code_snapshot_sha256}")
    print(f"git_commit_sha={report.git_commit_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
