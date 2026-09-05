"""Independent resolution protocols for five open Structure Two bindings.

Each protocol freezes its own estimand, complete arm family, validation-only
selection metric, confirmatory gates, information/budget contract, and claim
boundary.  The shared execution trace is deliberately low level: every arm
must cover the exact same validation and confirmatory unit UUIDs, while the
resolution result is recomputed rather than accepted from a caller.

These contracts define how a binding *could* be resolved.  They do not claim
that a formal execution, independent custody, or trust-anchor enrollment
currently exists, and they do not authorize a seven-operator ablation.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from statistics import mean
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from cpswm.contracts.base import ContractModel, PositiveInt
from cpswm.system.reproducibility import content_sha256

SCHEMA_VERSION = "0.1.0"
CONFIG_ROOT = Path(__file__).resolve().parents[4] / "configs/project_two_experiments"

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]


class OpenBinding(StrEnum):
    NEURAL_PROPOSER_ARCHITECTURE = "neural_proposer_architecture"
    TRAINING_SCHEDULE = "training_schedule"
    CONSOLIDATION_THRESHOLDS = "consolidation_thresholds"
    CIAV_ACTION_BUDGET = "ciav_action_budget"
    EXACT_ENUMERATION_FALSIFIER = "exact_enumeration_falsifier"


class ArmRole(StrEnum):
    ELIGIBLE = "eligible"
    DIAGNOSTIC_CONTROL = "diagnostic_control"


class MetricDirection(StrEnum):
    MINIMIZE = "minimize"
    MAXIMIZE = "maximize"


class ResolutionSplit(StrEnum):
    VALIDATION = "validation"
    CONFIRMATORY = "confirmatory"


class ResolutionArm(ContractModel):
    arm_id: str = Field(min_length=1)
    role: ArmRole
    implementation_contract: str = Field(min_length=1)


class ConfirmatoryGate(ContractModel):
    metric_id: str = Field(min_length=1)
    direction: MetricDirection
    threshold: FiniteFloat
    aggregation: Literal["mean_over_independent_confirmatory_units"]


class BindingResolutionProtocolBase(ContractModel):
    schema_version: Literal["0.1.0"]
    protocol_id: str = Field(min_length=1)
    binding: OpenBinding
    estimand: str = Field(min_length=1)
    arms: tuple[ResolutionArm, ...] = Field(min_length=2)
    validation_metric_id: str = Field(min_length=1)
    validation_direction: MetricDirection
    minimum_validation_units: PositiveInt
    minimum_confirmatory_units: PositiveInt
    selection_rule: Literal[
        "validation_mean_then_arm_order_tiebreak_confirmatory_hidden_until_selection"
    ]
    confirmatory_gates: tuple[ConfirmatoryGate, ...] = Field(min_length=1)
    information_contract: str = Field(min_length=1)
    budget_contract: str = Field(min_length=1)
    claim_boundary: str = Field(min_length=1)

    @model_validator(mode="after")
    def _complete_independent_definition(self) -> Self:
        arm_ids = tuple(arm.arm_id for arm in self.arms)
        if len(arm_ids) != len(set(arm_ids)):
            raise ValueError("resolution arms must be unique")
        if not any(arm.role is ArmRole.ELIGIBLE for arm in self.arms):
            raise ValueError("resolution protocol needs at least one selectable arm")
        metrics = tuple(gate.metric_id for gate in self.confirmatory_gates)
        if len(metrics) != len(set(metrics)):
            raise ValueError("confirmatory gate metrics must be unique")
        if self.validation_metric_id in set(metrics):
            raise ValueError("validation selection metric must not double as a confirmatory gate")
        if self.minimum_validation_units < 3 or self.minimum_confirmatory_units < 5:
            raise ValueError(
                "resolution protocols require at least 3 validation and 5 confirmatory units"
            )
        if "seven-operator ablation" not in self.claim_boundary:
            raise ValueError("claim boundary must explicitly deny ablation authority")
        return self

    @property
    def content_sha256(self) -> str:
        return content_sha256(self)


class NeuralProposerArchitectureProtocol(BindingResolutionProtocolBase):
    protocol_id: Literal["structure-two-neural-proposer-architecture-resolution@0.1"]
    binding: Literal[OpenBinding.NEURAL_PROPOSER_ARCHITECTURE]


class TrainingScheduleProtocol(BindingResolutionProtocolBase):
    protocol_id: Literal["structure-two-training-schedule-resolution@0.1"]
    binding: Literal[OpenBinding.TRAINING_SCHEDULE]


class ConsolidationThresholdsProtocol(BindingResolutionProtocolBase):
    protocol_id: Literal["structure-two-consolidation-thresholds-resolution@0.1"]
    binding: Literal[OpenBinding.CONSOLIDATION_THRESHOLDS]


class CiavActionBudgetProtocol(BindingResolutionProtocolBase):
    protocol_id: Literal["structure-two-ciav-action-budget-resolution@0.1"]
    binding: Literal[OpenBinding.CIAV_ACTION_BUDGET]


class ExactEnumerationFalsifierProtocol(BindingResolutionProtocolBase):
    protocol_id: Literal["structure-two-exact-enumeration-falsifier-resolution@0.1"]
    binding: Literal[OpenBinding.EXACT_ENUMERATION_FALSIFIER]


type BindingResolutionProtocol = (
    NeuralProposerArchitectureProtocol
    | TrainingScheduleProtocol
    | ConsolidationThresholdsProtocol
    | CiavActionBudgetProtocol
    | ExactEnumerationFalsifierProtocol
)

PROTOCOL_TYPE_BY_BINDING: dict[OpenBinding, type[BindingResolutionProtocolBase]] = {
    OpenBinding.NEURAL_PROPOSER_ARCHITECTURE: NeuralProposerArchitectureProtocol,
    OpenBinding.TRAINING_SCHEDULE: TrainingScheduleProtocol,
    OpenBinding.CONSOLIDATION_THRESHOLDS: ConsolidationThresholdsProtocol,
    OpenBinding.CIAV_ACTION_BUDGET: CiavActionBudgetProtocol,
    OpenBinding.EXACT_ENUMERATION_FALSIFIER: ExactEnumerationFalsifierProtocol,
}

CONFIG_PATH_BY_BINDING: dict[OpenBinding, Path] = {
    binding: CONFIG_ROOT / f"structure_two_{binding.value}_resolution_v0_1.json"
    for binding in OpenBinding
}


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key in binding protocol: {key}")
        result[key] = value
    return result


def load_binding_resolution_protocol(
    binding: OpenBinding,
    *,
    path: Path | None = None,
) -> BindingResolutionProtocol:
    """Load one independently versioned protocol with duplicate-key rejection."""

    protocol_type = PROTOCOL_TYPE_BY_BINDING[binding]
    source = path or CONFIG_PATH_BY_BINDING[binding]
    payload = json.loads(
        source.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_json_keys
    )
    if not isinstance(payload, dict):
        raise ValueError("binding resolution protocol must be a JSON object")
    return protocol_type.model_validate(payload)  # type: ignore[return-value]


class MetricObservation(ContractModel):
    metric_id: str = Field(min_length=1)
    value: FiniteFloat


class BindingArmUnitResult(ContractModel):
    split: ResolutionSplit
    independent_unit_id: UUID
    arm_id: str = Field(min_length=1)
    information_view_sha256: Sha256
    runtime_trace_sha256: Sha256
    budget_units: PositiveInt
    metrics: tuple[MetricObservation, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_metrics(self) -> Self:
        metric_ids = tuple(item.metric_id for item in self.metrics)
        if len(metric_ids) != len(set(metric_ids)):
            raise ValueError("one arm/unit row cannot repeat a metric")
        return self


class BindingResolutionExecutionTrace(ContractModel):
    trace_id: UUID
    binding: OpenBinding
    protocol_id: str = Field(min_length=1)
    protocol_content_sha256: Sha256
    frozen_at_utc: datetime
    execution_started_at_utc: datetime
    execution_completed_at_utc: datetime
    rows: tuple[BindingArmUnitResult, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _ordered_time(self) -> Self:
        times = (self.frozen_at_utc, self.execution_started_at_utc, self.execution_completed_at_utc)
        if any(value.tzinfo is None or value.utcoffset() is None for value in times):
            raise ValueError("binding execution times must be timezone-aware")
        frozen, started, completed = (value.astimezone(UTC) for value in times)
        if not frozen < started <= completed:
            raise ValueError("protocol must be frozen before execution starts")
        keys = tuple((row.split, row.independent_unit_id, row.arm_id) for row in self.rows)
        if len(keys) != len(set(keys)):
            raise ValueError("binding trace cannot repeat an arm x unit row")
        runtime_traces = tuple(row.runtime_trace_sha256 for row in self.rows)
        if len(runtime_traces) != len(set(runtime_traces)):
            raise ValueError("every arm x unit row requires its own runtime trace")
        return self


class ArmValidationScore(ContractModel):
    arm_id: str = Field(min_length=1)
    mean_validation_metric: FiniteFloat


class RecomputedConfirmatoryGate(ContractModel):
    metric_id: str = Field(min_length=1)
    mean_value: FiniteFloat
    direction: MetricDirection
    threshold: FiniteFloat
    passed: bool


class BindingResolutionResult(ContractModel):
    selected_arm_id: str = Field(min_length=1)
    validation_scores: tuple[ArmValidationScore, ...] = Field(min_length=1)
    confirmatory_gates: tuple[RecomputedConfirmatoryGate, ...] = Field(min_length=1)
    all_confirmatory_gates_passed: bool


def recompute_binding_resolution(
    protocol: BindingResolutionProtocol,
    trace: BindingResolutionExecutionTrace,
) -> BindingResolutionResult:
    """Validate exact coverage/fairness and recompute selection plus all gates."""

    protocol_type = PROTOCOL_TYPE_BY_BINDING[protocol.binding]
    protocol = protocol_type.model_validate(protocol.model_dump(mode="python"))  # type: ignore[assignment]
    trace = BindingResolutionExecutionTrace.model_validate(trace.model_dump(mode="python"))
    if (trace.binding, trace.protocol_id, trace.protocol_content_sha256) != (
        protocol.binding,
        protocol.protocol_id,
        content_sha256(protocol),
    ):
        raise ValueError("execution trace substitutes a different binding protocol")

    arm_ids = tuple(arm.arm_id for arm in protocol.arms)
    eligible = {arm.arm_id for arm in protocol.arms if arm.role is ArmRole.ELIGIBLE}
    required_metric_ids = {
        ResolutionSplit.VALIDATION: (protocol.validation_metric_id,),
        ResolutionSplit.CONFIRMATORY: tuple(gate.metric_id for gate in protocol.confirmatory_gates),
    }
    rows_by_split = {
        split: tuple(row for row in trace.rows if row.split is split) for split in ResolutionSplit
    }
    unit_ids_by_split: dict[ResolutionSplit, tuple[UUID, ...]] = {}
    for split, rows in rows_by_split.items():
        units = tuple(dict.fromkeys(row.independent_unit_id for row in rows))
        minimum = (
            protocol.minimum_validation_units
            if split is ResolutionSplit.VALIDATION
            else protocol.minimum_confirmatory_units
        )
        if len(units) < minimum:
            raise ValueError(f"{split.value} split has too few independent units")
        unit_ids_by_split[split] = units
        expected = {(unit, arm) for unit in units for arm in arm_ids}
        actual = {(row.independent_unit_id, row.arm_id) for row in rows}
        if actual != expected or len(rows) != len(expected):
            raise ValueError(f"{split.value} requires exact arm x independent-unit coverage")
        for row in rows:
            if tuple(item.metric_id for item in row.metrics) != required_metric_ids[split]:
                raise ValueError(f"{split.value} row metrics differ from the frozen protocol")
        for unit in units:
            matched = tuple(row for row in rows if row.independent_unit_id == unit)
            if len({row.information_view_sha256 for row in matched}) != 1:
                raise ValueError("arms on one unit must receive the identical information view")
            if len({row.budget_units for row in matched}) != 1:
                raise ValueError("arms on one unit must receive the identical execution budget")
    if set(unit_ids_by_split[ResolutionSplit.VALIDATION]) & set(
        unit_ids_by_split[ResolutionSplit.CONFIRMATORY]
    ):
        raise ValueError("validation and confirmatory unit UUIDs must be disjoint")

    validation_rows = rows_by_split[ResolutionSplit.VALIDATION]
    scores = tuple(
        ArmValidationScore(
            arm_id=arm_id,
            mean_validation_metric=mean(
                row.metrics[0].value for row in validation_rows if row.arm_id == arm_id
            ),
        )
        for arm_id in arm_ids
    )
    arm_order = {arm_id: index for index, arm_id in enumerate(arm_ids)}
    eligible_scores = tuple(item for item in scores if item.arm_id in eligible)
    if protocol.validation_direction is MetricDirection.MINIMIZE:
        selected = min(
            eligible_scores,
            key=lambda item: (item.mean_validation_metric, arm_order[item.arm_id]),
        ).arm_id
    else:
        selected = min(
            eligible_scores,
            key=lambda item: (-item.mean_validation_metric, arm_order[item.arm_id]),
        ).arm_id

    confirmatory_rows = tuple(
        row for row in rows_by_split[ResolutionSplit.CONFIRMATORY] if row.arm_id == selected
    )
    recomputed_gates: list[RecomputedConfirmatoryGate] = []
    for metric_index, gate in enumerate(protocol.confirmatory_gates):
        value = mean(row.metrics[metric_index].value for row in confirmatory_rows)
        passed = (
            value <= gate.threshold
            if gate.direction is MetricDirection.MINIMIZE
            else value >= gate.threshold
        )
        recomputed_gates.append(
            RecomputedConfirmatoryGate(
                metric_id=gate.metric_id,
                mean_value=value,
                direction=gate.direction,
                threshold=gate.threshold,
                passed=passed,
            )
        )
    return BindingResolutionResult(
        selected_arm_id=selected,
        validation_scores=scores,
        confirmatory_gates=tuple(recomputed_gates),
        all_confirmatory_gates_passed=all(item.passed for item in recomputed_gates),
    )


__all__ = [
    "ArmRole",
    "ArmValidationScore",
    "BindingArmUnitResult",
    "BindingResolutionExecutionTrace",
    "BindingResolutionProtocol",
    "BindingResolutionProtocolBase",
    "BindingResolutionResult",
    "CiavActionBudgetProtocol",
    "ConfirmatoryGate",
    "ConsolidationThresholdsProtocol",
    "ExactEnumerationFalsifierProtocol",
    "MetricDirection",
    "MetricObservation",
    "NeuralProposerArchitectureProtocol",
    "OpenBinding",
    "RecomputedConfirmatoryGate",
    "ResolutionArm",
    "ResolutionSplit",
    "TrainingScheduleProtocol",
    "load_binding_resolution_protocol",
    "recompute_binding_resolution",
]
