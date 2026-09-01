"""Three-stage external-method fidelity gate for Structure Two v0.6.

Native reproduction, cross-domain adaptation, and efficacy authorization are
separate claims.  A common-interface adapter cannot become a faithful external
reproduction merely by producing different actions or copying one equation.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from cpswm.system.attestation import (
    Attestation,
    AttestationError,
    Ed25519AttestationVerifier,
)
from cpswm.system.reproducibility import content_sha256

PROTOCOL_ID = "structure-two-external-adapter-fidelity-gate@0.2"
EVIDENCE_ATTESTATION_DOMAIN = "cpswm.evaluation.structure_two.external_fidelity.v0.2"
EXECUTION_ATTESTATION_DOMAIN = "cpswm.evaluation.structure_two.external_fidelity.execution.v0.6"


@dataclass(frozen=True, slots=True)
class ExternalMethodSpecification:
    arm: str
    method: str
    native_domain: str
    primary_source_url: str
    required_native_components: tuple[str, ...]
    required_adaptation_inputs: tuple[str, ...]
    official_code_required: bool
    official_code_url: str | None = None
    official_code_commit: str | None = None


@dataclass(frozen=True, slots=True)
class ExternalMethodEvidence:
    arm: str
    primary_source_sha256: str | None = None
    official_code_url: str | None = None
    official_code_commit: str | None = None
    implementation_bundle_sha256: str | None = None
    verified_native_components: tuple[str, ...] = ()
    component_parity_receipt_sha256: str | None = None
    native_protocol_recheck_receipt_sha256: str | None = None
    adaptation_contract_sha256: str | None = None
    adaptation_parity_receipt_sha256: str | None = None
    reviewer_key_id: str | None = None
    reviewer_public_key_base64: str | None = None
    reviewer_public_key_sha256: str | None = None
    attestation: Attestation | None = None


@dataclass(frozen=True, slots=True)
class ExternalEvidenceArtifactPaths:
    primary_source: Path
    implementation_bundle: Path
    component_parity_receipt: Path
    component_parity_execution_log: Path
    native_protocol_recheck_receipt: Path
    native_protocol_execution_log: Path
    adaptation_contract: Path
    adaptation_parity_receipt: Path
    adaptation_parity_execution_log: Path
    official_code_checkout: Path | None = None


def attested_external_method_evidence_payload(
    evidence: ExternalMethodEvidence,
) -> dict[str, Any]:
    payload = asdict(evidence)
    payload.pop("attestation", None)
    return payload


def default_external_method_specifications_v0_2() -> tuple[ExternalMethodSpecification, ...]:
    """Return the six content-independent native-method specifications.

    These rows define what must be reproduced.  They intentionally contain no
    passing evidence and therefore cannot authorize themselves.
    """

    return (
        ExternalMethodSpecification(
            arm="corrected_amg",
            method="Damen-Hogg Activity Manipulation Grammar",
            native_domain="video activity explanation",
            primary_source_url="https://doi.org/10.1109/TPAMI.2011.70",
            official_code_required=False,
            required_adaptation_inputs=(
                "event detections with source likelihoods",
                "event hierarchy attributes and cross-event constraints",
                "actor mechanism and ordered-role evidence",
            ),
            required_native_components=(
                "activity-event hierarchy and attribute representation",
                "shared-variable and physical-consistency constraints",
                "source-likelihood or likelihood-ratio scoring",
                "global multi-event MAP inference",
                "published native activity-explanation protocol recheck",
            ),
        ),
        ExternalMethodSpecification(
            arm="o_star_matched",
            method="O-STaR",
            native_domain="embodied open-vocabulary object search",
            primary_source_url=("https://www.hrl.uni-bonn.de/publications/2026/menon26grc"),
            official_code_required=False,
            required_adaptation_inputs=(
                "3D scene graph with room furniture compartment and object nodes",
                "geometric object-compartment feasibility",
                "positive and negative object observations",
                "navigation and inspection costs",
                "opportunistic non-target observations",
            ),
            required_native_components=(
                "open-vocabulary 3D dynamic scene graph",
                "LLM Day-0 semantic prior",
                "geometric candidate pruning",
                "Dirichlet-Categorical hit and miss updates",
                "Stay+Leak and relaxed transition inference",
                "cost-aware active search",
                "opportunistic multi-target perception",
                "published physical and simulation protocol recheck",
            ),
        ),
        ExternalMethodSpecification(
            arm="active_dreaming_matched",
            method="Active Dreaming Memory",
            native_domain="language-agent episodic-to-semantic memory consolidation",
            primary_source_url="https://engrxiv.org/preprint/view/5919/9826",
            official_code_required=True,
            official_code_url=("https://github.com/KasimVali2207/active-dreaming-memory"),
            official_code_commit="9c05baf41673d10e92c076ba7db18b1b6553a60d",
            required_adaptation_inputs=(
                "action execution failure episodes",
                "content embeddings for failure clustering",
                "executable counterfactual scenario interface",
                "episodic and semantic memory stores",
            ),
            required_native_components=(
                "episodic and semantic dual-store lifecycle",
                "failure-episode retrieval",
                "embedding-based DBSCAN failure clustering",
                "LLM failure-rule abstraction",
                "LLM counterfactual executable-scenario generation",
                "actual scenario execution before semantic commit",
                "published six-domain protocol recheck",
            ),
        ),
        ExternalMethodSpecification(
            arm="auto_dreamer_matched",
            method="Auto-Dreamer",
            native_domain="offline language-agent memory consolidation",
            primary_source_url="https://arxiv.org/abs/2605.20616",
            official_code_required=False,
            required_adaptation_inputs=(
                "cross-session typed memory bank",
                "provenance-linked source trajectories",
                "offline consolidation boundary",
                "downstream task reward and counterfactual masking utility",
            ),
            required_native_components=(
                "fast per-session acquisition and slow offline consolidation",
                "typed-memory working-region selection",
                "read-only evidence and provenance-linked trajectory inspection",
                "bounded consolidator tool use",
                "fresh replacement-set synthesis and supersession",
                "GRPO policy trained on downstream agent performance",
                "published ScienceWorld ALFWorld and WebArena protocol recheck",
            ),
        ),
        ExternalMethodSpecification(
            arm="trustmem_matched",
            method="TRUSTMEM",
            native_domain="trustworthy LLM-agent memory consolidation",
            primary_source_url="https://arxiv.org/abs/2606.25161",
            official_code_required=False,
            required_adaptation_inputs=(
                "candidate WRITE REVISE and PRUNE memory transitions",
                "chunk evidence and previous memory state",
                "downstream retrieval and task outcomes",
                "coverage preservation and faithfulness verifier judgments",
            ),
            required_native_components=(
                "WRITE REVISE and PRUNE candidate transitions",
                "coverage transition verification",
                "preservation transition verification",
                "faithfulness transition verification",
                "same-state candidate preference-pair construction",
                "preference-guided reinforcement learning of update behavior",
                "published MemoryAgentBench HaluMem and Mem-alpha protocol recheck",
            ),
        ),
        ExternalMethodSpecification(
            arm="brainctl_matched",
            method="brainctl",
            native_domain="LLM-agent memory admission and lifecycle control",
            primary_source_url="https://www.brainctl.org/whitepaper",
            official_code_required=True,
            official_code_url="https://github.com/TSchonleber/brainctl",
            official_code_commit="c6348087dd07e54583f762e07bf960ac982019e6",
            required_adaptation_inputs=(
                "memory content and embedding neighborhood",
                "source category and trust class",
                "scope category recall history arousal and valence",
                "existing memory lifecycle and supersession state",
            ),
            required_native_components=(
                "source-trust categories and category-specific priors",
                "embedding-based semantic novelty",
                "utility confidence novelty recency and type-prior worthiness",
                "scope recall arousal and valence factors",
                "two-stage write-decision gate",
                "memory-tier routing",
                "Bayesian confidence and merge supersede reject lifecycle",
                "official repository protocol recheck",
            ),
        ),
    )


def _is_sha256(value: str | None) -> bool:
    return bool(value and len(value) == 64 and all(char in "0123456789abcdef" for char in value))


def external_artifact_sha256(path: Path) -> str:
    """Hash a real file or a deterministic recursive directory bundle."""

    resolved = path.resolve(strict=True)
    if resolved.is_file():
        return hashlib.sha256(resolved.read_bytes()).hexdigest()
    if not resolved.is_dir():
        raise ValueError("external evidence artifact is neither a file nor directory")
    rows = tuple(
        (
            item.relative_to(resolved).as_posix(),
            hashlib.sha256(item.read_bytes()).hexdigest(),
        )
        for item in sorted(resolved.rglob("*"))
        if item.is_file() and ".git" not in item.relative_to(resolved).parts
    )
    if not rows:
        raise ValueError("external evidence directory artifact is empty")
    return content_sha256({"files": rows})


def _verified_json_receipt(
    path: Path,
    *,
    arm: str,
    expected_protocol: str,
    success_field: str | None,
) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    if payload.get("protocol") != expected_protocol or payload.get("arm") != arm:
        return False
    return success_field is None or payload.get(success_field) is True


def _verified_execution_receipt(
    receipt_path: Path,
    execution_log_path: Path,
    *,
    arm: str,
    expected_protocol: str,
    success_field: str,
    implementation_bundle_sha256: str | None,
    trusted_executor_key_id: str | None,
    trusted_executor_public_key_sha256: str | None,
) -> bool:
    try:
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    execution = payload.get("execution")
    if not isinstance(execution, dict):
        return False
    command = execution.get("command")
    checks = (
        payload.get("protocol") == expected_protocol,
        payload.get("arm") == arm,
        payload.get(success_field) is True,
        execution.get("exit_code") == 0,
        isinstance(command, list) and bool(command),
        execution.get("implementation_bundle_sha256") == implementation_bundle_sha256,
        _artifact_matches(execution_log_path, execution.get("log_sha256")),
    )
    if not all(checks):
        return False
    executor_key_id = payload.get("executor_key_id")
    executor_public_key_base64 = payload.get("executor_public_key_base64")
    executor_public_key_sha256 = payload.get("executor_public_key_sha256")
    executor_attestation = payload.get("executor_attestation")
    if not all(
        (
            executor_key_id,
            executor_public_key_base64,
            executor_public_key_sha256,
            executor_attestation,
            trusted_executor_key_id,
            trusted_executor_public_key_sha256,
        )
    ):
        return False
    if (
        executor_key_id != trusted_executor_key_id
        or executor_public_key_sha256 != trusted_executor_public_key_sha256
    ):
        return False
    verifier = Ed25519AttestationVerifier.from_public_key_base64(
        key_id=str(executor_key_id),
        public_key_base64=str(executor_public_key_base64),
    )
    if verifier.public_key_sha256 != trusted_executor_public_key_sha256:
        return False
    attested = dict(payload)
    for key in (
        "executor_key_id",
        "executor_public_key_base64",
        "executor_public_key_sha256",
        "executor_attestation",
    ):
        attested.pop(key, None)
    try:
        verifier.verify(
            EXECUTION_ATTESTATION_DOMAIN,
            attested,
            Attestation.model_validate(executor_attestation),
        )
    except (AttestationError, ValueError):
        return False
    return True


def _artifact_matches(path: Path, expected_sha256: str | None) -> bool:
    if not _is_sha256(expected_sha256):
        return False
    try:
        return external_artifact_sha256(path) == expected_sha256
    except (OSError, ValueError):
        return False


def _git_checkout_matches(path: Path | None, expected_commit: str | None) -> bool:
    if path is None or not expected_commit:
        return False
    try:
        commit = subprocess.run(
            ("git", "-C", str(path.resolve(strict=True)), "rev-parse", "HEAD"),
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return False
    return commit == expected_commit


def _score(
    specification: ExternalMethodSpecification,
    evidence: ExternalMethodEvidence | None,
    *,
    artifact_paths: ExternalEvidenceArtifactPaths | None,
    trusted_reviewer_key_id: str | None,
    trusted_reviewer_public_key_sha256: str | None,
    trusted_executor_key_id: str | None,
    trusted_executor_public_key_sha256: str | None,
) -> dict[str, Any]:
    if not specification.required_native_components:
        raise ValueError(f"external arm {specification.arm} has no native component specification")
    if evidence is None:
        evidence = ExternalMethodEvidence(arm=specification.arm)
    if evidence.arm != specification.arm:
        raise ValueError("external fidelity evidence is bound to the wrong arm")
    required = set(specification.required_native_components)
    verified = set(evidence.verified_native_components)
    component_set_exact = verified == required and len(verified) == len(
        evidence.verified_native_components
    )
    source_bound = bool(
        artifact_paths
        and _artifact_matches(artifact_paths.primary_source, evidence.primary_source_sha256)
    )
    implementation_bound = bool(
        artifact_paths
        and _artifact_matches(
            artifact_paths.implementation_bundle,
            evidence.implementation_bundle_sha256,
        )
    )
    official_code_bound = not specification.official_code_required or bool(
        artifact_paths
        and evidence.official_code_url == specification.official_code_url
        and evidence.official_code_commit == specification.official_code_commit
        and _git_checkout_matches(
            artifact_paths.official_code_checkout,
            specification.official_code_commit,
        )
    )
    component_parity = bool(
        artifact_paths
        and component_set_exact
        and _artifact_matches(
            artifact_paths.component_parity_receipt,
            evidence.component_parity_receipt_sha256,
        )
        and _verified_execution_receipt(
            artifact_paths.component_parity_receipt,
            artifact_paths.component_parity_execution_log,
            arm=specification.arm,
            expected_protocol="structure-two-component-parity-receipt@0.6",
            success_field="component_parity_passed",
            implementation_bundle_sha256=evidence.implementation_bundle_sha256,
            trusted_executor_key_id=trusted_executor_key_id,
            trusted_executor_public_key_sha256=(trusted_executor_public_key_sha256),
        )
    )
    native_protocol_rechecked = bool(
        artifact_paths
        and _artifact_matches(
            artifact_paths.native_protocol_recheck_receipt,
            evidence.native_protocol_recheck_receipt_sha256,
        )
        and _verified_execution_receipt(
            artifact_paths.native_protocol_recheck_receipt,
            artifact_paths.native_protocol_execution_log,
            arm=specification.arm,
            expected_protocol="structure-two-native-protocol-recheck@0.6",
            success_field="native_protocol_reproduction_passed",
            implementation_bundle_sha256=evidence.implementation_bundle_sha256,
            trusted_executor_key_id=trusted_executor_key_id,
            trusted_executor_public_key_sha256=(trusted_executor_public_key_sha256),
        )
    )
    independent_reviewed = False
    has_any_review_material = any(
        (
            evidence.reviewer_key_id,
            evidence.reviewer_public_key_base64,
            evidence.reviewer_public_key_sha256,
            evidence.attestation,
        )
    )
    if has_any_review_material:
        if not all(
            (
                evidence.reviewer_key_id,
                evidence.reviewer_public_key_base64,
                evidence.reviewer_public_key_sha256,
                evidence.attestation,
                trusted_reviewer_key_id,
                trusted_reviewer_public_key_sha256,
            )
        ):
            raise AttestationError("external fidelity reviewer evidence is incomplete")
        if evidence.reviewer_key_id != trusted_reviewer_key_id:
            raise AttestationError("external fidelity evidence uses an untrusted reviewer key")
        if evidence.reviewer_public_key_sha256 != trusted_reviewer_public_key_sha256:
            raise AttestationError("external fidelity reviewer trust-anchor mismatch")
        verifier = Ed25519AttestationVerifier.from_public_key_base64(
            key_id=str(evidence.reviewer_key_id),
            public_key_base64=str(evidence.reviewer_public_key_base64),
        )
        if verifier.public_key_sha256 != trusted_reviewer_public_key_sha256:
            raise AttestationError("external fidelity reviewer public key hash mismatch")
        verifier.verify(
            EVIDENCE_ATTESTATION_DOMAIN,
            attested_external_method_evidence_payload(evidence),
            evidence.attestation,
        )
        independent_reviewed = True
    native_passed = all(
        (
            source_bound,
            implementation_bound,
            official_code_bound,
            component_parity,
            native_protocol_rechecked,
            independent_reviewed,
        )
    )
    adaptation_contract_bound = bool(
        artifact_paths
        and _artifact_matches(
            artifact_paths.adaptation_contract,
            evidence.adaptation_contract_sha256,
        )
        and _verified_json_receipt(
            artifact_paths.adaptation_contract,
            arm=specification.arm,
            expected_protocol="structure-two-external-adaptation-contract@0.6",
            success_field=None,
        )
    )
    adaptation_parity = bool(
        artifact_paths
        and _artifact_matches(
            artifact_paths.adaptation_parity_receipt,
            evidence.adaptation_parity_receipt_sha256,
        )
        and _verified_execution_receipt(
            artifact_paths.adaptation_parity_receipt,
            artifact_paths.adaptation_parity_execution_log,
            arm=specification.arm,
            expected_protocol="structure-two-adaptation-parity-receipt@0.6",
            success_field="adaptation_parity_passed",
            implementation_bundle_sha256=evidence.implementation_bundle_sha256,
            trusted_executor_key_id=trusted_executor_key_id,
            trusted_executor_public_key_sha256=(trusted_executor_public_key_sha256),
        )
    )
    adaptation_passed = native_passed and adaptation_contract_bound and adaptation_parity
    checks = {
        "primary_source_content_bound": source_bound,
        "implementation_bundle_content_bound": implementation_bound,
        "official_code_identity_bound_if_required": official_code_bound,
        "native_component_set_exact_and_parity_tested": component_parity,
        "native_published_protocol_rechecked": native_protocol_rechecked,
        "independent_reviewer_attested": independent_reviewed,
        "adaptation_contract_content_bound": adaptation_contract_bound,
        "adaptation_parity_tested": adaptation_parity,
    }
    return {
        "arm": specification.arm,
        "method": specification.method,
        "native_domain": specification.native_domain,
        "primary_source_url": specification.primary_source_url,
        "required_native_components": specification.required_native_components,
        "verified_native_components": evidence.verified_native_components,
        "checks": checks,
        "native_fidelity_passed": native_passed,
        "adaptation_fidelity_passed": adaptation_passed,
        "missing_requirements": tuple(key for key, passed in checks.items() if not passed),
    }


def run_external_fidelity_gate_v0_2(
    specifications: Sequence[ExternalMethodSpecification],
    evidence_by_arm: Mapping[str, ExternalMethodEvidence],
    *,
    artifact_paths_by_arm: Mapping[str, ExternalEvidenceArtifactPaths] | None = None,
    trusted_reviewer_key_id: str | None = None,
    trusted_reviewer_public_key_sha256: str | None = None,
    trusted_executor_key_id: str | None = None,
    trusted_executor_public_key_sha256: str | None = None,
    enforce_canonical_catalog: bool = True,
) -> dict[str, Any]:
    if not specifications:
        raise ValueError("external fidelity gate requires at least one method")
    arms = tuple(item.arm for item in specifications)
    if len(arms) != len(set(arms)):
        raise ValueError("external method specifications must have unique arms")
    if set(evidence_by_arm) - set(arms):
        raise ValueError("external fidelity evidence contains an undeclared arm")
    if enforce_canonical_catalog and tuple(specifications) != (
        default_external_method_specifications_v0_2()
    ):
        raise ValueError("external fidelity gate requires the canonical six-arm catalog")
    if (
        trusted_reviewer_public_key_sha256 is not None
        and trusted_reviewer_public_key_sha256 == trusted_executor_public_key_sha256
    ):
        raise ValueError("external reviewer and execution attestor must be independent keys")
    artifact_paths_by_arm = artifact_paths_by_arm or {}
    if set(artifact_paths_by_arm) - set(arms):
        raise ValueError("external fidelity artifact paths contain an undeclared arm")
    rows = [
        _score(
            item,
            evidence_by_arm.get(item.arm),
            artifact_paths=artifact_paths_by_arm.get(item.arm),
            trusted_reviewer_key_id=trusted_reviewer_key_id,
            trusted_reviewer_public_key_sha256=trusted_reviewer_public_key_sha256,
            trusted_executor_key_id=trusted_executor_key_id,
            trusted_executor_public_key_sha256=(trusted_executor_public_key_sha256),
        )
        for item in specifications
    ]
    native_passed = all(bool(item["native_fidelity_passed"]) for item in rows)
    adaptation_passed = all(bool(item["adaptation_fidelity_passed"]) for item in rows)
    report: dict[str, Any] = {
        "protocol": PROTOCOL_ID,
        "method_results": rows,
        "native_fidelity_gate_passed": native_passed,
        "adaptation_fidelity_gate_passed": adaptation_passed,
        "external_fidelity_gate_passed": native_passed and adaptation_passed,
        "fidelity_precondition_for_combined_authorization_passed": (
            native_passed and adaptation_passed
        ),
        "external_method_efficacy_comparison_allowed": False,
        "claim_boundary": (
            "Native reproduction evidence supports claims only in each method's native "
            "domain. Cross-domain efficacy claims additionally require a content-bound "
            "adaptation contract and executable adaptation-parity evidence. Even complete "
            "fidelity evidence is only one precondition for the separate combined efficacy "
            "authorization gate."
        ),
    }
    report["content_sha256"] = content_sha256(report)
    return report


__all__ = [
    "EVIDENCE_ATTESTATION_DOMAIN",
    "EXECUTION_ATTESTATION_DOMAIN",
    "PROTOCOL_ID",
    "ExternalEvidenceArtifactPaths",
    "ExternalMethodEvidence",
    "ExternalMethodSpecification",
    "attested_external_method_evidence_payload",
    "default_external_method_specifications_v0_2",
    "external_artifact_sha256",
    "run_external_fidelity_gate_v0_2",
]
