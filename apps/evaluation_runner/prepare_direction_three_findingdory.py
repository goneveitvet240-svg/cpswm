"""Audit FindingDory public JSONL metadata without inventing S3 truth fields."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SOURCE_ROOT = _PROJECT_ROOT / "src"
if str(_SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SOURCE_ROOT))

from cpswm.system.evaluation_operations.real_data_adapters.findingdory import (  # noqa: E402
    load_findingdory_jsonl,
)
from cpswm.system.evaluation_operations.report_output import write_report_atomic  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="JSONL rows using the official 8-column schema")
    parser.add_argument("--source-split", default="train")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--include-records", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    batch = load_findingdory_jsonl(args.input, source_split=args.source_split)
    payload: dict[str, object] = {"audit": batch.audit.model_dump(mode="json")}
    if args.include_records:
        payload["records"] = [record.model_dump(mode="json") for record in batch.records]
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output is not None:
        write_report_atomic(
            rendered + "\n",
            output_path=args.output,
            config_path=args.input,
            repository_root=_PROJECT_ROOT,
            force=args.force,
        )
    print(rendered)


if __name__ == "__main__":
    main()
