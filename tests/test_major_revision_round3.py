"""Regression tests for the round-3 Major Revision findings.

Each test reproduces a defect the review demonstrated, so the fix is proved by
a failing-then-passing attack rather than asserted.  The review also required
*"at least one positive evidence/receipt test that ought to succeed"*; that is
:func:`test_a_correctly_constructed_evidence_and_receipt_pair_validates`, which
would have been impossible to write before the self-referential hash was fixed.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from ledger_evidence_fixtures import (
    TEST_AUTHORITY,
    build_payload,
    make_source_tree,
    write_evidence,
)

from cpswm.perception_mapping.adapters.validation import (
    reject_forbidden_payload_fields,
    scan_forbidden_payload_fields,
)
from cpswm.system.progress_ledger import Maturity, ProgressLedger, validate_ledger
from cpswm.system.progress_ledger.contracts import EvidenceArtifactPayload, EvidenceKind

REPO_ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = REPO_ROOT / "src" / "cpswm" / "system" / "progress_ledger" / "progress_ledger.json"


def _ledger() -> ProgressLedger:
    return ProgressLedger.model_validate(json.loads(LEDGER_PATH.read_text(encoding="utf-8")))


# --------------------------------------------------------------------------
# P0-A  the evidence gate must be reachable *and* meaningful
# --------------------------------------------------------------------------


def _payload(**overrides) -> EvidenceArtifactPayload:
    kind = EvidenceKind(overrides.pop("evidence_kind", "synthetic"))
    return build_payload(kind=kind, **overrides)


def test_the_payload_digest_is_actually_constructible():
    """The old rule asked for a SHA-256 fixed point; this one can be produced."""

    payload = _payload()

    assert payload.artifact_sha256 == payload.canonical_payload_sha256()


def test_the_digest_covers_every_field_except_itself():
    original = _payload()
    tampered = original.model_copy(update={"case_count": 9999})

    assert tampered.artifact_sha256 != tampered.canonical_payload_sha256()


def test_a_correctly_constructed_evidence_and_receipt_pair_validates(tmp_path):
    """The positive case the review asked for: honest evidence must pass.

    Writing this at all was impossible before the fix, because no byte string
    could satisfy the self-referential hash.
    """

    repo = tmp_path
    make_source_tree(repo)
    artifact = write_evidence(repo, _payload())

    ledger = _ledger()
    data = ledger.model_dump(mode="json")
    for module in data["modules"]:
        module["evidence_artifacts"] = []
        module["implementation_paths"] = []
        module["test_paths"] = []
        module["maturity"] = Maturity.ABSENT.value
        module["allowed_claims"] = []
        if module["module_id"] == "M05":
            module["maturity"] = Maturity.SYNTHETIC_VERTICAL_SLICE.value
            module["implementation_paths"] = ["src/mod.py"]
            module["test_paths"] = ["tests/test_mod.py"]
            module["evidence_artifacts"] = [artifact]

    report = validate_ledger(ProgressLedger.model_validate(data), repo, authority=TEST_AUTHORITY)
    evidence_errors = [
        error for error in report.errors if "evidence" in error or "receipt" in error
    ]

    assert evidence_errors == []


@pytest.mark.parametrize(
    ("override", "fragment"),
    [
        ({"result_status": "failed"}, "result_status"),
        ({"case_count": 0, "evidence_kind": "replay"}, "case_count=0"),
    ],
)
def test_semantically_empty_evidence_is_rejected(tmp_path, override, fragment):
    """A field that merely exists is not evidence."""

    repo = tmp_path
    make_source_tree(repo)
    payload = _payload(**override)
    # A failing run has a nonzero exit code; the receipt contract enforces the
    # pairing, so the fixture must not claim otherwise.
    receipt_overrides = {} if payload.result_status == "passed" else {"exit_code": 1}
    artifact = write_evidence(repo, payload, **receipt_overrides)

    data = _ledger().model_dump(mode="json")
    for module in data["modules"]:
        module["evidence_artifacts"] = []
        if module["module_id"] == "M05":
            module["implementation_paths"] = ["src/mod.py"]
            module["test_paths"] = ["tests/test_mod.py"]
            module["evidence_artifacts"] = [artifact]

    report = validate_ledger(ProgressLedger.model_validate(data), repo, authority=TEST_AUTHORITY)

    assert any(fragment in error for error in report.errors)


@pytest.mark.parametrize(
    "escaping_path",
    ["../outside/evidence.json", "evidence/../../outside/evidence.json", "/etc/passwd"],
)
def test_an_evidence_path_that_escapes_the_repository_is_rejected(tmp_path, escaping_path):
    """String comparison cannot see ``a/../b``; containment uses the resolved path."""

    data = _ledger().model_dump(mode="json")
    for module in data["modules"]:
        if module["module_id"] == "M05":
            module["evidence_artifacts"] = [
                {
                    "path": escaping_path,
                    "kind": "synthetic",
                    "description": "report",
                    "content_sha256": "0" * 64,
                    "artifact_schema": "synthetic_report_json_v1",
                    "run_receipt": "evidence/receipt.json",
                }
            ]

    report = validate_ledger(ProgressLedger.model_validate(data), tmp_path)

    assert any("inside the repository" in error for error in report.errors)


# --------------------------------------------------------------------------
# P0-C  a gate whose shape was tampered with must not report PASS
# --------------------------------------------------------------------------


def test_lowering_min_maturity_in_the_json_cannot_make_a_gate_pass():
    """The review lowered every gate to ``absent`` and still saw three PASSes."""

    data = _ledger().model_dump(mode="json")
    for gate in data["gates"]:
        gate["min_maturity"] = Maturity.ABSENT.value

    report = validate_ledger(ProgressLedger.model_validate(data), REPO_ROOT)
    required = [gate for gate in report.gate_results if gate.required]

    assert required
    assert not report.required_gates_passed
    # The individual gate results must agree with the overall verdict.
    assert all(not gate.passed for gate in required)
    assert all(
        any("frozen specification" in blocker for blocker in gate.blockers) for gate in required
    )


def test_rewriting_a_gate_module_list_also_blocks_that_gate():
    data = _ledger().model_dump(mode="json")
    for gate in data["gates"]:
        if gate["gate_id"] == "B1_SYNTHETIC_READINESS":
            gate["required_module_ids"] = ["ATG-1"]

    report = validate_ledger(ProgressLedger.model_validate(data), REPO_ROOT)
    b1 = next(gate for gate in report.gate_results if gate.gate_id == "B1_SYNTHETIC_READINESS")

    assert not b1.passed


# --------------------------------------------------------------------------
# P1-D  homoglyph field names
# --------------------------------------------------------------------------


# The homoglyph samples below are the attack, so ruff's ambiguous-character
# warning is correct and the samples must stay verbatim.
@pytest.mark.parametrize(
    "key",
    [
        "groundｔruth",  # fullwidth t, closed by NFKC
        "groundtruтh",  # Cyrillic te, closed by the non-ASCII rule
        "GROUND_TRUTH",
        "groundTruth",
        "ground-truth",
        "ground truth",
    ],
)
def test_evaluator_only_field_names_cannot_be_spelled_around(key):
    found = scan_forbidden_payload_fields({key: 1})

    assert found, f"{key!r} was not detected"
    with pytest.raises(Exception, match="evaluator-only"):
        reject_forbidden_payload_fields({key: 1})


def test_a_plain_ascii_payload_key_is_still_allowed():
    assert scan_forbidden_payload_fields({"depth_image": 1, "nested": {"pose": [1, 2]}}) == []


# --------------------------------------------------------------------------
# P1-E  NaN threshold and ambiguous sync
# --------------------------------------------------------------------------


def _sync_scenario(*, uncertainty_seconds: float = 0.01):
    """A registry with one calibration, one matching sync, and one envelope."""

    from datetime import UTC, datetime, timedelta
    from uuid import uuid4

    from cpswm.contracts import SourceType, ValidTimeInterval
    from cpswm.perception_mapping.adapters import (
        ObservationEnvelope,
        SensorModality,
        SensorRef,
    )
    from cpswm.perception_mapping.calibration_sync import (
        CalibrationRegistry,
        IntrinsicsModel,
        SensorTimeSyncResult,
    )

    start = datetime(2026, 8, 10, 8, 0, tzinfo=UTC)
    household = uuid4()
    session = uuid4()
    trace = uuid4()
    registry = CalibrationRegistry()
    registry.create_calibration(
        sensor=SensorRef(sensor_id="cam-1", modality=SensorModality.RGB),
        frame_id="cam_1_optical",
        household_id=household,
        valid_time=ValidTimeInterval(start=start, end=start + timedelta(minutes=10)),
        intrinsics=IntrinsicsModel(model="pinhole", parameters={"fx": 500.0}),
    )
    registry.record_sync(
        SensorTimeSyncResult(
            household_id=household,
            sensor_id="cam-1",
            source_clock_domain="sensor",
            target_clock_domain="host",
            source_time=start,
            target_time=start + timedelta(seconds=0.25),
            offset_seconds=0.25,
            uncertainty_seconds=uncertainty_seconds,
            sync_version="0.1.0",
            valid_time=ValidTimeInterval(start=start, end=start + timedelta(minutes=10)),
        )
    )
    envelope = ObservationEnvelope.model_validate(
        dict(
            metadata=dict(
                schema_name="x",
                schema_version="0.1.0",
                household_id=household,
                session_id=session,
                trace_id=trace,
                source_type=SourceType.SIMULATION.value,
                source_id="s",
            ),
            identity=dict(household_id=household, session_id=session, trace_id=trace),
            sensor=dict(sensor_id="cam-1", modality=SensorModality.RGB.value),
            capture_time=start,
            arrival_time=start,
            clock_domain="sensor",
            frame_id="cam_1_optical",
            payload=dict(payload_sha256="0" * 64, size_bytes=0),
        )
    )
    return registry, envelope


@pytest.mark.parametrize("threshold", [float("nan"), float("inf"), -1.0])
def test_an_incoherent_sync_uncertainty_threshold_is_rejected(threshold):
    """``x > nan`` is false for every x, so an unvalidated NaN accepts all syncs.

    The earlier version of this test asserted on ``inspect.getsource``: it
    proved two strings appear in a function body, not that the function rejects
    anything.  It would have passed against a body that computed the guard and
    then ignored the result.  This one calls the real entry point.
    """

    from cpswm.perception_mapping.calibration_sync import CalibrationConflictError

    registry, envelope = _sync_scenario()

    with pytest.raises(CalibrationConflictError, match="max_sync_uncertainty_seconds"):
        registry.apply_calibration(envelope, max_sync_uncertainty_seconds=threshold)


def test_a_finite_threshold_still_accepts_a_tight_sync_and_rejects_a_loose_one():
    """The guard must not become a blanket refusal: the honest path still works."""

    from cpswm.perception_mapping.calibration_sync import CalibrationConflictError

    registry, envelope = _sync_scenario(uncertainty_seconds=0.001)

    accepted = registry.apply_calibration(envelope, max_sync_uncertainty_seconds=0.01)
    assert accepted.sync_result_id is not None

    with pytest.raises(CalibrationConflictError, match="exceeds the tolerated maximum"):
        registry.apply_calibration(envelope, max_sync_uncertainty_seconds=0.0001)


def test_a_nan_threshold_would_have_accepted_a_999_second_sync():
    """The arithmetic behind the bug, kept so the guard's purpose stays legible."""

    assert not (float("nan") < 999.0)
    assert not (math.isfinite(float("nan")) and float("nan") >= 0.0)
