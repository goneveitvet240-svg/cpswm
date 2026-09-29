"""RGB-D owner/SQLite boundaries and consequential readouts, with controlled pixels.
PYTEST_DONT_REWRITE: owned decoder implementation is pinned.
"""

from copy import deepcopy
from dataclasses import replace
from datetime import timedelta

import pytest
from test_joint_camera_feedback import BrightnessDecoder, problem_for, setup
from test_owned_visual_support import SupportDecoder
from test_unity_rgbd import packet, rewrite_packet

from cpswm.perception_mapping.unity_rgbd import public_rgb_observations, surface_support
from cpswm.system.continuous_state_codec import StateCodec
from cpswm.system.joint_camera_feedback import decoder_binding
from cpswm.system.owned_visual_support import reconstruct_visual_support
from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput, ObservationDelivery
from cpswm.system.structure_two_particle_workspace import native_content_sha256


class RGBDSupportDecoder(SupportDecoder):
    def measurements(self, observations, *, cutoff):
        return super().measurements(
            public_rgb_observations(observations, cutoff=cutoff), cutoff=cutoff
        )

    def decode(self, observations, *, cutoff):
        return BrightnessDecoder.decode(
            self, public_rgb_observations(observations, cutoff=cutoff), cutoff=cutoff
        )


class RGBDCamera:
    def __init__(self, scope):
        self.scope, self.calls = scope, 0

    def execute(self, command):
        self.calls += 1
        rows, when = packet(
            action=command.action_id,
            scope=self.scope,
            capture=command.decision_time + timedelta(seconds=1),
        )
        return ObservationDelivery(command.action_id, rows, True, "", when)


def collect(stream, when):
    _, command = stream.prepare_posterior_observation(problem_for(stream, when), decision_time=when)
    assert command is not None
    camera = RGBDCamera(stream._scope)
    delivery = stream.execute_observation(command, executor=camera)
    assert camera.calls == 1
    return command, delivery


def ledger(stream):
    return native_content_sha256(stream._system.core._hybrid_loop.ledger.export_state())


def test_full_rgbd_owner_restore_fresh_geometry_preserves_ledger_and_action(tmp_path):
    decoder = RGBDSupportDecoder()
    stream, store, _, builder, start = setup(tmp_path / "state.sqlite", decoder=decoder)
    try:
        before = ledger(stream)
        command, delivery = collect(stream, start)
        view = stream.current_joint_decision_view()
        assert stream.joint_observation_updates()[0].source_observation_ids == tuple(
            r.envelope().identity.observation_id for r in delivery.observations
        )
        support = stream.visual_observation_support()
        assert support.actions[0].frames[0].geometry is not None
        assert StateCodec().loads(StateCodec().dumps(support)) == support
        when = delivery.received_at + timedelta(seconds=1)
        decision = problem_for(stream, when).select(view, stream._system.cause_information_planner)
        assert ledger(stream) == before
        resumed = ContinuousEvidenceInput.resume(
            store,
            producer=stream._producer,
            context_builder=builder,
            joint_producer=stream._joint_producer,
            observation_decoder=RGBDSupportDecoder(),
        )
        resumed.visual_observation_support(expected=support)
        assert resumed.current_joint_decision_view() == view
        assert ledger(resumed) == before
        assert resumed.observation_history() == stream.observation_history()
        assert (
            problem_for(resumed, when).select(
                resumed.current_joint_decision_view(), resumed._system.cause_information_planner
            )
            == decision
        )
        with pytest.raises(ValueError, match=r"capability|not this runtime|already dispatched"):
            resumed.execute_observation(command, executor=RGBDCamera(stream._scope))
    finally:
        store.close()


@pytest.mark.parametrize("kind", ["pose", "depth", "omitted_geometry", "invented_identity"])
def test_complete_forged_positive_geometry_cache_is_not_admitted(tmp_path, kind):
    decoder = RGBDSupportDecoder()
    stream, store, _, _, start = setup(tmp_path / "state.sqlite", decoder=decoder)
    try:
        _, d = collect(stream, start)
        original = stream.visual_observation_support()
        old = original.actions[0].frames[0]
        if kind in ("pose", "depth"):
            import numpy as np

            rows = rewrite_packet(
                d.observations,
                pose_changes={"position_m": [100.0, 200.0, 300.0]} if kind == "pose" else None,
                depth=np.full((4, 4), 9.0, dtype=np.float32) if kind == "depth" else None,
            )
            measured = decoder.measurements(rows, cutoff=d.received_at)[0]
            geometry = surface_support(rows, measured, cutoff=d.received_at)
            forged_frame = replace(old, frame=measured, geometry=geometry)
        elif kind == "omitted_geometry":
            forged_frame = replace(old, geometry=None)
        else:
            # Structurally complete and hashable despite fake declared type contents.
            geometry = replace(old.geometry, identity_association="certain-target")
            forged_frame = replace(old, geometry=geometry)
        forged = replace(original, actions=(replace(original.actions[0], frames=(forged_frame,)),))
        with pytest.raises(ValueError, match="fresh owned visual support differs"):
            stream.visual_observation_support(expected=forged)
        assert stream.visual_observation_support() == original
    finally:
        store.close()


def test_rebuilt_pose_cannot_replace_owned_receipt_without_owner_change(tmp_path):
    decoder = RGBDSupportDecoder()
    stream, store, _, _, start = setup(tmp_path / "state.sqlite", decoder=decoder)
    try:
        command, delivery = collect(stream, start)
        rows = rewrite_packet(
            delivery.observations, pose_changes={"position_m": [100.0, 200.0, 300.0]}
        )
        statuses = deepcopy(stream._observation_status)
        statuses[command.action_id] = replace(delivery, observations=rows)
        with pytest.raises(ValueError, match="ownership"):
            reconstruct_visual_support(
                commands=stream._observation_commands,
                statuses=statuses,
                native_origins=stream._observation_native_origins,
                raw=stream._raw,
                scope=stream._scope,
                decoder=decoder,
                expected_binding=decoder_binding(decoder),
            )
    finally:
        store.close()


@pytest.mark.parametrize("kind", ["transform", "filter"])
def test_loaded_geometry_dependency_change_rejected(tmp_path, monkeypatch, kind):
    from cpswm.perception_mapping import unity_rgbd

    decoder = RGBDSupportDecoder()
    stream, store, _, _, start = setup(tmp_path / "state.sqlite", decoder=decoder)
    try:
        collect(stream, start)
        if kind == "transform":
            monkeypatch.setattr(
                unity_rgbd.CameraSelfPose, "world_point", lambda *args: (0.0, 0.0, 0.0)
            )
        else:
            monkeypatch.setattr(unity_rgbd, "public_rgb_observations", lambda obs, **kw: obs[:1])
        with pytest.raises(ValueError, match=r"binding|dependency|changed"):
            stream.visual_observation_support()
    finally:
        store.close()
