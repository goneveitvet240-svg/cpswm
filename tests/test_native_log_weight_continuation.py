"""Legal finite-density underflow, exact owner priors, replay and fresh recovery.

Synthetic pixels/position models and real small neural checkpoints. These tests
change fixture configuration before owner creation, never a scientific model.
PYTEST_DONT_REWRITE: fixture helpers take part in source-bound recovery.
"""

from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from math import isfinite

import pytest
import test_native_position_production as fixture
import test_native_raw_candidate_verification as recovery
from test_native_neural_production import checkpoints as _checkpoints
from test_native_neural_production import context_for, stage
from test_native_neural_production import cpu_threads as _cpu_threads
from test_unity_rgbd import event_for

from cpswm.perception_mapping import position_observation_model as position
from cpswm.system.native_neural_production import verify_neural_evidence
from cpswm.system.structure_two_particle_workspace import (
    NativePreviousWeightEvidence,
    native_content_sha256,
)

checkpoints = _checkpoints
cpu_threads = _cpu_threads


@pytest.fixture(params=["known", "unknown_and_aggregate"])
def stress(request, monkeypatch):
    original_models, original_packet = fixture.fixture_models, fixture.packet

    def models():
        value = deepcopy(original_models())
        value["position_model"]["bias"] = (
            [100.0, 0.0, 0.0] if request.param == "known" else [1000.0, 0.0, 0.0]
        )
        value["position_pin"] = position.checkpoint_sha256(value["position_model"])
        position.restore(value["position_model"], value["position_pin"])
        return value

    def packet(**kwargs):
        event = event_for()
        if request.param == "unknown_and_aggregate":
            event.metadata["cameraPosition"]["x"] = 1000.0
        return original_packet(event=event, **kwargs)

    monkeypatch.setattr(fixture, "fixture_models", models)
    monkeypatch.setattr(fixture, "packet", packet)
    return request.param


def log_state(case):
    workspace = case["stream"]._system.core._particle_workspace
    evidence = workspace.previous_weight_evidence(workspace.batch)
    logs, aggregate = evidence.normalized_logs()
    assert len(logs) == len(workspace.batch.particle_weights) == 2
    assert all(row.accepted for row in workspace.batch.particle_weights)
    return {
        workspace.records[key].state.instance_association_key == "unknown_instance": value
        for key, value in logs.items()
    } | {"aggregate": aggregate}


def test_finite_log_mass_and_all_support_survive_neutral_steps(tmp_path, checkpoints, stress):
    case = fixture.scenario(tmp_path / "finite.db", checkpoints)
    try:
        fixture.advance(case, 0)
        initial = log_state(case)
        weights = fixture.weight_state(case)
        key = stress != "known"
        assert weights[key][0] == 0.0 and isfinite(initial[key]) and initial[key] < -745
        if key:
            assert weights["aggregate"] == 0.0 and initial["aggregate"] < -745
        for index in (1, 2):
            fixture.advance(case, index)
            assert log_state(case) == pytest.approx(initial, abs=1e-12)
            workspace = case["stream"]._system.core._particle_workspace
            assert len(workspace.receipts) == 2
            assert all(isfinite(row.prior_log_weight) for row in workspace.receipts)
            proof = next(reversed(workspace.input_bodies.values())).neural_evidence
            assert len(proof.support) == len(proof.scored) == 2
            assert len(case["candidate"].consumed_keys) == 1
            before = fixture.snapshot(case), case["joint"].checkpoint_state()
            case["stream"].produce_joint_posterior()
            assert (fixture.snapshot(case), case["joint"].checkpoint_state()) == before
    finally:
        case["store"].close()


def test_underflow_fresh_process_restore_and_next_neutral(tmp_path, checkpoints, stress):
    recovery.test_fresh_process_resume_without_constructing_another_stream(tmp_path, checkpoints)


def test_underflow_retraction_replay_matches_no_factor(tmp_path, checkpoints, stress):
    fixture.test_retraction_full_replay_matches_no_factor_and_survives_sqlite(tmp_path, checkpoints)


