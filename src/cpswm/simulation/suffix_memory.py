"""Opt-in, source-equivalent checkpoint/suffix replay for controlled simulation.

This is an execution optimization of SimulationMemory's full-history model, not
new evidence, a new prior, or acceptance of production global revision semantics.
"""

from __future__ import annotations

import copy
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

from cpswm.simulation.contracts import Observation, Visibility
from cpswm.simulation.memory import SimulationMemory
from cpswm.system.evaluation_operations.structure_two_stateful_full_joint import (
    StatefulFullJointRuntime,
)
from cpswm.system.reproducibility import content_sha256


def runtime_digest(runtime: StatefulFullJointRuntime) -> str:
    """Hash full owned state, including RB values, journals and pending ledger state.

    The runtime's ordinary state SHA intentionally covers a narrower view. Use a
    separate versioned fingerprint here; never change legacy artifact identities.
    The model locator uses its basename for portability; full weights are bound.
    Unknown newly added non-serializable state fails closed until explicitly bound.
    """
    payload = dict(vars(runtime))
    payload["config"] = {
        **asdict(runtime.config),
        "neural_proposal_model_path": runtime.config.neural_proposal_model_path.name,
    }
    payload["rgrc_ledger"] = vars(runtime.rgrc_ledger)
    for name in ("_initial", "_current_before"):
        if payload.get(name) is not None:
            snapshot = dict(payload[name])
            snapshot["rgrc_ledger"] = vars(snapshot["rgrc_ledger"])
            payload[name] = snapshot
    return content_sha256({"schema": "simulation-runtime-checkpoint-v1", "state": payload})


@dataclass(frozen=True)
class _Checkpoint:
    count: int
    prefix_sha256: str
    context_sha256: str
    runtime_sha256: str
    runtime: StatefulFullJointRuntime


class SuffixReplayMemory(SimulationMemory):
    """Bounded-count private checkpoints; no persistence or borrowed caller state."""

    def __init__(
        self,
        episode_id: str,
        locations: Sequence[str],
        arm: str = "native_joint",
        root: Path | None = None,
        *,
        checkpoint_stride: int = 4,
        max_checkpoints: int = 8,
    ) -> None:
        if arm not in {"native_joint", "native_factorized"}:
            raise ValueError("suffix replay requires a native model")
        if any(type(v) is not int or v < 1 for v in (checkpoint_stride, max_checkpoints)):
            raise ValueError("checkpoint bounds must be positive integers")
        super().__init__(episode_id, locations, arm, root)
        self.checkpoint_stride = checkpoint_stride
        self.max_checkpoints = max_checkpoints
        self._cached_history: tuple[Observation, ...] = ()
        self._checkpoints: dict[int, _Checkpoint] = {}
        self._context_sha256: str | None = None
        self._last_replay_scores = 0
        self.replay_history: list[dict[str, Any]] = []

    def _context_digest(self) -> str:
        return content_sha256(
            {
                "arm": self.arm,
                "locations": self.locations,
                "location_ids": self.location_ids,
                "config": None
                if self._native_config is None
                else {
                    **asdict(self._native_config),
                    "neural_proposal_model_path": (
                        self._native_config.neural_proposal_model_path.name
                    ),
                },
                "episode_id": self.episode_id,
                "model": self._native_model,
                "bridge": "simulation-memory-adapter-v1",
            }
        )

    def _rebuild_native(self, ordered: Sequence[Observation]) -> StatefulFullJointRuntime:
        started = perf_counter()
        history = tuple(
            o for o in ordered if o.visibility == Visibility.OBSERVED and not o.robot_generated
        )
        fresh = self._new_native_runtime()
        context = self._context_digest()
        common = 0
        if context == self._context_sha256:
            for a, b in zip(history, self._cached_history, strict=False):
                if a != b:
                    break
                common += 1
        candidates = {n: c for n, c in self._checkpoints.items() if n <= common}
        prefix = max(candidates, default=0)
        checkpoint_seconds = 0.0
        if prefix:
            checkpoint = candidates[prefix]
            checkpoint_started = perf_counter()
            if (
                checkpoint.count != prefix
                or checkpoint.context_sha256 != context
                or checkpoint.prefix_sha256 != content_sha256(history[:prefix])
                or checkpoint.runtime_sha256 != runtime_digest(checkpoint.runtime)
            ):
                raise ValueError("checkpoint state, context or prefix binding changed")
            runtime = copy.deepcopy(checkpoint.runtime)
            runtime.verify_internal_contracts()
            checkpoint_seconds += perf_counter() - checkpoint_started
        else:
            runtime = fresh
            candidates = {}
        # Keep no mutable aliases to either the published runtime or the new cache.
        staged = {n: c for n, c in candidates.items() if n % self.checkpoint_stride == 0}
        for index in range(prefix, len(history)):
            self._append_native(runtime, history[: index + 1])
            count = index + 1
            if count % self.checkpoint_stride == 0:
                checkpoint_started = perf_counter()
                snapshot = copy.deepcopy(runtime)
                staged[count] = _Checkpoint(
                    count,
                    content_sha256(history[:count]),
                    context,
                    runtime_digest(snapshot),
                    snapshot,
                )
                checkpoint_seconds += perf_counter() - checkpoint_started
        runtime.verify_internal_contracts()
        count = len(history)
        if count and count not in staged:
            checkpoint_started = perf_counter()
            snapshot = copy.deepcopy(runtime)
            staged[count] = _Checkpoint(
                count, content_sha256(history), context, runtime_digest(snapshot), snapshot
            )
            checkpoint_seconds += perf_counter() - checkpoint_started
        staged = {n: staged[n] for n in sorted(staged)[-self.max_checkpoints :]}
        scores = sum(r.target_score_evaluations for r in runtime.fairness_receipts[prefix:])
        receipt = {
            "input_events": len(history),
            "unchanged_prefix": common,
            "checkpoint_prefix": prefix,
            "replayed_events": len(history) - prefix,
            "target_score_evaluations": scores,
            "full_rebuild_target_scores": sum(
                r.target_score_evaluations for r in runtime.fairness_receipts
            ),
            "checkpoint_count": len(staged),
            "checkpoint_seconds": checkpoint_seconds,
            "rebuild_seconds": perf_counter() - started,
            "context_sha256": context,
            "state_sha256": runtime._state_sha256(),
        }
        # Publish only after all inference, copying, fingerprinting and checks succeed.
        self._cached_history = history
        self._checkpoints = staged
        self._context_sha256 = context
        self._last_replay_scores = scores
        self.replay_history.append(receipt)
        return runtime

    def _rebuild_target_scores(self, runtime: StatefulFullJointRuntime) -> int:
        return self._last_replay_scores

    def audit(self) -> dict[str, Any]:
        return {
            **super().audit(),
            "replay_implementation": "checkpoint_suffix_v1",
            "checkpoint_stride": self.checkpoint_stride,
            "max_checkpoints": self.max_checkpoints,
            "checkpoint_count": len(self._checkpoints),
            "last_replay": None if not self.replay_history else dict(self.replay_history[-1]),
        }
