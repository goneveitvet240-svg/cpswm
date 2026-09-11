#!/usr/bin/env python3
"""Versioned P5 recomputation and explicitly limited historical Git audit."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import get_context
from pathlib import Path
from typing import Any

from cpswm.system.evaluation_operations.structure_two_evidence_versions import (
    current_evidence_context,
    historical_entries,
    require_current_output,
    verify_historical_record,
)
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_production_system import build_production_assembly_manifest

ROOT = Path(__file__).resolve().parents[2]
EXPERIMENTS = (
    "three_arm_death_test",
    "readout_posthoc_diagnostic",
    "debt_replay_confirmation",
    "readout_prior_factorial",
    "unseen_d0_holdout",
)


def current_evidence_inventory() -> list[dict[str, Any]]:
    """Bind checkpoint rows; full verification occurs in its required audit command."""
    assembly = build_production_assembly_manifest(ROOT)["content_sha256"]
    rows = []
    for name in EXPERIMENTS:
        module = importlib.import_module(
            f"cpswm.system.evaluation_operations.structure_two_p5_{name}"
        )
        path = ROOT / module.DEFAULT_OUTPUT
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("evidence_context") != current_evidence_context():
            raise ValueError("current P5 inventory contains a historical or promoted artifact")
        if payload["source_binding"]["production_assembly_manifest_sha256"] != assembly:
            raise ValueError("current P5 inventory contains a stale source binding")
        unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
        if payload["content_sha256"] != content_sha256(unsigned):
            raise ValueError("current P5 inventory content hash mismatch")
        rows.append(
            {
                "experiment": name,
                "path": module.DEFAULT_OUTPUT.as_posix(),
                "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "content_sha256": payload["content_sha256"],
                "status": payload["status"],
                "evidence_context": payload["evidence_context"],
                "verification_command_id": "p5_evidence_current",
            }
        )
    return rows


def _verify_one(name: str, generate: bool) -> dict[str, str]:
    module = importlib.import_module(f"cpswm.system.evaluation_operations.structure_two_p5_{name}")
    output = require_current_output(ROOT, module.DEFAULT_OUTPUT)
    if generate:
        payload = getattr(module, f"run_p5_{name}")(repository_root=ROOT)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    else:
        payload = json.loads(output.read_text())
    getattr(module, f"verify_p5_{name}")(payload, repository_root=ROOT)
    return {"experiment": name, "status": payload["status"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--generate-current", action="store_true")
    mode.add_argument("--verify-current", action="store_true")
    mode.add_argument("--verify-history", action="store_true")
    args = parser.parse_args()
    history = [verify_historical_record(ROOT, entry) for entry in historical_entries(ROOT)]
    print(json.dumps({"historical_local_git_audit": history}), flush=True)
    if args.verify_history:
        return
    # Experiments consume frozen historical inputs, so these five executions
    # are independent. Spawn gives each verifier a freshly imported source tree.
    with ProcessPoolExecutor(max_workers=5, mp_context=get_context("spawn")) as pool:
        futures = [pool.submit(_verify_one, name, args.generate_current) for name in EXPERIMENTS]
        for future in as_completed(futures):
            print(json.dumps(future.result()), flush=True)
    print(json.dumps({"current_evidence_inventory": current_evidence_inventory()}), flush=True)


if __name__ == "__main__":
    main()
