"""Fresh-seed development protocol for the dual-timescale readout."""

from __future__ import annotations

import pytest

from cpswm.system.evaluation_operations.project_two_dual_timescale_development import (
    READOUT_SEARCH_SPACE,
    ActorEvidenceStress,
    DualTimescaleArm,
    run_dual_timescale_development,
)


def test_every_arm_has_the_same_registered_tuning_budget() -> None:
    assert set(READOUT_SEARCH_SPACE) == set(DualTimescaleArm)
    assert {len(space) for space in READOUT_SEARCH_SPACE.values()} == {3}


def test_development_validation_and_holdout_must_be_disjoint() -> None:
    with pytest.raises(ValueError, match="must be disjoint"):
        run_dual_timescale_development(
            validation_seeds=(12000,),
            holdout_seeds=(12000,),
            max_steps=4,
        )


def test_fresh_seed_smoke_report_keeps_every_stress_cell_and_arm_explicit() -> None:
    report = run_dual_timescale_development(
        validation_seeds=(12000,),
        holdout_seeds=(13000,),
        max_steps=4,
    )
    assert report["evidence_status"] == "post-diagnostic development; not confirmatory"
    assert report["same_visible_stream_and_action_evaluator"] is True
    assert report["search_budget_per_arm_per_cell"] == 3
    assert set(report["cells"]) == {stress.value for stress in ActorEvidenceStress}
    for cell in report["cells"].values():
        assert set(cell["selected_parameters"]) == {arm.value for arm in DualTimescaleArm}
        assert set(cell["holdout_results"]) == {arm.value for arm in DualTimescaleArm}


def test_registered_stress_mask_is_stable_across_fresh_sealed_uuid_secrets() -> None:
    from cpswm.contracts import ProjectTwoDatasetSplit
    from cpswm.system.evaluation_operations.project_two_dataset_adapters import (
        D0SyntheticOracleReplayAdapter,
    )
    from cpswm.system.evaluation_operations.project_two_dual_timescale_development import (
        _stress_transform,
    )

    def mask() -> tuple[bool, ...]:
        dataset = D0SyntheticOracleReplayAdapter(
            validation_seeds=(12000,),
            test_seeds=(13000,),
            max_steps_per_episode=12,
        ).build()
        episode = dataset.visible_episodes(ProjectTwoDatasetSplit.TEST)[0]
        transform = _stress_transform(
            ActorEvidenceStress.SYMMETRIC_MISATTRIBUTION,
            owner_key=episode.owner_actor_key,
            stress_namespace=episode.scene_id,
        )
        return tuple(
            transform(step).actor_evidence.actor_posterior != step.actor_evidence.actor_posterior
            for step in episode.steps
            if step.actor_evidence is not None
        )

    assert mask() == mask()
