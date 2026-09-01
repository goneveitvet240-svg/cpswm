"""Run or verify the frozen CARE-WM exact-counterfactual micro gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cpswm.system.evaluation_operations.care_wm_exact_counterfactual import (
    run_care_wm_exact_counterfactual_gate,
    verify_care_wm_exact_counterfactual_report,
    write_care_wm_exact_counterfactual_report,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--recompute", action="store_true")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "artifacts/project_two_v04_development/care_wm_exact_counterfactual_gate_v0_1.json"
        ),
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    if args.verify_only:
        report = verify_care_wm_exact_counterfactual_report(
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
                    "candidate_positive_mechanism": report["candidate_positive_mechanism"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    report = run_care_wm_exact_counterfactual_gate(repository_root=root)
    write_care_wm_exact_counterfactual_report(report, args.output)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "content_sha256": report["content_sha256"],
                "candidate_positive_mechanism": report["candidate_positive_mechanism"],
                "gate_criteria": report["gate_criteria"],
                "paired_cluster_comparisons": report["paired_cluster_comparisons"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
