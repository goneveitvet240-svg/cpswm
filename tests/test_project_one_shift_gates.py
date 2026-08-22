from __future__ import annotations

import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from cpswm.system.evaluation_operations.fair_ablation import ProjectOneAblationArmId
from cpswm.system.evaluation_operations.online_shift_attribution import (
    OnlineShiftSplit,
    OnlineShiftSuiteGenerator,
)
from cpswm.system.evaluation_operations.project_one_ablation_v0_2 import (
    ProjectOneProtocolPilotReportV2,
)
from cpswm.system.evaluation_operations.project_one_shift_gates import (
    SHIFT_THREE_ARMS,
    ProjectOneShiftGateReport,
    ProjectOneShiftGateRunner,
    ShiftATG2Report,
    ShiftATG3Report,
)
from cpswm.system.evaluation_operations.sealed_test_split import (
    SealedSplitAccessError,
    SealedTestSplit,
    TuningCompletionReceipt,
)
from cpswm.system.reproducibility import content_sha256

REPO = Path(__file__).resolve().parents[1]
TOPOLOGY_FIXTURE = (
    REPO / "benchmarks/project_one_ablation/project_one_protocol_pilot_report_v0.2.fixture.json"
)


@pytest.fixture(scope="module")
def completed_gates():
    topology = ProjectOneProtocolPilotReportV2.model_validate_json(
        TOPOLOGY_FIXTURE.read_text(encoding="utf-8")
    )
    suite = OnlineShiftSuiteGenerator().generate()
    validation = tuple(
        case for case in suite.cases if case.evaluator_truth.split == OnlineShiftSplit.VALIDATION
    )
    test = tuple(
        case for case in suite.cases if case.evaluator_truth.split == OnlineShiftSplit.TEST
    )
    sealed = SealedTestSplit(
        test,
        experiment_id=topology.manifest.experiment_id,
        test_split_sha256=content_sha256(test),
        required_validation_split_sha256=content_sha256(validation),
        required_receipt_scope="project-one-shift-atg3",
    )
    runner = ProjectOneShiftGateRunner()
    atg2 = runner.run_atg2(
        topology,
        validation,
        code_snapshot_sha256="a" * 64,
    )
    assert sealed.is_sealed
    atg3 = runner.run_atg3(
        topology,
        atg2,
        sealed,
        expected_code_snapshot_sha256="a" * 64,
        bootstrap_samples=100,
    )
    payload = {
        "atg1_topology_report": topology,
        "atg2": atg2,
        "atg3": atg3,
    }
    combined = ProjectOneShiftGateReport(
        **payload,
        report_sha256=content_sha256({"protocol_version": "project-one-shift-gates@1", **payload}),
    )
    return topology, validation, test, runner, atg2, atg3, combined


def test_atg2_has_independent_complete_measured_ledgers(completed_gates):
    topology, _validation, _test, _runner, atg2, _atg3, _combined = completed_gates
    assert tuple(ledger.arm_id for ledger in atg2.ledgers) == SHIFT_THREE_ARMS
    assert len({ledger.tuning_run_id for ledger in atg2.ledgers}) == 3
    assert all(len(ledger.trials) == 18 for ledger in atg2.ledgers)
    assert all(ledger.within_budget for ledger in atg2.ledgers)
    assert atg2.test_split_accessed is False
    assert atg2.global_eleven_arm_tuning_status == "BLOCK"
    assert atg2.receipt.topology_manifest_sha256 == topology.manifest_sha256


def test_atg3_uses_frozen_three_arm_test_and_keeps_global_blocks(completed_gates):
    _topology, _validation, test, _runner, atg2, atg3, combined = completed_gates
    assert atg3.test_split_sha256 == content_sha256(test)
    assert atg3.test_case_count == len(test) == 12
    assert set(atg3.reports_by_arm) == set(SHIFT_THREE_ARMS)
    assert len(atg3.paired_intervals) == 20
    assert all(
        interval.resampling_unit == "scenario_seed_trajectory" for interval in atg3.paired_intervals
    )
    assert atg3.formal_structure_one_b1_status == "BLOCK"
    assert atg3.global_eleven_arm_experiment_status == "BLOCK"
    assert "general-method-superiority" in atg3.forbidden_claims
    assert combined.atg2.receipt.receipt_hash == combined.atg3.receipt.receipt_hash
    assert atg2.receipt.is_authentic()


