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
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from math import log

from .project_one_dataset import ProjectOneTruthSet
from .project_one_methods import StepPrediction
from .project_one_protocol import ProjectOneDecision

__all__ = ["ProjectOneMetrics", "compute_metrics", "paired_step_differences"]

_EPSILON = 1e-12


@dataclass(frozen=True, slots=True)
class ProjectOneMetrics:
    """One arm's score on one stream."""

    method: str
    stream_id: str
    step_count: int
    expected_false_candidate_rate: float
    false_switch_rate: float
    anomaly_detection_rate: float
    habit_change_confirmation_rate: float
    mean_detection_delay: float | None
    false_regime_count: int
    paired_margin: float
    log_loss: float
    brier: float

    def as_dict(self) -> Mapping[str, object]:
        return asdict(self)


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
    confirmation_window: int = 3,
) -> ProjectOneMetrics:
    """Score one arm's step-level predictions against the evaluator truth."""

    if not predictions:
        raise ValueError("cannot score an empty prediction sequence")

    change_indices = [
        index
        for index, prediction in enumerate(predictions)
        if (record := truth.get(prediction.event_id)) is not None and record.true_change_point
    ]
    near_change = {
        index + offset for index in change_indices for offset in range(-1, confirmation_window + 1)
    }

    quiet_alarm = quiet_total = 0
    quiet_switch = 0
    anomaly_detected = anomaly_total = 0
    log_loss_total = brier_total = scored = 0.0
    anomaly_signals: list[float] = []
    expected_signals: list[float] = []
    seen_regimes: set[str] = set()
    false_regimes = 0

    for index, prediction in enumerate(predictions):
        record = truth.get(prediction.event_id)
        expected = record.expected_location if record is not None else None
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
        is_anomaly = record is not None and record.true_change_cause in {"transient", "guest"}
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

    return ProjectOneMetrics(
        method=method,
        stream_id=stream_id,
        step_count=len(predictions),
        expected_false_candidate_rate=(quiet_alarm / quiet_total) if quiet_total else 0.0,
        false_switch_rate=(quiet_switch / quiet_total) if quiet_total else 0.0,
        anomaly_detection_rate=(anomaly_detected / anomaly_total) if anomaly_total else 0.0,
        habit_change_confirmation_rate=(confirmed / len(change_indices) if change_indices else 0.0),
        mean_detection_delay=(sum(delays) / len(delays)) if delays else None,
        false_regime_count=false_regimes,
        paired_margin=(
            (sum(anomaly_signals) / len(anomaly_signals) if anomaly_signals else 0.0)
            - (sum(expected_signals) / len(expected_signals) if expected_signals else 0.0)
        ),
        log_loss=(log_loss_total / scored) if scored else 0.0,
        brier=(brier_total / scored) if scored else 0.0,
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
