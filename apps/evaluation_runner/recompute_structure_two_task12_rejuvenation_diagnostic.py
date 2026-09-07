#!/usr/bin/env python3
"""Independently recompute Task 12 results from raw traces."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Final

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[2]
SOURCE_ROOT: Final = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from cpswm.system.evaluation_operations.structure_two_task12_rejuvenation_diagnostic import (  # noqa: E402
    TASK11_OUTPUT_RELATIVE,
    TASK11_RAW_RELATIVE,
    load_jsonl,
    sha256_file,
    write_json,
)
from cpswm.system.evaluation_operations.structure_two_task12_rejuvenation_verifier import (  # noqa: E402
    recompute_results,
)

TASK11_DIR: Final = REPOSITORY_ROOT / TASK11_OUTPUT_RELATIVE


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--g1-traces", type=Path, required=True)
    parser.add_argument("--g2-traces", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    task11_paths = {
        context: TASK11_DIR / relative for context, relative in TASK11_RAW_RELATIVE.items()
    }
    task11_rows = [
        row
        for row in (*load_jsonl(task11_paths["G1"]), *load_jsonl(task11_paths["G2"]))
        if row.get("particle_budget") == 24
    ]
    if len(task11_rows) != 1872:
        raise ValueError("Task 11 full-budget artifact does not contain the frozen K=24 slice")
    task11_result = json.loads((TASK11_DIR / "task11_recomputed_results.json").read_text())
    task11_manifest = json.loads((TASK11_DIR / "TASK11_EVIDENCE_MANIFEST.json").read_text())
    result = recompute_results(
        [*load_jsonl(arguments.g1_traces), *load_jsonl(arguments.g2_traces)],
        task11_rows=task11_rows,
        task11_result=task11_result,
        task11_manifest=task11_manifest,
        task11_raw_hashes_by_context={
            context: sha256_file(path) for context, path in task11_paths.items()
        },
    )
    write_json(arguments.output, result)
    print(result["deterministic_result_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
