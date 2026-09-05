"""Raw formal-execution chain for comparator-typed dual Gate B v0.8.

The frozen v0.8 comparator scorer is intentionally diagnostic: its Python
objects can be constructed by a caller.  This module defines the evidence
chain that a future *formal* Gate-B execution must supply before those
readouts can become eligible evidence:

* a canonical-execution verifier signs the exact arm x episode source trace;
* an instrumented runtime emits canonical JSON belief/action readouts whose
  selected runtime command is checked against that source trace;
* an independently enrolled causal broker signs the readout -> action ->
  evaluator-truth -> utility order for every step;
* two independently enrolled custodians sign a parent-linked artifact chain;
* an independent reviewer signs the recomputed diagnostic report; and
* a verifier-owned persistent replay registry atomically consumes every nonce.

No boolean supplied by the candidate is treated as evidence.  A signature is
also insufficient unless its public key is present in the policy-bound trust
manifest and every role has a distinct authority and key.  The checked-in
policy is deliberately ``NOT_ENROLLED`` and ``REGISTERED_NOT_EXECUTED``;
therefore :func:`current_gate_b_v0_8_formal_status` can only fail closed.  This
module never authorizes or runs the seven-operator ablation.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from itertools import pairwise
from pathlib import Path
from typing import Annotated, Any, Final, Literal, cast
from uuid import UUID

from pydantic import Field, model_validator

from cpswm.contracts.base import ContractModel
from cpswm.system.attestation import (
    Attestation,
    AttestationError,
    Ed25519AttestationSigner,
    Ed25519AttestationVerifier,
    attested_payload,
)
from cpswm.system.evaluation_operations.structure_two_comparator_typed_dual_gate_b_v0_8 import (
    EXPECTED_ARMS,
    ComparatorEvidence,
    DecisionReadout,
    EpisodePublicOntology,
    FrozenComparatorTypedDualGateB,
    RuntimeActionProjection,
    canonical_comparator_specs_v0_8,
    canonical_protocol_payload_v0_8,
    score_frozen_gate_b_v0_8_diagnostic,
)
from cpswm.system.evaluation_operations.structure_two_comparator_typed_dual_gate_b_v0_8 import (
    PROTOCOL_ID as GATE_B_PROTOCOL_ID,
)
from cpswm.system.reproducibility import canonical_json, content_sha256

PROTOCOL_ID: Final = "structure-two-gate-b-v0.8-raw-formal-execution-chain@1.0"
POLICY_PROTOCOL_ID: Final = "structure-two-gate-b-v0.8-raw-formal-chain-policy@1.0"
TRUST_MANIFEST_PROTOCOL_ID: Final = "structure-two-gate-b-v0.8-trust-manifest@1.0"
CANONICAL_VERIFICATION_PROTOCOL_ID: Final = (
    "structure-two-gate-b-v0.8-canonical-execution-verification@1.0"
)
RUN_MANIFEST_PROTOCOL_ID: Final = "structure-two-gate-b-v0.8-run-manifest@1.0"
RAW_OUTPUT_PROTOCOL_ID: Final = "structure-two-gate-b-v0.8-runtime-readout-output@1.0"
RUNTIME_RECEIPT_PROTOCOL_ID: Final = "structure-two-gate-b-v0.8-runtime-readout-receipt@1.0"
BROKER_RECEIPT_PROTOCOL_ID: Final = "structure-two-gate-b-v0.8-causal-broker-step@1.0"
CUSTODY_RECEIPT_PROTOCOL_ID: Final = "structure-two-gate-b-v0.8-custody-hop@1.0"
REVIEW_RECEIPT_PROTOCOL_ID: Final = "structure-two-gate-b-v0.8-independent-review@1.0"
REPLAY_REGISTRY_PROTOCOL_ID: Final = "structure-two-gate-b-v0.8-persistent-replay-registry@1.0"

TRUST_MANIFEST_DOMAIN: Final = "cpswm.structure_two.gate_b_v0_8.trust_manifest.v1"
CANONICAL_VERIFICATION_DOMAIN: Final = (
    "cpswm.structure_two.gate_b_v0_8.canonical_execution_verification.v1"
)
RUN_MANIFEST_DOMAIN: Final = "cpswm.structure_two.gate_b_v0_8.run_manifest.v1"
RUNTIME_RECEIPT_DOMAIN: Final = "cpswm.structure_two.gate_b_v0_8.runtime_readout.v1"
BROKER_RECEIPT_DOMAIN: Final = "cpswm.structure_two.gate_b_v0_8.causal_broker.v1"
CUSTODY_RECEIPT_DOMAIN: Final = "cpswm.structure_two.gate_b_v0_8.custody.v1"
REVIEW_RECEIPT_DOMAIN: Final = "cpswm.structure_two.gate_b_v0_8.review.v1"

CANONICAL_EXECUTOR_PROTOCOL_ID: Final = "structure-two-canonical-per-episode-executor@0.9"
DEFAULT_POLICY_PATH: Final = (
    Path(__file__).resolve().parents[4]
    / "configs/project_two_experiments/structure_two_gate_b_v0_8_raw_formal_chain_v1_0.json"
)
MAX_RECEIPT_LIFETIME_SECONDS: Final = 86_400
SHA256_RE: Final = r"^[0-9a-f]{64}$"
Sha256 = Annotated[str, Field(pattern=SHA256_RE)]


class EnrollmentStatus(StrEnum):
    NOT_ENROLLED = "NOT_ENROLLED"
    ENROLLED = "ENROLLED"


class ExecutionStatus(StrEnum):
    REGISTERED_NOT_EXECUTED = "REGISTERED_NOT_EXECUTED"
    EXECUTED = "EXECUTED"


class FormalRole(StrEnum):
    CANONICAL_EXECUTION_VERIFIER = "canonical_execution_verifier"
    RUNTIME_READOUT_EXECUTOR = "runtime_readout_executor"
    CAUSAL_BROKER = "causal_broker"
    PREREGISTRATION_CUSTODIAN = "preregistration_custodian"
    INGEST_CUSTODIAN = "ingest_custodian"
    ARCHIVE_CUSTODIAN = "archive_custodian"
    INDEPENDENT_REVIEWER = "independent_reviewer"


ROLE_ORDER: Final = tuple(FormalRole)


class CausalEventKind(StrEnum):
    PREDECISION_READOUT_CAPTURED = "predecision_readout_captured"
    RUNTIME_ACTION_COMMITTED = "runtime_action_committed"
    EVALUATOR_TRUTH_DISCLOSED = "evaluator_truth_disclosed"
    CONSEQUENCE_UTILITY_OBSERVED = "consequence_utility_observed"


CAUSAL_EVENT_ORDER: Final = tuple(CausalEventKind)


class CustodyRole(StrEnum):
    INGEST = "ingest_custodian"
    ARCHIVE = "archive_custodian"


def _require_utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    normalized = value.astimezone(UTC)
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must use UTC")
    return normalized


def _validate_interval(issued_at: datetime, expires_at: datetime, *, label: str) -> None:
    issued = _require_utc(issued_at, f"{label} issue time")
    expires = _require_utc(expires_at, f"{label} expiry time")
    if not issued < expires:
        raise ValueError(f"{label} expiry must be after issue time")
    if (expires - issued).total_seconds() > MAX_RECEIPT_LIFETIME_SECONDS:
        raise ValueError(f"{label} lifetime exceeds the frozen freshness window")


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    output: dict[str, object] = {}
    for key, value in pairs:
        if key in output:
            raise ValueError(f"duplicate JSON key in Gate B v0.8 raw artifact: {key}")
        output[key] = value
    return output


class RawFormalChainPolicyV08(ContractModel):
    protocol: Literal["structure-two-gate-b-v0.8-raw-formal-chain-policy@1.0"]
    gate_b_protocol: Literal["structure-two-comparator-typed-dual-gate-b@0.8"]
    gate_b_protocol_status: Literal["FROZEN_NOT_EXECUTED"]
    gate_b_protocol_content_sha256: Sha256
    raw_execution_protocol: Literal["structure-two-gate-b-v0.8-raw-formal-execution-chain@1.0"]
    canonical_executor_protocol: Literal["structure-two-canonical-per-episode-executor@0.9"]
    exact_arms: tuple[str, ...]
    required_roles: tuple[FormalRole, ...]
    trust_anchor_status: EnrollmentStatus
    trust_manifest_content_sha256: Sha256 | None
    trust_manifest_root_key_id: str | None
    trust_manifest_root_public_key_base64: str | None
    trust_manifest_root_public_key_sha256: Sha256 | None
    replay_registry_status: EnrollmentStatus
    replay_registry_id: UUID | None
    replay_registry_enrollment_sha256: Sha256 | None
    replay_registry_storage_identity_sha256: Sha256 | None
    execution_status: ExecutionStatus
    formal_execution_content_sha256: Sha256 | None
    current_formal_gate_b_passed: Literal[False]
    seven_operator_ablation_authorized: Literal[False]
    claim_boundary: Literal[
        "Registration defines evidence requirements only. Until independent trust anchors, "
        "persistent replay custody, and a complete fresh execution are enrolled, Gate B and "
        "trusted seven-operator ablation authorization remain false."
    ]

    @model_validator(mode="after")
    def _freeze_scope(self) -> RawFormalChainPolicyV08:
        if self.gate_b_protocol_content_sha256 != content_sha256(canonical_protocol_payload_v0_8()):
            raise ValueError("raw-chain policy changed the frozen Gate B v0.8 protocol")
        if self.exact_arms != EXPECTED_ARMS or self.required_roles != ROLE_ORDER:
            raise ValueError("raw-chain policy changed exact arm or formal-role coverage")
        trust_values = (
            self.trust_manifest_content_sha256,
            self.trust_manifest_root_key_id,
            self.trust_manifest_root_public_key_base64,
            self.trust_manifest_root_public_key_sha256,
        )
        if self.trust_anchor_status is EnrollmentStatus.NOT_ENROLLED:
            if any(value is not None for value in trust_values):
                raise ValueError("non-enrolled trust policy must not carry anchor material")
        elif any(value is None for value in trust_values):
            raise ValueError("enrolled trust policy requires a complete root binding")
        replay_values = (
            self.replay_registry_id,
            self.replay_registry_enrollment_sha256,
            self.replay_registry_storage_identity_sha256,
        )
        if self.replay_registry_status is EnrollmentStatus.NOT_ENROLLED:
            if any(value is not None for value in replay_values):
                raise ValueError("non-enrolled replay policy must not carry registry material")
        elif any(value is None for value in replay_values):
            raise ValueError("enrolled replay policy requires registry id and enrollment hash")
        if self.execution_status is ExecutionStatus.REGISTERED_NOT_EXECUTED:
            if self.formal_execution_content_sha256 is not None:
                raise ValueError("an unexecuted policy cannot name a formal execution")
        elif self.formal_execution_content_sha256 is None:
            raise ValueError("an executed policy must bind the formal execution content")
        return self

    @property
    def content_sha256(self) -> str:
        return content_sha256(self)


def load_raw_formal_chain_policy_v0_8(
    path: Path = DEFAULT_POLICY_PATH,
) -> RawFormalChainPolicyV08:
    payload = json.loads(
        path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_json_keys
    )
    if not isinstance(payload, dict):
        raise ValueError("Gate B v0.8 raw-chain policy must be an object")
    return RawFormalChainPolicyV08.model_validate(payload)


class TrustAnchorV08(ContractModel):
    role: FormalRole
    authority_id: str = Field(min_length=1)
    key_id: str = Field(min_length=1)
    public_key_base64: str = Field(min_length=1)
    public_key_sha256: Sha256
    enrolled_at_utc: datetime

    @model_validator(mode="after")
    def _validate_key(self) -> TrustAnchorV08:
        _require_utc(self.enrolled_at_utc, "trust-anchor enrollment time")
        verifier = Ed25519AttestationVerifier.from_public_key_base64(
            key_id=self.key_id,
            public_key_base64=self.public_key_base64,
        )
        if verifier.public_key_sha256 != self.public_key_sha256:
            raise ValueError("trust-anchor public-key hash mismatch")
        return self

    def verifier(self) -> Ed25519AttestationVerifier:
        return Ed25519AttestationVerifier.from_public_key_base64(
            key_id=self.key_id,
            public_key_base64=self.public_key_base64,
        )


class GateBV08TrustManifest(ContractModel):
    protocol: Literal["structure-two-gate-b-v0.8-trust-manifest@1.0"]
    manifest_id: UUID
    issued_at_utc: datetime
    expires_at_utc: datetime
    gate_b_protocol_content_sha256: Sha256
    replay_registry_id: UUID
    replay_registry_enrollment_sha256: Sha256
    replay_registry_storage_identity_sha256: Sha256
    anchors: tuple[TrustAnchorV08, ...]
    root_key_id: str = Field(min_length=1)
    root_public_key_base64: str = Field(min_length=1)
    root_public_key_sha256: Sha256
    attestation: Attestation | None = None

    @model_validator(mode="after")
    def _independent_roles(self) -> GateBV08TrustManifest:
        _validate_interval(self.issued_at_utc, self.expires_at_utc, label="trust manifest")
        if self.gate_b_protocol_content_sha256 != content_sha256(canonical_protocol_payload_v0_8()):
            raise ValueError("trust manifest changed the frozen Gate B v0.8 protocol")
        if tuple(anchor.role for anchor in self.anchors) != ROLE_ORDER:
            raise ValueError("trust manifest lacks exact ordered role coverage")
        for field_name, values in (
            ("authority", tuple(anchor.authority_id for anchor in self.anchors)),
            ("key id", tuple(anchor.key_id for anchor in self.anchors)),
            ("public key", tuple(anchor.public_key_sha256 for anchor in self.anchors)),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"formal roles must use independent {field_name}s")
        if self.root_key_id in {anchor.key_id for anchor in self.anchors}:
            raise ValueError("trust-manifest root must be independent from formal roles")
        if self.root_public_key_sha256 in {anchor.public_key_sha256 for anchor in self.anchors}:
            raise ValueError("trust-manifest root key must be independent from formal roles")
        root = Ed25519AttestationVerifier.from_public_key_base64(
            key_id=self.root_key_id,
            public_key_base64=self.root_public_key_base64,
        )
        if root.public_key_sha256 != self.root_public_key_sha256:
            raise ValueError("trust-manifest root public-key hash mismatch")
        if any(anchor.enrolled_at_utc > self.issued_at_utc for anchor in self.anchors):
            raise ValueError("formal role anchor was enrolled after manifest issue")
        return self

    @property
    def content_sha256(self) -> str:
        return content_sha256(self)

    def anchor(self, role: FormalRole) -> TrustAnchorV08:
        return next(anchor for anchor in self.anchors if anchor.role is role)


def sign_trust_manifest_v0_8(
    manifest: GateBV08TrustManifest,
    *,
    root_signer: Ed25519AttestationSigner,
) -> GateBV08TrustManifest:
    if manifest.attestation is not None:
        raise ValueError("trust manifest is already signed")
    root = root_signer.verifier()
    if (
        manifest.root_key_id,
        manifest.root_public_key_base64,
        manifest.root_public_key_sha256,
    ) != (root.key_id, root.public_key_base64, root.public_key_sha256):
        raise AttestationError("trust-manifest root metadata differs from signer")
    return manifest.model_copy(
        update={
            "attestation": root_signer.sign(
                TRUST_MANIFEST_DOMAIN,
                attested_payload(manifest),
            )
        }
    )


def verify_policy_bound_trust_manifest_v0_8(
    manifest: GateBV08TrustManifest,
    *,
    policy: RawFormalChainPolicyV08,
    now_utc: datetime,
) -> None:
    if policy.trust_anchor_status is not EnrollmentStatus.ENROLLED:
        raise AttestationError("Gate B v0.8 trust anchors are not enrolled")
    if manifest.content_sha256 != policy.trust_manifest_content_sha256:
        raise AttestationError("trust manifest is outside the policy commitment")
    if (
        manifest.root_key_id,
        manifest.root_public_key_base64,
        manifest.root_public_key_sha256,
    ) != (
        policy.trust_manifest_root_key_id,
        policy.trust_manifest_root_public_key_base64,
        policy.trust_manifest_root_public_key_sha256,
    ):
        raise AttestationError("trust-manifest root differs from policy enrollment")
    now = _require_utc(now_utc, "verification time")
    if not manifest.issued_at_utc <= now <= manifest.expires_at_utc:
        raise ValueError("trust manifest is stale or not yet valid")
    root = Ed25519AttestationVerifier.from_public_key_base64(
        key_id=manifest.root_key_id,
        public_key_base64=manifest.root_public_key_base64,
    )
    root.verify(TRUST_MANIFEST_DOMAIN, attested_payload(manifest), manifest.attestation)
    if (
        manifest.replay_registry_id != policy.replay_registry_id
        or manifest.replay_registry_enrollment_sha256 != policy.replay_registry_enrollment_sha256
        or manifest.replay_registry_storage_identity_sha256
        != policy.replay_registry_storage_identity_sha256
    ):
        raise ValueError("trust manifest changed replay-registry enrollment")


class SignedRecordBase(ContractModel):
    issued_at_utc: datetime
    expires_at_utc: datetime
    nonce: UUID
    signer_role: FormalRole
    signer_authority_id: str = Field(min_length=1)
    signer_key_id: str = Field(min_length=1)
    signer_public_key_sha256: Sha256
    attestation: Attestation | None = None

    @model_validator(mode="after")
    def _fresh_interval(self) -> SignedRecordBase:
        _validate_interval(self.issued_at_utc, self.expires_at_utc, label="signed record")
        return self


class CanonicalStepBindingV08(ContractModel):
    step_index: int = Field(ge=0)
    runtime_action_id: str = Field(min_length=1)
    input_state_sha256: Sha256
    output_state_sha256: Sha256


class CanonicalTaskBindingV08(ContractModel):
    task_index: int = Field(ge=0)
    arm: str = Field(min_length=1)
    episode_id: str = Field(min_length=1)
    canonical_task_receipt_content_sha256: Sha256
    implementation_bundle_sha256: Sha256
    runtime_engine_sha256: Sha256
    steps: tuple[CanonicalStepBindingV08, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _step_order(self) -> CanonicalTaskBindingV08:
        if tuple(step.step_index for step in self.steps) != tuple(range(len(self.steps))):
            raise ValueError("canonical source steps must be contiguous and zero based")
        if any(
            right.input_state_sha256 != left.output_state_sha256
            for left, right in zip(self.steps, self.steps[1:], strict=False)
        ):
            raise ValueError("canonical source state chain is discontinuous")
        return self


class CanonicalTaskPlanV08(ContractModel):
    """Pre-execution commitments that do not depend on future receipt bytes."""

    task_index: int = Field(ge=0)
    arm: str = Field(min_length=1)
    episode_id: str = Field(min_length=1)
    expected_step_count: int = Field(gt=0)
    implementation_bundle_sha256: Sha256
    expected_runtime_engine_sha256: Sha256


class CanonicalExecutionVerificationV08(SignedRecordBase):
    protocol: Literal["structure-two-gate-b-v0.8-canonical-execution-verification@1.0"]
    signer_role: Literal[FormalRole.CANONICAL_EXECUTION_VERIFIER]
    parent_run_manifest_content_sha256: Sha256
    canonical_executor_protocol: Literal["structure-two-canonical-per-episode-executor@0.9"]
    canonical_execution_id: str = Field(min_length=16)
    canonical_execution_artifact_sha256: Sha256
    canonical_execution_content_sha256: Sha256
    arms: tuple[str, ...]
    episode_ids: tuple[str, ...] = Field(min_length=1)
    tasks: tuple[CanonicalTaskBindingV08, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _exact_coverage(self) -> CanonicalExecutionVerificationV08:
        if self.arms != EXPECTED_ARMS or len(self.episode_ids) != len(set(self.episode_ids)):
            raise ValueError("canonical verification changed arm or episode scope")
        expected = tuple(
            (arm, episode_id) for arm in EXPECTED_ARMS for episode_id in self.episode_ids
        )
        actual = tuple((task.arm, task.episode_id) for task in self.tasks)
        if actual != expected or len(actual) != len(set(actual)):
            raise ValueError("canonical verification lacks exact arm-by-episode coverage")
        if tuple(task.task_index for task in self.tasks) != tuple(range(len(expected))):
            raise ValueError("canonical verification task order is noncanonical")
        return self

    @property
    def content_sha256(self) -> str:
        return content_sha256(self)


class EpisodeRegistrationV08(ContractModel):
    episode_id: str = Field(min_length=1)
    ontology: EpisodePublicOntology
    evaluation_step_index: int = Field(ge=0)
    expected_step_count: int = Field(gt=0)
    shared_information_set_sha256_by_step: tuple[Sha256, ...] = Field(min_length=1)
    shared_decision_id_by_step: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _episode_scope(self) -> EpisodeRegistrationV08:
        if self.episode_id != self.ontology.episode_id:
            raise ValueError("episode registration and ontology IDs differ")
        if self.evaluation_step_index >= self.expected_step_count:
            raise ValueError("registered evaluation step is outside the episode")
        if len(self.shared_information_set_sha256_by_step) != self.expected_step_count:
            raise ValueError("registered information sets lack exact step coverage")
        if len(self.shared_decision_id_by_step) != self.expected_step_count:
            raise ValueError("registered decision IDs lack exact step coverage")
        if any(not decision_id for decision_id in self.shared_decision_id_by_step):
            raise ValueError("registered decision IDs must be non-empty")
        if len(self.shared_decision_id_by_step) != len(set(self.shared_decision_id_by_step)):
            raise ValueError("registered decision IDs must be unique within an episode")
        return self


class ProjectionRegistrationV08(ContractModel):
    arm: str = Field(min_length=1)
    episode_id: str = Field(min_length=1)
    projection: RuntimeActionProjection

    @model_validator(mode="after")
    def _projection_key(self) -> ProjectionRegistrationV08:
        if self.arm != self.projection.arm or self.episode_id != self.projection.episode_id:
            raise ValueError("projection registration key differs from projection payload")
        return self


class GateBV08RunManifest(SignedRecordBase):
    protocol: Literal["structure-two-gate-b-v0.8-run-manifest@1.0"]
    signer_role: Literal[FormalRole.PREREGISTRATION_CUSTODIAN]
    raw_chain_policy_content_sha256: Sha256
    run_id: UUID
    gate_b_protocol_content_sha256: Sha256
    expected_canonical_execution_id: str = Field(min_length=16)
    arms: tuple[str, ...]
    episodes: tuple[EpisodeRegistrationV08, ...] = Field(min_length=1)
    projections: tuple[ProjectionRegistrationV08, ...] = Field(min_length=1)
    canonical_task_plan: tuple[CanonicalTaskPlanV08, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _registered_scope(self) -> GateBV08RunManifest:
        if self.arms != EXPECTED_ARMS:
            raise ValueError("run manifest changed the frozen arm order")
        episode_ids = tuple(item.episode_id for item in self.episodes)
        if len(episode_ids) != len(set(episode_ids)):
            raise ValueError("run manifest duplicated an episode")
        expected_pairs = tuple((arm, episode) for arm in EXPECTED_ARMS for episode in episode_ids)
        actual_pairs = tuple((item.arm, item.episode_id) for item in self.projections)
        if actual_pairs != expected_pairs or len(actual_pairs) != len(set(actual_pairs)):
            raise ValueError("run manifest lacks exact arm-by-episode projections")
        ontology_by_episode = {item.episode_id: item.ontology for item in self.episodes}
        for registration in self.projections:
            registration.projection.validate_against(ontology_by_episode[registration.episode_id])
        plan_pairs = tuple((item.arm, item.episode_id) for item in self.canonical_task_plan)
        if plan_pairs != expected_pairs:
            raise ValueError("run manifest canonical task plan lacks exact coverage")
        if tuple(item.task_index for item in self.canonical_task_plan) != tuple(
            range(len(expected_pairs))
        ):
            raise ValueError("run manifest canonical task plan order is noncanonical")
        step_count_by_episode = {
            item.episode_id: item.expected_step_count for item in self.episodes
        }
        if any(
            item.expected_step_count != step_count_by_episode[item.episode_id]
            for item in self.canonical_task_plan
        ):
            raise ValueError("canonical task plan changed registered episode step counts")
        if self.gate_b_protocol_content_sha256 != content_sha256(canonical_protocol_payload_v0_8()):
            raise ValueError("run manifest changed the frozen Gate B protocol")
        return self

    @property
    def content_sha256(self) -> str:
        return content_sha256(self)


def belief_trace_sha256_v0_8(
    *,
    runtime_state_before_readout_sha256: str,
    readout: DecisionReadout,
) -> str:
    """Derive the stored belief-trace digest from the captured live payload."""

    return content_sha256(
        {
            "runtime_state_before_readout_sha256": runtime_state_before_readout_sha256,
            "decision_id": readout.decision_id,
            "information_set_sha256": readout.information_set_sha256,
            "ontology_manifest_sha256": readout.ontology_manifest_sha256,
            "belief": readout.belief,
        }
    )


def action_policy_trace_sha256_v0_8(
    *,
    runtime_state_before_readout_sha256: str,
    readout: DecisionReadout,
) -> str:
    """Derive the stored action trace from policy and committed runtime action."""

    return content_sha256(
        {
            "runtime_state_before_readout_sha256": runtime_state_before_readout_sha256,
            "decision_id": readout.decision_id,
            "information_set_sha256": readout.information_set_sha256,
            "projection_manifest_sha256": readout.projection_manifest_sha256,
            "action_policy": readout.action_policy,
            "selected_public_action": readout.selected_public_action,
            "selected_runtime_action": readout.selected_runtime_action,
        }
    )


class RawRuntimeStepV08(ContractModel):
    step_index: int = Field(ge=0)
    canonical_input_state_sha256: Sha256
    canonical_output_state_sha256: Sha256
    runtime_state_before_readout_sha256: Sha256
    belief_trace_sha256: Sha256
    action_policy_trace_sha256: Sha256
    evaluator_truth_sha256: Sha256
    readout: DecisionReadout

    @model_validator(mode="after")
    def _runtime_semantics(self) -> RawRuntimeStepV08:
        if self.runtime_state_before_readout_sha256 != self.canonical_input_state_sha256:
            raise ValueError("belief/action readout did not bind the canonical predecision state")
        if self.readout.realized_utility is None or self.readout.utility_event_index is None:
            raise ValueError("raw runtime step must retain post-action consequential utility")
        if self.readout.evaluator_truth_accessed:
            raise ValueError("runtime readout accessed evaluator truth before action")
        if self.belief_trace_sha256 != belief_trace_sha256_v0_8(
            runtime_state_before_readout_sha256=self.runtime_state_before_readout_sha256,
            readout=self.readout,
        ):
            raise ValueError("belief trace digest is not derived from the captured live readout")
        if self.action_policy_trace_sha256 != action_policy_trace_sha256_v0_8(
            runtime_state_before_readout_sha256=self.runtime_state_before_readout_sha256,
            readout=self.readout,
        ):
            raise ValueError("action trace digest is not derived from the captured live readout")
        return self

    @property
    def readout_payload_sha256(self) -> str:
        return content_sha256(
            {
                "information_set_sha256": self.readout.information_set_sha256,
                "ontology_manifest_sha256": self.readout.ontology_manifest_sha256,
                "projection_manifest_sha256": self.readout.projection_manifest_sha256,
                "runtime_state_before_readout_sha256": (self.runtime_state_before_readout_sha256),
                "belief": self.readout.belief,
                "action_policy": self.readout.action_policy,
                "belief_trace_sha256": self.belief_trace_sha256,
                "action_policy_trace_sha256": self.action_policy_trace_sha256,
            }
        )

    @property
    def action_payload_sha256(self) -> str:
        return self.readout.selected_runtime_action.content_sha256

    @property
    def utility_payload_sha256(self) -> str:
        return content_sha256({"realized_utility": self.readout.realized_utility})


class RawRuntimeArmEpisodeOutputV08(ContractModel):
    protocol: Literal["structure-two-gate-b-v0.8-runtime-readout-output@1.0"]
    raw_chain_policy_content_sha256: Sha256
    run_manifest_content_sha256: Sha256
    run_id: UUID
    canonical_execution_id: str = Field(min_length=16)
    canonical_execution_content_sha256: Sha256
    canonical_task_receipt_content_sha256: Sha256
    task_index: int = Field(ge=0)
    arm: str = Field(min_length=1)
    episode_id: str = Field(min_length=1)
    implementation_bundle_sha256: Sha256
    runtime_engine_sha256: Sha256
    ontology_manifest_sha256: Sha256
    projection_manifest_sha256: Sha256
    runtime_mode: Literal["instrumented-frozen-bundle-live-state-readout"]
    steps: tuple[RawRuntimeStepV08, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _step_scope(self) -> RawRuntimeArmEpisodeOutputV08:
        if tuple(step.step_index for step in self.steps) != tuple(range(len(self.steps))):
            raise ValueError("raw runtime steps must be contiguous and zero based")
        for step in self.steps:
            if step.readout.arm != self.arm or step.readout.episode_id != self.episode_id:
                raise ValueError("raw readout crossed its arm or episode boundary")
            if step.readout.ontology_manifest_sha256 != self.ontology_manifest_sha256:
                raise ValueError("raw readout changed the episode ontology")
            if step.readout.projection_manifest_sha256 != self.projection_manifest_sha256:
                raise ValueError("raw readout changed the runtime-action projection")
        return self

    @property
    def content_sha256(self) -> str:
        return content_sha256(self)


@dataclass(frozen=True, slots=True)
class LoadedRawRuntimeArtifactV08:
    path: Path
    artifact_sha256: str
    output_content_sha256: str
    output: RawRuntimeArmEpisodeOutputV08


def load_raw_runtime_artifact_v0_8(path: Path) -> LoadedRawRuntimeArtifactV08:
    """Read through one no-follow file descriptor and reject mutation/link aliases."""

    if not hasattr(os, "O_NOFOLLOW"):
        raise RuntimeError("raw formal chain requires O_NOFOLLOW support")
    flags = os.O_RDONLY | os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise ValueError("raw runtime artifact cannot be opened without following links") from error
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ValueError("raw runtime artifact must be a singly linked regular file")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        encoded = b"".join(chunks)
        after = os.fstat(descriptor)
        identity_before = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        identity_after = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if identity_before != identity_after or len(encoded) != before.st_size:
            raise ValueError("raw runtime artifact changed while being read")
    finally:
        os.close(descriptor)
    try:
        raw = json.loads(encoded, object_pairs_hook=_reject_duplicate_json_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("raw runtime artifact is not valid UTF-8 JSON") from error
    if not isinstance(raw, dict):
        raise ValueError("raw runtime artifact must contain one JSON object")
    if encoded != canonical_json(raw).encode("utf-8"):
        raise ValueError("raw runtime artifact bytes are not canonical JSON")
    output = RawRuntimeArmEpisodeOutputV08.model_validate(raw)
    if encoded != canonical_json(output.model_dump(mode="json")).encode("utf-8"):
        raise ValueError("raw runtime artifact contains hidden or unregistered fields")
    return LoadedRawRuntimeArtifactV08(
        path=path,
        artifact_sha256=hashlib.sha256(encoded).hexdigest(),
        output_content_sha256=output.content_sha256,
        output=output,
    )


class RuntimeReadoutReceiptV08(SignedRecordBase):
    protocol: Literal["structure-two-gate-b-v0.8-runtime-readout-receipt@1.0"]
    signer_role: Literal[FormalRole.RUNTIME_READOUT_EXECUTOR]
    run_id: UUID
    run_manifest_content_sha256: Sha256
    canonical_verification_content_sha256: Sha256
    canonical_task_receipt_content_sha256: Sha256
    task_index: int = Field(ge=0)
    arm: str = Field(min_length=1)
    episode_id: str = Field(min_length=1)
    implementation_bundle_sha256: Sha256
    raw_output_artifact_sha256: Sha256
    raw_output_content_sha256: Sha256
    process_started_at_utc: datetime
    process_finished_at_utc: datetime
    runtime_engine_sha256: Sha256

    @model_validator(mode="after")
    def _runtime_interval(self) -> RuntimeReadoutReceiptV08:
        started = _require_utc(self.process_started_at_utc, "runtime start time")
        finished = _require_utc(self.process_finished_at_utc, "runtime finish time")
        if not started <= finished <= self.issued_at_utc:
            raise ValueError("runtime receipt has impossible process/issue ordering")
        return self

    @property
    def content_sha256(self) -> str:
        return content_sha256(self)


class CausalBrokerEventV08(ContractModel):
    sequence_index: int = Field(ge=0)
    kind: CausalEventKind
    observed_at_utc: datetime
    payload_sha256: Sha256

    @model_validator(mode="after")
    def _utc_event(self) -> CausalBrokerEventV08:
        _require_utc(self.observed_at_utc, "causal-broker event time")
        return self


class CausalBrokerStepReceiptV08(SignedRecordBase):
    protocol: Literal["structure-two-gate-b-v0.8-causal-broker-step@1.0"]
    signer_role: Literal[FormalRole.CAUSAL_BROKER]
    run_id: UUID
    run_manifest_content_sha256: Sha256
    runtime_receipt_content_sha256: Sha256
    task_index: int = Field(ge=0)
    arm: str = Field(min_length=1)
    episode_id: str = Field(min_length=1)
    step_index: int = Field(ge=0)
    decision_id: str = Field(min_length=1)
    events: tuple[CausalBrokerEventV08, ...]

    @model_validator(mode="after")
    def _event_order(self) -> CausalBrokerStepReceiptV08:
        if tuple(event.kind for event in self.events) != CAUSAL_EVENT_ORDER:
            raise ValueError("causal broker event order or coverage is noncanonical")
        if tuple(event.sequence_index for event in self.events) != tuple(
            range(len(CAUSAL_EVENT_ORDER))
        ):
            raise ValueError("causal broker sequence must be contiguous and zero based")
        times = tuple(event.observed_at_utc for event in self.events)
        if any(right < left for left, right in pairwise(times)):
            raise ValueError("causal broker timestamps are not monotonic")
        if times[-1] > self.issued_at_utc:
            raise ValueError("causal broker receipt predates its final event")
        return self

    @property
    def content_sha256(self) -> str:
        return content_sha256(self)


class CustodyHopReceiptV08(SignedRecordBase):
    protocol: Literal["structure-two-gate-b-v0.8-custody-hop@1.0"]
    custody_role: CustodyRole
    run_id: UUID
    run_manifest_content_sha256: Sha256
    task_index: int = Field(ge=0)
    arm: str = Field(min_length=1)
    episode_id: str = Field(min_length=1)
    raw_output_artifact_sha256: Sha256
    raw_output_content_sha256: Sha256
    runtime_receipt_content_sha256: Sha256
    broker_receipt_content_sha256: tuple[Sha256, ...] = Field(min_length=1)
    parent_custody_receipt_sha256: Sha256 | None
    storage_locator_sha256: Sha256

    @model_validator(mode="after")
    def _custody_role(self) -> CustodyHopReceiptV08:
        expected = {
            CustodyRole.INGEST: FormalRole.INGEST_CUSTODIAN,
            CustodyRole.ARCHIVE: FormalRole.ARCHIVE_CUSTODIAN,
        }[self.custody_role]
        if self.signer_role is not expected:
            raise ValueError("custody role and signer role disagree")
        if (self.custody_role is CustodyRole.INGEST) != (
            self.parent_custody_receipt_sha256 is None
        ):
            raise ValueError("only the ingest custody hop may omit a parent")
        return self

    @property
    def content_sha256(self) -> str:
        return content_sha256(self)


class RawTaskEvidenceV08(ContractModel):
    raw_output_artifact_sha256: Sha256
    raw_output_content_sha256: Sha256
    output: RawRuntimeArmEpisodeOutputV08
    runtime_receipt: RuntimeReadoutReceiptV08
    broker_receipts: tuple[CausalBrokerStepReceiptV08, ...] = Field(min_length=1)
    custody_hops: tuple[CustodyHopReceiptV08, CustodyHopReceiptV08]

    @model_validator(mode="after")
    def _internal_hashes(self) -> RawTaskEvidenceV08:
        if self.raw_output_content_sha256 != self.output.content_sha256:
            raise ValueError("raw task evidence content hash mismatch")
        if tuple(row.step_index for row in self.broker_receipts) != tuple(
            range(len(self.output.steps))
        ):
            raise ValueError("causal broker lacks exact step coverage")
        if tuple(hop.custody_role for hop in self.custody_hops) != (
            CustodyRole.INGEST,
            CustodyRole.ARCHIVE,
        ):
            raise ValueError("raw task requires ingest then archive custody")
        if self.custody_hops[1].parent_custody_receipt_sha256 != (
            self.custody_hops[0].content_sha256
        ):
            raise ValueError("archive custody hop does not bind its ingest parent")
        return self

    @property
    def content_sha256(self) -> str:
        return content_sha256(self)


class IndependentReviewReceiptV08(SignedRecordBase):
    protocol: Literal["structure-two-gate-b-v0.8-independent-review@1.0"]
    signer_role: Literal[FormalRole.INDEPENDENT_REVIEWER]
    run_id: UUID
    run_manifest_content_sha256: Sha256
    canonical_verification_content_sha256: Sha256
    task_evidence_content_sha256: tuple[Sha256, ...] = Field(min_length=1)
    diagnostic_report_content_sha256: Sha256
    recomputed_outcome: Literal["PASS", "FAIL"]

    @property
    def content_sha256(self) -> str:
        return content_sha256(self)


class GateBV08RawFormalExecutionChain(ContractModel):
    protocol: Literal["structure-two-gate-b-v0.8-raw-formal-execution-chain@1.0"]
    raw_chain_policy_content_sha256: Sha256
    run_manifest: GateBV08RunManifest
    canonical_verification: CanonicalExecutionVerificationV08
    tasks: tuple[RawTaskEvidenceV08, ...] = Field(min_length=1)
    review_receipt: IndependentReviewReceiptV08

    @model_validator(mode="after")
    def _exact_task_coverage(self) -> GateBV08RawFormalExecutionChain:
        episode_ids = tuple(item.episode_id for item in self.run_manifest.episodes)
        expected = tuple((arm, episode_id) for arm in EXPECTED_ARMS for episode_id in episode_ids)
        actual = tuple((task.output.arm, task.output.episode_id) for task in self.tasks)
        if actual != expected or len(actual) != len(set(actual)):
            raise ValueError("raw formal chain lacks exact arm-by-episode coverage")
        if tuple(task.output.task_index for task in self.tasks) != tuple(range(len(expected))):
            raise ValueError("raw formal-chain task order is noncanonical")
        return self

    @property
    def content_sha256(self) -> str:
        return content_sha256(self)


def _sign_record(
    record: SignedRecordBase,
    *,
    signer: Ed25519AttestationSigner,
    role: FormalRole,
    domain: str,
) -> Any:
    if record.attestation is not None:
        raise ValueError("record is already signed")
    verifier = signer.verifier()
    if record.signer_role is not role:
        raise ValueError("signing helper received the wrong formal role")
    if (
        record.signer_key_id != verifier.key_id
        or record.signer_public_key_sha256 != verifier.public_key_sha256
    ):
        raise AttestationError("record signer metadata differs from signing key")
    return record.model_copy(update={"attestation": signer.sign(domain, attested_payload(record))})


def sign_canonical_verification_v0_8(
    record: CanonicalExecutionVerificationV08,
    *,
    signer: Ed25519AttestationSigner,
) -> CanonicalExecutionVerificationV08:
    return cast(
        CanonicalExecutionVerificationV08,
        _sign_record(
            record,
            signer=signer,
            role=FormalRole.CANONICAL_EXECUTION_VERIFIER,
            domain=CANONICAL_VERIFICATION_DOMAIN,
        ),
    )


def sign_run_manifest_v0_8(
    record: GateBV08RunManifest,
    *,
    signer: Ed25519AttestationSigner,
) -> GateBV08RunManifest:
    return cast(
        GateBV08RunManifest,
        _sign_record(
            record,
            signer=signer,
            role=FormalRole.PREREGISTRATION_CUSTODIAN,
            domain=RUN_MANIFEST_DOMAIN,
        ),
    )


def sign_runtime_receipt_v0_8(
    record: RuntimeReadoutReceiptV08,
    *,
    signer: Ed25519AttestationSigner,
) -> RuntimeReadoutReceiptV08:
    return cast(
        RuntimeReadoutReceiptV08,
        _sign_record(
            record,
            signer=signer,
            role=FormalRole.RUNTIME_READOUT_EXECUTOR,
            domain=RUNTIME_RECEIPT_DOMAIN,
        ),
    )


def sign_broker_receipt_v0_8(
    record: CausalBrokerStepReceiptV08,
    *,
    signer: Ed25519AttestationSigner,
) -> CausalBrokerStepReceiptV08:
    return cast(
        CausalBrokerStepReceiptV08,
        _sign_record(
            record,
            signer=signer,
            role=FormalRole.CAUSAL_BROKER,
            domain=BROKER_RECEIPT_DOMAIN,
        ),
    )


def sign_custody_hop_v0_8(
    record: CustodyHopReceiptV08,
    *,
    signer: Ed25519AttestationSigner,
) -> CustodyHopReceiptV08:
    return cast(
        CustodyHopReceiptV08,
        _sign_record(
            record,
            signer=signer,
            role=record.signer_role,
            domain=CUSTODY_RECEIPT_DOMAIN,
        ),
    )


def sign_review_receipt_v0_8(
    record: IndependentReviewReceiptV08,
    *,
    signer: Ed25519AttestationSigner,
) -> IndependentReviewReceiptV08:
    return cast(
        IndependentReviewReceiptV08,
        _sign_record(
            record,
            signer=signer,
            role=FormalRole.INDEPENDENT_REVIEWER,
            domain=REVIEW_RECEIPT_DOMAIN,
        ),
    )


class PersistentReplayRegistryV08:
    """SQLite nonce registry with an atomic unique constraint.

    Formal use additionally requires its id, enrollment digest, canonical path,
    and stable device/inode identity to match the checked-in policy and the
    independently signed trust manifest.  Every connection retains a no-follow
    guard descriptor and rechecks the path/descriptor identity after the
    transaction, so replacing the database object at the same path fails
    closed.  Device/inode identity does not detect an in-place content rollback
    or a filesystem snapshot restore that preserves identity; consequently this
    diagnostic backend is not a monotonic/WORM formal replay authority.
    """

    def __init__(
        self,
        *,
        path: Path,
        registry_id: UUID,
        enrollment_sha256: str,
        initialize: bool = False,
    ) -> None:
        if len(enrollment_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in enrollment_sha256
        ):
            raise ValueError("replay-registry enrollment must be a SHA-256 digest")
        if path.is_symlink():
            raise ValueError("replay registry cannot be a symlink")
        self.path = path
        self.registry_id = registry_id
        self.enrollment_sha256 = enrollment_sha256
        if initialize:
            self._initialize()
        self.storage_identity_sha256 = self._capture_storage_identity()
        self._verify_metadata()

    @staticmethod
    def _identity_tuple(metadata: os.stat_result) -> tuple[int, int]:
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ValueError("replay registry must be a singly linked regular file")
        return metadata.st_dev, metadata.st_ino

    def _identity_sha256(self, metadata: os.stat_result) -> str:
        device, inode = self._identity_tuple(metadata)
        return content_sha256(
            {
                "protocol": REPLAY_REGISTRY_PROTOCOL_ID,
                "canonical_path": str(self.path.resolve(strict=True)),
                "device": device,
                "inode": inode,
            }
        )

    def _open_guard(self) -> tuple[int, os.stat_result]:
        if not hasattr(os, "O_NOFOLLOW"):
            raise RuntimeError("replay registry requires O_NOFOLLOW support")
        try:
            descriptor = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
        except OSError as error:
            raise ValueError("replay registry cannot be opened without following links") from error
        try:
            metadata = os.fstat(descriptor)
            self._identity_tuple(metadata)
        except Exception:
            os.close(descriptor)
            raise
        return descriptor, metadata

    def _capture_storage_identity(self) -> str:
        descriptor, metadata = self._open_guard()
        try:
            return self._identity_sha256(metadata)
        finally:
            os.close(descriptor)

    @contextmanager
    def _guarded_connection(self) -> Any:
        descriptor, before = self._open_guard()
        try:
            if self._identity_sha256(before) != self.storage_identity_sha256:
                raise ValueError("replay registry stable storage identity changed")
            connection = sqlite3.connect(self.path, isolation_level="IMMEDIATE")
            try:
                with connection:
                    yield connection
            finally:
                connection.close()
            after = os.fstat(descriptor)
            path_after = os.lstat(self.path)
            if (
                self._identity_tuple(after) != self._identity_tuple(before)
                or self._identity_tuple(path_after) != self._identity_tuple(before)
                or self._identity_sha256(after) != self.storage_identity_sha256
            ):
                raise ValueError("replay registry stable storage identity changed")
        finally:
            os.close(descriptor)

    def _initialize(self) -> None:
        if self.path.exists():
            raise ValueError("replay registry already exists")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path, isolation_level="IMMEDIATE") as connection:
            connection.execute("CREATE TABLE metadata (registry_id TEXT, enrollment_sha256 TEXT)")
            connection.execute(
                "INSERT INTO metadata VALUES (?, ?)",
                (str(self.registry_id), self.enrollment_sha256),
            )
            connection.execute(
                "CREATE TABLE consumed (nonce TEXT PRIMARY KEY, consumed_at_utc TEXT NOT NULL)"
            )

    def _verify_metadata(self) -> None:
        if not self.path.exists() or self.path.is_symlink():
            raise ValueError("persistent replay registry is absent or linked")
        with self._guarded_connection() as connection:
            rows = connection.execute(
                "SELECT registry_id, enrollment_sha256 FROM metadata"
            ).fetchall()
        if rows != [(str(self.registry_id), self.enrollment_sha256)]:
            raise ValueError("persistent replay-registry enrollment mismatch")

    def consume_many(self, nonces: Sequence[UUID], *, consumed_at_utc: datetime) -> None:
        consumed = _require_utc(consumed_at_utc, "replay consumption time")
        nonce_values = tuple(str(nonce) for nonce in nonces)
        if len(nonce_values) != len(set(nonce_values)):
            raise ValueError("one formal chain reused a nonce internally")
        try:
            with self._guarded_connection() as connection:
                connection.executemany(
                    "INSERT INTO consumed VALUES (?, ?)",
                    ((nonce, consumed.isoformat()) for nonce in nonce_values),
                )
        except sqlite3.IntegrityError as error:
            raise ValueError("formal Gate B execution replay detected") from error


def _verify_signed_record(
    record: SignedRecordBase,
    *,
    manifest: GateBV08TrustManifest,
    expected_role: FormalRole,
    domain: str,
    now_utc: datetime,
) -> None:
    if record.signer_role is not expected_role:
        raise AttestationError("signed record used the wrong formal role")
    anchor = manifest.anchor(expected_role)
    if (
        record.signer_authority_id != anchor.authority_id
        or record.signer_key_id != anchor.key_id
        or record.signer_public_key_sha256 != anchor.public_key_sha256
    ):
        raise AttestationError("signed record is outside the enrolled role anchor")
    now = _require_utc(now_utc, "formal verification time")
    earliest_issue = max(manifest.issued_at_utc, anchor.enrolled_at_utc)
    if not earliest_issue <= record.issued_at_utc <= now <= record.expires_at_utc:
        raise ValueError("signed record is stale or not yet valid")
    anchor.verifier().verify(domain, attested_payload(record), record.attestation)


def _verify_broker_against_step(
    broker: CausalBrokerStepReceiptV08,
    *,
    output: RawRuntimeArmEpisodeOutputV08,
    runtime_receipt: RuntimeReadoutReceiptV08,
) -> None:
    step = output.steps[broker.step_index]
    if (
        broker.run_id != output.run_id
        or broker.run_manifest_content_sha256 != output.run_manifest_content_sha256
        or broker.runtime_receipt_content_sha256 != runtime_receipt.content_sha256
        or broker.task_index != output.task_index
        or broker.arm != output.arm
        or broker.episode_id != output.episode_id
        or broker.decision_id != step.readout.decision_id
    ):
        raise ValueError("causal broker receipt changed its raw runtime binding")
    expected_payloads = (
        step.readout_payload_sha256,
        step.action_payload_sha256,
        step.evaluator_truth_sha256,
        step.utility_payload_sha256,
    )
    if tuple(event.payload_sha256 for event in broker.events) != expected_payloads:
        raise ValueError("causal broker event payloads differ from raw runtime evidence")
    if step.readout.readout_event_index != broker.events[0].sequence_index:
        raise ValueError("runtime readout index differs from causal broker")
    if step.readout.action_commit_event_index != broker.events[1].sequence_index:
        raise ValueError("runtime action index differs from causal broker")
    if step.readout.utility_event_index != broker.events[3].sequence_index:
        raise ValueError("runtime utility index differs from causal broker")


def _validate_runtime_step_against_public_contract(
    step: RawRuntimeStepV08,
    *,
    ontology: EpisodePublicOntology,
    projection: RuntimeActionProjection,
) -> None:
    """Validate every captured step, including steps not selected for scoring."""

    step.readout.belief.validate_against(ontology)
    step.readout.action_policy.validate_against(ontology)
    if step.readout.belief.kind.value != "belief":
        raise ValueError("raw belief field contains an action distribution")
    if step.readout.action_policy.kind.value != "action":
        raise ValueError("raw action-policy field contains a belief distribution")
    if (
        step.readout.readout_stage.value != "pre_action_pre_evaluator_truth"
        or step.readout.evaluator_truth_accessed
        or step.readout.intervening_exogenous_event
    ):
        raise ValueError("raw step violated the pre-action causal boundary")
    projection.validate_against(ontology)
    selected_public = projection.project(
        step.readout.selected_runtime_action,
        ontology=ontology,
    )
    if (
        step.readout.selected_public_action not in ontology.action_support
        or selected_public != step.readout.selected_public_action
    ):
        raise ValueError("live runtime action projection changed semantics")
    maximum = max(step.readout.action_policy.probabilities)
    expected_selected = next(
        label
        for label, probability in zip(
            step.readout.action_policy.support,
            step.readout.action_policy.probabilities,
            strict=True,
        )
        if probability == maximum
    )
    if step.readout.selected_public_action != expected_selected:
        raise ValueError("raw selected action violates deterministic lexical argmax")


def _derive_diagnostic_report(
    chain: GateBV08RawFormalExecutionChain,
) -> dict[str, Any]:
    manifest = chain.run_manifest
    projection_by_key = {
        (item.arm, item.episode_id): item.projection for item in manifest.projections
    }
    task_by_key = {(task.output.arm, task.output.episode_id): task for task in chain.tasks}
    evidence: list[ComparatorEvidence] = []
    for spec in canonical_comparator_specs_v0_8():
        for registration in manifest.episodes:
            step_index = registration.evaluation_step_index
            left_step = task_by_key[(spec.left_arm, registration.episode_id)].output.steps[
                step_index
            ]
            right_step = task_by_key[(spec.right_arm, registration.episode_id)].output.steps[
                step_index
            ]
            utility_scored = spec.utility.relation.value != "not_scored"
            window_id = spec.causal_window.window_id

            def as_comparator_readout(
                step: RawRuntimeStepV08,
                *,
                causal_window_id: str = window_id,
                include_utility: bool = utility_scored,
            ) -> DecisionReadout:
                utility_event_index = step.readout.utility_event_index if include_utility else None
                return replace(
                    step.readout,
                    causal_window_id=causal_window_id,
                    realized_utility=(step.readout.realized_utility if include_utility else None),
                    utility_event_index=utility_event_index,
                )

            evidence.append(
                ComparatorEvidence(
                    comparison_id=spec.comparison_id,
                    left=as_comparator_readout(left_step),
                    right=as_comparator_readout(right_step),
                )
            )
    protocol = FrozenComparatorTypedDualGateB(
        content_sha256=content_sha256(canonical_protocol_payload_v0_8()),
        comparators=canonical_comparator_specs_v0_8(),
    )
    return score_frozen_gate_b_v0_8_diagnostic(
        evidence,
        protocol=protocol,
        ontologies=tuple(item.ontology for item in manifest.episodes),
        projections=projection_by_key,
    )


@dataclass(frozen=True, slots=True)
class VerifiedRawChainCandidateV08:
    chain_content_sha256: str
    diagnostic_report: Mapping[str, Any]
    diagnostic_report_content_sha256: str
    typed_relations_passed: bool
    consumed_nonce_count: int
    formal_gate_b_passed: Literal[False] = False
    seven_operator_ablation_authorized: Literal[False] = False


def verify_raw_chain_candidate_v0_8(
    chain: GateBV08RawFormalExecutionChain,
    *,
    policy: RawFormalChainPolicyV08,
    trust_manifest: GateBV08TrustManifest,
    replay_registry: PersistentReplayRegistryV08,
    raw_artifact_paths: Mapping[tuple[str, str], Path],
) -> VerifiedRawChainCandidateV08:
    """Recompute a policy-bound chain; never mint a Gate-B authorization token."""

    # Re-enter every immutable model through its strict parser.  ``model_copy``
    # is convenient for trusted code but deliberately does not rerun Pydantic
    # validators, so it cannot be accepted as a verification boundary.
    policy = RawFormalChainPolicyV08.model_validate(policy.model_dump(mode="python"))
    trust_manifest = GateBV08TrustManifest.model_validate(trust_manifest.model_dump(mode="python"))
    chain = GateBV08RawFormalExecutionChain.model_validate(chain.model_dump(mode="python"))
    # Formal freshness uses the verifier process clock.  A caller cannot
    # backdate ``now`` to revive an expired receipt.
    now = datetime.now(UTC)
    verify_policy_bound_trust_manifest_v0_8(
        trust_manifest,
        policy=policy,
        now_utc=now,
    )
    if policy.replay_registry_status is not EnrollmentStatus.ENROLLED:
        raise ValueError("persistent replay registry is not enrolled")
    if (
        replay_registry.registry_id != policy.replay_registry_id
        or replay_registry.enrollment_sha256 != policy.replay_registry_enrollment_sha256
        or replay_registry.storage_identity_sha256 != policy.replay_registry_storage_identity_sha256
    ):
        raise ValueError("replay registry differs from policy enrollment")
    if chain.raw_chain_policy_content_sha256 != policy.content_sha256:
        raise ValueError("raw chain substituted another policy")
    if chain.run_manifest.raw_chain_policy_content_sha256 != policy.content_sha256:
        raise ValueError("run manifest substituted another policy")
    if chain.run_manifest.gate_b_protocol_content_sha256 != (policy.gate_b_protocol_content_sha256):
        raise ValueError("run manifest substituted another Gate B protocol")
    if chain.canonical_verification.parent_run_manifest_content_sha256 != (
        chain.run_manifest.content_sha256
    ):
        raise ValueError("canonical verification changed its preregistration parent")
    _verify_signed_record(
        chain.canonical_verification,
        manifest=trust_manifest,
        expected_role=FormalRole.CANONICAL_EXECUTION_VERIFIER,
        domain=CANONICAL_VERIFICATION_DOMAIN,
        now_utc=now,
    )
    _verify_signed_record(
        chain.run_manifest,
        manifest=trust_manifest,
        expected_role=FormalRole.PREREGISTRATION_CUSTODIAN,
        domain=RUN_MANIFEST_DOMAIN,
        now_utc=now,
    )
    if chain.canonical_verification.issued_at_utc < chain.run_manifest.issued_at_utc:
        raise ValueError("canonical verification predates preregistration")
    if chain.canonical_verification.canonical_execution_id != (
        chain.run_manifest.expected_canonical_execution_id
    ):
        raise ValueError("canonical verification changed the preregistered execution ID")
    expected_paths = {
        (arm, episode.episode_id)
        for arm in EXPECTED_ARMS
        for episode in chain.run_manifest.episodes
    }
    if set(raw_artifact_paths) != expected_paths:
        raise ValueError("raw artifact paths lack exact arm-by-episode coverage")
    canonical_by_key = {
        (task.arm, task.episode_id): task for task in chain.canonical_verification.tasks
    }
    plan_by_key = {
        (task.arm, task.episode_id): task for task in chain.run_manifest.canonical_task_plan
    }
    for key, source in canonical_by_key.items():
        plan = plan_by_key[key]
        if (
            source.task_index != plan.task_index
            or source.implementation_bundle_sha256 != plan.implementation_bundle_sha256
            or source.runtime_engine_sha256 != plan.expected_runtime_engine_sha256
            or len(source.steps) != plan.expected_step_count
        ):
            raise ValueError("canonical verification changed its preregistered task plan")
    registration_by_episode = {item.episode_id: item for item in chain.run_manifest.episodes}
    projection_by_key = {
        (item.arm, item.episode_id): item.projection for item in chain.run_manifest.projections
    }
    nonces: list[UUID] = [chain.canonical_verification.nonce, chain.run_manifest.nonce]
    for task in chain.tasks:
        output = task.output
        key = (output.arm, output.episode_id)
        source = canonical_by_key[key]
        registration = registration_by_episode[output.episode_id]
        projection = projection_by_key[key]
        loaded = load_raw_runtime_artifact_v0_8(raw_artifact_paths[key])
        if (
            loaded.artifact_sha256 != task.raw_output_artifact_sha256
            or loaded.output_content_sha256 != task.raw_output_content_sha256
            or loaded.output != output
        ):
            raise ValueError("stored raw runtime artifact is stale or substituted")
        if (
            output.raw_chain_policy_content_sha256 != policy.content_sha256
            or output.run_manifest_content_sha256 != chain.run_manifest.content_sha256
            or output.run_id != chain.run_manifest.run_id
            or output.canonical_execution_id != chain.canonical_verification.canonical_execution_id
            or output.canonical_execution_content_sha256
            != chain.canonical_verification.canonical_execution_content_sha256
            or output.canonical_task_receipt_content_sha256
            != source.canonical_task_receipt_content_sha256
            or output.task_index != source.task_index
            or output.implementation_bundle_sha256 != source.implementation_bundle_sha256
            or output.runtime_engine_sha256 != source.runtime_engine_sha256
            or len(output.steps) != registration.expected_step_count
            or registration.expected_step_count != len(source.steps)
            or output.ontology_manifest_sha256 != registration.ontology.manifest_sha256
            or output.projection_manifest_sha256 != projection.manifest_sha256
        ):
            raise ValueError("raw runtime output changed a preregistered source binding")
        projection.validate_against(registration.ontology)
        for raw_step, source_step in zip(output.steps, source.steps, strict=True):
            _validate_runtime_step_against_public_contract(
                raw_step,
                ontology=registration.ontology,
                projection=projection,
            )
            if (
                raw_step.step_index != source_step.step_index
                or raw_step.canonical_input_state_sha256 != source_step.input_state_sha256
                or raw_step.canonical_output_state_sha256 != source_step.output_state_sha256
                or raw_step.readout.selected_runtime_action.runtime_action_id
                != source_step.runtime_action_id
                or raw_step.readout.information_set_sha256
                != registration.shared_information_set_sha256_by_step[raw_step.step_index]
                or raw_step.readout.decision_id
                != registration.shared_decision_id_by_step[raw_step.step_index]
            ):
                raise ValueError("live readout differs from canonical action/state trace")
        runtime = task.runtime_receipt
        if (
            runtime.run_id != output.run_id
            or runtime.run_manifest_content_sha256 != chain.run_manifest.content_sha256
            or runtime.canonical_verification_content_sha256
            != chain.canonical_verification.content_sha256
            or runtime.canonical_task_receipt_content_sha256
            != source.canonical_task_receipt_content_sha256
            or runtime.task_index != output.task_index
            or runtime.arm != output.arm
            or runtime.episode_id != output.episode_id
            or runtime.implementation_bundle_sha256 != output.implementation_bundle_sha256
            or runtime.runtime_engine_sha256 != output.runtime_engine_sha256
            or runtime.raw_output_artifact_sha256 != task.raw_output_artifact_sha256
            or runtime.raw_output_content_sha256 != task.raw_output_content_sha256
        ):
            raise ValueError("runtime receipt changed its raw artifact/source binding")
        _verify_signed_record(
            runtime,
            manifest=trust_manifest,
            expected_role=FormalRole.RUNTIME_READOUT_EXECUTOR,
            domain=RUNTIME_RECEIPT_DOMAIN,
            now_utc=now,
        )
        if runtime.process_started_at_utc < max(
            chain.run_manifest.issued_at_utc,
            chain.canonical_verification.issued_at_utc,
        ):
            raise ValueError("runtime execution predates preregistration or source verification")
        nonces.append(runtime.nonce)
        broker_hashes = tuple(row.content_sha256 for row in task.broker_receipts)
        for broker in task.broker_receipts:
            _verify_broker_against_step(broker, output=output, runtime_receipt=runtime)
            _verify_signed_record(
                broker,
                manifest=trust_manifest,
                expected_role=FormalRole.CAUSAL_BROKER,
                domain=BROKER_RECEIPT_DOMAIN,
                now_utc=now,
            )
            if not runtime.process_started_at_utc <= broker.events[0].observed_at_utc:
                raise ValueError("causal broker readout predates runtime start")
            if broker.events[-1].observed_at_utc > runtime.process_finished_at_utc:
                raise ValueError("causal broker consequence follows runtime finish")
            if broker.issued_at_utc < runtime.issued_at_utc:
                raise ValueError("causal broker receipt predates its runtime parent receipt")
            nonces.append(broker.nonce)
        if any(
            right.events[0].observed_at_utc <= left.events[-1].observed_at_utc
            for left, right in pairwise(task.broker_receipts)
        ):
            raise ValueError("causal broker step chronology overlaps or runs backward")
        for index, hop in enumerate(task.custody_hops):
            if (
                hop.run_id != output.run_id
                or hop.run_manifest_content_sha256 != chain.run_manifest.content_sha256
                or hop.task_index != output.task_index
                or hop.arm != output.arm
                or hop.episode_id != output.episode_id
                or hop.raw_output_artifact_sha256 != task.raw_output_artifact_sha256
                or hop.raw_output_content_sha256 != task.raw_output_content_sha256
                or hop.runtime_receipt_content_sha256 != runtime.content_sha256
                or hop.broker_receipt_content_sha256 != broker_hashes
            ):
                raise ValueError("custody hop changed its parent artifact evidence")
            role = FormalRole.INGEST_CUSTODIAN if index == 0 else FormalRole.ARCHIVE_CUSTODIAN
            _verify_signed_record(
                hop,
                manifest=trust_manifest,
                expected_role=role,
                domain=CUSTODY_RECEIPT_DOMAIN,
                now_utc=now,
            )
            nonces.append(hop.nonce)
        if task.custody_hops[0].issued_at_utc < max(
            runtime.issued_at_utc,
            *(broker.issued_at_utc for broker in task.broker_receipts),
        ):
            raise ValueError("ingest custody predates runtime or broker evidence")
        if task.custody_hops[1].issued_at_utc < task.custody_hops[0].issued_at_utc:
            raise ValueError("archive custody predates ingest custody")

    diagnostic = _derive_diagnostic_report(chain)
    diagnostic_hash = content_sha256(diagnostic)
    review = chain.review_receipt
    expected_outcome = "PASS" if diagnostic["diagnostic_typed_relations_passed"] else "FAIL"
    if (
        review.run_id != chain.run_manifest.run_id
        or review.run_manifest_content_sha256 != chain.run_manifest.content_sha256
        or review.canonical_verification_content_sha256
        != chain.canonical_verification.content_sha256
        or review.task_evidence_content_sha256 != tuple(task.content_sha256 for task in chain.tasks)
        or review.diagnostic_report_content_sha256 != diagnostic_hash
        or review.recomputed_outcome != expected_outcome
    ):
        raise ValueError("independent review differs from recomputed raw evidence")
    _verify_signed_record(
        review,
        manifest=trust_manifest,
        expected_role=FormalRole.INDEPENDENT_REVIEWER,
        domain=REVIEW_RECEIPT_DOMAIN,
        now_utc=now,
    )
    if review.issued_at_utc < max(task.custody_hops[1].issued_at_utc for task in chain.tasks):
        raise ValueError("independent review predates archive custody")
    nonces.append(review.nonce)
    replay_registry.consume_many(nonces, consumed_at_utc=now)
    return VerifiedRawChainCandidateV08(
        chain_content_sha256=chain.content_sha256,
        diagnostic_report=diagnostic,
        diagnostic_report_content_sha256=diagnostic_hash,
        typed_relations_passed=bool(diagnostic["diagnostic_typed_relations_passed"]),
        consumed_nonce_count=len(nonces),
    )


class CurrentGateBV08FormalStatus(ContractModel):
    gate_b_protocol: Literal["structure-two-comparator-typed-dual-gate-b@0.8"]
    raw_execution_protocol: Literal["structure-two-gate-b-v0.8-raw-formal-execution-chain@1.0"]
    trust_anchor_status: EnrollmentStatus
    replay_registry_status: EnrollmentStatus
    execution_status: ExecutionStatus
    raw_formal_execution_verified: Literal[False]
    formal_gate_b_passed: Literal[False]
    seven_operator_ablation_authorized: Literal[False]
    blockers: tuple[str, ...] = Field(min_length=1)


def current_gate_b_v0_8_formal_status() -> CurrentGateBV08FormalStatus:
    """Return the only official current status; it cannot accept caller evidence."""

    policy = load_raw_formal_chain_policy_v0_8()
    blockers: list[str] = []
    if policy.trust_anchor_status is not EnrollmentStatus.ENROLLED:
        blockers.append("independent_trust_anchors_not_enrolled")
    if policy.replay_registry_status is not EnrollmentStatus.ENROLLED:
        blockers.append("verifier_owned_persistent_replay_registry_not_enrolled")
    if policy.execution_status is not ExecutionStatus.EXECUTED:
        blockers.append("raw_formal_execution_not_registered")
    if not blockers:
        # A new policy/protocol revision must add the positive official verifier.
        # Keeping this explicit prevents an edited JSON file from silently
        # turning the current negative status function into an authority.
        blockers.append("positive_official_verifier_requires_new_policy_revision")
    return CurrentGateBV08FormalStatus(
        gate_b_protocol=GATE_B_PROTOCOL_ID,
        raw_execution_protocol=PROTOCOL_ID,
        trust_anchor_status=policy.trust_anchor_status,
        replay_registry_status=policy.replay_registry_status,
        execution_status=policy.execution_status,
        raw_formal_execution_verified=False,
        formal_gate_b_passed=False,
        seven_operator_ablation_authorized=False,
        blockers=tuple(blockers),
    )


__all__ = [
    "BROKER_RECEIPT_PROTOCOL_ID",
    "CANONICAL_VERIFICATION_PROTOCOL_ID",
    "CUSTODY_RECEIPT_PROTOCOL_ID",
    "DEFAULT_POLICY_PATH",
    "POLICY_PROTOCOL_ID",
    "PROTOCOL_ID",
    "RAW_OUTPUT_PROTOCOL_ID",
    "REVIEW_RECEIPT_PROTOCOL_ID",
    "RUNTIME_RECEIPT_PROTOCOL_ID",
    "TRUST_MANIFEST_PROTOCOL_ID",
    "CanonicalExecutionVerificationV08",
    "CanonicalStepBindingV08",
    "CanonicalTaskBindingV08",
    "CanonicalTaskPlanV08",
    "CausalBrokerEventV08",
    "CausalBrokerStepReceiptV08",
    "CausalEventKind",
    "CurrentGateBV08FormalStatus",
    "CustodyHopReceiptV08",
    "CustodyRole",
    "EnrollmentStatus",
    "EpisodeRegistrationV08",
    "ExecutionStatus",
    "FormalRole",
    "GateBV08RawFormalExecutionChain",
    "GateBV08RunManifest",
    "GateBV08TrustManifest",
    "IndependentReviewReceiptV08",
    "LoadedRawRuntimeArtifactV08",
    "PersistentReplayRegistryV08",
    "ProjectionRegistrationV08",
    "RawFormalChainPolicyV08",
    "RawRuntimeArmEpisodeOutputV08",
    "RawRuntimeStepV08",
    "RawTaskEvidenceV08",
    "RuntimeReadoutReceiptV08",
    "TrustAnchorV08",
    "VerifiedRawChainCandidateV08",
    "action_policy_trace_sha256_v0_8",
    "belief_trace_sha256_v0_8",
    "current_gate_b_v0_8_formal_status",
    "load_raw_formal_chain_policy_v0_8",
    "load_raw_runtime_artifact_v0_8",
    "sign_broker_receipt_v0_8",
    "sign_canonical_verification_v0_8",
    "sign_custody_hop_v0_8",
    "sign_review_receipt_v0_8",
    "sign_run_manifest_v0_8",
    "sign_runtime_receipt_v0_8",
    "sign_trust_manifest_v0_8",
    "verify_policy_bound_trust_manifest_v0_8",
    "verify_raw_chain_candidate_v0_8",
]
