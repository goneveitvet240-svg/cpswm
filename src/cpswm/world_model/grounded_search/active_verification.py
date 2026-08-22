"""Expected-information-gain observation selection baseline."""

from __future__ import annotations

from math import isfinite, log2
from uuid import UUID

from cpswm.contracts.grounded_search import (
    ActiveObservationPlan,
    ObservationActionCandidate,
    ObservationActionScore,
    ObservationPlannerObjective,
)


def _entropy(probabilities: list[float]) -> float:
    return -sum(value * log2(value) for value in probabilities if value > 0.0)


class InformationGainPlanner:
    """Rank observation actions by expected entropy reduction minus costs."""

    def __init__(
        self,
        *,
        information_value_weight: float = 1.0,
        motion_cost_weight: float = 1.0,
        time_cost_weight: float = 1.0,
        interruption_cost_weight: float = 1.0,
        privacy_cost_weight: float = 1.0,
        safety_cost_weight: float = 1.0,
    ) -> None:
        self.information_value_weight = information_value_weight
        self.motion_cost_weight = motion_cost_weight
        self.time_cost_weight = time_cost_weight
        self.interruption_cost_weight = interruption_cost_weight
        self.privacy_cost_weight = privacy_cost_weight
        self.safety_cost_weight = safety_cost_weight

    def select(
        self,
        prior: dict[UUID, float],
        actions: tuple[ObservationActionCandidate, ...],
        *,
        minimum_net_value: float = 0.0,
    ) -> ActiveObservationPlan:
        if not actions:
            return ActiveObservationPlan(
                scores=(), should_act=False, stop_reason="no_candidate_observation_action"
            )
        if abs(sum(prior.values()) - 1.0) > 1e-6:
            raise ValueError("prior must sum to one")

        prior_entropy = _entropy(list(prior.values()))
        scores: list[ObservationActionScore] = []
        for action in actions:
            action_hypotheses = set(next(iter(action.outcome_likelihoods.values())))
            if action_hypotheses != set(prior):
                raise ValueError(
                    "every observation action must score exactly the current hypotheses"
                )
            expected_entropy = 0.0
            for likelihoods in action.outcome_likelihoods.values():
                p_outcome = sum(
                    prior[hypothesis_id] * likelihood
                    for hypothesis_id, likelihood in likelihoods.items()
                )
                if p_outcome <= 0.0:
                    continue
                posterior = [
                    prior[hypothesis_id] * likelihood / p_outcome
                    for hypothesis_id, likelihood in likelihoods.items()
                ]
                expected_entropy += p_outcome * _entropy(posterior)
            information_gain = max(0.0, prior_entropy - expected_entropy)
            total_cost = (
                self.motion_cost_weight * action.motion_cost
                + self.time_cost_weight * action.time_cost
                + self.interruption_cost_weight * action.interruption_cost
                + self.privacy_cost_weight * action.privacy_cost
                + self.safety_cost_weight * action.safety_cost
            )
            scores.append(
                ObservationActionScore(
                    action_id=action.action_id,
                    expected_information_gain=information_gain,
                    expected_posterior_entropy=expected_entropy,
                    total_cost=total_cost,
                    net_value=self.information_value_weight * information_gain - total_cost,
                )
            )

        ranked = tuple(sorted(scores, key=lambda item: item.net_value, reverse=True))
        best = ranked[0]
        if best.net_value <= minimum_net_value:
            return ActiveObservationPlan(
                scores=ranked,
                should_act=False,
                stop_reason="no_observation_has_positive_net_information_value",
            )
        return ActiveObservationPlan(
            selected_action_id=best.action_id,
            scores=ranked,
            should_act=True,
            stop_reason="selected_maximum_net_information_value",
        )


