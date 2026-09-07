#!/usr/bin/env python3
"""Portable Task 11 full raw + fresh-source recomputation from compressed JSONL.

The current working directory is irrelevant.  Repository imports are resolved
relative to this script, while input and output paths are supplied by callers.
"""

from __future__ import annotations

import argparse
import sys
from itertools import chain
from pathlib import Path
from typing import Final

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[2]
SOURCE_ROOT: Final = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from cpswm.system.evaluation_operations.structure_two_task11_resampling_diagnostic import (  # noqa: E402
    iter_jsonl,
    recompute_results,
    verify_frozen_inputs,
    write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--g1-traces", type=Path, required=True)
    parser.add_argument("--g2-traces", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    verify_frozen_inputs(REPOSITORY_ROOT)
    traces = chain(iter_jsonl(arguments.g1_traces), iter_jsonl(arguments.g2_traces))
    result = recompute_results(traces, fresh_replay=True)
    write_json(arguments.output, result)
    print(result["deterministic_result_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
