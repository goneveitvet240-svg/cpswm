from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from cpswm.foundation.persistence_replay import AppendOnlyTransactionLog
from cpswm.system.evaluation_operations.fair_ablation import ProjectOneAblationArmId
from cpswm.system.evaluation_operations.online_shift_attribution import OnlineShiftSplit
from cpswm.system.evaluation_operations.project_one_shift_authority import (
    ShiftExperimentAuthority,
)
from cpswm.system.evaluation_operations.project_one_shift_gates import (
    ATG3_ALLOWED_CLAIM_IDS,
    ATG3_FORBIDDEN_CLAIM_IDS,
    SHIFT_THREE_ARMS,
    ProjectOneShiftGateConfig,
    ProjectOneShiftGateReport,
    ShiftATG2Report,
    ShiftATG3Report,
    generate_frozen_shift_suite,
)
from cpswm.system.evaluation_operations.sealed_test_split import (
    SealedSplitAccessError,
    SealedTestSplit,
)
from cpswm.system.reproducibility import content_sha256

REPO = Path(__file__).resolve().parents[1]
CLI = REPO / "apps/evaluation_runner/run_project_one_shift_gates.py"
CONFIG = REPO / "benchmarks/project_one_ablation/project_one_shift_gates_v2.json"
KEY = b"independent-evaluator-key-material-32-bytes-minimum"


@pytest.fixture(scope="module")
def completed_gates(tmp_path_factory):
    directory = tmp_path_factory.mktemp("shift-authority")
    key_path = directory / "authority.key"
    key_path.write_bytes(KEY)
    key_path.chmod(0o600)
    event_log = directory / "events.json"
    output = directory / "report.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(CLI),
            "--authority-key-file",
            str(key_path),
            "--event-log",
            str(event_log),
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
    config = ProjectOneShiftGateConfig.model_validate_json(CONFIG.read_text(encoding="utf-8"))
    suite = generate_frozen_shift_suite(config.suite)
    validation = tuple(
        case for case in suite.cases if case.evaluator_truth.split == OnlineShiftSplit.VALIDATION
    )
    test = tuple(
        case for case in suite.cases if case.evaluator_truth.split == OnlineShiftSplit.TEST
    )
    return directory, event_log, report, config, validation, test


def test_validation_test_seeds_are_disjoint_and_power_analysis_is_frozen(completed_gates):
    _directory, _event_log, report, config, validation, test = completed_gates
    validation_seeds = {item.evaluator_truth.scenario_seed for item in validation}
    test_seeds = {item.evaluator_truth.scenario_seed for item in test}
    assert validation_seeds == set(config.suite.validation_seeds)
    assert test_seeds == set(config.suite.test_seeds)
    assert validation_seeds.isdisjoint(test_seeds)
    assert len(validation_seeds) == len(test_seeds) == 3
    assert report.atg3.power_analysis == config.power_analysis
    assert config.power_analysis.status == "PASS"
    tampered = config.power_analysis.model_dump(mode="json")
    tampered["required_independent_test_seeds"] = 1
    tampered["analysis_sha256"] = content_sha256(
        {key: value for key, value in tampered.items() if key != "analysis_sha256"}
    )
    with pytest.raises(ValidationError, match="required seed count"):
        type(config.power_analysis).model_validate(tampered)


def test_tuning_is_a_validation_only_child_process_with_independent_ledgers(
    completed_gates,
):
    _directory, _event_log, report, _config, _validation, _test = completed_gates
    cli_source = CLI.read_text(encoding="utf-8")
    assert "subprocess.run" in cli_source
    assert "--tuning-worker" in cli_source
    worker_argv = cli_source.split("completed = subprocess.run", maxsplit=1)[1].split(
        "check=False", maxsplit=1
    )[0]
    assert "authority-key-file" not in worker_argv
    assert "event-log" not in worker_argv
    assert "worker-validation" in worker_argv
    assert report.atg2.test_split_accessed is False
    assert tuple(item.arm_id for item in report.atg2.ledgers) == SHIFT_THREE_ARMS
    assert len({item.tuning_run_id for item in report.atg2.ledgers}) == 3
    assert all(len(item.trials) == 18 for item in report.atg2.ledgers)
    assert all(item.total_validation_predictions == 324 for item in report.atg2.ledgers)


