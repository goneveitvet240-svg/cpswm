from __future__ import annotations

import hashlib
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

import pytest
from pydantic import ValidationError

from cpswm.system.attestation import AttestationError, Ed25519AttestationSigner
from cpswm.system.evaluation_operations.structure_two_evidence_artifacts import (
    CrossModuleCouplingKind,
)
from cpswm.system.evaluation_operations.structure_two_task9_protocol import (
    ATTESTATION_DOMAIN,
    CANONICAL_CELLS,
    CANONICAL_CONFIRMATORY_UNIT_IDS,
    CANONICAL_COUPLINGS,
    CANONICAL_OPERATOR_PAIRS,
    DEFAULT_PROTOCOL_PATH,
    OPERATOR_IMPLEMENTATION_MANIFEST_SHA256,
    SELECTED_METHOD_RECEIPT_PATH,
    ArmSemanticTrace,
    CouplingRunEvidence,
    EnabledNoOpReason,
    FactorialCell,
    FrozenExecutionBindings,
    IndependentUnitFourCellTrace,
    OmnibusEvidence,
    OperatorExecutionOutcome,
    OperatorRuntimeReceipt,
    SemanticOutcome,
    SemanticUtilityObservation,
    Task9Coupling,
    Task9EvidenceSubmission,
    Task9VerificationReport,
    UnverifiedCustodianAttestationClaim,
    evaluate_task9_runs,
    load_task9_protocol,
    operator_runtime_receipt_payload,
    semantic_trace_sha256,
    verify_authenticated_enabled_no_op,
    verify_task9_submission,
)
from cpswm.system.reproducibility import content_sha256

ROOT = Path(__file__).resolve().parents[1]


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


@lru_cache(maxsize=1)
def _bindings() -> FrozenExecutionBindings:
    return FrozenExecutionBindings(
        information_policy_sha256=_sha("information-policy"),
        truth_access_policy_sha256=_sha("truth-policy"),
        compute_budget_sha256=_sha("compute-budget"),
        action_budget_sha256=_sha("action-budget"),
        verification_budget_sha256=_sha("verification-budget"),
        non_target_modules_sha256=_sha("non-target-modules"),
        source_bundle_sha256=_sha("source-bundle"),
    )


def _observations(cell: FactorialCell, successes: int) -> tuple[SemanticUtilityObservation, ...]:
    return tuple(
        SemanticUtilityObservation(
            episode_id=f"episode-{index}",
            action_id=f"action-{cell.value}-{index}",
            outcome_event_id=f"outcome-{cell.value}-{index}",
            outcome=SemanticOutcome.SUCCESS if index < successes else SemanticOutcome.FAILURE,
            action_cost_units=0,
            verification_actions=0,
            owner_contamination_events=0,
            safety_violations=0,
        )
        for index in range(5)
    )


