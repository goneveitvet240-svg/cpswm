"""Run the preregistered project-two AMG action-interface audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cpswm.system.evaluation_operations.project_two_amg_interface_audit import (
    run_amg_action_interface_audit,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validation-start", type=int, default=19000)
    parser.add_argument("--validation-count", type=int, default=4)
    parser.add_argument("--holdout-start", type=int, default=20000)
    parser.add_argument("--holdout-count", type=int, default=12)
    parser.add_argument("--max-steps", type=int, default=32)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/project_two_v04_development/amg_interface_audit_v0_1.json"),
    )
    args = parser.parse_args()
    report = run_amg_action_interface_audit(
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
