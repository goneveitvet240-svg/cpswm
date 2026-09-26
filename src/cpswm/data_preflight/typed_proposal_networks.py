"""Three development architecture arms over the same complete typed support.

All visible JSON leaves are encoded, including record order and numeric values.
Support must be supplied by a runtime provider; labels never construct it here.
The shared decoder supplies exact normalized nine-factor probabilities. These
implementations do not resolve the registered architecture/schedule protocols.
"""

from __future__ import annotations

import hashlib
import json
import marshal
from dataclasses import asdict, dataclass
from types import CodeType
from typing import Any, cast

import torch
from torch import Tensor, nn
from torch.nn.utils.rnn import pack_padded_sequence, pad_sequence

from cpswm.data_preflight import proposal_graph_compute as graph_compute
from cpswm.data_preflight.proposal_graph_compute import (
    BLOCKED_BACKEND,
    MAX_BLOCKED_NODES,
    attend_query_rows,
    encode_graph_rows,
    encode_leaf_batches,
    project_key_value,
)
from cpswm.data_preflight.proposal_learning import FACTOR_ORDER
from cpswm.data_preflight.proposal_samples import (
    ProposalContext,
    ProposalTarget,
    export_context,
    proposal_factor_values,
)
from cpswm.system.reproducibility import content_sha256

ARMS = (
    "typed_factor_graph_transformer",
    "slot_conditioned_perceiver",
    "autoregressive_typed_graph_policy",
)


@dataclass(frozen=True)
class NetworkConfig:
    hidden_width: int = 64
    layers: int = 2
    attention_heads: int = 4
    perceiver_latent_slots: int = 16
    max_nodes: int = 4096
    max_bytes_per_leaf: int = 4096
    execution_backend: str = "dense@1"

    def validate(self) -> None:
        if (self.hidden_width, self.layers, self.attention_heads, self.perceiver_latent_slots) != (
            64,
            2,
            4,
            16,
        ):
            raise ValueError("use the frozen local-development architecture dimensions")
        if any(type(n) is not int or n <= 0 for n in (self.max_nodes, self.max_bytes_per_leaf)):
            raise ValueError("positive integer resource limits required; no history truncation")
        if self.execution_backend not in {"dense@1", BLOCKED_BACKEND}:
            raise ValueError("unknown proposal execution backend")
        if self.execution_backend == BLOCKED_BACKEND and self.max_nodes > MAX_BLOCKED_NODES:
            raise ValueError("blocked execution exceeds its bounded local node budget")


def leaves(value: Any, path: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], str]]:
    if isinstance(value, dict) and value:
        return [item for key in sorted(value) for item in leaves(value[key], (*path, str(key)))]
    if isinstance(value, (list, tuple)) and value:
        return [item for i, v in enumerate(value) for item in leaves(v, (*path, str(i)))]
    return [(path, json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":")))]


def parameter_fingerprint(network: TypedProposalNetwork) -> str:
    """Bind actual parameter/buffer bytes, including writes outside _version."""
    structure = architecture_fingerprint(network)
    if structure != network._architecture_sha256:
        raise ValueError("model architecture structure binding changed")
    digest = hashlib.sha256()
    digest.update(structure.encode())
    digest.update(
        json.dumps({"arm": network.arm, "config": asdict(network.config)}, sort_keys=True).encode()
    )
    for name, value in network.state_dict().items():
        digest.update(
            json.dumps([name, str(value.dtype), list(value.shape), str(value.device)]).encode()
        )
        digest.update(value.detach().contiguous().view(torch.uint8).cpu().numpy().tobytes())
    return digest.hexdigest()


