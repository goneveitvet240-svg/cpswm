from __future__ import annotations

from dataclasses import replace

import pytest
from test_structure_two_adaptive_runtime import (
    _adaptive_system_and_transition,
    _ciav_input,
    _features,
)
from test_structure_two_execution_interface import RecordingSink, _state_fingerprint
from test_structure_two_production_system import _system_and_transition

from cpswm.contracts import ObservationOutcome
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_adaptive_runtime import (
    AdaptiveAuthorizationPolicy,
    AdaptiveExecutionContext,
    AdaptivePathSelectionReceipt,
    select_adaptive_path,
)
from cpswm.system.structure_two_execution import (
    OperatorInvocationReceipt,
    StructureTwoExecutionTrace,
    registered_adaptive_execution_plan,
    seal_trace_abort_ack,
    seal_trace_commit_ack,
    verify_execution_trace,
)
from cpswm.world_model.grounded_search import RealizedCIAVObservation, VerificationCause

_POLICY_REBIND_TARGET = None
_POLICY_REBIND_MODEL_ID = ""
_CONTEXT_MUTATION_TARGET = None
_CONTEXT_MUTATION_MODEL_ID = ""
_SELECTION_MUTATION_TARGET = None


def _global_policy_rebinding_realizer(_opportunity):
    assert _POLICY_REBIND_TARGET is not None
    _POLICY_REBIND_TARGET.bind_adaptive_authorization_policy(
        AdaptiveAuthorizationPolicy(policy_id="attacker-deny")
    )


def _global_context_mutating_realizer(_opportunity):
    assert _CONTEXT_MUTATION_TARGET is not None
    object.__setattr__(_CONTEXT_MUTATION_TARGET, "step_index", 999)
    if _SELECTION_MUTATION_TARGET is not None:
        object.__setattr__(
            _SELECTION_MUTATION_TARGET,
            "selected_path_id",
            "P5_FULL_EAGER",
        )
    return RealizedCIAVObservation(
        outcome_label=VerificationCause.OBSERVATION.value,
        likelihood_model_id=_CONTEXT_MUTATION_MODEL_ID,
        detection_outcome=ObservationOutcome.DETECTED,
    )


def _forged_selection(
    *,
    feature_sha256: str,
    selected_path_id: str,
    ciav_available: bool,
) -> AdaptivePathSelectionReceipt:
    payload = {
        "feature_sha256": feature_sha256,
        "selected_path_id": selected_path_id,
        "safe_abstain": False,
        "reasons": ("attacker_rehashed_selection",),
        "ciav_runtime_input_available": ciav_available,
    }
    return AdaptivePathSelectionReceipt(
        **payload,
        receipt_sha256=content_sha256(payload),
    )


def test_round2_rehashed_router_selection_cannot_splice_a_different_path() -> None:
    system, transition = _adaptive_system_and_transition()
    features = _features(system, step=0, route="P1_EVENT_ACTOR_LOCAL")
    context = AdaptiveExecutionContext(router_features=features, step_index=0)
    forged = _forged_selection(
        feature_sha256=features.content_sha256,
        selected_path_id="P2_REGIME_RECOVERY_LOCAL",
        ciav_available=False,
    )
    before_core = _state_fingerprint(system)
    before_router = system.adaptive_router_state_sha256()
    sink = RecordingSink()

    with pytest.raises(ValueError, match="fresh deterministic routing pass"):
        system.process_transition(
            transition,
            execution_plan=registered_adaptive_execution_plan("P2_REGIME_RECOVERY_LOCAL"),
            trace_sink=sink,
            adaptive_context=context,
            adaptive_selection=forged,
        )

    assert sink.traces == []
    assert _state_fingerprint(system) == before_core
    assert system.adaptive_router_state_sha256() == before_router


def test_round2_caller_cannot_upgrade_runtime_denial_flags() -> None:
    system, transition = _system_and_transition()
    denied = _features(system, step=0, route="P0_SAFE_DEFERRED")
    forged = denied.model_copy(
        update={
            "memory_transition_authorized": True,
            "privacy_policy_satisfied": True,
            "safety_context_authorized": True,
        }
    )
    before = _state_fingerprint(system)

    with pytest.raises(ValueError, match="authorization flags differ"):
        system.process_adaptive_transition(
            transition,
            context=AdaptiveExecutionContext(router_features=forged, step_index=0),
            trace_sink=RecordingSink(),
        )

    assert _state_fingerprint(system) == before
    assert system.pending_adaptive_debts() == ()


