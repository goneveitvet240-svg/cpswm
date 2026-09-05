"""Independently sealed, one-attempt Gate-B opening contract for Structure Two.

This protocol is deliberately separate from the public Gate-A validation
opening.  A verifier accepts an opening only after matching it to already
verified freeze and Gate-A ledger facts, an independently frozen commitment,
the exact ten-arm implementation set, and an enrolled custodian key.

The in-memory consumed-attempt helpers are useful for a single verifier
process.  Formal external use must persist the same IDs in an append-only,
serialized ledger; a Python set is not evidence of independent custody.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, MutableSet, Sequence, Set
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import Field, StrictInt, model_validator

from cpswm.contracts.base import ContractModel, require_aware
from cpswm.system.attestation import (
    Attestation,
    AttestationError,
    Ed25519AttestationSigner,
    Ed25519AttestationVerifier,
    attested_payload,
)
from cpswm.system.evaluation_operations.structure_two_frozen_run_v0_8 import (
    FrozenHoldoutOpeningV08,
    recompute_frozen_holdout_v0_8,
)
from cpswm.system.evaluation_operations.structure_two_gate_b_protocol_v0_6 import (
    EXPECTED_ARMS,
)
from cpswm.system.reproducibility import content_sha256

PROTOCOL_ID = "structure-two-sealed-gate-b-opening@0.9"
COMMITMENT_PROTOCOL_ID = "structure-two-sealed-gate-b-commitment@0.9"
COMMITMENT_RECORD_PROTOCOL_ID = "structure-two-sealed-gate-b-commitment-record@0.9"
IMPLEMENTATION_SET_PROTOCOL_ID = "structure-two-gate-b-implementation-set@0.9"
DETACHED_SIGNING_REQUEST_PROTOCOL_ID = "structure-two-detached-signing-request@0.9"
FORBIDDEN_SEED_NAMESPACE_PROTOCOL_ID = "structure-two-forbidden-seed-namespaces@0.9"
ATTESTATION_DOMAIN = "cpswm.evaluation.structure_two.sealed_gate_b_opening.v0.9"
COMMITMENT_CUSTODIAN_ATTESTATION_DOMAIN = (
    "cpswm.evaluation.structure_two.sealed_gate_b_commitment.custodian.v0.9"
)
COMMITMENT_AUTHORITY_ATTESTATION_DOMAIN = (
    "cpswm.evaluation.structure_two.sealed_gate_b_commitment.enrollment_authority.v0.9"
)
GATE_A_LIFECYCLE_PROTOCOL_ID = "structure-two-gate-a-lifecycle-completion@0.9"
GATE_A_EXECUTOR_ATTESTATION_DOMAIN = "cpswm.evaluation.structure_two.gate_a_lifecycle.executor.v0.9"
GATE_A_CUSTODIAN_ATTESTATION_DOMAIN = (
    "cpswm.evaluation.structure_two.gate_a_lifecycle.custodian.v0.9"
)
GATE_A_AUTHORITY_ATTESTATION_DOMAIN = (
    "cpswm.evaluation.structure_two.gate_a_lifecycle.enrollment_authority.v0.9"
)
EVALUATION_SET_ROLE = "custodian_sealed_confirmatory_gate_b"

EXACT_WORLD_SEED_COUNT = 12
EXACT_TRAJECTORY_SEED_COUNT = 3
EXACT_OBSERVATION_SEED_COUNT = 2
EXACT_BOOTSTRAP_DRAWS = 4_000


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _validate_identifier(value: str, *, label: str, minimum_length: int = 1) -> None:
    if (
        len(value) < minimum_length
        or value != value.strip()
        or any(character.isspace() for character in value)
    ):
        raise ValueError(f"{label} is malformed")


def _validate_utc(value: datetime, *, label: str) -> None:
    require_aware(value, label)
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must use UTC")


class DetachedSigningRequestV09(ContractModel):
    """Content-bound request carried to exactly one isolated Ed25519 signer."""

    protocol: Literal["structure-two-detached-signing-request@0.9"] = (
        "structure-two-detached-signing-request@0.9"
    )
    artifact_protocol: str = Field(min_length=1)
    role: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    expected_key_id: str = Field(min_length=1)
    expected_public_key_base64: str = Field(min_length=1)
    expected_public_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    payload: dict[str, Any]
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_request(self) -> Self:
        if content_sha256(self.payload) != self.payload_sha256:
            raise ValueError("detached signing request payload hash mismatch")
        return self


def _detached_signing_request(
    *,
    artifact_protocol: str,
    role: str,
    domain: str,
    verifier: Ed25519AttestationVerifier,
    payload: Mapping[str, Any],
) -> DetachedSigningRequestV09:
    materialized = dict(payload)
    return DetachedSigningRequestV09(
        artifact_protocol=artifact_protocol,
        role=role,
        domain=domain,
        expected_key_id=verifier.key_id,
        expected_public_key_base64=verifier.public_key_base64,
        expected_public_key_sha256=verifier.public_key_sha256,
        payload=materialized,
        payload_sha256=content_sha256(materialized),
    )


def sign_detached_request_v0_9(
    request: DetachedSigningRequestV09,
    *,
    signer: Ed25519AttestationSigner,
) -> Attestation:
    """Sign one request inside the role holder's isolated process."""

    verifier = signer.verifier()
    if (
        verifier.key_id != request.expected_key_id
        or verifier.public_key_base64 != request.expected_public_key_base64
        or verifier.public_key_sha256 != request.expected_public_key_sha256
    ):
        raise AttestationError("detached request was delivered to the wrong signer")
    if content_sha256(request.payload) != request.payload_sha256:
        raise ValueError("detached signing request was mutated before signing")
    return signer.sign(request.domain, request.payload)


class ForbiddenSeedNamespacesV09(ContractModel):
    """Content-bound union of every already spent seed namespace."""

    protocol: Literal["structure-two-forbidden-seed-namespaces@0.9"] = (
        "structure-two-forbidden-seed-namespaces@0.9"
    )
    world_manifest_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    gate_a_spec_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    training_split_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    world_seeds: tuple[StrictInt, ...] = Field(min_length=1)
    trajectory_seeds: tuple[StrictInt, ...] = Field(min_length=1)
    observation_seeds: tuple[StrictInt, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_namespaces(self) -> Self:
        for label, values in (
            ("world", self.world_seeds),
            ("trajectory", self.trajectory_seeds),
            ("observation", self.observation_seeds),
        ):
            if tuple(sorted(set(values))) != values or any(value < 0 for value in values):
                raise ValueError(
                    f"forbidden {label} seeds must be sorted unique nonnegative values"
                )
        return self

    @property
    def content_sha256(self) -> str:
        return content_sha256(self.model_dump(mode="json"))


def _verify_content_bound_mapping(
    payload: Mapping[str, Any],
    *,
    expected_content_sha256: str,
    label: str,
) -> dict[str, Any]:
    materialized = dict(payload)
    embedded = materialized.pop("content_sha256", None)
    actual = content_sha256(materialized if embedded is not None else payload)
    if actual != expected_content_sha256 or (
        embedded is not None and embedded != expected_content_sha256
    ):
        raise ValueError(f"{label} content hash mismatch")
    return materialized


def derive_forbidden_seed_namespaces_v0_9(
    *,
    world_manifest: Mapping[str, Any],
    expected_world_manifest_content_sha256: str,
    gate_a_spec: Mapping[str, Any],
    expected_gate_a_spec_content_sha256: str,
    training_split: Mapping[str, Any],
    expected_training_split_content_sha256: str,
) -> ForbiddenSeedNamespacesV09:
    """Derive the verifier-owned union from content-bound split specifications."""

    world = _verify_content_bound_mapping(
        world_manifest,
        expected_content_sha256=expected_world_manifest_content_sha256,
        label="world manifest",
    )
    gate = _verify_content_bound_mapping(
        gate_a_spec,
        expected_content_sha256=expected_gate_a_spec_content_sha256,
        label="Gate-A spec",
    )
    training = _verify_content_bound_mapping(
        training_split,
        expected_content_sha256=expected_training_split_content_sha256,
        label="training split",
    )
    split_policy = world["split_policy"]
    public_validation = gate["public_preregistered_validation"]
    train_sampling = training["train_sampling"]

    def seeds(*values: Sequence[int]) -> tuple[int, ...]:
        flattened = tuple(value for group in values for value in group)
        if any(isinstance(value, bool) or not isinstance(value, int) for value in flattened):
            raise ValueError("seed specification contains a non-integer value")
        return tuple(sorted(set(flattened)))

    return ForbiddenSeedNamespacesV09(
        world_manifest_content_sha256=expected_world_manifest_content_sha256,
        gate_a_spec_content_sha256=expected_gate_a_spec_content_sha256,
        training_split_content_sha256=expected_training_split_content_sha256,
        world_seeds=seeds(
            split_policy["train_world_seeds_spent_for_tuning"],
            split_policy["prior_validation_world_seeds_spent"],
            split_policy["v0_5_validation_world_seeds_preregistered_not_generated"],
            public_validation["excluded_world_seeds"],
            public_validation["validation_world_seeds"],
            train_sampling["world_seeds"],
        ),
        trajectory_seeds=seeds(
            split_policy["validation_trajectory_seeds"],
            public_validation["trajectory_seeds"],
            train_sampling["trajectory_seeds"],
        ),
        observation_seeds=seeds(
            split_policy["validation_observation_seeds"],
            public_validation["observation_seeds"],
            train_sampling["observation_seeds"],
        ),
    )


def _validate_seed_tuple(
    values: Sequence[int],
    *,
    label: str,
    exact_count: int,
) -> tuple[int, ...]:
    materialized = tuple(values)
    if len(materialized) != exact_count:
        raise ValueError(f"sealed Gate B requires exactly {exact_count} {label}")
    if len(set(materialized)) != len(materialized):
        raise ValueError(f"sealed Gate B contains duplicate {label}")
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in materialized
    ):
        raise ValueError(f"sealed Gate B contains invalid {label}")
    return materialized


