"""Fail-closed receipt DAG for the Structure Two seven-operator ablation.

This module is the *only* positive authorization surface for a trusted
seven-operator ablation.  Existing task reports and local diagnostic binding
objects are inputs to independent evidence production, never authorization
tokens themselves.

The formal chain is deliberately expensive to fake:

* every dependency has a different typed receipt and an independently
  enrolled Ed25519 trust anchor;
* the receipt signs source/config/spec/result hashes, its exact parent receipt
  hashes, a run id, timestamps, a freshness window, a nonce, and an explicit
  custody chain;
* a verifier-owned replay registry consumes each nonce only after every other
  check succeeds;
* Task 12 metrics and gates are recomputed from the raw MH proposal trace;
* P5 is a stage diagnosis, including an explicit mixed-bottleneck outcome, and
  never exposes a generic ``passed`` field; and
* invalid, stale, replayed, substituted, or missing parents block every
  descendant and the final authorization.

The checked-in policy records that no trust-anchor manifest or complete formal
run set is currently enrolled, so its current authorization is necessarily
false.  This module does not run an ablation.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Literal, cast
from uuid import UUID

from pydantic import Field, model_validator

from cpswm.contracts.base import ContractModel, PositiveInt, Probability
from cpswm.system.attestation import (
    Attestation,
    AttestationError,
    Ed25519AttestationSigner,
    Ed25519AttestationVerifier,
    attested_payload,
)
from cpswm.system.evaluation_operations.structure_two_binding_resolution_protocols import (
    BindingResolutionExecutionTrace,
    BindingResolutionProtocol,
    BindingResolutionResult,
    CiavActionBudgetProtocol,
    ConsolidationThresholdsProtocol,
    ExactEnumerationFalsifierProtocol,
    NeuralProposerArchitectureProtocol,
    OpenBinding,
    TrainingScheduleProtocol,
    recompute_binding_resolution,
)
from cpswm.system.evaluation_operations.structure_two_selected_method import (
    UnresolvedMethodBinding,
)
from cpswm.system.reproducibility import content_sha256

SCHEMA_VERSION = "1.0.0"
AUTHORIZATION_PROTOCOL_ID = "structure-two-trusted-seven-operator-ablation-authorization@1.1"
TRUST_ANCHOR_MANIFEST_PROTOCOL_ID = "structure-two-receipt-trust-anchor-manifest@1.0"
TRUST_ANCHOR_MANIFEST_DOMAIN = "cpswm.structure_two.receipt_trust_anchor_manifest.v1"
FORMAL_RECEIPT_DOMAIN_PREFIX = "cpswm.structure_two.formal_receipt.v1"
CUSTODY_HOP_DOMAIN_PREFIX = "cpswm.structure_two.custody_hop.v1"
AUTHORIZATION_DOMAIN = "cpswm.structure_two.seven_operator_authorization.v1"
SEVEN_OPERATOR_IDENTITY = "ORRER_CHEH"
SEVEN_OPERATOR_COMPONENT_IDENTITIES = (
    "OPCEU",
    "ORRER_CHEH",
    "PCHMP",
    "CF-BOCPD",
    "RGRC",
    "CCRR",
    "CIAV",
)
DEFAULT_POLICY_PATH = (
    Path(__file__).resolve().parents[4] / "configs/project_two_experiments/"
    "structure_two_trusted_seven_operator_ablation_authorization_v1_1.json"
)

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
FiniteNonNegativeFloat = Annotated[float, Field(ge=0.0, allow_inf_nan=False)]


class ReceiptKind(StrEnum):
    GATE_B_V0_8 = "GATE_B_V0_8"
    TASK_7 = "TASK_7"
    TASK_8 = "TASK_8"
    TASK_9 = "TASK_9"
    TASK_10 = "TASK_10"
    TASK_11 = "TASK_11"
    TASK_12 = "TASK_12"
    TASK_13 = "TASK_13"
    PROPOSAL_P5 = "PROPOSAL_P5"
    NEURAL_PROPOSER_ARCHITECTURE = "NEURAL_PROPOSER_ARCHITECTURE"
    TRAINING_SCHEDULE = "TRAINING_SCHEDULE"
    CONSOLIDATION_THRESHOLDS = "CONSOLIDATION_THRESHOLDS"
    CIAV_ACTION_BUDGET = "CIAV_ACTION_BUDGET"
    EXACT_ENUMERATION_FALSIFIER = "EXACT_ENUMERATION_FALSIFIER"
    AUDIT_ROUND_1 = "AUDIT_ROUND_1"
    AUDIT_ROUND_2 = "AUDIT_ROUND_2"
    AUTHORIZATION = "TRUSTED_SEVEN_OPERATOR_ABLATION_AUTHORIZATION"


class CustodyRole(StrEnum):
    PRODUCER = "producer"
    EVIDENCE_CUSTODIAN = "evidence_custodian"
    INDEPENDENT_VERIFIER = "independent_verifier"


DEPENDENCY_ORDER = (
    ReceiptKind.GATE_B_V0_8,
    ReceiptKind.TASK_7,
    ReceiptKind.TASK_8,
    ReceiptKind.TASK_9,
    ReceiptKind.TASK_10,
    ReceiptKind.TASK_11,
    ReceiptKind.TASK_12,
    ReceiptKind.TASK_13,
    ReceiptKind.PROPOSAL_P5,
    ReceiptKind.NEURAL_PROPOSER_ARCHITECTURE,
    ReceiptKind.TRAINING_SCHEDULE,
    ReceiptKind.CONSOLIDATION_THRESHOLDS,
    ReceiptKind.CIAV_ACTION_BUDGET,
    ReceiptKind.EXACT_ENUMERATION_FALSIFIER,
    ReceiptKind.AUDIT_ROUND_1,
    ReceiptKind.AUDIT_ROUND_2,
)

EXPECTED_PROTOCOL_IDS: dict[ReceiptKind, str] = {
    ReceiptKind.GATE_B_V0_8: "structure-two-comparator-typed-dual-gate-b@0.8",
    ReceiptKind.TASK_7: "structure-two-windowed-late-correction@0.4",
    ReceiptKind.TASK_8: "structure-two-relative-probability-joint-coupling@0.4",
    ReceiptKind.TASK_9: "structure-two-task9-four-coupling-protocol@1.1",
    ReceiptKind.TASK_10: "structure-two-backbone-particle-budget-task-10@0.1",
    ReceiptKind.TASK_11: "structure-two-backbone-resampling-task-11@0.1",
    ReceiptKind.TASK_12: "structure-two-backbone-rejuvenation-task-12@0.2",
    ReceiptKind.TASK_13: "structure-two-backbone-differentiability-task-13@0.1",
    ReceiptKind.PROPOSAL_P5: "structure-two-backbone-proposal-headroom-p5@0.2",
    ReceiptKind.NEURAL_PROPOSER_ARCHITECTURE: (
        "structure-two-neural-proposer-architecture-resolution@0.1"
    ),
    ReceiptKind.TRAINING_SCHEDULE: "structure-two-training-schedule-resolution@0.1",
    ReceiptKind.CONSOLIDATION_THRESHOLDS: ("structure-two-consolidation-thresholds-resolution@0.1"),
    ReceiptKind.CIAV_ACTION_BUDGET: "structure-two-ciav-action-budget-resolution@0.1",
    ReceiptKind.EXACT_ENUMERATION_FALSIFIER: (
        "structure-two-exact-enumeration-falsifier-resolution@0.1"
    ),
    ReceiptKind.AUDIT_ROUND_1: "structure-two-backbone-p0-adversarial-audit-round-1@1.1",
    ReceiptKind.AUDIT_ROUND_2: "structure-two-backbone-p0-adversarial-audit-round-2@1.1",
    ReceiptKind.AUTHORIZATION: AUTHORIZATION_PROTOCOL_ID,
}

EXPECTED_PARENTS: dict[ReceiptKind, tuple[ReceiptKind, ...]] = {
    ReceiptKind.GATE_B_V0_8: (),
    ReceiptKind.TASK_7: (),
    ReceiptKind.TASK_8: (),
    ReceiptKind.TASK_9: (),
    ReceiptKind.TASK_10: (),
    ReceiptKind.TASK_11: (ReceiptKind.TASK_10,),
    ReceiptKind.TASK_12: (ReceiptKind.TASK_10, ReceiptKind.TASK_11),
    ReceiptKind.TASK_13: (
        ReceiptKind.TASK_10,
        ReceiptKind.TASK_11,
        ReceiptKind.TASK_12,
    ),
    ReceiptKind.PROPOSAL_P5: (
        ReceiptKind.TASK_10,
        ReceiptKind.TASK_11,
        ReceiptKind.TASK_12,
    ),
    ReceiptKind.NEURAL_PROPOSER_ARCHITECTURE: (
        ReceiptKind.TASK_9,
        ReceiptKind.TASK_10,
        ReceiptKind.TASK_11,
        ReceiptKind.TASK_12,
        ReceiptKind.TASK_13,
        ReceiptKind.PROPOSAL_P5,
    ),
    ReceiptKind.TRAINING_SCHEDULE: (
        ReceiptKind.TASK_9,
        ReceiptKind.TASK_10,
        ReceiptKind.TASK_11,
        ReceiptKind.TASK_12,
        ReceiptKind.TASK_13,
        ReceiptKind.NEURAL_PROPOSER_ARCHITECTURE,
    ),
    ReceiptKind.CONSOLIDATION_THRESHOLDS: (
        ReceiptKind.TASK_9,
        ReceiptKind.TASK_10,
        ReceiptKind.TASK_11,
        ReceiptKind.TASK_12,
        ReceiptKind.TASK_13,
        ReceiptKind.TRAINING_SCHEDULE,
    ),
    ReceiptKind.CIAV_ACTION_BUDGET: (
        ReceiptKind.GATE_B_V0_8,
        ReceiptKind.TASK_8,
        ReceiptKind.TASK_9,
        ReceiptKind.NEURAL_PROPOSER_ARCHITECTURE,
        ReceiptKind.TRAINING_SCHEDULE,
    ),
    ReceiptKind.EXACT_ENUMERATION_FALSIFIER: (
        ReceiptKind.TASK_9,
        ReceiptKind.TASK_10,
        ReceiptKind.TASK_12,
        ReceiptKind.PROPOSAL_P5,
        ReceiptKind.NEURAL_PROPOSER_ARCHITECTURE,
    ),
    ReceiptKind.AUDIT_ROUND_1: DEPENDENCY_ORDER[:14],
    ReceiptKind.AUDIT_ROUND_2: (*DEPENDENCY_ORDER[:14], ReceiptKind.AUDIT_ROUND_1),
}

ROUND2_POSITIVE_CONSEQUENTIAL_SURFACES = (
    "gate_b_v0_8_comparator_diagnostic",
    "gate_b_v0_8_raw_chain_candidate",
    "gate_b_v0_8_current_formal_status",
    "gate_b_v0_8_authorization_dependency_receipt",
    "task_7_v0_4_registered_evidence",
    "task_7_v0_4_authorization_dependency_receipt",
    "task_8_v0_4_registered_evidence",
    "task_8_v0_4_authorization_dependency_receipt",
    "task_9_v1_1_formal_receipt",
    "task_10_formal_receipt",
    "task_11_formal_receipt",
    "task_12_formal_receipt",
    "task_13_formal_receipt",
    "proposal_p5_formal_receipt",
    "neural_proposer_architecture_resolution_receipt",
    "training_schedule_resolution_receipt",
    "consolidation_thresholds_resolution_receipt",
    "ciav_action_budget_resolution_receipt",
    "exact_enumeration_falsifier_resolution_receipt",
    "audit_round_1_receipt",
    "audit_round_2_receipt",
    "trusted_seven_operator_authorization_decision",
    "seven_operator_factorial_core_runner",
    "seven_operator_factorial_cli_runner",
)


def _require_utc(value: datetime, *, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return value.astimezone(UTC)


def _verifier_utc_now() -> datetime:
    """Read time inside the trusted verifier process, never from runner input."""

    return datetime.now(UTC)


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    output: dict[str, object] = {}
    for key, value in pairs:
        if key in output:
            raise ValueError(f"duplicate JSON key in authorization policy: {key}")
        output[key] = value
    return output


class TrustAnchorStatus(StrEnum):
    NOT_ENROLLED = "NOT_ENROLLED"
    ENROLLED = "ENROLLED"


class ReplayRegistryStatus(StrEnum):
    NOT_ENROLLED = "NOT_ENROLLED"
    VERIFIER_OWNED_PERSISTENT = "VERIFIER_OWNED_PERSISTENT"


class CustodyAttestationStatus(StrEnum):
    NOT_ENROLLED = "NOT_ENROLLED"
    PER_HOP_INDEPENDENT = "PER_HOP_INDEPENDENT"


class DependencyCommitmentStatus(StrEnum):
    NOT_ENROLLED = "NOT_ENROLLED"
    ENROLLED = "ENROLLED"
    POLICY_CONTENT_HASH_BOUND = "POLICY_CONTENT_HASH_BOUND"


class DependencyProtocolBinding(ContractModel):
    receipt_kind: ReceiptKind
    protocol_id: str = Field(min_length=1)
    required_parent_kinds: tuple[ReceiptKind, ...]
    freshness_window_seconds: PositiveInt = Field(le=86_400)
    config_spec_commitment_status: DependencyCommitmentStatus
    expected_config_content_sha256: Sha256 | None
    expected_spec_content_sha256: Sha256 | None

    @model_validator(mode="after")
    def _commitment_pair(self) -> DependencyProtocolBinding:
        pair = (self.expected_config_content_sha256, self.expected_spec_content_sha256)
        if self.receipt_kind is ReceiptKind.AUTHORIZATION:
            if self.config_spec_commitment_status is not (
                DependencyCommitmentStatus.POLICY_CONTENT_HASH_BOUND
            ) or pair != (None, None):
                raise ValueError("authorization commitment is its frozen policy content hash")
        elif self.config_spec_commitment_status is DependencyCommitmentStatus.NOT_ENROLLED:
            if pair != (None, None):
                raise ValueError("non-enrolled dependency commitments must be null")
        elif self.config_spec_commitment_status is not DependencyCommitmentStatus.ENROLLED or any(
            item is None for item in pair
        ):
            raise ValueError("enrolled dependency requires config and spec commitments")
        return self


class TrustedAblationAuthorizationPolicy(ContractModel):
    schema_version: Literal["1.0.0"]
    protocol_id: Literal["structure-two-trusted-seven-operator-ablation-authorization@1.1"]
    seven_operator_identity: Literal["ORRER_CHEH"]
    seven_operator_component_identities: tuple[
        Literal["OPCEU"],
        Literal["ORRER_CHEH"],
        Literal["PCHMP"],
        Literal["CF-BOCPD"],
        Literal["RGRC"],
        Literal["CCRR"],
        Literal["CIAV"],
    ]
    authenticated_enabled_noop_allowed: Literal[True]
    dependency_order: tuple[ReceiptKind, ...]
    dependency_bindings: tuple[DependencyProtocolBinding, ...]
    trust_anchor_status: TrustAnchorStatus
    trust_anchor_manifest_sha256: Sha256 | None
    replay_registry_status: ReplayRegistryStatus
    replay_registry_id: UUID | None
    replay_registry_enrollment_sha256: Sha256 | None
    custody_attestation_status: CustodyAttestationStatus
    current_authorization: Literal[False]
    claim_boundary: Literal[
        "No seven-operator ablation may run until every typed dependency and both "
        "adversarial-audit rounds verify in one fresh receipt DAG."
    ]

    @model_validator(mode="after")
    def _frozen_graph(self) -> TrustedAblationAuthorizationPolicy:
        if self.seven_operator_component_identities != SEVEN_OPERATOR_COMPONENT_IDENTITIES:
            raise ValueError("seven-operator component identity/order is frozen")
        if self.dependency_order != DEPENDENCY_ORDER:
            raise ValueError("authorization dependency order is frozen")
        by_kind = {item.receipt_kind: item for item in self.dependency_bindings}
        if tuple(by_kind) != (*DEPENDENCY_ORDER, ReceiptKind.AUTHORIZATION):
            raise ValueError("authorization policy must bind every dependency exactly once")
        for kind, expected_protocol in EXPECTED_PROTOCOL_IDS.items():
            binding = by_kind[kind]
            if binding.protocol_id != expected_protocol:
                raise ValueError(f"protocol binding drift for {kind.value}")
            expected_parents = EXPECTED_PARENTS.get(kind, DEPENDENCY_ORDER)
            if binding.required_parent_kinds != expected_parents:
                raise ValueError(f"parent graph drift for {kind.value}")
        if self.trust_anchor_status is TrustAnchorStatus.NOT_ENROLLED:
            if self.trust_anchor_manifest_sha256 is not None:
                raise ValueError("a non-enrolled policy cannot name a trust-anchor manifest")
        elif self.trust_anchor_manifest_sha256 is None:
            raise ValueError("an enrolled policy requires the frozen trust-anchor manifest hash")
        replay_registration = (
            self.replay_registry_id,
            self.replay_registry_enrollment_sha256,
        )
        if self.replay_registry_status is ReplayRegistryStatus.NOT_ENROLLED:
            if replay_registration != (None, None):
                raise ValueError("a non-enrolled replay registry cannot carry registration data")
        else:
            raise ValueError(
                "authorization v1.1 has no formal monotonic/WORM replay backend; "
                "positive enrollment requires a new protocol revision"
            )
        return self

    @classmethod
    def load(cls, path: Path) -> TrustedAblationAuthorizationPolicy:
        payload = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_json_keys
        )
        if not isinstance(payload, dict):
            raise ValueError("authorization policy must be a JSON object")
        return cls.model_validate(payload)


class TrustAnchorEntry(ContractModel):
    receipt_kind: ReceiptKind
    authority_id: str = Field(min_length=1)
    key_id: str = Field(min_length=1)
    public_key_base64: str = Field(min_length=1)
    public_key_sha256: Sha256
    enrolled_at_utc: datetime

    @model_validator(mode="after")
    def _valid_public_key(self) -> TrustAnchorEntry:
        _require_utc(self.enrolled_at_utc, label="trust-anchor enrollment")
        verifier = Ed25519AttestationVerifier.from_public_key_base64(
            key_id=self.key_id, public_key_base64=self.public_key_base64
        )
        if verifier.public_key_sha256 != self.public_key_sha256:
            raise ValueError("trust-anchor public key hash mismatch")
        return self


class CustodyTrustAnchorEntry(ContractModel):
    receipt_kind: ReceiptKind
    role: CustodyRole
    actor_id: str = Field(min_length=1)
    key_id: str = Field(min_length=1)
    public_key_base64: str = Field(min_length=1)
    public_key_sha256: Sha256
    enrolled_at_utc: datetime

    @model_validator(mode="after")
    def _valid_public_key(self) -> CustodyTrustAnchorEntry:
        _require_utc(self.enrolled_at_utc, label="custody-anchor enrollment")
        verifier = Ed25519AttestationVerifier.from_public_key_base64(
            key_id=self.key_id, public_key_base64=self.public_key_base64
        )
        if verifier.public_key_sha256 != self.public_key_sha256:
            raise ValueError("custody-anchor public key hash mismatch")
        return self


class ReceiptTrustAnchorManifest(ContractModel):
    schema_version: Literal["1.0.0"]
    protocol_id: Literal["structure-two-receipt-trust-anchor-manifest@1.0"]
    registry_id: UUID
    issued_at_utc: datetime
    registry_authority_id: str = Field(min_length=1)
    registry_authority_key_id: str = Field(min_length=1)
    registry_authority_public_key_sha256: Sha256
    entries: tuple[TrustAnchorEntry, ...] = Field(min_length=1)
    custody_entries: tuple[CustodyTrustAnchorEntry, ...] = Field(min_length=1)
    attestation: Attestation | None = None

    @model_validator(mode="after")
    def _unique_independent_anchors(self) -> ReceiptTrustAnchorManifest:
        _require_utc(self.issued_at_utc, label="trust-anchor manifest issue time")
        kinds = tuple(item.receipt_kind for item in self.entries)
        if kinds != tuple(ReceiptKind):
            raise ValueError("trust-anchor manifest must cover every receipt kind in order")
        key_ids = tuple(item.key_id for item in self.entries)
        public_hashes = tuple(item.public_key_sha256 for item in self.entries)
        authority_ids = tuple(item.authority_id for item in self.entries)
        if len(key_ids) != len(set(key_ids)) or len(public_hashes) != len(set(public_hashes)):
            raise ValueError("each formal receipt kind requires an independent signing key")
        if len(authority_ids) != len(set(authority_ids)):
            raise ValueError("each formal receipt kind requires an independent authority")
        if self.registry_authority_id in set(authority_ids):
            raise ValueError("registry authority must be independent from receipt authorities")
        if self.registry_authority_public_key_sha256 in set(public_hashes):
            raise ValueError("registry signing key must be independent from receipt keys")
        if any(item.enrolled_at_utc > self.issued_at_utc for item in self.entries):
            raise ValueError("trust anchors must be enrolled before the manifest is issued")

        expected_custody_pairs = tuple(
            (kind, role) for kind in DEPENDENCY_ORDER for role in CustodyRole
        )
        actual_custody_pairs = tuple(
            (item.receipt_kind, item.role) for item in self.custody_entries
        )
        if actual_custody_pairs != expected_custody_pairs:
            raise ValueError(
                "custody trust anchors must cover every dependency/role exactly once in order"
            )
        custody_actor_ids = tuple(item.actor_id for item in self.custody_entries)
        custody_key_ids = tuple(item.key_id for item in self.custody_entries)
        custody_public_hashes = tuple(item.public_key_sha256 for item in self.custody_entries)
        if len(custody_actor_ids) != len(set(custody_actor_ids)):
            raise ValueError("every custody role requires an independent registered actor")
        if len(custody_key_ids) != len(set(custody_key_ids)) or len(custody_public_hashes) != len(
            set(custody_public_hashes)
        ):
            raise ValueError("every custody role requires an independent registered signing key")
        by_kind = {item.receipt_kind: item for item in self.entries}
        custody_by_pair = {(item.receipt_kind, item.role): item for item in self.custody_entries}
        for kind in DEPENDENCY_ORDER:
            receipt_anchor = by_kind[kind]
            verifier_anchor = custody_by_pair[(kind, CustodyRole.INDEPENDENT_VERIFIER)]
            if (
                receipt_anchor.authority_id,
                receipt_anchor.key_id,
                receipt_anchor.public_key_base64,
                receipt_anchor.public_key_sha256,
                receipt_anchor.enrolled_at_utc,
            ) != (
                verifier_anchor.actor_id,
                verifier_anchor.key_id,
                verifier_anchor.public_key_base64,
                verifier_anchor.public_key_sha256,
                verifier_anchor.enrolled_at_utc,
            ):
                raise ValueError("receipt verifier anchor must equal the final custody-hop anchor")
        if self.registry_authority_id in set(custody_actor_ids):
            raise ValueError("registry authority must be independent from custody actors")
        if self.registry_authority_public_key_sha256 in set(custody_public_hashes):
            raise ValueError("registry signing key must be independent from custody keys")
        if any(item.enrolled_at_utc > self.issued_at_utc for item in self.custody_entries):
            raise ValueError("custody anchors must be enrolled before the manifest is issued")
        authorization_anchor = by_kind[ReceiptKind.AUTHORIZATION]
        if authorization_anchor.authority_id in set(custody_actor_ids):
            raise ValueError("authorization authority must be independent from custody actors")
        if authorization_anchor.public_key_sha256 in set(custody_public_hashes):
            raise ValueError("authorization key must be independent from custody keys")
        return self


def trust_anchor_manifest_content_sha256(manifest: ReceiptTrustAnchorManifest) -> str:
    return content_sha256(attested_payload(manifest))


def issue_trust_anchor_manifest(
    unsigned: ReceiptTrustAnchorManifest,
    *,
    registry_authority: Ed25519AttestationSigner,
) -> ReceiptTrustAnchorManifest:
    """Sign a complete trust-anchor registry with a separate root authority."""

    unsigned = ReceiptTrustAnchorManifest.model_validate(unsigned.model_dump(mode="python"))
    if unsigned.attestation is not None:
        raise ValueError("trust-anchor manifest is already signed")
    verifier = registry_authority.verifier()
    expected = (
        unsigned.registry_authority_key_id,
        unsigned.registry_authority_public_key_sha256,
    )
    actual = (verifier.key_id, verifier.public_key_sha256)
    if actual != expected:
        raise ValueError("registry authority does not match the frozen manifest identity")
    return unsigned.model_copy(
        update={
            "attestation": registry_authority.sign(
                TRUST_ANCHOR_MANIFEST_DOMAIN, attested_payload(unsigned)
            )
        }
    )


def verify_trust_anchor_manifest(
    manifest: ReceiptTrustAnchorManifest,
    *,
    registry_authority: Ed25519AttestationVerifier,
    expected_manifest_sha256: str,
    verification_time_utc: datetime,
) -> ReceiptTrustAnchorManifest:
    """Verify registry authenticity before any contained key is trusted."""

    manifest = ReceiptTrustAnchorManifest.model_validate(manifest.model_dump(mode="python"))
    now = _require_utc(verification_time_utc, label="manifest verification time")
    if manifest.issued_at_utc > now:
        raise ValueError("trust-anchor manifest is from the verifier's future")
    if trust_anchor_manifest_content_sha256(manifest) != expected_manifest_sha256:
        raise ValueError("trust-anchor manifest hash is not the preregistered hash")
    if (
        manifest.registry_authority_key_id,
        manifest.registry_authority_public_key_sha256,
    ) != (registry_authority.key_id, registry_authority.public_key_sha256):
        raise ValueError("trust-anchor manifest root identity mismatch")
    registry_authority.verify(
        TRUST_ANCHOR_MANIFEST_DOMAIN,
        attested_payload(manifest),
        manifest.attestation,
    )
    return manifest


class CustodyHop(ContractModel):
    sequence: int = Field(ge=0)
    actor_id: str = Field(min_length=1)
    actor_key_id: str = Field(min_length=1)
    actor_public_key_sha256: Sha256
    role: CustodyRole
    received_artifact_sha256: Sha256
    released_artifact_sha256: Sha256
    received_at_utc: datetime
    released_at_utc: datetime
    attestation: Attestation | None = None

    @model_validator(mode="after")
    def _ordered_time(self) -> CustodyHop:
        received = _require_utc(self.received_at_utc, label="custody receive time")
        released = _require_utc(self.released_at_utc, label="custody release time")
        if released < received:
            raise ValueError("custody release precedes receipt")
        return self


def _custody_hop_payload(
    hop: CustodyHop,
    *,
    receipt_kind: ReceiptKind,
    receipt_id: UUID,
    run_id: UUID,
    receipt_nonce: UUID,
) -> dict[str, Any]:
    return {
        "receipt_kind": receipt_kind,
        "receipt_id": receipt_id,
        "run_id": run_id,
        "receipt_nonce": receipt_nonce,
        "hop": attested_payload(hop),
    }


def issue_custody_hop(
    unsigned: CustodyHop,
    *,
    receipt_kind: ReceiptKind,
    receipt_id: UUID,
    run_id: UUID,
    receipt_nonce: UUID,
    actor: Ed25519AttestationSigner,
) -> CustodyHop:
    """Sign one custody transfer with that hop's independently enrolled key."""

    unsigned = CustodyHop.model_validate(unsigned.model_dump(mode="python"))
    if unsigned.attestation is not None:
        raise ValueError("custody hop is already signed")
    verifier = actor.verifier()
    if (unsigned.actor_key_id, unsigned.actor_public_key_sha256) != (
        verifier.key_id,
        verifier.public_key_sha256,
    ):
        raise ValueError("custody-hop signer identity mismatch")
    domain = f"{CUSTODY_HOP_DOMAIN_PREFIX}:{receipt_kind.value}:{unsigned.sequence}"
    payload = _custody_hop_payload(
        unsigned,
        receipt_kind=receipt_kind,
        receipt_id=receipt_id,
        run_id=run_id,
        receipt_nonce=receipt_nonce,
    )
    return unsigned.model_copy(update={"attestation": actor.sign(domain, payload)})


