"""Joint cause-factorized change-point inference with selective reset.

This is the real ``CF-BOCPD`` that 结构二 §4.7#2 specifies, distinct from the
independent-per-cause detector in :mod:`cause_factorized_bocpd` (kept as the
"多独立 BOCPD" baseline that this model must beat).

结构二 §4.7#2 requires a joint posterior ``p(r_t, C_t, Z_t, Theta_t | D_{1:t})``
with ``Theta_t = R_{C_t}(Theta_{t-1}, D_t)``, where ``R_C`` is a testable
*selective reset operator*: an observation change updates only the observation
model, an actor change only the actor mixture, an owner-habit change only the
individual habit stage, and a noise change resets no long-term parameter.
Crucially this is not "BOCPD followed by a classifier": the cause variable
directly changes the transition kernel and which parameters may reset.

Structure (reviews 2026-08-21):

* **Event--regime separation.**  The filter reports both the instantaneous
  event posterior and the durable cause set that created the active regime, so
  downstream consolidation does not confuse "no new change today" with "the
  cause of the current regime is unknown".
* **Sparse multi-cause state.**  A segment event may reset a configurable sparse
  cause set (two causes by default), using the union selective-reset operator.
* **Measure 1 -- history-conditioned state.**  Each surviving hypothesis is a
  full segmentation carrying, per substantive block, Normal-Normal sufficient
  statistics ``(n, sum)`` since that block last reset (``Theta_{r,c}``); its
  predictive likelihood is the posterior predictive under those statistics.  A
  **beam** of the ``beam_width`` heaviest hypotheses is kept each step.
* **Noise as a transient-outlier state (Z_noise).**  Noise is *not* a segment
  change and does not share the segment emission.  It is an explicit transient
  state with a variance-inflated emission over the substantive channels plus a
  high-ambiguity emission for the noise indicator; it neither absorbs today's
  levels nor resets any block.  A one-step burst is therefore explained as noise
  without touching long-term ``Theta``, while a *persistent* shift is cheaper to
  explain with a single segment change than by paying the inflated-variance cost
  every step -- so bursts and regime changes separate on persistence.

The substantive change causes are observation / actor / habit; noise is handled
separately as the transient state above.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from itertools import combinations
from math import exp, isfinite, log, pi

from .cause_factorized_bocpd import ChangeCause

_LOG_2PI = log(2.0 * pi)

#: Causes that own a resettable long-term segment (noise does not).
SUBSTANTIVE_CAUSES: tuple[ChangeCause, ...] = tuple(
    cause for cause in ChangeCause if cause != ChangeCause.NOISE
)

#: Long-term parameter blocks a change of each cause is allowed to reset.
#: This is the literal ``R_C`` reset matrix; ``noise`` resets nothing.
DEFAULT_RESET_MATRIX: dict[ChangeCause, frozenset[ChangeCause]] = {
    ChangeCause.OBSERVATION: frozenset({ChangeCause.OBSERVATION}),
    ChangeCause.ACTOR: frozenset({ChangeCause.ACTOR}),
    ChangeCause.HABIT: frozenset({ChangeCause.HABIT}),
    ChangeCause.NOISE: frozenset(),
}


class CauseResetMatrix:
    """Which parameter blocks each change cause is permitted to reset."""

    def __init__(self, matrix: Mapping[ChangeCause, frozenset[ChangeCause]] | None = None) -> None:
        source = DEFAULT_RESET_MATRIX if matrix is None else matrix
        if set(source) != set(ChangeCause):
            raise ValueError("reset matrix must define every change cause")
        resolved = {cause: frozenset(source[cause]) for cause in ChangeCause}
        for cause, blocks in resolved.items():
            if not blocks <= set(SUBSTANTIVE_CAUSES):
                raise ValueError(f"reset matrix for {cause.value} names an unknown block")
        if resolved[ChangeCause.NOISE]:
            raise ValueError("noise cause must not reset any long-term parameter block")
        self._matrix = resolved

    def blocks_reset_by(self, cause: ChangeCause) -> frozenset[ChangeCause]:
        return self._matrix[cause]

    def resets(self, cause: ChangeCause, block: ChangeCause) -> bool:
        return block in self._matrix[cause]

    def blocks_reset_by_causes(self, causes: frozenset[ChangeCause]) -> frozenset[ChangeCause]:
        """Return the union reset operator for a simultaneous cause set."""

        if not causes or ChangeCause.NOISE in causes:
            raise ValueError("a substantive cause set must be non-empty and exclude noise")
        if not causes <= set(SUBSTANTIVE_CAUSES):
            raise ValueError("cause set contains an unknown substantive cause")
        return frozenset().union(*(self._matrix[cause] for cause in causes))


@dataclass(frozen=True, slots=True)
class _NormalNormalConfig:
    prior_mean: float
    prior_precision: float
    observation_variance: float
    noise_variance_inflation: float
    noise_indicator_low: float
    noise_indicator_high: float
    noise_indicator_variance: float


def _normal_logpdf(level: float, mean: float, variance: float) -> float:
    return -0.5 * (_LOG_2PI + log(variance) + (level - mean) ** 2 / variance)


@dataclass(frozen=True, slots=True)
class _Block:
    """Normal-Normal sufficient statistics for one block's current segment."""

    count: int
    total: float

    def posterior_mean(self, cfg: _NormalNormalConfig) -> float:
        strength = cfg.prior_precision + self.count
        return (cfg.prior_precision * cfg.prior_mean + self.total) / strength

    def predictive_logpdf(
        self, level: float, cfg: _NormalNormalConfig, *, variance_inflation: float = 1.0
    ) -> float:
        strength = cfg.prior_precision + self.count
        mean = (cfg.prior_precision * cfg.prior_mean + self.total) / strength
        variance = cfg.observation_variance * (1.0 + 1.0 / strength) * variance_inflation
        return _normal_logpdf(level, mean, variance)

    def absorb(self, level: float) -> _Block:
        return _Block(self.count + 1, self.total + level)


