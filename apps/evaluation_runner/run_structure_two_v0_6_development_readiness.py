#!/usr/bin/env python3
"""Write the fail-closed Structure-Two v0.6 development-readiness report."""

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
from cpswm.system.evaluation_operations.structure_two_v0_6_readiness import (  # noqa: E402
    DEFAULT_OUTPUT,
    build_v0_6_development_readiness,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--evidence-index",
        type=Path,
        default=ROOT / "configs/project_two_experiments/structure_two_v0_6_evidence_index.json",
    )
    parser.add_argument("--trusted-enrollment-authority-key-id")
    parser.add_argument("--trusted-enrollment-authority-public-key-pem", type=Path)
    args = parser.parse_args()
    authority_options = (
        args.trusted_enrollment_authority_key_id,
        args.trusted_enrollment_authority_public_key_pem,
    )
    if any(authority_options) and not all(authority_options):
        parser.error("both enrollment-authority options are required together")
    trusted_authority = (
        Ed25519AttestationVerifier.from_public_key_pem(
            key_id=args.trusted_enrollment_authority_key_id,
            public_key_pem=(args.trusted_enrollment_authority_public_key_pem.read_bytes()),
        )
        if all(authority_options)
        else None
    )
    report = build_v0_6_development_readiness(
        ROOT,
        evidence_index_path=args.evidence_index,
        trusted_enrollment_authority=trusted_authority,
    )
    output = ROOT / DEFAULT_OUTPUT
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        "design_evidence_ready_for_external_freeze="
        f"{report['design_evidence_ready_for_external_freeze']}"
    )
    print(f"v0_6_gate_b_scored={report['v0_6_gate_b_scored']}")
    print(
        f"external_fidelity_gate_passed={report['external_fidelity']['external_fidelity_gate_passed']}"
    )


if __name__ == "__main__":
    main()
