"""Compare full graph arithmetic independently of checkpoint export and labels."""

from dataclasses import replace

import pytest
import torch
from test_typed_proposal_training import data

from cpswm.data_preflight.proposal_decoder import TypedProposalDistribution
from cpswm.data_preflight.proposal_graph_compute import (
    BLOCKED_BACKEND,
    MAX_BLOCKED_NODES,
    QUERY_BATCH,
    attend_query_rows,
    project_key_value,
    typed_allowed_rows,
)
from cpswm.data_preflight.proposal_samples import export_context
from cpswm.data_preflight.typed_proposal_networks import ARMS, NetworkConfig, TypedProposalNetwork


@pytest.fixture(autouse=True)
def two_cpu_threads():
    previous = torch.get_num_threads()
    torch.set_num_threads(2)
    yield
    torch.set_num_threads(previous)


def paired(arm, max_nodes=4096):
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(41)
        dense = TypedProposalNetwork(arm, NetworkConfig(max_nodes=max_nodes)).eval()
        blocked = TypedProposalNetwork(
            arm, replace(dense.config, execution_backend=BLOCKED_BACKEND)
        ).eval()
    blocked.load_state_dict(dense.state_dict())
    return dense, blocked


@pytest.mark.parametrize("arm", ARMS)
def test_all_arms_retain_dense_graph_and_complete_probability_with_same_parameters(arm):
    sample, support = data()
    context = sample.runtime_context()
    dense, blocked = paired(arm)
    with torch.no_grad():
        original = dense.prepare(context, support)
        tiled = blocked.prepare(context, support)
        assert original.node_count == tiled.node_count
        torch.testing.assert_close(original.memory, tiled.memory, atol=1e-5, rtol=1e-5)
        torch.testing.assert_close(original.vectors, tiled.vectors, atol=1e-5, rtol=1e-5)
        before = TypedProposalDistribution(
            context=context, runtime_candidates=support, scorer=original
        )
        after = TypedProposalDistribution(context=context, runtime_candidates=support, scorer=tiled)
        assert before.target_sha256s == after.target_sha256s
        logs = torch.stack(
            [after.factor_log_probabilities(key).sum() for key in after.target_sha256s]
        )
        assert float(logs.exp().sum()) == pytest.approx(1, abs=1e-12)
        for key in before.target_sha256s:
            torch.testing.assert_close(
                before.factor_log_probabilities(key),
                after.factor_log_probabilities(key),
                atol=1e-5,
                rtol=1e-5,
            )
        assert len({after.decode(k).target.operation for k in after.target_sha256s}) == 6
    assert all(
        torch.equal(value, blocked.state_dict()[key]) for key, value in dense.state_dict().items()
    )


def test_masks_retain_far_edges_and_anchor_across_query_boundaries():
    rows = [(("candidate", str(i // 3), "state", str(i)), str(i % 11)) for i in range(300)]
    expected = torch.zeros(301, 301, dtype=torch.bool)
    expected[0, :] = True
    expected[:, 0] = True
    for i, (path_i, value_i) in enumerate(rows):
        for j, (path_j, value_j) in enumerate(rows):
            expected[i + 1, j + 1] = path_i[:-1] == path_j[:-1] or value_i == value_j
    factory = typed_allowed_rows(rows, torch.device("cpu"))
    actual = torch.cat(
        [factory(start, min(start + QUERY_BATCH, 301)) for start in range(0, 301, QUERY_BATCH)]
    )
    assert torch.equal(actual, expected)
    assert actual[1, 298]  # Same scalar across more than two query chunks.


@pytest.mark.parametrize("self_attention", (False, True))
def test_query_chunks_preserve_global_normalization_and_cached_keys(self_attention):
    with torch.random.fork_rng(devices=[]), torch.no_grad():
        torch.manual_seed(63)
        module = torch.nn.MultiheadAttention(64, 4, dropout=0, batch_first=True).eval()
        memory = torch.randn(301, 64)
        query = memory if self_attention else torch.randn(275, 64)
        expected, _ = module(query[None], memory[None], memory[None], need_weights=False)
        actual = attend_query_rows(module, query, memory)
        cached = attend_query_rows(
            module, query, memory, projected_kv=project_key_value(module, memory)
        )
        torch.testing.assert_close(actual, expected[0], atol=1e-5, rtol=1e-5)
        torch.testing.assert_close(cached, expected[0], atol=1e-5, rtol=1e-5)


def test_blocked_backend_never_creates_partial_training_graphs():
    sample, support = data()
    _, model = paired(ARMS[0])
    with pytest.raises(ValueError, match="without gradients"):
        model.prepare(sample.runtime_context(), support)
    with torch.no_grad():
        scorer = model.prepare(sample.runtime_context(), support)
        model.train()
        with pytest.raises(ValueError, match="evaluation only"):
            model.prepare(sample.runtime_context(), support)
    model.eval()
    with pytest.raises(ValueError, match="without gradients"):
        scorer(
            export_context(sample.runtime_context()),
            "operation",
            (),
            tuple(sorted({t.operation.value for t in support})),
            runtime_candidates=support,
        )


@pytest.mark.parametrize("value", (0, -1, True, 2.5, MAX_BLOCKED_NODES + 1))
def test_invalid_or_excessive_resource_profiles_are_rejected(value):
    with pytest.raises(ValueError, match=r"resource|budget"):
        NetworkConfig(max_nodes=value, execution_backend=BLOCKED_BACKEND).validate()


def test_cached_choice_projection_refuses_changed_actual_parameter_bytes():
    sample, support = data()
    _, model = paired(ARMS[1])
    with torch.no_grad():
        scorer = model.prepare(sample.runtime_context(), support)
        model.choice_attention.in_proj_weight.data.add_(0.25)
        with pytest.raises(ValueError, match="optimizer state"):
            scorer(
                export_context(sample.runtime_context()),
                "operation",
                (),
                tuple(sorted({t.operation.value for t in support})),
                runtime_candidates=support,
            )
