from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError
from test_structure_two_execution_interface import FailingSink, RecordingSink, _state_fingerprint
from test_structure_two_production_system import _system_and_transition

from cpswm.contracts import (
    ObservationActionCandidate,
    ObservationActionType,
    ObservationOutcome,
)
from cpswm.system.structure_two_adaptive_runtime import (
    EVALUATION_DIRECT_P5_REASON,
    AdaptiveAuthorizationPolicy,
    AdaptiveCIAVRuntimeInput,
    AdaptiveExecutionContext,
    AdaptiveRouterFeatures,
)
from cpswm.system.structure_two_execution import (
    OperatorExecutionDirective,
    StructureTwoExecutionPlan,
    verify_execution_trace,
)
from cpswm.world_model.grounded_search import (
    RealizedCIAVObservation,
    VerificationCause,
    verification_cause_hypothesis_id,
)


def _utilities() -> dict[UUID, dict[UUID, float]]:
    hypotheses = tuple(verification_cause_hypothesis_id(cause) for cause in VerificationCause)
    return {
        decision: {hypothesis: 1.0 if decision == hypothesis else 0.0 for hypothesis in hypotheses}
        for decision in hypotheses
    }


def _adaptive_system_and_transition():
    system, transition = _system_and_transition()
    system.bind_adaptive_authorization_policy(
        AdaptiveAuthorizationPolicy(
            policy_id="test-local-adaptive-policy",
            memory_transition_authorized=True,
            privacy_policy_satisfied=True,
            safety_context_authorized=True,
        )
    )
    return system, transition


def _ciav_input(transition) -> AdaptiveCIAVRuntimeInput:
    hypotheses = tuple(verification_cause_hypothesis_id(cause) for cause in VerificationCause)
    outcome_likelihoods = {
        cause.value: {
            hypothesis: float(hypothesis == verification_cause_hypothesis_id(cause))
            for hypothesis in hypotheses
        }
        for cause in VerificationCause
    }
    action = ObservationActionCandidate(
        action_type=ObservationActionType.MICRO_VERIFY,
        label="production adaptive cause probe",
        observation_likelihood_model_id="production-adaptive-ciav@0.1",
        calibration_domain="structure-two-adaptive-runtime-d0",
        outcome_likelihoods=outcome_likelihoods,
        motion_cost=0.0,
        time_cost=0.0,
        interruption_cost=0.0,
        privacy_cost=0.0,
        safety_cost=0.0,
    )
    outcome = VerificationCause.OBSERVATION.value

    def realize(_opportunity) -> RealizedCIAVObservation:
        return RealizedCIAVObservation(
            outcome_label=outcome,
            likelihood_model_id=action.observation_likelihood_model_id,
            detection_outcome=ObservationOutcome.DETECTED,
        )

    assert transition.after.detection_time is not None
    assert transition.after.detected_location_id is not None
    expected_location = next(
        location
        for location in (
            transition.before.detected_location_id,
            transition.after.detected_location_id,
        )
        if location is not None and location != transition.after.detected_location_id
    )
    return AdaptiveCIAVRuntimeInput(
        actions=(action,),
        consolidation_decision_utilities=_utilities(),
        terminal_decision_utilities=_utilities(),
        privacy_budget=1.0,
        opportunity_time=transition.after.detection_time + timedelta(minutes=1),
        actor_likelihoods_by_outcome={
            label: {"owner": 0.8, "guest": 0.2, "unknown_actor": 0.2}
            for label in outcome_likelihoods
        },
        expected_detected_location_id=expected_location,
        selection_probability=1.0,
        p_visible_given_state=1.0,
        p_detect_given_visible=1.0,
        realizer=realize,
    )