class ActionUtilityPlanner:
    """Select verification by expected downstream decision utility minus costs."""

    def __init__(
        self,
        *,
        motion_cost_weight: float = 1.0,
        time_cost_weight: float = 1.0,
        interruption_cost_weight: float = 1.0,
        privacy_cost_weight: float = 1.0,
        safety_cost_weight: float = 1.0,
    ) -> None:
        weights = (
            motion_cost_weight,
            time_cost_weight,
            interruption_cost_weight,
            privacy_cost_weight,
            safety_cost_weight,
        )
        if any(weight < 0.0 for weight in weights):
            raise ValueError("utility planner cost weights must be non-negative")
        self.motion_cost_weight = motion_cost_weight
        self.time_cost_weight = time_cost_weight
        self.interruption_cost_weight = interruption_cost_weight
        self.privacy_cost_weight = privacy_cost_weight
        self.safety_cost_weight = safety_cost_weight

    def select(
        self,
        prior: dict[UUID, float],
        actions: tuple[ObservationActionCandidate, ...],
        *,
        terminal_decision_utilities: dict[UUID, dict[UUID, float]],
        minimum_net_utility: float = 0.0,
    ) -> ActiveObservationPlan:
        """Maximize expected value of sample information under explicit costs.

        ``terminal_decision_utilities[d][h]`` is the utility of taking terminal
        decision ``d`` when hypothesis ``h`` is true. This makes retrieval gain,
        abstention, and task failure costs explicit instead of using entropy as
        a proxy for usefulness.
        """

        if not prior or abs(sum(prior.values()) - 1.0) > 1e-6:
            raise ValueError("prior must be non-empty and sum to one")
        hypothesis_ids = set(prior)
        if not terminal_decision_utilities:
            raise ValueError("terminal_decision_utilities cannot be empty")
        if any(set(row) != hypothesis_ids for row in terminal_decision_utilities.values()):
            raise ValueError("every terminal decision must score all current hypotheses")
        if any(
            not isfinite(utility)
            for row in terminal_decision_utilities.values()
            for utility in row.values()
        ):
            raise ValueError("terminal decision utilities must be finite")
        if not actions:
            return ActiveObservationPlan(
                scores=(), should_act=False, stop_reason="no_candidate_observation_action"
            )

        baseline_decision, baseline_utility = self._best_terminal_decision(
            prior,
            terminal_decision_utilities,
        )
        del baseline_decision
        scores: list[ObservationActionScore] = []
        prior_entropy = _entropy(list(prior.values()))
        for action in actions:
            action_hypotheses = set(next(iter(action.outcome_likelihoods.values())))
            if action_hypotheses != hypothesis_ids:
                raise ValueError(
                    "every observation action must score exactly the current hypotheses"
                )
            expected_entropy = 0.0
            expected_decision_utility = 0.0
            decisions_by_outcome: dict[str, UUID] = {}
            for outcome, likelihoods in action.outcome_likelihoods.items():
                p_outcome = sum(
                    prior[hypothesis_id] * likelihood
                    for hypothesis_id, likelihood in likelihoods.items()
                )
                if p_outcome <= 0.0:
                    continue
                posterior = {
                    hypothesis_id: prior[hypothesis_id] * likelihood / p_outcome
                    for hypothesis_id, likelihood in likelihoods.items()
                }
                expected_entropy += p_outcome * _entropy(list(posterior.values()))
                decision_id, outcome_utility = self._best_terminal_decision(
                    posterior,
                    terminal_decision_utilities,
                )
                decisions_by_outcome[outcome] = decision_id
                expected_decision_utility += p_outcome * outcome_utility

            expected_gain = max(0.0, expected_decision_utility - baseline_utility)
            total_cost = self._total_cost(action)
            scores.append(
                ObservationActionScore(
                    action_id=action.action_id,
                    expected_information_gain=max(0.0, prior_entropy - expected_entropy),
                    expected_posterior_entropy=expected_entropy,
                    total_cost=total_cost,
                    net_value=expected_gain - total_cost,
                    objective=ObservationPlannerObjective.DECISION_UTILITY,
                    baseline_decision_utility=baseline_utility,
                    expected_decision_utility=expected_decision_utility,
                    expected_utility_gain=expected_gain,
                    recommended_terminal_decision_by_outcome=decisions_by_outcome,
                )
            )

        ranked = tuple(sorted(scores, key=lambda score: (-score.net_value, str(score.action_id))))
        best = ranked[0]
        if best.net_value <= minimum_net_utility:
            return ActiveObservationPlan(
                scores=ranked,
                should_act=False,
                stop_reason="no_observation_has_positive_net_decision_utility",
            )
        return ActiveObservationPlan(
            selected_action_id=best.action_id,
            scores=ranked,
            should_act=True,
            stop_reason="selected_maximum_net_decision_utility",
        )

    def _total_cost(self, action: ObservationActionCandidate) -> float:
        return (
            self.motion_cost_weight * action.motion_cost
            + self.time_cost_weight * action.time_cost
            + self.interruption_cost_weight * action.interruption_cost
            + self.privacy_cost_weight * action.privacy_cost
            + self.safety_cost_weight * action.safety_cost
        )

    @staticmethod
    def _best_terminal_decision(
        posterior: dict[UUID, float],
        utilities: dict[UUID, dict[UUID, float]],
    ) -> tuple[UUID, float]:
        scored = {
            decision_id: sum(
                posterior[hypothesis_id] * utility
                for hypothesis_id, utility in utility_by_hypothesis.items()
            )
            for decision_id, utility_by_hypothesis in utilities.items()
        }
        decision_id = sorted(scored, key=lambda item: (-scored[item], str(item)))[0]
        return decision_id, scored[decision_id]