_FRESH_BLOCK = _Block(0, 0.0)


@dataclass(frozen=True, slots=True)
class CauseSignalFrame:
    """One time-local observation: a scalar level per cause in ``[0, 1]``.

    The observation/actor/habit levels are the substantive channels each block
    tracks.  The noise level is an *ambiguity indicator*: high when today's
    reading is likely a transient outlier rather than a regime change.
    """

    timestamp: datetime
    signals: Mapping[ChangeCause, float]

    def __post_init__(self) -> None:
        if set(self.signals) != set(ChangeCause):
            raise ValueError("signal frame must provide a level for every change cause")
        if any(not isfinite(level) or not 0.0 <= level <= 1.0 for level in self.signals.values()):
            raise ValueError("signal levels must be finite and in [0, 1]")


@dataclass(frozen=True, slots=True)
class JointCauseSnapshot:
    """Posterior state after absorbing one frame.

    Every field is computed from the *same* pruned-and-renormalized beam, so the
    run-length posterior, block references, and event probabilities are one
    coherent distribution.  Segment change and transient noise are reported
    separately; the three step-event masses partition the probability::

        continue_probability + segment_change_probability
            + transient_noise_probability == 1
    """

    timestamp: datetime
    #: P(run_length, segment cause) as a coupled, jointly normalized posterior.
    joint_run_length_cause_posterior: Mapping[tuple[int, ChangeCause], float]
    #: Exact P(run_length, active cause set), retaining simultaneous causes.
    joint_run_length_cause_set_posterior: Mapping[tuple[int, frozenset[ChangeCause]], float]
    #: P(this step continued the current segment).
    continue_probability: float
    #: P(this step began a new substantive segment: observation/actor/habit).
    segment_change_probability: float
    #: P(segment cause | a segment change happened); over substantive causes.
    #: These are inclusion marginals, so they may sum above one when a
    #: simultaneous multi-cause event has posterior mass.
    segment_cause_posterior: Mapping[ChangeCause, float]
    #: P(exact cause set | a substantive segment change happened this step).
    segment_cause_set_posterior: Mapping[frozenset[ChangeCause], float]
    #: P(exact cause set that created the currently active regime).
    active_regime_cause_set_posterior: Mapping[frozenset[ChangeCause], float]
    #: Inclusive marginal P(cause belongs to the active regime's cause set).
    active_regime_cause_posterior: Mapping[ChangeCause, float]
    #: P(this step was a transient outlier explained by the noise state).
    transient_noise_probability: float
    #: Beam-weighted per-block posterior means (substantive channels only).
    block_reference: Mapping[ChangeCause, float]
    #: Number of hypotheses retained after pruning (persistent state size).
    beam_size: int

    def __post_init__(self) -> None:
        scalar_probabilities = {
            "continue_probability": self.continue_probability,
            "segment_change_probability": self.segment_change_probability,
            "transient_noise_probability": self.transient_noise_probability,
        }
        mapped_probabilities = {
            "joint_run_length_cause_posterior": (self.joint_run_length_cause_posterior.values()),
            "joint_run_length_cause_set_posterior": (
                self.joint_run_length_cause_set_posterior.values()
            ),
            "segment_cause_posterior": self.segment_cause_posterior.values(),
            "segment_cause_set_posterior": self.segment_cause_set_posterior.values(),
            "active_regime_cause_set_posterior": (self.active_regime_cause_set_posterior.values()),
            "active_regime_cause_posterior": self.active_regime_cause_posterior.values(),
        }
        for name, probability in scalar_probabilities.items():
            if not isfinite(probability) or not 0.0 <= probability <= 1.0:
                raise ValueError(f"{name} must lie in [0, 1]")
        for name, probabilities in mapped_probabilities.items():
            if any(
                not isfinite(probability) or not 0.0 <= probability <= 1.0
                for probability in probabilities
            ):
                raise ValueError(f"{name} values must lie in [0, 1]")

    def marginal_cause_posterior(self) -> dict[ChangeCause, float]:
        marginal: dict[ChangeCause, float] = dict.fromkeys(ChangeCause, 0.0)
        for (_run_length, cause), probability in self.joint_run_length_cause_posterior.items():
            marginal[cause] += probability
        return marginal


