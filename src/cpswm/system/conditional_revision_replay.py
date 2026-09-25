"""Bound conditional measurement history and suffix recomputation.

This computes all three analytic blocks after a revision. It has no RGRC ledger
or particle-publication authority. A correction can change later measurements,
so the affected retained suffix is re-evaluated by the bound observation model;
subtracting a cached delta or keeping stale suffix statistics is not sufficient.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from cpswm.system.structure_two_conditional_updates import (
    ConditionalMeasurement,
    rebuild_conditional_state,
)
from cpswm.system.structure_two_particle_workspace import (
    ConditionalAnalyticState,
    native_content_sha256,
)


@dataclass(frozen=True)
class ConditionalReplayStep:
    particle_id: UUID
    parent_particle_id: UUID | None
    revision_id: UUID
    input_sha256: str
    measurement: ConditionalMeasurement


class BoundReplayModel(Protocol):
    binding_sha256: str

    def recompute(
        self, step: ConditionalReplayStep, retained_state: ConditionalAnalyticState
    ) -> ConditionalMeasurement: ...


@dataclass(frozen=True)
class ConditionalReplayResult:
    original_history_sha256: str
    particle_id: UUID
    removed_revisions: tuple[UUID, ...]
    retained_particles: tuple[UUID, ...]
    recomputed_particles: tuple[UUID, ...]
    measurements: tuple[ConditionalMeasurement, ...]
    state: ConditionalAnalyticState
    ledger_write_authority: bool = False
    native_publication_authority: bool = False


def _digest(value: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise ValueError("SHA256 model/input binding required")


@dataclass(frozen=True)
class ConditionalReplayHistory:
    prior: ConditionalAnalyticState
    model_binding_sha256: str
    observation_model_id: str
    steps: tuple[ConditionalReplayStep, ...] = ()

    @property
    def content_sha256(self) -> str:
        return native_content_sha256(self)

    def validate(self) -> None:
        _digest(self.model_binding_sha256)
        if not self.observation_model_id or self.prior.evidence_cluster_ids:
            raise ValueError("explicit empty-history prior and observation model required")
        rebuild_conditional_state(self.prior, ())
        seen: dict[UUID, ConditionalReplayStep] = {}
        for step in self.steps:
            _digest(step.input_sha256)
            if not all(isinstance(v, UUID) for v in (step.particle_id, step.revision_id)):
                raise ValueError("typed replay identities required")
            if step.particle_id in seen or (
                step.parent_particle_id is not None and step.parent_particle_id not in seen
            ):
                raise ValueError("duplicate, forward or cyclic conditional lineage")
            if step.measurement.observation_model_id != self.observation_model_id:
                raise ValueError("conditional history mixes observation models")
            seen[step.particle_id] = step
            lineage = self._lineage(step.particle_id, seen)
            # This also rejects duplicate clusters, malformed dimensions or noise.
            rebuild_conditional_state(self.prior, tuple(s.measurement for s in lineage))

    @staticmethod
    def _lineage(
        particle_id: UUID, records: dict[UUID, ConditionalReplayStep]
    ) -> tuple[ConditionalReplayStep, ...]:
        result = []
        current: UUID | None = particle_id
        visited = set()
        while current is not None:
            if current not in records or current in visited:
                raise ValueError("missing or cyclic conditional ancestry")
            visited.add(current)
            step = records[current]
            result.append(step)
            current = step.parent_particle_id
        return tuple(reversed(result))

    def append(self, supplied: ConditionalReplayStep) -> ConditionalReplayHistory:
        step = deepcopy(supplied)
        previous = next((s for s in self.steps if s.particle_id == step.particle_id), None)
        if previous is not None:
            if previous != step:
                raise ValueError("conditional particle identity reused")
            self.validate()
            return deepcopy(self)
        result = ConditionalReplayHistory(
            deepcopy(self.prior),
            self.model_binding_sha256,
            self.observation_model_id,
            (*deepcopy(self.steps), step),
        )
        result.validate()
        return result

    def replay(
        self,
        *,
        particle_id: UUID,
        revoked_revision_ids: frozenset[UUID],
        expected_history_sha256: str,
        model: BoundReplayModel | None,
    ) -> ConditionalReplayResult:
        self.validate()
        if self.content_sha256 != expected_history_sha256:
            raise ValueError("conditional history changed before replay")
        available = {s.revision_id for s in self.steps}
        if not revoked_revision_ids <= available:
            raise ValueError("correction cites a revision outside the conditional history")
        lineage = self._lineage(particle_id, {s.particle_id: s for s in self.steps})
        retained = []
        recomputed = []
        measurements = []
        state = deepcopy(self.prior)
        affected = False
        for step in lineage:
            if step.revision_id in revoked_revision_ids:
                affected = True
                continue
            if affected:
                if model is None or model.binding_sha256 != self.model_binding_sha256:
                    raise ValueError("affected suffix requires its bound observation replay model")
                detached = deepcopy(step)
                measurement = deepcopy(model.recompute(detached, deepcopy(state)))
                if (
                    model.binding_sha256 != self.model_binding_sha256
                    or measurement.evidence_cluster_id != step.measurement.evidence_cluster_id
                    or measurement.source_record_ids != step.measurement.source_record_ids
                    or measurement.observation_model_id != self.observation_model_id
                ):
                    raise ValueError("recomputed suffix changed source/model identity")
                recomputed.append(step.particle_id)
            else:
                measurement = deepcopy(step.measurement)
            measurements.append(measurement)
            # Rebuild, rather than subtracting a possibly cancelled precision matrix.
            state = rebuild_conditional_state(self.prior, tuple(measurements))
            retained.append(step.particle_id)
        if self.content_sha256 != expected_history_sha256:
            raise ValueError("conditional history mutated during replay")
        return ConditionalReplayResult(
            expected_history_sha256,
            particle_id,
            tuple(
                sorted(revoked_revision_ids.intersection(s.revision_id for s in lineage), key=str)
            ),
            tuple(retained),
            tuple(recomputed),
            tuple(measurements),
            state,
        )
