from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from cpswm.system.evaluation_operations.structure_two_action_utility_construct_gate import (
    COMBINED_UTILITY_STATUS,
    DEFAULT_CONFIG,
    ConstructActionKind,
    LocationProbability,
    TaskSeparatedActionEnvironment,
    TaskSeparatedActionReadout,
    TaskSeparatedLearnedInteractionRuntime,
    TypedRouteCAction,
    _deterministic_run_execution_id,
    _information_set_sha256,
    _new_task_separated_runtime,
    _observation_commitment_sha256,
    _task_head_decision_id,
    _visible_observation_payload,
    load_action_utility_construct_gate_config,
    run_action_utility_construct_gate,
    verify_action_utility_construct_gate,
)
from cpswm.system.evaluation_operations.structure_two_full_scientific_loop import (
    FullScientificLoopConfig,
    LearnedCrossAxisInteractionModel,
    load_full_scientific_loop_config,
    train_cross_axis_interactions,
)
from cpswm.system.evaluation_operations.structure_two_stateful_full_joint import (
    FullJointArm,
    FullJointObservation,
    StatefulFullJointConfig,
    load_neural_proposal_model,
    load_stateful_full_joint_config,
)
from cpswm.system.reproducibility import content_sha256, content_uuid

ROOT = Path(__file__).resolve().parents[1]
RuntimeMaterial = tuple[
    FullScientificLoopConfig,
    StatefulFullJointConfig,
    LearnedCrossAxisInteractionModel,
]


@pytest.fixture(scope="module")
def artifact() -> dict[str, Any]:
    return run_action_utility_construct_gate(repository_root=ROOT)


@pytest.fixture(scope="module")
def runtime_material() -> RuntimeMaterial:
    gate_config = load_action_utility_construct_gate_config(ROOT)
    base_config = load_full_scientific_loop_config(ROOT, gate_config.base_full_loop_config)
    route_config = load_stateful_full_joint_config(ROOT, base_config.base_route_config)
    interaction_model, _selection, _evidence = train_cross_axis_interactions(
        repository_root=ROOT,
        config=base_config,
    )
    return base_config, route_config, interaction_model


def _new_runtime(
    runtime_material: RuntimeMaterial,
) -> TaskSeparatedLearnedInteractionRuntime:
    _base_config, route_config, interaction_model = runtime_material
    return _new_task_separated_runtime(
        route_config=route_config,
        interaction_model=interaction_model,
    )


def _complete_step(
    environment: TaskSeparatedActionEnvironment,
    runtime: TaskSeparatedLearnedInteractionRuntime,
    readout: TaskSeparatedActionReadout,
) -> None:
    environment.commit_actions(readout)
    environment.execute_search()
    environment.execute_put_back()
    environment.disclose_truth()
    feedback = environment.feedback()
    runtime.apply_feedback(feedback)


def _resign(payload: dict[str, Any]) -> None:
    unsigned = copy.deepcopy(payload)
    unsigned.pop("content_sha256", None)
    payload["content_sha256"] = content_sha256(unsigned)


