"""Actual three-network sampling plus conditional model evaluation and recovery."""

import hashlib
import json
from dataclasses import replace

import pytest
import torch
from test_conditioned_proposal_runtime import FixtureModel, inputs, prior
from test_runtime_candidates import ARMS, LEDGER, checkpoint

from cpswm.data_preflight.proposal_inference_session import encoded
from cpswm.system.conditioned_inference_session import ConditionedInferenceSession
from cpswm.system.continuous_state_codec import StateCodec


def setup(tmp_path, arm):
    path, pin = checkpoint(tmp_path, arm)
    model = FixtureModel()
    session = ConditionedInferenceSession(
        path,
        manifest_sha256=pin,
        seed=11,
        prior=prior(),
        model=model,
        expected_model_binding_sha256=model.binding_sha256,
    )
    generated, kwargs = inputs()
    args = dict(
        request_id="one",
        context=generated.context,
        bootstrap_ledger_lineage_ref=LEDGER,
        groups=kwargs["groups"],
        parent_statistics={},
    )
    return session, path, pin, model, args


def restore(path, pin, blob, *, model=None, digest=None):
    model = model or FixtureModel()
    return ConditionedInferenceSession.restore(
        path,
        manifest_sha256=pin,
        snapshot=blob,
        snapshot_sha256=digest or hashlib.sha256(blob).hexdigest(),
        prior=prior(),
        model=model,
        expected_model_binding_sha256=model.binding_sha256,
    )


@pytest.fixture(autouse=True)
def threads():
    previous = torch.get_num_threads()
    torch.set_num_threads(2)
    yield
    torch.set_num_threads(previous)


@pytest.mark.parametrize("arm", ARMS)
def test_learned_sample_retains_original_q_identity_and_bound_actual_statistics(arm, tmp_path):
    session, path, pin, model, args = setup(tmp_path, arm)
    result = session.process(**args)
    assert result.selected.origin == result.proposed.receipt.decoded.target
    assert (
        result.selected.statistics.reference
        == result.selected.resolved_hypothesis.state.statistic_state_ref
    )
    assert result.selected.origin.candidate.state.statistic_state_ref.startswith(
        "pending-conditional:"
    )
    assert not result.conditioned.native_publication_authority
    blob = session.snapshot()
    assert result == session.process(**args)
    assert blob == session.snapshot() and model.calls == 0
    recovered = restore(path, pin, blob)
    assert recovered.snapshot() == blob
    args["request_id"] = "two"
    assert session.process(**args) == recovered.process(**args)
    assert session.snapshot() == recovered.snapshot()


@pytest.mark.parametrize("attack", ["raise", "source", "cluster", "covariance"])
def test_conditional_failure_also_rolls_back_actual_proposal_sampling(attack, tmp_path):
    session, path, pin, model, args = setup(tmp_path, ARMS[0])
    before = session.snapshot()
    model.attack = attack
    with pytest.raises((ValueError, RuntimeError)):
        session.process(**args)
    assert before == session.snapshot() and model.calls == 0
    model.attack = None
    recovered = restore(path, pin, before)
    assert session.process(**args) == recovered.process(**args)
    assert session.snapshot() == recovered.snapshot()


def test_resealed_complete_false_analytic_output_is_recomputed_on_restore(tmp_path):
    session, path, pin, _, args = setup(tmp_path, ARMS[0])
    session.process(**args)
    authentic = session.snapshot()
    payload = json.loads(authentic)
    request = StateCodec().loads(payload["requests"][0])
    row = request.result.conditioned.candidates[0]
    state = replace(row.statistics, alpha=(30.0, 20.0))
    hypothesis = row.resolved_hypothesis.model_copy(
        update={
            "state": row.resolved_hypothesis.state.model_copy(
                update={"statistic_state_ref": state.reference}
            )
        }
    )
    changed = replace(row, statistics=state, resolved_hypothesis_json=hypothesis.model_dump_json())
    conditioned = replace(
        request.result.conditioned, candidates=(changed, *request.result.conditioned.candidates[1:])
    )
    request = replace(request, result=replace(request.result, conditioned=conditioned))
    payload["requests"][0] = StateCodec().dumps(request)
    forged = encoded(payload)
    # Outer identity resealed; graph references and resolved statistic refs valid.
    with pytest.raises(ValueError, match="complete model replay"):
        restore(path, pin, forged)
    assert session.snapshot() == authentic


def test_changed_conditional_group_request_cannot_reuse_old_neural_receipt(tmp_path):
    session, _, _, _, args = setup(tmp_path, ARMS[0])
    session.process(**args)
    before = session.snapshot()
    args["groups"] = args["groups"][:1]
    with pytest.raises(ValueError, match="partition"):
        session.process(**args)
    assert session.snapshot() == before
