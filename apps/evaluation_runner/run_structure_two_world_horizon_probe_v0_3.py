"""Run or verify the frozen train-only Structure-Two horizon probe v0.3."""

from __future__ import annotations

import argparse
from pathlib import Path

from cpswm.system.evaluation_operations.structure_two_world_horizon_probe_v0_3 import (
    DEFAULT_OUTPUT,
    run_horizon_probe,
    verify_horizon_probe_report,
    write_horizon_probe_report,
)


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--recompute", action="store_true")
    args = parser.parse_args()
    root = _repository_root()
    output = args.output if args.output.is_absolute() else root / args.output
    if args.verify_only:
        report = verify_horizon_probe_report(
            output,
            repository_root=root,
            recompute=args.recompute,
        )
    else:
        report = run_horizon_probe(repository_root=root)
        write_horizon_probe_report(report, output)
        verify_horizon_probe_report(output, repository_root=root)
    print(f"artifact={output}")
    print(f"content_sha256={report['content_sha256']}")
    print(f"horizon_probe_passed={report['horizon_probe_passed']}")
    print(f"draft_manifest_may_adopt_duration={report['draft_manifest_may_adopt_duration']}")


if __name__ == "__main__":
    main()
