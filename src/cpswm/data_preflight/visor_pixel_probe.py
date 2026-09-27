"""Bounded learning-health probe on frozen existing RGB features, not a new method.

The 2-channel readout is isolated from the deployed detectors/proposal networks.
Losses on used/neighboring training-video frames are not generalization evidence.
"""

from __future__ import annotations

import io
import math
import re
from typing import Any

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from torch import Tensor, nn

from cpswm.data_preflight.full_hfd_training import encoded
from cpswm.data_preflight.hocap_joint_supervision import strict_json
from cpswm.data_preflight.visor_candidate_alignment import sha
from cpswm.data_preflight.visor_pixel_supervision import AXES, VOID

CONFIG: dict[str, Any] = {
    "format": "visor_pixel_linear_probe_v1",
    "feature": "existing_frozen_fpn_0",
    "train_ordinals": list(range(8)),
    "diagnostic_ordinals": list(range(8, 16)),
    "passes": 2,
    "optimizer": "SGD_no_momentum",
    "lr": 0.01,
    "init": "zeros",
    "loss": "sum_of_available_axis_mean_masked_BCE",
    "formal_model_selection": False,
}


def head_new(channels: int = 256) -> nn.Conv2d:
    head = nn.Conv2d(channels, 2, 1)
    assert head.bias is not None
    nn.init.zeros_(head.weight)
    nn.init.zeros_(head.bias)
    return head


def tensor_digest(tensor: Tensor) -> str:
    a = tensor.detach().cpu().contiguous().numpy()
    return sha(encoded({"shape": list(a.shape), "dtype": str(a.dtype)}) + a.tobytes())


def state_digest(model: nn.Module) -> str:
    return sha(encoded({name: tensor_digest(t) for name, t in sorted(model.state_dict().items())}))


def labels_from_png(targets: dict[str, bytes]) -> Tensor:
    arrays = []
    for axis in AXES:
        with Image.open(io.BytesIO(targets[axis])) as image:
            if image.mode != "L" or image.format != "PNG":
                raise ValueError("target must be grayscale PNG")
            a = np.asarray(image).copy()
        if a.ndim != 2 or not np.isin(a, (0, 1, VOID)).all():
            raise ValueError("target has invalid labels")
        arrays.append(torch.from_numpy(a))
    return torch.stack(arrays)


def extract_rgb(model: Any, jpeg: bytes) -> dict[str, Any]:
    """Only JPEG pixels enter the exact existing image transform/backbone."""
    with Image.open(io.BytesIO(jpeg)) as image:
        a = np.asarray(image).copy()
    if a.dtype != np.uint8 or a.ndim != 3 or a.shape[2] != 3:
        raise ValueError("RGB uint8 image required")
    tensor = torch.from_numpy(a).permute(2, 0, 1).float() / 255
    with torch.no_grad():
        transformed, _ = model.transform([tensor], None)
        feature = model.backbone(transformed.tensors)["0"].detach()
    return {
        "feature": feature,
        "original": tuple(a.shape[:2]),
        "resized": tuple(transformed.image_sizes[0]),
        "padded": tuple(transformed.tensors.shape[-2:]),
    }


def logits_image(head: nn.Module, feature: dict[str, Any]) -> Tensor:
    logits = head(feature["feature"])
    resized = F.interpolate(logits, size=feature["padded"], mode="bilinear", align_corners=False)
    h, w = feature["resized"]
    return F.interpolate(
        resized[:, :, :h, :w], size=feature["original"], mode="bilinear", align_corners=False
    )[0]


def masked_loss(logits: Tensor, target: Tensor) -> tuple[Tensor, dict[str, Any]]:
    if logits.shape != target.shape or logits.ndim != 3 or logits.shape[0] != 2:
        raise ValueError("two full-frame target axes must align with logits")
    if target.dtype != torch.uint8 or not bool(
        ((target == 0) | (target == 1) | (target == VOID)).all()
    ):
        raise ValueError("invalid target encoding")
    if not bool(torch.isfinite(logits).all()):
        raise ValueError("nonfinite logits")
    losses, summary = [], {}
    for i, axis in enumerate(AXES):
        valid = target[i] != VOID
        count = int(valid.sum())
        loss = (
            F.binary_cross_entropy_with_logits(logits[i][valid], target[i][valid].float())
            if count
            else None
        )
        if loss is not None:
            losses.append(loss)
        summary[axis] = {
            "pixels": count,
            "positive": int((target[i] == 1).sum()),
            "loss": float(loss.detach()) if loss is not None else None,
        }
    total = sum(losses, logits.sum() * 0)
    return total, summary