def _features(
    system,
    *,
    step: int,
    route: str,
    pending_count: int = 0,
    oldest_age: int = 0,
) -> AdaptiveRouterFeatures:
    state = system.adaptive_router_state_sha256()
    policy = system._adaptive_authorization_policy
    values = {
        "evidence_conflict_score": 0.05,
        "provenance_dependence_score": 0.05,
        "actor_ambiguity": 0.05,
        "instance_ambiguity": 0.05,
        "unknown_mass": 0.05,
        "action_margin": 0.8,
        "regime_hazard": 0.05,
        "state_staleness": 0,
    }
    if route == "P1_EVENT_ACTOR_LOCAL":
        values["evidence_conflict_score"] = 0.7
    elif route == "P2_REGIME_RECOVERY_LOCAL":
        values["regime_hazard"] = 0.4
    elif route == "P3_ACTIVE_VERIFY":
        values["actor_ambiguity"] = 0.35
        values["action_margin"] = 0.1
    elif route == "P4_EVENT_ACTOR_PLUS_REGIME":
        values["actor_ambiguity"] = 0.7
        values["regime_hazard"] = 0.7
    elif route == "P5_FULL_EAGER":
        values["maximum_debt_flip_bound"] = 0.3
    return AdaptiveRouterFeatures(
        source_state_sha256=state,
        authorization_policy_sha256=policy.content_sha256,
        observation_opportunity_coverage=0.9,
        evidence_conflict_score=values["evidence_conflict_score"],
        provenance_dependence_score=values["provenance_dependence_score"],
        actor_ambiguity=values["actor_ambiguity"],
        instance_ambiguity=values["instance_ambiguity"],
        unknown_mass=values["unknown_mass"],
        action_margin=values["action_margin"],
        pending_long_term_commit=False,
        regime_hazard=values["regime_hazard"],
        outstanding_debt_count=pending_count,
        oldest_debt_age=oldest_age,
        maximum_debt_flip_bound=values.get("maximum_debt_flip_bound", 0.05),
        state_staleness=values["state_staleness"],
        memory_transition_authorized=policy.memory_transition_authorized,
        privacy_policy_satisfied=policy.privacy_policy_satisfied,
        safety_context_authorized=policy.safety_context_authorized,
        feature_extraction_cost_units=0.1,
        feature_source_sha256s=(state, policy.content_sha256),
    )


@pytest.mark.parametrize(
    "path_id",
    (
        "P0_SAFE_DEFERRED",
        "P1_EVENT_ACTOR_LOCAL",
        "P2_REGIME_RECOVERY_LOCAL",
        "P3_ACTIVE_VERIFY",
        "P4_EVENT_ACTOR_PLUS_REGIME",
    ),
)
def test_state_dependent_router_executes_each_non_escalation_path(path_id: str) -> None:
    system, transition = _adaptive_system_and_transition()
    before_core = _state_fingerprint(system)
    context = AdaptiveExecutionContext(
        router_features=_features(system, step=0, route=path_id),
        step_index=0,
        ciav_input=_ciav_input(transition),
    )
    sink = RecordingSink()

    result = system.process_adaptive_transition(
        transition,
        context=context,
        trace_sink=sink,
    )

    assert result.path_selection.selected_path_id == path_id
    assert result.safe_abstained is False
    assert len(sink.traces) == 1
    trace = sink.traces[0]
    verify_execution_trace(trace)
    assert trace.plan.plan_id == path_id
    assert trace.adaptive_legal_path_executed is True
    assert trace.scientific_evidence_authorized is False
    assert trace.cross_system_trace_state_atomicity_established is False
    assert len(trace.receipts[:7]) == 7
    assert all(value >= 0 for value in result.elapsed_ns_by_operator.values())
    if path_id == "P0_SAFE_DEFERRED":
        assert result.primary_result is None
        assert [item.status for item in trace.receipts] == [
            "executed",
            "deferred",
            "executed",
            "executed",
            "executed",
            "executed",
            "deferred",
        ]
        assert len(result.debt_certificates) == 1
        after_core = _state_fingerprint(system)
        for key in (
            "habit",
            "rls",
            "ledger",
            "router_count",
            "snapshot",
            "committed",
            "observed",
            "fast",
            "quarantine",
        ):
            assert after_core[key] == before_core[key]
        assert system.core._corrector.weighted_count == 1
    elif path_id == "P3_ACTIVE_VERIFY":
        assert result.primary_result is not None
        assert result.ciav_plan is not None and result.ciav_plan.should_act
        assert result.ciav_receipt is not None
        assert result.feedback_result is not None
        assert trace.ciav_invoked is True
        assert trace.feedback_observation_acquired is True
        assert len(trace.receipts) == 13
        assert result.debt_certificates == ()
    else:
        assert result.primary_result is not None
        assert result.ciav_receipt is None
        assert trace.receipts[-1].status == "deferred"
        assert len(result.debt_certificates) == 1
        assert result.primary_result.event_revision_id not in system.core._committed_events
        assert any(
            item.revision_id == result.primary_result.event_revision_id
            for item in system.core._quarantined_events
        )


