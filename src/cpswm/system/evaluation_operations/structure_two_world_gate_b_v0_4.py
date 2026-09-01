"""Strict Structure-Two v0.4 Gate B and dual-gate authorization.

This module does not execute an arm.  It consumes complete prediction traces
produced after the fresh-world Gate A passed, binds every trace to that exact
Gate A artifact and frozen manifest, and rejects any missing, extra, duplicated,
reordered, or truncated rollout.  Only an exact ten-arm set can be scored.
Behavioral distinguishability never substitutes for external-adapter fidelity.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import Field

from cpswm.contracts.base import ContractModel
from cpswm.system.attestation import (
    Attestation,
    AttestationError,
    Ed25519AttestationSigner,
    Ed25519AttestationVerifier,
    attested_payload,
)
from cpswm.system.evaluation_operations.structure_two_external_adapter_fidelity import (
    build_external_adapter_fidelity_audit,
)
from cpswm.system.evaluation_operations.structure_two_world_arm_adapter_v0_4 import (
    GATE_B_MIN_EPISODE_FRACTION_WITH_MULTIPLE_ARM_TRAJECTORIES,
    GATE_B_MIN_PAIRWISE_PREDICTION_DISAGREEMENT_RATE,
)
from cpswm.system.evaluation_operations.structure_two_world_validation_gate_v0_4 import (
    DEFAULT_MANIFEST,
    verify_validation_gate_report,
)
from cpswm.system.evaluation_operations.structure_two_world_validation_gate_v0_4 import (
    DEFAULT_OUTPUT as DEFAULT_GATE_A_OUTPUT,
)
from cpswm.system.evaluation_operations.task_nontriviality_gates import (
    ArmPredictionTrace,
    run_gate_b,
)
from cpswm.system.reproducibility import content_sha256

PROTOCOL_ID = "structure-two-world-arm-distinguishability-gate-b@0.4"
TRACE_PROTOCOL_ID = "structure-two-world-bound-arm-prediction-trace@0.4"
TRACE_ATTESTATION_DOMAIN = "cpswm.evaluation.structure_two.bound_arm_trace.v0.4"
DEFAULT_TRACE_DIR = Path("benchmarks/structure_two/gate_b_arm_traces_v0_4")
DEFAULT_OUTPUT = Path(
    "benchmarks/structure_two/structure_two_world_dual_gate_authorization_v0_4.json"
)


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True, slots=True)
class ExpectedRollout:
    rollout_id: str
    scored_step_count: int


class BoundArmTraceRecord(ContractModel):
    protocol: str = Field(pattern=r"^structure-two-world-bound-arm-prediction-trace@0\.4$")
    arm: str = Field(min_length=1)
    gate_a_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    producer_run_id: str = Field(min_length=1)
    producer_source_bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    episode_predictions: tuple[tuple[str, tuple[str, ...]], ...]
    custodian_public_key_base64: str = Field(min_length=1)
    custodian_public_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    attestation: Attestation | None = None


def make_bound_arm_trace_payload(
    *,
    arm: str,
    gate_a_content_sha256: str,
    manifest_sha256: str,
    producer_run_id: str,
    producer_source_bundle_sha256: str,
    episode_predictions: Sequence[tuple[str, Sequence[str]]],
    signer: Ed25519AttestationSigner,
) -> dict[str, Any]:
    """Create a formally signed trace in the external custodian environment."""

    verifier = signer.verifier()
    unsigned = BoundArmTraceRecord(
        protocol=TRACE_PROTOCOL_ID,
        arm=arm,
        gate_a_content_sha256=gate_a_content_sha256,
        manifest_sha256=manifest_sha256,
        producer_run_id=producer_run_id,
        producer_source_bundle_sha256=producer_source_bundle_sha256,
        episode_predictions=tuple(
            (rollout_id, tuple(predictions)) for rollout_id, predictions in episode_predictions
        ),
        custodian_public_key_base64=verifier.public_key_base64,
        custodian_public_key_sha256=verifier.public_key_sha256,
    )
    signed = unsigned.model_copy(
        update={
            "attestation": signer.sign(
                TRACE_ATTESTATION_DOMAIN,
                attested_payload(unsigned),
            )
        }
    )
    payload: dict[str, Any] = signed.model_dump(mode="json")
    payload["content_sha256"] = content_sha256(payload)
    return payload


def write_bound_arm_trace(payload: Mapping[str, Any], output_path: Path) -> None:
    if output_path.exists():
        raise FileExistsError("bound arm trace already exists; refusing to overwrite")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _verify_bound_trace(
    payload: Mapping[str, Any],
    *,
    trusted_key_id: str,
    trusted_public_key_sha256: str,
) -> tuple[BoundArmTraceRecord, str]:
    stored = payload.get("content_sha256")
    unsigned = dict(payload)
    unsigned.pop("content_sha256", None)
    if not isinstance(stored, str) or content_sha256(unsigned) != stored:
        raise ValueError("bound arm trace content hash mismatch")
    record = BoundArmTraceRecord.model_validate(unsigned)
    if record.custodian_public_key_sha256 != trusted_public_key_sha256:
        raise AttestationError("arm trace public key is not the preregistered trust anchor")
    verifier = Ed25519AttestationVerifier.from_public_key_base64(
        key_id=trusted_key_id,
        public_key_base64=record.custodian_public_key_base64,
    )
    if verifier.public_key_sha256 != trusted_public_key_sha256:
        raise AttestationError("arm trace embedded public-key hash mismatch")
    if record.attestation is None:
        raise AttestationError("arm trace has no external custodian signature")
    verifier.verify(
        TRACE_ATTESTATION_DOMAIN,
        attested_payload(record),
        record.attestation,
    )
    return record, stored


def validate_and_score_bound_arm_traces(
    payloads: Sequence[Mapping[str, Any]],
    *,
    expected_arms: Sequence[str],
    expected_rollouts: Sequence[ExpectedRollout],
    gate_a_content_sha256: str,
    manifest_sha256: str,
    trusted_key_id: str,
    trusted_public_key_sha256: str,
    expected_producer_source_bundle_sha256: str,
) -> dict[str, Any]:
    """Apply the exact-set and exact-order contract before running Gate B."""

    arms = tuple(str(item) for item in expected_arms)
    if len(arms) < 2 or len(set(arms)) != len(arms):
        raise ValueError("Gate B expected-arm contract is invalid")
    rollout_ids = tuple(item.rollout_id for item in expected_rollouts)
    if not rollout_ids or len(set(rollout_ids)) != len(rollout_ids):
        raise ValueError("Gate A ordered rollout contract is empty or duplicated")
    expected_step_counts = {item.rollout_id: item.scored_step_count for item in expected_rollouts}

    by_arm: dict[str, BoundArmTraceRecord] = {}
    trace_hashes: dict[str, str] = {}
    producer_run_ids: set[str] = set()
    producer_source_hashes: set[str] = set()
    traces: list[ArmPredictionTrace] = []
    for payload in payloads:
        record, trace_hash = _verify_bound_trace(
            payload,
            trusted_key_id=trusted_key_id,
            trusted_public_key_sha256=trusted_public_key_sha256,
        )
        arm = record.arm
        if arm in by_arm:
            raise ValueError(f"duplicate Gate B arm trace: {arm}")
        by_arm[arm] = record
        trace_hashes[arm] = trace_hash
        producer_run_ids.add(record.producer_run_id)
        producer_source_hashes.add(record.producer_source_bundle_sha256)
        if record.gate_a_content_sha256 != gate_a_content_sha256:
            raise ValueError(f"arm {arm} is bound to the wrong Gate A artifact")
        if record.manifest_sha256 != manifest_sha256:
            raise ValueError(f"arm {arm} is bound to the wrong frozen manifest")

    if set(by_arm) != set(arms):
        missing = sorted(set(arms) - set(by_arm))
        extra = sorted(set(by_arm) - set(arms))
        raise ValueError(f"Gate B arm set mismatch; missing={missing}, extra={extra}")
    if len(producer_run_ids) != 1 or len(producer_source_hashes) != 1:
        raise ValueError("Gate B arms were not produced by one frozen run and source bundle")
    if next(iter(producer_source_hashes)) != expected_producer_source_bundle_sha256:
        raise ValueError("Gate B producer source bundle differs from the frozen manifest")

    for arm in arms:
        rows = by_arm[arm].episode_predictions
        observed_ids: list[str] = []
        parsed_rows: list[tuple[str, tuple[str, ...]]] = []
        for row in rows:
            rollout_id = row[0]
            predictions = row[1]
            observed_ids.append(rollout_id)
            if (
                rollout_id in expected_step_counts
                and len(predictions) != expected_step_counts[rollout_id]
            ):
                raise ValueError(f"arm {arm} has a truncated prediction sequence")
            parsed_rows.append((rollout_id, tuple(predictions)))
        if tuple(observed_ids) != rollout_ids:
            raise ValueError(f"arm {arm} rollout ids differ from Gate A order")
        traces.append(ArmPredictionTrace(arm=arm, episode_predictions=tuple(parsed_rows)))

    gate_b = run_gate_b(
        traces,
        min_pairwise_prediction_disagreement_rate=(
            GATE_B_MIN_PAIRWISE_PREDICTION_DISAGREEMENT_RATE
        ),
        min_episode_fraction_with_multiple_arm_trajectories=(
            GATE_B_MIN_EPISODE_FRACTION_WITH_MULTIPLE_ARM_TRAJECTORIES
        ),
    )
    return {
        "gate_b": gate_b,
        "expected_arm_count": len(arms),
        "expected_rollout_count": len(rollout_ids),
        "ordered_rollout_ids_sha256": content_sha256(list(rollout_ids)),
        "trace_content_sha256_by_arm": trace_hashes,
        "producer_run_id": next(iter(producer_run_ids)),
        "producer_source_bundle_sha256": next(iter(producer_source_hashes)),
    }


def _load_gate_b_inputs(
    *,
    repository_root: Path,
    trace_dir: Path,
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    tuple[str, ...],
    tuple[ExpectedRollout, ...],
    str,
    str,
    str,
]:
    gate_a_path = repository_root / DEFAULT_GATE_A_OUTPUT
    gate_a = verify_validation_gate_report(
        gate_a_path,
        repository_root=repository_root,
        recompute=True,
    )
    if gate_a.get("gate_a_passed") is not True or gate_a.get("gate_b_allowed") is not True:
        raise ValueError("fresh-world Gate A did not authorize Gate B")

    manifest_path = repository_root / DEFAULT_MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    contract = manifest.get("gate_b_contract", {})
    if contract.get("requires_verified_gate_a_pass") is not True:
        raise ValueError("frozen manifest lacks the strict Gate B prerequisite")
    expected_arms = tuple(str(item) for item in contract["expected_arms"])
    custody = manifest["custodian_attestation"]
    expected_rollouts = tuple(
        ExpectedRollout(
            rollout_id=str(item["rollout_id"]),
            scored_step_count=int(item["scored_step_count"]),
        )
        for item in gate_a["ordered_scored_rollouts"]
    )

    resolved_trace_dir = trace_dir if trace_dir.is_absolute() else repository_root / trace_dir
    expected_names = {f"arm_{arm}.json" for arm in expected_arms}
    actual_paths = sorted(resolved_trace_dir.glob("*.json"))
    actual_names = {path.name for path in actual_paths}
    if actual_names != expected_names:
        missing = sorted(expected_names - actual_names)
        extra = sorted(actual_names - expected_names)
        raise ValueError(f"Gate B trace-file set mismatch; missing={missing}, extra={extra}")
    payloads = [json.loads(path.read_text(encoding="utf-8")) for path in actual_paths]
    return (
        gate_a,
        payloads,
        expected_arms,
        expected_rollouts,
        str(custody["trusted_custodian_key_id"]),
        str(custody["trusted_custodian_public_key_sha256"]),
        str(contract["producer_source_bundle_sha256"]),
    )


def run_structure_two_world_gate_b_v0_4(
    *,
    repository_root: Path,
    trace_dir: Path = DEFAULT_TRACE_DIR,
) -> dict[str, Any]:
    (
        gate_a,
        payloads,
        expected_arms,
        expected_rollouts,
        trusted_key_id,
        trusted_public_key_sha256,
        expected_producer_source_bundle_sha256,
    ) = _load_gate_b_inputs(
        repository_root=repository_root,
        trace_dir=trace_dir,
    )
    manifest_sha256 = str(gate_a["provenance"]["manifest_sha256"])
    scored = validate_and_score_bound_arm_traces(
        payloads,
        expected_arms=expected_arms,
        expected_rollouts=expected_rollouts,
        gate_a_content_sha256=str(gate_a["content_sha256"]),
        manifest_sha256=manifest_sha256,
        trusted_key_id=trusted_key_id,
        trusted_public_key_sha256=trusted_public_key_sha256,
        expected_producer_source_bundle_sha256=(expected_producer_source_bundle_sha256),
    )
    gate_b_passed = scored["gate_b"]["gate_b_passed"] is True
    fidelity_audit = build_external_adapter_fidelity_audit(expected_arms)
    external_fidelity_gate_passed = fidelity_audit["external_fidelity_gate_passed"] is True
    method_comparison_allowed = gate_b_passed and external_fidelity_gate_passed
    report: dict[str, Any] = {
        "protocol": PROTOCOL_ID,
        "evidence_status": (
            "fresh-world exact arm-prediction distinguishability; no endpoint or "
            "sealed holdout result was computed"
        ),
        "gate_a_artifact": str(DEFAULT_GATE_A_OUTPUT),
        "gate_a_content_sha256": gate_a["content_sha256"],
        "manifest_sha256": manifest_sha256,
        **scored,
        "gate_a_passed": True,
        "gate_b_passed": gate_b_passed,
        "external_adapter_fidelity_audit": fidelity_audit,
        "external_fidelity_gate_passed": external_fidelity_gate_passed,
        "sealed_holdout_opened": False,
        "method_comparison_allowed": method_comparison_allowed,
        "limitations": [
            (
                "The external signature proves trace custody and integrity, not the "
                "semantic fidelity of the arm adapter; the common producer source-bundle "
                "hash is reported for independent reproduction."
            ),
            (
                "Gate B pass authorizes only the claim that arm trajectories are "
                "materially distinguishable. External-method efficacy comparison remains "
                "blocked until the independent fidelity gate passes."
            ),
        ],
    }
    report["content_sha256"] = content_sha256(report)
    return report


def write_gate_b_authorization(report: Mapping[str, Any], output_path: Path) -> None:
    if output_path.exists():
        raise FileExistsError("dual-gate authorization already exists; refusing to overwrite")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(dict(report), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def verify_dual_gate_authorization(
    report_path: Path,
    *,
    repository_root: Path,
    trace_dir: Path = DEFAULT_TRACE_DIR,
    recompute: bool = True,
) -> dict[str, Any]:
    report: dict[str, Any] = json.loads(report_path.read_text(encoding="utf-8"))
    stored = report.get("content_sha256")
    unsigned = dict(report)
    unsigned.pop("content_sha256", None)
    if not isinstance(stored, str) or content_sha256(unsigned) != stored:
        raise ValueError("dual-gate authorization content hash mismatch")
    if report.get("protocol") != PROTOCOL_ID:
        raise ValueError("dual-gate authorization protocol mismatch")
    fidelity_audit = report.get("external_adapter_fidelity_audit")
    if not isinstance(fidelity_audit, dict):
        raise ValueError("dual-gate report lacks the external adapter fidelity audit")
    expected_fidelity = fidelity_audit.get("external_fidelity_gate_passed") is True
    if report.get("external_fidelity_gate_passed") is not expected_fidelity:
        raise ValueError("dual-gate report disagrees with its external fidelity result")
    expected_allowed = (
        report.get("gate_a_passed") is True
        and report.get("gate_b_passed") is True
        and expected_fidelity
    )
    inner_gate_b = report.get("gate_b")
    if not isinstance(inner_gate_b, dict) or inner_gate_b.get("gate_b_passed") is not report.get(
        "gate_b_passed"
    ):
        raise ValueError("dual-gate report disagrees with its Gate B result")
    if report.get("method_comparison_allowed") is not expected_allowed:
        raise ValueError("dual-gate method authorization decision mismatch")
    if recompute:
        expected = run_structure_two_world_gate_b_v0_4(
            repository_root=repository_root,
            trace_dir=trace_dir,
        )
        if expected["content_sha256"] != stored:
            raise ValueError("dual-gate authorization deterministic recomputation mismatch")
    return report


__all__ = [
    "DEFAULT_GATE_A_OUTPUT",
    "DEFAULT_OUTPUT",
    "DEFAULT_TRACE_DIR",
    "PROTOCOL_ID",
    "TRACE_ATTESTATION_DOMAIN",
    "TRACE_PROTOCOL_ID",
    "BoundArmTraceRecord",
    "ExpectedRollout",
    "make_bound_arm_trace_payload",
    "run_structure_two_world_gate_b_v0_4",
    "validate_and_score_bound_arm_traces",
    "verify_dual_gate_authorization",
    "write_bound_arm_trace",
    "write_gate_b_authorization",
]