def architecture_fingerprint(network: nn.Module) -> str:
    """Bind the concrete module graph, non-tensor settings and loaded methods.

    This detects owned-model drift, not hostile replacement of the interpreter
    or its externally trusted roots. Runtime hooks are outside this contract.
    """

    def normalized(code: CodeType) -> CodeType:
        return code.replace(
            co_filename="",
            co_consts=tuple(
                normalized(v) if isinstance(v, CodeType) else v for v in code.co_consts
            ),
        )

    def callable_identity(value: Any) -> dict[str, str]:
        code = getattr(value, "__code__", None)
        return {
            "module": getattr(value, "__module__", type(value).__module__),
            "name": getattr(value, "__qualname__", type(value).__qualname__),
            "code": "native"
            if code is None
            else hashlib.sha256(marshal.dumps(normalized(code))).hexdigest(),
        }

    settings = (
        "eps",
        "normalized_shape",
        "num_heads",
        "head_dim",
        "embed_dim",
        "kdim",
        "vdim",
        "_qkv_same_embed_dim",
        "dropout",
        "batch_first",
        "norm_first",
        "activation_relu_or_gelu",
        "p",
        "inplace",
        "input_size",
        "hidden_size",
        "num_layers",
        "bias",
        "bidirectional",
        "proj_size",
        "num_embeddings",
        "embedding_dim",
        "padding_idx",
        "max_norm",
        "norm_type",
        "scale_grad_by_freq",
        "sparse",
        "in_features",
        "out_features",
        "approximate",
        "add_zero_attn",
        "enable_nested_tensor",
        "use_nested_tensor",
        "mask_check",
    )
    rows = []
    for name, module in network.named_modules():
        if any(
            bool(getattr(module, field, None))
            for field in (
                "_forward_hooks",
                "_forward_pre_hooks",
                "_backward_hooks",
                "_backward_pre_hooks",
            )
        ):
            raise ValueError("model architecture structure cannot include runtime hooks")
        attributes = {}
        for field in settings:
            value = getattr(module, field, None)
            if value is None or type(value) in (str, int, float, bool, tuple):
                attributes[field] = value
        activation = getattr(module, "activation", None)
        rows.append(
            {
                "path": name,
                "class": f"{type(module).__module__}.{type(module).__qualname__}",
                "settings": attributes,
                "forward": callable_identity(module.forward),
                "activation": callable_identity(activation) if callable(activation) else None,
            }
        )
    # Source-file hashes alone do not detect a loaded helper's __code__ being
    # replaced after construction. Bind both its module and the imported aliases
    # actually used by this network, as well as the owned scoring entry points.
    helper_names = (
        "query_block_size",
        "encode_leaf_batches",
        "_checked_attention",
        "project_key_value",
        "attend_query_rows",
        "typed_allowed_rows",
        "encode_graph_rows",
    )
    return content_sha256(
        {
            "modules": rows,
            "graph_helpers": {
                name: callable_identity(getattr(graph_compute, name, None)) for name in helper_names
            },
            "imported_helpers": [
                callable_identity(value)
                for value in (
                    leaves,
                    attend_query_rows,
                    encode_graph_rows,
                    encode_leaf_batches,
                    project_key_value,
                )
            ],
            "owned_classes": {
                cls.__name__: {
                    name: callable_identity(value)
                    for name, value in vars(cls).items()
                    if callable(value)
                }
                for cls in (TypedProposalNetwork, PreparedScorer)
            },
            "workspace_limits": {
                name: getattr(graph_compute, name, None)
                for name in (
                    "LEAF_BATCH",
                    "QUERY_BATCH",
                    "DEFAULT_BLOCKED_NODES",
                    "MAX_BLOCKED_NODES",
                    "ATTENTION_TEMPORARY_BYTES",
                )
            },
        }
    )


