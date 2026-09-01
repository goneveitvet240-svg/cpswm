"""Run or verify the frozen method-free Structure-Two world Gate A v0.2.

This entrypoint only samples validation worlds and evaluates frozen trivial
rules. It never opens sealed holdout worlds and never runs a research method.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from cpswm.system.evaluation_operations.structure_two_world_gate_v0_2 import (
    DEFAULT_OUTPUT,
    run_structure_two_world_gate_a,
    verify_structure_two_world_gate_a_report,
    write_structure_two_world_gate_a_report,
)


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--recompute", action="store_true")
    args = parser.parse_args()
    root = _repository_root()
    output = args.output if args.output.is_absolute() else root / args.output
    if args.verify_only:
        report = verify_structure_two_world_gate_a_report(
            output,
            repository_root=root,
            recompute=args.recompute,
        )
    else:
        report = run_structure_two_world_gate_a(repository_root=root)
        write_structure_two_world_gate_a_report(report, output)
        verify_structure_two_world_gate_a_report(output, repository_root=root)
    print(f"artifact={output}")
    print(f"content_sha256={report['content_sha256']}")
    print(f"gate_a_passed={report['gate_a_passed']}")
    print(f"method_comparison_allowed={report['method_comparison_allowed']}")


if __name__ == "__main__":
    main()
