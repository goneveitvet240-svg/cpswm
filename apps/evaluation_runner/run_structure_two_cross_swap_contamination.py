"""Run the v0.6 belief/readout cross-swap and contamination first-fault trace."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from cpswm.system.evaluation_operations.project_two_experiment_config import (  # noqa: E402
    D0SyntheticReplayExperimentConfig,
)
from cpswm.system.evaluation_operations.structure_two_cross_swap_contamination import (  # noqa: E402
    run_cross_swap_contamination_diagnostic,
)

DEFAULT_CONFIG = (
    REPOSITORY_ROOT
    / "configs/project_two_experiments/structure_two_cross_swap_contamination_v0_1.json"
)
DEFAULT_OUTPUT = (
    REPOSITORY_ROOT / "benchmarks/structure_two/structure_two_cross_swap_contamination_v0_1.json"
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    experiment_path = arguments.config.resolve()
    experiment = json.loads(experiment_path.read_text(encoding="utf-8"))
    if experiment.get("protocol") != "structure-two-belief-readout-cross-swap-contamination@0.2":
        raise ValueError("cross-swap experiment protocol mismatch")
    dataset_path = REPOSITORY_ROOT / experiment["dataset_config"]
    config = D0SyntheticReplayExperimentConfig.load(dataset_path)
    dataset = config.build_adapter().build()
    report = run_cross_swap_contamination_diagnostic(dataset)
    source_paths = (
        Path("src/cpswm/system/evaluation_operations/structure_two_cross_swap_contamination.py"),
        Path("apps/evaluation_runner/run_structure_two_cross_swap_contamination.py"),
        experiment_path.relative_to(REPOSITORY_ROOT),
        dataset_path.relative_to(REPOSITORY_ROOT),
    )
    unsigned = {
        "artifact_protocol_id": "structure-two-cross-swap-artifact@0.2-development",
        "source_files": [
            {
                "path": path.as_posix(),
                "sha256": hashlib.sha256((REPOSITORY_ROOT / path).read_bytes()).hexdigest(),
            }
            for path in source_paths
        ],
        "report": report.to_dict(),
    }
    artifact = {
        **unsigned,
        "content_sha256": hashlib.sha256(
            json.dumps(
                unsigned,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                default=str,
            ).encode("utf-8")
        ).hexdigest(),
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(artifact, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    print(
        f"traces={len(report.contamination_traces)} "
        f"first_faults={report.first_fault_counts} wrote={arguments.output}"
    )


if __name__ == "__main__":
    main()
