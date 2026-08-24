"""Run project-two action-level matched benchmark v0.2.

Validation and sealed test episodes are household/scene/object-family disjoint.
The old v0.1 reduced-skill death test remains importable for regression only;
this CLI is the authoritative v0.2 entry point.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from cpswm.system.evaluation_operations import (  # noqa: E402
    D0SyntheticOracleReplayAdapter,
    ProjectTwoActionBenchmarkV02,
    audit_project_two_replay,
)

VALIDATION_SEEDS = (101, 103)
SEALED_TEST_SEEDS = (211, 223)


def run() -> dict[str, object]:
    dataset = D0SyntheticOracleReplayAdapter(
        validation_seeds=VALIDATION_SEEDS,
        test_seeds=SEALED_TEST_SEEDS,
        max_steps_per_episode=32,
    ).build()
    quality = audit_project_two_replay(dataset)
    report = ProjectTwoActionBenchmarkV02().run(dataset)
    return {
        "data_quality": quality.model_dump(mode="json"),
        "benchmark": report.model_dump(mode="json"),
    }


def main() -> None:
    print(json.dumps(run(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
