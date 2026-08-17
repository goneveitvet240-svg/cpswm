"""Transparent diagnostic baselines for shift-cause attribution."""

from __future__ import annotations

from collections import Counter

from .d0_shift_scenarios import D0ShiftCaseInput, D0VisibleSimulationRun
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
