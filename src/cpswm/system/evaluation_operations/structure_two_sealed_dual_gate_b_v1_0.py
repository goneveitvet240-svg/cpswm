"""Historical sealed receipt layer for invalidated Gate B v0.7.

The v0.7 scorer remains diagnostic.  Formal promotion happens only here, from
runner-signed per-task readouts bound to the signed v0.9 canonical isolated
receipts.  Bare caller traces are never accepted by this module.

Gate B v0.7 was invalidated on 2026-09-05.  This module can still reproduce and
verify its historical chain, but every output is ineligible for formal Gate-B
or seven-operator authorization.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal, Self, cast

from pydantic import Field, StrictInt, model_validator

from cpswm.contracts.base import ContractModel, require_aware
from cpswm.system.attestation import (
    Attestation,
    AttestationError,
    Ed25519AttestationVerifier,
    attested_payload,
)
from cpswm.system.evaluation_operations.structure_two_canonical_episode_executor_v0_9 import (
    AGGREGATE_ATTESTATION_DOMAIN as CANONICAL_AGGREGATE_DOMAIN,
)
from cpswm.system.evaluation_operations.structure_two_canonical_episode_executor_v0_9 import (
    RECEIPT_ATTESTATION_DOMAIN as CANONICAL_TASK_DOMAIN,
)
from cpswm.system.evaluation_operations.structure_two_canonical_episode_executor_v0_9 import (
    BoundEpisodeExecutionReceiptV09,
    CanonicalPerEpisodeExecutionArtifactV09,
    artifact_content_sha256_v0_9,
)
from cpswm.system.evaluation_operations.structure_two_dual_gate_b_v0_7 import (
    ACTION_SCHEMA_ID,
    ACTION_SUPPORT,
    ACTION_SUPPORT_MANIFEST_SHA256,
    BELIEF_SCHEMA_ID,
    BELIEF_SUPPORT,
    BELIEF_SUPPORT_MANIFEST_SHA256,
    CANONICAL_COMPARISONS,
    CANONICAL_COMPONENT_IDS,
    CANONICAL_MECHANISM_EVENTS,
    EXPECTED_ARMS,
    ActionSelectionRule,
    BudgetEnvelope,
    CanonicalProbabilityDistribution,
    DualGateArmTrace,
    DualGateComparison,
    DualGateEpisode,
    DualGateStep,
    FrozenDualGateProtocol,
    InformationSetBinding,
    MechanismReceipt,
    MechanismRequirement,
    ReadoutStage,
    canonical_frozen_protocol_payload_v0_7,
    score_frozen_dual_gate_b_v0_7_diagnostic,
    validate_frozen_protocol_payload_v0_7,
)
from cpswm.system.evaluation_operations.structure_two_dual_gate_b_v0_7 import (
    PROTOCOL_ID as DUAL_GATE_PROTOCOL_ID,
)
from cpswm.system.evaluation_operations.structure_two_external_confirmation_gate_v0_9 import (
    OpeningConsumptionLedgerHeadV09,
)
from cpswm.system.evaluation_operations.structure_two_external_verification_freeze_v1_0 import (
    ExternalVerificationFreezeV10,
    FrozenPartyKeysV10,
    PublicKeyBindingV10,
    runner_verifiers_from_external_verification_freeze_v1_0,
)
from cpswm.system.evaluation_operations.structure_two_isolation_v0_9 import (
    ATTESTATION_DOMAIN as ISOLATION_DOMAIN,
)
from cpswm.system.evaluation_operations.structure_two_isolation_v0_9 import (
    DEFAULT_RESOURCE_LIMITS,
    IsolationExecutionReceiptV09,
    IsolationResourceLimitsV09,
    verify_isolation_receipt_v0_9,
)
from cpswm.system.evaluation_operations.structure_two_sealed_gate_b_opening_v0_9 import (
    ATTESTATION_DOMAIN as OPENING_DOMAIN,
)
from cpswm.system.evaluation_operations.structure_two_sealed_gate_b_opening_v0_9 import (
    SealedGateBOpeningV09,
)
from cpswm.system.reproducibility import canonical_json, content_sha256

PROTOCOL_ID = "structure-two-formal-sealed-dual-gate-b-receipt@1.0"
TASK_PROTOCOL_ID = "structure-two-dual-readout-task-receipt@1.0"
EXECUTION_PROTOCOL_ID = "structure-two-canonical-dual-readout-execution@1.0"

TASK_RUNNER_DOMAIN = "cpswm.evaluation.structure_two.dual_readout_task.runner.v1.0"
EXECUTION_EXECUTOR_DOMAIN = "cpswm.evaluation.structure_two.canonical_dual_readout.executor.v1.0"
REVIEWER_DOMAIN = "cpswm.evaluation.structure_two.sealed_dual_gate_b.reviewer.v1.0"
EXECUTOR_DOMAIN = "cpswm.evaluation.structure_two.sealed_dual_gate_b.executor.v1.0"
CUSTODIAN_DOMAIN = "cpswm.evaluation.structure_two.sealed_dual_gate_b.custodian.v1.0"
AUTHORITY_DOMAIN = "cpswm.evaluation.structure_two.sealed_dual_gate_b.authority_witness.v1.0"

CLAIM_BOUNDARY = (
    "This receipt is a verified historical replay of invalidated Gate B v0.7. "
    "It cannot establish a current Gate-B pass, native-method efficacy, combined "
    "authorization, or seven-operator ablation authorization. In addition, the v1.0 "
    "executor grants a whole visible episode to one process and trusts arm-emitted "
    "pre-action ordering and mechanism transitions; causal validity also requires a "
    "trusted stepwise broker and independent transition verifier."
)
_SHA256 = r"^[0-9a-f]{64}$"

CANONICAL_OBSERVATION_POLICY_V10: Mapping[str, Any] = {
    "protocol": "structure-two-dual-readout-observation-policy@1.0",
    "visible_input_semantics": "canonical-visible-episode-input-bytes",
    "history_semantics": "episode-static-fields-plus-visible-steps-through-current-step",
    "evaluator_truth_access": "forbidden",
}
CANONICAL_OBSERVATION_POLICY_SHA256 = content_sha256(CANONICAL_OBSERVATION_POLICY_V10)
CANONICAL_OFFLINE_BUDGET_POLICY_V10: Mapping[str, Any] = {
    "protocol": "structure-two-offline-dual-readout-budget-policy@1.0",
    "compute_unit_limit": "isolation-resource-limits.cpu_seconds",
    "active_observation_limit": 0,
    "physical_verification_limit": 0,
    "action_cost_limit": 0.0,
    "privacy_cost_limit": 0.0,
}
CANONICAL_OFFLINE_BUDGET_POLICY_SHA256 = content_sha256(CANONICAL_OFFLINE_BUDGET_POLICY_V10)


def _utc(value: datetime, label: str) -> None:
    require_aware(value, label)
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must use UTC")


def _verifier(binding: PublicKeyBindingV10) -> Ed25519AttestationVerifier:
    verifier = Ed25519AttestationVerifier.from_public_key_base64(
        key_id=binding.key_id,
        public_key_base64=binding.public_key_base64,
    )
    if verifier.public_key_sha256 != binding.public_key_sha256:
        raise AttestationError("public-key binding hash mismatch")
    return verifier


def _matches(binding: PublicKeyBindingV10, verifier: Ed25519AttestationVerifier) -> bool:
    return (
        binding.key_id == verifier.key_id
        and binding.public_key_base64 == verifier.public_key_base64
        and binding.public_key_sha256 == verifier.public_key_sha256
    )


def _freeze_content_hash(
    freeze: ExternalVerificationFreezeV10,
    supplied: str,
) -> str:
    expected = content_sha256(freeze.model_dump(mode="json"))
    if supplied != expected:
        raise ValueError("external verification freeze content hash mismatch")
    return expected


def _canonical_runner(
    freeze: ExternalVerificationFreezeV10,
) -> Ed25519AttestationVerifier:
    return runner_verifiers_from_external_verification_freeze_v1_0(freeze)[
        "canonical_episode_executor"
    ]


class FormalGateBUpstreamBindingsV10(ContractModel):
    """Hashes and ledger facts returned by the already verified sealed chain."""

    immutable_manifest_sha256: str = Field(pattern=_SHA256)
    producer_run_id: str = Field(min_length=1)
    gate_a_report_content_sha256: str = Field(pattern=_SHA256)
    sealed_opening_content_sha256: str = Field(pattern=_SHA256)
    sealed_opening_artifact_sha256: str = Field(pattern=_SHA256)
    opening_attempt_id: str = Field(min_length=16, max_length=128)
    opening_consumption_head_sha256: str = Field(pattern=_SHA256)
    ledger_identifier: str = Field(min_length=1)
    opening_consumption_ledger_sequence: StrictInt = Field(ge=0)
    opening_consumed_at_utc: datetime

    @model_validator(mode="after")
    def validate_time(self) -> Self:
        _utc(self.opening_consumed_at_utc, "opening consumption time")
        return self


class DenseDistributionV10(ContractModel):
    schema_id: Literal[
        "structure-two-common-joint-belief-readout@0.7",
        "structure-two-common-action-policy-readout@0.7",
    ]
    support_manifest_sha256: str = Field(pattern=_SHA256)
    probabilities: tuple[float, ...]

    @model_validator(mode="after")
    def validate_dense_distribution(self) -> Self:
        expected_manifest = (
            BELIEF_SUPPORT_MANIFEST_SHA256
            if self.schema_id == BELIEF_SCHEMA_ID
            else ACTION_SUPPORT_MANIFEST_SHA256
        )
        if self.support_manifest_sha256 != expected_manifest:
            raise ValueError("distribution support manifest is not the frozen ontology")
        self.as_v0_7()
        return self

    def as_v0_7(self) -> CanonicalProbabilityDistribution:
        support = BELIEF_SUPPORT if self.schema_id == BELIEF_SCHEMA_ID else ACTION_SUPPORT
        return CanonicalProbabilityDistribution(
            schema_id=self.schema_id,
            support=support,
            probabilities=self.probabilities,
        )


class InformationSetEvidenceV10(ContractModel):
    visible_input_sha256: str = Field(pattern=_SHA256)
    visible_history_sha256: str = Field(pattern=_SHA256)
    observation_policy_sha256: str = Field(
        default=CANONICAL_OBSERVATION_POLICY_SHA256, pattern=_SHA256
    )

    def as_v0_7(self) -> InformationSetBinding:
        return InformationSetBinding(**self.model_dump(mode="python"))


class BudgetEvidenceV10(ContractModel):
    compute_unit_limit: StrictInt = Field(ge=0)
    active_observation_limit: StrictInt = Field(ge=0)
    physical_verification_limit: StrictInt = Field(ge=0)
    action_cost_limit: float = Field(ge=0.0)
    privacy_cost_limit: float = Field(ge=0.0)

    @model_validator(mode="after")
    def validate_finite(self) -> Self:
        if not math.isfinite(self.action_cost_limit) or not math.isfinite(self.privacy_cost_limit):
            raise ValueError("budget costs must be finite")
        return self

    def as_v0_7(self) -> BudgetEnvelope:
        return BudgetEnvelope(**self.model_dump(mode="python"))


def canonical_offline_dual_readout_budget_v1_0(
    resource_limits: IsolationResourceLimitsV09,
) -> BudgetEvidenceV10:
    return BudgetEvidenceV10(
        compute_unit_limit=resource_limits.cpu_seconds,
        active_observation_limit=0,
        physical_verification_limit=0,
        action_cost_limit=0.0,
        privacy_cost_limit=0.0,
    )


class MechanismEventEvidenceV10(ContractModel):
    event: str = Field(min_length=1)
    component_id: str = Field(min_length=1)
    input_state_sha256: str = Field(pattern=_SHA256)
    output_state_sha256: str = Field(pattern=_SHA256)

    def as_v0_7(self) -> MechanismReceipt:
        return MechanismReceipt(**self.model_dump(mode="python"))


class DualReadoutStepEvidenceV10(ContractModel):
    step_index: StrictInt = Field(ge=0)
    step_id: str = Field(min_length=1)
    information_set: InformationSetEvidenceV10
    budget: BudgetEvidenceV10
    readout_stage: Literal["pre_action_pre_evaluator_truth"] = (
        ReadoutStage.PRE_ACTION_PRE_EVALUATOR_TRUTH.value
    )
    evaluator_truth_accessed: Literal[False] = False
    belief: DenseDistributionV10
    action_policy: DenseDistributionV10
    selected_action: str = Field(min_length=1)
    action_selection_rule: Literal["deterministic_argmax_lexical_tie_break"] = (
        ActionSelectionRule.DETERMINISTIC_ARGMAX_LEXICAL.value
    )
    mechanism_events: tuple[MechanismEventEvidenceV10, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_step(self) -> Self:
        if self.belief.schema_id != BELIEF_SCHEMA_ID:
            raise ValueError("belief readout does not use the canonical belief schema")
        if self.action_policy.schema_id != ACTION_SCHEMA_ID:
            raise ValueError("action readout does not use the canonical action schema")
        if len({row.event for row in self.mechanism_events}) != len(self.mechanism_events):
            raise ValueError("mechanism events must be unique within a step")
        self.as_v0_7()
        return self

    def as_v0_7(self) -> DualGateStep:
        return DualGateStep(
            step_id=self.step_id,
            information_set=self.information_set.as_v0_7(),
            budget=self.budget.as_v0_7(),
            readout_stage=ReadoutStage(self.readout_stage),
            evaluator_truth_accessed=self.evaluator_truth_accessed,
            belief=self.belief.as_v0_7(),
            action_policy=self.action_policy.as_v0_7(),
            selected_action=self.selected_action,
            action_selection_rule=ActionSelectionRule(self.action_selection_rule),
            mechanism_receipts=tuple(row.as_v0_7() for row in self.mechanism_events),
        )


class DualReadoutTaskOutputV10(ContractModel):
    """Instrumented arm output written inside the real isolation boundary."""

    protocol: Literal["structure-two-isolated-dual-readout-output@1.0"] = (
        "structure-two-isolated-dual-readout-output@1.0"
    )
    external_verification_freeze_content_sha256: str = Field(pattern=_SHA256)
    canonical_execution_content_sha256: str = Field(pattern=_SHA256)
    canonical_execution_id: str = Field(min_length=16)
    canonical_task_receipt_content_sha256: str = Field(pattern=_SHA256)
    canonical_isolation_receipt_content_sha256: str = Field(pattern=_SHA256)
    task_index: StrictInt = Field(ge=0)
    arm: str = Field(min_length=1)
    episode_id: str = Field(min_length=1)
    instrumented_canonical_rerun: Literal[True]
    pre_action_readouts_emitted_inside_arm_execution: Literal[True]
    steps: tuple[DualReadoutStepEvidenceV10, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_steps(self) -> Self:
        if tuple(row.step_index for row in self.steps) != tuple(range(len(self.steps))):
            raise ValueError("isolated dual-readout steps must be contiguous and zero based")
        return self


class DualReadoutCanonicalContextV10(ContractModel):
    """Read-only facts made available to the instrumented arm process."""

    protocol: Literal["structure-two-dual-readout-canonical-context@1.0"] = (
        "structure-two-dual-readout-canonical-context@1.0"
    )
    external_verification_freeze_content_sha256: str = Field(pattern=_SHA256)
    canonical_execution_content_sha256: str = Field(pattern=_SHA256)
    canonical_execution_id: str = Field(min_length=16)
    canonical_task_receipt_content_sha256: str = Field(pattern=_SHA256)
    canonical_isolation_receipt_content_sha256: str = Field(pattern=_SHA256)
    source_task_content_sha256: str = Field(pattern=_SHA256)
    sealed_opening_artifact_sha256: str = Field(pattern=_SHA256)
    task_index: StrictInt = Field(ge=0)
    arm: str = Field(min_length=1)
    episode_id: str = Field(min_length=1)
    expected_step_count: StrictInt = Field(gt=0)
    observation_policy_sha256: str = Field(
        default=CANONICAL_OBSERVATION_POLICY_SHA256, pattern=_SHA256
    )
    expected_information_sets: tuple[InformationSetEvidenceV10, ...] = Field(min_length=1)
    budget_policy_sha256: str = Field(
        default=CANONICAL_OFFLINE_BUDGET_POLICY_SHA256, pattern=_SHA256
    )
    expected_budget: BudgetEvidenceV10

    @model_validator(mode="after")
    def validate_expected_information_sets(self) -> Self:
        if self.observation_policy_sha256 != CANONICAL_OBSERVATION_POLICY_SHA256:
            raise ValueError("canonical context used a noncanonical observation policy")
        if self.budget_policy_sha256 != CANONICAL_OFFLINE_BUDGET_POLICY_SHA256:
            raise ValueError("canonical context used a noncanonical budget policy")
        if len(self.expected_information_sets) != self.expected_step_count:
            raise ValueError("canonical context information-set coverage is incomplete")
        return self


@dataclass(frozen=True, slots=True)
class DualReadoutIsolationVerificationInputsV10:
    """Verifier-owned paths for one instrumented rerun of the frozen arm."""

    implementation_bundle_path: Path
    visible_input_path: Path
    canonical_context_path: Path
    isolation_working_directory: Path
    output_path: Path
    isolation_receipt_payload: Mapping[str, Any]
    timeout_seconds: int
    resource_limits: IsolationResourceLimitsV09 = DEFAULT_RESOURCE_LIMITS


class DualReadoutTaskReceiptV10(ContractModel):
    protocol: Literal["structure-two-dual-readout-task-receipt@1.0"] = (
        "structure-two-dual-readout-task-receipt@1.0"
    )
    external_verification_freeze_content_sha256: str = Field(pattern=_SHA256)
    forbidden_seed_namespaces_sha256: str = Field(pattern=_SHA256)
    canonical_execution_content_sha256: str = Field(pattern=_SHA256)
    canonical_execution_id: str = Field(min_length=16)
    task_index: StrictInt = Field(ge=0)
    arm: str = Field(min_length=1)
    episode_id: str = Field(min_length=1)
    canonical_episode_receipt_content_sha256: str = Field(pattern=_SHA256)
    canonical_isolation_receipt_content_sha256: str = Field(pattern=_SHA256)
    canonical_candidate_output_artifact_sha256: str = Field(pattern=_SHA256)
    dual_readout_context_artifact_sha256: str = Field(pattern=_SHA256)
    dual_readout_context_content_sha256: str = Field(pattern=_SHA256)
    dual_readout_output_artifact_sha256: str = Field(pattern=_SHA256)
    dual_readout_output_content_sha256: str = Field(pattern=_SHA256)
    dual_readout_isolation_receipt_content_sha256: str = Field(pattern=_SHA256)
    instrumented_canonical_rerun_verified: Literal[True]
    deterministic_action_mechanism_equality_verified: Literal[True]
    belief_support_manifest_sha256: str = Field(
        default=BELIEF_SUPPORT_MANIFEST_SHA256, pattern=_SHA256
    )
    action_support_manifest_sha256: str = Field(
        default=ACTION_SUPPORT_MANIFEST_SHA256, pattern=_SHA256
    )
    steps: tuple[DualReadoutStepEvidenceV10, ...] = Field(min_length=1)
    runner: PublicKeyBindingV10
    runner_attestation: Attestation | None = None

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if self.belief_support_manifest_sha256 != BELIEF_SUPPORT_MANIFEST_SHA256:
            raise ValueError("task receipt used a noncanonical belief support manifest")
        if self.action_support_manifest_sha256 != ACTION_SUPPORT_MANIFEST_SHA256:
            raise ValueError("task receipt used a noncanonical action support manifest")
        if tuple(step.step_index for step in self.steps) != tuple(range(len(self.steps))):
            raise ValueError("dual-readout steps must be contiguous and zero based")
        if len({step.step_id for step in self.steps}) != len(self.steps):
            raise ValueError("dual-readout step IDs must be unique")
        return self

    @property
    def content_sha256(self) -> str:
        return content_sha256(self.model_dump(mode="json"))

    def as_v0_7(self) -> DualGateEpisode:
        return DualGateEpisode(
            episode_id=self.episode_id,
            steps=tuple(step.as_v0_7() for step in self.steps),
        )


def _task_payload(record: DualReadoutTaskReceiptV10) -> dict[str, Any]:
    return attested_payload(record, exclude=frozenset({"runner_attestation"}))


def _verify_source_receipt(
    source: BoundEpisodeExecutionReceiptV09,
    *,
    runner: Ed25519AttestationVerifier,
) -> None:
    receipt = source.receipt
    if (
        receipt.runner_key_id != runner.key_id
        or receipt.runner_public_key_base64 != runner.public_key_base64
        or receipt.runner_public_key_sha256 != runner.public_key_sha256
    ):
        raise AttestationError("canonical task receipt used an unregistered runner")
    runner.verify(CANONICAL_TASK_DOMAIN, attested_payload(receipt), receipt.attestation)
    isolation = source.isolation.receipt
    if (
        isolation.executor_key_id != runner.key_id
        or isolation.executor_public_key_base64 != runner.public_key_base64
        or isolation.executor_public_key_sha256 != runner.public_key_sha256
    ):
        raise AttestationError("canonical isolation receipt used an unregistered runner")
    runner.verify(
        ISOLATION_DOMAIN,
        isolation.model_dump(mode="json", exclude={"executor_attestation"}),
        isolation.executor_attestation,
    )
    if isolation.formal_isolation_verified is not True or isolation.status != "ISOLATION_PASSED":
        raise ValueError("canonical task lacks a positive real-isolation receipt")


def _verify_step_matches_source(
    step: DualReadoutStepEvidenceV10,
    source_step: Any,
    *,
    arm: str,
    expected_information_set: InformationSetEvidenceV10,
    expected_budget: BudgetEvidenceV10,
) -> None:
    if step.step_index != source_step.step_index:
        raise ValueError("dual-readout step index differs from canonical receipt")
    if step.selected_action != source_step.action:
        raise ValueError("dual-readout selected action differs from canonical receipt")
    if step.information_set != expected_information_set:
        raise ValueError("dual-readout information set differs from the visible prefix")
    if step.budget != expected_budget:
        raise ValueError("dual-readout budget differs from the frozen offline policy")
    expected = tuple(
        (
            event,
            CANONICAL_COMPONENT_IDS[arm],
            source_step.input_state_sha256,
            source_step.output_state_sha256,
        )
        for event in source_step.mechanism_events
    )
    actual = tuple(
        (
            row.event,
            row.component_id,
            row.input_state_sha256,
            row.output_state_sha256,
        )
        for row in step.mechanism_events
    )
    if actual != expected:
        raise ValueError("dual-readout mechanism evidence differs from canonical receipt")


DUAL_OUTPUT_LABEL = "dual_readout_output"
DUAL_OUTPUT_RELATIVE_PATH = "dual_readout_output.json"
DUAL_CONTEXT_LABEL = "canonical_dual_readout_context"


def _instrumented_rerun_arguments(
    *,
    entrypoint_path: Path,
    visible_input_path: Path,
    canonical_context_path: Path,
    output_path: Path,
    source: BoundEpisodeExecutionReceiptV09,
    freeze_content_sha256: str,
) -> tuple[str, ...]:
    return (
        str(entrypoint_path),
        "--visible-input",
        str(visible_input_path),
        "--canonical-context",
        str(canonical_context_path),
        "--output",
        str(output_path),
        "--task-content-sha256",
        source.receipt.task_content_sha256,
        "--instrumented-dual-readout-v1",
        "--external-verification-freeze-content-sha256",
        freeze_content_sha256,
    )


def _load_dual_context(
    path: Path,
) -> tuple[DualReadoutCanonicalContextV10, str, str]:
    _reject_symlink_chain(path, label="dual-readout canonical context")
    before = artifact_content_sha256_v0_9(path)
    encoded = path.read_bytes()
    try:
        payload = json.loads(encoded, object_pairs_hook=_reject_duplicate_json_keys)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("dual-readout canonical context is unreadable JSON") from exc
    after = artifact_content_sha256_v0_9(path)
    if before != after:
        raise ValueError("dual-readout canonical context changed while it was loaded")
    if not isinstance(payload, dict):
        raise ValueError("dual-readout canonical context must be a JSON object")
    if encoded != canonical_json(payload).encode("utf-8"):
        raise ValueError("dual-readout canonical context bytes are noncanonical")
    raw = dict(payload)
    stored = raw.pop("content_sha256", None)
    if not isinstance(stored, str) or content_sha256(raw) != stored:
        raise ValueError("dual-readout canonical context content hash mismatch")
    context = DualReadoutCanonicalContextV10.model_validate(raw)
    if raw != context.model_dump(mode="json"):
        raise ValueError("dual-readout canonical context encoding is noncanonical")
    return context, stored, after


def _load_dual_output(
    path: Path,
) -> tuple[DualReadoutTaskOutputV10, str, str]:
    _reject_symlink_chain(path, label="dual-readout output")
    before = artifact_content_sha256_v0_9(path)
    encoded = path.read_bytes()
    try:
        payload = json.loads(encoded, object_pairs_hook=_reject_duplicate_json_keys)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("isolated dual-readout output is unreadable JSON") from exc
    after = artifact_content_sha256_v0_9(path)
    if before != after:
        raise ValueError("isolated dual-readout output changed while it was loaded")
    if not isinstance(payload, dict):
        raise ValueError("isolated dual-readout output must be a JSON object")
    if encoded != canonical_json(payload).encode("utf-8"):
        raise ValueError("isolated dual-readout output bytes are noncanonical")
    raw = dict(payload)
    stored = raw.pop("content_sha256", None)
    if not isinstance(stored, str) or content_sha256(raw) != stored:
        raise ValueError("isolated dual-readout output content hash mismatch")
    output = DualReadoutTaskOutputV10.model_validate(raw)
    if raw != output.model_dump(mode="json"):
        raise ValueError("isolated dual-readout output encoding is noncanonical")
    return output, stored, after


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"isolated dual-readout output duplicated key {key!r}")
        result[key] = value
    return result


def _reject_symlink_chain(path: Path, *, label: str) -> None:
    absolute = path.absolute()
    cursor = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError(f"{label} must not traverse a symlink")


def _content_bound_artifact_hash(path: Path, *, expected: str, label: str) -> None:
    _reject_symlink_chain(path, label=label)
    if artifact_content_sha256_v0_9(path) != expected:
        raise ValueError(f"{label} differs from the canonical execution binding")


def canonical_dual_readout_information_sets_v1_0(
    visible_input_path: Path,
    *,
    expected_visible_input_artifact_sha256: str,
    expected_step_count: int,
) -> tuple[InformationSetEvidenceV10, ...]:
    """Recompute every pre-action information-set identity from live visible bytes."""

    _reject_symlink_chain(visible_input_path, label="instrumented rerun visible input")
    before = artifact_content_sha256_v0_9(visible_input_path)
    encoded = visible_input_path.read_bytes()
    try:
        payload = json.loads(encoded, object_pairs_hook=_reject_duplicate_json_keys)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("canonical visible input is unreadable JSON") from exc
    after = artifact_content_sha256_v0_9(visible_input_path)
    if before != after:
        raise ValueError("canonical visible input changed while deriving information sets")
    if before != expected_visible_input_artifact_sha256:
        raise ValueError("canonical visible input differs from its execution binding")
    if not isinstance(payload, dict) or payload.get("protocol") != (
        "structure-two-visible-episode-input@0.9"
    ):
        raise ValueError("canonical visible input uses the wrong protocol")
    if encoded != canonical_json(payload).encode("utf-8"):
        raise ValueError("canonical visible input bytes are noncanonical")
    episode = payload.get("episode")
    if not isinstance(episode, dict):
        raise ValueError("canonical visible input lacks an episode object")
    steps = episode.get("steps")
    if not isinstance(steps, list) or len(steps) != expected_step_count:
        raise ValueError("canonical visible input step coverage differs from the task")
    episode_static = {key: value for key, value in episode.items() if key != "steps"}
    return tuple(
        InformationSetEvidenceV10(
            visible_input_sha256=before,
            visible_history_sha256=content_sha256(
                {
                    "protocol": "structure-two-visible-prefix-identity@1.0",
                    "visible_input_protocol": payload["protocol"],
                    "episode_static": episode_static,
                    "visible_steps_through_current": steps[: step_index + 1],
                    "current_step_index": step_index,
                }
            ),
            observation_policy_sha256=CANONICAL_OBSERVATION_POLICY_SHA256,
        )
        for step_index in range(expected_step_count)
    )


def _verify_instrumented_rerun(
    *,
    external_verification_freeze: ExternalVerificationFreezeV10,
    freeze_content_sha256: str,
    canonical_execution: CanonicalPerEpisodeExecutionArtifactV09,
    canonical_execution_content_sha256: str,
    source: BoundEpisodeExecutionReceiptV09,
    isolation_inputs: DualReadoutIsolationVerificationInputsV10,
) -> tuple[
    DualReadoutTaskOutputV10,
    str,
    str,
    str,
    str,
    str,
    IsolationExecutionReceiptV09,
]:
    runner = _canonical_runner(external_verification_freeze)
    arm_bindings = {binding.arm: binding for binding in canonical_execution.arm_bundle_bindings}
    episode_bindings = {
        binding.episode_id: binding for binding in canonical_execution.episode_input_bindings
    }
    try:
        arm_binding = arm_bindings[source.receipt.arm]
        input_binding = episode_bindings[source.receipt.episode_id]
    except KeyError as exc:
        raise ValueError("instrumented rerun is outside canonical arm/episode scope") from exc
    _reject_symlink_chain(
        isolation_inputs.implementation_bundle_path,
        label="instrumented rerun bundle",
    )
    bundle_path = isolation_inputs.implementation_bundle_path.resolve(strict=True)
    if artifact_content_sha256_v0_9(bundle_path) != arm_binding.bundle_content_sha256:
        raise ValueError("instrumented rerun bundle differs from the frozen canonical arm")
    entrypoint_path = (bundle_path / arm_binding.entrypoint).resolve(strict=True)
    _content_bound_artifact_hash(
        entrypoint_path,
        expected=arm_binding.entrypoint_content_sha256,
        label="instrumented rerun entrypoint",
    )
    command_engine_path = Path(arm_binding.command_engine_path)
    _content_bound_artifact_hash(
        command_engine_path,
        expected=arm_binding.command_engine_content_sha256,
        label="instrumented rerun command engine",
    )
    _content_bound_artifact_hash(
        isolation_inputs.visible_input_path,
        expected=input_binding.input_artifact_sha256,
        label="instrumented rerun visible input",
    )
    context, context_content_hash, context_artifact_hash = _load_dual_context(
        isolation_inputs.canonical_context_path
    )
    expected_information_sets = canonical_dual_readout_information_sets_v1_0(
        isolation_inputs.visible_input_path,
        expected_visible_input_artifact_sha256=input_binding.input_artifact_sha256,
        expected_step_count=len(source.receipt.mechanism_steps),
    )
    expected_budget = canonical_offline_dual_readout_budget_v1_0(isolation_inputs.resource_limits)
    expected_context = DualReadoutCanonicalContextV10(
        external_verification_freeze_content_sha256=freeze_content_sha256,
        canonical_execution_content_sha256=canonical_execution_content_sha256,
        canonical_execution_id=canonical_execution.execution_id,
        canonical_task_receipt_content_sha256=source.receipt_content_sha256,
        canonical_isolation_receipt_content_sha256=(
            source.isolation.isolation_receipt_content_sha256
        ),
        source_task_content_sha256=source.receipt.task_content_sha256,
        sealed_opening_artifact_sha256=(canonical_execution.sealed_opening_binding.artifact_sha256),
        task_index=source.receipt.task_index,
        arm=source.receipt.arm,
        episode_id=source.receipt.episode_id,
        expected_step_count=len(source.receipt.mechanism_steps),
        expected_information_sets=expected_information_sets,
        expected_budget=expected_budget,
    )
    if context != expected_context:
        raise ValueError("dual-readout canonical context is stale or cross-task")
    _reject_symlink_chain(
        isolation_inputs.isolation_working_directory,
        label="instrumented rerun working directory",
    )
    work = isolation_inputs.isolation_working_directory.resolve(strict=True)
    _reject_symlink_chain(isolation_inputs.output_path, label="dual-readout output")
    output_path = isolation_inputs.output_path.resolve(strict=True)
    if output_path != work / DUAL_OUTPUT_RELATIVE_PATH:
        raise ValueError("instrumented rerun output path is not canonical")
    output, output_content_hash, output_artifact_hash = _load_dual_output(output_path)
    isolation_payload = dict(isolation_inputs.isolation_receipt_payload)
    isolation_content_hash = isolation_payload.get("content_sha256")
    if not isinstance(isolation_content_hash, str):
        raise ValueError("dual-readout isolation receipt lacks a content hash")
    arguments = _instrumented_rerun_arguments(
        entrypoint_path=entrypoint_path,
        visible_input_path=isolation_inputs.visible_input_path.resolve(strict=True),
        canonical_context_path=isolation_inputs.canonical_context_path.resolve(strict=True),
        output_path=output_path,
        source=source,
        freeze_content_sha256=freeze_content_sha256,
    )
    isolation = verify_isolation_receipt_v0_9(
        isolation_payload,
        trusted_executor=runner,
        command_engine_path=command_engine_path,
        arguments=arguments,
        code_bundle_path=bundle_path,
        input_artifact_paths={
            DUAL_CONTEXT_LABEL: isolation_inputs.canonical_context_path.resolve(strict=True),
            "visible_episode_input": isolation_inputs.visible_input_path.resolve(strict=True),
        },
        working_directory=work,
        expected_output_relative_paths={DUAL_OUTPUT_LABEL: DUAL_OUTPUT_RELATIVE_PATH},
        timeout_seconds=isolation_inputs.timeout_seconds,
        resource_limits=isolation_inputs.resource_limits,
    )
    if isolation.formal_isolation_verified is not True or isolation.status != "ISOLATION_PASSED":
        raise ValueError("instrumented dual-readout rerun lacks positive real isolation")
    if len(isolation.output_artifacts) != 1:
        raise ValueError("instrumented rerun must bind exactly one dual-readout output")
    output_binding = isolation.output_artifacts[0]
    if (
        output_binding.label != DUAL_OUTPUT_LABEL
        or output_binding.resolved_path != str(output_path)
        or output_binding.content_sha256 != output_artifact_hash
    ):
        raise ValueError("isolation receipt does not bind the exact dual-readout output")
    receipt = source.receipt
    expected_output = {
        "external_verification_freeze_content_sha256": freeze_content_sha256,
        "canonical_execution_content_sha256": canonical_execution_content_sha256,
        "canonical_execution_id": canonical_execution.execution_id,
        "canonical_task_receipt_content_sha256": source.receipt_content_sha256,
        "canonical_isolation_receipt_content_sha256": (
            source.isolation.isolation_receipt_content_sha256
        ),
        "task_index": receipt.task_index,
        "arm": receipt.arm,
        "episode_id": receipt.episode_id,
    }
    dumped = output.model_dump(mode="python")
    if any(dumped[name] != value for name, value in expected_output.items()):
        raise ValueError("isolated dual-readout output is stale, substituted, or cross-task")
    if len(output.steps) != len(receipt.mechanism_steps):
        raise ValueError("instrumented rerun has partial or extra step coverage")
    for step, source_step, information_set in zip(
        output.steps,
        receipt.mechanism_steps,
        expected_information_sets,
        strict=True,
    ):
        _verify_step_matches_source(
            step,
            source_step,
            arm=receipt.arm,
            expected_information_set=information_set,
            expected_budget=expected_budget,
        )
    return (
        output,
        output_content_hash,
        output_artifact_hash,
        context_content_hash,
        context_artifact_hash,
        isolation_content_hash,
        isolation,
    )


def prepare_dual_readout_task_receipt_v1_0(
    *,
    external_verification_freeze: ExternalVerificationFreezeV10,
    external_verification_freeze_content_sha256: str,
    canonical_execution: CanonicalPerEpisodeExecutionArtifactV09,
    canonical_execution_content_sha256: str,
    source: BoundEpisodeExecutionReceiptV09,
    isolation_inputs: DualReadoutIsolationVerificationInputsV10,
) -> DualReadoutTaskReceiptV10:
    freeze_hash = _freeze_content_hash(
        external_verification_freeze,
        external_verification_freeze_content_sha256,
    )
    runner = _canonical_runner(external_verification_freeze)
    _verify_source_receipt(source, runner=runner)
    if canonical_execution_content_sha256 != content_sha256(
        canonical_execution.model_dump(mode="json")
    ):
        raise ValueError("canonical execution content hash mismatch")
    receipt = source.receipt
    if (
        receipt.execution_id != canonical_execution.execution_id
        or source not in canonical_execution.task_receipts
    ):
        raise ValueError("source receipt is outside the canonical execution")
    (
        output,
        output_content_hash,
        output_artifact_hash,
        context_content_hash,
        context_artifact_hash,
        isolation_hash,
        _,
    ) = _verify_instrumented_rerun(
        external_verification_freeze=external_verification_freeze,
        freeze_content_sha256=freeze_hash,
        canonical_execution=canonical_execution,
        canonical_execution_content_sha256=canonical_execution_content_sha256,
        source=source,
        isolation_inputs=isolation_inputs,
    )
    return DualReadoutTaskReceiptV10(
        external_verification_freeze_content_sha256=freeze_hash,
        forbidden_seed_namespaces_sha256=(
            external_verification_freeze.body.forbidden_seed_namespaces_sha256
        ),
        canonical_execution_content_sha256=canonical_execution_content_sha256,
        canonical_execution_id=canonical_execution.execution_id,
        task_index=receipt.task_index,
        arm=receipt.arm,
        episode_id=receipt.episode_id,
        canonical_episode_receipt_content_sha256=source.receipt_content_sha256,
        canonical_isolation_receipt_content_sha256=(
            source.isolation.isolation_receipt_content_sha256
        ),
        canonical_candidate_output_artifact_sha256=(source.candidate_output.output_artifact_sha256),
        dual_readout_context_artifact_sha256=context_artifact_hash,
        dual_readout_context_content_sha256=context_content_hash,
        dual_readout_output_artifact_sha256=output_artifact_hash,
        dual_readout_output_content_sha256=output_content_hash,
        dual_readout_isolation_receipt_content_sha256=isolation_hash,
        instrumented_canonical_rerun_verified=True,
        deterministic_action_mechanism_equality_verified=True,
        steps=output.steps,
        runner=external_verification_freeze.body.runner_subkeys[0].runner,
    )


def finalize_dual_readout_task_receipt_v1_0(
    prepared: DualReadoutTaskReceiptV10,
    *,
    runner_attestation: Attestation | None,
) -> DualReadoutTaskReceiptV10:
    if prepared.runner_attestation is not None:
        raise ValueError("dual-readout task receipt was already signed")
    signed = prepared.model_copy(update={"runner_attestation": runner_attestation})
    _verifier(signed.runner).verify(
        TASK_RUNNER_DOMAIN,
        _task_payload(signed),
        signed.runner_attestation,
    )
    return signed


def verify_dual_readout_task_receipt_v1_0(
    record: DualReadoutTaskReceiptV10,
    *,
    external_verification_freeze: ExternalVerificationFreezeV10,
    external_verification_freeze_content_sha256: str,
    canonical_execution: CanonicalPerEpisodeExecutionArtifactV09,
    source: BoundEpisodeExecutionReceiptV09,
    isolation_inputs: DualReadoutIsolationVerificationInputsV10,
) -> DualReadoutTaskReceiptV10:
    canonical_hash = content_sha256(canonical_execution.model_dump(mode="json"))
    expected = prepare_dual_readout_task_receipt_v1_0(
        external_verification_freeze=external_verification_freeze,
        external_verification_freeze_content_sha256=(external_verification_freeze_content_sha256),
        canonical_execution=canonical_execution,
        canonical_execution_content_sha256=canonical_hash,
        source=source,
        isolation_inputs=isolation_inputs,
    )
    runner = _canonical_runner(external_verification_freeze)
    if not _matches(record.runner, runner):
        raise AttestationError("dual-readout receipt used an unregistered runner")
    if _task_payload(record) != _task_payload(expected):
        raise ValueError("dual-readout task receipt differs from isolated output evidence")
    runner.verify(TASK_RUNNER_DOMAIN, _task_payload(record), record.runner_attestation)
    return record


def _verified_upstream_bindings(
    *,
    external_verification_freeze: ExternalVerificationFreezeV10,
    sealed_opening: SealedGateBOpeningV09,
    opening_consumption_head: OpeningConsumptionLedgerHeadV09,
    canonical_execution: CanonicalPerEpisodeExecutionArtifactV09,
    trusted_reviewer: Ed25519AttestationVerifier,
    trusted_executor: Ed25519AttestationVerifier,
    trusted_custodian: Ed25519AttestationVerifier,
    trusted_enrollment_authority: Ed25519AttestationVerifier,
) -> FormalGateBUpstreamBindingsV10:
    parties = external_verification_freeze.body.party_keys
    supplied = (
        (parties.reviewer, trusted_reviewer),
        (parties.executor, trusted_executor),
        (parties.custodian, trusted_custodian),
        (parties.enrollment_authority, trusted_enrollment_authority),
    )
    if any(not _matches(binding, verifier) for binding, verifier in supplied):
        raise AttestationError("formal Gate-B verifier is outside the frozen trust registry")
    trusted_custodian.verify(
        OPENING_DOMAIN,
        attested_payload(sealed_opening, exclude=frozenset({"custodian_attestation"})),
        sealed_opening.custodian_attestation,
    )
    opening_hash = content_sha256(sealed_opening.model_dump(mode="json"))
    if (
        sealed_opening.gate_a_passed is not True
        or sealed_opening.forbidden_seed_namespaces_sha256
        != external_verification_freeze.body.forbidden_seed_namespaces_sha256
        or external_verification_freeze.body.frozen_at_utc >= sealed_opening.committed_at_utc
    ):
        raise ValueError("sealed opening is outside the frozen pre-commitment chain")
    if (
        opening_consumption_head.opening_content_sha256 != opening_hash
        or opening_consumption_head.opening_attempt_id != sealed_opening.opening_attempt_id
        or opening_consumption_head.immutable_manifest_sha256
        != sealed_opening.immutable_manifest_sha256
        or opening_consumption_head.producer_run_id != sealed_opening.producer_run_id
        or opening_consumption_head.ledger_identifier != sealed_opening.ledger_identifier
        or opening_consumption_head.ledger_sequence != sealed_opening.opening_ledger_sequence + 1
        or opening_consumption_head.consumed_at_utc <= sealed_opening.opened_at_utc
        or sealed_opening.opening_attempt_id not in opening_consumption_head.consumed_attempt_ids
    ):
        raise ValueError("opening consumption head is stale, forked, or cross-opening")
    prerequisites = canonical_execution.verified_prerequisites
    if (
        prerequisites.immutable_manifest_sha256 != sealed_opening.immutable_manifest_sha256
        or prerequisites.producer_run_id != sealed_opening.producer_run_id
        or prerequisites.opening_attempt_id != sealed_opening.opening_attempt_id
        or prerequisites.gate_a_report_content_sha256 != sealed_opening.gate_a_report_content_sha256
        or prerequisites.sealed_opening_content_sha256 != opening_hash
        or canonical_execution.sealed_opening_binding.artifact_sha256
        != prerequisites.sealed_opening_artifact_sha256
    ):
        raise ValueError("canonical execution differs from Gate A or sealed opening")
    return FormalGateBUpstreamBindingsV10(
        immutable_manifest_sha256=sealed_opening.immutable_manifest_sha256,
        producer_run_id=sealed_opening.producer_run_id,
        gate_a_report_content_sha256=sealed_opening.gate_a_report_content_sha256,
        sealed_opening_content_sha256=opening_hash,
        sealed_opening_artifact_sha256=(canonical_execution.sealed_opening_binding.artifact_sha256),
        opening_attempt_id=sealed_opening.opening_attempt_id,
        opening_consumption_head_sha256=opening_consumption_head.head_sha256,
        ledger_identifier=opening_consumption_head.ledger_identifier,
        opening_consumption_ledger_sequence=opening_consumption_head.ledger_sequence,
        opening_consumed_at_utc=opening_consumption_head.consumed_at_utc,
    )


class CanonicalDualReadoutExecutionV10(ContractModel):
    protocol: Literal["structure-two-canonical-dual-readout-execution@1.0"] = (
        "structure-two-canonical-dual-readout-execution@1.0"
    )
    external_verification_freeze_content_sha256: str = Field(pattern=_SHA256)
    external_verification_freeze_body_sha256: str = Field(pattern=_SHA256)
    external_verification_freeze_ledger_head_sha256: str = Field(pattern=_SHA256)
    forbidden_seed_namespaces_sha256: str = Field(pattern=_SHA256)
    frozen_canonical_verifier_config_bytes_sha256: str = Field(pattern=_SHA256)
    gate_b_protocol_id: Literal["structure-two-stratified-mechanism-dual-readout-gate-b@0.7"] = (
        DUAL_GATE_PROTOCOL_ID
    )
    gate_b_protocol_content_sha256: str = Field(pattern=_SHA256)
    upstream: FormalGateBUpstreamBindingsV10
    canonical_execution_content_sha256: str = Field(pattern=_SHA256)
    canonical_execution_id: str = Field(min_length=16)
    canonical_arms: tuple[str, ...]
    episode_ids: tuple[str, ...] = Field(min_length=1)
    task_receipts: tuple[DualReadoutTaskReceiptV10, ...] = Field(min_length=1)
    exact_arm_episode_coverage_verified: Literal[True]
    real_isolation_receipts_verified: Literal[True]
    canonical_runner: PublicKeyBindingV10
    ledger_identifier: str = Field(min_length=1)
    opening_consumption_ledger_sequence: StrictInt = Field(ge=0)
    canonical_execution_ledger_sequence: StrictInt = Field(ge=0)
    opening_consumed_at_utc: datetime
    canonical_execution_completed_at_utc: datetime
    executor: PublicKeyBindingV10
    executor_attestation: Attestation | None = None

    @model_validator(mode="after")
    def validate_execution(self) -> Self:
        if self.canonical_arms != EXPECTED_ARMS:
            raise ValueError("canonical dual-readout execution changed the ten-arm order")
        if len(set(self.episode_ids)) != len(self.episode_ids):
            raise ValueError("canonical dual-readout execution duplicated an episode")
        expected = tuple((arm, episode) for arm in EXPECTED_ARMS for episode in self.episode_ids)
        actual = tuple((row.arm, row.episode_id) for row in self.task_receipts)
        if actual != expected:
            raise ValueError("canonical dual-readout task coverage/order is incomplete")
        if tuple(row.task_index for row in self.task_receipts) != tuple(range(len(expected))):
            raise ValueError("canonical dual-readout task indexes are noncanonical")
        if self.gate_b_protocol_content_sha256 != content_sha256(
            canonical_frozen_protocol_payload_v0_7()
        ):
            raise ValueError("canonical dual-readout execution changed the v0.7 protocol")
        if self.canonical_execution_ledger_sequence != (
            self.opening_consumption_ledger_sequence + 1
        ):
            raise ValueError("canonical execution does not immediately append consumption")
        _utc(self.opening_consumed_at_utc, "opening consumption time")
        _utc(self.canonical_execution_completed_at_utc, "canonical completion time")
        if self.canonical_execution_completed_at_utc <= self.opening_consumed_at_utc:
            raise ValueError("canonical execution completion must follow opening consumption")
        return self

    @property
    def content_sha256(self) -> str:
        return content_sha256(self.model_dump(mode="json"))


def _execution_payload(record: CanonicalDualReadoutExecutionV10) -> dict[str, Any]:
    return attested_payload(record, exclude=frozenset({"executor_attestation"}))


def _verify_canonical_aggregate(
    canonical: CanonicalPerEpisodeExecutionArtifactV09,
    *,
    freeze: ExternalVerificationFreezeV10,
) -> None:
    executor = _verifier(freeze.body.party_keys.executor)
    if (
        canonical.executor_key_id != executor.key_id
        or canonical.executor_public_key_base64 != executor.public_key_base64
        or canonical.executor_public_key_sha256 != executor.public_key_sha256
    ):
        raise AttestationError("canonical aggregate used an unregistered executor")
    executor.verify(
        CANONICAL_AGGREGATE_DOMAIN,
        attested_payload(canonical),
        canonical.attestation,
    )


def prepare_canonical_dual_readout_execution_v1_0(
    *,
    external_verification_freeze: ExternalVerificationFreezeV10,
    external_verification_freeze_content_sha256: str,
    canonical_execution: CanonicalPerEpisodeExecutionArtifactV09,
    sealed_opening: SealedGateBOpeningV09,
    opening_consumption_head: OpeningConsumptionLedgerHeadV09,
    frozen_v0_7_config: Mapping[str, Any],
    task_receipts: Sequence[DualReadoutTaskReceiptV10],
    isolation_inputs_by_task: Mapping[tuple[str, str], DualReadoutIsolationVerificationInputsV10],
    canonical_execution_ledger_sequence: int,
    canonical_execution_completed_at_utc: datetime,
    trusted_reviewer: Ed25519AttestationVerifier,
    trusted_executor: Ed25519AttestationVerifier,
    trusted_custodian: Ed25519AttestationVerifier,
    trusted_enrollment_authority: Ed25519AttestationVerifier,
) -> CanonicalDualReadoutExecutionV10:
    freeze_hash = _freeze_content_hash(
        external_verification_freeze,
        external_verification_freeze_content_sha256,
    )
    _verify_canonical_aggregate(canonical_execution, freeze=external_verification_freeze)
    validate_frozen_protocol_payload_v0_7(frozen_v0_7_config)
    gate_b_protocol_hash = content_sha256(frozen_v0_7_config)
    canonical_hash = content_sha256(canonical_execution.model_dump(mode="json"))
    upstream = _verified_upstream_bindings(
        external_verification_freeze=external_verification_freeze,
        sealed_opening=sealed_opening,
        opening_consumption_head=opening_consumption_head,
        canonical_execution=canonical_execution,
        trusted_reviewer=trusted_reviewer,
        trusted_executor=trusted_executor,
        trusted_custodian=trusted_custodian,
        trusted_enrollment_authority=trusted_enrollment_authority,
    )
    if external_verification_freeze.body.frozen_at_utc >= upstream.opening_consumed_at_utc:
        raise ValueError("opening consumption must follow external verification freeze")
    rows = tuple(task_receipts)
    if len(rows) != len(canonical_execution.task_receipts):
        raise ValueError("dual-readout receipts lack exact canonical task coverage")
    expected_pairs = tuple(
        (source.receipt.arm, source.receipt.episode_id)
        for source in canonical_execution.task_receipts
    )
    if set(isolation_inputs_by_task) != set(expected_pairs) or len(isolation_inputs_by_task) != len(
        expected_pairs
    ):
        raise ValueError("isolation inputs lack exact canonical task coverage")
    for row, source in zip(rows, canonical_execution.task_receipts, strict=True):
        task_isolation = isolation_inputs_by_task[(source.receipt.arm, source.receipt.episode_id)]
        verify_dual_readout_task_receipt_v1_0(
            row,
            external_verification_freeze=external_verification_freeze,
            external_verification_freeze_content_sha256=freeze_hash,
            canonical_execution=canonical_execution,
            source=source,
            isolation_inputs=task_isolation,
        )
        isolation_raw = dict(task_isolation.isolation_receipt_payload)
        isolation_raw.pop("content_sha256", None)
        dual_isolation = IsolationExecutionReceiptV09.model_validate(isolation_raw)
        if dual_isolation.started_at_utc <= max(
            upstream.opening_consumed_at_utc,
            source.isolation.receipt.finished_at_utc,
        ):
            raise ValueError("instrumented rerun did not follow consumption and source execution")
        if dual_isolation.finished_at_utc > canonical_execution_completed_at_utc:
            raise ValueError("canonical completion predates an isolation receipt")
    return CanonicalDualReadoutExecutionV10(
        external_verification_freeze_content_sha256=freeze_hash,
        external_verification_freeze_body_sha256=(external_verification_freeze.freeze_body_sha256),
        external_verification_freeze_ledger_head_sha256=(
            external_verification_freeze.freeze_ledger_head_sha256
        ),
        forbidden_seed_namespaces_sha256=(
            external_verification_freeze.body.forbidden_seed_namespaces_sha256
        ),
        frozen_canonical_verifier_config_bytes_sha256=(
            external_verification_freeze.body.canonical_verifier.config_bytes_sha256
        ),
        gate_b_protocol_content_sha256=gate_b_protocol_hash,
        upstream=upstream,
        canonical_execution_content_sha256=canonical_hash,
        canonical_execution_id=canonical_execution.execution_id,
        canonical_arms=EXPECTED_ARMS,
        episode_ids=canonical_execution.episode_ids,
        task_receipts=rows,
        exact_arm_episode_coverage_verified=True,
        real_isolation_receipts_verified=True,
        canonical_runner=external_verification_freeze.body.runner_subkeys[0].runner,
        ledger_identifier=upstream.ledger_identifier,
        opening_consumption_ledger_sequence=(upstream.opening_consumption_ledger_sequence),
        canonical_execution_ledger_sequence=canonical_execution_ledger_sequence,
        opening_consumed_at_utc=upstream.opening_consumed_at_utc,
        canonical_execution_completed_at_utc=canonical_execution_completed_at_utc,
        executor=external_verification_freeze.body.party_keys.executor,
    )


def finalize_canonical_dual_readout_execution_v1_0(
    prepared: CanonicalDualReadoutExecutionV10,
    *,
    executor_attestation: Attestation | None,
) -> dict[str, Any]:
    if prepared.executor_attestation is not None:
        raise ValueError("canonical dual-readout execution was already signed")
    signed = prepared.model_copy(update={"executor_attestation": executor_attestation})
    _verifier(signed.executor).verify(
        EXECUTION_EXECUTOR_DOMAIN,
        _execution_payload(signed),
        signed.executor_attestation,
    )
    payload = signed.model_dump(mode="json")
    payload["content_sha256"] = content_sha256(payload)
    return payload


def verify_canonical_dual_readout_execution_v1_0(
    payload: Mapping[str, Any],
    *,
    external_verification_freeze: ExternalVerificationFreezeV10,
    external_verification_freeze_content_sha256: str,
    canonical_execution: CanonicalPerEpisodeExecutionArtifactV09,
    sealed_opening: SealedGateBOpeningV09,
    opening_consumption_head: OpeningConsumptionLedgerHeadV09,
    frozen_v0_7_config: Mapping[str, Any],
    isolation_inputs_by_task: Mapping[tuple[str, str], DualReadoutIsolationVerificationInputsV10],
    trusted_reviewer: Ed25519AttestationVerifier,
    trusted_executor: Ed25519AttestationVerifier,
    trusted_custodian: Ed25519AttestationVerifier,
    trusted_enrollment_authority: Ed25519AttestationVerifier,
) -> CanonicalDualReadoutExecutionV10:
    raw = dict(payload)
    stored = raw.pop("content_sha256", None)
    if not isinstance(stored, str) or content_sha256(raw) != stored:
        raise ValueError("canonical dual-readout aggregate content hash mismatch")
    execution = CanonicalDualReadoutExecutionV10.model_validate(raw)
    if raw != execution.model_dump(mode="json"):
        raise ValueError("canonical dual-readout aggregate encoding is noncanonical")
    expected = prepare_canonical_dual_readout_execution_v1_0(
        external_verification_freeze=external_verification_freeze,
        external_verification_freeze_content_sha256=(external_verification_freeze_content_sha256),
        canonical_execution=canonical_execution,
        sealed_opening=sealed_opening,
        opening_consumption_head=opening_consumption_head,
        frozen_v0_7_config=frozen_v0_7_config,
        task_receipts=execution.task_receipts,
        isolation_inputs_by_task=isolation_inputs_by_task,
        canonical_execution_ledger_sequence=(execution.canonical_execution_ledger_sequence),
        canonical_execution_completed_at_utc=(execution.canonical_execution_completed_at_utc),
        trusted_reviewer=trusted_reviewer,
        trusted_executor=trusted_executor,
        trusted_custodian=trusted_custodian,
        trusted_enrollment_authority=trusted_enrollment_authority,
    )
    if _execution_payload(execution) != _execution_payload(expected):
        raise ValueError("canonical dual-readout aggregate differs from raw verified evidence")
    if not _matches(execution.executor, trusted_executor):
        raise AttestationError("canonical dual-readout aggregate used an unregistered executor")
    trusted_executor.verify(
        EXECUTION_EXECUTOR_DOMAIN,
        _execution_payload(execution),
        execution.executor_attestation,
    )
    return execution


def _frozen_protocol() -> FrozenDualGateProtocol:
    return FrozenDualGateProtocol(
        content_sha256=content_sha256(canonical_frozen_protocol_payload_v0_7()),
        expected_arms=EXPECTED_ARMS,
        comparisons=tuple(
            DualGateComparison(
                comparison_id=comparison_id,
                domain=domain,
                left_arm="care_wm",
                right_arm=right_arm,
            )
            for comparison_id, (right_arm, domain) in CANONICAL_COMPARISONS.items()
        ),
        mechanism_requirements=tuple(
            MechanismRequirement(
                arm=arm,
                required_event_components=tuple(
                    (event, CANONICAL_COMPONENT_IDS[arm])
                    for event in CANONICAL_MECHANISM_EVENTS[arm]
                ),
            )
            for arm in EXPECTED_ARMS
        ),
    )


def _derive_and_score(
    execution: CanonicalDualReadoutExecutionV10,
) -> tuple[dict[str, Any], dict[str, str]]:
    traces: list[DualGateArmTrace] = []
    cursor = 0
    for arm in EXPECTED_ARMS:
        episodes: list[DualGateEpisode] = []
        for episode_id in execution.episode_ids:
            row = execution.task_receipts[cursor]
            if (row.arm, row.episode_id) != (arm, episode_id):
                raise ValueError("dual-readout execution order changed before scoring")
            episodes.append(row.as_v0_7())
            cursor += 1
        traces.append(DualGateArmTrace(arm=arm, episodes=tuple(episodes)))
    report = score_frozen_dual_gate_b_v0_7_diagnostic(tuple(traces), protocol=_frozen_protocol())
    trace_hashes = cast(dict[str, str], report["semantic_trace_sha256_by_arm"])
    return report, trace_hashes


class SealedDualGateBReceiptV10(ContractModel):
    protocol: Literal["structure-two-formal-sealed-dual-gate-b-receipt@1.0"] = (
        "structure-two-formal-sealed-dual-gate-b-receipt@1.0"
    )
    status: Literal["HISTORICAL_V0_7_RECEIPT_INVALIDATED"] = "HISTORICAL_V0_7_RECEIPT_INVALIDATED"
    gate_b_protocol_id: Literal["structure-two-stratified-mechanism-dual-readout-gate-b@0.7"] = (
        DUAL_GATE_PROTOCOL_ID
    )
    gate_b_protocol_content_sha256: str = Field(pattern=_SHA256)
    external_verification_freeze_content_sha256: str = Field(pattern=_SHA256)
    external_verification_freeze_body_sha256: str = Field(pattern=_SHA256)
    external_verification_freeze_ledger_head_sha256: str = Field(pattern=_SHA256)
    forbidden_seed_namespaces_sha256: str = Field(pattern=_SHA256)
    frozen_canonical_verifier_config_bytes_sha256: str = Field(pattern=_SHA256)
    canonical_runner_public_key_sha256: str = Field(pattern=_SHA256)
    immutable_manifest_sha256: str = Field(pattern=_SHA256)
    producer_run_id: str = Field(min_length=1)
    gate_a_report_content_sha256: str = Field(pattern=_SHA256)
    sealed_opening_content_sha256: str = Field(pattern=_SHA256)
    opening_consumption_head_sha256: str = Field(pattern=_SHA256)
    opening_attempt_id: str = Field(min_length=16, max_length=128)
    canonical_dual_readout_execution_content_sha256: str = Field(pattern=_SHA256)
    canonical_execution_content_sha256: str = Field(pattern=_SHA256)
    canonical_execution_id: str = Field(min_length=16)
    canonical_arms: tuple[str, ...]
    episode_ids: tuple[str, ...] = Field(min_length=1)
    task_receipt_content_sha256: tuple[str, ...] = Field(min_length=1)
    semantic_trace_sha256_by_arm: dict[str, str]
    diagnostic_report_content_sha256: str = Field(pattern=_SHA256)
    exact_arm_episode_coverage_verified: Literal[True]
    pre_action_pre_evaluator_truth_verified: Literal[True]
    real_isolation_receipts_verified: Literal[True]
    registered_runner_subkey_verified: Literal[True]
    belief_gate_passed: Literal[True]
    action_gate_passed: Literal[True]
    mechanism_gate_passed: Literal[True]
    protocol_invalidated: Literal[True] = True
    superseded_by_protocol_id: Literal["structure-two-comparator-typed-dual-gate-b@0.8"] = (
        "structure-two-comparator-typed-dual-gate-b@0.8"
    )
    formal_gate_b_passed: Literal[False] = False
    seven_operator_ablation_authorized: Literal[False] = False
    external_method_efficacy_comparison_allowed: Literal[False] = False
    ledger_identifier: str = Field(min_length=1)
    opening_consumption_ledger_sequence: StrictInt = Field(ge=0)
    canonical_execution_ledger_sequence: StrictInt = Field(ge=0)
    gate_b_ledger_sequence: StrictInt = Field(ge=0)
    canonical_execution_completed_at_utc: datetime
    gate_b_scored_at_utc: datetime
    signing_keys: FrozenPartyKeysV10
    reviewer_attestation: Attestation | None = None
    executor_attestation: Attestation | None = None
    custodian_attestation: Attestation | None = None
    authority_attestation: Attestation | None = None
    claim_boundary: str = CLAIM_BOUNDARY

    @model_validator(mode="after")
    def validate_formal_decision(self) -> Self:
        if self.canonical_arms != EXPECTED_ARMS:
            raise ValueError("formal Gate B changed the exact ten-arm order")
        expected_count = len(EXPECTED_ARMS) * len(self.episode_ids)
        if len(self.task_receipt_content_sha256) != expected_count:
            raise ValueError("formal Gate B lacks exact task-receipt coverage")
        if tuple(self.semantic_trace_sha256_by_arm) != EXPECTED_ARMS:
            raise ValueError("formal Gate B trace hashes lack exact arm coverage/order")
        if self.gate_b_protocol_content_sha256 != content_sha256(
            canonical_frozen_protocol_payload_v0_7()
        ):
            raise ValueError("formal Gate B used a noncanonical v0.7 protocol")
        if self.claim_boundary != CLAIM_BOUNDARY:
            raise ValueError("formal Gate B claim boundary was changed")
        if self.gate_b_ledger_sequence != self.canonical_execution_ledger_sequence + 1:
            raise ValueError("formal Gate B does not immediately follow canonical execution")
        _utc(self.canonical_execution_completed_at_utc, "canonical completion time")
        _utc(self.gate_b_scored_at_utc, "Gate-B score time")
        if self.gate_b_scored_at_utc <= self.canonical_execution_completed_at_utc:
            raise ValueError("formal Gate-B score does not follow canonical execution")
        return self


def _receipt_role_payload(record: SealedDualGateBReceiptV10) -> dict[str, Any]:
    return attested_payload(
        record,
        exclude=frozenset(
            {
                "reviewer_attestation",
                "executor_attestation",
                "custodian_attestation",
                "authority_attestation",
            }
        ),
    )


def _receipt_authority_payload(record: SealedDualGateBReceiptV10) -> dict[str, Any]:
    return attested_payload(record, exclude=frozenset({"authority_attestation"}))


def prepare_sealed_dual_gate_b_receipt_v1_0(
    *,
    execution: CanonicalDualReadoutExecutionV10,
    external_verification_freeze: ExternalVerificationFreezeV10,
    external_verification_freeze_content_sha256: str,
    gate_b_ledger_sequence: int,
    gate_b_scored_at_utc: datetime,
) -> SealedDualGateBReceiptV10:
    freeze_hash = _freeze_content_hash(
        external_verification_freeze,
        external_verification_freeze_content_sha256,
    )
    if execution.external_verification_freeze_content_sha256 != freeze_hash:
        raise ValueError("dual-readout execution used another external freeze")
    executor = _verifier(external_verification_freeze.body.party_keys.executor)
    if not _matches(execution.executor, executor):
        raise AttestationError("dual-readout aggregate used an unregistered executor")
    executor.verify(
        EXECUTION_EXECUTOR_DOMAIN,
        _execution_payload(execution),
        execution.executor_attestation,
    )
    runner = _canonical_runner(external_verification_freeze)
    if not _matches(execution.canonical_runner, runner):
        raise AttestationError("dual-readout aggregate used an unregistered runner")
    for row in execution.task_receipts:
        if not _matches(row.runner, runner):
            raise AttestationError("dual-readout task used an unregistered runner")
        runner.verify(TASK_RUNNER_DOMAIN, _task_payload(row), row.runner_attestation)
    diagnostic, trace_hashes = _derive_and_score(execution)
    if diagnostic["diagnostic_dual_conditions_passed"] is not True:
        raise ValueError("frozen v0.7 diagnostic conditions did not all pass")
    return SealedDualGateBReceiptV10(
        gate_b_protocol_content_sha256=execution.gate_b_protocol_content_sha256,
        external_verification_freeze_content_sha256=freeze_hash,
        external_verification_freeze_body_sha256=(
            execution.external_verification_freeze_body_sha256
        ),
        external_verification_freeze_ledger_head_sha256=(
            execution.external_verification_freeze_ledger_head_sha256
        ),
        forbidden_seed_namespaces_sha256=execution.forbidden_seed_namespaces_sha256,
        frozen_canonical_verifier_config_bytes_sha256=(
            execution.frozen_canonical_verifier_config_bytes_sha256
        ),
        canonical_runner_public_key_sha256=runner.public_key_sha256,
        immutable_manifest_sha256=execution.upstream.immutable_manifest_sha256,
        producer_run_id=execution.upstream.producer_run_id,
        gate_a_report_content_sha256=(execution.upstream.gate_a_report_content_sha256),
        sealed_opening_content_sha256=(execution.upstream.sealed_opening_content_sha256),
        opening_consumption_head_sha256=(execution.upstream.opening_consumption_head_sha256),
        opening_attempt_id=execution.upstream.opening_attempt_id,
        canonical_dual_readout_execution_content_sha256=execution.content_sha256,
        canonical_execution_content_sha256=execution.canonical_execution_content_sha256,
        canonical_execution_id=execution.canonical_execution_id,
        canonical_arms=EXPECTED_ARMS,
        episode_ids=execution.episode_ids,
        task_receipt_content_sha256=tuple(row.content_sha256 for row in execution.task_receipts),
        semantic_trace_sha256_by_arm=trace_hashes,
        diagnostic_report_content_sha256=cast(str, diagnostic["content_sha256"]),
        exact_arm_episode_coverage_verified=True,
        pre_action_pre_evaluator_truth_verified=True,
        real_isolation_receipts_verified=True,
        registered_runner_subkey_verified=True,
        belief_gate_passed=True,
        action_gate_passed=True,
        mechanism_gate_passed=True,
        formal_gate_b_passed=False,
        ledger_identifier=execution.ledger_identifier,
        opening_consumption_ledger_sequence=(execution.opening_consumption_ledger_sequence),
        canonical_execution_ledger_sequence=execution.canonical_execution_ledger_sequence,
        gate_b_ledger_sequence=gate_b_ledger_sequence,
        canonical_execution_completed_at_utc=(execution.canonical_execution_completed_at_utc),
        gate_b_scored_at_utc=gate_b_scored_at_utc,
        signing_keys=external_verification_freeze.body.party_keys,
    )


def sealed_dual_gate_b_role_signing_requests_v1_0(
    prepared: SealedDualGateBReceiptV10,
) -> dict[str, tuple[str, dict[str, Any]]]:
    if any(
        value is not None
        for value in (
            prepared.reviewer_attestation,
            prepared.executor_attestation,
            prepared.custodian_attestation,
            prepared.authority_attestation,
        )
    ):
        raise ValueError("formal Gate-B role signing requires a wholly unsigned receipt")
    payload = _receipt_role_payload(prepared)
    return {
        "reviewer": (REVIEWER_DOMAIN, payload),
        "executor": (EXECUTOR_DOMAIN, payload),
        "custodian": (CUSTODIAN_DOMAIN, payload),
    }


def sealed_dual_gate_b_authority_signing_request_v1_0(
    prepared: SealedDualGateBReceiptV10,
    *,
    reviewer_attestation: Attestation,
    executor_attestation: Attestation,
    custodian_attestation: Attestation,
) -> tuple[str, dict[str, Any]]:
    role_payload = _receipt_role_payload(prepared)
    _verifier(prepared.signing_keys.reviewer).verify(
        REVIEWER_DOMAIN, role_payload, reviewer_attestation
    )
    _verifier(prepared.signing_keys.executor).verify(
        EXECUTOR_DOMAIN, role_payload, executor_attestation
    )
    _verifier(prepared.signing_keys.custodian).verify(
        CUSTODIAN_DOMAIN, role_payload, custodian_attestation
    )
    role_signed = prepared.model_copy(
        update={
            "reviewer_attestation": reviewer_attestation,
            "executor_attestation": executor_attestation,
            "custodian_attestation": custodian_attestation,
        }
    )
    return AUTHORITY_DOMAIN, _receipt_authority_payload(role_signed)


def finalize_sealed_dual_gate_b_receipt_v1_0(
    prepared: SealedDualGateBReceiptV10,
    *,
    reviewer_attestation: Attestation,
    executor_attestation: Attestation,
    custodian_attestation: Attestation,
    authority_attestation: Attestation,
) -> dict[str, Any]:
    if any(
        value is not None
        for value in (
            prepared.reviewer_attestation,
            prepared.executor_attestation,
            prepared.custodian_attestation,
            prepared.authority_attestation,
        )
    ):
        raise ValueError("formal Gate-B receipt was already signed")
    role_payload = _receipt_role_payload(prepared)
    _verifier(prepared.signing_keys.reviewer).verify(
        REVIEWER_DOMAIN, role_payload, reviewer_attestation
    )
    _verifier(prepared.signing_keys.executor).verify(
        EXECUTOR_DOMAIN, role_payload, executor_attestation
    )
    _verifier(prepared.signing_keys.custodian).verify(
        CUSTODIAN_DOMAIN, role_payload, custodian_attestation
    )
    role_signed = prepared.model_copy(
        update={
            "reviewer_attestation": reviewer_attestation,
            "executor_attestation": executor_attestation,
            "custodian_attestation": custodian_attestation,
        }
    )
    _verifier(prepared.signing_keys.enrollment_authority).verify(
        AUTHORITY_DOMAIN,
        _receipt_authority_payload(role_signed),
        authority_attestation,
    )
    signed = role_signed.model_copy(update={"authority_attestation": authority_attestation})
    payload = signed.model_dump(mode="json")
    payload["content_sha256"] = content_sha256(payload)
    return payload


def verify_sealed_dual_gate_b_receipt_v1_0(
    payload: Mapping[str, Any],
    *,
    canonical_dual_readout_execution_payload: Mapping[str, Any],
    external_verification_freeze: ExternalVerificationFreezeV10,
    external_verification_freeze_content_sha256: str,
    canonical_execution: CanonicalPerEpisodeExecutionArtifactV09,
    sealed_opening: SealedGateBOpeningV09,
    opening_consumption_head: OpeningConsumptionLedgerHeadV09,
    frozen_v0_7_config: Mapping[str, Any],
    isolation_inputs_by_task: Mapping[tuple[str, str], DualReadoutIsolationVerificationInputsV10],
    trusted_reviewer: Ed25519AttestationVerifier,
    trusted_executor: Ed25519AttestationVerifier,
    trusted_custodian: Ed25519AttestationVerifier,
    trusted_enrollment_authority: Ed25519AttestationVerifier,
    verification_time_utc: datetime,
) -> SealedDualGateBReceiptV10:
    _utc(verification_time_utc, "trusted verification time")
    raw = dict(payload)
    stored = raw.pop("content_sha256", None)
    if not isinstance(stored, str) or content_sha256(raw) != stored:
        raise ValueError("formal sealed dual Gate-B receipt content hash mismatch")
    record = SealedDualGateBReceiptV10.model_validate(raw)
    if raw != record.model_dump(mode="json"):
        raise ValueError("formal sealed dual Gate-B receipt encoding is noncanonical")
    execution = verify_canonical_dual_readout_execution_v1_0(
        canonical_dual_readout_execution_payload,
        external_verification_freeze=external_verification_freeze,
        external_verification_freeze_content_sha256=(external_verification_freeze_content_sha256),
        canonical_execution=canonical_execution,
        sealed_opening=sealed_opening,
        opening_consumption_head=opening_consumption_head,
        frozen_v0_7_config=frozen_v0_7_config,
        isolation_inputs_by_task=isolation_inputs_by_task,
        trusted_reviewer=trusted_reviewer,
        trusted_executor=trusted_executor,
        trusted_custodian=trusted_custodian,
        trusted_enrollment_authority=trusted_enrollment_authority,
    )
    expected = prepare_sealed_dual_gate_b_receipt_v1_0(
        execution=execution,
        external_verification_freeze=external_verification_freeze,
        external_verification_freeze_content_sha256=(external_verification_freeze_content_sha256),
        gate_b_ledger_sequence=record.gate_b_ledger_sequence,
        gate_b_scored_at_utc=record.gate_b_scored_at_utc,
    )
    excluded = {
        "reviewer_attestation",
        "executor_attestation",
        "custodian_attestation",
        "authority_attestation",
    }
    if record.model_dump(mode="python", exclude=excluded) != expected.model_dump(
        mode="python", exclude=excluded
    ):
        raise ValueError("formal Gate-B receipt differs from recomputed full-chain evidence")
    if record.signing_keys != external_verification_freeze.body.party_keys:
        raise AttestationError("formal Gate-B signing keys differ from external freeze")
    if not _matches(record.signing_keys.enrollment_authority, trusted_enrollment_authority):
        raise AttestationError("formal Gate-B receipt used an untrusted authority")
    if record.gate_b_scored_at_utc > verification_time_utc:
        raise ValueError("formal sealed dual Gate-B receipt is in the verifier's future")
    role_payload = _receipt_role_payload(record)
    trusted_reviewer.verify(REVIEWER_DOMAIN, role_payload, record.reviewer_attestation)
    trusted_executor.verify(EXECUTOR_DOMAIN, role_payload, record.executor_attestation)
    trusted_custodian.verify(CUSTODIAN_DOMAIN, role_payload, record.custodian_attestation)
    trusted_enrollment_authority.verify(
        AUTHORITY_DOMAIN,
        _receipt_authority_payload(record),
        record.authority_attestation,
    )
    return record


__all__ = [
    "AUTHORITY_DOMAIN",
    "CANONICAL_OBSERVATION_POLICY_SHA256",
    "CANONICAL_OBSERVATION_POLICY_V10",
    "CANONICAL_OFFLINE_BUDGET_POLICY_SHA256",
    "CANONICAL_OFFLINE_BUDGET_POLICY_V10",
    "CLAIM_BOUNDARY",
    "CUSTODIAN_DOMAIN",
    "EXECUTION_EXECUTOR_DOMAIN",
    "EXECUTION_PROTOCOL_ID",
    "EXECUTOR_DOMAIN",
    "PROTOCOL_ID",
    "REVIEWER_DOMAIN",
    "TASK_PROTOCOL_ID",
    "TASK_RUNNER_DOMAIN",
    "BudgetEvidenceV10",
    "CanonicalDualReadoutExecutionV10",
    "DenseDistributionV10",
    "DualReadoutCanonicalContextV10",
    "DualReadoutIsolationVerificationInputsV10",
    "DualReadoutStepEvidenceV10",
    "DualReadoutTaskOutputV10",
    "DualReadoutTaskReceiptV10",
    "FormalGateBUpstreamBindingsV10",
    "InformationSetEvidenceV10",
    "MechanismEventEvidenceV10",
    "SealedDualGateBReceiptV10",
    "canonical_dual_readout_information_sets_v1_0",
    "canonical_offline_dual_readout_budget_v1_0",
    "finalize_canonical_dual_readout_execution_v1_0",
    "finalize_dual_readout_task_receipt_v1_0",
    "finalize_sealed_dual_gate_b_receipt_v1_0",
    "prepare_canonical_dual_readout_execution_v1_0",
    "prepare_dual_readout_task_receipt_v1_0",
    "prepare_sealed_dual_gate_b_receipt_v1_0",
    "sealed_dual_gate_b_authority_signing_request_v1_0",
    "sealed_dual_gate_b_role_signing_requests_v1_0",
    "verify_canonical_dual_readout_execution_v1_0",
    "verify_dual_readout_task_receipt_v1_0",
    "verify_sealed_dual_gate_b_receipt_v1_0",
]
