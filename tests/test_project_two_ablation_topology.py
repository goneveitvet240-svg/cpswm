from __future__ import annotations

import pytest

from cpswm.system.evaluation_operations.project_two_ablation import (
    REQUIRED_PROJECT_TWO_ABLATIONS,
    ProjectTwoAblation,
    ProjectTwoAblationProtocol,
)
from cpswm.system.evaluation_operations.project_two_tuning import (
    ProjectTwoExperimentalTrack,
    ProjectTwoFairTuner,
    ProjectTwoTuningCandidate,
    SealedHeldOutRunGuard,
)


def test_every_required_ablation_cuts_its_declared_topology_edge():
    protocol = ProjectTwoAblationProtocol()
    assert set(protocol.ablations) == set(REQUIRED_PROJECT_TWO_ABLATIONS)
    for ablation in protocol.ablations:
        topology = protocol.topology_for(ablation)
        assert topology != protocol.full_topology
        assert protocol.verify_cut(ablation, topology)


def test_each_arm_is_independently_tuned_with_equal_budget_and_receipt():
    arms = tuple(track.value for track in ProjectTwoExperimentalTrack) + tuple(
        item.value for item in REQUIRED_PROJECT_TWO_ABLATIONS
    )
    candidates = tuple(ProjectTwoTuningCandidate.pilot(index) for index in range(3))
    tuner = ProjectTwoFairTuner(search_budget=3)
    receipts = tuner.tune_all(
        arm_ids=arms,
        candidates=candidates,
        validation_episode_ids=("validation-101", "validation-103"),
        evaluator=lambda arm, candidate: (candidate.index, arm),
    )
    assert {item.arm_id for item in receipts} == set(arms)
    assert len({item.receipt_id for item in receipts}) == len(arms)
    assert {item.search_budget for item in receipts} == {3}
    assert all(not item.held_out_episode_ids_seen for item in receipts)


def test_held_out_can_run_only_once_after_tuning_and_ablation_list_freeze():
    candidates = (ProjectTwoTuningCandidate.pilot(0),)
    tuner = ProjectTwoFairTuner(search_budget=1)
    arms = tuple(track.value for track in ProjectTwoExperimentalTrack) + tuple(
        item.value for item in REQUIRED_PROJECT_TWO_ABLATIONS
    )
    receipts = tuner.tune_all(
        arm_ids=arms,
        candidates=candidates,
        validation_episode_ids=("validation-101",),
        evaluator=lambda _arm, candidate: (candidate.index,),
    )
    guard = SealedHeldOutRunGuard.freeze(
        receipts=receipts,
        arm_ids=arms,
        ablations=REQUIRED_PROJECT_TWO_ABLATIONS,
    )
    guard.open_once(("test-211", "test-223"))
    with pytest.raises(RuntimeError, match="exactly once"):
        guard.open_once(("test-211", "test-223"))


def test_target_module_is_not_accidentally_left_connected():
    protocol = ProjectTwoAblationProtocol()
    assert not protocol.topology_for(ProjectTwoAblation.NO_PCHMP_JOINT_PROPAGATION).pchmp_joint
    assert (
        protocol.topology_for(ProjectTwoAblation.ORRER_IN_PLACE_OVERWRITE).orrer_mode == "in_place"
    )
    assert not protocol.topology_for(
        ProjectTwoAblation.NO_PROJECT_ONE_RETRACT_CORRECT
    ).project_one_revision
    assert not protocol.topology_for(ProjectTwoAblation.NO_PROVENANCE_FIREWALL).provenance_firewall
