from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest
from test_structure_two_adaptive_runtime import (
    _adaptive_system_and_transition,
    _ciav_input,
    _features,
)
from test_structure_two_execution_interface import RecordingSink, _state_fingerprint

from cpswm.system.structure_two_adaptive_runtime import AdaptiveExecutionContext
from cpswm.system.structure_two_execution import canonical_legacy_ordinary_transition_plan


def test_round1_pending_debt_cannot_accumulate_behind_a_new_transition() -> None:
    system, transition = _adaptive_system_and_transition()
    system.process_adaptive_transition(
        transition,
        context=AdaptiveExecutionContext(
            router_features=_features(system, step=0, route="P0_SAFE_DEFERRED"),
            step_index=0,
            ciav_input=_ciav_input(transition),
        ),
        trace_sink=RecordingSink(),
    )
    before_core = _state_fingerprint(system)
    before_router = system.adaptive_router_state_sha256()
    sink = RecordingSink()

    with pytest.raises(RuntimeError, match="must be resolved through replay_adaptive_debt"):
        system.process_adaptive_transition(
            transition,
            context=AdaptiveExecutionContext(
                router_features=_features(
                    system,
                    step=1,
                    route="P2_REGIME_RECOVERY_LOCAL",
                    pending_count=1,
                    oldest_age=1,
                ),
                step_index=1,
            ),
            trace_sink=sink,
        )

    assert sink.traces == []
    assert len(system.pending_adaptive_debts()) == 1
    assert _state_fingerprint(system) == before_core
    assert system.adaptive_router_state_sha256() == before_router


def test_round1_pending_debt_blocks_legacy_and_direct_core_branch_evolution() -> None:
    system, transition = _adaptive_system_and_transition()
    ciav_input = _ciav_input(transition)
    system.process_adaptive_transition(
        transition,
        context=AdaptiveExecutionContext(
            router_features=_features(system, step=0, route="P0_SAFE_DEFERRED"),
            step_index=0,
            ciav_input=ciav_input,
        ),
        trace_sink=RecordingSink(),
    )
    debt = system.pending_adaptive_debts()[0]
    before_core = _state_fingerprint(system)
    before_router = system.adaptive_router_state_sha256()

    with pytest.raises(RuntimeError, match="pending adaptive debt blocks"):
        system.process_transition(transition)
    with pytest.raises(RuntimeError, match="pending adaptive debt blocks"):
        system.process_transition(
            transition,
            execution_plan=canonical_legacy_ordinary_transition_plan(),
            trace_sink=RecordingSink(),
        )
    with pytest.raises(RuntimeError, match="pending adaptive debt blocks"):
        system.core.process_transition(transition)
    with pytest.raises(RuntimeError, match="pending adaptive debt blocks"):
        system.core.apply_fast_action_verification(
            revision_id=uuid4(),
            verified_owner_probability=0.5,
            source_record_id=uuid4(),
        )

    assert _state_fingerprint(system) == before_core
    assert system.adaptive_router_state_sha256() == before_router
    assert system.pending_adaptive_debts() == (debt,)

    system.replay_adaptive_debt(
        debt.debt_id,
        step_index=20,
        ciav_input=ciav_input,
        trace_sink=RecordingSink(),
    )
    assert system.pending_adaptive_debts() == ()


def test_round1_replayed_debt_is_exactly_once() -> None:
    system, transition = _adaptive_system_and_transition()
    ciav_input = _ciav_input(transition)
    system.process_adaptive_transition(
        transition,
        context=AdaptiveExecutionContext(
            router_features=_features(system, step=0, route="P0_SAFE_DEFERRED"),
            step_index=0,
            ciav_input=ciav_input,
        ),
        trace_sink=RecordingSink(),
    )
    debt = system.pending_adaptive_debts()[0]
    system.replay_adaptive_debt(
        debt.debt_id,
        step_index=20,
        ciav_input=ciav_input,
        trace_sink=RecordingSink(),
    )
    before = _state_fingerprint(system)

    with pytest.raises(ValueError, match="not pending"):
        system.replay_adaptive_debt(
            debt.debt_id,
            step_index=21,
            ciav_input=ciav_input,
            trace_sink=RecordingSink(),
        )

    assert _state_fingerprint(system) == before
    assert system.pending_adaptive_debts() == ()


def test_round1_debt_replay_rejects_substituted_ciav_input() -> None:
    system, transition = _adaptive_system_and_transition()
    committed = _ciav_input(transition)
    system.process_adaptive_transition(
        transition,
        context=AdaptiveExecutionContext(
            router_features=_features(system, step=0, route="P0_SAFE_DEFERRED"),
            step_index=0,
            ciav_input=committed,
        ),
        trace_sink=RecordingSink(),
    )
    debt = system.pending_adaptive_debts()[0]
    before = _state_fingerprint(system)
    substituted = replace(
        committed,
        actor_likelihoods_by_outcome={
            outcome: {
                actor: (0.01 if actor == system.core.owner_key else 1.0) for actor in likelihoods
            }
            for outcome, likelihoods in committed.actor_likelihoods_by_outcome.items()
        },
    )

    assert substituted.content_sha256 != debt.deferred_ciav_input_sha256
    with pytest.raises(ValueError, match="CIAV input commitment mismatch"):
        system.replay_adaptive_debt(
            debt.debt_id,
            step_index=20,
            ciav_input=substituted,
            trace_sink=RecordingSink(),
        )

    assert system.pending_adaptive_debts() == (debt,)
    assert _state_fingerprint(system) == before