def test_round2_policy_hash_substitution_is_rejected_before_execution() -> None:
    system, transition = _adaptive_system_and_transition()
    features = _features(system, step=0, route="P0_SAFE_DEFERRED").model_copy(
        update={"authorization_policy_sha256": "0" * 64}
    )
    before = _state_fingerprint(system)

    with pytest.raises(ValueError, match="active authorization policy"):
        system.process_adaptive_transition(
            transition,
            context=AdaptiveExecutionContext(router_features=features, step_index=0),
            trace_sink=RecordingSink(),
        )

    assert _state_fingerprint(system) == before
    assert system.pending_adaptive_debts() == ()


def test_round2_pending_debt_cannot_be_spliced_into_direct_p5_execution() -> None:
    system, transition = _adaptive_system_and_transition()
    system.process_adaptive_transition(
        transition,
        context=AdaptiveExecutionContext(
            router_features=_features(system, step=0, route="P0_SAFE_DEFERRED"),
            step_index=0,
        ),
        trace_sink=RecordingSink(),
    )
    debt = system.pending_adaptive_debts()[0]
    features = _features(
        system,
        step=20,
        route="P5_FULL_EAGER",
        pending_count=1,
        oldest_age=20,
    )
    context = AdaptiveExecutionContext(
        router_features=features,
        step_index=20,
        ciav_input=_ciav_input(transition),
    )
    selection = select_adaptive_path(
        features,
        ciav_runtime_input_available=True,
        debt_expiry_steps=20,
    )
    assert selection.selected_path_id == "P5_FULL_EAGER"
    before_core = _state_fingerprint(system)
    before_router = system.adaptive_router_state_sha256()

    with pytest.raises(RuntimeError, match="cannot be bypassed"):
        system.process_transition(
            transition,
            execution_plan=registered_adaptive_execution_plan("P5_FULL_EAGER"),
            trace_sink=RecordingSink(),
            adaptive_context=context,
            adaptive_selection=selection,
        )

    assert _state_fingerprint(system) == before_core
    assert system.adaptive_router_state_sha256() == before_router
    assert system.pending_adaptive_debts() == (debt,)


def test_round2_same_source_realizer_closures_have_distinct_content_identities() -> None:
    _system, transition = _adaptive_system_and_transition()
    base = _ciav_input(transition)
    action = base.actions[0]

    def make_realizer(outcome_label: str):
        def realize(_opportunity):
            return RealizedCIAVObservation(
                outcome_label=outcome_label,
                likelihood_model_id=action.observation_likelihood_model_id,
                detection_outcome=ObservationOutcome.DETECTED,
            )

        return realize

    first = replace(base, realizer=make_realizer(VerificationCause.OBSERVATION.value))
    second = replace(base, realizer=make_realizer(VerificationCause.ACTOR.value))

    assert first.content_sha256 != second.content_sha256


def test_round2_realizer_cannot_mutate_its_bound_closure_during_execution() -> None:
    system, transition = _adaptive_system_and_transition()
    base = _ciav_input(transition)
    action = base.actions[0]
    mutable_outcome = {"label": VerificationCause.OBSERVATION.value}

    def mutate_then_realize(_opportunity):
        selected = mutable_outcome["label"]
        mutable_outcome["label"] = VerificationCause.ACTOR.value
        return RealizedCIAVObservation(
            outcome_label=selected,
            likelihood_model_id=action.observation_likelihood_model_id,
            detection_outcome=ObservationOutcome.DETECTED,
        )

    ciav_input = replace(base, realizer=mutate_then_realize)
    before_core = _state_fingerprint(system)
    before_router = system.adaptive_router_state_sha256()

    with pytest.raises(RuntimeError, match="runtime input mutated"):
        system.process_adaptive_transition(
            transition,
            context=AdaptiveExecutionContext(
                router_features=_features(system, step=0, route="P3_ACTIVE_VERIFY"),
                step_index=0,
                ciav_input=ciav_input,
            ),
            trace_sink=RecordingSink(),
        )

    assert system.ciav_opceu_loop.trace.receipts == ()
    assert _state_fingerprint(system) == before_core
    assert system.adaptive_router_state_sha256() == before_router


