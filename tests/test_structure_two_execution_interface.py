from __future__ import annotations

import importlib.util
import sys
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from threading import Event, RLock, Thread, current_thread
from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError
from test_structure_two_production_system import _system_and_transition

import cpswm.system.prototype_spine as prototype_module
import cpswm.system.structure_two_execution as execution_module
from cpswm.system.attestation import Ed25519AttestationSigner
from cpswm.system.counterfactual_event_hypergraph.engine import (
    CounterfactualEventHypergraphEngine,
)
from cpswm.system.counterfactual_event_hypergraph.hypothesis_message_passing import (
    ProvenanceConstrainedMessagePassing,
)
from cpswm.system.evaluation_operations.project_two_ablation import (
    EvaluatorNoDedupMessagePassing,
    EvaluatorNoProvenanceFirewallMessagePassing,
    IndependentEvidenceMessagePassing,
    PriorOnlyMessagePassing,
)
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_execution import (
    LEGACY_CIAV_NOT_APPLICABLE_REASON,
    OperatorExecutionDirective,
    StructureTwoExecutionPlan,
    StructureTwoExecutionTrace,
    TraceAbortAck,
    TraceCommitAck,
    TraceCompensationError,
    UnsupportedStructureTwoExecutionPlan,
    bind_runtime_callable,
    canonical_legacy_ordinary_transition_plan,
    seal_trace_abort_ack,
    seal_trace_commit_ack,
    verify_execution_trace,
)
from cpswm.world_model.habits_transitions import ChangeCause


class RecordingSink:
    def __init__(self) -> None:
        self.traces: list[StructureTwoExecutionTrace] = []
        self.aborted: list[StructureTwoExecutionTrace] = []

    def commit(self, trace: StructureTwoExecutionTrace, /) -> TraceCommitAck:
        verify_execution_trace(trace)
        self.traces.append(trace)
        return seal_trace_commit_ack(trace)

    def abort(self, trace: StructureTwoExecutionTrace, /, *, reason: str) -> TraceAbortAck:
        self.traces = [item for item in self.traces if item.trace_sha256 != trace.trace_sha256]
        self.aborted.append(trace)
        return seal_trace_abort_ack(trace, reason=reason)


class FailingSink:
    def __init__(self) -> None:
        self.calls = 0
        self.trace: StructureTwoExecutionTrace | None = None
        self.aborted = False

    def commit(self, trace: StructureTwoExecutionTrace, /) -> TraceCommitAck:
        self.calls += 1
        self.trace = trace
        raise RuntimeError("injected trace sink failure")

    def abort(self, trace: StructureTwoExecutionTrace, /, *, reason: str) -> TraceAbortAck:
        assert self.trace == trace
        self.trace = None
        self.aborted = True
        return seal_trace_abort_ack(trace, reason=reason)


class WrongAcknowledgementSink:
    def __init__(self) -> None:
        self.calls = 0
        self.aborted = False

    def commit(self, trace: StructureTwoExecutionTrace, /) -> TraceCommitAck:
        self.calls += 1
        return seal_trace_commit_ack(trace).model_copy(update={"trace_sha256": "0" * 64})

    def abort(self, trace: StructureTwoExecutionTrace, /, *, reason: str) -> TraceAbortAck:
        self.aborted = True
        return seal_trace_abort_ack(trace, reason=reason)


class UncompensatableSink:
    def __init__(self) -> None:
        self.trace: StructureTwoExecutionTrace | None = None

    def commit(self, trace: StructureTwoExecutionTrace, /) -> TraceCommitAck:
        self.trace = trace
        raise RuntimeError("injected post-persist commit failure")

    def abort(self, trace: StructureTwoExecutionTrace, /, *, reason: str) -> TraceAbortAck:
        raise RuntimeError("injected tombstone failure")


def _state_fingerprint(system: Any) -> dict[str, object]:
    core = system.core
    return {
        "habit": core._habit.canonical_state_hash(),
        "rls": core.rls_regime_snapshot(core.active_regime),
        "ledger": core._hybrid_loop.ledger.export_state().to_json(),
        "router_count": core.observation_count,
        "snapshot": core.current_snapshot,
        "committed": tuple(core._committed_events),
        "observed": tuple(core._observed_events),
        "fast": tuple(core._fast_action_events),
        "quarantine": tuple(item.revision_id for item in core._quarantined_events),
        "last_location": core._last_observed_location,
        "last_context": (core._last_context_key, core._last_context_value),
        "last_household": core._last_household_id,
        "switch_sequence": core._switch_sequence,
        "last_ccrr": core._last_ccrr_decision,
        "last_cause": core._last_cause_snapshot,
        "action_negatives": dict(core._action_scoped_negatives),
        "revision_feedback_bindings": dict(core._revision_feedback_bindings),
        "complete_execution_state": core._execution_observable_state_sha256(),
    }


def _seed_preexisting_rls_graph(system: Any) -> tuple[str, Any, Any, Any, Any]:
    core = system.core
    regime_id = core.active_regime
    head = core._regimes._head(regime_id)
    wrapper = head._get_model(
        object_instance_id=core.object_instance_id,
        actor_id=core.owner_key,
        regime_id=regime_id,
        location_id=core.locations[0],
    )
    assert wrapper is not None
    model_key = next(iter(head._models))
    return regime_id, head, head._models, model_key, wrapper


def test_canonical_plan_is_transitively_immutable_and_not_an_adaptive_path() -> None:
    plan = canonical_legacy_ordinary_transition_plan()

    assert plan.plan_id == "LEGACY_ORDINARY_TRANSITION"
    assert plan.lane == "legacy_ordinary_transition"
    assert plan.adaptive_path_id is None
    assert plan.scientific_evidence_authorized is False
    assert tuple(item.operator for item in plan.operator_directives) == (
        "opceu",
        "orrer_cheh",
        "pchmp",
        "cf_bocpd",
        "ccrr",
        "rgrc",
        "ciav",
    )
    assert tuple(item.mode for item in plan.operator_directives) == (
        "legacy_default_executed",
    ) * 6 + ("not_applicable_with_recomputed_reason",)
    with pytest.raises(ValidationError, match="frozen"):
        plan.plan_id = "P5_FULL_EAGER"  # type: ignore[misc]
    with pytest.raises(ValidationError, match="frozen"):
        plan.operator_directives[0].mode = "refinement_executed"  # type: ignore[misc]


def test_adaptive_plan_and_consumption_registries_are_transitively_read_only() -> None:
    p0_modes = execution_module.REGISTERED_ADAPTIVE_PATH_MODES["P0_SAFE_DEFERRED"]

    with pytest.raises(TypeError):
        execution_module.REGISTERED_ADAPTIVE_PATH_MODES["P0_SAFE_DEFERRED"] = (  # type: ignore[index]
            *p0_modes[:-1],
            "refinement_executed",
        )
    with pytest.raises(TypeError):
        execution_module.LEGACY_CONSUMPTION_GRAPH["opceu"] = ("ciav",)  # type: ignore[index]
    with pytest.raises(TypeError):
        execution_module.ADAPTIVE_PRIMARY_CONSUMPTION_GRAPHS["P0_SAFE_DEFERRED"][  # type: ignore[index]
            "opceu"
        ] = ("ciav",)
    with pytest.raises(TypeError):
        execution_module.ADAPTIVE_FEEDBACK_CONSUMPTION_GRAPH["opceu"] = ()  # type: ignore[index]

    plan = execution_module.registered_adaptive_execution_plan("P0_SAFE_DEFERRED")
    assert tuple(item.mode for item in plan.operator_directives) == p0_modes


