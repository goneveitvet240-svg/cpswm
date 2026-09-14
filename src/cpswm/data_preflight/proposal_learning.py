"""Full-target preparation and differentiable compatible-set proposal objective.

The three registered architecture arms share this target/loss boundary. This is
not an architecture implementation or a trainer. No support is generated from
labels on the method side. Targets may be teacher-forced during training only;
test-time generation must construct support from visible input and state.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from cpswm.data_preflight.proposal_samples import (
    ProposalSample,
    export_sample,
    proposal_factor_values,
)
from cpswm.system.reproducibility import content_sha256

if TYPE_CHECKING:
    from torch import Tensor

FACTOR_ORDER = ("operation", "parent", "H", "R", "I", "C", "Z", "r", "V")


@dataclass(frozen=True)
class ProposalLearningExample:
    model_input_json: str
    target_jsons: tuple[str, ...]
    target_sha256s: tuple[str, ...]
    target_factors: tuple[tuple[str, ...], ...]
    annotation_kind: str

    @classmethod
    def from_sample(cls, supplied: ProposalSample) -> ProposalLearningExample:
        sample = ProposalSample.model_validate(supplied.model_dump(mode="json"))
        projection = export_sample(sample)
        # Sample validation rejects repeated particle identities before scoring.
        unique = {}
        for target in sample.compatible_targets:
            payload = target.model_dump(mode="json")
            unique[content_sha256(payload)] = target
        keys = tuple(sorted(unique))
        factors = tuple(proposal_factor_values(unique[k]) for k in keys)
        # Two different replay effects cannot share all scored factors: that
        # would let a decoder attach unscored retraction/replay semantics.
        if len(set(factors)) != len(factors):
            raise ValueError("distinct proposal effects have identical scored factors")
        return cls(
            json.dumps(projection["model_input"], sort_keys=True, separators=(",", ":")),
            tuple(unique[k].model_dump_json() for k in keys),
            keys,
            factors,
            sample.annotation_kind,
        )

    def model_input(self) -> dict[str, object]:
        """Detached, complete history without supervision or annotation provenance."""
        return json.loads(self.model_input_json)  # type: ignore[no-any-return]


def compatible_proposal_nll(
    example: ProposalLearningExample,
    *,
    target_sha256s: tuple[str, ...],
    factor_order: tuple[str, ...],
    conditional_log_probabilities: Tensor,
) -> Tensor:
    """-log sum q(complete compatible proposal | visible prefix).

    The model supplies one row per distinct compatible target and nine columns
    in chain-rule order. Each entry must be the selected value's conditional
    log probability after conditioning on all preceding factors. This function
    preserves autograd; it neither detaches logits nor renormalizes only over
    the labeled candidates. It cannot certify that a caller implemented that
    generative distribution correctly. That needs the architecture's sampler
    and probability-trace comparison.
    """
    import torch

    if factor_order != FACTOR_ORDER or target_sha256s != example.target_sha256s:
        raise ValueError("loss must bind all axes and the exact supervised target order")
    terms = conditional_log_probabilities
    if not terms.is_floating_point() or terms.shape != (len(target_sha256s), len(FACTOR_ORDER)):
        raise ValueError("full proposal log probability matrix required")
    if not len(target_sha256s) or torch.isnan(terms).any() or (terms > 0).any():
        raise ValueError("invalid conditional log probabilities")
    # Exact zero probability (-inf) is permitted for an individual hypothesis.
    total_log_mass = torch.logsumexp(terms.sum(dim=1), dim=0)
    if not torch.isfinite(total_log_mass):
        raise ValueError("all compatible proposals have zero or nonfinite probability")
    if total_log_mass > 32 * torch.finfo(terms.dtype).eps:
        raise ValueError("compatible proposal probability exceeds one")
    return -total_log_mass
