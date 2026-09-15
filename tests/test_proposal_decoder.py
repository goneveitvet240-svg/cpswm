"""Exact probability and six-operation decoding on native-contract fixtures."""

import hashlib
from uuid import UUID

import pytest
import torch
from test_structure_two_proposal_scheduler import sample_payload

from cpswm.data_preflight.proposal_decoder import DecodedProposal, TypedProposalDistribution
from cpswm.data_preflight.proposal_learning import (
    FACTOR_ORDER,
    ProposalLearningExample,
    compatible_proposal_nll,
)
from cpswm.data_preflight.proposal_samples import ProposalContext, ProposalSample, bind_probability


class FixtureScorer(torch.nn.Module):
    """Trainable diagnostic logits, explicitly not any registered architecture arm."""

    def __init__(self):
        super().__init__()
        self.weight = torch.nn.Parameter(torch.linspace(-0.7, 0.7, 256, dtype=torch.float64))
        self.calls = []

    def forward(self, context, axis, prefix, choices, *, runtime_candidates):
        assert "training_targets" not in context and "audit_only" not in context
        assert all(x.candidate.events for x in runtime_candidates)
        self.calls.append((axis, prefix, choices))
        indices = [hashlib.sha256(repr((axis, prefix, x)).encode()).digest()[0] for x in choices]
        return self.weight[indices]


def setup():
    sample = ProposalSample.model_validate(sample_payload.__wrapped__())
    scorer = FixtureScorer()
    distribution = TypedProposalDistribution(
        context=sample.runtime_context(),
        runtime_candidates=sample.compatible_targets,
        scorer=scorer,
    )
    return sample, scorer, distribution


def test_all_six_operations_decode_exact_native_probability():
    sample, scorer, distribution = setup()
    total = 0.0
    operations = set()
    for key in distribution.target_sha256s:
        decoded = distribution.decode(key)
        bind_probability(sample, decoded.target, decoded.probability)
        native = decoded.native_proposal(
            evidence_cluster_id=UUID(int=50), model_version="fixture", code_version="test"
        )
        assert native.proposed_state == decoded.target.candidate.state
        assert native.operation == decoded.target.operation
        assert native.proposal_log_probability == pytest.approx(
            float(distribution.factor_log_probabilities(key).detach().sum()), abs=1e-12
        )
        if native.operation.value == "rejuvenate":
            assert decoded.target.replay_required and decoded.target.replaced_revision_ids
        total += torch.exp(distribution.factor_log_probabilities(key).sum()).item()
        operations.add(native.operation.value)
    assert total == pytest.approx(1.0, abs=1e-12)
    assert len(operations) == 6
    assert {x[0] for x in scorer.calls} == set(FACTOR_ORDER)


def test_training_gradient_and_sampling_use_same_complete_distribution():
    sample, scorer, distribution = setup()
    compatible = tuple(
        x
        for x in sample.compatible_targets
        if x.operation.value in {"branch", "preserve_unresolved"}
    )
    example = ProposalLearningExample.from_sample(
        sample.model_copy(update={"compatible_targets": compatible})
    )
    terms = distribution.training_terms(example)
    loss = compatible_proposal_nll(
        example,
        target_sha256s=example.target_sha256s,
        factor_order=FACTOR_ORDER,
        conditional_log_probabilities=terms,
    )
    expected_mass = sum(
        torch.exp(distribution.factor_log_probabilities(key).sum())
        for key in example.target_sha256s
    )
    assert loss.item() == pytest.approx(-torch.log(expected_mass).item(), abs=1e-12)
    loss.backward()
    assert scorer.weight.grad.abs().sum() > 0
    count = len(scorer.calls)
    rng = torch.Generator().manual_seed(11)
    state = rng.get_state().clone()
    a = [distribution.sample(generator=rng).target_json for _ in range(20)]
    rng.set_state(state)
    b = [distribution.sample(generator=rng).target_json for _ in range(20)]
    assert a == b
    assert len(scorer.calls) == count  # no stochastic rescoring after sample


def test_runtime_boundary_rejects_supervision_and_native_invalid_effects():
    sample, scorer, _ = setup()
    with pytest.raises(ValueError, match="without supervision"):
        TypedProposalDistribution(
            context=sample, runtime_candidates=sample.compatible_targets, scorer=scorer
        )
    raw = sample.runtime_context().model_dump()
    raw["compatible_targets"] = sample.compatible_targets
    with pytest.raises(ValueError):
        ProposalContext.model_validate(raw)
    bad = sample.compatible_targets[0].model_copy(update={"replay_required": True})
    with pytest.raises(ValueError):
        TypedProposalDistribution(
            context=sample.runtime_context(),
            runtime_candidates=(bad, *sample.compatible_targets[1:]),
            scorer=scorer,
        )


def test_truth_subset_does_not_define_runtime_support():
    sample, scorer, distribution = setup()
    compatible = tuple(
        x for x in sample.compatible_targets if x.operation.value == "preserve_unresolved"
    )
    e = ProposalLearningExample.from_sample(
        sample.model_copy(update={"compatible_targets": compatible})
    )
    assert distribution.training_terms(e).shape == (len(compatible), 9)
    assert len(distribution.target_sha256s) > len(compatible)
    changed = sample.runtime_context().model_copy(update={"source_snapshot_id": UUID(int=999)})
    with pytest.raises(ValueError, match="frozen snapshot catalog"):
        TypedProposalDistribution(
            context=changed, runtime_candidates=sample.compatible_targets, scorer=scorer
        )
    other = DecodedProposal(
        distribution.decode(distribution.target_sha256s[0]).target_json,
        distribution.decode(distribution.target_sha256s[-1]).trace_json,
    )
    with pytest.raises(ValueError, match="bind"):
        other.native_proposal(
            evidence_cluster_id=UUID(int=50), model_version="fixture", code_version="test"
        )


def test_scorer_nonfinite_or_wrong_support_is_rejected():
    sample, _, _ = setup()
    for scorer in [
        lambda c, a, p, v, **kw: torch.zeros(len(v) + 1),
        lambda c, a, p, v, **kw: torch.full((len(v),), float("nan")),
    ]:
        with pytest.raises(ValueError, match="entire conditional support"):
            TypedProposalDistribution(
                context=sample.runtime_context(),
                runtime_candidates=sample.compatible_targets,
                scorer=scorer,
            )
