from __future__ import annotations

import copy
import importlib.util
import json
from functools import lru_cache
from pathlib import Path

import pytest

from cpswm.system.evaluation_operations import structure_two_task8_matched_confirmatory as task8
from cpswm.system.evaluation_operations.structure_two_backbone_falsifier import (
    ArmName,
    CostMeter,
    _coupling_table,
    registered_scenarios,
)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "apps/evaluation_runner/run_structure_two_backbone_b_repairs.py"
SPEC = importlib.util.spec_from_file_location("run_structure_two_backbone_b_repairs", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


@lru_cache(maxsize=2)
def _registered_result(task: str) -> dict[str, object]:
    return MODULE.run_registered_task(task)


def _task7_result() -> dict[str, object]:
    return copy.deepcopy(_registered_result("7"))


def _task8_result() -> dict[str, object]:
    return copy.deepcopy(_registered_result("8"))


def _rehash(payload: dict[str, object]) -> None:
    result = payload["result"]
    assert isinstance(result, dict)
    recomputation = payload["recomputation"]
    assert isinstance(recomputation, dict)
    recomputation["deterministic_result_sha256"] = MODULE._canonical_sha256(
        MODULE.deterministic_projection(result)
    )
    unsigned = dict(payload)
    unsigned.pop("content_sha256", None)
    payload["content_sha256"] = MODULE._canonical_sha256(unsigned)


def test_task_specific_fresh_recomputation_accepts_an_unchanged_result() -> None:
    result = _task7_result()
    payload = MODULE.make_artifact("7", result)
    MODULE.verify_artifact(payload, task_runner=lambda task: copy.deepcopy(result))
    expected_paths = set(MODULE._positive_boolean_paths(result))
    assert set(payload["positive_output_trust_chain"]) == expected_paths


def test_missing_positive_output_binding_is_rejected() -> None:
    result = _task8_result()
    payload = MODULE.make_artifact("8", result)
    trust_chain = payload["positive_output_trust_chain"]
    assert isinstance(trust_chain, dict)
    trust_chain.pop("/validation_only_independent_tuning_passed")
    _rehash(payload)
    with pytest.raises(ValueError, match="positive-output trust chain"):
        MODULE.verify_artifact(payload, task_runner=lambda task: copy.deepcopy(result))


def test_forged_but_complete_positive_path_fails_fresh_recomputation() -> None:
    original = _task8_result()
    payload = MODULE.make_artifact("8", copy.deepcopy(original))
    forged = payload["result"]
    assert isinstance(forged, dict)
    forged["forged_but_complete_positive_marker"] = True
    payload["positive_output_trust_chain"] = {
        path: (
            "artifact_content+task_specific_source_bundle+frozen_config+"
            "semantic_derivation_from_raw_metrics+fresh_task_specific_recomputation"
        )
        for path in MODULE._positive_boolean_paths(forged)
    }
    _rehash(payload)
    with pytest.raises(ValueError, match="fresh task-specific recomputation"):
        MODULE.verify_artifact(payload, task_runner=lambda task: copy.deepcopy(original))


def test_instrument_pass_cannot_be_promoted_to_task8_overall_pass() -> None:
    result = _task8_result()
    result["task_8_passed"] = True
    with pytest.raises(ValueError, match="paired failure"):
        MODULE.make_artifact("8", result)


def test_action_distribution_shift_without_directional_utility_benefit_is_not_a_pass() -> None:
    result = _task8_result()
    payload = MODULE.make_artifact("8", result)
    paired = payload["result"]["paired_inference"]
    assert paired["strict_lower_bound_gate_passed"] is False
    assert payload["result"]["task_8_passed"] is False


def test_task8_endpoint_consumption_is_recomputed_not_caller_asserted() -> None:
    result = _task8_result()
    result["endpoint"]["consumes_interaction"] = False
    with pytest.raises(ValueError, match="does not consume"):
        MODULE.make_artifact("8", result)


def test_task8_result_cannot_lower_the_frozen_action_threshold() -> None:
    result = _task8_result()
    result["paired_inference"]["preregistered_strict_lower_bound_threshold"] = 0.0
    with pytest.raises(ValueError, match="preregistered paired threshold"):
        MODULE.make_artifact("8", result)


def test_window_instrument_cannot_hide_task7_contamination_failure() -> None:
    result = _task7_result()
    result["contamination_not_expanded"] = not bool(result["contamination_not_expanded"])
    result["task_7_passed"] = True
    with pytest.raises(ValueError, match="contamination gate"):
        MODULE.make_artifact("7", result)


def test_task7_complexity_pass_cannot_hide_a_suffix_read() -> None:
    result = _task7_result()
    probe = result["complexity_probe"]
    assert isinstance(probe, dict)
    rows = probe["rows"]
    assert isinstance(rows, list)
    rows[0]["marginal_untouched_suffix_items_read"] = 1
    with pytest.raises(ValueError, match="long-suffix complexity"):
        MODULE.make_artifact("7", result)


def test_task7_nonself_claim_is_derived_from_raw_proposal_counters() -> None:
    result = _task7_result()
    rows = result["rows"]
    assert isinstance(rows, list)
    local = next(row for row in rows if row["treatment"] == "local_rejuvenation")
    local["cost"]["marginal_nonself_rejuvenation_proposals"] = 0
    with pytest.raises(ValueError, match="non-self state"):
        MODULE.make_artifact("7", result)


def test_task_substitution_fails_even_after_outer_hash_is_recomputed() -> None:
    payload = MODULE.make_artifact("8", _task8_result())
    payload["task"] = "7"
    _rehash(payload)
    with pytest.raises(ValueError, match="source bundle drift"):
        MODULE.verify_artifact(payload, recompute=False)


def test_duplicate_json_keys_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text('{"task":"7","task":"8"}', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate JSON key"):
        MODULE.load_artifact(path)


def test_nonfinite_values_cannot_be_serialized_into_an_artifact() -> None:
    result = _task7_result()
    result["bad_metric"] = float("nan")
    with pytest.raises(ValueError, match="Out of range float"):
        MODULE.make_artifact("7", result)


def test_artifact_round_trip_uses_strict_loader(tmp_path: Path) -> None:
    result = _task8_result()
    payload = MODULE.make_artifact("8", result)
    path = tmp_path / "artifact.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    loaded = MODULE.load_artifact(path)
    MODULE.verify_artifact(
        loaded,
        task_runner=lambda task: copy.deepcopy(result),
    )


def test_registered_runner_rejects_config_drift_before_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(MODULE, "_file_sha256", lambda _path: "0" * 64)
    with pytest.raises(ValueError, match="frozen config drift"):
        MODULE.run_registered_task("7")


def test_registered_runner_rejects_code_config_threshold_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(MODULE, "TASK8_PAIRED_COST_CI_THRESHOLD", 999.0)
    with pytest.raises(ValueError, match="confirmatory contract disagree"):
        MODULE.run_registered_task("8")


def test_task7_v04_caller_selected_incomplete_matrix_cannot_claim_formal_protocol() -> None:
    with pytest.raises(ValueError, match="exact registered 2x2x2x2"):
        MODULE.run_late_correction_study(
            gaps=3,
            correction_index=1,
            scenario_seeds=(11,),
            budget=8,
            replicate_seeds=(101,),
            rejuvenation_window_length=2,
            protocol_id=MODULE.TASK7_CONDITIONAL_PROTOCOL_ID,
        )


def test_task8_one_seed_caller_design_cannot_claim_formal_v04() -> None:
    with pytest.raises(ValueError, match="only the frozen registered design"):
        MODULE.run_task8_matched_confirmatory_study(
            gaps=1,
            validation_seeds=(101,),
            confirmatory_seeds=(211,),
            state_budget=2_000_000,
        )


def test_task8_confirmatory_ci_clusters_the_eight_factor_cells_by_seed() -> None:
    result = _task8_result()
    assert result["task_8_verdict"] == "FAIL"
    assert len(result["paired_rows"]) == 40
    clusters = result["paired_seed_cluster_rows"]
    assert len(clusters) == 5
    assert {row["factor_cells"] for row in clusters} == {8}
    paired = result["paired_inference"]
    assert "seed cluster" in paired["independent_unit"]
    assert paired["paired_lower_confidence_bound"] <= 0.001


def test_task8_identity_matched_two_stage_algebraically_reconstructs_joint() -> None:
    scenario = registered_scenarios(
        1,
        (101,),
        relative_probability_coupling_nats=task8.TASK8_MATCHED_COUPLING_NATS,
        relative_probability_truth_model=True,
    )[0]
    exact, rows = _coupling_table(
        scenario,
        CostMeter(arm=ArmName.EXACT_ORACLE),
        2_000_000,
        include_regime=True,
    )
    matched = task8._matched_two_stage_belief(
        exact,
        rows,
        cause_temperature=1.0,
        conditional_temperature=1.0,
    )
    assert matched == pytest.approx(exact)


def test_task7_registered_rows_cover_every_factor_cell_and_treatment() -> None:
    result = _task7_result()
    assert result["complete_2x2x2x2_scenario_factor_matrix"] is True
    rows = result["rows"]
    assert len(rows) == 16 * 4
    assert {row["treatment"] for row in rows} == {
        "full_rerun",
        "local_rejuvenation",
        "reweight_only",
        "append_only",
    }
