from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from cpswm.contracts import ActorEvidenceTrack
from cpswm.system.synthetic_routines import SyntheticRoutineGenerator
from cpswm.system.world_model_simulator import SymbolicWorldModelSimulator
from cpswm.system.evaluation_operations import (
    D0FactorFingerprints,
    D0FactorName,
    D0ShiftCaseTruth,
    D0ShiftScenarioConfig,
    D0ShiftScenarioGenerator,
    LoggedPolicyActorLocationBaseline,
    LoggedPolicyThenLocationBaseline,
    ShiftAttributionEvaluator,
    ShiftCause,
    ShiftCausePrediction,
)


def suite_by_cause():
    suite = D0ShiftScenarioGenerator().generate()
    return suite, {
        case.evaluator_truth.true_cause: case for case in suite.cases
    }


def test_checked_in_d0_config_replays_the_frozen_suite():
    repository_root = Path(__file__).resolve().parents[1]
    config = D0ShiftScenarioConfig.model_validate_json(
        (
            repository_root
            / "benchmarks"
            / "d0_shift_attribution"
            / "d0_scenario_config_v0.1.json"
        ).read_text(encoding="utf-8")
    )

    suite = D0ShiftScenarioGenerator().generate(config)

    assert str(suite.suite_id) == "17fdae62-dead-5b0a-ad99-ec8ef0fa9265"
    assert (
        suite.suite_content_sha256
        == "5e20bbf40cebc89c8c83a015200bddd2e9e552e3968df6ebf5e5cc6834015bf6"
    )
    assert (
        suite.scenario_config_sha256
        == "3264f03eb7047a9683576d2bca5c8c9ac97d46b98d45d7df72460347829e6c9a"
    )


def test_d0_suite_is_deterministic_and_changes_exactly_one_bound_factor():
    first = D0ShiftScenarioGenerator().generate()
    replay = D0ShiftScenarioGenerator().generate()

    assert first == replay
    assert {case.evaluator_truth.true_cause for case in first.cases} == {
        ShiftCause.OBSERVATION_POLICY,
        ShiftCause.ACTOR_MIXTURE,
        ShiftCause.OWNER_HABIT_REGIME,
    }
    assert {
        case.evaluator_truth.true_cause: case.evaluator_truth.changed_factors
        for case in first.cases
    } == {
        ShiftCause.OBSERVATION_POLICY: (D0FactorName.OBSERVATION_PROCESS,),
        ShiftCause.ACTOR_MIXTURE: (D0FactorName.ACTOR_MIXTURE,),
        ShiftCause.OWNER_HABIT_REGIME: (D0FactorName.OWNER_HABIT_REGIME,),
    }


def test_d0_observation_shift_has_an_identical_pre_period_and_post_policy_change():
    _, cases = suite_by_cause()
    model_input = cases[ShiftCause.OBSERVATION_POLICY].model_input

    control_pre = tuple(
        item
        for item in model_input.control_run.observation_opportunities
        if item.opportunity_time < model_input.change_time
    )
    shifted_pre = tuple(
        item
        for item in model_input.shifted_run.observation_opportunities
        if item.opportunity_time < model_input.change_time
    )
    assert control_pre == shifted_pre

    control_post = tuple(
        item.selection_probability
        for item in model_input.control_run.observation_opportunities
        if item.opportunity_time >= model_input.change_time
    )
    shifted_post = tuple(
        item.selection_probability
        for item in model_input.shifted_run.observation_opportunities
        if item.opportunity_time >= model_input.change_time
    )
    assert control_post == (1.0, 1.0, 1.0, 1.0)
    assert shifted_post == (0.25, 0.25, 0.25, 0.25)


def test_d0_paired_randomness_reuses_draws_independently_of_policy_identity():
    config = D0ShiftScenarioConfig(
        control_selection_probability=0.55,
        shifted_selection_probability=0.25,
        duration_days=100,
        change_day=50,
    )
    generator = D0ShiftScenarioGenerator()
    plan = SyntheticRoutineGenerator().generate(generator._routine_config(config))
    first = generator._policy(
        config, policy_id="paired-policy-a", selection_probability=0.55
    )
    renamed = first.model_copy(update={"policy_id": "paired-policy-b"})
    high = generator._policy(
        config, policy_id="paired-policy-high", selection_probability=0.75
    )

    run_a, run_b, run_high = SymbolicWorldModelSimulator().run_paired(
        plan,
        (first, renamed, high),
        paired_noise_seed=config.paired_noise_seed,
    )

    selected_a = tuple(item.selected for item in run_a.observation_opportunities)
    selected_b = tuple(item.selected for item in run_b.observation_opportunities)
    selected_high = tuple(item.selected for item in run_high.observation_opportunities)
    assert selected_a == selected_b
    assert all(not low or high for low, high in zip(selected_a, selected_high, strict=True))
    assert tuple(
        item.metadata.record_id for item in run_a.observation_opportunities
    ) == tuple(item.metadata.record_id for item in run_b.observation_opportunities)


def test_d0_pairs_have_one_shared_session_and_trace_without_splice_shortcut():
    suite = D0ShiftScenarioGenerator().generate()

    for case in suite.cases:
        records = (
            *case.model_input.control_run.observation_opportunities,
            *case.model_input.control_run.detection_results,
            *case.model_input.shifted_run.observation_opportunities,
            *case.model_input.shifted_run.detection_results,
        )
        assert len({item.metadata.session_id for item in records}) == 1
        assert len({item.metadata.trace_id for item in records}) == 1


