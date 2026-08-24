"""Tests for the structure-two action-level matched death test.

This pins the *benchmark itself*: deterministic generation, truth isolation,
fair baselines, and the scientific-status gate that only grants
``strictly better`` when the new method beats every baseline on put-back error.
"""

from __future__ import annotations

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
    assert all(not item.test_episode_ids_seen for item in report.tuning)
    assert len({item.visible_input_hash for item in report.case_metrics}) == 1
    methods = {item.method for item in report.case_metrics}
    assert methods == set(ProjectTwoActionMethod)
    fidelity = {(item.method, item.fidelity) for item in report.aggregate_metrics}
    assert (ProjectTwoActionMethod.AMG_MATCHED, BenchmarkFidelity.FAITHFUL_MATCHED) in fidelity
    assert (ProjectTwoActionMethod.O_STAR, BenchmarkFidelity.MATCHED_REPLAY_ADAPTER) in fidelity
    assert (ProjectTwoActionMethod.DYNAMEM, BenchmarkFidelity.MATCHED_REPLAY_ADAPTER) in fidelity
    assert (ProjectTwoActionMethod.STAR, BenchmarkFidelity.MATCHED_REPLAY_ADAPTER) in fidelity
    assert not report.superiority_supported
    assert report.paper_level_gate_failures
    adapters = {item.method: item for item in report.baseline_fairness}
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


def test_scientific_status_is_one_of_the_expected_values():
    report = StructureTwoActionDeathTest().run(seeds=(1, 2, 3, 4, 5))
    assert report.scientific_status in {
        "new method strictly better on put-back error",
        "new method ties the best baseline on put-back error",
        "new method worse than the best baseline on put-back error",
    }


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