class ParentReceiptRef(ContractModel):
    receipt_kind: ReceiptKind
    receipt_id: UUID
    receipt_content_sha256: Sha256


class FormalReceiptBase(ContractModel):
    schema_version: Literal["1.0.0"]
    receipt_kind: ReceiptKind
    protocol_id: str = Field(min_length=1)
    receipt_id: UUID
    run_id: UUID
    seven_operator_identity: Literal["ORRER_CHEH"]
    parent_receipts: tuple[ParentReceiptRef, ...]
    source_bundle_sha256: Sha256
    config_content_sha256: Sha256
    spec_content_sha256: Sha256
    result_content_sha256: Sha256
    producer_id: str = Field(min_length=1)
    independent_verifier_id: str = Field(min_length=1)
    issued_at_utc: datetime
    verified_at_utc: datetime
    freshness_window_seconds: PositiveInt = Field(le=86_400)
    expires_at_utc: datetime
    custody_chain: tuple[CustodyHop, ...] = Field(min_length=3)
    nonce: UUID
    replay_registry_id: UUID
    trust_anchor_manifest_sha256: Sha256
    signer_key_id: str = Field(min_length=1)
    signer_public_key_sha256: Sha256
    attestation: Attestation | None = None

    @model_validator(mode="after")
    def _common_integrity(self) -> FormalReceiptBase:
        issued = _require_utc(self.issued_at_utc, label="receipt issue time")
        verified = _require_utc(self.verified_at_utc, label="receipt verified time")
        expires = _require_utc(self.expires_at_utc, label="receipt expiry time")
        if verified < issued:
            raise ValueError("receipt verification precedes issuance")
        if expires != issued + timedelta(seconds=self.freshness_window_seconds):
            raise ValueError("receipt expiry must equal issue time plus the freshness window")
        if verified > expires:
            raise ValueError("receipt was already stale when verified")
        if self.producer_id == self.independent_verifier_id:
            raise ValueError("receipt producer and independent verifier must differ")
        roles = tuple(item.role for item in self.custody_chain)
        if roles[0] is not CustodyRole.PRODUCER:
            raise ValueError("custody chain must begin at the producer")
        if roles[-1] is not CustodyRole.INDEPENDENT_VERIFIER:
            raise ValueError("custody chain must end at the independent verifier")
        if CustodyRole.EVIDENCE_CUSTODIAN not in roles[1:-1]:
            raise ValueError("custody chain requires an intermediate evidence custodian")
        actors = tuple(item.actor_id for item in self.custody_chain)
        if actors[0] != self.producer_id or actors[-1] != self.independent_verifier_id:
            raise ValueError("custody endpoint actors do not match receipt identities")
        if len(actors) != len(set(actors)):
            raise ValueError("custody actors must be independent")
        actor_key_ids = tuple(item.actor_key_id for item in self.custody_chain)
        actor_public_hashes = tuple(item.actor_public_key_sha256 for item in self.custody_chain)
        if len(actor_key_ids) != len(set(actor_key_ids)) or len(actor_public_hashes) != len(
            set(actor_public_hashes)
        ):
            raise ValueError("custody roles must not reuse one signing key")
        if (
            self.custody_chain[-1].actor_key_id,
            self.custody_chain[-1].actor_public_key_sha256,
        ) != (self.signer_key_id, self.signer_public_key_sha256):
            raise ValueError("final custody key must be the receipt signing key")
        if tuple(item.sequence for item in self.custody_chain) != tuple(range(len(actors))):
            raise ValueError("custody sequence must be contiguous from zero")
        if self.custody_chain[0].received_artifact_sha256 != self.source_bundle_sha256:
            raise ValueError("custody chain does not begin at the signed source bundle")
        if self.custody_chain[-1].released_artifact_sha256 != self.result_content_sha256:
            raise ValueError("custody chain does not end at the signed result")
        for previous, following in zip(self.custody_chain, self.custody_chain[1:], strict=False):
            if previous.released_artifact_sha256 != following.received_artifact_sha256:
                raise ValueError("custody artifact hashes do not form a continuous chain")
            if previous.released_at_utc > following.received_at_utc:
                raise ValueError("custody timestamps are not monotone")
        if self.custody_chain[-1].released_at_utc > issued:
            raise ValueError("receipt was issued before custody completed")
        return self


