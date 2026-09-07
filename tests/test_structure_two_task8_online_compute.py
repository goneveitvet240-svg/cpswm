from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

from cpswm.system.evaluation_operations.structure_two_task8_online_compute import (
    ARM_ORDER,
    content_sha256,
    run_task8_online_compute_study,
    verify_result,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs/project_two_experiments/structure_two_task8_online_compute_v0_1.json"
ARTIFACT_PATH = ROOT / "benchmarks/structure_two/structure_two_task8_online_compute_v0_1.json"
RUNNER_PATH = ROOT / "apps/evaluation_runner/run_structure_two_task8_online_compute.py"


def _runner() -> ModuleType:
    spec = importlib.util.spec_from_file_location("run_task8_online_compute", RUNNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def config() -> dict[str, object]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def artifact() -> dict[str, object]:
    return json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))


def _rehash_artifact(payload: dict[str, object]) -> None:
    unsigned = dict(payload)
    unsigned.pop("content_sha256", None)
    payload["content_sha256"] = content_sha256(unsigned)


def test_frozen_result_is_equal_compute_negative_development_signal(
    config: dict[str, object], artifact: dict[str, object]
) -> None:
    result = artifact["result"]
    assert isinstance(result, dict)
    verify_result(result, config)
    assert result["fairness_gate_passed"] is True
    assert result["any_strict_development_signal"] is False
    assert result["task_8_formal_passed"] is False
    assert result["seven_operator_ablation_authorized"] is False
    assert result["next_disposition"] == (
        "DEFAULT_METHOD_REDESIGN_BEFORE_EXPENSIVE_EXTERNAL_SCALEUP"
    )
    for receipt in result["budget_fairness_receipts"]:
        assert set(receipt["active_parameter_count_by_arm"]) == set(ARM_ORDER)
        assert len(set(receipt["active_parameter_count_by_arm"].values())) == 1
        assert len(set(receipt["training_multiply_adds_by_arm"].values())) == 1
        assert len(set(receipt["inference_multiply_adds_per_unit_by_arm"].values())) == 1


def test_seed_reuse_is_rejected() -> None:
    with pytest.raises(ValueError, match="disjoint"):
        run_task8_online_compute_study(
            gaps=1,
            training_seeds=(1, 2),
            validation_seeds=(2, 3),
            confirmatory_seeds=(4, 5),
            base_widths=(8,),
            learning_rates=(0.1,),
            l2_values=(0.0,),
            minimum_relative_improvement=0.1,
        )


def test_forged_complete_positive_frontier_is_rejected(
    config: dict[str, object], artifact: dict[str, object]
) -> None:
    forged = copy.deepcopy(artifact["result"])
    assert isinstance(forged, dict)
    for row in forged["primary_online_compute_frontier"]:
        row["strict_development_signal"] = True
        row["joint_pareto_better_at_equal_compute"] = True
    forged["any_strict_development_signal"] = True
    forged["next_disposition"] = (
        "PROCEED_TO_FULL_SYSTEM_GUARDRAIL_INTEGRATION_BEFORE_EXTERNAL_SCALEUP"
    )
    with pytest.raises(ValueError, match=r"Pareto verdict|strict signal"):
        verify_result(forged, config)


def test_rehashed_nonwinning_validation_selection_is_rejected(
    config: dict[str, object], artifact: dict[str, object]
) -> None:
    forged = copy.deepcopy(artifact["result"])
    assert isinstance(forged, dict)
    receipt = forged["selection_receipt"]
    key = "width=8|arm=learned_joint"
    winner = receipt["selections"][key]
    replacement = next(
        row
        for row in forged["validation_candidate_rows"]
        if row["arm"] == winner["arm"]
        and row["base_width"] == winner["base_width"]
        and row != winner
    )
    receipt["selections"][key] = replacement
    unsigned = dict(receipt)
    unsigned.pop("content_sha256")
    receipt["content_sha256"] = content_sha256(unsigned)
    with pytest.raises(ValueError, match="validation winner"):
        verify_result(forged, config)


def test_rehashed_budget_map_forgery_is_rejected(
    config: dict[str, object], artifact: dict[str, object]
) -> None:
    forged = copy.deepcopy(artifact["result"])
    assert isinstance(forged, dict)
    forged["budget_fairness_receipts"][0]["active_parameter_count_by_arm"]["learned_joint"] += 1
    with pytest.raises(ValueError, match="parameter counts"):
        verify_result(forged, config)


def test_missing_confirmatory_positive_path_is_rejected(
    config: dict[str, object], artifact: dict[str, object]
) -> None:
    forged = copy.deepcopy(artifact["result"])
    assert isinstance(forged, dict)
    forged["confirmatory_rows"].pop()
    with pytest.raises(ValueError, match="coverage"):
        verify_result(forged, config)


def test_rehashed_action_cost_forgery_is_rejected(
    config: dict[str, object], artifact: dict[str, object]
) -> None:
    forged = copy.deepcopy(artifact["result"])
    assert isinstance(forged, dict)
    forged["confirmatory_rows"][0]["consequential_expected_cost"] += 0.01
    with pytest.raises(ValueError, match="expected cost"):
        verify_result(forged, config)


def test_formal_promotion_fails_even_when_all_artifact_hashes_are_rebuilt(
    artifact: dict[str, object],
) -> None:
    runner = _runner()
    forged = copy.deepcopy(artifact)
    result = forged["result"]
    assert isinstance(result, dict)
    result["task_8_formal_passed"] = True
    forged["result_content_sha256"] = content_sha256(result)
    _rehash_artifact(forged)
    with pytest.raises(ValueError, match="cannot assert task_8_formal_passed"):
        runner.verify_artifact(forged, fresh_replay=False)


def test_source_bundle_substitution_fails_after_outer_rehash(artifact: dict[str, object]) -> None:
    runner = _runner()
    forged = copy.deepcopy(artifact)
    forged["source_files"][0]["sha256"] = "0" * 64
    forged["source_bundle_sha256"] = content_sha256(forged["source_files"])
    _rehash_artifact(forged)
    with pytest.raises(ValueError, match="source bundle drift"):
        runner.verify_artifact(forged, fresh_replay=False)


def test_artifact_verifies_with_fresh_source_replay(artifact: dict[str, object]) -> None:
    _runner().verify_artifact(artifact, fresh_replay=True)
