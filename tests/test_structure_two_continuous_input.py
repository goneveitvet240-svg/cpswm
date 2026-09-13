"""Continuous core integration with synthetic sensor/semantic fixtures.

The producer below deliberately does NOT recognize pixels. These tests prove
sequencing and real core state/action readout consequences, not perception,
calibration, full-axis neural generation, or physical execution.
"""

import hashlib
import io
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import numpy as np
import pytest
import test_structure_two_formal_revision_lineage as old
from structure_two_backbone_wiring_probe import BackboneWiringProbe

from cpswm.perception_mapping.adapters.contracts import (
    ObservationEnvelope,
    ObservationIdentity,
    PayloadRef,
    SensorModality,
    SensorRef,
)
from cpswm.perception_mapping.adapters.rgbd_capture import RawModalityObservation
from cpswm.system.continual.project_one_regime_loop import PrototypeStatisticOperation
from cpswm.system.structure_two_continuous_input import (
    ContinuousEvidenceInput,
    GroundedTransition,
    PlacementFeedbackDelivery,
)


def raw_for(transition, *, capture=None, arrival=None):
    meta = transition.after.metadata
    identity = uuid4()
    when = capture or transition.after.detection_time
    b = io.BytesIO()
    np.save(b, np.zeros((4, 4, 3), dtype=np.uint8), allow_pickle=False)
    payload = b.getvalue()
    envelope = ObservationEnvelope(
        metadata=meta.model_copy(update={"record_id": identity}),
        identity=ObservationIdentity(
            observation_id=identity,
            household_id=meta.household_id,
            session_id=meta.session_id,
            trace_id=meta.trace_id,
        ),
        sensor=SensorRef(sensor_id="synthetic-integration-fixture", modality=SensorModality.RGB),
        capture_time=when,
        arrival_time=arrival or when,
        clock_domain="fixture-utc",
        frame_id="fixture",
        payload=PayloadRef(
            payload_id=identity,
            payload_sha256=hashlib.sha256(payload).hexdigest(),
            size_bytes=len(payload),
        ),
    )
    return RawModalityObservation(envelope.model_dump_json(), payload, "a" * 64, None)


class FixtureProducer:
    def __init__(self):
        self.output = None
        self.prefixes = []

    def infer(self, visible_prefix, *, cutoff):
        self.prefixes.append(visible_prefix)
        return self.output


def setup(producer=True):
    probe = BackboneWiringProbe.build(seed=7)
    transition = probe.transition_for(probe.observed_days()[0])
    meta = transition.after.metadata
    backend = FixtureProducer() if producer else None
    stream = ContinuousEvidenceInput(
        system=probe.system,
        execution_lane="legacy_component_diagnostic",
        household_id=meta.household_id,
        session_id=meta.session_id,
        trace_id=meta.trace_id,
        producer=backend,
    )
    return probe, stream, backend, transition


def deliver(stream, backend, transition):
    raw = raw_for(transition)
    when = transition.after.detection_time + timedelta(seconds=1)
    ids = stream.admit((raw,), received_at=when)
    backend.output = GroundedTransition(
        transition, ids, "synthetic-producer-test-only", "fixture-not-calibrated"
    )
    return stream.advance(cutoff=when)


def test_continuous_hypotheses_retraction_and_fresh_action_readout():
    probe, stream, backend, _ = setup()
    receipts = []
    for day in probe.observed_days()[:12]:
        receipts.append(deliver(stream, backend, probe.transition_for(day)))
    assert all(len(r.result.event_history.latest.hypotheses) > 1 for r in receipts)
    assert len(stream.execution_traces()) == 12
    core = probe.system.core
    before = dict(stream.current_habit_location_distribution())
    old_snapshot = core.current_snapshot
    before_commits = set(core._committed_events)
    when = probe.observed_days()[12].after.detection_time
    rid = next(iter(core._committed_events))
    feedback, binding, likelihood = old._feedback(probe, rid)
    result = stream.consume_feedback(
        feedback=feedback,
        binding=binding,
        likelihood_model=likelihood,
        received_at=when,
        policy=old.RETRACTION_POLICY,
    )
    assert result.statistic_operations == (PrototypeStatisticOperation.RETRACT,)
    assert rid not in core._committed_events
    assert set(core._committed_events) <= before_commits - {rid}
    assert dict(stream.current_habit_location_distribution()) != before
    assert core.verify_hybrid_full_rerun_equivalence().equivalent
    with pytest.raises(ValueError, match="stale"):
        core.action_location_distribution(old_snapshot)
    after = dict(stream.current_habit_location_distribution())
    assert (
        stream.consume_feedback(
            feedback=feedback,
            binding=binding,
            likelihood_model=likelihood,
            received_at=when,
            policy=old.RETRACTION_POLICY,
        )
        == result
    )
    assert dict(stream.current_habit_location_distribution()) == after