class GateBV08Receipt(FormalReceiptBase):
    receipt_kind: Literal[ReceiptKind.GATE_B_V0_8]
    protocol_id: Literal["structure-two-comparator-typed-dual-gate-b@0.8"]
    raw_execution_protocol_id: Literal["structure-two-gate-b-v0.8-raw-formal-execution-chain@1.0"]
    raw_execution_policy_content_sha256: Sha256
    raw_execution_content_sha256: Sha256
    canonical_execution_verification_content_sha256: Sha256
    runtime_readout_bundle_content_sha256: Sha256
    causal_broker_bundle_content_sha256: Sha256
    independent_custody_bundle_content_sha256: Sha256
    replay_consumption_receipt_content_sha256: Sha256
    independent_review_receipt_content_sha256: Sha256
    exact_arm_episode_coverage_content_sha256: Sha256
    comparator_count: PositiveInt
    comparator_relations_frozen: Literal[True]
    causal_windows_frozen: Literal[True]
    exact_arm_episode_coverage_verified: Literal[True]
    canonical_runtime_action_projection_verified: Literal[True]
    predecision_belief_readout_verified: Literal[True]
    stepwise_causal_broker_verified: Literal[True]
    independent_custody_verified: Literal[True]
    freshness_and_replay_verified: Literal[True]
    independent_review_verified: Literal[True]
    raw_formal_execution_verified: Literal[True]
    formal_gate_b_passed: Literal[True]

    @model_validator(mode="after")
    def _bind_raw_formal_chain(self) -> GateBV08Receipt:
        expected = content_sha256(
            {
                "raw_execution_protocol_id": self.raw_execution_protocol_id,
                "raw_execution_policy_content_sha256": (self.raw_execution_policy_content_sha256),
                "raw_execution_content_sha256": self.raw_execution_content_sha256,
                "canonical_execution_verification_content_sha256": (
                    self.canonical_execution_verification_content_sha256
                ),
                "runtime_readout_bundle_content_sha256": (
                    self.runtime_readout_bundle_content_sha256
                ),
                "causal_broker_bundle_content_sha256": (self.causal_broker_bundle_content_sha256),
                "independent_custody_bundle_content_sha256": (
                    self.independent_custody_bundle_content_sha256
                ),
                "replay_consumption_receipt_content_sha256": (
                    self.replay_consumption_receipt_content_sha256
                ),
                "independent_review_receipt_content_sha256": (
                    self.independent_review_receipt_content_sha256
                ),
                "exact_arm_episode_coverage_content_sha256": (
                    self.exact_arm_episode_coverage_content_sha256
                ),
                "comparator_count": self.comparator_count,
                "comparator_relations_frozen": self.comparator_relations_frozen,
                "causal_windows_frozen": self.causal_windows_frozen,
                "exact_arm_episode_coverage_verified": (self.exact_arm_episode_coverage_verified),
                "canonical_runtime_action_projection_verified": (
                    self.canonical_runtime_action_projection_verified
                ),
                "predecision_belief_readout_verified": (self.predecision_belief_readout_verified),
                "stepwise_causal_broker_verified": self.stepwise_causal_broker_verified,
                "independent_custody_verified": self.independent_custody_verified,
                "freshness_and_replay_verified": self.freshness_and_replay_verified,
                "independent_review_verified": self.independent_review_verified,
                "raw_formal_execution_verified": self.raw_formal_execution_verified,
            }
        )
        if self.result_content_sha256 != expected:
            raise ValueError("Gate B result hash does not bind the raw formal execution chain")
        return self


class Task7Receipt(FormalReceiptBase):
    receipt_kind: Literal[ReceiptKind.TASK_7]
    protocol_id: Literal["structure-two-windowed-late-correction@0.4"]
    registered_execution_content_sha256: Sha256
    conditional_target_validation_content_sha256: Sha256
    exact_scenario_factor_matrix_content_sha256: Sha256
    exact_scenario_factor_cell_count: Literal[16]
    same_conditional_target_absolute_tolerance: float = Field(
        ge=1e-10, le=1e-10, allow_inf_nan=False
    )
    belief_axis_tv_threshold: float = Field(ge=0.1, le=0.1, allow_inf_nan=False)
    action_distribution_tv_threshold: float = Field(ge=0.1, le=0.1, allow_inf_nan=False)
    selected_action_must_match: Literal[True]
    same_conditional_target_verified: Literal[True]
    strict_o_window_verified: Literal[True]
    multi_axis_equivalence_verified: Literal[True]
    action_equivalence_verified: Literal[True]
    non_self_move_verified: Literal[True]
    multi_sweep_verified: Literal[True]
    long_suffix_cost_verified: Literal[True]
    adaptive_window_expansion_or_full_replay_fallback_implemented: Literal[True]
    fallback_path_verified_separately: Literal[True]
    registered_execution_used_fallback: Literal[False]
    terminal_responsible_actor_cached: Literal[True]
    contamination_gate_retained: Literal[True]
    contamination_not_expanded: Literal[True]
    threshold_relaxation_allowed: Literal[False]
    failed_execution_reports_fail: Literal[True]
    formal_task_7_passed: Literal[True]

    @model_validator(mode="after")
    def _bind_v04_window_contract(self) -> Task7Receipt:
        if (
            self.same_conditional_target_absolute_tolerance,
            self.belief_axis_tv_threshold,
            self.action_distribution_tv_threshold,
        ) != (1e-10, 0.1, 0.1):
            raise ValueError("Task 7 v0.4 tolerances are frozen")
        expected = content_sha256(
            {
                "registered_execution_content_sha256": (self.registered_execution_content_sha256),
                "conditional_target_validation_content_sha256": (
                    self.conditional_target_validation_content_sha256
                ),
                "exact_scenario_factor_matrix_content_sha256": (
                    self.exact_scenario_factor_matrix_content_sha256
                ),
                "exact_scenario_factor_cell_count": self.exact_scenario_factor_cell_count,
                "same_conditional_target_absolute_tolerance": (
                    self.same_conditional_target_absolute_tolerance
                ),
                "belief_axis_tv_threshold": self.belief_axis_tv_threshold,
                "action_distribution_tv_threshold": self.action_distribution_tv_threshold,
                "selected_action_must_match": self.selected_action_must_match,
                "same_conditional_target_verified": self.same_conditional_target_verified,
                "strict_o_window_verified": self.strict_o_window_verified,
                "multi_axis_equivalence_verified": self.multi_axis_equivalence_verified,
                "action_equivalence_verified": self.action_equivalence_verified,
                "non_self_move_verified": self.non_self_move_verified,
                "multi_sweep_verified": self.multi_sweep_verified,
                "long_suffix_cost_verified": self.long_suffix_cost_verified,
                "adaptive_window_expansion_or_full_replay_fallback_implemented": (
                    self.adaptive_window_expansion_or_full_replay_fallback_implemented
                ),
                "fallback_path_verified_separately": self.fallback_path_verified_separately,
                "registered_execution_used_fallback": self.registered_execution_used_fallback,
                "terminal_responsible_actor_cached": self.terminal_responsible_actor_cached,
                "contamination_gate_retained": self.contamination_gate_retained,
                "contamination_not_expanded": self.contamination_not_expanded,
                "threshold_relaxation_allowed": self.threshold_relaxation_allowed,
                "failed_execution_reports_fail": self.failed_execution_reports_fail,
            }
        )
        if self.result_content_sha256 != expected:
            raise ValueError("Task 7 result hash does not bind the complete v0.4 contract")
        return self


class Task8Receipt(FormalReceiptBase):
    receipt_kind: Literal[ReceiptKind.TASK_8]
    protocol_id: Literal["structure-two-relative-probability-joint-coupling@0.4"]
    historical_v0_3_status: Literal["FAILED_FOR_CURRENT_MATCHED_THREE_ARM_CLAIM"]
    exact_arm_order: tuple[Literal["joint"], Literal["factorized"], Literal["matched_two_stage"]]
    validation_selection_receipt_content_sha256: Sha256
    confirmatory_execution_content_sha256: Sha256
    exact_confirmatory_coverage_content_sha256: Sha256
    same_information_per_unit_verified: Literal[True]
    same_budget_per_arm_per_unit_verified: Literal[True]
    validation_only_independent_tuning_verified: Literal[True]
    selection_frozen_before_confirmatory_verified: Literal[True]
    validation_confirmatory_units_disjoint: Literal[True]
    exact_confirmatory_arm_by_unit_coverage_verified: Literal[True]
    confirmatory_unit_count: Literal[40]
    paired_estimand: Literal["matched_two_stage_cost - joint_cost"]
    paired_confidence_interval_method: Literal[
        "paired deterministic percentile bootstrap over seed-cluster means"
    ]
    paired_confidence: float = Field(ge=0.95, le=0.95, allow_inf_nan=False)
    paired_bootstrap_replicates: Literal[10000]
    paired_bootstrap_seed: Literal["task8-v0.4-ci-20260905"]
    strict_lower_bound_threshold: float = Field(ge=0.001, le=0.001, allow_inf_nan=False)
    paired_lower_confidence_bound: float = Field(allow_inf_nan=False)
    endpoint_preregistered_before_run: Literal[True]
    endpoint_consumes_h_plus_z_cross_c: Literal[True]
    thresholds_unchanged_after_run: Literal[True]
    action_and_utility_gate_passed: Literal[True]
    formal_task_8_passed: Literal[True]

    @model_validator(mode="after")
    def _bind_v04_matched_confirmatory_contract(self) -> Task8Receipt:
        if self.exact_arm_order != ("joint", "factorized", "matched_two_stage"):
            raise ValueError("Task 8 must retain the exact three-arm order")
        if (self.paired_confidence, self.strict_lower_bound_threshold) != (0.95, 0.001):
            raise ValueError("Task 8 confirmatory confidence and threshold are frozen")
        if self.paired_lower_confidence_bound <= self.strict_lower_bound_threshold:
            raise ValueError("Task 8 paired lower confidence bound misses its strict threshold")
        expected = content_sha256(
            {
                "historical_v0_3_status": self.historical_v0_3_status,
                "exact_arm_order": self.exact_arm_order,
                "validation_selection_receipt_content_sha256": (
                    self.validation_selection_receipt_content_sha256
                ),
                "confirmatory_execution_content_sha256": (
                    self.confirmatory_execution_content_sha256
                ),
                "exact_confirmatory_coverage_content_sha256": (
                    self.exact_confirmatory_coverage_content_sha256
                ),
                "same_information_per_unit_verified": (self.same_information_per_unit_verified),
                "same_budget_per_arm_per_unit_verified": (
                    self.same_budget_per_arm_per_unit_verified
                ),
                "validation_only_independent_tuning_verified": (
                    self.validation_only_independent_tuning_verified
                ),
                "selection_frozen_before_confirmatory_verified": (
                    self.selection_frozen_before_confirmatory_verified
                ),
                "validation_confirmatory_units_disjoint": (
                    self.validation_confirmatory_units_disjoint
                ),
                "exact_confirmatory_arm_by_unit_coverage_verified": (
                    self.exact_confirmatory_arm_by_unit_coverage_verified
                ),
                "confirmatory_unit_count": self.confirmatory_unit_count,
                "paired_estimand": self.paired_estimand,
                "paired_confidence_interval_method": self.paired_confidence_interval_method,
                "paired_confidence": self.paired_confidence,
                "paired_bootstrap_replicates": self.paired_bootstrap_replicates,
                "paired_bootstrap_seed": self.paired_bootstrap_seed,
                "strict_lower_bound_threshold": self.strict_lower_bound_threshold,
                "paired_lower_confidence_bound": self.paired_lower_confidence_bound,
                "endpoint_preregistered_before_run": self.endpoint_preregistered_before_run,
                "endpoint_consumes_h_plus_z_cross_c": (self.endpoint_consumes_h_plus_z_cross_c),
                "thresholds_unchanged_after_run": self.thresholds_unchanged_after_run,
                "action_and_utility_gate_passed": self.action_and_utility_gate_passed,
            }
        )
        if self.result_content_sha256 != expected:
            raise ValueError("Task 8 result hash does not bind the complete v0.4 contract")
        return self


