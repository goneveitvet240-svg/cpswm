from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "apps/evaluation_runner/run_structure_two_backbone_b_repairs.py"
SPEC = importlib.util.spec_from_file_location("run_structure_two_backbone_b_repairs", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _task7_result() -> dict[str, object]:
    local_row = {
        "treatment": "local_rejuvenation",
        "belief_axis_distances_to_full_rerun": {axis: 0.0 for axis in MODULE.TASK7_BELIEF_AXES},
        "action_distribution_distance_to_full_rerun": 0.0,
        "selected_action_matches_full_rerun": True,
        "cost": {
            "marginal_rejuvenation_proposals": 1,
            "marginal_nonself_rejuvenation_proposals": 1,
            "marginal_untouched_suffix_items_read": 0,
            "marginal_untouched_suffix_items_copied": 0,
            "marginal_untouched_suffix_items_rehashed": 0,
        },
    }
    complexity_row = {
        "marginal_window_gap_target_evaluations": 4,
        "marginal_max_repair_live_window_items": 25,
        "reachable_persistent_overlay_bytes": 300,
        "marginal_untouched_suffix_items_read": 0,
        "marginal_untouched_suffix_items_copied": 0,
        "marginal_untouched_suffix_items_rehashed": 0,
        "fallback_required": False,
    }
    return {
        "protocol_id": MODULE.TASK7_PROTOCOL_ID,
        "seven_operator_efficacy_authorized": False,
        "belief_equivalence_passed": True,
        "action_equivalence_passed": True,
        "equivalence_passed": True,
        "local_cost_passed": True,
        "no_fallbacks_in_registered_run": True,
        "nonself_move_passed": True,
        "strict_window_complexity_passed": True,
        "window_implementation_passed": True,
        "task_7_instrument_passed": True,
        "contamination_not_expanded": True,
        "task_7_passed": True,
        "window_contract": {
            "full_suffix_replayed_by_local_kernel": False,
            "untouched_suffix_copy_scan_or_rehash": False,
            "proposal_window_length": 3,
        },
        "complexity_probe": {
            "window_target_work_invariant_to_suffix_length": True,
            "persistent_live_items_invariant_to_suffix_length": True,
            "reachable_overlay_bytes_invariant_to_suffix_length": True,
            "zero_untouched_suffix_operations": True,
            "passed": True,
            "rows": [complexity_row],
        },
        "rows": [local_row],
    }


def _task8_result() -> dict[str, object]:
    return {
        "protocol_id": MODULE.TASK8_PROTOCOL_ID,
        "seven_operator_efficacy_authorized": False,
        "belief_coupling_instrument_passed": True,
        "consequential_endpoint_id": "joint-cross-safety-policy@0.1",
        "endpoint_consumes_interaction": True,
        "consequential_action_distribution_distance_primary": 0.02,
        "min_measurable_consequential_action_distribution_distance": 0.01,
        "consequential_action_endpoint_passed": True,
        "mean_factorized_excess_consequential_cost": 0.0,
        "min_measurable_mean_consequential_cost_advantage": 0.001,
        "consequential_utility_benefit_passed": False,
        "joint_action_utility_passed": False,
        "task_8_passed": False,
    }


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
    trust_chain.pop("/belief_coupling_instrument_passed")
    _rehash(payload)
    with pytest.raises(ValueError, match="positive-output trust chain"):
        MODULE.verify_artifact(payload, task_runner=lambda task: copy.deepcopy(result))


def test_forged_but_complete_positive_path_fails_fresh_recomputation() -> None:
    original = _task8_result()
    payload = MODULE.make_artifact("8", copy.deepcopy(original))
    forged = payload["result"]
    assert isinstance(forged, dict)
    forged["mean_factorized_excess_consequential_cost"] = 0.002
    forged["consequential_utility_benefit_passed"] = True
    forged["joint_action_utility_passed"] = True
    forged["task_8_passed"] = True
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
    with pytest.raises(ValueError, match="instrument-only"):
        MODULE.make_artifact("8", result)


def test_action_distribution_shift_without_directional_utility_benefit_is_not_a_pass() -> None:
    result = _task8_result()
    payload = MODULE.make_artifact("8", result)
    assert payload["result"]["consequential_utility_benefit_passed"] is False
    assert payload["result"]["task_8_passed"] is False


def test_task8_endpoint_consumption_is_recomputed_not_caller_asserted() -> None:
    result = _task8_result()
    result["endpoint_consumes_interaction"] = False
    with pytest.raises(ValueError, match="cross-term consumption"):
        MODULE.make_artifact("8", result)


def test_task8_result_cannot_lower_the_frozen_action_threshold() -> None:
    result = _task8_result()
    result["min_measurable_consequential_action_distribution_distance"] = 0.0
    with pytest.raises(ValueError, match="thresholds differ"):
        MODULE.make_artifact("8", result)


def test_window_instrument_cannot_hide_task7_contamination_failure() -> None:
    result = _task7_result()
    result["contamination_not_expanded"] = False
    result["task_7_passed"] = True
    with pytest.raises(ValueError, match="instrument-only"):
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
    rows[0]["cost"]["marginal_nonself_rejuvenation_proposals"] = 0
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
    monkeypatch.setattr(MODULE, "MIN_MEASURABLE_CONSEQUENTIAL_ACTION_DISTANCE", 999.0)
    with pytest.raises(ValueError, match="executable thresholds disagree"):
        MODULE.run_registered_task("8")