def _rebind_serialized_trace(trace: dict[str, Any]) -> None:
    """Make a forged trace internally consistent after an identity rewrite."""

    readout = trace["readout"]
    step_index = trace["step_index"]
    run_execution_id = UUID(readout["run_execution_id"])
    source_update_id = UUID(trace["source_update_id"])
    readout["source_update_id"] = str(source_update_id)
    observation_commitment = _observation_commitment_sha256(
        run_execution_id=run_execution_id,
        step_index=step_index,
        source_update_id=source_update_id,
        visible_observation=trace["visible_observation"],
    )
    information_set = _information_set_sha256(
        run_execution_id=run_execution_id,
        step_index=step_index,
        source_update_id=source_update_id,
        observation_commitment_sha256=observation_commitment,
        belief_state_sha256=readout["belief_state_sha256"],
    )
    readout["observation_commitment_sha256"] = observation_commitment
    readout["information_set_sha256"] = information_set
    search_decision = _task_head_decision_id(
        kind=ConstructActionKind.SEARCH,
        run_execution_id=run_execution_id,
        step_index=step_index,
        source_update_id=source_update_id,
        information_set_sha256=information_set,
    )
    put_back_decision = _task_head_decision_id(
        kind=ConstructActionKind.PUT_BACK,
        run_execution_id=run_execution_id,
        step_index=step_index,
        source_update_id=source_update_id,
        information_set_sha256=information_set,
    )
    target_object_id = UUID(readout["selected_put_back_action"]["target_object_id"])
    search_distribution = readout["search_distribution"]
    search_order = sorted(
        search_distribution,
        key=lambda location: (-search_distribution[location], location),
    )
    rebuilt_search = [
        TypedRouteCAction.build(
            kind=ConstructActionKind.SEARCH,
            target_object_id=target_object_id,
            location_id=UUID(location),
            decision_id=search_decision,
            information_set_sha256=information_set,
        ).to_dict()
        for location in search_order
    ]
    put_back_distribution = readout["put_back_distribution"]
    put_back_location = sorted(
        put_back_distribution,
        key=lambda location: (-put_back_distribution[location], location),
    )[0]
    rebuilt_put_back = TypedRouteCAction.build(
        kind=ConstructActionKind.PUT_BACK,
        target_object_id=target_object_id,
        location_id=UUID(put_back_location),
        decision_id=put_back_decision,
        information_set_sha256=information_set,
    ).to_dict()
    readout["search_plan"] = rebuilt_search
    readout["selected_search_action"] = copy.deepcopy(rebuilt_search[0])
    readout["selected_put_back_action"] = rebuilt_put_back

    true_location = trace["truth"]["object_location_before_action"]
    found_index = search_order.index(true_location)
    trace["search_execution"]["planned_action_ids"] = [
        action["action_id"] for action in rebuilt_search
    ]
    trace["search_execution"]["executed_action_ids"] = [
        action["action_id"] for action in rebuilt_search[: found_index + 1]
    ]
    trace["search_execution"]["inspected_location_ids"] = search_order[: found_index + 1]
    trace["search_execution"]["inspection_count"] = found_index + 1
    trace["put_back_transition"]["typed_action"] = copy.deepcopy(rebuilt_put_back)


def _rewrite_location_identity_in_trace(
    trace: dict[str, Any],
    *,
    old_location: str,
    new_location: str,
) -> None:
    def rewrite(value: str) -> str:
        return new_location if value == old_location else value

    visible = trace["visible_observation"]
    visible["observed_location_id"] = rewrite(visible["observed_location_id"])
    visible["known_location_ids"] = [rewrite(value) for value in visible["known_location_ids"]]
    visible["base_location_distribution"] = {
        rewrite(key): value for key, value in visible["base_location_distribution"].items()
    }
    readout = trace["readout"]
    for distribution_name in ("search_distribution", "put_back_distribution"):
        readout[distribution_name] = {
            rewrite(key): value for key, value in readout[distribution_name].items()
        }
    for field in ("owner_habit_location", "object_location_before_action"):
        trace["truth"][field] = rewrite(trace["truth"][field])
    for field in (
        "pre_search_object_location",
        "post_search_object_location",
    ):
        trace["search_execution"][field] = rewrite(trace["search_execution"][field])
    for field in (
        "pre_action_location",
        "attempted_location",
        "post_action_location",
        "counterfactual_action",
        "counterfactual_post_action_location",
    ):
        trace["put_back_transition"][field] = rewrite(trace["put_back_transition"][field])
    _rebind_serialized_trace(trace)


