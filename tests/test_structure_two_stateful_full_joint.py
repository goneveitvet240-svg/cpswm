from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from cpswm.contracts import EventMechanism, ProjectTwoDatasetSplit
from cpswm.contracts.hidden_event_evidence import ordered_role_key
from cpswm.system.evaluation_operations.project_two_dataset_adapters import (
    D0SyntheticOracleReplayAdapter,
)
from cpswm.system.evaluation_operations.structure_two_selected_method import (
    ParticleChangeCause,
    StructureTwoOperator,
)
from cpswm.system.evaluation_operations.structure_two_stateful_full_joint import (
    COMPLETE_STATE_AXES,
    FullJointArm,
    FullJointObservation,
    StatefulFullJointRuntime,
    evaluate_stateful_full_joint_episode,
    load_neural_proposal_model,
    load_stateful_full_joint_config,
    verify_stateful_full_joint_result,
)

ROOT = Path(__file__).resolve().parents[1]
DECISION = (
    ROOT / "configs/project_two_experiments/structure_two_task8_joint_redesign_decision_v0_1.json"
)
ARTIFACT = ROOT / "benchmarks/structure_two/structure_two_stateful_full_joint_v0_1.json"


@pytest.fixture(scope="module")
def runtime_dependencies():
    config = load_stateful_full_joint_config(ROOT)
    model = load_neural_proposal_model(config.neural_proposal_model_path)
    return config, model


def _observation(*, owner: float = 0.62, location_ids=None) -> FullJointObservation:
    locations = location_ids or (uuid4(), uuid4(), uuid4())
    return FullJointObservation(
        source_update_id=uuid4(),
        evidence_cluster_id=uuid4(),
        owner_actor_key="owner",
        actor_posterior={
            "owner": owner,
            "guest": max(0.0, 0.90 - owner),
            "unknown_actor": 0.10,
        },
        mechanism_posterior={
            EventMechanism.DIRECT_RELOCATION: 0.25,
            EventMechanism.HANDOFF_RELOCATION: 0.65,
            EventMechanism.UNKNOWN_MECHANISM: 0.10,
        },
        ordered_role_posterior={
            ordered_role_key("owner", "guest"): 0.35,
            ordered_role_key("guest", "owner"): 0.45,
            ordered_role_key("owner", "unknown_actor"): 0.20,
        },
        identity_target_probability=0.82,
        cause_posterior={
            ParticleChangeCause.OBSERVATION: 0.10,
            ParticleChangeCause.ACTOR: 0.38,
            ParticleChangeCause.IDENTITY: 0.10,
            ParticleChangeCause.HABIT: 0.29,
            ParticleChangeCause.NOISE: 0.08,
            ParticleChangeCause.UNRESOLVED: 0.05,
        },
        regime_change_probability=0.42,
        active_regime="R0",
        observed_location_id=locations[0],
        base_location_distribution={locations[0]: 0.50, locations[1]: 0.30, locations[2]: 0.20},
        known_location_ids=locations,
        unresolved_probability=0.05,
    )


def _runtime(arm: FullJointArm, dependencies) -> StatefulFullJointRuntime:
    config, model = dependencies
    return StatefulFullJointRuntime(arm=arm, config=config, neural_model=model)


def test_project_owner_selected_route_c_without_narrowing_scope() -> None:
    decision = json.loads(DECISION.read_text(encoding="utf-8"))

    assert decision["status"] == "PROJECT_OWNER_SELECTED"
    assert decision["selected_option"] == "C_stateful_joint_inference"
    assert decision["scope_policy"] == {
        "unified_seven_operator_framework_retained": True,
        "hidden_event_inference_retained": True,
        "multi_actor_reasoning_retained": True,
        "open_world_unknowns_retained": True,
        "reversible_attribution_retained": True,
        "embodied_feedback_loop_retained": True,
    }


def test_route_c_particles_carry_all_seven_axes_across_time(runtime_dependencies) -> None:
    runtime = _runtime(FullJointArm.STATEFUL_FULL_JOINT, runtime_dependencies)
    first = _observation()
    second = replace(
        first,
        source_update_id=uuid4(),
        evidence_cluster_id=uuid4(),
        observed_location_id=first.known_location_ids[1],
        regime_change_probability=0.75,
    )

    runtime.revise(first)
    runtime.revise(second)
    runtime.verify_internal_contracts()

    assert len(runtime.particles) == runtime.config.particle_budget
    assert runtime.unresolved_probability == pytest.approx(runtime.config.unresolved_prior)
    for particle in runtime.particles:
        world = particle.world
        assert len(world.event_chain) == 2
        assert len(world.ordered_actor_role_history) == 2
        assert len(world.instance_association_history) == 2
        assert len(world.change_cause_history) == 2
        assert len(world.habit_regime_history) == 2
        assert len(world.run_length_history) == 2
        assert len(world.revision_lineage) == 2
        assert world.typed_state.statistic_state_ref.startswith("full-rb:")


