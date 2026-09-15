"""Engineering fixtures only: durability is not calibrated visual capability."""

import sqlite3
from datetime import timedelta

import pytest
from test_structure_two_adaptive_runtime import (
    _adaptive_system_and_transition,
    _ciav_input,
    _features,
)
from test_structure_two_continuous_input import (
    FixtureProducer,
    FixtureWorldExecutor,
    deliver,
    old,
    raw_for,
    setup,
)

from cpswm.system.continuous_state_store import ContinuousStateStore
from cpswm.system.structure_two_adaptive_runtime import AdaptiveExecutionContext
from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput, GroundedTransition


class DurableFixtureProducer(FixtureProducer):
    def checkpoint_state(self):
        return {"output": self.output}

    def restore_state(self, state):
        self.output = state["output"]


def store_at(path):
    return ContinuousStateStore(path, source_identity="a" * 64, dependency_identity="b" * 64)


def durable_setup(path):
    probe, _, _, transition = setup()
    meta = transition.after.metadata
    backend = DurableFixtureProducer()
    store = store_at(path)
    stream = ContinuousEvidenceInput(
        system=probe.system,
        execution_lane="legacy_component_diagnostic",
        household_id=meta.household_id,
        session_id=meta.session_id,
        trace_id=meta.trace_id,
        producer=backend,
        state_store=store,
    )
    return probe, stream, backend, store, transition


def test_recovery_retains_one_graph_and_retraction_changes_next_action(tmp_path):
    path = tmp_path / "state.db"
    probe, stream, backend, store, transition = durable_setup(path)
    for day in probe.observed_days()[:12]:
        deliver(stream, backend, probe.transition_for(day))
    when = probe.observed_days()[12].after.detection_time
    first = stream.prepare_habit_placement(decision_time=when)
    world = FixtureWorldExecutor(transition.after.metadata)
    stream.execute_placement(first, executor=world)
    bundles = [
        old._feedback(probe, rid)
        for rid, event in probe.system.core._committed_events.items()
        if event.location_id == first.location_id
    ]
    state_hash = probe.system.adaptive_router_state_sha256()
    store.close()
    store = store_at(path)
    restored = ContinuousEvidenceInput.resume(store, producer=DurableFixtureProducer())
    assert restored._system.adaptive_router_state_sha256() == state_hash
    assert restored._system._assembly_components[0] is restored._system.core
    assert len(restored.execution_traces()) == 12
    assert len(restored.visible_prefix(cutoff=when)) == 12
    for i, (feedback, binding, likelihood) in enumerate(bundles):
        restored.consume_feedback(
            feedback=feedback,
            binding=binding,
            likelihood_model=likelihood,
            received_at=when + timedelta(seconds=i + 2),
            policy=old.RETRACTION_POLICY,
        )
    second = restored.prepare_habit_placement(decision_time=when + timedelta(minutes=1))
    assert second.location_id != first.location_id
    restored.execute_placement(second, executor=world)
    assert world.calls == 2
    assert restored._system.core.verify_hybrid_full_rerun_equivalence().equivalent
    store.close()


def test_placement_effect_is_not_repeated_after_recovery(tmp_path):
    path = tmp_path / "state.db"
    _, stream, backend, store, transition = durable_setup(path)
    deliver(stream, backend, transition)
    command = stream.prepare_habit_placement(
        decision_time=transition.after.detection_time + timedelta(seconds=2)
    )
    world = FixtureWorldExecutor(transition.after.metadata, fail_after_move=True)
    with pytest.raises(OSError):
        stream.execute_placement(command, executor=world)
    store.close()
    store = store_at(path)
    restored = ContinuousEvidenceInput.resume(store, producer=DurableFixtureProducer())
    with pytest.raises(ValueError, match="already dispatched"):
        restored.execute_placement(restored.placement_command(command.action_id), executor=world)
    assert world.calls == 1
    store.close()


