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
    fetch_findingdory_dataset_viewer_rows,
    load_findingdory_dataset_viewer_export,
    load_findingdory_jsonl,
    load_findingdory_parquet,
)
from cpswm.system.evaluation_operations.report_output import write_report_atomic  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input", type=Path, nargs="?", help="JSONL, Dataset Viewer JSON, or parquet rows"
    )
    parser.add_argument("--source-split", default="train")
    parser.add_argument(
        "--input-format",
        choices=("auto", "jsonl", "dataset-viewer", "parquet"),
        default="auto",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--fetch-viewer", action="store_true")
    parser.add_argument("--viewer-offset", type=int, default=0)
    parser.add_argument("--viewer-length", type=int, default=100)
    parser.add_argument("--viewer-timeout", type=float, default=30.0)
    parser.add_argument("--include-records", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.fetch_viewer:
        if args.input is not None:
            raise SystemExit("input path and --fetch-viewer are mutually exclusive")
        batch = fetch_findingdory_dataset_viewer_rows(
            source_split=args.source_split,
            offset=args.viewer_offset,
            length=args.viewer_length,
            timeout_seconds=args.viewer_timeout,
        )
        config_path = Path(__file__)
    else:
        if args.input is None:
            raise SystemExit("an input path or --fetch-viewer is required")
        input_format = args.input_format
        if input_format == "auto":
            input_format = (
                "parquet"
                if args.input.suffix == ".parquet"
                else ("dataset-viewer" if args.input.suffix == ".json" else "jsonl")
            )
        if input_format == "dataset-viewer":
            batch = load_findingdory_dataset_viewer_export(args.input)
        elif input_format == "parquet":
            batch = load_findingdory_parquet(args.input, source_split=args.source_split)
        else:
            batch = load_findingdory_jsonl(args.input, source_split=args.source_split)
        config_path = args.input
    payload: dict[str, object] = {"audit": batch.audit.model_dump(mode="json")}
    if args.include_records:
        payload["records"] = [record.model_dump(mode="json") for record in batch.records]
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output is not None:
        write_report_atomic(
            rendered + "\n",
            output_path=args.output,
            config_path=config_path,
            repository_root=_PROJECT_ROOT,
            force=args.force,
        )
    print(rendered)


if __name__ == "__main__":
    main()
