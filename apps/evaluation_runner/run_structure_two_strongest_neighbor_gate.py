"""Run or verify the frozen Structure-Two strongest-neighbor gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cpswm.system.evaluation_operations.structure_two_strongest_neighbor_gate import (
    run_structure_two_strongest_neighbor_gate,
    verify_structure_two_strongest_neighbor_report,
    write_structure_two_strongest_neighbor_report,
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
            "structure_two_strongest_neighbor_gate_current_source_v0_3.json"
        ),
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    output = args.output if args.output.is_absolute() else root / args.output
    if args.verify_only:
        report = verify_structure_two_strongest_neighbor_report(
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
                    "selected_strongest_published_neighbor": report[
                        "selected_strongest_published_neighbor"
                    ],
                    "strongest_neighbor_gate_passed": report["strongest_neighbor_gate_passed"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    report = run_structure_two_strongest_neighbor_gate(repository_root=root)
    write_structure_two_strongest_neighbor_report(report, output)
    print(
        json.dumps(
            {
                "output": str(output),
                "content_sha256": report["content_sha256"],
                "selected_strongest_published_neighbor": report[
                    "selected_strongest_published_neighbor"
                ],
                "strongest_neighbor_gate_passed": report["strongest_neighbor_gate_passed"],
                "gate_criteria": report["gate_criteria"],
                "paired_cluster_comparisons": report["paired_cluster_comparisons"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
