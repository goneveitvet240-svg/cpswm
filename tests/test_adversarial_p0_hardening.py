"""Adversarial regression tests for the P0/P1 hardening pass.

Each test reproduces one reported attack and asserts it is now rejected.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from cpswm.contracts import (
    BaseRecordMetadata,
    InputWatermark,
    SourceType,
    ValidTimeInterval,
)
from cpswm.perception_mapping.adapters import (
    ObservationEnvelope,
    ObservationEnvelopeValidationError,
    OracleAccessDecision,
    SensorModality,
    SensorRef,
    SyntheticSimulatorAdapter,
)
from cpswm.perception_mapping.calibration_sync import (
    CalibrationRegistry,
    IntrinsicsModel,
    SensorTimeSyncResult,
)
from cpswm.system.privacy_governance import (
    CapabilityGrant,
    CapabilityRevocation,
    GovernanceConflictError,
    HouseholdGovernance,
    Operation,
    OracleAccessRequest,
    ResourceKind,
)
from cpswm.system.progress_ledger import ProgressLedger, validate_ledger
from simobs import SyntheticObservation

START = datetime(2026, 8, 10, 8, 0, tzinfo=UTC)
REPO_ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = REPO_ROOT / "src" / "cpswm" / "system" / "progress_ledger" / "progress_ledger.json"


def _metadata(household_id):
    return BaseRecordMetadata(
        schema_name="cpswm.privacy.Record",
        schema_version="0.1.0",
        household_id=household_id,
        session_id=uuid4(),
        recorded_time=START,
        source_type=SourceType.MODEL,
        source_id="adversary-test",
    )


def _grant(household_id, subject="evaluator.benchmark"):
    return CapabilityGrant(
        metadata=_metadata(household_id),
        subject=subject,
        household_id=household_id,
        resource=ResourceKind.GT,
        operation=Operation.READ,
        purpose="evaluation_only",
        valid_time=ValidTimeInterval(start=START, end=START + timedelta(minutes=60)),
        issuer="adversary-test",
    )


def _observation(payload, *, oracle_channel=False, ground_truth_refs=()):
    household = uuid4()
    session = uuid4()
    trace = uuid4()
    return SyntheticObservation(
        metadata=dict(
            schema_name="simobs.SyntheticObservation",
            schema_version="0.1.0",
            household_id=household,
            session_id=session,
            recorded_time=START,
            source_type=SourceType.SIMULATION.value,
            source_id="sim-source",
            trace_id=trace,
        ),
        observation_type="rgb",
        payload=payload,
        noise_profile_id="controlled_noise_v1",
        oracle_channel=oracle_channel,
        ground_truth_refs=ground_truth_refs,
    )


# --------------------------------------------------------------------- P0-1


def test_P0_1_forged_decision_receipt_is_rejected():
    household = uuid4()
    governance = HouseholdGovernance()
    forged = OracleAccessDecision(
        metadata=_metadata(household),
        request_id=uuid4(),
        request_hash="0" * 64,
        grant_id=uuid4(),
        caller="attacker",
        household_id=household,
        allowed=True,
        decided_by="attacker",
        decided_time=START,
        input_watermark=InputWatermark(
            global_commit_seq=0,
            transaction_id=uuid4(),
            recorded_at=START,
        ),
    )
    adapter = SyntheticSimulatorAdapter(governance=governance)
    observation = _observation({"frame": 1}, oracle_channel=True, ground_truth_refs=(uuid4(),))
    with pytest.raises(ObservationEnvelopeValidationError):
        adapter.adapt(
            observation,
            sensor=SensorRef(sensor_id="cam-1", modality=SensorModality.RGB),
            frame_id="cam_1",
            oracle_authorization=forged,
        )


def test_P0_1_oracle_without_governance_is_rejected():
    adapter = SyntheticSimulatorAdapter()
    observation = _observation({"frame": 1}, oracle_channel=True, ground_truth_refs=(uuid4(),))
    household = uuid4()
    decision = OracleAccessDecision(
        metadata=_metadata(household),
        request_id=uuid4(),
        request_hash="0" * 64,
        grant_id=uuid4(),
        caller="evaluator.benchmark",
        household_id=household,
        allowed=True,
        decided_by="governance-test",
        decided_time=START,
        input_watermark=InputWatermark(
            global_commit_seq=0,
            transaction_id=uuid4(),
            recorded_at=START,
        ),
    )
    with pytest.raises(ObservationEnvelopeValidationError):
        adapter.adapt(
            observation,
            sensor=SensorRef(sensor_id="cam-1", modality=SensorModality.RGB),
            frame_id="cam_1",
            oracle_authorization=decision,
        )


# --------------------------------------------------------------------- P0-2


def test_P0_2_nested_ground_truth_in_normal_payload_is_rejected():
    adapter = SyntheticSimulatorAdapter()
    observation = _observation(
        {"nested": {"ground_truth_person_id": uuid4().hex, "latent_state": "owner_habit"}},
        oracle_channel=False,
    )
    with pytest.raises(ObservationEnvelopeValidationError):
        adapter.adapt(
            observation,
            sensor=SensorRef(sensor_id="cam-1", modality=SensorModality.RGB),
            frame_id="cam_1",
        )


def test_P0_2_ground_truth_inside_list_is_rejected():
    adapter = SyntheticSimulatorAdapter()
    observation = _observation(
        {"frames": [{"ok": 1}, {"ground_truth": True}]},
        oracle_channel=False,
    )
    with pytest.raises(ObservationEnvelopeValidationError):
        adapter.adapt(
            observation,
            sensor=SensorRef(sensor_id="cam-1", modality=SensorModality.RGB),
            frame_id="cam_1",
        )


# --------------------------------------------------------------------- P0-3


def test_P0_3_audit_fields_come_from_decision_not_caller():
    household = uuid4()
    governance = HouseholdGovernance()
    governance.issue_grant(_grant(household, subject="evaluator.benchmark"))
    watermark = InputWatermark(
        global_commit_seq=7,
        transaction_id=uuid4(),
        recorded_at=START,
    )
    request = OracleAccessRequest(
        metadata=_metadata(household),
        caller="evaluator.benchmark",
        household_id=household,
        resource=ResourceKind.GT,
        evaluation_only=True,
        purpose="evaluation_only",
        input_watermark=watermark,
    )
    decision = governance.decide_oracle_access(
        request,
        decided_by="governance-test",
        decided_time=START,
    )
    audit = governance.record_oracle_audit(
        decision_id=decision.decision_id,
        output_summary={"ok": True},
        metadata=_metadata(household),
    )
    # The audit must reflect the decision, not any attacker-supplied values.
    assert audit.caller == "evaluator.benchmark"
    assert audit.purpose == "evaluation_only"
    assert audit.input_watermark.global_commit_seq == 7


# --------------------------------------------------------------------- P1-4


def test_P1_4_cross_household_revocation_is_rejected():
    household = uuid4()
    other = uuid4()
    governance = HouseholdGovernance()
    grant = governance.issue_grant(_grant(household))
    with pytest.raises(GovernanceConflictError):
        governance.revoke(
            CapabilityRevocation(
                metadata=_metadata(other),
                grant_id=grant.grant_id,
                revoked_by="attacker",
                revoked_time=START + timedelta(minutes=2),
                reason="test",
            )
        )


def test_P1_4_revocation_before_grant_start_is_rejected():
    household = uuid4()
    governance = HouseholdGovernance()
    grant = governance.issue_grant(_grant(household))
    with pytest.raises(GovernanceConflictError):
        governance.revoke(
            CapabilityRevocation(
                metadata=_metadata(household),
                grant_id=grant.grant_id,
                revoked_by="attacker",
                revoked_time=START - timedelta(minutes=1),
                reason="test",
            )
        )


# --------------------------------------------------------------------- P1-5


def test_P1_5_parameter_hash_is_enforced():
    household = uuid4()
    good = IntrinsicsModel(model="pinhole", parameters={"fx": 500.0})
    import hashlib

    from cpswm.perception_mapping.calibration_sync import calibration_artifact_hash

    old_hash = calibration_artifact_hash(
        calibration_version="0.1.0",
        frame_id="cam_1_optical",
        intrinsics=good,
        extrinsics=None,
    )
    tampered = IntrinsicsModel(model="pinhole", parameters={"fx": 999999.0})
    from cpswm.perception_mapping.calibration_sync import SensorCalibration

    with pytest.raises(ValidationError):
        SensorCalibration(
            household_id=household,
            sensor=SensorRef(sensor_id="cam-1", modality=SensorModality.RGB),
            calibration_version="0.1.0",
            valid_time=ValidTimeInterval(start=START, end=START + timedelta(minutes=5)),
            frame_id="cam_1_optical",
            intrinsics=tampered,
            provenance_mode="parameters",
            parameters_sha256=old_hash,
        )
    # Silence unused-import warnings for hashlib by using it.
    assert hashlib.sha256(b"x").hexdigest()


# --------------------------------------------------------------------- P1-6


def test_P1_6_apply_calibration_rejects_unrelated_sync():
    household_a = uuid4()
    household_b = uuid4()
    start = START
    registry = CalibrationRegistry()
    registry.create_calibration(
        sensor=SensorRef(sensor_id="cam-1", modality=SensorModality.RGB),
        frame_id="cam_1_optical",
        household_id=household_a,
        valid_time=ValidTimeInterval(start=start, end=start + timedelta(minutes=10)),
        intrinsics=IntrinsicsModel(model="pinhole", parameters={"fx": 500.0}),
    )
    # A sync from household B / a different sensor must not apply.
    registry.record_sync(
        SensorTimeSyncResult(
            household_id=household_b,
            sensor_id="other",
            source_clock_domain="sensor",
            target_clock_domain="host",
            source_time=start,
            target_time=start + timedelta(seconds=0.25),
            offset_seconds=0.25,
            uncertainty_seconds=0.01,
            sync_version="0.1.0",
            valid_time=ValidTimeInterval(start=start, end=start + timedelta(minutes=10)),
        )
    )
    session_a = uuid4()
    trace_a = uuid4()
    envelope = ObservationEnvelope.model_validate(
        dict(
            metadata=dict(
                schema_name="x",
                schema_version="0.1.0",
                household_id=household_a,
                session_id=session_a,
                trace_id=trace_a,
                source_type=SourceType.SIMULATION.value,
                source_id="s",
            ),
            identity=dict(
                household_id=household_a,
                session_id=session_a,
                trace_id=trace_a,
            ),
            sensor=dict(sensor_id="cam-1", modality=SensorModality.RGB.value),
            capture_time=start,
            arrival_time=start,
            clock_domain="sensor",
            frame_id="cam_1_optical",
            payload=dict(payload_sha256="0" * 64, size_bytes=0),
        )
    )
    calibrated = registry.apply_calibration(envelope)
    # The unrelated sync must not be attached.
    assert calibrated.sync_result_id is None


# --------------------------------------------------------------------- P0-7


def test_P0_7_gate_substitution_is_rejected():
    ledger = ProgressLedger.model_validate(json.loads(LEDGER_PATH.read_text(encoding="utf-8")))
    data = ledger.model_dump(mode="json")
    data["gates"] = [
        {
            "gate_id": "EASY",
            "description": "tampered",
            "required": True,
            "required_module_ids": ["M01"],
            "required_workstream_ids": [],
            "min_maturity": "contract_only",
        }
    ]
    report = validate_ledger(ProgressLedger.model_validate(data), REPO_ROOT)
    assert any("is missing" in error for error in report.errors)
    assert not report.required_gates_passed


# --------------------------------------------------------------------- P0-8


def test_P0_8_one_file_fake_full_structure_is_rejected():
    ledger = ProgressLedger.model_validate(json.loads(LEDGER_PATH.read_text(encoding="utf-8")))
    data = ledger.model_dump(mode="json")
    for item in data["modules"]:
        mid = item["module_id"]
        if mid in {f"M{i:02d}" for i in range(5, 13)}:
            item["maturity"] = "real_data_validated"
        else:
            item["maturity"] = "replay_validated"
        item["implementation_paths"] = ["tests/test_base_contracts.py"]
        item["test_paths"] = ["tests/test_base_contracts.py"]
        item["evidence_artifacts"] = [
            {
                "path": "tests/test_base_contracts.py",
                "kind": "real_data",
                "description": "fake",
                "content_sha256": "0" * 64,
                "artifact_schema": "real_data_manifest_json_v1",
                "run_receipt": "run-1",
            }
        ]
    report = validate_ledger(ProgressLedger.model_validate(data), REPO_ROOT)
    assert any("content hash mismatch" in error for error in report.errors)
    assert any("cannot be a .py file" in error for error in report.errors)
    assert any("claimed by both" in error for error in report.errors)
    assert not report.required_gates_passed


# ------------------------------------------------------- new attack round


def test_P0_1_injected_decision_is_rejected_on_restore():
    household = uuid4()
    governance = HouseholdGovernance()
    grant = governance.issue_grant(_grant(household, subject="evaluator.good"))
    forged = OracleAccessDecision(
        metadata=_metadata(household),
        request_id=uuid4(),
        request_hash="0" * 64,
        grant_id=grant.grant_id,
        caller="evaluator.attacker",
        household_id=household,
        allowed=True,
        decided_by="attacker",
        decided_time=START,
        input_watermark=InputWatermark(
            global_commit_seq=0,
            transaction_id=uuid4(),
            recorded_at=START,
        ),
    )
    governance._log.append([forged], idempotency_key="injected-decision")
    restored = HouseholdGovernance(log=governance._log)
    with pytest.raises(GovernanceConflictError):
        restored.restore()


def test_P0_2_payload_alias_variants_are_rejected():
    adapter = SyntheticSimulatorAdapter()
    for key in [
        "groundTruthPersonId",
        "ground-truth-person-id",
        "ground truth person id",
        "latentState",
    ]:
        observation = _observation({key: uuid4().hex}, oracle_channel=False)
        with pytest.raises(ObservationEnvelopeValidationError):
            adapter.adapt(
                observation,
                sensor=SensorRef(sensor_id="cam-1", modality=SensorModality.RGB),
                frame_id="cam_1",
            )


def test_P0_3_gate_threshold_downgrade_is_rejected():
    ledger = ProgressLedger.model_validate(json.loads(LEDGER_PATH.read_text(encoding="utf-8")))
    data = ledger.model_dump(mode="json")
    for gate in data["gates"]:
        gate["min_maturity"] = "absent"
    report = validate_ledger(ProgressLedger.model_validate(data), REPO_ROOT)
    assert any("min_maturity must be" in error for error in report.errors)
    assert not report.required_gates_passed


def test_P0_4_unique_files_fake_completion_is_rejected():
    import hashlib

    ledger = ProgressLedger.model_validate(json.loads(LEDGER_PATH.read_text(encoding="utf-8")))
    data = ledger.model_dump(mode="json")
    # Every entry must be a tracked file, or this test fails on a clean
    # checkout for a reason that has nothing to do with the attack.
    real_files = [
        "docs/architecture/step1-a0-foundation.md",
        "pyproject.toml",
        "docs/architecture/B1_M05_M06_M28_progress_ledger.md",
    ]
    for candidate in real_files:
        assert (REPO_ROOT / candidate).is_file(), f"fixture file missing: {candidate}"
    for index, item in enumerate(data["modules"]):
        path = real_files[index % len(real_files)]
        target = REPO_ROOT / path
        content_sha256 = hashlib.sha256(target.read_bytes()).hexdigest()
        mid = item["module_id"]
        if mid in {f"M{i:02d}" for i in range(5, 13)}:
            item["maturity"] = "real_data_validated"
        else:
            item["maturity"] = "replay_validated"
        item["implementation_paths"] = [path]
        item["test_paths"] = [path]
        item["evidence_artifacts"] = [
            {
                "path": path,
                "kind": "replay",
                "description": "fake",
                "content_sha256": content_sha256,
                "artifact_schema": "replay_manifest_json_v1",
                "run_receipt": "forged-receipt",
            }
        ]
    report = validate_ledger(ProgressLedger.model_validate(data), REPO_ROOT)
    assert any("run receipt missing" in error for error in report.errors)
    assert any("does not parse" in error for error in report.errors)
    assert not report.required_gates_passed


def test_P1_5_capture_time_override_is_rejected():
    household = uuid4()
    start = START
    registry = CalibrationRegistry()
    registry.create_calibration(
        sensor=SensorRef(sensor_id="cam-1", modality=SensorModality.RGB),
        frame_id="cam_1_optical",
        household_id=household,
        valid_time=ValidTimeInterval(start=start, end=start + timedelta(minutes=10)),
        intrinsics=IntrinsicsModel(model="pinhole", parameters={"fx": 500.0}),
    )
    # An envelope captured a day later is outside the calibration validity.
    later = start + timedelta(days=1)
    session_a = uuid4()
    trace_a = uuid4()
    envelope = ObservationEnvelope.model_validate(
        dict(
            metadata=dict(
                schema_name="x",
                schema_version="0.1.0",
                household_id=household,
                session_id=session_a,
                trace_id=trace_a,
                source_type=SourceType.SIMULATION.value,
                source_id="s",
            ),
            identity=dict(
                household_id=household,
                session_id=session_a,
                trace_id=trace_a,
            ),
            sensor=dict(sensor_id="cam-1", modality=SensorModality.RGB.value),
            capture_time=later,
            arrival_time=later,
            clock_domain="sensor",
            frame_id="cam_1_optical",
            payload=dict(payload_sha256="0" * 64, size_bytes=0),
        )
    )
    from cpswm.perception_mapping.calibration_sync import (
        CalibrationConflictError,
        CalibrationNotFoundError,
    )

    with pytest.raises((CalibrationConflictError, CalibrationNotFoundError)):
        registry.apply_calibration(envelope)


def test_P1_6_required_sync_missing_is_rejected():
    household = uuid4()
    start = START
    registry = CalibrationRegistry()
    registry.create_calibration(
        sensor=SensorRef(sensor_id="cam-1", modality=SensorModality.RGB),
        frame_id="cam_1_optical",
        household_id=household,
        valid_time=ValidTimeInterval(start=start, end=start + timedelta(minutes=10)),
        intrinsics=IntrinsicsModel(model="pinhole", parameters={"fx": 500.0}),
    )
    session_a = uuid4()
    trace_a = uuid4()
    envelope = ObservationEnvelope.model_validate(
        dict(
            metadata=dict(
                schema_name="x",
                schema_version="0.1.0",
                household_id=household,
                session_id=session_a,
                trace_id=trace_a,
                source_type=SourceType.SIMULATION.value,
                source_id="s",
            ),
            identity=dict(
                household_id=household,
                session_id=session_a,
                trace_id=trace_a,
            ),
            sensor=dict(sensor_id="cam-1", modality=SensorModality.RGB.value),
            capture_time=start,
            arrival_time=start,
            clock_domain="sensor",
            frame_id="cam_1_optical",
            payload=dict(payload_sha256="0" * 64, size_bytes=0),
        )
    )
    from cpswm.perception_mapping.calibration_sync import CalibrationConflictError

    with pytest.raises(CalibrationConflictError):
        registry.apply_calibration(envelope, require_sync=True, target_clock="host")
