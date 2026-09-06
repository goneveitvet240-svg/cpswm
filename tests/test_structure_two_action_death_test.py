"""Tests for the structure-two action-level matched death test.

This pins the *benchmark itself*: deterministic generation, truth isolation,
fair baselines, and the scientific-status gate that only grants
``strictly better`` when the new method beats every baseline on put-back error.
"""

from __future__ import annotations

from itertools import permutations

import pytest

from cpswm.system.evaluation_operations import (
    ActionBaselineMethod,
    ActionTaskType,
    StructureTwoActionDeathTest,
    StructureTwoActionScenarioGenerator,
)


def test_v02_calls_real_feedback_revision_loop_and_project_one_interface(monkeypatch):
    """The v0.2 full arm cannot regress to the stand-in owner write gate."""
    import cpswm.system.evaluation_operations.project_two_action_benchmark as module
    from cpswm.system.counterfactual_event_hypergraph import ProjectTwoFeedbackRevisionLoop
    from cpswm.system.evaluation_operations import (
        D0SyntheticOracleReplayAdapter,
        ProjectTwoActionBenchmarkV02,
        ProjectTwoActionMethod,
    )

    calls = {"feedback": 0, "project_one": 0}
    original_ingest = ProjectTwoFeedbackRevisionLoop.ingest_feedback
    original_apply = module.apply_project_one_request

    def ingest(self, **kwargs):
        calls["feedback"] += 1
        return original_ingest(self, **kwargs)

    def apply(request, loop):
        calls["project_one"] += 1
        # Project two can only submit a typed request; it receives no direct
        # access to the project's internal statistic dictionaries here.
        from cpswm.system.counterfactual_event_hypergraph import ProjectOneStatRequest

        assert isinstance(request, ProjectOneStatRequest)
        return original_apply(request, loop)

    monkeypatch.setattr(ProjectTwoFeedbackRevisionLoop, "ingest_feedback", ingest)
    monkeypatch.setattr(module, "apply_project_one_request", apply)
    dataset = D0SyntheticOracleReplayAdapter(
        validation_seeds=(101,), test_seeds=(211,), max_steps_per_episode=8
    ).build()
    report = ProjectTwoActionBenchmarkV02().run(dataset)
    full = next(
        item for item in report.case_metrics if item.method is ProjectTwoActionMethod.PROJECT_TWO
    )
    assert calls["feedback"] > 0
    assert calls["project_one"] > 0
    assert full.full_feedback_revision_calls > 0
    assert full.project_one_stat_applications > 0


def test_v02_fairness_split_tuning_and_baseline_fidelity():
    from cpswm.system.evaluation_operations import (
        BenchmarkFidelity,
        D0SyntheticOracleReplayAdapter,
        ProjectTwoActionBenchmarkV02,
        ProjectTwoActionMethod,
    )

    dataset = D0SyntheticOracleReplayAdapter(
        validation_seeds=(101,), test_seeds=(211,), max_steps_per_episode=8
    ).build()
    report = ProjectTwoActionBenchmarkV02().run(dataset)
    assert set(report.validation_episode_ids).isdisjoint(report.sealed_test_episode_ids)
    assert {item.search_budget for item in report.tuning} == {3}
    assert {item.selection_metric for item in report.tuning} == {"cumulative_action_regret"}
    assert all(not item.test_episode_ids_seen for item in report.tuning)
    assert len({item.visible_input_hash for item in report.case_metrics}) == 1
    methods = {item.method for item in report.case_metrics}
    assert methods == set(ProjectTwoActionMethod)
    fidelity = {(item.method, item.fidelity) for item in report.aggregate_metrics}
    assert (
        ProjectTwoActionMethod.AMG_MATCHED,
        BenchmarkFidelity.MATCHED_REPLAY_ADAPTER,
    ) in fidelity
    assert (ProjectTwoActionMethod.O_STAR, BenchmarkFidelity.MATCHED_REPLAY_ADAPTER) in fidelity
    assert (ProjectTwoActionMethod.DYNAMEM, BenchmarkFidelity.MATCHED_REPLAY_ADAPTER) in fidelity
    assert (ProjectTwoActionMethod.STAR, BenchmarkFidelity.MATCHED_REPLAY_ADAPTER) in fidelity
    assert any(
        item.metric == "persistent_owner_mode_error_rate" for item in report.aggregate_metrics
    )
    assert not report.superiority_supported
    assert report.paper_level_gate_failures
    adapters = {item.method: item for item in report.baseline_fairness}
    assert adapters[ProjectTwoActionMethod.AMG_MATCHED].missing_faithful_inputs
    assert not adapters[ProjectTwoActionMethod.AMG_MATCHED].qualifies_for_paper_superiority
    assert adapters[ProjectTwoActionMethod.DYNAMEM].missing_faithful_inputs
    assert not adapters[ProjectTwoActionMethod.DYNAMEM].qualifies_for_paper_superiority