def test_resource_fields_have_truthful_hyperparameter_names(completed_gates):
    _directory, _event_log, report, _config, _validation, _test = completed_gates
    payload = report.atg2.model_dump(mode="json")
    serialized = json.dumps(payload)
    assert "persistent_bytes" not in serialized
    assert "parameter_count" not in serialized
    assert "peak_memory_bytes" not in serialized
    assert "hyperparameter_json_bytes" in serialized
    assert "hyperparameter_field_count" in serialized
    assert "peak_tracemalloc_bytes" in serialized


def test_hmac_receipt_and_m03_registration_are_independently_verified(completed_gates):
    _directory, event_log, report, config, _validation, _test = completed_gates
    authority = ShiftExperimentAuthority(
        key=KEY,
        key_id=config.authority_key_id,
        log_path=event_log,
    )
    assert authority.verify_atg2_report(report.atg2)
    assert authority.verify_complete_report(report)
    receipt = report.atg2.receipt
    assert receipt.authority_hmac_sha256
    assert receipt.registration_transaction_id
    assert receipt.registration_global_commit_seq == 1

    wrong_authority = ShiftExperimentAuthority(
        key=b"wrong-independent-authority-key-material-000000",
        key_id=config.authority_key_id,
        log_path=event_log,
    )
    assert not wrong_authority.verify_atg2_report(report.atg2)
    assert not wrong_authority.verify_complete_report(report)


def test_completion_proof_tamper_fails_independent_authority(completed_gates):
    _directory, event_log, report, config, _validation, _test = completed_gates
    forged_proof = report.atg3_completion_commit.model_copy(update={"log_head_sha256": "f" * 64})
    forged = report.model_copy(update={"atg3_completion_commit": forged_proof})
    authority = ShiftExperimentAuthority(
        key=KEY,
        key_id=config.authority_key_id,
        log_path=event_log,
    )
    assert not authority.verify_complete_report(forged)


def test_self_consistent_receipt_tamper_still_fails_authority(completed_gates):
    _directory, event_log, report, config, _validation, _test = completed_gates
    tampered_receipt = report.atg2.receipt.model_copy(update={"authority_hmac_sha256": "0" * 64})
    tampered = report.atg2.model_copy(update={"receipt": tampered_receipt})
    authority = ShiftExperimentAuthority(
        key=KEY,
        key_id=config.authority_key_id,
        log_path=event_log,
    )
    assert not authority.verify_atg2_report(tampered)


def _fresh_authorized_atg2(completed_gates, name: str):
    directory, _event_log, report, config, _validation, _test = completed_gates
    authority = ShiftExperimentAuthority(
        key=KEY,
        key_id=config.authority_key_id,
        log_path=directory / f"{name}.events.json",
    )
    draft = ShiftExperimentAuthority._draft_from_report(report.atg2)
    return authority, authority.commit_atg2(draft)


def test_sealed_test_requires_complete_atg2_report_and_authority(completed_gates):
    _directory, _event_log, report, _config, validation, test = completed_gates
    sealed = SealedTestSplit(
        test,
        experiment_id=report.atg1_topology_report.manifest.experiment_id,
        test_split_sha256=content_sha256(test),
        required_validation_split_sha256=content_sha256(validation),
        required_receipt_scope="project-one-shift-atg3",
    )
    with pytest.raises(SealedSplitAccessError, match="authority"):
        sealed.unseal(report.atg2)
    fake_authority = type(
        "FakeAuthority",
        (),
        {"authorize_test_unseal": lambda self, report, **kwargs: None},
    )()
    with pytest.raises(SealedSplitAccessError, match="complete ATG-2"):
        sealed.unseal(report.atg2.receipt, authority=fake_authority)
    assert sealed.is_sealed