class TypedProposalNetwork(nn.Module):
    def __init__(self, arm: str, config: NetworkConfig | None = None) -> None:
        super().__init__()
        config = config or NetworkConfig()
        config.validate()
        if arm not in ARMS:
            raise ValueError("unknown architecture arm")
        self.arm, self.config = arm, config
        w, h = config.hidden_width, config.attention_heads
        # Byte encoding avoids a training-label vocabulary or opaque hash buckets.
        self.byte_embedding = nn.Embedding(257, w, padding_idx=256)
        self.leaf_encoder = nn.GRU(w, w, batch_first=True)
        self.axis_embedding = nn.Embedding(len(FACTOR_ORDER), w)
        self.anchor = nn.Parameter(torch.zeros(1, w))
        self.encoder = nn.TransformerEncoder(
            nn.TransformerEncoderLayer(w, h, 4 * w, dropout=0, batch_first=True),
            config.layers,
            enable_nested_tensor=False,
        )
        if arm == "slot_conditioned_perceiver":
            self.latents = nn.Parameter(torch.randn(config.perceiver_latent_slots, w) / w**0.5)
            self.cross_layers = nn.ModuleList(
                [
                    nn.MultiheadAttention(w, h, dropout=0, batch_first=True)
                    for _ in range(config.layers)
                ]
            )
            self.cross_norms = nn.ModuleList([nn.LayerNorm(w) for _ in range(config.layers)])
        if arm == "autoregressive_typed_graph_policy":
            self.prefix_encoder = nn.GRU(w, w, num_layers=config.layers, batch_first=True)
        self.choice_attention = nn.MultiheadAttention(w, h, dropout=0, batch_first=True)
        self.head = nn.Sequential(nn.Linear(3 * w, w), nn.GELU(), nn.Linear(w, 1))
        self._architecture_sha256 = architecture_fingerprint(self)

    def prepare(
        self, context: ProposalContext, candidates: tuple[ProposalTarget, ...]
    ) -> PreparedScorer:
        blocked = self.config.execution_backend == BLOCKED_BACKEND
        if blocked and (
            torch.is_grad_enabled()
            or any(m.training for m in self.modules())
            or self.anchor.device.type != "cpu"
            or self.anchor.dtype != torch.float32
        ):
            raise ValueError("blocked backend is CPU float32 evaluation only, without gradients")
        if type(context) is not ProposalContext:
            raise ValueError("network input cannot contain a supervision envelope")
        context = ProposalContext.model_validate(context.model_dump())
        candidates = tuple(ProposalTarget.model_validate(c.model_dump()) for c in candidates)
        context.validate_candidates(candidates)
        # Runtime support is a set. Its caller's enumeration must not change q.
        candidates = tuple(
            sorted(candidates, key=lambda c: content_sha256(c.model_dump(mode="json")))
        )
        parameter_sha256 = parameter_fingerprint(self)
        payload = export_context(context)
        rows = leaves(payload, ("context",))
        ranges = []
        for i, candidate in enumerate(candidates):
            start = len(rows) + 1
            rows.extend(leaves(candidate.model_dump(mode="json"), ("candidate", str(i))))
            ranges.append((start, len(rows) + 1))
        if len(rows) + 1 > self.config.max_nodes:
            raise ValueError(
                "resource limit: full history/support exceeds node budget; no truncation"
            )
        encoded = [
            json.dumps([list(path), value], separators=(",", ":")).encode() for path, value in rows
        ]
        if any(len(b) > self.config.max_bytes_per_leaf for b in encoded):
            raise ValueError("resource limit: full leaf exceeds byte budget; no truncation")
        device = self.anchor.device
        if blocked:
            leaf_vectors = encode_leaf_batches(self, encoded)
        else:
            sequences = [torch.tensor(list(b), dtype=torch.long, device=device) for b in encoded]
            padded = pad_sequence(sequences, batch_first=True, padding_value=256)
            packed = pack_padded_sequence(
                self.byte_embedding(padded),
                [len(s) for s in sequences],
                batch_first=True,
                enforce_sorted=False,
            )
            _, hidden = self.leaf_encoder(packed)
            leaf_vectors = hidden[-1]
        nodes = torch.cat([self.anchor, leaf_vectors], dim=0)
        raw_candidates = torch.stack([nodes[a:b].mean(0) for a, b in ranges])
        if self.arm == "typed_factor_graph_transformer":
            if blocked:
                memory = encode_graph_rows(self.encoder, nodes, rows, typed=True)
            else:
                # Local typed records and shared scalar identities form edges; anchor
                # connects records so multi-hop evidence is retained across layers.
                groups = [path[:-1] for path, _ in rows]
                values = [value for _, value in rows]
                mask = torch.ones((len(nodes), len(nodes)), dtype=torch.bool, device=device)
                mask[0, :] = False
                mask[:, 0] = False
                for membership in (groups, values):
                    indexed: dict[Any, list[int]] = {}
                    for i, key in enumerate(membership):
                        indexed.setdefault(key, []).append(i + 1)
                    for members in indexed.values():
                        indices = torch.tensor(members, dtype=torch.long, device=device)
                        mask[indices[:, None], indices[None, :]] = False
                memory = self.encoder(nodes[None], mask=mask)
            candidate_vectors = torch.stack([memory[0, a:b].mean(0) for a, b in ranges])
        elif self.arm == "slot_conditioned_perceiver":
            memory = self.latents[None]
            for cross, norm in zip(self.cross_layers, self.cross_norms, strict=True):
                update, _ = cross(memory, nodes[None], nodes[None], need_weights=False)
                memory = norm(memory + update)
            memory = self.encoder(memory)
            candidate_vectors = raw_candidates
        else:
            memory = (
                encode_graph_rows(self.encoder, nodes, rows, typed=False)
                if blocked
                else self.encoder(nodes[None])
            )
            candidate_vectors = torch.stack([memory[0, a:b].mean(0) for a, b in ranges])
        if parameter_fingerprint(self) != parameter_sha256:
            raise ValueError("model parameters changed during graph preparation")
        return PreparedScorer(
            self, payload, candidates, memory, candidate_vectors, len(rows) + 1, parameter_sha256
        )


