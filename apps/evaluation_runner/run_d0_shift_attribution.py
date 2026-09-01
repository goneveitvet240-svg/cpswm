"""Run the checked-in D0 paired shift-attribution benchmark."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from cpswm.contracts import ActorEvidenceTrack  # noqa: E402
from cpswm.system.evaluation_operations import (  # noqa: E402
    D0ShiftScenarioConfig,
    D0ShiftScenarioGenerator,
    LoggedPolicyActorLocationBaseline,
    LoggedPolicyThenLocationBaseline,
    ShiftAttributionEvaluator,
    ShiftCause,
)

DEFAULT_CONFIG = (
    REPOSITORY_ROOT / "benchmarks" / "d0_shift_attribution" / "d0_scenario_config_v0.1.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run D0-O/D0-A/D0-H paired shift-attribution cases."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = D0ShiftScenarioConfig.model_validate_json(
        args.config.resolve().read_text(encoding="utf-8")
    )
    generator = D0ShiftScenarioGenerator()
    track_specs = (
        ("no_actor_evidence", None, LoggedPolicyThenLocationBaseline()),
        (
            ActorEvidenceTrack.CONTROLLED_NOISE.value,
            ActorEvidenceTrack.CONTROLLED_NOISE,
            LoggedPolicyActorLocationBaseline(),
        ),
        (
            ActorEvidenceTrack.ORACLE.value,
            ActorEvidenceTrack.ORACLE,
            LoggedPolicyActorLocationBaseline(),
        ),
    )
    runs = []
    for track_name, actor_track, model in track_specs:
        suite = generator.generate(config, actor_evidence_track=actor_track)
        bound_cases = tuple(
            case.bind_prediction(model.predict(case.model_input)) for case in suite.cases
        )
        report = ShiftAttributionEvaluator().evaluate(bound_cases)
        runs.append(
            {
                "track": track_name,
                "suite_id": str(suite.suite_id),
                "suite_content_sha256": suite.suite_content_sha256,
                "baseline_model_version": model.model_version,
                "case_results": [
                    {
                        "case_id": case.case_id,
                        "true_cause": case.true_cause.value,
                        "predicted_cause": case.prediction.predicted_cause.value,
                    }
                    for case in bound_cases
                ],
                "report": report.model_dump(mode="json"),
            }
        )

    no_actor_suite = generator.generate(config)
    cases_by_cause = {case.evaluator_truth.true_cause: case for case in no_actor_suite.cases}
    observational_equivalence = (
        cases_by_cause[ShiftCause.ACTOR_MIXTURE].model_input.shifted_run.visible_content_sha256
        == cases_by_cause[
            ShiftCause.OWNER_HABIT_REGIME
        ].model_input.shifted_run.visible_content_sha256
    )
    output = {
        "scenario_config_sha256": no_actor_suite.scenario_config_sha256,
        "generator_version": no_actor_suite.generator_version,
        "actor_vs_owner_habit_visible_logs_identical": observational_equivalence,
        "track_runs": runs,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