def test_v02_evaluator_truth_never_enters_method_input(monkeypatch):
    from cpswm.system.evaluation_operations import (
        D0SyntheticOracleReplayAdapter,
        ProjectTwoActionBenchmarkV02,
    )

    original = ProjectTwoActionBenchmarkV02._method

    def guarded(self, episode, method, params):
        payload = episode.model_dump(mode="json")
        assert "true_actor" not in repr(payload)
        assert "true_location" not in repr(payload)
        assert not hasattr(episode, "truth_by_step")
        return original(self, episode, method, params)

    monkeypatch.setattr(ProjectTwoActionBenchmarkV02, "_method", guarded)
    dataset = D0SyntheticOracleReplayAdapter(
        validation_seeds=(101,), test_seeds=(211,), max_steps_per_episode=5
    ).build()
    ProjectTwoActionBenchmarkV02().run(dataset)


def test_corrected_report_is_byte_stable_with_a_fixed_dataset_seal() -> None:
    from cpswm.system.evaluation_operations import (
        D0SyntheticOracleReplayAdapter,
        ProjectTwoActionBenchmarkV02,
    )

    def render() -> str:
        dataset = D0SyntheticOracleReplayAdapter(
            validation_seeds=(101,),
            test_seeds=(211,),
            max_steps_per_episode=8,
            sealed_secret="project-two-corrected-report-determinism-test",
        ).build()
        return ProjectTwoActionBenchmarkV02().run(dataset).model_dump_json(indent=2)

    assert render() == render()


def test_v02_success_and_failure_feedback_both_flow_through_full_loop(monkeypatch):
    from cpswm.contracts import RobotActionOutcome
    from cpswm.system.counterfactual_event_hypergraph import ProjectTwoFeedbackRevisionLoop
    from cpswm.system.evaluation_operations import (
        D0SyntheticOracleReplayAdapter,
        ProjectTwoActionBenchmarkV02,
    )

    observed_success_probabilities = []
    original = ProjectTwoFeedbackRevisionLoop.ingest_feedback

    def capture(self, **kwargs):
        feedback = kwargs["feedback"]
        observed_success_probabilities.append(
            feedback.outcome_distribution.get(RobotActionOutcome.SUCCESS, 0.0)
        )
        return original(self, **kwargs)

    monkeypatch.setattr(ProjectTwoFeedbackRevisionLoop, "ingest_feedback", capture)
    dataset = D0SyntheticOracleReplayAdapter(
        validation_seeds=(101,), test_seeds=(211,), max_steps_per_episode=8
    ).build()
    ProjectTwoActionBenchmarkV02().run(dataset)
    assert any(value > 0.5 for value in observed_success_probabilities)
    assert any(value <= 0.5 for value in observed_success_probabilities)


ALL_METHODS = (
    ActionBaselineMethod.AMG_2012,
    ActionBaselineMethod.O_STAR,
    ActionBaselineMethod.DYNAMEM,
    ActionBaselineMethod.STAR,
    ActionBaselineMethod.PCHMP_CCRR_RGRC,
)


def test_generation_is_deterministic():
    generator = StructureTwoActionScenarioGenerator()
    first = generator.generate(7)
    second = generator.generate(7)
    assert first.visible.case_id == second.visible.case_id
    assert first.visible.days == second.visible.days
    assert first.truth_by_day == second.truth_by_day


def test_sealed_evaluator_uuids_cannot_be_inverted_to_seed():
    """P0-3: with a private evaluator secret, the adversarial seed oracle cannot
    recover the generating seed from the visible UUIDs."""

    from cpswm.system.evaluation_operations.structure_two_action_death_test import (
        adversarial_seed_oracle,
        new_sealed_secret,
    )

    generator = StructureTwoActionScenarioGenerator(sealed_secret=new_sealed_secret())
    case = generator.generate(7)
    assert adversarial_seed_oracle(case.visible, max_seed=999) is None


def test_public_uuid_mapping_would_have_leaked_the_seed():
    """P0-3 control: the old public uuid5 mapping is invertible, which is why
    sealed generation exists.  This pins the attack, not the benchmark."""

    from cpswm.system.evaluation_operations.structure_two_action_death_test import (
        _public_deterministic_uuid,
        adversarial_seed_oracle,
    )

    leaked = _public_deterministic_uuid(7, "object")
    # A visible payload whose object id follows the public mapping is inverted.
    generator = StructureTwoActionScenarioGenerator()
    case = generator.generate(1)
    visible = case.visible.model_copy(update={"object_instance_id": leaked})
    assert adversarial_seed_oracle(visible, max_seed=999) == 7


def test_truth_is_not_exposed_on_model_inputs():
    case = StructureTwoActionScenarioGenerator().generate(1)
    # The visible slice structurally excludes evaluator truth.
    assert not hasattr(case.visible, "truth_by_day")
    for obs in case.visible.days:
        # Robot-visible observations carry no evaluator truth fields.
        assert not hasattr(obs, "true_owner_habit_location")
        assert not hasattr(obs, "true_actor")


def test_report_covers_every_method_and_case():
    report = StructureTwoActionDeathTest().run(seeds=(1, 2, 3))
    methods = {report.method for report in report.method_reports}
    assert methods == set(ALL_METHODS)
    assert len(report.case_results) == 3 * 32 * len(ALL_METHODS)


