"""Run the protocol-only Project One matched-ablation pilot."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from cpswm.system.evaluation_operations.project_one_ablation_pilot import (  # noqa: E402
    ProjectOneProtocolPilotConfig,
    ProjectOneProtocolPilotRunner,
)
from cpswm.system.evaluation_operations.report_output import (  # noqa: E402
    ProtectedReportOutputError,
    write_report_atomic,
)

DEFAULT_CONFIG = (
    REPOSITORY_ROOT / "benchmarks" / "project_one_ablation" / "project_one_protocol_pilot_v0.1.json"
)
DEFAULT_OUTPUT = REPOSITORY_ROOT / "output" / "project_one_protocol_pilot_report.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the five-pair Project One ablation protocol and adapter coverage."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace an existing non-benchmark output file",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = ProjectOneProtocolPilotConfig.model_validate_json(
        args.config.resolve().read_text(encoding="utf-8")
    )
    report = ProjectOneProtocolPilotRunner().run(config)
    rendered = report.model_dump_json(indent=2) + "\n"
    try:
        write_report_atomic(
            rendered,
            output_path=args.output,
            config_path=args.config,
            repository_root=REPOSITORY_ROOT,
            force=args.force,
        )
    except (FileExistsError, ProtectedReportOutputError) as exc:
        print(f"refusing report output: {exc}", file=sys.stderr)
        return 2
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
