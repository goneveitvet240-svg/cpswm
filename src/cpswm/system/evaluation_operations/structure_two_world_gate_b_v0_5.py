"""Signed ten-arm distinguishability Gate B for Structure Two v0.5."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
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
from cpswm.system.evaluation_operations.structure_two_world_seed_attestation_v0_5 import (
    compute_v0_5_source_bundle,
)
from cpswm.system.evaluation_operations.structure_two_world_validation_gate_v0_5 import (
    DEFAULT_MANIFEST,
    verify_validation_gate_report_v0_5,
)
from cpswm.system.evaluation_operations.structure_two_world_validation_gate_v0_5 import (
    DEFAULT_OUTPUT as DEFAULT_GATE_A_OUTPUT,
)
from cpswm.system.evaluation_operations.task_nontriviality_gates import (
    ArmPredictionTrace,
    run_gate_b,
)
from cpswm.system.reproducibility import content_sha256

PROTOCOL_ID = "structure-two-world-arm-distinguishability-gate-b@0.5"
TRACE_PROTOCOL_ID = "structure-two-world-bound-arm-prediction-trace@0.5"
TRACE_DOMAIN = "cpswm.evaluation.structure_two.bound_arm_trace.v0.5"
DEFAULT_TRACE_DIR = Path("benchmarks/structure_two/gate_b_arm_traces_v0_5")
DEFAULT_OUTPUT = Path(
    "benchmarks/structure_two/structure_two_world_dual_gate_authorization_v0_5.json"
)


class BoundArmTraceRecordV05(ContractModel):
    protocol: str = Field(pattern=r"^structure-two-world-bound-arm-prediction-trace@0\.5$")
    arm: str = Field(min_length=1)
    gate_a_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    producer_run_id: str = Field(min_length=1)
    producer_source_bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    episode_predictions: tuple[tuple[str, tuple[str, ...]], ...]
    custodian_public_key_base64: str = Field(min_length=1)
    custodian_public_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    attestation: Attestation | None = None


def make_bound_arm_trace_payload_v0_5(
    *,
    arm: str,
    gate_a_content_sha256: str,
    manifest_sha256: str,
    producer_run_id: str,
    producer_source_bundle_sha256: str,
    episode_predictions: Sequence[tuple[str, Sequence[str]]],
    signer: Ed25519AttestationSigner,
) -> dict[str, Any]:
    verifier = signer.verifier()
    unsigned = BoundArmTraceRecordV05(
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
        update={"attestation": signer.sign(TRACE_DOMAIN, attested_payload(unsigned))}
    )
    payload = signed.model_dump(mode="json")
    payload["content_sha256"] = content_sha256(payload)
    return payload


def _verify_trace(
    payload: Mapping[str, Any], *, key_id: str, public_key_sha256: str
) -> BoundArmTraceRecordV05:
    unsigned = dict(payload)
    stored = unsigned.pop("content_sha256", None)
    if not isinstance(stored, str) or content_sha256(unsigned) != stored:
        raise ValueError("v0.5 arm trace content hash mismatch")
    record = BoundArmTraceRecordV05.model_validate(unsigned)
    if record.custodian_public_key_sha256 != public_key_sha256:
        raise AttestationError("v0.5 arm trace is outside the trust anchor")
    verifier = Ed25519AttestationVerifier.from_public_key_base64(
        key_id=key_id, public_key_base64=record.custodian_public_key_base64
    )
    if verifier.public_key_sha256 != public_key_sha256 or record.attestation is None:
        raise AttestationError("v0.5 arm trace key or signature is invalid")
    verifier.verify(TRACE_DOMAIN, attested_payload(record), record.attestation)
    return record


def run_structure_two_world_gate_b_v0_5(
    *, repository_root: Path, trace_dir: Path = DEFAULT_TRACE_DIR
) -> dict[str, Any]:
    gate_a_path = repository_root / DEFAULT_GATE_A_OUTPUT
    if not gate_a_path.is_file():
        raise ValueError("v0.5 Gate A report is missing; Gate B remains forbidden")
    gate_a = verify_validation_gate_report_v0_5(
        gate_a_path,
        repository_root=repository_root,
        recompute=True,
    )
    if gate_a.get("gate_a_passed") is not True:
        raise ValueError("v0.5 Gate A did not authorize Gate B")
    manifest_path = repository_root / DEFAULT_MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    contract = manifest["gate_b_contract"]
    arms = tuple(str(item) for item in contract["expected_arms"])
    custody = manifest["freeze_authorization"]
    key_id = str(custody["trusted_custodian_key_id"])
    public_hash = str(custody["trusted_custodian_public_key_sha256"])
    source = compute_v0_5_source_bundle(repository_root)
    if source.content_sha256 != contract["producer_source_bundle_sha256"]:
        raise ValueError("v0.5 Gate B source bundle mismatch")
    resolved = trace_dir if trace_dir.is_absolute() else repository_root / trace_dir
    paths = sorted(resolved.glob("arm_*.json"))
    if {path.name for path in paths} != {f"arm_{arm}.json" for arm in arms}:
        raise ValueError("v0.5 Gate B signed trace set mismatch")
    by_arm: dict[str, BoundArmTraceRecordV05] = {}
    manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    expected_rollouts = tuple(
        (str(item["rollout_id"]), int(item["scored_step_count"]))
        for item in gate_a["ordered_scored_rollouts"]
    )
    traces: list[ArmPredictionTrace] = []
    producer_runs: set[str] = set()
    for path in paths:
        record = _verify_trace(
            json.loads(path.read_text(encoding="utf-8")),
            key_id=key_id,
            public_key_sha256=public_hash,
        )
        if record.arm in by_arm:
            raise ValueError("duplicate v0.5 Gate B arm")
        if record.arm not in arms:
            raise ValueError("unexpected v0.5 Gate B arm")
        if record.gate_a_content_sha256 != gate_a["content_sha256"]:
            raise ValueError("v0.5 arm trace names the wrong Gate A")
        if record.manifest_sha256 != manifest_sha256:
            raise ValueError("v0.5 arm trace names the wrong manifest")
        if record.producer_source_bundle_sha256 != source.content_sha256:
            raise ValueError("v0.5 arm trace names the wrong source bundle")
        observed = tuple((row[0], len(row[1])) for row in record.episode_predictions)
        if observed != expected_rollouts:
            raise ValueError("v0.5 arm trace rollout order or length mismatch")
        by_arm[record.arm] = record
        producer_runs.add(record.producer_run_id)
    if set(by_arm) != set(arms) or len(producer_runs) != 1:
        raise ValueError("v0.5 arms are incomplete or come from different producer runs")
    for arm in arms:
        traces.append(
            ArmPredictionTrace(
                arm=arm,
                episode_predictions=by_arm[arm].episode_predictions,
            )
        )
    gate_b = run_gate_b(
        traces,
        min_pairwise_prediction_disagreement_rate=(
            GATE_B_MIN_PAIRWISE_PREDICTION_DISAGREEMENT_RATE
        ),
        min_episode_fraction_with_multiple_arm_trajectories=(
            GATE_B_MIN_EPISODE_FRACTION_WITH_MULTIPLE_ARM_TRAJECTORIES
        ),
    )
    passed = gate_b["gate_b_passed"] is True
    fidelity = build_external_adapter_fidelity_audit(arms)
    fidelity_passed = fidelity["external_fidelity_gate_passed"] is True
    report: dict[str, Any] = {
        "protocol": PROTOCOL_ID,
        "gate_a_passed": True,
        "gate_b": gate_b,
        "gate_b_passed": passed,
        "external_adapter_fidelity_audit": fidelity,
        "external_fidelity_gate_passed": fidelity_passed,
        "proxy_method_comparison_allowed": passed,
        "official_method_comparison_allowed": passed and fidelity_passed,
        "method_comparison_allowed": passed and fidelity_passed,
        "sealed_holdout_opened": False,
        "producer_run_id": next(iter(producer_runs)),
        "producer_source_bundle_sha256": source.content_sha256,
        "gate_a_content_sha256": gate_a["content_sha256"],
        "manifest_sha256": manifest_sha256,
        "claim_boundary": (
            "Gate A and B can authorize transparent proxy/baseline comparison; official "
            "external-method claims additionally require the independent fidelity gate."
        ),
    }
    report["content_sha256"] = content_sha256(report)
    return report


def verify_gate_b_report_v0_5(
    report_path: Path, *, repository_root: Path, recompute: bool = True
) -> dict[str, Any]:
    report: dict[str, Any] = json.loads(report_path.read_text(encoding="utf-8"))
    unsigned = dict(report)
    stored = unsigned.pop("content_sha256", None)
    if not isinstance(stored, str) or content_sha256(unsigned) != stored:
        raise ValueError("v0.5 Gate B report content hash mismatch")
    if report.get("protocol") != PROTOCOL_ID:
        raise ValueError("v0.5 Gate B report protocol mismatch")
    inner_gate_b = report.get("gate_b")
    if not isinstance(inner_gate_b, dict) or inner_gate_b.get("gate_b_passed") is not report.get(
        "gate_b_passed"
    ):
        raise ValueError("v0.5 Gate B report disagrees with its scored gate")
    expected_official = (
        report.get("gate_a_passed") is True
        and report.get("gate_b_passed") is True
        and report.get("external_fidelity_gate_passed") is True
    )
    if report.get("official_method_comparison_allowed") is not expected_official:
        raise ValueError("v0.5 official-method authorization mismatch")
    if report.get("method_comparison_allowed") is not expected_official:
        raise ValueError("v0.5 legacy method authorization mismatch")
    if report.get("proxy_method_comparison_allowed") is not (
        report.get("gate_a_passed") is True and report.get("gate_b_passed") is True
    ):
        raise ValueError("v0.5 proxy comparison authorization mismatch")
    if recompute:
        expected = run_structure_two_world_gate_b_v0_5(repository_root=repository_root)
        if expected["content_sha256"] != stored:
            raise ValueError("v0.5 Gate B deterministic recomputation mismatch")
    return report


__all__ = [
    "DEFAULT_OUTPUT",
    "DEFAULT_TRACE_DIR",
    "PROTOCOL_ID",
    "TRACE_DOMAIN",
    "TRACE_PROTOCOL_ID",
    "BoundArmTraceRecordV05",
    "make_bound_arm_trace_payload_v0_5",
    "run_structure_two_world_gate_b_v0_5",
    "verify_gate_b_report_v0_5",
]