def test_no_argument_entrypoint_bypasses_plan_and_trace_allocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    system, transition = _system_and_transition()

    def forbidden_plan_allocation() -> StructureTwoExecutionPlan:
        raise AssertionError("legacy entrypoint allocated a plan")

    monkeypatch.setattr(
        prototype_module,
        "canonical_legacy_ordinary_transition_plan",
        forbidden_plan_allocation,
    )
    result = system.process_transition(transition)

    assert result.event_revision_id == result.event_history.latest.revision_id
    assert system.observation_count == 1


@pytest.mark.parametrize(
    "message_passing_type",
    (
        PriorOnlyMessagePassing,
        IndependentEvidenceMessagePassing,
        EvaluatorNoDedupMessagePassing,
        EvaluatorNoProvenanceFirewallMessagePassing,
    ),
)
def test_registered_pchmp_overrides_support_legacy_and_traced_execution_without_shape_pollution(
    message_passing_type: type[object],
) -> None:
    for traced in (False, True):
        message_passing = message_passing_type()
        system, transition = _system_and_transition(message_passing=message_passing)
        system.verify_runtime_assembly(allowed_operator_overrides=frozenset({"pchmp"}))

        if traced:
            sink = RecordingSink()
            result = system.process_transition(
                transition,
                execution_plan=canonical_legacy_ordinary_transition_plan(),
                trace_sink=sink,
            )
            assert len(sink.traces) == 1
        else:
            result = system.process_transition(transition)

        assert result.event_revision_id == result.event_history.latest.revision_id
        assert not hasattr(message_passing, "_independence_authority")


def test_sink_cannot_replace_registered_pchmp_delegate_and_rollback_preserves_identity() -> None:
    message_passing = PriorOnlyMessagePassing()
    authority = Ed25519AttestationSigner.generate(key_id="delegate-key").verifier()
    message_passing._delegate._independence_authority = authority
    system, transition = _system_and_transition(message_passing=message_passing)
    before = _state_fingerprint(system)
    original_delegate = message_passing._delegate
    replacement_delegate = ProvenanceConstrainedMessagePassing(independence_authority=authority)

    class DelegateReplacingSink(RecordingSink):
        def commit(self, trace: StructureTwoExecutionTrace, /) -> TraceCommitAck:
            acknowledgement = super().commit(trace)
            message_passing._delegate = replacement_delegate
            return acknowledgement

    sink = DelegateReplacingSink()
    with pytest.raises(RuntimeError, match="replaced an audited runtime component"):
        system.process_transition(
            transition,
            execution_plan=canonical_legacy_ordinary_transition_plan(),
            trace_sink=sink,
        )

    assert sink.traces == []
    assert len(sink.aborted) == 1
    assert system.core._message_passing is message_passing
    assert message_passing._delegate is original_delegate
    assert message_passing._delegate._independence_authority is authority
    assert not hasattr(message_passing, "_independence_authority")
    assert _state_fingerprint(system) == before


def test_sink_cannot_mutate_registered_pchmp_delegate_authority_in_place() -> None:
    message_passing = PriorOnlyMessagePassing()
    authority = Ed25519AttestationSigner.generate(key_id="delegate-key").verifier()
    replacement = Ed25519AttestationSigner.generate(key_id="delegate-key").verifier()
    message_passing._delegate._independence_authority = authority
    system, transition = _system_and_transition(message_passing=message_passing)
    before = _state_fingerprint(system)
    original_public_key_sha256 = authority.public_key_sha256

    class DelegateAuthorityMutatingSink(RecordingSink):
        def commit(self, trace: StructureTwoExecutionTrace, /) -> TraceCommitAck:
            acknowledgement = super().commit(trace)
            authority._public_key = replacement._public_key
            return acknowledgement

    sink = DelegateAuthorityMutatingSink()
    with pytest.raises(RuntimeError, match="mutated audited core state"):
        system.process_transition(
            transition,
            execution_plan=canonical_legacy_ordinary_transition_plan(),
            trace_sink=sink,
        )

    assert sink.traces == []
    assert len(sink.aborted) == 1
    assert message_passing._delegate._independence_authority is authority
    assert authority.public_key_sha256 == original_public_key_sha256
    assert not hasattr(message_passing, "_independence_authority")
    assert _state_fingerprint(system) == before


@pytest.mark.parametrize("omit", ["plan", "sink"])
def test_plan_and_sink_are_required_as_one_pair_before_state_change(omit: str) -> None:
    system, transition = _system_and_transition()
    before = _state_fingerprint(system)
    sink = RecordingSink()
    kwargs: dict[str, object] = {
        "execution_plan": canonical_legacy_ordinary_transition_plan(),
        "trace_sink": sink,
    }
    kwargs["execution_plan" if omit == "plan" else "trace_sink"] = None

    with pytest.raises(ValueError, match="must be supplied together"):
        system.process_transition(transition, **kwargs)  # type: ignore[arg-type]

    assert _state_fingerprint(system) == before
    assert sink.traces == []


def test_reordered_or_adaptive_plan_is_rejected_before_calls() -> None:
    system, transition = _system_and_transition()
    before = _state_fingerprint(system)
    sink = RecordingSink()
    canonical = canonical_legacy_ordinary_transition_plan()
    reordered = StructureTwoExecutionPlan.model_construct(
        **{
            **canonical.model_dump(mode="python"),
            "operator_directives": tuple(reversed(canonical.operator_directives)),
        }
    )
    with pytest.raises(ValidationError, match="exact ordered seven-operator registry"):
        system.process_transition(transition, execution_plan=reordered, trace_sink=sink)
    assert _state_fingerprint(system) == before
    assert sink.traces == []

    adaptive = StructureTwoExecutionPlan(
        plan_id="P5_FULL_EAGER",
        lane="registered_adaptive_path",
        adaptive_path_id="P5_FULL_EAGER",
        operator_directives=tuple(
            OperatorExecutionDirective(operator=item.operator, mode="refinement_executed")
            for item in canonical.operator_directives
        ),
    )
    with pytest.raises(UnsupportedStructureTwoExecutionPlan, match="not yet production-bound"):
        system.process_transition(transition, execution_plan=adaptive, trace_sink=sink)
    assert _state_fingerprint(system) == before
    assert sink.traces == []


