"""Fresh external-custodian seed commitments for Structure Two v0.5.

Unlike v0.4, v0.5 inherits no holdout commitment preimage.  After the public
design and Ed25519 trust anchor are preregistered, the external custodian
generates fresh random seeds and a fresh salt, keeps both secret, and returns
only signed commitments.  Candidate-side code can verify but cannot mint the
record without the preregistered private key.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from pathlib import Path

from pydantic import Field, model_validator

from cpswm.contracts.base import ContractModel
from cpswm.system.attestation import (
    Attestation,
    AttestationError,
    Ed25519AttestationSigner,
    Ed25519AttestationVerifier,
    attested_payload,
)
from cpswm.system.reproducibility import content_sha256

PROTOCOL_ID = "structure-two-world-seed-block-attestation@0.5"
COMMITMENT_PROTOCOL_ID = "structure-two-world-holdout-commitment@0.5"
DOMAIN = "cpswm.evaluation.structure_two.seed_block_attestation.v0.5"
V0_5_SOURCE_BUNDLE_APPS = (
    "apps/evaluation_runner/configure_structure_two_custodian_trust_anchor_v0_5.py",
    "apps/evaluation_runner/generate_structure_two_fresh_seed_block_v0_5.py",
    "apps/evaluation_runner/finalize_structure_two_world_manifest_v0_5.py",
    "apps/evaluation_runner/run_structure_two_world_validation_gate_v0_5.py",
    "apps/evaluation_runner/run_structure_two_world_arm_traces_v0_5.py",
    "apps/evaluation_runner/attest_structure_two_arm_trace_v0_5.py",
    "apps/evaluation_runner/run_structure_two_world_gate_b_v0_5.py",
)
FROZEN_V0_5_SOURCE_BUNDLE_FILE_COUNT = 245
FROZEN_V0_5_SOURCE_BUNDLE_SHA256 = (
    "a9f7ecba788304aec010380bdb2da1b5e5be75723f24c3caf004ab1db8619c4c"
)


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _commitment(world_seed: int, custody_salt: str) -> str:
    return hashlib.sha256(
        f"{COMMITMENT_PROTOCOL_ID}:{world_seed}:{custody_salt}".encode()
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class V05SourceBundle:
    files: tuple[tuple[str, str], ...]
    content_sha256: str


def compute_v0_5_source_bundle(repository_root: Path) -> V05SourceBundle:
    sources = list((repository_root / "src/cpswm").rglob("*.py"))
    sources.extend(repository_root / item for item in V0_5_SOURCE_BUNDLE_APPS)
    missing = [path for path in sources if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"v0.5 source bundle files missing: {missing}")
    rows = tuple(
        (path.relative_to(repository_root).as_posix(), _file_sha256(path))
        for path in sorted(set(sources))
    )
    return V05SourceBundle(
        files=rows,
        content_sha256=content_sha256([list(item) for item in rows]),
    )


def audit_v0_5_source_bundle_evidence(repository_root: Path) -> dict[str, object]:
    """Audit current documents without treating their trust anchor as immutable.

    The original 245-row inventory was not persisted, so the frozen digest cannot
    be recomputed from today's evolving source tree. Signed traces can be verified
    against the key declared by the current manifests, but those manifests have no
    external signature or timestamp proving that the trust anchor is immutable.
    """

    from cpswm.system.evaluation_operations.structure_two_world_gate_b_v0_5 import (
        _verify_trace,
        verify_gate_b_report_v0_5,
    )

    draft_path = repository_root / (
        "configs/project_two_experiments/structure_two_world_generator_manifest_v0_5_DRAFT.json"
    )
    final_path = repository_root / (
        "configs/project_two_experiments/structure_two_world_generator_manifest_v0_5.json"
    )
    result_path = repository_root / (
        "benchmarks/structure_two/structure_two_world_dual_gate_authorization_v0_5.json"
    )
    manifest_payloads: dict[str, dict[str, object]] = {}
    documents: list[tuple[str, int | None, str]] = []
    for label, path in (("draft_manifest", draft_path), ("final_manifest", final_path)):
        payload = json.loads(path.read_text(encoding="utf-8"))
        manifest_payloads[label] = payload
        contract = payload["gate_b_contract"]
        documents.append(
            (
                label,
                int(contract["producer_source_bundle_file_count"]),
                str(contract["producer_source_bundle_sha256"]),
            )
        )
    result = verify_gate_b_report_v0_5(
        result_path, repository_root=repository_root, recompute=False
    )
    documents.append(("gate_b_result", None, str(result["producer_source_bundle_sha256"])))
    trace_paths = sorted(
        (repository_root / "benchmarks/structure_two/gate_b_arm_traces_v0_5").glob("*.json")
    )
    if not trace_paths:
        raise ValueError("v0.5 signed arm traces are missing")
    final_manifest = manifest_payloads["final_manifest"]
    final_contract = final_manifest["gate_b_contract"]
    final_authorization = final_manifest["freeze_authorization"]
    if not isinstance(final_contract, dict) or not isinstance(final_authorization, dict):
        raise ValueError("v0.5 final manifest evidence sections are malformed")
    key_id = str(final_authorization["trusted_custodian_key_id"])
    public_hash = str(final_authorization["trusted_custodian_public_key_sha256"])
    expected_arms = {str(item) for item in final_contract["expected_arms"]}
    expected_manifest_sha256 = _file_sha256(final_path)
    observed_arms: set[str] = set()
    observed_runs: set[str] = set()
    trace_bindings_verified = True
    for path in trace_paths:
        trace = json.loads(path.read_text(encoding="utf-8"))
        record = _verify_trace(trace, key_id=key_id, public_key_sha256=public_hash)
        observed_arms.add(record.arm)
        observed_runs.add(record.producer_run_id)
        trace_bindings_verified = trace_bindings_verified and (
            record.manifest_sha256 == expected_manifest_sha256
            and record.producer_source_bundle_sha256 == FROZEN_V0_5_SOURCE_BUNDLE_SHA256
            and record.gate_a_content_sha256 == result["gate_a_content_sha256"]
        )
        documents.append(
            (
                f"signed_trace:{path.name}",
                None,
                str(trace["producer_source_bundle_sha256"]),
            )
        )

    digest_fields_match = all(
        digest == FROZEN_V0_5_SOURCE_BUNDLE_SHA256
        and (count is None or count == FROZEN_V0_5_SOURCE_BUNDLE_FILE_COUNT)
        for _, count, digest in documents
    )
    current = compute_v0_5_source_bundle(repository_root)
    current_compatible = (
        len(current.files) == FROZEN_V0_5_SOURCE_BUNDLE_FILE_COUNT
        and current.content_sha256 == FROZEN_V0_5_SOURCE_BUNDLE_SHA256
    )
    draft_authorization = manifest_payloads["draft_manifest"]["freeze_authorization"]
    authorization_cross_document_consistent = draft_authorization == final_authorization
    result_bindings_verified = (
        result["manifest_sha256"] == expected_manifest_sha256
        and result["producer_source_bundle_sha256"] == FROZEN_V0_5_SOURCE_BUNDLE_SHA256
        and observed_runs == {str(result["producer_run_id"])}
        and observed_arms == expected_arms
    )
    signed_trace_chain_verified = trace_bindings_verified and result_bindings_verified
    trust_anchor_externally_immutable = bool(
        final_authorization.get("user_approval_is_cryptographic_signature") is True
    )
    return {
        "protocol": "structure-two-world-v0.5-source-bundle-audit@0.2",
        "historical_inventory_recomputable": False,
        "historical_inventory_blocker": "frozen 245-row path/hash inventory was not persisted",
        "historical_digest_field_consistency_verified": digest_fields_match,
        "signed_trace_content_hashes_verified": True,
        "signed_trace_ed25519_verified_against_manifest_trust_anchor": True,
        "trace_set_and_result_bindings_verified": signed_trace_chain_verified,
        "gate_b_result_content_integrity_verified": True,
        "trust_anchor_cross_document_consistent": authorization_cross_document_consistent,
        "trust_anchor_externally_immutable": trust_anchor_externally_immutable,
        "historical_evidence_authenticity_and_integrity_verified": False,
        "historical_authenticity_blocker": (
            "the 245-row inventory is absent and the manifest trust anchor has no "
            "external cryptographic signature or immutable timestamp"
        ),
        "historical_binding_document_count": len(documents),
        "frozen_file_count": FROZEN_V0_5_SOURCE_BUNDLE_FILE_COUNT,
        "frozen_source_bundle_sha256": FROZEN_V0_5_SOURCE_BUNDLE_SHA256,
        "current_file_count": len(current.files),
        "current_source_bundle_sha256": current.content_sha256,
        "current_worktree_compatible_with_frozen_v0_5": current_compatible,
        "historical_evidence_rewritten": False,
    }


class FreshSeedAssertions(ContractModel):
    generated_after_public_design_and_trust_anchor_freeze: bool
    generated_with_os_cryptographic_randomness: bool
    raw_holdout_seed_count_matches_manifest: bool
    raw_holdout_seeds_are_unique: bool
    raw_holdout_seeds_are_disjoint_from_all_public_spent_seeds: bool
    raw_holdout_seeds_and_custody_salt_never_entered_candidate_environment: bool
    private_key_never_entered_candidate_environment: bool


class StructureTwoFreshSeedBlockAttestation(ContractModel):
    protocol: str = Field(pattern=r"^structure-two-world-seed-block-attestation@0\.5$")
    status: str = Field(pattern=r"^custodian-attested-fresh-seed-block$")
    custodian_run_id: str = Field(min_length=1)
    draft_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    train_artifact_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    commitment_protocol: str = Field(pattern=r"^structure-two-world-holdout-commitment@0\.5$")
    holdout_seed_count: int = Field(gt=0)
    holdout_seed_commitments: tuple[str, ...]
    holdout_commitment_set_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    public_spent_seed_set_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    custodian_public_key_base64: str = Field(min_length=1)
    custodian_public_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    assertions: FreshSeedAssertions
    attestation: Attestation | None = None

    @model_validator(mode="after")
    def validate_commitment_shape(self) -> StructureTwoFreshSeedBlockAttestation:
        commitments = self.holdout_seed_commitments
        if len(commitments) != self.holdout_seed_count:
            raise ValueError("fresh commitment count mismatch")
        if len(set(commitments)) != self.holdout_seed_count:
            raise ValueError("fresh commitments must be unique")
        malformed = any(
            len(item) != 64 or any(c not in "0123456789abcdef" for c in item)
            for item in commitments
        )
        if malformed:
            raise ValueError("fresh commitments must be lowercase SHA-256 values")
        if self.holdout_commitment_set_sha256 != content_sha256(sorted(commitments)):
            raise ValueError("fresh commitment-set hash mismatch")
        return self


def load_preregistered_v0_5_authorization(
    draft_manifest_path: Path,
) -> tuple[str, str, str]:
    draft = json.loads(draft_manifest_path.read_text(encoding="utf-8"))
    if draft.get("protocol") != "structure-two-world-generator-validation-gate@0.5":
        raise ValueError("v0.5 draft protocol mismatch")
    if draft.get("status") not in {
        "DRAFT-awaiting-external-custodian-public-key",
        "DRAFT-trust-anchor-frozen-awaiting-seed-attestation",
    }:
        raise ValueError("v0.5 draft is not in a signable preregistration state")
    authorization = draft.get("freeze_authorization", {})
    if authorization.get("configured_before_custodian_seed_generation") is not True:
        raise ValueError("v0.5 custodian trust anchor is not preregistered")
    key_id = str(authorization.get("trusted_custodian_key_id", ""))
    public_hash = str(authorization.get("trusted_custodian_public_key_sha256", ""))
    approval_id = str(authorization.get("user_approval_id", ""))
    if (
        not key_id
        or "TO BE SET" in key_id
        or len(public_hash) != 64
        or any(item not in "0123456789abcdef" for item in public_hash)
        or not approval_id
        or "TO BE SET" in approval_id
    ):
        raise ValueError("v0.5 freeze authorization is incomplete")
    return key_id, public_hash, approval_id


def generate_fresh_seed_block_attestation(
    *,
    draft_manifest_path: Path,
    train_artifact_content_sha256: str,
    signer: Ed25519AttestationSigner,
    custodian_run_id: str,
    holdout_seed_count: int,
) -> tuple[StructureTwoFreshSeedBlockAttestation, tuple[int, ...], str]:
    """Generate secrets and the public record; run only in the custodian environment."""

    key_id, public_hash, _ = load_preregistered_v0_5_authorization(draft_manifest_path)
    verifier = signer.verifier()
    if signer.key_id != key_id or verifier.public_key_sha256 != public_hash:
        raise ValueError("fresh seed signer differs from the preregistered trust anchor")
    if holdout_seed_count <= 0:
        raise ValueError("fresh holdout seed count must be positive")
    draft = json.loads(draft_manifest_path.read_text(encoding="utf-8"))
    split = draft["split_policy"]
    expected_count = int(split["sealed_holdout_world_count"])
    if holdout_seed_count != expected_count:
        raise ValueError("fresh holdout seed count differs from the public design")
    public_spent = {
        *(int(item) for item in split["train_world_seeds_spent_for_tuning"]),
        *(int(item) for item in split["prior_validation_world_seeds_spent"]),
        *(int(item) for item in split["v0_5_validation_world_seeds_preregistered_not_generated"]),
    }
    raw: set[int] = set()
    while len(raw) < holdout_seed_count:
        candidate = secrets.randbits(63)
        if candidate > 0 and candidate not in public_spent:
            raw.add(candidate)
    raw_seeds = tuple(sorted(raw))
    custody_salt = secrets.token_hex(32)
    commitments = tuple(_commitment(seed, custody_salt) for seed in raw_seeds)
    unsigned = StructureTwoFreshSeedBlockAttestation(
        protocol=PROTOCOL_ID,
        status="custodian-attested-fresh-seed-block",
        custodian_run_id=custodian_run_id,
        draft_manifest_sha256=_file_sha256(draft_manifest_path),
        train_artifact_content_sha256=train_artifact_content_sha256,
        commitment_protocol=COMMITMENT_PROTOCOL_ID,
        holdout_seed_count=holdout_seed_count,
        holdout_seed_commitments=commitments,
        holdout_commitment_set_sha256=content_sha256(sorted(commitments)),
        public_spent_seed_set_sha256=content_sha256(sorted(public_spent)),
        custodian_public_key_base64=verifier.public_key_base64,
        custodian_public_key_sha256=verifier.public_key_sha256,
        assertions=FreshSeedAssertions(
            generated_after_public_design_and_trust_anchor_freeze=True,
            generated_with_os_cryptographic_randomness=True,
            raw_holdout_seed_count_matches_manifest=True,
            raw_holdout_seeds_are_unique=True,
            raw_holdout_seeds_are_disjoint_from_all_public_spent_seeds=True,
            raw_holdout_seeds_and_custody_salt_never_entered_candidate_environment=True,
            private_key_never_entered_candidate_environment=True,
        ),
    )
    signed = unsigned.model_copy(
        update={"attestation": signer.sign(DOMAIN, attested_payload(unsigned))}
    )
    return signed, raw_seeds, custody_salt


def verify_fresh_seed_block_attestation(
    record: StructureTwoFreshSeedBlockAttestation,
    *,
    draft_manifest_path: Path,
    expected_train_artifact_content_sha256: str,
) -> None:
    key_id, public_hash, _ = load_preregistered_v0_5_authorization(draft_manifest_path)
    if record.draft_manifest_sha256 != _file_sha256(draft_manifest_path):
        raise AttestationError("fresh seed record names the wrong v0.5 draft")
    if record.train_artifact_content_sha256 != expected_train_artifact_content_sha256:
        raise AttestationError("fresh seed record names the wrong train artifact")
    draft = json.loads(draft_manifest_path.read_text(encoding="utf-8"))
    split = draft["split_policy"]
    if record.holdout_seed_count != int(split["sealed_holdout_world_count"]):
        raise AttestationError("fresh seed record has the wrong holdout count")
    public_spent = sorted(
        {
            *(int(item) for item in split["train_world_seeds_spent_for_tuning"]),
            *(int(item) for item in split["prior_validation_world_seeds_spent"]),
            *(
                int(item)
                for item in split["v0_5_validation_world_seeds_preregistered_not_generated"]
            ),
        }
    )
    if record.public_spent_seed_set_sha256 != content_sha256(public_spent):
        raise AttestationError("fresh seed record names the wrong public spent-seed set")
    if record.custodian_public_key_sha256 != public_hash:
        raise AttestationError("fresh seed record is outside the preregistered trust anchor")
    if not all(record.assertions.model_dump().values()):
        raise AttestationError("fresh seed record contains a false assertion")
    verifier = Ed25519AttestationVerifier.from_public_key_base64(
        key_id=key_id,
        public_key_base64=record.custodian_public_key_base64,
    )
    if verifier.public_key_sha256 != public_hash:
        raise AttestationError("fresh seed embedded public key hash mismatch")
    if record.attestation is None:
        raise AttestationError("fresh seed record has no Ed25519 signature")
    verifier.verify(DOMAIN, attested_payload(record), record.attestation)


def write_fresh_seed_block_attestation(
    record: StructureTwoFreshSeedBlockAttestation, output_path: Path
) -> None:
    if output_path.exists():
        raise FileExistsError("fresh seed attestation already exists")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_fresh_seed_block_attestation(path: Path) -> StructureTwoFreshSeedBlockAttestation:
    return StructureTwoFreshSeedBlockAttestation.model_validate_json(
        path.read_text(encoding="utf-8")
    )


__all__ = [
    "COMMITMENT_PROTOCOL_ID",
    "DOMAIN",
    "PROTOCOL_ID",
    "FreshSeedAssertions",
    "StructureTwoFreshSeedBlockAttestation",
    "V05SourceBundle",
    "compute_v0_5_source_bundle",
    "generate_fresh_seed_block_attestation",
    "load_fresh_seed_block_attestation",
    "load_preregistered_v0_5_authorization",
    "verify_fresh_seed_block_attestation",
    "write_fresh_seed_block_attestation",
]
