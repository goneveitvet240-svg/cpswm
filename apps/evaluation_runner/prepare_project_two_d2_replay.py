"""Executable D2 collection-normalization/import tool and sensor-shaped example batch."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from cpswm.contracts import (  # noqa: E402
    ProjectTwoEvaluatorTruthEnvelope,
)
from cpswm.system.evaluation_operations.project_two_dataset_adapters import (  # noqa: E402
    D2RealPerceptionReplayAdapter,
)
from cpswm.system.evaluation_operations.project_two_real_perception import (  # noqa: E402
    D2RealPerceptionConverter,
    D2RealPerceptionRawEpisode,
    materialize_d2_example_batch,
)
from cpswm.system.evaluation_operations.project_two_replay_importer import (  # noqa: E402
    export_project_two_replay_dataset,
)


def _load_jsonl(path: Path, model):
    return tuple(
        model.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "artifacts/project_two_data/d2_real_perception_example_v0_1",
    )
    parser.add_argument("--raw-visible", type=Path)
    parser.add_argument("--truth", type=Path)
    parser.add_argument("--dataset-version")
    parser.add_argument("--steps", type=int, default=12)
    args = parser.parse_args()
    supplied = args.raw_visible is not None or args.truth is not None
    if not supplied:
        report = materialize_d2_example_batch(args.output_dir, max_steps_per_episode=args.steps)
    else:
        if args.raw_visible is None or args.truth is None or not args.dataset_version:
            parser.error("--raw-visible, --truth, and --dataset-version are required together")
        raw = _load_jsonl(args.raw_visible, D2RealPerceptionRawEpisode)
        episodes = tuple(D2RealPerceptionConverter().convert_visible(item) for item in raw)
        truth = _load_jsonl(args.truth, ProjectTwoEvaluatorTruthEnvelope)
        dataset = D2RealPerceptionReplayAdapter(
            dataset_version=args.dataset_version,
            episodes=episodes,
            evaluator_store=truth,
            adapter_provenance="D2 raw perception collection converter",
        ).build()
        report = export_project_two_replay_dataset(dataset, args.output_dir)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
