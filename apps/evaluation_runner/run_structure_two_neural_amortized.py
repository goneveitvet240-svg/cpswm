"""Run or verify the frozen neural amortized proposal gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cpswm.system.evaluation_operations.structure_two_neural_amortized import (
    run_neural_amortized_gate,
    verify_neural_amortized_report,
    write_neural_amortized_report,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--recompute", action="store_true")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "artifacts/project_two_v04_development/structure_two_neural_amortized_gate_v0_1.json"
        ),
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    if args.verify_only:
        report = verify_neural_amortized_report(
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
                    "neural_mechanism_gate_passed": report["neural_mechanism_gate_passed"],
                },
                indent=2,
            )
        )
        return
    report = run_neural_amortized_gate(repository_root=root)
    write_neural_amortized_report(report, args.output)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "content_sha256": report["content_sha256"],
                "neural_mechanism_gate_passed": report["neural_mechanism_gate_passed"],
                "gate_criteria": report["gate_criteria"],
                "paired_cluster_comparisons": report["paired_cluster_comparisons"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
