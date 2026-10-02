"""Genuine owner reports on natural archived pixels, controlled depth/semantics.
PYTEST_DONT_REWRITE: reused producers remain bound to ordinary source.
"""

from uuid import UUID

import pytest
from run_correction_replay_comparison import OracleProducer
from test_owned_rgbd_support import RGBDSupportDecoder
from test_temporal_target_position import (
    PublicPixelCamera,
    association_joint,
    capture,
    make_case,
)
from test_temporal_target_position import checkpoints as _checkpoints
from test_temporal_target_position import cpu_threads as _cpu_threads
from test_temporal_target_position import weights as _weights

from cpswm.perception_mapping.unity_rgbd import decode_unity_rgbd
from cpswm.system.native_joint_replay import consumed_schedule
from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput
from cpswm.system.target_position_report import ReportTask, report_owned_temporal_target

checkpoints = _checkpoints
cpu_threads = _cpu_threads
weights = _weights


def task_for(stream):
    contexts = [
        u.context
        for u in consumed_schedule(stream._system.core._particle_workspace)
        if u.context is not None and u.context.observation_update is not None
    ]
    c = contexts[-1]
    u = c.observation_update
    lookup = {str(r.envelope().identity.observation_id): r for r in c.visible_prefix}
    camera, _ = decode_unity_rgbd(
        tuple(lookup[k] for k in u.packet["observation_ids"]), cutoff=u.received_at
    )
    return ReportTask(
        task_id=UUID(int=1),
        scene_id=camera.scene_sha256,
        frame_id=camera.world_frame,
        target_description="controlled semantic target with natural candidate",
        valid_at=camera.capture_time,
        initial_input_sha256=contexts[0].observation_update.packet["raw_sha256"],
        allowed_actions_sha256="a" * 64,
        action_budget=3,
        position_origin_m=(0.0, 0.0, 0.0),
    )


def test_real_owner_report_restore_and_capture_withdrawal(tmp_path, checkpoints, weights):
    case = make_case(tmp_path / "state.db", checkpoints, weights)
    try:
        stream = case["stream"]
        camera = PublicPixelCamera(stream._scope)
        first, _ = capture(case, camera)
        capture(case, camera)
        task = task_for(stream)
        reports = [
            report_owned_temporal_target(stream, task, particle_id=a.particle_id)
            for a in stream.current_joint_decision_view().atoms
        ]
        report = next(r for r in reports if r.status == "reported")
        before = case["store"]._db.execute("SELECT * FROM checkpoint").fetchall()
        assert report_owned_temporal_target(stream, task, particle_id=report.particle_id) == report
        for update in ({"frame_id": "foreign"}, {"position_origin_m": (1.0, 0.0, 0.0)}):
            with pytest.raises(ValueError, match="differs"):
                report_owned_temporal_target(
                    stream, task.model_copy(update=update), particle_id=report.particle_id
                )
        assert case["store"]._db.execute("SELECT * FROM checkpoint").fetchall() == before

        def forbidden(*args):
            raise AssertionError("restoration must not rerun semantics")

        restored = ContinuousEvidenceInput.resume(
            case["store"],
            producer=OracleProducer(),
            context_builder=forbidden,
            joint_producer=association_joint(case),
            observation_decoder=RGBDSupportDecoder(),
        )
        assert (
            report_owned_temporal_target(restored, task, particle_id=report.particle_id) == report
        )
        restored.withdraw_owned_position_observation(
            first.action_id, reason="withdraw initial anchor"
        )
        with pytest.raises(ValueError, match="no effective"):
            report_owned_temporal_target(restored, task, particle_id=report.particle_id)
        unknown = report_owned_temporal_target(restored, task, particle_id=None)
        assert unknown.status == "unknown" and not unknown.observation_ids
        assert camera.calls == 2
    finally:
        case["store"].close()
