"""Run project-two corrected action-level matched benchmark v0.4.

Validation and sealed test episodes are household/scene/object-family disjoint.
The old v0.1 reduced-skill death test remains importable for regression only;
this CLI now emits the corrected-interface v0.4 report.  Historical v0.2
artifacts remain immutable evidence of the earlier protocol.

``--seeds`` controls how many episodes each split gets.  The default of ``0``
keeps the two frozen validation and two frozen test seeds, so the 2026-08-24 D0
report stays byte-reproducible.  Any positive value draws from disjoint reserved
ranges instead.

That default is *small*: four episodes total.  A paired interval computed over
two test episodes can report zero width -- the bootstrap has two things to
resample -- which reads as certainty and is not.  Scale the seeds before
treating any of these differences as settled.
"""

from __future__ import annotations

import argparse
import hashlib
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
from cpswm.system.evaluation_operations.project_two_experiment_config import (  # noqa: E402
    D0SyntheticReplayExperimentConfig,
)

#: The two frozen splits behind the 2026-08-24 D0 report.  Kept as the default
#: so that report stays reproducible; four episodes is not a sample size.
VALIDATION_SEEDS = (101, 103)
SEALED_TEST_SEEDS = (211, 223)

#: Reserved, disjoint ranges for scaled runs.  Far from the frozen seeds so a
#: scaled run can never accidentally reuse one of them.
_VALIDATION_BASE = 1000
_TEST_BASE = 5000

DEFAULT_MULTISEED_CONFIG = (
    REPOSITORY_ROOT / "configs/project_two_datasets/d0_multiseed_evidence_v0_3.json"
)


def split_seeds(count: int) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Validation and sealed-test seeds for ``count`` episodes per split."""

    if count < 0:
        raise ValueError("count must be non-negative")
    if count == 0:
        return VALIDATION_SEEDS, SEALED_TEST_SEEDS
    return (
        tuple(range(_VALIDATION_BASE, _VALIDATION_BASE + count)),
        tuple(range(_TEST_BASE, _TEST_BASE + count)),
    )


def run_configured(config_path: Path = DEFAULT_MULTISEED_CONFIG) -> dict[str, object]:
    """Run the action benchmark on an already registered multiseed D0 design."""

    config_path = config_path.resolve()
    config_bytes = config_path.read_bytes()
    config = D0SyntheticReplayExperimentConfig.load(config_path)
    dataset = config.build_adapter().build()
    quality = audit_project_two_replay(dataset)
    report = ProjectTwoActionBenchmarkV02().run(dataset)
    return {
        "experiment_config": {
            "path": str(config_path),
            "sha256": hashlib.sha256(config_bytes).hexdigest(),
            "confirmatory": config.confirmatory,
            "evidence_stage": config.evidence_stage,
        },
        "data_quality": quality.model_dump(mode="json"),
        "benchmark": report.model_dump(mode="json"),
    }


def run(*, seeds: int = 0, max_steps: int = 32) -> dict[str, object]:
    validation, test = split_seeds(seeds)
    dataset = D0SyntheticOracleReplayAdapter(
        validation_seeds=validation,
        test_seeds=test,
        max_steps_per_episode=max_steps,
    ).build()
    quality = audit_project_two_replay(dataset)
    report = ProjectTwoActionBenchmarkV02().run(dataset)
    return {
        "data_quality": quality.model_dump(mode="json"),
        "benchmark": report.model_dump(mode="json"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seeds",
        type=int,
        default=0,
        help=(
            "episodes per split; 0 keeps the two frozen validation and two "
            "frozen test seeds behind the 2026-08-24 report"
        ),
    )
    parser.add_argument("--max-steps", type=int, default=32)
    parser.add_argument(
        "--dataset-config",
        type=Path,
        default=None,
        help=(
            "registered D0 JSON config; when supplied its split sizes, seeds, "
            "step budget, dataset version, family buckets, and seal are authoritative"
        ),
    )
    parser.add_argument("--output", type=Path, default=None)
    arguments = parser.parse_args()

    if arguments.dataset_config is not None:
        if arguments.seeds != 0 or arguments.max_steps != 32:
            parser.error("--dataset-config cannot be combined with --seeds or --max-steps")
        payload = run_configured(arguments.dataset_config)
    else:
        payload = run(seeds=arguments.seeds, max_steps=arguments.max_steps)
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    if arguments.output is not None:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(text, encoding="utf-8")
        quality = payload["data_quality"]
        print(
            f"episodes={quality['episode_count']} steps={quality['step_count']} "  # type: ignore[index]
            f"feedback={quality['feedback_count']}"  # type: ignore[index]
        )
        print(f"wrote {arguments.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
