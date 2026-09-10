from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

import cpswm.system.evaluation_operations.structure_two_runtime_identity_gate as gate_module
from cpswm.system.evaluation_operations.structure_two_runtime_identity_gate import (
    CLAIM_BOUNDARY,
    SELECTED_GLOBAL_RUNTIME,
    ArchitectureSelectionStatus,
    RuntimeIdentityEvidenceStatus,
    build_structural_non_vacuity_fixture,
    copy_and_rehash_report,
    load_runtime_identity_gate_config,
    run_runtime_identity_gate_audit,
    verify_runtime_identity_evidence,
    verify_runtime_identity_gate_report,
)
from cpswm.system.reproducibility import content_sha256

ROOT = Path(__file__).resolve().parents[1]


def _rehash_candidate(evidence: dict[str, object]) -> str:
    events = evidence["events"]
    assert isinstance(events, list)
    previous = "GENESIS"
    for event in events:
        assert isinstance(event, dict)
        event["invocation_id"] = content_sha256(
            {
                "runtime_execution_id": event["runtime_execution_id"],
                "sequence": event["sequence"],
                "step_index": event["step_index"],
                "event_kind": event["event_kind"],
                "phase": event["phase"],
                "operator": event["operator"],
                "callable_symbol": event["callable_symbol"],
                "consumer_kind": event["consumer_kind"],
            }
        )
        event["previous_receipt_sha256"] = previous
        unsigned = dict(event)
        unsigned.pop("receipt_sha256", None)
        event["receipt_sha256"] = content_sha256(unsigned)
        previous = str(event["receipt_sha256"])
    evidence["event_head_sha256"] = previous
    evidence.pop("content_sha256", None)
    evidence["content_sha256"] = content_sha256(evidence)
    return str(evidence["content_sha256"])


@pytest.fixture(scope="module")
def current_report() -> dict[str, object]:
    return run_runtime_identity_gate_audit(repository_root=ROOT)


def test_configuration_records_explicit_architecture_a_selection() -> None:
    config = load_runtime_identity_gate_config(ROOT)

    assert config.expected_observed_route_runtime.endswith(".LearnedInteractionRuntime")
    assert config.expected_sidecar_runtime == SELECTED_GLOBAL_RUNTIME
    assert config.architecture_selection_status == (
        ArchitectureSelectionStatus.A_SELECTED_STRUCTURE_TWO_PRODUCTION_SYSTEM
    )
    assert set(config.required_operators) == {
        "opceu",
        "orrer_cheh",
        "pchmp",
        "cf_bocpd",
        "ccrr",
        "rgrc",
        "ciav",
    }
    assert "invocation_id" in config.required_trace_binding_fields
    assert CLAIM_BOUNDARY.endswith("development evidence.")


def test_current_route_c_audit_distinguishes_trajectory_runtime_from_sidecar(
    current_report: dict[str, object],
) -> None:
    observed = current_report["observed_route_runtime"]
    sidecar = current_report["sidecar_production_manifest"]
    trace = current_report["trace_binding_audit"]
    assert isinstance(observed, dict)
    assert isinstance(sidecar, dict)
    assert isinstance(trace, dict)

    assert observed["symbol"].endswith(".LearnedInteractionRuntime")
    assert observed["produces_closed_loop_rows"] is True
    assert sidecar["assembly_class"].endswith(".StructureTwoProductionSystem")
    assert sidecar["built_after_all_registered_route_calls"] is True
    assert sidecar["builder_constructs_a_distinct_runtime"] is True
    assert sidecar["trajectory_runtime_bound"] is False
    assert sidecar["role"] == "POST_RUN_STATIC_SIDECAR_NOT_TRAJECTORY_RUNTIME_EVIDENCE"


