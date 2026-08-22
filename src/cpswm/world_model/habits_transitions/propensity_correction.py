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
