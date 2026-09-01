"""Observation-propensity correction for M17 habit counts.

`项目方向结构二 §2`: because the robot's route and task decide what it sees,
*"missingness is usually MNAR"*.  An uncorrected count therefore estimates the
robot's patrol route as much as the resident's habit.

`ObservationOpportunityRecord` already carries everything needed to correct for
this — ``selection_probability``, ``p_visible_given_state`` and
``p_detect_given_visible`` — but nothing consumed them.  This module turns them
into a per-record weight.

Two deliberate refusals, both because a coverage gap must stay visible:

* **Positivity is checked, not patched.**  ``1/pi`` is undefined at ``pi = 0``.
  A place the robot can never see is outside the support, not a small sample,
  so correcting modes raise :class:`PositivityViolation` instead of assigning
  some large or zero number.
* **Clipping is recorded.**  Truncating extreme weights is necessary for
  variance, but the truncated fraction is reported so a reader can see how much
  of the correction was capped.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from math import isfinite
from statistics import fmean

from cpswm.contracts.habit_learning import ObservationOpportunityRecord


class PositivityViolation(ValueError):
    """Raised when a record could never have been observed at all."""


class PropensityCorrectionMode(StrEnum):
    """How strongly to correct a habit count for its observation propensity."""

    #: Weight every record 1.0. Reproduces the audited baseline exactly.
    NONE = "none"
    #: ``1 / pi``. Unbiased under positivity, but high variance for rare views.
    INVERSE = "inverse"
    #: ``mean_pi / pi``. Keeps the effective sample size near the raw count.
    STABILIZED = "stabilized"


class ObservationIdentifiabilityStatus(StrEnum):
    """Whether propensity correction identifies the requested observation estimand."""

    IDENTIFIABLE = "identifiable"
    WEAK_OVERLAP = "weak_overlap"
    POSITIVITY_FAILURE = "positivity_failure"
    NON_IDENTIFIABLE = "non_identifiable"


@dataclass(frozen=True, slots=True)
class ObservationSupportDiagnostic:
    """Support and identification report that must accompany OPCEU weights.

    Propensity weighting can repair selection on recorded variables under
    positivity.  It cannot identify passive-MNAR missingness driven by an
    unmeasured state.  The independent flags remain visible even when the
    primary status is ``NON_IDENTIFIABLE``.
    """

    status: ObservationIdentifiabilityStatus
    sample_count: int
    minimum_propensity: float
    overlap_threshold: float
    below_overlap_fraction: float
    effective_sample_size: float
    positivity_satisfied: bool
    overlap_satisfied: bool
    passive_mnar: bool
    unmeasured_selection_confounding: bool
    propensity_correction_identifies_estimand: bool
    rationale: str


@dataclass(frozen=True, slots=True)
class PropensityWeight:
    """One record's correction, with enough detail to audit it."""

    raw_propensity: float
    applied_weight: float
    clipped: bool


def propensity_from_opportunity(record: ObservationOpportunityRecord) -> float:
    """Probability this opportunity both happened and produced a detection.

    Selection is the robot's choice to look; visibility and detection are what
    the sensor could then do.  All three must hold for the placement to enter
    the training stream at all, so all three belong in the propensity.
    """

    return (
        record.selection_probability * record.p_visible_given_state * record.p_detect_given_visible
    )