def test_expired_p0_debt_forces_p5_and_settles_the_exact_deferred_transition() -> None:
    system, transition = _adaptive_system_and_transition()
    ciav_input = _ciav_input(transition)
    first = AdaptiveExecutionContext(
        router_features=_features(system, step=0, route="P0_SAFE_DEFERRED"),
        step_index=0,
        ciav_input=ciav_input,
    )
    system.process_adaptive_transition(transition, context=first, trace_sink=RecordingSink())
    pending = system.pending_adaptive_debts()
    assert len(pending) == 1
    debt_ledger = system._adaptive_debt_ledger
    debt_entry = debt_ledger[pending[0].debt_id]
    execution_lock = system._execution_lock
    origin_execution_lock = debt_entry.origin_core_checkpoint["execution_lock"]

    sink = RecordingSink()
    result = system.replay_adaptive_debt(
        pending[0].debt_id,
        step_index=20,
        ciav_input=ciav_input,
        trace_sink=sink,
    )

    assert result.path_selection.selected_path_id == "P5_FULL_EAGER"
    assert result.primary_result is not None
    assert result.ciav_plan is not None
    assert sink.traces[0].all_seven_operators_invoked is True
    assert sink.traces[0].replayed_debt_certificates == pending
    assert system.pending_adaptive_debts() == ()
    assert system._adaptive_debt_ledger is debt_ledger
    assert debt_ledger[pending[0].debt_id] is debt_entry
    assert system._execution_lock is execution_lock
    assert debt_entry.origin_core_checkpoint["execution_lock"] is origin_execution_lock


def test_evaluation_only_direct_p5_runs_the_real_full_eager_path_without_router_drift() -> None:
    routed_system, routed_transition = _adaptive_system_and_transition()
    routed_context = AdaptiveExecutionContext(
        router_features=_features(routed_system, step=0, route="P0_SAFE_DEFERRED"),
        step_index=0,
        ciav_input=_ciav_input(routed_transition),
    )
    routed_result = routed_system.process_adaptive_transition(
        routed_transition,
        context=routed_context,
        trace_sink=RecordingSink(),
    )
    assert routed_result.path_selection.selected_path_id == "P0_SAFE_DEFERRED"

    system, transition = _adaptive_system_and_transition()
    context = AdaptiveExecutionContext(
        router_features=_features(system, step=0, route="P0_SAFE_DEFERRED"),
        step_index=0,
        ciav_input=_ciav_input(transition),
    )
    sink = RecordingSink()

    result = system.process_evaluation_direct_p5_transition(
        transition,
        context=context,
        trace_sink=sink,
    )

    assert result.primary_result is not None
    assert result.ciav_receipt is not None
    assert context.ciav_input is not None
    likelihoods = context.ciav_input.actor_likelihoods_by_outcome[result.ciav_receipt.outcome_label]
    unnormalized = {
        actor: probability * likelihoods[actor]
        for actor, probability in result.primary_result.actor_posterior.items()
    }
    total = sum(unnormalized.values())
    assert result.ciav_receipt.evidence.actor_posterior == pytest.approx(
        {actor: value / total for actor, value in unnormalized.items()}
    )
    assert result.path_selection.selected_path_id == "P5_FULL_EAGER"
    assert result.path_selection.reasons == (EVALUATION_DIRECT_P5_REASON,)
    assert result.debt_certificates == ()
    assert result.executed_operator_count == 13
    assert len(sink.traces) == 1
    trace = sink.traces[0]
    verify_execution_trace(trace)
    assert trace.plan.plan_id == "P5_FULL_EAGER"
    assert trace.all_seven_operators_invoked is True
    assert trace.ciav_invoked is True
    assert trace.feedback_observation_acquired is True
    assert trace.feedback_closure_kind == "full_transition"
    assert len(trace.receipts) == 13
    assert tuple(receipt.operator for receipt in trace.receipts[:7]) == (
        "opceu",
        "orrer_cheh",
        "pchmp",
        "cf_bocpd",
        "ccrr",
        "rgrc",
        "ciav",
    )