def test_report_is_a_put_back_only_diagnostic_not_a_scientific_verdict():
    """The old status string could read as "strictly better"; this one cannot."""

    report = StructureTwoActionDeathTest().run(seeds=(1, 2, 3, 4, 5))
    diagnostic = report.legacy_diagnostic
    assert diagnostic.diagnostic_id == "legacy_put_back_only_diagnostic"
    assert diagnostic.paper_claim_allowed is False
    assert diagnostic.route_a_primary_utility_evaluated is False
    assert diagnostic.comparison_scope == "put_back_error_rate_only"
    assert diagnostic.primary_utility_metric == "cumulative_action_regret"
    assert diagnostic.unresolved_contract_fields
    assert report.scientific_status.startswith("legacy_put_back_only_diagnostic: ")
    assert diagnostic.put_back_comparison in {
        "new method lower put-back error than every baseline",
        "new method ties the best baseline on put-back error",
        "new method higher put-back error than the best baseline",
        "new method not run",
        "no baselines run",
    }
    # No phrasing anywhere in the report may read as a settled scientific win.
    assert "strictly better" not in report.model_dump_json()


def test_new_method_is_location_tuple_order_invariant():
    """Tuple-order invariance: permuting the locations tuple must not change
    the new method's predictions (no ``locations[0]/[1]`` hard-coding)."""

    from cpswm.system.evaluation_operations.structure_two_action_death_test import (
        _PchmpCcrrRgrcMethod,
    )

    generator = StructureTwoActionScenarioGenerator()
    base = generator.generate(1)
    permuted_locations = (
        base.visible.locations[2],
        base.visible.locations[0],
        base.visible.locations[3],
        base.visible.locations[1],
    )
    permuted = base.model_copy(
        update={"visible": base.visible.model_copy(update={"locations": permuted_locations})}
    )

    first = _PchmpCcrrRgrcMethod(base.visible)
    second = _PchmpCcrrRgrcMethod(permuted.visible)
    for obs in base.visible.days:
        first.observe(obs)
        second.observe(obs)
        assert first.predict(ActionTaskType.PUT_BACK) == second.predict(ActionTaskType.PUT_BACK)
        assert first.predict(ActionTaskType.SEARCH) == second.predict(ActionTaskType.SEARCH)


def test_new_method_uses_all_three_operators_end_to_end():
    """The new method must actually route through PCHMP, CF-BOCPD, and CCRR.

    A guest-attributed placement must never write the owner habit; an
    owner-attributed placement under a non-unresolved regime decision must.
    """

    case = StructureTwoActionScenarioGenerator().generate(1)
    from cpswm.system.evaluation_operations.structure_two_action_death_test import (
        _PchmpCcrrRgrcMethod,
    )

    method = _PchmpCcrrRgrcMethod(case.visible)
    saw_owner_write = False
    saw_guest_write_to_owner = False
    for obs in case.visible.days:
        if obs.after is None:
            continue
        before_counts = dict(method.state.regimes.get(method.state.active_regime_id, {}))
        method.observe(obs)
        after_counts = method.state.regimes.get(method.state.active_regime_id, {})
        truth = case.truth_by_day[obs.day]
        if truth.true_actor == "guest":
            # The owner's active regime must not gain a write on a guest day.
            if after_counts != before_counts and truth.true_location_after in after_counts:
                saw_guest_write_to_owner = True
        else:
            if after_counts != before_counts:
                saw_owner_write = True
    assert saw_owner_write
    assert not saw_guest_write_to_owner


def test_dynamem_is_label_permutation_equivariant_after_first_observation():
    """P1: relabelling location UUIDs (not just reordering the tuple) must
    covariantly relabel the baselines' predictions once they have observed.

    DynaMem is the cleanest case: its prediction is a single tracked location
    with no argmax tie-break and no delayed initialization.  The other
    baselines carry a single-point fallback / tie-break that cannot be both
    tuple-order invariant and label-permutation equivariant (documented
    trade-off), so they are covered only by the tuple-order test.
    """

    from uuid import uuid4

    from cpswm.system.evaluation_operations.structure_two_action_death_test import (
        _DynaMemMethod,
    )

    case = StructureTwoActionScenarioGenerator().generate(1)
    rename = {loc: uuid4() for loc in case.visible.locations}

    def relabel_obs(obs):
        if obs.after is None:
            return obs
        before = obs.before.model_copy(
            update={"detected_location_id": rename[obs.before.detected_location_id]}
        )
        after = obs.after.model_copy(
            update={"detected_location_id": rename[obs.after.detected_location_id]}
        )
        return obs.model_copy(update={"before": before, "after": after})

    rel_visible = case.visible.model_copy(
        update={
            "locations": tuple(rename[loc] for loc in case.visible.locations),
            "days": tuple(relabel_obs(obs) for obs in case.visible.days),
        }
    )

    first = _DynaMemMethod(case.visible)
    second = _DynaMemMethod(rel_visible)
    seen = False
    for obs in case.visible.days:
        first.observe(obs)
        second.observe(relabel_obs(obs))
        if obs.after is not None:
            seen = True
        if not seen:
            # The "no information" fallback is a single point and cannot be
            # label-permutation equivariant; compare only after observing.
            continue
        for task in (ActionTaskType.PUT_BACK, ActionTaskType.SEARCH):
            p1 = first.predict(task)
            p2 = second.predict(task)
            assert rename.get(p1, p1) == p2, (
                f"DynaMem is not label-permutation equivariant on day {obs.day} for {task.value}"
            )


