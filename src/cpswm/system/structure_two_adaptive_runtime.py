"""Production-side contracts for state-dependent Structure-Two execution.

The router consumes only a frozen robot-visible feature snapshot.  It selects
one of the six registered plans or fails closed to safe abstention; it never
sees evaluator truth or another path's output.
"""

from __future__ import annotations

import hashlib
import inspect
import marshal
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from math import isfinite
from pathlib import Path
from types import CodeType
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from cpswm.contracts import (
    ActiveObservationPlan,
    ObservationActionCandidate,
    ObservationOpportunityRecord,
)
from cpswm.contracts.base import ContractModel, NonNegativeInt, Probability
from cpswm.system.prototype_spine import FastActionVerificationReceipt, PrototypeStepResult
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_execution import AdaptiveInferenceDebtCertificate
from cpswm.world_model.grounded_search.ciav_opceu_loop import (
    CIAVOPCEUReceipt,
    RealizedCIAVObservation,
)

SHA256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
AdaptivePathId = Literal[
    "P0_SAFE_DEFERRED",
    "P1_EVENT_ACTOR_LOCAL",
    "P2_REGIME_RECOVERY_LOCAL",
    "P3_ACTIVE_VERIFY",
    "P4_EVENT_ACTOR_PLUS_REGIME",
    "P5_FULL_EAGER",
]

EVALUATION_DIRECT_P5_REASON = "evaluation_only_direct_p5_ceiling_override"


class AdaptiveAuthorizationPolicy(ContractModel):
    """Runtime-owned local authorization policy for the adaptive lane.

    This is a D0 process-local policy binding, not an independently custodied
    authorization assertion.  The production runtime defaults to denying all
    adaptive writes until an owner explicitly binds a policy.
    """

    schema_version: Literal["0.1.0"] = "0.1.0"
    policy_id: str = Field(min_length=1)
    memory_transition_authorized: bool = False
    privacy_policy_satisfied: bool = False
    safety_context_authorized: bool = False

    @property
    def content_sha256(self) -> str:
        return content_sha256(self.model_dump(mode="json"))


class AdaptiveDebtStatus(StrEnum):
    PENDING = "pending"
    SETTLED = "settled"
    EXPIRED = "expired"


