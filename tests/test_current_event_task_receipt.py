from __future__ import annotations

import pytest
from run_current_event import build, dataset_for

from cpswm.contracts import ProjectTwoDatasetSplit
from cpswm.system.evaluation_operations.structure_two_stateful_full_joint import FullJointArm


@pytest.mark.parametrize("arm", list(FullJointArm))
def test_paid_search_matches_task_receipt_and_final_action(arm):
    dataset = dataset_for("sparse32", [66001])
    episode = dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)[0]
    state = build(dataset, episode, arm)
    for step in episode.steps[:6]:
        state.observe(step)
        prediction = state.predict()
        receipt = state.task_readout_receipts[-1]
        assert receipt.search_order == prediction.search_order
        assert (
            list(map(str, receipt.search_order))
            == state.event_actions[-1]["search"]["planned_order"]
        )
        assert receipt.put_back == prediction.put_back
        state.feedback(step)
