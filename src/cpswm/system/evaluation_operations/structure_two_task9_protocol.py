"""Fail-closed formal protocol for Structure Two Task 9.

The verifier in this module performs local structural and arithmetic checks.
It deliberately cannot authenticate caller-authored evidence and therefore
can never open the formal Task 9 gate.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections import defaultdict
from enum import StrEnum
from itertools import pairwise
from pathlib import Path
from statistics import NormalDist
from typing import Annotated, Final, Literal

from pydantic import Field, model_validator

from cpswm.contracts.base import ContractModel
from cpswm.system.attestation import (
    FORMAL_ATTESTATION_ALGORITHM,
    Attestation,
    AttestationError,
    AttestationVerifier,
    Ed25519AttestationVerifier,
)
from cpswm.system.evaluation_operations.structure_two_selected_method import (
    SELECTED_METHOD_ID,
    StructureTwoSelectedMethod,
)
from cpswm.system.reproducibility import content_sha256

PROTOCOL_ID: Final = "structure-two-task9-four-coupling-protocol@1.1"
DEFAULT_PROTOCOL_PATH: Final = Path(
    "configs/project_two_experiments/structure_two_task9_four_coupling_protocol_v1_1.json"
)
SELECTED_METHOD_RECEIPT_PATH: Final = Path(
    "configs/project_two_experiments/structure_two_selected_method_v0_1.json"
)
SELECTED_METHOD_RECEIPT_FILE_SHA256: Final = (
    "eff5e472346209053fe867e2ab53fdc455861e1e20125f192e6993e33bb33951"
)
SELECTED_METHOD_RECEIPT_CONTENT_SHA256: Final = (
    "a3ccafd6612a6ee57a855e82572524622b6f15f305924b3de99bd3e94e17ed2f"
)
SHA256_PATTERN: Final = r"^[0-9a-f]{64}$"
SIGNATURE_PATTERN: Final = r"^[0-9a-f]{128}$"
BOOTSTRAP_CONFIDENCE_LEVEL: Final = 0.95
BOOTSTRAP_RESAMPLES: Final = 2000
BOOTSTRAP_SEED: Final = 90409
HOLM_ALPHA: Final = 0.05

CANONICAL_HOUSEHOLDS: Final = tuple(f"household-{index:03d}" for index in range(1, 49))
VALIDATION_HOUSEHOLDS: Final = CANONICAL_HOUSEHOLDS[:8]
CONFIRMATORY_HOUSEHOLDS: Final = CANONICAL_HOUSEHOLDS[8:]
CANONICAL_REPLICATE_SEEDS: Final = (104729, 130363)
CONFIRMATORY_CLUSTERS: Final = 40
CONFIRMATORY_UNITS: Final = 80
EPISODES_PER_CELL: Final = 5
MINIMUM_DETECTABLE_INTERACTION: Final = 0.25
MINIMUM_PRACTICAL_INTERACTION: Final = 0.25
ASSUMED_CLUSTER_STANDARD_DEVIATION: Final = 0.40
TARGET_POWER: Final = 0.80
PLANNED_POWER_AT_MDE: Final = 0.927
MINIMUM_POWERED_CLUSTERS: Final = 32
POPULATION_MANIFEST_ID: Final = "structure-two-task9-population@1.0"
IMPLEMENTATION_MANIFEST_ID: Final = "structure-two-task9-operator-implementations@1.1"
ATTESTATION_DOMAIN: Final = "cpswm.structure_two.task9.operator_execution.v2"

FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
NonNegativeFiniteFloat = Annotated[float, Field(ge=0.0, allow_inf_nan=False)]
Probability = Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]


class DefinitionStatus(StrEnum):
    DEFINED_NOT_RUN = "DEFINED_NOT_RUN"


class Task9Coupling(StrEnum):
    OPCEU_X_CF_BOCPD = "opceu_x_cf_bocpd"
    ORRER_CHEH_PCHMP_X_RGRC = "orrer_cheh_pchmp_x_rgrc"
    CF_BOCPD_X_CCRR = "cf_bocpd_x_ccrr"
    RGRC_CCRR_X_CIAV = "rgrc_ccrr_x_ciav"


CANONICAL_COUPLINGS: Final = tuple(Task9Coupling)
CANONICAL_OPERATOR_PAIRS: Final[dict[Task9Coupling, tuple[tuple[str, ...], tuple[str, ...]]]] = {
    Task9Coupling.OPCEU_X_CF_BOCPD: (("OPCEU",), ("CF-BOCPD",)),
    Task9Coupling.ORRER_CHEH_PCHMP_X_RGRC: (("ORRER_CHEH", "PCHMP"), ("RGRC",)),
    Task9Coupling.CF_BOCPD_X_CCRR: (("CF-BOCPD",), ("CCRR",)),
    Task9Coupling.RGRC_CCRR_X_CIAV: (("RGRC", "CCRR"), ("CIAV",)),
}
CANONICAL_OPERATOR_IDS: Final = (
    "OPCEU",
    "ORRER_CHEH",
    "PCHMP",
    "CF-BOCPD",
    "RGRC",
    "CCRR",
    "CIAV",
)
SELECTED_TO_TASK9_OPERATOR_ID: Final = (
    ("opceu", "OPCEU"),
    ("orrer_cheh", "ORRER_CHEH"),
    ("pchmp", "PCHMP"),
    ("cf_bocpd", "CF-BOCPD"),
    ("rgrc", "RGRC"),
    ("ccrr", "CCRR"),
    ("ciav", "CIAV"),
)


class FactorialCell(StrEnum):
    ZERO_ZERO = "00"
    ONE_ZERO = "10"
    ZERO_ONE = "01"
    ONE_ONE = "11"


CANONICAL_CELLS: Final = (
    FactorialCell.ZERO_ZERO,
    FactorialCell.ONE_ZERO,
    FactorialCell.ZERO_ONE,
    FactorialCell.ONE_ONE,
)
CELL_SWITCHES: Final[dict[FactorialCell, tuple[bool, bool]]] = {
    FactorialCell.ZERO_ZERO: (False, False),
    FactorialCell.ONE_ZERO: (True, False),
    FactorialCell.ZERO_ONE: (False, True),
    FactorialCell.ONE_ONE: (True, True),
}


class SemanticOutcome(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILURE = "failure"
    SAFETY_ABORT = "safety_abort"


CANONICAL_CONFIRMATORY_UNIT_IDS: Final = tuple(
    f"{household_id}::seed-{seed}"
    for household_id in CONFIRMATORY_HOUSEHOLDS
    for seed in CANONICAL_REPLICATE_SEEDS
)


def _population_payload() -> dict[str, object]:
    return {"manifest_id": POPULATION_MANIFEST_ID, "household_ids": CANONICAL_HOUSEHOLDS}


def _seed_payload() -> dict[str, object]:
    return {
        "manifest_id": POPULATION_MANIFEST_ID,
        "replicate_seeds": CANONICAL_REPLICATE_SEEDS,
    }


def _split_payload() -> dict[str, object]:
    return {
        "manifest_id": POPULATION_MANIFEST_ID,
        "validation_household_ids": VALIDATION_HOUSEHOLDS,
        "confirmatory_household_ids": CONFIRMATORY_HOUSEHOLDS,
        "confirmatory_unit_ids": CANONICAL_CONFIRMATORY_UNIT_IDS,
        "cluster_key": "household_id",
    }


def _power_payload() -> dict[str, object]:
    return {
        "method": "conservative_normal_approximation",
        "family_correction": "bonferroni_worst_case_for_holm",
        "familywise_alpha": HOLM_ALPHA,
        "target_power": TARGET_POWER,
        "minimum_detectable_interaction": MINIMUM_DETECTABLE_INTERACTION,
        "minimum_practical_interaction": MINIMUM_PRACTICAL_INTERACTION,
        "assumed_cluster_standard_deviation": ASSUMED_CLUSTER_STANDARD_DEVIATION,
        "minimum_powered_clusters": MINIMUM_POWERED_CLUSTERS,
        "planned_confirmatory_clusters": CONFIRMATORY_CLUSTERS,
        "planned_confirmatory_units": CONFIRMATORY_UNITS,
        "planned_power_at_mde": PLANNED_POWER_AT_MDE,
    }


def _implementation_manifest_payload() -> dict[str, object]:
    return {
        "manifest_id": IMPLEMENTATION_MANIFEST_ID,
        "enrollment_status": "NOT_ENROLLED",
        "operator_identities": tuple(
            {
                "operator_id": operator_id,
                "enrollment_status": "NOT_ENROLLED",
                "implementation_sha256": None,
            }
            for operator_id in CANONICAL_OPERATOR_IDS
        ),
        "runtime_hash_consistency_required": True,
        "source_bundle_binding_required": True,
        "local_verifier_may_claim_implementation_identity_verified": False,
    }


def _selected_method_binding_payload() -> dict[str, object]:
    return {
        "receipt_type": "structure_two_selected_method_receipt",
        "receipt_path": SELECTED_METHOD_RECEIPT_PATH.as_posix(),
        "selected_method_id": SELECTED_METHOD_ID,
        "selected_method_file_sha256": SELECTED_METHOD_RECEIPT_FILE_SHA256,
        "selected_method_content_sha256": SELECTED_METHOD_RECEIPT_CONTENT_SHA256,
        "selected_method_operator_ids": tuple(
            source for source, _ in SELECTED_TO_TASK9_OPERATOR_ID
        ),
        "task9_operator_ids": CANONICAL_OPERATOR_IDS,
        "operator_id_projection": tuple(
            {"selected_method_operator_id": source, "task9_operator_id": target}
            for source, target in SELECTED_TO_TASK9_OPERATOR_ID
        ),
    }


OPERATOR_IMPLEMENTATION_MANIFEST_SHA256: Final = content_sha256(_implementation_manifest_payload())


class CouplingSpec(ContractModel):
    coupling: Task9Coupling
    left_operator_ids: tuple[str, ...] = Field(min_length=1)
    right_operator_ids: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def canonical_pair(self) -> CouplingSpec:
        if (self.left_operator_ids, self.right_operator_ids) != CANONICAL_OPERATOR_PAIRS[
            self.coupling
        ]:
            raise ValueError(f"operator substitution for {self.coupling.value}")
        return self


class BindingPolicy(ContractModel):
    required_equal_fields: tuple[str, ...]
    paired_within_independent_unit: Literal[True]
    semantic_utility_recomputation_required: Literal[True]
    runtime_receipts_required_per_operator_per_cell: Literal[True]

    @model_validator(mode="after")
    def exact_fields(self) -> BindingPolicy:
        expected = (
            "visible_input_sha256",
            "information_policy_sha256",
            "truth_access_policy_sha256",
            "compute_budget_sha256",
            "action_budget_sha256",
            "verification_budget_sha256",
            "non_target_modules_sha256",
            "source_bundle_sha256",
            "episode_ids",
        )
        if self.required_equal_fields != expected:
            raise ValueError("Task 9 binding policy changed")
        return self


class PopulationCommitmentSpec(ContractModel):
    manifest_id: Literal["structure-two-task9-population@1.0"]
    household_ids: tuple[str, ...]
    replicate_seeds: tuple[int, ...]
    validation_household_ids: tuple[str, ...]
    confirmatory_household_ids: tuple[str, ...]
    confirmatory_cluster_count: Literal[40]
    confirmatory_unit_count: Literal[80]
    population_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    seed_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    split_manifest_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def exact_manifest(self) -> PopulationCommitmentSpec:
        if (
            self.household_ids != CANONICAL_HOUSEHOLDS
            or self.replicate_seeds != CANONICAL_REPLICATE_SEEDS
            or self.validation_household_ids != VALIDATION_HOUSEHOLDS
            or self.confirmatory_household_ids != CONFIRMATORY_HOUSEHOLDS
        ):
            raise ValueError("Task 9 population, seed, or split manifest changed")
        expected = (
            content_sha256(_population_payload()),
            content_sha256(_seed_payload()),
            content_sha256(_split_payload()),
        )
        observed = (
            self.population_manifest_sha256,
            self.seed_manifest_sha256,
            self.split_manifest_sha256,
        )
        if observed != expected:
            raise ValueError("Task 9 population/seed/split commitment hash mismatch")
        return self


class PowerAnalysisSpec(ContractModel):
    method: Literal["conservative_normal_approximation"]
    family_correction: Literal["bonferroni_worst_case_for_holm"]
    familywise_alpha: Probability = Field(gt=0.0, lt=1.0)
    target_power: Probability = Field(gt=0.0, lt=1.0)
    minimum_detectable_interaction: NonNegativeFiniteFloat = Field(gt=0.0)
    minimum_practical_interaction: NonNegativeFiniteFloat = Field(gt=0.0)
    assumed_cluster_standard_deviation: NonNegativeFiniteFloat = Field(gt=0.0)
    minimum_powered_clusters: int = Field(ge=20)
    planned_confirmatory_clusters: Literal[40]
    planned_confirmatory_units: Literal[80]
    planned_power_at_mde: Probability
    power_commitment_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def frozen_power(self) -> PowerAnalysisSpec:
        observed = self.model_dump(mode="python", exclude={"power_commitment_sha256"})
        if observed != _power_payload():
            raise ValueError("Task 9 MDE/power design changed")
        if self.power_commitment_sha256 != content_sha256(_power_payload()):
            raise ValueError("Task 9 power commitment hash mismatch")
        normal = NormalDist()
        critical = normal.inv_cdf(1.0 - self.familywise_alpha / 8.0)
        noncentrality = (
            self.minimum_detectable_interaction
            * math.sqrt(self.minimum_powered_clusters)
            / self.assumed_cluster_standard_deviation
        )
        conservative_power = (
            1.0 - normal.cdf(critical - noncentrality) + normal.cdf(-critical - noncentrality)
        )
        if conservative_power < self.target_power:
            raise ValueError("Task 9 cluster floor is underpowered for the frozen MDE")
        planned_noncentrality = (
            self.minimum_detectable_interaction
            * math.sqrt(self.planned_confirmatory_clusters)
            / self.assumed_cluster_standard_deviation
        )
        planned_power = (
            1.0
            - normal.cdf(critical - planned_noncentrality)
            + normal.cdf(-critical - planned_noncentrality)
        )
        if not math.isclose(
            self.planned_power_at_mde, round(planned_power, 3), rel_tol=0.0, abs_tol=1e-12
        ):
            raise ValueError("Task 9 planned power does not reproduce")
        return self


class UtilityPolicySpec(ContractModel):
    success_reward: FiniteFloat
    partial_reward: FiniteFloat
    failure_reward: FiniteFloat
    safety_abort_reward: FiniteFloat
    action_cost_per_unit: NonNegativeFiniteFloat
    verification_cost_per_action: NonNegativeFiniteFloat
    owner_contamination_cost_per_event: NonNegativeFiniteFloat
    safety_cost_per_violation: NonNegativeFiniteFloat
    episodes_per_cell: Literal[5]

    @model_validator(mode="after")
    def frozen_policy(self) -> UtilityPolicySpec:
        observed = tuple(self.model_dump(mode="python").values())
        expected = (1.0, 0.4, 0.0, -1.0, 0.02, 0.05, 0.75, 2.0, EPISODES_PER_CELL)
        if observed != expected:
            raise ValueError("Task 9 semantic utility policy changed")
        return self


class PairedClusterBootstrapSpec(ContractModel):
    method: Literal["paired_cluster_bootstrap"]
    independent_unit: Literal["household_seed"]
    cluster_key: Literal["household_id"]
    confidence_level: Probability = Field(gt=0.0, lt=1.0)
    resamples: int = Field(ge=1000)
    seed: int
    minimum_independent_units: Literal[80]
    minimum_clusters: Literal[40]

    @model_validator(mode="after")
    def frozen_bootstrap(self) -> PairedClusterBootstrapSpec:
        observed = (self.confidence_level, self.resamples, self.seed)
        expected = (BOOTSTRAP_CONFIDENCE_LEVEL, BOOTSTRAP_RESAMPLES, BOOTSTRAP_SEED)
        if observed != expected:
            raise ValueError("Task 9 paired-cluster-bootstrap parameters changed")
        return self


class HolmSpec(ContractModel):
    method: Literal["holm"]
    alpha: Probability = Field(gt=0.0, lt=1.0)
    family_size: Literal[4]
    family: tuple[Task9Coupling, ...]

    @model_validator(mode="after")
    def exact_family(self) -> HolmSpec:
        if self.alpha != HOLM_ALPHA or self.family != CANONICAL_COUPLINGS:
            raise ValueError("Holm family must be the ordered exact four-coupling set")
        return self


class OmnibusSpec(ContractModel):
    comparison_id: Literal["full_x_b_star"]
    status: DefinitionStatus
    counted_toward_four_coupling_family: Literal[False]
    separate_analysis_required: Literal[True]


class OperatorImplementationIdentitySpec(ContractModel):
    operator_id: str = Field(min_length=1)
    enrollment_status: Literal["NOT_ENROLLED"]
    implementation_sha256: None = None


class OperatorImplementationManifestSpec(ContractModel):
    manifest_id: Literal["structure-two-task9-operator-implementations@1.1"]
    enrollment_status: Literal["NOT_ENROLLED"]
    operator_identities: tuple[OperatorImplementationIdentitySpec, ...]
    runtime_hash_consistency_required: Literal[True]
    source_bundle_binding_required: Literal[True]
    local_verifier_may_claim_implementation_identity_verified: Literal[False]
    manifest_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def exact_unenrolled_manifest(self) -> OperatorImplementationManifestSpec:
        if tuple(item.operator_id for item in self.operator_identities) != CANONICAL_OPERATOR_IDS:
            raise ValueError("Task 9 operator implementation manifest changed")
        if self.manifest_sha256 != OPERATOR_IMPLEMENTATION_MANIFEST_SHA256:
            raise ValueError("Task 9 operator implementation manifest hash mismatch")
        return self


class OperatorIdentityProjection(ContractModel):
    selected_method_operator_id: str = Field(min_length=1)
    task9_operator_id: str = Field(min_length=1)


class SelectedMethodReceiptBindingSpec(ContractModel):
    """Byte- and content-level binding to the user-selected seven-operator receipt."""

    receipt_type: Literal["structure_two_selected_method_receipt"]
    receipt_path: Literal["configs/project_two_experiments/structure_two_selected_method_v0_1.json"]
    selected_method_id: Literal["structure-two-nap-rbtpr-rc@0.1"]
    selected_method_file_sha256: str = Field(pattern=SHA256_PATTERN)
    selected_method_content_sha256: str = Field(pattern=SHA256_PATTERN)
    selected_method_operator_ids: tuple[str, ...]
    task9_operator_ids: tuple[str, ...]
    operator_id_projection: tuple[OperatorIdentityProjection, ...]
    receipt_binding_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def exact_selected_method_receipt(self) -> SelectedMethodReceiptBindingSpec:
        expected = _selected_method_binding_payload()
        observed = self.model_dump(mode="python", exclude={"receipt_binding_sha256"})
        if observed != expected:
            raise ValueError("Task 9 selected-method receipt binding changed")
        if self.receipt_binding_sha256 != content_sha256(expected):
            raise ValueError("Task 9 selected-method receipt binding hash mismatch")
        return self


class IndependentCustodySpec(ContractModel):
    required: Literal[True]
    authority_role: Literal["independent_evidence_custodian"]
    attestation_domain: Literal["cpswm.structure_two.task9.operator_execution.v2"]
    trust_anchor_status: Literal["NOT_ENROLLED"]
    trust_anchor_manifest_sha256: None = None
    local_arithmetic_verifier_may_open_formal_gate: Literal[False]
    formal_gate_requires_external_verifier: Literal[True]
    external_freshness_and_replay_registry_required: Literal[True]


class Task9ProtocolDefinition(ContractModel):
    protocol_id: Literal["structure-two-task9-four-coupling-protocol@1.1"]
    schema_version: Literal["1.1.0"]
    definition_status: DefinitionStatus
    task9_result_available: Literal[False]
    seven_operator_ablation_authorized: Literal[False]
    primary_metric: Literal["cumulative_action_utility"]
    higher_is_better: Literal[True]
    interaction_estimand: Literal["U11-U10-U01+U00"]
    factorial_cells: tuple[FactorialCell, ...]
    couplings: tuple[CouplingSpec, ...]
    binding_policy: BindingPolicy
    population_commitment: PopulationCommitmentSpec
    power_analysis: PowerAnalysisSpec
    utility_policy: UtilityPolicySpec
    selected_method_binding: SelectedMethodReceiptBindingSpec
    operator_implementation_manifest: OperatorImplementationManifestSpec
    bootstrap: PairedClusterBootstrapSpec
    multiplicity: HolmSpec
    omnibus: OmnibusSpec
    independent_custody: IndependentCustodySpec
    claim_boundary: str = Field(min_length=1)

    @model_validator(mode="after")
    def canonical_definition(self) -> Task9ProtocolDefinition:
        if self.definition_status is not DefinitionStatus.DEFINED_NOT_RUN:
            raise ValueError("a Task 9 definition cannot claim the task was run")
        observed = tuple(item.coupling for item in self.couplings)
        if self.factorial_cells != CANONICAL_CELLS:
            raise ValueError("Task 9 requires ordered exact 00/10/01/11 cells")
        if observed != CANONICAL_COUPLINGS or len(set(observed)) != 4:
            raise ValueError("Task 9 requires the ordered exact four-coupling set")
        return self


class FrozenExecutionBindings(ContractModel):
    information_policy_sha256: str = Field(pattern=SHA256_PATTERN)
    truth_access_policy_sha256: str = Field(pattern=SHA256_PATTERN)
    compute_budget_sha256: str = Field(pattern=SHA256_PATTERN)
    action_budget_sha256: str = Field(pattern=SHA256_PATTERN)
    verification_budget_sha256: str = Field(pattern=SHA256_PATTERN)
    non_target_modules_sha256: str = Field(pattern=SHA256_PATTERN)
    source_bundle_sha256: str = Field(pattern=SHA256_PATTERN)


class SemanticUtilityObservation(ContractModel):
    """Raw semantic event: callers cannot directly supply reward or utility."""

    episode_id: str = Field(min_length=1)
    action_id: str = Field(min_length=1)
    outcome_event_id: str = Field(min_length=1)
    outcome: SemanticOutcome
    action_cost_units: int = Field(ge=0)
    verification_actions: int = Field(ge=0)
    owner_contamination_events: int = Field(ge=0)
    safety_violations: int = Field(ge=0)


def semantic_trace_sha256(observations: tuple[SemanticUtilityObservation, ...]) -> str:
    return content_sha256(tuple(item.model_dump(mode="python") for item in observations))


class UnverifiedCustodianAttestationClaim(ContractModel):
    """A caller-supplied envelope whose cryptography is not locally trusted."""

    authority_role: Literal["independent_evidence_custodian"]
    attestation_domain: Literal["cpswm.structure_two.task9.operator_execution.v2"]
    signature_algorithm: Literal["ed25519"]
    key_id: str = Field(min_length=1)
    signed_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    custody_record_sha256: str = Field(pattern=SHA256_PATTERN)
    signature_hex: str = Field(pattern=SIGNATURE_PATTERN)


class OperatorExecutionOutcome(StrEnum):
    DISABLED = "disabled"
    STATE_CHANGED = "state_changed"
    ENABLED_NO_OP = "enabled_no_op"


class EnabledNoOpReason(StrEnum):
    NO_ADMISSIBLE_STATE_TRANSITION = "no_admissible_state_transition"
    POSTCONDITION_ALREADY_SATISFIED = "postcondition_already_satisfied"
    FROZEN_POLICY_BLOCKED_TRANSITION = "frozen_policy_blocked_transition"


def operator_runtime_receipt_payload(
    *,
    receipt_id: str,
    run_id: str,
    execution_nonce: str,
    independent_unit_id: str,
    cell: FactorialCell,
    operator_id: str,
    enabled: bool,
    execution_outcome: OperatorExecutionOutcome,
    invocation_ids: tuple[str, ...],
    no_op_reason_code: EnabledNoOpReason | None,
    no_op_evidence_sha256: str | None,
    implementation_sha256: str,
    implementation_manifest_sha256: str,
    source_bundle_sha256: str,
    input_state_sha256: str,
    output_state_sha256: str,
    visible_input_sha256: str,
    raw_semantic_trace_sha256: str,
    runtime_event_log_sha256: str,
) -> dict[str, object]:
    return {
        "attestation_domain": ATTESTATION_DOMAIN,
        "receipt_id": receipt_id,
        "run_id": run_id,
        "execution_nonce": execution_nonce,
        "independent_unit_id": independent_unit_id,
        "cell": cell,
        "operator_id": operator_id,
        "enabled": enabled,
        "execution_outcome": execution_outcome.value,
        "invocation_ids": invocation_ids,
        "no_op_reason_code": (no_op_reason_code.value if no_op_reason_code is not None else None),
        "no_op_evidence_sha256": no_op_evidence_sha256,
        "implementation_sha256": implementation_sha256,
        "implementation_manifest_sha256": implementation_manifest_sha256,
        "source_bundle_sha256": source_bundle_sha256,
        "input_state_sha256": input_state_sha256,
        "output_state_sha256": output_state_sha256,
        "visible_input_sha256": visible_input_sha256,
        "raw_semantic_trace_sha256": raw_semantic_trace_sha256,
        "runtime_event_log_sha256": runtime_event_log_sha256,
    }


class OperatorRuntimeReceipt(ContractModel):
    receipt_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    execution_nonce: str = Field(min_length=16)
    independent_unit_id: str = Field(min_length=1)
    cell: FactorialCell
    operator_id: str = Field(min_length=1)
    enabled: bool
    execution_outcome: OperatorExecutionOutcome
    invocation_ids: tuple[str, ...]
    no_op_reason_code: EnabledNoOpReason | None = None
    no_op_evidence_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    implementation_sha256: str = Field(pattern=SHA256_PATTERN)
    implementation_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    source_bundle_sha256: str = Field(pattern=SHA256_PATTERN)
    input_state_sha256: str = Field(pattern=SHA256_PATTERN)
    output_state_sha256: str = Field(pattern=SHA256_PATTERN)
    visible_input_sha256: str = Field(pattern=SHA256_PATTERN)
    raw_semantic_trace_sha256: str = Field(pattern=SHA256_PATTERN)
    runtime_event_log_sha256: str = Field(pattern=SHA256_PATTERN)
    receipt_payload_sha256: str = Field(pattern=SHA256_PATTERN)
    attestation_claim: UnverifiedCustodianAttestationClaim
    enabled_no_op_attestation: Attestation | None = None

    @model_validator(mode="after")
    def structurally_bound(self) -> OperatorRuntimeReceipt:
        if len(self.invocation_ids) != len(set(self.invocation_ids)):
            raise ValueError("runtime receipt contains duplicate invocation ids")
        if self.execution_outcome is OperatorExecutionOutcome.DISABLED:
            if (
                self.enabled
                or self.invocation_ids
                or self.input_state_sha256 != self.output_state_sha256
            ):
                raise ValueError(
                    "disabled outcome claims enablement, execution, or state transition"
                )
            if any(
                value is not None
                for value in (
                    self.no_op_reason_code,
                    self.no_op_evidence_sha256,
                    self.enabled_no_op_attestation,
                )
            ):
                raise ValueError("disabled outcome cannot carry enabled-no-op evidence")
        elif self.execution_outcome is OperatorExecutionOutcome.STATE_CHANGED:
            if not self.enabled or not self.invocation_ids:
                raise ValueError("state-changed outcome lacks enabled invocation")
            if self.input_state_sha256 == self.output_state_sha256:
                raise ValueError("state-changed outcome did not change state")
            if any(
                value is not None
                for value in (
                    self.no_op_reason_code,
                    self.no_op_evidence_sha256,
                    self.enabled_no_op_attestation,
                )
            ):
                raise ValueError("state-changed outcome cannot carry enabled-no-op evidence")
        else:
            if not self.enabled or not self.invocation_ids:
                raise ValueError("enabled-no-op outcome lacks an enabled invocation")
            if self.input_state_sha256 != self.output_state_sha256:
                raise ValueError("enabled-no-op outcome changed state")
            if self.no_op_reason_code is None:
                raise ValueError("enabled-no-op outcome lacks a reason code")
            if self.no_op_evidence_sha256 is None or self.enabled_no_op_attestation is None:
                raise ValueError("enabled-no-op outcome lacks authenticated evidence")
            if (
                self.enabled_no_op_attestation.algorithm != FORMAL_ATTESTATION_ALGORITHM
                or self.enabled_no_op_attestation.domain != ATTESTATION_DOMAIN
            ):
                raise ValueError("enabled-no-op attestation is not formal or domain separated")
        expected = content_sha256(
            operator_runtime_receipt_payload(
                receipt_id=self.receipt_id,
                run_id=self.run_id,
                execution_nonce=self.execution_nonce,
                independent_unit_id=self.independent_unit_id,
                cell=self.cell,
                operator_id=self.operator_id,
                enabled=self.enabled,
                execution_outcome=self.execution_outcome,
                invocation_ids=self.invocation_ids,
                no_op_reason_code=self.no_op_reason_code,
                no_op_evidence_sha256=self.no_op_evidence_sha256,
                implementation_sha256=self.implementation_sha256,
                implementation_manifest_sha256=self.implementation_manifest_sha256,
                source_bundle_sha256=self.source_bundle_sha256,
                input_state_sha256=self.input_state_sha256,
                output_state_sha256=self.output_state_sha256,
                visible_input_sha256=self.visible_input_sha256,
                raw_semantic_trace_sha256=self.raw_semantic_trace_sha256,
                runtime_event_log_sha256=self.runtime_event_log_sha256,
            )
        )
        if self.receipt_payload_sha256 != expected:
            raise ValueError("operator runtime receipt payload hash mismatch")
        if self.attestation_claim.signed_receipt_sha256 != expected:
            raise ValueError("attestation claim is not bound to the runtime receipt")
        return self


def verify_authenticated_enabled_no_op(
    receipt: OperatorRuntimeReceipt, verifier: AttestationVerifier
) -> None:
    """Verify one enabled-no-op with an externally supplied verification-only key."""

    receipt = OperatorRuntimeReceipt.model_validate(receipt.model_dump(mode="python"))
    if receipt.execution_outcome is not OperatorExecutionOutcome.ENABLED_NO_OP:
        return
    if type(verifier) is not Ed25519AttestationVerifier or not verifier.formal_grade:
        raise AttestationError("enabled-no-op requires a formal asymmetric verifier")
    payload = operator_runtime_receipt_payload(
        receipt_id=receipt.receipt_id,
        run_id=receipt.run_id,
        execution_nonce=receipt.execution_nonce,
        independent_unit_id=receipt.independent_unit_id,
        cell=receipt.cell,
        operator_id=receipt.operator_id,
        enabled=receipt.enabled,
        execution_outcome=receipt.execution_outcome,
        invocation_ids=receipt.invocation_ids,
        no_op_reason_code=receipt.no_op_reason_code,
        no_op_evidence_sha256=receipt.no_op_evidence_sha256,
        implementation_sha256=receipt.implementation_sha256,
        implementation_manifest_sha256=receipt.implementation_manifest_sha256,
        source_bundle_sha256=receipt.source_bundle_sha256,
        input_state_sha256=receipt.input_state_sha256,
        output_state_sha256=receipt.output_state_sha256,
        visible_input_sha256=receipt.visible_input_sha256,
        raw_semantic_trace_sha256=receipt.raw_semantic_trace_sha256,
        runtime_event_log_sha256=receipt.runtime_event_log_sha256,
    )
    verifier.verify(ATTESTATION_DOMAIN, payload, receipt.enabled_no_op_attestation)


class ArmSemanticTrace(ContractModel):
    cell: FactorialCell
    left_operator_enabled: bool
    right_operator_enabled: bool
    run_id: str = Field(min_length=1)
    visible_input_sha256: str = Field(pattern=SHA256_PATTERN)
    semantic_trace_source_state_sha256: str = Field(pattern=SHA256_PATTERN)
    frozen_bindings: FrozenExecutionBindings
    observations: tuple[SemanticUtilityObservation, ...] = Field(
        min_length=EPISODES_PER_CELL, max_length=EPISODES_PER_CELL
    )
    raw_semantic_trace_sha256: str = Field(pattern=SHA256_PATTERN)
    operator_runtime_receipts: tuple[OperatorRuntimeReceipt, ...] = Field(min_length=1)
    diagnostic_metadata: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def cell_trace_receipts(self) -> ArmSemanticTrace:
        if (self.left_operator_enabled, self.right_operator_enabled) != CELL_SWITCHES[self.cell]:
            raise ValueError(f"factorial cell {self.cell.value} has substituted switch semantics")
        episode_ids = tuple(item.episode_id for item in self.observations)
        outcome_ids = tuple(item.outcome_event_id for item in self.observations)
        if len(set(episode_ids)) != EPISODES_PER_CELL:
            raise ValueError("semantic trace contains duplicate episode ids")
        if len(set(outcome_ids)) != EPISODES_PER_CELL:
            raise ValueError("semantic trace contains duplicate outcome event ids")
        if self.raw_semantic_trace_sha256 != semantic_trace_sha256(self.observations):
            raise ValueError("raw semantic trace hash does not derive from structured events")
        receipts = self.operator_runtime_receipts
        if len({item.receipt_id for item in receipts}) != len(receipts):
            raise ValueError("arm contains duplicate operator runtime receipts")
        for receipt in receipts:
            if (
                receipt.run_id != self.run_id
                or receipt.cell is not self.cell
                or receipt.visible_input_sha256 != self.visible_input_sha256
                or receipt.raw_semantic_trace_sha256 != self.raw_semantic_trace_sha256
            ):
                raise ValueError("operator runtime receipt is not bound to its arm and trace")
            if receipt.implementation_manifest_sha256 != OPERATOR_IMPLEMENTATION_MANIFEST_SHA256:
                raise ValueError("runtime receipt is not bound to frozen implementation manifest")
            if receipt.source_bundle_sha256 != self.frozen_bindings.source_bundle_sha256:
                raise ValueError("runtime receipt implementation is not bound to source bundle")
        if receipts[0].input_state_sha256 != self.visible_input_sha256:
            raise ValueError("runtime receipt chain does not start from the visible input")
        for previous, current in pairwise(receipts):
            if previous.output_state_sha256 != current.input_state_sha256:
                raise ValueError("operator runtime receipt state chain is broken")
        if receipts[-1].output_state_sha256 != self.semantic_trace_source_state_sha256:
            raise ValueError("semantic trace is not bound to final runtime state")
        return self


class IndependentUnitFourCellTrace(ContractModel):
    independent_unit_id: str = Field(min_length=1)
    cluster_id: str = Field(min_length=1)
    arms: tuple[ArmSemanticTrace, ...] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def exact_four_cells(self) -> IndependentUnitFourCellTrace:
        if tuple(arm.cell for arm in self.arms) != CANONICAL_CELLS:
            raise ValueError("independent unit must contain ordered exact 00/10/01/11 cells")
        if len({arm.run_id for arm in self.arms}) != 4:
            raise ValueError("independent unit replays a run id across factorial cells")
        first = self.arms[0]
        episode_ids = tuple(item.episode_id for item in first.observations)
        for arm in self.arms[1:]:
            if arm.visible_input_sha256 != first.visible_input_sha256:
                raise ValueError("four cells do not share the same visible input")
            if arm.frozen_bindings != first.frozen_bindings:
                raise ValueError(
                    "budget, information, source, or non-target module binding changed"
                )
            if tuple(item.episode_id for item in arm.observations) != episode_ids:
                raise ValueError("four cells do not share the same ordered episodes")
        return self


def _canonical_run_id(
    coupling: Task9Coupling, independent_unit_id: str, cell: FactorialCell
) -> str:
    return f"task9/{coupling.value}/{independent_unit_id}/{cell.value}"


class CouplingRunEvidence(ContractModel):
    coupling: Task9Coupling
    left_operator_ids: tuple[str, ...] = Field(min_length=1)
    right_operator_ids: tuple[str, ...] = Field(min_length=1)
    units: tuple[IndependentUnitFourCellTrace, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def canonical_receipts(self) -> CouplingRunEvidence:
        expected_pair = CANONICAL_OPERATOR_PAIRS[self.coupling]
        if (self.left_operator_ids, self.right_operator_ids) != expected_pair:
            raise ValueError(f"operator substitution for {self.coupling.value}")
        if len({unit.independent_unit_id for unit in self.units}) != len(self.units):
            raise ValueError("coupling run contains duplicate independent units")
        visible = tuple(unit.arms[0].visible_input_sha256 for unit in self.units)
        if len(set(visible)) != len(visible):
            raise ValueError("coupling run replays one visible input as multiple units")
        reference_bindings = self.units[0].arms[0].frozen_bindings
        if any(unit.arms[0].frozen_bindings != reference_bindings for unit in self.units[1:]):
            raise ValueError(
                "coupling run changed budget, information, source, or non-target bindings "
                "between independent units"
            )

        expected_operators = self.left_operator_ids + self.right_operator_ids
        receipt_ids: set[str] = set()
        nonces: set[str] = set()
        invocation_ids: set[str] = set()
        implementation_hashes: dict[str, str] = {}
        for unit in self.units:
            for arm in unit.arms:
                expected_run_id = _canonical_run_id(
                    self.coupling, unit.independent_unit_id, arm.cell
                )
                if arm.run_id != expected_run_id:
                    raise ValueError("runtime run id is not canonical for coupling/unit/cell")
                receipts = arm.operator_runtime_receipts
                if tuple(item.operator_id for item in receipts) != expected_operators:
                    raise ValueError("missing, duplicate, or substituted operator runtime receipt")
                for receipt in receipts:
                    expected_enabled = (
                        arm.left_operator_enabled
                        if receipt.operator_id in self.left_operator_ids
                        else arm.right_operator_enabled
                    )
                    if receipt.enabled is not expected_enabled:
                        raise ValueError("runtime receipt contradicts registered operator switch")
                    if receipt.receipt_id != f"{arm.run_id}/operator/{receipt.operator_id}":
                        raise ValueError("operator runtime receipt id is not canonical")
                    if receipt.independent_unit_id != unit.independent_unit_id:
                        raise ValueError("operator runtime receipt substituted independent unit")
                    if receipt.receipt_id in receipt_ids or receipt.execution_nonce in nonces:
                        raise ValueError("coupling run replays a runtime receipt or nonce")
                    receipt_ids.add(receipt.receipt_id)
                    nonces.add(receipt.execution_nonce)
                    previous_hash = implementation_hashes.setdefault(
                        receipt.operator_id, receipt.implementation_sha256
                    )
                    if previous_hash != receipt.implementation_sha256:
                        raise ValueError(
                            "operator implementation hash changed across cells or units"
                        )
                    for invocation_id in receipt.invocation_ids:
                        if invocation_id in invocation_ids:
                            raise ValueError("coupling run replays a runtime invocation")
                        invocation_ids.add(invocation_id)
        return self


class UnitInteraction(ContractModel):
    independent_unit_id: str = Field(min_length=1)
    cluster_id: str = Field(min_length=1)
    utility_00: FiniteFloat
    utility_10: FiniteFloat
    utility_01: FiniteFloat
    utility_11: FiniteFloat
    interaction: FiniteFloat

    @model_validator(mode="after")
    def semantic_did(self) -> UnitInteraction:
        expected = self.utility_11 - self.utility_10 - self.utility_01 + self.utility_00
        if not math.isclose(self.interaction, expected, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("unit interaction does not reproduce semantic utility DiD")
        return self


class CouplingAnalysis(ContractModel):
    coupling: Task9Coupling
    unit_interactions: tuple[UnitInteraction, ...] = Field(min_length=1)
    interaction_estimate: FiniteFloat
    confidence_interval_low: FiniteFloat
    confidence_interval_high: FiniteFloat
    raw_p_value: Probability
    holm_rank: int = Field(ge=1, le=4)
    holm_adjusted_p_value: Probability
    holm_reject_null: bool
    minimum_practical_interaction: NonNegativeFiniteFloat
    diagnostic_positive_interaction_established: bool
    bootstrap_method: Literal["paired_cluster_bootstrap"]
    bootstrap_seed: int
    bootstrap_resamples: int = Field(ge=1000)

    @model_validator(mode="after")
    def diagnostic_rule(self) -> CouplingAnalysis:
        if self.confidence_interval_low > self.confidence_interval_high:
            raise ValueError("Task 9 confidence interval is reversed")
        if self.minimum_practical_interaction != MINIMUM_PRACTICAL_INTERACTION:
            raise ValueError("Task 9 practical interaction threshold changed")
        expected = (
            self.holm_reject_null
            and self.interaction_estimate >= self.minimum_practical_interaction
            and self.confidence_interval_low >= self.minimum_practical_interaction
        )
        if self.diagnostic_positive_interaction_established is not expected:
            raise ValueError("diagnostic interaction flag does not follow registered rule")
        return self


class OmnibusEvidence(ContractModel):
    comparison_id: Literal["full_x_b_star"]
    counted_toward_four_coupling_family: Literal[False]
    semantic_summary: str = Field(min_length=1)


class Task9EvidenceSubmission(ContractModel):
    protocol_id: Literal["structure-two-task9-four-coupling-protocol@1.1"]
    runs: tuple[CouplingRunEvidence, ...]
    declared_analyses: tuple[CouplingAnalysis, ...]
    omnibus: OmnibusEvidence | None = None


class Task9VerificationReport(ContractModel):
    protocol_id: Literal["structure-two-task9-four-coupling-protocol@1.1"]
    definition_status: DefinitionStatus
    evidence_status: Literal["DIAGNOSTIC_ARITHMETIC_VERIFIED"]
    couplings: tuple[CouplingAnalysis, ...]
    exact_four_couplings_verified: Literal[True]
    selected_method_binding_commitment_verified: Literal[True]
    population_commitment_verified: Literal[True]
    raw_semantic_trace_derivation_verified: Literal[True]
    runtime_receipt_structure_verified: Literal[True]
    runtime_implementation_hash_consistency_verified: Literal[True]
    runtime_receipt_source_bundle_binding_verified: Literal[True]
    enabled_no_op_count: int = Field(ge=0)
    authenticated_enabled_no_op_count: int = Field(ge=0)
    all_enabled_no_ops_authenticated: Literal[True]
    operator_implementation_identity_status: Literal["NOT_ENROLLED"]
    operator_implementation_identity_verified: Literal[False]
    diagnostic_positive_interaction_count: int = Field(ge=0, le=4)
    diagnostic_all_four_interactions_positive: bool
    independent_attestation_verified: Literal[False]
    formal_gate_reason: Literal["TRUSTED_OUTER_ATTESTATION_NOT_VERIFIED"]
    task9_positive_gate_passed: Literal[False]
    omnibus: OmnibusEvidence | None
    omnibus_counted_toward_four_coupling_family: Literal[False]
    seven_operator_ablation_authorized: Literal[False]
    claim_boundary: str = Field(min_length=1)

    @model_validator(mode="after")
    def consistent_diagnostics(self) -> Task9VerificationReport:
        if tuple(item.coupling for item in self.couplings) != CANONICAL_COUPLINGS:
            raise ValueError("diagnostic report does not contain exact four couplings")
        expected_count = sum(
            item.diagnostic_positive_interaction_established for item in self.couplings
        )
        if self.diagnostic_positive_interaction_count != expected_count:
            raise ValueError("Task 9 diagnostic interaction count is inconsistent")
        if self.diagnostic_all_four_interactions_positive is not (expected_count == 4):
            raise ValueError("Task 9 diagnostic all-four flag is inconsistent")
        if self.authenticated_enabled_no_op_count != self.enabled_no_op_count:
            raise ValueError("Task 9 contains an unauthenticated enabled-no-op")
        expected_holm = _holm_adjust(
            {item.coupling: item.raw_p_value for item in self.couplings}, HOLM_ALPHA
        )
        for item in self.couplings:
            rank, adjusted, reject = expected_holm[item.coupling]
            if item.holm_rank != rank or not math.isclose(
                item.holm_adjusted_p_value, adjusted, rel_tol=0.0, abs_tol=1e-12
            ):
                raise ValueError("Task 9 Holm result is inconsistent")
            if item.holm_reject_null is not reject:
                raise ValueError("Task 9 Holm rejection is inconsistent")
        return self


def _strict_json_payload(raw: bytes, *, label: str) -> dict[str, object]:
    def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
        payload: dict[str, object] = {}
        for key, value in pairs:
            if key in payload:
                raise ValueError(f"duplicate JSON key in {label}: {key}")
            payload[key] = value
        return payload

    decoded = json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicate_keys)
    if not isinstance(decoded, dict):
        raise ValueError(f"{label} must be a JSON object")
    return decoded


def _verify_selected_method_receipt(
    repository_root: Path, binding: SelectedMethodReceiptBindingSpec
) -> None:
    receipt_path = repository_root / Path(binding.receipt_path)
    raw = receipt_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != binding.selected_method_file_sha256:
        raise ValueError("Task 9 selected-method receipt file hash mismatch")
    payload = _strict_json_payload(raw, label="selected-method receipt")
    selected = StructureTwoSelectedMethod.model_validate(payload)
    if selected.method_id != binding.selected_method_id:
        raise ValueError("Task 9 selected-method identity mismatch")
    if selected.content_sha256 != binding.selected_method_content_sha256:
        raise ValueError("Task 9 selected-method receipt content hash mismatch")
    selected_operator_ids = tuple(operator.value for operator in selected.operators)
    if selected_operator_ids != binding.selected_method_operator_ids:
        raise ValueError("Task 9 selected-method operator order or identity changed")
    projected = tuple(
        (item.selected_method_operator_id, item.task9_operator_id)
        for item in binding.operator_id_projection
    )
    if projected != SELECTED_TO_TASK9_OPERATOR_ID:
        raise ValueError("Task 9 operator projection changed")
    if binding.task9_operator_ids != CANONICAL_OPERATOR_IDS:
        raise ValueError("Task 9 does not retain the selected seven-operator identity set")


def load_task9_protocol(
    repository_root: Path, path: Path = DEFAULT_PROTOCOL_PATH
) -> Task9ProtocolDefinition:
    raw = (repository_root / path).read_bytes()
    payload = _strict_json_payload(raw, label="Task 9 protocol")
    definition = Task9ProtocolDefinition.model_validate(payload)
    _verify_selected_method_receipt(repository_root, definition.selected_method_binding)
    return definition


def _utility(observation: SemanticUtilityObservation, policy: UtilityPolicySpec) -> float:
    reward = {
        SemanticOutcome.SUCCESS: policy.success_reward,
        SemanticOutcome.PARTIAL: policy.partial_reward,
        SemanticOutcome.FAILURE: policy.failure_reward,
        SemanticOutcome.SAFETY_ABORT: policy.safety_abort_reward,
    }[observation.outcome]
    return reward - (
        observation.action_cost_units * policy.action_cost_per_unit
        + observation.verification_actions * policy.verification_cost_per_action
        + observation.owner_contamination_events * policy.owner_contamination_cost_per_event
        + observation.safety_violations * policy.safety_cost_per_violation
    )


def _unit_interactions(
    run: CouplingRunEvidence, policy: UtilityPolicySpec
) -> tuple[UnitInteraction, ...]:
    results: list[UnitInteraction] = []
    for unit in run.units:
        utilities = {
            arm.cell: sum(_utility(observation, policy) for observation in arm.observations)
            for arm in unit.arms
        }
        interaction = (
            utilities[FactorialCell.ONE_ONE]
            - utilities[FactorialCell.ONE_ZERO]
            - utilities[FactorialCell.ZERO_ONE]
            + utilities[FactorialCell.ZERO_ZERO]
        )
        results.append(
            UnitInteraction(
                independent_unit_id=unit.independent_unit_id,
                cluster_id=unit.cluster_id,
                utility_00=utilities[FactorialCell.ZERO_ZERO],
                utility_10=utilities[FactorialCell.ONE_ZERO],
                utility_01=utilities[FactorialCell.ZERO_ONE],
                utility_11=utilities[FactorialCell.ONE_ONE],
                interaction=interaction,
            )
        )
    return tuple(results)


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _paired_cluster_bootstrap(
    samples: tuple[UnitInteraction, ...],
    coupling: Task9Coupling,
    spec: PairedClusterBootstrapSpec,
) -> tuple[float, float, float, float]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for sample in samples:
        grouped[sample.cluster_id].append(sample.interaction)
    cluster_ids = sorted(grouped)
    means = {key: sum(values) / len(values) for key, values in grouped.items()}
    point = sum(means.values()) / len(means)
    rng = random.Random(f"{PROTOCOL_ID}:{coupling.value}:{spec.seed}")
    draws = [
        sum(means[cluster_ids[rng.randrange(len(cluster_ids))]] for _ in cluster_ids)
        / len(cluster_ids)
        for _ in range(spec.resamples)
    ]
    tail = (1.0 - spec.confidence_level) / 2.0
    low, high = _quantile(draws, tail), _quantile(draws, 1.0 - tail)
    centered = {key: value - point for key, value in means.items()}
    null_rng = random.Random(f"{PROTOCOL_ID}:{coupling.value}:{spec.seed}:null")
    null_draws = [
        sum(centered[cluster_ids[null_rng.randrange(len(cluster_ids))]] for _ in cluster_ids)
        / len(cluster_ids)
        for _ in range(spec.resamples)
    ]
    raw_p = (1.0 + sum(abs(value) >= abs(point) for value in null_draws)) / (spec.resamples + 1.0)
    return point, low, high, raw_p


def _holm_adjust(
    raw: dict[Task9Coupling, float], alpha: float
) -> dict[Task9Coupling, tuple[int, float, bool]]:
    ordered = sorted(raw, key=lambda coupling: (raw[coupling], coupling.value))
    result: dict[Task9Coupling, tuple[int, float, bool]] = {}
    running_max, continue_rejecting = 0.0, True
    for index, coupling in enumerate(ordered):
        multiplier = len(ordered) - index
        running_max = max(running_max, min(1.0, multiplier * raw[coupling]))
        reject = continue_rejecting and raw[coupling] <= alpha / multiplier
        continue_rejecting = continue_rejecting and reject
        result[coupling] = (index + 1, running_max, reject)
    return result


def _validate_population(runs: tuple[CouplingRunEvidence, ...]) -> None:
    expected_clusters = tuple(
        household for household in CONFIRMATORY_HOUSEHOLDS for _ in CANONICAL_REPLICATE_SEEDS
    )
    for run in runs:
        if tuple(unit.independent_unit_id for unit in run.units) != CANONICAL_CONFIRMATORY_UNIT_IDS:
            raise ValueError(
                "Task 9 requires the ordered exact frozen confirmatory population; "
                "posthoc unit selection is forbidden"
            )
        if tuple(unit.cluster_id for unit in run.units) != expected_clusters:
            raise ValueError("Task 9 unit-to-household cluster assignment changed")
    reference_visible = tuple(unit.arms[0].visible_input_sha256 for unit in runs[0].units)
    reference_bindings = runs[0].units[0].arms[0].frozen_bindings
    for run in runs[1:]:
        if tuple(unit.arms[0].visible_input_sha256 for unit in run.units) != reference_visible:
            raise ValueError("Task 9 couplings do not share frozen visible inputs")
        if run.units[0].arms[0].frozen_bindings != reference_bindings:
            raise ValueError("Task 9 couplings changed frozen execution bindings")


def _validate_implementation_hash_consistency(
    runs: tuple[CouplingRunEvidence, ...],
) -> None:
    """Require one runtime hash per operator, without claiming its authenticity."""

    observed: dict[str, str] = {}
    for run in runs:
        for unit in run.units:
            for arm in unit.arms:
                for receipt in arm.operator_runtime_receipts:
                    previous = observed.setdefault(
                        receipt.operator_id, receipt.implementation_sha256
                    )
                    if previous != receipt.implementation_sha256:
                        raise ValueError(
                            "operator implementation hash changed across couplings, cells, or units"
                        )
    if set(observed) != set(CANONICAL_OPERATOR_IDS) or len(observed) != len(CANONICAL_OPERATOR_IDS):
        raise ValueError("runtime evidence does not cover exact canonical operator identities")


def _verify_enabled_no_ops(
    runs: tuple[CouplingRunEvidence, ...], verifier: AttestationVerifier | None
) -> int:
    enabled_no_ops = tuple(
        receipt
        for run in runs
        for unit in run.units
        for arm in unit.arms
        for receipt in arm.operator_runtime_receipts
        if receipt.execution_outcome is OperatorExecutionOutcome.ENABLED_NO_OP
    )
    if enabled_no_ops and verifier is None:
        raise AttestationError(
            "enabled-no-op receipts require an external formal verification-only key"
        )
    if verifier is not None:
        for receipt in enabled_no_ops:
            verify_authenticated_enabled_no_op(receipt, verifier)
    return len(enabled_no_ops)


def evaluate_task9_runs(
    definition: Task9ProtocolDefinition,
    runs: tuple[CouplingRunEvidence, ...],
    *,
    omnibus: OmnibusEvidence | None = None,
    enabled_no_op_verifier: AttestationVerifier | None = None,
) -> Task9VerificationReport:
    """Compute diagnostics from raw events; keep the formal gate hard false."""

    definition = Task9ProtocolDefinition.model_validate(definition.model_dump(mode="python"))
    runs = tuple(CouplingRunEvidence.model_validate(run.model_dump(mode="python")) for run in runs)
    if omnibus is not None:
        omnibus = OmnibusEvidence.model_validate(omnibus.model_dump(mode="python"))
    observed = tuple(run.coupling for run in runs)
    if observed != CANONICAL_COUPLINGS or len(set(observed)) != 4:
        raise ValueError("Task 9 evidence must contain the ordered exact four-coupling set")
    _validate_population(runs)
    _validate_implementation_hash_consistency(runs)
    enabled_no_op_count = _verify_enabled_no_ops(runs, enabled_no_op_verifier)

    interim: dict[
        Task9Coupling, tuple[tuple[UnitInteraction, ...], float, float, float, float]
    ] = {}
    for run in runs:
        samples = _unit_interactions(run, definition.utility_policy)
        interim[run.coupling] = (
            samples,
            *_paired_cluster_bootstrap(samples, run.coupling, definition.bootstrap),
        )
    holm = _holm_adjust(
        {coupling: values[4] for coupling, values in interim.items()},
        definition.multiplicity.alpha,
    )
    analyses: list[CouplingAnalysis] = []
    practical = definition.power_analysis.minimum_practical_interaction
    for coupling in CANONICAL_COUPLINGS:
        samples, point, low, high, raw_p = interim[coupling]
        rank, adjusted, reject = holm[coupling]
        analyses.append(
            CouplingAnalysis(
                coupling=coupling,
                unit_interactions=samples,
                interaction_estimate=point,
                confidence_interval_low=low,
                confidence_interval_high=high,
                raw_p_value=raw_p,
                holm_rank=rank,
                holm_adjusted_p_value=adjusted,
                holm_reject_null=reject,
                minimum_practical_interaction=practical,
                diagnostic_positive_interaction_established=(
                    reject and point >= practical and low >= practical
                ),
                bootstrap_method="paired_cluster_bootstrap",
                bootstrap_seed=definition.bootstrap.seed,
                bootstrap_resamples=definition.bootstrap.resamples,
            )
        )
    count = sum(item.diagnostic_positive_interaction_established for item in analyses)
    return Task9VerificationReport(
        protocol_id=PROTOCOL_ID,
        definition_status=definition.definition_status,
        evidence_status="DIAGNOSTIC_ARITHMETIC_VERIFIED",
        couplings=tuple(analyses),
        exact_four_couplings_verified=True,
        selected_method_binding_commitment_verified=True,
        population_commitment_verified=True,
        raw_semantic_trace_derivation_verified=True,
        runtime_receipt_structure_verified=True,
        runtime_implementation_hash_consistency_verified=True,
        runtime_receipt_source_bundle_binding_verified=True,
        enabled_no_op_count=enabled_no_op_count,
        authenticated_enabled_no_op_count=enabled_no_op_count,
        all_enabled_no_ops_authenticated=True,
        operator_implementation_identity_status="NOT_ENROLLED",
        operator_implementation_identity_verified=False,
        diagnostic_positive_interaction_count=count,
        diagnostic_all_four_interactions_positive=count == 4,
        independent_attestation_verified=False,
        formal_gate_reason="TRUSTED_OUTER_ATTESTATION_NOT_VERIFIED",
        task9_positive_gate_passed=False,
        omnibus=omnibus,
        omnibus_counted_toward_four_coupling_family=False,
        seven_operator_ablation_authorized=False,
        claim_boundary=(
            "Caller-authored evidence passed local equality, structure, and arithmetic "
            "checks only. Operator implementation identities are NOT_ENROLLED; this "
            "verifier cannot authenticate implementation identity, independent custody, "
            "freshness, or replay state and cannot open the formal Task 9 gate."
        ),
    )


def verify_task9_submission(
    definition: Task9ProtocolDefinition,
    submission: Task9EvidenceSubmission,
    *,
    enabled_no_op_verifier: AttestationVerifier | None = None,
) -> Task9VerificationReport:
    definition = Task9ProtocolDefinition.model_validate(definition.model_dump(mode="python"))
    submission = Task9EvidenceSubmission.model_validate(submission.model_dump(mode="python"))
    report = evaluate_task9_runs(
        definition,
        submission.runs,
        omnibus=submission.omnibus,
        enabled_no_op_verifier=enabled_no_op_verifier,
    )
    if tuple(submission.declared_analyses) != report.couplings:
        raise ValueError("declared Task 9 analysis does not reproduce from raw semantic traces")
    return report


__all__ = [
    "CANONICAL_CELLS",
    "CANONICAL_CONFIRMATORY_UNIT_IDS",
    "CANONICAL_COUPLINGS",
    "CANONICAL_HOUSEHOLDS",
    "CANONICAL_OPERATOR_PAIRS",
    "CANONICAL_REPLICATE_SEEDS",
    "CONFIRMATORY_HOUSEHOLDS",
    "OPERATOR_IMPLEMENTATION_MANIFEST_SHA256",
    "ArmSemanticTrace",
    "CouplingRunEvidence",
    "EnabledNoOpReason",
    "FactorialCell",
    "FrozenExecutionBindings",
    "IndependentUnitFourCellTrace",
    "OmnibusEvidence",
    "OperatorExecutionOutcome",
    "OperatorIdentityProjection",
    "OperatorImplementationIdentitySpec",
    "OperatorImplementationManifestSpec",
    "OperatorRuntimeReceipt",
    "SelectedMethodReceiptBindingSpec",
    "SemanticOutcome",
    "SemanticUtilityObservation",
    "Task9Coupling",
    "Task9EvidenceSubmission",
    "Task9ProtocolDefinition",
    "Task9VerificationReport",
    "UnverifiedCustodianAttestationClaim",
    "evaluate_task9_runs",
    "load_task9_protocol",
    "operator_runtime_receipt_payload",
    "semantic_trace_sha256",
    "verify_authenticated_enabled_no_op",
    "verify_task9_submission",
]
