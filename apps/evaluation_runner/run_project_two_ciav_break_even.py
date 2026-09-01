"""Run the preregistered CIAV accuracy--cost surface."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cpswm.system.evaluation_operations.project_two_ciav_break_even import (
    run_ciav_accuracy_cost_break_even,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed-start", type=int, default=18000)
    parser.add_argument("--seed-count", type=int, default=12)
    parser.add_argument("--max-steps", type=int, default=32)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/project_two_v04_development/ciav_accuracy_cost_v0_1.json"),
    )
    args = parser.parse_args()
    report = run_ciav_accuracy_cost_break_even(
        evaluation_seeds=tuple(range(args.seed_start, args.seed_start + args.seed_count)),
        max_steps=args.max_steps,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
