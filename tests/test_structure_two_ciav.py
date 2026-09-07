"""Cause-information active verification (CIAV) structure-two closure tests."""

from __future__ import annotations

from dataclasses import fields
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from cpswm.contracts import (
    EvidenceFactorKind,
    EvidenceFactorOperation,
    EvidenceFactorOperator,
    ObservationActionCandidate,
    ObservationActionType,
    ObservationOutcome,
)
from cpswm.world_model.grounded_search import (
    CauseInformationActiveVerificationPlanner,
    CIAVOPCEUObservationLoop,
    OffPolicyOverlapStatus,
    OffPolicyVerificationEvaluator,
    OffPolicyVerificationSample,
    RealizedCIAVObservation,
    StructureTwoCauseBelief,
    VerificationBaselinePolicy,
    VerificationCause,
    select_verification_baseline,
    verification_cause_hypothesis_id,
)
from cpswm.world_model.habits_transitions import (
    CauseSignalFrame,
    ChangeCause,
    JointCauseFactorizedBOCPD,
)


def _belief() -> StructureTwoCauseBelief:
    base = datetime(2026, 8, 25, tzinfo=UTC)
    frames = tuple(
        CauseSignalFrame(
            timestamp=base + timedelta(days=index),
            signals={
                ChangeCause.OBSERVATION: 0.2,
                ChangeCause.ACTOR: 0.2,
                ChangeCause.HABIT: 0.2 if index < 3 else 0.9,
                ChangeCause.NOISE: 0.1,
            },
        )
        for index in range(6)
    )
    snapshot = JointCauseFactorizedBOCPD(beam_width=64).run(frames, warmup_steps=2).snapshots[3]
    return StructureTwoCauseBelief.from_snapshot(
        snapshot,
        identity_switch_probability=0.2,
    )


def _action(*, informative: bool, privacy_cost: float = 0.0) -> ObservationActionCandidate:
    hypotheses = tuple(verification_cause_hypothesis_id(cause) for cause in VerificationCause)
    if informative:
        outcome_likelihoods = {
            cause.value: {
                candidate: 1.0 if candidate == verification_cause_hypothesis_id(cause) else 0.0
                for candidate in hypotheses
            }
            for cause in VerificationCause
        }
    else:
        outcome_likelihoods = {
            "positive": dict.fromkeys(hypotheses, 0.5),
            "negative": dict.fromkeys(hypotheses, 0.5),
        }
    return ObservationActionCandidate(
        action_type=ObservationActionType.MICRO_VERIFY,
        label="factorial cause probe",
        observation_likelihood_model_id="ciav-factorial-outcome@0.1",
        calibration_domain="structure-two-ciav-d0",
        outcome_likelihoods=outcome_likelihoods,
        motion_cost=0.0,
        time_cost=0.0,
        interruption_cost=0.0,
        privacy_cost=privacy_cost,
        safety_cost=0.0,
    )


def _actor_likelihood_table(
    action: ObservationActionCandidate,
    *,
    owner: float = 0.8,
    other: float = 0.2,
) -> dict[str, dict[str, float]]:
    return {
        outcome: {"owner": owner, "guest": other, "unknown_actor": other}
        for outcome in action.outcome_likelihoods
    }


def _terminal_utilities() -> dict[UUID, dict[UUID, float]]:
    hypotheses = tuple(verification_cause_hypothesis_id(cause) for cause in VerificationCause)
    return {
        decision: {hypothesis: 1.0 if decision == hypothesis else 0.0 for hypothesis in hypotheses}
        for decision in hypotheses
    }


def _consolidation_utilities() -> dict[UUID, dict[UUID, float]]:
    hypotheses = tuple(verification_cause_hypothesis_id(cause) for cause in VerificationCause)
    commit, quarantine, retract = uuid4(), uuid4(), uuid4()
    return {
        commit: {
            hypothesis: (
                1.0
                if hypothesis == verification_cause_hypothesis_id(VerificationCause.HABIT)
                else -1.0
            )
            for hypothesis in hypotheses
        },
        quarantine: {hypothesis: 0.2 for hypothesis in hypotheses},
        retract: {
            hypothesis: (
                0.8
                if hypothesis
                in {
                    verification_cause_hypothesis_id(VerificationCause.OBSERVATION),
                    verification_cause_hypothesis_id(VerificationCause.IDENTITY),
                    verification_cause_hypothesis_id(VerificationCause.NOISE),
                }
                else -0.4
            )
            for hypothesis in hypotheses
        },
    }


def test_structure_two_snapshot_exposes_identity_and_unresolved_to_ciav():
    belief = _belief()
    assert set(belief.posterior) == set(VerificationCause)
    assert sum(belief.posterior.values()) == pytest.approx(1.0)
    assert belief.posterior[VerificationCause.IDENTITY] == pytest.approx(0.2)
    assert belief.posterior[VerificationCause.UNRESOLVED] >= 0.0
    assert len(belief.source_snapshot_sha256) == 64


