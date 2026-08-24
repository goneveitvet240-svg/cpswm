"""Project-one metrics, computed from per-step predictions (阶段 4).

Every metric here is derived from the step-level record, never from a running
average an arm reported about itself.  That is what makes the paired analysis
in 阶段 6 possible: the same event index can be compared across arms, and a
per-case difference can be saved instead of only an overall mean.

The metric set follows the 阶段 6 table.  Two conventions matter:

* An **anomaly step** is one where the observed location differs from the
  truth's ``expected_location``.  It is the step an arm ought to react to.
* A **quiet step** is one that is neither an anomaly nor within the confirmation
  window of a true change point.  False alarms are counted only on quiet steps,
  so an arm is never punished for reacting near a real event.

**A step with no truth is scored by nothing at all.**  It used to fall through
into the quiet population, which meant an unlabelled event counted as "should
have stayed silent" -- a quiet negative.  On synthetic streams truth is total
and the bug never fired; on a real log, where most events carry no annotation,
it would have manufactured a false-alarm rate out of ignorance and punished
whichever arm reacted most.  Unscored steps are now excluded from every
population and reported as :attr:`ProjectOneMetrics.truth_coverage`, so a run
over mostly-unlabelled data cannot be mistaken for a fully scored one.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from math import log

from .project_one_dataset import ANOMALY_CAUSES, ProjectOneTruthSet
from .project_one_methods import StepPrediction
from .project_one_protocol import ProjectOneDecision

__all__ = ["ProjectOneMetrics", "compute_metrics", "paired_step_differences"]

_EPSILON = 1e-12


@dataclass(frozen=True, slots=True)
class ProjectOneMetrics:
    """One arm's score on one stream, split by what the data can support.

    Three tiers, and the split is the point.  A raw household log carries no
    change annotation at all, so reporting ``false_switch_rate = 0.0`` there
    would read as "this arm produced no false alarms" when it actually means
    "nothing could be checked".  Metrics whose denominator does not exist are
    ``None``, never zero.

    1. **Self-supervised** -- scored against the *next observation*, which every
       log has by definition.  This is the whole of the raw-data track.
    2. **Habit-truth** -- scored against ``expected_location``.  Needs a truth
       file saying where the habit *should* have put the object.
    3. **Change-label** -- false switches, disturbance detection, confirmation.
       Needs planted or annotated change points; available on the
       semi-synthetic track and nowhere else.
    """

    method: str
    stream_id: str
    step_count: int

    # -- tier 1: always available -------------------------------------------
    #: Was the next observed location the arm's most likely one?
    top1_accuracy: float
    #: Was it in the arm's top ``k``?  ``k`` is recorded in :attr:`top_k`.
    topk_accuracy: float
    top_k: int
    #: Log loss and Brier against the location actually observed next.
    observed_log_loss: float
    observed_brier: float

    # -- tier 3: need change labels -----------------------------------------
    expected_false_candidate_rate: float | None
    false_switch_rate: float | None
    anomaly_detection_rate: float | None
    habit_change_confirmation_rate: float | None
    mean_detection_delay: float | None
    false_regime_count: int | None
    paired_margin: float | None

    # -- tier 2: need habit truth -------------------------------------------
    log_loss: float | None
    brier: float | None

    # -- accounting ----------------------------------------------------------
    #: Steps that carried a truth entry and could therefore be scored at tier 2.
    scored_steps: int = 0
    #: Steps with no truth entry.  Excluded from every rate above -- never
    #: counted as quiet, never counted as an anomaly, never counted as a change.
    unscored_steps: int = 0
    #: Steps that actually carry a change point or a cause.  Informational: a
    #: fully annotated stream may legitimately contain zero.
    change_label_count: int = 0
    #: Whether the truth **set** declares that it annotates changes at all.
    #: This, not the count, decides whether tier 3 is reportable.
    change_labels_declared: bool = False

    @property
    def truth_coverage(self) -> float:
        """Fraction of steps the evaluator could say anything about."""

        return self.scored_steps / self.step_count if self.step_count else 0.0

    @property
    def has_change_labels(self) -> bool:
        return self.change_labels_declared

    @property
    def track(self) -> str:
        """Which evaluation track this stream's annotation supports."""

        if self.change_labels_declared:
            return "change_labelled"
        return "raw_real_data" if self.scored_steps == 0 else "habit_truth_only"

    def as_dict(self) -> Mapping[str, object]:
        return {
            **asdict(self),
            "truth_coverage": self.truth_coverage,
            "has_change_labels": self.has_change_labels,
            "track": self.track,
        }


