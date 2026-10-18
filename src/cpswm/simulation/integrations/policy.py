"""Official LIBERO observation convention and revision-bound action chunks."""

from __future__ import annotations

from collections import deque
from importlib import import_module
from typing import Any

import numpy as np


def policy_input(obs: dict[str, Any], prompt: str) -> dict[str, Any]:
    image_tools = import_module("openpi_client.image_tools")

    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("an explicit task instruction is required")
    images = {}
    for source, target in (
        ("agentview_image", "observation/image"),
        ("robot0_eye_in_hand_image", "observation/wrist_image"),
    ):
        img = np.asarray(obs[source])
        if img.dtype != np.uint8 or img.ndim != 3 or img.shape[-1] != 3:
            raise ValueError("expected HWC uint8 RGB")
        # Match openpi examples/libero/main.py, not a vertical-only flip.
        images[target] = image_tools.resize_with_pad(
            np.ascontiguousarray(img[::-1, ::-1]), 224, 224
        )
    pos = np.asarray(obs["robot0_eef_pos"], dtype=np.float64)
    quat = np.asarray(obs["robot0_eef_quat"], dtype=np.float64).copy()  # xyzw
    gripper = np.asarray(obs["robot0_gripper_qpos"], dtype=np.float64)
    if pos.shape != (3,) or quat.shape != (4,) or gripper.shape != (2,):
        raise ValueError("expected LIBERO state 3+axisangle3+gripper2")
    if not all(np.isfinite(x).all() for x in (pos, quat, gripper)):
        raise ValueError("non-finite robot state")
    if not np.isclose(np.linalg.norm(quat), 1.0, atol=1e-3):
        raise ValueError("invalid quaternion")
    w = np.clip(quat[3], -1.0, 1.0)
    den = np.sqrt(1.0 - w * w)
    aa = np.zeros(3) if np.isclose(den, 0.0) else quat[:3] * 2 * np.arccos(w) / den
    return {**images, "observation/state": np.concatenate((pos, aa, gripper)), "prompt": prompt}


class ActionChunks:
    """Never reuse a chunk after evidence/goal revision; no silent action clipping."""

    def __init__(self, replan_steps: int = 5) -> None:
        if type(replan_steps) is not int or replan_steps < 1:
            raise ValueError("positive replan_steps required")
        self.replan_steps = replan_steps
        self.actions: deque[np.ndarray[Any, Any]] = deque()
        self.binding: tuple[str, str] | None = None
        self.cancelled_actions = 0

    def bind(self, revision: str, prompt: str) -> None:
        binding = (revision, prompt)
        if binding != self.binding:
            self.cancelled_actions += len(self.actions)
            self.actions.clear()
            self.binding = binding

    def load(self, output: dict[str, Any]) -> None:
        a = np.asarray(output["actions"], dtype=np.float64)
        if self.binding is None or self.actions:
            raise ValueError("bind an empty chunk queue first")
        if a.ndim != 2 or a.shape[1] != 7 or len(a) < self.replan_steps:
            raise ValueError("expected at least replan_steps by 7 OSC_POSE actions")
        if not np.isfinite(a).all():
            raise ValueError("non-finite policy action")
        # Raw decoded policy actions are preserved; robosuite applies its declared
        # controller input limits. No renormalization or gripper sign inversion.
        self.actions.extend(row.copy() for row in a[: self.replan_steps])

    def pop(self, revision: str, prompt: str) -> np.ndarray[Any, Any]:
        if self.binding != (revision, prompt):
            self.bind(revision, prompt)
            raise ValueError("stale action chunk cancelled")
        return self.actions.popleft()


class SmokePolicy:
    """Explicit actuator diagnostic, never labelled pi0.5 inference."""

    def infer(self, _: dict[str, Any]) -> dict[str, Any]:
        a = np.zeros((5, 7))
        a[:, 6] = -1
        a[:, 2] = 0.05
        return {"actions": a}


def local_pi05(checkpoint: str, device: str = "cpu") -> Any:
    """Inference-only construction matching pinned official pi05_libero config.

    Avoids importing unrelated CUDA training/data-loader dependencies on macOS.
    All network layers, tokenizer, normalization and action transforms are upstream.
    """
    from pathlib import Path

    if device != "cpu":
        raise ValueError(
            "official downloaded checkpoint is JAX; this Mac path requires CPU, not MPS"
        )
    jax = import_module("jax")
    jnp = import_module("jax.numpy")
    t = import_module("openpi.transforms")
    model = import_module("openpi.models.model")
    pi0_config = import_module("openpi.models.pi0_config")
    tokenizer = import_module("openpi.models.tokenizer")
    libero_policy = import_module("openpi.policies.libero_policy")
    policy = import_module("openpi.policies.policy")
    normalize = import_module("openpi.shared.normalize")

    if any(d.platform != "cpu" for d in jax.devices()):
        raise RuntimeError("Mac inference entry requires JAX_PLATFORMS=cpu")
    path = Path(checkpoint).resolve()
    config = pi0_config.Pi0Config(
        pi05=True, action_horizon=10, discrete_state_input=False, pytorch_compile_mode=None
    )
    print("pi05: restoring official checkpoint on CPU", flush=True)
    weights = model.restore_params(path / "params", dtype=jnp.bfloat16)
    print("pi05: checkpoint restored; constructing upstream model", flush=True)
    network = config.load(weights)
    stats = normalize.load(path / "assets/physical-intelligence/libero")
    return policy.Policy(
        network,
        transforms=[
            libero_policy.LiberoInputs(model_type=config.model_type),
            t.InjectDefaultPrompt(None),
            t.Normalize(stats, use_quantiles=True),
            t.InjectDefaultPrompt(None),
            t.ResizeImages(224, 224),
            t.TokenizePrompt(
                tokenizer.PaligemmaTokenizer(config.max_token_len), discrete_state_input=False
            ),
            t.PadStatesAndActions(config.action_dim),
        ],
        output_transforms=[t.Unnormalize(stats, use_quantiles=True), libero_policy.LiberoOutputs()],
        metadata={
            "config": "pi05_libero",
            "checkpoint": str(path),
            "device": "cpu",
            "policy_rng_seed": 0,  # pinned upstream Policy default; simulator seed is separate
            "upstream": "215abfb217dbac7d5f1273282331b9b1866c0479",
        },
    )
