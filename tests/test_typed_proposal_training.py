"""Architecture/probability/optimizer checks on explicit component fixtures."""

from dataclasses import replace

import pytest
import torch
from test_structure_two_proposal_scheduler import sample_payload

from cpswm.data_preflight.proposal_samples import ProposalSample, export_context
from cpswm.data_preflight.proposal_trainer import (
    distribution,
    load_checkpoint,
    save_checkpoint,
    train_proposer,
)
from cpswm.data_preflight.typed_proposal_networks import ARMS, NetworkConfig, TypedProposalNetwork


def data():
    sample = ProposalSample.model_validate(sample_payload.__wrapped__())
    support = sample.compatible_targets
    sample = ProposalSample.model_validate(
        sample.model_copy(
            update={
                "compatible_targets": tuple(
                    t for t in support if t.operation.value in {"branch", "preserve_unresolved"}
                )
            }
        ).model_dump()
    )
    return sample, support


@pytest.mark.parametrize("arm", ARMS)
def test_real_architecture_optimizer_full_probability_and_exact_checkpoint(arm, tmp_path):
    sample, support = data()
    seen = []

    def provider(context):
        assert not hasattr(context, "compatible_targets")
        seen.append(context)
        return support

    model, report = train_proposer(
        arm=arm,
        samples=(sample,),
        support_provider=provider,
        seed=0,
        optimizer_steps=2,
        max_seconds=60,
        learning_rate=0.001,
        fixture_diagnostic=True,
    )
    assert report["optimizer_steps"] == 2 and report["losses"][0] != report["losses"][1]
    assert len(seen) == 1 and report["track"] == "COMPONENT_FIXTURE_ONLY"
    digest = save_checkpoint(model, report, tmp_path / "weights")
    loaded, manifest = load_checkpoint(tmp_path / "weights", manifest_sha256=digest)
    assert not manifest["production_authorized"]
    old_threads = torch.get_num_threads()
    torch.set_num_threads(2)
    try:
        with torch.no_grad():
            before = distribution(model, sample.runtime_context(), support)
            after = distribution(loaded, sample.runtime_context(), support)
            reordered = distribution(model, sample.runtime_context(), tuple(reversed(support)))
            mass = 0.0
            operations = set()
            for key in before.target_sha256s:
                a, b = before.decode(key), after.decode(key)
                assert a == b
                assert a == reordered.decode(key)
                operations.add(a.target.operation.value)
                mass += torch.exp(before.factor_log_probabilities(key).sum()).item()
            assert mass == pytest.approx(1.0, abs=1e-12) and len(operations) == 6
    finally:
        torch.set_num_threads(old_threads)


def test_label_envelope_budget_and_unreviewed_natural_training_are_rejected():
    sample, support = data()
    model = TypedProposalNetwork(ARMS[0], replace(NetworkConfig(), max_nodes=2))
    with pytest.raises(ValueError, match="supervision"):
        model.prepare(sample, support)
    with pytest.raises(ValueError, match="resource limit"):
        model.prepare(sample.runtime_context(), support)
    with pytest.raises(ValueError, match="separately reviewed"):
        train_proposer(
            arm=ARMS[0],
            samples=(sample,),
            support_provider=lambda _: support,
            seed=0,
            optimizer_steps=2,
            max_seconds=60,
            learning_rate=0.001,
            reviewed_dataset={"full_proposal_training_ready": False},
        )


def test_prepared_encoding_cannot_be_reused_after_model_or_support_changes():
    sample, support = data()
    old_threads = torch.get_num_threads()
    torch.set_num_threads(2)
    try:
        model = TypedProposalNetwork(ARMS[1])
        scorer = model.prepare(sample.runtime_context(), support)
        with torch.no_grad():
            next(model.parameters()).add_(1)
        with pytest.raises(ValueError, match="optimizer state"):
            scorer(
                export_context(sample.runtime_context()),
                "operation",
                (),
                tuple(sorted({t.operation.value for t in support})),
                runtime_candidates=support,
            )
    finally:
        torch.set_num_threads(old_threads)
