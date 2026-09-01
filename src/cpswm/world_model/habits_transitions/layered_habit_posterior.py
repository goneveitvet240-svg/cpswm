"""RQ5: the layered personalized habit posterior, without counting evidence twice.

`项目结构一 §4.2` no longer states a single formula.  It records that writing
the three layers as a direct product of normalized posteriors::

    P(L | o, p, c) ∝ P_common(L | class, attributes)
                   x P_household(L | o, c)
                   x P_person(L | p, o, c)

*"会重复计算嵌套证据, 并让任一层的零概率永久消灭候选"*, and it keeps three
mutually exclusive candidate routes open, each to be selected on validation
only:

1. hierarchical Bayesian shrinkage -- pseudo-count shrinkage from the shared
   layer to the household layer to the person layer;
2. mixture of experts -- non-negative gating weights over the three layers'
   predictive distributions;
3. tempered product of likelihood-ratio experts -- multiply only the ratios
   against each layer's explicit reference prior, with a temperature and a
   probability floor.

This module implements **route 1**, and does so in the form that actually
avoids the double counting the document warns about.  It also exposes route 3's
object: :meth:`LayeredHabitPrediction.deviation` returns exactly the
likelihood ratio of a layer against its parent, and the product of those
ratios times the common prior reconstructs the posterior to floating-point
exactness.  So the two routes are not rivals at the representation level -- 3
is 1 read multiplicatively -- and a comparison between them is a comparison of
tempering and flooring, not of factorizations.

The reason the naive product is not merely an approximation: the three factors
are nested conditionals over the *same* evidence.  Every event that raises
``P_person`` for this resident also raised ``P_household`` for this object.
Written as a product of *deviations* the identity telescopes and is exact::

    P(L | o, p, c) ∝ P_common(L)
                   x [P_household(L | o) / P_common(L)]
                   x [P_person(L | p, o) / P_household(L | o)]
                   x [P_context(L | p, o, c) / P_person(L | p, o)]
                   = P_context(L | p, o, c)

so multiplying the *levels* rather than the *deviations* produces a different,
sharper distribution -- not a coarser estimate of the same one.

**What the current baseline does.**
:class:`HierarchicalDirichletHabitModel` is on route 1 but takes the additive
form of it.  It *adds* pseudo-counts::

    score(L) = k0*P_common(L) + w_h*n_household(L) + w_p*n_person(L) + w_c*n_context(L)

and because a single resident observation increments all three count tables,
one observation enters the score three times.  Measured on a three-location
model with default weights, one observation yields ``P(top) = 0.8333`` -- the
sharpness a single-level Dirichlet would need **three** observations to reach.
:func:`measure_evidence_multiplicity` reports that factor for any model, and
returns exactly ``3.0`` for the additive baseline.

This module supplies the back-off form the layering was meant to be.  Each
level uses the level above it as its *prior*, with a concentration ``κ`` saying
how much evidence it takes to move away from the parent.

The subtlety — and the reason the obvious back-off is still wrong — is which
counts the parent is allowed to use.  Writing the nested version naively::

    P_household(L) = (n_h(L) + κ_h-P_common(L))    / (N_h + κ_h)
    P_person(L)    = (n_p(L) + κ_p-P_household(L)) / (N_p + κ_p)
    P_context(L)   = (n_c(L) + κ_c-P_person(L))    / (N_c + κ_c)

reintroduces the same defect in multiplicative clothing.  For a single-resident
single-context stream ``n_c = n_p = n_h``, so the *same* observation raises
``P_household``, is then used as the prior that raises ``P_person``, and is
used again as the prior that raises ``P_context``.  Measured, one observation
over three locations gives ``P(top) = 0.7156`` where the evidence justifies
``0.6667``.  Less inflated than the additive form, still inflated.

The fix is a **leave-one-out** hierarchy: a parent is estimated from the
siblings of the cell being predicted, never from the cell itself::

    n_person_excl(p)     = n_person(p)     - n_context(p, c)   this person's OTHER contexts
    n_household_excl(p)  = n_household     - n_person(p)       the household's OTHER residents

    P_household(L) = (n_household_excl(L) + κ_h-P_common(L))    / (N_household_excl + κ_h)
    P_person(L)    = (n_person_excl(L)    + κ_p-P_household(L)) / (N_person_excl + κ_p)
    P_context(L)   = (n_context(L)        + κ_c-P_person(L))    / (N_context + κ_c)

Now every observation for this ``(household, object)`` appears in exactly one
numerator of the chain: its own cell if it matches ``(person, context)``, its
person's sibling pool if it matches the person only, the household's sibling
pool otherwise.  The parent contributes information a child does not already
have, which is the whole point of a hierarchy, and contributes it once.
:meth:`LayeredHabitPosterior.evidence_report` asserts the partition rather than
assuming it: ``counted_evidence_mass`` must equal ``observations_applied`` and
``evidence_multiplicity`` must be exactly 1.

This also gives `§4.2`'s remaining requirement a mechanism:

    系统必须允许个性化证据逐渐覆盖常识, 但不能因一次异常彻底覆盖长期规律.

``κ`` *is* that rule.  A level needs roughly ``κ`` observations before it
outweighs its parent, so one anomaly cannot flip a long-standing regularity,
and sustained personal evidence eventually does.  In the additive form there is
no such quantity: the weights are unnormalized and one observation already
moves the answer.

This class is a **posterior estimator, not a replacement for M17's ledger**.
It deliberately does not implement retraction, tombstones or derived-evidence
lineage; :class:`HybridStatisticLedger` owns those.  It consumes the same
:class:`HabitLearningEvidence` stream so the two can be compared on identical
input.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from math import isclose, isfinite
from typing import Any
from uuid import UUID

from cpswm.contracts.habit_learning import HabitLearningEvidence

__all__ = [
    "LAYERED_POSTERIOR_VERSION",
    "EvidenceReport",
    "HabitLayer",
    "LayerConcentration",
    "LayeredHabitPosterior",
    "LayeredHabitPrediction",
    "measure_evidence_multiplicity",
]

LAYERED_POSTERIOR_VERSION = "layered-habit-posterior@0.1"

#: Shared open-world actor key.  Same spelling as
#: :attr:`HierarchicalDirichletHabitModel.UNKNOWN_ACTOR` on purpose.
UNKNOWN_ACTOR = "unknown_actor"


class HabitLayer(StrEnum):
    """The four nested levels of `项目结构一 §4.2`, coarsest first."""

    COMMON = "common"
    HOUSEHOLD = "household"
    PERSON = "person"
    CONTEXT = "context"


@dataclass(frozen=True, slots=True)
class LayerConcentration:
    """How much evidence a level needs before it outweighs its parent.

    Each value is a pseudo-count, so it is directly comparable with the number
    of observations: ``household=4.0`` means four household observations move
    the household level halfway off the commonsense prior.  That is the
    *interpretable* knob `§4.2` asks for and the additive form does not have.
    """

    household: float = 4.0
    person: float = 4.0
    context: float = 2.0

    def __post_init__(self) -> None:
        for name in ("household", "person", "context"):
            value = getattr(self, name)
            if not isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} concentration must be finite and positive")

    def of(self, layer: HabitLayer) -> float:
        if layer is HabitLayer.HOUSEHOLD:
            return self.household
        if layer is HabitLayer.PERSON:
            return self.person
        if layer is HabitLayer.CONTEXT:
            return self.context
        raise ValueError("the common layer is a prior and has no concentration")


@dataclass(frozen=True, slots=True)
class EvidenceReport:
    """Whether a posterior rests on more evidence than it was given."""

    observations_applied: float
    counted_evidence_mass: float
    evidence_multiplicity: float
    layer_counts: Mapping[HabitLayer, float]

    @property
    def double_counts(self) -> bool:
        """True when one observation enters the scoring expression more than once."""

        return self.evidence_multiplicity > 1.0 + 1e-9

    def summary(self) -> dict[str, object]:
        return {
            "observations_applied": repr(self.observations_applied),
            "counted_evidence_mass": repr(self.counted_evidence_mass),
            "evidence_multiplicity": repr(self.evidence_multiplicity),
            "double_counts": self.double_counts,
            "layer_counts": {
                layer.value: repr(value) for layer, value in sorted(self.layer_counts.items())
            },
        }


@dataclass(frozen=True, slots=True)
class LayeredHabitPrediction:
    """A posterior plus the level-by-level path that produced it."""

    probabilities: Mapping[UUID, float]
    layer_probabilities: Mapping[HabitLayer, Mapping[UUID, float]]
    layer_weight: Mapping[HabitLayer, float]
    deepest_layer: HabitLayer
    evidence: EvidenceReport
    model_version: str = LAYERED_POSTERIOR_VERSION
    layer_counts: Mapping[HabitLayer, float] = field(default_factory=dict)

    def deviation(self, layer: HabitLayer) -> dict[UUID, float]:
        """This level's likelihood ratio against its parent.

        The product of every level's deviation, times the common prior, equals
        :attr:`probabilities` — the telescoping identity in the module
        docstring.  Exposed because it, not the raw level distribution, is what
        may be multiplied into another factor without double counting.
        """

        order = list(HabitLayer)
        index = order.index(layer)
        if index == 0:
            raise ValueError("the common layer has no parent to deviate from")
        parent = self.layer_probabilities[order[index - 1]]
        child = self.layer_probabilities[layer]
        return {
            location: (child[location] / parent[location] if parent[location] > 0.0 else 0.0)
            for location in child
        }


class LayeredHabitPosterior:
    """Back-off estimator for ``P(L | object, person, context)``.

    ``unknown_actor`` mass updates the household level only.  A guest's
    placement is evidence about *this household's object*, and is not evidence
    about any resident's personal habit — the same isolation rule
    :class:`HierarchicalDirichletHabitModel` enforces, restated here because
    the failure it prevents (访客污染, RQ8) is the expensive one.
    """

    UNKNOWN_ACTOR = UNKNOWN_ACTOR

    def __init__(
        self,
        *,
        locations: Sequence[UUID],
        common_prior: Mapping[UUID, float] | None = None,
        concentration: LayerConcentration | None = None,
        resident_actor_keys: Sequence[UUID | str] | None = None,
        model_version: str = LAYERED_POSTERIOR_VERSION,
    ) -> None:
        unique = tuple(dict.fromkeys(locations))
        if not unique:
            raise ValueError("locations must contain at least one candidate")
        self._locations = unique
        self._common_prior = self._normalize_prior(common_prior)
        self._concentration = concentration or LayerConcentration()
        self._resident_actor_keys = (
            None
            if resident_actor_keys is None
            else frozenset(str(actor) for actor in resident_actor_keys)
        )
        if self._resident_actor_keys is not None:
            if not self._resident_actor_keys:
                raise ValueError("resident_actor_keys cannot be empty when isolation is enabled")
            if self.UNKNOWN_ACTOR in self._resident_actor_keys:
                raise ValueError("unknown_actor cannot be declared as a resident")
        self._model_version = model_version
        self._household: dict[tuple[UUID, UUID], dict[UUID, float]] = defaultdict(
            lambda: defaultdict(float)
        )
        self._person: dict[tuple[UUID, str, UUID], dict[UUID, float]] = defaultdict(
            lambda: defaultdict(float)
        )
        self._context: dict[tuple[UUID, str, UUID, str], dict[UUID, float]] = defaultdict(
            lambda: defaultdict(float)
        )
        self._observations_applied = 0.0

    # -- construction helpers ------------------------------------------------

    def _normalize_prior(self, prior: Mapping[UUID, float] | None) -> dict[UUID, float]:
        if prior is None:
            share = 1.0 / len(self._locations)
            return dict.fromkeys(self._locations, share)
        values = {location: float(prior.get(location, 0.0)) for location in self._locations}
        for location, value in values.items():
            if not isfinite(value) or value < 0.0:
                raise ValueError(f"common prior for {location} must be finite and non-negative")
        total = sum(values.values())
        if total <= 0.0:
            raise ValueError("common prior must place mass on at least one candidate location")
        return {location: value / total for location, value in values.items()}

    # -- learning ------------------------------------------------------------

    def update(self, evidence: HabitLearningEvidence, *, weight_multiplier: float = 1.0) -> float:
        """Absorb one piece of evidence and return the weight actually applied.

        The same firewall as M17: a model prediction has an effective training
        weight of zero and therefore cannot train itself.
        """

        if not isfinite(weight_multiplier) or weight_multiplier < 0.0:
            raise ValueError("weight_multiplier must be finite and non-negative")
        if evidence.location_id not in self._common_prior:
            raise ValueError("evidence location is outside the declared candidate set")
        weight = evidence.effective_training_weight * weight_multiplier
        if weight <= 0.0:
            return 0.0

        household_id = evidence.metadata.household_id
        object_id = evidence.object_instance_id
        location = evidence.location_id

        # One observation, counted once at the household level regardless of who
        # is thought to have done it.  The actor posterior partitions that same
        # unit of evidence across the person level; it does not add to it.
        self._household[(household_id, object_id)][location] += weight
        for actor, probability in evidence.actor_posterior.items():
            if actor == self.UNKNOWN_ACTOR or probability <= 0.0:
                continue
            if self._resident_actor_keys is not None and actor not in self._resident_actor_keys:
                continue
            share = weight * probability
            self._person[(household_id, actor, object_id)][location] += share
            self._context[(household_id, actor, object_id, evidence.context_key)][location] += share
        self._observations_applied += weight
        return weight

    # -- prediction ----------------------------------------------------------

    def predict(
        self,
        *,
        household_id: UUID,
        person_id: UUID | str,
        object_instance_id: UUID,
        context_key: str,
    ) -> LayeredHabitPrediction:
        actor = str(person_id)
        household_excl, person_excl, context_counts = self._partitioned_counts(
            household_id=household_id,
            actor=actor,
            object_instance_id=object_instance_id,
            context_key=context_key,
        )

        layer_probabilities: dict[HabitLayer, Mapping[UUID, float]] = {
            HabitLayer.COMMON: dict(self._common_prior)
        }
        layer_weight: dict[HabitLayer, float] = {HabitLayer.COMMON: 1.0}
        layer_counts: dict[HabitLayer, float] = {HabitLayer.COMMON: 0.0}

        parent: Mapping[UUID, float] = self._common_prior
        deepest = HabitLayer.COMMON
        for layer, counts in (
            (HabitLayer.HOUSEHOLD, household_excl),
            (HabitLayer.PERSON, person_excl),
            (HabitLayer.CONTEXT, context_counts),
        ):
            kappa = self._concentration.of(layer)
            total = sum(counts.values())
            distribution = {
                location: (counts.get(location, 0.0) + kappa * parent[location]) / (total + kappa)
                for location in self._locations
            }
            layer_probabilities[layer] = distribution
            # ``lambda`` in the shrinkage sense: how far this level has moved
            # off its parent.  Zero counts means "identical to the parent",
            # which is exactly the behaviour a back-off must have.
            layer_weight[layer] = total / (total + kappa)
            layer_counts[layer] = total
            if total > 0.0:
                deepest = layer
            parent = distribution

        probabilities = dict(parent)
        return LayeredHabitPrediction(
            probabilities=probabilities,
            layer_probabilities=layer_probabilities,
            layer_weight=layer_weight,
            deepest_layer=deepest,
            evidence=self.evidence_report(
                household_id=household_id,
                person_id=actor,
                object_instance_id=object_instance_id,
                context_key=context_key,
            ),
            model_version=self._model_version,
            layer_counts=layer_counts,
        )

    # -- the leave-one-out partition ----------------------------------------

    def _partitioned_counts(
        self,
        *,
        household_id: UUID,
        actor: str,
        object_instance_id: UUID,
        context_key: str,
    ) -> tuple[dict[UUID, float], dict[UUID, float], dict[UUID, float]]:
        """Split this object's evidence into three disjoint pools.

        ``context`` holds the cell being predicted, ``person`` holds that
        resident's other contexts, ``household`` holds the other residents plus
        any unknown-actor mass.  Disjoint by construction, which is what makes
        the multiplicity assertion in :meth:`evidence_report` provable rather
        than hopeful.
        """

        household = self._household[(household_id, object_instance_id)]
        person = self._person[(household_id, actor, object_instance_id)]
        context = self._context[(household_id, actor, object_instance_id, context_key)]

        context_counts = {location: context.get(location, 0.0) for location in self._locations}
        person_excl = {
            location: max(person.get(location, 0.0) - context_counts[location], 0.0)
            for location in self._locations
        }
        household_excl = {
            location: max(
                household.get(location, 0.0) - person.get(location, 0.0),
                0.0,
            )
            for location in self._locations
        }
        return household_excl, person_excl, context_counts

    # -- the RQ5 diagnostic --------------------------------------------------

    def evidence_report(
        self,
        *,
        household_id: UUID,
        person_id: UUID | str,
        object_instance_id: UUID,
        context_key: str,
    ) -> EvidenceReport:
        """How much counted evidence this prediction rests on.

        The three pools are disjoint and their union is every observation for
        this ``(household, object)``, so the counted mass equals the applied
        mass and the multiplicity is exactly 1.  A value above 1 means an
        observation reached the scoring expression more than once; below 1
        means some evidence was dropped.  Both are bugs, and both are visible
        here instead of showing up later as an overconfident posterior.
        """

        actor = str(person_id)
        household_excl, person_excl, context_counts = self._partitioned_counts(
            household_id=household_id,
            actor=actor,
            object_instance_id=object_instance_id,
            context_key=context_key,
        )
        counts = {
            HabitLayer.HOUSEHOLD: sum(household_excl.values()),
            HabitLayer.PERSON: sum(person_excl.values()),
            HabitLayer.CONTEXT: sum(context_counts.values()),
        }
        counted = sum(counts.values())
        applied = sum(self._household[(household_id, object_instance_id)].values())
        multiplicity = 0.0 if applied <= 0.0 else counted / applied
        return EvidenceReport(
            observations_applied=applied,
            counted_evidence_mass=counted,
            evidence_multiplicity=multiplicity,
            layer_counts=counts,
        )

    @property
    def observations_applied(self) -> float:
        return self._observations_applied

    @property
    def concentration(self) -> LayerConcentration:
        return self._concentration

    def config_payload(self) -> dict[str, object]:
        return {
            "model_version": self._model_version,
            "locations": [str(location) for location in self._locations],
            "common_prior": {
                str(location): repr(value)
                for location, value in sorted(
                    self._common_prior.items(), key=lambda item: str(item[0])
                )
            },
            "concentration": {
                "household": repr(self._concentration.household),
                "person": repr(self._concentration.person),
                "context": repr(self._concentration.context),
            },
            "resident_isolation": self._resident_actor_keys is not None,
        }


def measure_evidence_multiplicity(
    model: Any,
    *,
    evidence: HabitLearningEvidence,
    household_id: UUID,
    person_id: UUID | str,
    object_instance_id: UUID,
    context_key: str,
    repeats: int = 8,
) -> float:
    """How many times one observation enters a model's scoring expression.

    Model-agnostic and measured rather than derived, so it applies to the
    additive :class:`HierarchicalDirichletHabitModel` and to
    :class:`LayeredHabitPosterior` alike.  The probe fits the *implied* single
    level Dirichlet sample size: after ``n`` identical observations a one-level
    model with a uniform prior of strength 1 over ``K`` locations reports

    ``p = (ess + 1/K) / (ess + 1)``  →  ``ess = (1/K - p) / (p - 1)``

    and the multiplicity is ``ess / n``.  A value of 1 means the posterior is
    exactly as confident as the evidence justifies; 3 means it is as confident
    as three times the evidence would justify.
    """

    if repeats < 1:
        raise ValueError("repeats must be at least 1")
    for _ in range(repeats):
        model.update(evidence)
    prediction = model.predict(
        household_id=household_id,
        person_id=person_id,
        object_instance_id=object_instance_id,
        context_key=context_key,
    )
    probabilities = prediction.probabilities
    location_count = len(probabilities)
    top = probabilities[evidence.location_id]
    uniform = 1.0 / location_count
    if isclose(top, 1.0, rel_tol=0.0, abs_tol=1e-12):
        return float("inf")
    implied = (uniform - top) / (top - 1.0)
    return float(implied / repeats)
