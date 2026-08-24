"""Run project-two action-level matched benchmark v0.2.

Validation and sealed test episodes are household/scene/object-family disjoint.
The old v0.1 reduced-skill death test remains importable for regression only;
this CLI is the authoritative v0.2 entry point.

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

#: The two frozen splits behind the 2026-08-24 D0 report.  Kept as the default
#: so that report stays reproducible; four episodes is not a sample size.
VALIDATION_SEEDS = (101, 103)
SEALED_TEST_SEEDS = (211, 223)

#: Reserved, disjoint ranges for scaled runs.  Far from the frozen seeds so a
#: scaled run can never accidentally reuse one of them.
_VALIDATION_BASE = 1000
_TEST_BASE = 5000


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
    parser.add_argument("--output", type=Path, default=None)
    arguments = parser.parse_args()

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
