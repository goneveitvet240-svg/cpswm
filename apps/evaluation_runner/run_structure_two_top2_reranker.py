"""Run or verify the Structure-Two visible-only top-two reranker."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cpswm.system.evaluation_operations.structure_two_top2_reranker import (
    DEFAULT_OUTPUT,
    run_top2_reranker,
    verify_top2_reranker,
    write_top2_reranker,
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
        report = verify_top2_reranker(
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
                    "development_gate_passed": report["development_gate_passed"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    report = run_top2_reranker(repository_root=root)
    write_top2_reranker(report, output)
    print(
        json.dumps(
            {
                "output": str(output),
                "content_sha256": report["content_sha256"],
                "selected_thresholds": report["selected_thresholds"],
                "summaries": report["summaries"],
                "paired_validation_comparisons": report["paired_validation_comparisons"],
                "development_gate_passed": report["development_gate_passed"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
