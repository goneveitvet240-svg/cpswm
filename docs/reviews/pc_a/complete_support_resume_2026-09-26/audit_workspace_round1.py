"""First review: full-key numerical reference and failure before attention work."""

import pytest
import torch
from torch.nn import functional as F

from cpswm.data_preflight import proposal_graph_compute as compute


@pytest.fixture(autouse=True)
def cpu_two():
    previous = torch.get_num_threads()
    torch.set_num_threads(2)
    yield
    torch.set_num_threads(previous)


@pytest.mark.parametrize("keys", (37241, 65536))
def test_far_keys_against_independent_double_precision_full_sum(keys):
    with torch.random.fork_rng(devices=[]), torch.no_grad():
        torch.manual_seed(1724)
        module = torch.nn.MultiheadAttention(64, 4, dropout=0, batch_first=True).eval()
        memory, query = torch.randn(keys, 64), torch.randn(139, 64)
        # Independent float64 reference uses all keys in one normalization.
        weight, bias = module.in_proj_weight.double(), module.in_proj_bias.double()
        q = F.linear(query.double(), weight[:64], bias[:64]).reshape(139, 4, 16).transpose(0, 1)
        k = (
            F.linear(memory.double(), weight[64:128], bias[64:128])
            .reshape(keys, 4, 16)
            .transpose(0, 1)
        )
        v = F.linear(memory.double(), weight[128:], bias[128:]).reshape(keys, 4, 16).transpose(0, 1)
        expected = torch.bmm((torch.bmm(q, k.transpose(1, 2)) / 4).softmax(-1), v)
        expected = F.linear(
            expected.transpose(0, 1).reshape(139, 64),
            module.out_proj.weight.double(),
            module.out_proj.bias.double(),
        )
        actual = compute.attend_query_rows(module, query, memory)
        torch.testing.assert_close(actual.double(), expected, atol=1e-5, rtol=1e-5)


@pytest.mark.parametrize("value", (0, -1, True, 0.5))
def test_invalid_resource_dimensions_do_not_round_into_accepted_profiles(value):
    with pytest.raises(ValueError, match="positive integers"):
        compute.query_block_size(value, 4, 4)