def test_joint_and_factorized_arms_are_compute_matched_but_not_the_same_model(
    runtime_dependencies,
) -> None:
    observation = _observation()
    joint = _runtime(FullJointArm.STATEFUL_FULL_JOINT, runtime_dependencies)
    factorized = _runtime(FullJointArm.MATCHED_FULL_STATE_FACTORIZED, runtime_dependencies)

    joint.revise(observation)
    factorized.revise(observation)
    joint_budget = joint.fairness_receipts[-1]
    factorized_budget = factorized.fairness_receipts[-1]

    assert joint_budget.complete_state_axes == COMPLETE_STATE_AXES
    assert replace(joint_budget, arm=factorized_budget.arm) == factorized_budget
    joint_mass = {
        particle.world.signature: particle.posterior_probability for particle in joint.particles
    }
    factorized_mass = {
        particle.world.signature: particle.posterior_probability
        for particle in factorized.particles
    }
    assert joint_mass.keys() == factorized_mass.keys()
    assert any(abs(joint_mass[key] - factorized_mass[key]) > 1e-8 for key in joint_mass)


def test_low_owner_unknown_event_cannot_enter_joint_rgrc(runtime_dependencies) -> None:
    runtime = _runtime(FullJointArm.STATEFUL_FULL_JOINT, runtime_dependencies)
    first = _observation(owner=0.05)
    first = replace(
        first,
        actor_posterior={"owner": 0.05, "guest": 0.10, "unknown_actor": 0.85},
    )
    second = replace(
        first,
        source_update_id=uuid4(),
        evidence_cluster_id=uuid4(),
        observed_location_id=first.known_location_ids[2],
    )

    runtime.revise(first)
    runtime.revise(second)

    assert not any(
        record.operation in {"promote", "corrected_revision"}
        for record in runtime.rgrc_ledger.records
    )


def test_feedback_reweights_full_state_and_extends_revision_lineage(runtime_dependencies) -> None:
    runtime = _runtime(FullJointArm.STATEFUL_FULL_JOINT, runtime_dependencies)
    observation = _observation()
    runtime.revise(observation)
    before_lengths = [len(particle.world.revision_lineage) for particle in runtime.particles]
    feedback = SimpleNamespace(
        feedback_record_id=uuid4(),
        superseded_revision_id=observation.source_update_id,
        corrected_revision_id=uuid4(),
        actor_posterior_after=(
            SimpleNamespace(key="owner", probability=0.12),
            SimpleNamespace(key="guest", probability=0.78),
            SimpleNamespace(key="unknown_actor", probability=0.10),
        ),
        mechanism_posterior_after=(
            SimpleNamespace(key=EventMechanism.DIRECT_RELOCATION.value, probability=0.10),
            SimpleNamespace(key=EventMechanism.HANDOFF_RELOCATION.value, probability=0.80),
            SimpleNamespace(key=EventMechanism.UNKNOWN_MECHANISM.value, probability=0.10),
        ),
        role_posterior_after=tuple(
            SimpleNamespace(key=key, probability=value)
            for key, value in observation.ordered_role_posterior.items()
        ),
    )

    runtime.apply_feedback(feedback)
    runtime.verify_internal_contracts()

    assert all(
        len(particle.world.revision_lineage) == before + 1
        for particle, before in zip(runtime.particles, before_lengths, strict=True)
    )
    assert any(
        receipt.operator is StructureTwoOperator.ORRER_CHEH and receipt.executed
        for receipt in runtime.operator_flow_receipts
    )


def test_full_d0_episode_executes_all_seven_operators_in_one_closed_loop() -> None:
    dataset = D0SyntheticOracleReplayAdapter(
        validation_seeds=(701,),
        test_seeds=(709,),
        max_steps_per_episode=10,
        dataset_version="route-c-integration-test@0.1",
        scenario_duration_days=10,
        guest_window=(2, 3),
        abrupt_day=5,
        recurrence_day=8,
        unknown_event_days=(1,),
    ).build()
    episode = dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)[0]

    metric, runtime = evaluate_stateful_full_joint_episode(
        repository_root=ROOT,
        dataset=dataset,
        episode=episode,
        arm=FullJointArm.STATEFUL_FULL_JOINT,
    )

    assert metric.step_count == len(episode.steps)
    assert metric.owner_habit_contamination == 0.0
    assert {
        receipt.operator for receipt in runtime.operator_flow_receipts if receipt.executed
    } == set(StructureTwoOperator)
    assert runtime.fairness_receipts
    assert all(
        receipt.proposal_support_policy == "enumerate_all_positive_support"
        and receipt.target_score_evaluations == runtime.config.particle_budget
        and receipt.score_operations
        == receipt.target_score_evaluations * receipt.score_operations_per_candidate
        for receipt in runtime.fairness_receipts
    )


def test_checked_in_route_c_artifact_is_honest_and_verifiable() -> None:
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))

    verify_stateful_full_joint_result(artifact, repository_root=ROOT)
    assert artifact["route_c_replay_feedback_loop_executable"] is True
    assert (
        artifact["feedback_loop_semantics"]["environment_trajectory_responds_to_route_action"]
        is False
    )
    assert artifact["implementation_complete_for_paper"] is False
    assert artifact["scientific_superiority_established"] is False
    assert artifact["joint_causal_utilization_diagnostic"]["positive_action_posterior_tv_steps"] > 0


def test_rehashed_forged_scientific_pass_is_rejected() -> None:
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    forged = copy.deepcopy(artifact)
    forged["scientific_superiority_established"] = True
    forged.pop("content_sha256")
    from cpswm.system.reproducibility import content_sha256

    forged["content_sha256"] = content_sha256(forged)
    with pytest.raises(ValueError, match="cannot claim scientific superiority"):
        verify_stateful_full_joint_result(forged)