# --- search-utility correction: minimal counterexamples ------------------------
#
# Every test below first states what the withdrawn ``@0.1`` cost model did, then
# pins the corrected behaviour.  ALL_METHODS covers AMG, O-STaR, DynaMem, STAR
# and the project-two (PCHMP x CCRR x RGRC) arm.


#: A *test* price.  ``frozen_protocol_reference=None`` marks it as a development
#: fixture: it produces numbers, and it authorizes no claim.
def _test_search_contract():
    from cpswm.system.evaluation_operations import SearchUtilityContract

    return SearchUtilityContract(
        contract_id="structure-two-action-death-test@search-utility-test-fixture",
        frozen_protocol_reference=None,
        inspection_cost_per_container=1.0,
        unfound_target_penalty=7.0,
        seconds_per_container_inspection=5.0,
    )


def _permuted(case, order=(2, 0, 3, 1)):
    locations = tuple(case.visible.locations[index] for index in order)
    return case.model_copy(
        update={"visible": case.visible.model_copy(update={"locations": locations})}
    )


def _relabelled(case, rename):
    def relabel_obs(obs):
        if obs.after is None or obs.before is None:
            return obs
        before = obs.before.model_copy(
            update={"detected_location_id": rename[obs.before.detected_location_id]}
        )
        after = obs.after.model_copy(
            update={"detected_location_id": rename[obs.after.detected_location_id]}
        )
        return obs.model_copy(update={"before": before, "after": after})

    visible = case.visible.model_copy(
        update={
            "locations": tuple(rename[loc] for loc in case.visible.locations),
            "days": tuple(relabel_obs(obs) for obs in case.visible.days),
        }
    )
    truth = {
        day: item.model_copy(
            update={
                "true_location_after": rename[item.true_location_after],
                "true_owner_habit_location": rename[item.true_owner_habit_location],
            }
        )
        for day, item in case.truth_by_day.items()
    }
    return case.model_copy(update={"visible": visible, "truth_by_day": truth})


def test_withdrawn_v0_1_cost_moves_from_one_to_four_under_a_location_permutation():
    """The defect itself: same prediction, different cost, because of tuple order.

    AMG and DynaMem answer SEARCH with the last observed location.  The withdrawn
    cost model ignored that answer and walked ``list(locations)``, so moving the
    true location to the end of an unordered registry turned a cost of 1 into a
    cost of 4 without any belief changing.
    """

    from cpswm.system.evaluation_operations import withdrawn_v0_1_search_cost
    from cpswm.system.evaluation_operations.structure_two_action_death_test import (
        _AMGMethod,
        _DynaMemMethod,
    )

    case = StructureTwoActionScenarioGenerator().generate(1)
    locations = case.visible.locations
    for factory in (_AMGMethod, _DynaMemMethod):
        method = factory(case.visible)
        moved_costs = set()
        checked = 0
        for obs in case.visible.days:
            method.observe(obs)
            target = case.truth_by_day[obs.day].true_location_after
            others = tuple(item for item in locations if item != target)
            first = (target, *others)
            last = (*others, target)
            if withdrawn_v0_1_search_cost(method, target, first) == 1:
                moved_costs.add(withdrawn_v0_1_search_cost(method, target, last))
                checked += 1
        assert checked > 0
        assert moved_costs == {len(locations)} == {4}


def test_withdrawn_v0_1_cost_model_scored_a_plan_no_method_ever_emitted():
    """Second half of the defect: the scored itinerary was not anyone's answer."""

    from cpswm.system.evaluation_operations import withdrawn_v0_1_search_cost

    case = StructureTwoActionScenarioGenerator().generate(1)
    locations = case.visible.locations
    for name in ALL_METHODS:
        from cpswm.system.evaluation_operations.structure_two_action_death_test import (
            _METHOD_FACTORIES,
        )

        method = _METHOD_FACTORIES[name](case.visible)
        disagreements = 0
        for obs in case.visible.days:
            method.observe(obs)
            answer = method.predict(ActionTaskType.SEARCH)
            # The withdrawn model charges 1 only when *its* first container is
            # the target, so scoring the method's own answer as the target and
            # getting more than 1 back means it scored a different itinerary.
            if withdrawn_v0_1_search_cost(method, answer, locations) != 1:
                disagreements += 1
        assert disagreements > 0, f"{name} unexpectedly agreed with the withdrawn cost model"


def test_every_method_registers_a_plan_that_matches_its_own_search_answer():
    """One plan, one answer: the evaluator never guesses a strategy again."""

    from cpswm.system.evaluation_operations.structure_two_action_death_test import (
        _METHOD_FACTORIES,
    )

    case = StructureTwoActionScenarioGenerator().generate(2)
    for name in ALL_METHODS:
        method = _METHOD_FACTORIES[name](case.visible)
        for obs in case.visible.days:
            method.observe(obs)
            plan = method.search_plan()
            assert plan.method_id == name.value
            assert set(plan.registered_locations) == set(case.visible.locations)
            assert plan.first_choice == method.predict(ActionTaskType.SEARCH)


