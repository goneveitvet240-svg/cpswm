"""Matched development controls. No model selection or runtime authority."""

from __future__ import annotations

import copy
import math
from typing import Any

import torch
import torch.nn.functional as F
from torch import Tensor, nn

from cpswm.data_preflight.full_hfd_training import encoded
from cpswm.data_preflight.hocap_joint_supervision import strict_json
from cpswm.data_preflight.visor_candidate_alignment import sha
from cpswm.data_preflight.visor_pixel_probe import (
    head_new,
    logits_image,
    masked_loss,
    state_digest,
    tensor_digest,
)
from cpswm.data_preflight.visor_pixel_supervision import AXES, VOID

CONFIG = {
    "format": "visor_matched_feature_control_v1",
    "train_ordinals": list(range(8)),
    "budgets": [16, 128],
    "lr": 0.01,
    "optimizer": "SGD_no_momentum",
    "init": "zeros",
    "feature": "existing_frozen_fpn_0",
    "loss": "sum_of_available_axis_mean_masked_BCE",
    "selection": "none_both_budgets_reported",
}


def new_head(arm: str) -> nn.Conv2d:
    if arm not in {"feature", "bias"}:
        raise ValueError("unknown control arm")
    head = head_new()
    if arm == "bias":
        head.weight.requires_grad_(False)
    return head


def save_head(head: nn.Conv2d, arm: str, step: int) -> bytes:
    assert head.bias is not None
    return encoded(
        {
            "config": CONFIG,
            "arm": arm,
            "step": step,
            "weight": head.weight.detach().tolist(),
            "bias": head.bias.detach().tolist(),
        }
    )


def restore(raw: bytes, expected_sha: str) -> nn.Conv2d:
    if len(raw) > 65536 or sha(raw) != expected_sha:
        raise ValueError("checkpoint differs from external execution digest")
    doc = strict_json(raw)
    if (
        set(doc) != {"config", "arm", "step", "weight", "bias"}
        or doc["config"] != CONFIG
        or type(doc["step"]) is not int
        or doc["step"] not in (16, 128)
    ):
        raise ValueError("invalid control checkpoint")
    head = new_head(doc["arm"])
    weight = torch.tensor(doc["weight"], dtype=torch.float32)
    bias = torch.tensor(doc["bias"], dtype=torch.float32)
    if (
        weight.shape != (2, 256, 1, 1)
        or bias.shape != (2,)
        or not bool(torch.isfinite(weight).all() and torch.isfinite(bias).all())
        or (doc["arm"] == "bias" and bool(weight.any()))
    ):
        raise ValueError("invalid control tensors")
    head.load_state_dict({"weight": weight, "bias": bias}, strict=True)
    return head


def measure(head: nn.Module, feature: dict[str, Any], target: Tensor) -> dict[str, Any]:
    with torch.no_grad():
        logits = logits_image(head, feature)
        loss, axes = masked_loss(logits, target)
        for i, axis in enumerate(AXES):
            for label, name in [(0, "negative"), (1, "positive")]:
                mask = target[i] == label
                axes[axis][name + "_pixels"] = int(mask.sum())
                axes[axis][name + "_bce"] = (
                    float(
                        F.binary_cross_entropy_with_logits(logits[i][mask], target[i][mask].float())
                    )
                    if bool(mask.any())
                    else None
                )
        return {"objective": float(loss), "axes": axes, "logits_sha256": tensor_digest(logits)}


def step_once(head: nn.Conv2d, feature: dict[str, Any], target: Tensor) -> dict[str, Any]:
    opt = torch.optim.SGD([p for p in head.parameters() if p.requires_grad], lr=0.01)
    opt.zero_grad(set_to_none=True)
    before = state_digest(head)
    loss, axes = masked_loss(logits_image(head, feature), target)
    if not any(a["pixels"] for a in axes.values()):
        raise ValueError("fixed training frame has no supervision")
    loss.backward()  # type: ignore[no-untyped-call]
    grads = [p.grad for p in head.parameters() if p.requires_grad and p.grad is not None]
    if not grads or not all(bool(torch.isfinite(g).all()) for g in grads):
        raise ValueError("invalid control gradient")
    norm = float(torch.sqrt(torch.stack([g.square().sum() for g in grads]).sum()))
    if not math.isfinite(norm):
        raise ValueError("nonfinite control gradient")
    opt.step()
    if not all(bool(torch.isfinite(p).all()) for p in head.parameters()):
        raise ValueError("nonfinite updated parameters")
    return {
        "before": before,
        "after": state_digest(head),
        "gradient_norm": norm,
        "objective": float(loss.detach()),
        "axes": axes,
    }