def _receipt(
    *,
    run_id: str,
    unit_id: str,
    cell: FactorialCell,
    operator_id: str,
    enabled: bool,
    input_state: str,
    output_state: str,
    visible_input: str,
    raw_trace: str,
    enabled_no_op_signer: Ed25519AttestationSigner | None = None,
) -> OperatorRuntimeReceipt:
    receipt_id = f"{run_id}/operator/{operator_id}"
    invocation_ids = (f"{run_id}/invoke/{operator_id}",) if enabled else ()
    enabled_no_op = enabled and input_state == output_state
    execution_outcome = (
        OperatorExecutionOutcome.ENABLED_NO_OP
        if enabled_no_op
        else (
            OperatorExecutionOutcome.STATE_CHANGED if enabled else OperatorExecutionOutcome.DISABLED
        )
    )
    no_op_reason_code = EnabledNoOpReason.NO_ADMISSIBLE_STATE_TRANSITION if enabled_no_op else None
    no_op_evidence_sha256 = _sha(f"no-op-evidence:{receipt_id}") if enabled_no_op else None
    execution_nonce = _sha(f"nonce:{receipt_id}")
    implementation_sha = _sha(f"implementation:{operator_id}")
    event_log_sha = _sha(f"event-log:{receipt_id}")
    payload_sha = content_sha256(
        operator_runtime_receipt_payload(
            receipt_id=receipt_id,
            run_id=run_id,
            execution_nonce=execution_nonce,
            independent_unit_id=unit_id,
            cell=cell,
            operator_id=operator_id,
            enabled=enabled,
            execution_outcome=execution_outcome,
            invocation_ids=invocation_ids,
            no_op_reason_code=no_op_reason_code,
            no_op_evidence_sha256=no_op_evidence_sha256,
            implementation_sha256=implementation_sha,
            implementation_manifest_sha256=OPERATOR_IMPLEMENTATION_MANIFEST_SHA256,
            source_bundle_sha256=_bindings().source_bundle_sha256,
            input_state_sha256=input_state,
            output_state_sha256=output_state,
            visible_input_sha256=visible_input,
            raw_semantic_trace_sha256=raw_trace,
            runtime_event_log_sha256=event_log_sha,
        )
    )
    payload = operator_runtime_receipt_payload(
        receipt_id=receipt_id,
        run_id=run_id,
        execution_nonce=execution_nonce,
        independent_unit_id=unit_id,
        cell=cell,
        operator_id=operator_id,
        enabled=enabled,
        execution_outcome=execution_outcome,
        invocation_ids=invocation_ids,
        no_op_reason_code=no_op_reason_code,
        no_op_evidence_sha256=no_op_evidence_sha256,
        implementation_sha256=implementation_sha,
        implementation_manifest_sha256=OPERATOR_IMPLEMENTATION_MANIFEST_SHA256,
        source_bundle_sha256=_bindings().source_bundle_sha256,
        input_state_sha256=input_state,
        output_state_sha256=output_state,
        visible_input_sha256=visible_input,
        raw_semantic_trace_sha256=raw_trace,
        runtime_event_log_sha256=event_log_sha,
    )
    if enabled_no_op and enabled_no_op_signer is None:
        raise ValueError("test enabled-no-op fixture requires a signer")
    enabled_no_op_attestation = (
        enabled_no_op_signer.sign(ATTESTATION_DOMAIN, payload) if enabled_no_op else None
    )
    return OperatorRuntimeReceipt(
        receipt_id=receipt_id,
        run_id=run_id,
        execution_nonce=execution_nonce,
        independent_unit_id=unit_id,
        cell=cell,
        operator_id=operator_id,
        enabled=enabled,
        execution_outcome=execution_outcome,
        invocation_ids=invocation_ids,
        no_op_reason_code=no_op_reason_code,
        no_op_evidence_sha256=no_op_evidence_sha256,
        implementation_sha256=implementation_sha,
        implementation_manifest_sha256=OPERATOR_IMPLEMENTATION_MANIFEST_SHA256,
        source_bundle_sha256=_bindings().source_bundle_sha256,
        input_state_sha256=input_state,
        output_state_sha256=output_state,
        visible_input_sha256=visible_input,
        raw_semantic_trace_sha256=raw_trace,
        runtime_event_log_sha256=event_log_sha,
        receipt_payload_sha256=payload_sha,
        attestation_claim=UnverifiedCustodianAttestationClaim(
            authority_role="independent_evidence_custodian",
            attestation_domain="cpswm.structure_two.task9.operator_execution.v2",
            signature_algorithm="ed25519",
            key_id="caller-selected-untrusted-key",
            signed_receipt_sha256=payload_sha,
            custody_record_sha256=_sha(f"custody:{receipt_id}"),
            signature_hex="ab" * 64,
        ),
        enabled_no_op_attestation=enabled_no_op_attestation,
    )


def _rehashed_receipt(
    receipt: OperatorRuntimeReceipt,
    *,
    implementation_sha256: str | None = None,
    source_bundle_sha256: str | None = None,
) -> OperatorRuntimeReceipt:
    implementation = implementation_sha256 or receipt.implementation_sha256
    source_bundle = source_bundle_sha256 or receipt.source_bundle_sha256
    payload_sha = content_sha256(
        operator_runtime_receipt_payload(
            receipt_id=receipt.receipt_id,
            run_id=receipt.run_id,
            execution_nonce=receipt.execution_nonce,
            independent_unit_id=receipt.independent_unit_id,
            cell=receipt.cell,
            operator_id=receipt.operator_id,
            enabled=receipt.enabled,
            execution_outcome=receipt.execution_outcome,
            invocation_ids=receipt.invocation_ids,
            no_op_reason_code=receipt.no_op_reason_code,
            no_op_evidence_sha256=receipt.no_op_evidence_sha256,
            implementation_sha256=implementation,
            implementation_manifest_sha256=receipt.implementation_manifest_sha256,
            source_bundle_sha256=source_bundle,
            input_state_sha256=receipt.input_state_sha256,
            output_state_sha256=receipt.output_state_sha256,
            visible_input_sha256=receipt.visible_input_sha256,
            raw_semantic_trace_sha256=receipt.raw_semantic_trace_sha256,
            runtime_event_log_sha256=receipt.runtime_event_log_sha256,
        )
    )
    claim = receipt.attestation_claim.model_copy(update={"signed_receipt_sha256": payload_sha})
    return receipt.model_copy(
        update={
            "implementation_sha256": implementation,
            "source_bundle_sha256": source_bundle,
            "receipt_payload_sha256": payload_sha,
            "attestation_claim": claim,
        }
    )