def test_current_route_c_runtime_identity_gate_fails_closed(
    current_report: dict[str, object],
) -> None:
    trace = current_report["trace_binding_audit"]
    assert isinstance(trace, dict)

    assert trace["audited_run_count"] > 0
    assert trace["audited_operator_receipt_count"] > 0
    assert trace["per_run_runtime_execution_binding_present"] is False
    assert trace["operator_instance_binding_present"] is False
    assert trace["callable_invocation_binding_present"] is False
    assert trace["call_consumption_binding_present"] is False
    assert trace["all_required_receipt_fields_present"] is False
    assert (
        current_report["evidence_status"]
        == RuntimeIdentityEvidenceStatus.MISSING_LIVE_RUNTIME_OPERATOR_CALL_CONSUMPTION_BINDING
    )
    assert current_report["runtime_identity_gate_passed"] is False
    assert current_report["production_runtime_equivalence_established"] is False
    assert current_report["independent_custody_established"] is False


def test_current_report_selects_architecture_a_without_rewriting_history(
    current_report: dict[str, object],
) -> None:
    assert current_report["architecture_selection_status"] == (
        ArchitectureSelectionStatus.A_SELECTED_STRUCTURE_TWO_PRODUCTION_SYSTEM
    )
    assert current_report["selected_global_runtime"] == SELECTED_GLOBAL_RUNTIME
    assert current_report["global_architecture_selected"] is True
    assert current_report["runtime_identity_gate_passed"] is False
    assert current_report["production_runtime_equivalence_established"] is False
    assert current_report["independent_custody_established"] is False


def test_historical_artifact_integrity_is_independent_of_current_source_freshness(
    current_report: dict[str, object],
) -> None:
    integrity = current_report["historical_artifact_integrity"]
    freshness = current_report["historical_source_binding_check"]
    blockers = current_report["blocking_reasons"]
    assert isinstance(integrity, dict)
    assert isinstance(freshness, dict)
    assert isinstance(blockers, list)
    assert integrity == {
        "content_sha256_verified": True,
        "embedded_production_manifest_content_sha256_verified": True,
    }
    if current_report["historical_source_binding_currently_fresh"] is True:
        assert freshness["status"] == "CURRENTLY_FRESH"
        assert freshness["failure_code"] is None
        assert "historical_source_binding_not_currently_fresh" not in blockers
    else:
        assert freshness["status"] == ("HISTORICAL_SNAPSHOT_STALE_AGAINST_CURRENT_CHECKOUT")
        assert isinstance(freshness["failure_code"], str)
        assert "historical_source_binding_not_currently_fresh" in blockers


