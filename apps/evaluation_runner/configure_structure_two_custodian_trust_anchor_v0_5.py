#!/usr/bin/env python3
"""Register only the external custodian's public v0.5 Ed25519 key."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cpswm.system.attestation import Ed25519AttestationVerifier  # noqa: E402

DEFAULT_DRAFT = ROOT / (
    "configs/project_two_experiments/structure_two_world_generator_manifest_v0_5_DRAFT.json"
)
ATTESTATION = ROOT / (
    "configs/project_two_experiments/structure_two_world_seed_block_attestation_v0_5.json"
)
FROZEN = ROOT / ("configs/project_two_experiments/structure_two_world_generator_manifest_v0_5.json")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--public-key-file", type=Path, required=True)
    parser.add_argument("--key-id", required=True)
    args = parser.parse_args()
    if ATTESTATION.exists() or FROZEN.exists():
        raise FileExistsError("v0.5 trust anchor cannot change after signing or freeze")
    payload = json.loads(DEFAULT_DRAFT.read_text(encoding="utf-8"))
    if payload.get("status") != "DRAFT-awaiting-external-custodian-public-key":
        raise ValueError("v0.5 draft is not awaiting its first external public key")
    verifier = Ed25519AttestationVerifier.from_public_key_pem(
        key_id=args.key_id,
        public_key_pem=args.public_key_file.read_bytes(),
    )
    key_hash = verifier.public_key_sha256
    payload["status"] = "DRAFT-trust-anchor-frozen-awaiting-seed-attestation"
    payload["custodian_attestation"].update(
        {
            "trusted_custodian_key_id": args.key_id,
            "trusted_custodian_public_key_sha256": key_hash,
            "current_status": "AWAITING externally generated fresh seed block - fail closed",
        }
    )
    payload["freeze_authorization"].update(
        {
            "trusted_custodian_key_id": args.key_id,
            "trusted_custodian_public_key_sha256": key_hash,
            "configured_before_custodian_seed_generation": True,
        }
    )
    DEFAULT_DRAFT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"draft={DEFAULT_DRAFT}")
    print(f"key_id={args.key_id}")
    print(f"public_key_sha256={key_hash}")
    print("private_key_loaded=False")
    print("fresh_seeds_generated=False")


if __name__ == "__main__":
    main()
