"""Contracts and metrics for the D0 shift-cause death test.

The evaluator lives on the benchmark side of the ground-truth boundary.  A
candidate world model only emits a posterior over causes; it never receives the
label used here for evaluation.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import StrEnum
from math import isclose, log

from pydantic import Field, model_validator

from cpswm.contracts.base import ContractModel, Probability


class ShiftCause(StrEnum):
    """Competing explanations for an apparent change in observed habits."""

    OBSERVATION_POLICY = "observation_policy"
    ACTOR_MIXTURE = "actor_mixture"
    IDENTITY_ASSOCIATION = "identity_association"
    OWNER_HABIT_REGIME = "owner_habit_regime"
    TRANSIENT_NOISE = "transient_noise"
    UNRESOLVED = "unresolved"


class IdentifiabilityStatus(StrEnum):
    """What the robot-visible input can distinguish without intervention."""

    IDENTIFIABLE = "identifiable"
    PARTIALLY_IDENTIFIABLE = "partially_identifiable"
    NON_IDENTIFIABLE = "non_identifiable"


class ShiftCausePrediction(ContractModel):
    """Robot-visible output required from every D0 candidate method."""

    case_id: str = Field(min_length=1)
    posterior: dict[ShiftCause, Probability] = Field(min_length=1)
    model_version: str = Field(min_length=1)
    evidence_record_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_posterior(self) -> ShiftCausePrediction:
        if not isclose(sum(self.posterior.values()), 1.0, rel_tol=0.0, abs_tol=1e-6):
            raise ValueError("shift-cause posterior probabilities must sum to 1")
        return self

    @property
    def predicted_cause(self) -> ShiftCause:
        """Return a deterministic MAP cause, including explicit abstention."""

        return sorted(
            self.posterior,
            key=lambda cause: (-self.posterior[cause], cause.value),
        )[0]


class ShiftAttributionCase(ContractModel):
    """One evaluator-only D0 label paired with a model prediction."""

    case_id: str = Field(min_length=1)
    true_cause: ShiftCause
    identifiability_status: IdentifiabilityStatus = IdentifiabilityStatus.IDENTIFIABLE
    acceptable_cause_set: tuple[ShiftCause, ...] = ()
    intervention_available: bool = False
    prediction: ShiftCausePrediction

    @model_validator(mode="after")
    def validate_case_binding(self) -> ShiftAttributionCase:
        if self.true_cause == ShiftCause.UNRESOLVED:
            raise ValueError("D0 ground truth must identify a concrete shift cause")
        if self.prediction.case_id != self.case_id:
            raise ValueError("prediction case_id does not match evaluation case")
        causes = self.accepted_causes
        if ShiftCause.UNRESOLVED in causes:
            raise ValueError("acceptable_cause_set contains only concrete latent causes")
        if len(causes) != len(set(causes)):
            raise ValueError("acceptable_cause_set must not contain duplicates")
        if self.true_cause not in causes:
            raise ValueError("acceptable_cause_set must include the latent true cause")
        if self.identifiability_status == IdentifiabilityStatus.IDENTIFIABLE and causes != (
            self.true_cause,
        ):
            raise ValueError("identifiable cases require one acceptable true cause")
        if self.identifiability_status != IdentifiabilityStatus.IDENTIFIABLE and len(causes) < 2:
            raise ValueError("non-identifiable cases require an equivalence class")
        return self

    @property
    def accepted_causes(self) -> tuple[ShiftCause, ...]:
        return self.acceptable_cause_set or (self.true_cause,)

    @property
    def scoring_target(self) -> dict[ShiftCause, float]:
        """Return the benchmark's declared target distribution.

        A structurally non-identifiable case is scored against explicit
        abstention.  A partially identifiable equivalence class is represented
        by a uniform distribution over its accepted concrete causes.
        """

        if self.identifiability_status == IdentifiabilityStatus.NON_IDENTIFIABLE:
            return {ShiftCause.UNRESOLVED: 1.0}
        if self.identifiability_status == IdentifiabilityStatus.PARTIALLY_IDENTIFIABLE:
            mass = 1.0 / len(self.accepted_causes)
            return {cause: mass for cause in self.accepted_causes}
        return {self.true_cause: 1.0}


class RiskCoveragePoint(ContractModel):
    confidence_threshold: Probability
    coverage: Probability
    selective_risk: Probability
    covered_count: int = Field(ge=0)


class ShiftAttributionReport(ContractModel):
    """Decision-facing summary for a batch of paired D0 cases."""

    sample_count: int = Field(ge=1)
    identifiable_sample_count: int = Field(ge=0)
    non_identifiable_sample_count: int = Field(ge=0)
    shift_cause_accuracy: Probability
    shift_cause_macro_f1: Probability
    acceptable_cause_accuracy: Probability
    epistemic_decision_accuracy: Probability
    unresolved_rate: Probability
    correct_abstention_rate: Probability
    incorrect_abstention_rate: Probability
    log_loss: float = Field(ge=0.0)
    brier_score: float = Field(ge=0.0)
    selective_coverage: Probability
    selective_risk: Probability
    risk_coverage_curve: tuple[RiskCoveragePoint, ...] = Field(min_length=1)
    false_owner_habit_change_rate: Probability
    observation_to_habit_leakage: Probability
    actor_mixture_to_owner_leakage: Probability
    confusion_counts: dict[str, int]


class ShiftAttributionEvaluator:
    """Evaluate whether a method separates observation, actor, and habit shifts."""

    def evaluate(self, cases: Sequence[ShiftAttributionCase]) -> ShiftAttributionReport:
        if not cases:
            raise ValueError("at least one shift-attribution case is required")
        case_ids = [case.case_id for case in cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("shift-attribution case ids must be unique")

        pairs = [(case.true_cause, case.prediction.predicted_cause) for case in cases]
        correct = sum(truth == predicted for truth, predicted in pairs)
        unresolved = sum(predicted == ShiftCause.UNRESOLVED for _, predicted in pairs)
        concrete_truth = sorted({truth for truth, _ in pairs}, key=lambda cause: cause.value)

        f1_scores = [self._f1_for_cause(pairs, cause) for cause in concrete_truth]
        confusion = self._confusion_counts(pairs)
        non_habit = [pair for pair in pairs if pair[0] != ShiftCause.OWNER_HABIT_REGIME]
        observation = [pair for pair in pairs if pair[0] == ShiftCause.OBSERVATION_POLICY]
        actor = [pair for pair in pairs if pair[0] == ShiftCause.ACTOR_MIXTURE]
        identifiable = [
            case
            for case in cases
            if case.identifiability_status == IdentifiabilityStatus.IDENTIFIABLE
        ]
        non_identifiable = [
            case
            for case in cases
            if case.identifiability_status != IdentifiabilityStatus.IDENTIFIABLE
        ]
        accepted_correct = sum(
            case.prediction.predicted_cause in case.accepted_causes for case in cases
        )
        epistemic_correct = sum(self._epistemic_correct(case) for case in cases)
        covered = [
            case for case in cases if case.prediction.predicted_cause != ShiftCause.UNRESOLVED
        ]
        selective_risk = self._selective_risk(covered)

        return ShiftAttributionReport(
            sample_count=len(cases),
            identifiable_sample_count=len(identifiable),
            non_identifiable_sample_count=len(non_identifiable),
            shift_cause_accuracy=correct / len(cases),
            shift_cause_macro_f1=sum(f1_scores) / len(f1_scores),
            acceptable_cause_accuracy=accepted_correct / len(cases),
            epistemic_decision_accuracy=epistemic_correct / len(cases),
            unresolved_rate=unresolved / len(cases),
            correct_abstention_rate=self._case_prediction_rate(
                non_identifiable, ShiftCause.UNRESOLVED
            ),
            incorrect_abstention_rate=self._case_prediction_rate(
                identifiable, ShiftCause.UNRESOLVED
            ),
            log_loss=self._log_loss(cases),
            brier_score=self._brier_score(cases),
            selective_coverage=len(covered) / len(cases),
            selective_risk=selective_risk,
            risk_coverage_curve=self._risk_coverage_curve(cases),
            false_owner_habit_change_rate=self._prediction_rate(
                non_habit, ShiftCause.OWNER_HABIT_REGIME
            ),
            observation_to_habit_leakage=self._prediction_rate(
                observation, ShiftCause.OWNER_HABIT_REGIME
            ),
            actor_mixture_to_owner_leakage=self._prediction_rate(
                actor, ShiftCause.OWNER_HABIT_REGIME
            ),
            confusion_counts=confusion,
        )

    @staticmethod
    def _epistemic_correct(case: ShiftAttributionCase) -> bool:
        predicted = case.prediction.predicted_cause
        if case.identifiability_status == IdentifiabilityStatus.NON_IDENTIFIABLE:
            return predicted == ShiftCause.UNRESOLVED
        if case.identifiability_status == IdentifiabilityStatus.PARTIALLY_IDENTIFIABLE:
            return predicted == ShiftCause.UNRESOLVED or predicted in case.accepted_causes
        return predicted == case.true_cause

    @staticmethod
    def _log_loss(cases: Sequence[ShiftAttributionCase]) -> float:
        epsilon = 1e-12
        total = 0.0
        for case in cases:
            total -= sum(
                target_probability * log(max(case.prediction.posterior.get(cause, 0.0), epsilon))
                for cause, target_probability in case.scoring_target.items()
            )
        return total / len(cases)

    @staticmethod
    def _brier_score(cases: Sequence[ShiftAttributionCase]) -> float:
        causes = tuple(ShiftCause)
        return sum(
            sum(
                (case.prediction.posterior.get(cause, 0.0) - case.scoring_target.get(cause, 0.0))
                ** 2
                for cause in causes
            )
            for case in cases
        ) / len(cases)

    def _risk_coverage_curve(
        self, cases: Sequence[ShiftAttributionCase]
    ) -> tuple[RiskCoveragePoint, ...]:
        points = []
        for threshold in (0.0, 0.25, 0.5, 0.75, 0.9):
            covered = [
                case
                for case in cases
                if case.prediction.predicted_cause != ShiftCause.UNRESOLVED
                and max(
                    (
                        probability
                        for cause, probability in case.prediction.posterior.items()
                        if cause != ShiftCause.UNRESOLVED
                    ),
                    default=0.0,
                )
                >= threshold
            ]
            points.append(
                RiskCoveragePoint(
                    confidence_threshold=threshold,
                    coverage=len(covered) / len(cases),
                    selective_risk=self._selective_risk(covered),
                    covered_count=len(covered),
                )
            )
        return tuple(points)

    @staticmethod
    def _selective_risk(cases: Sequence[ShiftAttributionCase]) -> float:
        if not cases:
            return 0.0
        errors = sum(case.prediction.predicted_cause not in case.accepted_causes for case in cases)
        return errors / len(cases)

    @staticmethod
    def _case_prediction_rate(
        cases: Sequence[ShiftAttributionCase], predicted_cause: ShiftCause
    ) -> float:
        if not cases:
            return 0.0
        return sum(case.prediction.predicted_cause == predicted_cause for case in cases) / len(
            cases
        )

    @staticmethod
    def _f1_for_cause(pairs: Sequence[tuple[ShiftCause, ShiftCause]], cause: ShiftCause) -> float:
        true_positive = sum(truth == cause and predicted == cause for truth, predicted in pairs)
        false_positive = sum(truth != cause and predicted == cause for truth, predicted in pairs)
        false_negative = sum(truth == cause and predicted != cause for truth, predicted in pairs)
        denominator = 2 * true_positive + false_positive + false_negative
        return (2 * true_positive / denominator) if denominator else 0.0

    @staticmethod
    def _prediction_rate(
        pairs: Sequence[tuple[ShiftCause, ShiftCause]], predicted_cause: ShiftCause
    ) -> float:
        if not pairs:
            return 0.0
        return sum(predicted == predicted_cause for _, predicted in pairs) / len(pairs)

    @staticmethod
    def _confusion_counts(
        pairs: Sequence[tuple[ShiftCause, ShiftCause]],
    ) -> Mapping[str, int]:
        counts: dict[str, int] = {}
        for truth, predicted in pairs:
            key = f"{truth.value}->{predicted.value}"
            counts[key] = counts.get(key, 0) + 1
        return counts