def test_round2_ciav_callback_cannot_rebind_authorization_mid_transaction() -> None:
    global _POLICY_REBIND_MODEL_ID, _POLICY_REBIND_TARGET
    system, transition = _adaptive_system_and_transition()
    base = _ciav_input(transition)
    action = base.actions[0]
    _POLICY_REBIND_TARGET = system
    _POLICY_REBIND_MODEL_ID = action.observation_likelihood_model_id

    before_core = _state_fingerprint(system)
    before_router = system.adaptive_router_state_sha256()

    try:
        with pytest.raises(RuntimeError, match="policy mutation is forbidden"):
            system.process_adaptive_transition(
                transition,
                context=AdaptiveExecutionContext(
                    router_features=_features(system, step=0, route="P3_ACTIVE_VERIFY"),
                    step_index=0,
                    ciav_input=replace(base, realizer=_global_policy_rebinding_realizer),
                ),
                trace_sink=RecordingSink(),
            )
    finally:
        _POLICY_REBIND_TARGET = None
        _POLICY_REBIND_MODEL_ID = ""

    assert _state_fingerprint(system) == before_core
    assert system.adaptive_router_state_sha256() == before_router


def test_round2_ciav_callback_cannot_rewrite_committed_step_via_caller_context() -> None:
    global _CONTEXT_MUTATION_MODEL_ID, _CONTEXT_MUTATION_TARGET
    system, transition = _adaptive_system_and_transition()
    base = _ciav_input(transition)
    _CONTEXT_MUTATION_MODEL_ID = base.actions[0].observation_likelihood_model_id
    context = AdaptiveExecutionContext(
        router_features=_features(system, step=0, route="P3_ACTIVE_VERIFY"),
        step_index=0,
        ciav_input=replace(base, realizer=_global_context_mutating_realizer),
    )
    _CONTEXT_MUTATION_TARGET = context
    sink = RecordingSink()

    try:
        system.process_adaptive_transition(transition, context=context, trace_sink=sink)
    finally:
        _CONTEXT_MUTATION_TARGET = None
        _CONTEXT_MUTATION_MODEL_ID = ""

    # The untrusted callback did mutate its caller-owned object, but production
    # used a detached snapshot for both the trace and the committed state.
    assert context.step_index == 999
    assert sink.traces[0].adaptive_step_index == 0
    assert system._adaptive_last_step == 0


def test_round2_direct_adaptive_overload_detaches_caller_context_before_callback() -> None:
    global _CONTEXT_MUTATION_MODEL_ID, _CONTEXT_MUTATION_TARGET, _SELECTION_MUTATION_TARGET
    system, transition = _adaptive_system_and_transition()
    base = _ciav_input(transition)
    _CONTEXT_MUTATION_MODEL_ID = base.actions[0].observation_likelihood_model_id
    context = AdaptiveExecutionContext(
        router_features=_features(system, step=0, route="P3_ACTIVE_VERIFY"),
        step_index=0,
        ciav_input=replace(base, realizer=_global_context_mutating_realizer),
    )
    _CONTEXT_MUTATION_TARGET = context
    selection = select_adaptive_path(
        context.router_features,
        ciav_runtime_input_available=True,
        debt_expiry_steps=context.debt_expiry_steps,
    )
    _SELECTION_MUTATION_TARGET = selection
    sink = RecordingSink()

    try:
        system.process_transition(
            transition,
            execution_plan=registered_adaptive_execution_plan("P3_ACTIVE_VERIFY"),
            trace_sink=sink,
            adaptive_context=context,
            adaptive_selection=selection,
        )
    finally:
        _CONTEXT_MUTATION_TARGET = None
        _CONTEXT_MUTATION_MODEL_ID = ""
        _SELECTION_MUTATION_TARGET = None

    assert context.step_index == 999
    assert selection.selected_path_id == "P5_FULL_EAGER"
    assert sink.traces[0].plan.plan_id == "P3_ACTIVE_VERIFY"
    assert sink.traces[0].adaptive_step_index == 0
    assert system._adaptive_last_step == 0


