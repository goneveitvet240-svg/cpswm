"""Selected identity and commonsense adapters for Structure One."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from math import exp, sqrt
from typing import Protocol
from uuid import UUID

UNKNOWN_OBJECT = "unknown_object"


@dataclass(frozen=True, slots=True)
class IdentityObservation:
    observation_id: UUID
    observed_at: datetime
    payload: object
    source_record_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class IdentityCandidate:
    identity_id: str
    reference_embedding: tuple[float, ...]
    identity_prior: float
    transition_likelihood: float
    relation_likelihood: float
    valid_through: datetime
    evidence_record_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class IdentityPosterior:
    observation_id: UUID
    selected_identity_id: str
    identity_probabilities: Mapping[str, float]
    unknown_probability: float
    evidence_record_ids: tuple[UUID, ...]


class LearnedMetricEncoder(Protocol):
    @property
    def model_version(self) -> str: ...

    def encode(self, payload: object) -> Sequence[float]: ...


class PastOnlyIdentityCatalog(Protocol):
    def candidates_as_of(self, observation: IdentityObservation) -> Sequence[IdentityCandidate]: ...


@dataclass(frozen=True, slots=True)
class LearnedMetricBayesianConfig:
    visual_temperature: float = 0.15
    unknown_prior: float = 0.10
    minimum_binding_probability: float = 0.65

    def __post_init__(self) -> None:
        if self.visual_temperature <= 0.0:
            raise ValueError("visual_temperature must be positive")
        if not 0.0 < self.unknown_prior < 1.0:
            raise ValueError("unknown_prior must be in (0, 1)")
        if not 0.0 < self.minimum_binding_probability <= 1.0:
            raise ValueError("minimum_binding_probability must be in (0, 1]")


class LearnedMetricBayesianIdentityBackend:
    """Learned visual likelihood with Bayesian identity as authority."""

    def __init__(
        self,
        *,
        encoder: LearnedMetricEncoder,
        catalog: PastOnlyIdentityCatalog,
        config: LearnedMetricBayesianConfig | None = None,
    ) -> None:
        self._encoder = encoder
        self._catalog = catalog
        self._config = config or LearnedMetricBayesianConfig()

    def resolve(self, observation: object) -> IdentityPosterior:
        if not isinstance(observation, IdentityObservation):
            raise TypeError("identity backend requires IdentityObservation")
        embedding = tuple(float(value) for value in self._encoder.encode(observation.payload))
        if not embedding or _norm(embedding) == 0.0:
            raise ValueError("learned metric encoder returned an empty/zero embedding")

        scores: dict[str, float] = {}
        evidence_ids = list(observation.source_record_ids)
        for candidate in self._catalog.candidates_as_of(observation):
            if candidate.valid_through > observation.observed_at:
                raise ValueError("identity candidate contains future evidence")
            if len(candidate.reference_embedding) != len(embedding):
                raise ValueError("identity embedding dimensions do not match")
            factors = (
                candidate.identity_prior,
                candidate.transition_likelihood,
                candidate.relation_likelihood,
            )
            if any(value < 0.0 for value in factors):
                raise ValueError("Bayesian identity factors cannot be negative")
            cosine = _cosine(embedding, candidate.reference_embedding)
            visual_likelihood = exp((cosine - 1.0) / self._config.visual_temperature)
            scores[candidate.identity_id] = (
                max(candidate.identity_prior, 1e-12)
                * max(candidate.transition_likelihood, 1e-12)
                * max(candidate.relation_likelihood, 1e-12)
                * max(visual_likelihood, 1e-12)
            )
            evidence_ids.extend(candidate.evidence_record_ids)

        total = self._config.unknown_prior + sum(scores.values())
        probabilities = {key: value / total for key, value in scores.items()}
        unknown_probability = self._config.unknown_prior / total
        selected = UNKNOWN_OBJECT
        if probabilities:
            best_identity, best_probability = max(probabilities.items(), key=lambda item: item[1])
            if (
                best_probability >= self._config.minimum_binding_probability
                and best_probability > unknown_probability
            ):
                selected = best_identity
        return IdentityPosterior(
            observation_id=observation.observation_id,
            selected_identity_id=selected,
            identity_probabilities=probabilities,
            unknown_probability=unknown_probability,
            evidence_record_ids=tuple(dict.fromkeys(evidence_ids)),
        )


def _norm(values: Sequence[float]) -> float:
    return sqrt(sum(value * value for value in values))


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    denominator = _norm(left) * _norm(right)
    if denominator == 0.0:
        return 0.0
    return max(
        -1.0,
        min(1.0, sum(a * b for a, b in zip(left, right, strict=True)) / denominator),
    )


@dataclass(frozen=True, slots=True)
class CommonsenseClaim:
    predicate: str
    value: str
    confidence: float
    source_id: str
    source_kind: str
    source_record_ids: tuple[UUID, ...] = ()
    household_confirmed: bool = False

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("commonsense confidence must be in [0, 1]")


@dataclass(frozen=True, slots=True)
class FusedCommonsenseClaim:
    predicate: str
    value: str
    probability: float
    source_ids: tuple[str, ...]
    source_record_ids: tuple[UUID, ...]
    household_authoritative: bool


class CommonsenseSource(Protocol):
    @property
    def source_id(self) -> str: ...

    def claims_for(self, entity: object) -> Sequence[CommonsenseClaim]: ...


class ProvenanceWeightedCommonsenseProvider:
    """Fuse KG/VLM/LLM/visual claims without upgrading priors to observations."""

    def __init__(
        self,
        *,
        sources: Sequence[CommonsenseSource],
        source_weights: Mapping[str, float],
    ) -> None:
        if not sources:
            raise ValueError("at least one commonsense source is required")
        self._sources = tuple(sources)
        self._weights = dict(source_weights)
        for source in self._sources:
            if self._weights.get(source.source_id, 0.0) <= 0.0:
                raise ValueError(f"missing positive weight for {source.source_id}")

    def describe(self, entity: object) -> tuple[FusedCommonsenseClaim, ...]:
        by_predicate: dict[str, list[CommonsenseClaim]] = defaultdict(list)
        for source in self._sources:
            for claim in source.claims_for(entity):
                if claim.source_id != source.source_id:
                    raise ValueError("commonsense claim/source provenance mismatch")
                by_predicate[claim.predicate].append(claim)

        fused: list[FusedCommonsenseClaim] = []
        for predicate, claims in sorted(by_predicate.items()):
            household_claims = [claim for claim in claims if claim.household_confirmed]
            eligible = household_claims or claims
            value_scores: dict[str, float] = defaultdict(float)
            value_claims: dict[str, list[CommonsenseClaim]] = defaultdict(list)
            for claim in eligible:
                value_scores[claim.value] += self._weights[claim.source_id] * claim.confidence
                value_claims[claim.value].append(claim)
            normalizer = sum(value_scores.values()) or 1.0
            for value, score in sorted(value_scores.items()):
                supports = value_claims[value]
                fused.append(
                    FusedCommonsenseClaim(
                        predicate=predicate,
                        value=value,
                        probability=score / normalizer,
                        source_ids=tuple(dict.fromkeys(claim.source_id for claim in supports)),
                        source_record_ids=tuple(
                            dict.fromkeys(
                                record_id
                                for claim in supports
                                for record_id in claim.source_record_ids
                            )
                        ),
                        household_authoritative=bool(household_claims),
                    )
                )
        return tuple(fused)
