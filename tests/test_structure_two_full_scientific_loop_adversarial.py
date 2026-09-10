from __future__ import annotations

import copy
import json
from pathlib import Path

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
from cpswm.system.evaluation_operations.structure_two_stateful_full_joint import (
    FullJointArm,
)
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_production_system import build_production_assembly_manifest

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


def _bind_current_production_manifest(payload: dict[str, object]) -> None:
    """Reach semantic checks without rewriting or promoting the historical artifact."""

    payload["production_system_assembly"] = build_production_assembly_manifest(ROOT)


def test_round_one_config_rejects_evaluation_seed_leakage(tmp_path: Path) -> None:
    payload = json.loads((ROOT / DEFAULT_CONFIG).read_text(encoding="utf-8"))
    payload["interaction_training"]["train_seeds"].append(
        payload["action_responsive_environment"]["evaluation_seeds"][0]
    )
    config_path = tmp_path / "leaky.json"
    config_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="must be non-empty and disjoint"):
        load_full_scientific_loop_config(ROOT, config_path)


def test_round_one_config_rejects_operator_scope_narrowing(tmp_path: Path) -> None:
    payload = json.loads((ROOT / DEFAULT_CONFIG).read_text(encoding="utf-8"))
    payload["retained_operators"].remove(StructureTwoOperator.RGRC.value)
    config_path = tmp_path / "narrowed.json"
    config_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="retain all seven operators"):
        load_full_scientific_loop_config(ROOT, config_path)


def test_round_one_rehashed_missing_neutralization_is_rejected(
    artifact: dict[str, object],
) -> None:
    forged = copy.deepcopy(artifact)
    del forged["seven_operator_neutralization"]["runs"][  # type: ignore[index]
        StructureTwoOperator.CIAV.value
    ]
    _bind_current_production_manifest(forged)
    _resign(forged)

    with pytest.raises(ValueError, match="neutralization matrix is incomplete"):
        verify_full_scientific_loop_result(forged, repository_root=ROOT)


def test_round_one_rehashed_rgrc_ledger_forgery_is_rejected(
    artifact: dict[str, object],
) -> None:
    forged = copy.deepcopy(artifact)
    forged["rgrc_activation_suite"]["positive_ledger_records"][0][  # type: ignore[index]
        "owner_target_mass"
    ] = 1.0
    _bind_current_production_manifest(forged)
    _resign(forged)

    with pytest.raises(ValueError, match="RGRC record hash mismatch"):
        verify_full_scientific_loop_result(forged, repository_root=ROOT)


def test_round_two_rehashed_metric_claim_is_rejected(
    artifact: dict[str, object],
) -> None:
    forged = copy.deepcopy(artifact)
    forged["closed_loop_runs"][FullJointArm.STATEFUL_FULL_JOINT.value][0][  # type: ignore[index]
        "unknown_calibration_brier"
    ] = 0.0
    _bind_current_production_manifest(forged)
    _resign(forged)

    with pytest.raises(ValueError, match="aggregate metric is not trace-derived"):
        verify_full_scientific_loop_result(forged, repository_root=ROOT)


def test_round_two_rehashed_positive_claim_is_rejected(
    artifact: dict[str, object],
) -> None:
    forged = copy.deepcopy(artifact)
    forged["scientific_superiority_established"] = True
    _bind_current_production_manifest(forged)
    _resign(forged)

    with pytest.raises(ValueError, match="promoted a paper-level or external claim"):
        verify_full_scientific_loop_result(forged, repository_root=ROOT)


def test_round_two_fresh_replay_detects_self_consistent_receipt_substitution(
    artifact: dict[str, object],
) -> None:
    clean_rebound = copy.deepcopy(artifact)
    _bind_current_production_manifest(clean_rebound)
    _resign(clean_rebound)
    verify_full_scientific_loop_result(
        clean_rebound,
        repository_root=ROOT,
        fresh_replay=True,
    )

    forged = copy.deepcopy(clean_rebound)
    forged["closed_loop_runs"][FullJointArm.STATEFUL_FULL_JOINT.value][0][  # type: ignore[index]
        "fairness_receipts"
    ][0]["common_random_number_sha256"] = "0" * 64
    _resign(forged)

    # A caller-held, self-consistent receipt field is not independent custody.
    verify_full_scientific_loop_result(forged, repository_root=ROOT, fresh_replay=False)
    with pytest.raises(ValueError, match="fresh-source replay disagrees"):
        verify_full_scientific_loop_result(forged, repository_root=ROOT, fresh_replay=True)