def test_single_candidate_plans_separate_inspection_found_and_failure():
    """A one-container method is scored as: one inspection, found or not, penalty."""

    from cpswm.system.evaluation_operations import SearchPlanKind

    contract = _test_search_contract()
    report = StructureTwoActionDeathTest().run(seeds=(1,), search_utility_contract=contract)
    for result in report.case_results:
        assert result.search_plan_kind is SearchPlanKind.SINGLE_CANDIDATE
        assert result.search_plan_length == 1
        assert result.inspected_container_count == 1
        assert result.search_path_length == 1
        assert result.search_target_found is result.search_correct
        # A wrong single-point search is never charged a flat 1.
        assert result.search_cost == (1.0 if result.search_correct else 8.0)
        assert result.search_time_seconds == 5.0
    assert any(not result.search_correct for result in report.case_results)


def test_search_cost_is_unresolved_and_absent_without_a_registered_price():
    from cpswm.system.evaluation_operations import (
        SEARCH_UTILITY_CONTRACT_UNRESOLVED,
        SearchUtilityStatus,
    )

    report = StructureTwoActionDeathTest().run(seeds=(1,))
    assert report.search_utility_status is SearchUtilityStatus.UNRESOLVED
    assert report.search_utility_status.value == SEARCH_UTILITY_CONTRACT_UNRESOLVED
    assert report.search_utility_contract_id is None
    for method_report in report.method_reports:
        assert method_report.mean_search_cost is None
        assert method_report.mean_search_time_seconds is None
        assert "search_cost" in method_report.search_unresolved_fields
        # Dimensions that need no price stay reported.
        assert method_report.mean_inspected_container_count == 1.0
    for result in report.case_results:
        assert result.search_cost is None


def test_a_forged_search_plan_is_rejected_by_the_evaluator():
    """A method cannot claim another arm's identity or another household's shelves."""

    from uuid import uuid4

    from cpswm.system.evaluation_operations import SearchPlan
    from cpswm.system.evaluation_operations.structure_two_action_death_test import (
        StructureTwoActionDeathTest as Runner,
    )

    case = StructureTwoActionScenarioGenerator().generate(1)
    locations = case.visible.locations
    impostor = SearchPlan.build(
        method_id=ActionBaselineMethod.DYNAMEM.value,
        registered_locations=locations,
        visit_order=(locations[0],),
    )
    with pytest.raises(ValueError, match="claims method"):
        Runner._verify_plan(impostor, ActionBaselineMethod.AMG_2012, case.visible)

    foreign = tuple(uuid4() for _ in locations)
    outsider = SearchPlan.build(
        method_id=ActionBaselineMethod.AMG_2012.value,
        registered_locations=foreign,
        visit_order=(foreign[0],),
    )
    with pytest.raises(ValueError, match="different location set"):
        Runner._verify_plan(outsider, ActionBaselineMethod.AMG_2012, case.visible)


def test_per_day_and_aggregate_search_metrics_survive_a_location_permutation():
    """Permuting an unordered registry changes no belief, so it may change no metric."""

    generator = StructureTwoActionScenarioGenerator()
    contract = _test_search_contract()
    base = generator.generate(1)
    runner = StructureTwoActionDeathTest(generator)

    original = runner.run_cases((base,), search_utility_contract=contract)
    permuted = runner.run_cases((_permuted(base),), search_utility_contract=contract)

    for left, right in zip(original.case_results, permuted.case_results, strict=True):
        assert left == right
    for left, right in zip(original.method_reports, permuted.method_reports, strict=True):
        assert left.search_error_rate == right.search_error_rate
        assert left.mean_search_cost == right.mean_search_cost
        assert left.mean_inspected_container_count == right.mean_inspected_container_count
        assert left == right


@pytest.mark.parametrize("seed", (1, 2, 3, 4, 5))
def test_full_priced_report_is_invariant_to_every_location_tuple_order(seed):
    """Exhaust the full 4! registry order space instead of sampling one shuffle."""

    from cpswm.system.evaluation_operations import NON_SEMANTIC_REPORT_FIELDS

    generator = StructureTwoActionScenarioGenerator()
    runner = StructureTwoActionDeathTest(generator)
    base = generator.generate(seed)
    expected = runner.run_cases(
        (base,), search_utility_contract=_test_search_contract()
    ).model_dump(mode="json")
    for order in permutations(range(len(base.visible.locations))):
        actual = runner.run_cases(
            (_permuted(base, order),),
            search_utility_contract=_test_search_contract(),
        ).model_dump(mode="json")
        differing = {key for key in expected if expected[key] != actual[key]}
        assert differing <= set(NON_SEMANTIC_REPORT_FIELDS), (seed, order, differing)


def test_report_rejects_forged_but_complete_metric_rewrite():
    """Derived summaries cannot be edited independently of the retained plan and target."""

    from pydantic import ValidationError

    from cpswm.system.evaluation_operations import StructureTwoActionDeathTestReport

    report = StructureTwoActionDeathTest().run(
        seeds=(1,), search_utility_contract=_test_search_contract()
    )
    payload = report.model_dump(mode="python")
    first = dict(payload["case_results"][0])
    first["search_correct"] = not first["search_correct"]
    payload["case_results"] = (first, *payload["case_results"][1:])
    # Also forge the visible aggregate so the artifact looks internally complete
    # to a validator that checks only top-level status and contract identity.
    forged_method = dict(payload["method_reports"][0])
    forged_method["search_error_rate"] = 0.0
    forged_method["total_search_errors"] = 0
    payload["method_reports"] = (forged_method, *payload["method_reports"][1:])
    with pytest.raises(ValidationError, match="search plan"):
        StructureTwoActionDeathTestReport.model_validate(payload)


