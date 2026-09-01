#!/usr/bin/env python3
"""Register an external custodian's public Ed25519 trust anchor before signing.

This candidate-side step accepts only a public key.  It never generates or
loads the custodian private key and therefore cannot mint an attestation.
"""

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
    "configs/project_two_experiments/structure_two_world_generator_manifest_v0_4_DRAFT.json"
)
FROZEN_MANIFEST = ROOT / (
    "configs/project_two_experiments/structure_two_world_generator_manifest_v0_4.json"
)
SEED_ATTESTATION = ROOT / (
    "configs/project_two_experiments/structure_two_world_seed_block_attestation_v0_4.json"
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--public-key-file", type=Path, required=True)
    parser.add_argument("--key-id", required=True)
    parser.add_argument("--draft", type=Path, default=DEFAULT_DRAFT)
    args = parser.parse_args()
    draft_path = args.draft if args.draft.is_absolute() else ROOT / args.draft
    if FROZEN_MANIFEST.exists() or SEED_ATTESTATION.exists():
        raise FileExistsError("trust anchor cannot change after attestation or freeze")

    payload = json.loads(draft_path.read_text(encoding="utf-8"))
    if payload.get("status") != "DRAFT-awaiting-trust-anchor-and-custodian-attestation":
        raise ValueError("input is not the unsigned v0.4 validation draft")
    authorization = payload.get("freeze_authorization", {})
    approval_id = str(authorization.get("user_approval_id", ""))
    if not approval_id or "TO BE SET" in approval_id:
        raise ValueError("user freeze approval id must be recorded first")
    if authorization.get("configured_before_custodian_signature") is True:
        raise ValueError("custodian trust anchor is already configured")

    public_key_path = (
        args.public_key_file
        if args.public_key_file.is_absolute()
        else Path.cwd() / args.public_key_file
    )
    verifier = Ed25519AttestationVerifier.from_public_key_pem(
        key_id=args.key_id,
        public_key_pem=public_key_path.read_bytes(),
    )
    key_hash = verifier.public_key_sha256
    payload["custodian_attestation"] = {
        "required_artifact": (
            "configs/project_two_experiments/structure_two_world_seed_block_attestation_v0_4.json"
        ),
        "trusted_custodian_key_id": args.key_id,
        "trusted_custodian_public_key_sha256": key_hash,
        "current_status": "AWAITING external custodian signature - fail closed",
    }
    payload["freeze_authorization"] = {
        **authorization,
        "trusted_custodian_key_id": args.key_id,
        "trusted_custodian_public_key_sha256": key_hash,
        "configured_before_custodian_signature": True,
    }
    draft_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"draft={draft_path}")
    print(f"key_id={args.key_id}")
    print(f"trusted_custodian_public_key_sha256={key_hash}")
    print(f"user_approval_id={approval_id}")
    print("private_key_loaded=False")
    print("signature_created=False")


if __name__ == "__main__":
    main()
