#!/usr/bin/env python3
"""Run or verify the fail-closed Structure-Two runtime-identity audit."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from cpswm.system.evaluation_operations.structure_two_runtime_identity_gate import (  # noqa: E402
    run_runtime_identity_gate_audit,
    verify_runtime_identity_gate_report,
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
        raise ValueError("runtime-identity report root must be a JSON object")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        help="optional report destination; without it the report is printed to stdout",
    )
    parser.add_argument("--verify", type=Path, help="freshly verify an existing report")
    args = parser.parse_args()
    if args.verify is not None:
        report = _load(args.verify)
        verify_runtime_identity_gate_report(report, repository_root=ROOT)
        print(f"verified {args.verify}")
        return 0

    report = run_runtime_identity_gate_audit(repository_root=ROOT)
    verify_runtime_identity_gate_report(report, repository_root=ROOT)
    rendered = (
        json.dumps(
            report,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )
    if args.output is None:
        print(rendered, end="")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
