from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest

from cpswm.system.evaluation_operations.structure_two_task7_task8_method_restructure import (
    TASK8_IDENTIFIABILITY_PROTOCOL_ID,
    run_task7_guarded_restructure_study,
    run_task8_identifiability_audit,
)

ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "apps/evaluation_runner/run_structure_two_task7_task8_failure_restructure.py"
SPEC = importlib.util.spec_from_file_location("run_task7_task8_restructure", RUNNER_PATH)
assert SPEC is not None and SPEC.loader is not None
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


def _synthetic_result() -> dict[str, object]:
    factor_names = (
        "high_attribution_ambiguity",
        "adverse_delayed_feedback",
        "open_world_actor",
        "short_regime",
    )
    task7_rows = []
    for cell in range(16):
        bits = f"{cell:04b}"
        route = "guarded_reweight" if cell == 0 else "guarded_full_replay"
        task7_rows.append(
            {
                "scenario_id": f"G12-S307-{bits}",
                "scenario_factors": {
                    name: bit == "1" for name, bit in zip(factor_names, bits, strict=True)
                },
                "replicate_seed": 419,
                "route": route,
                "fallback_required": route == "guarded_full_replay",
                "fallback_reasons": (
                    "" if route == "guarded_reweight" else "reweight_support_collapse"
                ),
                "pre_rejuvenation_ess_ratio": (0.5 if route == "guarded_reweight" else 0.1),
                "belief_axis_distances_to_full_rerun": {
                    axis: 0.0 for axis in RUNNER.TASK7_BELIEF_AXES
                },
                "max_belief_axis_distance_to_full_rerun": 0.0,
                "action_distribution_distance_to_full_rerun": 0.0,
                "selected_action_matches_full_rerun": True,
                "guarded_owner_contamination": 0.0,
                "full_rerun_owner_contamination": 0.0,
                "guarded_marginal_elementary_evaluations": 1,
                "full_rerun_marginal_elementary_evaluations": 2,
            }
        )
    task8_rows = [
        {
            "unit_id": f"G1-S{seed}-{cell:03b}1-RPC1.5",
            "cluster_seed": seed,
            "posterior_l1": 0.0,
            "policy_l1": 0.0,
            "matched_two_stage_cost_minus_joint_cost": 0.0,
        }
        for seed in (307, 311)
        for cell in range(8)
    ]
    return {
        "task_7": {
            "protocol_id": RUNNER.TASK7_GUARDED_RESTRUCTURE_PROTOCOL_ID,
            "evidence_status": "synthetic verifier fixture",
            "design": {
                "gaps": 12,
                "correction_index": 2,
                "scenario_seeds": [307],
                "replicate_seeds": [419],
                "factor_cells_per_scenario_seed": 16,
                "particle_budget": 384,
                "guarded_reweight_ess_ratio": 0.3,
                "threshold_origin": (
                    "frozen after diagnosing v0.4 and before evaluating the new holdout seeds"
                ),
            },
            "method": {
                "name": "support-aware reversible correction router",
                "adequate_support_route": "exact observation likelihood-ratio reweighting",
                "support_collapse_route": "explicit full replay",
                "window_mh_after_support_collapse_forbidden": True,
                "fallback_visible_and_fully_costed": True,
            },
            "rows": task7_rows,
            "route_counts": {"guarded_reweight": 1, "guarded_full_replay": 15},
            "belief_guardrail_passed": True,
            "action_guardrail_passed": True,
            "contamination_guardrail_passed": True,
            "mixed_route_nontriviality_passed": True,
            "candidate_passed": True,
            "mean_guarded_owner_contamination": 0.0,
            "mean_full_rerun_owner_contamination": 0.0,
            "mean_guarded_marginal_elementary_evaluations": 1.0,
            "mean_full_rerun_marginal_elementary_evaluations": 2.0,
            "failed_guard_rows": [],
            "failure_diagnosis": None,
            "required_next_state_change": None,
            "claim_boundary": "synthetic verifier fixture",
        },
        "task_8": {
            "protocol_id": RUNNER.TASK8_IDENTIFIABILITY_PROTOCOL_ID,
            "evidence_status": "synthetic verifier fixture",
            "seeds": [307, 311],
            "rows": task8_rows,
            "factor_units": 16,
            "identity_temperature": 1.0,
            "max_posterior_l1": 0.0,
            "max_policy_l1": 0.0,
            "max_absolute_expected_cost_difference": 0.0,
            "matched_two_stage_representation_equivalent": True,
            "joint_representation_superiority_identifiable": False,
            "diagnosis": "synthetic verifier fixture",
            "redesign_options_requiring_owner_choice": [],
            "seven_operator_efficacy_authorized": False,
        },
    }


