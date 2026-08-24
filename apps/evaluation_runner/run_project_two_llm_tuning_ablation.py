"""Run the D0 LLM evidence/tuning/ablation protocol pilot."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from cpswm.system.evaluation_operations.project_two_dataset_adapters import (  # noqa: E402
    D0SyntheticOracleReplayAdapter,
)
from cpswm.system.evaluation_operations.project_two_llm_experiment import (  # noqa: E402
    ProjectTwoLLMExperimentPilot,
)


def run() -> dict[str, object]:
    dataset = D0SyntheticOracleReplayAdapter(
        validation_seeds=(101, 103),
        test_seeds=(211, 223),
        max_steps_per_episode=16,
    ).build()
    return ProjectTwoLLMExperimentPilot(search_budget=3).run(dataset).model_dump(mode="json")


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