def _is_alarm(prediction: StepPrediction) -> bool:
    return prediction.decision in (
        ProjectOneDecision.HABIT_CHANGE,
        ProjectOneDecision.SHORT_TERM_DISTURBANCE,
    )


def compute_metrics(
    *,
    method: str,
    stream_id: str,
    predictions: Sequence[StepPrediction],
    truth: ProjectOneTruthSet,
    observed: Mapping[str, str],
    confirmation_window: int = 3,
    require_full_truth: bool = False,
    top_k: int = 3,
) -> ProjectOneMetrics:
    """Score one arm's step-level predictions.

    ``observed`` maps event id to the location that was actually seen next, in
    the arm's own candidate vocabulary.  It is required, not optional: it is the
    only target a raw household log can supply, and the whole raw-data track is
    scored against it.  Passing the *unresolved* location for an open-set arm
    would score it against a slot it was never offered.

    ``require_full_truth`` makes a missing truth entry an error rather than an
    exclusion.  Synthetic runs should set it: there, truth is generated
    alongside the data, so a gap means the generator and the runner disagree
    about event ids, and silently scoring 90% of the stream would hide that.
    """

    if not predictions:
        raise ValueError("cannot score an empty prediction sequence")
    if top_k < 1:
        raise ValueError("top_k must be at least 1")

    records = [truth.get(prediction.event_id) for prediction in predictions]
    scorable = [index for index, record in enumerate(records) if record is not None]
    unscored = len(predictions) - len(scorable)
    if require_full_truth and unscored:
        missing = [
            predictions[index].event_id for index, record in enumerate(records) if record is None
        ]
        raise ValueError(
            f"{unscored} of {len(predictions)} steps have no truth entry "
            f"(first: {missing[0]!r}); pass require_full_truth=False to score a "
            "partially annotated stream"
        )

    change_indices = [
        index
        for index in scorable
        if (record := records[index]) is not None and record.true_change_point
    ]
    near_change = {
        index + offset for index in change_indices for offset in range(-1, confirmation_window + 1)
    }

    change_labels = sum(
        1
        for record in records
        if record is not None and (record.true_change_point or record.true_change_cause is not None)
    )

    quiet_alarm = quiet_total = 0
    quiet_switch = 0
    anomaly_detected = anomaly_total = 0
    log_loss_total = brier_total = scored = 0.0
    anomaly_signals: list[float] = []
    expected_signals: list[float] = []
    seen_regimes: set[str] = set()
    false_regimes = 0

    # -- tier 1: against the next observation, which every log supplies -------
    top1_hits = topk_hits = observed_scored = 0
    observed_log_loss_total = observed_brier_total = 0.0
    for prediction in predictions:
        target = observed.get(prediction.event_id)
        if target is None:
            continue
        probabilities = prediction.predicted_location_probabilities
        observed_scored += 1
        probability = max(_EPSILON, probabilities.get(target, 0.0))
        observed_log_loss_total += -log(probability)
        observed_brier_total += sum(
            (value - (1.0 if name == target else 0.0)) ** 2 for name, value in probabilities.items()
        )
        # Ties broken by name so no arm gains from dictionary order.
        ranked = sorted(probabilities.items(), key=lambda item: (-item[1], item[0]))
        if ranked and ranked[0][0] == target:
            top1_hits += 1
        if any(name == target for name, _ in ranked[:top_k]):
            topk_hits += 1

    for index, prediction in enumerate(predictions):
        record = records[index]
        if record is None:
            # No truth, no opinion.  Falling through to the quiet population
            # here is the quiet-negative bug: it would score an unlabelled event
            # as one the arm should have stayed silent on.
            continue
        expected = record.expected_location
        observed_probabilities = prediction.predicted_location_probabilities

        if expected is not None:
            probability = max(_EPSILON, observed_probabilities.get(expected, 0.0))
            log_loss_total += -log(probability)
            brier_total += sum(
                (value - (1.0 if name == expected else 0.0)) ** 2
                for name, value in observed_probabilities.items()
            )
            scored += 1.0

        # An anomaly is defined by the *data*, not by the arm: the object was
        # seen somewhere the true habit would not have put it, and the truth
        # attributes that to a transient cause rather than a new regime.
        # ANOMALY_CAUSES is shared with every truth producer, so an injector
        # cannot spell its cause privately and score as nothing.
        is_anomaly = record.true_change_cause in ANOMALY_CAUSES
        if is_anomaly:
            anomaly_total += 1
            anomaly_signals.append(prediction.habit_signal)
            if _is_alarm(prediction):
                anomaly_detected += 1
        elif index not in near_change:
            quiet_total += 1
            expected_signals.append(prediction.habit_signal)
            if _is_alarm(prediction):
                quiet_alarm += 1
            if prediction.decision is ProjectOneDecision.HABIT_CHANGE:
                quiet_switch += 1

        regime = prediction.predicted_regime_id
        if regime is not None and regime not in seen_regimes:
            seen_regimes.add(regime)
            if index not in near_change and len(seen_regimes) > 1:
                false_regimes += 1

    delays: list[int] = []
    confirmed = 0
    for index in change_indices:
        for offset in range(0, confirmation_window + 1):
            probe = index + offset
            if probe < len(predictions) and (
                predictions[probe].decision is ProjectOneDecision.HABIT_CHANGE
            ):
                confirmed += 1
                delays.append(offset)
                break

    # Tier 3 exists only where change annotation does -- declared by the
    # producer, not counted from the data.  ``None`` rather than ``0.0``: on a
    # raw log, "no false switches" and "nothing was checkable" are opposite
    # readings, and zero would print as the flattering one.
    labelled = truth.carries_change_labels

    return ProjectOneMetrics(
        method=method,
        stream_id=stream_id,
        step_count=len(predictions),
        top1_accuracy=(top1_hits / observed_scored) if observed_scored else 0.0,
        topk_accuracy=(topk_hits / observed_scored) if observed_scored else 0.0,
        top_k=top_k,
        observed_log_loss=((observed_log_loss_total / observed_scored) if observed_scored else 0.0),
        observed_brier=(observed_brier_total / observed_scored) if observed_scored else 0.0,
        expected_false_candidate_rate=(
            ((quiet_alarm / quiet_total) if quiet_total else 0.0) if labelled else None
        ),
        false_switch_rate=(
            ((quiet_switch / quiet_total) if quiet_total else 0.0) if labelled else None
        ),
        anomaly_detection_rate=(
            ((anomaly_detected / anomaly_total) if anomaly_total else 0.0) if labelled else None
        ),
        habit_change_confirmation_rate=(
            ((confirmed / len(change_indices)) if change_indices else 0.0) if labelled else None
        ),
        mean_detection_delay=(sum(delays) / len(delays)) if delays else None,
        false_regime_count=false_regimes if labelled else None,
        paired_margin=(
            (
                (sum(anomaly_signals) / len(anomaly_signals) if anomaly_signals else 0.0)
                - (sum(expected_signals) / len(expected_signals) if expected_signals else 0.0)
            )
            if labelled
            else None
        ),
        log_loss=(log_loss_total / scored) if scored else None,
        brier=(brier_total / scored) if scored else None,
        scored_steps=len(scorable),
        unscored_steps=unscored,
        change_label_count=change_labels,
        change_labels_declared=labelled,
    )


def paired_step_differences(
    reference: Sequence[StepPrediction],
    candidate: Sequence[StepPrediction],
) -> tuple[Mapping[str, float], ...]:
    """Per-event differences between two arms on the same stream.

    Saving these — rather than only the two means — is what lets 阶段 6 report a
    paired interval instead of a difference of averages.
    """

    if len(reference) != len(candidate):
        raise ValueError("paired arms must have the same number of steps")
    rows: list[Mapping[str, float]] = []
    for left, right in zip(reference, candidate, strict=True):
        if left.event_id != right.event_id:
            raise ValueError("paired arms must be aligned on event_id")
        rows.append(
            {
                "habit_signal": right.habit_signal - left.habit_signal,
                "change_probability": right.change_probability - left.change_probability,
            }
        )
    return tuple(rows)
