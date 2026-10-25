"""Opt-in task-conditioned memory readout and explicitly absent regime evidence.

No evaluator labels enter this module. The three analytic blocks and all native
operators remain active. This is a new decision rule, not a faithful reproduction
of LEDGER, MEMORA or T2Mem, nor a change to the historical default.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, fields
from typing import Any
from uuid import UUID

from cpswm.system.evaluation_operations.structure_two_current_event import (
    CurrentEventObservation,
    CurrentEventRuntime,
)
from cpswm.system.evaluation_operations.structure_two_selected_method import (
    ParticleRegimeDecision,
    StructureTwoOperator,
)
from cpswm.system.reproducibility import content_sha256


@dataclass(frozen=True, slots=True)
class MemoryActionObservation(CurrentEventObservation):
    regime_evidence_available: bool = True

    def __post_init__(self):
        CurrentEventObservation.__post_init__(self)
        if type(self.regime_evidence_available) is not bool:
            raise ValueError("regime evidence availability must be explicit boolean")


def projection_observation(observation):
    """Adapt the existing D0 missing-event producer's documented zero placeholder.

    Callers with actual zero evidence must use MemoryActionObservation(..., True).
    A later paid LOCATION replaces this same object and retains availability=False;
    a location alone does not magically supply regime evidence.
    """
    if isinstance(observation, MemoryActionObservation):
        return observation
    values = {f.name: getattr(observation, f.name) for f in fields(observation)}
    values.setdefault("prediction_only", observation.observed_location_id is None)
    return MemoryActionObservation(
        **values,
        regime_evidence_available=not (
            values["prediction_only"] and observation.regime_change_probability == 0.0
        ),
    )


class MemoryActionRuntime(CurrentEventRuntime):
    def __init__(self, *, owner_readout=True, missing_evidence=True, **kwargs):
        self.owner_readout = owner_readout
        self.missing_evidence = missing_evidence
        super().__init__(**kwargs)

    def revise(self, observation):
        # Conversion is owned by this explicit adapter, not inferred by the target.
        return super().revise(projection_observation(observation))

    def _candidates(self, observation, parent):
        mass = 1.0 if parent is None else parent.posterior_probability
        if not math.isfinite(mass) or mass < 0:
            raise ValueError("invalid parent mass")
        return tuple(
            (candidate, max(mass * q, 1e-280))
            for candidate, q in super()._candidates(observation, parent)
        )

    def _main_log_factor(self, observation, candidate):
        original = super()._main_log_factor(observation, candidate)
        if (
            not self.missing_evidence
            or getattr(observation, "regime_evidence_available", True)
            or StructureTwoOperator.CCRR in self.neutralized_operators
        ):
            return original
        probability = (
            observation.regime_change_probability
            if candidate.regime_decision
            in (ParticleRegimeDecision.CREATE, ParticleRegimeDecision.REACTIVATE)
            else 1.0 - observation.regime_change_probability
        )
        if candidate.regime_decision is ParticleRegimeDecision.UNRESOLVED:
            probability = max(observation.unresolved_probability, 1e-12)
        return original - math.log(max(probability, 1e-300))

    def action_distribution(self):
        if not self.owner_readout:
            return super().action_distribution()
        return owner_habit_readout(self)[0]


def owner_habit_readout(runtime, owner: str | None = None):
    """Marginalize current mover; query owner statistics within each latent regime.

    RB cells contain target-instance evidence admitted by the native writer. A
    visitor acting NOW cannot erase the owner's previously admitted statistics.
    All three RB blocks are consumed with a uniform, location-symmetric fallback
    within a cell. Missing cells/unresolved particle mass retain the existing base.
    No truth-based retired-regime selection, arbitrary confidence gain or new data.
    """
    observation = runtime._last_observation
    if observation is None:
        raise ValueError("native observation required")
    owner = observation.owner_actor_key if owner is None else owner
    if owner != observation.owner_actor_key:
        raise ValueError("owner must match this native target's declared query")
    locations = observation.known_location_ids
    base = observation.base_location_distribution
    uniform = dict.fromkeys(locations, 1.0 / len(locations))
    result = dict.fromkeys(locations, 0.0)
    consumed = 0.0
    components = []
    for particle in runtime.particles:
        world = particle.world
        cell = world.rb_cells.get((owner, world.active_regime))
        if cell is None or cell.observation_count == 0:
            continue
        distribution = cell.combined_location_distribution(locations, uniform)
        weight = particle.posterior_probability
        consumed += weight
        for location in locations:
            result[location] += weight * distribution[location]
        components.append(
            {
                "particle": str(world.typed_state.particle_id),
                "regime": world.active_regime,
                "cell_sha256": content_sha256(cell),
                "observations": cell.observation_count,
                "weight": weight,
                "distribution": {str(k): v for k, v in distribution.items()},
            }
        )
    if not 0 <= consumed <= 1 + 1e-6:
        raise ValueError("invalid posterior mass")
    fallback = max(0.0, 1.0 - consumed)
    for location in locations:
        result[location] += fallback * base[location]
    total = sum(result.values())
    result = {k: v / total for k, v in result.items()}
    receipt = {
        "schema": "owner-habit-readout-v1",
        "task": "PUT_BACK",
        "owner": owner,
        "state_sha256": runtime._state_sha256(),
        "source_update_id": str(observation.source_update_id),
        "ledger_head": runtime.rgrc_ledger.head_hash,
        "components": components,
        "consumed_mass": consumed,
        "fallback_mass": fallback,
        "base": {str(k): v for k, v in base.items()},
        "distribution": {str(k): v for k, v in result.items()},
    }
    receipt["sha256"] = content_sha256(receipt)
    return result, receipt


class NativeGoalMemory:
    """Read-only view of a LIVE native runtime for the existing goal controller.

    The binding is an explicit operator-supplied map, never inferred from truth.
    It must cover the whole native catalogue. No precomputed caller distribution
    or self-signed receipt is accepted as an alternative to recomputation.
    """

    def __init__(self, runtime, bindings: dict[UUID, str]):
        self.runtime = runtime
        self.bindings = dict(bindings)
        observation = runtime._last_observation
        if observation is None or set(bindings) != set(observation.known_location_ids):
            raise ValueError("complete native location binding required")
        if len(set(bindings.values())) != len(bindings) or any(
            not isinstance(v, str) or not v.strip() for v in bindings.values()
        ):
            raise ValueError("location binding must be one-to-one")

    @property
    def revision(self) -> str:
        return content_sha256(
            [self.runtime._state_sha256(), self.bindings, "owner-habit-readout-v1"]
        )

    def destination_distribution(self) -> dict[str, float]:
        distribution, _ = owner_habit_readout(self.runtime)
        if set(distribution) != set(self.bindings):
            raise ValueError("native catalogue changed; rebind explicitly")
        return {self.bindings[k]: v for k, v in distribution.items()}

    def audit(self) -> dict[str, Any]:
        _, receipt = owner_habit_readout(self.runtime)
        return {
            "memory_revision": self.revision,
            "readout": receipt,
            "bindings": {str(k): v for k, v in self.bindings.items()},
            "memory_source": "live_native_posterior",
            "scientific_acceptance": False,
        }
