"""Validate and seal the authority-scoped placement v0.2 preregistration."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from cpswm.system.evaluation_operations.placement_authority_preregistration import (  # noqa: E402
    build_preregistration_receipt,
)
from cpswm.system.evaluation_operations.report_output import write_report_atomic  # noqa: E402

DEFAULT_CONFIG = ROOT / "configs/method_falsification/placement_authority_v0_2_preregistration.json"
DEFAULT_OUTPUT = (
    ROOT / "output/method_falsification/placement_authority_v0_2_preregistration_receipt.json"
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    receipt = build_preregistration_receipt(
        args.config,
        repository_root=ROOT,
    )
    rendered = json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    write_report_atomic(
        rendered,
        output_path=args.output,
        config_path=args.config,
        repository_root=ROOT,
        force=args.force,
    )
    print(rendered, end="")


if __name__ == "__main__":
    main()
