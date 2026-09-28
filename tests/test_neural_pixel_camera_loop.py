"""Pixel-only transport, fixed scene setup and real checkpoint/camera composition."""

import base64
import io
import json
import sys
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import numpy as np
import pytest
from test_joint_camera_feedback import execute, setup
from test_native_joint_production import JointFixture
from test_native_neural_production import checkpoints as _checkpoint_fixture
from test_native_neural_production import cpu_threads as _thread_fixture

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from run_neural_pixel_camera_loop import DiagnosticViewModel, diagnostic_house
from unity_camera_feedback_worker import method_response, validate_request

from cpswm.data_preflight.typed_proposal_networks import ARMS
from cpswm.system.native_neural_production import NeuralNativeProducer

checkpoints = _checkpoint_fixture
cpu_threads = _thread_fixture


@pytest.mark.parametrize("arm", ARMS)
def test_actual_neural_native_prior_accepts_real_owned_pixel_measurements(
    tmp_path, checkpoints, arm
):
    path, pin = checkpoints[arm]
    joint = NeuralNativeProducer(JointFixture(), path, manifest_sha256=pin)
    stream, store, transition, _, start = setup(tmp_path / "db", joint=joint)
    before, _, _, _, _ = execute(stream, transition, start + timedelta(seconds=2))
    diagnostic = DiagnosticViewModel(None)
    p = diagnostic.problem(before, stream.visible_prefix(cutoff=start), decision_time=start)
    plan, selected = p.select(before, stream._system.cause_information_planner)
    assert plan.should_act and selected is not None and selected.degrees == 45
    after = stream.current_joint_decision_view()
    assert after != before and len(after.observation_evidence) == 1
    assert joint.calls == 1 and len(stream.joint_observation_updates()) == 1
    assert tuple(a.statistics for a in before.atoms) == tuple(a.statistics for a in after.atoms)
    store.close()


def test_transport_releases_pixels_and_status_without_reading_truth_fields():
    class TruthTrap(dict):
        def get(self, key, *default):
            assert key in {"lastActionSuccess", "errorMessage"}
            return super().get(key, *default)

    rgb = np.full((4, 4, 3), 71, dtype=np.uint8)
    event = SimpleNamespace(
        frame=rgb,
        metadata=TruthTrap(
            lastActionSuccess=True, errorMessage="", objects=["hidden"], agent={"hidden": True}
        ),
    )
    identity = str(uuid4())
    response = method_response(identity, event)
    assert set(response) == {"action_id", "capture_time", "success", "error", "rgb_npy"}
    assert np.array_equal(
        np.load(io.BytesIO(base64.b64decode(response["rgb_npy"])), allow_pickle=False), rgb
    )


@pytest.mark.parametrize(
    "action,degrees",
    [
        ("Pass", 1),
        ("RotateRight", 0),
        ("RotateLeft", 91),
        ("TeleportObject", 1),
        ("RotateLeft", float("nan")),
    ],
)
def test_worker_rejects_unbounded_or_non_camera_commands(action, degrees):
    with pytest.raises(ValueError, match=r"unsupported|unbounded"):
        validate_request({"action_id": str(uuid4()), "action": action, "degrees": degrees}, set())


def test_worker_does_not_repeat_complete_command():
    request = {"action_id": str(uuid4()), "action": "RotateRight", "degrees": 45}
    assert validate_request(request, set())[1:] == ("RotateRight", {"degrees": 45})
    with pytest.raises(ValueError, match="redispatch"):
        validate_request(request, {request["action_id"]})


def test_two_scene_initializations_have_same_public_camera_and_only_target_position_differs():
    root = Path(__file__).resolve().parents[1]
    original = json.loads(
        (
            root
            / "docs/reviews/pc_a/proposal_scheduler_2026-09-13/procthor_run_07/train_house.json"
        ).read_text()
    )
    encoded = json.dumps(original, sort_keys=True)
    north, south = (diagnostic_house(original, site) for site in ("north", "south"))
    assert north["metadata"] == south["metadata"]
    n = next(x for x in north["objects"][0]["children"] if x["id"] == "Apple|surface|2|0")
    s = next(x for x in south["objects"][0]["children"] if x["id"] == "Apple|surface|2|0")
    assert n["position"]["z"] != s["position"]["z"]
    s["position"] = n["position"]
    assert north == south and json.dumps(original, sort_keys=True) == encoded


def test_public_action_ids_do_not_depend_on_hidden_receipt_hashes(tmp_path):
    from dataclasses import replace

    stream, store, _, _, when = setup(tmp_path / "db")
    view = stream.current_joint_decision_view()
    model = DiagnosticViewModel(None)
    raw = stream.visible_prefix(cutoff=when)
    p = model.problem(view, raw, decision_time=when)
    altered = tuple(replace(x, capture_receipt_sha256="f" * 64) for x in raw)
    q = model.problem(view, altered, decision_time=when)
    assert p == q
    assert p.select(view, stream._system.cause_information_planner) == q.select(
        view, stream._system.cause_information_planner
    )
    store.close()