def test_successful_trace_binds_calls_consumption_chain_and_truthful_ciav_disposition() -> None:
    system, transition = _system_and_transition()
    sink = RecordingSink()
    result = system.process_transition(
        transition,
        execution_plan=canonical_legacy_ordinary_transition_plan(),
        trace_sink=sink,
    )

    assert len(sink.traces) == 1
    trace = sink.traces[0]
    verify_execution_trace(trace)
    assert trace.runtime_symbol.endswith(".StructureTwoProductionSystem")
    assert trace.transition_sha256 == content_sha256(transition)
    assert trace.final_output_sha256 == content_sha256(result)
    assert trace.all_seven_operators_invoked is False
    assert trace.adaptive_legal_path_executed is False
    assert trace.ciav_invoked is False
    assert trace.scientific_evidence_authorized is False
    assert trace.cross_system_trace_state_atomicity_established is False
    assert [receipt.status for receipt in trace.receipts] == ["executed"] * 6 + ["not_applicable"]

    by_operator = {receipt.operator: receipt for receipt in trace.receipts}
    for receipt in trace.receipts[:6]:
        assert receipt.operator_instance_id is not None
        assert receipt.implementation_symbol
        assert receipt.implementation_source_sha256
        assert receipt.loaded_callable_code_sha256
        assert receipt.callable_symbol
        assert receipt.invocation_id
    assert [receipt.binding_kind for receipt in trace.receipts[:6]] == [
        "direct_operator_callable",
        "direct_operator_callable",
        "direct_operator_callable",
        "direct_operator_callable",
        "composite_operator_stage",
        "enclosing_runtime_stage",
    ]
    assert by_operator["ccrr"].implementation_symbol.endswith(".AutomaticCFBOCPDCCRRRouter")
    assert by_operator["rgrc"].implementation_symbol.endswith(".CorePrototypeSpine")
    ciav = by_operator["ciav"]
    assert ciav.operator_instance_id is None
    assert ciav.loaded_callable_code_sha256 is None
    assert ciav.callable_symbol is None
    assert ciav.invocation_id is None
    assert ciav.recomputed_reason == LEGACY_CIAV_NOT_APPLICABLE_REASON
    assert by_operator["pchmp"].consumed_output_ids == (by_operator["orrer_cheh"].output_id,)
    assert by_operator["cf_bocpd"].consumed_output_ids == (by_operator["pchmp"].output_id,)
    assert by_operator["ccrr"].consumed_output_ids == (
        by_operator["pchmp"].output_id,
        by_operator["cf_bocpd"].output_id,
    )
    assert by_operator["rgrc"].consumed_output_ids == (
        by_operator["opceu"].output_id,
        by_operator["pchmp"].output_id,
        by_operator["ccrr"].output_id,
    )


def test_receipts_hash_the_actual_bound_callable_inputs_and_outputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    system, transition = _system_and_transition()
    core = system.core
    router = core._automatic_regimes
    observed: dict[str, tuple[tuple[object, ...], dict[str, object], object]] = {}

    # A profiler observes the real class members; it does not replace any bound
    # production callable, and every content assertion below remains in force.
    import sys

    specifications = (
        ("opceu", core._corrector.weight_for_opportunity, ("record",), ()),
        (
            "orrer_cheh",
            core._event_engine.branch,
            (),
            (
                "before",
                "after",
                "actor_prior",
                "unresolved_probability",
                "allow_unknown_handoff_roles",
            ),
        ),
        ("pchmp", core._message_passing.consume, ("history", "evidence"), ()),
        ("cf_bocpd", router.bocpd.observe_online, ("frame",), ()),
        (
            "ccrr",
            router.observe,
            (),
            (
                "frame",
                "state_key",
                "context_features",
                "owner_probability",
                "evidence_source_record_ids",
                "identity_switch_probability",
                "stage_observer",
            ),
        ),
        ("rgrc", core._process_transition, ("transition",), ()),
    )
    codes = {
        method.__func__.__code__: (operator, positional, keywords)
        for operator, method, positional, keywords in specifications
    }

    def profile(frame, event, output):
        if event != "return" or frame.f_code not in codes:
            return
        operator, positional, keywords = codes[frame.f_code]
        values = frame.f_locals
        observed[operator] = (
            tuple(values[key] for key in positional),
            {key: values[key] for key in keywords},
            output,
        )

    sink = RecordingSink()
    previous = sys.getprofile()
    try:
        sys.setprofile(profile)
        system.process_transition(
            transition,
            execution_plan=canonical_legacy_ordinary_transition_plan(),
            trace_sink=sink,
        )
    finally:
        sys.setprofile(previous)
    by_operator = {receipt.operator: receipt for receipt in sink.traces[0].receipts}

    opceu_args, _, opceu_output = observed["opceu"]
    assert by_operator["opceu"].raw_input_sha256 == content_sha256(opceu_args[0])
    assert by_operator["opceu"].output_payload_sha256 == content_sha256(opceu_output)

    _, orrer_kwargs, orrer_output = observed["orrer_cheh"]
    assert by_operator["orrer_cheh"].raw_input_sha256 == content_sha256(orrer_kwargs)
    assert by_operator["orrer_cheh"].output_payload_sha256 == content_sha256(orrer_output)

    pchmp_args, _, pchmp_output = observed["pchmp"]
    assert by_operator["pchmp"].raw_input_sha256 == content_sha256(
        {"event_history": pchmp_args[0], "evidence": pchmp_args[1]}
    )
    assert by_operator["pchmp"].output_payload_sha256 == content_sha256(pchmp_output)

    cf_args, _, cf_output = observed["cf_bocpd"]
    assert by_operator["cf_bocpd"].raw_input_sha256 == content_sha256(cf_args[0])
    assert by_operator["cf_bocpd"].output_payload_sha256 == content_sha256(cf_output)

    _, ccrr_kwargs, ccrr_output = observed["ccrr"]
    ccrr_semantic_input = dict(ccrr_kwargs)
    ccrr_semantic_input.pop("stage_observer")
    ccrr_semantic_input["identity_switch_probability"] = 0.0
    assert by_operator["ccrr"].raw_input_sha256 == content_sha256(ccrr_semantic_input)
    assert by_operator["ccrr"].output_payload_sha256 == content_sha256(ccrr_output)

    rgrc_args, _, rgrc_output = observed["rgrc"]
    assert by_operator["rgrc"].raw_input_sha256 == content_sha256(rgrc_args[0])
    assert by_operator["rgrc"].output_payload_sha256 == content_sha256(rgrc_output)
    assert all("actual_callable" not in by_operator[name].callable_symbol for name in observed)
    assert len(observed) == 6


def test_public_operator_inventory_override_cannot_forge_the_called_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    system, transition = _system_and_transition()
    stale_inventory = system.runtime_operator_instances()
    stale_inventory["orrer_cheh"] = (
        CounterfactualEventHypergraphEngine(),
        system.feedback_revision_loop,
    )
    monkeypatch.setattr(system, "runtime_operator_instances", lambda: stale_inventory)
    sink = RecordingSink()

    system.process_transition(
        transition,
        execution_plan=canonical_legacy_ordinary_transition_plan(),
        trace_sink=sink,
    )

    orrer = sink.traces[0].receipts[1]
    assert orrer.implementation_symbol.endswith(
        ".OpenWorldRoleConditionedReversibleEventRevisionEngine"
    )
    assert orrer.callable_symbol is not None
    assert orrer.callable_symbol.endswith(
        ".OpenWorldRoleConditionedReversibleEventRevisionEngine.branch"
    )


def test_core_rejects_a_provider_not_bound_to_the_objects_it_will_call() -> None:
    system, transition = _system_and_transition()
    core = system.core
    stale_inventory = system.runtime_operator_instances()
    stale_inventory["orrer_cheh"] = (
        CounterfactualEventHypergraphEngine(),
        system.feedback_revision_loop,
    )
    before = _state_fingerprint(system)

    with pytest.raises(ValueError, match="not bound to the called orrer_cheh object"):
        core._process_transition_with_runtime_binding(
            transition,
            execution_plan=canonical_legacy_ordinary_transition_plan(),
            trace_sink=RecordingSink(),
            runtime_symbol="test.synthetic.Runtime",
            system_version="test@0.1",
            runtime_operator_instances_provider=lambda: stale_inventory,
            runtime_guard_components_provider=None,
            runtime_guard_state_provider=None,
            runtime_lock_components_provider=None,
        )

    assert _state_fingerprint(system) == before