def test_ciav_couples_cause_memory_and_task_utility_under_hard_privacy():
    belief = _belief()
    informative = _action(informative=True)
    uninformative = _action(informative=False)
    privacy_blocked = _action(informative=True, privacy_cost=0.9)
    plan = CauseInformationActiveVerificationPlanner().select(
        belief,
        (uninformative, informative, privacy_blocked),
        consolidation_decision_utilities=_consolidation_utilities(),
        terminal_decision_utilities=_terminal_utilities(),
        privacy_budget=0.2,
    )
    assert plan.should_act
    assert plan.selected_action_id == informative.action_id
    assert privacy_blocked.action_id in plan.blocked_action_ids
    selected = next(item for item in plan.scores if item.action_id == informative.action_id)
    assert selected.expected_cause_information_gain > 0.0
    assert selected.expected_utility_gain > 0.0
    assert selected.expected_consolidation_decision_value_gain is not None
    assert selected.expected_consolidation_decision_value_gain > 0.0


def test_ciav_linear_single_consolidation_decision_has_zero_information_value():
    belief = _belief()
    only_decision = uuid4()
    linear_utility = {
        only_decision: {
            verification_cause_hypothesis_id(cause): float(index)
            for index, cause in enumerate(VerificationCause)
        }
    }
    plan = CauseInformationActiveVerificationPlanner(
        cause_information_weight=0.0,
        task_utility_weight=0.0,
    ).select(
        belief,
        (_action(informative=True),),
        consolidation_decision_utilities=linear_utility,
        terminal_decision_utilities=_terminal_utilities(),
        privacy_budget=1.0,
        minimum_net_value=-1.0,
    )
    assert plan.scores[0].expected_consolidation_decision_value_gain == pytest.approx(0.0)


@pytest.mark.parametrize(
    "policy",
    (
        VerificationBaselinePolicy.ALWAYS_VERIFY,
        VerificationBaselinePolicy.RANDOM,
        VerificationBaselinePolicy.MAX_ENTROPY,
    ),
)
def test_ciav_matched_baselines_share_action_set_and_privacy_gate(policy):
    belief = _belief()
    eligible = _action(informative=True)
    blocked = _action(informative=True, privacy_cost=0.8)
    plan = select_verification_baseline(
        policy,
        belief.as_uuid_prior(),
        (eligible, blocked),
        privacy_budget=0.2,
        random_seed=7,
    )
    assert plan.should_act
    assert plan.selected_action_id == eligible.action_id
    assert blocked.action_id in plan.blocked_action_ids


def test_never_act_baseline_is_explicit():
    plan = select_verification_baseline(
        VerificationBaselinePolicy.NEVER_ACT,
        _belief().as_uuid_prior(),
        (_action(informative=True),),
        privacy_budget=1.0,
    )
    assert not plan.should_act
    assert plan.stop_reason == "never_act_baseline"


def test_ciav_off_policy_evaluation_reports_overlap_and_non_identification():
    action = uuid4()
    samples = (
        OffPolicyVerificationSample(
            logged_action_id=action,
            logged_propensity=0.5,
            target_action_probability=0.5,
            realized_utility=1.0,
        ),
        OffPolicyVerificationSample(
            logged_action_id=action,
            logged_propensity=0.01,
            target_action_probability=0.5,
            realized_utility=0.0,
        ),
    )
    evaluator = OffPolicyVerificationEvaluator()
    weak = evaluator.evaluate(
        samples,
        target_policy_support_complete=True,
        overlap_threshold=0.05,
    )
    assert weak.status is OffPolicyOverlapStatus.WEAK_OVERLAP
    assert weak.ips_utility is not None
    assert weak.self_normalized_ips_utility is not None

    missing = evaluator.evaluate(
        samples,
        target_policy_support_complete=False,
    )
    assert missing.status is OffPolicyOverlapStatus.NON_IDENTIFIABLE
    assert missing.ips_utility is None
    assert missing.self_normalized_ips_utility is None


