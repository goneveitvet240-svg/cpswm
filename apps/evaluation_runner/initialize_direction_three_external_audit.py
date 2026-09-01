"""Write the complete S3-DG-12C neighbor registry with honest pending states."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SOURCE_ROOT = _PROJECT_ROOT / "src"
if str(_SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SOURCE_ROOT))

from cpswm.system.evaluation_operations.direction_three_external_audit import (  # noqa: E402
    selected_direction_three_external_audit,
)
from cpswm.system.evaluation_operations.report_output import write_report_atomic  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    rendered = selected_direction_three_external_audit().model_dump_json(indent=2) + "\n"
    write_report_atomic(
        rendered,
        output_path=args.output,
        config_path=Path(__file__),
        repository_root=_PROJECT_ROOT,
    )
    print(rendered, end="")


if __name__ == "__main__":
    main()
