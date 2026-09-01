"""Run or verify the frozen structured residual transition gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cpswm.system.evaluation_operations.structure_two_structured_residual import (
    run_structured_residual_gate,
    verify_structured_residual_report,
    write_structured_residual_report,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--recompute", action="store_true")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "artifacts/project_two_v04_development/structure_two_structured_residual_gate_v0_1.json"
        ),
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    if args.verify_only:
        report = verify_structured_residual_report(
            args.output,
            repository_root=root,
            recompute=args.recompute,
        )
        print(
            json.dumps(
                {
                    "verified": True,
                    "recomputed": args.recompute,
                    "content_sha256": report["content_sha256"],
                    "structured_residual_gate_passed": report["structured_residual_gate_passed"],
                },
                indent=2,
            )
        )
        return
    report = run_structured_residual_gate(repository_root=root)
    write_structured_residual_report(report, args.output)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "content_sha256": report["content_sha256"],
                "structured_residual_gate_passed": report["structured_residual_gate_passed"],
                "gate_criteria": report["gate_criteria"],
                "paired_cluster_comparisons": report["paired_cluster_comparisons"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
