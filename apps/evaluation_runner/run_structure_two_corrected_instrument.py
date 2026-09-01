"""Run and verify the Structure-Two corrected evaluation instrument v0.3."""

from __future__ import annotations

import argparse
from pathlib import Path

from cpswm.system.evaluation_operations.structure_two_corrected_instrument import (
    DEFAULT_OUTPUT,
    run_structure_two_corrected_instrument,
    verify_structure_two_corrected_instrument_report,
    write_structure_two_corrected_instrument_report,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--recompute", action="store_true")
    args = parser.parse_args()
    root = args.repository_root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    if args.verify_only:
        report = verify_structure_two_corrected_instrument_report(
            output,
            repository_root=root,
            recompute=args.recompute,
        )
    else:
        report = run_structure_two_corrected_instrument(repository_root=root)
        write_structure_two_corrected_instrument_report(report, output)
        verify_structure_two_corrected_instrument_report(
            output,
            repository_root=root,
            recompute=False,
        )
    print(f"report={output}")
    print(f"content_sha256={report['content_sha256']}")
    print(f"instrument_integrity_passed={report['instrument_integrity_passed']}")
    print(f"comparison_validity_passed={report['comparison_validity_passed']}")
    print(f"scientific_conclusion={report['scientific_conclusion']}")


if __name__ == "__main__":
    main()