def test_complete_previous_evidence_shift_rejected_then_legal(tmp_path, checkpoints):
    case = fixture.scenario(tmp_path / "shift.db", checkpoints)
    try:
        fixture.advance(case, 0)
        when = fixture.advance(case, 1, publish=False)
        context = context_for(case["stream"], when)
        original = context.previous_weight_evidence
        # A common additive shift preserves every normalized weight. It is a
        # complete alternative prior with correct q, not an incomplete field edit.
        shifted = NativePreviousWeightEvidence(
            tuple(
                row.model_copy(update={"prior_log_weight": row.prior_log_weight + 2.0})
                for row in original.receipts
            ),
            original.unresolved_log_weight + 2.0,
        )
        assert shifted.batch() == context.previous_batch
        altered = replace(context, previous_weight_evidence=shifted)
        before = fixture.snapshot(case)
        initial = case["joint"].checkpoint_state()
        forged = case["joint"].produce(altered)
        verify_neural_evidence(forged.neural_evidence)
        with pytest.raises(ValueError, match="not admitted by the owner"):
            stage(case["stream"], forged)
        assert fixture.snapshot(case) == before
        core = case["stream"]._system.core
        with pytest.raises(ValueError, match="previous weights are not owned"):
            core._register_native_raw_context(
                altered, authority=case["stream"]._raw_candidate_authority
            )
        assert fixture.snapshot(case) == before
        case["joint"].restore_state(initial)
        case["stream"].produce_joint_posterior()
        assert len(case["candidate"].consumed_keys) == 1
    finally:
        case["store"].close()


def test_previous_evidence_cannot_be_dict_or_missing_and_none_hash_is_legacy(tmp_path, checkpoints):
    case = fixture.scenario(tmp_path / "types.db", checkpoints)
    try:
        when = fixture.advance(case, 0, publish=False)
        context = context_for(case["stream"], when)
        assert context.previous_weight_evidence is None
        assert context.content_sha256 == native_content_sha256(
            (
                context.source,
                context.previous_batch,
                context.records,
                context.ledger_head_sha256,
                tuple(
                    (
                        raw.envelope_json,
                        raw.capture_receipt_sha256,
                        sha256(raw.payload_bytes).hexdigest(),
                        raw.depth_unit,
                    )
                    for raw in context.visible_prefix
                ),
                context.cutoff,
            )
        )
        case["stream"].produce_joint_posterior()
        when = fixture.advance(case, 1, publish=False)
        context = context_for(case["stream"], when)
        for value in (None, {"receipts": context.previous_weight_evidence.receipts}):
            with pytest.raises(ValueError, match="actual previous log weight evidence"):
                case["joint"].produce(replace(context, previous_weight_evidence=value))
        case["stream"].produce_joint_posterior()
    finally:
        case["store"].close()


def test_complete_loaded_log_replacement_rejects_and_recovers_with_traceback_held(
    tmp_path, checkpoints, monkeypatch
):
    case = fixture.scenario(tmp_path / "loaded.db", checkpoints)
    try:
        fixture.advance(case, 0)
        when = fixture.advance(case, 1, publish=False)
        context = context_for(case["stream"], when)
        before = fixture.snapshot(case)
        initial = case["joint"].checkpoint_state()
        original = NativePreviousWeightEvidence.normalized_logs

        def changed(self):
            weights, unresolved = original(self)
            return {key: value + 2.0 for key, value in weights.items()}, unresolved + 2.0

        with monkeypatch.context() as patch:
            patch.setattr(NativePreviousWeightEvidence, "normalized_logs", changed)
            forged = case["joint"].produce(context)
            verify_neural_evidence(forged.neural_evidence)
            with pytest.raises(ValueError, match="loaded implementation changed") as captured:
                stage(case["stream"], forged)
        retained = captured.value
        assert retained.__traceback__ is not None
        assert fixture.snapshot(case) == before
        case["joint"].restore_state(initial)
        case["stream"].produce_joint_posterior()
        assert len(case["candidate"].consumed_keys) == 1
        assert retained.__traceback__ is not None
    finally:
        case["store"].close()


def test_full_code_encoding_stable_when_active_and_type_exact():
    import marshal

    from cpswm.system.controlled_position_producer import _helper_code_sha256
    from cpswm.system.structure_two_execution import _code_object_payload

    def carrier():
        yield from ("first", "second", "third")

    def identity(code):
        expected = sha256(marshal.dumps(_code_object_payload(code), 2)).hexdigest()
        assert _helper_code_sha256(code) == expected
        return expected

    expected = identity(carrier.__code__)
    active = carrier()
    assert next(active) == "first"
    held = _code_object_payload(carrier.__code__)
    assert identity(carrier.__code__) == expected
    active.close()
    del held, active
    assert identity(carrier.__code__) == expected
    for left, right in (("True", "1"), ("0.0", "-0.0"), ("1", "1.0")):
        first, second = {}, {}
        exec(compile("def value():\n    return " + left, "<typed-code>", "exec"), first)
        exec(compile("def value():\n    return " + right, "<typed-code>", "exec"), second)
        assert identity(first["value"].__code__) != identity(second["value"].__code__)


