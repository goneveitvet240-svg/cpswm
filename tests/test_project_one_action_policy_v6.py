from datetime import timedelta
from pathlib import Path

import pytest

from cpswm.system.evaluation_operations.cross_structure_strata_diagnostic import (
    PROJECT_ONE_PARAMS,
    _project_one_strata,
)
from cpswm.system.evaluation_operations.fair_ablation import ProjectOneAblationArmId
from cpswm.system.evaluation_operations.online_shift_attribution import (
    OnlineShiftFamily,
    OnlineShiftSuiteConfig,
    OnlineShiftSuiteGenerator,
)
from cpswm.system.evaluation_operations.project_one_shift_action_death_test import (
    FrozenActionPolicy,
    PrefixOnlinePrediction,
    PrefixPosteriorSnapshot,
    ProjectOneShiftActionDeathTestConfig,
    VerificationEvidence,
    _case_outcome,
    _evaluate_arm,
)
from cpswm.system.evaluation_operations.shift_attribution import ShiftCause

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "benchmarks/project_one_ablation/project_one_shift_action_death_test_v6.json"
JOINT = ProjectOneAblationArmId.JOINT_CAUSE_FACTORIZED_BOCPD


def _policy_v6() -> FrozenActionPolicy:
    return FrozenActionPolicy(
        policy_id="habit-reset-consolidation-policy@6",
        active_verification_enabled=True,
        multi_label_consolidation=True,
    )


def test_v6_preregisters_at_least_152_fresh_test_seeds() -> None:
    config = ProjectOneShiftActionDeathTestConfig.model_validate_json(CONFIG.read_text())
    legacy = set(range(15101, 15201, 2))
    assert config.protocol_version == "project-one-shift-action-death-test@6"
    assert len(config.seed_plan.test_seeds) == 160
    assert len(set(config.seed_plan.test_seeds)) == 160
    assert legacy.isdisjoint(config.seed_plan.test_seeds)

    payload = config.model_dump(mode="json")
    payload["seed_plan"]["test_seeds"] = payload["seed_plan"]["test_seeds"][:151]
    with pytest.raises(ValueError, match="at least 152"):
        ProjectOneShiftActionDeathTestConfig.model_validate(payload)


def test_active_verification_closes_s2_without_weakening_s4_multilabel_gate() -> None:
    strata = _project_one_strata(12)
    policy = _policy_v6()
    s2 = _evaluate_arm(
        JOINT,
        PROJECT_ONE_PARAMS[JOINT],
        strata["s2_actor_confusion_missing_evidence"],
        policy,
        "test",
    )
    s4 = _evaluate_arm(
        JOINT,
        PROJECT_ONE_PARAMS[JOINT],
        strata["s4_observation_policy_plus_habit_change"],
        policy,
        "test",
    )
    assert s2.metrics.missed_consolidation_rate == 0.0
    assert s2.metrics.false_consolidation_rate == 0.0
    assert s4.metrics.missed_consolidation_rate <= 0.25
    assert s4.metrics.false_consolidation_rate == 0.0


def test_negative_active_owner_confirmation_vetoes_consolidation() -> None:
    suite = OnlineShiftSuiteGenerator().generate(
        OnlineShiftSuiteConfig(seeds=(39001, 39007, 39011, 39019, 39023, 39041), duration_days=10)
    )
    case = next(
        item for item in suite.cases if item.evaluator_truth.family == OnlineShiftFamily.OBSERVATION
    )
    truth = case.evaluator_truth.model_copy(update={"intervention_available": True})
    start = case.model_input.observation_stream.start_time
    prediction = PrefixOnlinePrediction(
        case_id=str(truth.case_id),
        model_version="negative-active-confirmation-test@1",
        snapshots=(
            PrefixPosteriorSnapshot(
                as_of_time=start + timedelta(days=4),
                change_time_estimate=start + timedelta(days=3),
                posterior={ShiftCause.OWNER_HABIT_REGIME: 0.99},
                prefix_input_sha256="a" * 64,
                visible_evidence_record_ids=(),
            ),
            PrefixPosteriorSnapshot(
                as_of_time=start + timedelta(days=7),
                change_time_estimate=start + timedelta(days=3),
                posterior={ShiftCause.OWNER_HABIT_REGIME: 0.99},
                prefix_input_sha256="b" * 64,
                visible_evidence_record_ids=(),
            ),
        ),
    )
    evidence = VerificationEvidence(
        predicate_id="active-owner-confirmation-across-observations@1",
        object_instance_id=str(truth.object_id),
        location_id="negative-confirmation-location",
        first_detection_result_id="first",
        second_detection_result_id="second",
        first_evidence_time=start + timedelta(days=5),
        second_evidence_time=start + timedelta(days=6),
        minimum_owner_posterior=0.02,
    )
    outcome = _case_outcome(
        truth,
        prediction,
        _policy_v6(),
        model_input=None,
        stream_start_time=start,
        duration_days=10,
        verification_evidence=evidence,
    )
    assert outcome.verification_issued
    assert not outcome.consolidation_issued
    assert not outcome.false_consolidation
