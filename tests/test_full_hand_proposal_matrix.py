"""First review: complete event-chain scoring and fixed matrix selection."""

import math
import sys
from dataclasses import replace
from pathlib import Path

import pytest
import torch
from test_proposal_hand_input import context, pixel, with_hands

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from run_hfd_hand_proposals import checked_scores, plan_windows

from cpswm.data_preflight.proposal_graph_compute import BLOCKED_BACKEND
from cpswm.data_preflight.proposal_trainer import distribution
from cpswm.data_preflight.runtime_candidates import generate_runtime_candidates
from cpswm.data_preflight.typed_proposal_networks import (
    ARMS,
    NetworkConfig,
    TypedProposalNetwork,
)


def matrix_keys():
    return tuple(f"{s * 64}/window-{i:06d}" for s in ("b", "a") for i in (10, 0, 5))


def test_window_selection_retains_every_declared_window_in_deterministic_order():
    rows = {k: None for k in matrix_keys()}
    all_windows, first = plan_windows(rows, "all")
    assert all_windows == tuple(sorted(rows)) and len(all_windows) == 6
    assert len(first) == 2 and all(k.endswith("000000") for k in first)
    assert plan_windows(dict(reversed(list(rows.items()))), "all") == (all_windows, first)
    assert set(plan_windows(rows, "first")[0]) == first
    with pytest.raises(ValueError):
        plan_windows(rows, "success_only")
    with pytest.raises(ValueError):
        plan_windows({k: v for k, v in rows.items() if not k.endswith("000000")}, "all")


@pytest.mark.parametrize("arm", ARMS)
def test_four_frame_complete_chains_and_unknown_actor_are_really_scored(arm):
    torch.set_num_threads(2)
    ctx = context([with_hands(pixel(i), x=25 + i) for i in range(4)])
    support = generate_runtime_candidates(
        ctx, bootstrap_ledger_lineage_ref="hybrid-ledger:" + "a" * 64
    ).targets
    chains = {tuple(e.kind for e in t.candidate.events) for t in support}
    assert ("pick_up", "carry", "handoff", "place") in chains
    assert ("unresolved",) in chains and ("no_move",) in chains
    assert any("unknown_actor" in [e.actor_key for e in t.candidate.events] for t in support)
    with torch.random.fork_rng():
        torch.manual_seed(91)
        model = TypedProposalNetwork(
            arm, replace(NetworkConfig(), max_nodes=65536, execution_backend=BLOCKED_BACKEND)
        ).eval()
    with torch.no_grad():
        a = distribution(model, ctx, support)
        left, mass = checked_scores(tuple(a.decode(k) for k in a.target_sha256s), support)
        b = distribution(model, ctx, tuple(reversed(support)))
        right, _ = checked_scores(tuple(b.decode(k) for k in b.target_sha256s), support)
    assert left == right
    assert mass == pytest.approx(1, abs=1e-10)
    assert len(left) == len(support)
    assert all(math.isfinite(r["joint_log_probability"]) for r in left)
