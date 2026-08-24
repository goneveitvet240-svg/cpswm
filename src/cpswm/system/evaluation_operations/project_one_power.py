"""Is this comparison big enough to mean anything?

Every project-one reading so far has ended `UNDERPOWERED`, and the reason was
never stated as a number: five scenarios, one seed, a confirmation rate whose
smallest possible step is 0.2.  This module makes the question answerable before
the result is read, so "we cannot tell" is a computed verdict rather than a
judgement call that a hopeful reader can talk themselves out of.

Two decisions carry most of the weight.

**The resampling unit is the stream, not the event.**  Twenty events inside one
scenario are not twenty independent observations of a detector -- they share a
regime, a location vocabulary and a change point.  Bootstrapping over events
would shrink every interval by roughly the square root of the stream length and
manufacture significance out of correlation.  Everything here resamples whole
``(family, seed)`` streams, which is the same unit SHIFT v5 settled on after
four rounds of getting it wrong.

**The standard deviation is inflated before it is used.**  An SD estimated from
a handful of streams is itself noisy, and estimating it low is the failure that
matters: it makes an underpowered study look adequate.  Following SHIFT v5,
``powered_sd = max(empirical_sd * 1.5, floor)``, with a floor so that an
endpoint which happened to produce zero variance on a small sample does not
report that it needs one pair.
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from statistics import fmean, stdev

__all__ = [
    "DEFAULT_MDE",
    "DEFAULT_SD_FLOOR",
    "DEFAULT_SD_INFLATION",
    "PowerCheck",
    "PowerReport",
    "paired_bootstrap_ci",
    "power_check",
    "required_pairs",
]

#: Smallest difference worth being able to detect.  0.05 matches the MDE the
#: project already used for the SHIFT action-baseline guardrail, so the two
#: families of result stay comparable.
DEFAULT_MDE = 0.05

#: Estimated SDs are noisy on small samples and under-estimating is the
#: dangerous direction, so the estimate is inflated before it sizes the study.
DEFAULT_SD_INFLATION = 1.5

#: Floor, so an endpoint that happens to show zero spread on a few streams does
#: not claim it needs one pair.
DEFAULT_SD_FLOOR = 0.05

#: ``(z(0.975) + z(0.8)) ** 2`` = ``(1.959964 + 0.841621) ** 2``.
#: Two-sided alpha 0.05, power 0.8, paired design.
_Z_SUM_SQUARED = 7.848878


def required_pairs(sd: float, *, mde: float = DEFAULT_MDE) -> int:
    """Pairs needed to detect ``mde`` at alpha 0.05 with power 0.8."""

    if sd < 0.0 or not math.isfinite(sd):
        raise ValueError("sd must be finite and non-negative")
    if mde <= 0.0 or not math.isfinite(mde):
        raise ValueError("mde must be finite and positive")
    return max(1, math.ceil(_Z_SUM_SQUARED * (sd**2) / (mde**2)))


@dataclass(frozen=True, slots=True)
class PowerCheck:
    """One endpoint's answer to "could this study have seen a real effect?"."""

    endpoint: str
    reference: str
    achieved_pairs: int
    empirical_sd: float
    powered_sd: float
    minimum_detectable_effect: float
    required_pairs: int
    observed_difference: float
    confidence_interval_95: tuple[float, float]

    @property
    def powered(self) -> bool:
        """Could this study have detected an effect as small as the MDE?

        A *design* question, answered before the data is read.  It is not the
        same as whether an effect was found: a study underpowered for 0.05 can
        still resolve an effect of 0.20, and a study powered for 0.05 that finds
        nothing has said something real.
        """

        return self.achieved_pairs >= self.required_pairs

    @property
    def significant(self) -> bool:
        low, high = self.confidence_interval_95
        return low > 0.0 or high < 0.0

    @property
    def conclusion(self) -> str:
        """The three outcomes worth distinguishing.

        Collapsing these into one "powered / underpowered" flag is what makes
        reports unreadable: it prints ``need=290`` next to an interval that
        clearly excludes zero, and a reader cannot tell whether that means
        "we found something" or "we cannot tell".

        * ``significant``   -- the interval excludes zero.  An effect was
          resolved, whatever the design was sized for.
        * ``null_result``   -- adequately powered and the interval spans zero.
          Evidence *against* an effect of at least the MDE, which is a finding.
        * ``inconclusive``  -- underpowered and the interval spans zero.  The
          study cannot answer the question either way.
        """

        if self.significant:
            return "significant"
        return "null_result" if self.powered else "inconclusive"

    def as_dict(self) -> dict[str, object]:
        return {
            "endpoint": self.endpoint,
            "reference": self.reference,
            "achieved_pairs": self.achieved_pairs,
            "empirical_sd": self.empirical_sd,
            "powered_sd": self.powered_sd,
            "minimum_detectable_effect": self.minimum_detectable_effect,
            "required_pairs_for_mde": self.required_pairs,
            "observed_difference": self.observed_difference,
            "confidence_interval_95": list(self.confidence_interval_95),
            "powered_for_mde": self.powered,
            "statistically_significant": self.significant,
            "conclusion": self.conclusion,
        }


