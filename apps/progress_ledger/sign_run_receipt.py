"""Sign a run receipt with the governance attestation key.

A verifier nobody can produce input for is not a control, it is a wall.  This
is the other half of ``validate_progress.py --authority-key-file``: the harness
that actually executed a run hands the resulting receipt to whoever holds the
key, and that party -- not the candidate implementation -- signs it.

Usage::

    python apps/progress_ledger/sign_run_receipt.py \\
        --receipt evidence/m05_receipt.json \\
        --authority-key-file /secure/cpswm-authority.key

The receipt is read, validated against :class:`RunReceipt`, signed in the
``cpswm.ledger.run_receipt.v1`` domain, and written back with its
``attestation`` field populated.  An existing attestation is replaced, because
the signature covers content and stale signatures must never survive an edit.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from cpswm.system.attestation import (  # noqa: E402
    DOMAIN_RUN_RECEIPT,
    AttestationAuthority,
    AttestationError,
)
from cpswm.system.progress_ledger.contracts import RunReceipt  # noqa: E402

AUTHORITY_KEY_ID = "cpswm-governance-authority"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Attest a CPSWM run receipt.")
    parser.add_argument("--receipt", type=Path, required=True, help="run receipt JSON to sign")
    parser.add_argument(
        "--authority-key-file",
        type=Path,
        default=None,
        help="key file (>=32 bytes); defaults to $CPSWM_ATTESTATION_KEY_FILE",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the existing attestation instead of writing a new one",
    )
    return parser.parse_args()


def load_authority(path: Path | None) -> AttestationAuthority:
    if path is None:
        env_path = os.environ.get("CPSWM_ATTESTATION_KEY_FILE")
        if not env_path:
            raise SystemExit(
                "no attestation key: pass --authority-key-file or set CPSWM_ATTESTATION_KEY_FILE"
            )
        path = Path(env_path)
    return AttestationAuthority(key_id=AUTHORITY_KEY_ID, secret=path.read_bytes().strip())


def main() -> int:
    args = parse_args()
    authority = load_authority(args.authority_key_file)
    receipt = RunReceipt.model_validate(json.loads(args.receipt.read_text(encoding="utf-8")))

    if args.check:
        # A verdict, not a traceback: this runs in CI, where a crash and a
        # failed check must not look the same.
        try:
            authority.verify(DOMAIN_RUN_RECEIPT, receipt.attested_content(), receipt.attestation)
        except AttestationError as error:
            print(f"{args.receipt}: NOT ATTESTED -- {error}")
            return 1
        print(f"{args.receipt}: attestation is valid")
        return 0

    unsigned = receipt.model_copy(update={"attestation": None})
    signature = authority.sign(DOMAIN_RUN_RECEIPT, unsigned.attested_content())
    signed = unsigned.model_copy(update={"attestation": signature})
    args.receipt.write_text(
        json.dumps(json.loads(signed.model_dump_json()), indent=2) + "\n", encoding="utf-8"
    )
    print(f"{args.receipt}: signed under key {authority.key_id!r} ({signature.mac[:16]}...)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