def test_single_writer_and_source_identity(tmp_path):
    path = tmp_path / "state.db"
    store = store_at(path)
    store.save({"x": 1})
    with pytest.raises(sqlite3.OperationalError):
        store_at(path)
    store.close()
    with pytest.raises(ValueError, match="differ"):
        ContinuousStateStore(path, source_identity="c" * 64, dependency_identity="b" * 64)


def test_effect_receipt_reuse_and_uncertain_reconciliation(tmp_path):
    path = tmp_path / "state.db"
    store = store_at(path)
    calls = []

    def fail(request):
        calls.append(request)
        raise OSError("after effect")

    with pytest.raises(OSError):
        store.execute_once("step0", {"look": 1}, fail)
    store.close()
    store = store_at(path)
    with pytest.raises(RuntimeError, match="UNCERTAIN"):
        store.execute_once("step0", {"look": 1}, fail)
    assert store.pending_effects() == (("step0", {"look": 1}),)
    store.reconcile_effect("step0", {"look": 1}, {"success": True})
    assert store.pending_effects() == ()
    assert store.execute_once("step0", {"look": 1}, fail) == {"success": True}
    assert len(calls) == 1
    with pytest.raises(ValueError, match="changed"):
        store.execute_once("step0", {"look": 2}, fail)
    store.close()


def test_registered_p5_first_runs_in_continuous_history(tmp_path):
    system, transition = _adaptive_system_and_transition()
    ciav = _ciav_input(transition)

    def builder(system, item, when, step):
        return AdaptiveExecutionContext(
            router_features=_features(system, step=step, route="P0_FAST_LOCAL"),
            step_index=step,
            ciav_input=ciav,
        )

    meta = transition.after.metadata
    backend = DurableFixtureProducer()
    store = store_at(tmp_path / "p5.db")
    stream = ContinuousEvidenceInput(
        system=system,
        execution_lane="registered_p5_first",
        context_builder=builder,
        household_id=meta.household_id,
        session_id=meta.session_id,
        trace_id=meta.trace_id,
        producer=backend,
        state_store=store,
    )
    when = ciav.opportunity_time
    ids = stream.admit((raw_for(transition),), received_at=when)
    backend.output = GroundedTransition(transition, ids, "fixture", "fixture-not-calibrated")
    receipt = stream.advance(cutoff=when)
    assert receipt.result.path_selection.selected_path_id == "P5_FULL_EAGER"
    assert receipt.result.ciav_receipt is not None
    assert len(stream.execution_traces()) == 1
    store.close()
    store = store_at(tmp_path / "p5.db")
    restored = ContinuousEvidenceInput.resume(
        store, producer=DurableFixtureProducer(), context_builder=builder
    )
    assert restored.advance(cutoff=when) == receipt
    store.close()


def test_p5_crash_after_receipt_does_not_repeat_ciav(tmp_path):
    from dataclasses import replace

    system, transition = _adaptive_system_and_transition()
    original = _ciav_input(transition)

    class Transport:
        calls = 0

        def execute(self, opportunity):
            self.calls += 1
            return self.original.realizer(opportunity)

    transport = Transport()
    transport.original = original
    ciav = replace(original, realizer=transport.execute)

    def builder(system, item, when, step):
        return AdaptiveExecutionContext(
            router_features=_features(system, step=step, route="P0_FAST_LOCAL"),
            step_index=step,
            ciav_input=ciav,
        )

    meta = transition.after.metadata
    backend = DurableFixtureProducer()
    path = tmp_path / "p5.db"
    store = store_at(path)
    stream = ContinuousEvidenceInput(
        system=system,
        execution_lane="registered_p5_first",
        context_builder=builder,
        household_id=meta.household_id,
        session_id=meta.session_id,
        trace_id=meta.trace_id,
        producer=backend,
        state_store=store,
    )
    when = ciav.opportunity_time
    ids = stream.admit((raw_for(transition),), received_at=when)
    backend.output = GroundedTransition(transition, ids, "fixture", "fixture")
    save = store.save

    def fail_final(state):
        if state["fields"]["_advanced"]:
            raise OSError("crash before final checkpoint")
        save(state)

    store.save = fail_final
    with pytest.raises(OSError):
        stream.advance(cutoff=when)
    assert transport.calls == 1
    store.close()
    store = store_at(path)
    restored = ContinuousEvidenceInput.resume(
        store, producer=DurableFixtureProducer(), context_builder=builder
    )
    receipt = restored.advance(cutoff=when)
    assert receipt.result.ciav_receipt is not None
    assert transport.calls == 1
    assert len(restored.execution_traces()) == 1
    store.close()


