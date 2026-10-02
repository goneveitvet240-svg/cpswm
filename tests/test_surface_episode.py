"""Real pinned masks and native transactions; controlled semantics/depth explicit.
PYTEST_DONT_REWRITE: durable dependency identities use ordinary source bodies.
"""

import os
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import pytest
from surface_pipeline_fixture import make_case
from test_native_neural_production import checkpoints as _checkpoints
from test_native_neural_production import cpu_threads as _cpu_threads
from test_natural_candidate_position import PublicPixelCamera
from test_owned_position_delivery import state

from cpswm.system.surface_episode import (
    PREFIX,
    collect_scheduled_surface,
    effective_surface_state,
    policy_reason,
    surface_report,
)

checkpoints = _checkpoints
cpu_threads = _cpu_threads


@pytest.fixture(scope="module")
def weights():
    paths = [Path(os.environ.get(k, "")) for k in ("CPSWM_SSDLITE_WEIGHTS", "CPSWM_MASK_WEIGHTS")]
    if not all(p.is_file() for p in paths):
        pytest.skip("explicit two pinned checkpoints required")
    return paths


def test_real_mask_surface_owned_sequence_duplicate_and_budget(
    tmp_path, checkpoints, weights, monkeypatch
):
    schedule = [dict(action="RotateRight", degrees=1.0)] * 2
    case = make_case(tmp_path / "state.db", checkpoints, *weights, schedule=schedule)
    try:
        stream = case["stream"]
        camera = PublicPixelCamera(stream._scope)
        before = stream.current_joint_decision_view()
        first = collect_scheduled_surface(stream, executor=camera, decision_time=case["when"])
        from cpswm.system.native_neural_production import (
            NeuralNativeProducer,
            verify_neural_evidence,
        )
        from cpswm.system.reproducibility import canonical_json
        from cpswm.system.temporal_target_position import TemporalTargetPositionProducer

        when = first[1].received_at + timedelta(seconds=1)
        ids = tuple(
            r.envelope().identity.observation_id for r in stream.visible_prefix(cutoff=when)
        )
        reason = policy_reason(
            stream, view=stream.current_joint_decision_view(), source_ids=ids, index=1
        )
        command = stream.prepare_observation(
            action=reason["action"],
            degrees=reason["degrees"],
            reason=PREFIX + canonical_json(reason),
            source_ids=ids,
            decision_time=when,
        )
        delivery = stream.execute_observation(command, executor=camera)
        for fault in ("complete_aggregate", "published"):
            saved_before = state(case)
            attacked, proofs = [], []

            def attack(frame, event, value, fault=fault, attacked=attacked, proofs=proofs):
                if event != "return":
                    return
                if fault == "published" and frame.f_code.co_name == "_cancel_stale_joint_commands":
                    attacked.append(True)
                    raise RuntimeError("injected surface publication failure")
                if (
                    fault == "complete_aggregate"
                    and not attacked
                    and frame.f_code is TemporalTargetPositionProducer.produce.__code__
                    and frame.f_locals.get("self") is case["candidate"]
                ):
                    object.__setattr__(
                        value, "unresolved_log_weight", value.unresolved_log_weight + 1
                    )
                    attacked.append(True)
                if (
                    frame.f_code is NeuralNativeProducer.produce.__code__
                    and frame.f_locals.get("self") is case["joint"]
                    and value is not None
                ):
                    verify_neural_evidence(value.neural_evidence)
                    proofs.append(True)

            original = sys.getprofile()
            sys.setprofile(attack)
            try:
                with pytest.raises(
                    (ValueError, RuntimeError),
                    match=r"complete owner recomputation|injected surface",
                ):
                    stream.consume_owned_position_observation(command.action_id)
            finally:
                sys.setprofile(original)
            assert attacked and state(case) == saved_before
            if fault == "complete_aggregate":
                assert proofs == [True]
            assert camera.calls == 2
        update = stream.consume_owned_position_observation(command.action_id)
        second = command, delivery, update
        data = effective_surface_state(stream)
        assert len(data["records"]) == 2 and camera.calls == 2
        assert all(len(v) <= 1 for v in data["history"].values())
        assert any(data["history"].values())
        assert all(
            np.array_equal(a.statistics.information, before.atoms[0].statistics.information)
            for a in stream.current_joint_decision_view().atoms
        )
        report = surface_report(
            stream, category="bottle", ordinal=0, reference_action=str(first[0].action_id)
        )
        assert report["status"] == "reported" and report["action_id"] == str(second[0].action_id)
        saved = state(case)
        stream.consume_owned_position_observation(first[0].action_id)
        assert state(case) == saved
        assert (
            collect_scheduled_surface(
                stream, executor=camera, decision_time=second[1].received_at + timedelta(seconds=1)
            )
            is None
        )
        assert camera.calls == 2
        from cpswm.perception_mapping import mask_surface_sequence, natural_mask_surface

        def forged_surface(*args, **kwargs):
            return {"world_point_m": [0.0, 0.0, 0.0]}

        with monkeypatch.context() as patch:
            patch.setattr(natural_mask_surface, "select_surface", forged_surface)
            patch.setattr(mask_surface_sequence, "select_surface", forged_surface)
            with pytest.raises(ValueError, match="dependency changed"):
                stream.current_joint_decision_view()
        assert state(case) == saved
        stream.withdraw_owned_position_observation(
            first[0].action_id, reason="withdraw initial support"
        )
        report = surface_report(
            stream, category="bottle", ordinal=0, reference_action=str(first[0].action_id)
        )
        assert report["status"] == "unknown" and report["world_point_m"] is None
        assert camera.calls == 2 and len(stream.observation_history()) == 2
    finally:
        case["store"].close()
