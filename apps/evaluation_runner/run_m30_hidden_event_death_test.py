"""Run the held-out multi-seed M30 hidden-event matched death test."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from cpswm.system.evaluation_operations import (  # noqa: E402
    HiddenEventFamily,
    HiddenEventMatchedDeathTest,
    HiddenEventMethod,
    M30HiddenEventSuiteGenerator,
)


def run() -> dict[str, object]:
    suite = M30HiddenEventSuiteGenerator().generate()
    report = HiddenEventMatchedDeathTest().run(suite)
    family_diagnosis = {
        method.value: {
            family.value: {
                "case_count": len(family_results),
                "final_exact_chain_rate": sum(
                    result.final_exact_chain is True for result in family_results
                )
                / len(family_results),
                "truth_set_coverage": sum(
                    result.truth_in_final_emitted_set is True for result in family_results
                )
                / len(family_results),
                "responsible_actor_accuracy": sum(
                    result.final_responsible_actor_correct is True for result in family_results
                )
                / len(family_results),
            }
            for family in HiddenEventFamily
            if (
                family_results := [
                    result
                    for result in report.test_results
                    if result.method == method and result.family == family and result.supported
                ]
            )
        }
        for method in (
            HiddenEventMethod.CHEH,
            HiddenEventMethod.ORRER,
            HiddenEventMethod.DAMEN_HOGG_2012_MATCHED,
        )
    }
    return {
        "suite_generator_version": report.suite_generator_version,
        "validation_case_count": report.validation_case_count,
        "test_case_count": report.test_case_count,
        "test_family_counts": dict(
            sorted(
                Counter(
                    case.model_input.family.value
                    for case in suite.cases
                    if case.model_input.split.value == "test"
                ).items()
            )
        ),
        "tuning": [item.model_dump(mode="json") for item in report.tuning],
        "method_reports": [item.model_dump(mode="json") for item in report.method_reports],
        "family_diagnosis": family_diagnosis,
        "interpretation": {
            "matched_final_comparison": (
                "stateless baselines receive the same cumulative evidence and are rerun"
            ),
            "revision_capability": (
                "only append-only revisions count as revision; a full rerun does not"
            ),
            "unknown_actor_track": (
                "source-faithful 2021/2012 adaptations remain separate; ORRER is also compared "
                "with a deliberately strengthened open-world AMG adaptation"
            ),
            "reactivation": (
                "held-out tuning selected zero pruning; adversarial prune-then-correct behavior "
                "is covered by tests/test_orrer_event_revision.py"
            ),
        },
        "scientific_status": report.scientific_status,
    }


def main() -> None:
    print(json.dumps(run(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