def _manual_readout(
    environment: TaskSeparatedActionEnvironment,
    observation: FullJointObservation,
    *,
    put_back_location: UUID,
    observation_commitment_override: str | None = None,
) -> TaskSeparatedActionReadout:
    locations = environment.locations
    search_values = observation.base_location_distribution
    search_order = tuple(
        sorted(search_values, key=lambda location: (-search_values[location], str(location)))
    )
    belief_state = content_sha256({"test": "manual-belief", "step": environment.step_index})
    source_update_id = observation.source_update_id
    observation_commitment = observation_commitment_override or _observation_commitment_sha256(
        run_execution_id=environment.run_execution_id,
        step_index=environment.step_index,
        source_update_id=source_update_id,
        visible_observation=_visible_observation_payload(observation),
    )
    information_set = _information_set_sha256(
        run_execution_id=environment.run_execution_id,
        step_index=environment.step_index,
        source_update_id=source_update_id,
        observation_commitment_sha256=observation_commitment,
        belief_state_sha256=belief_state,
    )
    search_decision = _task_head_decision_id(
        kind=ConstructActionKind.SEARCH,
        run_execution_id=environment.run_execution_id,
        step_index=environment.step_index,
        source_update_id=source_update_id,
        information_set_sha256=information_set,
    )
    put_back_decision = _task_head_decision_id(
        kind=ConstructActionKind.PUT_BACK,
        run_execution_id=environment.run_execution_id,
        step_index=environment.step_index,
        source_update_id=source_update_id,
        information_set_sha256=information_set,
    )
    search_plan = tuple(
        TypedRouteCAction.build(
            kind=ConstructActionKind.SEARCH,
            target_object_id=environment.target_object_id,
            location_id=location,
            decision_id=search_decision,
            information_set_sha256=information_set,
        )
        for location in search_order
    )
    put_back_values = {location: float(location == put_back_location) for location in locations}
    return TaskSeparatedActionReadout(
        step_index=environment.step_index,
        run_execution_id=environment.run_execution_id,
        source_update_id=source_update_id,
        observation_commitment_sha256=observation_commitment,
        belief_state_sha256=belief_state,
        information_set_sha256=information_set,
        search_distribution=tuple(
            LocationProbability(location, search_values[location])
            for location in sorted(locations, key=str)
        ),
        put_back_distribution=tuple(
            LocationProbability(location, put_back_values[location])
            for location in sorted(locations, key=str)
        ),
        search_plan=search_plan,
        put_back_action=TypedRouteCAction.build(
            kind=ConstructActionKind.PUT_BACK,
            target_object_id=environment.target_object_id,
            location_id=put_back_location,
            decision_id=put_back_decision,
            information_set_sha256=information_set,
        ),
    )


def test_three_step_artifact_is_deterministic_and_freshly_verifiable(
    artifact: dict[str, Any],
) -> None:
    verify_action_utility_construct_gate(artifact, repository_root=ROOT)
    repeated = run_action_utility_construct_gate(repository_root=ROOT)

    assert repeated == artifact
    assert artifact["action_utility_construct_gate_passed"] is True
    assert artifact["probe"]["step_count"] == 3
    assert artifact["diagnostic_counts"] == {
        "selected_location_disagreement_step_count": 1,
        "successful_non_noop_put_back_transition_count": 1,
        "search_sensitivity_positive_control_count": 1,
        "put_back_sensitivity_positive_control_count": 1,
        "successful_wrong_put_back_control_count": 1,
    }


def test_source_binding_includes_direct_full_loop_configuration(
    artifact: dict[str, Any],
) -> None:
    gate_config = load_action_utility_construct_gate_config(ROOT)
    full_loop_path = ROOT / gate_config.base_full_loop_config
    bindings = {item["path"]: item["sha256"] for item in artifact["source_binding"]}
    assert (
        bindings[gate_config.base_full_loop_config.as_posix()]
        == hashlib.sha256(full_loop_path.read_bytes()).hexdigest()
    )


def test_typed_search_and_put_back_are_distinct_and_only_put_back_moves_state(
    artifact: dict[str, Any],
) -> None:
    traces = artifact["probe"]["traces"]
    non_owner = traces[2]
    search = non_owner["readout"]["selected_search_action"]
    put_back = non_owner["readout"]["selected_put_back_action"]
    truth = non_owner["truth"]
    search_execution = non_owner["search_execution"]
    transition = non_owner["put_back_transition"]

    assert search["kind"] == ConstructActionKind.SEARCH.value
    assert put_back["kind"] == ConstructActionKind.PUT_BACK.value
    assert search["location_id"] == truth["object_location_before_action"]
    assert put_back["location_id"] == truth["owner_habit_location"]
    assert search["location_id"] != put_back["location_id"]
    assert search_execution["object_state_changed"] is False
    assert search_execution["environment_step_advanced"] is False
    assert transition["action_success"] is True
    assert transition["commanded_non_noop"] is True
    assert transition["pre_action_location"] != transition["post_action_location"]
    assert transition["object_state_changed"] is True


