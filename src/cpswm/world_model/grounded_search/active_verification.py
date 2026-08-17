"""Expected-information-gain observation selection baseline."""

from __future__ import annotations

from math import log2
from uuid import UUID

from cpswm.contracts.grounded_search import (
    ActiveObservationPlan,
    ObservationActionCandidate,
    ObservationActionScore,
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
