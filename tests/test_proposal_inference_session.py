"""Inference lifecycle and complete resealed forgeries on component fixtures."""

import hashlib
import json
import math
from datetime import timedelta

import pytest
import torch
from test_typed_proposal_training import data

from cpswm.data_preflight.proposal_decoder import TypedProposalDistribution
from cpswm.data_preflight.proposal_inference_session import ProposalInferenceSession, encoded
from cpswm.data_preflight.proposal_trainer import save_checkpoint
from cpswm.data_preflight.typed_proposal_networks import ARMS, TypedProposalNetwork


@pytest.fixture(autouse=True)
def threads():
    old = torch.get_num_threads()
    torch.set_num_threads(2)
    yield
    torch.set_num_threads(old)


def setup(tmp_path, arm=ARMS[0]):
    with torch.random.fork_rng():
        torch.manual_seed(0)
        model = TypedProposalNetwork(arm).eval()
    checkpoint = tmp_path / arm
    pin = save_checkpoint(model, {"track": "COMPONENT_FIXTURE_ONLY"}, checkpoint)
    session = ProposalInferenceSession(checkpoint, manifest_sha256=pin, seed=11)
    sample, support = data()
    return checkpoint, pin, session, sample, support


def resume(checkpoint, pin, blob):
    return ProposalInferenceSession.restore(
        checkpoint,
        manifest_sha256=pin,
        snapshot=blob,
        snapshot_sha256=hashlib.sha256(blob).hexdigest(),
    )


@pytest.mark.parametrize("arm", ARMS)
def test_full_six_operations_idempotency_and_restored_next_draw(arm, tmp_path):
    checkpoint, pin, session, sample, support = setup(tmp_path, arm)
    context = sample.runtime_context()
    start = session.snapshot()
    all_targets = session.score_support(context=context, support=support)
    assert len({p.target.operation for p in all_targets}) == 6
    assert math.fsum(math.exp(p.probability.joint_log_probability) for p in all_targets) == (
        pytest.approx(1.0, abs=1e-12)
    )
    assert session.snapshot() == start
    rejuvenation = next(p.target for p in all_targets if p.target.operation.value == "rejuvenate")
    assert rejuvenation.replay_required and rejuvenation.replaced_revision_ids
    first = session.infer(request_id="observation-1", context=context, support=support)
    assert not first.ledger_authorized and not first.native_publication_authorized
    blob = session.snapshot()
    assert first == session.infer(
        request_id="observation-1", context=context, support=tuple(reversed(support))
    )
    assert session.snapshot() == blob
    restored = resume(checkpoint, pin, blob)
    for i in range(2, 6):
        kwargs = {"request_id": f"observation-{i}", "context": context, "support": support}
        assert session.infer(**kwargs) == restored.infer(**kwargs)
    assert session.snapshot() == restored.snapshot()


@pytest.mark.parametrize("fault", ["context", "support", "supervision", "model"])
def test_changed_request_inputs_or_model_rejected_without_rng_consumption(tmp_path, fault):
    _, _, session, sample, support = setup(tmp_path)
    context = sample.runtime_context()
    session.infer(request_id="one", context=context, support=support)
    rng = session._generator.get_state().clone()
    records = dict(session._records)
    if fault == "context":
        context = context.model_copy(
            update={
                "visible": context.visible.model_copy(
                    update={"cutoff": context.visible.cutoff + timedelta(seconds=1)}
                )
            }
        )
    elif fault == "support":
        support = support[:-1]
    elif fault == "supervision":
        context = sample
    else:
        session._model.byte_embedding.weight.data.add_(1)
    with pytest.raises(ValueError, match=r"changed|supervision"):
        session.infer(request_id="one", context=context, support=support)
    assert torch.equal(rng, session._generator.get_state())
    assert records == session._records


def test_interrupt_after_random_draw_is_rolled_back_and_retry_matches(tmp_path, monkeypatch):
    checkpoint, pin, session, sample, support = setup(tmp_path)
    control = resume(checkpoint, pin, session.snapshot())
    real_sample = TypedProposalDistribution.sample

    def interrupt(self, *, generator):
        real_sample(self, generator=generator)
        raise KeyboardInterrupt("interrupted after consuming a random sample")

    before = session.snapshot()
    monkeypatch.setattr(TypedProposalDistribution, "sample", interrupt)
    kwargs = {"request_id": "retry", "context": sample.runtime_context(), "support": support}
    with pytest.raises(KeyboardInterrupt):
        session.infer(**kwargs)
    assert session.snapshot() == before
    monkeypatch.setattr(TypedProposalDistribution, "sample", real_sample)
    assert session.infer(**kwargs) == control.infer(**kwargs)


@pytest.mark.parametrize("fault", ["target", "probability", "rng", "authority", "duplicate"])
def test_fully_resealed_inconsistent_snapshot_cannot_restore(tmp_path, fault):
    checkpoint, pin, session, sample, support = setup(tmp_path)
    session.infer(request_id="one", context=sample.runtime_context(), support=support)
    payload = json.loads(session.snapshot())
    receipt = payload["records"][0]["receipt"]
    if fault == "target":
        other = next(
            p
            for p in session.score_support(context=sample.runtime_context(), support=support)
            if p.target_json != receipt["decoded"]["target_json"]
        )
        # Swap a complete legitimate alternative with its matching probability.
        receipt["decoded"] = {"target_json": other.target_json, "trace_json": other.trace_json}
    elif fault == "probability":
        trace = json.loads(receipt["decoded"]["trace_json"])
        trace["joint_log_probability"] -= 1
        receipt["decoded"]["trace_json"] = json.dumps(trace)
    elif fault == "rng":
        payload["rng_sha256"] = "f" * 64
    elif fault == "authority":
        payload["native_publication_authorized"] = True
        receipt["native_publication_authorized"] = True
    else:
        payload["records"].append(payload["records"][0])
    with pytest.raises(ValueError, match="recomputed replay"):
        resume(checkpoint, pin, encoded(payload))


def test_restore_binds_external_digest_checkpoint_and_installed_source(tmp_path, monkeypatch):
    import cpswm.data_preflight.proposal_inference_session as module

    checkpoint, pin, session, _, _ = setup(tmp_path)
    blob = session.snapshot()
    with pytest.raises(ValueError, match="snapshot identity"):
        ProposalInferenceSession.restore(
            checkpoint, manifest_sha256=pin, snapshot=blob, snapshot_sha256="f" * 64
        )
    other_path, other_pin, _, _, _ = setup(tmp_path, ARMS[1])
    with pytest.raises(ValueError, match="dependency binding"):
        resume(other_path, other_pin, blob)
    monkeypatch.setattr(module, "source_digest", lambda: "0" * 64)
    with pytest.raises(ValueError, match="dependency binding"):
        resume(checkpoint, pin, blob)