def test_round1_adaptive_step_index_is_strictly_monotone() -> None:
    system, transition = _adaptive_system_and_transition()
    context = AdaptiveExecutionContext(
        router_features=_features(system, step=0, route="P3_ACTIVE_VERIFY"),
        step_index=0,
        ciav_input=_ciav_input(transition),
    )
    system.process_adaptive_transition(transition, context=context, trace_sink=RecordingSink())
    before = _state_fingerprint(system)
    sink = RecordingSink()

    with pytest.raises(ValueError, match="step indices must increase strictly"):
        system.process_adaptive_transition(
            transition,
            context=AdaptiveExecutionContext(
                router_features=_features(system, step=0, route="P3_ACTIVE_VERIFY"),
                step_index=0,
                ciav_input=_ciav_input(transition),
            ),
            trace_sink=sink,
        )

    assert sink.traces == []
    assert _state_fingerprint(system) == before


def test_round1_ciav_realizer_failure_rolls_back_every_local_state() -> None:
    system, transition = _adaptive_system_and_transition()
    before_core = _state_fingerprint(system)
    before_router = system.adaptive_router_state_sha256()
    base_input = _ciav_input(transition)

    def fail_realizer(_opportunity):
        raise RuntimeError("round1 injected CIAV realization failure")

    context = AdaptiveExecutionContext(
        router_features=_features(system, step=0, route="P3_ACTIVE_VERIFY"),
        step_index=0,
        ciav_input=replace(base_input, realizer=fail_realizer),
    )
    sink = RecordingSink()

    with pytest.raises(RuntimeError, match="injected CIAV realization failure"):
        system.process_adaptive_transition(transition, context=context, trace_sink=sink)

    assert sink.traces == []
    assert system.ciav_opceu_loop.trace.receipts == ()
    assert system.pending_adaptive_debts() == ()
    assert _state_fingerprint(system) == before_core
    assert system.adaptive_router_state_sha256() == before_router


def test_round1_ciav_no_action_keeps_primary_write_quarantined() -> None:
    system, transition = _adaptive_system_and_transition()
    ciav_input = replace(_ciav_input(transition), minimum_net_value=1_000_000.0)
    sink = RecordingSink()

    result = system.process_adaptive_transition(
        transition,
        context=AdaptiveExecutionContext(
            router_features=_features(system, step=0, route="P3_ACTIVE_VERIFY"),
            step_index=0,
            ciav_input=ciav_input,
        ),
        trace_sink=sink,
    )

    assert result.ciav_plan is not None and result.ciav_plan.should_act is False
    assert result.ciav_receipt is None
    assert result.feedback_result is None
    assert result.primary_result is not None
    assert result.primary_result.event_revision_id not in system.core._committed_events
    assert any(
        item.revision_id == result.primary_result.event_revision_id
        for item in system.core._quarantined_events
    )
    trace = sink.traces[0]
    assert trace.all_seven_operators_invoked is True
    assert trace.feedback_observation_acquired is False
    assert len(trace.receipts) == 7


def test_round1_same_location_ciav_detection_closes_feedback_without_fabrication() -> None:
    system, transition = _adaptive_system_and_transition()
    assert transition.after.detected_location_id is not None
    ciav_input = replace(
        _ciav_input(transition),
        expected_detected_location_id=transition.after.detected_location_id,
    )
    sink = RecordingSink()

    result = system.process_adaptive_transition(
        transition,
        context=AdaptiveExecutionContext(
            router_features=_features(system, step=0, route="P3_ACTIVE_VERIFY"),
            step_index=0,
            ciav_input=ciav_input,
        ),
        trace_sink=sink,
    )

    assert result.ciav_receipt is not None
    assert result.feedback_result is None
    assert result.fast_verification_receipt is not None
    assert result.fast_verification_receipt.long_term_write is False
    assert sink.traces[0].feedback_observation_acquired is True
    assert sink.traces[0].feedback_closure_kind == "same_location_fast_verification"
    assert len(sink.traces[0].receipts) == 8


def test_round1_trace_binds_route_policy_input_and_positive_resource_measurements() -> None:
    system, transition = _adaptive_system_and_transition()
    context = AdaptiveExecutionContext(
        router_features=_features(system, step=0, route="P3_ACTIVE_VERIFY"),
        step_index=0,
        ciav_input=_ciav_input(transition),
    )
    sink = RecordingSink()

    result = system.process_adaptive_transition(
        transition,
        context=context,
        trace_sink=sink,
    )

    trace = sink.traces[0]
    assert trace.adaptive_router_feature_sha256 == context.router_features.content_sha256
    assert trace.adaptive_authorization_policy_sha256 == system.adaptive_authorization_policy_sha256
    assert trace.adaptive_path_selection_receipt_sha256 == result.path_selection.receipt_sha256
    assert trace.adaptive_ciav_input_sha256 == context.ciav_input.content_sha256
    assert trace.adaptive_step_index == 0
    assert trace.adaptive_debt_expiry_steps == 20
    assert all(receipt.elapsed_ns > 0 for receipt in trace.receipts if receipt.status == "executed")
