"""Bounded-buffer evaluation of the same complete proposal graph.

Leaf sequences are independent GRUs. Attention is divided along QUERY rows only;
each row always sees every original key/value and the original typed edges.
This changes floating point execution order, not support or model parameters.
It is an explicit CPU evaluation backend, not a training or pruning algorithm.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

import torch
from torch import Tensor, nn
from torch.nn import functional as F
from torch.nn.utils.rnn import pack_padded_sequence, pad_sequence

if TYPE_CHECKING:
    from cpswm.data_preflight.typed_proposal_networks import TypedProposalNetwork

BLOCKED_BACKEND = "blocked-full-support-eval@1"
LEAF_BATCH = 128
QUERY_BATCH = 128
DEFAULT_BLOCKED_NODES = 32768
MAX_BLOCKED_NODES = 65536
# Conservative accounting for three score/probability buffers and two boolean
# masks, including head broadcasting. This bounds those temporary tensors,
# not the complete Python/PyTorch process or resident input/parameter storage.
ATTENTION_TEMPORARY_BYTES = 256 * 1024**2
LeafRow = tuple[tuple[str, ...], str]
ProjectedKV = tuple[Tensor, Tensor]


def query_block_size(keys: int, heads: int, element_bytes: int) -> int:
    """Keep ALL keys; reduce only independent query rows to fit the workspace."""
    if any(type(value) is not int or value <= 0 for value in (keys, heads, element_bytes)):
        raise ValueError("attention resource dimensions must be positive integers")
    per_query = keys * heads * (3 * element_bytes + 2)
    count = min(QUERY_BATCH, ATTENTION_TEMPORARY_BYTES // per_query)
    if count < 1:
        raise ValueError("resource limit: one complete attention row exceeds temporary budget")
    return count


def encode_leaf_batches(model: TypedProposalNetwork, encoded: list[bytes]) -> Tensor:
    chunks = []
    for start in range(0, len(encoded), LEAF_BATCH):
        sequences = [
            torch.tensor(list(raw), dtype=torch.long, device=model.anchor.device)
            for raw in encoded[start : start + LEAF_BATCH]
        ]
        padded = pad_sequence(sequences, batch_first=True, padding_value=256)
        packed = pack_padded_sequence(
            model.byte_embedding(padded),
            [len(s) for s in sequences],
            batch_first=True,
            enforce_sorted=False,
        )
        _, hidden = model.leaf_encoder(packed)
        chunks.append(hidden[-1])
    return torch.cat(chunks)


def _checked_attention(module: nn.MultiheadAttention) -> Tensor:
    if (
        not module.batch_first
        or module.dropout != 0
        or module.add_zero_attn
        or module.bias_k is not None
        or module.bias_v is not None
        or module.kdim != module.embed_dim
        or module.vdim != module.embed_dim
        or module.in_proj_weight is None
    ):
        raise ValueError("blocked execution requires the frozen attention structure")
    return module.in_proj_weight


def project_key_value(module: nn.MultiheadAttention, memory: Tensor) -> ProjectedKV:
    """Shared memory projection; a prepared scorer pins its parameter version."""
    weight = _checked_attention(module)
    width, heads = module.embed_dim, module.num_heads
    bias = module.in_proj_bias
    projected = F.linear(memory, weight[width:], None if bias is None else bias[width:])
    key, value = projected.reshape(len(memory), 2, heads, width // heads).permute(1, 2, 0, 3)
    return key, value


def attend_query_rows(
    module: nn.MultiheadAttention,
    queries: Tensor,
    memory: Tensor,
    *,
    allowed_rows: Callable[[int, int], Tensor] | None = None,
    projected_kv: ProjectedKV | None = None,
) -> Tensor:
    """Global softmax over ALL keys for each query, never per-key-block softmax."""
    weight = _checked_attention(module)
    width, heads = module.embed_dim, module.num_heads
    bias = module.in_proj_bias
    batch = query_block_size(len(memory), heads, queries.element_size())
    native_self = queries is memory and projected_kv is None
    if native_self:
        if bias is None:
            raise ValueError("blocked native self attention requires the frozen bias")
        # Mirror the installed CPU native encoder: projection WITHOUT bias,
        # then its bias/rescale kernel. Flash SDPA is mathematically equivalent
        # but exceeded the preregistered 1e-5 graph tolerance at 10,246 nodes.
        projected = F.linear(queries, weight)
        query4, key4, value4 = torch._transform_bias_rescale_qkv(projected[None], bias, heads)
        query, key, value = query4[0], key4[0], value4[0]
    else:
        query = F.linear(queries, weight[:width], None if bias is None else bias[:width])
        query = query.reshape(len(queries), heads, width // heads).transpose(0, 1)
        key, value = project_key_value(module, memory) if projected_kv is None else projected_kv
    pieces = []
    for start in range(0, len(queries), batch):
        stop = min(start + batch, len(queries))
        mask = None if allowed_rows is None else allowed_rows(start, stop)
        if native_self:
            scores = torch.bmm(query[:, start:stop], key.transpose(1, 2))
            probabilities = (
                scores.softmax(-1)
                if mask is None
                else torch._masked_softmax(
                    scores[None],
                    (~mask)[None, None].expand(1, heads, stop - start, len(memory)),
                    -1,
                    2,
                )[0]
            )
            attended = torch.bmm(probabilities, value)
        else:
            attended = F.scaled_dot_product_attention(
                query[None, :, start:stop],
                key[None],
                value[None],
                attn_mask=None if mask is None else mask[None, None],
                dropout_p=0.0,
                is_causal=False,
            )[0]
        pieces.append(attended.transpose(0, 1).reshape(stop - start, width))
    return F.linear(torch.cat(pieces), module.out_proj.weight, module.out_proj.bias)


def typed_allowed_rows(rows: list[LeafRow], device: torch.device) -> Callable[[int, int], Tensor]:
    """Exact original parent-group/shared-scalar edges plus the global anchor."""

    def ids(values: list[Any]) -> Tensor:
        index: dict[Any, int] = {}
        return torch.tensor([-1, *[index.setdefault(v, len(index)) for v in values]], device=device)

    groups = ids([path[:-1] for path, _ in rows])
    values = ids([value for _, value in rows])

    def allowed(start: int, stop: int) -> Tensor:
        mask = (groups[start:stop, None] == groups[None, :]) | (
            values[start:stop, None] == values[None, :]
        )
        mask[:, 0] = True
        if start == 0:
            mask[0, :] = True
        return mask

    return allowed


def encode_graph_rows(
    encoder: nn.TransformerEncoder, nodes: Tensor, rows: list[LeafRow], *, typed: bool
) -> Tensor:
    """Finish each full layer before advancing to the next graph layer."""
    mask = typed_allowed_rows(rows, nodes.device) if typed else None
    state = nodes
    for module in encoder.layers:
        layer = cast(nn.TransformerEncoderLayer, module)
        if layer.norm_first or any(
            dropout.p != 0 for dropout in (layer.dropout, layer.dropout1, layer.dropout2)
        ):
            raise ValueError("blocked execution requires the frozen encoder structure")
        attended = attend_query_rows(layer.self_attn, state, state, allowed_rows=mask)
        state = layer.norm1(state + layer.dropout1(attended))
        feedforward = layer.linear2(layer.dropout(layer.activation(layer.linear1(state))))
        state = layer.norm2(state + layer.dropout2(feedforward))
    if encoder.norm is not None:
        state = encoder.norm(state)
    return state[None]
