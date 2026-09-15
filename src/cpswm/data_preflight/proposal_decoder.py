"""Shared differentiable scoring and exact typed sampling over runtime support.

The support generator supplies complete native proposals from visible context;
labels are only supplied to training_terms, never to the scorer or sampler.
This decoder does not implement that support generator, authenticate supervision,
choose a neural architecture, or authorize any ledger effect.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID, uuid4

import torch
from torch import Tensor

from cpswm.data_preflight.proposal_learning import FACTOR_ORDER, ProposalLearningExample
from cpswm.data_preflight.proposal_samples import (
    ConditionalFactor,
    JointProposalProbability,
    ProposalContext,
    ProposalTarget,
    export_context,
    proposal_factor_values,
)
from cpswm.system.evaluation_operations.structure_two_selected_method import NeuralParticleProposal
from cpswm.system.reproducibility import content_sha256


class ConditionalScorer(Protocol):
    def __call__(
        self,
        context: dict[str, object],
        axis: str,
        prefix: tuple[str, ...],
        choices: tuple[str, ...],
        *,
        runtime_candidates: tuple[ProposalTarget, ...],
    ) -> Tensor: ...


@dataclass(frozen=True)
class DecodedProposal:
    target_json: str
    trace_json: str

    @property
    def target(self) -> ProposalTarget:
        return ProposalTarget.model_validate_json(self.target_json)

    @property
    def probability(self) -> JointProposalProbability:
        return JointProposalProbability.model_validate_json(self.trace_json)

    def native_proposal(
        self, *, evidence_cluster_id: UUID, model_version: str, code_version: str
    ) -> NeuralParticleProposal:
        target, trace = self.target, self.probability
        if trace.proposal_sha256 != content_sha256(target.model_dump(mode="json")):
            raise ValueError("decoded probability does not bind the complete native target")
        if tuple(x.selected for x in trace.factors) != proposal_factor_values(target):
            raise ValueError("decoded factors do not match native target")
        return NeuralParticleProposal(
            proposal_id=uuid4(),
            evidence_cluster_id=evidence_cluster_id,
            operation=target.operation,
            source_particle_id=target.candidate.state.parent_particle_id,
            source_snapshot_id=target.candidate.state.source_snapshot_id,
            proposed_state=target.candidate.state,
            proposal_log_probability=trace.joint_log_probability,
            proposer_model_version=model_version,
            proposer_code_version=code_version,
        )


class TypedProposalDistribution:
    """One evaluated conditional tree, reused for teacher forcing and sampling.

    Every conditional is evaluated once, so stochastic layers cannot give a
    sampled proposal a different subsequently reported score. A new optimizer
    step or new input requires constructing a new distribution. No truncation,
    top-k renormalization or probability floor is applied.
    """

    def __init__(
        self,
        *,
        context: ProposalContext,
        runtime_candidates: tuple[ProposalTarget, ...],
        scorer: ConditionalScorer,
    ) -> None:
        # Reject a full training envelope at the runtime boundary.
        if type(context) is not ProposalContext:
            raise ValueError("runtime decoder requires context without supervision")
        clean = ProposalContext.model_validate(context.model_dump())
        candidates = tuple(
            ProposalTarget.model_validate(x.model_dump()) for x in runtime_candidates
        )
        clean.validate_candidates(candidates)
        self._input_json = json.dumps(export_context(clean), sort_keys=True, separators=(",", ":"))
        self.context_sha256 = content_sha256(json.loads(self._input_json))
        self._targets = {
            content_sha256(x.model_dump(mode="json")): x.model_dump_json() for x in candidates
        }
        factors = {
            key: proposal_factor_values(ProposalTarget.model_validate_json(value))
            for key, value in self._targets.items()
        }
        if len(set(factors.values())) != len(candidates):
            raise ValueError("runtime proposals have colliding or duplicate scored effects")
        self._factors = factors
        self._leaves = {values: key for key, values in factors.items()}
        self._nodes: dict[tuple[str, ...], tuple[tuple[str, ...], Tensor]] = {}
        for depth, axis in enumerate(FACTOR_ORDER):
            for prefix in sorted({values[:depth] for values in factors.values()}):
                choices = tuple(
                    sorted(
                        {values[depth] for values in factors.values() if values[:depth] == prefix}
                    )
                )
                # Semantic graph values accompany their canonical factor keys: a
                # learned scorer must not be limited to opaque event/role hashes.
                logits = scorer(
                    json.loads(self._input_json),
                    axis,
                    prefix,
                    choices,
                    runtime_candidates=tuple(
                        ProposalTarget.model_validate_json(self._targets[key])
                        for key in sorted(self._targets)
                    ),
                )
                if (
                    not logits.is_floating_point()
                    or logits.shape != (len(choices),)
                    or not torch.isfinite(logits).all()
                ):
                    raise ValueError(
                        "scorer must return finite logits for the entire conditional support"
                    )
                # Double precision also matches the existing probability receipt tolerance.
                logs = torch.log_softmax(logits.to(dtype=torch.float64), dim=0)
                if not torch.isfinite(logs).all():
                    raise ValueError("conditional log probability overflow")
                if (logs.detach().exp() == 0).any():
                    raise ValueError(
                        "conditional probability underflow would drop supported choices"
                    )
                self._nodes[prefix] = (choices, logs)

    @property
    def target_sha256s(self) -> tuple[str, ...]:
        return tuple(sorted(self._targets))

    def factor_log_probabilities(self, target_sha256: str) -> Tensor:
        values = self._factors[target_sha256]
        return torch.stack(
            tuple(
                self._nodes[values[:i]][1][self._nodes[values[:i]][0].index(value)]
                for i, value in enumerate(values)
            )
        )

    def training_terms(self, example: ProposalLearningExample) -> Tensor:
        if content_sha256(example.model_input()) != self.context_sha256:
            raise ValueError("training labels refer to a different runtime input")
        for key, expected_factors in zip(
            example.target_sha256s, example.target_factors, strict=True
        ):
            if key not in self._targets or self._factors[key] != expected_factors:
                raise ValueError("compatible supervision is outside generated runtime support")
        return torch.stack(
            tuple(self.factor_log_probabilities(key) for key in example.target_sha256s)
        )

    def decode(self, target_sha256: str) -> DecodedProposal:
        values = self._factors[target_sha256]
        factors = []
        prefix: list[tuple[str, str]] = []
        for i, (axis, selected) in enumerate(zip(FACTOR_ORDER, values, strict=True)):
            choices, logs = self._nodes[values[:i]]
            probabilities = tuple(float(x) for x in logs.detach().cpu().exp())
            if probabilities[choices.index(selected)] == 0:
                raise ValueError(
                    "selected probability underflow cannot be represented by native receipt"
                )
            factors.append(
                ConditionalFactor(
                    axis=axis,
                    context_sha256=content_sha256({"root": self.context_sha256, "prefix": prefix}),
                    choices=choices,
                    probabilities=probabilities,
                    selected=selected,
                )
            )
            prefix.append((axis, selected))
        trace = JointProposalProbability(
            root_context_sha256=self.context_sha256,
            proposal_sha256=target_sha256,
            factors=tuple(factors),
            joint_log_probability=float(
                self.factor_log_probabilities(target_sha256).detach().sum()
            ),
        )
        return DecodedProposal(self._targets[target_sha256], trace.model_dump_json())

    def sample(self, *, generator: torch.Generator) -> DecodedProposal:
        # CPU sampling uses the exact retained logits and explicit caller-owned RNG.
        prefix: tuple[str, ...] = ()
        for _ in FACTOR_ORDER:
            choices, logs = self._nodes[prefix]
            index = int(torch.multinomial(logs.detach().cpu().exp(), 1, generator=generator).item())
            prefix += (choices[index],)
        return self.decode(self._leaves[prefix])
