"""Run the fresh-seed interactive CIAV development protocol."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cpswm.system.evaluation_operations.project_two_ciav_interactive_development import (
    run_ciav_interactive_development,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validation-start", type=int, default=14000)
    parser.add_argument("--validation-count", type=int, default=20)
    parser.add_argument("--holdout-start", type=int, default=15000)
    parser.add_argument("--holdout-count", type=int, default=60)
    parser.add_argument("--max-steps", type=int, default=32)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/project_two_v04_development/ciav_interactive_v0_1.json"),
    )
    args = parser.parse_args()
    report = run_ciav_interactive_development(
        validation_seeds=tuple(
            range(args.validation_start, args.validation_start + args.validation_count)
        ),
        holdout_seeds=tuple(range(args.holdout_start, args.holdout_start + args.holdout_count)),
        max_steps=args.max_steps,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
