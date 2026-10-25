"""T2Mem-inspired differentiable fast memory, independently opt-in.

This bounded linear associative implementation is NOT the paper's complete VLA,
nonlinear multi-head architecture or adaptive step-size recipe. Slow parameters
learn through action supervision; fast state resets per episode, reads before
writes, and uses observation-only self-supervised updates. No torch import is
introduced into the default CPSWM runtime.
"""

from __future__ import annotations

import torch
from torch import nn


class ObservationFastMemory(nn.Module):
    def __init__(self, feature_dim: int, memory_dim: int = 16):
        super().__init__()
        if feature_dim < 1 or memory_dim < 1:
            raise ValueError("positive feature and memory dimensions required")
        self.feature_dim, self.memory_dim = feature_dim, memory_dim
        self.query = nn.Linear(feature_dim, memory_dim)
        self.key = nn.Linear(feature_dim, memory_dim)
        self.value = nn.Linear(feature_dim, memory_dim)
        self.initial = nn.Parameter(torch.zeros(memory_dim, memory_dim))
        self.log_step = nn.Parameter(torch.tensor(-1.0))
        self.gate = nn.Parameter(torch.full((memory_dim,), 0.1))

    def reset(self, batch_size: int):
        if batch_size < 1:
            raise ValueError("nonempty episode batch required")
        return self.initial.unsqueeze(0).expand(batch_size, -1, -1).clone()

    def forward(self, features, fast_state, *, write_mask=None):
        if features.ndim != 2 or features.shape[-1] != self.feature_dim:
            raise ValueError("expected observation-grounded [batch, features]")
        if fast_state.shape != (len(features), self.memory_dim, self.memory_dim):
            raise ValueError("invalid episode memory shape")
        if not torch.isfinite(features).all() or not torch.isfinite(fast_state).all():
            raise ValueError("non-finite observation or fast state")
        query = torch.tanh(self.query(features))
        key = torch.nn.functional.normalize(self.key(features), dim=-1)
        value = torch.tanh(self.value(features))
        # Read BEFORE write, so a current frame never masquerades as past memory.
        read = torch.bmm(query.unsqueeze(1), fast_state).squeeze(1)
        read = read * torch.tanh(self.gate)
        residual = torch.bmm(key.unsqueeze(1), fast_state).squeeze(1) - value
        # Exact gradient of per-episode 0.5 * sum((key @ W - value)^2).
        gradient = key.unsqueeze(2) * residual.unsqueeze(1)
        if write_mask is None:
            write_mask = torch.ones(len(features), dtype=torch.bool, device=features.device)
        if write_mask.shape != (len(features),) or write_mask.dtype is not torch.bool:
            raise ValueError("write mask must be a boolean per episode")
        # Bounded positive step; the paper's adaptive scaling is deliberately not
        # claimed here. Keeping this constant family makes this prototype auditable.
        next_state = (
            fast_state - torch.sigmoid(self.log_step) * gradient * write_mask[:, None, None]
        )
        return read, next_state


class AlternatingMemoryTrainer:
    """Freeze slow parameter groups; allow gradients THROUGH a frozen action head.

    The caller supplies observation features and expert action labels. During
    deployment only ObservationFastMemory is needed; no action labels enter writes.
    This trainer does not silently turn official inference-only pi05 into a trained
    memory-conditioned model.
    """

    def __init__(self, memory, action_head, *, learning_rate=1e-3):
        self.memory, self.action_head = memory, action_head
        self.optimizers = {
            "memory": torch.optim.Adam(memory.parameters(), lr=learning_rate),
            "policy": torch.optim.Adam(action_head.parameters(), lr=learning_rate),
        }

    def step(self, observations, targets, *, phase: str):
        if phase not in self.optimizers:
            raise ValueError("phase must be memory or policy")
        if observations.ndim != 3 or observations.shape[0] < 2:
            raise ValueError("time-major observation history required")
        for parameter in self.memory.parameters():
            parameter.requires_grad_(phase == "memory")
        for parameter in self.action_head.parameters():
            parameter.requires_grad_(phase == "policy")
        self.memory.zero_grad(set_to_none=True)
        self.action_head.zero_grad(set_to_none=True)
        state = self.memory.reset(observations.shape[1])
        for frame in observations:
            read, state = self.memory(frame, state)
        logits = self.action_head(torch.cat((observations[-1], read), dim=-1))
        loss = torch.nn.functional.cross_entropy(logits, targets)
        loss.backward()
        self.optimizers[phase].step()
        return float(loss.detach())
