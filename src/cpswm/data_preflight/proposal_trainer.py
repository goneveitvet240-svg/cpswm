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
from dataclasses import asdict, replace
from pathlib import Path
from time import monotonic
from typing import Any

import torch

from cpswm.data_preflight.proposal_decoder import TypedProposalDistribution
from cpswm.data_preflight.proposal_graph_compute import BLOCKED_BACKEND
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
    if model.config.execution_backend != "dense@1":
        raise ValueError("use explicit execution derivation for an existing dense checkpoint")
    from cpswm.data_preflight.typed_proposal_networks import parameter_fingerprint

    parameter_fingerprint(model)
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
    validate_execution_derivation(manifest)
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


def execution_source_files() -> dict[str, str]:
    """Bind the concrete graph/backend and checkpoint interpreter implementation."""
    return {
        name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
        for name in (
            "proposal_graph_compute.py",
            "typed_proposal_networks.py",
            "proposal_trainer.py",
        )
    }


def validate_execution_derivation(manifest: dict[str, Any]) -> None:
    config = NetworkConfig(**manifest["config"])
    config.validate()
    derivative = manifest.get("execution_derivation")
    if config.execution_backend == "dense@1":
        if derivative is not None:
            raise ValueError("dense checkpoint cannot claim a blocked execution derivation")
        return
    fields = {
        "format",
        "parent_manifest_sha256",
        "parent_manifest_utf8",
        "parameters_changed",
        "added_optimizer_steps",
        "execution_source_files",
        "execution_torch_version",
    }
    if (
        not isinstance(derivative, dict)
        or set(derivative) != fields
        or derivative["format"] != "full-support-execution-derivation@1"
        or derivative["parameters_changed"] is not False
        or type(derivative["added_optimizer_steps"]) is not int
        or derivative["added_optimizer_steps"] != 0
        or derivative["execution_source_files"] != execution_source_files()
        or derivative["execution_torch_version"] != torch.__version__
        or not isinstance(derivative["parent_manifest_utf8"], str)
    ):
        raise ValueError("execution derivation identity or provenance mismatch")
    parent_bytes = derivative["parent_manifest_utf8"].encode()
    if hashlib.sha256(parent_bytes).hexdigest() != derivative["parent_manifest_sha256"]:
        raise ValueError("execution derivation parent manifest identity mismatch")
    parent = json.loads(parent_bytes)
    parent_config = NetworkConfig(**parent["config"])
    parent_config.validate()
    if (
        parent_config.execution_backend != "dense@1"
        or parent.get("execution_derivation") is not None
        or parent["format"] != "typed-proposal-development@1"
        or parent["production_authorized"] is not False
        or parent["arm"] != manifest["arm"]
        or parent["weights_sha256"] != manifest["weights_sha256"]
        or parent["training"] != manifest["training"]
        or parent["torch_version"] != manifest["torch_version"]
        or replace(parent_config, max_nodes=config.max_nodes, execution_backend=BLOCKED_BACKEND)
        != config
    ):
        raise ValueError(
            "execution derivation changed parameters, training lineage or architecture"
        )


def derive_execution_checkpoint(
    source: Path,
    *,
    manifest_sha256: str,
    directory: Path,
    max_nodes: int,
) -> str:
    """Create an explicitly derived eval artifact; copy original weight bytes.

    The original manifest is retained verbatim. This export neither trains nor
    selects a model, authorizes production, nor authenticates caller-held roots.
    """
    sources_before = execution_source_files()
    parent_bytes = (source / "manifest.json").read_bytes()
    model, parent = load_checkpoint(source, manifest_sha256=manifest_sha256)
    if hashlib.sha256(parent_bytes).hexdigest() != manifest_sha256:
        raise ValueError("parent manifest changed during execution derivation")
    if model.config.execution_backend != "dense@1":
        raise ValueError("derive execution directly from the original dense checkpoint")
    config = replace(model.config, execution_backend=BLOCKED_BACKEND, max_nodes=max_nodes)
    config.validate()
    payload = (source / "weights.pt").read_bytes()
    if hashlib.sha256(payload).hexdigest() != parent["weights_sha256"]:
        raise ValueError("parent weights changed during execution derivation")
    manifest = {
        **parent,
        "config": asdict(config),
        "execution_derivation": {
            "format": "full-support-execution-derivation@1",
            "parent_manifest_sha256": manifest_sha256,
            "parent_manifest_utf8": parent_bytes.decode(),
            "parameters_changed": False,
            "added_optimizer_steps": 0,
            "execution_source_files": sources_before,
            "execution_torch_version": torch.__version__,
        },
    }
    validate_execution_derivation(manifest)
    data = json.dumps(manifest, sort_keys=True, indent=2, allow_nan=False).encode()
    if (
        execution_source_files() != sources_before
        or (source / "manifest.json").read_bytes() != parent_bytes
        or (source / "weights.pt").read_bytes() != payload
    ):
        raise ValueError("dependencies changed during execution derivation")
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "weights.pt").write_bytes(payload)
    (directory / "manifest.json").write_bytes(data)
    return hashlib.sha256(data).hexdigest()