class PreparedScorer:
    """One graph evaluation, valid for one input and optimizer parameter version."""

    def __init__(
        self,
        network: TypedProposalNetwork,
        context: dict[str, Any],
        candidates: tuple[ProposalTarget, ...],
        memory: Tensor,
        vectors: Tensor,
        nodes: int,
        parameter_sha256: str,
    ) -> None:
        self.network, self.context_hash = network, content_sha256(context)
        self.factors = tuple(proposal_factor_values(t) for t in candidates)
        self.candidate_hashes = frozenset(
            content_sha256(t.model_dump(mode="json")) for t in candidates
        )
        self.memory, self.vectors, self.node_count = memory, vectors, nodes
        self.parameter_versions = tuple(p._version for p in network.parameters())
        self.parameter_sha256 = parameter_sha256
        self.choice_key_value = (
            project_key_value(network.choice_attention, memory[0])
            if network.config.execution_backend == BLOCKED_BACKEND
            else None
        )
        self.graph_sha256 = self._graph_fingerprint() if self.choice_key_value is not None else None

    def _graph_fingerprint(self) -> str:
        """The eval cache is owned computed state, including raw-data mutations."""
        if not isinstance(self.choice_key_value, tuple) or len(self.choice_key_value) != 2:
            raise ValueError("prepared graph cache schema changed")
        digest = hashlib.sha256()
        digest.update(
            json.dumps(
                [self.context_hash, sorted(self.candidate_hashes), self.factors, self.node_count],
                sort_keys=True,
                allow_nan=False,
            ).encode()
        )
        for value in (self.memory, self.vectors, *self.choice_key_value):
            if not isinstance(value, Tensor):
                raise ValueError("prepared graph cache tensor changed")
            digest.update(
                json.dumps([str(value.dtype), str(value.device), list(value.shape)]).encode()
            )
            digest.update(value.detach().contiguous().view(torch.uint8).cpu().numpy().tobytes())
        return digest.hexdigest()

    def __call__(
        self,
        context: dict[str, object],
        axis: str,
        prefix: tuple[str, ...],
        choices: tuple[str, ...],
        *,
        runtime_candidates: tuple[ProposalTarget, ...],
    ) -> Tensor:
        if (
            content_sha256(context) != self.context_hash
            or tuple(p._version for p in self.network.parameters()) != self.parameter_versions
            or parameter_fingerprint(self.network) != self.parameter_sha256
            or frozenset(content_sha256(t.model_dump(mode="json")) for t in runtime_candidates)
            != self.candidate_hashes
        ):
            raise ValueError("prepared network belongs to another input/support/optimizer state")
        if self.network.config.execution_backend == BLOCKED_BACKEND and (
            torch.is_grad_enabled() or any(m.training for m in self.network.modules())
        ):
            raise ValueError("blocked scorer is evaluation only, without gradients")
        if self.graph_sha256 is not None and self._graph_fingerprint() != self.graph_sha256:
            raise ValueError("prepared graph cache changed after complete encoding")
        depth = len(prefix)
        if depth >= len(FACTOR_ORDER) or axis != FACTOR_ORDER[depth]:
            raise ValueError("invalid typed autoregressive prefix")
        compatible = [i for i, row in enumerate(self.factors) if row[:depth] == prefix]
        expected = {self.factors[i][depth] for i in compatible}
        if not compatible or set(choices) != expected or len(choices) != len(expected):
            raise ValueError("conditional choice support is incomplete")
        queries = torch.stack(
            [
                self.vectors[[i for i in compatible if self.factors[i][depth] == c]].mean(0)
                for c in choices
            ]
        )
        axes = self.network.axis_embedding.weight
        if depth:
            prefix_vectors = torch.stack(
                [
                    self.vectors[
                        [i for i, row in enumerate(self.factors) if row[: j + 1] == prefix[: j + 1]]
                    ].mean(0)
                    + axes[j]
                    for j in range(depth)
                ]
            )
            if self.network.arm == "autoregressive_typed_graph_policy":
                _, h = self.network.prefix_encoder(prefix_vectors[None])
                conditioned = h[-1, 0]
            else:
                conditioned = prefix_vectors.mean(0)
        else:
            conditioned = torch.zeros_like(queries[0])
        queries = queries + axes[depth] + conditioned
        if self.network.config.execution_backend == BLOCKED_BACKEND:
            attended = attend_query_rows(
                self.network.choice_attention,
                queries,
                self.memory[0],
                projected_kv=self.choice_key_value,
            )
        else:
            batched, _ = self.network.choice_attention(
                queries[None], self.memory, self.memory, need_weights=False
            )
            attended = batched[0]
        scores = self.network.head(
            torch.cat([queries, attended, conditioned.expand(len(choices), -1)], dim=-1)
        ).squeeze(-1)
        if parameter_fingerprint(self.network) != self.parameter_sha256:
            raise ValueError("model parameters changed during conditional scoring")
        if self.graph_sha256 is not None and self._graph_fingerprint() != self.graph_sha256:
            raise ValueError("prepared graph cache changed during conditional scoring")
        return cast(Tensor, scores)
