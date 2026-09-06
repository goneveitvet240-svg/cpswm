"""Counterexample tests for the one search semantics and the route-A verdict.

Every test here is written as a *minimal counterexample*: it states a concrete
way the withdrawn v0.1 search-utility model, or a put-back-only verdict, could
be talked into an answer it has no right to give.
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from cpswm.system.evaluation_operations.structure_two_search_utility import (
    ROUTE_A_FROZEN_ROUTE_REFERENCE,
    ROUTE_A_HARD_GUARDRAILS,
    ROUTE_A_PRIMARY_UTILITY_CONTRACT_UNRESOLVED,
    ROUTE_A_PRIMARY_UTILITY_METRIC,
    ROUTE_A_UNRESOLVED_UTILITY_FIELDS,
    SEARCH_UTILITY_CONTRACT_UNRESOLVED,
    GuardrailObservation,
    MethodUtilityObservation,
    RouteADevelopmentUtilityContract,
    RouteAPrimaryUtilityDefinition,
    SearchPlan,
    SearchPlanKind,
    SearchScore,
    SearchUtilityContract,
    SearchUtilityStatus,
    SecondaryMetricObservation,
    aggregate_search_scores,
    current_route_a_development_utility_contract,
    evaluate_route_a_superiority,
    normalized_extra_inspection_regret,
    score_search_plan,
)

ROOT = Path(__file__).resolve().parents[1]
DEVELOPMENT_CONTRACT_PATH = (
    ROOT / "configs/project_two_experiments/structure_two_route_a_utility_contract_v0_1.json"
)

LOCATIONS: tuple[UUID, ...] = tuple(
    UUID(int=index) for index in (0x11111111, 0x22222222, 0x33333333, 0x44444444)
)

#: A *test* price, deliberately not a frozen protocol: it may produce numbers,
#: but it can never authorize a paper-level claim.
TEST_CONTRACT = SearchUtilityContract(
    contract_id="structure-two-search-utility@test-fixture",
    frozen_protocol_reference=None,
    inspection_cost_per_container=1.0,
    unfound_target_penalty=7.0,
    seconds_per_container_inspection=5.0,
)


def _plan(visit: tuple[UUID, ...], method_id: str = "method-under-test") -> SearchPlan:
    return SearchPlan.build(
        method_id=method_id,
        registered_locations=LOCATIONS,
        visit_order=visit,
    )


def test_registered_development_contract_matches_code_and_cannot_authorize_a_paper_claim() -> None:
    registered = RouteADevelopmentUtilityContract.model_validate(
        json.loads(DEVELOPMENT_CONTRACT_PATH.read_text(encoding="utf-8"))
    )
    assert registered == current_route_a_development_utility_contract()
    assert registered.selection_metric == ROUTE_A_PRIMARY_UTILITY_METRIC
    assert registered.reference_scope == "all_registered_non_oracle_arms"
    assert registered.paper_claim_allowed is False
    assert "real_task_cost_calibration" in registered.unresolved_paper_bindings


@pytest.mark.parametrize(
    ("inspected", "location_count", "found", "expected"),
    ((1, 4, True, 0.0), (2, 4, True, 1 / 3), (4, 4, True, 1.0), (1, 4, False, 1.0)),
)
def test_development_search_regret_is_normalized_extra_inspection_work(
    inspected: int, location_count: int, found: bool, expected: float
) -> None:
    assert normalized_extra_inspection_regret(
        inspected_container_count=inspected,
        registered_location_count=location_count,
        target_found_in_plan=found,
    ) == pytest.approx(expected)


# --- plan integrity -----------------------------------------------------------


def test_plan_kind_cannot_be_forged() -> None:
    """A single-candidate plan cannot relabel itself as an exhaustive ranking."""

    with pytest.raises(ValidationError, match="contradicts its contents"):
        SearchPlan(
            method_id="liar",
            registered_locations=LOCATIONS,
            visit_order=(LOCATIONS[0],),
            plan_kind=SearchPlanKind.EXHAUSTIVE_RANKING,
        )


def test_plan_rejects_repeated_and_unregistered_containers() -> None:
    with pytest.raises(ValidationError, match="same container twice"):
        _plan((LOCATIONS[0], LOCATIONS[0]))
    with pytest.raises(ValidationError, match="only visit registered locations"):
        _plan((LOCATIONS[0], uuid4()))
    with pytest.raises(ValidationError, match="must be unique"):
        SearchPlan.build(
            method_id="m",
            registered_locations=(LOCATIONS[0], LOCATIONS[0]),
            visit_order=(LOCATIONS[0],),
        )


# --- target first / middle / last / absent ------------------------------------


@pytest.mark.parametrize(
    ("target_index", "expected_inspected"),
    [(0, 1), (1, 2), (3, 4)],
)
def test_cost_follows_the_plan_position_of_the_target(
    target_index: int, expected_inspected: int
) -> None:
    plan = _plan(LOCATIONS)
    score = score_search_plan(plan, LOCATIONS[target_index], TEST_CONTRACT)
    assert score.plan_kind is SearchPlanKind.EXHAUSTIVE_RANKING
    assert score.inspected_container_count == expected_inspected
    assert score.search_path_length == expected_inspected
    assert score.target_found_in_plan
    assert score.first_choice_correct is (target_index == 0)
    assert score.search_cost == float(expected_inspected)
    assert score.search_time_seconds == 5.0 * expected_inspected


def test_target_absent_from_the_plan_pays_every_inspection_plus_the_penalty() -> None:
    plan = _plan((LOCATIONS[0], LOCATIONS[1]))
    score = score_search_plan(plan, LOCATIONS[3], TEST_CONTRACT)
    assert score.plan_kind is SearchPlanKind.PARTIAL_RANKING
    assert not score.target_found_in_plan
    assert score.inspected_container_count == 2
    assert score.search_cost == 2 * 1.0 + 7.0


def test_a_wrong_single_point_search_is_never_charged_a_flat_one() -> None:
    """The exact v0.1 giveaway: a failed one-container search cost 1.

    Under the corrected semantics a method that opens one wrong container pays
    for that inspection *and* owes the failure penalty, so failing cannot be
    cheaper than an honest multi-container search that succeeds.
    """

    wrong = score_search_plan(_plan((LOCATIONS[0],)), LOCATIONS[2], TEST_CONTRACT)
    right = score_search_plan(_plan((LOCATIONS[0],)), LOCATIONS[0], TEST_CONTRACT)
    exhaustive_success = score_search_plan(_plan(LOCATIONS), LOCATIONS[3], TEST_CONTRACT)

    assert wrong.plan_kind is SearchPlanKind.SINGLE_CANDIDATE
    assert not wrong.target_found_in_plan
    assert wrong.inspected_container_count == 1
    assert right.search_cost == 1.0
    assert wrong.search_cost == 8.0
    assert wrong.search_cost is not None and exhaustive_success.search_cost is not None
    assert wrong.search_cost > exhaustive_success.search_cost


# --- fail-closed pricing ------------------------------------------------------


def test_unpriced_search_reports_the_unresolved_marker_and_no_number() -> None:
    score = score_search_plan(_plan((LOCATIONS[0],)), LOCATIONS[2])
    assert score.status is SearchUtilityStatus.UNRESOLVED
    assert score.status.value == SEARCH_UTILITY_CONTRACT_UNRESOLVED
    assert score.search_cost is None
    assert score.search_time_seconds is None
    assert "search_cost" in score.unresolved_fields
    # The dimensions that need no price are still reported.
    assert score.inspected_container_count == 1
    assert score.target_found_in_plan is False


def test_unpriced_time_does_not_silently_become_zero() -> None:
    contract = TEST_CONTRACT.model_copy(update={"seconds_per_container_inspection": None})
    score = score_search_plan(_plan(LOCATIONS), LOCATIONS[1], contract)
    assert score.search_cost == 2.0
    assert score.search_time_seconds is None
    assert "search_time_seconds" in score.unresolved_fields


def test_caller_selected_protocol_reference_never_self_authorizes() -> None:
    """A path string is not independent custody or preregistration evidence."""

    with pytest.raises(ValidationError):
        SearchUtilityContract(
            contract_id="forged-empty-reference",
            frozen_protocol_reference="",
            inspection_cost_per_container=1.0,
            unfound_target_penalty=1.0,
        )
    forged = SearchUtilityContract(
        contract_id="forged-reference",
        frozen_protocol_reference="fake://caller-selected",
        inspection_cost_per_container=1.0,
        unfound_target_penalty=1.0,
    )
    assert not forged.authorizes_paper_claim


def test_resolved_score_rejects_negative_cost_or_missing_contract_identity() -> None:
    base = score_search_plan(_plan((LOCATIONS[0],)), LOCATIONS[0], TEST_CONTRACT)
    payload = base.model_dump(mode="python")
    with pytest.raises(ValidationError):
        type(base).model_validate({**payload, "search_cost": -1.0})
    with pytest.raises(ValidationError, match="must name its pricing contract"):
        type(base).model_validate({**payload, "contract_id": None})


def test_score_rejects_first_inspection_hit_relabelled_as_wrong_first_choice() -> None:
    base = score_search_plan(_plan(LOCATIONS), LOCATIONS[0])
    payload = base.model_dump(mode="python")
    with pytest.raises(ValidationError, match="correct first choice"):
        SearchScore.model_validate({**payload, "first_choice_correct": False})


def test_aggregate_rejects_cross_method_and_cross_contract_poisoning() -> None:
    first = score_search_plan(_plan((LOCATIONS[0],), "method-a"), LOCATIONS[0], TEST_CONTRACT)
    second_contract = TEST_CONTRACT.model_copy(update={"contract_id": "other-contract"})
    second = score_search_plan(_plan((LOCATIONS[0],), "method-a"), LOCATIONS[0], second_contract)
    with pytest.raises(ValueError, match="method identities"):
        aggregate_search_scores("method-b", (first,))
    with pytest.raises(ValueError, match="different contracts"):
        aggregate_search_scores("method-a", (first, second))


def test_aggregate_rejects_empty_evidence() -> None:
    with pytest.raises(ValueError, match="empty set"):
        aggregate_search_scores("method-a", ())


def test_aggregate_never_averages_an_unresolved_cost_into_a_number() -> None:
    scores = tuple(score_search_plan(_plan(LOCATIONS), LOCATIONS[index]) for index in range(4))
    aggregate = aggregate_search_scores("method-under-test", scores)
    assert aggregate.status is SearchUtilityStatus.UNRESOLVED
    assert aggregate.mean_search_cost is None
    assert aggregate.mean_inspected_container_count == pytest.approx(2.5)
    assert aggregate.first_choice_error_rate == pytest.approx(0.75)
    assert aggregate.target_not_found_rate == 0.0


# --- route-A verdict counterexamples ------------------------------------------


def _definition(*, unresolved: tuple[str, ...]) -> RouteAPrimaryUtilityDefinition:
    return RouteAPrimaryUtilityDefinition(
        primary_utility_metric=ROUTE_A_PRIMARY_UTILITY_METRIC,
        optimization_direction="minimize",
        frozen_route_reference=ROUTE_A_FROZEN_ROUTE_REFERENCE,
        implemented_component_terms=("put_back_error_count", "search_first_choice_error_count"),
        implemented_unit="unweighted error-event count per episode",
        oracle_reference_method="oracle_upper_bound",
        oracle_reference_value=0.0,
        unresolved_contract_fields=unresolved,
    )


def _passing_guardrails() -> tuple[GuardrailObservation, ...]:
    return tuple(
        GuardrailObservation(guardrail=name, passed=True) for name in ROUTE_A_HARD_GUARDRAILS
    )


def test_unresolved_utility_contract_blocks_before_any_number_is_compared() -> None:
    verdict = evaluate_route_a_superiority(
        definition=_definition(unresolved=ROUTE_A_UNRESOLVED_UTILITY_FIELDS),
        candidate=MethodUtilityObservation(
            method="project_two", primary_utility=0.0, guardrails=_passing_guardrails()
        ),
        references=(MethodUtilityObservation(method="frequency", primary_utility=99.0),),
    )
    assert not verdict.superiority_authorized
    assert not verdict.route_a_primary_utility_evaluated
    assert not verdict.paper_claim_allowed
    assert any(
        item.startswith(ROUTE_A_PRIMARY_UTILITY_CONTRACT_UNRESOLVED)
        for item in verdict.blocking_reasons
    )


def test_same_put_back_but_worse_search_path_is_not_a_complete_win() -> None:
    """Identical primary utility, longer search: a tie can never read as a win."""

    verdict = evaluate_route_a_superiority(
        definition=_definition(unresolved=()),
        candidate=MethodUtilityObservation(
            method="project_two",
            primary_utility=10.0,
            secondary_metrics=(
                SecondaryMetricObservation(metric="mean_search_path_cost", value=2.4),
            ),
            guardrails=_passing_guardrails(),
        ),
        references=(
            MethodUtilityObservation(
                method="frequency",
                primary_utility=10.0,
                secondary_metrics=(
                    SecondaryMetricObservation(metric="mean_search_path_cost", value=1.1),
                ),
            ),
        ),
    )
    assert not verdict.superiority_authorized
    assert "PRIMARY_UTILITY_NOT_STRICTLY_BETTER" in verdict.blocking_reasons
    assert "SECONDARY_METRIC_REGRESSION" in verdict.blocking_reasons
    assert verdict.secondary_regressions


def test_equal_search_success_with_higher_path_cost_is_not_ignored() -> None:
    verdict = evaluate_route_a_superiority(
        definition=_definition(unresolved=()),
        candidate=MethodUtilityObservation(
            method="project_two",
            primary_utility=1.0,
            secondary_metrics=(
                SecondaryMetricObservation(metric="search_error_rate", value=0.2),
                SecondaryMetricObservation(metric="mean_search_path_cost", value=3.0),
            ),
            guardrails=_passing_guardrails(),
        ),
        references=(
            MethodUtilityObservation(
                method="frequency",
                primary_utility=5.0,
                secondary_metrics=(
                    SecondaryMetricObservation(metric="search_error_rate", value=0.2),
                    SecondaryMetricObservation(metric="mean_search_path_cost", value=1.0),
                ),
            ),
        ),
    )
    assert not verdict.superiority_authorized
    assert verdict.secondary_regressions == ("mean_search_path_cost: 3 vs frequency 1",)
    assert "SECONDARY_METRIC_REGRESSION" in verdict.blocking_reasons


def test_better_primary_utility_cannot_buy_off_a_failed_hard_guardrail() -> None:
    guardrails = (
        GuardrailObservation(guardrail="owner_contamination", passed=False, detail="contaminated"),
        GuardrailObservation(guardrail="recovery_latency", passed=True),
        GuardrailObservation(guardrail="full_rerun_equivalence", passed=True),
    )
    verdict = evaluate_route_a_superiority(
        definition=_definition(unresolved=()),
        candidate=MethodUtilityObservation(
            method="project_two", primary_utility=0.0, guardrails=guardrails
        ),
        references=(MethodUtilityObservation(method="frequency", primary_utility=42.0),),
    )
    assert not verdict.superiority_authorized
    assert "HARD_GUARDRAIL_FAILED:owner_contamination" in verdict.blocking_reasons


def test_an_unmeasured_hard_guardrail_fails_closed_like_a_failed_one() -> None:
    verdict = evaluate_route_a_superiority(
        definition=_definition(unresolved=()),
        candidate=MethodUtilityObservation(method="project_two", primary_utility=0.0),
        references=(MethodUtilityObservation(method="frequency", primary_utility=42.0),),
    )
    assert not verdict.superiority_authorized
    for guardrail in ROUTE_A_HARD_GUARDRAILS:
        assert f"HARD_GUARDRAIL_NOT_MEASURED:{guardrail}" in verdict.blocking_reasons


def test_a_secondary_improvement_alone_never_promotes_the_status() -> None:
    verdict = evaluate_route_a_superiority(
        definition=_definition(unresolved=()),
        candidate=MethodUtilityObservation(
            method="project_two",
            primary_utility=10.0,
            secondary_metrics=(
                SecondaryMetricObservation(metric="mean_search_path_cost", value=1.0),
            ),
            guardrails=_passing_guardrails(),
        ),
        references=(
            MethodUtilityObservation(
                method="frequency",
                primary_utility=10.0,
                secondary_metrics=(
                    SecondaryMetricObservation(metric="mean_search_path_cost", value=9.0),
                ),
            ),
        ),
    )
    assert not verdict.superiority_authorized
    assert verdict.secondary_regressions == ()
    assert "PRIMARY_UTILITY_NOT_STRICTLY_BETTER" in verdict.blocking_reasons


def test_a_clean_strict_win_is_still_reachable() -> None:
    """The gate is fail-closed, not permanently closed."""

    verdict = evaluate_route_a_superiority(
        definition=_definition(unresolved=()),
        candidate=MethodUtilityObservation(
            method="project_two",
            primary_utility=1.0,
            secondary_metrics=(
                SecondaryMetricObservation(metric="mean_search_path_cost", value=1.0),
            ),
            guardrails=_passing_guardrails(),
        ),
        references=(
            MethodUtilityObservation(
                method="frequency",
                primary_utility=4.0,
                secondary_metrics=(
                    SecondaryMetricObservation(metric="mean_search_path_cost", value=2.0),
                ),
            ),
        ),
    )
    assert verdict.superiority_authorized
    assert verdict.paper_claim_allowed
    assert verdict.route_a_primary_utility_evaluated
    assert verdict.blocking_reasons == ()


def test_route_a_definition_rejects_direction_or_metric_substitution() -> None:
    payload = _definition(unresolved=()).model_dump(mode="python")
    with pytest.raises(ValidationError, match="minimizes"):
        RouteAPrimaryUtilityDefinition.model_validate(
            {**payload, "optimization_direction": "maximize"}
        )
    with pytest.raises(ValidationError, match="secondary metric"):
        RouteAPrimaryUtilityDefinition.model_validate(
            {**payload, "primary_utility_metric": "mean_search_path_cost"}
        )
