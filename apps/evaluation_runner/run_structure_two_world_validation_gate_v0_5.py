#!/usr/bin/env python3
"""Run or verify the externally attested Structure-Two v0.5 Gate A."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cpswm.system.evaluation_operations.structure_two_world_validation_gate_v0_5 import (  # noqa: E402
    DEFAULT_OUTPUT,
    run_structure_two_world_validation_gate_a_v0_5,
    verify_validation_gate_report_v0_5,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    output = ROOT / DEFAULT_OUTPUT
    if args.verify:
        report = verify_validation_gate_report_v0_5(output, repository_root=ROOT, recompute=True)
    else:
        if output.exists():
            raise FileExistsError("v0.5 Gate A artifact exists; use --verify")
        report = run_structure_two_world_validation_gate_a_v0_5(repository_root=ROOT)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report = verify_validation_gate_report_v0_5(output, repository_root=ROOT, recompute=True)
    print(f"report={output}")
    print(f"gate_a_passed={report['gate_a_passed']}")
    print(f"gate_b_allowed={report['gate_b_allowed']}")
    print("method_comparison_allowed=False")


if __name__ == "__main__":
    main()
