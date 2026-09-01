"""External-custodian seed-disjointness attestation for Structure Two v0.4.

The candidate evaluator cannot mint this evidence: creation requires the raw
sealed holdout seeds, their custody salt, and an Ed25519 private key held by the
custodian.  The public artifact discloses none of those secrets.  It only binds
the existing commitment set and the preregistered validation seeds to the
custodian's signed disjointness assertions.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from pydantic import Field

from cpswm.contracts.base import ContractModel
from cpswm.system.attestation import (
    Attestation,
    AttestationError,
    Ed25519AttestationSigner,
    Ed25519AttestationVerifier,
    attested_payload,
)
from cpswm.system.reproducibility import content_sha256

PROTOCOL_ID = "structure-two-world-seed-block-attestation@0.4"
DOMAIN = "cpswm.evaluation.structure_two.seed_block_attestation.v0.4"


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SeedBlockAssertions(ContractModel):
    commitments_recomputed_from_all_raw_holdout_seeds: bool
    raw_holdout_seed_count_matches_manifest: bool
    raw_holdout_seeds_are_unique: bool
    validation_world_seeds_are_disjoint_from_raw_holdout_seeds: bool
    validation_world_seeds_are_disjoint_from_disclosed_train_seeds: bool
    validation_world_seeds_are_disjoint_from_prior_validation_seeds: bool
    raw_holdout_seeds_are_disjoint_from_disclosed_train_seeds: bool
    raw_holdout_seeds_are_disjoint_from_prior_validation_seeds: bool
    raw_holdout_seeds_and_custody_salt_not_disclosed: bool


class StructureTwoSeedBlockAttestation(ContractModel):
    protocol: str = Field(pattern=r"^structure-two-world-seed-block-attestation@0\.4$")
    status: str = Field(pattern=r"^custodian-attested$")
    custodian_run_id: str = Field(min_length=1)
    draft_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    base_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    train_artifact_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    holdout_commitment_count: int = Field(gt=0)
    holdout_commitment_set_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    validation_world_seeds: tuple[int, ...]
    disclosed_train_world_seeds: tuple[int, ...]
    prior_validation_world_seeds: tuple[int, ...]
    custodian_public_key_base64: str = Field(min_length=1)
    custodian_public_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    assertions: SeedBlockAssertions
    attestation: Attestation | None = None


def _commitment(protocol: str, world_seed: int, custody_salt: str) -> str:
    return hashlib.sha256(f"{protocol}:{world_seed}:{custody_salt}".encode()).hexdigest()


def load_preregistered_freeze_authorization(
    draft_manifest_path: Path,
) -> tuple[str, str, str]:
    """Return the fixed trust anchor and approval id, or fail closed."""

    draft = json.loads(draft_manifest_path.read_text(encoding="utf-8"))
    authorization = draft.get("freeze_authorization", {})
    if authorization.get("configured_before_custodian_signature") is not True:
        raise ValueError("custodian trust anchor and approval record are not preregistered")
    key_id = str(authorization.get("trusted_custodian_key_id", ""))
    public_key_sha256 = str(authorization.get("trusted_custodian_public_key_sha256", ""))
    user_approval_id = str(authorization.get("user_approval_id", ""))
    if (
        not key_id
        or len(public_key_sha256) != 64
        or any(item not in "0123456789abcdef" for item in public_key_sha256)
        or not user_approval_id
        or "TO BE SET" in key_id
        or "TO BE SET" in user_approval_id
    ):
        raise ValueError("invalid preregistered freeze authorization")
    return key_id, public_key_sha256, user_approval_id


def create_seed_block_attestation(
    *,
    draft_manifest_path: Path,
    base_manifest_path: Path,
    train_artifact_content_sha256: str,
    validation_world_seeds: Sequence[int],
    raw_holdout_world_seeds: Sequence[int],
    custody_salt: str,
    custodian_run_id: str,
    signer: Ed25519AttestationSigner,
) -> StructureTwoSeedBlockAttestation:
    """Validate secret material and return a public, formally signed statement."""

    trusted_key_id, trusted_public_key_sha256, _ = load_preregistered_freeze_authorization(
        draft_manifest_path
    )
    verifier = signer.verifier()
    if signer.key_id != trusted_key_id:
        raise ValueError("signing key id differs from the preregistered trust anchor")
    if verifier.public_key_sha256 != trusted_public_key_sha256:
        raise ValueError("signing public key differs from the preregistered trust anchor")

    payload = json.loads(base_manifest_path.read_text(encoding="utf-8"))
    split = payload["split_policy"]
    commitments = tuple(str(item) for item in split["sealed_holdout_world_seed_commitments"])
    expected_count = int(split["sealed_holdout_world_count"])
    raw = tuple(int(item) for item in raw_holdout_world_seeds)
    validation = tuple(int(item) for item in validation_world_seeds)
    disclosed_train = tuple(int(item) for item in split["train_world_seeds"])
    prior_validation = tuple(int(item) for item in split["validation_world_seeds"])
    if not custody_salt:
        raise ValueError("custody salt must not be empty")
    if len(raw) != expected_count or len(set(raw)) != expected_count:
        raise ValueError("raw holdout seed count or uniqueness mismatch")
    recomputed = tuple(_commitment(str(payload["protocol"]), seed, custody_salt) for seed in raw)
    if Counter(recomputed) != Counter(commitments):
        raise ValueError("raw seeds and custody salt do not reproduce the frozen commitments")
    if set(raw) & set(validation):
        raise ValueError("candidate validation worlds collide with sealed holdout worlds")
    if len(set(validation)) != len(validation):
        raise ValueError("candidate validation world seeds must be unique")
    if set(validation) & set(disclosed_train):
        raise ValueError("candidate validation worlds collide with disclosed train worlds")
    if set(validation) & set(prior_validation):
        raise ValueError("candidate validation worlds collide with prior validation worlds")
    if set(raw) & set(disclosed_train):
        raise ValueError("sealed holdout worlds collide with disclosed train worlds")
    if set(raw) & set(prior_validation):
        raise ValueError("sealed holdout worlds collide with prior validation worlds")

    unsigned = StructureTwoSeedBlockAttestation(
        protocol=PROTOCOL_ID,
        status="custodian-attested",
        custodian_run_id=custodian_run_id,
        draft_manifest_sha256=_file_sha256(draft_manifest_path),
        base_manifest_sha256=_file_sha256(base_manifest_path),
        train_artifact_content_sha256=train_artifact_content_sha256,
        holdout_commitment_count=expected_count,
        holdout_commitment_set_sha256=content_sha256(sorted(commitments)),
        validation_world_seeds=validation,
        disclosed_train_world_seeds=disclosed_train,
        prior_validation_world_seeds=prior_validation,
        custodian_public_key_base64=verifier.public_key_base64,
        custodian_public_key_sha256=verifier.public_key_sha256,
        assertions=SeedBlockAssertions(
            commitments_recomputed_from_all_raw_holdout_seeds=True,
            raw_holdout_seed_count_matches_manifest=True,
            raw_holdout_seeds_are_unique=True,
            validation_world_seeds_are_disjoint_from_raw_holdout_seeds=True,
            validation_world_seeds_are_disjoint_from_disclosed_train_seeds=True,
            validation_world_seeds_are_disjoint_from_prior_validation_seeds=True,
            raw_holdout_seeds_are_disjoint_from_disclosed_train_seeds=True,
            raw_holdout_seeds_are_disjoint_from_prior_validation_seeds=True,
            raw_holdout_seeds_and_custody_salt_not_disclosed=True,
        ),
    )
    return unsigned.model_copy(
        update={"attestation": signer.sign(DOMAIN, attested_payload(unsigned))}
    )


def verify_seed_block_attestation(
    record: StructureTwoSeedBlockAttestation,
    *,
    draft_manifest_path: Path,
    base_manifest_path: Path,
    expected_train_artifact_content_sha256: str,
    expected_validation_world_seeds: Sequence[int],
    trusted_key_id: str,
    trusted_public_key_sha256: str,
) -> None:
    """Fail closed unless content, trust anchor, and formal signature all agree."""

    if record.draft_manifest_sha256 != _file_sha256(draft_manifest_path):
        raise AttestationError("seed attestation names the wrong validation draft")
    try:
        draft_key_id, draft_public_key_sha256, _ = load_preregistered_freeze_authorization(
            draft_manifest_path
        )
    except ValueError as error:
        raise AttestationError(str(error)) from error
    if draft_key_id != trusted_key_id:
        raise AttestationError("caller trust key id differs from the validation draft")
    if draft_public_key_sha256 != trusted_public_key_sha256:
        raise AttestationError("caller public-key hash differs from the validation draft")
    if record.base_manifest_sha256 != _file_sha256(base_manifest_path):
        raise AttestationError("seed attestation names the wrong base manifest")
    if record.train_artifact_content_sha256 != expected_train_artifact_content_sha256:
        raise AttestationError("seed attestation names the wrong train artifact")
    if record.validation_world_seeds != tuple(expected_validation_world_seeds):
        raise AttestationError("seed attestation names the wrong validation worlds")
    payload = json.loads(base_manifest_path.read_text(encoding="utf-8"))
    split = payload["split_policy"]
    expected_train = tuple(int(item) for item in split["train_world_seeds"])
    expected_prior_validation = tuple(int(item) for item in split["validation_world_seeds"])
    if record.disclosed_train_world_seeds != expected_train:
        raise AttestationError("seed attestation names the wrong disclosed train split")
    if record.prior_validation_world_seeds != expected_prior_validation:
        raise AttestationError("seed attestation names the wrong prior validation split")
    commitments = tuple(str(item) for item in split["sealed_holdout_world_seed_commitments"])
    if record.holdout_commitment_count != len(commitments):
        raise AttestationError("seed attestation commitment count mismatch")
    if record.holdout_commitment_set_sha256 != content_sha256(sorted(commitments)):
        raise AttestationError("seed attestation commitment-set hash mismatch")
    if record.custodian_public_key_sha256 != trusted_public_key_sha256:
        raise AttestationError("custodian public key is not the preregistered trust anchor")
    verifier = Ed25519AttestationVerifier.from_public_key_base64(
        key_id=trusted_key_id,
        public_key_base64=record.custodian_public_key_base64,
    )
    if verifier.public_key_sha256 != trusted_public_key_sha256:
        raise AttestationError("embedded custodian key hash mismatch")
    if not all(record.assertions.model_dump().values()):
        raise AttestationError("seed attestation contains a false assertion")
    if record.attestation is None:
        raise AttestationError("seed attestation has no formal signature")
    verifier.verify(DOMAIN, attested_payload(record), record.attestation)


def write_seed_block_attestation(
    record: StructureTwoSeedBlockAttestation,
    output_path: Path,
) -> None:
    if output_path.exists():
        raise FileExistsError("seed attestation already exists; refusing to overwrite")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_seed_block_attestation(path: Path) -> StructureTwoSeedBlockAttestation:
    return StructureTwoSeedBlockAttestation.model_validate_json(path.read_text(encoding="utf-8"))


__all__ = [
    "DOMAIN",
    "PROTOCOL_ID",
    "SeedBlockAssertions",
    "StructureTwoSeedBlockAttestation",
    "create_seed_block_attestation",
    "load_preregistered_freeze_authorization",
    "load_seed_block_attestation",
    "verify_seed_block_attestation",
    "write_seed_block_attestation",
]
