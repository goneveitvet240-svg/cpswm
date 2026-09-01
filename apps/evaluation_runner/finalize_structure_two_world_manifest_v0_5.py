#!/usr/bin/env python3
"""Freeze v0.5 after verifying the fresh external seed commitment block."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cpswm.system.evaluation_operations.structure_two_world_seed_attestation_v0_5 import (  # noqa: E402
    compute_v0_5_source_bundle,
    load_fresh_seed_block_attestation,
    load_preregistered_v0_5_authorization,
    verify_fresh_seed_block_attestation,
)

DRAFT = ROOT / (
    "configs/project_two_experiments/structure_two_world_generator_manifest_v0_5_DRAFT.json"
)
ATTESTATION = ROOT / (
    "configs/project_two_experiments/structure_two_world_seed_block_attestation_v0_5.json"
)
OUTPUT = ROOT / ("configs/project_two_experiments/structure_two_world_generator_manifest_v0_5.json")


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if OUTPUT.exists():
        raise FileExistsError("frozen v0.5 manifest already exists")
    draft = json.loads(DRAFT.read_text(encoding="utf-8"))
    if draft.get("status") != "DRAFT-trust-anchor-frozen-awaiting-seed-attestation":
        raise ValueError("v0.5 draft is not ready for external attestation verification")
    _, _, approval_id = load_preregistered_v0_5_authorization(DRAFT)
    source_bundle = compute_v0_5_source_bundle(ROOT)
    contract = draft["gate_b_contract"]
    if contract.get(
        "producer_source_bundle_sha256"
    ) != source_bundle.content_sha256 or contract.get("producer_source_bundle_file_count") != len(
        source_bundle.files
    ):
        raise ValueError("v0.5 source bundle differs from the preregistered draft")
    record = load_fresh_seed_block_attestation(ATTESTATION)
    verify_fresh_seed_block_attestation(
        record,
        draft_manifest_path=DRAFT,
        expected_train_artifact_content_sha256=draft["inheritance"][
            "train_artifact_content_sha256"
        ],
    )
    frozen = json.loads(json.dumps(draft))
    frozen["status"] = "frozen-before-first-v0.5-validation-run"
    frozen["split_policy"]["sealed_holdout_world_seed_commitments"] = list(
        record.holdout_seed_commitments
    )
    frozen["custodian_attestation"].update(
        {
            "artifact": str(ATTESTATION.relative_to(ROOT)),
            "artifact_file_sha256": _file_sha256(ATTESTATION),
            "custodian_run_id": record.custodian_run_id,
            "verified": True,
            "current_status": "VERIFIED fresh external seed block",
        }
    )
    frozen["freeze_record"] = {
        "draft_file_sha256": _file_sha256(DRAFT),
        "user_approval_id": approval_id,
        "validation_metrics_observed_before_freeze": False,
        "v0_4_commitments_reused": False,
    }
    frozen["execution_policy"] = {
        "validation_gate_a_allowed": True,
        "gate_b_allowed": False,
        "proxy_method_comparison_allowed": False,
        "official_method_comparison_allowed": False,
    }
    OUTPUT.write_text(json.dumps(frozen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"frozen_manifest={OUTPUT}")
    print(f"file_sha256={_file_sha256(OUTPUT)}")
    print("validation_gate_a_allowed=True")
    print("method_comparison_allowed=False")


if __name__ == "__main__":
    main()