def test_tamper_reorder_and_cross_run_splice_break_trace_verification() -> None:
    traces = []
    for _ in range(2):
        system, transition = _system_and_transition()
        sink = RecordingSink()
        system.process_transition(
            transition,
            execution_plan=canonical_legacy_ordinary_transition_plan(),
            trace_sink=sink,
        )
        traces.append(sink.traces[0])

    payload = traces[0].model_dump(mode="json")
    payload["receipts"][0]["output_payload_sha256"] = "0" * 64
    with pytest.raises(ValidationError, match="output identity mismatch"):
        StructureTwoExecutionTrace.model_validate(payload)

    payload = traces[0].model_dump(mode="json")
    payload["receipts"][0], payload["receipts"][1] = (
        payload["receipts"][1],
        payload["receipts"][0],
    )
    with pytest.raises(ValidationError):
        StructureTwoExecutionTrace.model_validate(payload)

    payload = traces[0].model_dump(mode="json")
    payload["receipts"][3] = traces[1].receipts[3].model_dump(mode="json")
    with pytest.raises(ValidationError):
        StructureTwoExecutionTrace.model_validate(payload)


@pytest.mark.parametrize("sink_type", [FailingSink, WrongAcknowledgementSink])
def test_sink_failure_or_wrong_ack_rolls_back_complete_transition_state(
    sink_type: type[Any],
) -> None:
    system, transition = _system_and_transition()
    before = _state_fingerprint(system)
    sink = sink_type()

    with pytest.raises((RuntimeError, ValidationError), match=r"trace sink|acknowledgement"):
        system.process_transition(
            transition,
            execution_plan=canonical_legacy_ordinary_transition_plan(),
            trace_sink=sink,
        )

    assert sink.calls == 1
    assert sink.aborted is True
    assert _state_fingerprint(system) == before
    assert system.core._execution_contract_active is False


def test_sink_reentrancy_is_rejected_without_a_second_state_transition() -> None:
    system, transition = _system_and_transition()

    class ReentrantSink:
        def __init__(self) -> None:
            self.error: RuntimeError | None = None

        def commit(self, trace: StructureTwoExecutionTrace, /) -> TraceCommitAck:
            try:
                system.process_transition(transition)
            except RuntimeError as error:
                self.error = error
            return seal_trace_commit_ack(trace)

        def abort(self, trace: StructureTwoExecutionTrace, /, *, reason: str) -> TraceAbortAck:
            return seal_trace_abort_ack(trace, reason=reason)

    sink = ReentrantSink()
    system.process_transition(
        transition,
        execution_plan=canonical_legacy_ordinary_transition_plan(),
        trace_sink=sink,
    )

    assert sink.error is not None
    assert "reentrant" in str(sink.error)
    assert system.observation_count == 1


def test_cross_thread_sink_callback_fails_fast_instead_of_deadlocking() -> None:
    system, transition = _system_and_transition()

    class CrossThreadSink(RecordingSink):
        def __init__(self) -> None:
            super().__init__()
            self.callback_error: BaseException | None = None
            self.callback_completed_during_commit = False
            self.callback_thread: Thread | None = None

        def commit(self, trace: StructureTwoExecutionTrace, /) -> TraceCommitAck:
            acknowledgement = super().commit(trace)

            def invoke_callback() -> None:
                try:
                    system.process_transition(transition)
                except BaseException as error:
                    self.callback_error = error

            self.callback_thread = Thread(target=invoke_callback, name="sink-callback")
            self.callback_thread.start()
            self.callback_thread.join(timeout=1.0)
            self.callback_completed_during_commit = not self.callback_thread.is_alive()
            return acknowledgement

    sink = CrossThreadSink()
    system.process_transition(
        transition,
        execution_plan=canonical_legacy_ordinary_transition_plan(),
        trace_sink=sink,
    )
    assert sink.callback_thread is not None
    sink.callback_thread.join(timeout=5.0)

    assert sink.callback_completed_during_commit is True
    assert isinstance(sink.callback_error, RuntimeError)
    assert "concurrent production execution" in str(sink.callback_error)
    assert system.observation_count == 1


def test_public_mutator_fails_fast_while_trace_sink_commit_is_in_progress() -> None:
    system, transition = _system_and_transition()
    sink_entered = Event()
    release_sink = Event()
    transition_errors: list[BaseException] = []
    mutator_errors: list[BaseException] = []

    class PausingSink(RecordingSink):
        def commit(self, trace: StructureTwoExecutionTrace, /) -> TraceCommitAck:
            acknowledgement = super().commit(trace)
            sink_entered.set()
            assert release_sink.wait(timeout=5.0)
            return acknowledgement

    def run_transition() -> None:
        try:
            system.process_transition(
                transition,
                execution_plan=canonical_legacy_ordinary_transition_plan(),
                trace_sink=PausingSink(),
            )
        except BaseException as error:
            transition_errors.append(error)

    def run_mutator() -> None:
        try:
            assert transition.after.detection_time is not None
            system.switch_regime(
                "concurrent-mutator-regime",
                event_time=transition.after.detection_time + timedelta(seconds=1),
            )
        except BaseException as error:
            mutator_errors.append(error)

    transition_thread = Thread(target=run_transition, name="traced-transition")
    transition_thread.start()
    assert sink_entered.wait(timeout=5.0)

    mutator_thread = Thread(target=run_mutator, name="public-mutator")
    mutator_thread.start()
    mutator_thread.join(timeout=1.0)
    completed_during_commit = not mutator_thread.is_alive()
    release_sink.set()
    transition_thread.join(timeout=5.0)
    mutator_thread.join(timeout=5.0)

    assert completed_during_commit is True
    assert transition_errors == []
    assert len(mutator_errors) == 1
    assert isinstance(mutator_errors[0], RuntimeError)
    assert "runtime mutation is forbidden" in str(mutator_errors[0])
    assert system.observation_count == 1


@pytest.mark.parametrize(
    "disabled_field",
    ["cause_factorized_bocpd_enabled", "ccrr_enabled"],
)
def test_trace_rejects_disabled_operator_configuration_before_state_change(
    disabled_field: str,
) -> None:
    system, transition = _system_and_transition()
    system.core.loop_config = replace(system.core.loop_config, **{disabled_field: False})
    before = _state_fingerprint(system)
    sink = RecordingSink()

    with pytest.raises(UnsupportedStructureTwoExecutionPlan, match="requires CF-BOCPD"):
        system.process_transition(
            transition,
            execution_plan=canonical_legacy_ordinary_transition_plan(),
            trace_sink=sink,
        )

    assert _state_fingerprint(system) == before
    assert sink.traces == []


def test_trace_rejects_disabled_rgrc_gate_before_state_change() -> None:
    system, transition = _system_and_transition()
    system.core._rgrc_gate_enabled = False
    before = _state_fingerprint(system)
    sink = RecordingSink()

    with pytest.raises(UnsupportedStructureTwoExecutionPlan, match="requires CF-BOCPD"):
        system.process_transition(
            transition,
            execution_plan=canonical_legacy_ordinary_transition_plan(),
            trace_sink=sink,
        )

    assert _state_fingerprint(system) == before
    assert sink.traces == []