def test_neutral_ciav_actor_likelihood_preserves_primary_pchmp_posterior() -> None:
    system, transition = _adaptive_system_and_transition()
    ciav_input = _ciav_input(transition)
    neutral = replace(
        ciav_input,
        actor_likelihoods_by_outcome={
            outcome: dict.fromkeys(transition.actor_prior, 1.0)
            for outcome in ciav_input.actor_likelihoods_by_outcome
        },
        expected_detected_location_id=transition.after.detected_location_id,
    )
    context = AdaptiveExecutionContext(
        router_features=_features(system, step=0, route="P0_SAFE_DEFERRED"),
        step_index=0,
        ciav_input=neutral,
    )

    result = system.process_evaluation_direct_p5_transition(
        transition,
        context=context,
        trace_sink=RecordingSink(),
    )

    assert result.primary_result is not None
    assert result.ciav_receipt is not None
    assert result.fast_verification_receipt is not None
    assert result.feedback_result is None
    assert result.ciav_receipt.evidence.actor_posterior == pytest.approx(
        result.primary_result.actor_posterior
    )
    assert result.fast_verification_receipt.owner_mass_before == pytest.approx(
        result.primary_result.actor_posterior[system.core.owner_key]
    )
    assert result.fast_verification_receipt.owner_mass_after == pytest.approx(
        result.primary_result.actor_posterior[system.core.owner_key]
    )
    assert result.fast_verification_receipt.changed is False


def test_evaluation_only_direct_p5_fails_closed_without_ciav_or_with_debt() -> None:
    system, transition = _adaptive_system_and_transition()
    no_ciav = AdaptiveExecutionContext(
        router_features=_features(system, step=0, route="P0_SAFE_DEFERRED"),
        step_index=0,
    )
    with pytest.raises(ValueError, match="requires CIAV runtime input"):
        system.process_evaluation_direct_p5_transition(
            transition,
            context=no_ciav,
            trace_sink=RecordingSink(),
        )

    system.process_adaptive_transition(
        transition,
        context=AdaptiveExecutionContext(
            router_features=no_ciav.router_features,
            step_index=no_ciav.step_index,
            ciav_input=_ciav_input(transition),
        ),
        trace_sink=RecordingSink(),
    )
    pending = system.pending_adaptive_debts()
    assert len(pending) == 1
    debt_context = AdaptiveExecutionContext(
        router_features=_features(
            system,
            step=1,
            route="P5_FULL_EAGER",
            pending_count=1,
            oldest_age=1,
        ),
        step_index=1,
        ciav_input=_ciav_input(transition),
    )
    with pytest.raises(RuntimeError, match="while adaptive debt is pending"):
        system.process_evaluation_direct_p5_transition(
            transition,
            context=debt_context,
            trace_sink=RecordingSink(),
        )


