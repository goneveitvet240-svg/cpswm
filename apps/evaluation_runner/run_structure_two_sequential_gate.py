"""Run or verify the frozen Structure Two sequential consolidation gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cpswm.system.evaluation_operations.structure_two_sequential_gate import (
    run_sequential_consolidation_gate,
    verify_sequential_consolidation_gate_report,
    write_sequential_consolidation_gate_report,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--recompute", action="store_true")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "artifacts/project_two_v04_development/"
            "structure_two_sequential_consolidation_gate_v0_1.json"
        ),
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    if args.verify_only:
        report = verify_sequential_consolidation_gate_report(
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
                    "mechanism_gate_passed": report["mechanism_gate_passed"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    report = run_sequential_consolidation_gate(repository_root=root)
    write_sequential_consolidation_gate_report(report, args.output)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "content_sha256": report["content_sha256"],
                "mechanism_gate_passed": report["mechanism_gate_passed"],
                "gate_criteria": report["gate_criteria"],
                "paired_cluster_comparisons": report["paired_cluster_comparisons"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
