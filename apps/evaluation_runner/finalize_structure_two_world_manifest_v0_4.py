#!/usr/bin/env python3
"""Freeze the v0.4 validation manifest after external seed attestation."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cpswm.system.evaluation_operations.structure_two_world_rolling_gate_v0_4 import (  # noqa: E402
    verify_rolling_train_gate_report,
)
from cpswm.system.evaluation_operations.structure_two_world_seed_attestation_v0_4 import (  # noqa: E402
    load_preregistered_freeze_authorization,
    load_seed_block_attestation,
    verify_seed_block_attestation,
)
from cpswm.system.evaluation_operations.structure_two_world_validation_gate_v0_4 import (  # noqa: E402
    verify_validation_manifest_against_train_evidence,
)

DRAFT = ROOT / (
    "configs/project_two_experiments/structure_two_world_generator_manifest_v0_4_DRAFT.json"
)
BASE = ROOT / ("configs/project_two_experiments/structure_two_world_generator_manifest_v0_2.json")
DEFAULT_ATTESTATION = ROOT / (
    "configs/project_two_experiments/structure_two_world_seed_block_attestation_v0_4.json"
)
DEFAULT_OUTPUT = ROOT / (
    "configs/project_two_experiments/structure_two_world_generator_manifest_v0_4.json"
)


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attestation", type=Path, default=DEFAULT_ATTESTATION)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    attestation_path = (
        args.attestation if args.attestation.is_absolute() else ROOT / args.attestation
    )
    output_path = args.output if args.output.is_absolute() else ROOT / args.output

    draft = json.loads(DRAFT.read_text(encoding="utf-8"))
    if draft.get("status") != "DRAFT-awaiting-trust-anchor-and-custodian-attestation":
        raise ValueError("input manifest is not the unsigned v0.4 draft")
    trusted_key_id, trusted_public_key_sha256, user_approval_id = (
        load_preregistered_freeze_authorization(DRAFT)
    )
    if output_path.exists():
        raise FileExistsError("frozen manifest already exists; refusing to overwrite")
    train_path = ROOT / draft["train_promotion_evidence"]["artifact"]
    train = verify_rolling_train_gate_report(
        train_path,
        repository_root=ROOT,
        recompute=True,
    )
    if not train["train_promotion_gate_passed"]:
        raise ValueError("train promotion gate did not pass")
    if _file_sha256(train_path) != draft["train_promotion_evidence"]["artifact_file_sha256"]:
        raise ValueError("train artifact file hash differs from the draft")
    if train["content_sha256"] != draft["train_promotion_evidence"]["artifact_content_sha256"]:
        raise ValueError("train artifact content hash differs from the draft")
    verify_validation_manifest_against_train_evidence(
        draft,
        train,
        repository_root=ROOT,
    )

    record = load_seed_block_attestation(attestation_path)
    validation_seeds = draft["split_policy"][
        "v0_4_validation_world_seeds_preregistered_not_generated"
    ]
    verify_seed_block_attestation(
        record,
        draft_manifest_path=DRAFT,
        base_manifest_path=BASE,
        expected_train_artifact_content_sha256=train["content_sha256"],
        expected_validation_world_seeds=validation_seeds,
        trusted_key_id=trusted_key_id,
        trusted_public_key_sha256=trusted_public_key_sha256,
    )

    frozen = dict(draft)
    frozen["status"] = "frozen-before-first-validation-run"
    frozen["custodian_attestation"] = {
        "artifact": str(attestation_path.relative_to(ROOT)),
        "artifact_file_sha256": _file_sha256(attestation_path),
        "trusted_custodian_key_id": trusted_key_id,
        "trusted_custodian_public_key_sha256": trusted_public_key_sha256,
        "custodian_run_id": record.custodian_run_id,
        "verified": True,
    }
    frozen["freeze_record"] = {
        "draft_file_sha256": _file_sha256(DRAFT),
        "user_approval_id": user_approval_id,
        "user_approval_is_cryptographic_signature": False,
        "validation_metrics_observed_before_freeze": False,
    }
    frozen["execution_policy"] = {
        "validation_gate_a_allowed": True,
        "gate_b_allowed": False,
        "method_comparison_allowed": False,
        "transition_1": "one deterministic Gate A run is now permitted",
        "transition_2": "Gate A pass permits Gate B",
        "transition_3": (
            "Gate A pass plus Gate B pass plus the independent external-adapter "
            "fidelity gate pass permits external-method efficacy comparison"
        ),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(frozen, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"frozen_manifest={output_path}")
    print(f"file_sha256={_file_sha256(output_path)}")
    print("validation_gate_a_allowed=True")
    print("gate_b_allowed=False")
    print("method_comparison_allowed=False")


if __name__ == "__main__":
    main()