def _arm(
    coupling: Task9Coupling,
    unit_id: str,
    cell: FactorialCell,
    successes: int,
    metadata: dict[str, str] | None = None,
) -> ArmSemanticTrace:
    left, right = CANONICAL_OPERATOR_PAIRS[coupling]
    left_on, right_on = {
        FactorialCell.ZERO_ZERO: (False, False),
        FactorialCell.ONE_ZERO: (True, False),
        FactorialCell.ZERO_ONE: (False, True),
        FactorialCell.ONE_ONE: (True, True),
    }[cell]
    visible = _sha(f"visible:{unit_id}")
    run_id = f"task9/{coupling.value}/{unit_id}/{cell.value}"
    observations = _observations(cell, successes)
    raw_trace = semantic_trace_sha256(observations)
    state = visible
    receipts: list[OperatorRuntimeReceipt] = []
    for operator_id in left + right:
        enabled = left_on if operator_id in left else right_on
        output = _sha(f"output:{run_id}:{operator_id}") if enabled else state
        receipts.append(
            _receipt(
                run_id=run_id,
                unit_id=unit_id,
                cell=cell,
                operator_id=operator_id,
                enabled=enabled,
                input_state=state,
                output_state=output,
                visible_input=visible,
                raw_trace=raw_trace,
            )
        )
        state = output
    return ArmSemanticTrace(
        cell=cell,
        left_operator_enabled=left_on,
        right_operator_enabled=right_on,
        run_id=run_id,
        visible_input_sha256=visible,
        semantic_trace_source_state_sha256=state,
        frozen_bindings=_bindings(),
        observations=observations,
        raw_semantic_trace_sha256=raw_trace,
        operator_runtime_receipts=tuple(receipts),
        diagnostic_metadata=metadata or {},
    )


def _unit(
    coupling: Task9Coupling,
    unit_id: str,
    *,
    positive: bool,
    metadata_only: bool = False,
) -> IndependentUnitFourCellTrace:
    successes = {
        FactorialCell.ZERO_ZERO: 0,
        FactorialCell.ONE_ZERO: 1,
        FactorialCell.ZERO_ONE: 1,
        FactorialCell.ONE_ONE: 3 if positive else 2,
    }
    return IndependentUnitFourCellTrace(
        independent_unit_id=unit_id,
        cluster_id=unit_id.split("::", maxsplit=1)[0],
        arms=tuple(
            _arm(
                coupling,
                unit_id,
                cell,
                successes[cell],
                {"nonce": f"metadata-only-{cell.value}"} if metadata_only else None,
            )
            for cell in CANONICAL_CELLS
        ),
    )


@lru_cache(maxsize=4)
def _runs(positive: bool = True, metadata_only: bool = False) -> tuple[CouplingRunEvidence, ...]:
    return tuple(
        CouplingRunEvidence(
            coupling=coupling,
            left_operator_ids=CANONICAL_OPERATOR_PAIRS[coupling][0],
            right_operator_ids=CANONICAL_OPERATOR_PAIRS[coupling][1],
            units=tuple(
                _unit(coupling, unit_id, positive=positive, metadata_only=metadata_only)
                for unit_id in CANONICAL_CONFIRMATORY_UNIT_IDS
            ),
        )
        for coupling in CANONICAL_COUPLINGS
    )


def _replace_run(
    runs: tuple[CouplingRunEvidence, ...], index: int, run: CouplingRunEvidence
) -> tuple[CouplingRunEvidence, ...]:
    return (*runs[:index], run, *runs[index + 1 :])