def arm_implementation_bundle_set_sha256_v0_9(
    arm_implementation_bundle_sha256: Mapping[str, str],
) -> str:
    """Hash the exact ten-arm set in protocol-defined canonical order."""

    if set(arm_implementation_bundle_sha256) != set(EXPECTED_ARMS):
        raise ValueError("sealed Gate B implementation set is not the exact ten-arm set")
    if any(not _is_sha256(value) for value in arm_implementation_bundle_sha256.values()):
        raise ValueError("sealed Gate B implementation set contains a malformed digest")
    return content_sha256(
        {
            "protocol": IMPLEMENTATION_SET_PROTOCOL_ID,
            "ordered_arm_implementation_bundles": tuple(
                (arm, arm_implementation_bundle_sha256[arm]) for arm in EXPECTED_ARMS
            ),
        }
    )


def _validate_opening_material(
    *,
    world_distribution: Mapping[str, Any],
    world_seeds: Sequence[int],
    trajectory_seeds: Sequence[int],
    observation_seeds: Sequence[int],
    estimator: Mapping[str, float | int],
    bootstrap_draws: int,
    commitment_nonce: str,
) -> tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...]]:
    worlds = _validate_seed_tuple(
        world_seeds,
        label="world seeds",
        exact_count=EXACT_WORLD_SEED_COUNT,
    )
    trajectories = _validate_seed_tuple(
        trajectory_seeds,
        label="trajectory seeds",
        exact_count=EXACT_TRAJECTORY_SEED_COUNT,
    )
    observations = _validate_seed_tuple(
        observation_seeds,
        label="observation seeds",
        exact_count=EXACT_OBSERVATION_SEED_COUNT,
    )
    if bootstrap_draws != EXACT_BOOTSTRAP_DRAWS:
        raise ValueError(f"sealed Gate B requires exactly {EXACT_BOOTSTRAP_DRAWS} bootstrap draws")
    _validate_identifier(
        commitment_nonce,
        label="sealed Gate-B commitment nonce",
        minimum_length=16,
    )

    # This projection invokes the already audited distribution/estimator
    # validators.  It is never serialized or accepted as Gate-A evidence.
    FrozenHoldoutOpeningV08(
        protocol="structure-two-public-validation-opening@0.8",
        evaluation_set_role="public_preregistered_validation",
        immutable_manifest_sha256="0" * 64,
        producer_run_id="v0.9-material-validation-only",
        seed_opening_nonce=commitment_nonce,
        holdout_opening_nonce=commitment_nonce,
        world_distribution=dict(world_distribution),
        validation_world_seeds=worlds,
        trajectory_seeds=trajectories,
        observation_seeds=observations,
        estimator=dict(estimator),
        bootstrap_draws=bootstrap_draws,
    )
    return worlds, trajectories, observations


def sealed_gate_b_commitment_sha256_v0_9(
    *,
    immutable_manifest_sha256: str,
    producer_run_id: str,
    arm_implementation_bundle_set_sha256: str,
    world_distribution: Mapping[str, Any],
    world_seeds: Sequence[int],
    trajectory_seeds: Sequence[int],
    observation_seeds: Sequence[int],
    estimator: Mapping[str, float | int],
    bootstrap_draws: int,
    commitment_nonce: str,
) -> str:
    """Commit to secret Gate-B material without depending on Gate-A seeds."""

    if not _is_sha256(immutable_manifest_sha256) or not _is_sha256(
        arm_implementation_bundle_set_sha256
    ):
        raise ValueError("sealed Gate-B commitment context contains a malformed digest")
    _validate_identifier(producer_run_id, label="producer run ID")
    worlds, trajectories, observations = _validate_opening_material(
        world_distribution=world_distribution,
        world_seeds=world_seeds,
        trajectory_seeds=trajectory_seeds,
        observation_seeds=observation_seeds,
        estimator=estimator,
        bootstrap_draws=bootstrap_draws,
        commitment_nonce=commitment_nonce,
    )
    return content_sha256(
        {
            "protocol": COMMITMENT_PROTOCOL_ID,
            "evaluation_set_role": EVALUATION_SET_ROLE,
            "immutable_manifest_sha256": immutable_manifest_sha256,
            "producer_run_id": producer_run_id,
            "arm_implementation_bundle_set_sha256": (arm_implementation_bundle_set_sha256),
            "world_distribution": dict(world_distribution),
            "world_seeds": worlds,
            "trajectory_seeds": trajectories,
            "observation_seeds": observations,
            "estimator": dict(estimator),
            "bootstrap_draws": bootstrap_draws,
            "commitment_nonce": commitment_nonce,
        }
    )


class SealedGateBCommitmentV09(ContractModel):
    """Dual-signed commitment ledger entry created after freeze and before Gate A."""

    protocol: Literal["structure-two-sealed-gate-b-commitment-record@0.9"] = (
        "structure-two-sealed-gate-b-commitment-record@0.9"
    )
    status: Literal["COMMITTED_AFTER_FREEZE_BEFORE_GATE_A"] = "COMMITTED_AFTER_FREEZE_BEFORE_GATE_A"
    immutable_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    producer_run_id: str = Field(min_length=1)
    arm_implementation_bundle_sha256: dict[str, str]
    arm_implementation_bundle_set_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sealed_gate_b_commitment_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    opening_attempt_id: str = Field(min_length=16, max_length=128)
    ledger_identifier: str = Field(min_length=1)
    freeze_ledger_sequence: StrictInt = Field(ge=0)
    commitment_ledger_sequence: StrictInt = Field(ge=0)
    freeze_completed_at_utc: datetime
    committed_at_utc: datetime
    custodian_key_id: str = Field(min_length=1)
    custodian_public_key_base64: str = Field(min_length=1)
    custodian_public_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    enrollment_authority_key_id: str = Field(min_length=1)
    enrollment_authority_public_key_base64: str = Field(min_length=1)
    enrollment_authority_public_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    custodian_attestation: Attestation | None = None
    enrollment_authority_attestation: Attestation | None = None

    @model_validator(mode="after")
    def validate_commitment_record(self) -> Self:
        _validate_identifier(self.producer_run_id, label="producer run ID")
        _validate_identifier(
            self.opening_attempt_id,
            label="opening attempt ID",
            minimum_length=16,
        )
        _validate_identifier(self.ledger_identifier, label="commitment ledger identifier")
        _validate_identifier(self.custodian_key_id, label="custodian key ID")
        _validate_identifier(
            self.enrollment_authority_key_id,
            label="enrollment authority key ID",
        )
        expected_set = arm_implementation_bundle_set_sha256_v0_9(
            self.arm_implementation_bundle_sha256
        )
        if expected_set != self.arm_implementation_bundle_set_sha256:
            raise ValueError("commitment record implementation set hash mismatch")
        if self.custodian_public_key_sha256 == self.enrollment_authority_public_key_sha256:
            raise ValueError("commitment custodian and enrollment authority must be independent")
        _validate_utc(self.freeze_completed_at_utc, label="freeze completion")
        _validate_utc(self.committed_at_utc, label="Gate-B commitment")
        if self.freeze_ledger_sequence >= self.commitment_ledger_sequence:
            raise ValueError("Gate-B commitment ledger sequence must follow freeze")
        if self.freeze_completed_at_utc >= self.committed_at_utc:
            raise ValueError("Gate-B commitment timestamp must follow freeze")
        return self


@dataclass(frozen=True, slots=True)
class VerifiedSealedGateBCommitmentV09:
    """A commitment record that passed both trust-anchor verifiers."""

    record: SealedGateBCommitmentV09
    content_sha256: str


def _commitment_attested_payload(record: SealedGateBCommitmentV09) -> dict[str, Any]:
    return attested_payload(
        record,
        exclude=frozenset(
            {
                "custodian_attestation",
                "enrollment_authority_attestation",
            }
        ),
    )


