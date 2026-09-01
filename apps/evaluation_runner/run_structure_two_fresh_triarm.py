"""Run the frozen fresh-family Structure Two three-arm action comparison."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cpswm.system.evaluation_operations.structure_two_fresh_triarm import (
    run_fresh_multiaxis_triarm,
    verify_fresh_multiaxis_triarm_report,
    write_fresh_multiaxis_triarm_report,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--recompute", action="store_true")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "artifacts/project_two_v04_development/structure_two_fresh_multiaxis_triarm_v0_1.json"
        ),
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    if args.verify_only:
        report = verify_fresh_multiaxis_triarm_report(
            args.output,
            repository_root=root,
            recompute=args.recompute,
        )
        print(
            json.dumps(
                {
                    "output": str(args.output),
                    "verified": True,
                    "recomputed": args.recompute,
                    "content_sha256": report["content_sha256"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    report = run_fresh_multiaxis_triarm(repository_root=root)
    write_fresh_multiaxis_triarm_report(report, args.output)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "content_sha256": report["content_sha256"],
                "all_multiaxis_sensitivity_gates_passed": report[
                    "all_multiaxis_sensitivity_gates_passed"
                ],
                "paired_cluster_comparisons": report["paired_cluster_comparisons"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