def test_definition_freezes_design_and_cannot_claim_a_result() -> None:
    protocol = load_task9_protocol(ROOT)
    assert protocol.definition_status.value == "DEFINED_NOT_RUN"
    assert protocol.task9_result_available is False
    assert protocol.seven_operator_ablation_authorized is False
    assert tuple(item.coupling for item in protocol.couplings) == CANONICAL_COUPLINGS
    assert protocol.factorial_cells == CANONICAL_CELLS
    assert protocol.population_commitment.confirmatory_cluster_count == 40
    assert protocol.population_commitment.confirmatory_unit_count == 80
    assert protocol.power_analysis.minimum_detectable_interaction == 0.25
    assert protocol.power_analysis.minimum_practical_interaction == 0.25
    assert protocol.power_analysis.planned_power_at_mde == 0.927
    assert protocol.operator_implementation_manifest.enrollment_status == "NOT_ENROLLED"
    assert protocol.protocol_id.endswith("@1.1")
    assert protocol.selected_method_binding.selected_method_operator_ids == (
        "opceu",
        "orrer_cheh",
        "pchmp",
        "cf_bocpd",
        "rgrc",
        "ccrr",
        "ciav",
    )
    assert protocol.selected_method_binding.task9_operator_ids == (
        "OPCEU",
        "ORRER_CHEH",
        "PCHMP",
        "CF-BOCPD",
        "RGRC",
        "CCRR",
        "CIAV",
    )
    assert all(
        item.implementation_sha256 is None
        for item in protocol.operator_implementation_manifest.operator_identities
    )
    assert protocol.independent_custody.trust_anchor_status == "NOT_ENROLLED"
    assert protocol.independent_custody.local_arithmetic_verifier_may_open_formal_gate is False


def test_local_analysis_is_diagnostic_and_formal_gate_is_hard_false() -> None:
    protocol = load_task9_protocol(ROOT)
    runs = _runs()
    report = evaluate_task9_runs(protocol, runs)
    assert report.evidence_status == "DIAGNOSTIC_ARITHMETIC_VERIFIED"
    assert report.diagnostic_positive_interaction_count == 4
    assert report.diagnostic_all_four_interactions_positive is True
    assert report.independent_attestation_verified is False
    assert report.runtime_implementation_hash_consistency_verified is True
    assert report.runtime_receipt_source_bundle_binding_verified is True
    assert report.selected_method_binding_commitment_verified is True
    assert report.enabled_no_op_count == 0
    assert report.all_enabled_no_ops_authenticated is True
    assert report.operator_implementation_identity_status == "NOT_ENROLLED"
    assert report.operator_implementation_identity_verified is False
    assert report.task9_positive_gate_passed is False
    assert report.seven_operator_ablation_authorized is False
    for analysis in report.couplings:
        assert analysis.interaction_estimate == pytest.approx(1.0)
        assert analysis.confidence_interval_low == pytest.approx(1.0)
        assert analysis.holm_adjusted_p_value <= protocol.multiplicity.alpha
        assert analysis.diagnostic_positive_interaction_established is True
    submission = Task9EvidenceSubmission(
        protocol_id=protocol.protocol_id,
        runs=runs,
        declared_analyses=report.couplings,
    )
    assert verify_task9_submission(protocol, submission) == report


@pytest.mark.parametrize(
    "attack",
    [lambda runs: runs[:-1], lambda runs: (*runs[:-1], runs[-2])],
    ids=("missing", "duplicate"),
)
def test_exact_four_couplings_are_mandatory(
    attack: Callable[[tuple[CouplingRunEvidence, ...]], tuple[CouplingRunEvidence, ...]],
) -> None:
    with pytest.raises(ValueError, match="exact four-coupling set"):
        evaluate_task9_runs(load_task9_protocol(ROOT), attack(_runs()))


@pytest.mark.parametrize(
    "attack",
    [lambda arms: arms[:-1], lambda arms: (*arms[:-1], arms[-2])],
    ids=("missing-cell", "duplicate-cell"),
)
def test_each_unit_requires_ordered_00_10_01_11(
    attack: Callable[[tuple[ArmSemanticTrace, ...]], tuple[ArmSemanticTrace, ...]],
) -> None:
    runs = _runs()
    unit = runs[0].units[0]
    forged_unit = unit.model_copy(update={"arms": attack(unit.arms)})
    forged_run = runs[0].model_copy(update={"units": (forged_unit, *runs[0].units[1:])})
    with pytest.raises((ValueError, ValidationError), match=r"00/10/01/11|at least 4"):
        evaluate_task9_runs(load_task9_protocol(ROOT), _replace_run(runs, 0, forged_run))