def test_sink_state_mutation_is_detected_tombstoned_and_rolled_back() -> None:
    system, transition = _system_and_transition()
    before = _state_fingerprint(system)

    class MutatingSink(RecordingSink):
        def commit(self, trace: StructureTwoExecutionTrace, /) -> TraceCommitAck:
            acknowledgement = super().commit(trace)
            assert transition.after.detection_time is not None
            system.switch_regime(
                "sink-mutated-regime",
                event_time=transition.after.detection_time + timedelta(seconds=1),
            )
            return acknowledgement

    sink = MutatingSink()
    with pytest.raises(RuntimeError, match="runtime mutation is forbidden"):
        system.process_transition(
            transition,
            execution_plan=canonical_legacy_ordinary_transition_plan(),
            trace_sink=sink,
        )

    assert sink.traces == []
    assert len(sink.aborted) == 1
    assert _state_fingerprint(system) == before


def test_sink_cannot_mutate_the_sealed_trace_before_acknowledging_it() -> None:
    system, transition = _system_and_transition()
    before = _state_fingerprint(system)

    class TraceMutatingSink(RecordingSink):
        def commit(self, trace: StructureTwoExecutionTrace, /) -> TraceCommitAck:
            self.traces.append(trace)
            object.__setattr__(trace, "runtime_symbol", "sink.forged.Runtime")
            return seal_trace_commit_ack(trace)

    sink = TraceMutatingSink()
    with pytest.raises(RuntimeError, match="mutated the sealed execution trace"):
        system.process_transition(
            transition,
            execution_plan=canonical_legacy_ordinary_transition_plan(),
            trace_sink=sink,
        )

    assert sink.traces == []
    assert len(sink.aborted) == 1
    verify_execution_trace(sink.aborted[0])
    assert _state_fingerprint(system) == before


def test_unverified_sink_compensation_is_explicit_while_model_state_rolls_back() -> None:
    system, transition = _system_and_transition()
    before = _state_fingerprint(system)
    sink = UncompensatableSink()

    with pytest.raises(TraceCompensationError, match="tombstone acknowledgement"):
        system.process_transition(
            transition,
            execution_plan=canonical_legacy_ordinary_transition_plan(),
            trace_sink=sink,
        )

    assert sink.trace is not None
    assert _state_fingerprint(system) == before
    assert system.core._execution_contract_active is False


def test_abort_cannot_mutate_the_only_trace_snapshot_and_acknowledge_a_different_hash() -> None:
    system, transition = _system_and_transition()
    before = _state_fingerprint(system)
    committed_trace_sha256: str | None = None

    class AbortTraceMutatingSink(RecordingSink):
        def commit(self, trace: StructureTwoExecutionTrace, /) -> TraceCommitAck:
            nonlocal committed_trace_sha256
            committed_trace_sha256 = trace.trace_sha256
            raise RuntimeError("injected commit failure")

        def abort(self, trace: StructureTwoExecutionTrace, /, *, reason: str) -> TraceAbortAck:
            object.__setattr__(trace, "trace_sha256", "0" * 64)
            return seal_trace_abort_ack(trace, reason=reason)

    with pytest.raises(TraceCompensationError, match="tombstone acknowledgement"):
        system.process_transition(
            transition,
            execution_plan=canonical_legacy_ordinary_transition_plan(),
            trace_sink=AbortTraceMutatingSink(),
        )

    assert committed_trace_sha256 is not None
    assert committed_trace_sha256 != "0" * 64
    assert _state_fingerprint(system) == before


@pytest.mark.parametrize(
    "mutation",
    [
        "configuration",
        "component",
        "fusion_configuration",
        "feedback_projector_state",
        "execution_lock",
    ],
)
def test_sink_configuration_or_component_replacement_is_aborted_and_rolled_back(
    mutation: str,
) -> None:
    system, transition = _system_and_transition()
    core = system.core
    before = _state_fingerprint(system)
    original_loop_config = core.loop_config
    original_event_engine = core._event_engine
    original_message_passing = core._message_passing
    original_corrector = core._corrector
    original_habit = core._habit
    original_regimes = core._regimes
    original_router = core._automatic_regimes
    original_bocpd = original_router.bocpd
    original_ccrr = original_router.ccrr
    original_hybrid_loop = core._hybrid_loop
    original_ledger = original_hybrid_loop.ledger
    original_map = original_hybrid_loop._map
    original_coordinator = original_hybrid_loop._coordinator
    original_hybrid_projector = original_hybrid_loop._feedback_projector
    original_fusion = original_hybrid_loop._fusion
    original_fusion_probability_floor = core._hybrid_loop._fusion.probability_floor
    original_projector_seen = dict(core._hybrid_loop._feedback_projector._seen)
    original_execution_lock = core._execution_lock

    class MutatingSink(RecordingSink):
        def commit(self, trace: StructureTwoExecutionTrace, /) -> TraceCommitAck:
            acknowledgement = super().commit(trace)
            if mutation == "configuration":
                core.loop_config = replace(
                    core.loop_config,
                    confirmation_window=core.loop_config.confirmation_window + 7,
                )
            elif mutation == "component":
                core._event_engine = type(core._event_engine)()
            elif mutation == "fusion_configuration":
                core._hybrid_loop._fusion.probability_floor = 0.2
            elif mutation == "feedback_projector_state":
                core._hybrid_loop._feedback_projector._seen[UUID(int=0)] = (  # type: ignore[assignment]
                    "mutated",
                    "during",
                    "commit",
                )
            else:
                core._execution_lock = RLock()
            return acknowledgement

    sink = MutatingSink()
    with pytest.raises(RuntimeError, match=r"mutated audited core state|replaced an audited"):
        system.process_transition(
            transition,
            execution_plan=canonical_legacy_ordinary_transition_plan(),
            trace_sink=sink,
        )

    assert sink.traces == []
    assert len(sink.aborted) == 1
    assert core.loop_config is original_loop_config
    assert core._event_engine is original_event_engine
    assert core._message_passing is original_message_passing
    assert core._corrector is original_corrector
    assert core._habit is original_habit
    assert core._regimes is original_regimes
    assert core._automatic_regimes is original_router
    assert core._automatic_regimes.bocpd is original_bocpd
    assert core._automatic_regimes.ccrr is original_ccrr
    assert core._hybrid_loop is original_hybrid_loop
    assert core._hybrid_loop.ledger is original_ledger
    assert core._hybrid_loop._map is original_map
    assert core._hybrid_loop._coordinator is original_coordinator
    assert core._hybrid_loop._feedback_projector is original_hybrid_projector
    assert core._hybrid_loop._fusion is original_fusion
    assert core._hybrid_loop._fusion.probability_floor == original_fusion_probability_floor
    assert core._hybrid_loop._feedback_projector._seen == original_projector_seen
    assert core._execution_lock is original_execution_lock
    assert _state_fingerprint(system) == before


