"""Three-stage external-method fidelity gate for Structure Two v0.6.

Native reproduction, cross-domain adaptation, and efficacy authorization are
separate claims.  A common-interface adapter cannot become a faithful external
reproduction merely by producing different actions or copying one equation.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cpswm.system.attestation import (
    Attestation,
    AttestationError,
    Ed25519AttestationSigner,
    Ed25519AttestationVerifier,
)
from cpswm.system.evaluation_operations.structure_two_isolated_pytest_v0_8 import (
    isolated_pytest_environment,
    run_isolated_pytest_v0_8,
)
from cpswm.system.reproducibility import content_sha256

PROTOCOL_ID = "structure-two-external-adapter-fidelity-gate@0.2"
DIAGNOSTIC_PROTOCOL_ID = "structure-two-external-adapter-fidelity-diagnostic@0.2"
EVIDENCE_ATTESTATION_DOMAIN = "cpswm.evaluation.structure_two.external_fidelity.v0.2"
EXECUTION_ATTESTATION_DOMAIN = "cpswm.evaluation.structure_two.external_fidelity.execution.v0.6"
FROZEN_BUILD_ENVIRONMENT_PROTOCOL_ID = "structure-two-frozen-build-environment@0.8"
FROZEN_TEST_ENVIRONMENT_PROTOCOL_ID = "structure-two-frozen-pytest-environment@0.8"


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
    component_parity_test_nodes: tuple[str, ...] = ()
    native_protocol_test_nodes: tuple[str, ...] = ()
    adaptation_parity_test_nodes: tuple[str, ...] = ()
    fidelity_test_bundle_sha256: str | None = None
    official_build_command: tuple[str, ...] = ()


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
    fidelity_test_bundle: Path | None = None
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
            primary_source_url=("https://eprints.whiterose.ac.uk/id/eprint/75560/15/hoggdc9.pdf"),
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


def _trusted_test_nodes(
    test_bundle: Path,
    expected_test_nodes: tuple[str, ...],
) -> tuple[str, ...] | None:
    resolved_nodes: list[str] = []
    for node in expected_test_nodes:
        relative_file, separator, selector = node.partition("::")
        if not separator or not relative_file or not selector:
            return None
        relative_path = Path(relative_file)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            return None
        try:
            test_file = (test_bundle / relative_path).resolve(strict=True)
            test_file.relative_to(test_bundle)
        except (OSError, ValueError):
            return None
        if not test_file.is_file():
            return None
        resolved_nodes.append(f"{test_file}::{selector}")
    return tuple(resolved_nodes)


def _rerun_fidelity_tests(
    implementation_bundle: Path,
    trusted_test_bundle: Path,
    expected_test_nodes: tuple[str, ...],
    expected_test_bundle_sha256: str | None,
) -> bool:
    if not expected_test_nodes or len(set(expected_test_nodes)) != len(expected_test_nodes):
        return False
    try:
        root = implementation_bundle.resolve(strict=True)
        test_root = trusted_test_bundle.resolve(strict=True)
        actual_test_bundle_sha256 = external_artifact_sha256(test_root)
        bundle_sha256_before = external_artifact_sha256(root)
        test_bundle_sha256_before = actual_test_bundle_sha256
    except (OSError, ValueError):
        return False
    if (
        not root.is_dir()
        or not test_root.is_dir()
        or root == test_root
        or root.is_relative_to(test_root)
        or test_root.is_relative_to(root)
        or not _is_sha256(expected_test_bundle_sha256)
        or actual_test_bundle_sha256 != expected_test_bundle_sha256
    ):
        return False
    resolved_nodes = _trusted_test_nodes(test_root, expected_test_nodes)
    if resolved_nodes is None:
        return False
    try:
        with tempfile.TemporaryDirectory(prefix="cpswm-fidelity-") as directory:
            isolated_root = Path(directory)
            junit_path = isolated_root / "junit.xml"
            process = run_isolated_pytest_v0_8(
                nodes=resolved_nodes,
                working_directory=isolated_root,
                junit_path=junit_path,
                timeout_seconds=120,
                extra_environment={"CPSWM_IMPLEMENTATION_BUNDLE": str(root)},
            )
            if process.returncode != 0:
                return False
            junit_root = ET.fromstring(junit_path.read_bytes())
    except (OSError, ValueError, subprocess.SubprocessError, ET.ParseError):
        return False
    testcases = tuple(junit_root.iter("testcase"))
    if len(testcases) != len(expected_test_nodes):
        return False
    if any(
        any(testcase.find(name) is not None for name in ("failure", "error", "skipped"))
        for testcase in testcases
    ):
        return False
    expected_names = tuple(node.rsplit("::", maxsplit=1)[-1] for node in expected_test_nodes)
    return (
        tuple(testcase.get("name") for testcase in testcases) == expected_names
        and external_artifact_sha256(root) == bundle_sha256_before
        and external_artifact_sha256(test_root) == test_bundle_sha256_before
    )


def run_fidelity_tests_and_make_receipt_v0_7(
    *,
    receipt_path: Path,
    execution_log_path: Path,
    implementation_bundle_path: Path,
    trusted_test_bundle_path: Path,
    arm: str,
    receipt_protocol: str,
    success_field: str,
    expected_test_nodes: tuple[str, ...],
    immutable_manifest_sha256: str,
    producer_run_id: str,
    input_bundle_sha256: str,
    primary_source_sha256: str,
    implementation_bundle_sha256: str,
    fidelity_test_bundle_sha256: str,
    adaptation_contract_sha256: str,
    executor: Ed25519AttestationSigner,
) -> dict[str, Any]:
    """Execute frozen fidelity tests, then atomically derive and sign their receipt."""

    if external_artifact_sha256(implementation_bundle_path) != (implementation_bundle_sha256):
        raise ValueError("fidelity runner implementation bundle hash mismatch")
    started_at_utc = datetime.now(UTC)
    passed = _rerun_fidelity_tests(
        implementation_bundle_path,
        trusted_test_bundle_path,
        expected_test_nodes,
        fidelity_test_bundle_sha256,
    )
    finished_at_utc = datetime.now(UTC)
    if not passed:
        raise ValueError("fidelity runner subprocess did not pass the frozen test nodes")
    log: dict[str, Any] = {
        "protocol": "structure-two-fidelity-test-result@0.7",
        "arm": arm,
        "receipt_protocol": receipt_protocol,
        "immutable_manifest_sha256": immutable_manifest_sha256,
        "producer_run_id": producer_run_id,
        "input_bundle_sha256": input_bundle_sha256,
        "primary_source_sha256": primary_source_sha256,
        "implementation_bundle_sha256": implementation_bundle_sha256,
        "fidelity_test_bundle_sha256": fidelity_test_bundle_sha256,
        "test_environment_protocol": FROZEN_TEST_ENVIRONMENT_PROTOCOL_ID,
        "adaptation_contract_sha256": adaptation_contract_sha256,
        "pytest_node_ids": list(expected_test_nodes),
        "assertions": [
            {
                "node_id": node,
                "passed": True,
                "evidence_sha256": content_sha256(
                    {
                        "node_id": node,
                        "implementation_bundle_sha256": implementation_bundle_sha256,
                        "fidelity_test_bundle_sha256": fidelity_test_bundle_sha256,
                        "test_result": "passed",
                    }
                ),
            }
            for node in expected_test_nodes
        ],
        "summary": {
            "collected": len(expected_test_nodes),
            "passed": len(expected_test_nodes),
            "failed": 0,
        },
        "exit_code": 0,
        "started_at_utc": started_at_utc.isoformat(),
        "finished_at_utc": finished_at_utc.isoformat(),
        "execution_basis": "runner_subprocess_then_verifier_reexecution",
    }
    log["content_sha256"] = content_sha256(log)
    execution_log_path.write_text(json.dumps(log, sort_keys=True), encoding="utf-8")
    unsigned: dict[str, Any] = {
        "protocol": receipt_protocol,
        "arm": arm,
        success_field: True,
        "execution": {
            "command": [
                "python",
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                "--noconftest",
                *expected_test_nodes,
            ],
            "exit_code": 0,
            "log_sha256": external_artifact_sha256(execution_log_path),
            "test_result_content_sha256": log["content_sha256"],
            "implementation_bundle_sha256": implementation_bundle_sha256,
            "fidelity_test_bundle_sha256": fidelity_test_bundle_sha256,
            "test_environment_protocol": FROZEN_TEST_ENVIRONMENT_PROTOCOL_ID,
            "immutable_manifest_sha256": immutable_manifest_sha256,
            "producer_run_id": producer_run_id,
            "input_bundle_sha256": input_bundle_sha256,
            "primary_source_sha256": primary_source_sha256,
            "adaptation_contract_sha256": adaptation_contract_sha256,
        },
    }
    verifier = executor.verifier()
    receipt = {
        **unsigned,
        "executor_key_id": verifier.key_id,
        "executor_public_key_base64": verifier.public_key_base64,
        "executor_public_key_sha256": verifier.public_key_sha256,
        "executor_attestation": executor.sign(EXECUTION_ATTESTATION_DOMAIN, unsigned).model_dump(
            mode="json"
        ),
    }
    receipt_path.write_text(json.dumps(receipt, sort_keys=True), encoding="utf-8")
    return receipt


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
    expected_manifest_sha256: str | None,
    expected_producer_run_id: str | None,
    expected_input_bundle_sha256: str | None,
    expected_primary_source_sha256: str | None,
    expected_adaptation_contract_sha256: str | None,
    implementation_bundle_path: Path,
    trusted_test_bundle_path: Path,
    expected_test_bundle_sha256: str | None,
    expected_test_nodes: tuple[str, ...],
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
    try:
        log_payload = json.loads(execution_log_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(log_payload, dict):
        return False
    unsigned_log = dict(log_payload)
    stored_log_content_sha256 = unsigned_log.pop("content_sha256", None)
    test_nodes = log_payload.get("pytest_node_ids")
    assertions = log_payload.get("assertions")
    summary = log_payload.get("summary")
    structured_log_valid = (
        isinstance(stored_log_content_sha256, str)
        and content_sha256(unsigned_log) == stored_log_content_sha256
        and log_payload.get("protocol") == "structure-two-fidelity-test-result@0.7"
        and log_payload.get("arm") == arm
        and log_payload.get("receipt_protocol") == expected_protocol
        and log_payload.get("immutable_manifest_sha256") == expected_manifest_sha256
        and log_payload.get("producer_run_id") == expected_producer_run_id
        and log_payload.get("input_bundle_sha256") == expected_input_bundle_sha256
        and log_payload.get("primary_source_sha256") == expected_primary_source_sha256
        and log_payload.get("implementation_bundle_sha256") == implementation_bundle_sha256
        and log_payload.get("fidelity_test_bundle_sha256") == expected_test_bundle_sha256
        and log_payload.get("test_environment_protocol") == FROZEN_TEST_ENVIRONMENT_PROTOCOL_ID
        and log_payload.get("adaptation_contract_sha256") == expected_adaptation_contract_sha256
        and isinstance(test_nodes, list)
        and tuple(test_nodes) == expected_test_nodes
        and bool(expected_test_nodes)
        and isinstance(assertions, list)
        and len(assertions) == len(test_nodes)
        and all(
            isinstance(row, dict)
            and row.get("node_id") == node
            and row.get("passed") is True
            and row.get("evidence_sha256")
            == content_sha256(
                {
                    "node_id": node,
                    "implementation_bundle_sha256": implementation_bundle_sha256,
                    "fidelity_test_bundle_sha256": expected_test_bundle_sha256,
                    "test_result": "passed",
                }
            )
            for row, node in zip(assertions, test_nodes, strict=True)
        )
        and isinstance(summary, dict)
        and summary.get("collected") == len(test_nodes)
        and summary.get("passed") == len(test_nodes)
        and summary.get("failed") == 0
        and log_payload.get("exit_code") == 0
    )
    checks = (
        payload.get("protocol") == expected_protocol,
        payload.get("arm") == arm,
        payload.get(success_field) is True,
        execution.get("exit_code") == 0,
        isinstance(command, list) and bool(command),
        command
        == [
            "python",
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "--noconftest",
            *expected_test_nodes,
        ],
        structured_log_valid,
        execution.get("implementation_bundle_sha256") == implementation_bundle_sha256,
        execution.get("fidelity_test_bundle_sha256") == expected_test_bundle_sha256,
        execution.get("test_environment_protocol") == FROZEN_TEST_ENVIRONMENT_PROTOCOL_ID,
        execution.get("immutable_manifest_sha256") == expected_manifest_sha256,
        execution.get("producer_run_id") == expected_producer_run_id,
        execution.get("input_bundle_sha256") == expected_input_bundle_sha256,
        execution.get("primary_source_sha256") == expected_primary_source_sha256,
        execution.get("adaptation_contract_sha256") == expected_adaptation_contract_sha256,
        execution.get("test_result_content_sha256") == stored_log_content_sha256,
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
    return _rerun_fidelity_tests(
        implementation_bundle_path,
        trusted_test_bundle_path,
        expected_test_nodes,
        expected_test_bundle_sha256,
    )


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
        resolved = path.resolve(strict=True)
        commit = subprocess.run(
            ("git", "-C", str(resolved), "rev-parse", "HEAD"),
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        repository_root = Path(
            subprocess.run(
                ("git", "-C", str(resolved), "rev-parse", "--show-toplevel"),
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        ).resolve(strict=True)
        expected_tree = subprocess.run(
            ("git", "-C", str(resolved), "rev-parse", f"{expected_commit}^{{tree}}"),
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        head_tree = subprocess.run(
            ("git", "-C", str(resolved), "rev-parse", "HEAD^{tree}"),
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        status = subprocess.run(
            (
                "git",
                "-C",
                str(resolved),
                "status",
                "--porcelain",
                "--untracked-files=all",
            ),
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        submodules = subprocess.run(
            ("git", "-C", str(resolved), "submodule", "status", "--recursive"),
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError):
        return False
    return (
        resolved == repository_root
        and commit == expected_commit
        and head_tree == expected_tree
        and not status.strip()
        and all(not row.startswith(("-", "+", "U")) for row in submodules)
    )


def _reproduce_official_build(
    *,
    specification: ExternalMethodSpecification,
    official_checkout: Path,
    submitted_implementation_bundle: Path,
) -> dict[str, Any] | None:
    """Rebuild a frozen checkout in a clean temporary process workspace.

    This is process/environment isolation, not a network- or syscall-isolated
    container.  Canonical specifications remain fail-closed until they freeze a
    concrete build argv containing exactly one ``{output_dir}`` placeholder.
    """

    command_template = specification.official_build_command
    if (
        not specification.official_code_required
        or not command_template
        or command_template.count("{output_dir}") != 1
        or any(not token for token in command_template)
    ):
        return None
    try:
        checkout = official_checkout.resolve(strict=True)
        submitted = submitted_implementation_bundle.resolve(strict=True)
        if any(path.is_symlink() for path in checkout.rglob("*")):
            return None
        checkout_sha256_before = external_artifact_sha256(checkout)
        submitted_sha256 = external_artifact_sha256(submitted)
        with tempfile.TemporaryDirectory(prefix="cpswm-official-build-") as directory:
            isolated_root = Path(directory)
            source_copy = isolated_root / "source"
            output_dir = isolated_root / "output"
            shutil.copytree(
                checkout,
                source_copy,
                ignore=shutil.ignore_patterns(".git"),
            )
            output_dir.mkdir()
            command = tuple(
                str(output_dir) if token == "{output_dir}" else token for token in command_template
            )
            if command[0] == "python":
                command = (sys.executable, *command[1:])
            environment = isolated_pytest_environment(
                temporary_directory=isolated_root,
                extra={"CPSWM_BUILD_OUTPUT_DIR": str(output_dir)},
            )
            process = subprocess.run(
                command,
                cwd=source_copy,
                capture_output=True,
                text=True,
                check=False,
                timeout=300,
                env=environment,
            )
            if process.returncode != 0:
                return None
            rebuilt_sha256 = external_artifact_sha256(output_dir)
            source_copy_sha256_after = external_artifact_sha256(source_copy)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    if (
        rebuilt_sha256 != submitted_sha256
        or source_copy_sha256_after != checkout_sha256_before
        or external_artifact_sha256(checkout) != checkout_sha256_before
    ):
        return None
    receipt: dict[str, Any] = {
        "protocol": "structure-two-verifier-derived-build-provenance@0.8",
        "arm": specification.arm,
        "official_code_url": specification.official_code_url,
        "official_code_commit": specification.official_code_commit,
        "official_checkout_tree_sha256": checkout_sha256_before,
        "build_environment_protocol": FROZEN_BUILD_ENVIRONMENT_PROTOCOL_ID,
        "build_command": list(command_template),
        "build_output_bundle_sha256": rebuilt_sha256,
        "verifier_reexecuted_build": True,
        "isolation_boundary": "clean_env_temporary_copy_no_shell_not_containerized",
    }
    receipt["content_sha256"] = content_sha256(receipt)
    return receipt


def _verified_adaptation_contract(
    path: Path,
    *,
    specification: ExternalMethodSpecification,
    expected_manifest_sha256: str | None,
    expected_producer_run_id: str | None,
    expected_input_bundle_sha256: str | None,
    expected_primary_source_sha256: str | None,
    expected_implementation_bundle_sha256: str | None,
    expected_official_checkout_tree_sha256: str | None,
) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    unsigned = dict(payload)
    stored = unsigned.pop("content_sha256", None)
    mappings = payload.get("input_mappings")
    base_valid = bool(
        isinstance(stored, str)
        and content_sha256(unsigned) == stored
        and payload.get("protocol") == "structure-two-external-adaptation-contract@0.6"
        and payload.get("arm") == specification.arm
        and payload.get("method") == specification.method
        and payload.get("primary_source_url") == specification.primary_source_url
        and payload.get("immutable_manifest_sha256") == expected_manifest_sha256
        and payload.get("producer_run_id") == expected_producer_run_id
        and payload.get("input_bundle_sha256") == expected_input_bundle_sha256
        and payload.get("primary_source_sha256") == expected_primary_source_sha256
        and payload.get("implementation_bundle_sha256") == expected_implementation_bundle_sha256
        and payload.get("fidelity_test_bundle_sha256") == specification.fidelity_test_bundle_sha256
        and payload.get("fidelity_test_environment_protocol") == FROZEN_TEST_ENVIRONMENT_PROTOCOL_ID
        and payload.get("fidelity_test_nodes")
        == {
            "component_parity": list(specification.component_parity_test_nodes),
            "native_protocol": list(specification.native_protocol_test_nodes),
            "adaptation_parity": list(specification.adaptation_parity_test_nodes),
        }
        and tuple(payload.get("required_adaptation_inputs", ()))
        == specification.required_adaptation_inputs
        and isinstance(mappings, list)
        and len(mappings) == len(specification.required_adaptation_inputs)
        and tuple(row.get("required_input") for row in mappings if isinstance(row, dict))
        == specification.required_adaptation_inputs
        and all(
            isinstance(row, dict)
            and isinstance(row.get("typed_input_field"), str)
            and bool(row["typed_input_field"])
            and isinstance(row.get("transformation"), str)
            and bool(row["transformation"])
            for row in mappings
        )
    )
    if not base_valid:
        return False
    if not specification.official_code_required:
        return True
    build_command = payload.get("implementation_build_command")
    return bool(
        payload.get("official_checkout_tree_sha256") == expected_official_checkout_tree_sha256
        and build_command == list(specification.official_build_command)
        and bool(specification.official_build_command)
        and specification.official_build_command.count("{output_dir}") == 1
        and payload.get("build_environment_protocol") == FROZEN_BUILD_ENVIRONMENT_PROTOCOL_ID
        and payload.get("build_output_bundle_sha256") == expected_implementation_bundle_sha256
    )


def _score(
    specification: ExternalMethodSpecification,
    evidence: ExternalMethodEvidence | None,
    *,
    artifact_paths: ExternalEvidenceArtifactPaths | None,
    trusted_reviewer_key_id: str | None,
    trusted_reviewer_public_key_sha256: str | None,
    trusted_executor_key_id: str | None,
    trusted_executor_public_key_sha256: str | None,
    expected_manifest_sha256: str | None,
    expected_producer_run_id: str | None,
    expected_input_bundle_sha256: str | None,
    expected_primary_source_sha256: str | None,
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
    trusted_test_bundle_bound = bool(
        artifact_paths
        and artifact_paths.fidelity_test_bundle is not None
        and _artifact_matches(
            artifact_paths.fidelity_test_bundle,
            specification.fidelity_test_bundle_sha256,
        )
        and artifact_paths.fidelity_test_bundle.resolve()
        != artifact_paths.implementation_bundle.resolve()
    )
    adaptation_contract_artifact_sha256 = (
        external_artifact_sha256(artifact_paths.adaptation_contract)
        if artifact_paths is not None and artifact_paths.adaptation_contract.is_file()
        else None
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
    official_checkout_tree_sha256 = (
        external_artifact_sha256(artifact_paths.official_code_checkout)
        if specification.official_code_required
        and artifact_paths is not None
        and artifact_paths.official_code_checkout is not None
        else None
    )
    official_build_provenance = (
        _reproduce_official_build(
            specification=specification,
            official_checkout=artifact_paths.official_code_checkout,
            submitted_implementation_bundle=artifact_paths.implementation_bundle,
        )
        if specification.official_code_required
        and official_code_bound
        and artifact_paths is not None
        and artifact_paths.official_code_checkout is not None
        else None
    )
    official_build_reproduced = (
        not specification.official_code_required or official_build_provenance is not None
    )
    component_parity = bool(
        artifact_paths
        and artifact_paths.fidelity_test_bundle is not None
        and trusted_test_bundle_bound
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
            expected_manifest_sha256=expected_manifest_sha256,
            expected_producer_run_id=expected_producer_run_id,
            expected_input_bundle_sha256=expected_input_bundle_sha256,
            expected_primary_source_sha256=expected_primary_source_sha256,
            expected_adaptation_contract_sha256=(adaptation_contract_artifact_sha256),
            implementation_bundle_path=artifact_paths.implementation_bundle,
            trusted_test_bundle_path=artifact_paths.fidelity_test_bundle,
            expected_test_bundle_sha256=specification.fidelity_test_bundle_sha256,
            expected_test_nodes=specification.component_parity_test_nodes,
        )
    )
    native_protocol_rechecked = bool(
        artifact_paths
        and artifact_paths.fidelity_test_bundle is not None
        and trusted_test_bundle_bound
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
            expected_manifest_sha256=expected_manifest_sha256,
            expected_producer_run_id=expected_producer_run_id,
            expected_input_bundle_sha256=expected_input_bundle_sha256,
            expected_primary_source_sha256=expected_primary_source_sha256,
            expected_adaptation_contract_sha256=(adaptation_contract_artifact_sha256),
            implementation_bundle_path=artifact_paths.implementation_bundle,
            trusted_test_bundle_path=artifact_paths.fidelity_test_bundle,
            expected_test_bundle_sha256=specification.fidelity_test_bundle_sha256,
            expected_test_nodes=specification.native_protocol_test_nodes,
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
            trusted_test_bundle_bound,
            official_code_bound,
            official_build_reproduced,
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
        and _verified_adaptation_contract(
            artifact_paths.adaptation_contract,
            specification=specification,
            expected_manifest_sha256=expected_manifest_sha256,
            expected_producer_run_id=expected_producer_run_id,
            expected_input_bundle_sha256=expected_input_bundle_sha256,
            expected_primary_source_sha256=expected_primary_source_sha256,
            expected_implementation_bundle_sha256=(evidence.implementation_bundle_sha256),
            expected_official_checkout_tree_sha256=(official_checkout_tree_sha256),
        )
    )
    adaptation_parity = bool(
        artifact_paths
        and artifact_paths.fidelity_test_bundle is not None
        and trusted_test_bundle_bound
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
            expected_manifest_sha256=expected_manifest_sha256,
            expected_producer_run_id=expected_producer_run_id,
            expected_input_bundle_sha256=expected_input_bundle_sha256,
            expected_primary_source_sha256=expected_primary_source_sha256,
            expected_adaptation_contract_sha256=(evidence.adaptation_contract_sha256),
            implementation_bundle_path=artifact_paths.implementation_bundle,
            trusted_test_bundle_path=artifact_paths.fidelity_test_bundle,
            expected_test_bundle_sha256=specification.fidelity_test_bundle_sha256,
            expected_test_nodes=specification.adaptation_parity_test_nodes,
        )
    )
    adaptation_passed = native_passed and adaptation_contract_bound and adaptation_parity
    checks = {
        "primary_source_content_bound": source_bound,
        "implementation_bundle_content_bound": implementation_bound,
        "trusted_fidelity_test_bundle_content_bound": trusted_test_bundle_bound,
        "official_code_identity_bound_if_required": official_code_bound,
        "official_checkout_build_reproduced_if_required": (official_build_reproduced),
        "native_component_set_exact_and_parity_tested": component_parity,
        "component_parity_verifier_reexecution_passed": component_parity,
        "native_published_protocol_rechecked": native_protocol_rechecked,
        "native_protocol_verifier_reexecution_passed": native_protocol_rechecked,
        "independent_reviewer_attested": independent_reviewed,
        "adaptation_contract_content_bound": adaptation_contract_bound,
        "adaptation_parity_tested": adaptation_parity,
        "adaptation_parity_verifier_reexecution_passed": adaptation_parity,
    }
    return {
        "arm": specification.arm,
        "method": specification.method,
        "native_domain": specification.native_domain,
        "primary_source_url": specification.primary_source_url,
        "required_native_components": specification.required_native_components,
        "verified_native_components": evidence.verified_native_components,
        "official_build_provenance": official_build_provenance,
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
    expected_manifest_sha256: str | None = None,
    expected_producer_run_id: str | None = None,
    expected_input_bundle_sha256_by_arm: Mapping[str, str] | None = None,
    expected_primary_source_sha256_by_arm: Mapping[str, str] | None = None,
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
    if enforce_canonical_catalog and (
        not _is_sha256(expected_manifest_sha256)
        or not expected_producer_run_id
        or set(expected_input_bundle_sha256_by_arm or {}) != set(arms)
        or set(expected_primary_source_sha256_by_arm or {}) != set(arms)
    ):
        raise ValueError(
            "canonical fidelity requires the frozen run, typed input, and source chain"
        )
    expected_input_bundle_sha256_by_arm = expected_input_bundle_sha256_by_arm or {}
    expected_primary_source_sha256_by_arm = expected_primary_source_sha256_by_arm or {}
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
            expected_manifest_sha256=expected_manifest_sha256,
            expected_producer_run_id=expected_producer_run_id,
            expected_input_bundle_sha256=(expected_input_bundle_sha256_by_arm.get(item.arm)),
            expected_primary_source_sha256=(expected_primary_source_sha256_by_arm.get(item.arm)),
        )
        for item in specifications
    ]
    native_passed = all(bool(item["native_fidelity_passed"]) for item in rows)
    adaptation_passed = all(bool(item["adaptation_fidelity_passed"]) for item in rows)
    canonical_protocol_enforced = enforce_canonical_catalog
    isolated_external_execution_environment_verified = False
    rows = [
        {
            **item,
            "canonical_protocol_enforced": canonical_protocol_enforced,
            "clean_subprocess_native_checks_passed": item["native_fidelity_passed"],
            "clean_subprocess_adaptation_checks_passed": item["adaptation_fidelity_passed"],
            "diagnostic_native_fidelity_passed": item["native_fidelity_passed"],
            "diagnostic_adaptation_fidelity_passed": item["adaptation_fidelity_passed"],
            "native_fidelity_passed": False,
            "adaptation_fidelity_passed": False,
            "missing_requirements": tuple(
                (*item["missing_requirements"], "isolated_external_execution_environment")
            ),
        }
        for item in rows
    ]
    formal_native_passed = (
        native_passed
        and canonical_protocol_enforced
        and isolated_external_execution_environment_verified
    )
    formal_adaptation_passed = (
        adaptation_passed
        and canonical_protocol_enforced
        and isolated_external_execution_environment_verified
    )
    report: dict[str, Any] = {
        "protocol": (PROTOCOL_ID if canonical_protocol_enforced else DIAGNOSTIC_PROTOCOL_ID),
        "canonical_protocol_enforced": canonical_protocol_enforced,
        "isolated_external_execution_environment_verified": (
            isolated_external_execution_environment_verified
        ),
        "method_results": rows,
        "diagnostic_native_fidelity_passed": native_passed,
        "diagnostic_adaptation_fidelity_passed": adaptation_passed,
        "native_fidelity_gate_passed": formal_native_passed,
        "adaptation_fidelity_gate_passed": formal_adaptation_passed,
        "external_fidelity_gate_passed": (formal_native_passed and formal_adaptation_passed),
        "fidelity_precondition_for_combined_authorization_passed": (
            formal_native_passed and formal_adaptation_passed
        ),
        "external_method_efficacy_comparison_allowed": False,
        "claim_boundary": (
            "Native reproduction evidence supports claims only in each method's native "
            "domain. Cross-domain efficacy claims additionally require a content-bound "
            "adaptation contract and executable adaptation-parity evidence. Even complete "
            "fidelity evidence is only one precondition for the separate combined efficacy "
            "authorization gate."
            if canonical_protocol_enforced
            else "This is a noncanonical diagnostic run. Diagnostic method results may be "
            "inspected, but every formal fidelity pass and authorization precondition is "
            "forced false."
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
    "run_fidelity_tests_and_make_receipt_v0_7",
]