def test_scope_protected_test_rejects_legacy_or_wrong_receipts(completed_gates):
    topology, validation, test, _runner, atg2, _atg3, _combined = completed_gates
    sealed = SealedTestSplit(
        test,
        experiment_id=topology.manifest.experiment_id,
        test_split_sha256=content_sha256(test),
        required_validation_split_sha256=content_sha256(validation),
        required_receipt_scope="project-one-shift-atg3",
    )
    weak = TuningCompletionReceipt.issue(
        experiment_id=topology.manifest.experiment_id,
        validation_split_sha256=content_sha256(validation),
        tuning_runs_completed=3,
    )
    with pytest.raises(SealedSplitAccessError, match="scope"):
        sealed.unseal(weak)

    wrong = atg2.receipt.model_copy(update={"test_split_sha256": "f" * 64})
    with pytest.raises(SealedSplitAccessError, match="authentic"):
        sealed.unseal(wrong)
    assert sealed.is_sealed


def test_runner_forbids_retuning_and_second_unseal(completed_gates):
    topology, validation, test, runner, atg2, _atg3, _combined = completed_gates
    with pytest.raises(RuntimeError, match="retuning"):
        runner.run_atg2(topology, validation, code_snapshot_sha256="a" * 64)

    sealed = SealedTestSplit(
        test,
        experiment_id=topology.manifest.experiment_id,
        test_split_sha256=content_sha256(test),
        required_validation_split_sha256=content_sha256(validation),
        required_receipt_scope="project-one-shift-atg3",
    )
    with pytest.raises(RuntimeError, match="only once"):
        runner.run_atg3(
            topology,
            atg2,
            sealed,
            expected_code_snapshot_sha256="a" * 64,
            bootstrap_samples=100,
        )


def test_atg3_rejects_code_snapshot_drift_before_unseal(completed_gates):
    topology, validation, test, _runner, atg2, _atg3, _combined = completed_gates
    sealed = SealedTestSplit(
        test,
        experiment_id=topology.manifest.experiment_id,
        test_split_sha256=content_sha256(test),
        required_validation_split_sha256=content_sha256(validation),
        required_receipt_scope="project-one-shift-atg3",
    )
    with pytest.raises(ValueError, match="code snapshot"):
        ProjectOneShiftGateRunner().run_atg3(
            topology,
            atg2,
            sealed,
            expected_code_snapshot_sha256="f" * 64,
            bootstrap_samples=100,
        )
    assert sealed.is_sealed


@pytest.mark.parametrize(
    ("target", "mutate"),
    [
        (
            ShiftATG2Report,
            lambda data: data["ledgers"][0]["trials"][0]["params"].update({"warmup_days": 99}),
        ),
        (
            ShiftATG2Report,
            lambda data: data["receipt"]["arm_bindings"][0].update({"trial_count": 17}),
        ),
        (
            ShiftATG3Report,
            lambda data: data["selected_params_sha256_by_arm"].update(
                {ProjectOneAblationArmId.ORDINARY_BOCPD.value: "f" * 64}
            ),
        ),
        (
            ShiftATG3Report,
            lambda data: data.update({"test_case_count": 11}),
        ),
    ],
)
def test_gate_contracts_reject_nested_tampering(completed_gates, target, mutate):
    source = completed_gates[4] if target is ShiftATG2Report else completed_gates[5]
    data = deepcopy(source.model_dump(mode="json"))
    mutate(data)
    with pytest.raises(ValidationError):
        target.model_validate(data)


def test_combined_hash_rejects_outer_tampering(completed_gates):
    data = deepcopy(completed_gates[6].model_dump(mode="json"))
    data["atg3"]["forbidden_claims"].remove("general-method-superiority")
    with pytest.raises(ValidationError):
        ProjectOneShiftGateReport.model_validate(data)


def test_real_cli_reproduces_a_self_validating_gate_report(tmp_path):
    output = tmp_path / "shift-gates.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(REPO / "apps/evaluation_runner/run_project_one_shift_gates.py"),
            "--output",
            str(output),
        ],
        cwd=REPO,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    report = ProjectOneShiftGateReport.model_validate_json(output.read_text(encoding="utf-8"))
    assert report.atg2.gate_status == "PASS"
    assert report.atg3.gate_status == "PASS"