def test_new_python_process_loads_checkpoint_without_test_imports(tmp_path):
    import os
    import subprocess
    import sys

    path = tmp_path / "state.db"
    probe, stream, backend, store, transition = durable_setup(path)
    deliver(stream, backend, transition)
    expected = probe.system.adaptive_router_state_sha256()
    store.close()
    script = """
import sys
from pathlib import Path
from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput
from cpswm.system.continuous_state_store import ContinuousStateStore
store = ContinuousStateStore(Path(sys.argv[1]), source_identity="a"*64, dependency_identity="b"*64)
saved = store.load()
print(saved["fields"]["_system"].adaptive_router_state_sha256())
store.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(path)],
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == expected


def test_observation_receipt_admits_new_input_and_uncertain_never_reexecutes(tmp_path):
    from cpswm.system.structure_two_continuous_input import ObservationDelivery

    path = tmp_path / "state.db"
    _, stream, backend, store, transition = durable_setup(path)
    deliver(stream, backend, transition)
    when = transition.after.detection_time + timedelta(seconds=2)
    source = stream.visible_prefix(cutoff=when)[0].envelope().identity.observation_id
    command = stream.prepare_observation(
        action="RotateRight",
        degrees=90,
        reason="fixture uncertainty",
        source_ids=(source,),
        decision_time=when,
    )

    class Camera:
        calls = 0

        def execute(self, command):
            self.calls += 1
            raw = raw_for(transition, capture=when + timedelta(seconds=1))
            return ObservationDelivery(
                command.action_id, (raw,), True, "", when + timedelta(seconds=1)
            )

    camera = Camera()
    receipt = stream.execute_observation(command, executor=camera)
    assert len(stream.visible_prefix(cutoff=receipt.received_at)) == 2
    store.close()
    store = store_at(path)
    restored = ContinuousEvidenceInput.resume(store, producer=DurableFixtureProducer())
    owned = restored._observation_commands[command.action_id][0]
    with pytest.raises(ValueError, match="already dispatched"):
        restored.execute_observation(owned, executor=camera)
    assert camera.calls == 1
    assert len(restored.visible_prefix(cutoff=receipt.received_at)) == 2
    store.close()


def test_codec_preserves_mutable_cycles_and_rejects_immutable_cycles():
    from cpswm.system.continuous_state_codec import StateCodec

    codec = StateCodec()
    value = []
    value.append(value)
    restored = codec.loads(codec.dumps(value))
    assert restored[0] is restored
    cycle = []
    immutable = (cycle,)
    cycle.append(immutable)
    with pytest.raises(ValueError, match="immutable cycle"):
        codec.loads(codec.dumps(immutable))


def test_observation_old_decision_rejected_and_empty_failure_advances_watermark():
    from cpswm.system.structure_two_continuous_input import ObservationDelivery

    _, stream, _, transition = setup(False)
    when = transition.after.detection_time
    ids = stream.admit((raw_for(transition),), received_at=when)
    command = stream.prepare_observation(
        action="Pass", degrees=0, reason="fixture", source_ids=ids, decision_time=when
    )
    stream.admit((raw_for(transition),), received_at=when + timedelta(hours=1))

    class Failure:
        calls = 0

        def execute(self, command):
            self.calls += 1
            return ObservationDelivery(
                command.action_id, (), False, "failed", when + timedelta(hours=2)
            )

    executor = Failure()
    with pytest.raises(ValueError, match="predates"):
        stream.execute_observation(command, executor=executor)
    assert executor.calls == 0
    fresh = stream.prepare_observation(
        action="Pass",
        degrees=0,
        reason="fixture",
        source_ids=ids,
        decision_time=when + timedelta(hours=1),
    )
    stream.execute_observation(fresh, executor=executor)
    with pytest.raises(ValueError):
        stream.admit((raw_for(transition),), received_at=when + timedelta(minutes=90))


def test_effect_only_store_is_source_bound_before_first_checkpoint(tmp_path):
    path = tmp_path / "effects.db"
    store = store_at(path)
    store.execute_once("effect", {"camera": 1}, lambda request: {"success": True})
    store.close()
    with pytest.raises(ValueError, match="differ"):
        ContinuousStateStore(path, source_identity="c" * 64, dependency_identity="d" * 64)
    store = store_at(path)
    assert store.execute_once("effect", {"camera": 1}, lambda request: None) == {"success": True}
    store.close()


def test_accepted_observation_receipt_is_detached_from_transport_and_survives_restore(tmp_path):
    from cpswm.system.structure_two_continuous_input import ObservationDelivery

    path = tmp_path / "state.db"
    _, stream, backend, store, transition = durable_setup(path)
    deliver(stream, backend, transition)
    when = transition.after.detection_time + timedelta(seconds=2)
    ids = tuple(stream._raw)
    command = stream.prepare_observation(
        action="Pass", degrees=0, reason="fixture", source_ids=ids, decision_time=when
    )

    class Camera:
        def execute(self, command):
            self.reply = ObservationDelivery(command.action_id, (), False, "original failure", when)
            return self.reply

    camera = Camera()
    stream.execute_observation(command, executor=camera)
    object.__setattr__(camera.reply, "success", True)
    object.__setattr__(camera.reply, "error", "changed outside")
    stream.prepare_observation(
        action="Pass",
        degrees=0,
        reason="next fixture",
        source_ids=ids,
        decision_time=when + timedelta(seconds=1),
    )
    store.close()
    store = store_at(path)
    restored = ContinuousEvidenceInput.resume(store, producer=DurableFixtureProducer())
    accepted = restored._observation_status[command.action_id]
    assert accepted.success is False and accepted.error == "original failure"
    store.close()


def test_fresh_process_registers_configured_visual_history_before_restore(tmp_path):
    import subprocess
    import sys
    from types import SimpleNamespace

    from test_interaction_evidence import frame

    from cpswm.perception_mapping.natural_vision import (
        WEIGHTS_SHA256,
        NaturalVisionEvidenceProducer,
    )
    from cpswm.system.continuous_state_codec import StateCodec

    observed = frame()
    scope = (observed.household_id, observed.session_id, observed.trace_id)
    producer = NaturalVisionEvidenceProducer(
        SimpleNamespace(
            _scope=scope,
            _versions=("test", "test"),
            weights_sha256=WEIGHTS_SHA256,
            _minimum_score=0.5,
        )
    )
    # A type-bootstrap probe, not a detector correctness claim.
    producer._frames = (observed,)
    producer._interactions = producer._recompute_interactions(producer._frames)
    path = tmp_path / "visual-state.json"
    path.write_text(StateCodec().dumps(producer.checkpoint_state()))
    script = """
from pathlib import Path
import sys
from types import SimpleNamespace
from uuid import UUID
from cpswm.perception_mapping.natural_vision import WEIGHTS_SHA256, NaturalVisionEvidenceProducer
from cpswm.system.continuous_state_codec import StateCodec
producer = NaturalVisionEvidenceProducer(SimpleNamespace(
    _scope=tuple(UUID(x) for x in sys.argv[2:]), _versions=("test","test"), _minimum_score=.5,
    weights_sha256=WEIGHTS_SHA256,
))
producer.restore_state(StateCodec().loads(Path(sys.argv[1]).read_text()))
assert len(producer.frames()) == len(producer.interactions()) == 1
assert len(producer.interactions()[0][0].detections) == 2
print("visual history restored in fresh process")
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(path), *map(str, scope)], text=True, capture_output=True
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "visual history restored in fresh process"
