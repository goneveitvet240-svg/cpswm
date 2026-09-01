#!/usr/bin/env python3
"""External-custodian-only fresh v0.5 seed/salt generator and signer."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cpswm.system.attestation import Ed25519AttestationSigner  # noqa: E402
from cpswm.system.evaluation_operations.structure_two_world_seed_attestation_v0_5 import (  # noqa: E402
    generate_fresh_seed_block_attestation,
    write_fresh_seed_block_attestation,
)

DRAFT = ROOT / (
    "configs/project_two_experiments/structure_two_world_generator_manifest_v0_5_DRAFT.json"
)
DEFAULT_PUBLIC_OUTPUT = ROOT / (
    "configs/project_two_experiments/structure_two_world_seed_block_attestation_v0_5.json"
)


def _write_secret(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(content)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run only in the independent custodian environment."
    )
    parser.add_argument("--private-key-file", type=Path, required=True)
    parser.add_argument("--key-id", required=True)
    parser.add_argument("--custodian-run-id", required=True)
    parser.add_argument("--secret-output-dir", type=Path, required=True)
    parser.add_argument("--public-output", type=Path, default=DEFAULT_PUBLIC_OUTPUT)
    args = parser.parse_args()
    draft = json.loads(DRAFT.read_text(encoding="utf-8"))
    signer = Ed25519AttestationSigner.from_private_key_pem(
        key_id=args.key_id,
        private_key_pem=args.private_key_file.read_bytes(),
    )
    record, raw_seeds, custody_salt = generate_fresh_seed_block_attestation(
        draft_manifest_path=DRAFT,
        train_artifact_content_sha256=draft["inheritance"]["train_artifact_content_sha256"],
        signer=signer,
        custodian_run_id=args.custodian_run_id,
        holdout_seed_count=int(draft["split_policy"]["sealed_holdout_world_count"]),
    )
    _write_secret(
        args.secret_output_dir / "structure_two_v0_5_raw_holdout_seeds.json",
        json.dumps(list(raw_seeds)) + "\n",
    )
    _write_secret(
        args.secret_output_dir / "structure_two_v0_5_custody_salt.txt",
        custody_salt + "\n",
    )
    write_fresh_seed_block_attestation(record, args.public_output)
    print(f"public_attestation={args.public_output}")
    print(f"commitment_count={record.holdout_seed_count}")
    print(f"public_key_sha256={record.custodian_public_key_sha256}")
    print("raw_seeds_disclosed=False")
    print("custody_salt_disclosed=False")


if __name__ == "__main__":
    main()
