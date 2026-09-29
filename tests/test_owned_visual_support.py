"""Owned candidate support: controlled fixtures, not visual accuracy evidence.
PYTEST_DONT_REWRITE: test decoder implementation is pinned by the runtime.
"""

from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4, uuid5

import pytest
from test_joint_camera_feedback import BrightnessDecoder, Camera, problem_for, setup
from test_structure_two_adaptive_runtime import _adaptive_system_and_transition
from test_structure_two_continuous_input import raw_for

from cpswm.perception_mapping.natural_vision import DetectionCandidate, VisualFrame, decode_rgb
from cpswm.system.continuous_state_codec import StateCodec
from cpswm.system.joint_camera_feedback import decoder_binding
from cpswm.system.owned_visual_support import _frame_support, reconstruct_visual_support
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_continuous_input import (
    ContinuousEvidenceInput,
    ObservationCommand,
    ObservationDelivery,
)


class SupportDecoder(BrightnessDecoder):
    def measurements(self, observations, *, cutoff):
        frames = []
        for raw in observations:
            e, pixels = decode_rgb(raw, cutoff=cutoff)
            h, w = pixels.shape[:2]
            candidates = tuple(
                DetectionCandidate(uuid5(e.identity.observation_id, str(i)), category, score, box)
                for i, (category, score, box) in enumerate(
                    (
                        ("apple", 0.9, (0.0, 0.0, float(w), float(h))),
                        ("apple", 0.6, (0.0, 0.0, w / 2.0, h / 2.0)),
                        ("cup", 0.7, (w / 2.0, h / 2.0, float(w), float(h))),
                    )
                )
            )
            frames.append(
                VisualFrame(
                    e.identity.observation_id,
                    e.identity.household_id,
                    e.identity.session_id,
                    e.identity.trace_id,
                    e.sensor.sensor_id,
                    e.frame_id,
                    e.capture_time,
                    e.arrival_time,
                    cutoff,
                    e.payload.payload_sha256,
                    raw.capture_receipt_sha256,
                    "explicit-fixture",
                    "a" * 64,
                    "fixture",
                    "fixture",
                    0.5,
                    w,
                    h,
                    candidates,
                )
            )
        return tuple(frames)


class EmptyDecoder(SupportDecoder):
    def measurements(self, observations, *, cutoff):
        return tuple(
            replace(f, candidates=()) for f in super().measurements(observations, cutoff=cutoff)
        )


def owned(raw, action):
    e = raw.envelope()
    e = e.model_copy(update={"metadata": e.metadata.model_copy(update={"source_id": str(action)})})
    return replace(raw, envelope_json=e.model_dump_json())


@pytest.fixture
def journal():
    _, transition = _adaptive_system_and_transition()
    r = raw_for(transition)
    key = uuid4()
    r = owned(r, key)
    e = r.envelope()
    command = ObservationCommand(
        key, uuid4(), "Pass", 0.0, "fixture", (), e.capture_time - timedelta(seconds=1)
    )
    delivery = ObservationDelivery(key, (r,), True, "", e.arrival_time)
    decoder = SupportDecoder()
    return dict(
        commands={key: (command, content_sha256(command))},
        statuses={key: delivery},
        native_origins={},
        raw={e.identity.observation_id: r},
        scope=(e.identity.household_id, e.identity.session_id, e.identity.trace_id),
        decoder=decoder,
        expected_binding=decoder_binding(decoder),
    )


def test_positive_keeps_all_candidates_and_image_coordinates_without_world_claims(journal):
    result = reconstruct_visual_support(**journal)
    frame = result.actions[0].frames[0]
    assert len(frame.candidates) == 3
    assert [c.category for c in frame.candidates] == ["apple", "apple", "cup"]
    assert frame.candidates[1].normalized_box_xyxy == (0.0, 0.0, 0.5, 0.5)
    assert all(
        c.world_instance_id is c.world_position_m is c.orientation is c.probability is None
        for c in frame.candidates
    )
    assert result.scored_joint_density is None
    assert not result.negative_observation_authorized and not result.memory_write_authorized
    assert StateCodec().loads(StateCodec().dumps(result)) == result


def test_empty_candidates_preserve_observation_not_absence(journal):
    journal.update(decoder=EmptyDecoder(), expected_binding=decoder_binding(EmptyDecoder()))
    result = reconstruct_visual_support(**journal)
    assert len(result.actions[0].frames) == 1
    assert result.actions[0].frames[0].candidates == ()
    assert not result.negative_observation_authorized