def test_round2_sink_cannot_mutate_debt_or_replay_guard_state() -> None:
    system, transition = _adaptive_system_and_transition()
    debt_ledger = system._adaptive_debt_ledger
    replay_guard = system._adaptive_replay_authorized_debt_ids

    class MutatingSink:
        aborted = False

        def commit(self, trace, /):
            debt_id = next(iter(system._adaptive_debt_ledger))
            system._adaptive_debt_ledger[debt_id].settled_step = 999
            system._adaptive_replay_authorized_debt_ids.add(debt_id)
            return seal_trace_commit_ack(trace)

        def abort(self, trace, /, *, reason: str):
            self.aborted = True
            return seal_trace_abort_ack(trace, reason=reason)

    sink = MutatingSink()
    before = _state_fingerprint(system)

    with pytest.raises(RuntimeError, match="production-wrapper state"):
        system.process_adaptive_transition(
            transition,
            context=AdaptiveExecutionContext(
                router_features=_features(system, step=0, route="P0_SAFE_DEFERRED"),
                step_index=0,
            ),
            trace_sink=sink,
        )

    assert sink.aborted is True
    assert system._adaptive_debt_ledger is debt_ledger
    assert system._adaptive_replay_authorized_debt_ids is replay_guard
    assert system._adaptive_debt_ledger == {}
    assert system._adaptive_replay_authorized_debt_ids == set()
    assert _state_fingerprint(system) == before


def test_round2_fully_rehashed_but_wrong_adaptive_dag_is_rejected() -> None:
    system, transition = _adaptive_system_and_transition()
    sink = RecordingSink()
    system.process_adaptive_transition(
        transition,
        context=AdaptiveExecutionContext(
            router_features=_features(system, step=0, route="P0_SAFE_DEFERRED"),
            step_index=0,
        ),
        trace_sink=sink,
    )
    original = sink.traces[0]
    forged_receipts: list[OperatorInvocationReceipt] = []
    previous = "GENESIS"
    for index, receipt in enumerate(original.receipts):
        payload = receipt.model_dump(mode="python", exclude={"receipt_sha256"})
        payload["previous_receipt_sha256"] = previous
        if index == 1:
            consumed = (original.receipts[0].output_id,)
            payload["consumed_output_ids"] = consumed
            payload["input_payload_sha256"] = content_sha256(
                {
                    "raw_input_sha256": payload["raw_input_sha256"],
                    "consumed_output_ids": list(consumed),
                }
            )
        forged = OperatorInvocationReceipt(
            **payload,
            receipt_sha256=content_sha256(payload),
        )
        forged_receipts.append(forged)
        previous = forged.receipt_sha256

    trace_payload = {
        name: getattr(original, name)
        for name in type(original).model_fields
        if name != "trace_sha256"
    }
    trace_payload["receipts"] = tuple(forged_receipts)
    forged_trace = StructureTwoExecutionTrace.model_construct(
        **trace_payload,
        trace_sha256=content_sha256(trace_payload),
    )

    with pytest.raises(ValueError, match="output-consumption DAG mismatch"):
        verify_execution_trace(forged_trace)


def test_round2_sink_cannot_zero_measured_resource_receipts() -> None:
    system, transition = _adaptive_system_and_transition()
    before = _state_fingerprint(system)

    class ResourceTamperingSink:
        aborted = False

        def commit(self, trace, /):
            object.__setattr__(trace.receipts[0], "elapsed_ns", 0)
            return seal_trace_commit_ack(trace)

        def abort(self, trace, /, *, reason: str):
            self.aborted = True
            return seal_trace_abort_ack(trace, reason=reason)

    sink = ResourceTamperingSink()
    with pytest.raises((RuntimeError, ValueError), match=r"trace|hash"):
        system.process_adaptive_transition(
            transition,
            context=AdaptiveExecutionContext(
                router_features=_features(system, step=0, route="P1_EVENT_ACTOR_LOCAL"),
                step_index=0,
            ),
            trace_sink=sink,
        )

    assert sink.aborted is True
    assert system.pending_adaptive_debts() == ()
    assert _state_fingerprint(system) == before