def test_delayed_capture_is_invisible_until_arrival_and_retains_transport_order():
    _, stream, _, transition = setup(False)
    t = transition.after.detection_time
    new = raw_for(transition, capture=t, arrival=t)
    late = raw_for(transition, capture=t - timedelta(hours=1), arrival=t + timedelta(seconds=2))
    stream.admit((new,), received_at=t)
    stream.admit((late,), received_at=t + timedelta(seconds=2))
    assert stream.visible_prefix(cutoff=t + timedelta(seconds=1)) == (new,)
    assert stream.visible_prefix(cutoff=t + timedelta(seconds=3)) == (new, late)
    stream.admit((late,), received_at=t + timedelta(seconds=3))
    assert len(stream.visible_prefix(cutoff=t + timedelta(seconds=4))) == 2
    with pytest.raises(RuntimeError, match="PRODUCER_UNAVAILABLE"):
        stream.advance(cutoff=t + timedelta(seconds=3))
    assert stream.execution_traces() == ()


def test_whole_raw_batch_is_atomic_on_bad_second_payload_and_retry():
    _, stream, _, transition = setup(False)
    first, second = raw_for(transition), raw_for(transition)
    t = transition.after.detection_time
    with pytest.raises(ValueError):
        stream.admit((first, replace(second, payload_bytes=b"bad")), received_at=t)
    assert stream.visible_prefix(cutoff=t) == ()
    assert len(stream.admit((first, second), received_at=t)) == 2
    with pytest.raises(ValueError):
        stream.admit((replace(first, capture_receipt_sha256="b" * 64),), received_at=t)


@pytest.mark.parametrize("attack", ["source", "future", "scope", "empty_calibration"])
def test_bad_producer_is_rejected_without_learning_and_legal_retry(attack):
    probe, stream, backend, transition = setup()
    raw = raw_for(transition)
    t = transition.after.detection_time + timedelta(seconds=1)
    ids = stream.admit((raw,), received_at=t)
    good = GroundedTransition(transition, ids, "fixture", "fixture")
    if attack == "source":
        bad = replace(good, source_observation_ids=(uuid4(),))
    elif attack == "empty_calibration":
        bad = replace(good, calibration_id=" ")
    else:
        after = transition.after
        changes = (
            {"detection_time": t + timedelta(hours=1)}
            if attack == "future"
            else {"metadata": after.metadata.model_copy(update={"session_id": uuid4()})}
        )
        bad = replace(good, transition=replace(transition, after=after.model_copy(update=changes)))
    backend.output = bad
    before = probe.system.core.current_snapshot
    with pytest.raises(ValueError):
        stream.advance(cutoff=t)
    assert probe.system.core.current_snapshot == before
    assert not stream.execution_traces()
    backend.output = good
    result = stream.advance(cutoff=t)
    assert result.result is not None
    assert stream.advance(cutoff=t) == result
    assert len(stream.execution_traces()) == 1


def test_no_evidence_is_not_missing_object_and_cutoff_cannot_backdate():
    probe, stream, _backend, transition = setup()
    t = transition.after.detection_time
    stream.admit((raw_for(transition),), received_at=t)
    before = probe.system.core.current_snapshot
    assert stream.advance(cutoff=t + timedelta(hours=1)).status == "INSUFFICIENT_SEMANTIC_EVIDENCE"
    assert probe.system.core.current_snapshot == before
    with pytest.raises(ValueError):
        stream.admit((raw_for(transition),), received_at=t)
    with pytest.raises(ValueError):
        stream.advance(cutoff=t)


def test_reentrant_producer_cannot_mutate_stream():
    _, stream, backend, transition = setup()
    t = transition.after.detection_time
    raw = raw_for(transition)
    stream.admit((raw,), received_at=t)

    def infer(prefix, *, cutoff):
        stream.admit((raw,), received_at=cutoff)

    backend.infer = infer
    with pytest.raises(RuntimeError, match="reentrant"):
        stream.advance(cutoff=t)
    assert stream.visible_prefix(cutoff=t) == (raw,)