class Task9Receipt(FormalReceiptBase):
    receipt_kind: Literal[ReceiptKind.TASK_9]
    protocol_id: Literal["structure-two-task9-four-coupling-protocol@1.1"]
    selected_method_identity: Literal["ORRER_CHEH"]
    selected_method_receipt_content_sha256: Sha256
    operator_identity_order: tuple[
        Literal["OPCEU"],
        Literal["ORRER_CHEH"],
        Literal["PCHMP"],
        Literal["CF-BOCPD"],
        Literal["RGRC"],
        Literal["CCRR"],
        Literal["CIAV"],
    ]
    implementation_manifest_id: Literal["structure-two-task9-operator-implementations@1.1"]
    implementation_manifest_content_sha256: Sha256
    formal_execution_content_sha256: Sha256
    operator_execution_receipts_content_sha256: Sha256
    exact_factorial_coverage_content_sha256: Sha256
    independent_review_receipt_content_sha256: Sha256
    exact_four_couplings_verified: Literal[True]
    selected_method_receipt_verified: Literal[True]
    authenticated_enabled_noop_allowed: Literal[True]
    authenticated_enabled_noop_receipts_verified: Literal[True]
    freshness_replay_and_custody_verified: Literal[True]
    formal_task_9_passed: Literal[True]

    @model_validator(mode="after")
    def _frozen_operator_identities(self) -> Task9Receipt:
        if self.operator_identity_order != SEVEN_OPERATOR_COMPONENT_IDENTITIES:
            raise ValueError("Task 9 seven-operator identity/order is frozen")
        expected = content_sha256(
            {
                "selected_method_identity": self.selected_method_identity,
                "selected_method_receipt_content_sha256": (
                    self.selected_method_receipt_content_sha256
                ),
                "operator_identity_order": self.operator_identity_order,
                "implementation_manifest_id": self.implementation_manifest_id,
                "implementation_manifest_content_sha256": (
                    self.implementation_manifest_content_sha256
                ),
                "formal_execution_content_sha256": self.formal_execution_content_sha256,
                "operator_execution_receipts_content_sha256": (
                    self.operator_execution_receipts_content_sha256
                ),
                "exact_factorial_coverage_content_sha256": (
                    self.exact_factorial_coverage_content_sha256
                ),
                "independent_review_receipt_content_sha256": (
                    self.independent_review_receipt_content_sha256
                ),
                "exact_four_couplings_verified": self.exact_four_couplings_verified,
                "selected_method_receipt_verified": self.selected_method_receipt_verified,
                "authenticated_enabled_noop_allowed": (self.authenticated_enabled_noop_allowed),
                "authenticated_enabled_noop_receipts_verified": (
                    self.authenticated_enabled_noop_receipts_verified
                ),
                "freshness_replay_and_custody_verified": (
                    self.freshness_replay_and_custody_verified
                ),
            }
        )
        if self.result_content_sha256 != expected:
            raise ValueError("Task 9 result hash does not bind its formal execution chain")
        return self


class Task10Receipt(FormalReceiptBase):
    receipt_kind: Literal[ReceiptKind.TASK_10]
    protocol_id: Literal["structure-two-backbone-particle-budget-task-10@0.1"]
    selected_particle_budget: PositiveInt
    budget_curve_recomputed: Literal[True]
    formal_task_10_passed: Literal[True]


class Task11Receipt(FormalReceiptBase):
    receipt_kind: Literal[ReceiptKind.TASK_11]
    protocol_id: Literal["structure-two-backbone-resampling-task-11@0.1"]
    independent_definition_protocol_id: Literal["structure-two-backbone-resampling-task-11@0.1"]
    independent_definition_spec_content_sha256: Sha256
    raw_arm_matrix_content_sha256: Sha256
    selection_receipt_content_sha256: Sha256
    selected_resampling_policy: str = Field(min_length=1)
    exact_arm_by_unit_coverage_verified: Literal[True]
    validation_only_selection_verified: Literal[True]
    raw_arm_matrix_recomputed: Literal[True]
    formal_task_11_passed: Literal[True]

    @model_validator(mode="after")
    def _bind_formal_task11_execution(self) -> Task11Receipt:
        if self.independent_definition_spec_content_sha256 != self.spec_content_sha256:
            raise ValueError("Task 11 receipt must bind its independent definition spec")
        expected = content_sha256(
            {
                "raw_arm_matrix_content_sha256": self.raw_arm_matrix_content_sha256,
                "selection_receipt_content_sha256": self.selection_receipt_content_sha256,
                "selected_resampling_policy": self.selected_resampling_policy,
                "exact_arm_by_unit_coverage_verified": (self.exact_arm_by_unit_coverage_verified),
                "validation_only_selection_verified": self.validation_only_selection_verified,
                "raw_arm_matrix_recomputed": self.raw_arm_matrix_recomputed,
            }
        )
        if self.result_content_sha256 != expected:
            raise ValueError("Task 11 result hash does not bind its formal execution chain")
        return self


class Task12State(ContractModel):
    state_id: str = Field(min_length=1)
    h: str = Field(min_length=1)
    r: str = Field(min_length=1)
    i: str = Field(min_length=1)
    c: str = Field(min_length=1)
    z: str = Field(min_length=1)
    action_id: str = Field(min_length=1)
    utility: float = Field(allow_inf_nan=False)
    target_probability: Annotated[float, Field(gt=0.0, le=1.0, allow_inf_nan=False)]


class Task12ProposalProbability(ContractModel):
    destination_state_id: str = Field(min_length=1)
    probability: Probability


class Task12ProposalRow(ContractModel):
    source_state_id: str = Field(min_length=1)
    destinations: tuple[Task12ProposalProbability, ...] = Field(min_length=1)


class Task12ProposalEvent(ContractModel):
    event_index: int = Field(ge=0)
    source_state_id: str = Field(min_length=1)
    proposed_state_id: str = Field(min_length=1)
    uniform_draw: Probability
    accepted: bool
    resulting_state_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def _half_open_uniform(self) -> Task12ProposalEvent:
        if self.uniform_draw >= 1.0:
            raise ValueError("proposal uniform draw must lie in [0, 1)")
        return self


class ActionProbability(ContractModel):
    action_id: str = Field(min_length=1)
    probability: Probability


class Task12RawProposalTrace(ContractModel):
    trace_id: UUID
    selected_kernel: str = Field(min_length=1)
    states: tuple[Task12State, ...] = Field(min_length=2)
    proposal_rows: tuple[Task12ProposalRow, ...] = Field(min_length=2)
    initial_state_id: str = Field(min_length=1)
    events: tuple[Task12ProposalEvent, ...] = Field(min_length=4)
    burn_in_events: int = Field(ge=0)
    reference_action_distribution: tuple[ActionProbability, ...] = Field(min_length=1)
    reference_expected_utility: float = Field(allow_inf_nan=False)
    elementary_evaluations: PositiveInt

    @model_validator(mode="after")
    def _raw_chain_semantics(self) -> Task12RawProposalTrace:
        state_ids = tuple(item.state_id for item in self.states)
        if len(state_ids) != len(set(state_ids)):
            raise ValueError("Task 12 state ids must be unique")
        target_sum = sum(item.target_probability for item in self.states)
        if abs(target_sum - 1.0) > 1e-12:
            raise ValueError("Task 12 target probabilities must sum to one")
        if self.initial_state_id not in set(state_ids):
            raise ValueError("Task 12 initial state is outside the state space")
        if tuple(item.source_state_id for item in self.proposal_rows) != state_ids:
            raise ValueError("Task 12 proposal rows must cover states once in frozen order")
        for row in self.proposal_rows:
            destinations = tuple(item.destination_state_id for item in row.destinations)
            if destinations != state_ids:
                raise ValueError("each Task 12 proposal row must cover all states in order")
            if abs(sum(item.probability for item in row.destinations) - 1.0) > 1e-12:
                raise ValueError("each Task 12 proposal row must sum to one")
        actions = tuple(item.action_id for item in self.reference_action_distribution)
        if len(actions) != len(set(actions)):
            raise ValueError("Task 12 reference action ids must be unique")
        if set(actions) != {item.action_id for item in self.states}:
            raise ValueError("Task 12 reference actions must equal the state action support")
        if abs(sum(item.probability for item in self.reference_action_distribution) - 1.0) > 1e-12:
            raise ValueError("Task 12 reference action distribution must sum to one")
        expected_actions = {action: 0.0 for action in actions}
        for state in self.states:
            expected_actions[state.action_id] += state.target_probability
        supplied_actions = {
            item.action_id: item.probability for item in self.reference_action_distribution
        }
        if any(
            abs(supplied_actions[action] - expected_actions[action]) > 1e-12 for action in actions
        ):
            raise ValueError(
                "Task 12 reference action distribution must be aggregated from target mass"
            )
        expected_utility = sum(state.target_probability * state.utility for state in self.states)
        if abs(self.reference_expected_utility - expected_utility) > 1e-12:
            raise ValueError("Task 12 reference utility must be derived from target mass")
        if self.burn_in_events >= len(self.events):
            raise ValueError("Task 12 burn-in must leave post-burn-in samples")

        state_by_id = {item.state_id: item for item in self.states}
        q = {
            row.source_state_id: {
                item.destination_state_id: item.probability for item in row.destinations
            }
            for row in self.proposal_rows
        }
        current = self.initial_state_id
        for index, event in enumerate(self.events):
            if event.event_index != index:
                raise ValueError("Task 12 proposal event indices must be contiguous")
            if event.source_state_id != current:
                raise ValueError("Task 12 proposal chain source does not match prior result")
            forward = q[current][event.proposed_state_id]
            if forward <= 0.0:
                raise ValueError("observed Task 12 proposal has zero proposal probability")
            reverse = q[event.proposed_state_id][current]
            source_mass = state_by_id[current].target_probability
            destination_mass = state_by_id[event.proposed_state_id].target_probability
            acceptance = min(1.0, destination_mass * reverse / (source_mass * forward))
            expected_accepted = event.uniform_draw < acceptance
            expected_result = event.proposed_state_id if expected_accepted else current
            if (event.accepted, event.resulting_state_id) != (
                expected_accepted,
                expected_result,
            ):
                raise ValueError("Task 12 acceptance/result is not derived from the raw MH event")
            current = event.resulting_state_id
        if self.elementary_evaluations < len(self.events):
            raise ValueError("Task 12 elementary evaluations cannot undercount proposal events")
        return self


class Task12GateThresholds(ContractModel):
    max_detailed_balance_error: FiniteNonNegativeFloat
    max_stationarity_error: FiniteNonNegativeFloat
    min_acceptance_rate: Probability
    max_acceptance_rate: Probability
    min_effective_sample_size_per_evaluation: FiniteNonNegativeFloat
    max_action_total_variation: Probability
    max_absolute_expected_utility_difference: FiniteNonNegativeFloat

    @model_validator(mode="after")
    def _frozen_thresholds(self) -> Task12GateThresholds:
        values = (
            self.max_detailed_balance_error,
            self.max_stationarity_error,
            self.min_acceptance_rate,
            self.max_acceptance_rate,
            self.min_effective_sample_size_per_evaluation,
            self.max_action_total_variation,
            self.max_absolute_expected_utility_difference,
        )
        if values != (1e-9, 1e-9, 0.01, 1.0, 0.01, 0.05, 0.05):
            raise ValueError("Task 12 raw-trace thresholds are preregistered and frozen")
        return self


class Task12RecomputedGateResult(ContractModel):
    detailed_balance_error: FiniteNonNegativeFloat
    stationarity_error: FiniteNonNegativeFloat
    acceptance_rate: Probability
    effective_sample_size_per_evaluation: FiniteNonNegativeFloat
    action_total_variation: Probability
    absolute_expected_utility_difference: FiniteNonNegativeFloat
    touched_axes: tuple[Literal["H", "R", "I", "C", "Z"], ...]
    non_self_move_count: int = Field(ge=0)
    detailed_balance_passed: bool
    stationarity_passed: bool
    mixing_passed: bool
    action_equivalence_passed: bool
    multi_axis_passed: bool
    non_self_move_passed: bool

    @property
    def all_passed(self) -> bool:
        return all(
            (
                self.detailed_balance_passed,
                self.stationarity_passed,
                self.mixing_passed,
                self.action_equivalence_passed,
                self.multi_axis_passed,
                self.non_self_move_passed,
            )
        )


