"""Second local review: independent grammar count and complete positive recovery."""

import hashlib
import json
import math
import sys
from datetime import timedelta
from pathlib import Path

import pytest
import torch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tests"))
from test_runtime_candidates import (  # noqa: E402
    ARMS,
    LEDGER,
    NOW,
    checkpoint,
    context,
    generate,
    pixel,
    posterior_context,
)

from cpswm.data_preflight.runtime_candidate_session import RuntimeCandidateSession  # noqa: E402
from cpswm.data_preflight.runtime_candidates import event_grid  # noqa: E402
from cpswm.system.reproducibility import content_sha256  # noqa: E402


@pytest.mark.parametrize("n,actors,locations", [(3, 1, 1), (5, 1, 2), (6, 2, 1)])
def test_independent_closed_form_complete_grammar_cardinality(n, actors, locations):
    values = tuple(
        event_grid(
            tuple(NOW + timedelta(seconds=i) for i in range(n)),
            tuple(f"a{i}" for i in range(actors)),
            tuple(f"l{i}" for i in range(locations)),
        )
    )
    # For k events: choose time slots; first pickup/carry fixes holder, each
    # middle step either carries or hands off to any distinct receiver.
    expected = 2 * actors * locations + sum(
        math.comb(n, k) * actors ** (k - 2) * locations**k for k in range(3, n + 1)
    )
    assert len(values) == expected
    assert len({content_sha256(v) for v in values}) == expected


def test_semantic_and_pixel_generation_does_not_silently_invent_parent_after_retraction():
    ctx = posterior_context()
    raw = ctx.model_dump()
    for revision in raw["revisions"]:
        revision["status"] = "retracted"
    from cpswm.data_preflight.proposal_samples import ProposalContext

    with pytest.raises(ValueError, match="no active parent"):
        generate(ProposalContext.model_validate(raw))


@pytest.mark.parametrize("arm", ARMS)
def test_complete_forged_but_internally_valid_history_requires_external_digest_custody(
    tmp_path, arm
):
    previous = torch.get_num_threads()
    torch.set_num_threads(2)
    try:
        path, pin = checkpoint(tmp_path, arm)
        genuine = RuntimeCandidateSession(path, manifest_sha256=pin, seed=7)
        genuine.process(
            request_id="one", context=context([pixel(0)]), bootstrap_ledger_lineage_ref=LEDGER
        )
        authentic = genuine.snapshot()
        forged = RuntimeCandidateSession(path, manifest_sha256=pin, seed=7)
        altered = pixel(0).model_copy(update={"candidates": (), "input_sha256": "e" * 64})
        forged.process(
            request_id="one", context=context([altered]), bootstrap_ledger_lineage_ref=LEDGER
        )
        blob = forged.snapshot()
        # Authentic externally-held identity rejects a fully coherent replacement.
        with pytest.raises(ValueError, match="identity mismatch"):
            RuntimeCandidateSession.restore(
                path,
                manifest_sha256=pin,
                snapshot=blob,
                snapshot_sha256=hashlib.sha256(authentic).hexdigest(),
            )
        # If the caller also replaces its external identity, internal replay is
        # deliberately NOT authentication of the pixels or ledger's provenance.
        accepted = RuntimeCandidateSession.restore(
            path,
            manifest_sha256=pin,
            snapshot=blob,
            snapshot_sha256=hashlib.sha256(blob).hexdigest(),
        )
        assert accepted.snapshot() == blob
        payload = json.loads(blob)
        assert not payload["ledger_authorized"] and not payload["native_publication_authorized"]
        assert not payload["requests"]["one"]["generation_report"]["analytic_updates_computed"]
        # Rejection on the genuine object leaves exact subsequent behavior intact.
        restored = RuntimeCandidateSession.restore(
            path,
            manifest_sha256=pin,
            snapshot=authentic,
            snapshot_sha256=hashlib.sha256(authentic).hexdigest(),
        )
        kwargs = dict(
            request_id="two",
            context=context([pixel(0), pixel(1)]),
            bootstrap_ledger_lineage_ref=LEDGER,
        )
        assert genuine.process(**kwargs) == restored.process(**kwargs)
    finally:
        torch.set_num_threads(previous)


@pytest.mark.parametrize("arm", ARMS)
def test_real_network_six_operation_support_and_overflow_atomicity(tmp_path, arm):
    previous = torch.get_num_threads()
    torch.set_num_threads(2)
    try:
        from cpswm.data_preflight.proposal_samples import ProposalContext

        raw = posterior_context().model_dump()
        raw["parents"] = [raw["parents"][0], raw["parents"][2]]
        raw["revisions"] = [raw["revisions"][0], raw["revisions"][2]]
        raw["visible"]["pixel_observations"] = raw["visible"]["pixel_observations"][:2]
        ctx = ProposalContext.model_validate(raw)
        path, pin = checkpoint(tmp_path, arm)
        session = RuntimeCandidateSession(path, manifest_sha256=pin, seed=11)
        first = session.process(
            request_id="first", context=ctx, bootstrap_ledger_lineage_ref=LEDGER
        )
        assert len(first.support.targets) == 88
        assert set(first.support.report["operation_counts"]) == {
            "branch",
            "revise",
            "retract",
            "reactivate",
            "rejuvenate",
            "preserve_unresolved",
        }
        scored = session._engine.score_support(context=ctx, support=first.support.targets)
        assert math.fsum(
            math.exp(v.probability.joint_log_probability) for v in scored
        ) == pytest.approx(1, abs=1e-12)
        before = session.snapshot()
        with pytest.raises(ValueError, match="node budget; no truncation"):
            session.process(
                request_id="overflow",
                context=posterior_context(),
                bootstrap_ledger_lineage_ref=LEDGER,
            )
        assert before == session.snapshot()
        restored = RuntimeCandidateSession.restore(
            path,
            manifest_sha256=pin,
            snapshot=before,
            snapshot_sha256=hashlib.sha256(before).hexdigest(),
        )
        args = dict(request_id="second", context=ctx, bootstrap_ledger_lineage_ref=LEDGER)
        assert session.process(**args) == restored.process(**args)
        assert session.snapshot() == restored.snapshot()
    finally:
        torch.set_num_threads(previous)