@pytest.mark.parametrize(
    "status", ["READY", "OUTCOME_UNCERTAIN", "CANCELLED_STALE_JOINT", "FAILED"]
)
def test_non_success_states_have_no_fabricated_frames(journal, status):
    key = next(iter(journal["statuses"]))
    journal["statuses"][key] = (
        status
        if status != "FAILED"
        else replace(
            journal["statuses"][key], success=False, error="fixture failure", observations=()
        )
    )
    result = reconstruct_visual_support(**journal)
    assert result.actions[0].status == status and result.actions[0].frames == ()


@pytest.mark.parametrize(
    "attack",
    [
        "owner",
        "payload",
        "scope",
        "time",
        "command",
        "orphan",
        "missing_source",
        "bad_status",
        "origin",
        "receipt",
    ],
)
def test_owner_journal_attacks_rejected(journal, attack):
    key = next(iter(journal["commands"]))
    command, _ = journal["commands"][key]
    delivery = journal["statuses"][key]
    r = delivery.observations[0]
    if attack == "owner":
        r = owned(r, uuid4())
        journal["raw"][r.envelope().identity.observation_id] = r
        journal["statuses"][key] = replace(delivery, observations=(r,))
    elif attack == "payload":
        journal["statuses"][key] = replace(
            delivery, observations=(replace(r, payload_bytes=b"fake"),)
        )
    elif attack == "scope":
        journal["scope"] = (uuid4(), *journal["scope"][1:])
    elif attack == "time":
        journal["statuses"][key] = replace(
            delivery, received_at=command.decision_time - timedelta(seconds=1)
        )
    elif attack == "command":
        journal["commands"][key] = (replace(command, degrees=30.0), journal["commands"][key][1])
    elif attack == "orphan":
        journal["native_origins"][uuid4()] = "e" * 64
    elif attack == "missing_source":
        journal["raw"].clear()
    elif attack == "bad_status":
        journal["statuses"][key] = "SUCCEEDED"
    elif attack == "origin":
        journal["native_origins"][key] = "e" * 64  # unmodeled reason cannot hide modeled origin
    else:
        journal["statuses"][key] = replace(delivery, action_id=uuid4())
    with pytest.raises((ValueError, EOFError)):
        reconstruct_visual_support(**journal)


@pytest.mark.parametrize("attack", ["authority", "duplicate", "nan", "box", "frame_time", "input"])
def test_invalid_measured_frame_rejected(journal, attack):
    delivery = next(iter(journal["statuses"].values()))
    r = delivery.observations[0]
    frame = journal["decoder"].measurements((r,), cutoff=delivery.received_at)[0]
    if attack == "authority":
        frame = replace(frame, negative_observation_authorized=True)
    elif attack == "duplicate":
        frame = replace(frame, candidates=frame.candidates * 2)
    elif attack == "nan":
        frame = replace(
            frame, candidates=(replace(frame.candidates[0], detector_score=float("nan")),)
        )
    elif attack == "box":
        frame = replace(
            frame, candidates=(replace(frame.candidates[0], box_xyxy=(0.0, 0.0, 100.0, 100.0)),)
        )
    elif attack == "frame_time":
        frame = replace(frame, inference_cutoff=delivery.received_at + timedelta(seconds=1))
    else:
        frame = replace(frame, input_sha256="f" * 64)
    with pytest.raises(ValueError):
        _frame_support(r, frame, delivery.received_at)


class OwnedCamera(Camera):
    def execute(self, command):
        delivery = super().execute(command)
        return replace(
            delivery, observations=tuple(owned(r, command.action_id) for r in delivery.observations)
        )


def collect(stream, transition, when):
    _, command = stream.prepare_posterior_observation(problem_for(stream, when), decision_time=when)
    assert command is not None
    return stream.execute_observation(command, executor=OwnedCamera(transition))


def runtime_state(stream):
    from cpswm.system.structure_two_particle_workspace import native_content_sha256

    core = stream._system.core
    return (
        stream.current_joint_decision_view(),
        stream.observation_history(),
        deepcopy(stream._raw),
        core._hybrid_loop.ledger.export_state(),
        native_content_sha256(core._particle_workspace.state_payload()),
    )


