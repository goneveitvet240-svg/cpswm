"""Run the frozen Round-2 direct-opponent experiments that are executable."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from cpswm.system.evaluation_operations.method_falsification import (  # noqa: E402
    current_method_falsification_registry,
    evaluate_method_submission,
)
from cpswm.system.evaluation_operations.report_output import write_report_atomic  # noqa: E402
from cpswm.system.evaluation_operations.round_two_falsification import (  # noqa: E402
    run_structure_one_layered_habit_round_two,
    run_structure_one_placement_round_two,
    run_structure_three_multi_parse_round_two,
)

DEFAULT_CONFIG = REPOSITORY_ROOT / "configs/method_falsification/round_two_v0_1.json"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "output/method_falsification/round_two_structure_one_v0_1.json"
DEFAULT_SUBMISSIONS = (
    REPOSITORY_ROOT / "output/method_falsification/round_two_submissions_v0_1.json"
)
DEFAULT_STRUCTURE_THREE_OUTPUT = (
    REPOSITORY_ROOT / "output/method_falsification/round_two_structure_three_v0_1.json"
)
DEFAULT_PLACEMENT_OUTPUT = (
    REPOSITORY_ROOT / "output/method_falsification/round_two_structure_one_placement_v0_1.json"
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--submissions-output", type=Path, default=DEFAULT_SUBMISSIONS)
    parser.add_argument(
        "--structure-three-output",
        type=Path,
        default=DEFAULT_STRUCTURE_THREE_OUTPUT,
    )
    parser.add_argument("--placement-output", type=Path, default=DEFAULT_PLACEMENT_OUTPUT)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    report, submission = run_structure_one_layered_habit_round_two(args.config)
    placement_report, placement_submission = run_structure_one_placement_round_two(args.config)
    s3_report, s3_submission = run_structure_three_multi_parse_round_two(args.config)
    registry = current_method_falsification_registry()
    result = evaluate_method_submission(registry.by_id(submission.method_id), submission)
    s3_result = evaluate_method_submission(registry.by_id(s3_submission.method_id), s3_submission)
    placement_result = evaluate_method_submission(
        registry.by_id(placement_submission.method_id), placement_submission
    )
    report["formal_result"] = result.model_dump(mode="json")
    placement_report["formal_result"] = placement_result.model_dump(mode="json")
    s3_report["formal_result"] = s3_result.model_dump(mode="json")
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    s3_rendered = json.dumps(s3_report, ensure_ascii=False, indent=2, sort_keys=True)
    placement_rendered = json.dumps(placement_report, ensure_ascii=False, indent=2, sort_keys=True)
    submissions = json.dumps(
        [
            submission.model_dump(mode="json"),
            placement_submission.model_dump(mode="json"),
            s3_submission.model_dump(mode="json"),
        ],
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    write_report_atomic(
        rendered + "\n",
        output_path=args.output,
        config_path=args.config,
        repository_root=REPOSITORY_ROOT,
        force=args.force,
    )
    write_report_atomic(
        placement_rendered + "\n",
        output_path=args.placement_output,
        config_path=args.config,
        repository_root=REPOSITORY_ROOT,
        force=args.force,
    )
    write_report_atomic(
        s3_rendered + "\n",
        output_path=args.structure_three_output,
        config_path=args.config,
        repository_root=REPOSITORY_ROOT,
        force=args.force,
    )
    write_report_atomic(
        submissions + "\n",
        output_path=args.submissions_output,
        config_path=args.config,
        repository_root=REPOSITORY_ROOT,
        force=args.force,
    )
    print(
        json.dumps(
            {
                "results": {
                    submission.method_id: result.decision.value,
                    placement_submission.method_id: placement_result.decision.value,
                    s3_submission.method_id: s3_result.decision.value,
                },
                "structure_one_output": str(args.output),
                "placement_output": str(args.placement_output),
                "structure_three_output": str(args.structure_three_output),
                "submissions_output": str(args.submissions_output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
