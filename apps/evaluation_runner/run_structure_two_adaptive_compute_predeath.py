#!/usr/bin/env python3
"""Generate or freshly verify the Structure-Two adaptive-compute readiness report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from cpswm.system.evaluation_operations.structure_two_adaptive_compute_predeath import (  # noqa: E402
    DEFAULT_OUTPUT,
    run_adaptive_compute_predeath_readiness,
    verify_adaptive_compute_predeath_readiness,
)


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_nonstandard_constant(value: str) -> object:
    raise ValueError(f"non-standard JSON numeric constant: {value}")


def _load(path: Path) -> dict[str, object]:
    payload = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_nonstandard_constant,
    )
    if not isinstance(payload, dict):
        raise ValueError("adaptive-compute readiness artifact must be a JSON object")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args()

    if args.verify is not None:
        verify_path = args.verify if args.verify.is_absolute() else REPOSITORY_ROOT / args.verify
        verify_adaptive_compute_predeath_readiness(
            _load(verify_path),
            repository_root=REPOSITORY_ROOT,
        )
        print(f"verified {verify_path}")
        return 0

    output = args.output if args.output.is_absolute() else REPOSITORY_ROOT / args.output
    report = run_adaptive_compute_predeath_readiness(repository_root=REPOSITORY_ROOT)
    verify_adaptive_compute_predeath_readiness(
        report,
        repository_root=REPOSITORY_ROOT,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"status={report['status']} "
        f"shadow_execution_authorized={report['shadow_execution_authorized']} "
        f"output={output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