def test_actual_owner_readout_restore_and_full_forged_positive_rejection(tmp_path):
    from test_continuous_state_recovery import DurableFixtureProducer
    from test_native_joint_production import JointFixture

    decoder = SupportDecoder()
    stream, store, transition, builder, start = setup(tmp_path / "db", decoder=decoder)
    try:
        collect(stream, transition, start + timedelta(seconds=2))
        before = runtime_state(stream)
        saved = store._db.execute("SELECT * FROM checkpoint").fetchall()
        support = stream.visual_observation_support()
        assert runtime_state(stream) == before
        restored = ContinuousEvidenceInput.resume(
            store,
            producer=DurableFixtureProducer(),
            context_builder=builder,
            joint_producer=JointFixture(),
            observation_decoder=SupportDecoder(),
        )
        assert restored.visual_observation_support(expected=support) == support
        frame = support.actions[0].frames[0]
        new_candidate = replace(frame.frame.candidates[0], category="forged", detector_score=0.99)
        fake_frame = replace(frame.frame, candidates=(new_candidate,))
        # A complete internally consistent forged positive, not merely a stale hash.
        r = restored.observation_history()[0][1].observations[0]
        fake = _frame_support(r, fake_frame, fake_frame.inference_cutoff)
        forged = replace(support, actions=(replace(support.actions[0], frames=(fake,)),))
        with pytest.raises(ValueError, match="fresh owned visual support differs"):
            restored.visual_observation_support(expected=forged)
        assert restored.visual_observation_support(expected=support) == support
        assert runtime_state(restored) == before
        assert store._db.execute("SELECT * FROM checkpoint").fetchall() == saved
    finally:
        store.close()


def test_repeat_pixels_are_grouped_but_never_merge_candidate_identities(tmp_path):
    stream, store, transition, _, start = setup(tmp_path / "db", decoder=SupportDecoder())
    try:
        first = collect(stream, transition, start + timedelta(seconds=2))
        collect(stream, transition, first.received_at + timedelta(seconds=2))
        result = stream.visual_observation_support()
        a, b = [row.frames[0] for row in result.actions]
        assert a.identical_pixel_group == b.identical_pixel_group
        assert {c.candidate_id for c in a.candidates}.isdisjoint(
            c.candidate_id for c in b.candidates
        )
        assert len(stream.joint_observation_updates()) == 2
    finally:
        store.close()


def test_changed_loaded_measurement_method_rejected_atomically(tmp_path, monkeypatch):
    stream, store, transition, _, start = setup(tmp_path / "db", decoder=SupportDecoder())
    try:
        collect(stream, transition, start + timedelta(seconds=2))
        before = deepcopy(stream._raw)

        def forged(self, observations, *, cutoff):
            return ()

        with monkeypatch.context() as patch:
            patch.setattr(SupportDecoder.measurements, "__code__", forged.__code__)
            with pytest.raises(ValueError, match="dependency changed"):
                stream.visual_observation_support()
        assert stream._raw == before
        assert len(stream.visual_observation_support().actions) == 1
    finally:
        store.close()


def test_missing_modeled_origin_rejected_even_with_complete_command_and_receipt(journal):
    key = next(iter(journal["commands"]))
    command = replace(journal["commands"][key][0], reason="joint-ciav@1:fixture")
    journal["commands"][key] = (command, content_sha256(command))
    with pytest.raises(ValueError, match="lost its native origin"):
        reconstruct_visual_support(**journal)


@pytest.mark.parametrize(
    "attack", ["omit_action", "invent_metric_pose", "claim_probability", "erase_group"]
)
def test_complete_derived_support_cannot_replace_fresh_source(tmp_path, attack):
    stream, store, transition, _, start = setup(tmp_path / "db", decoder=SupportDecoder())
    try:
        collect(stream, transition, start + timedelta(seconds=2))
        support = stream.visual_observation_support()
        state = runtime_state(stream)
        action = support.actions[0]
        frame = action.frames[0]
        if attack == "omit_action":
            forged = replace(support, actions=())
        else:
            if attack == "erase_group":
                frame = replace(frame, identical_pixel_group="0" * 64)
            else:
                candidate = replace(
                    frame.candidates[0],
                    **(
                        {"world_position_m": (1.0, 2.0, 3.0)}
                        if attack == "invent_metric_pose"
                        else {"probability": 0.99}
                    ),
                )
                frame = replace(frame, candidates=(candidate, *frame.candidates[1:]))
            forged = replace(support, actions=(replace(action, frames=(frame,)),))
        with pytest.raises(ValueError, match="fresh owned visual support differs"):
            stream.visual_observation_support(expected=forged)
        assert runtime_state(stream) == state
        assert stream.visual_observation_support(expected=support) == support
    finally:
        store.close()