class AdaptiveRouterFeatures(ContractModel):
    """Frozen pre-path feature vector; no latent truth or future output exists here."""

    schema_version: Literal["0.1.0"] = "0.1.0"
    source_state_sha256: SHA256
    authorization_policy_sha256: SHA256
    observation_opportunity_coverage: Probability
    evidence_conflict_score: Probability
    provenance_dependence_score: Probability
    actor_ambiguity: Probability
    instance_ambiguity: Probability
    unknown_mass: Probability
    action_margin: Probability
    pending_long_term_commit: bool
    regime_hazard: Probability
    outstanding_debt_count: NonNegativeInt
    oldest_debt_age: NonNegativeInt
    maximum_debt_flip_bound: Probability
    state_staleness: NonNegativeInt
    memory_transition_authorized: bool
    privacy_policy_satisfied: bool
    safety_context_authorized: bool
    feature_extraction_cost_units: float = Field(ge=0.0)
    feature_source_sha256s: tuple[SHA256, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_sources(self) -> AdaptiveRouterFeatures:
        if len(self.feature_source_sha256s) != len(set(self.feature_source_sha256s)):
            raise ValueError("adaptive router feature sources must be unique")
        if not isfinite(self.feature_extraction_cost_units):
            raise ValueError("adaptive router feature extraction cost must be finite")
        return self

    @property
    def content_sha256(self) -> str:
        return content_sha256(self.model_dump(mode="json"))


class AdaptivePathSelectionReceipt(ContractModel):
    """Hash-bound result of the deterministic, pre-path-only router."""

    feature_sha256: SHA256
    selected_path_id: AdaptivePathId | None = None
    safe_abstain: bool
    reasons: tuple[str, ...] = Field(min_length=1)
    ciav_runtime_input_available: bool
    receipt_sha256: SHA256

    @model_validator(mode="after")
    def validate_selection(self) -> AdaptivePathSelectionReceipt:
        if self.safe_abstain == (self.selected_path_id is not None):
            raise ValueError("router must select exactly one path or safe-abstain")
        unsigned = self.model_dump(mode="json", exclude={"receipt_sha256"})
        if self.receipt_sha256 != content_sha256(unsigned):
            raise ValueError("adaptive path selection receipt hash mismatch")
        return self


def _selection_receipt(
    features: AdaptiveRouterFeatures,
    *,
    selected_path_id: AdaptivePathId | None,
    reasons: tuple[str, ...],
    ciav_available: bool,
) -> AdaptivePathSelectionReceipt:
    payload = {
        "feature_sha256": features.content_sha256,
        "selected_path_id": selected_path_id,
        "safe_abstain": selected_path_id is None,
        "reasons": reasons,
        "ciav_runtime_input_available": ciav_available,
    }
    return AdaptivePathSelectionReceipt(
        **payload,
        receipt_sha256=content_sha256(payload),
    )


def select_adaptive_path(
    features: AdaptiveRouterFeatures,
    *,
    ciav_runtime_input_available: bool,
    debt_expiry_steps: int,
) -> AdaptivePathSelectionReceipt:
    """Select one legal path using only frozen, inexpensive visible features."""

    if debt_expiry_steps < 1:
        raise ValueError("debt_expiry_steps must be positive")
    if not (
        features.memory_transition_authorized
        and features.privacy_policy_satisfied
        and features.safety_context_authorized
    ):
        return _selection_receipt(
            features,
            selected_path_id=None,
            reasons=("hard_safety_or_privacy_precondition_failed",),
            ciav_available=ciav_runtime_input_available,
        )
    expired_debt = (
        features.outstanding_debt_count > 0 and features.oldest_debt_age >= debt_expiry_steps
    )
    high_debt_risk = features.outstanding_debt_count > 0 and features.maximum_debt_flip_bound > 0.25
    if expired_debt or high_debt_risk:
        if not ciav_runtime_input_available:
            return _selection_receipt(
                features,
                selected_path_id=None,
                reasons=("mandatory_full_escalation_missing_ciav_runtime_input",),
                ciav_available=False,
            )
        return _selection_receipt(
            features,
            selected_path_id="P5_FULL_EAGER",
            reasons=("expired_or_high_flip_risk_debt_forced_full_eager",),
            ciav_available=True,
        )
    event_actor_pressure = max(
        features.evidence_conflict_score,
        features.actor_ambiguity,
        features.instance_ambiguity,
        features.unknown_mass,
    )
    if event_actor_pressure >= 0.45 and features.regime_hazard >= 0.45:
        return _selection_receipt(
            features,
            selected_path_id="P4_EVENT_ACTOR_PLUS_REGIME",
            reasons=("joint_event_actor_and_regime_pressure",),
            ciav_available=ciav_runtime_input_available,
        )
    if (
        ciav_runtime_input_available
        and features.action_margin <= 0.2
        and max(features.actor_ambiguity, features.unknown_mass) >= 0.3
    ):
        return _selection_receipt(
            features,
            selected_path_id="P3_ACTIVE_VERIFY",
            reasons=("low_action_margin_and_resolvable_uncertainty",),
            ciav_available=True,
        )
    if event_actor_pressure >= 0.45 or features.provenance_dependence_score >= 0.45:
        return _selection_receipt(
            features,
            selected_path_id="P1_EVENT_ACTOR_LOCAL",
            reasons=("event_actor_or_provenance_pressure",),
            ciav_available=ciav_runtime_input_available,
        )
    if (
        features.regime_hazard >= 0.35
        or features.outstanding_debt_count > 0
        or features.state_staleness > 0
    ):
        return _selection_receipt(
            features,
            selected_path_id="P2_REGIME_RECOVERY_LOCAL",
            reasons=("regime_recovery_or_staleness_pressure",),
            ciav_available=ciav_runtime_input_available,
        )
    return _selection_receipt(
        features,
        selected_path_id="P0_SAFE_DEFERRED",
        reasons=("low_visible_risk_safe_deferral",),
        ciav_available=ciav_runtime_input_available,
    )


def select_evaluation_direct_p5(
    features: AdaptiveRouterFeatures,
    *,
    ciav_runtime_input_available: bool,
) -> AdaptivePathSelectionReceipt:
    """Authorize an isolated evaluation-only P5 ceiling run.

    This is intentionally separate from :func:`select_adaptive_path`: it does
    not change production routing policy and it refuses to bypass debt,
    staleness, authorization, privacy, or safety preconditions.  Its receipt
    carries an explicit evaluation-only reason so a production-selected P5 and
    a ceiling probe cannot be confused in downstream evidence.
    """

    if not ciav_runtime_input_available:
        raise ValueError("evaluation-only direct P5 requires CIAV runtime input")
    if not (
        features.memory_transition_authorized
        and features.privacy_policy_satisfied
        and features.safety_context_authorized
    ):
        raise PermissionError(
            "evaluation-only direct P5 is denied by safety, privacy, or authorization policy"
        )
    if (
        features.outstanding_debt_count != 0
        or features.oldest_debt_age != 0
        or features.pending_long_term_commit
    ):
        raise RuntimeError("evaluation-only direct P5 cannot bypass pending adaptive debt")
    if features.state_staleness != 0:
        raise ValueError("evaluation-only direct P5 requires a fresh router feature snapshot")
    return _selection_receipt(
        features,
        selected_path_id="P5_FULL_EAGER",
        reasons=(EVALUATION_DIRECT_P5_REASON,),
        ciav_available=True,
    )


def _callable_source_binding(callback: Callable[..., object]) -> dict[str, object]:
    target = getattr(callback, "__func__", callback)
    module = getattr(target, "__module__", None)
    qualname = getattr(target, "__qualname__", None)
    source_name = inspect.getsourcefile(target)
    if not isinstance(module, str) or not isinstance(qualname, str) or source_name is None:
        raise ValueError("CIAV realizer must have an inspectable source binding")
    code = getattr(target, "__code__", None)
    if not isinstance(code, CodeType):
        raise ValueError("CIAV realizer must expose inspectable loaded code")
    source_path = Path(source_name).resolve()
    if not source_path.is_file():
        raise ValueError("CIAV realizer source is unavailable")
    try:
        closure_values = tuple(
            cell.cell_contents for cell in (getattr(target, "__closure__", None) or ())
        )
        closure_sha256 = content_sha256(
            {
                "closure_values": closure_values,
                "defaults": getattr(target, "__defaults__", None),
                "keyword_defaults": getattr(target, "__kwdefaults__", None),
            }
        )
    except (TypeError, ValueError) as error:
        raise ValueError("CIAV realizer closure is not content-addressable") from error
    return {
        "symbol": f"{module}.{qualname}",
        "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "loaded_code_sha256": hashlib.sha256(marshal.dumps(code)).hexdigest(),
        "closure_sha256": closure_sha256,
    }


@dataclass(frozen=True, slots=True)
class AdaptiveCIAVRuntimeInput:
    """Runtime-only CIAV input; its callback identity is source-bound before use."""

    actions: tuple[ObservationActionCandidate, ...]
    consolidation_decision_utilities: Mapping[UUID, Mapping[UUID, float]]
    terminal_decision_utilities: Mapping[UUID, Mapping[UUID, float]]
    privacy_budget: float
    opportunity_time: datetime
    actor_likelihoods_by_outcome: Mapping[str, Mapping[str, float]]
    expected_detected_location_id: UUID
    selection_probability: float
    p_visible_given_state: float
    p_detect_given_visible: float
    realizer: Callable[[ObservationOpportunityRecord], RealizedCIAVObservation]
    identity_switch_probability: float = 0.0
    minimum_net_value: float = 0.0

    def __post_init__(self) -> None:
        if not self.actions:
            raise ValueError("adaptive CIAV input requires at least one action")
        for name, value in (
            ("privacy_budget", self.privacy_budget),
            ("selection_probability", self.selection_probability),
            ("p_visible_given_state", self.p_visible_given_state),
            ("p_detect_given_visible", self.p_detect_given_visible),
            ("identity_switch_probability", self.identity_switch_probability),
            ("minimum_net_value", self.minimum_net_value),
        ):
            if not isfinite(value):
                raise ValueError(f"{name} must be finite")
        for name, value in (
            ("selection_probability", self.selection_probability),
            ("p_visible_given_state", self.p_visible_given_state),
            ("p_detect_given_visible", self.p_detect_given_visible),
            ("identity_switch_probability", self.identity_switch_probability),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must lie in [0, 1]")
        if self.privacy_budget < 0.0:
            raise ValueError("privacy_budget must be non-negative")
        if self.opportunity_time.tzinfo is None or self.opportunity_time.utcoffset() is None:
            raise ValueError("CIAV opportunity_time must be timezone-aware")
        _callable_source_binding(self.realizer)

    @property
    def content_sha256(self) -> str:
        realizer_binding = _callable_source_binding(self.realizer)

        def utility_rows(values: Mapping[UUID, Mapping[UUID, float]]) -> tuple[object, ...]:
            return tuple(
                (
                    str(decision_id),
                    tuple(sorted((str(key), value) for key, value in row.items())),
                )
                for decision_id, row in sorted(values.items(), key=lambda item: str(item[0]))
            )

        return content_sha256(
            {
                "actions": self.actions,
                "consolidation_decision_utilities": utility_rows(
                    self.consolidation_decision_utilities
                ),
                "terminal_decision_utilities": utility_rows(self.terminal_decision_utilities),
                "privacy_budget": self.privacy_budget,
                "opportunity_time": self.opportunity_time,
                "actor_likelihoods_by_outcome": tuple(
                    (
                        outcome,
                        tuple(sorted(likelihoods.items())),
                    )
                    for outcome, likelihoods in sorted(self.actor_likelihoods_by_outcome.items())
                ),
                "expected_detected_location_id": self.expected_detected_location_id,
                "selection_probability": self.selection_probability,
                "p_visible_given_state": self.p_visible_given_state,
                "p_detect_given_visible": self.p_detect_given_visible,
                "identity_switch_probability": self.identity_switch_probability,
                "minimum_net_value": self.minimum_net_value,
                "realizer_binding": realizer_binding,
            }
        )


@dataclass(frozen=True, slots=True)
class AdaptiveExecutionContext:
    router_features: AdaptiveRouterFeatures
    step_index: int
    debt_expiry_steps: int = 20
    ciav_input: AdaptiveCIAVRuntimeInput | None = None

    def __post_init__(self) -> None:
        if self.step_index < 0:
            raise ValueError("adaptive step_index must be non-negative")
        if self.debt_expiry_steps < 1:
            raise ValueError("adaptive debt_expiry_steps must be positive")


@dataclass(frozen=True, slots=True)
class AdaptiveStepResult:
    """Inspectable outcome of one selected adaptive production transaction."""

    path_selection: AdaptivePathSelectionReceipt
    primary_result: PrototypeStepResult | None
    feedback_result: PrototypeStepResult | None
    fast_verification_receipt: FastActionVerificationReceipt | None
    ciav_plan: ActiveObservationPlan | None
    ciav_receipt: CIAVOPCEUReceipt | None
    debt_certificates: tuple[AdaptiveInferenceDebtCertificate, ...]
    safe_abstained: bool
    executed_operator_count: int
    deferred_operator_count: int
    elapsed_ns_by_operator: Mapping[str, int]

    def __post_init__(self) -> None:
        if self.safe_abstained != (self.path_selection.selected_path_id is None):
            raise ValueError("adaptive result safe-abstain status mismatches router selection")
        if self.safe_abstained and self.primary_result is not None:
            raise ValueError("safe abstention cannot return a committed primary result")
        if self.ciav_receipt is not None and self.ciav_plan is None:
            raise ValueError("CIAV observation receipt requires a CIAV plan")
        if self.feedback_result is not None and self.ciav_receipt is None:
            raise ValueError("feedback closure requires a realized CIAV observation")
        if self.fast_verification_receipt is not None and self.ciav_receipt is None:
            raise ValueError("fast verification requires a realized CIAV observation")
        if self.feedback_result is not None and self.fast_verification_receipt is not None:
            raise ValueError("CIAV feedback must use exactly one closure kind")
        if self.executed_operator_count < 0 or self.deferred_operator_count < 0:
            raise ValueError("adaptive operator counts must be non-negative")
        if any(value < 0 for value in self.elapsed_ns_by_operator.values()):
            raise ValueError("adaptive elapsed resource values must be non-negative")


__all__ = [
    "EVALUATION_DIRECT_P5_REASON",
    "AdaptiveAuthorizationPolicy",
    "AdaptiveCIAVRuntimeInput",
    "AdaptiveDebtStatus",
    "AdaptiveExecutionContext",
    "AdaptivePathId",
    "AdaptivePathSelectionReceipt",
    "AdaptiveRouterFeatures",
    "AdaptiveStepResult",
    "select_adaptive_path",
    "select_evaluation_direct_p5",
]
