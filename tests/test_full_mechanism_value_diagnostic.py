"""Pin diagnostic boundaries and the actual current readout's dominance."""

from dataclasses import replace

import pytest
from verify_full_mechanism_value import dominance_certificate, evaluate

from cpswm.contracts import ProjectTwoDatasetSplit
from cpswm.system.evaluation_operations.project_two_dataset_adapters import (
    D0SyntheticOracleReplayAdapter,
)
from cpswm.system.prototype_spine import CorePrototypeSpine
from cpswm.system.runtime_readout import current_action_readout


def test_default_readout_cannot_overrule_live_fast_event():
    config = current_action_readout()
    assert dominance_certificate(config)["strict_argmax_dominance"]
    # Use the production mixer and worst possible agreement of both slow heads.
    for fast in range(3):
        for opposing in range(3):
            distribution = CorePrototypeSpine._mix_action_components(
                type("LocationSupport", (), {"locations": (0, 1, 2)})(),
                [
                    (0.7, {k: float(k == fast) for k in range(3)}),
                    (0.2, {k: float(k == opposing) for k in range(3)}),
                    (0.1, {k: float(k == opposing) for k in range(3)}),
                ],
            )
            assert max(distribution, key=distribution.__getitem__) == fast
    for changed in (
        replace(config, unconfirmed_fast_discount=0.1),
        replace(config, pending_correction_discount=0.5),
        replace(config, fast_action_weight=0.2),
    ):
        assert not dominance_certificate(changed)["strict_argmax_dominance"]


@pytest.mark.parametrize("method", ["stateful_full_joint", "matched_full_state_factorized"])
def test_diagnostic_records_real_feedback_and_nonempty_actions(method):
    dataset = D0SyntheticOracleReplayAdapter(
        validation_seeds=(7,),
        test_seeds=(30,),
        max_steps_per_episode=4,
        sealed_secret="mechanism-value-test-only",
    ).build()
    episode = dataset.visible_episodes(ProjectTwoDatasetSplit.TEST)[0]
    result = evaluate(dataset, episode, method)
    assert len(result["actions"]) == result["metric"]["step_count"] == 4
    assert result["metric"]["full_feedback_revision_calls"] > 0
    assert result["runtime_audit"]["fairness_receipts"]
    assert result["particle_count"] > 0
    assert all("true_actor" not in row for row in result["actions"])