def test_d0_actor_and_owner_habit_changes_are_observationally_equivalent_without_people():
    _, cases = suite_by_cause()
    actor_case = cases[ShiftCause.ACTOR_MIXTURE]
    habit_case = cases[ShiftCause.OWNER_HABIT_REGIME]

    assert actor_case.model_input.shifted_run == habit_case.model_input.shifted_run
    assert (
        actor_case.model_input.shifted_run.visible_content_sha256
        == habit_case.model_input.shifted_run.visible_content_sha256
    )
    assert actor_case.evaluator_truth.true_cause != habit_case.evaluator_truth.true_cause


def test_candidate_input_excludes_truth_cause_actor_and_regime_labels():
    suite = D0ShiftScenarioGenerator().generate()

    for case in suite.cases:
        serialized = case.model_input.model_dump_json()
        for forbidden in (
            "true_cause",
            "evaluator_truth",
            "factor_fingerprint",
            "ground_truth",
            "actor_gt",
            "regime_kind",
            "guest_contamination",
            "abrupt_change",
        ):
            assert forbidden not in serialized


def test_logged_policy_location_baseline_exposes_actor_to_habit_leakage():
    suite = D0ShiftScenarioGenerator().generate()
    model = LoggedPolicyThenLocationBaseline()
    bound_cases = tuple(
        case.bind_prediction(model.predict(case.model_input)) for case in suite.cases
    )

    report = ShiftAttributionEvaluator().evaluate(bound_cases)

    assert report.shift_cause_accuracy == pytest.approx(2 / 3)
    assert report.observation_to_habit_leakage == 0.0
    assert report.actor_mixture_to_owner_leakage == 1.0
    assert report.false_owner_habit_change_rate == 0.5
    assert report.non_identifiable_sample_count == 2
    assert report.correct_abstention_rate == 0.0
    assert report.epistemic_decision_accuracy == pytest.approx(1 / 3)


def test_non_identifiable_cases_reward_explicit_abstention_with_proper_scores():
    suite = D0ShiftScenarioGenerator().generate()
    bound_cases = tuple(
        case.bind_prediction(
            ShiftCausePrediction(
                case_id=case.model_input.case_id,
                posterior={
                    (
                        ShiftCause.UNRESOLVED
                        if case.evaluator_truth.identifiability_status.value
                        == "non_identifiable"
                        else case.evaluator_truth.true_cause
                    ): 1.0
                },
                model_version="identifiability-aware-oracle@0.1",
            )
        )
        for case in suite.cases
    )

    report = ShiftAttributionEvaluator().evaluate(bound_cases)

    assert report.shift_cause_accuracy == pytest.approx(1 / 3)
    assert report.epistemic_decision_accuracy == 1.0
    assert report.correct_abstention_rate == 1.0
    assert report.incorrect_abstention_rate == 0.0
    assert report.log_loss == pytest.approx(0.0)
    assert report.brier_score == pytest.approx(0.0)
    assert report.selective_coverage == pytest.approx(1 / 3)
    assert report.selective_risk == 0.0


@pytest.mark.parametrize(
    "track",
    (ActorEvidenceTrack.CONTROLLED_NOISE, ActorEvidenceTrack.ORACLE),
)
def test_actor_evidence_tracks_break_d0_actor_habit_equivalence(track):
    suite = D0ShiftScenarioGenerator().generate(actor_evidence_track=track)
    model = LoggedPolicyActorLocationBaseline()
    bound_cases = tuple(
        case.bind_prediction(model.predict(case.model_input)) for case in suite.cases
    )

    report = ShiftAttributionEvaluator().evaluate(bound_cases)

    assert report.shift_cause_accuracy == 1.0
    assert report.actor_mixture_to_owner_leakage == 0.0
    actor_case = next(
        case
        for case in suite.cases
        if case.evaluator_truth.true_cause == ShiftCause.ACTOR_MIXTURE
    )
    habit_case = next(
        case
        for case in suite.cases
        if case.evaluator_truth.true_cause == ShiftCause.OWNER_HABIT_REGIME
    )
    assert actor_case.model_input.shifted_run == habit_case.model_input.shifted_run
    assert (
        actor_case.model_input.shifted_actor_evidence
        != habit_case.model_input.shifted_actor_evidence
    )


def test_controlled_actor_evidence_is_uncertain_and_gt_free():
    suite = D0ShiftScenarioGenerator().generate(
        actor_evidence_track=ActorEvidenceTrack.CONTROLLED_NOISE
    )

    for case in suite.cases:
        for evidence in (
            *case.model_input.control_actor_evidence,
            *case.model_input.shifted_actor_evidence,
        ):
            assert max(evidence.actor_posterior.values()) == 0.8
            serialized = evidence.model_dump_json()
            assert "true_actor" not in serialized
            assert "actor_gt" not in serialized
            assert "ground_truth" not in serialized


def test_d0_truth_rejects_a_pair_that_changes_multiple_factors():
    suite = D0ShiftScenarioGenerator().generate()
    original = suite.cases[0].evaluator_truth
    shifted = original.shifted_factors.model_copy(
        update={"actor_mixture": "f" * 64}
    )

    with pytest.raises(ValidationError, match="change exactly the factor"):
        D0ShiftCaseTruth(
            case_id=original.case_id,
            true_cause=ShiftCause.OBSERVATION_POLICY,
            control_factors=original.control_factors,
            shifted_factors=shifted,
        )


def test_d0_factor_fingerprints_report_no_change_for_identical_values():
    fingerprints = D0FactorFingerprints(
        observation_process="1" * 64,
        actor_mixture="2" * 64,
        identity_association="3" * 64,
        owner_habit_regime="4" * 64,
        transient_noise="5" * 64,
    )

    assert fingerprints.changed_from(fingerprints) == ()