@dataclass(frozen=True, slots=True)
class _Hypothesis:
    run_length: int
    active_causes: frozenset[ChangeCause]
    blocks: tuple[tuple[ChangeCause, _Block], ...]
    log_weight: float

    def block(self, cause: ChangeCause) -> _Block:
        for key, value in self.blocks:
            if key == cause:
                return value
        raise KeyError(cause)


@dataclass(frozen=True, slots=True)
class JointCauseFactorizedResult:
    snapshots: tuple[JointCauseSnapshot, ...]
    detected_change_time_by_cause: Mapping[ChangeCause, datetime | None]
    peak_change_cause_probability: Mapping[ChangeCause, float]
    model_version: str


def _cause_score(snapshot: JointCauseSnapshot, cause: ChangeCause) -> float:
    """Per-step detection score: segment mass for a segment cause, noise mass for noise."""

    if cause == ChangeCause.NOISE:
        return snapshot.transient_noise_probability
    return snapshot.segment_change_probability * snapshot.segment_cause_posterior.get(cause, 0.0)


def _renormalize_pairs(
    items: list[tuple[frozenset[ChangeCause] | ChangeCause | None, _Hypothesis]],
) -> list[tuple[frozenset[ChangeCause] | ChangeCause | None, _Hypothesis]]:
    """Return the same (event, hypothesis) pairs with log weights summing to 1."""

    peak = max(hypothesis.log_weight for _event, hypothesis in items)
    total = peak + log(sum(exp(hypothesis.log_weight - peak) for _event, hypothesis in items))
    return [
        (event, replace(hypothesis, log_weight=hypothesis.log_weight - total))
        for event, hypothesis in items
    ]


