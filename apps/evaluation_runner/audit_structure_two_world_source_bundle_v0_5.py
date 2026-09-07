#!/usr/bin/env python3
"""Regenerate the current-tree compatibility audit for historical v0.5 evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cpswm.system.evaluation_operations.structure_two_world_seed_attestation_v0_5 import (  # noqa: E402
    audit_v0_5_source_bundle_evidence,
)

DEFAULT_OUTPUT = ROOT / (
    "benchmarks/structure_two/structure_two_world_source_bundle_v0_5_compatibility_audit.json"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    output = arguments.output.resolve()
    report = audit_v0_5_source_bundle_evidence(ROOT)
    report["claim_boundary"] = (
        "The ten trace content hashes and Ed25519 signatures verify against the trust anchor "
        "declared by the current manifests, and the current Gate B result is internally bound. "
        "Historical authenticity remains unproved because the 245-row inventory is absent and "
        "the trust anchor has no external immutable anchor."
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"report={output}")
    print(f"current_file_count={report['current_file_count']}")
    print(f"current_source_bundle_sha256={report['current_source_bundle_sha256']}")
    print(
        "current_worktree_compatible_with_frozen_v0_5="
        f"{report['current_worktree_compatible_with_frozen_v0_5']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
