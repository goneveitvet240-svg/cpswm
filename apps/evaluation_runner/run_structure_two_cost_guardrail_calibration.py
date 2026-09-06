"""Build the Structure Two v0.1 development cost/guardrail calibration.

The source action artifact is read-only.  This runner derives a paired cost
sensitivity envelope from its already-opened development holdout and executes
only the registered TRAIN episodes for the Hybrid RGRC cache-versus-log-replay
check.  It does not reopen or rerun the v0.6 holdout.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from cpswm.system.evaluation_operations import (  # noqa: E402
    build_cost_guardrail_calibration,
)

DEFAULT_SOURCE_REPORT = (
    REPOSITORY_ROOT / "artifacts/project_two_v04_development/"
    "structure_two_action_benchmark_v0_6_dual_timescale_2026_09_06.json"
)
DEFAULT_DATASET_CONFIG = (
    REPOSITORY_ROOT / "configs/project_two_datasets/d0_multiseed_readout_v0_5.json"
)
DEFAULT_OUTPUT = (
    REPOSITORY_ROOT / "artifacts/project_two_v04_development/"
    "structure_two_cost_guardrail_calibration_v0_1_2026_09_06.json"
)


def run(
    *,
    source_report: Path = DEFAULT_SOURCE_REPORT,
    dataset_config: Path = DEFAULT_DATASET_CONFIG,
) -> dict[str, object]:
    report = build_cost_guardrail_calibration(
        source_action_report_path=source_report,
        dataset_config_path=dataset_config,
    )
    return {"calibration": report.model_dump(mode="json")}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-report", type=Path, default=DEFAULT_SOURCE_REPORT)
    parser.add_argument("--dataset-config", type=Path, default=DEFAULT_DATASET_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()

    payload = run(
        source_report=arguments.source_report,
        dataset_config=arguments.dataset_config,
    )
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(text, encoding="utf-8")
    report = payload["calibration"]
    assert isinstance(report, dict)
    envelope = report["break_even_envelope"]
    assert isinstance(envelope, dict)
    print(
        "paired_holdout="
        f"{len(report['paired_holdout_rows'])} "
        f"train_replay={len(report['train_full_rerun_observations'])} "
        f"break_even_ratio={envelope['maximum_contamination_cost_per_event_in_inspection_cost_units']}"
    )
    print(f"wrote {arguments.output}")


if __name__ == "__main__":
    main()