@pytest.mark.parametrize(
    "mutation",
    [
        "core",
        "feedback_revision_loop",
        "cause_information_planner",
        "ciav_opceu_loop",
        "execution_lock",
        "planner_state",
        "feedback_engine_version",
        "feedback_projector_state",
        "evidence_trace_state",
    ],
)
def test_sink_production_wrapper_mutation_is_aborted_and_rolled_back(mutation: str) -> None:
    system, transition = _system_and_transition()
    donor, _ = _system_and_transition()
    original_core = system.core
    original_feedback_loop = system.feedback_revision_loop
    original_feedback_projector = original_feedback_loop._projector
    original_feedback_engine = original_feedback_loop._engine
    original_planner = system.cause_information_planner
    original_ciav_loop = system.ciav_opceu_loop
    original_evidence_trace = original_ciav_loop.trace
    original_execution_lock = system._execution_lock
    original_wrapper_state = system._execution_guard_state_sha256()

    class MutatingSink(RecordingSink):
        def commit(self, trace: StructureTwoExecutionTrace, /) -> TraceCommitAck:
            acknowledgement = super().commit(trace)
            if mutation == "core":
                system.core = donor.core
            elif mutation == "feedback_revision_loop":
                system.feedback_revision_loop = donor.feedback_revision_loop
            elif mutation == "cause_information_planner":
                system.cause_information_planner = donor.cause_information_planner
            elif mutation == "ciav_opceu_loop":
                system.ciav_opceu_loop = donor.ciav_opceu_loop
            elif mutation == "execution_lock":
                system._execution_lock = RLock()
            elif mutation == "planner_state":
                system.cause_information_planner.task_utility_weight += 0.5
            elif mutation == "feedback_engine_version":
                system.feedback_revision_loop._engine.engine_version = "sink-mutated"
            elif mutation == "feedback_projector_state":
                system.feedback_revision_loop._projector._seen[UUID(int=0)] = (  # type: ignore[assignment]
                    "mutated",
                    "during",
                    "commit",
                )
            else:
                system.ciav_opceu_loop.trace._record_payload_hashes[UUID(int=0)] = "0" * 64
            return acknowledgement

    sink = MutatingSink()
    with pytest.raises(
        RuntimeError,
        match=(
            r"mutated audited core state"
            if mutation == "feedback_engine_version"
            else r"replaced an audited runtime component|mutated audited production-wrapper state"
        ),
    ):
        system.process_transition(
            transition,
            execution_plan=canonical_legacy_ordinary_transition_plan(),
            trace_sink=sink,
        )

    assert sink.traces == []
    assert len(sink.aborted) == 1
    assert system.core is original_core
    assert system.feedback_revision_loop is original_feedback_loop
    assert system.feedback_revision_loop._projector is original_feedback_projector
    assert system.feedback_revision_loop._engine is original_feedback_engine
    assert system.cause_information_planner is original_planner
    assert system.ciav_opceu_loop is original_ciav_loop
    assert system.ciav_opceu_loop.trace is original_evidence_trace
    assert system._execution_lock is original_execution_lock
    assert system._execution_guard_state_sha256() == original_wrapper_state


@pytest.mark.parametrize(
    "mutation",
    [
        "core_release",
        "core_acquire",
        "wrapper_release",
        "wrapper_acquire",
        "ccrr_acquire",
        "ledger_acquire",
        "map_acquire",
    ],
)
def test_sink_lock_ownership_mutation_is_aborted_normalized_and_rolled_back(
    mutation: str,
) -> None:
    system, transition = _system_and_transition()
    core = system.core
    before = _state_fingerprint(system)
    locks = {
        "core": core._execution_lock,
        "wrapper": system._execution_lock,
        "ccrr": core._automatic_regimes.ccrr._lock,
        "ledger": core._hybrid_loop.ledger._lock,
        "map": core._hybrid_loop._map._lock,
    }

    class LockMutatingSink(RecordingSink):
        def commit(self, trace: StructureTwoExecutionTrace, /) -> TraceCommitAck:
            acknowledgement = super().commit(trace)
            target, operation = mutation.split("_", maxsplit=1)
            lock = locks[target]
            if operation == "release":
                lock.release()
            else:
                assert lock.acquire()
            return acknowledgement

    sink = LockMutatingSink()
    with pytest.raises(RuntimeError, match=r"runtime-lock|production-wrapper state"):
        system.process_transition(
            transition,
            execution_plan=canonical_legacy_ordinary_transition_plan(),
            trace_sink=sink,
        )

    assert sink.traces == []
    assert len(sink.aborted) == 1
    assert _state_fingerprint(system) == before
    assert all(lock._recursion_count() == 0 for lock in locks.values())  # type: ignore[attr-defined]


@pytest.mark.parametrize("target", ["core", "wrapper"])
def test_sink_cannot_swap_an_in_place_attestation_verifier_key(target: str) -> None:
    system, transition = _system_and_transition()
    original_authority = Ed25519AttestationSigner.generate(key_id="stable-key").verifier()
    replacement_authority = Ed25519AttestationSigner.generate(key_id="stable-key").verifier()
    if target == "core":
        message_passing = system.core._message_passing
    else:
        message_passing = system.feedback_revision_loop._message_passing
    message_passing._independence_authority = original_authority
    original_public_key_sha256 = original_authority.public_key_sha256
    before = _state_fingerprint(system)

    class KeyMutatingSink(RecordingSink):
        def commit(self, trace: StructureTwoExecutionTrace, /) -> TraceCommitAck:
            acknowledgement = super().commit(trace)
            original_authority._public_key = replacement_authority._public_key
            return acknowledgement

    sink = KeyMutatingSink()
    with pytest.raises(
        RuntimeError,
        match=r"mutated audited core state|mutated audited production-wrapper state",
    ):
        system.process_transition(
            transition,
            execution_plan=canonical_legacy_ordinary_transition_plan(),
            trace_sink=sink,
        )

    assert sink.traces == []
    assert len(sink.aborted) == 1
    assert message_passing._independence_authority is original_authority
    assert original_authority.public_key_sha256 == original_public_key_sha256
    assert _state_fingerprint(system) == before


def test_abort_lock_mutation_is_not_accepted_as_successful_compensation() -> None:
    system, transition = _system_and_transition()
    before = _state_fingerprint(system)

    class AbortLockMutatingSink(RecordingSink):
        def commit(self, trace: StructureTwoExecutionTrace, /) -> TraceCommitAck:
            self.traces.append(trace)
            raise RuntimeError("injected commit failure")

        def abort(self, trace: StructureTwoExecutionTrace, /, *, reason: str) -> TraceAbortAck:
            self.traces = []
            assert system.core._execution_lock.acquire()
            return seal_trace_abort_ack(trace, reason=reason)

    with pytest.raises(TraceCompensationError, match="tombstone acknowledgement"):
        system.process_transition(
            transition,
            execution_plan=canonical_legacy_ordinary_transition_plan(),
            trace_sink=AbortLockMutatingSink(),
        )

    assert system.core._execution_lock._recursion_count() == 0  # type: ignore[attr-defined]
    assert _state_fingerprint(system) == before


def test_abort_cannot_temporarily_release_the_production_serialization_lock() -> None:
    system, transition = _system_and_transition()
    before = _state_fingerprint(system)

    class AbortWrapperLockMutatingSink(RecordingSink):
        def commit(self, trace: StructureTwoExecutionTrace, /) -> TraceCommitAck:
            raise RuntimeError("injected commit failure")

        def abort(self, trace: StructureTwoExecutionTrace, /, *, reason: str) -> TraceAbortAck:
            system._execution_lock.release()
            return seal_trace_abort_ack(trace, reason=reason)

    with pytest.raises(TraceCompensationError, match="tombstone acknowledgement"):
        system.process_transition(
            transition,
            execution_plan=canonical_legacy_ordinary_transition_plan(),
            trace_sink=AbortWrapperLockMutatingSink(),
        )

    assert system._execution_lock._recursion_count() == 0  # type: ignore[attr-defined]
    assert _state_fingerprint(system) == before


