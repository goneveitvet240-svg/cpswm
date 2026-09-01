"""Run or verify the frozen consolidation compatibility gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cpswm.system.evaluation_operations.structure_two_consolidation_compatibility import (
    run_consolidation_compatibility_gate,
    verify_consolidation_compatibility_report,
    write_consolidation_compatibility_report,
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
            "structure_two_consolidation_compatibility_gate_v0_1.json"
        ),
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    if args.verify_only:
        report = verify_consolidation_compatibility_report(
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
                    "mitigation_gate_passed": report["mitigation_gate_passed"],
                    "positive_contribution_candidate": report["positive_contribution_candidate"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    report = run_consolidation_compatibility_gate(repository_root=root)
    write_consolidation_compatibility_report(report, args.output)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "content_sha256": report["content_sha256"],
                "mitigation_gate_passed": report["mitigation_gate_passed"],
                "positive_contribution_candidate": report["positive_contribution_candidate"],
                "gate_criteria": report["gate_criteria"],
                "paired_cluster_comparisons": report["paired_cluster_comparisons"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
