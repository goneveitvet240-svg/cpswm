"""Run the post-diagnostic structure-two dual-timescale development benchmark."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from cpswm.system.evaluation_operations.project_two_dual_timescale_development import (  # noqa: E402
    run_dual_timescale_development,
)


def _seeds(start: int, count: int) -> tuple[int, ...]:
    if count < 1:
        raise ValueError("seed count must be positive")
    return tuple(range(start, start + count))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validation-count", type=int, default=20)
    parser.add_argument("--holdout-count", type=int, default=60)
    parser.add_argument("--validation-seed-start", type=int, default=12000)
    parser.add_argument("--holdout-seed-start", type=int, default=13000)
    parser.add_argument("--max-steps", type=int, default=32)
    parser.add_argument("--output", type=Path, default=None)
    arguments = parser.parse_args()
    payload = run_dual_timescale_development(
        validation_seeds=_seeds(arguments.validation_seed_start, arguments.validation_count),
        holdout_seeds=_seeds(arguments.holdout_seed_start, arguments.holdout_count),
        max_steps=arguments.max_steps,
    )
    rendered = json.dumps(payload, indent=2, ensure_ascii=False)
    if arguments.output is None:
        print(rendered)
        return
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(rendered, encoding="utf-8")
    print(f"wrote {arguments.output}")


if __name__ == "__main__":
    main()
