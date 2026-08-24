"""Frozen project-one evaluation protocol (阶段 0).

This module fixes the *interface* every project-one experiment must speak, so
that algorithm changes, data changes and threshold changes can be attributed
separately.  It deliberately does **not** extend
:mod:`cpswm.system.prototype_spine`; that module is frozen for this experiment
series and is consumed, never modified.

Three things are frozen here:

1. **The decision label space.**  Exactly four outcomes, mirroring
   :class:`~cpswm.system.continual.project_one_regime_loop.HabitStateConclusion`
   so a protocol run and a spine run are directly comparable.
2. **The per-step trace.**  Six intermediate quantities must be recorded for
   every event, because an ablation that cannot show *which* signal moved is
   not an attribution.
3. **The configuration identity.**  Every run carries a ``config_hash`` derived
   from the canonical serialization of its config, so a result can always be
   traced back to the exact thresholds that produced it.

Scope boundary (stated once, honestly)
--------------------------------------
The protocol covers the **habit-change decision chain**: Dirichlet predictive
surprise, RLS residual, the derived habit signal, joint CF-BOCPD change
probability, the CCRR routing decision, and the resulting active regime.  It
does *not* cover the ORRER/PCHMP event layer or the hybrid RGRC ledger that
:class:`~cpswm.system.prototype_spine.CorePrototypeSpine` also integrates.
Those stay in the spine.  Results produced under this protocol are therefore
evidence about the change-detection chain, not about the full spine.

The signal formulas below are pinned to the frozen spine: the predictive
surprise helper is imported directly from it (so it cannot silently drift), and
:func:`habit_signal` reproduces the spine's combination rule.  The regression
test ``tests/test_project_one_protocol.py`` pins the numeric values.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from math import exp, isfinite, log, sqrt

from cpswm.system.continual.project_one_regime_loop import (
    HabitStateConclusion,
    PrototypeLoopConfig,
)

# The spine owns this formula.  Importing it (rather than re-deriving it) means
# a change in the frozen module breaks loudly here instead of silently
# producing two different definitions of "surprise".
from cpswm.system.prototype_spine import (
    _normalized_predictive_surprise as normalized_predictive_surprise,
)
from cpswm.system.reproducibility import content_sha256

__all__ = [
    "DEFAULT_RESIDUAL_CALIBRATION_NAME",
    "PROTOCOL_VERSION",
    "SIGMOID_AT_ONE",
    "SIGMOID_RESIDUAL_FLOOR",
    "CategoricalBOCPDConfig",
    "ContextFrequencyConfig",
    "HistogramResidualCalibrator",
    "PersistenceConfig",
    "PlattResidualCalibrator",
    "ProjectOneDecision",
    "ProjectOneProtocolConfig",
    "ProjectOneStepTrace",
    "ResidualCalibration",
    "SignalAblation",
    "calibrated_residual",
    "config_identity",
    "habit_signal",
    "normalized_predictive_surprise",
    "residual_severity",
]

PROTOCOL_VERSION = "project-one-evaluation-protocol@0.3"


#: The one calibration route the benchmark, the tuner and the default config all
#: use.  Having each entry point pick its own default is how two runs end up
#: incomparable without anyone noticing.
DEFAULT_RESIDUAL_CALIBRATION_NAME = "raw_clip"


def config_identity(config: object) -> str:
    """Content identity of any frozen dataclass config.

    Every arm — method under test *and* baseline — must be able to answer
    "which exact numbers produced this?".  A baseline whose parameters live as
    hardcoded defaults cannot be independently tuned in 阶段 7 and cannot be
    audited afterwards, so every arm carries one of these.
    """

    return content_sha256(asdict(config))  # type: ignore[call-overload]


class ProjectOneDecision(StrEnum):
    """The four — and only four — project-one step outcomes."""

    STABLE = "stable"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    SHORT_TERM_DISTURBANCE = "short_term_disturbance"
    HABIT_CHANGE = "habit_change"

    @classmethod
    def from_conclusion(cls, conclusion: HabitStateConclusion) -> ProjectOneDecision:
        """Map a spine conclusion onto the frozen protocol label space."""

        return cls(conclusion.value)


class SignalAblation(StrEnum):
    """Which cause-signal channels an arm is allowed to use.

    The intervention is surgical: it changes only the two scalar channels that
    feed :func:`habit_signal`.  Learning, routing, thresholds, data order and
    every other component stay byte-identical across arms, so a difference in
    outcome is attributable to the channel that was cut.
    """

    #: Both channels live.  This is the method under test.
    FULL = "full"
    #: RLS residual forced to zero; Dirichlet surprise untouched.
    NO_RLS = "no_rls"
    #: Residual replaced by another step's residual (deterministic derangement).
    #: Preserves the residual's marginal distribution and destroys its pairing
    #: with the event, which separates "informative signal" from "any signal of
    #: that magnitude".
    SHUFFLED_RLS = "shuffled_rls"
    #: Dirichlet surprise forced to zero; RLS residual untouched.
    RLS_ONLY = "rls_only"


class ResidualCalibration(StrEnum):
    """How the RLS score is read before it becomes a residual.

    ``RLSHabitScoreHead.score_candidates`` applies a sigmoid by default, but the
    underlying model is a least-squares regressor already fitted to ``{0, 1}``
    targets — its raw output *is* the calibrated score.  Squashing it a second
    time compresses a perfectly learned score from ``1.0`` to ``0.731`` and a
    perfectly rejected one from ``0.0`` to ``0.5``, so the residual can never
    leave ``[0.269, 0.5]``.

    ``AS_IS`` reproduces the shipped wiring exactly.  ``LOGIT`` inverts the
    sigmoid inside this harness, so the cost of that wiring can be measured
    without editing the frozen spine or the shared RLS head.  Neither option
    modifies any module outside the evaluation package.
    """

    #: Use the bank's score exactly as returned.  Reproduces the shipped wiring.
    AS_IS = "as_is"
    #: Invert the sigmoid, then take ``|1 - raw|`` capped at 1.
    LOGIT = "logit"
    #: Invert the sigmoid, clamp the recovered raw score into ``[0, 1]`` first,
    #: then take ``1 - raw``.  Differs from LOGIT only for over-confident
    #: scores (raw > 1), which LOGIT turns back into a residual and this route
    #: treats as "no error at all".
    RAW_CLIP = "raw_clip"
    #: Affine-rescale the squashed range ``[sigmoid(0), sigmoid(1)]`` back onto
    #: ``[0, 1]``.  Keeps the head untouched and needs no inverse, but assumes
    #: the raw score really does live in ``[0, 1]``.
    RECENTER = "recenter"
    #: Bucketed empirical calibration: map the score through the observed hit
    #: rate of nearby scores.  Makes no assumption about the head's output
    #: scale, at the cost of needing history before it is meaningful.  This is
    #: histogram binning, *not* Platt scaling -- it was misnamed ``PLATT`` in
    #: v0.2, which claimed a method it did not implement.
    HISTOGRAM = "histogram"
    #: Platt scaling proper: a one-dimensional logistic regression
    #: ``P(hit | s) = sigmoid(-(A * s + B))`` fitted online by gradient descent
    #: on the log-loss, with Platt's own target smoothing.  Parametric, so it
    #: needs far less history than binning, but it can only express a monotone
    #: sigmoid in the score.
    PLATT = "platt"


#: ``sigmoid(1.0)`` -- what the head reports for a perfectly learned location.
SIGMOID_AT_ONE = 0.7310585786300049

#: Residual produced by a *perfectly* predicted location under ``AS_IS``.
#: ``1 - sigmoid(1.0)``.  Pinned by ``tests/test_project_one_protocol.py``.
SIGMOID_RESIDUAL_FLOOR = 0.2689414213699951


class HistogramResidualCalibrator:
    """Empirical ``P(hit | score)`` over a fixed score grid.

    Deliberately simple: bucket the score, keep Laplace-smoothed hit and miss
    counts per bucket, and read the calibrated probability back out.  It makes
    no assumption about the head's output scale, which is the point — it is the
    one route that survives whatever the head does downstream.

    It is also the one route with a cold start: before a bucket has seen
    anything, it returns the smoothed prior (0.5), so early residuals are
    uninformative rather than wrong.  Because every bucket starts cold
    independently, that cold start is long -- which is exactly what
    :class:`PlattResidualCalibrator` trades away for a parametric form.
    """

    __slots__ = ("_buckets", "_hits", "_misses", "_prior")

    def __init__(self, buckets: int = 10, prior: float = 1.0) -> None:
        if buckets < 2:
            raise ValueError("buckets must be at least 2")
        if prior <= 0.0:
            raise ValueError("prior must be positive")
        self._buckets = buckets
        self._prior = prior
        self._hits = [0.0] * buckets
        self._misses = [0.0] * buckets

    def _index(self, score: float) -> int:
        clamped = min(1.0 - 1e-9, max(0.0, score))
        return int(clamped * self._buckets)

    def residual(self, score: float) -> float:
        index = self._index(score)
        hits = self._hits[index] + self._prior
        total = hits + self._misses[index] + self._prior
        return min(1.0, max(0.0, 1.0 - hits / total))

    def update(self, score: float, hit: bool, weight: float = 1.0) -> None:
        index = self._index(score)
        if hit:
            self._hits[index] += weight
        else:
            self._misses[index] += weight

    def snapshot(self) -> dict[str, object]:
        return {
            "kind": "histogram",
            "buckets": self._buckets,
            "hits": list(self._hits),
            "misses": list(self._misses),
        }


#: Bound on the fitted Platt parameters; see :meth:`PlattResidualCalibrator.update`.
_PLATT_BOUND = 25.0


class PlattResidualCalibrator:
    r"""Platt scaling: a one-dimensional logistic fit of ``P(hit | score)``.

    Platt (1999) fits ``P(y=1 | s) = 1 / (1 + exp(A * s + B))`` by minimizing
    the log-loss, using smoothed targets

    .. math::
        t_+ = \frac{N_+ + 1}{N_+ + 2}, \qquad t_- = \frac{1}{N_- + 2}

    rather than hard 0/1, which is what stops the fit from running away to
    infinity on separable data.  Both pieces are implemented here; the fit is
    online gradient descent rather than Platt's Newton solver, because the
    arm sees one event at a time and cannot hold the batch.

    ``A`` starts negative so that a *higher* score means a *higher* hit
    probability before any data arrives -- the identity-like starting point.
    That matters: a calibrator initialized flat would make every early residual
    exactly 0.5 and drown the first few steps of a short stream.

    The score is **standardized** with a running mean and variance before the
    logistic.  This is not cosmetic.  Under the ``as_is`` route the head's whole
    informative range is ``[0.5, 0.731]`` -- 0.231 wide -- so an unstandardized
    fit needs a slope near -33 and creeps toward it, while under ``raw_clip``
    the same data spans the full unit interval and converges immediately.
    Without standardization this calibrator would look bad on ``as_is`` for a
    reason that has nothing to do with calibration, and the route comparison
    would be measuring conditioning instead of method.
    """

    __slots__ = (
        "_a",
        "_b",
        "_count",
        "_learning_rate",
        "_m2",
        "_mean",
        "_negatives",
        "_positives",
        "_updates",
    )

    def __init__(self, learning_rate: float = 0.5) -> None:
        if learning_rate <= 0.0 or not isfinite(learning_rate):
            raise ValueError("learning_rate must be finite and positive")
        self._learning_rate = learning_rate
        self._a = -4.0
        self._b = 0.0
        self._positives = 0.0
        self._negatives = 0.0
        self._updates = 0
        self._count = 0
        self._mean = 0.0
        self._m2 = 0.0

    def _standardize(self, score: float) -> float:
        """Welford-standardized score; identity-ish until a spread is known."""

        if self._count < 2:
            return score - self._mean
        variance = self._m2 / (self._count - 1)
        deviation = sqrt(variance)
        if deviation < 1e-9:
            return 0.0
        return float((score - self._mean) / deviation)

    def _observe_score(self, score: float) -> None:
        self._count += 1
        delta = score - self._mean
        self._mean += delta / self._count
        self._m2 += delta * (score - self._mean)

    def _probability(self, score: float) -> float:
        z = self._a * self._standardize(score) + self._b
        z = min(60.0, max(-60.0, z))
        return 1.0 / (1.0 + exp(z))

    def residual(self, score: float) -> float:
        return min(1.0, max(0.0, 1.0 - self._probability(score)))

    def update(self, score: float, hit: bool, weight: float = 1.0) -> None:
        """One weighted gradient step on the smoothed-target log-loss."""

        if weight <= 0.0:
            return
        if hit:
            self._positives += weight
            target = (self._positives + 1.0) / (self._positives + 2.0)
        else:
            self._negatives += weight
            target = 1.0 / (self._negatives + 2.0)

        self._observe_score(score)
        standardized = self._standardize(score)
        probability = self._probability(score)
        # With z = A*s + B and p = sigmoid(-z), d(log-loss)/dz = target - p.
        # Descent therefore *subtracts* it: raising the target lowers z, which
        # raises p.  Adding it would push the fit away from the data, which is
        # exactly the sign error that made the v0.3 draft report P(hit) = 1 for
        # a score whose observed hit rate was 1 in 4.
        step = self._learning_rate * weight * (target - probability)
        self._a -= step * standardized
        self._b -= step
        # A runaway fit is not a better fit; separable data would otherwise send
        # both parameters to infinity even with smoothed targets.
        self._a = min(_PLATT_BOUND, max(-_PLATT_BOUND, self._a))
        self._b = min(_PLATT_BOUND, max(-_PLATT_BOUND, self._b))
        self._updates += 1

    def snapshot(self) -> dict[str, object]:
        return {
            "kind": "platt",
            "a": self._a,
            "b": self._b,
            "score_mean": self._mean,
            "score_std": sqrt(self._m2 / (self._count - 1)) if self._count > 1 else 0.0,
            "positives": self._positives,
            "negatives": self._negatives,
            "updates": self._updates,
        }


@dataclass(frozen=True, slots=True)
class ProjectOneStepTrace:
    """The six intermediates every protocol step must record."""

    dirichlet_surprise: float
    rls_residual: float
    habit_signal: float
    change_probability: float
    ccrr_decision: str
    active_regime: str

    def __post_init__(self) -> None:
        for name in ("dirichlet_surprise", "rls_residual", "habit_signal", "change_probability"):
            value = float(getattr(self, name))
            if not isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be finite and in [0, 1]")
        if not self.ccrr_decision.strip():
            raise ValueError("ccrr_decision must be a non-empty label")
        if not self.active_regime.strip():
            raise ValueError("active_regime must be a non-empty label")


@dataclass(frozen=True, slots=True)
class ProjectOneProtocolConfig:
    """Every knob an arm is allowed to vary, plus its content identity.

    Defaults mirror :class:`PrototypeLoopConfig` so that "protocol defaults"
    and "prototype defaults" are the same numbers.  None of these values is a
    preregistered threshold; 阶段 6 runs at fixed thresholds and 阶段 7 tunes
    each arm independently.
    """

    minimum_baseline_observations: int = 3
    confirmation_window: int = 2
    habit_change_probability_threshold: float = 0.5
    transient_disturbance_probability_threshold: float = 0.5
    owner_evidence_threshold: float = 0.5
    forgetting_factor: float = 1.0
    context_confirmation_max_distance: float = 0.25
    dirichlet_surprise_weight: float = 0.1
    rls_residual_weight: float = 0.1
    #: Ridge term handed to ``RLSHabitScoreHead``.  The default matches that
    #: class's own default, so wiring this field through changed no behaviour;
    #: before v0.2 it was declared here and never used.
    rls_regularization: float = 1e-6
    ablation: SignalAblation = SignalAblation.FULL
    residual_calibration: ResidualCalibration = ResidualCalibration.RAW_CLIP
    protocol_version: str = PROTOCOL_VERSION

    def __post_init__(self) -> None:
        if self.minimum_baseline_observations < 1:
            raise ValueError("minimum_baseline_observations must be at least 1")
        # The frozen PrototypeLoopConfig requires at least two confirmations, so
        # accepting 1 here would only defer the failure to loop_config().
        if self.confirmation_window < 2:
            raise ValueError("confirmation_window must be at least 2")
        if not 0.0 < self.forgetting_factor <= 1.0:
            raise ValueError("forgetting_factor must lie in (0, 1]")
        if self.rls_regularization <= 0.0 or not isfinite(self.rls_regularization):
            raise ValueError("rls_regularization must be finite and positive")
        for name in (
            "habit_change_probability_threshold",
            "transient_disturbance_probability_threshold",
            "owner_evidence_threshold",
            "context_confirmation_max_distance",
            "dirichlet_surprise_weight",
            "rls_residual_weight",
        ):
            value = float(getattr(self, name))
            if not isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be finite and in [0, 1]")

    def config_hash(self) -> str:
        """Content identity of this configuration.

        Two runs may only be compared when their ``config_hash`` values agree,
        or when the difference is exactly the field under study.
        """

        return config_identity(self)

    def loop_config(self) -> PrototypeLoopConfig:
        """Project this protocol config onto the frozen prototype loop config."""

        return PrototypeLoopConfig(
            minimum_baseline_observations=self.minimum_baseline_observations,
            confirmation_window=self.confirmation_window,
            habit_change_probability_threshold=self.habit_change_probability_threshold,
            transient_disturbance_probability_threshold=(
                self.transient_disturbance_probability_threshold
            ),
            owner_evidence_threshold=self.owner_evidence_threshold,
            forgetting_factor=self.forgetting_factor,
            context_confirmation_max_distance=self.context_confirmation_max_distance,
            dirichlet_surprise_weight=self.dirichlet_surprise_weight,
            rls_residual_weight=self.rls_residual_weight,
        )


@dataclass(frozen=True, slots=True)
class CategoricalBOCPDConfig:
    """Standard BOCPD over the categorical location, conditioned on context.

    Information-matched to the chain arms: it sees the full location category
    and the same ``context_key`` pooling level, not a binary moved/not-moved
    indicator.  A baseline that only sees whether the object moved is a
    weakened baseline, and a weakened baseline is not evidence.
    """

    expected_run_length: float = 50.0
    dirichlet_alpha: float = 1.0
    change_threshold: float = 0.5
    max_run_length: int = 200
    context_conditioned: bool = True

    def __post_init__(self) -> None:
        if self.expected_run_length <= 1.0 or not isfinite(self.expected_run_length):
            raise ValueError("expected_run_length must be finite and exceed 1")
        if self.dirichlet_alpha <= 0.0 or not isfinite(self.dirichlet_alpha):
            raise ValueError("dirichlet_alpha must be finite and positive")
        if not isfinite(self.change_threshold) or not 0.0 <= self.change_threshold <= 1.0:
            raise ValueError("change_threshold must be finite and in [0, 1]")
        if self.max_run_length < 2:
            raise ValueError("max_run_length must be at least 2")

    def config_hash(self) -> str:
        return config_identity(self)


@dataclass(frozen=True, slots=True)
class ContextFrequencyConfig:
    """Context-conditioned frequency with Dirichlet smoothing."""

    alpha: float = 1.0
    change_threshold: float = 0.5

    def __post_init__(self) -> None:
        if self.alpha <= 0.0 or not isfinite(self.alpha):
            raise ValueError("alpha must be finite and positive")
        if not isfinite(self.change_threshold) or not 0.0 <= self.change_threshold <= 1.0:
            raise ValueError("change_threshold must be finite and in [0, 1]")

    def config_hash(self) -> str:
        return config_identity(self)


@dataclass(frozen=True, slots=True)
class PersistenceConfig:
    """Predict the last observed location; call any move a change."""

    confidence: float = 0.9

    def __post_init__(self) -> None:
        if not 0.0 < self.confidence < 1.0:
            raise ValueError("confidence must lie in (0, 1)")

    def config_hash(self) -> str:
        return config_identity(self)


def calibrated_residual(score: float, calibration: ResidualCalibration) -> float:
    """Turn one RLS candidate score into the residual the habit signal consumes.

    Under ``AS_IS`` the score is used exactly as the bank returns it.  Under
    ``LOGIT`` the sigmoid the head applied is inverted first, which recovers the
    regressor's own ``[0, 1]`` output before the residual is taken.
    """

    if not isfinite(score):
        raise ValueError("score must be finite")
    if calibration in (ResidualCalibration.HISTOGRAM, ResidualCalibration.PLATT):
        raise ValueError(f"{calibration.value} is stateful; the arm owns a calibrator for it")
    if calibration is ResidualCalibration.RECENTER:
        span = SIGMOID_AT_ONE - 0.5
        rescaled = min(1.0, max(0.0, (score - 0.5) / span))
        return 1.0 - rescaled
    if calibration in (ResidualCalibration.LOGIT, ResidualCalibration.RAW_CLIP):
        clamped = min(1.0 - 1e-12, max(1e-12, score))
        raw = log(clamped / (1.0 - clamped))
        if calibration is ResidualCalibration.RAW_CLIP:
            return 1.0 - min(1.0, max(0.0, raw))
        return min(1.0, abs(1.0 - raw))
    return min(1.0, abs(1.0 - score))


def residual_severity(residual: float) -> float:
    """Map an RLS residual onto its severity contribution.

    Mirrors the frozen spine: ``1 - (1 - residual) ** 2``.  The quadratic keeps
    small residuals nearly free while preserving a strict ordering, so a slight
    prediction miss cannot masquerade as an anomaly.
    """

    if not isfinite(residual) or not 0.0 <= residual <= 1.0:
        raise ValueError("residual must be finite and in [0, 1]")
    return 1.0 - (1.0 - residual) ** 2


def habit_signal(
    *,
    habit_transition: float,
    dirichlet_surprise: float,
    rls_residual: float,
    dirichlet_surprise_weight: float,
    rls_residual_weight: float,
) -> float:
    """Combine the two model-error channels into one habit cause signal.

    Reproduces the frozen spine exactly::

        unexpected = habit_transition * (1 - (1 - surprise) * (1 - severity))
        signal     = max(unexpected, w_s * surprise, w_r * residual)

    A location change on its own no longer produces a full-valued signal: the
    move must coincide with model error before it can drive a regime decision.
    The two weighted floors are independent guardrails so that a persistent
    model error is still visible even without a move.
    """

    for name, value in (
        ("habit_transition", habit_transition),
        ("dirichlet_surprise", dirichlet_surprise),
        ("rls_residual", rls_residual),
        ("dirichlet_surprise_weight", dirichlet_surprise_weight),
        ("rls_residual_weight", rls_residual_weight),
    ):
        if not isfinite(value) or not 0.0 <= value <= 1.0:
            raise ValueError(f"{name} must be finite and in [0, 1]")

    unexpected_move = habit_transition * (
        1.0 - (1.0 - dirichlet_surprise) * (1.0 - residual_severity(rls_residual))
    )
    return max(
        unexpected_move,
        dirichlet_surprise_weight * dirichlet_surprise,
        rls_residual_weight * rls_residual,
    )
