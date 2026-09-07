from __future__ import annotations

from dataclasses import replace

import pytest

from cpswm.system.evaluation_operations import structure_two_task7_support_recovery as task7
from cpswm.system.evaluation_operations.structure_two_backbone_falsifier import (
    UNRESOLVED_KEY,
    ArmName,
    CostMeter,
    build_scenario,
)
from cpswm.system.evaluation_operations.structure_two_task7_support_recovery import (
    Task7SupportRecoveryArm,
    run_task7_support_recovery_arm,
    run_task7_support_recovery_five_arm_study,
)
from cpswm.system.reproducibility import content_sha256


@pytest.fixture(scope="module")
def scenario():
    return build_scenario(
        gaps=5,
        seed=307,
        high_attribution_ambiguity=True,
        adverse_delayed_feedback=True,
        open_world_actor=True,
        short_regime=True,
        corrupt_index=1,
    )


def test_all_five_task7_arms_execute_and_normalize(scenario) -> None:
    results = {
        arm: run_task7_support_recovery_arm(
            scenario,
            recovery_arm=arm,
            correction_index=1,
            budget=32,
            seed=419,
            v04_window_length=2,
            v04_sweeps=1,
        )
        for arm in Task7SupportRecoveryArm
    }

    assert set(results) == set(Task7SupportRecoveryArm)
    for result in results.values():
        assert sum(result.posterior.values()) == pytest.approx(1.0)
        assert UNRESOLVED_KEY in result.posterior
    assert (
        results[Task7SupportRecoveryArm.RESERVOIR_ONLY].cost["repair_mode"]
        == "pre_correction_reservoir_boundary_replay"
    )
    assert (
        results[Task7SupportRecoveryArm.BACKWARD_MESSAGE_ONLY].cost["repair_mode"]
        == "surviving_support_conditional_backward_message"
    )
    combined = results[Task7SupportRecoveryArm.COMBINED]
    assert combined.cost["repair_mode"] == "reservoir_plus_conditional_backward_message"
    assert combined.cost["reservoir_unique_prefix_count"] > 0
    assert combined.cost["backward_message_unique_descendant_count"] > 0
    assert combined.cost["backward_message_checkpoint_sha256"]


def test_five_arm_report_keeps_every_attribution_arm() -> None:
    report = run_task7_support_recovery_five_arm_study(
        scenario_seeds=(307,),
        replicate_seeds=(419,),
        gaps=4,
        correction_index=1,
        budget=16,
        v04_window_length=2,
        v04_sweeps=1,
    )

    expected = {arm.value for arm in Task7SupportRecoveryArm}
    assert set(report["required_arms"]) == expected
    assert set(report["summaries"]) == expected
    assert len(report["rows"]) == 16 * len(expected)
    assert all(summary["row_count"] == 16 for summary in report["summaries"].values())


def test_backward_only_executes_conditional_message_path(monkeypatch, scenario) -> None:
    calls = 0
    original = task7._apply_backward_messages

    def audited_apply(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(task7, "_apply_backward_messages", audited_apply)
    result = run_task7_support_recovery_arm(
        scenario,
        recovery_arm=Task7SupportRecoveryArm.BACKWARD_MESSAGE_ONLY,
        correction_index=1,
        budget=16,
        seed=419,
    )

    assert calls == 1
    assert result.cost["backward_message_descendant_count"] > 0


def test_backward_checkpoint_rejects_stale_prefix_stream(scenario) -> None:
    (
        _final_particles,
        _final_evidence,
        _rng,
        _meter,
        reservoir,
        _prefix_evidence,
    ) = task7._capture_forward_reservoir(
        scenario,
        correction_index=1,
        arm=ArmName.ADAPTIVE_TYPED_RBPF,
        budget=8,
        seed=419,
    )
    checkpoint, _ = task7._build_backward_checkpoint(
        reservoir,
        scenario=scenario,
        correction_index=1,
        arm=ArmName.ADAPTIVE_TYPED_RBPF,
        seed=419,
    )
    changed_first = replace(
        scenario.observations[0],
        placement_value=scenario.observations[0].placement_value + 0.125,
    )
    stale_scenario = replace(
        scenario,
        observations=(changed_first, *scenario.observations[1:]),
    )
    repair_meter = CostMeter(arm=ArmName.ADAPTIVE_TYPED_RBPF, particle_count=8)
    repair_meter.start()

    with pytest.raises(ValueError, match="prefix binding is stale"):
        task7._apply_backward_messages(
            checkpoint,
            scenario=stale_scenario,
            corrected=stale_scenario.observations,
            meter=repair_meter,
        )


def test_reservoir_rejects_forged_rng_state_even_with_rehashed_outer_payload(scenario) -> None:
    *_, reservoir, _prefix_evidence = task7._capture_forward_reservoir(
        scenario,
        correction_index=1,
        arm=ArmName.ADAPTIVE_TYPED_RBPF,
        budget=8,
        seed=419,
    )
    forged_rng_state = (reservoir.rng_state[0], (), None)
    forged_rng_hash = content_sha256(forged_rng_state)
    forged = replace(
        reservoir,
        rng_state=forged_rng_state,
        rng_state_sha256=forged_rng_hash,
        reservoir_sha256=content_sha256(
            {
                "particles": [
                    task7._particle_payload(particle) for particle in reservoir.particles
                ],
                "rng_state_sha256": forged_rng_hash,
            }
        ),
    )

    # Rehashing the self-consistency fields is insufficient: the forged RNG
    # state is not a valid Python random checkpoint and cannot drive replay.
    with pytest.raises((TypeError, ValueError)):
        task7._build_backward_checkpoint(
            forged,
            scenario=scenario,
            correction_index=1,
            arm=ArmName.ADAPTIVE_TYPED_RBPF,
            seed=419,
        )
