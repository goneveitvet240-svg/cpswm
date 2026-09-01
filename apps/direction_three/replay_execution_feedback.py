"""Rebuild direction-three target-presence memory from a canonical M03 log."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SOURCE_ROOT = _PROJECT_ROOT / "src"
if str(_SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SOURCE_ROOT))

from cpswm.foundation.persistence_replay import AppendOnlyTransactionLog  # noqa: E402
from cpswm.system.evaluation_operations.report_output import write_report_atomic  # noqa: E402
from cpswm.world_model.grounded_search import (  # noqa: E402
    BoundActionOutcomeModelRegistry,
    CanonicalExecutionFeedbackReplayer,
    DirectionThreeFeedbackReplaySpec,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("canonical_log", type=Path)
    parser.add_argument("replay_spec", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    log = AppendOnlyTransactionLog.load(args.canonical_log)
    spec = DirectionThreeFeedbackReplaySpec.model_validate_json(
        args.replay_spec.read_text(encoding="utf-8")
    )
    report = CanonicalExecutionFeedbackReplayer().replay(
        log,
        initial_priors=spec.initial_priors,
        outcome_model_provider=BoundActionOutcomeModelRegistry(spec.outcome_models),
        through_commit_seq=spec.through_commit_seq,
        household_id=spec.household_id,
    )
    rendered = json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        write_report_atomic(
            rendered,
            output_path=args.output,
            config_path=args.replay_spec,
            repository_root=_PROJECT_ROOT,
            force=args.force,
        )
    print(rendered, end="")


if __name__ == "__main__":
    main()
