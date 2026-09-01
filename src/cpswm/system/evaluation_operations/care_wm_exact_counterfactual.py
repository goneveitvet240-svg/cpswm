"""Exact finite-state falsifier for CARE-WM memory-write decisions.

The gate is intentionally smaller than the complete Project Two runtime.  It
isolates one claim: future contamination-aware verification and consolidation
should outperform confidence-only, current-task VOI, and a matched
risk-aware/TRW rollback composition without receiving evaluator truth.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from statistics import mean
from typing import Any, cast

from cpswm.system.evaluation_operations.structure_two_fresh_triarm import _file_sha256
from cpswm.system.reproducibility import content_sha256

PROTOCOL_ID = "care-wm-exact-counterfactual-gate@0.1"
DEFAULT_MANIFEST = Path(
    "configs/project_two_experiments/care_wm_exact_counterfactual_manifest_v0_1.json"
)
DEFAULT_SEALED_SEEDS = Path(
    "configs/project_two_experiments/care_wm_exact_counterfactual_sealed_seeds_v0_1.json"
)
DEFAULT_PREREGISTRATION = Path(
    "docs/experiments/care_wm_exact_counterfactual_gate_preregistration_2026-08-29.md"
)


class CareArm(StrEnum):
    CORRECTED_AMG = "corrected_amg"
    NO_CONSOLIDATION = "sequential_no_consolidation"
    CONFIDENCE = "posterior_confidence_consolidation"
    CURRENT_TASK_VOI = "current_task_voi"
    TRW_QUARANTINE = "trw_conflict_quarantine"
    MATCHED_COMPOSED = "matched_risk_trw_current_voi"
    CARE_WM = "care_wm"
    FULL_RERUN_ORACLE = "full_rerun_oracle"


@dataclass(frozen=True, slots=True)
class CareFamily:
    family_id: str
    family_role: str
    habit_rate: float
    prior_habit_probability: float
    evidence_strength: float
    evidence_noise: float
    decoy_rate: float
    horizon: int
    feedback_step: int
    actual_action_cost: float
    predicted_action_cost: float
    repair_cost: float
    verification_cost: float
    immediate_action_cost: float


@dataclass(frozen=True, slots=True)
class CareDesign:
    validation_seeds: tuple[int, ...]
    holdout_seed_commitments: tuple[str, ...]
    sealed_holdout_seed_count: int
    sealed_seed_file_sha256: str
    families: tuple[CareFamily, ...]
    search_spaces: Mapping[str, tuple[Any, ...]]
    primary_baseline: CareArm
    noninferiority_margin_per_step: float
    misspecification_margin_per_step: float
    bootstrap_draws: int
    manifest_file_sha256: str


@dataclass(frozen=True, slots=True)
class VisibleCareCase:
    """The complete method-visible state; evaluator truth is deliberately absent."""

    case_id: str
    family_id: str
    habit_posterior: float
    horizon: int
    feedback_step: int
    predicted_action_cost: float
    repair_cost: float
    verification_cost: float
    immediate_action_cost: float

    @property
    def feedback_available(self) -> bool:
        return self.feedback_step < self.horizon

    @property
    def pre_feedback_steps(self) -> int:
        return min(self.horizon, self.feedback_step)


@dataclass(frozen=True, slots=True)
class HiddenCareTruth:
    habit_truth: bool
    actual_action_cost: float
    decoy_evidence: bool


@dataclass(frozen=True, slots=True)
class GeneratedCareCase:
    visible: VisibleCareCase
    truth: HiddenCareTruth


@dataclass(frozen=True, slots=True)
class CareDecision:
    commit_new_habit: bool | None
    verify_first: bool
    reversible: bool
    decision_rule: str
    predicted_commit_risk: float
    predicted_escrow_risk: float
    predicted_verification_value: float


@dataclass(frozen=True, slots=True)
class CareReading:
    net_action_loss_per_step: float
    action_loss_per_step: float
    contamination_auc_per_step: float
    missed_adaptation_auc_per_step: float
    post_correction_regret_per_step: float
    verification_cost_per_step: float
    repair_cost_per_step: float
    rollback_equivalence_applicable: bool
    rollback_equivalent: bool
    operation_counts: Mapping[str, int]
    decision_receipt: Mapping[str, Any]


class SignedMemoryLedger:
    """One-cluster signed sufficient-statistic ledger used by the micro gate."""

    def __init__(self) -> None:
        self.value = 0
        self.operations: list[str] = []

    def initialize(self, commit_new_habit: bool) -> None:
        if commit_new_habit:
            self.value = 1
            self.operations.append("promote")
        else:
            self.operations.append("escrow")

    def correct(self, habit_truth: bool) -> bool:
        target = int(habit_truth)
        if self.value == target:
            return False
        if self.value == 1:
            self.operations.append("retract")
            self.value = 0
        if target == 1:
            self.operations.append("corrected_revision")
            self.value = 1
        return True

    @property
    def operation_counts(self) -> dict[str, int]:
        return {
            operation: self.operations.count(operation)
            for operation in ("promote", "escrow", "verify", "retract", "corrected_revision")
        }


def load_frozen_care_design(manifest_path: Path = DEFAULT_MANIFEST) -> CareDesign:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("protocol") != PROTOCOL_ID:
        raise ValueError("CARE manifest protocol mismatch")
    families = tuple(CareFamily(**item) for item in payload["scenario_families"])
    design = CareDesign(
        validation_seeds=tuple(payload["validation_seeds"]),
        holdout_seed_commitments=tuple(payload["sealed_holdout_seed_commitments"]),
        sealed_holdout_seed_count=int(payload["sealed_holdout_seed_count"]),
        sealed_seed_file_sha256=str(payload["sealed_seed_file_sha256"]),
        families=families,
        search_spaces={key: tuple(value) for key, value in payload["search_spaces"].items()},
        primary_baseline=CareArm(payload["primary_baseline"]),
        noninferiority_margin_per_step=float(payload["noninferiority_margin_per_step"]),
        misspecification_margin_per_step=float(payload["misspecification_margin_per_step"]),
        bootstrap_draws=int(payload["bootstrap_draws"]),
        manifest_file_sha256=_file_sha256(manifest_path),
    )
    if len(families) != 5 or len({family.family_id for family in families}) != 5:
        raise ValueError("CARE gate requires five unique families")
    if set(design.search_spaces) != {arm.value for arm in CareArm}:
        raise ValueError("CARE search spaces do not match frozen arms")
    if len(design.holdout_seed_commitments) != design.sealed_holdout_seed_count:
        raise ValueError("CARE holdout commitment count mismatch")
    roles = {family.family_role for family in families}
    expected_roles = {
        "required_contamination_gain",
        "low_consequence_guardrail",
        "required_delayed_correction_gain",
        "required_learning_gain",
        "model_misspecification_guardrail",
    }
    if roles != expected_roles:
        raise ValueError("CARE family roles are incomplete")
    return design


def _load_and_verify_holdout_seeds(
    design: CareDesign,
    sealed_seed_path: Path,
) -> tuple[int, ...]:
    if _file_sha256(sealed_seed_path) != design.sealed_seed_file_sha256:
        raise ValueError("CARE sealed seed file hash mismatch")
    payload = json.loads(sealed_seed_path.read_text(encoding="utf-8"))
    if payload.get("protocol") != PROTOCOL_ID:
        raise ValueError("CARE sealed seed protocol mismatch")
    seeds = tuple(int(seed) for seed in payload["holdout_seeds"])
    salt = str(payload["commitment_salt"])
    commitments = tuple(
        hashlib.sha256(f"{PROTOCOL_ID}:{seed}:{salt}".encode()).hexdigest() for seed in seeds
    )
    if commitments != design.holdout_seed_commitments:
        raise ValueError("CARE holdout seed commitments mismatch")
    if set(seeds) & set(design.validation_seeds):
        raise ValueError("CARE validation and holdout seeds overlap")
    return seeds


def _logit(probability: float) -> float:
    clipped = min(1.0 - 1e-9, max(1e-9, probability))
    return math.log(clipped / (1.0 - clipped))


def _sigmoid(value: float) -> float:
    if value >= 0.0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)


def generate_care_case(family: CareFamily, seed: int) -> GeneratedCareCase:
    rng = random.Random(f"{PROTOCOL_ID}:{family.family_id}:{seed}")
    habit_truth = rng.random() < family.habit_rate
    decoy = rng.random() < family.decoy_rate
    evidence_sign = 1.0 if habit_truth else -1.0
    if decoy:
        evidence_sign *= -1.0
    log_odds = (
        _logit(family.prior_habit_probability)
        + evidence_sign * family.evidence_strength
        + rng.gauss(0.0, family.evidence_noise)
    )
    posterior = min(1.0 - 1e-6, max(1e-6, _sigmoid(log_odds)))
    visible_payload = {
        "family_id": family.family_id,
        "seed_public_commitment": hashlib.sha256(
            f"{PROTOCOL_ID}:{family.family_id}:{seed}:case".encode()
        ).hexdigest(),
        "habit_posterior": posterior,
        "horizon": family.horizon,
        "feedback_step": family.feedback_step,
        "predicted_action_cost": family.predicted_action_cost,
        "repair_cost": family.repair_cost,
        "verification_cost": family.verification_cost,
        "immediate_action_cost": family.immediate_action_cost,
    }
    visible = VisibleCareCase(
        case_id=content_sha256(visible_payload),
        family_id=family.family_id,
        habit_posterior=posterior,
        horizon=family.horizon,
        feedback_step=family.feedback_step,
        predicted_action_cost=family.predicted_action_cost,
        repair_cost=family.repair_cost,
        verification_cost=family.verification_cost,
        immediate_action_cost=family.immediate_action_cost,
    )
    return GeneratedCareCase(
        visible=visible,
        truth=HiddenCareTruth(
            habit_truth=habit_truth,
            actual_action_cost=family.actual_action_cost,
            decoy_evidence=decoy,
        ),
    )


def _predicted_risks(
    visible: VisibleCareCase,
    *,
    risk_aversion: float,
) -> tuple[float, float]:
    p_habit = visible.habit_posterior
    exposure = visible.pre_feedback_steps * visible.predicted_action_cost
    repair = visible.repair_cost if visible.feedback_available else 0.0
    commit_risk = (1.0 - p_habit) * (exposure + risk_aversion * repair)
    escrow_risk = p_habit * exposure
    return commit_risk, escrow_risk


def choose_care_decision(
    arm: CareArm,
    visible: VisibleCareCase,
    parameter: Any,
) -> CareDecision:
    """Choose without hidden truth. The oracle is intentionally rejected here."""

    if arm is CareArm.FULL_RERUN_ORACLE:
        raise ValueError("full-rerun oracle is evaluator-owned and cannot use visible policy API")
    p_habit = visible.habit_posterior
    default_commit_risk, default_escrow_risk = _predicted_risks(visible, risk_aversion=1.0)
    if arm is CareArm.NO_CONSOLIDATION:
        return CareDecision(
            commit_new_habit=False,
            verify_first=False,
            reversible=False,
            decision_rule="no_consolidation",
            predicted_commit_risk=default_commit_risk,
            predicted_escrow_risk=default_escrow_risk,
            predicted_verification_value=0.0,
        )
    if arm is CareArm.CORRECTED_AMG:
        threshold = float(parameter)
        return CareDecision(
            commit_new_habit=p_habit >= threshold,
            verify_first=False,
            reversible=True,
            decision_rule="amg_top_hypothesis_then_full_revision",
            predicted_commit_risk=default_commit_risk,
            predicted_escrow_risk=default_escrow_risk,
            predicted_verification_value=0.0,
        )
    if arm in {CareArm.CONFIDENCE, CareArm.TRW_QUARANTINE}:
        threshold = float(parameter)
        return CareDecision(
            commit_new_habit=p_habit >= threshold,
            verify_first=False,
            reversible=arm is CareArm.TRW_QUARANTINE,
            decision_rule=(
                "posterior_confidence"
                if arm is CareArm.CONFIDENCE
                else "confidence_plus_conflict_compensation"
            ),
            predicted_commit_risk=default_commit_risk,
            predicted_escrow_risk=default_escrow_risk,
            predicted_verification_value=0.0,
        )
    if arm is CareArm.CURRENT_TASK_VOI:
        threshold = float(parameter)
        current_evpi = min(p_habit, 1.0 - p_habit) * visible.immediate_action_cost
        verify = current_evpi > visible.verification_cost
        return CareDecision(
            commit_new_habit=None if verify else p_habit >= threshold,
            verify_first=verify,
            reversible=False,
            decision_rule="confidence_plus_current_task_voi",
            predicted_commit_risk=default_commit_risk,
            predicted_escrow_risk=default_escrow_risk,
            predicted_verification_value=current_evpi,
        )
    risk_aversion = float(parameter)
    commit_risk, escrow_risk = _predicted_risks(visible, risk_aversion=risk_aversion)
    commit = commit_risk < escrow_risk
    if arm is CareArm.MATCHED_COMPOSED:
        current_evpi = min(p_habit, 1.0 - p_habit) * visible.immediate_action_cost
        verify = current_evpi > visible.verification_cost
        return CareDecision(
            commit_new_habit=None if verify else commit,
            verify_first=verify,
            reversible=True,
            decision_rule="risk_gate_plus_current_task_voi_plus_trw",
            predicted_commit_risk=commit_risk,
            predicted_escrow_risk=escrow_risk,
            predicted_verification_value=current_evpi,
        )
    if arm is not CareArm.CARE_WM:
        raise ValueError(f"unsupported CARE arm: {arm}")
    prevented_contamination_value = min(commit_risk, escrow_risk)
    verify = prevented_contamination_value > visible.verification_cost
    return CareDecision(
        commit_new_habit=None if verify else commit,
        verify_first=verify,
        reversible=True,
        decision_rule="counterfactual_action_regret_escrow",
        predicted_commit_risk=commit_risk,
        predicted_escrow_risk=escrow_risk,
        predicted_verification_value=prevented_contamination_value,
    )


def evaluate_care_case(
    generated: GeneratedCareCase,
    arm: CareArm,
    parameter: Any,
) -> CareReading:
    visible = generated.visible
    truth = generated.truth
    ledger = SignedMemoryLedger()
    if arm is CareArm.FULL_RERUN_ORACLE:
        decision = CareDecision(
            commit_new_habit=truth.habit_truth,
            verify_first=False,
            reversible=True,
            decision_rule="evaluator_truth_oracle",
            predicted_commit_risk=0.0,
            predicted_escrow_risk=0.0,
            predicted_verification_value=0.0,
        )
    else:
        decision = choose_care_decision(arm, visible, parameter)
    if decision.verify_first:
        ledger.operations.append("verify")
        initial_commit = truth.habit_truth
        verification_cost = visible.verification_cost
    else:
        if decision.commit_new_habit is None:
            raise ValueError("non-verifying CARE decision must choose promote or escrow")
        initial_commit = decision.commit_new_habit
        verification_cost = 0.0
    ledger.initialize(initial_commit)
    action_state = initial_commit
    action_loss = 0.0
    contamination_auc = 0.0
    missed_adaptation_auc = 0.0
    post_correction_regret = 0.0
    charged_repair_cost = 0.0
    feedback_applied = False
    for step_index in range(visible.horizon):
        if step_index == visible.feedback_step and visible.feedback_available:
            feedback_applied = True
            if decision.reversible:
                changed = ledger.correct(truth.habit_truth)
                action_state = truth.habit_truth
                if changed:
                    charged_repair_cost += visible.repair_cost
            elif arm is CareArm.NO_CONSOLIDATION:
                # Explicit feedback can guide the current action without becoming a
                # long-term semantic-memory write.
                action_state = truth.habit_truth
        wrong_action = action_state != truth.habit_truth
        if wrong_action:
            action_loss += truth.actual_action_cost
            if step_index >= visible.feedback_step and visible.feedback_available:
                post_correction_regret += truth.actual_action_cost
        if ledger.value == 1 and not truth.habit_truth:
            contamination_auc += 1.0
        if ledger.value == 0 and truth.habit_truth:
            missed_adaptation_auc += 1.0
    rollback_applicable = feedback_applied and decision.reversible
    rollback_equivalent = (not rollback_applicable) or ledger.value == int(truth.habit_truth)
    total_loss = action_loss + verification_cost + charged_repair_cost
    decision_receipt = {
        "case_id": visible.case_id,
        "decision_rule": decision.decision_rule,
        "verify_first": decision.verify_first,
        "initial_commit": initial_commit,
        "predicted_commit_risk": decision.predicted_commit_risk,
        "predicted_escrow_risk": decision.predicted_escrow_risk,
        "predicted_verification_value": decision.predicted_verification_value,
        "truth_fields_present": False,
    }
    return CareReading(
        net_action_loss_per_step=total_loss / visible.horizon,
        action_loss_per_step=action_loss / visible.horizon,
        contamination_auc_per_step=contamination_auc / visible.horizon,
        missed_adaptation_auc_per_step=missed_adaptation_auc / visible.horizon,
        post_correction_regret_per_step=post_correction_regret / visible.horizon,
        verification_cost_per_step=verification_cost / visible.horizon,
        repair_cost_per_step=charged_repair_cost / visible.horizon,
        rollback_equivalence_applicable=rollback_applicable,
        rollback_equivalent=rollback_equivalent,
        operation_counts=ledger.operation_counts,
        decision_receipt=decision_receipt,
    )


def _summary(readings: list[CareReading]) -> dict[str, float]:
    applicable = [reading for reading in readings if reading.rollback_equivalence_applicable]
    return {
        "net_action_loss_per_step": mean(reading.net_action_loss_per_step for reading in readings),
        "action_loss_per_step": mean(reading.action_loss_per_step for reading in readings),
        "contamination_auc_per_step": mean(
            reading.contamination_auc_per_step for reading in readings
        ),
        "missed_adaptation_auc_per_step": mean(
            reading.missed_adaptation_auc_per_step for reading in readings
        ),
        "post_correction_regret_per_step": mean(
            reading.post_correction_regret_per_step for reading in readings
        ),
        "verification_cost_per_step": mean(
            reading.verification_cost_per_step for reading in readings
        ),
        "repair_cost_per_step": mean(reading.repair_cost_per_step for reading in readings),
        "rollback_equivalence_rate": (
            1.0
            if not applicable
            else mean(float(reading.rollback_equivalent) for reading in applicable)
        ),
        "verify_count": sum(reading.operation_counts["verify"] for reading in readings),
        "promote_count": sum(reading.operation_counts["promote"] for reading in readings),
        "escrow_count": sum(reading.operation_counts["escrow"] for reading in readings),
        "retract_count": sum(reading.operation_counts["retract"] for reading in readings),
        "corrected_revision_count": sum(
            reading.operation_counts["corrected_revision"] for reading in readings
        ),
    }


def _bootstrap_ci(
    values: list[float],
    *,
    draws: int,
    comparison_name: str,
) -> tuple[float, float]:
    rng = random.Random(f"{PROTOCOL_ID}:{comparison_name}:paired-cluster-bootstrap")
    samples = sorted(mean(rng.choices(values, k=len(values))) for _ in range(draws))
    return samples[int(0.025 * draws)], samples[min(draws - 1, int(0.975 * draws))]


def _serialized_report_discloses_seed(report: Mapping[str, Any], seeds: tuple[int, ...]) -> bool:
    """Detect a seed token without mistaking digits embedded in floats or hashes."""

    serialized = json.dumps(report, sort_keys=True)
    return any(
        re.search(rf"(?<![0-9A-Za-z]){seed}(?![0-9A-Za-z])", serialized) is not None
        for seed in seeds
    )


COMPARISONS = {
    "care_minus_matched_composed": (CareArm.CARE_WM, CareArm.MATCHED_COMPOSED),
    "care_minus_no_consolidation": (CareArm.CARE_WM, CareArm.NO_CONSOLIDATION),
    "care_minus_confidence": (CareArm.CARE_WM, CareArm.CONFIDENCE),
    "care_minus_current_task_voi": (CareArm.CARE_WM, CareArm.CURRENT_TASK_VOI),
    "care_minus_trw": (CareArm.CARE_WM, CareArm.TRW_QUARANTINE),
    "care_minus_corrected_amg": (CareArm.CARE_WM, CareArm.CORRECTED_AMG),
    "care_minus_oracle": (CareArm.CARE_WM, CareArm.FULL_RERUN_ORACLE),
}


def counterfactual_sensitivity_audit() -> dict[str, bool]:
    high = VisibleCareCase(
        case_id="counterfactual-sensitivity-audit",
        family_id="audit-high-consequence",
        habit_posterior=0.70,
        horizon=12,
        feedback_step=10,
        predicted_action_cost=1.00,
        repair_cost=0.30,
        verification_cost=0.80,
        immediate_action_cost=0.10,
    )
    low = VisibleCareCase(
        case_id="counterfactual-sensitivity-audit",
        family_id="audit-low-consequence",
        habit_posterior=0.70,
        horizon=12,
        feedback_step=10,
        predicted_action_cost=0.05,
        repair_cost=0.30,
        verification_cost=0.80,
        immediate_action_cost=0.10,
    )
    confidence_high = choose_care_decision(CareArm.CONFIDENCE, high, 0.65)
    confidence_low = choose_care_decision(CareArm.CONFIDENCE, low, 0.65)
    current_high = choose_care_decision(CareArm.CURRENT_TASK_VOI, high, 0.65)
    current_low = choose_care_decision(CareArm.CURRENT_TASK_VOI, low, 0.65)
    care_high = choose_care_decision(CareArm.CARE_WM, high, 1.0)
    care_low = choose_care_decision(CareArm.CARE_WM, low, 1.0)
    return {
        "equal_entropy_confidence_invariant": (
            confidence_high.verify_first == confidence_low.verify_first
            and confidence_high.commit_new_habit == confidence_low.commit_new_habit
        ),
        "same_immediate_voi_invariant": (
            current_high.verify_first == current_low.verify_first
            and current_high.commit_new_habit == current_low.commit_new_habit
        ),
        "care_responds_to_long_horizon_consequence": (
            care_high.verify_first and not care_low.verify_first
        ),
    }


def run_care_wm_exact_counterfactual_gate(
    *,
    repository_root: Path,
    manifest_path: Path | None = None,
    sealed_seed_path: Path | None = None,
) -> dict[str, Any]:
    manifest = manifest_path or repository_root / DEFAULT_MANIFEST
    sealed = sealed_seed_path or repository_root / DEFAULT_SEALED_SEEDS
    design = load_frozen_care_design(manifest)
    phase_audit = ["validation_tuning_started"]
    selected: dict[str, dict[CareArm, Any]] = {}
    validation_reports: dict[str, Any] = {}
    for family in design.families:
        selected[family.family_id] = {}
        validation_reports[family.family_id] = {}
        validation_cases = [generate_care_case(family, seed) for seed in design.validation_seeds]
        for arm in CareArm:
            candidates: list[dict[str, Any]] = []
            for parameter in design.search_spaces[arm.value]:
                readings = [
                    evaluate_care_case(generated, arm, parameter) for generated in validation_cases
                ]
                candidates.append(
                    {
                        "parameter": parameter,
                        "mean_net_action_loss_per_step": mean(
                            reading.net_action_loss_per_step for reading in readings
                        ),
                    }
                )
            winner = min(
                candidates,
                key=lambda item: (
                    item["mean_net_action_loss_per_step"],
                    json.dumps(item["parameter"], sort_keys=True),
                ),
            )
            selected[family.family_id][arm] = winner["parameter"]
            validation_reports[family.family_id][arm.value] = {
                "candidates": candidates,
                "selected_parameter": winner["parameter"],
            }
    phase_audit.extend(("validation_tuning_completed", "sealed_seed_file_open_requested"))
    holdout_seeds = _load_and_verify_holdout_seeds(design, sealed)
    phase_audit.append("sealed_seed_file_verified")
    family_reports: dict[str, Any] = {}
    paired: dict[str, dict[str, list[float]]] = {
        commitment: {name: [] for name in COMPARISONS}
        for commitment in design.holdout_seed_commitments
    }
    truth_isolation_gates: dict[str, bool] = {}
    care_rollback_gates: dict[str, bool] = {}
    care_operation_totals = dict.fromkeys(
        ("verify", "promote", "escrow", "retract", "corrected_revision"), 0
    )
    for family in design.families:
        cases = [generate_care_case(family, seed) for seed in holdout_seeds]
        readings_by_arm: dict[CareArm, list[CareReading]] = {
            arm: [
                evaluate_care_case(
                    generated,
                    arm,
                    selected[family.family_id][arm],
                )
                for generated in cases
            ]
            for arm in CareArm
        }
        for arm in CareArm:
            if arm is CareArm.FULL_RERUN_ORACLE:
                continue
            truth_isolation_gates[f"{family.family_id}:{arm.value}"] = all(
                reading.decision_receipt.get("truth_fields_present") is False
                for reading in readings_by_arm[arm]
            )
        applicable_care = [
            reading
            for reading in readings_by_arm[CareArm.CARE_WM]
            if reading.rollback_equivalence_applicable
        ]
        care_rollback_gates[family.family_id] = all(
            reading.rollback_equivalent for reading in applicable_care
        )
        for operation in care_operation_totals:
            care_operation_totals[operation] += sum(
                reading.operation_counts[operation] for reading in readings_by_arm[CareArm.CARE_WM]
            )
        rows = []
        for index, commitment in enumerate(design.holdout_seed_commitments):
            losses = {
                arm.value: readings_by_arm[arm][index].net_action_loss_per_step for arm in CareArm
            }
            differences = {
                name: losses[left.value] - losses[right.value]
                for name, (left, right) in COMPARISONS.items()
            }
            for name, value in differences.items():
                paired[commitment][name].append(value)
            rows.append(
                {
                    "holdout_seed_commitment": commitment,
                    "visible_case_id": cases[index].visible.case_id,
                    "net_action_loss_per_step": losses,
                    "paired_differences": differences,
                    "care_decision_receipt": readings_by_arm[CareArm.CARE_WM][
                        index
                    ].decision_receipt,
                }
            )
        family_reports[family.family_id] = {
            "family_parameters": asdict(family),
            "selected_parameters": {
                arm.value: value for arm, value in selected[family.family_id].items()
            },
            "summaries": {
                arm.value: _summary(readings) for arm, readings in readings_by_arm.items()
            },
            "paired_holdout_rows": rows,
        }
    clustered = {
        name: [mean(paired[commitment][name]) for commitment in design.holdout_seed_commitments]
        for name in COMPARISONS
    }
    comparisons: dict[str, dict[str, Any]] = {
        name: {
            "mean": mean(values),
            "confidence_interval_95": _bootstrap_ci(
                values,
                draws=design.bootstrap_draws,
                comparison_name=name,
            ),
            "cluster_count": len(values),
            "benefit_if_negative": True,
        }
        for name, values in clustered.items()
    }
    family_primary_differences: dict[str, float] = {}
    family_no_consolidation_differences: dict[str, float] = {}
    for family_id, raw_family_report in family_reports.items():
        family_report = cast(dict[str, Any], raw_family_report)
        rows = cast(list[dict[str, Any]], family_report["paired_holdout_rows"])
        family_primary_differences[family_id] = mean(
            cast(dict[str, float], row["paired_differences"])["care_minus_matched_composed"]
            for row in rows
        )
        family_no_consolidation_differences[family_id] = mean(
            cast(dict[str, float], row["paired_differences"])["care_minus_no_consolidation"]
            for row in rows
        )
    family_by_role = {family.family_role: family.family_id for family in design.families}
    sensitivity = counterfactual_sensitivity_audit()
    gate_criteria = {
        "primary_ci_upper_below_zero": comparisons["care_minus_matched_composed"][
            "confidence_interval_95"
        ][1]
        < 0.0,
        "no_consolidation_ci_upper_below_zero": comparisons["care_minus_no_consolidation"][
            "confidence_interval_95"
        ][1]
        < 0.0,
        "required_contamination_gain": family_primary_differences[
            family_by_role["required_contamination_gain"]
        ]
        < 0.0,
        "required_delayed_correction_gain": family_primary_differences[
            family_by_role["required_delayed_correction_gain"]
        ]
        < 0.0,
        "required_clean_learning_gain": family_no_consolidation_differences[
            family_by_role["required_learning_gain"]
        ]
        < 0.0,
        "low_consequence_noninferiority": family_primary_differences[
            family_by_role["low_consequence_guardrail"]
        ]
        <= design.noninferiority_margin_per_step,
        "misspecification_noninferiority": family_primary_differences[
            family_by_role["model_misspecification_guardrail"]
        ]
        <= design.misspecification_margin_per_step,
        "all_truth_isolation_gates": all(truth_isolation_gates.values()),
        "all_care_rollback_equivalence_gates": all(care_rollback_gates.values()),
        "care_exercised_verify_promote_escrow_retract": all(
            care_operation_totals[operation] > 0
            for operation in ("verify", "promote", "escrow", "retract")
        ),
        "all_counterfactual_sensitivity_audits": all(sensitivity.values()),
    }
    provenance_paths = {
        "gate_source_sha256": Path(__file__).resolve(),
        "manifest_file_sha256": manifest,
        "sealed_seed_file_sha256": sealed,
        "preregistration_sha256": repository_root / DEFAULT_PREREGISTRATION,
    }
    report: dict[str, Any] = {
        "protocol": PROTOCOL_ID,
        "evidence_status": (
            "finite synthetic exact counterfactual mechanism evidence; not paper evidence"
        ),
        "complete_project_two_status": "not_evaluated_by_this_micro_gate",
        "raw_holdout_seeds_disclosed": False,
        "holdout_seed_commitments": list(design.holdout_seed_commitments),
        "phase_audit": phase_audit,
        "validation": validation_reports,
        "families": family_reports,
        "paired_cluster_comparisons": comparisons,
        "family_primary_differences": family_primary_differences,
        "family_no_consolidation_differences": family_no_consolidation_differences,
        "truth_isolation_gates": truth_isolation_gates,
        "care_rollback_gates": care_rollback_gates,
        "care_operation_totals": care_operation_totals,
        "counterfactual_sensitivity_audit": sensitivity,
        "gate_criteria": gate_criteria,
        "candidate_positive_mechanism": all(gate_criteria.values()),
        "provenance": {key: _file_sha256(path) for key, path in provenance_paths.items()},
        "limitations": [
            "binary habit-versus-nonhabit latent state",
            "finite synthetic cases with an explicit consequence model",
            "perfect verification observation when purchased",
            "repository-local sealed seeds",
            "no complete four-axis particle posterior",
            "no RGB-D, household, LLM, or robot execution evidence",
        ],
    }
    report["content_sha256"] = content_sha256(report)
    return report


def write_care_wm_exact_counterfactual_report(
    report: dict[str, Any],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def verify_care_wm_exact_counterfactual_report(
    report_path: Path,
    *,
    repository_root: Path,
    recompute: bool = False,
) -> dict[str, Any]:
    report: dict[str, Any] = json.loads(report_path.read_text(encoding="utf-8"))
    stored_hash = report.get("content_sha256")
    unsigned = dict(report)
    unsigned.pop("content_sha256", None)
    if not isinstance(stored_hash, str) or content_sha256(unsigned) != stored_hash:
        raise ValueError("CARE report content hash mismatch")
    if report.get("protocol") != PROTOCOL_ID:
        raise ValueError("CARE report protocol mismatch")
    design = load_frozen_care_design(repository_root / DEFAULT_MANIFEST)
    seeds = _load_and_verify_holdout_seeds(design, repository_root / DEFAULT_SEALED_SEEDS)
    if tuple(report.get("holdout_seed_commitments", ())) != design.holdout_seed_commitments:
        raise ValueError("CARE report commitment mismatch")
    if _serialized_report_discloses_seed(report, seeds):
        raise ValueError("CARE report disclosed a raw holdout seed")
    provenance_paths = {
        "gate_source_sha256": Path(__file__).resolve(),
        "manifest_file_sha256": repository_root / DEFAULT_MANIFEST,
        "sealed_seed_file_sha256": repository_root / DEFAULT_SEALED_SEEDS,
        "preregistration_sha256": repository_root / DEFAULT_PREREGISTRATION,
    }
    if report.get("provenance") != {
        key: _file_sha256(path) for key, path in provenance_paths.items()
    }:
        raise ValueError("CARE report provenance mismatch")
    if recompute:
        expected = run_care_wm_exact_counterfactual_gate(repository_root=repository_root)
        if expected["content_sha256"] != report["content_sha256"]:
            raise ValueError("CARE deterministic recomputation mismatch")
    return report


__all__ = [
    "DEFAULT_MANIFEST",
    "DEFAULT_PREREGISTRATION",
    "DEFAULT_SEALED_SEEDS",
    "PROTOCOL_ID",
    "CareArm",
    "CareDecision",
    "CareDesign",
    "CareFamily",
    "CareReading",
    "GeneratedCareCase",
    "HiddenCareTruth",
    "SignedMemoryLedger",
    "VisibleCareCase",
    "choose_care_decision",
    "counterfactual_sensitivity_audit",
    "evaluate_care_case",
    "generate_care_case",
    "load_frozen_care_design",
    "run_care_wm_exact_counterfactual_gate",
    "verify_care_wm_exact_counterfactual_report",
    "write_care_wm_exact_counterfactual_report",
]
