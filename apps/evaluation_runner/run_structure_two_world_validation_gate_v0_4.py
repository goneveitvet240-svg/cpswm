#!/usr/bin/env python3
"""Run the attestation-gated fresh-world Structure-Two v0.4 Gate A once."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cpswm.system.evaluation_operations.structure_two_world_validation_gate_v0_4 import (  # noqa: E402
    DEFAULT_OUTPUT,
    run_structure_two_world_validation_gate_a_v0_4,
    verify_validation_gate_report,
    write_validation_gate_report,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    if args.verify:
        report = verify_validation_gate_report(
            output,
            repository_root=ROOT,
            recompute=True,
        )
    else:
        if output.exists():
            raise FileExistsError(
                "validation Gate A artifact already exists; use --verify instead of overwriting"
            )
        report = run_structure_two_world_validation_gate_a_v0_4(repository_root=ROOT)
        write_validation_gate_report(report, output)
        report = verify_validation_gate_report(
            output,
            repository_root=ROOT,
            recompute=True,
        )
    print(f"report={output}")
    print(f"content_sha256={report['content_sha256']}")
    print(f"gate_a_passed={report['gate_a_passed']}")
    print(f"gate_b_allowed={report['gate_b_allowed']}")
    print("method_comparison_allowed=False")


if __name__ == "__main__":
    main()