def test_commit_keyboard_interrupt_is_compensated_and_model_state_is_rolled_back() -> None:
    system, transition = _system_and_transition()
    before = _state_fingerprint(system)

    class InterruptingSink(RecordingSink):
        def commit(self, trace: StructureTwoExecutionTrace, /) -> TraceCommitAck:
            self.traces.append(trace)
            raise KeyboardInterrupt

    sink = InterruptingSink()
    with pytest.raises(KeyboardInterrupt):
        system.process_transition(
            transition,
            execution_plan=canonical_legacy_ordinary_transition_plan(),
            trace_sink=sink,
        )

    assert sink.traces == []
    assert len(sink.aborted) == 1
    assert _state_fingerprint(system) == before


def test_operator_keyboard_interrupt_rolls_back_without_attempting_sink_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    system, transition = _system_and_transition()
    core = system.core
    original = core._process_transition

    import sys

    def interrupt_after_transition(frame, event, _value):
        if frame.f_code is original.__func__.__code__ and event == "return":
            raise KeyboardInterrupt

    before = _state_fingerprint(system)
    sink = RecordingSink()
    previous = sys.getprofile()
    try:
        sys.setprofile(interrupt_after_transition)
        with pytest.raises(KeyboardInterrupt):
            system.process_transition(
                transition,
                execution_plan=canonical_legacy_ordinary_transition_plan(),
                trace_sink=sink,
            )
    finally:
        sys.setprofile(previous)

    assert sink.traces == []
    assert _state_fingerprint(system) == before


def test_runtime_lock_prevents_a_stale_concurrent_checkpoint_from_erasing_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    system, transition = _system_and_transition()
    core = system.core
    original_capture = core._capture_revision_transaction
    stale_checkpoint_captured = Event()
    release_stale_call = Event()

    def gated_capture(*, include_operator_state: bool = False) -> dict[str, object]:
        checkpoint = original_capture(include_operator_state=include_operator_state)
        if current_thread().name == "stale-checkpoint-call":
            stale_checkpoint_captured.set()
            assert release_stale_call.wait(timeout=5.0)
        return checkpoint

    monkeypatch.setattr(core, "_capture_revision_transaction", gated_capture)
    outcomes: list[tuple[str, BaseException | None]] = []

    def invoke(name: str, sink: RecordingSink) -> None:
        try:
            system.process_transition(
                transition,
                execution_plan=canonical_legacy_ordinary_transition_plan(),
                trace_sink=sink,
            )
        except BaseException as error:
            outcomes.append((name, error))
        else:
            outcomes.append((name, None))

    first_sink = RecordingSink()
    second_sink = RecordingSink()
    first = Thread(
        target=invoke,
        args=("first", first_sink),
        name="stale-checkpoint-call",
    )
    second = Thread(target=invoke, args=("second", second_sink), name="concurrent-call")
    first.start()
    assert stale_checkpoint_captured.wait(timeout=5.0)
    # The first call has captured its checkpoint but still owns the runtime
    # lock, so a second transition cannot capture a competing stale snapshot.
    lock_was_available = core._execution_lock.acquire(blocking=False)
    if lock_was_available:
        core._execution_lock.release()
    assert lock_was_available is False
    second.start()
    release_stale_call.set()
    first.join(timeout=5.0)
    second.join(timeout=5.0)

    assert not first.is_alive()
    assert not second.is_alive()
    assert sorted(name for name, error in outcomes if error is None) == ["first"]
    failures = [error for _, error in outcomes if error is not None]
    assert len(failures) == 1
    assert isinstance(failures[0], RuntimeError)
    assert "concurrent production execution" in str(failures[0])
    assert system.observation_count == 1
    assert len(first_sink.traces) == 1
    assert second_sink.traces == []


def test_direct_core_entrypoint_uses_the_same_contract_without_claiming_production_runtime() -> (
    None
):
    system, transition = _system_and_transition()
    sink = RecordingSink()
    result = system.core.process_transition(
        transition,
        execution_plan=canonical_legacy_ordinary_transition_plan(),
        trace_sink=sink,
    )

    assert result.event_revision_id == result.event_history.latest.revision_id
    assert sink.traces[0].runtime_symbol.endswith(".CorePrototypeSpine")
    assert sink.traces[0].adaptive_legal_path_executed is False


@pytest.mark.parametrize("mutation", ["bocpd_reset_matrix", "ccrr_threshold"])
def test_sink_cannot_mutate_live_operator_configuration_in_place(mutation: str) -> None:
    system, transition = _system_and_transition()
    core = system.core
    reset_matrix = core._automatic_regimes.bocpd._reset_matrix
    ccrr = core._automatic_regimes.ccrr
    before = _state_fingerprint(system)
    before_reset = dict(reset_matrix._matrix)
    before_threshold = ccrr.change_threshold

    class ConfigurationMutatingSink(RecordingSink):
        def commit(self, trace: StructureTwoExecutionTrace, /) -> TraceCommitAck:
            acknowledgement = super().commit(trace)
            if mutation == "bocpd_reset_matrix":
                reset_matrix._matrix[ChangeCause.HABIT] = frozenset()
            else:
                ccrr.change_threshold = 0.99
            return acknowledgement

    sink = ConfigurationMutatingSink()
    with pytest.raises(RuntimeError, match="mutated audited core state"):
        system.process_transition(
            transition,
            execution_plan=canonical_legacy_ordinary_transition_plan(),
            trace_sink=sink,
        )

    assert sink.traces == []
    assert len(sink.aborted) == 1
    assert core._automatic_regimes.bocpd._reset_matrix is reset_matrix
    assert core._automatic_regimes.ccrr is ccrr
    assert reset_matrix._matrix == before_reset
    assert ccrr.change_threshold == before_threshold
    assert _state_fingerprint(system) == before


@pytest.mark.parametrize("mutation", ["head_copy", "model_config", "commit_failure"])
def test_preexisting_rls_graph_is_guarded_and_rolled_back_in_place(mutation: str) -> None:
    system, transition = _system_and_transition()
    core = system.core
    regime_id, head, models, model_key, wrapper = _seed_preexisting_rls_graph(system)
    model = wrapper.model
    config = model.config
    theta = model.theta
    covariance = model.covariance
    before = _state_fingerprint(system)

    class RLSMutatingSink(RecordingSink):
        def commit(self, trace: StructureTwoExecutionTrace, /) -> TraceCommitAck:
            if mutation == "head_copy":
                core._regimes._heads[regime_id] = deepcopy(head)
                return seal_trace_commit_ack(trace)
            if mutation == "model_config":
                model._config = replace(config, clip_theta=0.0)
                return seal_trace_commit_ack(trace)
            raise RuntimeError("injected commit failure")

    sink = RLSMutatingSink()
    expected_exception = RuntimeError
    with pytest.raises(expected_exception):
        system.process_transition(
            transition,
            execution_plan=canonical_legacy_ordinary_transition_plan(),
            trace_sink=sink,
        )

    assert core._regimes._heads[regime_id] is head
    assert head._models is models
    assert head._models[model_key] is wrapper
    assert wrapper.model is model
    assert model.config is config
    assert model.theta is theta
    assert model.covariance is covariance
    assert model.config.clip_theta == 10.0
    assert _state_fingerprint(system) == before


