"""Run the CF-BOCPD direct-baseline gate: ordinary / independent / joint / BOCPDMS.

``--seeds`` is seeds *per split*.  ``0`` keeps the nine frozen seeds behind the
existing ATG artifacts (three per split, 18 test cases) so that reading stays
reproducible.  Any positive value draws from a reserved range far above every
frozen seed, so a scaled run can never reuse a sealed test seed.

Three test seeds cannot settle a 0.03 effect.  Scale before believing a verdict.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from cpswm.system.evaluation_operations.project_one_shift_four_arm import (  # noqa: E402
    GUARDRAIL_METRIC,
    PRIMARY_METRIC,
    format_four_arm_table,
    run_four_arm_comparison,
    scaled_seed_partition,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seeds",
        type=int,
        default=0,
        help="seeds per split; 0 keeps the nine frozen seeds",
    )
    parser.add_argument("--output", type=Path, default=None)
    arguments = parser.parse_args()

    config = scaled_seed_partition(arguments.seeds) if arguments.seeds else None
    payload = run_four_arm_comparison(config)

    print(format_four_arm_table(payload))
    print()
    suite = payload["suite"]
    print(f"validation cases={suite['validation_cases']}  test cases={suite['test_cases']}")
    print(f"tuning budget per arm={payload['tuning_budget_per_arm']}")
    print()
    for arm, comparison in payload["comparisons_vs_candidate"].items():
        print(
            f"  joint vs {arm:<30} "
            f"{PRIMARY_METRIC} {comparison['primary_paired_mean_candidate_minus_control']:+.4f} "
            f"ci={[round(value, 4) for value in comparison['primary_ci95']]} "
            f"win={comparison['primary_candidate_wins']}  |  "
            f"{GUARDRAIL_METRIC} "
            f"{comparison['guardrail_paired_mean_control_minus_candidate']:+.4f} "
            f"ci={[round(value, 4) for value in comparison['guardrail_ci95']]} "
            f"candidate_loses={comparison['guardrail_candidate_loses']}"
        )
    print()
    print(f"ledger transition: {payload['ledger_transition']}")
    for finding in payload["blocking_findings"]:
        print(f"  BLOCKING: {finding}")

    if arguments.output is not None:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"wrote {arguments.output}")


if __name__ == "__main__":
    main()
