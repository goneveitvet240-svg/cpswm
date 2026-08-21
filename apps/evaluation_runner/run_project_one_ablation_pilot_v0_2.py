"""Run Project One ATG-1, the v0.2 matched-ablation topology gate.

This validates the 11-arm v0.2 topology (adding joint CF-BOCPD as the 11th arm,
with a three-arm shift comparison) and writes a topology-only report.  It loads
only a v0.2 config, calls only the v0.2 runner, rejects a v0.1 config, and never
loads or generates any TEST data.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from cpswm.system.evaluation_operations.project_one_ablation_v0_2 import (  # noqa: E402
    ProjectOneProtocolPilotConfigV2,
    select_pilot_runner,
)

DEFAULT_CONFIG = (
    REPOSITORY_ROOT / "benchmarks" / "project_one_ablation" / "project_one_protocol_pilot_v0.2.json"
)
DEFAULT_OUTPUT = REPOSITORY_ROOT / "output" / "project_one_protocol_pilot_report_v0.2.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate Project One ATG-1: the 11-arm v0.2 ablation topology only. "
            "This is not formal Structure One B1 perception."
        )
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    # A v0.1 config carries protocol_version @0.1 and will fail this validation,
    # so a v0.1 config cannot be run through the v0.2 CLI.
    config = ProjectOneProtocolPilotConfigV2.model_validate_json(
        args.config.resolve().read_text(encoding="utf-8")
    )
    report = select_pilot_runner(config).run(config)
    rendered = report.model_dump_json(indent=2)
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
