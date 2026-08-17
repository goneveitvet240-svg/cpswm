"""Auditable structured baseline for M17 habit learning.

This is deliberately a baseline, not the project's final method. It pools
common, household, person, and context pseudo-counts while enforcing the
learning firewall defined by :class:`HabitLearningEvidence`.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isclose
from uuid import UUID

from cpswm.contracts.habit_learning import HabitLearningEvidence


CountKey = tuple[UUID, ...] | tuple[UUID, str, UUID] | tuple[UUID, str, UUID, str]


@dataclass(frozen=True, slots=True)
class HabitPrediction:
    """Normalized location probabilities and their supporting pseudo-counts."""

    probabilities: Mapping[UUID, float]
    pseudo_counts: Mapping[UUID, float]
    model_version: str


class HierarchicalDirichletHabitModel:
    """Four-level pseudo-count pooling baseline.

    The model is intentionally simple and interpretable. Direct or inferred
    evidence updates household counts. Known-person posterior mass also updates
    person and context counts. ``unknown_actor`` contributes only to the shared
    household distribution and cannot contaminate a known person's counts.
    """

    UNKNOWN_ACTOR = "unknown_actor"

    def __init__(
        self,
        *,
        locations: Sequence[UUID],
        common_prior: Mapping[UUID, float] | None = None,
        common_prior_strength: float = 1.0,
        household_weight: float = 1.0,
        person_weight: float = 1.0,
        context_weight: float = 1.0,
        model_version: str = "hierarchical-dirichlet@0.1",
    ) -> None:
        unique_locations = tuple(dict.fromkeys(locations))
        if not unique_locations:
            raise ValueError("locations must contain at least one candidate")
        if min(
            common_prior_strength,
            household_weight,
            person_weight,
            context_weight,
        ) < 0.0:
            raise ValueError("prior strength and pooling weights must be non-negative")

        self._locations = unique_locations
        self._common_prior = self._normalize_prior(common_prior)
        self._common_prior_strength = common_prior_strength
        self._household_weight = household_weight
        self._person_weight = person_weight
        self._context_weight = context_weight
        self._model_version = model_version
        self._household_counts: dict[CountKey, dict[UUID, float]] = defaultdict(
            lambda: defaultdict(float)
        )
        self._person_counts: dict[CountKey, dict[UUID, float]] = defaultdict(
            lambda: defaultdict(float)
        )
        self._context_counts: dict[CountKey, dict[UUID, float]] = defaultdict(
            lambda: defaultdict(float)
        )

    def _normalize_prior(
        self, common_prior: Mapping[UUID, float] | None
    ) -> dict[UUID, float]:
        if common_prior is None:
            uniform = 1.0 / len(self._locations)
            return {location: uniform for location in self._locations}
        if set(common_prior) != set(self._locations):
            raise ValueError("common_prior must define exactly the candidate locations")
        if any(value < 0.0 for value in common_prior.values()):
            raise ValueError("common_prior values must be non-negative")
        total = sum(common_prior.values())
        if total <= 0.0:
            raise ValueError("common_prior must have positive total mass")
        normalized = {location: value / total for location, value in common_prior.items()}
        if not isclose(sum(normalized.values()), 1.0, abs_tol=1e-9):
            raise ValueError("common_prior could not be normalized")
        return normalized

    @property
    def model_version(self) -> str:
        return self._model_version

    def update(self, evidence: HabitLearningEvidence) -> bool:
        """Apply one auditable soft-count update.

        Returns ``False`` when the learning firewall rejects a model prediction
        or a caller supplies an explicitly zero-weight record.
        """

        weight = evidence.effective_training_weight
        if weight <= 0.0:
            return False
        if evidence.location_id not in self._common_prior:
            raise ValueError("evidence location is outside the model candidate set")

        household_id = evidence.metadata.household_id
        object_id = evidence.object_instance_id
        self._household_counts[(household_id, object_id)][evidence.location_id] += weight

        for actor, probability in evidence.actor_posterior.items():
            if actor == self.UNKNOWN_ACTOR or probability <= 0.0:
                continue
            actor_weight = weight * probability
            self._person_counts[(household_id, actor, object_id)][
                evidence.location_id
            ] += actor_weight
            self._context_counts[
                (household_id, actor, object_id, evidence.context_key)
            ][evidence.location_id] += actor_weight
        return True

    def predict(
        self,
        *,
        household_id: UUID,
        person_id: UUID | str,
        object_instance_id: UUID,
        context_key: str,
    ) -> HabitPrediction:
        actor = str(person_id)
        household = self._household_counts[(household_id, object_instance_id)]
        person = self._person_counts[(household_id, actor, object_instance_id)]
        context = self._context_counts[
            (household_id, actor, object_instance_id, context_key)
        ]

        scores: dict[UUID, float] = {}
        for location in self._locations:
            scores[location] = (
                self._common_prior_strength * self._common_prior[location]
                + self._household_weight * household[location]
                + self._person_weight * person[location]
                + self._context_weight * context[location]
            )
        total = sum(scores.values())
        if total <= 0.0:
            raise ValueError("at least one prior strength or learned count is required")
        probabilities = {location: score / total for location, score in scores.items()}
        return HabitPrediction(
            probabilities=probabilities,
            pseudo_counts=scores,
            model_version=self._model_version,
        )

    def known_person_count(
        self,
        *,
        household_id: UUID,
        person_id: UUID | str,
        object_instance_id: UUID,
        location_id: UUID,
    ) -> float:
        """Expose one statistic for evaluation without leaking mutable state."""

        return self._person_counts[
            (household_id, str(person_id), object_instance_id)
        ][location_id]

