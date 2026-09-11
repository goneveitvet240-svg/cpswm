#!/usr/bin/env python3
"""Run a development-only audit; never reopen or relabel an unseen holdout."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cpswm.system.evaluation_operations.structure_two_comparison_audit import (
    run_audit,
    save,
    verify,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--verify",
        action="store_true",
        help="fresh rerun; compare semantic results without overwriting",
    )
    parser.add_argument("--timing-repeats", type=int, default=3)
    parser.add_argument("--timing-episodes", type=int, default=2)
    args = parser.parse_args()
    if args.timing_repeats < 1 or not 1 <= args.timing_episodes <= 60:
        parser.error("positive timing repeats and 1..60 timing episodes required")
    root = args.repository_root.resolve()
    output = args.output.resolve()
    if not args.verify and any(
        (output / name).exists() for name in ("audit.json", "steps.jsonl.gz", "timing.json")
    ):
        parser.error("output already exists; choose --verify or a new directory")
    payload, rows, timing = run_audit(
        root, timing_repeats=args.timing_repeats, timing_episodes=args.timing_episodes
    )
    if args.verify:
        verify(output, payload, rows)
    else:
        save(output, payload, rows, timing)
    print(
        json.dumps(
            {
                "verified" if args.verify else "output": str(output),
                "steps": len(rows),
                "retained_score_mismatches": payload["retained_score_mismatches"],
                "semantic_steps_sha256": payload["semantic_steps_sha256"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
