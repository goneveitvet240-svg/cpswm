"""Frozen design selection for Structure Two Combination A.

The selection receipt records what was chosen; it is not experimental evidence.
Confirmatory execution remains fail-closed until split, tuning, power, and
guardrail bindings are supplied in a separate protocol.
"""

from __future__ import annotations

import json
from enum import StrEnum
from itertools import product
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator

from cpswm.contracts.base import ContractModel
from cpswm.system.reproducibility import content_sha256

from .structure_two_evidence_artifacts import ExperimentalUnit, InterventionFactor

SHA256_PATTERN = r"^[0-9a-f]{64}$"
COMBINATION_A_SELECTION_ID = "structure-two-combination-a@0.1"


class PrimaryUtilityMetric(StrEnum):
    CUMULATIVE_ACTION_REGRET = "cumulative_action_regret"


class OptimizationDirection(StrEnum):
    MINIMIZE = "minimize"


class HardGuardrailMetric(StrEnum):
    OWNER_CONTAMINATION = "owner_contamination"
    RECOVERY_LATENCY = "recovery_latency"
    FULL_RERUN_EQUIVALENCE = "full_rerun_equivalence"


class OrdinaryGraphBaseline(StrEnum):
    GRAPH_FREE_MLP = "graph_free_mlp"
    R_GCN = "r_gcn"
    HGT = "hgt"


class RegimeBaseline(StrEnum):
    FACTORIZED_STICKY_FINITE_HMM = "factorized_sticky_finite_hmm"
    STICKY_HDP_HSMM = "sticky_hdp_hsmm"


class FactorialDesignKind(StrEnum):
    FULL_TWO_LEVEL_FIVE_FACTOR = "full_2x2x2x2x2"


class ExternalComparisonStage(StrEnum):
    O_STAR_FAITHFUL = "o_star_faithful"
    ENHANCED_O_STAR = "enhanced_o_star"


class ExecutionBindingRequirement(StrEnum):
    TRAIN_SPLIT = "train_split"
    VALIDATION_SPLIT = "validation_split"
    SEALED_TEST_SPLIT = "sealed_test_split"
    INDEPENDENT_TUNING_BUDGETS = "independent_tuning_budgets"
    PRIMARY_BENEFIT_MARGIN = "primary_benefit_margin"
    GUARDRAIL_THRESHOLDS = "guardrail_thresholds"
    POWER_ANALYSIS = "power_analysis"
    FACTORIAL_UNIT_MANIFEST = "factorial_unit_manifest"
    O_STAR_FIDELITY_MANIFEST = "o_star_fidelity_manifest"


REQUIRED_STRUCTURE_TWO_CAPABILITIES = frozenset(
    {
        "hidden_event_inference",
        "multi_actor_reasoning",
        "open_world_unknowns",
        "reversible_attribution",
        "embodied_execution_feedback",
    }
)
REQUIRED_GUARDRAILS = frozenset(HardGuardrailMetric)
REQUIRED_GRAPH_BASELINES = frozenset(OrdinaryGraphBaseline)
REQUIRED_REGIME_BASELINES = frozenset(RegimeBaseline)
REQUIRED_EXECUTION_BINDINGS = frozenset(ExecutionBindingRequirement)

COMBINATION_A_FACTOR_LEVELS: dict[InterventionFactor, tuple[str, str]] = {
    InterventionFactor.OBSERVATION_PROCESS: (
        "complete_observation",
        "selective_mnar_observation",
    ),
    InterventionFactor.ACTOR_MIXTURE: ("owner_only", "owner_plus_visitor"),
    InterventionFactor.IDENTITY_ASSOCIATION: (
        "verified_identity",
        "identity_association_error",
    ),
    InterventionFactor.OWNER_HABIT_REGIME: (
        "stationary_owner_habit",
        "owner_habit_change",
    ),
    InterventionFactor.TRANSIENT_NOISE: ("transient_noise_absent", "transient_noise_present"),
}


class CombinationAFactorialCell(ContractModel):
    """One design cell before households and episodes are allocated."""

    cell_id: str = Field(pattern=r"^A-[01]{5}$")
    levels: dict[InterventionFactor, str]

    @model_validator(mode="after")
    def _complete_levels(self) -> Self:
        if set(self.levels) != set(InterventionFactor):
            raise ValueError("Combination A cell must assign every intervention factor")
        for factor, level in self.levels.items():
            if level not in COMBINATION_A_FACTOR_LEVELS[factor]:
                raise ValueError(f"unregistered level for {factor.value}: {level}")
        return self


