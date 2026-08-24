"""Run the S3-1 multi-scenario oracle suite and optionally persist its JSON report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SOURCE_ROOT = _PROJECT_ROOT / "src"
if str(_SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SOURCE_ROOT))

from cpswm.system.evaluation_operations.direction_three_oracle_suite import (  # noqa: E402
    run_oracle_suite,
)
from cpswm.system.evaluation_operations.report_output import write_report_atomic  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write the JSON report under output/.")
    parser.add_argument("--force", action="store_true", help="Replace an existing report.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    rendered = json.dumps(run_oracle_suite(), ensure_ascii=False, indent=2, sort_keys=True)
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