def analytic_constant(targets: list[Tensor]) -> tuple[nn.Conv2d, list[float]]:
    """Optimum constant for the actual equal-frame, per-available-axis loss."""
    probabilities = []
    for i in range(2):
        ratios = [
            float((t[i] == 1).sum()) / int((t[i] != VOID).sum())
            for t in targets
            if bool((t[i] != VOID).any())
        ]
        if not ratios:
            raise ValueError("no training support for axis")
        p = sum(ratios) / len(ratios)
        if not 0 < p < 1:
            raise ValueError("finite constant requires both training labels")
        probabilities.append(p)
    head = new_head("bias")
    with torch.no_grad():
        assert head.bias is not None
        head.bias.copy_(torch.tensor([math.log(p / (1 - p)) for p in probabilities]))
    head.requires_grad_(False)
    return head, probabilities


def train_controls(
    features: list[dict[str, Any]], targets: list[Tensor]
) -> tuple[dict[str, nn.Conv2d], dict[str, bytes], dict[str, Any]]:
    if len(features) != 8 or len(targets) != 8:
        raise ValueError("exactly the fixed eight training frames required")
    for f in features:
        x = f["feature"]
        if (
            x.ndim != 4
            or x.shape[:2] != (1, 256)
            or x.requires_grad
            or not bool(torch.isfinite(x).all())
        ):
            raise ValueError("finite frozen 256-channel RGB features required")
    heads, artifacts, updates = {}, {}, {}
    recovery = []
    for arm in ("feature", "bias"):
        head = new_head(arm)
        events = []
        for step in range(1, 129):
            i = (step - 1) % 8
            events.append({"step": step, "ordinal": i, **step_once(head, features[i], targets[i])})
            if step in (16, 128):
                name = f"{arm}_{step}"
                raw = save_head(head, arm, step)
                restored = restore(raw, sha(raw))
                outputs = [measure(head, f, t) for f, t in zip(features, targets, strict=True)]
                if outputs != [
                    measure(restored, f, t) for f, t in zip(features, targets, strict=True)
                ]:
                    raise ValueError("restored full outputs differ")
                # Two disposable instances; never advance the retained checkpoint.
                a, b = copy.deepcopy(head), restore(raw, sha(raw))
                ra = step_once(a, features[0], targets[0])
                rb = step_once(b, features[0], targets[0])
                if ra != rb:
                    raise ValueError("restored next update differs")
                recovery.append(
                    {
                        "arm": arm,
                        "step": step,
                        "full_outputs_equal": True,
                        "next_update_equal": True,
                        "next_update_sha256": ra["after"],
                    }
                )
                heads[name] = restored
                artifacts[name + ".json"] = raw
        updates[arm] = events
    constant, probabilities = analytic_constant(targets)
    heads["analytic_constant"] = constant
    return (
        heads,
        artifacts,
        {
            "config": CONFIG,
            "updates": updates,
            "recovery": recovery,
            "constant_probabilities": probabilities,
            "training_updates": 256,
            "verification_extra_updates": 8,
        },
    )


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("cannot summarize empty diagnostic")
    axes = {}
    for axis in AXES:
        a: dict[str, Any] = {}
        for label in ("positive", "negative"):
            count = sum(r["axes"][axis][label + "_pixels"] for r in rows)
            supported = [r["axes"][axis] for r in rows if r["axes"][axis][label + "_pixels"]]
            a[label + "_pixels"] = count
            a[label + "_frames"] = len(supported)
            a[label + "_bce_equal_frame"] = (
                sum(r[label + "_bce"] for r in supported) / len(supported) if supported else None
            )
        axes[axis] = a
    return {
        "frames": len(rows),
        "objective_equal_frame": sum(r["objective"] for r in rows) / len(rows),
        "axes": axes,
    }