class StructureTwoCombinationASelection(ContractModel):
    """User-owned route choice without caller-controlled success claims."""

    schema_version: Literal["0.1.0"]
    selection_id: Literal["structure-two-combination-a@0.1"]
    decision_source: Literal["user_selection"]
    primary_utility_metric: PrimaryUtilityMetric
    optimization_direction: OptimizationDirection
    hard_guardrails: tuple[HardGuardrailMetric, ...]
    ordinary_graph_baselines: tuple[OrdinaryGraphBaseline, ...]
    regime_baselines: tuple[RegimeBaseline, ...]
    factorial_design: FactorialDesignKind
    factorial_independent_unit: ExperimentalUnit
    factor_levels: dict[InterventionFactor, tuple[str, str]]
    external_comparison_sequence: tuple[ExternalComparisonStage, ...]
    retained_capabilities: tuple[str, ...]
    unresolved_execution_bindings: tuple[ExecutionBindingRequirement, ...]

    @model_validator(mode="after")
    def _freeze_combination_a(self) -> Self:
        if self.primary_utility_metric is not PrimaryUtilityMetric.CUMULATIVE_ACTION_REGRET:
            raise ValueError("Combination A fixes cumulative action regret as primary utility")
        if self.optimization_direction is not OptimizationDirection.MINIMIZE:
            raise ValueError("cumulative action regret must be minimized")
        if set(self.hard_guardrails) != REQUIRED_GUARDRAILS:
            raise ValueError("Combination A requires all contamination/recovery guardrails")
        if set(self.ordinary_graph_baselines) != REQUIRED_GRAPH_BASELINES:
            raise ValueError("Combination A requires MLP, R-GCN, and HGT baselines")
        if set(self.regime_baselines) != REQUIRED_REGIME_BASELINES:
            raise ValueError("Combination A requires both selected HMM baselines")
        if self.factorial_design is not FactorialDesignKind.FULL_TWO_LEVEL_FIVE_FACTOR:
            raise ValueError("Combination A requires the complete two-level five-factor design")
        if self.factorial_independent_unit is not ExperimentalUnit.HOUSEHOLD:
            raise ValueError("Combination A fixes household as the independent unit")
        if self.factor_levels != COMBINATION_A_FACTOR_LEVELS:
            raise ValueError("Combination A factorial levels differ from the frozen semantics")
        if self.external_comparison_sequence != (
            ExternalComparisonStage.O_STAR_FAITHFUL,
            ExternalComparisonStage.ENHANCED_O_STAR,
        ):
            raise ValueError("Combination A requires faithful O-STaR before enhanced O-STaR")
        if not REQUIRED_STRUCTURE_TWO_CAPABILITIES.issubset(self.retained_capabilities):
            raise ValueError("Combination A cannot narrow the Structure Two capability set")
        if set(self.unresolved_execution_bindings) != REQUIRED_EXECUTION_BINDINGS:
            raise ValueError("selection receipt must expose every unresolved execution binding")
        return self

    @classmethod
    def load(cls, path: Path) -> Self:
        return cls.model_validate(json.loads(path.read_text(encoding="utf-8")))

    @property
    def content_sha256(self) -> str:
        return content_sha256(self)

    @property
    def confirmatory_execution_ready(self) -> bool:
        """A selection receipt alone can never authorize a confirmatory run."""

        return False

    def factorial_cells(self) -> tuple[CombinationAFactorialCell, ...]:
        factors = tuple(InterventionFactor)
        cells: list[CombinationAFactorialCell] = []
        for bits in product((0, 1), repeat=len(factors)):
            levels = {
                factor: self.factor_levels[factor][bit]
                for factor, bit in zip(factors, bits, strict=True)
            }
            cells.append(
                CombinationAFactorialCell(
                    cell_id="A-" + "".join(str(bit) for bit in bits),
                    levels=levels,
                )
            )
        return tuple(cells)


class GuardrailThresholdBinding(ContractModel):
    """Pre-run numerical thresholds; values must come from registered evidence."""

    owner_contamination_upper_bound: float = Field(ge=0.0, le=1.0)
    recovery_latency_upper_bound: float = Field(ge=0.0)
    full_rerun_absolute_tolerance: float = Field(gt=0.0)
    threshold_derivation_artifact_sha256: str = Field(pattern=SHA256_PATTERN)


class CombinationAConfirmatoryProtocol(ContractModel):
    """Resolved execution bindings; still contains no result or pass flags."""

    protocol_id: str = Field(min_length=1)
    design_selection_sha256: str = Field(pattern=SHA256_PATTERN)
    train_split_sha256: str = Field(pattern=SHA256_PATTERN)
    validation_split_sha256: str = Field(pattern=SHA256_PATTERN)
    sealed_test_split_sha256: str = Field(pattern=SHA256_PATTERN)
    visible_input_schema_sha256: str = Field(pattern=SHA256_PATTERN)
    shared_action_budget_sha256: str = Field(pattern=SHA256_PATTERN)
    independent_tuning_budget_sha256_by_method: dict[str, str]
    primary_superiority_margin: float = Field(ge=0.0)
    primary_margin_derivation_artifact_sha256: str = Field(pattern=SHA256_PATTERN)
    guardrails: GuardrailThresholdBinding
    target_power: float = Field(ge=0.8, lt=1.0)
    minimum_detectable_effect: float = Field(gt=0.0)
    power_analysis_artifact_sha256: str = Field(pattern=SHA256_PATTERN)
    factorial_unit_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    households_per_cell: int = Field(ge=2)
    o_star_fidelity_manifest_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def _confirmatory_bindings(self) -> Self:
        split_hashes = {
            self.train_split_sha256,
            self.validation_split_sha256,
            self.sealed_test_split_sha256,
        }
        if len(split_hashes) != 3:
            raise ValueError("train, validation, and sealed-test splits must be content-distinct")
        required_methods = {
            *(method.value for method in OrdinaryGraphBaseline),
            *(method.value for method in RegimeBaseline),
        }
        if set(self.independent_tuning_budget_sha256_by_method) != required_methods:
            raise ValueError("every Combination A learned baseline needs its own tuning budget")
        if any(
            not isinstance(value, str)
            or len(value) != 64
            or any(char not in "0123456789abcdef" for char in value)
            for value in self.independent_tuning_budget_sha256_by_method.values()
        ):
            raise ValueError("baseline tuning budgets must be content-addressed")
        return self


__all__ = [
    "COMBINATION_A_FACTOR_LEVELS",
    "COMBINATION_A_SELECTION_ID",
    "CombinationAConfirmatoryProtocol",
    "CombinationAFactorialCell",
    "ExecutionBindingRequirement",
    "ExternalComparisonStage",
    "FactorialDesignKind",
    "GuardrailThresholdBinding",
    "HardGuardrailMetric",
    "OptimizationDirection",
    "OrdinaryGraphBaseline",
    "PrimaryUtilityMetric",
    "RegimeBaseline",
    "StructureTwoCombinationASelection",
]