def test_posthoc_four_unit_selection_is_rejected() -> None:
    runs = _runs()
    forged = runs[0].model_copy(update={"units": runs[0].units[:4]})
    with pytest.raises(ValueError, match=r"exact frozen confirmatory population|posthoc"):
        evaluate_task9_runs(load_task9_protocol(ROOT), _replace_run(runs, 0, forged))


def test_two_cluster_pseudo_certainty_is_rejected() -> None:
    runs = _runs()
    units = tuple(
        unit.model_copy(update={"cluster_id": f"household-{index % 2:03d}"})
        for index, unit in enumerate(runs[0].units)
    )
    forged = runs[0].model_copy(update={"units": units})
    with pytest.raises(ValueError, match="cluster assignment changed"):
        evaluate_task9_runs(load_task9_protocol(ROOT), _replace_run(runs, 0, forged))


def test_operator_substitution_and_arbitrary_switch_boolean_are_rejected() -> None:
    protocol, runs = load_task9_protocol(ROOT), _runs()
    substituted = runs[0].model_copy(update={"left_operator_ids": ("CHEH",)})
    with pytest.raises((ValueError, ValidationError), match="operator substitution"):
        evaluate_task9_runs(protocol, _replace_run(runs, 0, substituted))
    unit = runs[0].units[0]
    arm = unit.arms[1].model_copy(update={"left_operator_enabled": False})
    forged_unit = unit.model_copy(update={"arms": (unit.arms[0], arm, *unit.arms[2:])})
    forged_run = runs[0].model_copy(update={"units": (forged_unit, *runs[0].units[1:])})
    with pytest.raises((ValueError, ValidationError), match="substituted switch semantics"):
        evaluate_task9_runs(protocol, _replace_run(runs, 0, forged_run))


def test_switch_boolean_without_operator_execution_receipt_is_rejected() -> None:
    protocol, runs = load_task9_protocol(ROOT), _runs()
    unit, arm = runs[0].units[0], runs[0].units[0].arms[3]
    forged_arm = arm.model_copy(
        update={"operator_runtime_receipts": arm.operator_runtime_receipts[:1]}
    )
    forged_unit = unit.model_copy(update={"arms": (*unit.arms[:3], forged_arm)})
    forged_run = runs[0].model_copy(update={"units": (forged_unit, *runs[0].units[1:])})
    with pytest.raises(
        (ValueError, ValidationError),
        match=r"missing, duplicate, or substituted|not bound to final runtime state",
    ):
        evaluate_task9_runs(protocol, _replace_run(runs, 0, forged_run))


def test_stale_raw_trace_hash_and_forged_receipt_are_rejected() -> None:
    protocol, runs = load_task9_protocol(ROOT), _runs()
    unit, arm = runs[0].units[0], runs[0].units[0].arms[0]
    changed = arm.observations[0].model_copy(update={"outcome": SemanticOutcome.SUCCESS})
    stale_arm = arm.model_copy(update={"observations": (changed, *arm.observations[1:])})
    stale_unit = unit.model_copy(update={"arms": (stale_arm, *unit.arms[1:])})
    stale_run = runs[0].model_copy(update={"units": (stale_unit, *runs[0].units[1:])})
    with pytest.raises((ValueError, ValidationError), match="raw semantic trace hash"):
        evaluate_task9_runs(protocol, _replace_run(runs, 0, stale_run))

    receipt = arm.operator_runtime_receipts[0]
    forged_receipt = receipt.model_copy(update={"runtime_event_log_sha256": _sha("forged")})
    forged_arm = arm.model_copy(
        update={"operator_runtime_receipts": (forged_receipt, *arm.operator_runtime_receipts[1:])}
    )
    forged_unit = unit.model_copy(update={"arms": (forged_arm, *unit.arms[1:])})
    forged_run = runs[0].model_copy(update={"units": (forged_unit, *runs[0].units[1:])})
    with pytest.raises((ValueError, ValidationError), match="receipt payload hash mismatch"):
        evaluate_task9_runs(protocol, _replace_run(runs, 0, forged_run))


