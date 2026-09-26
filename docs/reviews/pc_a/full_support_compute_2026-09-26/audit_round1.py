"""First review: execute a valid proposal, alter non-tensor architecture, retry."""

import sys
from pathlib import Path

import pytest
import torch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tests"))
from test_proposal_execution_derivation import artifacts  # noqa: E402
from test_runtime_candidates import LEDGER, context, pixel  # noqa: E402

from cpswm.data_preflight.runtime_candidate_session import RuntimeCandidateSession  # noqa: E402


@pytest.mark.parametrize("fault", ("normalization", "attention_heads", "activation"))
def test_live_non_tensor_architecture_changes_cannot_publish_a_new_valid_proposal(tmp_path, fault):
    previous = torch.get_num_threads()
    torch.set_num_threads(2)
    try:
        _, _, path, pin = artifacts(tmp_path)
        session = RuntimeCandidateSession(path, manifest_sha256=pin, seed=11)
        ctx = context([pixel(0)])
        session.process(request_id="first", context=ctx, bootstrap_ledger_lineage_ref=LEDGER)
        before = session.snapshot()
        layer = session._engine._model.encoder.layers[0]
        if fault == "normalization":
            owner, name, value = layer.norm1, "eps", 0.75
        elif fault == "attention_heads":
            owner, name, value = layer.self_attn, "num_heads", 2
        else:
            owner, name, value = layer, "activation", torch.sigmoid
        original = getattr(owner, name)
        try:
            setattr(owner, name, value)
            with pytest.raises(ValueError, match=r"binding|structure|architecture"):
                session.process(
                    request_id="second", context=ctx, bootstrap_ledger_lineage_ref=LEDGER
                )
        finally:
            setattr(owner, name, original)
        assert session.snapshot() == before
        session.process(request_id="second", context=ctx, bootstrap_ledger_lineage_ref=LEDGER)
    finally:
        torch.set_num_threads(previous)