def test_ciav_selected_action_enters_real_opceu_loop_before_truth_realization():
    action = _action(informative=True)
    household_id, session_id, trace_id, update_id = (uuid4() for _ in range(4))
    object_id, location_id = uuid4(), uuid4()
    callback_observed_opportunity = []

    def realize(opportunity):
        callback_observed_opportunity.append(opportunity)
        assert opportunity.selected
        assert opportunity.observation_action_id == action.action_id
        assert opportunity.likelihood_model_id == action.observation_likelihood_model_id
        return RealizedCIAVObservation(
            outcome_label=next(iter(action.outcome_likelihoods)),
            likelihood_model_id=action.observation_likelihood_model_id,
            detection_outcome=ObservationOutcome.DETECTED,
        )

    runtime = CIAVOPCEUObservationLoop()
    receipt = runtime.execute_selected_action(
        action=action,
        update_id=update_id,
        household_id=household_id,
        session_id=session_id,
        trace_id=trace_id,
        opportunity_time=datetime(2026, 9, 6, tzinfo=UTC),
        object_instance_id=object_id,
        actor_keys=("owner", "guest"),
        actor_prior={"owner": 0.5, "guest": 0.3, "unknown_actor": 0.2},
        actor_likelihoods_by_outcome=_actor_likelihood_table(action),
        location_keys=(str(location_id),),
        expected_detected_location_id=location_id,
        selection_probability=1.0,
        p_visible_given_state=1.0,
        p_detect_given_visible=1.0,
        realizer=realize,
    )

    assert callback_observed_opportunity == [receipt.opportunity]
    assert receipt.detection.observation_opportunity_id == receipt.opportunity.metadata.record_id
    assert receipt.evidence.observation_opportunity == receipt.opportunity
    assert receipt.evidence.actor_posterior == pytest.approx(
        {"owner": 0.8, "guest": 0.12, "unknown_actor": 0.08}
    )
    assert receipt.mechanism.detection == receipt.detection
    assert receipt.produced_factor.operator is EvidenceFactorOperator.OPCEU
    assert receipt.produced_factor.factor_kind is EvidenceFactorKind.OBSERVATION_LIKELIHOOD
    assert receipt.consumed_factor.operator is EvidenceFactorOperator.CIAV
    assert receipt.consumed_factor.operation is EvidenceFactorOperation.CONSUME
    assert receipt.consumed_factor.consumed_as_likelihood
    assert receipt.posterior_summary.factor_kind is EvidenceFactorKind.POSTERIOR_SUMMARY
    assert all(
        item.likelihood_model_id == action.observation_likelihood_model_id
        for item in runtime.trace.receipts
    )
    assert runtime.trace.verify_chain()


@pytest.mark.parametrize(
    ("outcome_label", "model_id", "message"),
    (
        ("unregistered-but-complete", "ciav-factorial-outcome@0.1", "unregistered outcome"),
        (VerificationCause.HABIT.value, "swapped-model@9", "different likelihood model"),
    ),
)
def test_ciav_rejects_forged_complete_realizations(
    outcome_label: str,
    model_id: str,
    message: str,
) -> None:
    action = _action(informative=True)
    object_id, location_id = uuid4(), uuid4()

    def forged(_opportunity):
        return RealizedCIAVObservation(
            outcome_label=outcome_label,
            likelihood_model_id=model_id,
            detection_outcome=ObservationOutcome.DETECTED,
        )

    runtime = CIAVOPCEUObservationLoop()
    with pytest.raises(ValueError, match=message):
        runtime.execute_selected_action(
            action=action,
            update_id=uuid4(),
            household_id=uuid4(),
            session_id=uuid4(),
            trace_id=uuid4(),
            opportunity_time=datetime(2026, 9, 6, tzinfo=UTC),
            object_instance_id=object_id,
            actor_keys=("owner", "guest"),
            actor_prior={"owner": 0.5, "guest": 0.3, "unknown_actor": 0.2},
            actor_likelihoods_by_outcome=_actor_likelihood_table(action),
            location_keys=(str(location_id),),
            expected_detected_location_id=location_id,
            selection_probability=1.0,
            p_visible_given_state=1.0,
            p_detect_given_visible=1.0,
            realizer=forged,
        )
    assert runtime.trace.receipts == ()


def test_ciav_realizer_contract_cannot_author_a_posterior_or_location() -> None:
    field_names = {item.name for item in fields(RealizedCIAVObservation)}
    assert "actor_posterior" not in field_names
    assert "object_posterior" not in field_names
    assert "location_posterior" not in field_names
    assert "detected_location_id" not in field_names
    assert "actor_likelihoods" not in field_names


def test_ciav_rejects_zero_support_actor_likelihood_before_producing_evidence() -> None:
    action = _action(informative=True)
    object_id, location_id = uuid4(), uuid4()

    def impossible(_opportunity):
        return RealizedCIAVObservation(
            outcome_label=next(iter(action.outcome_likelihoods)),
            likelihood_model_id=action.observation_likelihood_model_id,
            detection_outcome=ObservationOutcome.DETECTED,
        )

    runtime = CIAVOPCEUObservationLoop()
    with pytest.raises(ValueError, match="zero probability"):
        runtime.execute_selected_action(
            action=action,
            update_id=uuid4(),
            household_id=uuid4(),
            session_id=uuid4(),
            trace_id=uuid4(),
            opportunity_time=datetime(2026, 9, 6, tzinfo=UTC),
            object_instance_id=object_id,
            actor_keys=("owner", "guest"),
            actor_prior={"owner": 0.5, "guest": 0.3, "unknown_actor": 0.2},
            actor_likelihoods_by_outcome=_actor_likelihood_table(
                action,
                owner=0.0,
                other=0.0,
            ),
            location_keys=(str(location_id),),
            expected_detected_location_id=location_id,
            selection_probability=1.0,
            p_visible_given_state=1.0,
            p_detect_given_visible=1.0,
            realizer=impossible,
        )
    assert runtime.trace.receipts == ()
