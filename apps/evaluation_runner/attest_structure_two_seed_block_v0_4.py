#!/usr/bin/env python3
"""Custodian-only signer for the Structure-Two v0.4 seed-block statement."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cpswm.system.attestation import Ed25519AttestationSigner  # noqa: E402
from cpswm.system.evaluation_operations.structure_two_world_seed_attestation_v0_4 import (  # noqa: E402
    create_seed_block_attestation,
    write_seed_block_attestation,
)

BASE_MANIFEST = ROOT / (
    "configs/project_two_experiments/structure_two_world_generator_manifest_v0_2.json"
)
DRAFT_MANIFEST = ROOT / (
    "configs/project_two_experiments/structure_two_world_generator_manifest_v0_4_DRAFT.json"
)
DEFAULT_OUTPUT = ROOT / (
    "configs/project_two_experiments/structure_two_world_seed_block_attestation_v0_4.json"
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run only in the external custodian environment; secrets are never output."
    )
    parser.add_argument("--raw-holdout-seeds-file", type=Path, required=True)
    parser.add_argument("--custody-salt-file", type=Path, required=True)
    parser.add_argument("--private-key-file", type=Path, required=True)
    parser.add_argument("--key-id", required=True)
    parser.add_argument("--custodian-run-id", required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("seed attestation already exists; refusing to overwrite")

    draft = json.loads(DRAFT_MANIFEST.read_text(encoding="utf-8"))
    gate_b = draft["gate_b_contract"]
    producer_hash = str(gate_b.get("producer_source_bundle_sha256", ""))
    if gate_b.get("producer_source_bundle_configured_before_custodian_signature") is not True or (
        len(producer_hash) != 64 or any(item not in "0123456789abcdef" for item in producer_hash)
    ):
        raise ValueError("Gate B producer source bundle must be frozen before attestation")
    raw_payload = json.loads(args.raw_holdout_seeds_file.read_text(encoding="utf-8"))
    if not isinstance(raw_payload, list):
        raise ValueError("raw holdout seed file must be a JSON list of integers")
    signer = Ed25519AttestationSigner.from_private_key_pem(
        key_id=args.key_id,
        private_key_pem=args.private_key_file.read_bytes(),
    )
    record = create_seed_block_attestation(
        draft_manifest_path=DRAFT_MANIFEST,
        base_manifest_path=BASE_MANIFEST,
        train_artifact_content_sha256=draft["train_promotion_evidence"]["artifact_content_sha256"],
        validation_world_seeds=draft["split_policy"][
            "v0_4_validation_world_seeds_preregistered_not_generated"
        ],
        raw_holdout_world_seeds=[int(item) for item in raw_payload],
        custody_salt=args.custody_salt_file.read_text(encoding="utf-8").strip(),
        custodian_run_id=args.custodian_run_id,
        signer=signer,
    )
    write_seed_block_attestation(record, args.output)
    print(f"attestation={args.output}")
    print(f"key_id={record.attestation.key_id if record.attestation else 'missing'}")
    print(f"public_key_sha256={record.custodian_public_key_sha256}")
    print("raw_holdout_seeds_disclosed=False")
    print("custody_salt_disclosed=False")


if __name__ == "__main__":
    main()
