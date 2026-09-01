#!/usr/bin/env python3
"""Run pinned official component parity checks for Structure Two v0.6."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cpswm.system.evaluation_operations.structure_two_official_component_parity_v0_6 import (  # noqa: E402
    run_official_component_parity_v0_6,
)

OUTPUT = ROOT / "benchmarks/structure_two/structure_two_official_component_parity_v0_6.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--active-dreaming-repository", type=Path, required=True)
    parser.add_argument("--brainctl-repository", type=Path, required=True)
    args = parser.parse_args()
    report = run_official_component_parity_v0_6(
        active_dreaming_repository=args.active_dreaming_repository,
        brainctl_repository=args.brainctl_repository,
    )
    OUTPUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"selected_fixture_parity_passed={report['selected_fixture_parity_passed']}")
    print(f"component_parity_passed={report['component_parity_passed']}")
    print(f"native_protocol_reproduction_passed={report['native_protocol_reproduction_passed']}")
    print(f"adaptation_parity_passed={report['adaptation_parity_passed']}")


if __name__ == "__main__":
    main()
