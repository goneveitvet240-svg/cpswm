"""Run the preregistered Structure Two structured rejuvenation gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cpswm.system.evaluation_operations.structure_two_rejuvenation_gate import (
    FROZEN_PARTICLE_BUDGET,
    run_structured_rejuvenation_gate,
    verify_structured_rejuvenation_report,
    write_structured_rejuvenation_report,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--particle-budget", type=int, default=FROZEN_PARTICLE_BUDGET)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "artifacts/project_two_v04_development/"
            "structure_two_structured_rejuvenation_gate_v0_2.json"
        ),
    )
    args = parser.parse_args()
    if args.verify_only:
        report = verify_structured_rejuvenation_report(args.output)
        print(
            json.dumps(
                {
                    "output": str(args.output),
                    "verified": True,
                    "content_sha256": report["content_sha256"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    report = run_structured_rejuvenation_gate(particle_budget=args.particle_budget)
    write_structured_rejuvenation_report(report, args.output)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "content_sha256": report["content_sha256"],
                "all_preregistered_blocking_gates_passed": report[
                    "all_preregistered_blocking_gates_passed"
                ],
                "method_summaries": report["method_summaries"],
                "stress_summaries": report["stress_summaries"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
