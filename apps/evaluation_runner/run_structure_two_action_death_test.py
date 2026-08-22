"""Run the structure-two action-level matched death test.

The benchmark compares PCHMP x CCRR x RGRC against four faithfully adapted
baselines (AMG / O-STaR / DynaMem / STAR) on a multi-day household scenario
with selective observation, hidden direct/handoff relocations, guest
contamination, an abrupt owner-habit change, and a recurrence of the old habit.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from cpswm.system.evaluation_operations import (  # noqa: E402
    StructureTwoActionDeathTest,
    StructureTwoActionScenarioGenerator,
)

DEFAULT_SEEDS = tuple(range(1, 21))


def run() -> dict[str, object]:
    generator = StructureTwoActionScenarioGenerator()
    report = StructureTwoActionDeathTest(generator).run(DEFAULT_SEEDS)
    return {
        "generator_version": report.generator_version,
        "seed_count": len(DEFAULT_SEEDS),
        "method_reports": [
            report.model_dump(mode="json") for report in report.method_reports
        ],
        "scientific_status": report.scientific_status,
        "interpretation": {
            "fairness": (
                "every method receives the same robot-visible stream and action "
                "budget; ground truth is only available to the evaluator"
            ),
            "baselines": (
                "domain adaptations, not full reproductions: AMG MAP event parse, "
                "O-STaR Dirichlet counts, DynaMem latest state, STAR frequency "
                "retrieval"
            ),
            "new_method": (
                "PCHMP joint event posterior -> CF-BOCPD cause posterior -> CCRR "
                "stay/create/reactivate/unresolved -> RGRC-gated owner habit "
                "consolidation"
            ),
            "claim_discipline": (
                "a strictly-better put-back result is a research signal, not a "
                "general superiority claim; external validity remains unproven"
            ),
        },
    }


def main() -> None:
    print(json.dumps(run(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
