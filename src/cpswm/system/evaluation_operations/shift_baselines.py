"""Transparent diagnostic baselines for shift-cause attribution."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import timedelta
from statistics import fmean
from typing import ClassVar

from cpswm.contracts import ObservationOutcome
from cpswm.world_model.habits_transitions.cause_factorized_bocpd import (
    CauseEvidenceFrame,
    CauseFactorizedBOCPD,
    ChangeCause,
)

from .d0_shift_scenarios import D0ShiftCaseInput, D0VisibleSimulationRun
from .online_shift_attribution import OnlineShiftCaseInput, OnlineShiftPrediction
from .shift_attribution import ShiftCause, ShiftCausePrediction


class LoggedPolicyThenLocationBaseline:
    """Attribute logged policy changes first, then any location change to habit.

    This intentionally simple baseline exposes the exact failure that motivates
    actor evidence and cause-aware inference: a guest-induced relocation is
    observationally indistinguishable from an owner habit change when the input
    contains locations but no person observations.
    """

    model_version = "logged-policy-then-location@0.1"

    def predict(self, model_input: D0ShiftCaseInput) -> ShiftCausePrediction:
        control_propensities = tuple(
            item.selection_probability for item in model_input.control_run.observation_opportunities
        )
        shifted_propensities = tuple(
            item.selection_probability for item in model_input.shifted_run.observation_opportunities
        )
        if control_propensities != shifted_propensities:
            cause = ShiftCause.OBSERVATION_POLICY
        elif self._detected_location_counts(
            model_input.control_run, model_input.change_time
        ) != self._detected_location_counts(model_input.shifted_run, model_input.change_time):
            cause = ShiftCause.OWNER_HABIT_REGIME
        else:
            cause = ShiftCause.UNRESOLVED

        evidence_ids = tuple(
            str(item.metadata.record_id)
            for item in (
                *model_input.shifted_run.observation_opportunities,
                *model_input.shifted_run.detection_results,
            )
            if item.metadata.recorded_time >= model_input.change_time
        )
        return ShiftCausePrediction(
            case_id=model_input.case_id,
            posterior={cause: 1.0},
            model_version=self.model_version,
            evidence_record_ids=evidence_ids,
        )

    @staticmethod
    def _detected_location_counts(run: D0VisibleSimulationRun, change_time) -> Counter[str]:
        return Counter(
            str(result.detected_location_id)
            for result in run.detection_results
            if result.metadata.recorded_time >= change_time
            and result.detected_location_id is not None
        )


class LoggedPolicyActorLocationBaseline(LoggedPolicyThenLocationBaseline):
    """Add an explicit actor-posterior comparison to the location baseline."""

    model_version = "logged-policy-actor-location@0.1"

    def predict(self, model_input: D0ShiftCaseInput) -> ShiftCausePrediction:
        control_propensities = tuple(
            item.selection_probability for item in model_input.control_run.observation_opportunities
        )
        shifted_propensities = tuple(
            item.selection_probability for item in model_input.shifted_run.observation_opportunities
        )
        if control_propensities != shifted_propensities:
            cause = ShiftCause.OBSERVATION_POLICY
        elif self._actor_mixture_changed(model_input):
            cause = ShiftCause.ACTOR_MIXTURE
        elif self._detected_location_counts(
            model_input.control_run, model_input.change_time
        ) != self._detected_location_counts(model_input.shifted_run, model_input.change_time):
            cause = ShiftCause.OWNER_HABIT_REGIME
        else:
            cause = ShiftCause.UNRESOLVED

        evidence_ids = tuple(
            str(item.metadata.record_id)
            for item in (
                *model_input.shifted_run.observation_opportunities,
                *model_input.shifted_run.detection_results,
                *model_input.shifted_actor_evidence,
            )
            if item.metadata.recorded_time >= model_input.change_time
        )
        return ShiftCausePrediction(
            case_id=model_input.case_id,
            posterior={cause: 1.0},
            model_version=self.model_version,
            evidence_record_ids=evidence_ids,
        )

    @staticmethod
    def _actor_mixture_changed(model_input: D0ShiftCaseInput) -> bool:
        if not model_input.shifted_actor_evidence:
            return False
        target_key = str(model_input.target_person_id)
        target_mass = sum(
            item.actor_posterior.get(target_key, 0.0) for item in model_input.shifted_actor_evidence
        )
        non_target_mass = sum(
            sum(
                probability
                for actor, probability in item.actor_posterior.items()
                if actor not in {target_key, "unknown_actor"}
            )
            for item in model_input.shifted_actor_evidence
        )
        return non_target_mass > target_mass


class OnlineCauseFactorizedBOCPDBaseline:
    """Transparent robot-visible CF-BOCPD baseline for held-out streams."""

    model_version = "online-cause-factorized-bocpd@0.1"

    _CAUSE_MAP: ClassVar[dict[ChangeCause, ShiftCause]] = {
        ChangeCause.OBSERVATION: ShiftCause.OBSERVATION_POLICY,
        ChangeCause.ACTOR: ShiftCause.ACTOR_MIXTURE,
        ChangeCause.HABIT: ShiftCause.OWNER_HABIT_REGIME,
        ChangeCause.NOISE: ShiftCause.TRANSIENT_NOISE,
    }

    def __init__(
        self,
        *,
        warmup_days: int = 2,
        hazard_probability: float = 0.05,
        detection_threshold: float = 0.5,
    ) -> None:
        if warmup_days < 1:
            raise ValueError("warmup_days must be positive")
        if not 0.0 <= detection_threshold <= 1.0:
            raise ValueError("detection_threshold must lie in [0, 1]")
        self._warmup_days = warmup_days
        self._hazard_probability = hazard_probability
        self._detection_threshold = detection_threshold

    def predict(self, model_input: OnlineShiftCaseInput) -> OnlineShiftPrediction:
        frames = self.evidence_frames(model_input)
        result = CauseFactorizedBOCPD(
            hazard_probability=self._hazard_probability,
            model_version=self.model_version,
        ).run(
            frames,
            detection_threshold=self._detection_threshold,
            minimum_observations=self._warmup_days + 1,
        )
        detected_times = [
            timestamp
            for timestamp in result.detected_change_time_by_cause.values()
            if timestamp is not None
        ]
        return OnlineShiftPrediction(
            case_id=model_input.case_id,
            predicted_change_time=min(detected_times) if detected_times else None,
            cause_probabilities={
                self._CAUSE_MAP[cause]: probability
                for cause, probability in result.peak_changepoint_probability_by_cause.items()
            },
            model_version=self.model_version,
        )

    def evidence_frames(self, model_input: OnlineShiftCaseInput) -> tuple[CauseEvidenceFrame, ...]:
        run = model_input.observation_stream
        result_by_opportunity = {
            result.observation_opportunity_id: result for result in run.detection_results
        }
        actor_by_detection = defaultdict(list)
        for evidence in model_input.actor_evidence:
            actor_by_detection[evidence.source_detection_result_id].append(evidence)

        daily_metrics: list[dict[str, object]] = []
        for day_index in range(run.duration_days):
            day_start = run.start_time + timedelta(days=day_index)
            day_end = day_start + timedelta(days=1)
            opportunities = tuple(
                opportunity
                for opportunity in run.observation_opportunities
                if day_start <= opportunity.opportunity_time < day_end
            )
            if not opportunities:
                continue
            results = tuple(
                result_by_opportunity[item.metadata.record_id] for item in opportunities
            )
            observation_propensity = fmean(
                item.selection_probability
                * item.p_visible_given_state
                * item.p_detect_given_visible
                for item in opportunities
            )
            actor_values: list[float] = []
            location_counts: Counter[str] = Counter()
            for result in results:
                evidence_items = actor_by_detection.get(result.metadata.record_id, ())
                owner_mass = 1.0
                if evidence_items:
                    owner_mass = fmean(
                        item.actor_posterior.get(str(model_input.target_person_id), 0.0)
                        for item in evidence_items
                    )
                    actor_values.append(1.0 - owner_mass)
                if result.detected_location_id is not None:
                    location_counts[str(result.detected_location_id)] += owner_mass
            total_location_mass = sum(location_counts.values())
            location_distribution = (
                {
                    location: count / total_location_mass
                    for location, count in location_counts.items()
                }
                if total_location_mass > 0.0
                else {}
            )
            daily_metrics.append(
                {
                    "timestamp": day_start,
                    "observation": observation_propensity,
                    "actor": fmean(actor_values) if actor_values else None,
                    "habit": location_distribution,
                    "noise": sum(
                        result.outcome == ObservationOutcome.AMBIGUOUS for result in results
                    )
                    / len(results),
                    "evidence_ids": tuple(
                        str(item.metadata.record_id) for item in (*opportunities, *results)
                    )
                    + tuple(
                        str(item.metadata.record_id)
                        for result in results
                        for item in actor_by_detection.get(result.metadata.record_id, ())
                    ),
                }
            )

        if len(daily_metrics) <= self._warmup_days:
            raise ValueError("online stream is too short for the configured warmup")
        warmup = daily_metrics[: self._warmup_days]
        reference_observation = fmean(float(item["observation"]) for item in warmup)
        actor_warmup = [float(item["actor"]) for item in warmup if item["actor"] is not None]
        reference_actor = fmean(actor_warmup) if actor_warmup else None
        reference_noise = fmean(float(item["noise"]) for item in warmup)
        reference_habit = self._mean_distribution(
            tuple(item["habit"] for item in warmup)  # type: ignore[arg-type]
        )

        frames: list[CauseEvidenceFrame] = []
        for index, item in enumerate(daily_metrics):
            if index < self._warmup_days:
                distances = {cause: 0.0 for cause in ChangeCause}
            else:
                actor_value = item["actor"]
                distances = {
                    ChangeCause.OBSERVATION: min(
                        1.0,
                        abs(float(item["observation"]) - reference_observation)
                        / max(reference_observation, 1.0 - reference_observation, 0.05),
                    ),
                    ChangeCause.ACTOR: (
                        0.0
                        if actor_value is None or reference_actor is None
                        else min(1.0, abs(float(actor_value) - reference_actor))
                    ),
                    ChangeCause.HABIT: self._total_variation(
                        item["habit"],
                        reference_habit,  # type: ignore[arg-type]
                    ),
                    ChangeCause.NOISE: min(1.0, abs(float(item["noise"]) - reference_noise)),
                }
            frames.append(
                CauseEvidenceFrame(
                    timestamp=item["timestamp"],  # type: ignore[arg-type]
                    continuation_likelihoods={
                        cause: 0.01 + 0.99 * (1.0 - distance)
                        for cause, distance in distances.items()
                    },
                    changepoint_likelihoods={
                        cause: 0.01 + 0.99 * distance for cause, distance in distances.items()
                    },
                    evidence_record_ids=tuple(dict.fromkeys(item["evidence_ids"])),  # type: ignore[arg-type]
                )
            )
        return tuple(frames)

    @staticmethod
    def _mean_distribution(
        distributions: tuple[dict[str, float], ...],
    ) -> dict[str, float]:
        support = set().union(*(distribution.keys() for distribution in distributions))
        averaged = {
            key: fmean(distribution.get(key, 0.0) for distribution in distributions)
            for key in support
        }
        total = sum(averaged.values())
        return {key: value / total for key, value in averaged.items()} if total else {}

    @staticmethod
    def _total_variation(left: dict[str, float], right: dict[str, float]) -> float:
        support = set(left) | set(right)
        return 0.5 * sum(abs(left.get(key, 0.0) - right.get(key, 0.0)) for key in support)


class OnlineOrdinaryBOCPDBaseline:
    """Single-run-length BOCPD control over the shared online evidence frames.

    Unlike CF-BOCPD, this control detects one global change point. Cause scores
    are read only from the evidence frame at the global posterior peak, so it
    cannot maintain independent change histories for observation, actor, habit,
    and noise channels.
    """

    model_version = "online-ordinary-bocpd@0.1"

    def __init__(
        self,
        *,
        warmup_days: int = 2,
        hazard_probability: float = 0.05,
        detection_threshold: float = 0.5,
        maximum_run_length: int = 256,
    ) -> None:
        if warmup_days < 1:
            raise ValueError("warmup_days must be positive")
        if not 0.0 < hazard_probability < 1.0:
            raise ValueError("ordinary BOCPD hazard must lie in (0, 1)")
        if not 0.0 <= detection_threshold <= 1.0:
            raise ValueError("detection_threshold must lie in [0, 1]")
        if maximum_run_length < 1:
            raise ValueError("maximum_run_length must be positive")
        self._warmup_days = warmup_days
        self._hazard_probability = hazard_probability
        self._detection_threshold = detection_threshold
        self._maximum_run_length = maximum_run_length

    def predict(self, model_input: OnlineShiftCaseInput) -> OnlineShiftPrediction:
        frame_adapter = OnlineCauseFactorizedBOCPDBaseline(
            warmup_days=self._warmup_days,
            hazard_probability=self._hazard_probability,
            detection_threshold=self._detection_threshold,
        )
        frames = frame_adapter.evidence_frames(model_input)
        posterior = {0: 1.0}
        snapshots: list[tuple[CauseEvidenceFrame, float]] = []
        for frame in frames:
            changepoint_likelihood = max(frame.changepoint_likelihoods.values())
            continuation_likelihood = min(frame.continuation_likelihoods.values())
            next_posterior = {
                0: sum(posterior.values()) * self._hazard_probability * changepoint_likelihood
            }
            for run_length, probability in posterior.items():
                next_length = min(run_length + 1, self._maximum_run_length)
                next_posterior[next_length] = next_posterior.get(next_length, 0.0) + (
                    probability * (1.0 - self._hazard_probability) * continuation_likelihood
                )
            total = sum(next_posterior.values())
            if total <= 0.0:
                raise ValueError("ordinary BOCPD update produced zero posterior mass")
            posterior = {
                run_length: probability / total
                for run_length, probability in next_posterior.items()
            }
            snapshots.append((frame, posterior[0]))

        eligible = snapshots[self._warmup_days :]
        if not eligible:
            raise ValueError("online stream is too short for the configured warmup")
        detected_time = next(
            (
                frame.timestamp
                for frame, probability in eligible
                if probability >= self._detection_threshold
            ),
            None,
        )
        peak_frame, _ = max(eligible, key=lambda item: item[1])
        cause_probabilities = {
            OnlineCauseFactorizedBOCPDBaseline._CAUSE_MAP[cause]: (
                peak_frame.changepoint_likelihoods[cause]
                / (
                    peak_frame.changepoint_likelihoods[cause]
                    + peak_frame.continuation_likelihoods[cause]
                )
            )
            for cause in ChangeCause
        }
        return OnlineShiftPrediction(
            case_id=model_input.case_id,
            predicted_change_time=detected_time,
            cause_probabilities=cause_probabilities,
            model_version=self.model_version,
        )
