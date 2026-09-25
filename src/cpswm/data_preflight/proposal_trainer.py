"""Budgeted proposal pretraining shared by all three development arms.

This is proposal NLL pretraining, not any of the unresolved joint training
schedules. The runtime support provider only receives label-free context. Natural
training additionally requires a separately reviewed complete dataset; the current
author-pose package is intentionally rejected as incomplete proposal supervision.
"""

from __future__ import annotations

import hashlib
import io
import json
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from time import monotonic
from typing import Any

import torch

from cpswm.data_preflight.proposal_decoder import TypedProposalDistribution
from cpswm.data_preflight.proposal_learning import (
    FACTOR_ORDER,
    ProposalLearningExample,
    compatible_proposal_nll,
)
from cpswm.data_preflight.proposal_samples import ProposalContext, ProposalSample, ProposalTarget
from cpswm.data_preflight.typed_proposal_networks import ARMS, NetworkConfig, TypedProposalNetwork
from cpswm.system.reproducibility import content_sha256

SupportProvider = Callable[[ProposalContext], tuple[ProposalTarget, ...]]


def distribution(
    model: TypedProposalNetwork, context: ProposalContext, support: tuple[ProposalTarget, ...]
) -> TypedProposalDistribution:
    return TypedProposalDistribution(
        context=context, runtime_candidates=support, scorer=model.prepare(context, support)
    )


def train_proposer(
    *,
    arm: str,
    samples: tuple[ProposalSample, ...],
    support_provider: SupportProvider,
    seed: int,
    optimizer_steps: int,
    max_seconds: float,
    learning_rate: float,
    fixture_diagnostic: bool = False,
    reviewed_dataset: dict[str, Any] | None = None,
) -> tuple[TypedProposalNetwork, dict[str, Any]]:
    if arm not in ARMS or seed not in (0, 1, 2):
        raise ValueError("registered development arm and seed required")
    if not 0 < optimizer_steps <= 1500 or not 0 < max_seconds <= 300 or not 0 < learning_rate < 1:
        raise ValueError("outside frozen local per-run budget")
    samples = tuple(ProposalSample.model_validate(s.model_dump()) for s in samples)
    if not samples:
        raise ValueError("nonempty reviewed compatible targets required")
    if fixture_diagnostic:
        if any(
            s.annotation_kind != "component_fixture" or s.partition != "development"
            for s in samples
        ):
            raise ValueError("fixture mode cannot relabel natural data or spend training data")
    elif (
        any(s.annotation_kind == "component_fixture" or s.partition != "train" for s in samples)
        or reviewed_dataset is None
        or reviewed_dataset.get("full_proposal_training_ready") is not True
        or reviewed_dataset.get("independently_reviewed") is not True
        or not reviewed_dataset.get("review_source_sha256")
        or reviewed_dataset.get("sample_sha256s")
        != [content_sha256(s.model_dump(mode="json")) for s in samples]
    ):
        raise ValueError(
            "natural training requires complete, separately reviewed bound proposal data"
        )
    # Preparation itself cannot read the supervision envelope.
    units = []
    for sample in samples:
        context = sample.runtime_context()
        support = support_provider(ProposalContext.model_validate(context.model_dump()))
        context.validate_candidates(support)
        units.append((context, support, ProposalLearningExample.from_sample(sample)))
    old_threads = torch.get_num_threads()
    torch.set_num_threads(2)
    try:
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(seed)
            model = TypedProposalNetwork(arm).cpu()
            optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)
            start, losses, steps, examples_seen = monotonic(), [], 0, 0
            # One optimizer/evaluation step is indivisible. Wall limit is checked
            # between steps, and any overrun is measured rather than hidden.
            while steps < optimizer_steps and monotonic() - start < max_seconds:
                optimizer.zero_grad()
                selected = [units[(steps * 8 + i) % len(units)] for i in range(min(8, len(units)))]
                terms = []
                for context, support, example in selected:
                    d = distribution(model, context, support)
                    terms.append(
                        compatible_proposal_nll(
                            example,
                            target_sha256s=example.target_sha256s,
                            factor_order=FACTOR_ORDER,
                            conditional_log_probabilities=d.training_terms(example),
                        )
                    )
                loss = torch.stack(terms).mean()
                loss.backward()  # type: ignore[no-untyped-call]
                grads = [p.grad for p in model.parameters() if p.grad is not None]
                if (
                    not torch.isfinite(loss)
                    or not grads
                    or any(not torch.isfinite(g).all() for g in grads)
                ):
                    raise ValueError("nonfinite or missing training gradient")
                optimizer.step()
                losses.append(float(loss.detach()))
                steps += 1
                examples_seen += len(selected)
            elapsed = monotonic() - start
            if not steps:
                raise ValueError("resource limit reached before first optimizer step")
            model.eval()
            report = {
                "arm": arm,
                "seed": seed,
                "optimizer_steps": steps,
                "examples_seen": examples_seen,
                "requested_steps": optimizer_steps,
                "seconds": elapsed,
                "wall_limit_seconds": max_seconds,
                "wall_overrun_seconds": max(0.0, elapsed - max_seconds),
                "stop_reason": "step_limit" if steps == optimizer_steps else "wall_limit",
                "losses": losses,
                "learning_rate": learning_rate,
                "optimizer": "AdamW(default betas/weight_decay)",
                "objective": "compatible_proposal_nll_only",
                "track": "COMPONENT_FIXTURE_ONLY"
                if fixture_diagnostic
                else "REVIEWED_PROPOSAL_PRETRAINING",
                "formal_architecture_selected": False,
                "joint_training_schedule_implemented": False,
                "natural_closed_loop_verified": False,
                "parameter_count": sum(p.numel() for p in model.parameters()),
                "sample_sha256s": [content_sha256(s.model_dump(mode="json")) for s in samples],
                "support_sha256s": [
                    content_sha256([t.model_dump(mode="json") for t in u[1]]) for u in units
                ],
            }
            return model, report
    finally:
        torch.set_num_threads(old_threads)