@dataclass(frozen=True, slots=True)
class PowerReport:
    """Every endpoint's power check, plus the one verdict that follows."""

    checks: tuple[PowerCheck, ...]

    @property
    def powered(self) -> bool:
        return bool(self.checks) and all(check.powered for check in self.checks)

    def verdict(self) -> str:
        """``CONCLUSIVE`` when no endpoint is left unable to answer.

        An endpoint counts as answered if it resolved an effect *or* was
        adequately sized and found none.  Only a comparison that is both
        underpowered and null leaves the question open, and one of those is
        enough to stop the whole run being reported as a conclusion.

        Deliberately all-or-nothing at that point: letting the answered
        endpoints carry the verdict is exactly how an underpowered study gets
        written up as a finding.
        """

        if not self.checks:
            return "UNDERPOWERED"
        return "UNDERPOWERED" if self.shortfall() else "CONCLUSIVE"

    def shortfall(self) -> tuple[PowerCheck, ...]:
        """Endpoints that answered nothing: underpowered *and* null."""

        return tuple(check for check in self.checks if check.conclusion == "inconclusive")

    def significant(self) -> tuple[PowerCheck, ...]:
        return tuple(check for check in self.checks if check.conclusion == "significant")

    def null_results(self) -> tuple[PowerCheck, ...]:
        return tuple(check for check in self.checks if check.conclusion == "null_result")

    def as_dict(self) -> dict[str, object]:
        return {
            "verdict": self.verdict(),
            "checks": [check.as_dict() for check in self.checks],
            "significant": [f"{c.reference}:{c.endpoint}" for c in self.significant()],
            "null_results": [f"{c.reference}:{c.endpoint}" for c in self.null_results()],
            "inconclusive": [f"{c.reference}:{c.endpoint}" for c in self.shortfall()],
        }


def paired_bootstrap_ci(
    differences: Sequence[float],
    *,
    iterations: int = 2000,
    seed: int = 0,
    alpha: float = 0.05,
) -> tuple[float, float]:
    """Percentile bootstrap over whole streams.

    ``differences`` must already be one value per stream -- see the module
    docstring on why the unit matters.
    """

    if not differences:
        return (0.0, 0.0)
    if iterations < 1:
        raise ValueError("iterations must be at least 1")
    rng = random.Random(seed)
    count = len(differences)
    means = sorted(fmean(rng.choices(differences, k=count)) for _ in range(iterations))
    low = means[max(0, math.floor(iterations * alpha / 2.0))]
    high = means[min(iterations - 1, math.ceil(iterations * (1.0 - alpha / 2.0)) - 1)]
    return (low, high)


def power_check(
    per_stream_differences: Mapping[str, float],
    *,
    endpoint: str,
    reference: str,
    mde: float = DEFAULT_MDE,
    sd_inflation: float = DEFAULT_SD_INFLATION,
    sd_floor: float = DEFAULT_SD_FLOOR,
    bootstrap_iterations: int = 2000,
    bootstrap_seed: int = 0,
) -> PowerCheck:
    """Size one paired comparison, keyed by stream id.

    Keying by stream id rather than taking a bare list is a guardrail: it makes
    it impossible to hand in two differences for the same stream and quietly
    double its weight.
    """

    values = [per_stream_differences[key] for key in sorted(per_stream_differences)]
    empirical = stdev(values) if len(values) > 1 else 0.0
    powered = max(empirical * sd_inflation, sd_floor)
    return PowerCheck(
        endpoint=endpoint,
        reference=reference,
        achieved_pairs=len(values),
        empirical_sd=empirical,
        powered_sd=powered,
        minimum_detectable_effect=mde,
        required_pairs=required_pairs(powered, mde=mde),
        observed_difference=fmean(values) if values else 0.0,
        confidence_interval_95=paired_bootstrap_ci(
            values, iterations=bootstrap_iterations, seed=bootstrap_seed
        ),
    )
