from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import pytest

from cpswm.system.evaluation_operations.structure_two_full_scientific_loop import (
    DEFAULT_CONFIG,
    INTERACTION_FEATURE_NAMES,
    ActionResponsiveEnvironment,
    _deterministic_payload,
    load_full_scientific_loop_config,
    verify_full_scientific_loop_result,
)
from cpswm.system.evaluation_operations.structure_two_selected_method import (
    StructureTwoOperator,
)
from cpswm.system.evaluation_operations.structure_two_stateful_full_joint import (
    COMPLETE_STATE_AXES,
    RB_BLOCKS,
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
    """Keep semantic-forgery tests behind current source binding.

    The checked-in v0.2 artifact is intentionally immutable and its historical
    production sidecar predates Architecture A.  Tests that target deeper
    semantic checks replace only that sidecar in memory; the historical file is
    never rewritten or promoted to current runtime evidence.
    """

    payload["production_system_assembly"] = build_production_assembly_manifest(ROOT)


def test_protocol_keeps_the_complete_route_c_scope_and_disjoint_splits() -> None:
    config = load_full_scientific_loop_config(ROOT, DEFAULT_CONFIG)

    assert set(COMPLETE_STATE_AXES) == {
        "event_chain",
        "ordered_actor_roles",
        "instance_association",
        "change_cause",
        "habit_regime",
        "run_length",
        "revision_lineage",
    }
    assert len(RB_BLOCKS) == 3
    assert len(StructureTwoOperator) == 7
    assert not (set(config.train_seeds) & set(config.validation_seeds))
    assert not (set(config.train_seeds) & set(config.evaluation_seeds))
    assert not (set(config.validation_seeds) & set(config.evaluation_seeds))


def test_action_responsive_environment_changes_the_next_observation() -> None:
    config = load_full_scientific_loop_config(ROOT)
    selected_seed = next(
        seed
        for seed in range(1, 100)
        if ActionResponsiveEnvironment(seed=seed, config=config)._unit_random("action-success", 0)
        < config.action_success_probability
    )
    left = ActionResponsiveEnvironment(seed=selected_seed, config=config)
    right = ActionResponsiveEnvironment(seed=selected_seed, config=config)
    left_observation, _ = left.observe()
    right_observation, _ = right.observe()

    left_transition = left.execute(left.locations[0])
    right_transition = right.execute(right.locations[1])
    left_next, _ = left.observe()
    right_next, _ = right.observe()

    assert left_observation == right_observation
    assert (
        left_transition["potential_outcome_randomness_key"]
        == right_transition["potential_outcome_randomness_key"]
    )
    assert left_transition["action_success"] is True
    assert right_transition["action_success"] is True
    assert left_next.observed_location_id == left.locations[0]
    assert right_next.observed_location_id == right.locations[1]
    assert left_next.observed_location_id != right_next.observed_location_id


def test_checked_in_full_loop_artifact_is_historical_and_source_stale(
    artifact: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="production assembly manifest mismatch"):
        verify_full_scientific_loop_result(artifact, repository_root=ROOT)

    assert artifact["matched_closed_loop_fairness"]["passed"] is True  # type: ignore[index]
    assert (
        artifact["action_responsive_environment"][  # type: ignore[index]
            "environment_trajectory_responds_to_route_action"
        ]
        is True
    )
    assert artifact["rgrc_positive_and_negative_activation_passed"] is True
    assert artifact["scientific_superiority_established"] is False


def test_interactions_are_learned_then_frozen_before_evaluation(
    artifact: dict[str, object],
) -> None:
    model = artifact["learned_cross_axis_interaction"]  # type: ignore[assignment]
    split = artifact["split_contract"]  # type: ignore[assignment]

    assert tuple(model["feature_names"]) == INTERACTION_FEATURE_NAMES
    assert any(abs(float(weight)) > 1e-9 for weight in model["weights"])
    assert all(math.isfinite(float(weight)) for weight in model["weights"])
    assert model["frozen_before_evaluation"] is True
    assert model["evaluation_seeds_seen_during_training_or_selection"] is False
    assert not (
        set(split["development_evaluation_seeds"])
        & (set(model["train_seeds"]) | set(model["validation_seeds"]))
    )
    assert (
        artifact["learned_interaction_utilization"][  # type: ignore[index]
            "positive_action_posterior_tv_steps"
        ]
        > 0
    )


def test_rgrc_suite_exercises_positive_and_negative_paths(
    artifact: dict[str, object],
) -> None:
    suite = artifact["rgrc_activation_suite"]  # type: ignore[assignment]
    operations = suite["positive_transition_sequence"]

    assert {"quarantine", "promote", "retract", "corrected_revision"} <= set(operations)
    assert operations[-1] == "retract"
    assert all(suite["positive_cases"].values())
    assert all(suite["negative_cases"].values())
    assert suite["negative_case_evidence"]["unstable_owner_rejected"]["operations"] == [
        "quarantine"
    ]


def test_all_seven_single_operator_neutralizations_are_complete(
    artifact: dict[str, object],
) -> None:
    ablation = artifact["seven_operator_neutralization"]  # type: ignore[assignment]
    expected = {operator.value for operator in StructureTwoOperator}

    assert ablation["all_seven_neutralizations_completed"] is True
    assert set(ablation["runs"]) == expected
    assert set(ablation["summaries"]) == expected
    for operator, rows in ablation["runs"].items():
        assert all(row["neutralized_operator"] == operator for row in rows)
        assert all(row["all_seven_operators_retained"] for row in rows)
        assert all(row["neutralization_exercised"] for row in rows)
        assert all(
            all(
                counts["executed_count"] > 0
                for name, counts in row["operator_counts"].items()
                if name != operator
            )
            for row in rows
        )


def test_rehashed_environment_transition_forgery_is_rejected(
    artifact: dict[str, object],
) -> None:
    forged = copy.deepcopy(artifact)
    trace = forged["closed_loop_runs"][FullJointArm.STATEFUL_FULL_JOINT.value][0][  # type: ignore[index]
        "traces"
    ][0]
    trace["transition"]["action_success"] = not trace["transition"]["action_success"]
    _bind_current_production_manifest(forged)
    _resign(forged)

    with pytest.raises(ValueError, match="transition is not environment-derived"):
        verify_full_scientific_loop_result(forged, repository_root=ROOT)


def test_rehashed_operator_receipt_forgery_is_rejected(
    artifact: dict[str, object],
) -> None:
    forged = copy.deepcopy(artifact)
    receipt = forged["seven_operator_neutralization"]["runs"][  # type: ignore[index]
        StructureTwoOperator.OPCEU.value
    ][0]["operator_flow_receipts"][0]
    receipt["detail"] = "forged-but-complete"
    _bind_current_production_manifest(forged)
    _resign(forged)

    with pytest.raises(ValueError, match="receipt content hash mismatch"):
        verify_full_scientific_loop_result(forged, repository_root=ROOT)


def test_rehashed_ablation_summary_forgery_is_rejected(
    artifact: dict[str, object],
) -> None:
    forged = copy.deepcopy(artifact)
    forged["seven_operator_neutralization"]["summaries"][  # type: ignore[index]
        StructureTwoOperator.RGRC.value
    ]["decision_effect_observed"] = False
    _bind_current_production_manifest(forged)
    _resign(forged)

    with pytest.raises(ValueError, match="neutralization summary is not run-derived"):
        verify_full_scientific_loop_result(forged, repository_root=ROOT)


def test_result_does_not_promote_development_evidence(
    artifact: dict[str, object],
) -> None:
    assert artifact["all_seven_operator_contributions_established"] is False
    assert artifact["scientific_superiority_established"] is False
    assert artifact["real_robot_external_validity_established"] is False
    assert artifact["independent_custody_established"] is False
    assert artifact["task_8_formal_passed"] is False