def prepare_sealed_gate_b_commitment_record_v0_9(
    *,
    immutable_manifest_sha256: str,
    producer_run_id: str,
    arm_implementation_bundle_sha256: Mapping[str, str],
    sealed_gate_b_commitment_sha256: str,
    opening_attempt_id: str,
    ledger_identifier: str,
    freeze_ledger_sequence: int,
    commitment_ledger_sequence: int,
    freeze_completed_at_utc: datetime,
    committed_at_utc: datetime,
    custodian: Ed25519AttestationVerifier,
    enrollment_authority: Ed25519AttestationVerifier,
) -> SealedGateBCommitmentV09:
    """Prepare an unsigned commitment using public keys only."""

    return SealedGateBCommitmentV09(
        immutable_manifest_sha256=immutable_manifest_sha256,
        producer_run_id=producer_run_id,
        arm_implementation_bundle_sha256=dict(arm_implementation_bundle_sha256),
        arm_implementation_bundle_set_sha256=(
            arm_implementation_bundle_set_sha256_v0_9(arm_implementation_bundle_sha256)
        ),
        sealed_gate_b_commitment_sha256=sealed_gate_b_commitment_sha256,
        opening_attempt_id=opening_attempt_id,
        ledger_identifier=ledger_identifier,
        freeze_ledger_sequence=freeze_ledger_sequence,
        commitment_ledger_sequence=commitment_ledger_sequence,
        freeze_completed_at_utc=freeze_completed_at_utc,
        committed_at_utc=committed_at_utc,
        custodian_key_id=custodian.key_id,
        custodian_public_key_base64=custodian.public_key_base64,
        custodian_public_key_sha256=custodian.public_key_sha256,
        enrollment_authority_key_id=enrollment_authority.key_id,
        enrollment_authority_public_key_base64=(enrollment_authority.public_key_base64),
        enrollment_authority_public_key_sha256=(enrollment_authority.public_key_sha256),
    )


def sealed_gate_b_commitment_signing_requests_v0_9(
    prepared: SealedGateBCommitmentV09,
) -> dict[str, DetachedSigningRequestV09]:
    """Return role-separated signing requests for isolated custodians."""

    if (
        prepared.custodian_attestation is not None
        or prepared.enrollment_authority_attestation is not None
    ):
        raise ValueError("commitment signing requests require an unsigned record")
    payload = _commitment_attested_payload(prepared)
    return {
        "custodian": _detached_signing_request(
            artifact_protocol=prepared.protocol,
            role="custodian",
            domain=COMMITMENT_CUSTODIAN_ATTESTATION_DOMAIN,
            verifier=Ed25519AttestationVerifier.from_public_key_base64(
                key_id=prepared.custodian_key_id,
                public_key_base64=prepared.custodian_public_key_base64,
            ),
            payload=payload,
        ),
        "enrollment_authority": _detached_signing_request(
            artifact_protocol=prepared.protocol,
            role="enrollment_authority",
            domain=COMMITMENT_AUTHORITY_ATTESTATION_DOMAIN,
            verifier=Ed25519AttestationVerifier.from_public_key_base64(
                key_id=prepared.enrollment_authority_key_id,
                public_key_base64=prepared.enrollment_authority_public_key_base64,
            ),
            payload=payload,
        ),
    }


def finalize_sealed_gate_b_commitment_record_v0_9(
    prepared: SealedGateBCommitmentV09,
    *,
    custodian_attestation: Attestation | None,
    enrollment_authority_attestation: Attestation | None,
    trusted_custodian: Ed25519AttestationVerifier,
    trusted_enrollment_authority: Ed25519AttestationVerifier,
    verification_time_utc: datetime,
) -> dict[str, Any]:
    """Finalize detached signatures using verification-only capabilities."""

    if (
        prepared.custodian_attestation is not None
        or prepared.enrollment_authority_attestation is not None
    ):
        raise ValueError("commitment finalization requires the prepared unsigned record")
    signed = prepared.model_copy(
        update={
            "custodian_attestation": custodian_attestation,
            "enrollment_authority_attestation": enrollment_authority_attestation,
        }
    )
    payload = signed.model_dump(mode="json")
    payload["content_sha256"] = content_sha256(payload)
    verify_sealed_gate_b_commitment_record_v0_9(
        payload,
        expected_immutable_manifest_sha256=prepared.immutable_manifest_sha256,
        expected_producer_run_id=prepared.producer_run_id,
        expected_arm_implementation_bundle_sha256=(prepared.arm_implementation_bundle_sha256),
        expected_ledger_identifier=prepared.ledger_identifier,
        expected_freeze_ledger_sequence=prepared.freeze_ledger_sequence,
        expected_freeze_completed_at_utc=prepared.freeze_completed_at_utc,
        trusted_custodian=trusted_custodian,
        trusted_enrollment_authority=trusted_enrollment_authority,
        verification_time_utc=verification_time_utc,
    )
    return payload


def make_sealed_gate_b_commitment_record_v0_9(
    *,
    immutable_manifest_sha256: str,
    producer_run_id: str,
    arm_implementation_bundle_sha256: Mapping[str, str],
    sealed_gate_b_commitment_sha256: str,
    opening_attempt_id: str,
    ledger_identifier: str,
    freeze_ledger_sequence: int,
    commitment_ledger_sequence: int,
    freeze_completed_at_utc: datetime,
    committed_at_utc: datetime,
    custodian: Ed25519AttestationSigner,
    enrollment_authority: Ed25519AttestationSigner,
    verification_time_utc: datetime,
) -> dict[str, Any]:
    """Create the independently dual-signed pre-Gate-A commitment record."""

    prepared = prepare_sealed_gate_b_commitment_record_v0_9(
        immutable_manifest_sha256=immutable_manifest_sha256,
        producer_run_id=producer_run_id,
        arm_implementation_bundle_sha256=arm_implementation_bundle_sha256,
        sealed_gate_b_commitment_sha256=sealed_gate_b_commitment_sha256,
        opening_attempt_id=opening_attempt_id,
        ledger_identifier=ledger_identifier,
        freeze_ledger_sequence=freeze_ledger_sequence,
        commitment_ledger_sequence=commitment_ledger_sequence,
        freeze_completed_at_utc=freeze_completed_at_utc,
        committed_at_utc=committed_at_utc,
        custodian=custodian.verifier(),
        enrollment_authority=enrollment_authority.verifier(),
    )
    requests = sealed_gate_b_commitment_signing_requests_v0_9(prepared)
    return finalize_sealed_gate_b_commitment_record_v0_9(
        prepared,
        custodian_attestation=sign_detached_request_v0_9(requests["custodian"], signer=custodian),
        enrollment_authority_attestation=sign_detached_request_v0_9(
            requests["enrollment_authority"], signer=enrollment_authority
        ),
        trusted_custodian=custodian.verifier(),
        trusted_enrollment_authority=enrollment_authority.verifier(),
        verification_time_utc=verification_time_utc,
    )


def verify_sealed_gate_b_commitment_record_v0_9(
    payload: Mapping[str, Any],
    *,
    expected_immutable_manifest_sha256: str,
    expected_producer_run_id: str,
    expected_arm_implementation_bundle_sha256: Mapping[str, str],
    expected_ledger_identifier: str,
    expected_freeze_ledger_sequence: int,
    expected_freeze_completed_at_utc: datetime,
    trusted_custodian: Ed25519AttestationVerifier,
    trusted_enrollment_authority: Ed25519AttestationVerifier,
    verification_time_utc: datetime,
) -> VerifiedSealedGateBCommitmentV09:
    """Verify content, freeze binding, distinct roles, and both signatures."""

    _validate_utc(verification_time_utc, label="commitment verification time")
    unsigned_payload = dict(payload)
    stored = unsigned_payload.pop("content_sha256", None)
    if not isinstance(stored, str) or content_sha256(unsigned_payload) != stored:
        raise ValueError("sealed Gate-B commitment record content hash mismatch")
    record = SealedGateBCommitmentV09.model_validate(unsigned_payload)
    if unsigned_payload != record.model_dump(mode="json"):
        raise ValueError("sealed Gate-B commitment record encoding is noncanonical")
    expected = {
        "immutable_manifest_sha256": expected_immutable_manifest_sha256,
        "producer_run_id": expected_producer_run_id,
        "arm_implementation_bundle_sha256": dict(expected_arm_implementation_bundle_sha256),
        "arm_implementation_bundle_set_sha256": (
            arm_implementation_bundle_set_sha256_v0_9(expected_arm_implementation_bundle_sha256)
        ),
        "ledger_identifier": expected_ledger_identifier,
        "freeze_ledger_sequence": expected_freeze_ledger_sequence,
        "freeze_completed_at_utc": expected_freeze_completed_at_utc,
    }
    dumped = record.model_dump(mode="python")
    if any(dumped[name] != value for name, value in expected.items()):
        raise ValueError("sealed Gate-B commitment differs from verified freeze context")
    if record.committed_at_utc > verification_time_utc:
        raise ValueError("sealed Gate-B commitment is in the verifier's future")
    if (
        record.custodian_key_id != trusted_custodian.key_id
        or record.custodian_public_key_base64 != trusted_custodian.public_key_base64
        or record.custodian_public_key_sha256 != trusted_custodian.public_key_sha256
    ):
        raise AttestationError("sealed Gate-B commitment used an untrusted custodian")
    if (
        record.enrollment_authority_key_id != trusted_enrollment_authority.key_id
        or record.enrollment_authority_public_key_base64
        != trusted_enrollment_authority.public_key_base64
        or record.enrollment_authority_public_key_sha256
        != trusted_enrollment_authority.public_key_sha256
    ):
        raise AttestationError("sealed Gate-B commitment used an untrusted enrollment authority")
    attested = _commitment_attested_payload(record)
    trusted_custodian.verify(
        COMMITMENT_CUSTODIAN_ATTESTATION_DOMAIN,
        attested,
        record.custodian_attestation,
    )
    trusted_enrollment_authority.verify(
        COMMITMENT_AUTHORITY_ATTESTATION_DOMAIN,
        attested,
        record.enrollment_authority_attestation,
    )
    return VerifiedSealedGateBCommitmentV09(record=record, content_sha256=stored)