def test_failed_expired_p0_debt_replay_restores_entry_and_lock_identity() -> None:
    system, transition = _adaptive_system_and_transition()
    ciav_input = _ciav_input(transition)
    first = AdaptiveExecutionContext(
        router_features=_features(system, step=0, route="P0_SAFE_DEFERRED"),
        step_index=0,
        ciav_input=ciav_input,
    )
    system.process_adaptive_transition(transition, context=first, trace_sink=RecordingSink())
    pending = system.pending_adaptive_debts()
    assert len(pending) == 1
    debt_id = pending[0].debt_id
    debt_ledger = system._adaptive_debt_ledger
    debt_entry = debt_ledger[debt_id]
    execution_lock = system._execution_lock
    core_execution_lock = system.core._execution_lock
    origin_execution_lock = debt_entry.origin_core_checkpoint["execution_lock"]
    before_core = _state_fingerprint(system)
    before_router = system.adaptive_router_state_sha256()
    sink = FailingSink()

    with pytest.raises(RuntimeError, match="injected trace sink failure"):
        system.replay_adaptive_debt(
            debt_id,
            step_index=20,
            ciav_input=ciav_input,
            trace_sink=sink,
        )

    assert sink.aborted is True
    assert system._adaptive_debt_ledger is debt_ledger
    assert debt_ledger[debt_id] is debt_entry
    assert debt_entry.status.value == "pending"
    assert debt_entry.settled_step is None
    assert debt_entry.origin_core_checkpoint["execution_lock"] is origin_execution_lock
    assert system._execution_lock is execution_lock
    assert system.core._execution_lock is core_execution_lock
    assert system._adaptive_replay_authorized_debt_ids == set()
    assert system.pending_adaptive_debts() == pending
    assert _state_fingerprint(system) == before_core
    assert system.adaptive_router_state_sha256() == before_router
    assert system.ciav_opceu_loop.trace.receipts == ()


def test_safe_abstention_and_stale_features_cannot_mutate_runtime() -> None:
    system, transition = _adaptive_system_and_transition()
    before = _state_fingerprint(system)
    system.bind_adaptive_authorization_policy(
        AdaptiveAuthorizationPolicy(
            policy_id="test-local-deny-policy",
            memory_transition_authorized=True,
            privacy_policy_satisfied=False,
            safety_context_authorized=True,
        )
    )
    features = _features(system, step=0, route="P0_SAFE_DEFERRED")
    context = AdaptiveExecutionContext(router_features=features, step_index=0)
    sink = RecordingSink()

    result = system.process_adaptive_transition(transition, context=context, trace_sink=sink)
    assert result.safe_abstained is True
    assert sink.traces == []
    assert _state_fingerprint(system) == before

    stale = context.router_features.model_copy(
        update={"source_state_sha256": "0" * 64, "feature_source_sha256s": ("0" * 64,)}
    )
    with pytest.raises(ValueError, match="stale or foreign"):
        system.process_adaptive_transition(
            transition,
            context=AdaptiveExecutionContext(router_features=stale, step_index=1),
            trace_sink=sink,
        )
    assert _state_fingerprint(system) == before


def test_adaptive_sink_failure_rolls_back_core_debt_and_ciav_state() -> None:
    system, transition = _adaptive_system_and_transition()
    before_core = _state_fingerprint(system)
    before_router = system.adaptive_router_state_sha256()
    debt_ledger = system._adaptive_debt_ledger
    context = AdaptiveExecutionContext(
        router_features=_features(system, step=0, route="P3_ACTIVE_VERIFY"),
        step_index=0,
        ciav_input=_ciav_input(transition),
    )
    sink = FailingSink()

    with pytest.raises(RuntimeError, match="injected trace sink failure"):
        system.process_adaptive_transition(transition, context=context, trace_sink=sink)

    assert sink.aborted is True
    assert _state_fingerprint(system) == before_core
    assert system._adaptive_debt_ledger is debt_ledger
    assert system._adaptive_debt_ledger == {}
    assert system.adaptive_router_state_sha256() == before_router
    assert system.ciav_opceu_loop.trace.receipts == ()


def test_forged_complete_adaptive_mode_vector_is_rejected() -> None:
    system, transition = _adaptive_system_and_transition()
    canonical = tuple(
        OperatorExecutionDirective(operator=operator, mode="refinement_executed")
        for operator in (
            "opceu",
            "orrer_cheh",
            "pchmp",
            "cf_bocpd",
            "ccrr",
            "rgrc",
            "ciav",
        )
    )
    with pytest.raises(ValidationError, match="mode vector drifted"):
        StructureTwoExecutionPlan(
            plan_id="P0_SAFE_DEFERRED",
            lane="registered_adaptive_path",
            adaptive_path_id="P0_SAFE_DEFERRED",
            operator_directives=canonical,
        )
    assert system.pending_adaptive_debts() == ()
    assert transition is not None