def test_report_rejects_forged_location_tuple_digest() -> None:
    from pydantic import ValidationError

    from cpswm.system.evaluation_operations import StructureTwoActionDeathTestReport

    report = StructureTwoActionDeathTest().run(seeds=(1,))
    payload = report.model_dump(mode="python")
    payload["location_tuple_digest"] = "0" * 64
    with pytest.raises(ValidationError, match="not derived from retained raw inputs"):
        StructureTwoActionDeathTestReport.model_validate(payload)


def test_report_rejects_generator_protocol_substitution() -> None:
    from pydantic import ValidationError

    from cpswm.system.evaluation_operations import StructureTwoActionDeathTestReport

    report = StructureTwoActionDeathTest().run(seeds=(1,))
    payload = report.model_dump(mode="python")
    payload["generator_version"] = "substituted-generator@9"
    with pytest.raises(ValidationError, match="generator protocol substitution"):
        StructureTwoActionDeathTestReport.model_validate(payload)


def test_full_report_survives_a_permutation_except_registered_non_semantic_fields():
    from cpswm.system.evaluation_operations import NON_SEMANTIC_REPORT_FIELDS

    generator = StructureTwoActionScenarioGenerator()
    runner = StructureTwoActionDeathTest(generator)
    base = generator.generate(3)
    original = runner.run_cases((base,)).model_dump(mode="json")
    permuted = runner.run_cases((_permuted(base),)).model_dump(mode="json")

    differing = {key for key in original if original[key] != permuted[key]}
    assert differing <= set(NON_SEMANTIC_REPORT_FIELDS)
    assert original["location_tuple_digest"] != permuted["location_tuple_digest"]


def test_search_outputs_are_label_permutation_equivariant_after_first_observation():
    """Renaming every location UUID must relabel the plan and change no metric."""

    from uuid import uuid4

    generator = StructureTwoActionScenarioGenerator()
    runner = StructureTwoActionDeathTest(generator)
    contract = _test_search_contract()
    base = generator.generate(1)
    rename = {loc: uuid4() for loc in base.visible.locations}
    relabelled = _relabelled(base, rename)

    original = runner.run_cases((base,), search_utility_contract=contract)
    renamed = runner.run_cases((relabelled,), search_utility_contract=contract)

    # Before a method has seen anything it answers with the shared "no
    # information" fallback, a single point that cannot covary with an arbitrary
    # relabelling (documented in the module docstring).  Compare from the first
    # observed day onward; under selective observation that is not day 0.
    first_observed_day = min(obs.day for obs in base.visible.days if obs.after is not None)
    compared = 0
    for left, right in zip(original.case_results, renamed.case_results, strict=True):
        if left.day < first_observed_day:
            continue
        compared += 1
        assert left.method is right.method
        assert left.search_correct == right.search_correct
        assert left.search_cost == right.search_cost
        assert left.search_target_found == right.search_target_found
        assert left.inspected_container_count == right.inspected_container_count
        assert left.search_path_length == right.search_path_length
    assert compared > 0

    from cpswm.system.evaluation_operations.structure_two_action_death_test import (
        _METHOD_FACTORIES,
    )

    for name in ALL_METHODS:
        left_method = _METHOD_FACTORIES[name](base.visible)
        right_method = _METHOD_FACTORIES[name](relabelled.visible)
        observed = False
        for left_obs, right_obs in zip(base.visible.days, relabelled.visible.days, strict=True):
            left_method.observe(left_obs)
            right_method.observe(right_obs)
            observed = observed or left_obs.after is not None
            if not observed:
                continue
            mapped = tuple(rename[item] for item in left_method.search_plan().visit_order)
            assert mapped == right_method.search_plan().visit_order


def test_predictions_are_unchanged_by_the_correction():
    """The fix repriced search; it did not move any method's answer."""

    from cpswm.system.evaluation_operations.structure_two_action_death_test import (
        _METHOD_FACTORIES,
    )

    generator = StructureTwoActionScenarioGenerator()
    base = generator.generate(1)
    permuted = _permuted(base)
    for name in ALL_METHODS:
        left = _METHOD_FACTORIES[name](base.visible)
        right = _METHOD_FACTORIES[name](permuted.visible)
        for obs in base.visible.days:
            left.observe(obs)
            right.observe(obs)
            for task in (ActionTaskType.PUT_BACK, ActionTaskType.SEARCH):
                assert left.predict(task) == right.predict(task)


# --- v0.5 benchmark: one plan, one development utility, fail-closed paper gate ---


def _v04_report():
    from cpswm.system.evaluation_operations import (
        D0SyntheticOracleReplayAdapter,
        ProjectTwoActionBenchmarkV02,
    )

    dataset = D0SyntheticOracleReplayAdapter(
        validation_seeds=(101,), test_seeds=(211,), max_steps_per_episode=8
    ).build()
    return ProjectTwoActionBenchmarkV02().run(dataset)


