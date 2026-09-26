"""Resource-profile growth must preserve all keys and original distributions."""

import pytest
import torch
from torch.nn import functional as F

from cpswm.data_preflight import proposal_graph_compute as compute
from cpswm.data_preflight.typed_proposal_networks import NetworkConfig


@pytest.fixture(autouse=True)
def two_threads():
    old = torch.get_num_threads()
    torch.set_num_threads(2)
    yield
    torch.set_num_threads(old)


@pytest.mark.parametrize("keys", (32768, 37241, 65536))
def test_declared_workspace_covers_each_full_key_row(keys):
    rows = compute.query_block_size(keys, 4, 4)
    assert 0 < rows <= 128
    assert rows * keys * 4 * (3 * 4 + 2) <= compute.ATTENTION_TEMPORARY_BYTES
    assert rows == 128 or (rows + 1) * keys * 4 * 14 > compute.ATTENTION_TEMPORARY_BYTES
    NetworkConfig(max_nodes=keys, execution_backend=compute.BLOCKED_BACKEND).validate()
    assert NetworkConfig().max_nodes == 4096
    assert compute.DEFAULT_BLOCKED_NODES == 32768


@pytest.mark.parametrize("self_attention", (False, True))
def test_reducing_only_queries_preserves_outputs_and_full_masks(monkeypatch, self_attention):
    with torch.random.fork_rng(devices=[]), torch.no_grad():
        torch.manual_seed(753)
        module = torch.nn.MultiheadAttention(64, 4, dropout=0, batch_first=True).eval()
        memory = torch.randn(301, 64)
        queries = memory if self_attention else torch.randn(257, 64)
        mask = torch.rand(len(queries), len(memory)) > 0.3
        mask[:, -1] = True
        seen = []

        def allowed(a, b):
            seen.append((a, b))
            return mask[a:b]

        full, _ = module(
            queries[None], memory[None], memory[None], attn_mask=~mask, need_weights=False
        )
        monkeypatch.setattr(compute, "ATTENTION_TEMPORARY_BYTES", 13 * 301 * 4 * 14)
        actual = compute.attend_query_rows(module, queries, memory, allowed_rows=allowed)
        assert seen == [(i, min(i + 13, len(queries))) for i in range(0, len(queries), 13)]
        torch.testing.assert_close(actual, full[0], atol=1e-5, rtol=1e-5)


def test_last_key_beyond_previous_limit_contributes_to_global_normalization():
    # Exact analytic mean; any truncation or separately normalized key blocks fails.
    size = 65536
    with torch.no_grad():
        module = torch.nn.MultiheadAttention(64, 4, dropout=0, batch_first=True).eval()
        module.in_proj_weight.zero_()
        module.in_proj_weight[128:].copy_(torch.eye(64))
        module.in_proj_bias.zero_()
        module.out_proj.weight.copy_(torch.eye(64))
        module.out_proj.bias.zero_()
        memory = torch.zeros(size, 64)
        memory[-1] = size
        queries = torch.zeros(151, 64)
        actual = compute.attend_query_rows(module, queries, memory)
        torch.testing.assert_close(actual, torch.ones_like(actual), atol=1e-5, rtol=1e-5)


def test_one_row_over_budget_is_rejected_before_projection(monkeypatch):
    module = torch.nn.MultiheadAttention(64, 4, dropout=0, batch_first=True).eval()
    monkeypatch.setattr(compute, "ATTENTION_TEMPORARY_BYTES", 1)
    called = []
    monkeypatch.setattr(F, "linear", lambda *args, **kwargs: called.append(True))
    with torch.no_grad(), pytest.raises(ValueError, match="one complete attention row"):
        compute.attend_query_rows(module, torch.ones(1, 64), torch.ones(2, 64))
    assert called == []
