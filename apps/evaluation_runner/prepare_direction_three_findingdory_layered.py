"""Build an immutable S3-DG-13D FindingDory artifact at a pinned revision."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SOURCE_ROOT = _PROJECT_ROOT / "src"
if str(_SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SOURCE_ROOT))

from cpswm.system.evaluation_operations.real_data_adapters.findingdory_layered_ingress import (  # noqa: E402
    FindingDoryAcquisitionBackend,
    acquire_findingdory_with_datasets,
    materialize_findingdory_rows,
)
from cpswm.system.evaluation_operations.report_output import write_report_atomic  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backend",
        choices=("datasets", "local-jsonl"),
        required=True,
        help="Pinned Hub streaming acquisition or normalization of provided pinned rows",
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="Raw JSONL rows; required only for --backend=local-jsonl",
    )
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--dataset-revision", required=True)
    parser.add_argument("--source-split", default="train")
    parser.add_argument("--max-rows", type=int)
    return parser.parse_args()


def _iter_jsonl(path: Path, max_rows: int | None) -> Iterator[Mapping[str, object]]:
    if max_rows is not None and max_rows <= 0:
        raise ValueError("max rows must be positive")
    emitted = 0
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError(f"FindingDory JSONL row {line_number} is not an object")
            yield payload
            emitted += 1
            if max_rows is not None and emitted >= max_rows:
                return


def main() -> None:
    args = _parse_args()
    if args.artifact.resolve(strict=False) == args.manifest.resolve(strict=False):
        raise SystemExit("artifact and manifest paths must differ")
    if args.backend == "datasets":
        if args.input is not None:
            raise SystemExit("--input is not valid with --backend=datasets")
        manifest = acquire_findingdory_with_datasets(
            args.artifact,
            dataset_revision=args.dataset_revision,
            source_split=args.source_split,
            max_rows=args.max_rows,
        )
        config_path = Path(__file__)
    else:
        if args.input is None:
            raise SystemExit("--input is required with --backend=local-jsonl")
        manifest = materialize_findingdory_rows(
            _iter_jsonl(args.input, args.max_rows),
            args.artifact,
            dataset_revision=args.dataset_revision,
            source_split=args.source_split,
            acquisition_backend=FindingDoryAcquisitionBackend.PROVIDED_PINNED_ROWS,
        )
        config_path = args.input
    rendered = manifest.model_dump_json(indent=2) + "\n"
    write_report_atomic(
        rendered,
        output_path=args.manifest,
        config_path=config_path,
        repository_root=_PROJECT_ROOT,
    )
    print(rendered, end="")


if __name__ == "__main__":
    main()
