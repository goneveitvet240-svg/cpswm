"""Likelihood-aware projection of uncertain M27 execution feedback."""

from __future__ import annotations

from cpswm.contracts.grounded_search import (
    ActionOutcomeLikelihoodModel,
    ExecutionFeedbackRecord,
    FeedbackBeliefUpdate,
)


class ExecutionFeedbackProjector:
    """Convert action outcomes into derived evidence, never certain facts."""

    def update_target_presence(
        self,
        prior_target_present: float,
        feedback: ExecutionFeedbackRecord,
        model: ActionOutcomeLikelihoodModel,
    ) -> FeedbackBeliefUpdate:
        feedback = ExecutionFeedbackRecord.model_validate(feedback.model_dump(mode="python"))
        model = ActionOutcomeLikelihoodModel.model_validate(model.model_dump(mode="python"))
        if feedback.action_type != model.action_type:
            raise ValueError("feedback and outcome model action types must match")
        if not 0.0 <= prior_target_present <= 1.0:
            raise ValueError("presence prior must be a probability")
        realized_outcomes = {
            outcome
            for outcome, probability in feedback.outcome_distribution.items()
            if probability > 0.0
        }
        modeled_outcomes = set(model.p_outcome_given_target_present)
        if not realized_outcomes.issubset(modeled_outcomes):
            missing = sorted(outcome.value for outcome in realized_outcomes - modeled_outcomes)
            raise ValueError(
                f"outcome model must cover every realized feedback outcome; missing={missing}"
            )

        p_feedback_present = sum(
            feedback.outcome_distribution.get(outcome, 0.0) * likelihood
            for outcome, likelihood in model.p_outcome_given_target_present.items()
        )
        p_feedback_absent = sum(
            feedback.outcome_distribution.get(outcome, 0.0) * likelihood
            for outcome, likelihood in model.p_outcome_given_target_absent.items()
        )
        numerator = prior_target_present * p_feedback_present
        denominator = numerator + (1.0 - prior_target_present) * p_feedback_absent
        posterior = prior_target_present if denominator == 0.0 else numerator / denominator
        likelihood_ratio = (
            None if p_feedback_absent == 0.0 else p_feedback_present / p_feedback_absent
        )
        return FeedbackBeliefUpdate(
            feedback_record_id=feedback.metadata.record_id,
            prior_target_present=prior_target_present,
            posterior_target_present=posterior,
            likelihood_ratio=likelihood_ratio,
            outcome_model_version=model.model_version,
        )