def _validate_verified_commitment_integrity(
    verified_commitment: VerifiedSealedGateBCommitmentV09,
) -> None:
    if (
        content_sha256(verified_commitment.record.model_dump(mode="json"))
        != verified_commitment.content_sha256
    ):
        raise ValueError("verified Gate-B commitment record was mutated after verification")


class GateALifecycleCompletionV09(ContractModel):
    """Three-role witness for the Gate-A completion sequence and timestamp."""

    protocol: Literal["structure-two-gate-a-lifecycle-completion@0.9"] = (
        "structure-two-gate-a-lifecycle-completion@0.9"
    )
    status: Literal["GATE_A_PASSED_AFTER_SEALED_COMMITMENT"] = (
        "GATE_A_PASSED_AFTER_SEALED_COMMITMENT"
    )
    immutable_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    producer_run_id: str = Field(min_length=1)
    commitment_record_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    gate_a_report_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    gate_a_passed: Literal[True]
    ledger_identifier: str = Field(min_length=1)
    commitment_ledger_sequence: StrictInt = Field(ge=0)
    gate_a_ledger_sequence: StrictInt = Field(ge=0)
    committed_at_utc: datetime
    gate_a_completed_at_utc: datetime
    forbidden_seed_namespaces_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    forbidden_world_seeds: tuple[StrictInt, ...] = Field(min_length=1)
    forbidden_trajectory_seeds: tuple[StrictInt, ...] = Field(min_length=1)
    forbidden_observation_seeds: tuple[StrictInt, ...] = Field(min_length=1)
    executor_key_id: str = Field(min_length=1)
    executor_public_key_base64: str = Field(min_length=1)
    executor_public_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    custodian_key_id: str = Field(min_length=1)
    custodian_public_key_base64: str = Field(min_length=1)
    custodian_public_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    enrollment_authority_key_id: str = Field(min_length=1)
    enrollment_authority_public_key_base64: str = Field(min_length=1)
    enrollment_authority_public_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    executor_attestation: Attestation | None = None
    custodian_attestation: Attestation | None = None
    enrollment_authority_attestation: Attestation | None = None

    @model_validator(mode="after")
    def validate_lifecycle(self) -> Self:
        for label, value in (
            ("producer run ID", self.producer_run_id),
            ("lifecycle ledger identifier", self.ledger_identifier),
            ("executor key ID", self.executor_key_id),
            ("custodian key ID", self.custodian_key_id),
            ("enrollment authority key ID", self.enrollment_authority_key_id),
        ):
            _validate_identifier(value, label=label)
        if (
            len(
                {
                    self.executor_public_key_sha256,
                    self.custodian_public_key_sha256,
                    self.enrollment_authority_public_key_sha256,
                }
            )
            != 3
        ):
            raise ValueError("Gate-A lifecycle witnesses must use three independent keys")
        _validate_utc(self.committed_at_utc, label="Gate-B commitment")
        _validate_utc(self.gate_a_completed_at_utc, label="Gate-A completion")
        if self.commitment_ledger_sequence >= self.gate_a_ledger_sequence:
            raise ValueError("Gate-A ledger sequence must follow Gate-B commitment")
        if self.committed_at_utc >= self.gate_a_completed_at_utc:
            raise ValueError("Gate-A timestamp must follow Gate-B commitment")
        for label, values in (
            ("world", self.forbidden_world_seeds),
            ("trajectory", self.forbidden_trajectory_seeds),
            ("observation", self.forbidden_observation_seeds),
        ):
            if tuple(sorted(set(values))) != values or any(value < 0 for value in values):
                raise ValueError(f"forbidden {label} seeds are not canonical")
        return self


@dataclass(frozen=True, slots=True)
class VerifiedGateALifecycleCompletionV09:
    """A Gate-A lifecycle record that passed all three role signatures."""

    record: GateALifecycleCompletionV09
    content_sha256: str


def _gate_a_lifecycle_attested_payload(
    record: GateALifecycleCompletionV09,
) -> dict[str, Any]:
    return attested_payload(
        record,
        exclude=frozenset(
            {
                "executor_attestation",
                "custodian_attestation",
                "enrollment_authority_attestation",
            }
        ),
    )


def prepare_gate_a_lifecycle_completion_record_v0_9(
    *,
    verified_commitment: VerifiedSealedGateBCommitmentV09,
    gate_a_report_content_sha256: str,
    gate_a_passed: bool,
    gate_a_ledger_sequence: int,
    gate_a_completed_at_utc: datetime,
    forbidden_seed_namespaces: ForbiddenSeedNamespacesV09,
    executor: Ed25519AttestationVerifier,
    custodian: Ed25519AttestationVerifier,
    enrollment_authority: Ed25519AttestationVerifier,
) -> GateALifecycleCompletionV09:
    """Prepare an unsigned Gate-A lifecycle record with public keys only."""

    _validate_verified_commitment_integrity(verified_commitment)
    if gate_a_passed is not True:
        raise ValueError("failed Gate A cannot produce a completion witness")
    commitment = verified_commitment.record
    return GateALifecycleCompletionV09(
        immutable_manifest_sha256=commitment.immutable_manifest_sha256,
        producer_run_id=commitment.producer_run_id,
        commitment_record_content_sha256=verified_commitment.content_sha256,
        gate_a_report_content_sha256=gate_a_report_content_sha256,
        gate_a_passed=True,
        ledger_identifier=commitment.ledger_identifier,
        commitment_ledger_sequence=commitment.commitment_ledger_sequence,
        gate_a_ledger_sequence=gate_a_ledger_sequence,
        committed_at_utc=commitment.committed_at_utc,
        gate_a_completed_at_utc=gate_a_completed_at_utc,
        forbidden_seed_namespaces_sha256=forbidden_seed_namespaces.content_sha256,
        forbidden_world_seeds=forbidden_seed_namespaces.world_seeds,
        forbidden_trajectory_seeds=forbidden_seed_namespaces.trajectory_seeds,
        forbidden_observation_seeds=forbidden_seed_namespaces.observation_seeds,
        executor_key_id=executor.key_id,
        executor_public_key_base64=executor.public_key_base64,
        executor_public_key_sha256=executor.public_key_sha256,
        custodian_key_id=custodian.key_id,
        custodian_public_key_base64=custodian.public_key_base64,
        custodian_public_key_sha256=custodian.public_key_sha256,
        enrollment_authority_key_id=enrollment_authority.key_id,
        enrollment_authority_public_key_base64=(enrollment_authority.public_key_base64),
        enrollment_authority_public_key_sha256=(enrollment_authority.public_key_sha256),
    )


def gate_a_lifecycle_signing_requests_v0_9(
    prepared: GateALifecycleCompletionV09,
) -> dict[str, DetachedSigningRequestV09]:
    """Return executor, custodian, and authority detached requests."""

    if any(
        signature is not None
        for signature in (
            prepared.executor_attestation,
            prepared.custodian_attestation,
            prepared.enrollment_authority_attestation,
        )
    ):
        raise ValueError("Gate-A lifecycle signing requests require an unsigned record")
    payload = _gate_a_lifecycle_attested_payload(prepared)
    role_specs = (
        (
            "executor",
            GATE_A_EXECUTOR_ATTESTATION_DOMAIN,
            prepared.executor_key_id,
            prepared.executor_public_key_base64,
        ),
        (
            "custodian",
            GATE_A_CUSTODIAN_ATTESTATION_DOMAIN,
            prepared.custodian_key_id,
            prepared.custodian_public_key_base64,
        ),
        (
            "enrollment_authority",
            GATE_A_AUTHORITY_ATTESTATION_DOMAIN,
            prepared.enrollment_authority_key_id,
            prepared.enrollment_authority_public_key_base64,
        ),
    )
    return {
        role: _detached_signing_request(
            artifact_protocol=prepared.protocol,
            role=role,
            domain=domain,
            verifier=Ed25519AttestationVerifier.from_public_key_base64(
                key_id=key_id,
                public_key_base64=public_key,
            ),
            payload=payload,
        )
        for role, domain, key_id, public_key in role_specs
    }


