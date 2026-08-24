"""Validate the machine-readable M01-M32 / WS1-WS10 progress ledger.

Usage::

    python apps/progress_ledger/validate_progress.py [--ledger PATH] [--repo-root PATH]
        [--authority-key-file PATH]

Exit code 0 means the ledger is internally consistent AND every required gate
is passed.  Exit code 1 means the ledger contains contradictions, missing
files, tampered evidence, or a blocked required gate.  This CLI never upgrades
maturity and never chooses a research route.

Gates that promote on an execution against data (``replay_validated`` and
above) need the governance attestation key, supplied by
``--authority-key-file`` or ``CPSWM_ATTESTATION_KEY_FILE``.  Run without it and
those gates BLOCK with an explicit "no authority was supplied" reason: the
candidate implementation is not allowed to authenticate its own run receipts,
so a reviewer holding the key is the one who can turn them green.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from cpswm.system.attestation import AttestationAuthority  # noqa: E402
from cpswm.system.progress_ledger import ProgressLedger, validate_ledger  # noqa: E402

#: Key id the ledger's run receipts are signed under.
AUTHORITY_KEY_ID = "cpswm-governance-authority"

DEFAULT_LEDGER = (
    REPOSITORY_ROOT / "src" / "cpswm" / "system" / "progress_ledger" / "progress_ledger.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the CPSWM structure-one progress ledger."
    )
    parser.add_argument(
        "--ledger",
        type=Path,
        default=DEFAULT_LEDGER,
        help="path to the progress ledger JSON",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPOSITORY_ROOT,
        help="repository root against which referenced paths are resolved",
    )
    parser.add_argument(
        "--authority-key-file",
        type=Path,
        default=None,
        help=(
            "file holding the governance attestation key (>=32 bytes). "
            "Defaults to $CPSWM_ATTESTATION_KEY_FILE. Without it, every gate "
            "above synthetic BLOCKs because its run receipts cannot be "
            "authenticated."
        ),
    )
    return parser.parse_args()


def load_authority(path: Path | None) -> AttestationAuthority | None:
    """Load the signing key, or return ``None`` and let the gates say so."""

    if path is None:
        env_path = os.environ.get("CPSWM_ATTESTATION_KEY_FILE")
        if not env_path:
            return None
        path = Path(env_path)
    secret = path.read_bytes().strip()
    return AttestationAuthority(key_id=AUTHORITY_KEY_ID, secret=secret)


def load_ledger(path: Path) -> ProgressLedger:
    data = json.loads(path.read_text(encoding="utf-8"))
    return ProgressLedger.model_validate(data)


def print_coverage_matrix(ledger: ProgressLedger) -> None:
    print("=== coverage matrix (module -> workstreams) ===")
    for entry in ledger.modules:
        workstreams = ",".join(entry.workstream_ids) if entry.workstream_ids else "-"
        print(f"{entry.module_id}\t{entry.maturity.value}\t{workstreams}")


def main() -> int:
    args = parse_args()
    ledger = load_ledger(args.ledger)
    authority = load_authority(args.authority_key_file)
    report = validate_ledger(ledger, args.repo_root, authority=authority)

    print_coverage_matrix(ledger)
    print()
    if authority is None:
        print(
            "attestation: NO KEY SUPPLIED -- run receipts are unauthenticated, "
            "so every gate above synthetic BLOCKs"
        )
    else:
        print(f"attestation: verifying run receipts under key {authority.key_id!r}")
    print()

    for gate in report.gate_results:
        status = "PASS" if gate.passed else "BLOCK"
        required = "required" if gate.required else "optional"
        print(f"=== gate {gate.gate_id} [{required}]: {status} ===")
        for blocker in gate.blockers:
            print(f"  BLOCK: {blocker}")
        print()

    if report.errors:
        print("=== errors ===")
        for error in report.errors:
            print(f"  ERROR: {error}")
    if report.warnings:
        print("=== warnings ===")
        for warning in report.warnings:
            print(f"  WARN: {warning}")

    print(
        f"internally_consistent={report.internally_consistent} "
        f"required_gates_passed={report.required_gates_passed}"
    )

    if not report.internally_consistent or not report.required_gates_passed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