def test_search_put_back_and_contamination_metrics_remain_separate(
    artifact: dict[str, Any],
) -> None:
    summary = artifact["separate_metric_summary"]

    assert set(summary) == {"search", "put_back", "contamination", "combined_utility"}
    assert summary["search"] == {
        "mean_normalized_extra_inspection_regret": 0.0,
        "mean_inspection_count": 1,
    }
    assert summary["put_back"]["error_rate"] == 0.0
    assert summary["put_back"]["successful_non_noop_state_change_count"] == 1
    assert summary["contamination"] == {
        "metric_id": "non_owner_copy_putback_proxy_only",
        "event_count": 0.0,
        "long_term_memory_contamination_established": False,
    }
    assert summary["combined_utility"] == {
        "status": COMBINED_UTILITY_STATUS,
        "value": None,
        "weights": None,
    }
    assert artifact["long_term_product_action_semantics_selected"] is False


def test_source_recomputed_single_head_controls_show_independent_metric_response(
    artifact: dict[str, Any],
) -> None:
    controls = artifact["sensitivity_controls"]
    baseline = artifact["probe"]["traces"][2]
    search_control = controls["search_ranking_intervention"]
    put_back_control = controls["put_back_ranking_intervention"]
    search_trace = search_control["raw_intervention_trace"]
    put_back_trace = put_back_control["raw_intervention_trace"]

    assert controls["summary"] == {
        "baseline_search_regret": 0.0,
        "search_intervention_regret": 0.5,
        "baseline_put_back_error": 0.0,
        "put_back_intervention_error": 1.0,
        "wrong_put_back_execution_success": True,
        "wrong_put_back_goal_satisfied": False,
    }
    assert all(search_control["comparisons"].values())
    assert all(put_back_control["comparisons"].values())
    assert {
        key: value
        for key, value in search_trace["put_back_transition"].items()
        if key != "typed_action"
    } == {
        key: value
        for key, value in baseline["put_back_transition"].items()
        if key != "typed_action"
    }
    assert search_trace["metrics"]["search_regret"] > baseline["metrics"]["search_regret"]
    assert {
        key: value
        for key, value in put_back_trace["search_execution"].items()
        if key not in {"planned_action_ids", "executed_action_ids"}
    } == {
        key: value
        for key, value in baseline["search_execution"].items()
        if key not in {"planned_action_ids", "executed_action_ids"}
    }
    assert put_back_trace["metrics"]["put_back_error"] == 1.0
    assert put_back_trace["metrics"]["put_back_execution_success"] is True
    assert put_back_trace["metrics"]["post_action_goal_satisfied"] is False


def test_environment_phase_guards_reject_truth_leak_bare_uuid_and_double_execution(
    runtime_material: RuntimeMaterial,
) -> None:
    base_config, _route_config, _interaction_model = runtime_material
    environment = TaskSeparatedActionEnvironment(seed=857, config=base_config)
    runtime = _new_runtime(runtime_material)

    with pytest.raises(ValueError, match="precommitted"):
        environment.execute_search()
    with pytest.raises(ValueError, match="after the committed search"):
        environment.execute_put_back()
    with pytest.raises(ValueError, match="only after action consequence"):
        environment.disclose_truth()

    observation = environment.observe_visible()
    step_before = environment.step_index
    with pytest.raises(ValueError, match="only after action consequence"):
        environment.disclose_truth()
    with pytest.raises(ValueError, match="precommitted"):
        environment.execute_search()
    with pytest.raises(ValueError, match="typed task-separated"):
        environment.commit_actions(environment.locations[0])  # type: ignore[arg-type]

    manual_readout = _manual_readout(
        environment,
        observation,
        put_back_location=environment.locations[1],
    )
    with pytest.raises(ValueError, match="single-use runtime capability"):
        environment.commit_actions(manual_readout)
    runtime.revise(observation)
    readout = environment.issue_runtime_readout(runtime)
    with pytest.raises(ValueError, match="single-use runtime capability"):
        environment.commit_actions(replace(readout))
    environment.commit_actions(readout)
    with pytest.raises(ValueError, match="only after action consequence"):
        environment.disclose_truth()
    search = environment.execute_search()
    assert environment.step_index == step_before
    assert search["environment_step_advanced"] is False
    with pytest.raises(ValueError, match="only after action consequence"):
        environment.disclose_truth()
    environment.execute_put_back()
    assert environment.step_index == step_before + 1
    with pytest.raises(ValueError, match="after the committed search"):
        environment.execute_put_back()
    assert environment.step_index == step_before + 1
    environment.disclose_truth()
    assert environment.phase_guard_events == (
        "visible_observation_issued",
        "typed_actions_committed",
        "search_executed",
        "put_back_executed",
        "truth_disclosed",
    )