def _lag_one_effective_sample_size(values: Sequence[float]) -> float:
    count = len(values)
    if count < 2:
        return 0.0
    mean = sum(values) / count
    variance_sum = sum((item - mean) ** 2 for item in values)
    if variance_sum <= 0.0:
        return 0.0
    covariance = sum(
        (values[index] - mean) * (values[index + 1] - mean) for index in range(count - 1)
    )
    rho = max(-0.999999999999, min(0.999999999999, covariance / variance_sum))
    return max(0.0, min(float(count), count * (1.0 - rho) / (1.0 + rho)))


def recompute_task12_gate_result(
    trace: Task12RawProposalTrace,
    thresholds: Task12GateThresholds,
) -> Task12RecomputedGateResult:
    """Recompute every formal Task 12 gate from raw proposal events and matrices."""

    trace = Task12RawProposalTrace.model_validate(trace.model_dump(mode="python"))
    thresholds = Task12GateThresholds.model_validate(thresholds.model_dump(mode="python"))
    states = {item.state_id: item for item in trace.states}
    state_order = tuple(states)
    q = {
        row.source_state_id: {
            item.destination_state_id: item.probability for item in row.destinations
        }
        for row in trace.proposal_rows
    }
    kernel: dict[str, dict[str, float]] = {
        source: {destination: 0.0 for destination in state_order} for source in state_order
    }
    for source in state_order:
        off_diagonal_sum = 0.0
        for destination in state_order:
            if source == destination:
                continue
            forward = q[source][destination]
            if forward <= 0.0:
                continue
            reverse = q[destination][source]
            acceptance = min(
                1.0,
                states[destination].target_probability
                * reverse
                / (states[source].target_probability * forward),
            )
            value = forward * acceptance
            kernel[source][destination] = value
            off_diagonal_sum += value
        kernel[source][source] = 1.0 - off_diagonal_sum

    detailed_balance_error = max(
        abs(
            states[source].target_probability * kernel[source][destination]
            - states[destination].target_probability * kernel[destination][source]
        )
        for source in state_order
        for destination in state_order
    )
    stationarity_error = max(
        abs(
            sum(
                states[source].target_probability * kernel[source][destination]
                for source in state_order
            )
            - states[destination].target_probability
        )
        for destination in state_order
    )

    chain = [trace.initial_state_id, *(item.resulting_state_id for item in trace.events)]
    post_burn = chain[trace.burn_in_events :]
    ess_values = [
        _lag_one_effective_sample_size(
            [1.0 if observed == state_id else 0.0 for observed in post_burn]
        )
        for state_id in state_order
        if 0 < sum(observed == state_id for observed in post_burn) < len(post_burn)
    ]
    effective_sample_size = min(ess_values, default=0.0)
    ess_per_evaluation = effective_sample_size / trace.elementary_evaluations
    acceptance_rate = sum(item.accepted for item in trace.events) / len(trace.events)

    reference_actions = {
        item.action_id: item.probability for item in trace.reference_action_distribution
    }
    observed_counts = {action: 0 for action in reference_actions}
    for state_id in post_burn:
        observed_counts[states[state_id].action_id] += 1
    observed_actions = {action: count / len(post_burn) for action, count in observed_counts.items()}
    action_tv = 0.5 * sum(
        abs(observed_actions[action] - reference_actions[action]) for action in reference_actions
    )
    observed_utility = sum(states[state_id].utility for state_id in post_burn) / len(post_burn)
    utility_difference = abs(observed_utility - trace.reference_expected_utility)

    axes: set[Literal["H", "R", "I", "C", "Z"]] = set()
    non_self_moves = 0
    for event in trace.events:
        if event.resulting_state_id == event.source_state_id:
            continue
        non_self_moves += 1
        source_state = states[event.source_state_id]
        result_state = states[event.resulting_state_id]
        for label, before, after in (
            ("H", source_state.h, result_state.h),
            ("R", source_state.r, result_state.r),
            ("I", source_state.i, result_state.i),
            ("C", source_state.c, result_state.c),
            ("Z", source_state.z, result_state.z),
        ):
            if before != after:
                axes.add(cast(Literal["H", "R", "I", "C", "Z"], label))
    touched_axes = tuple(axis for axis in ("H", "R", "I", "C", "Z") if axis in axes)
    return Task12RecomputedGateResult(
        detailed_balance_error=detailed_balance_error,
        stationarity_error=stationarity_error,
        acceptance_rate=acceptance_rate,
        effective_sample_size_per_evaluation=ess_per_evaluation,
        action_total_variation=action_tv,
        absolute_expected_utility_difference=utility_difference,
        touched_axes=touched_axes,
        non_self_move_count=non_self_moves,
        detailed_balance_passed=(detailed_balance_error <= thresholds.max_detailed_balance_error),
        stationarity_passed=stationarity_error <= thresholds.max_stationarity_error,
        mixing_passed=(
            thresholds.min_acceptance_rate <= acceptance_rate <= thresholds.max_acceptance_rate
            and ess_per_evaluation >= thresholds.min_effective_sample_size_per_evaluation
        ),
        action_equivalence_passed=(
            action_tv <= thresholds.max_action_total_variation
            and utility_difference <= thresholds.max_absolute_expected_utility_difference
        ),
        multi_axis_passed=touched_axes == ("H", "R", "I", "C", "Z"),
        non_self_move_passed=non_self_moves > 0,
    )


class Task12Receipt(FormalReceiptBase):
    receipt_kind: Literal[ReceiptKind.TASK_12]
    protocol_id: Literal["structure-two-backbone-rejuvenation-task-12@0.2"]
    independent_definition_protocol_id: Literal["structure-two-backbone-rejuvenation-task-12@0.1"]
    independent_definition_spec_content_sha256: Sha256
    selected_rejuvenation_kernel: str = Field(min_length=1)
    raw_proposal_trace: Task12RawProposalTrace
    raw_proposal_trace_sha256: Sha256
    gate_thresholds: Task12GateThresholds
    recomputed_gate_result: Task12RecomputedGateResult
    formal_task_12_passed: Literal[True]

    @model_validator(mode="after")
    def _derive_from_raw_trace(self) -> Task12Receipt:
        if self.independent_definition_spec_content_sha256 != self.spec_content_sha256:
            raise ValueError("Task 12 receipt must bind its @0.1 independent definition spec")
        if self.selected_rejuvenation_kernel != self.raw_proposal_trace.selected_kernel:
            raise ValueError("Task 12 selected kernel differs from the raw proposal trace")
        if self.selected_rejuvenation_kernel in {
            "no_rejuvenation",
            "exact_conditional_gibbs_evaluator_only",
        }:
            raise ValueError("Task 12 formal receipt requires a deployable non-null kernel")
        if self.raw_proposal_trace_sha256 != content_sha256(self.raw_proposal_trace):
            raise ValueError("Task 12 raw proposal trace hash mismatch")
        recomputed = recompute_task12_gate_result(self.raw_proposal_trace, self.gate_thresholds)
        if self.recomputed_gate_result != recomputed:
            raise ValueError("Task 12 gate result was not recomputed from the raw proposal trace")
        if not recomputed.all_passed:
            raise ValueError("Task 12 raw proposal trace does not pass every frozen gate")
        expected_result = content_sha256(
            {
                "selected_rejuvenation_kernel": self.selected_rejuvenation_kernel,
                "raw_proposal_trace_sha256": self.raw_proposal_trace_sha256,
                "recomputed_gate_result": recomputed,
            }
        )
        if self.result_content_sha256 != expected_result:
            raise ValueError("Task 12 result hash does not bind the recomputed trace result")
        return self


class Task13Receipt(FormalReceiptBase):
    receipt_kind: Literal[ReceiptKind.TASK_13]
    protocol_id: Literal["structure-two-backbone-differentiability-task-13@0.1"]
    independent_definition_protocol_id: Literal[
        "structure-two-backbone-differentiability-task-13@0.1"
    ]
    independent_definition_spec_content_sha256: Sha256
    raw_gradient_arm_matrix_content_sha256: Sha256
    selection_receipt_content_sha256: Sha256
    selected_differentiability_strategy: str = Field(min_length=1)
    exact_arm_by_unit_coverage_verified: Literal[True]
    validation_only_selection_verified: Literal[True]
    raw_gradient_checks_recomputed: Literal[True]
    formal_task_13_passed: Literal[True]

    @model_validator(mode="after")
    def _bind_formal_task13_execution(self) -> Task13Receipt:
        if self.independent_definition_spec_content_sha256 != self.spec_content_sha256:
            raise ValueError("Task 13 receipt must bind its independent definition spec")
        expected = content_sha256(
            {
                "raw_gradient_arm_matrix_content_sha256": (
                    self.raw_gradient_arm_matrix_content_sha256
                ),
                "selection_receipt_content_sha256": self.selection_receipt_content_sha256,
                "selected_differentiability_strategy": (self.selected_differentiability_strategy),
                "exact_arm_by_unit_coverage_verified": (self.exact_arm_by_unit_coverage_verified),
                "validation_only_selection_verified": self.validation_only_selection_verified,
                "raw_gradient_checks_recomputed": self.raw_gradient_checks_recomputed,
            }
        )
        if self.result_content_sha256 != expected:
            raise ValueError("Task 13 result hash does not bind its formal execution chain")
        return self


class P5PipelineStage(StrEnum):
    RAW_CANDIDATE = "raw_candidate_generation"
    HARD_CONSTRAINT = "hard_constraint_survival"
    WEIGHTED_SUPPORT = "weighted_support"
    RESAMPLING = "resampling_survival"
    FINAL_CHAIN = "final_chain_support"


class P5BottleneckDiagnosis(StrEnum):
    NO_PROPOSAL_HEADROOM = "NO_PROPOSAL_HEADROOM"
    PROPOSAL_BOTTLENECK = "PROPOSAL_BOTTLENECK"
    DOWNSTREAM_BOTTLENECK = "DOWNSTREAM_WEIGHTING_OR_RESAMPLING_BOTTLENECK"
    MIXED_BOTTLENECK = "MIXED_PROPOSAL_AND_DOWNSTREAM_BOTTLENECK"
    READOUT_INCONCLUSIVE = "READOUT_INCONCLUSIVE"


class P5StageDecomposition(ContractModel):
    stage: P5PipelineStage
    best_deployable_recall: Probability
    best_oracle_recall: Probability
    headroom: Probability
    deployable_loss_from_previous_stage: Probability
    oracle_loss_from_previous_stage: Probability
    downstream_excess_loss: Probability

    @model_validator(mode="after")
    def _derived_values(self) -> P5StageDecomposition:
        if self.best_oracle_recall < self.best_deployable_recall:
            raise ValueError("P5 oracle recall must be an upper bound on deployable recall")
        expected_headroom = max(0.0, self.best_oracle_recall - self.best_deployable_recall)
        expected_excess = max(
            0.0,
            self.deployable_loss_from_previous_stage - self.oracle_loss_from_previous_stage,
        )
        if abs(self.headroom - expected_headroom) > 1e-12:
            raise ValueError("P5 stage headroom must be derived")
        if abs(self.downstream_excess_loss - expected_excess) > 1e-12:
            raise ValueError("P5 downstream excess loss must be derived")
        return self


def diagnose_p5_bottleneck(
    stages: Sequence[P5StageDecomposition],
    *,
    oracle_action_gain: float,
    recall_epsilon: float = 0.01,
    action_gain_epsilon: float = 0.0,
) -> P5BottleneckDiagnosis:
    """Return one exhaustive stage-aware diagnosis, including the mixed case."""

    if tuple(item.stage for item in stages) != tuple(P5PipelineStage):
        raise ValueError("P5 decomposition must contain all stages exactly once in order")
    if recall_epsilon != 0.01 or action_gain_epsilon != 0.0:
        raise ValueError("P5 diagnosis thresholds are frozen")
    final_headroom = stages[-1].headroom
    if final_headroom <= recall_epsilon:
        return P5BottleneckDiagnosis.NO_PROPOSAL_HEADROOM
    if oracle_action_gain <= action_gain_epsilon:
        return P5BottleneckDiagnosis.READOUT_INCONCLUSIVE
    proposal = stages[0].headroom > recall_epsilon
    downstream = any(item.downstream_excess_loss > recall_epsilon for item in stages[1:])
    if proposal and downstream:
        return P5BottleneckDiagnosis.MIXED_BOTTLENECK
    if proposal:
        return P5BottleneckDiagnosis.PROPOSAL_BOTTLENECK
    if downstream:
        return P5BottleneckDiagnosis.DOWNSTREAM_BOTTLENECK
    return P5BottleneckDiagnosis.READOUT_INCONCLUSIVE


