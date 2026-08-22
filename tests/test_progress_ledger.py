"""Progress ledger validator and tamper-detection tests."""

from __future__ import annotations

import json
from pathlib import Path

from cpswm.system.progress_ledger import Maturity, ProgressLedger, validate_ledger

REPO_ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = REPO_ROOT / "src" / "cpswm" / "system" / "progress_ledger" / "progress_ledger.json"


def _load() -> ProgressLedger:
    data = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    return ProgressLedger.model_validate(data)


def _module(ledger: ProgressLedger, module_id: str):
    return next(item for item in ledger.modules if item.module_id == module_id)


def test_ledger_reports_blocked_b1_gate():
    ledger = _load()
    report = validate_ledger(ledger, REPO_ROOT)
    b1 = next(gate for gate in report.gate_results if gate.gate_id == "B1_SYNTHETIC_READINESS")
    assert not b1.passed
    # M07-M12 are below synthetic_vertical_slice and must appear as blockers.
    assert any("M07" in blocker for blocker in b1.blockers)


def test_ledger_reports_blocked_structure_one_gate():
    ledger = _load()
    report = validate_ledger(ledger, REPO_ROOT)
    gate = next(gate for gate in report.gate_results if gate.gate_id == "STRUCTURE_ONE_COMPLETE")
    assert not gate.passed


def test_coverage_matrix_covers_all_modules():
    ledger = _load()
    report = validate_ledger(ledger, REPO_ROOT)
    assert set(report.coverage_matrix.keys()) == {f"M{i:02d}" for i in range(1, 33)}


def test_validator_never_upgrades_maturity():
    ledger = _load()
    before = {item.module_id: item.maturity for item in ledger.modules}
    validate_ledger(ledger, REPO_ROOT)
    after = {item.module_id: item.maturity for item in ledger.modules}
    assert before == after


def test_missing_module_is_an_error():
    ledger = _load()
    data = ledger.model_dump(mode="json")
    data["modules"] = [item for item in data["modules"] if item["module_id"] != "M07"]
    report = validate_ledger(ProgressLedger.model_validate(data), REPO_ROOT)
    assert any("M07" in error and "missing" in error for error in report.errors)


def test_b1_gate_cannot_be_rewritten_to_atg1():
    ledger = _load()
    data = ledger.model_dump(mode="json")
    for gate in data["gates"]:
        if gate["gate_id"] == "B1_SYNTHETIC_READINESS":
            gate["required_module_ids"] = ["ATG-1"]
    report = validate_ledger(ProgressLedger.model_validate(data), REPO_ROOT)
    assert any("must require exactly M05-M12" in error for error in report.errors)


def test_synthetic_evidence_cannot_pose_as_real_validation():
    ledger = _load()
    data = ledger.model_dump(mode="json")
    for item in data["modules"]:
        if item["module_id"] == "M17":
            item["maturity"] = Maturity.REAL_DATA_VALIDATED.value
    report = validate_ledger(ProgressLedger.model_validate(data), REPO_ROOT)
    assert any("M17" in error and "real-data evidence" in error for error in report.errors)


def test_missing_referenced_file_is_an_error():
    ledger = _load()
    data = ledger.model_dump(mode="json")
    for item in data["modules"]:
        if item["module_id"] == "M01":
            item["implementation_paths"] = ["src/cpswm/does_not_exist.py"]
    report = validate_ledger(ProgressLedger.model_validate(data), REPO_ROOT)
    assert any("M01" in error and "missing" in error for error in report.errors)


def test_claim_cannot_exceed_maturity():
    ledger = _load()
    data = ledger.model_dump(mode="json")
    for item in data["modules"]:
        if item["module_id"] == "M01":
            item["allowed_claims"] = ["full embodied system"]
    report = validate_ledger(ProgressLedger.model_validate(data), REPO_ROOT)
    assert any("M01" in error for error in report.errors)


def test_internally_consistent_is_separate_from_gates_passed():
    ledger = _load()
    report = validate_ledger(ledger, REPO_ROOT)
    # The ledger is internally consistent (no errors) even though required
    # gates are still BLOCK.
    assert report.internally_consistent is True
    assert report.required_gates_passed is False


def test_contract_only_requires_implementation_and_test():
    ledger = _load()
    data = ledger.model_dump(mode="json")
    for item in data["modules"]:
        if item["module_id"] == "M01":
            item["test_paths"] = []
    report = validate_ledger(ProgressLedger.model_validate(data), REPO_ROOT)
    assert any("M01" in error and "test path" in error for error in report.errors)


def test_evidence_content_hash_is_verified():
    ledger = _load()
    data = ledger.model_dump(mode="json")
    for item in data["modules"]:
        if item["module_id"] == "M17":
            item["evidence_artifacts"] = [
                {
                    "path": "tests/test_base_contracts.py",
                    "kind": "synthetic",
                    "description": "tampered hash",
                    "content_sha256": "0" * 64,
                    "artifact_schema": "synthetic_report_json_v1",
                    "run_receipt": "run-1",
                }
            ]
    report = validate_ledger(ProgressLedger.model_validate(data), REPO_ROOT)
    assert any("content hash mismatch" in error for error in report.errors)
