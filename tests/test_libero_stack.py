"""Integration contracts; actual model/physics runs are recorded separately."""

from pathlib import Path

import numpy as np
import pytest

from cpswm.simulation.integrations.bridge import NativeBridge
from cpswm.simulation.integrations.libero_env import public_observation
from cpswm.simulation.integrations.perception import Sam2Tracker, visual_event
from cpswm.simulation.integrations.policy import ActionChunks, local_pi05, policy_input


def raw_observation():
    image = np.arange(12, dtype=np.uint8).reshape(2, 2, 3)
    return {
        "agentview_image": image,
        "robot0_eye_in_hand_image": image + 10,
        "robot0_eef_pos": np.array([0.1, 0.2, 0.3]),
        "robot0_eef_quat": np.array([0.0, 0.0, 0.0, 1.0]),
        "robot0_gripper_qpos": np.array([0.01, -0.01]),
    }


def test_official_image_orientation_and_state_not_mutated():
    from openpi_client.image_tools import resize_with_pad

    obs = raw_observation()
    before = obs["robot0_eef_quat"].copy()
    data = policy_input(obs, "put bowl on plate")
    assert np.array_equal(
        data["observation/image"], resize_with_pad(obs["agentview_image"][::-1, ::-1], 224, 224)
    )
    assert data["observation/state"].tolist() == [0.1, 0.2, 0.3, 0.0, 0.0, 0.0, 0.01, -0.01]
    assert np.array_equal(obs["robot0_eef_quat"], before)
    assert data["prompt"] == "put bowl on plate"


@pytest.mark.parametrize(
    "field,value",
    [
        ("robot0_eef_pos", [float("nan"), 0, 0]),
        ("robot0_eef_quat", [0, 0, 0, 0]),
        ("robot0_gripper_qpos", [0]),
        ("agentview_image", np.zeros((2, 2, 3))),
    ],
)
def test_invalid_policy_observation_rejected(field, value):
    obs = raw_observation()
    obs[field] = np.asarray(value)
    with pytest.raises(ValueError):
        policy_input(obs, "task")


def test_ground_truth_is_not_forwarded():
    obs = raw_observation()
    obs.update(object_states=[1, 2], success=True, body_id=17)
    public = public_observation(obs)
    assert set(public) == set(raw_observation())
    public["agentview_image"][:] = 0
    assert obs["agentview_image"].any()


def test_chunk_preserves_action_semantics_and_cancels_on_revision():
    q = ActionChunks(2)
    q.bind("v1", "plate")
    q.load({"actions": [[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, -1], [0, 0, 0, 0, 0, 0, 1]]})
    assert q.pop("v1", "plate")[-1] == -1
    with pytest.raises(ValueError):
        q.pop("v2", "plate")
    assert q.cancelled_actions == 1 and not q.actions
    q.load({"actions": np.zeros((2, 7))})
    q.bind("v2", "drawer")
    assert q.cancelled_actions == 3


@pytest.mark.parametrize(
    "actions", [np.zeros((7,)), np.zeros((1, 7)), np.zeros((2, 8)), np.full((2, 7), np.nan)]
)
def test_bad_chunk_rejected_atomically(actions):
    q = ActionChunks(2)
    q.bind("r", "task")
    with pytest.raises(ValueError):
        q.load({"actions": actions})
    assert not q.actions


def test_visual_predictions_and_losses_are_not_independent_sightings():
    mask = np.zeros((20, 30), bool)
    mask[2:8, 2:8] = True
    first = visual_event("e", 0, mask, initialized=True, image_digest="a")
    pred = visual_event("e", 1, mask, initialized=False, image_digest="b")
    lost = visual_event("e", 2, np.zeros_like(mask), initialized=False, image_digest="c")
    assert first["visibility"] == "observed" and first["location"] == "image_left"
    assert pred["visibility"] == "predicted" and pred["identity_probability"] == 0
    assert lost["visibility"] == "lost" and lost["location"] is None
    assert all(x["actors"] == [["unknown_actor", 1.0]] for x in (first, pred, lost))


class PrefixPredictor:
    def __init__(self):
        self.seen = []

    def init_state(self, path, **kwargs):
        files = sorted(Path(path).glob("*.jpg"))
        self.seen.append(len(files))
        return {"n": len(files)}

    def add_new_points_or_box(self, **kwargs):
        import torch

        assert kwargs["frame_idx"] == 0 and kwargs["obj_id"] == 1
        return 0, [1], torch.ones((1, 1, 20, 30))

    def propagate_in_video(self, state, **kwargs):
        import torch

        assert kwargs["max_frame_num_to_track"] == state["n"] - 1
        for i in range(state["n"]):
            yield i, [1], torch.ones((1, 1, 20, 30))


def test_sam_adapter_sees_only_received_prefix_and_needs_explicit_reset(tmp_path):
    predictor = PrefixPredictor()
    t = Sam2Tracker(
        tmp_path / "unused.pt",
        tmp_path / "frames",
        [1, 1, 10, 10],
        max_frames=2,
        predictor=predictor,
    )
    image = np.zeros((20, 30, 3), np.uint8)
    a, _ = t.observe(image, "e", 0)
    b, _ = t.observe(image, "e", 5)
    assert predictor.seen == [1, 2]
    assert a["visibility"] == "observed" and b["visibility"] == "predicted"
    with pytest.raises(ValueError):
        t.observe(image, "e", 4)
    with pytest.raises(RuntimeError, match="prefix limit"):
        t.observe(image, "e", 10)


def test_native_cross_environment_receipt_and_failed_input_recovery():
    root = Path(__file__).resolve().parents[1]
    python = root.parent / "envs/core/bin/python"
    if not python.exists():
        pytest.skip("requires separate locked CPSWM core environment")
    b = NativeBridge(str(python), root, "real-native-contract")
    try:
        mask = np.ones((20, 30), bool)
        event = visual_event("real-native-contract", 0, mask, initialized=True, image_digest="a")
        receipt = b.observe(event)
        assert receipt["ok"] and receipt["current_location"] == "image_center"
        assert receipt["revision"] != b.initial["revision"]
        with pytest.raises(RuntimeError):
            b.observe(event)
        next_event = visual_event(
            "real-native-contract", 1, mask, initialized=False, image_digest="b"
        )
        next_receipt = b.observe(next_event)
        assert next_receipt["ok"] and next_receipt["current_location"] is None
    finally:
        b.close()
    assert b.process.poll() is not None


def test_jax_weights_not_mislabelled_as_mps():
    with pytest.raises(ValueError, match="requires CPU"):
        local_pi05("missing", "mps")


def test_official_inference_dependencies_and_checkpoint_normalization():
    # Regression: a successful lightweight adapter import previously hid the
    # incompatible Pydantic/numpydantic combination until the full model run.
    from openpi.models import pi0_config, tokenizer
    from openpi.policies import policy
    from openpi.shared import normalize

    config = pi0_config.Pi0Config(pi05=True, action_horizon=10, discrete_state_input=False)
    assert config.max_token_len == 200 and config.action_dim == 32
    assert callable(tokenizer.PaligemmaTokenizer) and callable(policy.Policy)
    stats = normalize.NormStats(mean=np.zeros(7), std=np.ones(7), q01=-np.ones(7), q99=np.ones(7))
    assert stats.mean.shape == (7,)
