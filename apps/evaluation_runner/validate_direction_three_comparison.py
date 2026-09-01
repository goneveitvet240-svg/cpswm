"""Validate matched direction-three method submissions before scoring truth."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SOURCE_ROOT = _PROJECT_ROOT / "src"
if str(_SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SOURCE_ROOT))

from cpswm.system.evaluation_operations.direction_three_comparison import (  # noqa: E402
    DirectionThreeMethodRun,
    validate_matched_direction_three_runs,
)
from cpswm.system.evaluation_operations.direction_three_dataset import (  # noqa: E402
    DirectionThreeEpisodeDataset,
)
from cpswm.system.evaluation_operations.direction_three_external_audit import (  # noqa: E402
    DirectionThreeExternalAudit,
    validate_sealed_direction_three_runs,
)
from cpswm.system.evaluation_operations.report_output import write_report_atomic  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("runs", type=Path, nargs="+")
    parser.add_argument("--external-audit", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    dataset = DirectionThreeEpisodeDataset.model_validate_json(
        args.dataset.read_text(encoding="utf-8")
    )
    runs = tuple(
        DirectionThreeMethodRun.model_validate_json(path.read_text(encoding="utf-8"))
        for path in args.runs
    )
    contains_external_system = any(run.method.external_system for run in runs)
    if contains_external_system:
        if args.external_audit is None:
            raise SystemExit("external method runs require --external-audit under S3-DG-12C")
        external_audit = DirectionThreeExternalAudit.model_validate_json(
            args.external_audit.read_text(encoding="utf-8")
        )
        audit = validate_sealed_direction_three_runs(dataset, external_audit, runs)
    else:
        audit = validate_matched_direction_three_runs(dataset, runs)
    rendered = json.dumps(audit.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        write_report_atomic(
            rendered,
            output_path=args.output,
            config_path=args.dataset,
            repository_root=_PROJECT_ROOT,
            force=args.force,
        )
    print(rendered, end="")


if __name__ == "__main__":
    main()
