"""Run only the preregistered v0.2 placement-authority development households."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from cpswm.system.evaluation_operations.placement_authority_development import (  # noqa: E402
    run_placement_authority_development,
)
from cpswm.system.evaluation_operations.report_output import write_report_atomic  # noqa: E402

DEFAULT_CONFIG = ROOT / "configs/method_falsification/placement_authority_v0_2_preregistration.json"
DEFAULT_OUTPUT = (
    ROOT / "output/method_falsification/placement_authority_v0_2_development_report.json"
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    report = run_placement_authority_development(
        args.config,
        repository_root=ROOT,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    write_report_atomic(
        rendered,
        output_path=args.output,
        config_path=args.config,
        repository_root=ROOT,
        force=args.force,
    )
    print(
        json.dumps(
            {
                "output": str(args.output.resolve()),
                "scientific_status": report["scientific_status"],
                "development_households": report["development_household_count"],
                "diagnostic_episodes": report["diagnostic_episode_count"],
                "all_candidate_attacks_passed": report["all_candidate_attacks_passed"],
                "sealed_test_access_count": report["sealed_test_access_count"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
