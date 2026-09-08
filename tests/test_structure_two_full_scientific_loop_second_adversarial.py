from __future__ import annotations

import copy
import json
from pathlib import Path
from uuid import UUID

import pytest

from cpswm.system.evaluation_operations.structure_two_full_scientific_loop import (
    DEFAULT_CONFIG,
    _deterministic_payload,
    load_full_scientific_loop_config,
    verify_full_scientific_loop_result,
)
from cpswm.system.evaluation_operations.structure_two_selected_method import (
    StructureTwoOperator,
)
from cpswm.system.reproducibility import content_sha256

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "benchmarks/structure_two/structure_two_full_scientific_loop_v0_2.json"


@pytest.fixture(scope="module")
def artifact() -> dict[str, object]:
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))


def _resign(payload: dict[str, object]) -> None:
    payload.pop("content_sha256", None)
    payload.pop("deterministic_replay_sha256", None)
    payload["deterministic_replay_sha256"] = content_sha256(_deterministic_payload(payload))
    payload["content_sha256"] = content_sha256(payload)


def _rehash_operator_receipts(run: dict[str, object]) -> None:
    previous = "GENESIS"
    receipts = run["operator_flow_receipts"]
    assert isinstance(receipts, list)
    for receipt in receipts:
        assert isinstance(receipt, dict)
        receipt["previous_receipt_sha256"] = previous
        receipt["receipt_sha256"] = content_sha256(
            {
                "step_index": receipt["step_index"],
                "operator": receipt["operator"],
                "executed": receipt["executed"],
                "changed_state": receipt["changed_state"],
                "input_state_sha256": receipt["input_state_sha256"],
                "output_state_sha256": receipt["output_state_sha256"],
                "consumed_axes": receipt["consumed_axes"],
                "detail": receipt["detail"],
                "previous_receipt_sha256": receipt["previous_receipt_sha256"],
            }
        )
        previous = str(receipt["receipt_sha256"])
    run["operator_receipt_head_sha256"] = previous


def _rehash_ledger(records: list[dict[str, object]]) -> str:
    previous = "GENESIS"
    for record in records:
        record["previous_hash"] = previous
        distribution = record["action_distribution"]
        assert isinstance(distribution, dict)
        record["record_hash"] = content_sha256(
            {
                "operation": record["operation"],
                "source_revision_id": record["source_revision_id"],
                "particle_revision_id": record["particle_revision_id"],
                "owner_target_mass": record["owner_target_mass"],
                "action_distribution": sorted(distribution.items()),
                "previous_hash": record["previous_hash"],
            }
        )
        previous = str(record["record_hash"])
    return previous


def test_new_round_one_rejects_truth_leaking_training_policy(tmp_path: Path) -> None:
    payload = json.loads((ROOT / DEFAULT_CONFIG).read_text(encoding="utf-8"))
    payload["interaction_training"]["training_action_policy"] = "oracle_owner_habit"
    config_path = tmp_path / "truth-leaking-policy.json"
    config_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="uses truth or drifted"):
        load_full_scientific_loop_config(ROOT, config_path)


def test_new_round_one_rejects_boolean_integer_coercion(tmp_path: Path) -> None:
    payload = json.loads((ROOT / DEFAULT_CONFIG).read_text(encoding="utf-8"))
    payload["action_responsive_environment"]["horizon"] = True
    config_path = tmp_path / "boolean-horizon.json"
    config_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="JSON integer, not a coercible value"):
        load_full_scientific_loop_config(ROOT, config_path)


def test_new_round_one_training_and_validation_examples_are_distinct(
    artifact: dict[str, object],
) -> None:
    evidence = artifact["learned_cross_axis_interaction"]["training_evidence"]  # type: ignore[index]
    assert evidence["train_validation_examples_distinct"] is True
    assert evidence["train_examples_sha256"] != evidence["validation_examples_sha256"]


def test_new_round_one_rehashed_corrected_state_chain_forgery_is_rejected(
    artifact: dict[str, object],
) -> None:
    forged = copy.deepcopy(artifact)
    run = forged["closed_loop_runs"]["stateful_full_joint"][0]  # type: ignore[index]
    run["traces"][1]["pre_observation_state_sha256"] = "0" * 64
    run["environment_trace_sha256"] = content_sha256(run["traces"])
    _resign(forged)

    with pytest.raises(ValueError, match="corrected-state consumption"):
        verify_full_scientific_loop_result(forged, repository_root=ROOT)


def test_new_round_one_rehashed_neutralization_semantic_forgery_is_rejected(
    artifact: dict[str, object],
) -> None:
    forged = copy.deepcopy(artifact)
    run = forged["seven_operator_neutralization"]["runs"][  # type: ignore[index]
        StructureTwoOperator.RGRC.value
    ][0]
    receipt = next(
        row
        for row in run["operator_flow_receipts"]
        if row["operator"] == StructureTwoOperator.RGRC.value and row["executed"] is True
    )
    receipt["detail"] = "RGRC happened to leave state unchanged"
    _rehash_operator_receipts(run)
    _resign(forged)

    with pytest.raises(ValueError, match="registered neutralization semantics failed"):
        verify_full_scientific_loop_result(forged, repository_root=ROOT)


def test_new_round_one_rehashed_negative_ledger_evidence_removal_is_rejected(
    artifact: dict[str, object],
) -> None:
    forged = copy.deepcopy(artifact)
    evidence = forged["rgrc_activation_suite"]["negative_case_evidence"][  # type: ignore[index]
        "unstable_owner_rejected"
    ]
    evidence["ledger_records"] = []
    evidence["record_count"] = 0
    evidence["operations"] = []
    evidence["ledger_head_sha256"] = "GENESIS"
    _resign(forged)

    with pytest.raises(ValueError, match="negative activation claim is false"):
        verify_full_scientific_loop_result(forged, repository_root=ROOT)


