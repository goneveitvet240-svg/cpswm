"""Unified retrieval, uncertainty, action, and recovery metrics for direction three."""

from __future__ import annotations

from dataclasses import dataclass
from math import log
from uuid import UUID

from cpswm.contracts import ResolutionStatus


@dataclass(frozen=True, slots=True)
class DirectionThreeMetricCase:
    case_id: str
    posterior_by_candidate_id: dict[UUID, float]
    unknown_candidate_id: UUID
    true_target_candidate_id: UUID | None
    target_is_unknown: bool
    resolution_status: ResolutionStatus
    expected_resolution_status: ResolutionStatus
    known_target_out_of_support: bool = False
    selected_target_candidate_id: UUID | None = None
    picked_object_candidate_id: UUID | None = None
    asked_user: bool = False
    identity_switch_count: int = 0
    task_success: bool = False
    recovery_required: bool = False
    recovery_success: bool = False
    motion_cost: float = 0.0
    time_cost: float = 0.0
    interruption_cost: float = 0.0
    privacy_cost: float = 0.0
    safety_cost: float = 0.0

    def __post_init__(self) -> None:
        if not self.case_id.strip() or not self.posterior_by_candidate_id:
            raise ValueError("metric case id and posterior must be non-empty")
        if set(self.posterior_by_candidate_id) == {self.unknown_candidate_id}:
            raise ValueError("metric cases require at least one known candidate")
        if self.unknown_candidate_id not in self.posterior_by_candidate_id:
            raise ValueError("metric posterior must include explicit unknown")
        if abs(sum(self.posterior_by_candidate_id.values()) - 1.0) > 1e-6:
            raise ValueError("metric posterior must sum to one")
        if any(value < 0.0 or value > 1.0 for value in self.posterior_by_candidate_id.values()):
            raise ValueError("metric posterior probabilities must be in [0, 1]")
        if self.target_is_unknown:
            if self.true_target_candidate_id is not None or self.known_target_out_of_support:
                raise ValueError("true unknown cannot also carry a known target")
        elif self.true_target_candidate_id is None:
            raise ValueError("known metric truth requires a target id")
        elif self.known_target_out_of_support:
            if self.true_target_candidate_id in self.posterior_by_candidate_id:
                raise ValueError("out-of-support target must not appear in posterior support")
        elif self.true_target_candidate_id not in self.posterior_by_candidate_id:
            raise ValueError("known in-support target must appear in posterior support")
        if self.identity_switch_count < 0:
            raise ValueError("identity switch count must be non-negative")
        if self.picked_object_candidate_id is not None:
            if self.picked_object_candidate_id == self.unknown_candidate_id:
                raise ValueError("a physical pickup cannot target the explicit unknown candidate")
            if self.picked_object_candidate_id not in self.posterior_by_candidate_id:
                raise ValueError("picked object must be in the candidate support")
        costs = (
            self.motion_cost,
            self.time_cost,
            self.interruption_cost,
            self.privacy_cost,
            self.safety_cost,
        )
        if any(value < 0.0 for value in costs):
            raise ValueError("metric costs must be non-negative")
        if self.recovery_success and not self.recovery_required:
            raise ValueError("recovery success requires a recovery-required case")

    @property
    def evaluation_target_id(self) -> UUID:
        if self.known_target_out_of_support:
            raise ValueError("known out-of-support cases have no fusion evaluation target")
        target = (
            self.unknown_candidate_id if self.target_is_unknown else self.true_target_candidate_id
        )
        if target is None:
            raise ValueError("evaluation target ID is required for supported cases")
        return target

    @property
    def support_status(self) -> str:
        if self.target_is_unknown:
            return "true_unknown"
        if self.known_target_out_of_support:
            return "known_out_of_support"
        return "known_in_support"


def _binary_auroc(labels: list[int], scores: list[float]) -> float | None:
    positives = sum(labels)
    negatives = len(labels) - positives
    if positives == 0 or negatives == 0:
        return None
    favorable = 0.0
    for label, score in zip(labels, scores, strict=True):
        if not label:
            continue
        for other_label, other_score in zip(labels, scores, strict=True):
            if other_label:
                continue
            favorable += float(score > other_score) + 0.5 * float(score == other_score)
    return favorable / (positives * negatives)


