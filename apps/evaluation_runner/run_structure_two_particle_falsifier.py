"""Run the Structure Two exact-enumeration particle conformance falsifier."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cpswm.system.evaluation_operations.structure_two_particle_falsifier import (
    run_exact_enumeration_falsifier,
    write_exact_enumeration_report,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--particle-budget", type=int, default=24)
    parser.add_argument("--bootstrap-seed", type=int, default=8701)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "artifacts/project_two_v04_development/structure_two_particle_exact_falsifier_v0_1.json"
        ),
    )
    args = parser.parse_args()
    report = run_exact_enumeration_falsifier(
        particle_budget=args.particle_budget,
        bootstrap_seed=args.bootstrap_seed,
    )
    write_exact_enumeration_report(report, args.output)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "content_sha256": report["content_sha256"],
                "all_development_gates_passed": report["all_development_gates_passed"],
                "method_summaries": report["method_summaries"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
