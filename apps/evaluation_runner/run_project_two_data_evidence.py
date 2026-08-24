"""Materialize the project-two multi-seed data evidence batch.

Visible replay, evaluator-only truth, and summary reports are written to
separate files so method code never needs access to oracle labels.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from cpswm.system.evaluation_operations import (  # noqa: E402
    D0SyntheticOracleReplayAdapter,
    enforce_project_two_replay_gate,
    summarize_project_two_evidence_coverage,
)

DEFAULT_CONFIG = (
    REPOSITORY_ROOT / "configs" / "project_two_datasets" / "d0_multiseed_evidence_v0_3.json"
)
DEFAULT_OUTPUT = REPOSITORY_ROOT / "artifacts" / "project_two_data" / "d0_multiseed_v0_3"


def _seed_range(start: int, count: int) -> tuple[int, ...]:
    if count < 1:
        raise ValueError("seed count must be positive")
    return tuple(range(start, start + count))


def materialize(config_path: Path, output_dir: Path) -> dict[str, object]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    validation_seeds = _seed_range(config["validation_seed_start"], config["validation_seed_count"])
    test_seeds = _seed_range(config["test_seed_start"], config["test_seed_count"])
    dataset = D0SyntheticOracleReplayAdapter(
        validation_seeds=validation_seeds,
        test_seeds=test_seeds,
        max_steps_per_episode=config["steps_per_episode"],
        dataset_version=config["dataset_version"],
        object_family_bucket_count=config["object_family_bucket_count"],
        sealed_secret=config["development_uuid_seal_secret"],
    ).build()
    quality = enforce_project_two_replay_gate(dataset)
    coverage = summarize_project_two_evidence_coverage(dataset)

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "manifest.json").write_text(
        dataset.manifest.model_dump_json(indent=2), encoding="utf-8"
    )
    (output_dir / "visible_replay.jsonl").write_text(
        "\n".join(item.model_dump_json() for item in dataset.episodes) + "\n",
        encoding="utf-8",
    )
    (output_dir / "evaluator_truth.jsonl").write_text(
        "\n".join(item.model_dump_json() for item in dataset.evaluator_store) + "\n",
        encoding="utf-8",
    )
    report = {
        "config": config,
        "quality": quality.model_dump(mode="json"),
        "coverage": coverage.model_dump(mode="json"),
        "artifacts": {
            "manifest": "manifest.json",
            "visible_replay": "visible_replay.jsonl",
            "evaluator_truth": "evaluator_truth.jsonl",
        },
    }
    (output_dir / "evidence_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(json.dumps(materialize(args.config, args.output_dir), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
