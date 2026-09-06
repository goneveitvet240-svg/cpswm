"""Two-round adversarial audit for the v0.5 Structure Two action report.

Round one attacks forged-but-complete positive and derived-output paths.
Round two attacks type, plan, identity, and state-boundary substitutions.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from cpswm.contracts import ProjectTwoDatasetSplit
from cpswm.system.evaluation_operations import (
    D0SyntheticOracleReplayAdapter,
    ProjectTwoActionBenchmarkReport,
    ProjectTwoActionBenchmarkV02,
    ProjectTwoActionMethod,
    RouteADevelopmentUtilityContract,
    current_route_a_development_utility_contract,
)
from cpswm.system.evaluation_operations.project_two_action_benchmark import _locations, _Prediction


@pytest.fixture(scope="module")
def report_payload() -> dict[str, Any]:
    dataset = D0SyntheticOracleReplayAdapter(
        validation_seeds=(101,), test_seeds=(211,), max_steps_per_episode=8
    ).build()
    return ProjectTwoActionBenchmarkV02().run(dataset).model_dump(mode="python")


def _payload(report_payload: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(report_payload)


# --- round one: forged positive and derived-output paths ----------------------


def test_round1_rejects_a_forged_but_complete_paper_positive(
    report_payload: dict[str, Any],
) -> None:
    payload = _payload(report_payload)
    payload["primary_utility_definition"]["unresolved_contract_fields"] = ()
    payload["unresolved_utility_contract_fields"] = ()
    payload["route_a_primary_utility_evaluated"] = True
    verdict = payload["scientific_verdict"]
    verdict.update(
        {
            "route_a_primary_utility_evaluated": True,
            "superiority_authorized": True,
            "paper_claim_allowed": True,
            "primary_utility_comparison": (
                "cumulative_action_regret is strictly better than the best reference "
                "independently_tuned_recency"
            ),
            "secondary_regressions": (),
            "blocking_reasons": (),
            "unresolved_contract_fields": (),
            "summary": "route-A superiority authorized",
        }
    )
    payload["paper_level_gate_failures"] = ()
    payload["superiority_supported"] = True
    payload["scientific_status"] = "paper-level superiority supported"

    with pytest.raises(ValidationError):
        ProjectTwoActionBenchmarkReport.model_validate(payload)


def test_round1_rejects_misleading_comparison_and_erased_gates(
    report_payload: dict[str, Any],
) -> None:
    misleading = _payload(report_payload)
    best = next(
        method
        for method in ProjectTwoActionMethod
        if method.value in misleading["scientific_verdict"]["primary_utility_comparison"]
    )
    misleading["scientific_verdict"]["primary_utility_comparison"] = (
        f"cumulative_action_regret is strictly better than the best reference {best.value}"
    )
    with pytest.raises(ValidationError, match="not derived from report metrics and gates"):
        ProjectTwoActionBenchmarkReport.model_validate(misleading)

    erased = _payload(report_payload)
    erased["paper_level_gate_failures"] = ()
    with pytest.raises(ValidationError, match="paper-level gates were erased"):
        ProjectTwoActionBenchmarkReport.model_validate(erased)


def test_round1_rejects_unresolved_split_brain_and_duplicate_aggregates(
    report_payload: dict[str, Any],
) -> None:
    split_brain = _payload(report_payload)
    split_brain["unresolved_utility_contract_fields"] = ()
    split_brain["route_a_primary_utility_evaluated"] = True
    with pytest.raises(ValidationError, match="disagree on unresolved utility fields"):
        ProjectTwoActionBenchmarkReport.model_validate(split_brain)

    duplicate = _payload(report_payload)
    duplicate["aggregate_metrics"] = (
        *duplicate["aggregate_metrics"],
        deepcopy(duplicate["aggregate_metrics"][0]),
    )
    with pytest.raises(ValidationError, match="identities must be unique"):
        ProjectTwoActionBenchmarkReport.model_validate(duplicate)


def test_round1_rejects_validation_selection_substitution(
    report_payload: dict[str, Any],
) -> None:
    payload = _payload(report_payload)
    tuning = payload["tuning"][0]
    assert tuning["selected_parameters"] != tuning["parameter_space"][-1]
    tuning["selected_parameters"] = deepcopy(tuning["parameter_space"][-1])
    with pytest.raises(ValidationError, match="not the validation primary-utility optimum"):
        ProjectTwoActionBenchmarkReport.model_validate(payload)


# A marker used by the second audit round; it must never become a valid method
# or evidence identifier merely because it has UUID shape.
ATTACKER_UUID = uuid4()


# --- round two: type, plan, identity, and state-boundary substitutions ---------


@pytest.mark.parametrize(
    "mutation",
    (
        "omit_baseline_fairness",
        "aggregate_fidelity_substitution",
        "duplicate_case_row",
        "tuning_validation_id_substitution",
        "erase_visible_hash",
    ),
)
def test_round2_rejects_identity_coverage_and_fidelity_substitution(
    report_payload: dict[str, Any], mutation: str
) -> None:
    payload = _payload(report_payload)
    if mutation == "omit_baseline_fairness":
        payload["baseline_fairness"] = payload["baseline_fairness"][:-1]
    elif mutation == "aggregate_fidelity_substitution":
        payload["aggregate_metrics"][0]["fidelity"] = "oracle_upper_bound"
    elif mutation == "duplicate_case_row":
        payload["case_metrics"] = (
            *payload["case_metrics"],
            deepcopy(payload["case_metrics"][0]),
        )
    elif mutation == "tuning_validation_id_substitution":
        payload["tuning"][0]["validation_episode_ids"] = (ATTACKER_UUID,)
    else:
        payload["fairness_visible_hashes"].pop(next(iter(payload["fairness_visible_hashes"])))
    with pytest.raises(ValidationError):
        ProjectTwoActionBenchmarkReport.model_validate(payload)


def test_round2_rejects_bool_as_a_numeric_utility_weight() -> None:
    payload = current_route_a_development_utility_contract().model_dump(mode="python")
    payload["put_back_weight"] = True
    with pytest.raises(ValidationError):
        RouteADevelopmentUtilityContract.model_validate(payload)


class _BadState:
    revision_calls = 0
    project_one_requests = 0
    project_one_applications = 0
    rejected_feedback = 0
    unnecessary_revisions = 0
    project_one_rejections = 0

    def __init__(self, prediction: _Prediction) -> None:
        self.prediction = prediction

    def observe(self, _step: object) -> None:
        return None

    def predict(self) -> _Prediction:
        return self.prediction

    def feedback(self, _step: object) -> None:
        return None


@pytest.mark.parametrize(
    "attack",
    (
        "duplicate_search_plan",
        "unregistered_search_plan",
        "unregistered_put_back",
        "invalid_unknown_probability",
        "empty_search_plan",
    ),
)
def test_round2_rejects_invalid_method_action_state(attack: str) -> None:
    dataset = D0SyntheticOracleReplayAdapter(
        validation_seeds=(101,), test_seeds=(211,), max_steps_per_episode=8
    ).build()
    episode = dataset.visible_episodes(ProjectTwoDatasetSplit.TEST)[0]
    location = _locations(episode)[0]
    prediction = {
        "duplicate_search_plan": _Prediction(location, (location, location), 0.0),
        "unregistered_search_plan": _Prediction(location, (ATTACKER_UUID,), 0.0),
        "unregistered_put_back": _Prediction(ATTACKER_UUID, (location,), 0.0),
        "invalid_unknown_probability": _Prediction(location, (location,), 2.0),
        "empty_search_plan": _Prediction(location, (), 0.0),
    }[attack]
    with pytest.raises((TypeError, ValueError)):
        ProjectTwoActionBenchmarkV02().evaluate_custom_state(
            dataset, episode, _BadState(prediction)
        )