class ProposalP5Receipt(FormalReceiptBase):
    receipt_kind: Literal[ReceiptKind.PROPOSAL_P5]
    protocol_id: Literal["structure-two-backbone-proposal-headroom-p5@0.2"]
    independent_definition_protocol_id: Literal["structure-two-backbone-proposal-headroom-p5@0.1"]
    independent_definition_spec_content_sha256: Sha256
    raw_arm_unit_stage_trace_content_sha256: Sha256
    exact_arm_unit_stage_coverage_verified: Literal[True]
    stage_decomposition: tuple[P5StageDecomposition, ...]
    oracle_action_gain: float = Field(allow_inf_nan=False)
    recall_headroom_epsilon: FiniteNonNegativeFloat
    action_gain_epsilon: FiniteNonNegativeFloat
    diagnosis: P5BottleneckDiagnosis
    completed_diagnostic: Literal[True]

    @model_validator(mode="after")
    def _recompute_diagnosis(self) -> ProposalP5Receipt:
        if self.independent_definition_spec_content_sha256 != self.spec_content_sha256:
            raise ValueError("P5 receipt must bind its @0.1 independent definition spec")
        recalls = tuple(
            (item.best_deployable_recall, item.best_oracle_recall)
            for item in self.stage_decomposition
        )
        for index, item in enumerate(self.stage_decomposition):
            expected_deployable_loss = (
                0.0 if index == 0 else max(0.0, recalls[index - 1][0] - recalls[index][0])
            )
            expected_oracle_loss = (
                0.0 if index == 0 else max(0.0, recalls[index - 1][1] - recalls[index][1])
            )
            if (
                abs(item.deployable_loss_from_previous_stage - expected_deployable_loss) > 1e-12
                or abs(item.oracle_loss_from_previous_stage - expected_oracle_loss) > 1e-12
            ):
                raise ValueError("P5 per-stage losses were not derived from adjacent recalls")
            if index > 0 and (
                recalls[index][0] > recalls[index - 1][0] + 1e-12
                or recalls[index][1] > recalls[index - 1][1] + 1e-12
            ):
                raise ValueError("P5 recall cannot increase after a support-removing stage")
        if (self.recall_headroom_epsilon, self.action_gain_epsilon) != (0.01, 0.0):
            raise ValueError("P5 receipt thresholds are preregistered and frozen")
        expected = diagnose_p5_bottleneck(
            self.stage_decomposition,
            oracle_action_gain=self.oracle_action_gain,
            recall_epsilon=self.recall_headroom_epsilon,
            action_gain_epsilon=self.action_gain_epsilon,
        )
        if self.diagnosis is not expected:
            raise ValueError("P5 diagnosis was not derived from the stage decomposition")
        expected_result = content_sha256(
            {
                "raw_arm_unit_stage_trace_content_sha256": (
                    self.raw_arm_unit_stage_trace_content_sha256
                ),
                "exact_arm_unit_stage_coverage_verified": (
                    self.exact_arm_unit_stage_coverage_verified
                ),
                "stage_decomposition": self.stage_decomposition,
                "oracle_action_gain": self.oracle_action_gain,
                "diagnosis": self.diagnosis,
            }
        )
        if self.result_content_sha256 != expected_result:
            raise ValueError("P5 result hash does not bind its stage diagnosis")
        return self


class BindingResolutionReceiptBase(FormalReceiptBase):
    """Shared signed envelope; concrete subclasses keep the binding type distinct."""

    selected_method_receipt_content_sha256: Sha256
    unresolved_bindings_at_protocol_freeze: tuple[UnresolvedMethodBinding, ...]
    resolution_protocol_content_sha256: Sha256
    raw_execution_trace: BindingResolutionExecutionTrace
    raw_execution_trace_sha256: Sha256
    recomputed_resolution: BindingResolutionResult
    formal_binding_resolved: Literal[True]

    def _verify_resolution_payload(
        self,
        protocol: BindingResolutionProtocol,
        *,
        expected_binding: OpenBinding,
    ) -> None:
        if self.unresolved_bindings_at_protocol_freeze != tuple(UnresolvedMethodBinding):
            raise ValueError(
                "binding receipt must retain the complete original unresolved-binding set"
            )
        if protocol.binding is not expected_binding:
            raise ValueError("binding receipt carries the wrong independently typed protocol")
        protocol_hash = content_sha256(protocol)
        if self.resolution_protocol_content_sha256 != protocol_hash:
            raise ValueError("binding receipt protocol content hash mismatch")
        if self.spec_content_sha256 != protocol_hash:
            raise ValueError("binding receipt spec hash must bind the independent protocol")
        if self.raw_execution_trace_sha256 != content_sha256(self.raw_execution_trace):
            raise ValueError("binding receipt raw execution trace hash mismatch")
        recomputed = recompute_binding_resolution(protocol, self.raw_execution_trace)
        if self.recomputed_resolution != recomputed:
            raise ValueError("binding resolution was not recomputed from the raw arm x unit trace")
        if not recomputed.all_confirmatory_gates_passed:
            raise ValueError("binding confirmatory gates did not all pass")
        expected_result = content_sha256(
            {
                "binding": expected_binding,
                "selected_method_receipt_content_sha256": (
                    self.selected_method_receipt_content_sha256
                ),
                "unresolved_bindings_at_protocol_freeze": (
                    self.unresolved_bindings_at_protocol_freeze
                ),
                "resolution_protocol_content_sha256": protocol_hash,
                "raw_execution_trace_sha256": self.raw_execution_trace_sha256,
                "recomputed_resolution": recomputed,
            }
        )
        if self.result_content_sha256 != expected_result:
            raise ValueError("binding result hash does not bind the recomputed resolution")


class NeuralProposerArchitectureReceipt(BindingResolutionReceiptBase):
    receipt_kind: Literal[ReceiptKind.NEURAL_PROPOSER_ARCHITECTURE]
    protocol_id: Literal["structure-two-neural-proposer-architecture-resolution@0.1"]
    resolution_protocol: NeuralProposerArchitectureProtocol

    @model_validator(mode="after")
    def _typed_resolution(self) -> NeuralProposerArchitectureReceipt:
        self._verify_resolution_payload(
            self.resolution_protocol,
            expected_binding=OpenBinding.NEURAL_PROPOSER_ARCHITECTURE,
        )
        return self


class TrainingScheduleReceipt(BindingResolutionReceiptBase):
    receipt_kind: Literal[ReceiptKind.TRAINING_SCHEDULE]
    protocol_id: Literal["structure-two-training-schedule-resolution@0.1"]
    resolution_protocol: TrainingScheduleProtocol

    @model_validator(mode="after")
    def _typed_resolution(self) -> TrainingScheduleReceipt:
        self._verify_resolution_payload(
            self.resolution_protocol,
            expected_binding=OpenBinding.TRAINING_SCHEDULE,
        )
        return self


class ConsolidationThresholdsReceipt(BindingResolutionReceiptBase):
    receipt_kind: Literal[ReceiptKind.CONSOLIDATION_THRESHOLDS]
    protocol_id: Literal["structure-two-consolidation-thresholds-resolution@0.1"]
    resolution_protocol: ConsolidationThresholdsProtocol

    @model_validator(mode="after")
    def _typed_resolution(self) -> ConsolidationThresholdsReceipt:
        self._verify_resolution_payload(
            self.resolution_protocol,
            expected_binding=OpenBinding.CONSOLIDATION_THRESHOLDS,
        )
        return self


class CiavActionBudgetReceipt(BindingResolutionReceiptBase):
    receipt_kind: Literal[ReceiptKind.CIAV_ACTION_BUDGET]
    protocol_id: Literal["structure-two-ciav-action-budget-resolution@0.1"]
    resolution_protocol: CiavActionBudgetProtocol

    @model_validator(mode="after")
    def _typed_resolution(self) -> CiavActionBudgetReceipt:
        self._verify_resolution_payload(
            self.resolution_protocol,
            expected_binding=OpenBinding.CIAV_ACTION_BUDGET,
        )
        return self


class ExactEnumerationFalsifierReceipt(BindingResolutionReceiptBase):
    receipt_kind: Literal[ReceiptKind.EXACT_ENUMERATION_FALSIFIER]
    protocol_id: Literal["structure-two-exact-enumeration-falsifier-resolution@0.1"]
    resolution_protocol: ExactEnumerationFalsifierProtocol

    @model_validator(mode="after")
    def _typed_resolution(self) -> ExactEnumerationFalsifierReceipt:
        self._verify_resolution_payload(
            self.resolution_protocol,
            expected_binding=OpenBinding.EXACT_ENUMERATION_FALSIFIER,
        )
        return self


class AuditRound1Receipt(FormalReceiptBase):
    receipt_kind: Literal[ReceiptKind.AUDIT_ROUND_1]
    protocol_id: Literal["structure-two-backbone-p0-adversarial-audit-round-1@1.1"]
    audit_round: Literal[1]
    scientific_counterexample_matrix_content_sha256: Sha256
    positive_consequential_output_inventory_content_sha256: Sha256
    scientific_counterexample_matrix_complete: Literal[True]
    every_positive_consequential_output_trust_chain_covered: Literal[True]
    every_positive_output_has_independent_falsifier: Literal[True]
    all_p0_surfaces_covered: Literal[True]

    @model_validator(mode="after")
    def _bind_round_one_semantics(self) -> AuditRound1Receipt:
        expected = content_sha256(
            {
                "audit_round": self.audit_round,
                "scientific_counterexample_matrix_content_sha256": (
                    self.scientific_counterexample_matrix_content_sha256
                ),
                "positive_consequential_output_inventory_content_sha256": (
                    self.positive_consequential_output_inventory_content_sha256
                ),
                "scientific_counterexample_matrix_complete": (
                    self.scientific_counterexample_matrix_complete
                ),
                "every_positive_consequential_output_trust_chain_covered": (
                    self.every_positive_consequential_output_trust_chain_covered
                ),
                "every_positive_output_has_independent_falsifier": (
                    self.every_positive_output_has_independent_falsifier
                ),
                "all_p0_surfaces_covered": self.all_p0_surfaces_covered,
            }
        )
        if self.result_content_sha256 != expected:
            raise ValueError("round-one result hash does not bind scientific/positive coverage")
        return self


class AuditRound2Receipt(FormalReceiptBase):
    receipt_kind: Literal[ReceiptKind.AUDIT_ROUND_2]
    protocol_id: Literal["structure-two-backbone-p0-adversarial-audit-round-2@1.1"]
    audit_round: Literal[2]
    independent_reviewer: Literal[True]
    attack_transcript_content_sha256: Sha256
    positive_consequential_surface_inventory_content_sha256: Sha256
    covered_positive_consequential_surface_ids: tuple[str, ...] = Field(min_length=1)
    forged_but_complete_rejected: Literal[True]
    cross_version_substitution_rejected: Literal[True]
    replay_rejected: Literal[True]
    missing_dependency_rejected: Literal[True]
    direct_runner_bypass_rejected_before_workload: Literal[True]
    trust_manifest_bound_to_checked_in_policy: Literal[True]
    trust_manifest_root_signature_verified: Literal[True]
    caller_backdated_verification_time_rejected: Literal[True]
    replay_registry_identity_replacement_rejected: Literal[True]
    same_inode_or_snapshot_rollback_not_claimed: Literal[True]
    monotonic_or_worm_formal_replay_backend_required: Literal[True]
    all_p0_surfaces_covered: Literal[True]

    @model_validator(mode="after")
    def _bind_round_two_semantics(self) -> AuditRound2Receipt:
        if self.covered_positive_consequential_surface_ids != (
            ROUND2_POSITIVE_CONSEQUENTIAL_SURFACES
        ):
            raise ValueError("round-two coverage does not enumerate every positive surface")
        expected = content_sha256(
            {
                "audit_round": self.audit_round,
                "independent_reviewer": self.independent_reviewer,
                "attack_transcript_content_sha256": self.attack_transcript_content_sha256,
                "positive_consequential_surface_inventory_content_sha256": (
                    self.positive_consequential_surface_inventory_content_sha256
                ),
                "covered_positive_consequential_surface_ids": (
                    self.covered_positive_consequential_surface_ids
                ),
                "forged_but_complete_rejected": self.forged_but_complete_rejected,
                "cross_version_substitution_rejected": (self.cross_version_substitution_rejected),
                "replay_rejected": self.replay_rejected,
                "missing_dependency_rejected": self.missing_dependency_rejected,
                "direct_runner_bypass_rejected_before_workload": (
                    self.direct_runner_bypass_rejected_before_workload
                ),
                "trust_manifest_bound_to_checked_in_policy": (
                    self.trust_manifest_bound_to_checked_in_policy
                ),
                "trust_manifest_root_signature_verified": (
                    self.trust_manifest_root_signature_verified
                ),
                "caller_backdated_verification_time_rejected": (
                    self.caller_backdated_verification_time_rejected
                ),
                "replay_registry_identity_replacement_rejected": (
                    self.replay_registry_identity_replacement_rejected
                ),
                "same_inode_or_snapshot_rollback_not_claimed": (
                    self.same_inode_or_snapshot_rollback_not_claimed
                ),
                "monotonic_or_worm_formal_replay_backend_required": (
                    self.monotonic_or_worm_formal_replay_backend_required
                ),
                "all_p0_surfaces_covered": self.all_p0_surfaces_covered,
            }
        )
        if self.result_content_sha256 != expected:
            raise ValueError("round-two result hash does not bind the required attack classes")
        return self


type FormalDependencyReceipt = (
    GateBV08Receipt
    | Task7Receipt
    | Task8Receipt
    | Task9Receipt
    | Task10Receipt
    | Task11Receipt
    | Task12Receipt
    | Task13Receipt
    | ProposalP5Receipt
    | NeuralProposerArchitectureReceipt
    | TrainingScheduleReceipt
    | ConsolidationThresholdsReceipt
    | CiavActionBudgetReceipt
    | ExactEnumerationFalsifierReceipt
    | AuditRound1Receipt
    | AuditRound2Receipt
)

RECEIPT_TYPE_BY_KIND: dict[ReceiptKind, type[FormalReceiptBase]] = {
    ReceiptKind.GATE_B_V0_8: GateBV08Receipt,
    ReceiptKind.TASK_7: Task7Receipt,
    ReceiptKind.TASK_8: Task8Receipt,
    ReceiptKind.TASK_9: Task9Receipt,
    ReceiptKind.TASK_10: Task10Receipt,
    ReceiptKind.TASK_11: Task11Receipt,
    ReceiptKind.TASK_12: Task12Receipt,
    ReceiptKind.TASK_13: Task13Receipt,
    ReceiptKind.PROPOSAL_P5: ProposalP5Receipt,
    ReceiptKind.NEURAL_PROPOSER_ARCHITECTURE: NeuralProposerArchitectureReceipt,
    ReceiptKind.TRAINING_SCHEDULE: TrainingScheduleReceipt,
    ReceiptKind.CONSOLIDATION_THRESHOLDS: ConsolidationThresholdsReceipt,
    ReceiptKind.CIAV_ACTION_BUDGET: CiavActionBudgetReceipt,
    ReceiptKind.EXACT_ENUMERATION_FALSIFIER: ExactEnumerationFalsifierReceipt,
    ReceiptKind.AUDIT_ROUND_1: AuditRound1Receipt,
    ReceiptKind.AUDIT_ROUND_2: AuditRound2Receipt,
}


def formal_receipt_content_sha256(receipt: FormalReceiptBase) -> str:
    return content_sha256(attested_payload(receipt))


