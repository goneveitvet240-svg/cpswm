"""Run fixed-configuration D0 and D1 episodes through the complete Project Two loop."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from cpswm.system.evaluation_operations.project_two_d1_development import (  # noqa: E402
    build_d1_development_batch,
)
from cpswm.system.evaluation_operations.project_two_dataset_adapters import (  # noqa: E402
    D0SyntheticOracleReplayAdapter,
)
from cpswm.system.evaluation_operations.project_two_multiseed_evidence import (  # noqa: E402
    run_project_two_replay_evidence,
    write_project_two_replay_evidence,
)
from cpswm.system.evaluation_operations.project_two_replay_importer import (  # noqa: E402
    export_project_two_replay_dataset,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "benchmarks/project_two_action/replay_evidence_v0_3",
    )
    parser.add_argument("--bootstrap-samples", type=int, default=2000)
    parser.add_argument("--d1-steps", type=int, default=32)
    args = parser.parse_args()
    config = json.loads(
        (ROOT / "configs/project_two_datasets/d0_multiseed_evidence_v0_3.json").read_text()
    )
    d0 = D0SyntheticOracleReplayAdapter(
        validation_seeds=tuple(
            range(
                config["validation_seed_start"],
                config["validation_seed_start"] + config["validation_seed_count"],
            )
        ),
        test_seeds=tuple(
            range(
                config["test_seed_start"],
                config["test_seed_start"] + config["test_seed_count"],
            )
        ),
        max_steps_per_episode=config["steps_per_episode"],
        dataset_version=config["dataset_version"],
        object_family_bucket_count=config["object_family_bucket_count"],
        sealed_secret=config["development_uuid_seal_secret"],
    ).build()
    d1 = build_d1_development_batch(max_steps_per_episode=args.d1_steps)
    summaries = {}
    for label, dataset in (("d0", d0), ("d1", d1)):
        output = args.output_root / label
        export_project_two_replay_dataset(dataset, output / "dataset")
        report = run_project_two_replay_evidence(dataset, bootstrap_samples=args.bootstrap_samples)
        write_project_two_replay_evidence(report, output / "full_loop")
        summaries[label] = {
            "dataset_version": report["dataset_version"],
            "episode_count": report["episode_count"],
            "step_count": report["step_count"],
            "aggregate_metrics": report["aggregate_metrics"],
        }
    (args.output_root / "run_summary.json").write_text(
        json.dumps(summaries, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(summaries, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
