"""Round-one attacks against frozen runtime source; no production edits."""

import hashlib
import json
import sys
from pathlib import Path

import pytest
import torch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tests"))
from test_runtime_candidates import ARMS, LEDGER, checkpoint, context, pixel  # noqa: E402

from cpswm.data_preflight.proposal_inference_session import encoded  # noqa: E402
from cpswm.data_preflight.runtime_candidate_session import RuntimeCandidateSession  # noqa: E402


@pytest.fixture
def session(tmp_path):
    previous = torch.get_num_threads()
    torch.set_num_threads(2)
    path, pin = checkpoint(tmp_path, ARMS[0])
    value = RuntimeCandidateSession(path, manifest_sha256=pin, seed=11)
    value.process(
        request_id="first", context=context([pixel(0)]), bootstrap_ledger_lineage_ref=LEDGER
    )
    yield value, path, pin
    torch.set_num_threads(previous)


@pytest.mark.parametrize("fault", ["ledger", "authority", "drop", "extra", "report", "budget"])
def test_resealed_generation_metadata_cannot_change_runtime_history(session, fault):
    value, path, pin = session
    before = value.snapshot()
    payload = json.loads(before)
    if fault == "ledger":
        payload["requests"]["first"]["bootstrap_ledger_lineage_ref"] = "hybrid-ledger:" + "9" * 64
    elif fault == "authority":
        payload["native_publication_authorized"] = True
        payload["ledger_authorized"] = True
    elif fault == "drop":
        del payload["requests"]["first"]
    elif fault == "extra":
        payload["requests"]["unexecuted"] = payload["requests"]["first"]
    elif fault == "report":
        payload["requests"]["first"]["generation_report"]["analytic_updates_computed"] = True
    else:
        payload["requests"]["first"]["max_candidates"] = 1
    blob = encoded(payload)
    with pytest.raises(ValueError):
        RuntimeCandidateSession.restore(
            path,
            manifest_sha256=pin,
            snapshot=blob,
            snapshot_sha256=hashlib.sha256(blob).hexdigest(),
        )
    assert value.snapshot() == before


def test_overflow_and_detached_output_mutation_do_not_advance_rng_or_history(session):
    value, path, pin = session
    before = value.snapshot()
    with pytest.raises(ValueError, match="no truncation"):
        value.process(
            request_id="failed",
            context=context([pixel(0), pixel(1)]),
            bootstrap_ledger_lineage_ref=LEDGER,
            max_candidates=1,
        )
    assert value.snapshot() == before
    result = value.process(
        request_id="first", context=context([pixel(0)]), bootstrap_ledger_lineage_ref=LEDGER
    )
    object.__setattr__(
        result.support.context, "actor_support", ("unknown_actor", "injected-person")
    )
    result.support.report["ledger_authorized"] = True
    object.__setattr__(
        result.support.targets[0].candidate.state, "statistic_state_ref", "forged-computed-blocks"
    )
    assert value.snapshot() == before
    restored = RuntimeCandidateSession.restore(
        path,
        manifest_sha256=pin,
        snapshot=before,
        snapshot_sha256=hashlib.sha256(before).hexdigest(),
    )
    args = dict(
        request_id="next",
        context=context([pixel(0), pixel(1)]),
        bootstrap_ledger_lineage_ref=LEDGER,
    )
    assert value.process(**args) == restored.process(**args)
    assert value.snapshot() == restored.snapshot()
