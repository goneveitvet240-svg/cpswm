"""Validate the machine-readable M01-M32 / WS1-WS10 progress ledger.

Usage::

    python apps/progress_ledger/validate_progress.py [--ledger PATH] [--repo-root PATH]

Exit code 0 means the ledger is internally consistent AND every required gate
is passed.  Exit code 1 means the ledger contains contradictions, missing
files, tampered evidence, or a blocked required gate.  This CLI never upgrades
maturity and never chooses a research route.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from cpswm.system.progress_ledger import ProgressLedger, validate_ledger  # noqa: E402

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
    return parser.parse_args()


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
    report = validate_ledger(ledger, args.repo_root)

    print_coverage_matrix(ledger)
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
