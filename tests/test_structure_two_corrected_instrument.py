from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from cpswm.system.evaluation_operations.project_two_action_benchmark import _Prediction
from cpswm.system.evaluation_operations.structure_two_corrected_instrument import (
    DEFAULT_MANIFEST,
    ExternalActionExecutionReceipt,
    _LastObservedSearchPinState,
    audit_legacy_corrected_instrument_v0_2,
    bayesian_categorical_update,
    load_corrected_instrument_design,
    price_external_repairs,
    verify_structure_two_corrected_instrument_report,
)
from cpswm.system.reproducibility import content_sha256

ROOT = Path(__file__).resolve().parents[1]


def test_corrected_v0_3_binds_current_source_and_blocks_false_legacy_claim() -> None:
    legacy_audit = audit_legacy_corrected_instrument_v0_2(ROOT)
    assert legacy_audit["immutable_manifest_and_report_match"] is True
    assert legacy_audit["legacy_source_recoverable"] is False
    assert legacy_audit["status"] == "BLOCKED_LEGACY_SOURCE_UNRECOVERABLE"
    assert legacy_audit["historical_evidence_rewritten"] is False

    design = load_corrected_instrument_design(
        ROOT / DEFAULT_MANIFEST,
        repository_root=ROOT,
    )
    assert design.validation_seeds == (
        310101,
        310102,
        310103,
        310104,
        310105,
        310106,
        310107,
        310108,
    )
    legacy = json.loads(
        (
            ROOT / "artifacts/project_two_v04_development/"
            "structure_two_strongest_neighbor_gate_v0_1.json"
        ).read_text(encoding="utf-8")
    )
    assert legacy["content_sha256"] == design.source_report_content_sha256

    report = verify_structure_two_corrected_instrument_report(
        ROOT / "artifacts/project_two_v04_development/structure_two_corrected_instrument_v0_3.json",
        repository_root=ROOT,
        recompute=False,
    )
    assert report["instrument_integrity_passed"] is True
    assert report["comparison_validity_passed"] is False
    assert report["legacy_v0_1_source_preservation_verified"] is False


def test_corrected_v0_3_rejects_false_legacy_claim_and_source_substitution(
    tmp_path: Path,
) -> None:
    manifest = json.loads((ROOT / DEFAULT_MANIFEST).read_text(encoding="utf-8"))
    manifest["legacy_v0_1_source_preservation_claim"] = True
    attack = tmp_path / "false-legacy-claim.json"
    attack.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="must not claim"):
        load_corrected_instrument_design(attack, repository_root=ROOT)

    manifest["legacy_v0_1_source_preservation_claim"] = False
    manifest["source_gate_file_sha256"] = "0" * 64
    attack.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="source binding mismatch"):
        load_corrected_instrument_design(attack, repository_root=ROOT)


def _write_rehashed_report(path: Path, report: dict[str, object]) -> None:
    unsigned = dict(report)
    unsigned.pop("content_sha256", None)
    unsigned["content_sha256"] = content_sha256(unsigned)
    path.write_text(json.dumps(unsigned), encoding="utf-8")


def test_report_verifier_rejects_rehashed_legacy_recovery_forgery(tmp_path: Path) -> None:
    source = ROOT / (
        "artifacts/project_two_v04_development/structure_two_corrected_instrument_v0_3.json"
    )
    report = json.loads(source.read_text(encoding="utf-8"))
    report["legacy_v0_2_status"] = "LEGACY_SOURCE_VERIFIED"
    report["legacy_v0_1_source_preservation_verified"] = True
    attack = tmp_path / "forged-legacy.json"
    _write_rehashed_report(attack, report)
    with pytest.raises(ValueError, match=r"legacy v0\.2 blocker"):
        verify_structure_two_corrected_instrument_report(
            attack, repository_root=ROOT, recompute=False
        )


def test_report_verifier_requires_recomputation_for_positive_comparison(
    tmp_path: Path,
) -> None:
    source = ROOT / (
        "artifacts/project_two_v04_development/structure_two_corrected_instrument_v0_3.json"
    )
    report = json.loads(source.read_text(encoding="utf-8"))
    validity = report["comparison_validity_criteria"]
    assert isinstance(validity, dict)
    report["comparison_validity_criteria"] = dict.fromkeys(validity, True)
    report["comparison_validity_passed"] = True
    report["scientific_conclusion"] = "comparison_valid_on_validation_only"
    attack = tmp_path / "forged-positive-comparison.json"
    _write_rehashed_report(attack, report)
    with pytest.raises(ValueError, match="requires deterministic recomputation"):
        verify_structure_two_corrected_instrument_report(
            attack, repository_root=ROOT, recompute=False
        )


def test_bayesian_verification_is_normalized_and_prior_sensitive() -> None:
    a, b = uuid4(), uuid4()
    first = bayesian_categorical_update(
        {a: 0.8, b: 0.2},
        observed=b,
        reliability=0.9,
        prior_floor=1e-9,
    )
    second = bayesian_categorical_update(
        {a: 0.2, b: 0.8},
        observed=b,
        reliability=0.9,
        prior_floor=1e-9,
    )
    assert sum(first.values()) == pytest.approx(1.0)
    assert sum(second.values()) == pytest.approx(1.0)
    assert first[b] != pytest.approx(0.9)
    assert first[b] < second[b]


def test_repair_pricing_requires_unique_external_execution_receipts() -> None:
    receipts = (
        ExternalActionExecutionReceipt("a", "r1", True, True),
        ExternalActionExecutionReceipt("a", "r1", True, True),
        ExternalActionExecutionReceipt("b", "r2", False, True),
        ExternalActionExecutionReceipt("c", "r3", True, False),
    )
    pricing = price_external_repairs(receipts, repair_cost=0.8)
    assert pricing.charged_unique_rollback_count == 1
    assert pricing.external_repair_cost == pytest.approx(0.8)
    assert pricing.ignored_internal_or_nonexecuted_count == 2
    assert pricing.invalid_receipt_count == 0


class _FakeState:
    def __init__(self, put_back, first, second) -> None:  # type: ignore[no-untyped-def]
        self._prediction = _Prediction(put_back, (first, second), 0.3)

    def observe(self, step) -> None:  # type: ignore[no-untyped-def]
        del step

    def predict(self) -> _Prediction:
        return self._prediction

    def feedback(self, step) -> None:  # type: ignore[no-untyped-def]
        del step


class _VisibleStep:
    def __init__(self, location) -> None:  # type: ignore[no-untyped-def]
        self.after = type("After", (), {"detected_location_id": location})()


def test_dual_task_readout_changes_search_only() -> None:
    put_back, native_first, last = uuid4(), uuid4(), uuid4()
    state = _LastObservedSearchPinState(_FakeState(put_back, native_first, last))
    state.observe(_VisibleStep(last))  # type: ignore[arg-type]
    prediction = state.predict()
    assert prediction.put_back == put_back
    assert prediction.search_order == (last, native_first)
    assert state.search_pin_change_count == 1
    assert state.search_pin_violation_count == 0