def issue_formal_receipt[ReceiptT: FormalReceiptBase](
    unsigned: ReceiptT,
    *,
    independent_verifier: Ed25519AttestationSigner,
) -> ReceiptT:
    """Sign a typed receipt; trust-anchor enrollment is checked on verification."""

    receipt_type = type(unsigned)
    unsigned = receipt_type.model_validate(unsigned.model_dump(mode="python"))
    if unsigned.attestation is not None:
        raise ValueError("formal receipt is already signed")
    if any(hop.attestation is None for hop in unsigned.custody_chain):
        raise ValueError("every custody hop requires its own signature before receipt issuance")
    verifier = independent_verifier.verifier()
    if (unsigned.signer_key_id, unsigned.signer_public_key_sha256) != (
        verifier.key_id,
        verifier.public_key_sha256,
    ):
        raise ValueError("formal receipt signer identity mismatch")
    signed = unsigned.model_copy(
        update={
            "attestation": independent_verifier.sign(
                f"{FORMAL_RECEIPT_DOMAIN_PREFIX}:{unsigned.receipt_kind.value}",
                attested_payload(unsigned),
            )
        }
    )
    return signed


class ReceiptReplayRegistry:
    """Verifier-owned, in-memory one-time nonce registry.

    Production use must persist the same key tuple atomically.  The object is
    intentionally not serializable as evidence and offers no reset method.
    """

    def __init__(self, *, registry_id: UUID) -> None:
        self.registry_id = registry_id
        self._seen: dict[UUID, tuple[ReceiptKind, str]] = {}

    @property
    def formal_grade(self) -> bool:
        """An in-memory registry is diagnostic and cannot authorize a formal run."""

        return False

    @property
    def enrollment_receipt_sha256(self) -> None:
        return None

    def contains(self, kind: ReceiptKind, nonce: UUID) -> bool:
        del kind
        return nonce in self._seen

    def consume(self, kind: ReceiptKind, nonce: UUID, receipt_hash: str) -> None:
        if nonce in self._seen:
            raise ValueError(f"replayed nonce for {kind.value}")
        self._seen[nonce] = (kind, receipt_hash)


def _entry_by_kind(manifest: ReceiptTrustAnchorManifest, kind: ReceiptKind) -> TrustAnchorEntry:
    entries = {item.receipt_kind: item for item in manifest.entries}
    if kind not in entries:
        raise ValueError(f"trust-anchor manifest lacks {kind.value}")
    return entries[kind]


def _custody_entry_by_pair(
    manifest: ReceiptTrustAnchorManifest,
    kind: ReceiptKind,
    role: CustodyRole,
) -> CustodyTrustAnchorEntry:
    entries = {(item.receipt_kind, item.role): item for item in manifest.custody_entries}
    try:
        return entries[(kind, role)]
    except KeyError as exc:
        raise ValueError(f"custody trust-anchor manifest lacks {kind.value}/{role.value}") from exc


def verify_custody_chain(
    receipt: FormalReceiptBase,
    *,
    manifest: ReceiptTrustAnchorManifest,
) -> None:
    """Verify every custody hop against its separately registered actor/key."""

    for hop in receipt.custody_chain:
        anchor = _custody_entry_by_pair(manifest, receipt.receipt_kind, hop.role)
        if (
            hop.actor_id,
            hop.actor_key_id,
            hop.actor_public_key_sha256,
        ) != (anchor.actor_id, anchor.key_id, anchor.public_key_sha256):
            raise ValueError("custody hop does not match its registered role anchor")
        if anchor.enrolled_at_utc > hop.received_at_utc:
            raise ValueError("custody hop predates actor/key enrollment")
        verifier = Ed25519AttestationVerifier.from_public_key_base64(
            key_id=anchor.key_id,
            public_key_base64=anchor.public_key_base64,
        )
        verifier.verify(
            f"{CUSTODY_HOP_DOMAIN_PREFIX}:{receipt.receipt_kind.value}:{hop.sequence}",
            _custody_hop_payload(
                hop,
                receipt_kind=receipt.receipt_kind,
                receipt_id=receipt.receipt_id,
                run_id=receipt.run_id,
                receipt_nonce=receipt.nonce,
            ),
            hop.attestation,
        )


def verify_formal_receipt(
    receipt: FormalDependencyReceipt,
    *,
    policy: TrustedAblationAuthorizationPolicy,
    manifest: ReceiptTrustAnchorManifest,
    verified_parents: Mapping[ReceiptKind, FormalDependencyReceipt],
    expected_run_id: UUID,
    verification_time_utc: datetime,
    replay_registry: ReceiptReplayRegistry,
) -> FormalDependencyReceipt:
    """Verify type, graph, time, custody, trust anchor, signature, and replay."""

    raw_kind = receipt.receipt_kind
    if raw_kind not in RECEIPT_TYPE_BY_KIND:
        raise ValueError("authorization received an unsupported receipt kind")
    expected_type = RECEIPT_TYPE_BY_KIND[raw_kind]
    if type(receipt) is not expected_type:
        raise ValueError("receipt object type does not match its task discriminator")
    receipt = expected_type.model_validate(receipt.model_dump(mode="python"))
    bindings = {item.receipt_kind: item for item in policy.dependency_bindings}
    binding = bindings[raw_kind]
    if receipt.protocol_id != binding.protocol_id:
        raise ValueError("receipt protocol is not the preregistered task protocol")
    if receipt.run_id != expected_run_id:
        raise ValueError("cross-run receipt substitution")
    if receipt.freshness_window_seconds != binding.freshness_window_seconds:
        raise ValueError("receipt freshness window differs from the preregistered policy")
    if binding.config_spec_commitment_status is not DependencyCommitmentStatus.ENROLLED:
        raise ValueError("dependency config/spec commitments are not enrolled")
    if (
        receipt.config_content_sha256,
        receipt.spec_content_sha256,
    ) != (
        binding.expected_config_content_sha256,
        binding.expected_spec_content_sha256,
    ):
        raise ValueError("receipt config/spec hashes differ from preregistered commitments")
    now = _require_utc(verification_time_utc, label="receipt verification time")
    if receipt.issued_at_utc > now or receipt.verified_at_utc > now:
        raise ValueError("receipt timestamp is in the verifier's future")
    if now > receipt.expires_at_utc:
        raise ValueError("receipt is stale")
    if receipt.replay_registry_id != replay_registry.registry_id:
        raise ValueError("receipt names the wrong replay registry")
    if receipt.trust_anchor_manifest_sha256 != trust_anchor_manifest_content_sha256(manifest):
        raise ValueError("receipt substitutes a different trust-anchor manifest")

    verify_custody_chain(receipt, manifest=manifest)

    expected_parent_kinds = binding.required_parent_kinds
    actual_parent_kinds = tuple(item.receipt_kind for item in receipt.parent_receipts)
    if actual_parent_kinds != expected_parent_kinds:
        raise ValueError("receipt parent types do not match the frozen DAG")
    if set(verified_parents) != set(expected_parent_kinds):
        raise ValueError("verifier did not supply the exact parent set")
    for parent_ref in receipt.parent_receipts:
        parent = verified_parents[parent_ref.receipt_kind]
        if parent.run_id != receipt.run_id:
            raise ValueError("parent and child belong to different runs")
        if (
            parent_ref.receipt_id,
            parent_ref.receipt_content_sha256,
        ) != (parent.receipt_id, formal_receipt_content_sha256(parent)):
            raise ValueError("parent receipt id/content hash mismatch")
        if parent.verified_at_utc > receipt.issued_at_utc:
            raise ValueError("child receipt predates verification of its parent")
    if isinstance(receipt, BindingResolutionReceiptBase):
        task9_parent = verified_parents.get(ReceiptKind.TASK_9)
        if not isinstance(task9_parent, Task9Receipt):
            raise ValueError("binding resolution receipt lacks its typed Task 9 parent")
        if (
            receipt.selected_method_receipt_content_sha256
            != task9_parent.selected_method_receipt_content_sha256
        ):
            raise ValueError("binding receipt substitutes a different selected-method receipt")

    anchor = _entry_by_kind(manifest, raw_kind)
    if (
        receipt.independent_verifier_id,
        receipt.signer_key_id,
        receipt.signer_public_key_sha256,
    ) != (anchor.authority_id, anchor.key_id, anchor.public_key_sha256):
        raise ValueError("receipt signer is not the enrolled task trust anchor")
    if anchor.enrolled_at_utc > receipt.issued_at_utc:
        raise ValueError("receipt predates signer enrollment")
    verifier = Ed25519AttestationVerifier.from_public_key_base64(
        key_id=anchor.key_id, public_key_base64=anchor.public_key_base64
    )
    verifier.verify(
        f"{FORMAL_RECEIPT_DOMAIN_PREFIX}:{raw_kind.value}",
        attested_payload(receipt),
        receipt.attestation,
    )
    if replay_registry.contains(raw_kind, receipt.nonce):
        raise ValueError(f"replayed nonce for {raw_kind.value}")
    replay_registry.consume(raw_kind, receipt.nonce, formal_receipt_content_sha256(receipt))
    return receipt


class DependencyState(StrEnum):
    VERIFIED = "VERIFIED"
    MISSING = "MISSING"
    INVALID = "INVALID"
    BLOCKED_BY_PARENT = "BLOCKED_BY_PARENT"


class DependencyAssessment(ContractModel):
    receipt_kind: ReceiptKind
    state: DependencyState
    receipt_content_sha256: Sha256 | None = None
    blockers: tuple[str, ...]


class AuthorizationDecisionStatus(StrEnum):
    NOT_AUTHORIZED = "NOT_AUTHORIZED"
    AUTHORIZED = "AUTHORIZED"


class TrustedSevenOperatorAblationAuthorization(ContractModel):
    """The single aggregate authorization object for seven-operator ablation."""

    schema_version: Literal["1.0.0"]
    protocol_id: Literal["structure-two-trusted-seven-operator-ablation-authorization@1.1"]
    decision_id: UUID
    run_id: UUID
    seven_operator_identity: Literal["ORRER_CHEH"]
    authenticated_enabled_noop_allowed: Literal[True]
    evaluated_at_utc: datetime
    freshness_window_seconds: PositiveInt = Field(le=86_400)
    expires_at_utc: datetime
    replay_registry_id: UUID
    policy_content_sha256: Sha256
    dependency_assessments: tuple[DependencyAssessment, ...]
    dependency_receipt_hashes: tuple[ParentReceiptRef, ...]
    blockers: tuple[str, ...]
    decision_status: AuthorizationDecisionStatus
    authorized: bool
    authorization_nonce: UUID | None = None
    trust_anchor_manifest_sha256: Sha256 | None = None
    authorization_signer_key_id: str | None = None
    authorization_signer_public_key_sha256: Sha256 | None = None
    attestation: Attestation | None = None

    @model_validator(mode="after")
    def _decision_consistency(self) -> TrustedSevenOperatorAblationAuthorization:
        evaluated = _require_utc(self.evaluated_at_utc, label="authorization evaluation time")
        expires = _require_utc(self.expires_at_utc, label="authorization expiry time")
        if expires != evaluated + timedelta(seconds=self.freshness_window_seconds):
            raise ValueError(
                "authorization expiry must equal evaluation time plus freshness window"
            )
        if tuple(item.receipt_kind for item in self.dependency_assessments) != DEPENDENCY_ORDER:
            raise ValueError("authorization assessments must cover the frozen dependency order")
        all_verified = all(
            item.state is DependencyState.VERIFIED for item in self.dependency_assessments
        )
        if self.authorized != (self.decision_status is AuthorizationDecisionStatus.AUTHORIZED):
            raise ValueError("authorization boolean and decision status disagree")
        if self.authorized:
            if not all_verified or self.blockers:
                raise ValueError("authorization cannot coexist with dependency blockers")
            if tuple(item.receipt_kind for item in self.dependency_receipt_hashes) != (
                DEPENDENCY_ORDER
            ):
                raise ValueError("authorized decision must bind every dependency receipt")
            required = (
                self.authorization_nonce,
                self.trust_anchor_manifest_sha256,
                self.authorization_signer_key_id,
                self.authorization_signer_public_key_sha256,
                self.attestation,
            )
            if any(item is None for item in required):
                raise ValueError("authorized decision requires an independently signed envelope")
        else:
            if all_verified and not self.blockers:
                raise ValueError(
                    "a fully verified unsigned decision must report its signer blocker"
                )
            if self.attestation is not None:
                raise ValueError("a denied decision must not masquerade as signed authorization")
        return self


def _authorization_payload(
    decision: TrustedSevenOperatorAblationAuthorization,
) -> dict[str, Any]:
    return attested_payload(decision)


