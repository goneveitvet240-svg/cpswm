#!/usr/bin/env python3
"""Run a development-only audit; never reopen or relabel an unseen holdout."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

# Bootstrap from this CLI's sibling source bytes before ANY project import.
# Importing the module for descriptive analysis does not authorize verification.
_EXECUTION_SOURCE = None
if __name__ == "__main__":
    import sys

    _guard_path = Path(__file__).resolve().with_name("_structure_two_audit_source.py")
    _guard_bytes = _guard_path.read_bytes()
    _guard_namespace = {"__file__": str(_guard_path), "__name__": "_audit_cli_source_guard"}
    try:
        exec(compile(_guard_bytes, str(_guard_path), "exec", dont_inherit=True), _guard_namespace)
        _EXECUTION_SOURCE = _guard_namespace["bootstrap"](
            __file__, sys._getframe().f_code, _guard_bytes
        )
    except Exception as error:
        print(json.dumps({"status": "EXECUTION_SOURCE_REJECTED", "error": str(error)}))
        raise SystemExit(1) from error

from cpswm.system.evaluation_operations.structure_two_comparison_audit import (  # noqa: E402
    check_source_binding,
    compare_snapshot,
    load_bundle,
    run_audit,
    save,
)


def main() -> None:
    if _EXECUTION_SOURCE is None:
        raise RuntimeError("TRUSTED_CLI_BOOTSTRAP_REQUIRED")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help=(
            "execution and data root; must resolve to this CLI checkout "
            "(not an alternate data root)"
        ),
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--verify",
        action="store_true",
        help="fresh rerun; compare semantic results without overwriting",
    )
    parser.add_argument("--timing-repeats", type=int, default=3)
    parser.add_argument("--timing-episodes", type=int, default=2)
    args = parser.parse_args()
    if args.timing_repeats < 1 or not 1 <= args.timing_episodes <= 60:
        parser.error("positive timing repeats and 1..60 timing episodes required")
    root = args.repository_root.resolve()
    _EXECUTION_SOURCE.require_root(root)
    _EXECUTION_SOURCE.checkpoint()
    output = args.output.resolve()
    if not args.verify and any(
        (output / name).exists() for name in ("audit.json", "steps.jsonl.gz", "timing.json")
    ):
        parser.error("output already exists; choose --verify or a new directory")
    snapshot = load_bundle(output) if args.verify else None
    if snapshot is not None:
        check_source_binding(snapshot, root)
    _EXECUTION_SOURCE.checkpoint()
    payload, rows, timing = run_audit(
        root, timing_repeats=args.timing_repeats, timing_episodes=args.timing_episodes
    )
    _EXECUTION_SOURCE.require_bindings(payload["source_bindings"])
    _EXECUTION_SOURCE.checkpoint()
    if args.verify:
        assert snapshot is not None
        compare_snapshot(snapshot, payload, rows)
    else:
        save(output, payload, rows, timing)
    print(
        json.dumps(
            {
                "verified" if args.verify else "output": str(output),
                "steps": len(rows),
                "execution_source": _EXECUTION_SOURCE.identity(),
                "retained_score_mismatches": payload["retained_score_mismatches"],
                "semantic_steps_sha256": payload["semantic_steps_sha256"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except _guard_namespace["ExecutionSourceError"] as error:
        print(json.dumps({"status": "EXECUTION_SOURCE_REJECTED", "error": str(error)}))
        raise SystemExit(1) from error
