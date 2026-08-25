"""Run the deterministic S3-2 controlled-noise benchmark."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SOURCE_ROOT = _PROJECT_ROOT / "src"
if str(_SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SOURCE_ROOT))

from cpswm.system.evaluation_operations.direction_three_controlled_noise import (  # noqa: E402
    run_controlled_noise_benchmark,
    run_controlled_noise_study,
)
from cpswm.system.evaluation_operations.report_output import write_report_atomic  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--expanded-study", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    report = (
        run_controlled_noise_study() if args.expanded_study else run_controlled_noise_benchmark()
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output is not None:
        write_report_atomic(
            rendered + "\n",
            output_path=args.output,
            config_path=Path(__file__),
            repository_root=_PROJECT_ROOT,
            force=args.force,
        )
    print(rendered)


if __name__ == "__main__":
    main()
