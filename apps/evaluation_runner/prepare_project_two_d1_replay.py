"""Generate the source-neutral D1 batch or import a selected D1 JSONL/Parquet source."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from cpswm.contracts import ProjectTwoDataMaturity  # noqa: E402
from cpswm.system.evaluation_operations.project_two_d1_development import (  # noqa: E402
    build_d1_development_batch,
)
from cpswm.system.evaluation_operations.project_two_replay_importer import (  # noqa: E402
    ProjectTwoReplayFileImporter,
    export_project_two_replay_dataset,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "artifacts/project_two_data/d1_generic_development_v0_1",
    )
    parser.add_argument("--visible", type=Path)
    parser.add_argument("--truth", type=Path)
    parser.add_argument("--dataset-version")
    parser.add_argument("--steps", type=int, default=32)
    args = parser.parse_args()
    supplied = args.visible is not None or args.truth is not None
    if supplied and (args.visible is None or args.truth is None or not args.dataset_version):
        parser.error("--visible, --truth, and --dataset-version are required together")
    if supplied:
        dataset = ProjectTwoReplayFileImporter(
            maturity=ProjectTwoDataMaturity.D1_SIMULATOR_ANNOTATED_REPLAY,
            dataset_version=args.dataset_version,
            adapter_provenance="generic D1 JSONL/Parquet importer",
        ).load(args.visible, args.truth)
    else:
        dataset = build_d1_development_batch(max_steps_per_episode=args.steps)
    print(
        json.dumps(
            export_project_two_replay_dataset(dataset, args.output_dir),
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