def test_stale_historical_source_binding_is_reported_not_promoted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject_current_sources(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise ValueError(
            "Structure-Two production assembly manifest mismatch: /private/unstable/path"
        )

    artifact_path = ROOT / ("benchmarks/structure_two/structure_two_full_scientific_loop_v0_2.json")
    before = artifact_path.read_bytes()
    monkeypatch.setattr(
        gate_module,
        "verify_full_scientific_loop_result",
        reject_current_sources,
    )

    report = run_runtime_identity_gate_audit(repository_root=ROOT)

    assert artifact_path.read_bytes() == before
    assert report["historical_source_binding_currently_fresh"] is False
    detail = report["historical_source_binding_check"]
    assert isinstance(detail, dict)
    assert detail == {
        "scope": "CURRENT_CHECKOUT_SOURCE_AND_PRODUCTION_MANIFEST",
        "status": "HISTORICAL_SNAPSHOT_STALE_AGAINST_CURRENT_CHECKOUT",
        "failure_code": "PRODUCTION_ASSEMBLY_CURRENT_SOURCE_BINDING_MISMATCH",
    }
    assert "/private/unstable/path" not in str(report)
    assert "historical_source_binding_not_currently_fresh" in report["blocking_reasons"]
    assert report["runtime_identity_gate_passed"] is False
    assert report["production_runtime_equivalence_established"] is False
    assert report["independent_custody_established"] is False


def test_historical_artifact_content_tampering_fails_before_freshness_check() -> None:
    artifact = gate_module._strict_json(
        ROOT / "benchmarks/structure_two/structure_two_full_scientific_loop_v0_2.json"
    )
    artifact["scientific_superiority_established"] = True

    with pytest.raises(ValueError, match="historical Route-C artifact content hash mismatch"):
        gate_module._verify_historical_artifact_integrity(artifact)


def test_non_source_verifier_failure_is_not_mislabeled_as_stale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject_semantics(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise ValueError("development result promoted a paper-level claim")

    monkeypatch.setattr(
        gate_module,
        "verify_full_scientific_loop_result",
        reject_semantics,
    )

    with pytest.raises(ValueError, match="paper-level claim"):
        run_runtime_identity_gate_audit(repository_root=ROOT)


def test_checked_out_sources_freshly_verify_current_report(
    current_report: dict[str, object],
) -> None:
    verify_runtime_identity_gate_report(current_report, repository_root=ROOT)


def test_self_consistent_rehash_cannot_promote_the_current_gate(
    current_report: dict[str, object],
) -> None:
    forged = copy.deepcopy(current_report)
    forged["runtime_identity_gate_passed"] = True
    forged["production_runtime_equivalence_established"] = True
    trace = forged["trace_binding_audit"]
    assert isinstance(trace, dict)
    trace["per_run_runtime_execution_binding_present"] = True
    trace["operator_instance_binding_present"] = True
    trace["callable_invocation_binding_present"] = True
    trace["call_consumption_binding_present"] = True
    trace["all_required_receipt_fields_present"] = True
    forged = copy_and_rehash_report(forged)

    with pytest.raises(ValueError, match="fresh source-bound audit"):
        verify_runtime_identity_gate_report(forged, repository_root=ROOT)


def test_structural_non_vacuity_fixture_never_establishes_live_identity() -> None:
    evidence, enrollment, reference_hash = build_structural_non_vacuity_fixture()

    assessment = verify_runtime_identity_evidence(
        evidence,
        enrollment,
        evidence_reference_sha256=reference_hash,
    )
    assert len(evidence["runtime_binding"]["operator_instances"]) == 7
    assert len(evidence["events"]) == 10
    assert all("invocation_id" in event for event in evidence["events"])
    assert assessment.structural_candidate is True
    assert assessment.enrollment_reference_matched is True
    assert assessment.evidence_reference_matched is True
    assert assessment.independent_execution_authority_verified is False
    assert assessment.live_runtime_identity_established is False
    assert assessment.runtime_identity_gate_passed is False
    assert (
        assessment.evidence_status
        == RuntimeIdentityEvidenceStatus.STRUCTURAL_CANDIDATE_ONLY_NO_LIVE_EXECUTION_AUTHORITY
    )


@pytest.mark.parametrize("runtime_symbol", [None, "", "   "])
def test_structural_candidate_rejects_missing_or_blank_runtime_symbol(
    runtime_symbol: Any,
) -> None:
    evidence, enrollment, reference_hash = build_structural_non_vacuity_fixture(
        runtime_symbol=runtime_symbol
    )

    with pytest.raises(ValueError, match="runtime enrollment symbol is malformed"):
        verify_runtime_identity_evidence(
            evidence,
            enrollment,
            evidence_reference_sha256=reference_hash,
        )


def test_forged_but_complete_rehashed_runtime_identity_cannot_replace_enrollment() -> None:
    _, trusted_enrollment, trusted_reference_hash = build_structural_non_vacuity_fixture()
    forged_evidence, forged_enrollment, forged_reference_hash = (
        build_structural_non_vacuity_fixture(
            runtime_symbol=(
                "cpswm.system.structure_two_production_system.StructureTwoProductionSystem"
            )
        )
    )

    # A caller-controlled enrollment and reference can make the candidate
    # structurally consistent, but the assessment must still refuse a live
    # identity claim or gate pass.
    assessment = verify_runtime_identity_evidence(
        forged_evidence,
        forged_enrollment,
        evidence_reference_sha256=forged_reference_hash,
    )
    assert assessment.structural_candidate is True
    assert assessment.live_runtime_identity_established is False
    assert assessment.runtime_identity_gate_passed is False
    with pytest.raises(ValueError, match="retained reference"):
        verify_runtime_identity_evidence(
            forged_evidence,
            trusted_enrollment,
            evidence_reference_sha256=trusted_reference_hash,
        )


def test_complete_operator_calls_without_consumption_are_rejected() -> None:
    evidence, enrollment, _ = build_structural_non_vacuity_fixture()
    forged = copy.deepcopy(evidence)
    events = forged["events"]
    assert isinstance(events, list)
    next_state = events[-1]
    assert isinstance(next_state, dict)
    next_state["consumed_output_ids"] = []
    next_state["input_payload_sha256"] = content_sha256(
        {
            "raw_input_sha256": next_state["raw_input_sha256"],
            "consumed_outputs": [],
        }
    )
    unsigned_event = dict(next_state)
    unsigned_event.pop("receipt_sha256")
    next_state["receipt_sha256"] = content_sha256(unsigned_event)
    forged["event_head_sha256"] = next_state["receipt_sha256"]
    forged_reference_hash = _rehash_candidate(forged)

    # All caller-controlled hashes are now self-consistent; the semantic DAG
    # still fails because the next state does not consume ORRER/CHEH's output.
    with pytest.raises(ValueError, match="consequential consumer did not consume"):
        verify_runtime_identity_evidence(
            forged,
            enrollment,
            evidence_reference_sha256=forged_reference_hash,
        )


def test_raw_input_full_rehash_is_not_live_identity_evidence() -> None:
    evidence, enrollment, retained_reference_hash = build_structural_non_vacuity_fixture()
    forged = copy.deepcopy(evidence)
    events = forged["events"]
    assert isinstance(events, list)
    first = events[0]
    assert isinstance(first, dict)
    first["raw_input_sha256"] = content_sha256({"forged_raw_input": "alternate"})
    first["input_payload_sha256"] = content_sha256(
        {
            "raw_input_sha256": first["raw_input_sha256"],
            "consumed_outputs": [],
        }
    )
    forged_reference_hash = _rehash_candidate(forged)

    with pytest.raises(ValueError, match="retained reference"):
        verify_runtime_identity_evidence(
            forged,
            enrollment,
            evidence_reference_sha256=retained_reference_hash,
        )

    attacker_assessment = verify_runtime_identity_evidence(
        forged,
        enrollment,
        evidence_reference_sha256=forged_reference_hash,
    )
    assert attacker_assessment.structural_candidate is True
    assert attacker_assessment.independent_execution_authority_verified is False
    assert attacker_assessment.live_runtime_identity_established is False
    assert attacker_assessment.runtime_identity_gate_passed is False


def test_operator_output_and_consumption_full_rehash_is_not_live_identity_evidence() -> None:
    evidence, enrollment, retained_reference_hash = build_structural_non_vacuity_fixture()
    forged = copy.deepcopy(evidence)
    runtime_binding = forged["runtime_binding"]
    events = forged["events"]
    assert isinstance(runtime_binding, dict)
    assert isinstance(events, list)
    opceu = events[1]
    pchmp = events[2]
    assert isinstance(opceu, dict)
    assert isinstance(pchmp, dict)

    original_opceu_output_id = opceu["output_id"]
    forged_output_hash = content_sha256({"forged_opceu_output": "alternate"})
    opceu["output_payload_sha256"] = forged_output_hash
    forged_opceu_output_id = content_sha256(
        {
            "runtime_execution_id": runtime_binding["runtime_execution_id"],
            "sequence": opceu["sequence"],
            "output_payload_sha256": forged_output_hash,
        }
    )
    opceu["output_id"] = forged_opceu_output_id
    assert pchmp["consumed_output_ids"] == [original_opceu_output_id]
    pchmp["consumed_output_ids"] = [forged_opceu_output_id]
    pchmp["input_payload_sha256"] = content_sha256(
        {
            "raw_input_sha256": pchmp["raw_input_sha256"],
            "consumed_outputs": [(forged_opceu_output_id, forged_output_hash)],
        }
    )
    forged_reference_hash = _rehash_candidate(forged)

    with pytest.raises(ValueError, match="retained reference"):
        verify_runtime_identity_evidence(
            forged,
            enrollment,
            evidence_reference_sha256=retained_reference_hash,
        )

    attacker_assessment = verify_runtime_identity_evidence(
        forged,
        enrollment,
        evidence_reference_sha256=forged_reference_hash,
    )
    assert attacker_assessment.structural_candidate is True
    assert attacker_assessment.independent_execution_authority_verified is False
    assert attacker_assessment.live_runtime_identity_established is False
    assert attacker_assessment.runtime_identity_gate_passed is False
