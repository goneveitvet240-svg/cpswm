"""Run the fresh-seed seven-operator factorial development benchmark."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from cpswm.system.evaluation_operations.project_two_factorial_benchmark import (  # noqa: E402
    TrustedSevenOperatorAuthorizationRequired,
    run_project_two_factorial_benchmark,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validation-start", type=int, default=33000)
    parser.add_argument("--validation-count", type=int, default=2)
    parser.add_argument("--holdout-start", type=int, default=34000)
    parser.add_argument("--holdout-count", type=int, default=6)
    parser.add_argument("--max-steps", type=int, default=16)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/project_two_v04_development/seven_operator_factorial_v0_1.json"),
    )
    args = parser.parse_args()
    if args.validation_count < 1 or args.holdout_count < 1:
        parser.error("split counts must be positive")
    try:
        report = run_project_two_factorial_benchmark(
            validation_seeds=tuple(
                range(args.validation_start, args.validation_start + args.validation_count)
            ),
            holdout_seeds=tuple(range(args.holdout_start, args.holdout_start + args.holdout_count)),
            max_steps=args.max_steps,
        )
    except TrustedSevenOperatorAuthorizationRequired as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"authorized factorial report wrote={args.output}")


if __name__ == "__main__":
    main()