class FixtureWorldExecutor:
    """A small stateful test world; never evidence of a real simulator/robot."""

    def __init__(self, metadata, *, fail_after_move=False, wrong_reply=False):
        self.metadata = metadata
        self.location = None
        self.calls = 0
        self.fail_after_move = fail_after_move
        self.wrong_reply = wrong_reply

    def execute(self, command):
        from cpswm.contracts import (
            EntityRef,
            EntityType,
            ExecutionFeedbackRecord,
            RobotActionOutcome,
            RobotActionType,
            SourceType,
            ValidTimeInterval,
        )

        self.calls += 1
        self.location = command.location_id
        if self.fail_after_move:
            raise OSError("fixture transport failed after movement")
        feedback = ExecutionFeedbackRecord(
            metadata=self.metadata.model_copy(
                update={
                    "record_id": uuid4(),
                    "source_type": SourceType.ACTION,
                    "recorded_time": command.decision_time + timedelta(seconds=1),
                }
            ),
            action_id=uuid4() if self.wrong_reply else command.action_id,
            action_type=RobotActionType.PLACE,
            target_entity=EntityRef(
                entity_id=command.object_instance_id, entity_type=EntityType.OBJECT_INSTANCE
            ),
            attempted_location_id=command.location_id,
            valid_time=ValidTimeInterval(
                start=command.decision_time, end=command.decision_time + timedelta(seconds=1)
            ),
            outcome_distribution={RobotActionOutcome.SUCCESS: 1.0},
        )

        return PlacementFeedbackDelivery(feedback, command.decision_time + timedelta(seconds=1))


def test_late_retractions_change_next_issued_and_executed_placement():
    probe, stream, backend, transition = setup()
    for day in probe.observed_days()[:12]:
        deliver(stream, backend, probe.transition_for(day))
    core = probe.system.core
    when = probe.observed_days()[12].after.detection_time
    first = stream.prepare_habit_placement(decision_time=when)
    world = FixtureWorldExecutor(transition.after.metadata)
    stream.execute_placement(first, executor=world)
    assert world.location == first.location_id and world.calls == 1
    stale = stream.prepare_habit_placement(decision_time=when + timedelta(seconds=1))
    # Capture each original decision binding BEFORE any delayed revision.
    bundles = [
        old._feedback(probe, rid)
        for rid, event in core._committed_events.items()
        if event.location_id == first.location_id
    ]
    assert bundles
    for i, (feedback, binding, likelihood) in enumerate(bundles):
        stream.consume_feedback(
            feedback=feedback,
            binding=binding,
            likelihood_model=likelihood,
            received_at=when + timedelta(seconds=i + 2),
            policy=old.RETRACTION_POLICY,
        )
    with pytest.raises(ValueError, match="stale"):
        stream.execute_placement(stale, executor=world)
    second = stream.prepare_habit_placement(decision_time=when + timedelta(minutes=1))
    assert second.location_id != first.location_id
    stream.execute_placement(second, executor=world)
    assert world.location == second.location_id and world.calls == 2
    assert core.verify_hybrid_full_rerun_equivalence().equivalent


@pytest.mark.parametrize("mode", ["raise", "wrong_reply"])
def test_uncertain_execution_is_retained_and_never_retried(mode):
    _, stream, backend, transition = setup()
    deliver(stream, backend, transition)
    command = stream.prepare_habit_placement(
        decision_time=transition.after.detection_time + timedelta(seconds=2)
    )
    executor = FixtureWorldExecutor(
        transition.after.metadata,
        fail_after_move=mode == "raise",
        wrong_reply=mode == "wrong_reply",
    )
    with pytest.raises((ValueError, OSError)):
        stream.execute_placement(command, executor=executor)
    assert executor.calls == 1
    assert stream.placement_dispatches()[0].status == "OUTCOME_UNCERTAIN"
    with pytest.raises(ValueError, match="already dispatched"):
        stream.execute_placement(command, executor=executor)
    assert executor.calls == 1


def test_copied_command_is_not_a_live_capability():
    _, stream, backend, transition = setup()
    deliver(stream, backend, transition)
    command = stream.prepare_habit_placement(
        decision_time=transition.after.detection_time + timedelta(seconds=2)
    )
    executor = FixtureWorldExecutor(transition.after.metadata)
    with pytest.raises(ValueError, match="capability"):
        stream.execute_placement(replace(command), executor=executor)
    assert executor.calls == 0


def test_forcibly_mutated_live_command_cannot_change_target():
    _, stream, backend, transition = setup()
    deliver(stream, backend, transition)
    command = stream.prepare_habit_placement(
        decision_time=transition.after.detection_time + timedelta(seconds=2)
    )
    executor = FixtureWorldExecutor(transition.after.metadata)
    object.__setattr__(command, "object_instance_id", uuid4())
    with pytest.raises(ValueError, match="content was changed"):
        stream.execute_placement(command, executor=executor)
    assert executor.calls == 0


