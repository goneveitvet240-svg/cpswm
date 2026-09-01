"""AMG action-interface fairness audit contract."""

from __future__ import annotations

import pytest

from cpswm.system.evaluation_operations.project_two_amg_interface_audit import (
    SEARCH_SPACE,
    AMGInterfaceAuditArm,
    run_amg_action_interface_audit,
)


def test_every_audit_arm_has_equal_tuning_budget() -> None:
    assert set(SEARCH_SPACE) == set(AMGInterfaceAuditArm)
    assert {len(space) for space in SEARCH_SPACE.values()} == {3}


def test_audit_splits_must_be_disjoint() -> None:
    with pytest.raises(ValueError, match="must be disjoint"):
        run_amg_action_interface_audit(
            validation_seeds=(19000,),
            holdout_seeds=(19000,),
            max_steps=4,
        )


def test_audit_smoke_exposes_interface_and_target_checks() -> None:
    report = run_amg_action_interface_audit(
        validation_seeds=(19000,),
        holdout_seeds=(20000,),
        max_steps=4,
    )
    assert report["same_visible_stream"] is True
    assert report["same_put_back_location_set"] is True
    assert report["search_budget_per_arm_per_cell"] == 3
    assert set(report["cells"]) == {
        "clean",
        "ambiguous",
        "symmetric_misattribution",
    }
    for cell in report["cells"].values():
        assert set(cell["holdout_results"]) == {arm.value for arm in AMGInterfaceAuditArm}


def test_audit_stress_mask_is_stable_across_fresh_sealed_uuid_secrets() -> None:
    from cpswm.contracts import ProjectTwoDatasetSplit
    from cpswm.system.evaluation_operations.project_two_amg_interface_audit import (
        _audit_stress_transform,
    )
    from cpswm.system.evaluation_operations.project_two_dataset_adapters import (
        D0SyntheticOracleReplayAdapter,
    )
    from cpswm.system.evaluation_operations.project_two_dual_timescale_development import (
        ActorEvidenceStress,
    )

    def mask() -> tuple[bool, ...]:
        dataset = D0SyntheticOracleReplayAdapter(
            validation_seeds=(19000,),
            test_seeds=(20000,),
            max_steps_per_episode=12,
        ).build()
        episode = dataset.visible_episodes(ProjectTwoDatasetSplit.TEST)[0]
        transform = _audit_stress_transform(
            episode,
            ActorEvidenceStress.SYMMETRIC_MISATTRIBUTION,
        )
        return tuple(
            transform(step).actor_evidence.actor_posterior != step.actor_evidence.actor_posterior
            for step in episode.steps
            if step.actor_evidence is not None
        )

    assert mask() == mask()