class JointCauseFactorizedBOCPD:
    """Coupled run-length x cause beam filter with a transient noise state."""

    def __init__(
        self,
        *,
        hazard_probability: float | Mapping[ChangeCause, float] = 0.05,
        prior_mean: float = 0.5,
        prior_precision: float = 1.0,
        observation_variance: float = 0.01,
        noise_variance_inflation: float = 36.0,
        noise_indicator_low: float = 0.1,
        noise_indicator_high: float = 0.8,
        noise_indicator_variance: float = 0.02,
        beam_width: int = 24,
        maximum_run_length: int = 256,
        maximum_simultaneous_causes: int = 2,
        simultaneous_hazard_scale: float = 0.25,
        reset_matrix: CauseResetMatrix | None = None,
        model_version: str = "joint-cause-factorized-bocpd@0.4",
    ) -> None:
        if isinstance(hazard_probability, Mapping):
            if set(hazard_probability) != set(ChangeCause):
                raise ValueError("hazard mapping must cover every change cause")
            hazards = {cause: float(hazard_probability[cause]) for cause in ChangeCause}
        else:
            hazards = {cause: float(hazard_probability) for cause in ChangeCause}
        if any(not 0.0 < hazard < 1.0 for hazard in hazards.values()):
            raise ValueError("every cause hazard must lie in (0, 1)")
        if sum(hazards.values()) >= 1.0:
            raise ValueError("total change hazard across causes must be below 1")
        if prior_precision <= 0.0:
            raise ValueError("prior_precision must be positive")
        if observation_variance <= 0.0:
            raise ValueError("observation_variance must be positive")
        if noise_variance_inflation < 1.0:
            raise ValueError("noise_variance_inflation must be at least 1")
        if noise_indicator_variance <= 0.0:
            raise ValueError("noise_indicator_variance must be positive")
        if beam_width < 1:
            raise ValueError("beam_width must be positive")
        if maximum_run_length < 1:
            raise ValueError("maximum_run_length must be positive")
        if not 1 <= maximum_simultaneous_causes <= len(SUBSTANTIVE_CAUSES):
            raise ValueError("maximum_simultaneous_causes is outside the cause space")
        if not 0.0 < simultaneous_hazard_scale <= 1.0:
            raise ValueError("simultaneous_hazard_scale must lie in (0, 1]")
        event_hazards: dict[frozenset[ChangeCause], float] = {
            frozenset({cause}): hazards[cause] for cause in SUBSTANTIVE_CAUSES
        }
        for size in range(2, maximum_simultaneous_causes + 1):
            for cause_tuple in combinations(SUBSTANTIVE_CAUSES, size):
                # Sparse prior: a joint event is possible but less likely than
                # each of its singleton explanations.
                event_hazards[frozenset(cause_tuple)] = simultaneous_hazard_scale ** (
                    size - 1
                ) * min(hazards[cause] for cause in cause_tuple)
        total_hazard = hazards[ChangeCause.NOISE] + sum(event_hazards.values())
        if total_hazard >= 1.0:
            raise ValueError("total singleton, simultaneous, and noise hazard must be below 1")
        self._hazards = hazards
        self._event_hazards = event_hazards
        self._config = _NormalNormalConfig(
            prior_mean,
            prior_precision,
            observation_variance,
            noise_variance_inflation,
            noise_indicator_low,
            noise_indicator_high,
            noise_indicator_variance,
        )
        self._beam_width = beam_width
        self._maximum_run_length = maximum_run_length
        self._reset_matrix = reset_matrix or CauseResetMatrix()
        self._model_version = model_version
        self.reset_online()

    @staticmethod
    def _fresh_beam() -> list[_Hypothesis]:
        return [
            _Hypothesis(
                run_length=0,
                active_causes=frozenset(),
                blocks=tuple((cause, _FRESH_BLOCK) for cause in SUBSTANTIVE_CAUSES),
                log_weight=0.0,
            )
        ]

    def reset_online(self) -> None:
        """Reset the prefix-online posterior without changing configuration."""

        self._online_beam = self._fresh_beam()
        self._online_last_timestamp: datetime | None = None

    def observe_online(self, frame: CauseSignalFrame) -> JointCauseSnapshot:
        """Advance exactly one posterior step for a new chronological frame."""

        if (
            self._online_last_timestamp is not None
            and frame.timestamp <= self._online_last_timestamp
        ):
            raise ValueError("online frames must have unique increasing timestamps")
        self._online_beam, snapshot = self._step(self._online_beam, frame)
        self._online_last_timestamp = frame.timestamp
        return snapshot

    def run(
        self,
        frames: Sequence[CauseSignalFrame],
        *,
        detection_threshold: float = 0.5,
        warmup_steps: int = 1,
    ) -> JointCauseFactorizedResult:
        if not frames:
            raise ValueError("joint CF-BOCPD requires at least one frame")
        if not 0.0 <= detection_threshold <= 1.0:
            raise ValueError("detection_threshold must lie in [0, 1]")
        if warmup_steps < 0 or warmup_steps >= len(frames):
            raise ValueError("warmup_steps must be in [0, len(frames))")
        timestamps = [frame.timestamp for frame in frames]
        if timestamps != sorted(timestamps) or len(timestamps) != len(set(timestamps)):
            raise ValueError("frames must have unique increasing timestamps")

        beam = self._fresh_beam()
        snapshots: list[JointCauseSnapshot] = []
        for frame in frames:
            beam, snapshot = self._step(beam, frame)
            snapshots.append(snapshot)

        eligible = snapshots[warmup_steps:]
        detected: dict[ChangeCause, datetime | None] = {}
        peak: dict[ChangeCause, float] = {}
        for cause in ChangeCause:
            detected[cause] = next(
                (
                    snapshot.timestamp
                    for snapshot in eligible
                    if _cause_score(snapshot, cause) >= detection_threshold
                ),
                None,
            )
            peak[cause] = max(_cause_score(snapshot, cause) for snapshot in eligible)
        return JointCauseFactorizedResult(
            snapshots=tuple(snapshots),
            detected_change_time_by_cause=detected,
            peak_change_cause_probability=peak,
            model_version=self._model_version,
        )

    def _step(
        self, beam: list[_Hypothesis], frame: CauseSignalFrame
    ) -> tuple[list[_Hypothesis], JointCauseSnapshot]:
        cfg = self._config
        signals = frame.signals
        noise_level = signals[ChangeCause.NOISE]
        hazard_total = self._hazards[ChangeCause.NOISE] + sum(self._event_hazards.values())
        log_no_change = log(1.0 - hazard_total)
        # Non-noise events expect a low ambiguity indicator; the noise state
        # expects a high one.
        low_indicator = _normal_logpdf(
            noise_level, cfg.noise_indicator_low, cfg.noise_indicator_variance
        )
        high_indicator = _normal_logpdf(
            noise_level, cfg.noise_indicator_high, cfg.noise_indicator_variance
        )

        children: list[tuple[frozenset[ChangeCause] | ChangeCause | None, _Hypothesis]] = []
        for hypothesis in beam:
            # Continuation: no change; every substantive block absorbs today.
            cont_loglik = low_indicator
            grown_blocks = []
            for cause in SUBSTANTIVE_CAUSES:
                block = hypothesis.block(cause)
                cont_loglik += block.predictive_logpdf(signals[cause], cfg)
                grown_blocks.append((cause, block.absorb(signals[cause])))
            children.append(
                (
                    None,
                    _Hypothesis(
                        run_length=min(hypothesis.run_length + 1, self._maximum_run_length),
                        active_causes=hypothesis.active_causes,
                        blocks=tuple(grown_blocks),
                        log_weight=hypothesis.log_weight + log_no_change + cont_loglik,
                    ),
                )
            )
            # Segment change of one or more causes: the union R_C resets only
            # the blocks owned by the selected sparse cause set.
            for changed_set, event_hazard in self._event_hazards.items():
                reset_blocks = self._reset_matrix.blocks_reset_by_causes(changed_set)
                change_loglik = low_indicator
                new_blocks = []
                for cause in SUBSTANTIVE_CAUSES:
                    base = _FRESH_BLOCK if cause in reset_blocks else hypothesis.block(cause)
                    change_loglik += base.predictive_logpdf(signals[cause], cfg)
                    new_blocks.append((cause, base.absorb(signals[cause])))
                children.append(
                    (
                        changed_set,
                        _Hypothesis(
                            run_length=0,
                            active_causes=changed_set,
                            blocks=tuple(new_blocks),
                            log_weight=hypothesis.log_weight + log(event_hazard) + change_loglik,
                        ),
                    )
                )
            # Transient noise: variance-inflated emission, no absorb, no reset.
            noise_loglik = high_indicator
            for cause in SUBSTANTIVE_CAUSES:
                noise_loglik += hypothesis.block(cause).predictive_logpdf(
                    signals[cause], cfg, variance_inflation=cfg.noise_variance_inflation
                )
            children.append(
                (
                    ChangeCause.NOISE,
                    _Hypothesis(
                        run_length=min(hypothesis.run_length + 1, self._maximum_run_length),
                        active_causes=hypothesis.active_causes,
                        blocks=hypothesis.blocks,
                        log_weight=hypothesis.log_weight
                        + log(self._hazards[ChangeCause.NOISE])
                        + noise_loglik,
                    ),
                )
            )

        # Fix 1: prune first, then do all posterior accounting on the single
        # renormalized surviving beam -- probabilities, run-length posterior, and
        # block references now come from exactly the same distribution.
        children.sort(key=lambda item: item[1].log_weight, reverse=True)
        survivors = _renormalize_pairs(children[: self._beam_width])
        snapshot = self._snapshot(survivors, frame.timestamp)
        beam = [hypothesis for _event, hypothesis in survivors]
        return beam, snapshot

    def _snapshot(
        self,
        survivors: list[tuple[frozenset[ChangeCause] | ChangeCause | None, _Hypothesis]],
        timestamp: datetime,
    ) -> JointCauseSnapshot:
        cfg = self._config
        joint: dict[tuple[int, ChangeCause], float] = {}
        joint_sets: dict[tuple[int, frozenset[ChangeCause]], float] = {}
        block_reference: dict[ChangeCause, float] = dict.fromkeys(SUBSTANTIVE_CAUSES, 0.0)
        continue_mass = 0.0
        segment_mass: dict[ChangeCause, float] = dict.fromkeys(SUBSTANTIVE_CAUSES, 0.0)
        segment_set_mass: dict[frozenset[ChangeCause], float] = {}
        active_set_mass: dict[frozenset[ChangeCause], float] = {}
        noise_mass = 0.0
        normalizer = sum(exp(hypothesis.log_weight) for _event, hypothesis in survivors)
        for event, hypothesis in survivors:
            probability = exp(hypothesis.log_weight) / normalizer
            set_key = (hypothesis.run_length, hypothesis.active_causes)
            joint_sets[set_key] = joint_sets.get(set_key, 0.0) + probability
            active_set_mass[hypothesis.active_causes] = (
                active_set_mass.get(hypothesis.active_causes, 0.0) + probability
            )
            # Backward-compatible single-cause projection. Multi-cause mass is
            # split evenly only in this legacy view; the exact set posterior
            # above retains the full semantics.
            projected_causes = hypothesis.active_causes or frozenset({ChangeCause.NOISE})
            for cause in projected_causes:
                key = (hypothesis.run_length, cause)
                joint[key] = joint.get(key, 0.0) + probability / len(projected_causes)
            for cause in SUBSTANTIVE_CAUSES:
                block_reference[cause] += probability * hypothesis.block(cause).posterior_mean(cfg)
            # Fix 2: continuation, substantive segment change, and transient
            # noise are three distinct step events that partition the mass.
            if event is None:
                continue_mass += probability
            elif event == ChangeCause.NOISE:
                noise_mass += probability
            else:
                assert isinstance(event, frozenset)
                segment_set_mass[event] = segment_set_mass.get(event, 0.0) + probability
                for cause in event:
                    segment_mass[cause] += probability

        joint_normalizer = sum(joint.values())
        joint = {
            key: min(1.0, max(0.0, probability / joint_normalizer))
            for key, probability in joint.items()
        }
        set_normalizer = sum(joint_sets.values())
        joint_sets = {
            key: min(1.0, max(0.0, probability / set_normalizer))
            for key, probability in joint_sets.items()
        }
        active_normalizer = sum(active_set_mass.values())
        active_set_mass = {
            causes: min(1.0, max(0.0, mass / active_normalizer))
            for causes, mass in active_set_mass.items()
        }
        # Exact event sets partition the segment mass. Inclusive per-cause
        # marginals intentionally do not: a two-cause event contributes to two
        # marginals but remains one event.
        event_normalizer = continue_mass + sum(segment_set_mass.values()) + noise_mass
        continue_mass = min(1.0, max(0.0, continue_mass / event_normalizer))
        noise_mass = min(1.0, max(0.0, noise_mass / event_normalizer))
        segment_mass = {
            cause: min(1.0, max(0.0, mass / event_normalizer))
            for cause, mass in segment_mass.items()
        }
        segment_change_probability = min(
            1.0,
            max(0.0, sum(segment_set_mass.values()) / event_normalizer),
        )
        segment_cause_posterior = (
            {
                cause: min(1.0, max(0.0, mass / segment_change_probability))
                for cause, mass in segment_mass.items()
            }
            if segment_change_probability > 0.0
            else {}
        )
        segment_cause_set_posterior = (
            {
                causes: min(1.0, max(0.0, mass / event_normalizer / segment_change_probability))
                for causes, mass in segment_set_mass.items()
            }
            if segment_change_probability > 0.0
            else {}
        )
        active_regime_cause_posterior = {
            cause: min(
                1.0,
                max(
                    0.0,
                    sum(mass for causes, mass in active_set_mass.items() if cause in causes),
                ),
            )
            for cause in SUBSTANTIVE_CAUSES
        }
        return JointCauseSnapshot(
            timestamp=timestamp,
            joint_run_length_cause_posterior=joint,
            joint_run_length_cause_set_posterior=joint_sets,
            continue_probability=continue_mass,
            segment_change_probability=segment_change_probability,
            segment_cause_posterior=segment_cause_posterior,
            segment_cause_set_posterior=segment_cause_set_posterior,
            active_regime_cause_set_posterior=active_set_mass,
            active_regime_cause_posterior=active_regime_cause_posterior,
            transient_noise_probability=noise_mass,
            block_reference=block_reference,
            beam_size=len(survivors),
        )