def test_cross_step_and_copied_readout_replay_are_rejected(
    runtime_material: RuntimeMaterial,
) -> None:
    base_config, _route_config, _interaction_model = runtime_material
    environment = TaskSeparatedActionEnvironment(seed=859, config=base_config)
    runtime = _new_runtime(runtime_material)

    observation_0 = environment.observe_visible()
    runtime.revise(observation_0)
    readout_0 = environment.issue_runtime_readout(runtime)
    _complete_step(environment, runtime, readout_0)

    observation_1 = environment.observe_visible()
    runtime.revise(observation_1)
    with pytest.raises(ValueError, match="another environment step"):
        environment.commit_actions(readout_0)
    with pytest.raises(ValueError, match="canonical execution-bound decision"):
        replace(readout_0, step_index=1)

    current_but_unissued = _manual_readout(
        environment,
        observation_1,
        put_back_location=environment.locations[0],
    )
    with pytest.raises(ValueError, match="single-use runtime capability"):
        environment.commit_actions(current_but_unissued)
    issued_1 = environment.issue_runtime_readout(runtime)
    with pytest.raises(ValueError, match="single-use runtime capability"):
        environment.commit_actions(copy.deepcopy(issued_1))
    environment.commit_actions(issued_1)


def test_same_seed_cross_environment_and_foreign_runtime_replay_are_rejected(
    runtime_material: RuntimeMaterial,
) -> None:
    base_config, _route_config, _interaction_model = runtime_material
    shared_logical_run = _deterministic_run_execution_id(seed=863, role="same-role-replay-test")
    first = TaskSeparatedActionEnvironment(
        seed=863,
        config=base_config,
        run_execution_id=shared_logical_run,
    )
    second = TaskSeparatedActionEnvironment(
        seed=863,
        config=base_config,
        run_execution_id=shared_logical_run,
    )
    first_runtime = _new_runtime(runtime_material)
    second_runtime = _new_runtime(runtime_material)
    first_observation = first.observe_visible()
    second_observation = second.observe_visible()
    first_runtime.revise(first_observation)
    second_runtime.revise(second_observation)
    first_readout = first.issue_runtime_readout(first_runtime)

    assert first.run_execution_id == second.run_execution_id
    with pytest.raises(ValueError, match="single-use runtime capability"):
        second.commit_actions(first_readout)
    with pytest.raises(ValueError, match="this environment observation instance"):
        second.issue_runtime_readout(first_runtime)
    second_readout = second.issue_runtime_readout(second_runtime)
    second.commit_actions(second_readout)