def save_checkpoint(model: TypedProposalNetwork, report: dict[str, Any], directory: Path) -> str:
    directory.mkdir(parents=True, exist_ok=False)
    blob = io.BytesIO()
    torch.save(model.state_dict(), blob)
    if any(
        v.dtype != torch.float32 or not torch.isfinite(v).all() for v in model.state_dict().values()
    ):
        raise ValueError("checkpoint requires finite float32 parameters")
    payload = blob.getvalue()
    digest = hashlib.sha256(payload).hexdigest()
    (directory / "weights.pt").write_bytes(payload)
    manifest = {
        "format": "typed-proposal-development@1",
        "arm": model.arm,
        "config": asdict(model.config),
        "weights_sha256": digest,
        "training": report,
        "production_authorized": False,
        "torch_version": torch.__version__,
    }
    data = json.dumps(manifest, sort_keys=True, indent=2, allow_nan=False).encode()
    (directory / "manifest.json").write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def load_checkpoint(
    directory: Path, *, manifest_sha256: str
) -> tuple[TypedProposalNetwork, dict[str, Any]]:
    data = (directory / "manifest.json").read_bytes()
    if hashlib.sha256(data).hexdigest() != manifest_sha256:
        raise ValueError("checkpoint manifest identity mismatch")
    manifest = json.loads(data)
    if (
        manifest["format"] != "typed-proposal-development@1"
        or manifest["production_authorized"] is not False
    ):
        raise ValueError("development checkpoint cannot authorize production")
    payload = (directory / "weights.pt").read_bytes()
    if hashlib.sha256(payload).hexdigest() != manifest["weights_sha256"]:
        raise ValueError("checkpoint weights identity mismatch")
    with torch.random.fork_rng(devices=[]):
        model = TypedProposalNetwork(manifest["arm"], NetworkConfig(**manifest["config"]))
    weights = torch.load(io.BytesIO(payload), map_location="cpu", weights_only=True)
    expected = model.state_dict()
    if not isinstance(weights, dict) or set(weights) != set(expected):
        raise ValueError("checkpoint parameter tensor schema mismatch")
    for name, reference in expected.items():
        value = weights[name]
        if (
            not isinstance(value, torch.Tensor)
            or value.layout != torch.strided
            or value.shape != reference.shape
            or value.dtype != reference.dtype
            or not torch.isfinite(value).all()
        ):
            raise ValueError("checkpoint tensor shape/dtype or finite parameter mismatch")
    model.load_state_dict(weights, strict=True)
    model.eval()
    return model, manifest
