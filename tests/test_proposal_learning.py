"""Full-axis gradient checks on explicit fixtures, not trained-model results."""

import json
import math

import pytest
import test_structure_two_proposal_scheduler as fixtures
import torch

from cpswm.data_preflight.proposal_learning import (
    FACTOR_ORDER,
    ProposalLearningExample,
    compatible_proposal_nll,
)
from cpswm.data_preflight.proposal_samples import ProposalSample, export_sample


@pytest.fixture
def sample_payload():
    return fixtures.sample_payload.__wrapped__()


def example(payload):
    return ProposalLearningExample.from_sample(ProposalSample.model_validate(payload))


def loss(e, terms, **kwargs):
    return compatible_proposal_nll(
        e,
        target_sha256s=kwargs.get("ids", e.target_sha256s),
        factor_order=kwargs.get("order", FACTOR_ORDER),
        conditional_log_probabilities=terms,
    )


def test_full_history_is_detached_from_supervision(sample_payload):
    sample = ProposalSample.model_validate(sample_payload)
    e = ProposalLearningExample.from_sample(sample)
    assert e.model_input() == json.loads(json.dumps(export_sample(sample)["model_input"]))
    assert "training_targets" not in e.model_input()
    assert "audit_only" not in e.model_input()
    assert {row[0] for row in e.target_factors} == {
        "branch",
        "revise",
        "retract",
        "reactivate",
        "rejuvenate",
        "preserve_unresolved",
    }
    assert all(len(row) == 9 for row in e.target_factors)
    read = e.model_input()
    read.clear()
    assert e.model_input()


def test_compatible_mass_objective_preserves_all_axes_and_gradients(sample_payload):
    e = example(sample_payload)
    n = len(e.target_sha256s)
    terms = torch.full((n, 9), -math.log(4.0), dtype=torch.float64, requires_grad=True)
    result = loss(e, terms)
    assert result.item() == pytest.approx(9 * math.log(4.0) - math.log(n))
    result.backward()
    assert torch.allclose(terms.grad, torch.full_like(terms, -1 / n))


def test_duplicate_annotations_do_not_increase_probability_mass(sample_payload):
    base = ProposalSample.model_validate(sample_payload)
    duplicated = base.model_copy(update={"compatible_targets": base.compatible_targets * 2})
    with pytest.raises(ValueError, match="unique new particle"):
        ProposalLearningExample.from_sample(duplicated)


def test_target_order_omitted_axes_and_impossible_mass_are_not_silently_fixed(sample_payload):
    e = example(sample_payload)
    terms = torch.full((len(e.target_sha256s), 9), -10.0)
    with pytest.raises(ValueError, match="exact"):
        loss(e, terms, ids=e.target_sha256s[::-1])
    with pytest.raises(ValueError, match="all axes"):
        loss(e, terms[:, :8], order=FACTOR_ORDER[:8])
    with pytest.raises(ValueError, match="exceeds one"):
        loss(e, torch.zeros_like(terms))
    with pytest.raises(ValueError, match="zero or nonfinite"):
        loss(e, torch.full_like(terms, -float("inf")))


def test_zero_probability_alternative_does_not_remove_other_hypotheses(sample_payload):
    e = example(sample_payload)
    terms = torch.full((len(e.target_sha256s), 9), -float("inf"), dtype=torch.float64)
    terms[0] = -1.0
    terms.requires_grad_()
    result = loss(e, terms)
    assert result.item() == pytest.approx(9.0)
    result.backward()
    assert torch.equal(terms.grad[0], -torch.ones(9, dtype=torch.float64))
    assert torch.equal(terms.grad[1:], torch.zeros_like(terms.grad[1:]))