def evaluate_trusted_seven_operator_ablation_authorization(
    *,
    policy: TrustedAblationAuthorizationPolicy,
    run_id: UUID,
    receipts: Mapping[ReceiptKind, FormalDependencyReceipt],
    replay_registry: ReceiptReplayRegistry,
    decision_id: UUID,
    authorization_nonce: UUID | None = None,
    trust_anchor_manifest: ReceiptTrustAnchorManifest | None = None,
    registry_authority: Ed25519AttestationVerifier | None = None,
    authorization_authority: Ed25519AttestationSigner | None = None,
) -> TrustedSevenOperatorAblationAuthorization:
    """Evaluate the full DAG and sign only a blocker-free positive decision.

    Missing current formal runs are ordinary blockers.  Invalid receipts never
    raise from this aggregate surface: they are recorded and propagated so the
    caller receives the complete fail-closed dependency picture.
    """

    supplied_policy = TrustedAblationAuthorizationPolicy.model_validate(
        policy.model_dump(mode="python")
    )
    frozen_policy = TrustedAblationAuthorizationPolicy.load(DEFAULT_POLICY_PATH)
    policy_matches_frozen = content_sha256(supplied_policy) == content_sha256(frozen_policy)
    policy = frozen_policy
    now = _require_utc(_verifier_utc_now(), label="authorization evaluation time")
    assessments: list[DependencyAssessment] = []
    verified: dict[ReceiptKind, FormalDependencyReceipt] = {}
    verified_receipt_ids: set[UUID] = set()
    blockers: list[str] = []
    manifest: ReceiptTrustAnchorManifest | None = None
    manifest_error: str | None = None
    if not policy_matches_frozen:
        blockers.append("caller_policy_differs_from_checked_in_frozen_policy")
    replay_registry_error: str | None = None
    replay_registry_error = "formal_monotonic_or_worm_replay_backend_not_implemented_or_enrolled"
    if replay_registry_error is not None:
        blockers.append(replay_registry_error)
    bindings_by_kind = {item.receipt_kind: item for item in policy.dependency_bindings}
    commitment_errors: dict[ReceiptKind, str] = {}
    for kind in DEPENDENCY_ORDER:
        binding = bindings_by_kind[kind]
        if binding.config_spec_commitment_status is not DependencyCommitmentStatus.ENROLLED:
            commitment_errors[kind] = "config_spec_commitments_not_enrolled"
            blockers.append(f"{kind.value}:config_spec_commitments_not_enrolled")
    custody_error: str | None = None
    if policy.custody_attestation_status is not CustodyAttestationStatus.PER_HOP_INDEPENDENT:
        custody_error = "per_hop_independent_custody_attestation_not_enrolled"
        blockers.append(custody_error)
    if policy.trust_anchor_status is not TrustAnchorStatus.ENROLLED:
        manifest_error = "trust_anchor_manifest_not_enrolled"
    elif trust_anchor_manifest is None or registry_authority is None:
        manifest_error = "enrolled_trust_anchor_manifest_or_root_verifier_missing"
    else:
        try:
            manifest = verify_trust_anchor_manifest(
                trust_anchor_manifest,
                registry_authority=registry_authority,
                expected_manifest_sha256=cast(str, policy.trust_anchor_manifest_sha256),
                verification_time_utc=now,
            )
        except (ValueError, AttestationError) as exc:
            manifest_error = f"trust_anchor_manifest_invalid:{exc}"
    if manifest_error is not None:
        blockers.append(manifest_error)

    for kind in DEPENDENCY_ORDER:
        expected_parents = EXPECTED_PARENTS[kind]
        invalid_parents = tuple(parent for parent in expected_parents if parent not in verified)
        if invalid_parents:
            reasons = tuple(f"parent_not_verified:{parent.value}" for parent in invalid_parents)
            assessments.append(
                DependencyAssessment(
                    receipt_kind=kind,
                    state=DependencyState.BLOCKED_BY_PARENT,
                    blockers=reasons,
                )
            )
            blockers.extend(f"{kind.value}:{reason}" for reason in reasons)
            continue
        receipt = receipts.get(kind)
        if receipt is None:
            reason = "formal_receipt_missing"
            assessments.append(
                DependencyAssessment(
                    receipt_kind=kind,
                    state=DependencyState.MISSING,
                    blockers=(reason,),
                )
            )
            blockers.append(f"{kind.value}:{reason}")
            continue
        global_errors = tuple(
            error
            for error in (
                None if policy_matches_frozen else "policy_provenance_invalid",
                replay_registry_error,
                custody_error,
                commitment_errors.get(kind),
            )
            if error is not None
        )
        if global_errors:
            assessments.append(
                DependencyAssessment(
                    receipt_kind=kind,
                    state=DependencyState.INVALID,
                    blockers=global_errors,
                )
            )
            blockers.extend(f"{kind.value}:{reason}" for reason in global_errors)
            continue
        if manifest is None:
            reason = manifest_error or "trust_anchor_manifest_unavailable"
            assessments.append(
                DependencyAssessment(
                    receipt_kind=kind,
                    state=DependencyState.INVALID,
                    blockers=(reason,),
                )
            )
            blockers.append(f"{kind.value}:{reason}")
            continue
        try:
            if receipt.receipt_kind is not kind:
                raise ValueError("cross-task receipt substitution")
            if receipt.receipt_id in verified_receipt_ids:
                raise ValueError("receipt id is reused across dependency types")
            parent_map = {parent: verified[parent] for parent in expected_parents}
            checked = verify_formal_receipt(
                receipt,
                policy=policy,
                manifest=manifest,
                verified_parents=parent_map,
                expected_run_id=run_id,
                verification_time_utc=now,
                replay_registry=replay_registry,
            )
        except (ValueError, AttestationError) as exc:
            reason = f"receipt_invalid:{exc}"
            assessments.append(
                DependencyAssessment(
                    receipt_kind=kind,
                    state=DependencyState.INVALID,
                    blockers=(reason,),
                )
            )
            blockers.append(f"{kind.value}:{reason}")
            continue
        verified[kind] = checked
        verified_receipt_ids.add(checked.receipt_id)
        assessments.append(
            DependencyAssessment(
                receipt_kind=kind,
                state=DependencyState.VERIFIED,
                receipt_content_sha256=formal_receipt_content_sha256(checked),
                blockers=(),
            )
        )

    refs = tuple(
        ParentReceiptRef(
            receipt_kind=kind,
            receipt_id=verified[kind].receipt_id,
            receipt_content_sha256=formal_receipt_content_sha256(verified[kind]),
        )
        for kind in DEPENDENCY_ORDER
        if kind in verified
    )
    can_authorize = len(verified) == len(DEPENDENCY_ORDER) and not blockers
    authorization_anchor: TrustAnchorEntry | None = None
    if can_authorize:
        if authorization_authority is None or authorization_nonce is None or manifest is None:
            blockers.append("independent_authorization_signer_or_nonce_missing")
            can_authorize = False
        else:
            try:
                authorization_anchor = _entry_by_kind(manifest, ReceiptKind.AUTHORIZATION)
                verifier = authorization_authority.verifier()
                if (
                    verifier.key_id,
                    verifier.public_key_sha256,
                ) != (
                    authorization_anchor.key_id,
                    authorization_anchor.public_key_sha256,
                ):
                    raise ValueError("authorization signer is not the enrolled anchor")
                if replay_registry.contains(ReceiptKind.AUTHORIZATION, authorization_nonce):
                    raise ValueError("authorization nonce was replayed")
            except ValueError as exc:
                blockers.append(f"authorization_signer_invalid:{exc}")
                can_authorize = False

    decision_payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "protocol_id": AUTHORIZATION_PROTOCOL_ID,
        "decision_id": decision_id,
        "run_id": run_id,
        "seven_operator_identity": SEVEN_OPERATOR_IDENTITY,
        "authenticated_enabled_noop_allowed": True,
        "evaluated_at_utc": now,
        "freshness_window_seconds": next(
            item.freshness_window_seconds
            for item in policy.dependency_bindings
            if item.receipt_kind is ReceiptKind.AUTHORIZATION
        ),
        "expires_at_utc": now
        + timedelta(
            seconds=next(
                item.freshness_window_seconds
                for item in policy.dependency_bindings
                if item.receipt_kind is ReceiptKind.AUTHORIZATION
            )
        ),
        "replay_registry_id": replay_registry.registry_id,
        "policy_content_sha256": content_sha256(policy),
        "dependency_assessments": tuple(assessments),
        "dependency_receipt_hashes": refs,
        "blockers": tuple(blockers),
        "decision_status": (
            AuthorizationDecisionStatus.AUTHORIZED
            if can_authorize
            else AuthorizationDecisionStatus.NOT_AUTHORIZED
        ),
        "authorized": can_authorize,
        "authorization_nonce": authorization_nonce if can_authorize else None,
        "trust_anchor_manifest_sha256": (
            trust_anchor_manifest_content_sha256(cast(ReceiptTrustAnchorManifest, manifest))
            if can_authorize
            else None
        ),
        "authorization_signer_key_id": (
            authorization_anchor.key_id
            if authorization_anchor is not None and can_authorize
            else None
        ),
        "authorization_signer_public_key_sha256": (
            authorization_anchor.public_key_sha256
            if authorization_anchor is not None and can_authorize
            else None
        ),
    }
    if not can_authorize:
        return TrustedSevenOperatorAblationAuthorization.model_validate(decision_payload)
    assert authorization_authority is not None
    assert authorization_nonce is not None
    provisional = TrustedSevenOperatorAblationAuthorization.model_construct(
        **decision_payload, attestation=None
    )
    normalized_payload = _authorization_payload(provisional)
    signature = authorization_authority.sign(AUTHORIZATION_DOMAIN, normalized_payload)
    signed = TrustedSevenOperatorAblationAuthorization.model_validate(
        {**normalized_payload, "attestation": signature}
    )
    authorization_authority.verifier().verify(
        AUTHORIZATION_DOMAIN, _authorization_payload(signed), signed.attestation
    )
    return signed


def verify_trusted_seven_operator_ablation_authorization(
    decision: TrustedSevenOperatorAblationAuthorization,
    *,
    policy: TrustedAblationAuthorizationPolicy,
    manifest: ReceiptTrustAnchorManifest,
    registry_authority: Ed25519AttestationVerifier,
    expected_run_id: UUID,
    replay_registry: ReceiptReplayRegistry,
) -> None:
    """Verify a positive authorization; denied decisions are never executable tokens."""

    decision = TrustedSevenOperatorAblationAuthorization.model_validate(
        decision.model_dump(mode="python")
    )
    policy = TrustedAblationAuthorizationPolicy.model_validate(policy.model_dump(mode="python"))
    frozen_policy = TrustedAblationAuthorizationPolicy.load(DEFAULT_POLICY_PATH)
    if content_sha256(policy) != content_sha256(frozen_policy):
        raise ValueError("authorization policy is not the checked-in frozen policy")
    policy = frozen_policy
    now = _require_utc(_verifier_utc_now(), label="authorization verification time")
    if not decision.authorized:
        raise ValueError("seven-operator ablation is not authorized")
    if decision.run_id != expected_run_id:
        raise ValueError("authorization belongs to a different run")
    if now < decision.evaluated_at_utc:
        raise ValueError("authorization is from the executor's future")
    if now > decision.expires_at_utc:
        raise ValueError("authorization is stale")
    authorization_binding = next(
        item
        for item in policy.dependency_bindings
        if item.receipt_kind is ReceiptKind.AUTHORIZATION
    )
    if decision.freshness_window_seconds != authorization_binding.freshness_window_seconds:
        raise ValueError("authorization freshness window differs from frozen policy")
    if decision.policy_content_sha256 != content_sha256(policy):
        raise ValueError("authorization policy hash mismatch")
    if (
        policy.trust_anchor_status is not TrustAnchorStatus.ENROLLED
        or policy.trust_anchor_manifest_sha256 is None
    ):
        raise ValueError("trust-anchor manifest is not enrolled by the checked-in policy")
    manifest = verify_trust_anchor_manifest(
        manifest,
        registry_authority=registry_authority,
        expected_manifest_sha256=policy.trust_anchor_manifest_sha256,
        verification_time_utc=now,
    )
    manifest_hash = trust_anchor_manifest_content_sha256(manifest)
    if decision.trust_anchor_manifest_sha256 != manifest_hash:
        raise ValueError("authorization trust-anchor manifest mismatch")
    if policy.custody_attestation_status is not CustodyAttestationStatus.PER_HOP_INDEPENDENT:
        raise ValueError("per-hop independent custody attestation is not enrolled")
    if decision.replay_registry_id != replay_registry.registry_id:
        raise ValueError("authorization names the wrong replay registry")
    if manifest.registry_id != replay_registry.registry_id:
        raise ValueError("trust-anchor manifest names a different replay registry")
    anchor = _entry_by_kind(manifest, ReceiptKind.AUTHORIZATION)
    if (
        decision.authorization_signer_key_id,
        decision.authorization_signer_public_key_sha256,
    ) != (anchor.key_id, anchor.public_key_sha256):
        raise ValueError("authorization signer identity mismatch")
    verifier = Ed25519AttestationVerifier.from_public_key_base64(
        key_id=anchor.key_id, public_key_base64=anchor.public_key_base64
    )
    verifier.verify(AUTHORIZATION_DOMAIN, _authorization_payload(decision), decision.attestation)
    raise ValueError(
        "authorization v1.1 leaves the formal monotonic/WORM replay backend unresolved; "
        "positive verification requires a new protocol revision"
    )


__all__ = [
    "AUTHORIZATION_PROTOCOL_ID",
    "CUSTODY_HOP_DOMAIN_PREFIX",
    "DEPENDENCY_ORDER",
    "EXPECTED_PARENTS",
    "EXPECTED_PROTOCOL_IDS",
    "ROUND2_POSITIVE_CONSEQUENTIAL_SURFACES",
    "SEVEN_OPERATOR_COMPONENT_IDENTITIES",
    "SEVEN_OPERATOR_IDENTITY",
    "ActionProbability",
    "AuditRound1Receipt",
    "AuditRound2Receipt",
    "AuthorizationDecisionStatus",
    "BindingResolutionReceiptBase",
    "CiavActionBudgetReceipt",
    "ConsolidationThresholdsReceipt",
    "CustodyAttestationStatus",
    "CustodyHop",
    "CustodyRole",
    "CustodyTrustAnchorEntry",
    "DependencyAssessment",
    "DependencyCommitmentStatus",
    "DependencyProtocolBinding",
    "DependencyState",
    "ExactEnumerationFalsifierReceipt",
    "FormalDependencyReceipt",
    "FormalReceiptBase",
    "GateBV08Receipt",
    "NeuralProposerArchitectureReceipt",
    "P5BottleneckDiagnosis",
    "P5PipelineStage",
    "P5StageDecomposition",
    "ParentReceiptRef",
    "ProposalP5Receipt",
    "ReceiptKind",
    "ReceiptReplayRegistry",
    "ReceiptTrustAnchorManifest",
    "ReplayRegistryStatus",
    "Task7Receipt",
    "Task8Receipt",
    "Task9Receipt",
    "Task10Receipt",
    "Task11Receipt",
    "Task12GateThresholds",
    "Task12ProposalEvent",
    "Task12ProposalProbability",
    "Task12ProposalRow",
    "Task12RawProposalTrace",
    "Task12Receipt",
    "Task12RecomputedGateResult",
    "Task12State",
    "Task13Receipt",
    "TrainingScheduleReceipt",
    "TrustAnchorEntry",
    "TrustAnchorStatus",
    "TrustedAblationAuthorizationPolicy",
    "TrustedSevenOperatorAblationAuthorization",
    "diagnose_p5_bottleneck",
    "evaluate_trusted_seven_operator_ablation_authorization",
    "formal_receipt_content_sha256",
    "issue_custody_hop",
    "issue_formal_receipt",
    "issue_trust_anchor_manifest",
    "recompute_task12_gate_result",
    "trust_anchor_manifest_content_sha256",
    "verify_custody_chain",
    "verify_formal_receipt",
    "verify_trust_anchor_manifest",
    "verify_trusted_seven_operator_ablation_authorization",
]
