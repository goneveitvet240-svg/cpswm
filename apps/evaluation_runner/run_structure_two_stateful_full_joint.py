#!/usr/bin/env python3
"""Run or verify the Route-C stateful full-joint D0 development artifact."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from cpswm.system.evaluation_operations.structure_two_stateful_full_joint import (  # noqa: E402
    run_stateful_full_joint_development,
    verify_stateful_full_joint_result,
)

DEFAULT_OUTPUT = ROOT / "benchmarks/structure_two/structure_two_stateful_full_joint_v0_1.json"


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_nonstandard_constant(value: str) -> object:
    raise ValueError(f"non-standard JSON numeric constant: {value}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args()
    if args.verify is not None:
        payload = json.loads(
            args.verify.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonstandard_constant,
        )
        verify_stateful_full_joint_result(
            payload,
            repository_root=ROOT,
            fresh_replay=True,
        )
        print(f"verified {args.verify}")
        return 0
    result = run_stateful_full_joint_development(repository_root=ROOT)
    verify_stateful_full_joint_result(result, repository_root=ROOT, fresh_replay=False)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