def test_raw_admission_and_prefix_are_detached_from_caller_aliases():
    _, stream, _, transition = setup(False)
    raw = raw_for(transition)
    when = transition.after.detection_time
    stream.admit((raw,), received_at=when)
    object.__setattr__(raw, "payload_bytes", b"mutated after validation")
    delivered = stream.visible_prefix(cutoff=when)[0]
    delivered.envelope()
    object.__setattr__(delivered, "payload_bytes", b"mutated public read")
    stream.visible_prefix(cutoff=when)[0].envelope()


def test_duplicate_feedback_advances_arrival_watermark():
    probe, stream, backend, _ = setup()
    for day in probe.observed_days()[:3]:
        deliver(stream, backend, probe.transition_for(day))
    when = probe.observed_days()[3].after.detection_time
    rid = next(iter(probe.system.core._committed_events))
    feedback, binding, likelihood = old._feedback(probe, rid)
    for arrival in (when, when + timedelta(hours=2)):
        stream.consume_feedback(
            feedback=feedback,
            binding=binding,
            likelihood_model=likelihood,
            received_at=arrival,
            policy=old.RETRACTION_POLICY,
        )
    transition = probe.transition_for(probe.observed_days()[0])
    with pytest.raises(ValueError, match="backwards"):
        stream.admit((raw_for(transition),), received_at=when + timedelta(hours=1))


def test_execution_completion_advances_time_and_does_not_expose_owned_command():
    _, stream, backend, transition = setup()
    deliver(stream, backend, transition)
    when = transition.after.detection_time + timedelta(seconds=2)
    command = stream.prepare_habit_placement(decision_time=when)
    executor = FixtureWorldExecutor(transition.after.metadata)
    stream.execute_placement(command, executor=executor)
    with pytest.raises(ValueError, match="predates"):
        stream.prepare_habit_placement(decision_time=when)
    detached = stream.placement_dispatches()[0]
    original = detached.command.location_id
    object.__setattr__(detached.command, "location_id", uuid4())
    assert stream.placement_dispatches()[0].command.location_id == original


def test_uncertain_action_reconciles_without_reexecution_then_allows_next_command():
    _, stream, backend, transition = setup()
    deliver(stream, backend, transition)
    when = transition.after.detection_time + timedelta(seconds=2)
    command = stream.prepare_habit_placement(decision_time=when)
    transport = FixtureWorldExecutor(transition.after.metadata, fail_after_move=True)
    with pytest.raises(OSError):
        stream.execute_placement(command, executor=transport)
    with pytest.raises(RuntimeError, match="reconciliation"):
        stream.prepare_habit_placement(decision_time=when + timedelta(seconds=2))
    # Independent receipt simulation: read the already attempted action's outcome.
    # The original transport is never invoked again.
    reply = FixtureWorldExecutor(transition.after.metadata).execute(command)
    result = stream.reconcile_placement(command.action_id, reply)
    assert result.status == "FEEDBACK_RECEIVED" and transport.calls == 1
    next_command = stream.prepare_habit_placement(decision_time=when + timedelta(seconds=2))
    assert next_command.action_id != command.action_id


@pytest.mark.parametrize("bad_time", ["arrival", "record", "start"])
def test_inconsistent_executor_timeline_remains_uncertain(bad_time):
    _, stream, backend, transition = setup()
    deliver(stream, backend, transition)
    when = transition.after.detection_time + timedelta(seconds=2)
    command = stream.prepare_habit_placement(decision_time=when)
    realizer = FixtureWorldExecutor(transition.after.metadata)

    class BadTimeline:
        def execute(self, cmd):
            delivery = realizer.execute(cmd)
            if bad_time == "arrival":
                return replace(delivery, received_at=when)
            if bad_time == "record":
                fb = delivery.feedback.model_copy(
                    update={
                        "metadata": delivery.feedback.metadata.model_copy(
                            update={"recorded_time": when}
                        )
                    }
                )
            else:
                fb = delivery.feedback.model_copy(
                    update={
                        "valid_time": delivery.feedback.valid_time.model_copy(
                            update={"start": when - timedelta(seconds=1)}
                        )
                    }
                )
            return replace(delivery, feedback=fb)

    with pytest.raises(ValueError):
        stream.execute_placement(command, executor=BadTimeline())
    assert stream.placement_dispatches()[0].status == "OUTCOME_UNCERTAIN"
