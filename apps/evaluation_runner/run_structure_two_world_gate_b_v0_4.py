#!/usr/bin/env python3
"""Run strict Structure-Two v0.4 Gate B after fresh-world Gate A passes."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cpswm.system.evaluation_operations.structure_two_world_gate_b_v0_4 import (  # noqa: E402
    DEFAULT_OUTPUT,
    DEFAULT_TRACE_DIR,
    run_structure_two_world_gate_b_v0_4,
    verify_dual_gate_authorization,
    write_gate_b_authorization,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace-dir", type=Path, default=DEFAULT_TRACE_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    if args.verify:
        report = verify_dual_gate_authorization(
            output,
            repository_root=ROOT,
            trace_dir=args.trace_dir,
            recompute=True,
        )
    else:
        report = run_structure_two_world_gate_b_v0_4(
            repository_root=ROOT,
            trace_dir=args.trace_dir,
        )
        write_gate_b_authorization(report, output)
        report = verify_dual_gate_authorization(
            output,
            repository_root=ROOT,
            trace_dir=args.trace_dir,
            recompute=True,
        )
    print(f"report={output}")
    print(f"content_sha256={report['content_sha256']}")
    print(f"gate_a_passed={report['gate_a_passed']}")
    print(f"gate_b_passed={report['gate_b_passed']}")
    print(f"method_comparison_allowed={report['method_comparison_allowed']}")


if __name__ == "__main__":
    main()