def test_rehashed_cell10_operator_implementation_substitution_is_rejected() -> None:
    """Reproduce the round-two attack with a fully recomputed receipt envelope."""

    protocol, runs = load_task9_protocol(ROOT), _runs()
    unit, arm = runs[0].units[0], runs[0].units[0].arms[1]
    receipt = arm.operator_runtime_receipts[0]
    assert receipt.operator_id == "OPCEU" and arm.cell is FactorialCell.ONE_ZERO
    forged_receipt = _rehashed_receipt(
        receipt, implementation_sha256=_sha("attacker-cell10-opceu-implementation")
    )
    forged_arm = arm.model_copy(
        update={
            "operator_runtime_receipts": (
                forged_receipt,
                *arm.operator_runtime_receipts[1:],
            )
        }
    )
    forged_unit = unit.model_copy(update={"arms": (unit.arms[0], forged_arm, *unit.arms[2:])})
    forged_run = runs[0].model_copy(update={"units": (forged_unit, *runs[0].units[1:])})
    with pytest.raises((ValueError, ValidationError), match="implementation hash changed across"):
        evaluate_task9_runs(protocol, _replace_run(runs, 0, forged_run))


def test_rehashed_receipt_cannot_substitute_source_bundle() -> None:
    protocol, runs = load_task9_protocol(ROOT), _runs()
    unit, arm = runs[0].units[0], runs[0].units[0].arms[1]
    receipt = arm.operator_runtime_receipts[0]
    forged_receipt = _rehashed_receipt(receipt, source_bundle_sha256=_sha("attacker-source-bundle"))
    forged_arm = arm.model_copy(
        update={
            "operator_runtime_receipts": (
                forged_receipt,
                *arm.operator_runtime_receipts[1:],
            )
        }
    )
    forged_unit = unit.model_copy(update={"arms": (unit.arms[0], forged_arm, *unit.arms[2:])})
    forged_run = runs[0].model_copy(update={"units": (forged_unit, *runs[0].units[1:])})
    with pytest.raises((ValueError, ValidationError), match="not bound to source bundle"):
        evaluate_task9_runs(protocol, _replace_run(runs, 0, forged_run))


def test_structurally_complete_caller_forgery_never_opens_formal_gate() -> None:
    # Fixtures contain caller-selected keys and signature-shaped bytes. They can
    # pass local shape/arithmetic checks, but are not independent attestation.
    report = evaluate_task9_runs(load_task9_protocol(ROOT), _runs())
    assert report.runtime_receipt_structure_verified is True
    assert report.diagnostic_all_four_interactions_positive is True
    assert report.independent_attestation_verified is False
    assert report.task9_positive_gate_passed is False


def test_metadata_only_difference_cannot_create_semantic_interaction() -> None:
    protocol = load_task9_protocol(ROOT)
    plain = evaluate_task9_runs(protocol, _runs(False, False))
    renamed = evaluate_task9_runs(protocol, _runs(False, True))
    assert renamed.couplings == plain.couplings
    assert renamed.diagnostic_positive_interaction_count == 0
    assert renamed.task9_positive_gate_passed is False


def test_forged_effect_sample_is_rejected() -> None:
    protocol, runs = load_task9_protocol(ROOT), _runs()
    report = evaluate_task9_runs(protocol, runs)
    analysis = report.couplings[0]
    sample = analysis.unit_interactions[0]
    forged_sample = sample.model_copy(update={"interaction": 100.0})
    forged_analysis = analysis.model_copy(
        update={"unit_interactions": (forged_sample, *analysis.unit_interactions[1:])}
    )
    submission = Task9EvidenceSubmission(
        protocol_id=protocol.protocol_id,
        runs=runs,
        declared_analyses=(forged_analysis, *report.couplings[1:]),
    )
    with pytest.raises(
        (ValueError, ValidationError), match=r"semantic utility DiD|does not reproduce"
    ):
        verify_task9_submission(protocol, submission)


@pytest.mark.parametrize(
    "field", ("compute_budget_sha256", "information_policy_sha256", "non_target_modules_sha256")
)
def test_budget_information_and_non_target_substitution_is_rejected(field: str) -> None:
    protocol, runs = load_task9_protocol(ROOT), _runs()
    unit = runs[0].units[0]
    binding = unit.arms[-1].frozen_bindings.model_copy(update={field: _sha(f"attack:{field}")})
    arm = unit.arms[-1].model_copy(update={"frozen_bindings": binding})
    forged_unit = unit.model_copy(update={"arms": (*unit.arms[:-1], arm)})
    forged_run = runs[0].model_copy(update={"units": (forged_unit, *runs[0].units[1:])})
    with pytest.raises((ValueError, ValidationError), match="budget, information, source"):
        evaluate_task9_runs(protocol, _replace_run(runs, 0, forged_run))