def finalize_gate_a_lifecycle_completion_record_v0_9(
    prepared: GateALifecycleCompletionV09,
    *,
    executor_attestation: Attestation | None,
    custodian_attestation: Attestation | None,
    enrollment_authority_attestation: Attestation | None,
    verified_commitment: VerifiedSealedGateBCommitmentV09,
    expected_verified_gate_a_report_content_sha256: str,
    expected_forbidden_seed_namespaces: ForbiddenSeedNamespacesV09,
    trusted_executor: Ed25519AttestationVerifier,
    trusted_custodian: Ed25519AttestationVerifier,
    trusted_enrollment_authority: Ed25519AttestationVerifier,
) -> dict[str, Any]:
    """Finalize three detached signatures using public verifiers only."""

    if any(
        signature is not None
        for signature in (
            prepared.executor_attestation,
            prepared.custodian_attestation,
            prepared.enrollment_authority_attestation,
        )
    ):
        raise ValueError("Gate-A lifecycle finalization requires an unsigned record")
    signed = prepared.model_copy(
        update={
            "executor_attestation": executor_attestation,
            "custodian_attestation": custodian_attestation,
            "enrollment_authority_attestation": enrollment_authority_attestation,
        }
    )
    payload = signed.model_dump(mode="json")
    payload["content_sha256"] = content_sha256(payload)
    verify_gate_a_lifecycle_completion_record_v0_9(
        payload,
        verified_commitment=verified_commitment,
        expected_verified_gate_a_report_content_sha256=(
            expected_verified_gate_a_report_content_sha256
        ),
        expected_forbidden_seed_namespaces=expected_forbidden_seed_namespaces,
        trusted_executor=trusted_executor,
        trusted_custodian=trusted_custodian,
        trusted_enrollment_authority=trusted_enrollment_authority,
    )
    return payload


def make_gate_a_lifecycle_completion_record_v0_9(
    *,
    verified_commitment: VerifiedSealedGateBCommitmentV09,
    gate_a_report_content_sha256: str,
    gate_a_passed: bool,
    gate_a_ledger_sequence: int,
    gate_a_completed_at_utc: datetime,
    forbidden_seed_namespaces: ForbiddenSeedNamespacesV09,
    executor: Ed25519AttestationSigner,
    custodian: Ed25519AttestationSigner,
    enrollment_authority: Ed25519AttestationSigner,
) -> dict[str, Any]:
    """Witness a passed Gate A with three independent Ed25519 roles."""

    prepared = prepare_gate_a_lifecycle_completion_record_v0_9(
        verified_commitment=verified_commitment,
        gate_a_report_content_sha256=gate_a_report_content_sha256,
        gate_a_passed=gate_a_passed,
        gate_a_ledger_sequence=gate_a_ledger_sequence,
        gate_a_completed_at_utc=gate_a_completed_at_utc,
        forbidden_seed_namespaces=forbidden_seed_namespaces,
        executor=executor.verifier(),
        custodian=custodian.verifier(),
        enrollment_authority=enrollment_authority.verifier(),
    )
    requests = gate_a_lifecycle_signing_requests_v0_9(prepared)
    return finalize_gate_a_lifecycle_completion_record_v0_9(
        prepared,
        executor_attestation=sign_detached_request_v0_9(requests["executor"], signer=executor),
        custodian_attestation=sign_detached_request_v0_9(requests["custodian"], signer=custodian),
        enrollment_authority_attestation=sign_detached_request_v0_9(
            requests["enrollment_authority"], signer=enrollment_authority
        ),
        verified_commitment=verified_commitment,
        expected_verified_gate_a_report_content_sha256=gate_a_report_content_sha256,
        expected_forbidden_seed_namespaces=forbidden_seed_namespaces,
        trusted_executor=executor.verifier(),
        trusted_custodian=custodian.verifier(),
        trusted_enrollment_authority=enrollment_authority.verifier(),
    )


def verify_gate_a_lifecycle_completion_record_v0_9(
    payload: Mapping[str, Any],
    *,
    verified_commitment: VerifiedSealedGateBCommitmentV09,
    expected_verified_gate_a_report_content_sha256: str,
    expected_forbidden_seed_namespaces: ForbiddenSeedNamespacesV09,
    trusted_executor: Ed25519AttestationVerifier,
    trusted_custodian: Ed25519AttestationVerifier,
    trusted_enrollment_authority: Ed25519AttestationVerifier,
) -> VerifiedGateALifecycleCompletionV09:
    """Verify Gate-A lifecycle linkage, content, roles, and three signatures."""

    _validate_verified_commitment_integrity(verified_commitment)
    unsigned_payload = dict(payload)
    stored = unsigned_payload.pop("content_sha256", None)
    if not isinstance(stored, str) or content_sha256(unsigned_payload) != stored:
        raise ValueError("Gate-A lifecycle record content hash mismatch")
    record = GateALifecycleCompletionV09.model_validate(unsigned_payload)
    if unsigned_payload != record.model_dump(mode="json"):
        raise ValueError("Gate-A lifecycle record encoding is noncanonical")
    commitment = verified_commitment.record
    expected = {
        "immutable_manifest_sha256": commitment.immutable_manifest_sha256,
        "producer_run_id": commitment.producer_run_id,
        "commitment_record_content_sha256": verified_commitment.content_sha256,
        "gate_a_report_content_sha256": (expected_verified_gate_a_report_content_sha256),
        "forbidden_seed_namespaces_sha256": (expected_forbidden_seed_namespaces.content_sha256),
        "forbidden_world_seeds": expected_forbidden_seed_namespaces.world_seeds,
        "forbidden_trajectory_seeds": (expected_forbidden_seed_namespaces.trajectory_seeds),
        "forbidden_observation_seeds": (expected_forbidden_seed_namespaces.observation_seeds),
        "ledger_identifier": commitment.ledger_identifier,
        "commitment_ledger_sequence": commitment.commitment_ledger_sequence,
        "committed_at_utc": commitment.committed_at_utc,
    }
    dumped = record.model_dump(mode="python")
    if any(dumped[name] != value for name, value in expected.items()):
        raise ValueError(
            "Gate-A lifecycle record differs from verified commitment, Gate-A report, "
            "or forbidden namespaces"
        )
    trusted_roles = (
        (
            "executor",
            trusted_executor,
            record.executor_key_id,
            record.executor_public_key_base64,
            record.executor_public_key_sha256,
            GATE_A_EXECUTOR_ATTESTATION_DOMAIN,
            record.executor_attestation,
        ),
        (
            "custodian",
            trusted_custodian,
            record.custodian_key_id,
            record.custodian_public_key_base64,
            record.custodian_public_key_sha256,
            GATE_A_CUSTODIAN_ATTESTATION_DOMAIN,
            record.custodian_attestation,
        ),
        (
            "enrollment authority",
            trusted_enrollment_authority,
            record.enrollment_authority_key_id,
            record.enrollment_authority_public_key_base64,
            record.enrollment_authority_public_key_sha256,
            GATE_A_AUTHORITY_ATTESTATION_DOMAIN,
            record.enrollment_authority_attestation,
        ),
    )
    attested = _gate_a_lifecycle_attested_payload(record)
    for label, verifier, key_id, public_key, public_key_hash, domain, signature in trusted_roles:
        if (
            key_id != verifier.key_id
            or public_key != verifier.public_key_base64
            or public_key_hash != verifier.public_key_sha256
        ):
            raise AttestationError(f"Gate-A lifecycle used an untrusted {label}")
        verifier.verify(domain, attested, signature)
    return VerifiedGateALifecycleCompletionV09(record=record, content_sha256=stored)


def _validate_verified_gate_a_lifecycle_integrity(
    verified_gate_a_lifecycle: VerifiedGateALifecycleCompletionV09,
) -> None:
    if (
        content_sha256(verified_gate_a_lifecycle.record.model_dump(mode="json"))
        != verified_gate_a_lifecycle.content_sha256
    ):
        raise ValueError("verified Gate-A lifecycle record was mutated after verification")