def test_original_helper_payloads_stay_bound_during_actual_condition_and_retention(
    tmp_path, checkpoints
):
    import base64
    import inspect
    import json
    import marshal
    import sys

    import cpswm.system.controlled_position_producer as controlled
    from cpswm.system.structure_two_execution import _code_object_payload

    case = fixture.scenario(tmp_path / "live-helpers.db", checkpoints)
    try:
        helpers = {}
        for module in (
            controlled.instance_affinity,
            controlled.soft_surface_position,
            controlled.position,
            controlled.natural_vision,
            controlled.unity_rgbd,
        ):
            for name, member in vars(module).items():
                if inspect.isfunction(member):
                    helpers[module.__name__ + "." + name] = member
                elif inspect.isclass(member) and member.__module__ == module.__name__:
                    for key, descriptor in vars(member).items():
                        bodies = (
                            (descriptor.fget, descriptor.fset, descriptor.fdel)
                            if isinstance(descriptor, property)
                            else (
                                (
                                    descriptor.__func__
                                    if isinstance(descriptor, (classmethod, staticmethod))
                                    else descriptor
                                ),
                            )
                        )
                        for index, body in enumerate(bodies):
                            if inspect.isfunction(body):
                                helpers[f"{module.__name__}.{name}.{key}.{index}"] = body
        before = {
            name: marshal.dumps(_code_object_payload(fn.__code__), 2)
            for name, fn in helpers.items()
        }
        # Hold all original semantic payloads, including literal tuples/constants.
        held = tuple(_code_object_payload(fn.__code__) for fn in helpers.values())
        original_binding = case["candidate"]._implementation
        condition = position.condition.__code__
        original_condition = marshal.dumps(_code_object_payload(condition), 2)
        active_payloads = []

        def trace(frame, event, arg):
            if frame.f_code is condition and event == "line":
                active = marshal.dumps(_code_object_payload(condition), 2)
                assert active == original_condition
                assert controlled.implementation_binding() == original_binding
                active_payloads.append(active)
            return trace

        previous = sys.gettrace()
        try:
            sys.settrace(trace)
            fixture.advance(case, 0)
        finally:
            sys.settrace(previous)
        assert active_payloads and held
        assert controlled.implementation_binding() == original_binding
        fixture.advance(case, 1)
        after = {
            name: marshal.dumps(_code_object_payload(fn.__code__), 2)
            for name, fn in helpers.items()
        }
        assert before == after
        del held
        assert controlled.implementation_binding() == original_binding
        (tmp_path / "helper-payloads.json").write_text(
            json.dumps(
                dict(
                    scope="controlled_helper_full_payload_stability_not_original_171_root_cause",
                    helper_count=len(helpers),
                    active_condition_line_checks=len(active_payloads),
                    original_full_payloads_v2={
                        name: base64.b64encode(value).decode() for name, value in before.items()
                    },
                    active_condition_full_payload_v2=base64.b64encode(active_payloads[0]).decode(),
                    restored_payloads_equal=True,
                    actual_active_then_neutral_publication=True,
                ),
                indent=2,
            )
            + "\n"
        )
    finally:
        case["store"].close()


@pytest.mark.parametrize("attack", ["helper_code", "helper_constant"])
def test_helper_full_forgery_rejected_then_original_binding_recovers_with_traceback(
    tmp_path, checkpoints, monkeypatch, attack
):
    case = fixture.scenario(tmp_path / "helper-attack.db", checkpoints)
    try:
        when = fixture.advance(case, 0, publish=False)
        context = context_for(case["stream"], when)
        before = fixture.snapshot(case)
        original_state = case["joint"].checkpoint_state()
        original = position.condition

        def changed(*args, **kwargs):
            measurement, diagnostic = original(*args, **kwargs)
            return replace(measurement, information_weight=0.5), diagnostic

        with monkeypatch.context() as patch:
            if attack == "helper_code":
                patch.setattr(position, "condition", changed)
            else:
                patch.setattr(
                    position,
                    "H",
                    tuple(
                        tuple(float(column == row + 3) for column in range(6)) for row in range(3)
                    ),
                )
            attacker = fixture.fresh_joint(case)
            forged = attacker.produce(context)
            verify_neural_evidence(forged.neural_evidence)
            with pytest.raises(ValueError) as captured:
                stage(case["stream"], forged)
            with pytest.raises(ValueError, match="controlled helper implementation changed"):
                case["joint"].produce(context)
        retained = captured.value
        assert retained.__traceback__ is not None
        assert fixture.snapshot(case) == before
        assert case["joint"].checkpoint_state() == original_state
        case["stream"].produce_joint_posterior()
        assert len(case["candidate"].consumed_keys) == 1
        assert retained.__traceback__ is not None
    finally:
        case["store"].close()
