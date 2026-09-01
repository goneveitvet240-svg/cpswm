"""DBN/factor-graph particle inference with CHEH-ORRER persistence."""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass
from math import exp, isfinite, log
from typing import Protocol
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class HiddenEventParticle:
    particle_id: UUID
    state: object
    log_weight: float
    parent_particle_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ParticleHiddenEventHypothesis:
    hypothesis_id: UUID
    state: object
    posterior_probability: float
    particle_id: UUID
    parent_particle_id: UUID | None
    source_record_ids: tuple[UUID, ...]


class DBNFactorGraphHiddenEventModel(Protocol):
    """Probability structure; it does not own persistence or revision."""

    def initial_state(self, observation: object, *, rng: random.Random) -> object: ...

    def transition(
        self, prior_state: object, observation: object, *, rng: random.Random
    ) -> object: ...

    def log_observation_likelihood(self, state: object, observation: object) -> float: ...

    def source_record_ids(self, observation: object) -> tuple[UUID, ...]: ...

    def partition_key(self, observation: object) -> tuple[str, str, str]: ...


class CHEHORRERRevisionManager(Protocol):
    """Persist a posterior candidate as a reversible CHEH-ORRER explanation."""

    def persist(self, hypothesis: ParticleHiddenEventHypothesis) -> object: ...


@dataclass(frozen=True, slots=True)
class ParticleFilterConfig:
    particle_count: int = 128
    resample_ess_fraction: float = 0.50
    persisted_hypothesis_count: int = 8
    random_seed: int = 0

    def __post_init__(self) -> None:
        if self.particle_count < 2:
            raise ValueError("particle_count must be at least 2")
        if not 0.0 < self.resample_ess_fraction <= 1.0:
            raise ValueError("resample_ess_fraction must be in (0, 1]")
        if not 1 <= self.persisted_hypothesis_count <= self.particle_count:
            raise ValueError("invalid persisted_hypothesis_count")


class DBNParticleCHEHHiddenEventBackend:
    """Selected 3D route with one authoritative posterior at the PF boundary."""

    def __init__(
        self,
        *,
        model: DBNFactorGraphHiddenEventModel,
        revision_manager: CHEHORRERRevisionManager,
        config: ParticleFilterConfig | None = None,
    ) -> None:
        self._model = model
        self._revision_manager = revision_manager
        self._config = config or ParticleFilterConfig()
        self._rng = random.Random(self._config.random_seed)
        self._particles_by_partition: dict[
            tuple[str, str, str], tuple[HiddenEventParticle, ...]
        ] = {}

    def particles_for(self, partition_key: tuple[str, str, str]) -> tuple[HiddenEventParticle, ...]:
        return self._particles_by_partition.get(partition_key, ())

    def infer(self, observation: object) -> tuple[object, ...]:
        partition_key = self._model.partition_key(observation)
        if len(partition_key) != 3 or any(not part for part in partition_key):
            raise ValueError("hidden-event partition must be (household, subject, object)")
        prior_particles = self._particles_by_partition.get(partition_key, ())
        proposed = self._propose(observation, prior_particles)
        normalized, probabilities = _normalize_particles(proposed)
        source_ids = self._model.source_record_ids(observation)
        ranked = sorted(
            zip(normalized, probabilities, strict=True), key=lambda item: item[1], reverse=True
        )[: self._config.persisted_hypothesis_count]
        persisted = tuple(
            self._revision_manager.persist(
                ParticleHiddenEventHypothesis(
                    hypothesis_id=uuid4(),
                    state=particle.state,
                    posterior_probability=probability,
                    particle_id=particle.particle_id,
                    parent_particle_id=particle.parent_particle_id,
                    source_record_ids=source_ids,
                )
            )
            for particle, probability in ranked
        )

        ess = 1.0 / sum(probability * probability for probability in probabilities)
        if ess < self._config.resample_ess_fraction * self._config.particle_count:
            self._particles_by_partition[partition_key] = self._systematic_resample(
                normalized, probabilities
            )
        else:
            self._particles_by_partition[partition_key] = tuple(
                HiddenEventParticle(
                    particle_id=particle.particle_id,
                    state=particle.state,
                    log_weight=log(max(probability, 1e-300)),
                    parent_particle_id=particle.parent_particle_id,
                )
                for particle, probability in zip(normalized, probabilities, strict=True)
            )
        return persisted

    def _propose(
        self,
        observation: object,
        prior_particles: Sequence[HiddenEventParticle],
    ) -> tuple[HiddenEventParticle, ...]:
        proposed: list[HiddenEventParticle] = []
        if not prior_particles:
            for _ in range(self._config.particle_count):
                state = self._model.initial_state(observation, rng=self._rng)
                likelihood = self._model.log_observation_likelihood(state, observation)
                _require_log_likelihood(likelihood)
                proposed.append(
                    HiddenEventParticle(particle_id=uuid4(), state=state, log_weight=likelihood)
                )
            return tuple(proposed)

        for prior in prior_particles:
            state = self._model.transition(prior.state, observation, rng=self._rng)
            likelihood = self._model.log_observation_likelihood(state, observation)
            _require_log_likelihood(likelihood)
            proposed.append(
                HiddenEventParticle(
                    particle_id=uuid4(),
                    state=state,
                    log_weight=prior.log_weight + likelihood,
                    parent_particle_id=prior.particle_id,
                )
            )
        return tuple(proposed)

    def _systematic_resample(
        self,
        particles: Sequence[HiddenEventParticle],
        probabilities: Sequence[float],
    ) -> tuple[HiddenEventParticle, ...]:
        count = self._config.particle_count
        start = self._rng.random() / count
        thresholds = [start + index / count for index in range(count)]
        cumulative = probabilities[0]
        source_index = 0
        output: list[HiddenEventParticle] = []
        uniform_log_weight = -log(count)
        for threshold in thresholds:
            while threshold > cumulative and source_index < len(probabilities) - 1:
                source_index += 1
                cumulative += probabilities[source_index]
            source = particles[source_index]
            output.append(
                HiddenEventParticle(
                    particle_id=uuid4(),
                    state=source.state,
                    log_weight=uniform_log_weight,
                    parent_particle_id=source.particle_id,
                )
            )
        return tuple(output)


class CHEHORREREngineAdapter:
    """Keep CHEH request construction explicit and separate from PF scoring."""

    def __init__(self, *, engine: object, branch_request_factory: object) -> None:
        if not callable(branch_request_factory):
            raise TypeError("branch_request_factory must be callable")
        self._engine = engine
        self._branch_request_factory = branch_request_factory

    def persist(self, hypothesis: ParticleHiddenEventHypothesis) -> object:
        request = self._branch_request_factory(hypothesis)
        branch = getattr(self._engine, "branch", None)
        if not callable(branch):
            raise TypeError("CHEH-ORRER engine must expose branch(request)")
        return branch(request)


def _require_log_likelihood(value: float) -> None:
    if not isfinite(value):
        raise ValueError("DBN/factor-graph likelihood must be finite")


def _normalize_particles(
    particles: Sequence[HiddenEventParticle],
) -> tuple[tuple[HiddenEventParticle, ...], tuple[float, ...]]:
    if not particles:
        raise ValueError("particle filter produced no particles")
    maximum = max(particle.log_weight for particle in particles)
    unnormalized = tuple(exp(particle.log_weight - maximum) for particle in particles)
    total = sum(unnormalized)
    if total <= 0.0:
        raise ValueError("particle posterior has zero mass")
    return tuple(particles), tuple(value / total for value in unnormalized)
