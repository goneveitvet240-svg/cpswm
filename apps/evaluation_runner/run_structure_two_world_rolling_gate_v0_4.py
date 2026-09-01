#!/usr/bin/env python3
"""Run or verify the retrospective Structure-Two v0.4 train outer-CV gate."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cpswm.system.evaluation_operations.structure_two_world_rolling_gate_v0_4 import (  # noqa: E402
    DEFAULT_OUTPUT,
    run_rolling_train_outer_cv_gate,
    verify_rolling_train_gate_report,
    write_rolling_train_gate_report,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--replace-retrospective-artifact", action="store_true")
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    if args.verify:
        report = verify_rolling_train_gate_report(
            output,
            repository_root=ROOT,
            recompute=True,
        )
    else:
        if output.exists() and not args.replace_retrospective_artifact:
            raise FileExistsError(
                "train artifact already exists; pass --replace-retrospective-artifact "
                "only when deliberately regenerating this development artifact"
            )
        report = run_rolling_train_outer_cv_gate(repository_root=ROOT)
        write_rolling_train_gate_report(report, output)
        report = verify_rolling_train_gate_report(
            output,
            repository_root=ROOT,
            recompute=True,
        )
    print(f"report={output}")
    print(f"content_sha256={report['content_sha256']}")
    print(f"train_promotion_gate_passed={report['train_promotion_gate_passed']}")
    print(
        "outer_mean_search_top1_gain="
        f"{report['outer_cv_overall_world_weighted_metrics']['search_top1_gain']:.6f}"
    )
    print(
        "outer_worst_fold_search_top1_gain="
        f"{report['outer_cv_worst_held_out_fold_search_top1_gain']:.6f}"
    )


if __name__ == "__main__":
    main()