class ObservationPropensityCorrector:
    """Turn an observation propensity into an auditable training weight."""

    def __init__(
        self,
        *,
        mode: PropensityCorrectionMode = PropensityCorrectionMode.NONE,
        minimum_propensity: float | None = None,
    ) -> None:
        if minimum_propensity is not None and not 0.0 < minimum_propensity <= 1.0:
            raise ValueError("minimum_propensity must be in (0, 1]")
        self._mode = mode
        self._minimum_propensity = minimum_propensity
        self._mean_propensity: float | None = None
        self._weighted_count = 0
        self._clipped_count = 0

    @property
    def mode(self) -> PropensityCorrectionMode:
        return self._mode

    @property
    def weighted_count(self) -> int:
        return self._weighted_count

    @property
    def clipped_fraction(self) -> float:
        """Share of weighted records whose propensity hit the clip threshold."""

        if self._weighted_count == 0:
            return 0.0
        return self._clipped_count / self._weighted_count

    def observe_propensities(self, propensities: Iterable[float]) -> float:
        """Record the propensity population that stabilised weights divide by.

        Stabilisation needs the mean over the records being corrected, so it
        must be supplied before weighting rather than inferred on the fly.
        """

        values = [self._validate(value) for value in propensities]
        if not values:
            raise ValueError("observe_propensities requires at least one propensity")
        self._mean_propensity = fmean(values)
        return self._mean_propensity

    def diagnose_support(
        self,
        propensities: Iterable[float],
        *,
        passive_mnar: bool,
        unmeasured_selection_confounding: bool,
        overlap_threshold: float | None = None,
    ) -> ObservationSupportDiagnostic:
        """Report positivity, overlap, and passive-MNAR identifiability.

        ``unmeasured_selection_confounding`` means the selection/detection
        probability still depends on an unrecorded state after conditioning on
        the logged observation process.  In that case inverse propensity
        weights may be computable but do not identify the target estimand.
        """

        values = tuple(self._validate(value) for value in propensities)
        if not values:
            raise ValueError("support diagnosis requires at least one propensity")
        threshold = (
            self._minimum_propensity
            if overlap_threshold is None and self._minimum_propensity is not None
            else 0.05
            if overlap_threshold is None
            else float(overlap_threshold)
        )
        if not isfinite(threshold) or not 0.0 < threshold <= 1.0:
            raise ValueError("overlap_threshold must lie in (0, 1]")

        positivity_satisfied = all(value > 0.0 for value in values)
        below = sum(value < threshold for value in values)
        overlap_satisfied = positivity_satisfied and below == 0
        positive_weights = tuple(1.0 / value for value in values if value > 0.0)
        effective_sample_size = (
            sum(positive_weights) ** 2 / sum(weight * weight for weight in positive_weights)
            if positive_weights
            else 0.0
        )

        if passive_mnar and unmeasured_selection_confounding:
            status = ObservationIdentifiabilityStatus.NON_IDENTIFIABLE
            rationale = (
                "passive MNAR depends on an unmeasured selection variable; propensity "
                "correction does not identify the target estimand"
            )
        elif not positivity_satisfied:
            status = ObservationIdentifiabilityStatus.POSITIVITY_FAILURE
            rationale = (
                "at least one target stratum has zero observation probability; report "
                "the unsupported stratum instead of extrapolating"
            )
        elif not overlap_satisfied:
            status = ObservationIdentifiabilityStatus.WEAK_OVERLAP
            rationale = (
                "observed support falls below the declared overlap threshold; corrected "
                "weights are high-variance and not paper-claim eligible"
            )
        else:
            status = ObservationIdentifiabilityStatus.IDENTIFIABLE
            rationale = "logged-variable positivity and overlap checks passed"

        return ObservationSupportDiagnostic(
            status=status,
            sample_count=len(values),
            minimum_propensity=min(values),
            overlap_threshold=threshold,
            below_overlap_fraction=below / len(values),
            effective_sample_size=effective_sample_size,
            positivity_satisfied=positivity_satisfied,
            overlap_satisfied=overlap_satisfied,
            passive_mnar=passive_mnar,
            unmeasured_selection_confounding=unmeasured_selection_confounding,
            propensity_correction_identifies_estimand=(
                status is ObservationIdentifiabilityStatus.IDENTIFIABLE
            ),
            rationale=rationale,
        )

    def weight_for(self, propensity: float) -> PropensityWeight:
        propensity = self._validate(propensity)

        if self._mode == PropensityCorrectionMode.NONE:
            self._weighted_count += 1
            return PropensityWeight(raw_propensity=propensity, applied_weight=1.0, clipped=False)

        # Zero propensity is a support failure, not an extreme value: no amount
        # of clipping makes an unobservable place observable.
        if propensity <= 0.0:
            raise PositivityViolation(
                "zero observation propensity: this record could never have been "
                "observed, so its habit weight is undefined. Report the coverage "
                "gap instead of correcting it."
            )

        effective = propensity
        clipped = False
        if self._minimum_propensity is not None and propensity < self._minimum_propensity:
            effective = self._minimum_propensity
            clipped = True

        if self._mode == PropensityCorrectionMode.INVERSE:
            weight = 1.0 / effective
        else:
            if self._mean_propensity is None:
                raise ValueError("stabilized correction requires observe_propensities() first")
            weight = self._mean_propensity / effective

        self._weighted_count += 1
        if clipped:
            self._clipped_count += 1
        return PropensityWeight(raw_propensity=propensity, applied_weight=weight, clipped=clipped)

    def weight_for_opportunity(
        self,
        record: ObservationOpportunityRecord,
    ) -> PropensityWeight:
        """Weight one real observation opportunity through the audited path."""

        return self.weight_for(propensity_from_opportunity(record))

    @staticmethod
    def _validate(propensity: float) -> float:
        value = float(propensity)
        if not 0.0 <= value <= 1.0:
            raise ValueError("propensity must be a probability in [0, 1]")
        return value