def _rehash(artifact: dict[str, object]) -> None:
    unsigned = dict(artifact)
    unsigned.pop("content_sha256")
    artifact["content_sha256"] = RUNNER._sha256(unsigned)


def _refresh_result_bindings(artifact: dict[str, object]) -> None:
    artifact["recomputation"]["deterministic_result_sha256"] = RUNNER._sha256(artifact["result"])
    artifact["positive_output_trust_chain"] = {
        path: RUNNER.TRUST_CHAIN_DESCRIPTION
        for path in RUNNER._positive_boolean_paths(
            {"result": artifact["result"], "recomputation": artifact["recomputation"]}
        )
    }
    _rehash(artifact)


def test_task8_exact_two_stage_equivalence_blocks_representation_superiority_claim() -> None:
    result = run_task8_identifiability_audit(seeds=(307,))
    assert result["protocol_id"] == TASK8_IDENTIFIABILITY_PROTOCOL_ID
    assert result["factor_units"] == 8
    assert result["matched_two_stage_representation_equivalent"] is True
    assert result["joint_representation_superiority_identifiable"] is False
    assert result["max_posterior_l1"] < 1e-12
    assert result["max_policy_l1"] < 1e-12
    assert result["max_absolute_expected_cost_difference"] < 1e-12
    assert result["seven_operator_efficacy_authorized"] is False


def test_task8_identifiability_audit_rejects_seed_reuse() -> None:
    with pytest.raises(ValueError, match="non-empty and unique"):
        run_task8_identifiability_audit(seeds=(307, 307))


def test_task7_guarded_study_rejects_invalid_threshold_before_execution() -> None:
    with pytest.raises(ValueError, match="ESS threshold"):
        run_task7_guarded_restructure_study(
            scenario_seeds=(307,),
            replicate_seeds=(419,),
            budget=8,
            ess_ratio_threshold=0.0,
        )


def test_restructure_artifact_derives_every_positive_output_from_raw_rows() -> None:
    result = _synthetic_result()
    artifact = RUNNER.make_artifact(result)
    RUNNER.verify_artifact(artifact, fresh_result=result)
    expected_paths = set(
        RUNNER._positive_boolean_paths(
            {"result": artifact["result"], "recomputation": artifact["recomputation"]}
        )
    )
    assert set(artifact["positive_output_trust_chain"]) == expected_paths


def test_forged_complete_restructure_positive_fails_semantic_recomputation() -> None:
    result = _synthetic_result()
    forged = RUNNER.make_artifact(result)
    forged["result"]["task_7"]["belief_guardrail_passed"] = False
    _refresh_result_bindings(forged)
    with pytest.raises(ValueError, match="verdict is not derived"):
        RUNNER.verify_artifact(forged, fresh_result=forged["result"])


def test_restructure_artifact_rejects_incomplete_factor_coverage() -> None:
    result = _synthetic_result()
    forged = RUNNER.make_artifact(result)
    forged["result"]["task_7"]["rows"] = forged["result"]["task_7"]["rows"][:2]
    _refresh_result_bindings(forged)
    with pytest.raises(ValueError, match="exactly cover"):
        RUNNER.verify_artifact(forged, fresh_result=forged["result"])