def test_new_round_two_rejects_nonfinite_numbers_before_hash_trust(
    artifact: dict[str, object],
) -> None:
    forged = copy.deepcopy(artifact)
    forged["learned_cross_axis_interaction"]["validation_loss"] = float("nan")  # type: ignore[index]

    with pytest.raises(ValueError, match="non-finite numeric value"):
        verify_full_scientific_loop_result(forged, repository_root=ROOT)


def test_new_round_two_rehashed_boolean_step_index_is_rejected(
    artifact: dict[str, object],
) -> None:
    forged = copy.deepcopy(artifact)
    run = forged["closed_loop_runs"]["stateful_full_joint"][0]  # type: ignore[index]
    run["traces"][0]["step_index"] = False
    run["environment_trace_sha256"] = content_sha256(run["traces"])
    _resign(forged)

    with pytest.raises(ValueError, match="trace index or state hash is malformed"):
        verify_full_scientific_loop_result(forged, repository_root=ROOT)


def test_new_round_two_rehashed_boolean_fairness_integer_is_rejected(
    artifact: dict[str, object],
) -> None:
    forged = copy.deepcopy(artifact)
    run = forged["closed_loop_runs"]["stateful_full_joint"][0]  # type: ignore[index]
    run["fairness_receipts"][0]["step_index"] = True
    _resign(forged)

    with pytest.raises(ValueError, match="fairness receipt is invalid"):
        verify_full_scientific_loop_result(forged, repository_root=ROOT)


def test_new_round_two_rehashed_rgrc_location_support_substitution_is_rejected(
    artifact: dict[str, object],
) -> None:
    forged = copy.deepcopy(artifact)
    suite = forged["rgrc_activation_suite"]  # type: ignore[index]
    records = suite["positive_ledger_records"]
    distribution = records[0]["action_distribution"]
    original_location = next(iter(distribution))
    distribution[str(UUID("00000000-0000-4000-8000-000000000001"))] = distribution.pop(
        original_location
    )
    suite["ledger_head_sha256"] = _rehash_ledger(records)
    _resign(forged)

    with pytest.raises(ValueError, match="distribution support was substituted"):
        verify_full_scientific_loop_result(forged, repository_root=ROOT)


def test_new_round_two_rehashed_degenerate_split_evidence_is_rejected(
    artifact: dict[str, object],
) -> None:
    forged = copy.deepcopy(artifact)
    evidence = forged["learned_cross_axis_interaction"]["training_evidence"]  # type: ignore[index]
    evidence["validation_examples_sha256"] = evidence["train_examples_sha256"]
    _resign(forged)

    with pytest.raises(ValueError, match="train/validation examples are degenerate copies"):
        verify_full_scientific_loop_result(forged, repository_root=ROOT)


def test_new_round_two_rehashed_distinct_training_hash_substitution_is_rejected(
    artifact: dict[str, object],
) -> None:
    forged = copy.deepcopy(artifact)
    evidence = forged["learned_cross_axis_interaction"]["training_evidence"]  # type: ignore[index]
    evidence["train_examples_sha256"] = "1" * 64
    evidence["validation_examples_sha256"] = "2" * 64
    _resign(forged)

    with pytest.raises(ValueError, match="example evidence is not source-regenerated"):
        verify_full_scientific_loop_result(forged, repository_root=ROOT)


def test_new_round_two_training_evidence_extra_claim_is_rejected(
    artifact: dict[str, object],
) -> None:
    forged = copy.deepcopy(artifact)
    evidence = forged["learned_cross_axis_interaction"]["training_evidence"]  # type: ignore[index]
    evidence["unregistered_training_claim"] = True
    _resign(forged)

    with pytest.raises(ValueError, match="training evidence is incomplete"):
        verify_full_scientific_loop_result(forged, repository_root=ROOT)


def test_new_round_two_rehashed_production_source_substitution_is_rejected(
    artifact: dict[str, object],
) -> None:
    forged = copy.deepcopy(artifact)
    assembly = forged["production_system_assembly"]  # type: ignore[index]
    assembly["operators"][0]["sources"][0]["sha256"] = "0" * 64
    assembly.pop("content_sha256")
    assembly["content_sha256"] = content_sha256(assembly)
    _resign(forged)

    with pytest.raises(ValueError, match="production assembly manifest mismatch"):
        verify_full_scientific_loop_result(forged, repository_root=ROOT)


def test_new_round_two_rehashed_runner_substitution_is_rejected(
    artifact: dict[str, object],
) -> None:
    forged = copy.deepcopy(artifact)
    forged["source_binding"]["runner"]["sha256"] = "0" * 64  # type: ignore[index]
    _resign(forged)

    with pytest.raises(ValueError, match="source binding mismatch: runner"):
        verify_full_scientific_loop_result(forged, repository_root=ROOT)


def test_new_round_two_rejects_an_incomplete_positive_output_trust_map(
    artifact: dict[str, object],
) -> None:
    forged = copy.deepcopy(artifact)
    trust = forged["positive_output_trust_chain"]
    assert isinstance(trust, dict)
    removed_path = next(path for path in trust if path.startswith("/closed_loop_runs/"))
    trust.pop(removed_path)
    _resign(forged)

    with pytest.raises(ValueError, match="positive-output trust map is incomplete"):
        verify_full_scientific_loop_result(forged, repository_root=ROOT)
