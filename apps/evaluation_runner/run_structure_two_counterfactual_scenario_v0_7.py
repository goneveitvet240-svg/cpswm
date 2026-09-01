#!/usr/bin/env python3
"""Execute one bounded counterfactual scenario and write a signed receipt."""

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
from cpswm.system.evaluation_operations.structure_two_counterfactual_executor_v0_7 import (  # noqa: E402
    execute_counterfactual_scenario,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--program", type=Path, required=True)
    parser.add_argument("--executor-key-id", required=True)
    parser.add_argument("--executor-private-key-pem", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    signer = Ed25519AttestationSigner.from_private_key_pem(
        key_id=args.executor_key_id,
        private_key_pem=args.executor_private_key_pem.read_bytes(),
    )
    receipt = execute_counterfactual_scenario(args.program, signer=signer)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(receipt.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"scenario_id={receipt.scenario_id}")
    print(f"execution_succeeded={receipt.execution_succeeded}")
    print(f"exit_code={receipt.exit_code}")
    if not receipt.execution_succeeded:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
