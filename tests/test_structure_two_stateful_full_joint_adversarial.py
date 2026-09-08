from __future__ import annotations

import copy
import importlib.util
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from cpswm.contracts import EventMechanism, ProjectTwoDatasetSplit
from cpswm.system.evaluation_operations.project_two_dataset_adapters import (
    D0SyntheticOracleReplayAdapter,
)
from cpswm.system.evaluation_operations.structure_two_selected_method import (
    ParticleChangeCause,
)
from cpswm.system.evaluation_operations.structure_two_stateful_full_joint import (
    FullJointArm,
    FullJointObservation,
    RBCellState,
    ReversibleJointRGRCLedger,
    StatefulFullJointRuntime,
    StatefulJointParticle,
    _deterministic_result_payload,
    _fairness_comparison_payload,
    build_stateful_full_joint_state,
    load_neural_proposal_model,
    load_stateful_full_joint_config,
    verify_stateful_full_joint_result,
)
from cpswm.system.reproducibility import content_sha256

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "benchmarks/structure_two/structure_two_stateful_full_joint_v0_1.json"
RUNNER = ROOT / "apps/evaluation_runner/run_structure_two_stateful_full_joint.py"


@pytest.fixture(scope="module")
def dependencies():
    config = load_stateful_full_joint_config(ROOT)
    return config, load_neural_proposal_model(config.neural_proposal_model_path)


def _runtime(arm: FullJointArm, dependencies) -> StatefulFullJointRuntime:
    config, model = dependencies
    return StatefulFullJointRuntime(arm=arm, config=config, neural_model=model)