def test_v04_search_correctness_and_path_cost_share_one_plan():
    """A first-choice hit costs exactly one container; a miss always costs more.

    This identity is what the withdrawn v0.1 model broke: it scored correctness
    against the method's answer and cost against a different ranking, so a
    "correct" search could cost 4 and a wrong one could cost 1.
    """

    report = _v04_report()
    for item in report.case_metrics:
        if item.search_error_rate == 0.0:
            assert item.mean_search_path_cost == 1.0
        else:
            assert item.mean_search_path_cost > 1.0
        assert item.search_success_rate == 1.0 - item.search_error_rate
        # Three names, one quantity -- registered as such rather than presented
        # as three independent measurements.
        assert item.mean_search_path_cost == item.mean_search_path_length
        assert item.mean_search_path_cost == item.mean_search_cost
        assert item.mean_search_time_seconds == 5.0 * item.mean_search_path_cost
        assert item.cumulative_action_regret == pytest.approx(
            item.cumulative_put_back_regret + item.cumulative_search_regret
        )


def test_v04_declares_its_unregistered_search_constants():
    report = _v04_report()
    joined = " ".join(report.unregistered_search_metric_assumptions)
    assert "5.0 s per inspected container" in joined
    assert "not a registered real-world cost" in joined
    assert "three names for one quantity" in joined


def test_v04_tracks_the_route_a_primary_utility_and_fails_closed_on_it():
    from cpswm.system.evaluation_operations import ROUTE_A_PRIMARY_UTILITY_CONTRACT_UNRESOLVED

    report = _v04_report()
    definition = report.primary_utility_definition
    assert definition.primary_utility_metric == "cumulative_action_regret"
    assert definition.optimization_direction == "minimize"
    assert definition.implemented_component_terms == (
        "put_back_error_count (0/1 per step, weight 1)",
        "normalized_extra_inspection_regret (0..1 per step, weight 1)",
    )
    assert definition.implemented_unit == (
        "dimensionless task-regret units per episode (D0 development only)"
    )
    assert definition.development_contract_id == report.development_utility_contract.contract_id
    assert report.development_utility_contract.paper_claim_allowed is False
    assert definition.development_primary_utility_evaluated is True
    assert report.development_primary_utility_evaluated is True
    assert definition.oracle_reference_method == "oracle_upper_bound"
    assert definition.oracle_reference_value == 0.0
    assert "cumulative_action_regret.component_weights" in definition.unresolved_contract_fields

    assert report.route_a_primary_utility_evaluated is False
    assert report.unresolved_utility_contract_fields == definition.unresolved_contract_fields
    assert report.superiority_supported is False
    assert not report.scientific_verdict.superiority_authorized
    assert not report.scientific_verdict.paper_claim_allowed
    assert any(
        item.startswith(ROUTE_A_PRIMARY_UTILITY_CONTRACT_UNRESOLVED)
        for item in report.scientific_verdict.blocking_reasons
    )
    assert any(
        ROUTE_A_PRIMARY_UTILITY_CONTRACT_UNRESOLVED in item
        for item in report.paper_level_gate_failures
    )
    for guardrail in ("owner_contamination", "recovery_latency", "full_rerun_equivalence"):
        assert f"HARD_GUARDRAIL_NOT_MEASURED:{guardrail}" in (
            report.scientific_verdict.blocking_reasons
        )


def test_v05_strongest_neighbor_comparison_includes_matched_adapters() -> None:
    from cpswm.system.evaluation_operations import ProjectTwoActionMethod

    report = _v04_report()
    verdict = report.scientific_verdict
    assert ProjectTwoActionMethod.AMG_MATCHED.value in verdict.reference_methods
    assert ProjectTwoActionMethod.O_STAR.value in verdict.reference_methods
    assert ProjectTwoActionMethod.DYNAMEM.value in verdict.reference_methods
    assert ProjectTwoActionMethod.STAR.value in verdict.reference_methods
    assert ProjectTwoActionMethod.ORACLE.value not in verdict.reference_methods
    best = min(
        (
            item
            for item in report.aggregate_metrics
            if item.method
            not in {ProjectTwoActionMethod.PROJECT_TWO, ProjectTwoActionMethod.ORACLE}
            and item.metric == "cumulative_action_regret"
        ),
        key=lambda item: (item.value, item.method.value),
    )
    assert best.method.value in verdict.primary_utility_comparison
    assert {
        "PRIMARY_UTILITY_NOT_STRICTLY_BETTER",
        "PRIMARY_UTILITY_WORSE",
    } & set(verdict.blocking_reasons)


def test_v06_project_two_search_space_is_equal_budget_and_uses_only_reversible_reads() -> None:
    from cpswm.system.evaluation_operations import ProjectTwoActionMethod
    from cpswm.system.evaluation_operations.project_two_action_benchmark import PARAMETER_SPACE

    space = PARAMETER_SPACE[ProjectTwoActionMethod.PROJECT_TWO]
    assert len(space) == 3
    assert {item["readout"] for item in space} == {
        "latest_owner_event",
        "dual_timescale_reversible",
    }
    assert all(item["owner_threshold"] == 0.4 for item in space)
    assert all(item.get("hybrid_alpha_weight", 0.0) == 0.0 for item in space)


def test_v04_report_cannot_assert_a_superiority_its_verdict_withholds():
    from pydantic import ValidationError

    from cpswm.system.evaluation_operations import ProjectTwoActionBenchmarkReport

    payload = _v04_report().model_dump(mode="python")
    with pytest.raises(ValidationError, match="route-A verdict withholds it"):
        ProjectTwoActionBenchmarkReport.model_validate({**payload, "superiority_supported": True})