class SealedGateBOpeningVerificationContextV09(ContractModel):
    """Facts produced by the strict commitment-plus-Gate-A context builder."""

    immutable_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    producer_run_id: str = Field(min_length=1)
    verified_commitment_record_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    verified_gate_a_lifecycle_record_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    verified_gate_a_report_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    verified_gate_a_passed: Literal[True]
    arm_implementation_bundle_sha256: dict[str, str]
    committed_custodian_key_id: str = Field(min_length=1)
    committed_custodian_public_key_base64: str = Field(min_length=1)
    committed_custodian_public_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_sealed_gate_b_commitment_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_opening_attempt_id: str = Field(min_length=16, max_length=128)
    ledger_identifier: str = Field(min_length=1)
    freeze_ledger_sequence: StrictInt = Field(ge=0)
    commitment_ledger_sequence: StrictInt = Field(ge=0)
    gate_a_ledger_sequence: StrictInt = Field(ge=0)
    opening_ledger_sequence: StrictInt = Field(ge=0)
    freeze_completed_at_utc: datetime
    committed_at_utc: datetime
    gate_a_completed_at_utc: datetime
    opened_at_utc: datetime
    forbidden_seed_namespaces_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    forbidden_world_seeds: tuple[StrictInt, ...] = Field(min_length=1)
    forbidden_trajectory_seeds: tuple[StrictInt, ...] = Field(min_length=1)
    forbidden_observation_seeds: tuple[StrictInt, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_context(self) -> Self:
        _validate_identifier(self.producer_run_id, label="producer run ID")
        _validate_identifier(
            self.expected_opening_attempt_id,
            label="opening attempt ID",
            minimum_length=16,
        )
        _validate_identifier(self.ledger_identifier, label="opening ledger identifier")
        _validate_identifier(
            self.committed_custodian_key_id,
            label="committed custodian key ID",
        )
        arm_implementation_bundle_set_sha256_v0_9(self.arm_implementation_bundle_sha256)
        for name, values in (
            ("forbidden world seeds", self.forbidden_world_seeds),
            ("forbidden trajectory seeds", self.forbidden_trajectory_seeds),
            ("forbidden observation seeds", self.forbidden_observation_seeds),
        ):
            if len(set(values)) != len(values) or any(value < 0 for value in values):
                raise ValueError(f"{name} are malformed")
        for name, value in (
            ("freeze completion", self.freeze_completed_at_utc),
            ("Gate-B commitment", self.committed_at_utc),
            ("Gate-A completion", self.gate_a_completed_at_utc),
            ("Gate-B opening", self.opened_at_utc),
        ):
            require_aware(value, name)
            if value.utcoffset() != timedelta(0):
                raise ValueError(f"{name} must use UTC")
        if not (
            self.freeze_ledger_sequence
            < self.commitment_ledger_sequence
            < self.gate_a_ledger_sequence
            < self.opening_ledger_sequence
        ):
            raise ValueError("sealed Gate-B ledger sequence is not strictly increasing")
        if not (
            self.freeze_completed_at_utc
            < self.committed_at_utc
            < self.gate_a_completed_at_utc
            < self.opened_at_utc
        ):
            raise ValueError("sealed Gate-B timestamps are not strictly increasing")
        return self

    @property
    def arm_implementation_bundle_set_sha256(self) -> str:
        return arm_implementation_bundle_set_sha256_v0_9(self.arm_implementation_bundle_sha256)


def build_sealed_gate_b_opening_context_v0_9(
    *,
    verified_commitment: VerifiedSealedGateBCommitmentV09,
    verified_gate_a_lifecycle: VerifiedGateALifecycleCompletionV09,
    opening_ledger_sequence: int,
    opened_at_utc: datetime,
) -> SealedGateBOpeningVerificationContextV09:
    """Derive opening authority from verified commitment and Gate-A witnesses."""

    record = verified_commitment.record
    _validate_verified_commitment_integrity(verified_commitment)
    _validate_verified_gate_a_lifecycle_integrity(verified_gate_a_lifecycle)
    gate_a = verified_gate_a_lifecycle.record
    expected_gate_a_link = {
        "immutable_manifest_sha256": record.immutable_manifest_sha256,
        "producer_run_id": record.producer_run_id,
        "commitment_record_content_sha256": verified_commitment.content_sha256,
        "ledger_identifier": record.ledger_identifier,
        "commitment_ledger_sequence": record.commitment_ledger_sequence,
        "committed_at_utc": record.committed_at_utc,
    }
    dumped_gate_a = gate_a.model_dump(mode="python")
    if any(dumped_gate_a[name] != value for name, value in expected_gate_a_link.items()):
        raise ValueError("verified Gate-A lifecycle does not match verified commitment")
    return SealedGateBOpeningVerificationContextV09(
        immutable_manifest_sha256=record.immutable_manifest_sha256,
        producer_run_id=record.producer_run_id,
        verified_commitment_record_content_sha256=verified_commitment.content_sha256,
        verified_gate_a_lifecycle_record_content_sha256=(verified_gate_a_lifecycle.content_sha256),
        verified_gate_a_report_content_sha256=gate_a.gate_a_report_content_sha256,
        verified_gate_a_passed=True,
        arm_implementation_bundle_sha256=record.arm_implementation_bundle_sha256,
        committed_custodian_key_id=record.custodian_key_id,
        committed_custodian_public_key_base64=record.custodian_public_key_base64,
        committed_custodian_public_key_sha256=record.custodian_public_key_sha256,
        expected_sealed_gate_b_commitment_sha256=(record.sealed_gate_b_commitment_sha256),
        expected_opening_attempt_id=record.opening_attempt_id,
        ledger_identifier=record.ledger_identifier,
        freeze_ledger_sequence=record.freeze_ledger_sequence,
        commitment_ledger_sequence=record.commitment_ledger_sequence,
        gate_a_ledger_sequence=gate_a.gate_a_ledger_sequence,
        opening_ledger_sequence=opening_ledger_sequence,
        freeze_completed_at_utc=record.freeze_completed_at_utc,
        committed_at_utc=record.committed_at_utc,
        gate_a_completed_at_utc=gate_a.gate_a_completed_at_utc,
        opened_at_utc=opened_at_utc,
        forbidden_seed_namespaces_sha256=gate_a.forbidden_seed_namespaces_sha256,
        forbidden_world_seeds=gate_a.forbidden_world_seeds,
        forbidden_trajectory_seeds=gate_a.forbidden_trajectory_seeds,
        forbidden_observation_seeds=gate_a.forbidden_observation_seeds,
    )


def verify_and_build_sealed_gate_b_opening_context_v0_9(
    commitment_payload: Mapping[str, Any],
    gate_a_lifecycle_payload: Mapping[str, Any],
    *,
    expected_immutable_manifest_sha256: str,
    expected_producer_run_id: str,
    expected_arm_implementation_bundle_sha256: Mapping[str, str],
    expected_ledger_identifier: str,
    expected_freeze_ledger_sequence: int,
    expected_freeze_completed_at_utc: datetime,
    trusted_custodian: Ed25519AttestationVerifier,
    trusted_enrollment_authority: Ed25519AttestationVerifier,
    verification_time_utc: datetime,
    trusted_executor: Ed25519AttestationVerifier,
    expected_verified_gate_a_report_content_sha256: str,
    expected_forbidden_seed_namespaces: ForbiddenSeedNamespacesV09,
    opening_ledger_sequence: int,
    opened_at_utc: datetime,
) -> SealedGateBOpeningVerificationContextV09:
    """Verify both signed lifecycle records and derive the trusted context."""

    verified_commitment = verify_sealed_gate_b_commitment_record_v0_9(
        commitment_payload,
        expected_immutable_manifest_sha256=expected_immutable_manifest_sha256,
        expected_producer_run_id=expected_producer_run_id,
        expected_arm_implementation_bundle_sha256=(expected_arm_implementation_bundle_sha256),
        expected_ledger_identifier=expected_ledger_identifier,
        expected_freeze_ledger_sequence=expected_freeze_ledger_sequence,
        expected_freeze_completed_at_utc=expected_freeze_completed_at_utc,
        trusted_custodian=trusted_custodian,
        trusted_enrollment_authority=trusted_enrollment_authority,
        verification_time_utc=verification_time_utc,
    )
    verified_gate_a_lifecycle = verify_gate_a_lifecycle_completion_record_v0_9(
        gate_a_lifecycle_payload,
        verified_commitment=verified_commitment,
        expected_verified_gate_a_report_content_sha256=(
            expected_verified_gate_a_report_content_sha256
        ),
        expected_forbidden_seed_namespaces=expected_forbidden_seed_namespaces,
        trusted_executor=trusted_executor,
        trusted_custodian=trusted_custodian,
        trusted_enrollment_authority=trusted_enrollment_authority,
    )
    return build_sealed_gate_b_opening_context_v0_9(
        verified_commitment=verified_commitment,
        verified_gate_a_lifecycle=verified_gate_a_lifecycle,
        opening_ledger_sequence=opening_ledger_sequence,
        opened_at_utc=opened_at_utc,
    )


class SealedGateBOpeningV09(ContractModel):
    protocol: Literal["structure-two-sealed-gate-b-opening@0.9"] = (
        "structure-two-sealed-gate-b-opening@0.9"
    )
    evaluation_set_role: Literal["custodian_sealed_confirmatory_gate_b"] = (
        "custodian_sealed_confirmatory_gate_b"
    )
    status: Literal["OPENED_ONCE_AFTER_PASSED_GATE_A"] = "OPENED_ONCE_AFTER_PASSED_GATE_A"
    immutable_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    producer_run_id: str = Field(min_length=1)
    commitment_record_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    gate_a_lifecycle_record_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    gate_a_report_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    gate_a_passed: Literal[True]
    forbidden_seed_namespaces_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    arm_implementation_bundle_set_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sealed_gate_b_commitment_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    opening_attempt_id: str = Field(min_length=16, max_length=128)
    ledger_identifier: str = Field(min_length=1)
    freeze_ledger_sequence: StrictInt = Field(ge=0)
    commitment_ledger_sequence: StrictInt = Field(ge=0)
    gate_a_ledger_sequence: StrictInt = Field(ge=0)
    opening_ledger_sequence: StrictInt = Field(ge=0)
    freeze_completed_at_utc: datetime
    committed_at_utc: datetime
    gate_a_completed_at_utc: datetime
    opened_at_utc: datetime
    commitment_nonce: str = Field(min_length=16)
    world_distribution: dict[str, Any]
    world_seeds: tuple[StrictInt, ...]
    trajectory_seeds: tuple[StrictInt, ...]
    observation_seeds: tuple[StrictInt, ...]
    estimator: dict[str, float | int]
    bootstrap_draws: Literal[4000]
    custodian_key_id: str = Field(min_length=1)
    custodian_public_key_base64: str = Field(min_length=1)
    custodian_public_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    custodian_attestation: Attestation | None = None

    @model_validator(mode="after")
    def validate_opening(self) -> Self:
        _validate_identifier(self.producer_run_id, label="producer run ID")
        _validate_identifier(
            self.opening_attempt_id,
            label="opening attempt ID",
            minimum_length=16,
        )
        _validate_identifier(self.ledger_identifier, label="opening ledger identifier")
        _validate_opening_material(
            world_distribution=self.world_distribution,
            world_seeds=self.world_seeds,
            trajectory_seeds=self.trajectory_seeds,
            observation_seeds=self.observation_seeds,
            estimator=self.estimator,
            bootstrap_draws=self.bootstrap_draws,
            commitment_nonce=self.commitment_nonce,
        )
        for name, value in (
            ("freeze completion", self.freeze_completed_at_utc),
            ("Gate-B commitment", self.committed_at_utc),
            ("Gate-A completion", self.gate_a_completed_at_utc),
            ("Gate-B opening", self.opened_at_utc),
        ):
            require_aware(value, name)
            if value.utcoffset() != timedelta(0):
                raise ValueError(f"{name} must use UTC")
        if not (
            self.freeze_ledger_sequence
            < self.commitment_ledger_sequence
            < self.gate_a_ledger_sequence
            < self.opening_ledger_sequence
        ):
            raise ValueError("sealed Gate-B ledger sequence is not strictly increasing")
        if not (
            self.freeze_completed_at_utc
            < self.committed_at_utc
            < self.gate_a_completed_at_utc
            < self.opened_at_utc
        ):
            raise ValueError("sealed Gate-B timestamps are not strictly increasing")
        return self


def _opening_attested_payload(record: SealedGateBOpeningV09) -> dict[str, Any]:
    return attested_payload(record, exclude=frozenset({"custodian_attestation"}))


def _validate_context_bindings(
    record: SealedGateBOpeningV09,
    context: SealedGateBOpeningVerificationContextV09,
) -> None:
    expected = {
        "immutable_manifest_sha256": context.immutable_manifest_sha256,
        "producer_run_id": context.producer_run_id,
        "commitment_record_content_sha256": (context.verified_commitment_record_content_sha256),
        "gate_a_lifecycle_record_content_sha256": (
            context.verified_gate_a_lifecycle_record_content_sha256
        ),
        "gate_a_report_content_sha256": (context.verified_gate_a_report_content_sha256),
        "gate_a_passed": context.verified_gate_a_passed,
        "forbidden_seed_namespaces_sha256": (context.forbidden_seed_namespaces_sha256),
        "arm_implementation_bundle_set_sha256": (context.arm_implementation_bundle_set_sha256),
        "custodian_key_id": context.committed_custodian_key_id,
        "custodian_public_key_base64": context.committed_custodian_public_key_base64,
        "custodian_public_key_sha256": context.committed_custodian_public_key_sha256,
        "sealed_gate_b_commitment_sha256": (context.expected_sealed_gate_b_commitment_sha256),
        "opening_attempt_id": context.expected_opening_attempt_id,
        "ledger_identifier": context.ledger_identifier,
        "freeze_ledger_sequence": context.freeze_ledger_sequence,
        "commitment_ledger_sequence": context.commitment_ledger_sequence,
        "gate_a_ledger_sequence": context.gate_a_ledger_sequence,
        "opening_ledger_sequence": context.opening_ledger_sequence,
        "freeze_completed_at_utc": context.freeze_completed_at_utc,
        "committed_at_utc": context.committed_at_utc,
        "gate_a_completed_at_utc": context.gate_a_completed_at_utc,
        "opened_at_utc": context.opened_at_utc,
    }
    dumped = record.model_dump(mode="python")
    if any(dumped[name] != value for name, value in expected.items()):
        raise ValueError("sealed Gate-B opening differs from verified lifecycle context")
    overlap_labels = tuple(
        label
        for label, opened, forbidden in (
            ("world", record.world_seeds, context.forbidden_world_seeds),
            (
                "trajectory",
                record.trajectory_seeds,
                context.forbidden_trajectory_seeds,
            ),
            (
                "observation",
                record.observation_seeds,
                context.forbidden_observation_seeds,
            ),
        )
        if set(opened) & set(forbidden)
    )
    if overlap_labels:
        raise ValueError(
            "sealed Gate-B opening reuses forbidden " + ", ".join(overlap_labels) + " seeds"
        )
    _validate_independent_commitment(record)


def _validate_independent_commitment(record: SealedGateBOpeningV09) -> None:
    recomputed_commitment = sealed_gate_b_commitment_sha256_v0_9(
        immutable_manifest_sha256=record.immutable_manifest_sha256,
        producer_run_id=record.producer_run_id,
        arm_implementation_bundle_set_sha256=(record.arm_implementation_bundle_set_sha256),
        world_distribution=record.world_distribution,
        world_seeds=record.world_seeds,
        trajectory_seeds=record.trajectory_seeds,
        observation_seeds=record.observation_seeds,
        estimator=record.estimator,
        bootstrap_draws=record.bootstrap_draws,
        commitment_nonce=record.commitment_nonce,
    )
    if recomputed_commitment != record.sealed_gate_b_commitment_sha256:
        raise ValueError("sealed Gate-B opening does not match its independent commitment")


def make_sealed_gate_b_opening_v0_9(
    *,
    context: SealedGateBOpeningVerificationContextV09,
    world_distribution: Mapping[str, Any],
    world_seeds: Sequence[int],
    trajectory_seeds: Sequence[int],
    observation_seeds: Sequence[int],
    estimator: Mapping[str, float | int],
    bootstrap_draws: int,
    commitment_nonce: str,
    custodian: Ed25519AttestationSigner,
) -> dict[str, Any]:
    """Open committed Gate-B material and bind it to the passed Gate-A state."""

    verifier = custodian.verifier()
    unsigned = SealedGateBOpeningV09(
        immutable_manifest_sha256=context.immutable_manifest_sha256,
        producer_run_id=context.producer_run_id,
        commitment_record_content_sha256=(context.verified_commitment_record_content_sha256),
        gate_a_lifecycle_record_content_sha256=(
            context.verified_gate_a_lifecycle_record_content_sha256
        ),
        gate_a_report_content_sha256=(context.verified_gate_a_report_content_sha256),
        gate_a_passed=True,
        forbidden_seed_namespaces_sha256=context.forbidden_seed_namespaces_sha256,
        arm_implementation_bundle_set_sha256=(context.arm_implementation_bundle_set_sha256),
        sealed_gate_b_commitment_sha256=(context.expected_sealed_gate_b_commitment_sha256),
        opening_attempt_id=context.expected_opening_attempt_id,
        ledger_identifier=context.ledger_identifier,
        freeze_ledger_sequence=context.freeze_ledger_sequence,
        commitment_ledger_sequence=context.commitment_ledger_sequence,
        gate_a_ledger_sequence=context.gate_a_ledger_sequence,
        opening_ledger_sequence=context.opening_ledger_sequence,
        freeze_completed_at_utc=context.freeze_completed_at_utc,
        committed_at_utc=context.committed_at_utc,
        gate_a_completed_at_utc=context.gate_a_completed_at_utc,
        opened_at_utc=context.opened_at_utc,
        commitment_nonce=commitment_nonce,
        world_distribution=dict(world_distribution),
        world_seeds=tuple(world_seeds),
        trajectory_seeds=tuple(trajectory_seeds),
        observation_seeds=tuple(observation_seeds),
        estimator=dict(estimator),
        bootstrap_draws=bootstrap_draws,
        custodian_key_id=verifier.key_id,
        custodian_public_key_base64=verifier.public_key_base64,
        custodian_public_key_sha256=verifier.public_key_sha256,
    )
    _validate_context_bindings(unsigned, context)
    signed = unsigned.model_copy(
        update={
            "custodian_attestation": custodian.sign(
                ATTESTATION_DOMAIN,
                _opening_attested_payload(unsigned),
            )
        }
    )
    payload = signed.model_dump(mode="json")
    payload["content_sha256"] = content_sha256(payload)
    return payload


def verify_sealed_gate_b_opening_v0_9(
    payload: Mapping[str, Any],
    *,
    context: SealedGateBOpeningVerificationContextV09,
    trusted_custodian: Ed25519AttestationVerifier,
    consumed_attempt_ids: Set[str] = frozenset(),
) -> SealedGateBOpeningV09:
    """Verify content, lifecycle, commitment, custody, and replay boundaries."""

    unsigned_payload = dict(payload)
    stored = unsigned_payload.pop("content_sha256", None)
    if not isinstance(stored, str) or content_sha256(unsigned_payload) != stored:
        raise ValueError("sealed Gate-B opening content hash mismatch")
    record = SealedGateBOpeningV09.model_validate(unsigned_payload)
    if unsigned_payload != record.model_dump(mode="json"):
        raise ValueError("sealed Gate-B opening encoding is noncanonical")
    _validate_context_bindings(record, context)
    if (
        record.custodian_key_id != trusted_custodian.key_id
        or record.custodian_public_key_base64 != trusted_custodian.public_key_base64
        or record.custodian_public_key_sha256 != trusted_custodian.public_key_sha256
    ):
        raise AttestationError("sealed Gate-B opening used an untrusted custodian")
    trusted_custodian.verify(
        ATTESTATION_DOMAIN,
        _opening_attested_payload(record),
        record.custodian_attestation,
    )
    if record.opening_attempt_id in consumed_attempt_ids:
        raise ValueError("sealed Gate-B opening attempt was already consumed")
    return record


def verify_and_consume_sealed_gate_b_opening_v0_9(
    payload: Mapping[str, Any],
    *,
    context: SealedGateBOpeningVerificationContextV09,
    trusted_custodian: Ed25519AttestationVerifier,
    consumed_attempt_ids: MutableSet[str],
) -> SealedGateBOpeningV09:
    """Verify then mark one attempt consumed in a caller-owned local registry."""

    record = verify_sealed_gate_b_opening_v0_9(
        payload,
        context=context,
        trusted_custodian=trusted_custodian,
        consumed_attempt_ids=consumed_attempt_ids,
    )
    consumed_attempt_ids.add(record.opening_attempt_id)
    return record


@dataclass(frozen=True, slots=True)
class RecomputedSealedGateBHoldoutV09:
    """Deterministic Gate-B worlds/rollouts produced from a verified opening."""

    opening: SealedGateBOpeningV09
    worlds: tuple[Any, ...]
    world_rollouts: tuple[tuple[Any, Any], ...]
    world_rows: tuple[dict[str, Any], ...]
    rollout_rows: tuple[dict[str, Any], ...]
    metrics: dict[str, float]

    @property
    def episode_ids(self) -> tuple[str, ...]:
        return tuple(str(row["rollout_id"]) for row in self.rollout_rows)


def recompute_sealed_gate_b_holdout_v0_9(
    opening: SealedGateBOpeningV09,
) -> RecomputedSealedGateBHoldoutV09:
    """Regenerate canonical worlds and episodes without changing opening identity."""

    # v0.8's computation is deterministic and does not consult its role label.
    # The temporary projection is computation-only; the returned object keeps
    # the v0.9 sealed opening and therefore cannot masquerade as Gate-A evidence.
    _validate_independent_commitment(opening)
    projection = FrozenHoldoutOpeningV08(
        protocol="structure-two-public-validation-opening@0.8",
        evaluation_set_role="public_preregistered_validation",
        immutable_manifest_sha256=opening.immutable_manifest_sha256,
        producer_run_id=opening.producer_run_id,
        seed_opening_nonce=opening.commitment_nonce,
        holdout_opening_nonce=opening.commitment_nonce,
        world_distribution=opening.world_distribution,
        validation_world_seeds=opening.world_seeds,
        trajectory_seeds=opening.trajectory_seeds,
        observation_seeds=opening.observation_seeds,
        estimator=opening.estimator,
        bootstrap_draws=opening.bootstrap_draws,
    )
    recomputed = recompute_frozen_holdout_v0_8(projection)
    return RecomputedSealedGateBHoldoutV09(
        opening=opening,
        worlds=recomputed.worlds,
        world_rollouts=recomputed.world_rollouts,
        world_rows=recomputed.world_rows,
        rollout_rows=recomputed.rollout_rows,
        metrics=recomputed.metrics,
    )


def load_and_verify_sealed_gate_b_opening_v0_9(
    path: Path,
    *,
    context: SealedGateBOpeningVerificationContextV09,
    trusted_custodian: Ed25519AttestationVerifier,
    consumed_attempt_ids: Set[str] = frozenset(),
) -> SealedGateBOpeningV09:
    """Load a JSON artifact and apply the full v0.9 verifier."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("sealed Gate-B opening JSON must be an object")
    return verify_sealed_gate_b_opening_v0_9(
        payload,
        context=context,
        trusted_custodian=trusted_custodian,
        consumed_attempt_ids=consumed_attempt_ids,
    )


__all__ = [
    "ATTESTATION_DOMAIN",
    "COMMITMENT_AUTHORITY_ATTESTATION_DOMAIN",
    "COMMITMENT_CUSTODIAN_ATTESTATION_DOMAIN",
    "COMMITMENT_PROTOCOL_ID",
    "COMMITMENT_RECORD_PROTOCOL_ID",
    "DETACHED_SIGNING_REQUEST_PROTOCOL_ID",
    "EVALUATION_SET_ROLE",
    "EXACT_BOOTSTRAP_DRAWS",
    "EXACT_OBSERVATION_SEED_COUNT",
    "EXACT_TRAJECTORY_SEED_COUNT",
    "EXACT_WORLD_SEED_COUNT",
    "FORBIDDEN_SEED_NAMESPACE_PROTOCOL_ID",
    "GATE_A_AUTHORITY_ATTESTATION_DOMAIN",
    "GATE_A_CUSTODIAN_ATTESTATION_DOMAIN",
    "GATE_A_EXECUTOR_ATTESTATION_DOMAIN",
    "GATE_A_LIFECYCLE_PROTOCOL_ID",
    "IMPLEMENTATION_SET_PROTOCOL_ID",
    "PROTOCOL_ID",
    "DetachedSigningRequestV09",
    "ForbiddenSeedNamespacesV09",
    "GateALifecycleCompletionV09",
    "RecomputedSealedGateBHoldoutV09",
    "SealedGateBCommitmentV09",
    "SealedGateBOpeningV09",
    "SealedGateBOpeningVerificationContextV09",
    "VerifiedGateALifecycleCompletionV09",
    "VerifiedSealedGateBCommitmentV09",
    "arm_implementation_bundle_set_sha256_v0_9",
    "build_sealed_gate_b_opening_context_v0_9",
    "derive_forbidden_seed_namespaces_v0_9",
    "finalize_gate_a_lifecycle_completion_record_v0_9",
    "finalize_sealed_gate_b_commitment_record_v0_9",
    "gate_a_lifecycle_signing_requests_v0_9",
    "load_and_verify_sealed_gate_b_opening_v0_9",
    "make_gate_a_lifecycle_completion_record_v0_9",
    "make_sealed_gate_b_commitment_record_v0_9",
    "make_sealed_gate_b_opening_v0_9",
    "prepare_gate_a_lifecycle_completion_record_v0_9",
    "prepare_sealed_gate_b_commitment_record_v0_9",
    "recompute_sealed_gate_b_holdout_v0_9",
    "sealed_gate_b_commitment_sha256_v0_9",
    "sealed_gate_b_commitment_signing_requests_v0_9",
    "sign_detached_request_v0_9",
    "verify_and_build_sealed_gate_b_opening_context_v0_9",
    "verify_and_consume_sealed_gate_b_opening_v0_9",
    "verify_gate_a_lifecycle_completion_record_v0_9",
    "verify_sealed_gate_b_commitment_record_v0_9",
    "verify_sealed_gate_b_opening_v0_9",
]