def _observation(*, source_update_id=None) -> FullJointObservation:
    locations = (uuid4(), uuid4(), uuid4())
    return FullJointObservation(
        source_update_id=source_update_id or uuid4(),
        evidence_cluster_id=uuid4(),
        owner_actor_key="owner",
        actor_posterior={"owner": 0.62, "guest": 0.28, "unknown_actor": 0.10},
        mechanism_posterior={
            EventMechanism.DIRECT_RELOCATION: 0.25,
            EventMechanism.HANDOFF_RELOCATION: 0.65,
            EventMechanism.UNKNOWN_MECHANISM: 0.10,
        },
        ordered_role_posterior={
            "owner=>guest": 0.35,
            "guest=>owner": 0.45,
            "owner=>unknown_actor": 0.20,
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


def _feedback(observation: FullJointObservation, *, record_id=None, corrected_id=None):
    return SimpleNamespace(
        feedback_record_id=record_id or uuid4(),
        superseded_revision_id=observation.source_update_id,
        corrected_revision_id=corrected_id or uuid4(),
        actor_posterior_after=tuple(
            SimpleNamespace(key=key, probability=value)
            for key, value in observation.actor_posterior.items()
        ),
        mechanism_posterior_after=tuple(
            SimpleNamespace(key=key.value, probability=value)
            for key, value in observation.mechanism_posterior.items()
        ),
        role_posterior_after=tuple(
            SimpleNamespace(key=key, probability=value)
            for key, value in observation.ordered_role_posterior.items()
        ),
    )


def _resign(payload: dict[str, object]) -> None:
    payload.pop("content_sha256", None)
    payload.pop("deterministic_replay_sha256", None)
    payload["deterministic_replay_sha256"] = content_sha256(_deterministic_result_payload(payload))
    payload["content_sha256"] = content_sha256(payload)


def _runtime_state(runtime: StatefulFullJointRuntime) -> tuple[object, ...]:
    return (
        runtime._state_sha256(),
        runtime.step_index,
        runtime.particles,
        runtime.unresolved_probability,
        tuple(runtime.operator_flow_receipts),
        tuple(runtime.fairness_receipts),
        tuple(runtime.revision_batches),
        tuple(runtime.importance_revision_receipts),
        tuple(tuple(sorted(row.items())) for row in runtime.action_readout_traces),
        tuple(runtime.rgrc_ledger.records),
        runtime.rgrc_ledger.active_source_revision_id,
        runtime.rgrc_ledger.active_distribution,
        frozenset(runtime._consumed_updates),
        frozenset(runtime._consumed_feedback_revisions),
        frozenset(runtime._consumed_feedback_records),
        runtime._last_observation,
        runtime._last_operator_receipt_sha256,
    )


def test_round_one_complete_positive_support_is_not_top_k_truncated(dependencies) -> None:
    runtime = _runtime(FullJointArm.STATEFUL_FULL_JOINT, dependencies)
    support = runtime._candidates(_observation(), None)

    assert len(support) == 351
    assert sum(probability for _, probability in support) == pytest.approx(1.0)
    assert all(probability > 0.0 for _, probability in support)
    assert {candidate.mechanism for candidate, _ in support} == set(EventMechanism)
    assert {candidate.change_cause for candidate, _ in support} == set(ParticleChangeCause)


def test_round_one_matched_arms_keep_pre_treatment_fairness_after_feedback() -> None:
    dataset = D0SyntheticOracleReplayAdapter(
        validation_seeds=(701,),
        test_seeds=(709,),
        max_steps_per_episode=5,
        dataset_version="route-c-adversarial-fairness@0.1",
        scenario_duration_days=10,
        guest_window=(2, 3),
        abrupt_day=5,
        recurrence_day=8,
        unknown_event_days=(1,),
    ).build()
    episode = dataset.visible_episodes(ProjectTwoDatasetSplit.TEST)[0]
    joint = build_stateful_full_joint_state(
        repository_root=ROOT,
        dataset=dataset,
        episode=episode,
        arm=FullJointArm.STATEFUL_FULL_JOINT,
    )
    factorized = build_stateful_full_joint_state(
        repository_root=ROOT,
        dataset=dataset,
        episode=episode,
        arm=FullJointArm.MATCHED_FULL_STATE_FACTORIZED,
    )

    for index, step in enumerate(episode.steps):
        for state in (joint, factorized):
            state.observe(step)
        if joint.runtime.fairness_receipts:
            assert _fairness_comparison_payload(joint.runtime.fairness_receipts[-1]) == (
                _fairness_comparison_payload(factorized.runtime.fairness_receipts[-1])
            )
        for state in (joint, factorized):
            prediction = state.predict()
            state.bind_prediction_trace(prediction, index)
            state.feedback(step)


@pytest.mark.parametrize(
    "field,value,error",
    [
        ("actor_posterior", {"owner": float("nan"), "guest": 0.9, "unknown_actor": 0.1}, "finite"),
        ("known_location_ids", (), "cannot be empty"),
        ("active_regime", "", "non-empty"),
    ],
)
def test_round_one_invalid_observation_is_rejected(field, value, error) -> None:
    with pytest.raises(ValueError, match=error):
        replace(_observation(), **{field: value})


def test_round_one_mutated_observation_is_revalidated_at_use_boundary(dependencies) -> None:
    runtime = _runtime(FullJointArm.STATEFUL_FULL_JOINT, dependencies)
    actor_posterior = {"owner": 0.62, "guest": 0.28, "unknown_actor": 0.10}
    observation = replace(_observation(), actor_posterior=actor_posterior)
    actor_posterior["owner"] = float("nan")

    with pytest.raises(ValueError, match="finite"):
        runtime.revise(observation)
    assert runtime.step_index == 0
    assert not runtime.operator_flow_receipts


def test_round_one_revision_failure_rolls_back_all_mutable_state(dependencies, monkeypatch) -> None:
    runtime = _runtime(FullJointArm.STATEFUL_FULL_JOINT, dependencies)
    observation = _observation()
    before = _runtime_state(runtime)

    def fail_candidates(*_args, **_kwargs):
        raise RuntimeError("injected proposal failure")

    original = runtime._candidates
    monkeypatch.setattr(runtime, "_candidates", fail_candidates)
    with pytest.raises(RuntimeError, match="injected proposal failure"):
        runtime.revise(observation)
    assert _runtime_state(runtime) == before

    monkeypatch.setattr(runtime, "_candidates", original)
    runtime.revise(observation)
    runtime.verify_internal_contracts()


def test_round_one_feedback_replay_and_substitution_are_rejected_atomically(
    dependencies,
) -> None:
    runtime = _runtime(FullJointArm.STATEFUL_FULL_JOINT, dependencies)
    observation = _observation()
    runtime.revise(observation)
    record_id = uuid4()
    runtime.apply_feedback(_feedback(observation, record_id=record_id))
    before = _runtime_state(runtime)

    with pytest.raises(ValueError, match="record was already consumed"):
        runtime.apply_feedback(_feedback(observation, record_id=record_id, corrected_id=uuid4()))
    assert _runtime_state(runtime) == before

    duplicate = _feedback(observation)
    duplicate.actor_posterior_after = (
        *duplicate.actor_posterior_after,
        duplicate.actor_posterior_after[0],
    )
    with pytest.raises(ValueError, match="duplicate keys"):
        runtime.apply_feedback(duplicate)
    assert _runtime_state(runtime) == before

    forged_target = replace(observation, source_update_id=uuid4())
    with pytest.raises(ValueError, match="does not target an admitted"):
        runtime.apply_feedback(_feedback(forged_target))
    assert _runtime_state(runtime) == before


def test_round_one_rgrc_requires_consecutive_stability_and_retracts_old_subject(
    dependencies,
) -> None:
    runtime = _runtime(FullJointArm.STATEFUL_FULL_JOINT, dependencies)
    observation = _observation()
    runtime.revise(observation)
    target = max(
        (
            particle
            for particle in runtime.particles
            if particle.world.placement_actor == "owner"
            and particle.world.instance_association_history[-1] == "target_instance"
        ),
        key=lambda particle: particle.posterior_probability,
    )
    typed = target.world.typed_state.model_copy(update={"run_length": 9})
    stable_world = replace(
        target.world,
        typed_state=typed,
        run_length_history=(*target.world.run_length_history[:-1], 9),
    )
    stable_world.validate_complete()
    stable = StatefulJointParticle(world=stable_world, posterior_probability=0.95)
    distribution = runtime.action_distribution()
    ledger = ReversibleJointRGRCLedger(admission_floor=0.5, stability_steps=2)

    ledger.consider((stable,), owner_key="owner", action_distribution=distribution)
    assert not any(record.operation == "promote" for record in ledger.records)
    forged_ledger = copy.deepcopy(ledger)
    forged_record = replace(forged_ledger.records[0], operation="promote")
    forged_payload = {
        "operation": forged_record.operation,
        "source_revision_id": str(forged_record.source_revision_id),
        "particle_revision_id": str(forged_record.particle_revision_id),
        "owner_target_mass": forged_record.owner_target_mass,
        "action_distribution": sorted(
            (str(key), value) for key, value in forged_record.action_distribution.items()
        ),
        "previous_hash": forged_record.previous_hash,
    }
    forged_ledger.records[0] = replace(forged_record, record_hash=content_sha256(forged_payload))
    with pytest.raises(ValueError, match="promote is unreachable"):
        forged_ledger.verify_chain()

    ledger.consider((stable,), owner_key="owner", action_distribution=distribution)
    assert ledger.active_source_revision_id == stable.world.source_revision_id

    old_source = stable.world.source_revision_id
    new_source = uuid4()
    replacement_particle = replace(
        stable,
        world=replace(stable.world, source_revision_id=new_source),
    )
    ledger.consider((replacement_particle,), owner_key="owner", action_distribution=distribution)
    ledger.consider((replacement_particle,), owner_key="owner", action_distribution=distribution)
    ledger.verify_chain()
    retract = next(record for record in reversed(ledger.records) if record.operation == "retract")
    assert retract.source_revision_id == old_source
    assert ledger.active_source_revision_id == new_source


def test_round_one_all_three_rb_blocks_change_decision_readout() -> None:
    locations = (uuid4(), uuid4())
    base = {locations[0]: 0.5, locations[1]: 0.5}
    original = RBCellState(
        location_alpha=(5.0, 1.0),
        ridge_precision=(2.0, 5.0),
        ridge_natural=(1.0, 4.0),
        information_precision=4.0,
        information_natural=2.0,
        observation_count=3,
    )
    ridge_changed = replace(original, ridge_natural=(4.0, 1.0))
    information_changed = replace(original, information_natural=3.5)

    baseline = original.combined_location_distribution(locations, base)
    assert ridge_changed.combined_location_distribution(locations, base) != baseline
    assert information_changed.combined_location_distribution(locations, base) != baseline


def test_round_one_operator_chain_tampering_is_detected(dependencies) -> None:
    runtime = _runtime(FullJointArm.STATEFUL_FULL_JOINT, dependencies)
    runtime.revise(_observation())
    runtime.operator_flow_receipts[0] = replace(
        runtime.operator_flow_receipts[0], executed=False, changed_state=True
    )
    with pytest.raises(ValueError, match="without execution"):
        runtime.verify_internal_contracts()


def test_round_two_embedded_receipt_forgery_is_rejected() -> None:
    forged = copy.deepcopy(json.loads(ARTIFACT.read_text(encoding="utf-8")))
    receipt = forged["runtime_audit_traces"]["stateful_full_joint"][0]["operator_flow_receipts"][0]
    receipt["detail"] = "forged but top-level rehashed"
    _resign(forged)

    with pytest.raises(ValueError, match="receipt content hash mismatch"):
        verify_stateful_full_joint_result(forged, repository_root=ROOT)


def test_round_two_paired_action_deletion_is_rejected_even_when_rehashed() -> None:
    forged = copy.deepcopy(json.loads(ARTIFACT.read_text(encoding="utf-8")))
    forged["paired_action_readouts"].pop()
    _resign(forged)

    with pytest.raises(ValueError, match="paired actions are not bound"):
        verify_stateful_full_joint_result(forged, repository_root=ROOT)


def test_round_two_claim_boundary_and_source_substitution_are_rejected() -> None:
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    weakened = copy.deepcopy(artifact)
    weakened["next_gate"] = "paper_ready"
    _resign(weakened)
    with pytest.raises(ValueError, match="next scientific gate was weakened"):
        verify_stateful_full_joint_result(weakened, repository_root=ROOT)

    substituted = copy.deepcopy(artifact)
    substituted["source_binding"]["implementation"]["path"] = substituted["source_binding"][
        "config"
    ]["path"]
    substituted["source_binding"]["implementation"]["sha256"] = substituted["source_binding"][
        "config"
    ]["sha256"]
    _resign(substituted)
    with pytest.raises(ValueError, match="source path substitution"):
        verify_stateful_full_joint_result(substituted, repository_root=ROOT)


def test_round_two_config_rejects_extra_or_promoted_claims(tmp_path) -> None:
    source = ROOT / "configs/project_two_experiments/structure_two_stateful_full_joint_v0_1.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["paper_ready"] = True
    config_path = tmp_path / "forged-route-c-config.json"
    config_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="schema drift or extra claim field"):
        load_stateful_full_joint_config(ROOT, config_path)


def test_round_two_fresh_replay_detects_forged_but_self_consistent_provenance() -> None:
    forged = copy.deepcopy(json.loads(ARTIFACT.read_text(encoding="utf-8")))
    for arm in FullJointArm:
        forged["runtime_audit_traces"][arm.value][0]["fairness_receipts"][0][
            "proposal_support_sha256"
        ] = "0" * 64
    _resign(forged)

    verify_stateful_full_joint_result(forged, repository_root=ROOT, fresh_replay=False)
    with pytest.raises(ValueError, match="fresh-source replay disagrees"):
        verify_stateful_full_joint_result(forged, repository_root=ROOT, fresh_replay=True)


def test_round_two_strict_json_rejects_duplicate_keys_and_nan() -> None:
    spec = importlib.util.spec_from_file_location("route_c_runner", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    with pytest.raises(ValueError, match="duplicate JSON key"):
        json.loads(
            '{"claim": false, "claim": true}', object_pairs_hook=module._reject_duplicate_keys
        )
    with pytest.raises(ValueError, match="non-standard JSON numeric constant"):
        json.loads('{"metric": NaN}', parse_constant=module._reject_nonstandard_constant)
