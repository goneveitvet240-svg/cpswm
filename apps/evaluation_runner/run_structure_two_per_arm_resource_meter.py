"""Run the Structure-Two per-arm resource meter on a registered D0 config."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from cpswm.system.evaluation_operations.project_two_experiment_config import (  # noqa: E402
    D0SyntheticReplayExperimentConfig,
)
from cpswm.system.evaluation_operations.structure_two_per_arm_resource_meter import (  # noqa: E402
    run_per_arm_resource_meter,
)

DEFAULT_CONFIG = ROOT / "configs/project_two_datasets/d0_multiseed_readout_v0_5.json"
DEFAULT_OUTPUT = (
    ROOT / "benchmarks/structure_two/structure_two_per_arm_resource_measurement_v0_1.json"
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    dataset = D0SyntheticReplayExperimentConfig.load(args.dataset_config).build_adapter().build()
    report = run_per_arm_resource_meter(dataset)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"output={args.output}")
    print(f"engineering_ready={report.comparison_environment_ready_for_engineering}")
    print(f"paper_ready={report.comparison_environment_ready_for_paper_claim}")
    print(f"fairness_sha256={report.deterministic_fairness_sha256}")


if __name__ == "__main__":
    main()