def test_v05_report_rejects_metric_and_reference_semantic_tampering() -> None:
    from pydantic import ValidationError

    from cpswm.system.evaluation_operations import ProjectTwoActionBenchmarkReport

    payload = _v04_report().model_dump(mode="python")
    case_metrics = list(payload["case_metrics"])
    forged_case = dict(case_metrics[0])
    forged_case["cumulative_action_regret"] += 1.0
    case_metrics[0] = forged_case
    with pytest.raises(ValidationError, match="registered components"):
        ProjectTwoActionBenchmarkReport.model_validate({**payload, "case_metrics": case_metrics})

    verdict = dict(payload["scientific_verdict"])
    verdict["reference_methods"] = tuple(verdict["reference_methods"][:-1])
    with pytest.raises(ValidationError, match="omits or substitutes"):
        ProjectTwoActionBenchmarkReport.model_validate({**payload, "scientific_verdict": verdict})

    with pytest.raises(ValidationError):
        ProjectTwoActionBenchmarkReport.model_validate(
            {**payload, "benchmark_version": "project-two-action-benchmark@0.4-corrected-interface"}
        )


# --- adversarial round two: version, hash and metric substitution ---------------


def test_a_corrected_report_cannot_be_relabelled_as_the_withdrawn_protocol():
    """Neither direction of a version swap is available.

    Downgrading the label would reinstate a withdrawn ``mean_search_cost``;
    upgrading an old artifact's label would launder withdrawn numbers into
    corrected ones.
    """

    from pydantic import ValidationError

    from cpswm.system.evaluation_operations import (
        PROTOCOL_VERSION,
        SUPERSEDED_PROTOCOL_VERSION,
        StructureTwoActionDeathTestReport,
    )

    assert PROTOCOL_VERSION != SUPERSEDED_PROTOCOL_VERSION
    payload = StructureTwoActionDeathTest().run(seeds=(1,)).model_dump(mode="python")
    assert payload["protocol_version"] == PROTOCOL_VERSION
    assert payload["superseded_protocol_version"] == SUPERSEDED_PROTOCOL_VERSION

    with pytest.raises(ValidationError, match="it cannot carry"):
        StructureTwoActionDeathTestReport.model_validate(
            {**payload, "protocol_version": SUPERSEDED_PROTOCOL_VERSION}
        )
    with pytest.raises(ValidationError, match="superseded protocol is fixed"):
        StructureTwoActionDeathTestReport.model_validate(
            {**payload, "superseded_protocol_version": PROTOCOL_VERSION}
        )


def test_a_resolved_search_utility_must_name_the_contract_that_priced_it():
    from pydantic import ValidationError

    from cpswm.system.evaluation_operations import StructureTwoActionDeathTestReport

    payload = StructureTwoActionDeathTest().run(seeds=(1,)).model_dump(mode="python")
    with pytest.raises(ValidationError, match="name the contract that priced it"):
        StructureTwoActionDeathTestReport.model_validate(
            {**payload, "search_utility_status": "resolved"}
        )


def test_a_secondary_metric_cannot_be_promoted_into_the_primary_utility_slot():
    from pydantic import ValidationError

    from cpswm.system.evaluation_operations import ProjectTwoActionBenchmarkReport

    payload = _v04_report().model_dump(mode="python")
    swapped = dict(payload["primary_utility_definition"])
    swapped["primary_utility_metric"] = "mean_search_path_cost"
    with pytest.raises(ValidationError, match="cannot be promoted"):
        ProjectTwoActionBenchmarkReport.model_validate(
            {**payload, "primary_utility_definition": swapped}
        )

    flipped = dict(payload["primary_utility_definition"])
    flipped["optimization_direction"] = "maximize"
    with pytest.raises(ValidationError, match="minimizes its primary utility"):
        ProjectTwoActionBenchmarkReport.model_validate(
            {**payload, "primary_utility_definition": flipped}
        )


def test_a_verdict_cannot_be_forced_open_while_a_blocking_reason_stands():
    from pydantic import ValidationError

    from cpswm.system.evaluation_operations import ScientificVerdict

    payload = _v04_report().scientific_verdict.model_dump(mode="python")
    assert payload["blocking_reasons"]
    with pytest.raises(ValidationError, match="while a blocking reason stands"):
        ScientificVerdict.model_validate({**payload, "superiority_authorized": True})
    with pytest.raises(ValidationError, match="requires the route-A primary utility"):
        ScientificVerdict.model_validate(
            {**payload, "superiority_authorized": True, "blocking_reasons": ()}
        )
    with pytest.raises(ValidationError, match="requires authorized superiority"):
        ScientificVerdict.model_validate({**payload, "paper_claim_allowed": True})


def test_an_empty_search_plan_is_not_a_plan():
    from pydantic import ValidationError

    from cpswm.system.evaluation_operations import SearchPlan

    case = StructureTwoActionScenarioGenerator().generate(1)
    with pytest.raises(ValidationError):
        SearchPlan.build(
            method_id=ActionBaselineMethod.AMG_2012.value,
            registered_locations=case.visible.locations,
            visit_order=(),
        )