def test_cross_control_replay_is_rejected_even_with_same_seed(
    runtime_material: RuntimeMaterial,
) -> None:
    base_config, _route_config, _interaction_model = runtime_material
    seed = 853
    baseline = TaskSeparatedActionEnvironment(
        seed=seed,
        config=base_config,
        run_execution_id=_deterministic_run_execution_id(seed=seed, role="baseline"),
    )
    search_control = TaskSeparatedActionEnvironment(
        seed=seed,
        config=base_config,
        run_execution_id=_deterministic_run_execution_id(
            seed=seed,
            role="search_sensitivity_control",
        ),
    )
    baseline_runtime = _new_runtime(runtime_material)
    control_runtime = _new_runtime(runtime_material)
    baseline_observation = baseline.observe_visible()
    control_observation = search_control.observe_visible()
    baseline_runtime.revise(baseline_observation)
    control_runtime.revise(control_observation)
    baseline_readout = baseline.issue_runtime_readout(baseline_runtime)

    with pytest.raises(ValueError, match="another environment execution"):
        search_control.commit_actions(baseline_readout)
    control_readout = search_control.issue_runtime_readout(
        control_runtime,
        intervention_head=ConstructActionKind.SEARCH,
    )
    search_control.commit_actions(control_readout)


def test_truth_derived_manual_readout_and_hostile_runtime_subclass_are_rejected(
    runtime_material: RuntimeMaterial,
) -> None:
    base_config, route_config, interaction_model = runtime_material
    environment = TaskSeparatedActionEnvironment(seed=877, config=base_config)
    observation = environment.observe_visible()
    truth_commitment = content_sha256({"forged_evaluator_truth": repr(environment._truth)})
    truth_derived = _manual_readout(
        environment,
        observation,
        put_back_location=environment.locations[0],
        observation_commitment_override=truth_commitment,
    )
    with pytest.raises(ValueError, match="current visible observation"):
        environment.commit_actions(truth_derived)

    class HostileRuntime(TaskSeparatedLearnedInteractionRuntime):
        def task_separated_readout(
            self,
            *,
            target_object_id: UUID,
            external_step_index: int,
            run_execution_id: UUID,
        ) -> TaskSeparatedActionReadout:
            del target_object_id, external_step_index, run_execution_id
            return truth_derived

    hostile = HostileRuntime(
        arm=FullJointArm.STATEFUL_FULL_JOINT,
        config=route_config,
        neural_model=load_neural_proposal_model(route_config.neural_proposal_model_path),
        interaction_model=interaction_model,
    )
    hostile.revise(observation)
    with pytest.raises(ValueError, match="registered task-separated runtime"):
        environment.issue_runtime_readout(hostile)


def test_typed_action_rejects_kind_substitution_and_hidden_fields(
    artifact: dict[str, Any],
) -> None:
    action = artifact["probe"]["traces"][2]["readout"]["selected_put_back_action"]
    wrong_kind = dict(action)
    wrong_kind["kind"] = "search"
    with pytest.raises(ValueError, match="malformed"):
        TypedRouteCAction.from_mapping(wrong_kind)

    hidden = dict(action)
    hidden["opaque_target"] = "forged"
    with pytest.raises(ValueError, match="hidden field"):
        TypedRouteCAction.from_mapping(hidden)


def test_rehashed_successful_noop_cannot_satisfy_state_change_gate(
    artifact: dict[str, Any],
) -> None:
    forged = copy.deepcopy(artifact)
    # Step 1 is a genuinely successful no-op in the deterministic probe.  A
    # caller cannot relabel it as a state change and increment the aggregate.
    trace = forged["probe"]["traces"][1]
    assert trace["put_back_transition"]["action_success"] is True
    assert trace["put_back_transition"]["commanded_non_noop"] is False
    trace["put_back_transition"]["object_state_changed"] = True
    trace["metrics"]["put_back_object_state_changed"] = True
    forged["diagnostic_counts"]["successful_non_noop_put_back_transition_count"] = 2
    forged["separate_metric_summary"]["put_back"]["successful_non_noop_state_change_count"] = 2
    _resign(forged)

    with pytest.raises(ValueError, match="successful-noop"):
        verify_action_utility_construct_gate(
            forged,
            repository_root=ROOT,
            fresh_recompute=False,
        )


def test_rehashed_search_put_back_construct_swap_is_rejected(
    artifact: dict[str, Any],
) -> None:
    forged = copy.deepcopy(artifact)
    readout = forged["probe"]["traces"][2]["readout"]
    readout["selected_search_action"] = copy.deepcopy(readout["selected_put_back_action"])
    _resign(forged)

    with pytest.raises(ValueError, match="task-head action"):
        verify_action_utility_construct_gate(
            forged,
            repository_root=ROOT,
            fresh_recompute=False,
        )