def test_full_x_b_star_is_separate_from_exact_four_and_holm() -> None:
    omnibus = OmnibusEvidence(
        comparison_id="full_x_b_star",
        counted_toward_four_coupling_family=False,
        semantic_summary="Separate full versus independently retuned B-star comparison.",
    )
    report = evaluate_task9_runs(load_task9_protocol(ROOT), _runs(), omnibus=omnibus)
    assert len(report.couplings) == 4
    assert report.omnibus == omnibus
    assert report.omnibus_counted_toward_four_coupling_family is False
    with pytest.raises(ValueError):
        Task9Coupling("full_x_b_star")


def test_model_copy_cannot_forge_formal_gate_or_seven_operator_authority() -> None:
    report = evaluate_task9_runs(load_task9_protocol(ROOT), _runs())
    forged = report.model_copy(
        update={"task9_positive_gate_passed": True, "seven_operator_ablation_authorized": True}
    )
    with pytest.raises(ValidationError):
        Task9VerificationReport.model_validate(forged.model_dump(mode="python"))


def test_protocol_loader_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    attacked = tmp_path / "task9-duplicate.json"
    attacked.write_text('{"protocol_id":"first","protocol_id":"shadow"}', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate JSON key"):
        load_task9_protocol(ROOT, attacked)


def test_selected_method_receipt_bytes_and_orrer_cheh_identity_are_bound(
    tmp_path: Path,
) -> None:
    protocol_target = tmp_path / DEFAULT_PROTOCOL_PATH
    protocol_target.parent.mkdir(parents=True)
    protocol_target.write_bytes((ROOT / DEFAULT_PROTOCOL_PATH).read_bytes())
    selected_target = tmp_path / SELECTED_METHOD_RECEIPT_PATH
    selected_target.parent.mkdir(parents=True, exist_ok=True)
    selected_target.write_text(
        (ROOT / SELECTED_METHOD_RECEIPT_PATH)
        .read_text(encoding="utf-8")
        .replace('"orrer_cheh"', '"cheh"'),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="selected-method receipt file hash mismatch"):
        load_task9_protocol(tmp_path)

    protocol = load_task9_protocol(ROOT)
    attacked_binding = protocol.selected_method_binding.model_copy(
        update={
            "task9_operator_ids": (
                "OPCEU",
                "CHEH",
                "PCHMP",
                "CF-BOCPD",
                "RGRC",
                "CCRR",
                "CIAV",
            )
        }
    )
    attacked = protocol.model_copy(update={"selected_method_binding": attacked_binding})
    with pytest.raises(ValidationError, match="selected-method receipt binding changed"):
        type(protocol).model_validate(attacked.model_dump(mode="python"))


def test_superseded_v1_0_protocol_cannot_enter_v1_1_verifier() -> None:
    with pytest.raises(ValidationError, match=r"protocol_id|selected_method_binding"):
        load_task9_protocol(
            ROOT,
            Path(
                "configs/project_two_experiments/"
                "structure_two_task9_four_coupling_protocol_v1_0.json"
            ),
        )


def test_shared_evidence_contract_uses_same_orrer_cheh_coupling_identity() -> None:
    assert tuple(item.value for item in CrossModuleCouplingKind) == tuple(
        item.value for item in CANONICAL_COUPLINGS
    )
    with pytest.raises(ValueError):
        CrossModuleCouplingKind("cheh_pchmp_x_rgrc")


def _runs_with_one_authenticated_enabled_no_op(
    signer: Ed25519AttestationSigner,
) -> tuple[CouplingRunEvidence, ...]:
    runs = _runs()
    run, unit, arm = runs[0], runs[0].units[0], runs[0].units[0].arms[1]
    no_op = _receipt(
        run_id=arm.run_id,
        unit_id=unit.independent_unit_id,
        cell=arm.cell,
        operator_id="OPCEU",
        enabled=True,
        input_state=arm.visible_input_sha256,
        output_state=arm.visible_input_sha256,
        visible_input=arm.visible_input_sha256,
        raw_trace=arm.raw_semantic_trace_sha256,
        enabled_no_op_signer=signer,
    )
    disabled = _receipt(
        run_id=arm.run_id,
        unit_id=unit.independent_unit_id,
        cell=arm.cell,
        operator_id="CF-BOCPD",
        enabled=False,
        input_state=arm.visible_input_sha256,
        output_state=arm.visible_input_sha256,
        visible_input=arm.visible_input_sha256,
        raw_trace=arm.raw_semantic_trace_sha256,
    )
    no_op_arm = arm.model_copy(
        update={
            "semantic_trace_source_state_sha256": arm.visible_input_sha256,
            "operator_runtime_receipts": (no_op, disabled),
        }
    )
    no_op_unit = unit.model_copy(update={"arms": (unit.arms[0], no_op_arm, *unit.arms[2:])})
    no_op_run = run.model_copy(update={"units": (no_op_unit, *run.units[1:])})
    return _replace_run(runs, 0, no_op_run)


def test_enabled_no_op_requires_and_verifies_external_ed25519_attestation() -> None:
    signer = Ed25519AttestationSigner.generate(key_id="independent-task9-custodian")
    runs = _runs_with_one_authenticated_enabled_no_op(signer)
    receipt = runs[0].units[0].arms[1].operator_runtime_receipts[0]
    verify_authenticated_enabled_no_op(receipt, signer.verifier())

    with pytest.raises(AttestationError, match="external formal verification-only key"):
        evaluate_task9_runs(load_task9_protocol(ROOT), runs)

    report = evaluate_task9_runs(
        load_task9_protocol(ROOT),
        runs,
        enabled_no_op_verifier=signer.verifier(),
    )
    assert report.enabled_no_op_count == 1
    assert report.authenticated_enabled_no_op_count == 1
    assert report.all_enabled_no_ops_authenticated is True
    assert report.task9_positive_gate_passed is False
    assert report.seven_operator_ablation_authorized is False

    attacker = Ed25519AttestationSigner.generate(key_id="attacker-task9-custodian")
    with pytest.raises(AttestationError, match="not this verifier's key"):
        evaluate_task9_runs(
            load_task9_protocol(ROOT),
            runs,
            enabled_no_op_verifier=attacker.verifier(),
        )


def test_duck_typed_verifier_cannot_fake_enabled_no_op_authentication() -> None:
    class CallerControlledVerifier:
        key_id = "caller-controlled"
        formal_grade = True

        def verify(self, *_args: object, **_kwargs: object) -> None:
            return None

    signer = Ed25519AttestationSigner.generate(key_id="independent-task9-custodian")
    with pytest.raises(AttestationError, match="formal asymmetric verifier"):
        evaluate_task9_runs(
            load_task9_protocol(ROOT),
            _runs_with_one_authenticated_enabled_no_op(signer),
            enabled_no_op_verifier=CallerControlledVerifier(),  # type: ignore[arg-type]
        )


def test_enabled_no_op_signature_binds_reason_and_evidence_after_rehash() -> None:
    signer = Ed25519AttestationSigner.generate(key_id="independent-task9-custodian")
    receipt = _runs_with_one_authenticated_enabled_no_op(signer)[0].units[0].arms[1]
    original = receipt.operator_runtime_receipts[0]
    attacked_reason = EnabledNoOpReason.POSTCONDITION_ALREADY_SATISFIED
    attacked_payload = operator_runtime_receipt_payload(
        receipt_id=original.receipt_id,
        run_id=original.run_id,
        execution_nonce=original.execution_nonce,
        independent_unit_id=original.independent_unit_id,
        cell=original.cell,
        operator_id=original.operator_id,
        enabled=original.enabled,
        execution_outcome=original.execution_outcome,
        invocation_ids=original.invocation_ids,
        no_op_reason_code=attacked_reason,
        no_op_evidence_sha256=original.no_op_evidence_sha256,
        implementation_sha256=original.implementation_sha256,
        implementation_manifest_sha256=original.implementation_manifest_sha256,
        source_bundle_sha256=original.source_bundle_sha256,
        input_state_sha256=original.input_state_sha256,
        output_state_sha256=original.output_state_sha256,
        visible_input_sha256=original.visible_input_sha256,
        raw_semantic_trace_sha256=original.raw_semantic_trace_sha256,
        runtime_event_log_sha256=original.runtime_event_log_sha256,
    )
    attacked_sha = content_sha256(attacked_payload)
    attacked = original.model_copy(
        update={
            "no_op_reason_code": attacked_reason,
            "receipt_payload_sha256": attacked_sha,
            "attestation_claim": original.attestation_claim.model_copy(
                update={"signed_receipt_sha256": attacked_sha}
            ),
        }
    )
    with pytest.raises(AttestationError, match="signature does not match"):
        verify_authenticated_enabled_no_op(attacked, signer.verifier())