def test_restructure_artifact_rejects_arbitrary_trust_claim_values() -> None:
    result = _synthetic_result()
    forged = RUNNER.make_artifact(result)
    forged["positive_output_trust_chain"] = {
        path: "forged self-assertion" for path in forged["positive_output_trust_chain"]
    }
    _rehash(forged)
    with pytest.raises(ValueError, match="trust chain"):
        RUNNER.verify_artifact(forged, fresh_result=result)


def test_restructure_artifact_rejects_protocol_substitution() -> None:
    result = _synthetic_result()
    forged = RUNNER.make_artifact(result)
    forged["result"]["task_8"]["protocol_id"] = "substituted@9"
    _refresh_result_bindings(forged)
    with pytest.raises(ValueError, match="protocol substitution"):
        RUNNER.verify_artifact(forged, fresh_result=forged["result"])


def test_restructure_artifact_rejects_duplicate_units() -> None:
    result = _synthetic_result()
    forged = RUNNER.make_artifact(result)
    forged["result"]["task_8"]["rows"][1] = copy.deepcopy(forged["result"]["task_8"]["rows"][0])
    _refresh_result_bindings(forged)
    with pytest.raises(ValueError, match="duplicate factor unit"):
        RUNNER.verify_artifact(forged, fresh_result=forged["result"])


def test_restructure_artifact_requires_fresh_independent_execution() -> None:
    result = _synthetic_result()
    artifact = RUNNER.make_artifact(result)
    with pytest.raises(ValueError, match="fresh independent"):
        RUNNER.verify_artifact(artifact)


def test_restructure_artifact_rejects_stored_rewrite_against_fresh_run() -> None:
    result = _synthetic_result()
    forged_result = copy.deepcopy(result)
    forged_result["task_7"]["evidence_status"] = "rewritten after outcome"
    forged = RUNNER.make_artifact(forged_result)
    with pytest.raises(ValueError, match="does not match"):
        RUNNER.verify_artifact(forged, fresh_result=result)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("mean_guarded_owner_contamination", False),
        ("mean_guarded_marginal_elementary_evaluations", True),
    ),
)
def test_restructure_artifact_rejects_boolean_as_task7_numeric(field: str, value: bool) -> None:
    result = _synthetic_result()
    forged = RUNNER.make_artifact(result)
    forged["result"]["task_7"][field] = value
    _refresh_result_bindings(forged)
    with pytest.raises(ValueError, match="JSON number"):
        RUNNER.verify_artifact(forged, fresh_result=forged["result"])


def test_restructure_artifact_rejects_integer_as_factor_boolean() -> None:
    result = _synthetic_result()
    forged = RUNNER.make_artifact(result)
    forged["result"]["task_7"]["rows"][0]["scenario_factors"]["high_attribution_ambiguity"] = 0
    _refresh_result_bindings(forged)
    with pytest.raises(ValueError, match="factors or identity"):
        RUNNER.verify_artifact(forged, fresh_result=forged["result"])


def test_restructure_artifact_rejects_boolean_as_identity_temperature() -> None:
    result = _synthetic_result()
    forged = RUNNER.make_artifact(result)
    forged["result"]["task_8"]["identity_temperature"] = True
    _refresh_result_bindings(forged)
    with pytest.raises(ValueError, match="JSON number"):
        RUNNER.verify_artifact(forged, fresh_result=forged["result"])


def test_restructure_artifact_rejects_run_date_substitution() -> None:
    result = _synthetic_result()
    forged = RUNNER.make_artifact(result)
    forged["run_date"] = "2099-01-01"
    _rehash(forged)
    with pytest.raises(ValueError, match="run-date substitution"):
        RUNNER.verify_artifact(forged, fresh_result=result)


def test_restructure_frozen_config_hash_is_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    original = RUNNER._file_sha256

    def drifted_hash(path: Path) -> str:
        if path == RUNNER.REPOSITORY_ROOT / RUNNER.CONFIG_PATH:
            return "0" * 64
        return original(path)

    monkeypatch.setattr(RUNNER, "_file_sha256", drifted_hash)
    with pytest.raises(ValueError, match="frozen config content drift"):
        RUNNER._load_config()