def test_fresh_authority_can_unlock_once_then_persist_state(completed_gates):
    _directory, _event_log, report, config, validation, test = completed_gates
    authority, atg2 = _fresh_authorized_atg2(completed_gates, "fresh-unseal")
    sealed = SealedTestSplit(
        test,
        experiment_id=report.atg1_topology_report.manifest.experiment_id,
        test_split_sha256=content_sha256(test),
        required_validation_split_sha256=content_sha256(validation),
        required_receipt_scope="project-one-shift-atg3",
    )
    released = sealed.unseal(atg2, authority=authority)
    assert released == test
    assert sealed.unseal_authority_proof.event_type == "TEST_UNSEALED"
    with pytest.raises(SealedSplitAccessError, match="already"):
        sealed.unseal(atg2, authority=authority)
    assert config.power_analysis.status == "PASS"


def test_persistent_state_log_has_exact_cross_process_order(completed_gates):
    _directory, event_log, report, _config, _validation, _test = completed_gates
    log = AppendOnlyTransactionLog.load(event_log)
    transactions = log.read()
    assert [item.global_commit_seq for item in transactions] == [1, 2, 3]
    assert [item.records[0].envelope.payload["event_type"] for item in transactions] == [
        "ATG2_COMPLETED",
        "TEST_UNSEALED",
        "ATG3_COMPLETED",
    ]
    assert report.atg2.receipt.registration_transaction_id == transactions[0].transaction_id
    assert report.atg3.test_unseal_commit.transaction_id == transactions[1].transaction_id
    assert report.atg3_completion_commit.transaction_id == transactions[2].transaction_id


def test_prediction_artifacts_recompute_metrics_and_intervals(completed_gates):
    _directory, _event_log, report, _config, _validation, _test = completed_gates
    atg3 = ShiftATG3Report.model_validate(report.atg3.model_dump(mode="json"))
    assert len(atg3.test_truth_artifact.truths) == 18
    assert all(
        len(atg3.prediction_artifacts_by_arm[arm].predictions) == 18 for arm in SHIFT_THREE_ARMS
    )
    assert len(atg3.paired_intervals) == 20


@pytest.mark.parametrize("claim_field", ["allowed_claims", "forbidden_claims"])
def test_claim_ids_are_exact_canonical_sets(completed_gates, claim_field):
    _directory, _event_log, report, _config, _validation, _test = completed_gates
    assert report.atg3.allowed_claims == ATG3_ALLOWED_CLAIM_IDS
    assert report.atg3.forbidden_claims == ATG3_FORBIDDEN_CLAIM_IDS
    payload = deepcopy(report.atg3.model_dump(mode="json"))
    payload[claim_field].append("forged.claim@9")
    with pytest.raises(ValidationError, match="claim IDs"):
        ShiftATG3Report.model_validate(payload)


def test_prediction_tamper_rejected_even_if_outer_artifact_hash_is_recomputed(
    completed_gates,
):
    _directory, _event_log, report, _config, _validation, _test = completed_gates
    payload = deepcopy(report.atg3.model_dump(mode="json"))
    arm = ProjectOneAblationArmId.ORDINARY_BOCPD.value
    artifact = payload["prediction_artifacts_by_arm"][arm]
    prediction = artifact["predictions"][0]
    first_cause = next(iter(prediction["cause_probabilities"]))
    prediction["cause_probabilities"][first_cause] = 0.0
    artifact["artifact_sha256"] = content_sha256(
        {key: value for key, value in artifact.items() if key != "artifact_sha256"}
    )
    with pytest.raises(ValidationError, match="aggregate metrics"):
        ShiftATG3Report.model_validate(payload)


def test_atg2_ledger_tamper_cannot_be_reauthorized(completed_gates):
    _directory, event_log, report, config, _validation, _test = completed_gates
    payload = deepcopy(report.atg2.model_dump(mode="json"))
    payload["ledgers"][0]["trials"][0]["elapsed_ns"] += 1
    with pytest.raises(ValidationError):
        ShiftATG2Report.model_validate(payload)
    authority = ShiftExperimentAuthority(
        key=KEY,
        key_id=config.authority_key_id,
        log_path=event_log,
    )
    assert not authority.verify_atg2_report(payload)