@pytest.mark.parametrize(
    "mutation",
    ["head_factory_configuration", "habit_row_copy", "receipt_row_copy"],
)
def test_factory_configuration_and_nested_rows_are_guarded_and_restored(mutation: str) -> None:
    system, transition = _system_and_transition()
    core = system.core
    head_factory = core._regimes._head_factory
    person_table = core._habit._person_counts
    person_key = (
        transition.after.metadata.household_id,
        core.owner_key,
        core.object_instance_id,
    )
    person_row: dict[UUID, float] = {}
    person_table[person_key] = person_row
    receipt_table = core._project_one_application_receipts
    receipt_key = UUID(int=913)
    receipt_row: list[Any] = []
    receipt_table[receipt_key] = receipt_row
    original_head_dimension = head_factory.location_embedding_dim
    before = _state_fingerprint(system)

    class FactoryMutatingSink(RecordingSink):
        def commit(self, trace: StructureTwoExecutionTrace, /) -> TraceCommitAck:
            acknowledgement = super().commit(trace)
            if mutation == "head_factory_configuration":
                object.__setattr__(head_factory, "location_embedding_dim", 2)
            elif mutation == "habit_row_copy":
                person_table[person_key] = deepcopy(person_row)
            else:
                receipt_table[receipt_key] = deepcopy(receipt_row)
            return acknowledgement

    sink = FactoryMutatingSink()
    with pytest.raises(RuntimeError, match=r"mutated audited core state|replaced an audited"):
        system.process_transition(
            transition,
            execution_plan=canonical_legacy_ordinary_transition_plan(),
            trace_sink=sink,
        )

    assert sink.traces == []
    assert len(sink.aborted) == 1
    assert core._regimes._head_factory is head_factory
    assert head_factory.location_embedding_dim == original_head_dimension
    assert core._habit._person_counts is person_table
    assert person_table[person_key] is person_row
    assert core._project_one_application_receipts is receipt_table
    assert receipt_table[receipt_key] is receipt_row
    assert _state_fingerprint(system) == before


def test_habit_count_reads_use_plain_dicts_without_callable_default_factories() -> None:
    system, _ = _system_and_transition()
    core = system.core
    tables = (
        core._habit._household_counts,
        core._habit._person_counts,
        core._habit._context_counts,
        core._habit._isolated_nonresident_counts,
    )
    before = tuple(dict(table) for table in tables)

    assert (
        core._habit.known_person_count(
            household_id=UUID(int=1),
            person_id="unknown-person",
            object_instance_id=core.object_instance_id,
            location_id=core.locations[0],
        )
        == 0.0
    )
    assert (
        core._habit.isolated_nonresident_count(
            household_id=UUID(int=1),
            object_instance_id=core.object_instance_id,
            location_id=core.locations[0],
        )
        == 0.0
    )
    assert all(type(table) is dict for table in tables)
    assert tuple(dict(table) for table in tables) == before


def test_legacy_failure_rollback_preserves_public_operator_instance_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    system, transition = _system_and_transition()
    before_instances = system.runtime_operator_instances()

    def fail_after_rls(stage: str) -> None:
        if stage == "rls":
            raise RuntimeError("injected legacy failure")

    monkeypatch.setattr(system.core, "_transition_fault_hook", fail_after_rls)
    before_state = _state_fingerprint(system)
    with pytest.raises(RuntimeError, match="injected legacy failure"):
        system.process_transition(transition)

    after_instances = system.runtime_operator_instances()
    assert tuple(after_instances) == tuple(before_instances)
    for operator in before_instances:
        assert len(after_instances[operator]) == len(before_instances[operator])
        assert all(
            after is before
            for after, before in zip(
                after_instances[operator], before_instances[operator], strict=True
            )
        )
    assert _state_fingerprint(system) == before_state


@pytest.mark.parametrize("failure_type", [KeyboardInterrupt, SystemExit])
def test_legacy_base_exception_rolls_back_complete_state_and_instance_identity(
    monkeypatch: pytest.MonkeyPatch,
    failure_type: type[BaseException],
) -> None:
    system, transition = _system_and_transition()
    before_instances = system.runtime_operator_instances()

    def interrupt_after_rls(stage: str) -> None:
        if stage == "rls":
            raise failure_type

    monkeypatch.setattr(system.core, "_transition_fault_hook", interrupt_after_rls)
    before_state = _state_fingerprint(system)
    with pytest.raises(failure_type):
        system.process_transition(transition)

    after_instances = system.runtime_operator_instances()
    assert all(
        after is before
        for operator in before_instances
        for after, before in zip(after_instances[operator], before_instances[operator], strict=True)
    )
    assert _state_fingerprint(system) == before_state


@pytest.mark.parametrize("lock_target", ["core", "wrapper", "ccrr"])
def test_cross_thread_lock_handoff_fails_without_waiting_for_foreign_release(
    lock_target: str,
) -> None:
    system, transition = _system_and_transition()
    before_state = _state_fingerprint(system)
    target_lock = {
        "core": system.core._execution_lock,
        "wrapper": system._execution_lock,
        "ccrr": system.core._automatic_regimes.ccrr._lock,
    }[lock_target]
    worker_has_lock = Event()
    release_worker = Event()
    worker: Thread | None = None

    class LockHandoffSink(RecordingSink):
        def commit(self, trace: StructureTwoExecutionTrace, /) -> TraceCommitAck:
            nonlocal worker
            acknowledgement = super().commit(trace)
            if lock_target != "ccrr":
                target_lock.release()

            def hold_lock() -> None:
                with target_lock:
                    worker_has_lock.set()
                    assert release_worker.wait(timeout=5.0)

            worker = Thread(target=hold_lock, daemon=True)
            worker.start()
            assert worker_has_lock.wait(timeout=5.0)
            return acknowledgement

    sink = LockHandoffSink()
    outcome: list[BaseException | None] = []

    def invoke() -> None:
        try:
            system.process_transition(
                transition,
                execution_plan=canonical_legacy_ordinary_transition_plan(),
                trace_sink=sink,
            )
        except BaseException as error:
            outcome.append(error)
        else:
            outcome.append(None)

    caller = Thread(target=invoke, daemon=True)
    caller.start()
    try:
        caller.join(timeout=1.0)
        assert not caller.is_alive(), "transaction waited for a foreign lock owner"
        assert len(outcome) == 1
        assert isinstance(outcome[0], RuntimeError)
        assert sink.traces == []
        assert len(sink.aborted) == 1
    finally:
        release_worker.set()
        if worker is not None:
            worker.join(timeout=5.0)
        caller.join(timeout=5.0)
    assert not caller.is_alive()
    assert worker is not None and not worker.is_alive()
    assert target_lock.acquire(blocking=False) is True
    target_lock.release()
    assert _state_fingerprint(system) == before_state


def test_callable_binding_rejects_disk_source_drift_from_loaded_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_path = tmp_path / "drifted_operator.py"
    module_path.write_text(
        "class Operator:\n    def invoke(self):\n        return 'loaded'\n",
        encoding="utf-8",
    )
    spec = importlib.util.spec_from_file_location("drifted_operator", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "drifted_operator", module)
    spec.loader.exec_module(module)
    operator = module.Operator()
    module_path.write_text(
        "class Operator:\n    def invoke(self):\n        return 'disk'\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="does not match the current source file"):
        bind_runtime_callable(
            runtime_execution_id=UUID("00000000-0000-4000-8000-000000000991"),
            operator="opceu",
            binding_slot=0,
            binding_kind="direct_operator_callable",
            instance=operator,
            callable_name="invoke",
        )
