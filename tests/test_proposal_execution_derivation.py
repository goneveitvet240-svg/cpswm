"""Pinned derivative lineage, complete re-sealed attacks and legal recovery."""

import hashlib
import json

import pytest
import torch
from test_runtime_candidates import LEDGER, context, pixel

from cpswm.data_preflight.proposal_inference_session import ProposalInferenceSession, encoded
from cpswm.data_preflight.proposal_trainer import (
    derive_execution_checkpoint,
    load_checkpoint,
    save_checkpoint,
)
from cpswm.data_preflight.runtime_candidate_session import RuntimeCandidateSession
from cpswm.data_preflight.typed_proposal_networks import ARMS, TypedProposalNetwork


@pytest.fixture(autouse=True)
def two_threads():
    previous = torch.get_num_threads()
    torch.set_num_threads(2)
    yield
    torch.set_num_threads(previous)


def artifacts(tmp_path, arm=ARMS[0]):
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(74)
        model = TypedProposalNetwork(arm)
    parent = tmp_path / "parent"
    original = save_checkpoint(model, {"track": "TEST_FIXTURE_UNTRAINED"}, parent)
    # An actual old manifest did not contain the newly introduced default field.
    manifest = json.loads((parent / "manifest.json").read_bytes())
    del manifest["config"]["execution_backend"]
    old_bytes = encoded(manifest)
    (parent / "manifest.json").write_bytes(old_bytes)
    original = hashlib.sha256(old_bytes).hexdigest()
    derived = tmp_path / "derived"
    pin = derive_execution_checkpoint(
        parent, manifest_sha256=original, directory=derived, max_nodes=32768
    )
    return parent, original, derived, pin


@pytest.mark.parametrize("arm", ARMS)
def test_original_bytes_and_lineage_preserved_with_old_config_compatibility(tmp_path, arm):
    parent, original, derived, pin = artifacts(tmp_path, arm)
    old, before = load_checkpoint(parent, manifest_sha256=original)
    new, after = load_checkpoint(derived, manifest_sha256=pin)
    assert before["training"] == after["training"]
    assert before["weights_sha256"] == after["weights_sha256"]
    assert (parent / "weights.pt").read_bytes() == (derived / "weights.pt").read_bytes()
    assert (
        after["execution_derivation"]["parent_manifest_utf8"].encode()
        == (parent / "manifest.json").read_bytes()
    )
    assert all(torch.equal(v, new.state_dict()[k]) for k, v in old.state_dict().items())
    assert after["execution_derivation"]["added_optimizer_steps"] == 0
    assert after["production_authorized"] is False
    with pytest.raises(ValueError, match="explicit execution derivation"):
        save_checkpoint(new, before["training"], tmp_path / "laundered")
    with pytest.raises(ValueError, match="original dense"):
        derive_execution_checkpoint(
            derived, manifest_sha256=pin, directory=tmp_path / "chain", max_nodes=32768
        )


@pytest.mark.parametrize(
    "attack",
    (
        "training",
        "weights",
        "parent",
        "architecture",
        "leaf_limit",
        "authority",
        "source",
        "torch",
        "optimizer",
        "boolean_optimizer",
        "missing",
        "extra",
    ),
)
def test_fully_resealed_derivatives_cannot_change_pinned_parent_claims(tmp_path, attack):
    _, _, derived, pin = artifacts(tmp_path)
    original = (derived / "manifest.json").read_bytes()
    payload = json.loads(original)
    lineage = payload["execution_derivation"]
    if attack == "training":
        payload["training"] = {"track": "INVENTED_NATURAL_TRAINING", "optimizer_steps": 50}
    elif attack == "weights":
        payload["weights_sha256"] = "b" * 64
    elif attack == "parent":
        lineage["parent_manifest_sha256"] = "c" * 64
    elif attack == "architecture":
        payload["arm"] = ARMS[1]
    elif attack == "leaf_limit":
        payload["config"]["max_bytes_per_leaf"] *= 2
    elif attack == "authority":
        payload["production_authorized"] = True
    elif attack == "source":
        lineage["execution_source_files"]["proposal_graph_compute.py"] = "d" * 64
    elif attack == "torch":
        lineage["execution_torch_version"] = "fabricated-version"
    elif attack in {"optimizer", "boolean_optimizer"}:
        lineage["added_optimizer_steps"] = 1 if attack == "optimizer" else False
    elif attack == "missing":
        del payload["execution_derivation"]
    else:
        lineage["calibration_authorized"] = True
    forged = encoded(payload)
    (derived / "manifest.json").write_bytes(forged)
    with pytest.raises(ValueError):
        load_checkpoint(derived, manifest_sha256=hashlib.sha256(forged).hexdigest())
    (derived / "manifest.json").write_bytes(original)
    load_checkpoint(derived, manifest_sha256=pin)  # Rejection did not poison legal reuse.


@pytest.mark.parametrize("arm", ARMS)
def test_blocked_session_exact_restore_complete_subset_forgery_and_legal_retry(tmp_path, arm):
    parent, original, derived, pin = artifacts(tmp_path, arm)
    ctx = context([pixel(0)])
    session = RuntimeCandidateSession(derived, manifest_sha256=pin, seed=11)
    first = session.process(request_id="one", context=ctx, bootstrap_ledger_lineage_ref=LEDGER)
    blob = session.snapshot()
    restored = RuntimeCandidateSession.restore(
        derived,
        manifest_sha256=pin,
        snapshot=blob,
        snapshot_sha256=hashlib.sha256(blob).hexdigest(),
    )
    assert restored.snapshot() == blob
    with pytest.raises(ValueError, match="binding"):
        RuntimeCandidateSession.restore(
            parent,
            manifest_sha256=original,
            snapshot=blob,
            snapshot_sha256=hashlib.sha256(blob).hexdigest(),
        )
    subset = tuple(t for t in first.support.targets if t.candidate.events[0].kind == "unresolved")
    engine = ProposalInferenceSession(derived, manifest_sha256=pin, seed=11)
    engine.infer(request_id="one", context=ctx, support=subset)
    forged_engine = engine.snapshot()
    # The counterfeit is itself a valid, fully rescored and sampled NN history.
    ProposalInferenceSession.restore(
        derived,
        manifest_sha256=pin,
        snapshot=forged_engine,
        snapshot_sha256=hashlib.sha256(forged_engine).hexdigest(),
    )
    payload = json.loads(blob)
    payload["engine"] = json.loads(forged_engine)
    forged = encoded(payload)
    with pytest.raises(ValueError, match="regenerated"):
        RuntimeCandidateSession.restore(
            derived,
            manifest_sha256=pin,
            snapshot=forged,
            snapshot_sha256=hashlib.sha256(forged).hexdigest(),
        )
    kwargs = {"request_id": "two", "context": ctx, "bootstrap_ledger_lineage_ref": LEDGER}
    assert session.process(**kwargs) == restored.process(**kwargs)
    assert session.snapshot() == restored.snapshot()
