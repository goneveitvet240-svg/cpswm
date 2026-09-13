#!/usr/bin/env python3
"""Versioned P5 recomputation and explicitly limited historical Git audit."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import json

# Establish execution provenance before importing project dependencies.
import sys
import types
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import get_context
from pathlib import Path
from typing import Any

_bootstrap_path = (
    Path(__file__).resolve().parents[2] / "apps/evaluation_runner/structure_two_source_bootstrap.py"
)
if "_cpswm_source_bootstrap" not in sys.modules:
    _bootstrap = types.ModuleType("_cpswm_source_bootstrap")
    _bootstrap.__file__ = str(_bootstrap_path)
    sys.modules[_bootstrap.__name__] = _bootstrap
    exec(compile(_bootstrap_path.read_bytes(), str(_bootstrap_path), "exec"), _bootstrap.__dict__)
sys.modules["_cpswm_source_bootstrap"].establish(Path(__file__).resolve().parents[2])

from cpswm.system.evaluation_operations.structure_two_evidence_publication import (  # noqa: E402
    publish_verified_json,
)
from cpswm.system.evaluation_operations.structure_two_evidence_versions import (  # noqa: E402
    current_evidence_context,
    historical_entries,
    require_current_output,
    require_execution_source,
    verify_historical_record,
)
from cpswm.system.reproducibility import content_sha256  # noqa: E402
from cpswm.system.structure_two_production_system import (  # noqa: E402
    build_production_assembly_manifest,
)

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
        if payload["source_binding"].get("execution_source") != require_execution_source(ROOT):
            raise ValueError("current P5 inventory contains a stale formal execution source")
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
    output = ROOT / module.DEFAULT_OUTPUT
    if generate:
        require_current_output(ROOT, output)
    if generate:
        payload = getattr(module, f"run_p5_{name}")(repository_root=ROOT)
        publish_verified_json(
            ROOT,
            output,
            payload,
            verify=lambda value: getattr(module, f"verify_p5_{name}")(value, repository_root=ROOT),
        )
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
        # Run the same complete source audit, not only the retained-byte loop.

        spec = importlib.util.spec_from_file_location(
            "required_history_audit",
            ROOT / "apps/evaluation_runner/audit_structure_two_evidence_history.py",
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules["_cpswm_source_bootstrap"].guard.execute_application(
            module, ROOT / "apps/evaluation_runner/audit_structure_two_evidence_history.py"
        )
        report = module.build_history_report(
            recompute_first_failure=True, recompute_failed_replay=True
        )
        module.require_completed_replay(report)
        print(json.dumps({"historical_source_audit": report}), flush=True)
        return
    if args.generate_current:
        for name in EXPERIMENTS:
            module = importlib.import_module(
                f"cpswm.system.evaluation_operations.structure_two_p5_{name}"
            )
            require_current_output(ROOT, module.DEFAULT_OUTPUT)
    # Experiments consume frozen historical inputs, so these five executions
    # are independent. Spawn gives each verifier a freshly imported source tree.
    with ProcessPoolExecutor(max_workers=5, mp_context=get_context("spawn")) as pool:
        futures = [pool.submit(_verify_one, name, args.generate_current) for name in EXPERIMENTS]
        for future in as_completed(futures):
            print(json.dumps(future.result()), flush=True)
    print(json.dumps({"current_evidence_inventory": current_evidence_inventory()}), flush=True)


if __name__ == "__main__":
    main()
