"""Auditable structured baseline for M17 habit learning.

This is deliberately a baseline, not the project's final method. It pools
common, household, person, and context pseudo-counts while enforcing the
learning firewall defined by :class:`HabitLearningEvidence`.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from math import isclose, isfinite
from uuid import UUID

from cpswm.contracts.habit_learning import (
    HabitLearningEvidence,
    ObservationOpportunityRecord,
)

from .propensity_correction import ObservationPropensityCorrector

CountKey = tuple[UUID, ...] | tuple[UUID, str, UUID] | tuple[UUID, str, UUID, str]


@dataclass(frozen=True, slots=True)
class HabitPrediction:
    """Normalized location probabilities and their supporting pseudo-counts."""

    probabilities: Mapping[UUID, float]
    pseudo_counts: Mapping[UUID, float]
    model_version: str
    component_probabilities: Mapping[str, Mapping[UUID, float]] = field(default_factory=dict)
    actor_residual: Mapping[UUID, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class HabitUpdateAudit:
    """One update's opportunity, actor-mixture, and applied-weight decomposition."""

    applied: bool
    base_training_weight: float
    propensity_weight: float
    effective_weight: float
    resident_mass: float
    isolated_nonresident_mass: float
    observation_opportunity_id: UUID | None = None
    raw_observation_propensity: float | None = None
    propensity_clipped: bool = False


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
        resident_actor_keys: Sequence[UUID | str] | None = None,
        actor_residual_weight: float | None = None,
        model_version: str = "hierarchical-dirichlet@0.1",
    ) -> None:
        unique_locations = tuple(dict.fromkeys(locations))
        if not unique_locations:
            raise ValueError("locations must contain at least one candidate")
        if (
            min(
                common_prior_strength,
                household_weight,
                person_weight,
                context_weight,
            )
            < 0.0
        ):
            raise ValueError("prior strength and pooling weights must be non-negative")
        if actor_residual_weight is not None and not 0.0 <= actor_residual_weight <= 1.0:
            raise ValueError("actor_residual_weight must lie in [0, 1]")

        self._locations = unique_locations
        self._common_prior = self._normalize_prior(common_prior)
        self._common_prior_strength = common_prior_strength
        self._household_weight = household_weight
        self._person_weight = person_weight
        self._context_weight = context_weight
        self._resident_actor_keys = (
            None
            if resident_actor_keys is None
            else frozenset(str(actor) for actor in resident_actor_keys)
        )
        if self._resident_actor_keys is not None and not self._resident_actor_keys:
            raise ValueError("resident_actor_keys cannot be empty when isolation is enabled")
        if self.UNKNOWN_ACTOR in (self._resident_actor_keys or ()):
            raise ValueError("unknown_actor cannot be declared as a resident")
        self._actor_residual_weight = actor_residual_weight
        self._model_version = model_version
        self._household_counts: dict[CountKey, dict[UUID, float]] = {}
        self._person_counts: dict[CountKey, dict[UUID, float]] = {}
        self._context_counts: dict[CountKey, dict[UUID, float]] = {}
        self._isolated_nonresident_counts: dict[CountKey, dict[UUID, float]] = {}

    def _normalize_prior(self, common_prior: Mapping[UUID, float] | None) -> dict[UUID, float]:
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

    def update(self, evidence: HabitLearningEvidence, *, weight_multiplier: float = 1.0) -> bool:
        """Apply one auditable soft-count update.

        Returns ``False`` when the learning firewall rejects a model prediction
        or a caller supplies an explicitly zero-weight record.

        ``weight_multiplier`` lets a caller correct for how likely this record
        was to be observed at all (see
        :mod:`cpswm.world_model.habits_transitions.propensity_correction`).
        It defaults to 1.0, so the audited baseline behaviour is unchanged, and
        it is applied *after* the learning firewall: no multiplier can revive a
        record the firewall has already zeroed.
        """

        return self.update_audited(
            evidence,
            weight_multiplier=weight_multiplier,
        ).applied

    def update_audited(
        self,
        evidence: HabitLearningEvidence,
        *,
        weight_multiplier: float = 1.0,
    ) -> HabitUpdateAudit:
        """Update counts while exposing every weight and contamination gate."""

        if not isfinite(weight_multiplier) or weight_multiplier < 0.0:
            raise ValueError("weight_multiplier must be finite and non-negative")
        base_weight = evidence.effective_training_weight
        if base_weight <= 0.0 or weight_multiplier <= 0.0:
            return HabitUpdateAudit(
                applied=False,
                base_training_weight=base_weight,
                propensity_weight=weight_multiplier,
                effective_weight=0.0,
                resident_mass=0.0,
                isolated_nonresident_mass=0.0,
                observation_opportunity_id=evidence.observation_opportunity_id,
            )
        weight = base_weight * weight_multiplier
        if evidence.location_id not in self._common_prior:
            raise ValueError("evidence location is outside the model candidate set")

        resident_mass = self._resident_mass(evidence.actor_posterior)
        resident_mass = min(1.0, max(0.0, resident_mass))
        isolated_mass = 0.0 if self._resident_actor_keys is None else max(0.0, 1.0 - resident_mass)
        household_weight = weight if self._resident_actor_keys is None else weight * resident_mass
        household_id = evidence.metadata.household_id
        object_id = evidence.object_instance_id
        if household_weight > 0.0:
            household_counts = self._household_counts.setdefault((household_id, object_id), {})
            household_counts[evidence.location_id] = (
                household_counts.get(evidence.location_id, 0.0) + household_weight
            )
        if isolated_mass > 0.0:
            isolated_counts = self._isolated_nonresident_counts.setdefault(
                (household_id, object_id), {}
            )
            isolated_counts[evidence.location_id] = (
                isolated_counts.get(evidence.location_id, 0.0) + weight * isolated_mass
            )

        for actor, probability in evidence.actor_posterior.items():
            if actor == self.UNKNOWN_ACTOR or probability <= 0.0:
                continue
            actor_weight = weight * probability
            person_counts = self._person_counts.setdefault((household_id, actor, object_id), {})
            person_counts[evidence.location_id] = (
                person_counts.get(evidence.location_id, 0.0) + actor_weight
            )
            context_counts = self._context_counts.setdefault(
                (household_id, actor, object_id, evidence.context_key), {}
            )
            context_counts[evidence.location_id] = (
                context_counts.get(evidence.location_id, 0.0) + actor_weight
            )
        return HabitUpdateAudit(
            applied=True,
            base_training_weight=base_weight,
            propensity_weight=weight_multiplier,
            effective_weight=weight,
            resident_mass=resident_mass,
            isolated_nonresident_mass=isolated_mass,
            observation_opportunity_id=evidence.observation_opportunity_id,
        )

    def update_from_opportunity(
        self,
        evidence: HabitLearningEvidence,
        opportunity: ObservationOpportunityRecord,
        corrector: ObservationPropensityCorrector,
    ) -> HabitUpdateAudit:
        """Bind one M17 update to the exact opportunity used for correction."""

        if evidence.observation_opportunity_id != opportunity.metadata.record_id:
            raise ValueError("habit evidence must cite the corrected observation opportunity")
        for field_name in ("household_id", "session_id", "trace_id"):
            if getattr(evidence.metadata, field_name) != getattr(opportunity.metadata, field_name):
                raise ValueError(
                    f"habit evidence {field_name} does not match observation opportunity"
                )
        if not opportunity.selected:
            raise ValueError("an unselected opportunity cannot produce a habit update")
        propensity = corrector.weight_for_opportunity(opportunity)
        audit = self.update_audited(
            evidence,
            weight_multiplier=propensity.applied_weight,
        )
        return HabitUpdateAudit(
            applied=audit.applied,
            base_training_weight=audit.base_training_weight,
            propensity_weight=audit.propensity_weight,
            effective_weight=audit.effective_weight,
            resident_mass=audit.resident_mass,
            isolated_nonresident_mass=audit.isolated_nonresident_mass,
            observation_opportunity_id=opportunity.metadata.record_id,
            raw_observation_propensity=propensity.raw_propensity,
            propensity_clipped=propensity.clipped,
        )

    def predict(
        self,
        *,
        household_id: UUID,
        person_id: UUID | str,
        object_instance_id: UUID,
        context_key: str,
    ) -> HabitPrediction:
        actor = str(person_id)
        household = self._household_counts.get((household_id, object_instance_id), {})
        person = self._person_counts.get((household_id, actor, object_instance_id), {})
        context = self._context_counts.get(
            (household_id, actor, object_instance_id, context_key), {}
        )

        scores: dict[UUID, float] = {}
        for location in self._locations:
            scores[location] = (
                self._common_prior_strength * self._common_prior[location]
                + self._household_weight * household.get(location, 0.0)
                + self._person_weight * person.get(location, 0.0)
                + self._context_weight * context.get(location, 0.0)
            )
        probabilities = self._normalize_scores(scores)
        component_probabilities: dict[str, Mapping[UUID, float]] = {}
        actor_residual: dict[UUID, float] = {}
        if self._actor_residual_weight is not None:
            household_scores = {
                location: (
                    self._common_prior_strength * self._common_prior[location]
                    + self._household_weight * household.get(location, 0.0)
                )
                for location in self._locations
            }
            household_probabilities = self._normalize_scores(household_scores)
            actor_scores = {
                location: (
                    self._common_prior_strength * self._common_prior[location]
                    + self._person_weight * person.get(location, 0.0)
                    + self._context_weight * context.get(location, 0.0)
                )
                for location in self._locations
            }
            actor_mass = sum(person.values()) + sum(context.values())
            if sum(actor_scores.values()) > 0.0:
                actor_probabilities = self._normalize_scores(actor_scores)
            else:
                actor_probabilities = household_probabilities
            shrinkage_denominator = actor_mass + self._common_prior_strength
            shrinkage = actor_mass / shrinkage_denominator if shrinkage_denominator > 0.0 else 0.0
            actor_residual = {
                location: shrinkage
                * (actor_probabilities[location] - household_probabilities[location])
                for location in self._locations
            }
            probabilities = {
                location: household_probabilities[location]
                + self._actor_residual_weight * actor_residual[location]
                for location in self._locations
            }
            probabilities = self._normalize_scores(probabilities)
            # F1 fix: pseudo_counts must reconstruct the *returned* probabilities.
            # In residual mode the output is a shrinkage mixture, so report
            # count-scaled mixture masses (proportional to probabilities), not
            # the household-only scores, which renormalise to a different vector.
            household_total = sum(household_scores.values())
            scores = {
                location: probabilities[location] * household_total for location in self._locations
            }
            component_probabilities = {
                "household": household_probabilities,
                "actor": actor_probabilities,
            }
        return HabitPrediction(
            probabilities=probabilities,
            pseudo_counts=scores,
            model_version=self._model_version,
            component_probabilities=component_probabilities,
            actor_residual=actor_residual,
        )

    def isolated_nonresident_count(
        self,
        *,
        household_id: UUID,
        object_instance_id: UUID,
        location_id: UUID,
    ) -> float:
        """Expose quarantined visitor/unknown mass without mixing it into residents."""

        return self._isolated_nonresident_counts.get((household_id, object_instance_id), {}).get(
            location_id, 0.0
        )

    def _resident_mass(self, actor_posterior: Mapping[str, float]) -> float:
        if self._resident_actor_keys is None:
            return 1.0
        return sum(
            probability
            for actor, probability in actor_posterior.items()
            if actor in self._resident_actor_keys
        )

    @staticmethod
    def _normalize_scores(scores: Mapping[UUID, float]) -> dict[UUID, float]:
        if any(not isfinite(score) or score < 0.0 for score in scores.values()):
            raise ValueError("habit scores must be finite and non-negative")
        total = sum(scores.values())
        if total <= 0.0:
            raise ValueError("at least one prior strength or learned count is required")
        return {location: score / total for location, score in scores.items()}

    def known_person_count(
        self,
        *,
        household_id: UUID,
        person_id: UUID | str,
        object_instance_id: UUID,
        location_id: UUID,
    ) -> float:
        """Expose one statistic for evaluation without leaking mutable state."""

        return self._person_counts.get((household_id, str(person_id), object_instance_id), {}).get(
            location_id, 0.0
        )

    def canonical_state_hash(self) -> str:
        """Deterministic hash of the full learned parameter state.

        Covers every non-zero household, person, context, and isolated
        non-resident count, so it changes if and only if a real parameter
        changes -- unlike a probe-grid hash, which only sees probed locations.
        Zero entries are excluded; accessors use ``dict.get`` and cannot create
        empty rows as a read side effect.
        """

        def table(counts: dict[CountKey, dict[UUID, float]]) -> list[list[object]]:
            rows: list[list[object]] = []
            for key, locations in counts.items():
                nonzero = {
                    str(location): repr(value)
                    for location, value in locations.items()
                    if value != 0.0
                }
                if nonzero:
                    rows.append([[str(part) for part in key], dict(sorted(nonzero.items()))])
            return sorted(rows, key=lambda row: json.dumps(row[0], sort_keys=True))

        payload = {
            "model_version": self._model_version,
            "household": table(self._household_counts),
            "person": table(self._person_counts),
            "context": table(self._context_counts),
            "isolated_nonresident": table(self._isolated_nonresident_counts),
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
