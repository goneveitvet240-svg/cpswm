"""Run or verify the Structure-Two action-information upper-bound diagnostic."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cpswm.system.evaluation_operations.structure_two_action_information_upper_bound import (
    DEFAULT_OUTPUT,
    run_action_information_upper_bound,
    verify_action_information_upper_bound,
    write_action_information_upper_bound,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--recompute", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    output = args.output if args.output.is_absolute() else root / args.output
    if args.verify_only:
        report = verify_action_information_upper_bound(
            output,
            repository_root=root,
            recompute=args.recompute,
        )
        print(
            json.dumps(
                {
                    "verified": True,
                    "recomputed": args.recompute,
                    "content_sha256": report["content_sha256"],
                    "diagnostic_criteria": report["diagnostic_criteria"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    report = run_action_information_upper_bound(repository_root=root)
    write_action_information_upper_bound(report, output)
    print(
        json.dumps(
            {
                "output": str(output),
                "content_sha256": report["content_sha256"],
                "best_fixed_operator": report["best_fixed_operator"],
                "diagnostic_criteria": report["diagnostic_criteria"],
                "paired_episode_comparisons": report["paired_episode_comparisons"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
