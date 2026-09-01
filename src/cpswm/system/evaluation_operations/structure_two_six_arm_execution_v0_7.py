"""Exact-six-arm executable reference-core bundle for Structure Two v0.7.

This runner closes the orchestration gap: every declared external arm must run
from one typed input bundle.  It intentionally emits no native-reproduction,
adaptation-parity, fidelity, or efficacy pass flag.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from cpswm.system.attestation import (
    Attestation,
    AttestationError,
    Ed25519AttestationSigner,
    Ed25519AttestationVerifier,
)
from cpswm.system.evaluation_operations.oam_phm_external_evidence import (
    OStarReferenceConfig,
)
from cpswm.system.evaluation_operations.structure_two_counterfactual_executor_v0_7 import (
    CounterfactualExecutionReceipt,
    verify_counterfactual_execution,
)
from cpswm.system.evaluation_operations.structure_two_external_inputs_v0_6 import (
    CompleteExternalAdaptationInputsV06,
)
from cpswm.system.evaluation_operations.structure_two_external_reference_cores_v0_6 import (
    ReferenceCoreResult,
    run_active_dreaming_reference_core,
    run_amg_reference_core,
    run_auto_dreamer_reference_core,
    run_brainctl_reference_core,
    run_o_star_reference_core,
    run_trustmem_reference_core,
)
from cpswm.system.reproducibility import content_sha256

PROTOCOL_ID = "structure-two-six-arm-reference-execution@0.7"
ATTESTATION_DOMAIN = "cpswm.evaluation.structure_two.six_arm_execution.v0.7"
CANONICAL_SIX_ARMS = (
    "corrected_amg",
    "o_star_matched",
    "active_dreaming_matched",
    "auto_dreamer_matched",
    "trustmem_matched",
    "brainctl_matched",
)


def run_six_arm_reference_execution_v0_7(
    inputs: CompleteExternalAdaptationInputsV06,
    *,
    input_bundle_artifact_path: Path,
    o_star_target_id: str,
    o_star_config: OStarReferenceConfig,
    active_rule_by_cluster: dict[int, str],
    active_scenario_execution_receipts: Mapping[str, CounterfactualExecutionReceipt],
    active_scenario_program_paths: Mapping[str, Path],
    trusted_scenario_executor_key_id: str,
    trusted_scenario_executor_public_key_sha256: str,
    arm_result_artifact_paths_by_arm: Mapping[str, Path],
    active_scenario_receipt_paths: Mapping[str, Path],
    source_artifact_sha256_by_arm: Mapping[str, str],
    implementation_bundle_sha256_by_arm: Mapping[str, str],
    executor: Ed25519AttestationSigner,
    immutable_manifest_sha256: str,
    producer_run_id: str,
    producer_source_bundle_sha256: str,
    trustmem_minimum_verifier_score: float = 0.8,
) -> dict[str, Any]:
    stored_inputs = CompleteExternalAdaptationInputsV06.model_validate_json(
        input_bundle_artifact_path.read_text(encoding="utf-8")
    )
    if stored_inputs != inputs:
        raise ValueError("six-arm input artifact differs from executed typed bundle")
    if set(source_artifact_sha256_by_arm) != set(CANONICAL_SIX_ARMS):
        raise ValueError("six-arm execution source-artifact set mismatch")
    if set(implementation_bundle_sha256_by_arm) != set(CANONICAL_SIX_ARMS):
        raise ValueError("six-arm execution implementation-bundle set mismatch")
    if set(arm_result_artifact_paths_by_arm) != set(CANONICAL_SIX_ARMS):
        raise ValueError("six-arm execution result-artifact path set mismatch")
    if set(active_scenario_receipt_paths) != set(active_scenario_execution_receipts):
        raise ValueError("six-arm execution Active Dreaming receipt-path set mismatch")
    if any(
        len(value) != 64 or any(char not in "0123456789abcdef" for char in value)
        for value in (
            *source_artifact_sha256_by_arm.values(),
            *implementation_bundle_sha256_by_arm.values(),
        )
    ):
        raise ValueError("six-arm execution received a malformed content digest")
    active_result = run_active_dreaming_reference_core(
        inputs.active_dreaming_matched,
        abstracted_rule_by_cluster=active_rule_by_cluster,
        scenario_execution_receipts=active_scenario_execution_receipts,
        scenario_program_paths=active_scenario_program_paths,
        trusted_executor_key_id=trusted_scenario_executor_key_id,
        trusted_executor_public_key_sha256=(trusted_scenario_executor_public_key_sha256),
    )
    verified_receipt_count = int(active_result.output["verified_execution_receipt_count"])
    if verified_receipt_count <= 0 or verified_receipt_count != len(active_rule_by_cluster):
        raise ValueError("six-arm execution lacks exact Active Dreaming receipt coverage")
    results: tuple[ReferenceCoreResult, ...] = (
        run_amg_reference_core(inputs.corrected_amg),
        run_o_star_reference_core(
            inputs.o_star_matched,
            target_id=o_star_target_id,
            config=o_star_config,
        ),
        active_result,
        run_auto_dreamer_reference_core(inputs.auto_dreamer_matched),
        run_trustmem_reference_core(
            inputs.trustmem_matched,
            minimum_verifier_score=trustmem_minimum_verifier_score,
        ),
        run_brainctl_reference_core(inputs.brainctl_matched),
    )
    if tuple(item.arm for item in results) != CANONICAL_SIX_ARMS:
        raise ValueError("six-arm reference execution arm order or membership mismatch")
    arm_rows: list[dict[str, Any]] = []
    for item in results:
        artifact_payload = item.model_dump(mode="json")
        artifact_payload["content_sha256"] = item.content_sha256
        artifact_path = arm_result_artifact_paths_by_arm[item.arm]
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(
            json.dumps(artifact_payload, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        arm_rows.append(
            {
                "arm": item.arm,
                "result_content_sha256": item.content_sha256,
                "result_artifact_file_sha256": hashlib.sha256(
                    artifact_path.read_bytes()
                ).hexdigest(),
                "source_artifact_sha256": source_artifact_sha256_by_arm[item.arm],
                "implementation_bundle_sha256": (implementation_bundle_sha256_by_arm[item.arm]),
            }
        )
    active_rows: list[dict[str, Any]] = []
    for scenario_id, receipt in active_scenario_execution_receipts.items():
        receipt_path = active_scenario_receipt_paths[scenario_id]
        stored_receipt = CounterfactualExecutionReceipt.model_validate_json(
            receipt_path.read_text(encoding="utf-8")
        )
        if stored_receipt != receipt:
            raise ValueError("six-arm execution receipt artifact differs from executed receipt")
        program_path = active_scenario_program_paths[scenario_id]
        active_rows.append(
            {
                "scenario_id": scenario_id,
                "receipt_artifact_file_sha256": hashlib.sha256(
                    receipt_path.read_bytes()
                ).hexdigest(),
                "receipt_content_sha256": content_sha256(receipt),
                "program_artifact_file_sha256": hashlib.sha256(
                    program_path.read_bytes()
                ).hexdigest(),
            }
        )
    executor_verifier = executor.verifier()
    report: dict[str, Any] = {
        "protocol": PROTOCOL_ID,
        "immutable_manifest_sha256": immutable_manifest_sha256,
        "producer_run_id": producer_run_id,
        "producer_source_bundle_sha256": producer_source_bundle_sha256,
        "input_bundle_content_sha256": inputs.content_sha256,
        "input_bundle_artifact_file_sha256": hashlib.sha256(
            input_bundle_artifact_path.read_bytes()
        ).hexdigest(),
        "execution_parameters": {
            "o_star_target_id": o_star_target_id,
            "o_star_config": o_star_config.model_dump(mode="json"),
            "active_rule_by_cluster": {
                str(key): value for key, value in sorted(active_rule_by_cluster.items())
            },
            "trustmem_minimum_verifier_score": trustmem_minimum_verifier_score,
        },
        "arm_results": arm_rows,
        "active_scenario_artifacts": active_rows,
        "all_six_reference_cores_executed": True,
        "active_scenario_execution_receipts_verified": (
            verified_receipt_count == len(active_rule_by_cluster) and verified_receipt_count > 0
        ),
        "active_verified_execution_receipt_count": verified_receipt_count,
        "native_protocol_reproduction_passed": False,
        "component_parity_passed": False,
        "adaptation_parity_passed": False,
        "external_fidelity_gate_passed": False,
        "external_method_efficacy_comparison_allowed": False,
        "executor_public_key_base64": executor_verifier.public_key_base64,
        "executor_public_key_sha256": executor_verifier.public_key_sha256,
        "claim_boundary": (
            "All six bounded adaptation reference cores executed from one typed bundle. "
            "This is not official native execution, full component parity, adaptation "
            "parity, external fidelity, or efficacy evidence."
        ),
    }
    report["attestation"] = executor.sign(ATTESTATION_DOMAIN, report).model_dump(mode="json")
    report["content_sha256"] = content_sha256(report)
    return report


def verify_six_arm_reference_execution_v0_7(
    report: Mapping[str, Any],
    *,
    expected_input_bundle_sha256: str,
    input_bundle_artifact_path: Path,
    expected_source_artifact_sha256_by_arm: Mapping[str, str],
    expected_implementation_bundle_sha256_by_arm: Mapping[str, str],
    arm_result_artifact_paths_by_arm: Mapping[str, Path],
    active_scenario_receipt_paths: Mapping[str, Path],
    active_scenario_program_paths: Mapping[str, Path],
    trusted_executor: Ed25519AttestationVerifier,
    trusted_scenario_executor: Ed25519AttestationVerifier,
    expected_immutable_manifest_sha256: str,
    expected_producer_run_id: str,
    expected_producer_source_bundle_sha256: str,
) -> dict[str, Any]:
    payload = dict(report)
    stored = payload.pop("content_sha256", None)
    if not isinstance(stored, str) or content_sha256(payload) != stored:
        raise ValueError("six-arm reference-execution content hash mismatch")
    raw_attestation = payload.pop("attestation", None)
    if not isinstance(raw_attestation, dict):
        raise ValueError("six-arm reference execution lacks an executor signature")
    attestation = Attestation.model_validate(raw_attestation)
    if payload.get("protocol") != PROTOCOL_ID:
        raise ValueError("six-arm reference-execution protocol mismatch")
    if (
        payload.get("immutable_manifest_sha256") != expected_immutable_manifest_sha256
        or payload.get("producer_run_id") != expected_producer_run_id
        or payload.get("producer_source_bundle_sha256") != expected_producer_source_bundle_sha256
    ):
        raise ValueError("six-arm reference execution frozen-run context mismatch")
    inputs = CompleteExternalAdaptationInputsV06.model_validate_json(
        input_bundle_artifact_path.read_text(encoding="utf-8")
    )
    if (
        payload.get("input_bundle_content_sha256") != inputs.content_sha256
        or payload.get("input_bundle_artifact_file_sha256")
        != hashlib.sha256(input_bundle_artifact_path.read_bytes()).hexdigest()
        or payload.get("input_bundle_artifact_file_sha256") != expected_input_bundle_sha256
    ):
        raise ValueError("six-arm reference-execution input binding mismatch")
    rows = payload.get("arm_results")
    if not isinstance(rows, list) or len(rows) != len(CANONICAL_SIX_ARMS):
        raise ValueError("six-arm reference execution lacks six result rows")
    row_arms = tuple(str(row.get("arm")) for row in rows if isinstance(row, dict))
    if row_arms != CANONICAL_SIX_ARMS or len(row_arms) != len(rows):
        raise ValueError("six-arm reference execution arm order or membership mismatch")
    if set(expected_source_artifact_sha256_by_arm) != set(CANONICAL_SIX_ARMS) or set(
        expected_implementation_bundle_sha256_by_arm
    ) != set(CANONICAL_SIX_ARMS):
        raise ValueError("six-arm reference-execution expected binding set mismatch")
    if set(arm_result_artifact_paths_by_arm) != set(CANONICAL_SIX_ARMS):
        raise ValueError("six-arm reference-execution result-artifact set mismatch")
    result_by_arm: dict[str, ReferenceCoreResult] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("six-arm reference-execution result row is malformed")
        arm = str(row["arm"])
        result_path = arm_result_artifact_paths_by_arm[arm]
        result_payload = json.loads(result_path.read_text(encoding="utf-8"))
        if not isinstance(result_payload, dict):
            raise ValueError("six-arm result artifact must be a JSON object")
        result_content_sha256 = result_payload.pop("content_sha256", None)
        result = ReferenceCoreResult.model_validate(result_payload)
        if (
            row.get("source_artifact_sha256") != expected_source_artifact_sha256_by_arm[arm]
            or row.get("implementation_bundle_sha256")
            != expected_implementation_bundle_sha256_by_arm[arm]
            or result.arm != arm
            or result_content_sha256 != result.content_sha256
            or row.get("result_content_sha256") != result.content_sha256
            or row.get("result_artifact_file_sha256")
            != hashlib.sha256(result_path.read_bytes()).hexdigest()
        ):
            raise ValueError("six-arm reference-execution artifact binding mismatch")
        result_by_arm[arm] = result
    active_rows = payload.get("active_scenario_artifacts")
    if (
        not isinstance(active_rows, list)
        or not active_rows
        or len(active_rows) != len(active_scenario_receipt_paths)
        or set(active_scenario_receipt_paths) != set(active_scenario_program_paths)
    ):
        raise ValueError("six-arm reference execution lacks Active Dreaming artifacts")
    active_by_id = {
        str(row.get("scenario_id")): row for row in active_rows if isinstance(row, dict)
    }
    if len(active_by_id) != len(active_rows) or set(active_by_id) != set(
        active_scenario_receipt_paths
    ):
        raise ValueError("six-arm Active Dreaming artifact set mismatch")
    scenario_receipts: dict[str, CounterfactualExecutionReceipt] = {}
    for scenario_id, active_row in active_by_id.items():
        receipt_path = active_scenario_receipt_paths[scenario_id]
        program_path = active_scenario_program_paths[scenario_id]
        receipt = CounterfactualExecutionReceipt.model_validate_json(
            receipt_path.read_text(encoding="utf-8")
        )
        scenario_receipts[scenario_id] = receipt
        if (
            active_row.get("receipt_artifact_file_sha256")
            != hashlib.sha256(receipt_path.read_bytes()).hexdigest()
            or active_row.get("receipt_content_sha256") != content_sha256(receipt)
            or active_row.get("program_artifact_file_sha256")
            != hashlib.sha256(program_path.read_bytes()).hexdigest()
        ):
            raise ValueError("six-arm Active Dreaming artifact binding mismatch")
        verify_counterfactual_execution(
            receipt,
            program_path=program_path,
            expected_payload_sha256=receipt.executable_payload_sha256,
            expected_cluster_id=receipt.cluster_id,
            expected_failure_set_sha256=receipt.failure_set_sha256,
            expected_candidate_rule_sha256=receipt.candidate_rule_sha256,
            trusted_executor_key_id=trusted_scenario_executor.key_id,
            trusted_executor_public_key_sha256=(trusted_scenario_executor.public_key_sha256),
        )
    raw_parameters = payload.get("execution_parameters")
    if not isinstance(raw_parameters, dict):
        raise ValueError("six-arm reference execution lacks execution parameters")
    raw_rule_by_cluster = raw_parameters.get("active_rule_by_cluster")
    if not isinstance(raw_rule_by_cluster, dict) or not raw_rule_by_cluster:
        raise ValueError("six-arm reference execution lacks Active Dreaming rules")
    try:
        active_rule_by_cluster = {
            int(key): str(value) for key, value in raw_rule_by_cluster.items()
        }
        o_star_config = OStarReferenceConfig.model_validate(raw_parameters.get("o_star_config"))
        raw_trustmem_threshold = raw_parameters.get("trustmem_minimum_verifier_score")
        if not isinstance(raw_trustmem_threshold, (int, float)):
            raise ValueError("TrustMem threshold is malformed")
        trustmem_threshold = float(raw_trustmem_threshold)
    except (TypeError, ValueError) as exc:
        raise ValueError("six-arm execution parameters are malformed") from exc
    o_star_target_id = raw_parameters.get("o_star_target_id")
    if not isinstance(o_star_target_id, str) or not o_star_target_id:
        raise ValueError("six-arm O-STaR target is malformed")
    recomputed_results: tuple[ReferenceCoreResult, ...] = (
        run_amg_reference_core(inputs.corrected_amg),
        run_o_star_reference_core(
            inputs.o_star_matched,
            target_id=o_star_target_id,
            config=o_star_config,
        ),
        run_active_dreaming_reference_core(
            inputs.active_dreaming_matched,
            abstracted_rule_by_cluster=active_rule_by_cluster,
            scenario_execution_receipts=scenario_receipts,
            scenario_program_paths=active_scenario_program_paths,
            trusted_executor_key_id=trusted_scenario_executor.key_id,
            trusted_executor_public_key_sha256=(trusted_scenario_executor.public_key_sha256),
        ),
        run_auto_dreamer_reference_core(inputs.auto_dreamer_matched),
        run_trustmem_reference_core(
            inputs.trustmem_matched,
            minimum_verifier_score=trustmem_threshold,
        ),
        run_brainctl_reference_core(inputs.brainctl_matched),
    )
    mismatched_arms = tuple(
        item.arm
        for item in recomputed_results
        if result_by_arm[item.arm].content_sha256 != item.content_sha256
    )
    if tuple(item.arm for item in recomputed_results) != CANONICAL_SIX_ARMS or mismatched_arms:
        raise ValueError(
            "six-arm result artifacts differ from deterministic re-execution: "
            + ",".join(mismatched_arms)
        )
    required_true = (
        "all_six_reference_cores_executed",
        "active_scenario_execution_receipts_verified",
    )
    required_false = (
        "native_protocol_reproduction_passed",
        "component_parity_passed",
        "adaptation_parity_passed",
        "external_fidelity_gate_passed",
        "external_method_efficacy_comparison_allowed",
    )
    if any(payload.get(key) is not True for key in required_true) or any(
        payload.get(key) is not False for key in required_false
    ):
        raise ValueError("six-arm reference-execution status fields are invalid")
    if int(payload.get("active_verified_execution_receipt_count", 0)) != len(active_rows):
        raise ValueError("six-arm reference execution lacks Active Dreaming receipts")
    if (
        payload.get("executor_public_key_base64") != trusted_executor.public_key_base64
        or payload.get("executor_public_key_sha256") != trusted_executor.public_key_sha256
    ):
        raise AttestationError("six-arm reference execution used an untrusted executor")
    trusted_executor.verify(ATTESTATION_DOMAIN, payload, attestation)
    return dict(report)


__all__ = [
    "CANONICAL_SIX_ARMS",
    "PROTOCOL_ID",
    "run_six_arm_reference_execution_v0_7",
    "verify_six_arm_reference_execution_v0_7",
]