def test_rehashed_cross_object_task_heads_are_rejected_in_both_verify_modes(
    artifact: dict[str, Any],
) -> None:
    forged = copy.deepcopy(artifact)
    trace = forged["probe"]["traces"][0]
    readout = trace["readout"]
    foreign_target = content_uuid(
        "test-action-utility-foreign-target",
        {"original": forged["probe"]["target_object_id"]},
    )
    rebuilt_search_plan = []
    for action_payload in readout["search_plan"]:
        action = TypedRouteCAction.from_mapping(action_payload)
        rebuilt_search_plan.append(
            TypedRouteCAction.build(
                kind=ConstructActionKind.SEARCH,
                target_object_id=foreign_target,
                location_id=action.location_id,
                decision_id=action.decision_id,
                information_set_sha256=action.information_set_sha256,
            ).to_dict()
        )
    executed_count = len(trace["search_execution"]["executed_action_ids"])
    readout["search_plan"] = rebuilt_search_plan
    readout["selected_search_action"] = copy.deepcopy(rebuilt_search_plan[0])
    trace["search_execution"]["planned_action_ids"] = [
        action["action_id"] for action in rebuilt_search_plan
    ]
    trace["search_execution"]["executed_action_ids"] = [
        action["action_id"] for action in rebuilt_search_plan[:executed_count]
    ]
    _resign(forged)

    for fresh_recompute in (False, True):
        with pytest.raises(ValueError, match="registered probe target object"):
            verify_action_utility_construct_gate(
                forged,
                repository_root=ROOT,
                fresh_recompute=fresh_recompute,
            )


def test_complete_rehashed_probe_target_substitution_is_structurally_rejected(
    artifact: dict[str, Any],
) -> None:
    forged = copy.deepcopy(artifact)
    foreign_target = content_uuid(
        "test-action-utility-complete-probe-target-substitution",
        {"seed": forged["probe"]["seed"]},
    )
    forged["probe"]["target_object_id"] = str(foreign_target)
    traces = list(forged["probe"]["traces"])
    traces.extend(
        (
            forged["sensitivity_controls"]["search_ranking_intervention"]["raw_intervention_trace"],
            forged["sensitivity_controls"]["put_back_ranking_intervention"][
                "raw_intervention_trace"
            ],
        )
    )
    for trace in traces:
        readout = trace["readout"]
        rebuilt_search = []
        for payload in readout["search_plan"]:
            action = TypedRouteCAction.from_mapping(payload)
            rebuilt_search.append(
                TypedRouteCAction.build(
                    kind=ConstructActionKind.SEARCH,
                    target_object_id=foreign_target,
                    location_id=action.location_id,
                    decision_id=action.decision_id,
                    information_set_sha256=action.information_set_sha256,
                ).to_dict()
            )
        put_back = TypedRouteCAction.from_mapping(readout["selected_put_back_action"])
        rebuilt_put_back = TypedRouteCAction.build(
            kind=ConstructActionKind.PUT_BACK,
            target_object_id=foreign_target,
            location_id=put_back.location_id,
            decision_id=put_back.decision_id,
            information_set_sha256=put_back.information_set_sha256,
        ).to_dict()
        executed_count = len(trace["search_execution"]["executed_action_ids"])
        readout["search_plan"] = rebuilt_search
        readout["selected_search_action"] = copy.deepcopy(rebuilt_search[0])
        readout["selected_put_back_action"] = rebuilt_put_back
        trace["search_execution"]["planned_action_ids"] = [
            action["action_id"] for action in rebuilt_search
        ]
        trace["search_execution"]["executed_action_ids"] = [
            action["action_id"] for action in rebuilt_search[:executed_count]
        ]
        trace["put_back_transition"]["typed_action"] = copy.deepcopy(rebuilt_put_back)
    _resign(forged)

    with pytest.raises(ValueError, match="target or execution ID is noncanonical"):
        verify_action_utility_construct_gate(
            forged,
            repository_root=ROOT,
            fresh_recompute=False,
        )