def _average_precision(labels: list[int], scores: list[float]) -> float | None:
    positives = sum(labels)
    negatives = len(labels) - positives
    if positives == 0 or negatives == 0:
        return None
    ranked = sorted(
        zip(labels, scores, strict=True),
        key=lambda item: item[1],
        reverse=True,
    )
    true_positives = 0
    precision_sum = 0.0
    for rank, (label, _) in enumerate(ranked, start=1):
        if label:
            true_positives += 1
            precision_sum += true_positives / rank
    return precision_sum / positives


def _ece(confidences: list[float], correctness: list[bool], bins: int) -> float:
    total = len(confidences)
    error = 0.0
    for index in range(bins):
        lower = index / bins
        upper = (index + 1) / bins
        members = [
            position
            for position, confidence in enumerate(confidences)
            if lower <= confidence < upper or (index == bins - 1 and confidence == 1.0)
        ]
        if not members:
            continue
        accuracy = sum(correctness[position] for position in members) / len(members)
        confidence = sum(confidences[position] for position in members) / len(members)
        error += len(members) / total * abs(accuracy - confidence)
    return error


def evaluate_direction_three_metrics(
    cases: tuple[DirectionThreeMetricCase, ...],
    *,
    recall_k: int = 5,
    ece_bins: int = 10,
    selective_thresholds: tuple[float, ...] = (0.0, 0.5, 0.7, 0.9),
) -> dict[str, object]:
    if not cases:
        raise ValueError("direction-three metrics require at least one case")
    if recall_k <= 0 or ece_bins <= 0:
        raise ValueError("recall_k and ece_bins must be positive")
    if any(not 0.0 <= threshold <= 1.0 for threshold in selective_thresholds):
        raise ValueError("selective thresholds must be in [0, 1]")

    fusion_cases = tuple(case for case in cases if not case.known_target_out_of_support)
    if not fusion_cases:
        raise ValueError(
            "conditional fusion metrics require at least one in-support or unknown case"
        )
    ranks: list[int] = []
    confidences: list[float] = []
    correctness: list[bool] = []
    nll_values: list[float] = []
    brier_values: list[float] = []
    unknown_labels: list[int] = []
    unknown_scores: list[float] = []
    per_case: list[dict[str, object]] = []

    for case in cases:
        ranked = sorted(
            case.posterior_by_candidate_id,
            key=lambda candidate: (
                -case.posterior_by_candidate_id[candidate],
                str(candidate),
            ),
        )
        prediction = ranked[0]
        confidence = case.posterior_by_candidate_id[prediction]
        if case.known_target_out_of_support:
            rank = None
            correct = None
            target_probability = None
            brier = None
        else:
            target = case.evaluation_target_id
            rank = ranked.index(target) + 1
            correct = prediction == target
            target_probability = max(case.posterior_by_candidate_id[target], 1e-12)
            brier = sum(
                (probability - (1.0 if candidate == target else 0.0)) ** 2
                for candidate, probability in case.posterior_by_candidate_id.items()
            )
            ranks.append(rank)
            confidences.append(confidence)
            correctness.append(correct)
            nll_values.append(-log(target_probability))
            brier_values.append(brier)
            unknown_labels.append(int(case.target_is_unknown))
            unknown_scores.append(case.posterior_by_candidate_id[case.unknown_candidate_id])
        per_case.append(
            {
                "case_id": case.case_id,
                "support_status": case.support_status,
                "rank": rank,
                "top1_correct": correct,
                "confidence": confidence,
                "target_probability": target_probability,
                "known_target_misidentification": (
                    not case.target_is_unknown
                    and case.picked_object_candidate_id is not None
                    and case.picked_object_candidate_id != case.true_target_candidate_id
                ),
                "unknown_target_false_pick": (
                    case.target_is_unknown and case.picked_object_candidate_id is not None
                ),
            }
        )

    selective_curve = []
    for threshold in selective_thresholds:
        accepted = [
            index for index, confidence in enumerate(confidences) if confidence >= threshold
        ]
        coverage = len(accepted) / len(fusion_cases)
        risk = (
            None
            if not accepted
            else 1.0 - sum(correctness[index] for index in accepted) / len(accepted)
        )
        selective_curve.append(
            {"confidence_threshold": threshold, "coverage": coverage, "risk": risk}
        )

    known_cases = [case for case in cases if not case.target_is_unknown]
    known_in_support_cases = [case for case in known_cases if not case.known_target_out_of_support]
    unknown_cases = [case for case in cases if case.target_is_unknown]
    recovery_cases = [case for case in cases if case.recovery_required]
    known_misidentifications = sum(
        case.picked_object_candidate_id is not None
        and case.picked_object_candidate_id != case.true_target_candidate_id
        for case in known_cases
    )
    unknown_false_picks = sum(case.picked_object_candidate_id is not None for case in unknown_cases)
    unsafe_picks = known_misidentifications + unknown_false_picks
    return {
        "schema_name": "cpswm.DirectionThreeMetricReport",
        "schema_version": "0.2.0",
        "case_count": len(cases),
        "retrieval": {
            "known_target_retrieval_recall": len(known_in_support_cases) / max(1, len(known_cases)),
            "known_target_count": len(known_cases),
            "known_out_of_support_count": sum(
                case.known_target_out_of_support for case in known_cases
            ),
        },
        "conditional_fusion": {
            "case_count": len(fusion_cases),
            "recall_at_1": sum(rank <= 1 for rank in ranks) / len(ranks),
            f"recall_at_{recall_k}": sum(rank <= recall_k for rank in ranks) / len(ranks),
            "mrr": sum(1.0 / rank for rank in ranks) / len(ranks),
        },
        "open_set": {
            "unknown_auroc": _binary_auroc(unknown_labels, unknown_scores),
            "unknown_auprc": _average_precision(unknown_labels, unknown_scores),
        },
        "calibration": {
            "ece": _ece(confidences, correctness, ece_bins),
            "mean_brier": sum(brier_values) / len(brier_values),
            "mean_nll": sum(nll_values) / len(nll_values),
        },
        "decision": {
            "ambiguous_detection_accuracy": sum(
                case.resolution_status == case.expected_resolution_status for case in fusion_cases
            )
            / len(fusion_cases),
            "selective_risk_coverage": selective_curve,
            "known_target_misidentification_rate": known_misidentifications
            / max(1, len(known_cases)),
            "unknown_target_false_pick_rate": unknown_false_picks / max(1, len(unknown_cases)),
            "overall_unsafe_pick_rate": unsafe_picks / len(cases),
            "clarification_rate": sum(case.asked_user for case in cases) / len(cases),
            "unnecessary_clarification_rate": sum(
                case.asked_user and case.expected_resolution_status == ResolutionStatus.RESOLVED
                for case in cases
            )
            / len(cases),
        },
        "identity": {
            "identity_switch_count": sum(case.identity_switch_count for case in cases),
            "identity_switch_rate": sum(case.identity_switch_count > 0 for case in cases)
            / len(cases),
        },
        "task": {
            "task_success_rate": sum(case.task_success for case in cases) / len(cases),
            "failure_recovery_success_rate": (
                None
                if not recovery_cases
                else sum(case.recovery_success for case in recovery_cases) / len(recovery_cases)
            ),
        },
        "cost": {
            "mean_motion_cost": sum(case.motion_cost for case in cases) / len(cases),
            "mean_time_cost": sum(case.time_cost for case in cases) / len(cases),
            "mean_interruption_cost": sum(case.interruption_cost for case in cases) / len(cases),
            "mean_privacy_cost": sum(case.privacy_cost for case in cases) / len(cases),
            "mean_safety_cost": sum(case.safety_cost for case in cases) / len(cases),
        },
        "cases": per_case,
    }
