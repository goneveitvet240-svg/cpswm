"""Second review: fully resealed profiles/history and interrupted state recovery."""

import hashlib
import json
import sys
from pathlib import Path

import pytest
import torch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tests"))
from test_proposal_execution_derivation import artifacts  # noqa: E402
from test_runtime_candidates import LEDGER, context, pixel  # noqa: E402

from cpswm.data_preflight import proposal_graph_compute as compute  # noqa: E402
from cpswm.data_preflight.proposal_inference_session import encoded  # noqa: E402
from cpswm.data_preflight.proposal_trainer import (  # noqa: E402
    derive_execution_checkpoint,
    load_checkpoint,
)
from cpswm.data_preflight.runtime_candidate_session import RuntimeCandidateSession  # noqa: E402
from cpswm.data_preflight.typed_proposal_networks import ARMS  # noqa: E402


@pytest.fixture(autouse=True)
def cpu_two():
    previous = torch.get_num_threads()
    torch.set_num_threads(2)
    yield
    torch.set_num_threads(previous)


@pytest.mark.parametrize("arm", ARMS)
def test_complete_high_profile_history_cannot_relabel_low_profile_or_gain_authority(tmp_path, arm):
    parent, original, low, low_pin = artifacts(tmp_path, arm)
    high = tmp_path / "high"
    high_pin = derive_execution_checkpoint(
        parent, manifest_sha256=original, directory=high, max_nodes=65536
    )
    ctx = context([pixel(0)])
    session = RuntimeCandidateSession(high, manifest_sha256=high_pin, seed=77)
    receipt = session.process(request_id="first", context=ctx, bootstrap_ledger_lineage_ref=LEDGER)
    assert (
        not receipt.receipt.ledger_authorized and not receipt.receipt.native_publication_authorized
    )
    blob = session.snapshot()
    with pytest.raises(ValueError, match="binding"):
        RuntimeCandidateSession.restore(
            low,
            manifest_sha256=low_pin,
            snapshot=blob,
            snapshot_sha256=hashlib.sha256(blob).hexdigest(),
        )
    restored = RuntimeCandidateSession.restore(
        high,
        manifest_sha256=high_pin,
        snapshot=blob,
        snapshot_sha256=hashlib.sha256(blob).hexdigest(),
    )
    forged = json.loads(blob)
    forged["engine"]["ledger_authorized"] = True
    raw = encoded(forged)
    with pytest.raises(ValueError, match=r"history|replay|snapshot"):
        RuntimeCandidateSession.restore(
            high,
            manifest_sha256=high_pin,
            snapshot=raw,
            snapshot_sha256=hashlib.sha256(raw).hexdigest(),
        )
    args = dict(request_id="next", context=ctx, bootstrap_ledger_lineage_ref=LEDGER)
    assert session.process(**args) == restored.process(**args)
    assert session.snapshot() == restored.snapshot()


@pytest.mark.parametrize("arm", ARMS)
def test_attention_workspace_failure_after_valid_history_preserves_next_rng(
    tmp_path, monkeypatch, arm
):
    parent, original, _, _ = artifacts(tmp_path, arm)
    path = tmp_path / "high"
    pin = derive_execution_checkpoint(
        parent, manifest_sha256=original, directory=path, max_nodes=65536
    )
    session = RuntimeCandidateSession(path, manifest_sha256=pin, seed=53)
    ctx = context([pixel(0)])
    args = dict(context=ctx, bootstrap_ledger_lineage_ref=LEDGER)
    session.process(request_id="first", **args)
    before = session.snapshot()
    reference = RuntimeCandidateSession.restore(
        path,
        manifest_sha256=pin,
        snapshot=before,
        snapshot_sha256=hashlib.sha256(before).hexdigest(),
    )
    with monkeypatch.context() as patch:
        patch.setattr(compute, "ATTENTION_TEMPORARY_BYTES", 1)
        with pytest.raises(ValueError, match="resource limit"):
            session.process(request_id="next", **args)
    assert before == session.snapshot()
    assert session.process(request_id="next", **args) == reference.process(
        request_id="next", **args
    )
    assert session.snapshot() == reference.snapshot()


def test_complete_resealed_derivative_cannot_remove_the_physical_bound(tmp_path):
    _, _, path, pin = artifacts(tmp_path)
    original = (path / "manifest.json").read_bytes()
    manifest = json.loads(original)
    manifest["config"]["max_nodes"] = 65537
    forged = encoded(manifest)
    (path / "manifest.json").write_bytes(forged)
    with pytest.raises(ValueError, match="bounded local node budget"):
        load_checkpoint(path, manifest_sha256=hashlib.sha256(forged).hexdigest())
    (path / "manifest.json").write_bytes(original)
    load_checkpoint(path, manifest_sha256=pin)