def head_bytes(head: nn.Conv2d, *, step: int, source_manifest: str) -> bytes:
    assert head.bias is not None
    return encoded(
        {
            "config": CONFIG,
            "step": step,
            "source_manifest": source_manifest,
            "weight": head.weight.detach().tolist(),
            "bias": head.bias.detach().tolist(),
        }
    )


def restore_head(raw: bytes, expected_sha256: str) -> nn.Conv2d:
    if len(raw) > 65536 or sha(raw) != expected_sha256:
        raise ValueError("checkpoint differs from fixed execution digest")
    doc = strict_json(raw)
    if (
        set(doc) != {"config", "step", "source_manifest", "weight", "bias"}
        or doc["config"] != CONFIG
        or type(doc["step"]) is not int
        or not 0 <= doc["step"] <= 16
        or not isinstance(doc["source_manifest"], str)
        or re.fullmatch(r"[0-9a-f]{64}", doc["source_manifest"]) is None
    ):
        raise ValueError("checkpoint configuration differs")
    weight, bias = (
        torch.tensor(doc["weight"], dtype=torch.float32),
        torch.tensor(doc["bias"], dtype=torch.float32),
    )
    if (
        weight.shape != (2, 256, 1, 1)
        or bias.shape != (2,)
        or not bool(torch.isfinite(weight).all() and torch.isfinite(bias).all())
    ):
        raise ValueError("checkpoint tensors invalid")
    head = head_new()
    head.load_state_dict({"weight": weight, "bias": bias}, strict=True)
    return head


def measurements(
    head: nn.Module, features: list[dict[str, Any]], targets: list[Tensor]
) -> list[dict[str, Any]]:
    rows = []
    with torch.no_grad():
        for feature, target in zip(features, targets, strict=True):
            logits = logits_image(head, feature)
            loss, axes = masked_loss(logits, target)
            rows.append(
                {"logits_sha256": tensor_digest(logits), "objective": float(loss), "axes": axes}
            )
    return rows


def fit(
    features: list[dict[str, Any]], targets: list[Tensor], source_manifest: str
) -> tuple[dict[str, Any], bytes]:
    if len(features) != 16 or len(targets) != 16:
        raise ValueError("fixed complete 16-frame prefix required")
    head = head_new()
    before = measurements(head, features, targets)
    optimizer = torch.optim.SGD(head.parameters(), lr=CONFIG["lr"])
    events: list[dict[str, Any]] = []
    for epoch in range(2):
        for ordinal in range(8):
            optimizer.zero_grad(set_to_none=True)
            loss, axes = masked_loss(logits_image(head, features[ordinal]), targets[ordinal])
            if not any(r["pixels"] for r in axes.values()):
                events.append({"epoch": epoch, "ordinal": ordinal, "updated": False, "axes": axes})
                continue
            old = state_digest(head)
            loss.backward()  # type: ignore[no-untyped-call]
            grads = [p.grad for p in head.parameters() if p.grad is not None]
            if not grads or not all(bool(torch.isfinite(g).all()) for g in grads):
                raise ValueError("missing/nonfinite real gradient")
            gradient_norm = float(torch.sqrt(torch.stack([g.square().sum() for g in grads]).sum()))
            if not math.isfinite(gradient_norm):
                raise ValueError("nonfinite gradient norm")
            optimizer.step()
            events.append(
                {
                    "epoch": epoch,
                    "ordinal": ordinal,
                    "updated": True,
                    "axes": axes,
                    "gradient_norm": gradient_norm,
                    "before": old,
                    "after": state_digest(head),
                }
            )
    after = measurements(head, features, targets)
    checkpoint = head_bytes(
        head, step=sum(e["updated"] for e in events), source_manifest=source_manifest
    )
    restored = restore_head(checkpoint, sha(checkpoint))
    if measurements(restored, features, targets) != after:
        raise ValueError("restored model differs on full pixel outputs")

    # Verify the next actual SGD update from restored parameters, not only reads.
    def next_step(model: nn.Conv2d) -> str:
        opt = torch.optim.SGD(model.parameters(), lr=CONFIG["lr"])
        opt.zero_grad(set_to_none=True)
        loss, _ = masked_loss(logits_image(model, features[0]), targets[0])
        loss.backward()  # type: ignore[no-untyped-call]
        opt.step()
        return state_digest(model)

    if next_step(head) != next_step(restored):
        raise ValueError("restored next optimizer update differs")
    return {
        "config": CONFIG,
        "source_manifest": source_manifest,
        "before": before,
        "after": after,
        "updates": events,
        "optimizer_steps": sum(e["updated"] for e in events),
        "restored_full_outputs_equal": True,
        "restored_next_update_equal": True,
        "checkpoint_sha256": sha(checkpoint),
        "independent_validation": False,
        "native_proposal_training_steps": 0,
        "runtime_authorized": False,
    }, checkpoint