@pytest.mark.parametrize(
    ("identity_field", "error_pattern"),
    (
        ("location", "location registry"),
        ("source", "source update ID is not seed/step canonical"),
        ("cluster", "evidence cluster ID is not seed/step canonical"),
    ),
)
def test_rehashed_seed_derived_identity_anchor_substitution_is_rejected(
    artifact: dict[str, Any],
    identity_field: str,
    error_pattern: str,
) -> None:
    forged = copy.deepcopy(artifact)
    foreign_id = str(
        content_uuid(
            "test-action-utility-foreign-identity-anchor",
            {"field": identity_field},
        )
    )
    if identity_field == "location":
        old_location = forged["probe"]["location_ids"][0]
        # Change only the final hexadecimal digit so UUID lexical tie-breaking
        # remains unchanged while every dependent location identity is rewritten.
        foreign_id = old_location[:-1] + ("0" if old_location[-1] != "0" else "1")
        forged["probe"]["location_ids"][0] = foreign_id
        all_traces = list(forged["probe"]["traces"])
        all_traces.extend(
            (
                forged["sensitivity_controls"]["search_ranking_intervention"][
                    "raw_intervention_trace"
                ],
                forged["sensitivity_controls"]["put_back_ranking_intervention"][
                    "raw_intervention_trace"
                ],
            )
        )
        for trace in all_traces:
            _rewrite_location_identity_in_trace(
                trace,
                old_location=old_location,
                new_location=foreign_id,
            )
    elif identity_field == "source":
        trace = forged["probe"]["traces"][0]
        trace["source_update_id"] = foreign_id
        trace["visible_observation"]["source_update_id"] = foreign_id
        _rebind_serialized_trace(trace)
    else:
        trace = forged["probe"]["traces"][0]
        trace["visible_observation"]["evidence_cluster_id"] = foreign_id
        _rebind_serialized_trace(trace)
    _resign(forged)

    with pytest.raises(ValueError, match=error_pattern):
        verify_action_utility_construct_gate(
            forged,
            repository_root=ROOT,
            fresh_recompute=False,
        )


def test_rehashed_successful_wrong_action_cannot_claim_zero_put_back_error(
    artifact: dict[str, Any],
) -> None:
    forged = copy.deepcopy(artifact)
    trace = forged["sensitivity_controls"]["put_back_ranking_intervention"][
        "raw_intervention_trace"
    ]
    assert trace["put_back_transition"]["action_success"] is True
    assert trace["metrics"]["post_action_goal_satisfied"] is False
    assert trace["metrics"]["put_back_error"] == 1.0
    trace["metrics"]["put_back_error"] = 0.0
    _resign(forged)

    with pytest.raises(ValueError, match="sensitivity metric"):
        verify_action_utility_construct_gate(
            forged,
            repository_root=ROOT,
            fresh_recompute=False,
        )


def test_complete_rehash_of_source_derived_field_fails_fresh_recomputation(
    artifact: dict[str, Any],
) -> None:
    forged = copy.deepcopy(artifact)
    forged["probe"]["interaction_model_sha256"] = "0" * 64
    _resign(forged)

    # Structural checks and a caller-held content hash are not historical
    # authenticity.  Fresh source recomputation is the decisive check.
    verify_action_utility_construct_gate(
        forged,
        repository_root=ROOT,
        fresh_recompute=False,
    )
    with pytest.raises(ValueError, match="fresh deterministic recomputation"):
        verify_action_utility_construct_gate(forged, repository_root=ROOT)


def test_config_rejects_combined_utility_or_product_semantic_selection(
    tmp_path: Path,
) -> None:
    payload = json.loads((ROOT / DEFAULT_CONFIG).read_text(encoding="utf-8"))
    payload["action_semantics"]["combined_utility_status"] = "EQUAL_WEIGHTED_SUM"
    payload["action_semantics"]["long_term_product_action_semantics_selected"] = True
    path = tmp_path / "narrowed-product-policy.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="semantics drifted"):
        load_action_utility_construct_gate_config(ROOT, path)
