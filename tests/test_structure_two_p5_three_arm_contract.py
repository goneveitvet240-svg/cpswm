from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from cpswm.system.evaluation_operations.structure_two_action_utility_construct_gate import (
    ConstructActionKind,
)
from cpswm.system.evaluation_operations.structure_two_p5_three_arm_contract import (
    MatchedCIAVArmReceipt,
    P5ComparisonArm,
    TypedLocationPosterior,
    verify_exact_three_arm_ciav_match,
)
from cpswm.system.reproducibility import content_sha256


def _posterior() -> TypedLocationPosterior:
    locations = (uuid4(), uuid4())
    return TypedLocationPosterior.seal(
        arm=P5ComparisonArm.DIRECT_P5,
        episode_id=uuid4(),
        step_id=uuid4(),
        target_object_id=uuid4(),
        source_visible_step_sha256=content_sha256("visible"),
        belief_state_sha256=content_sha256("belief"),
        location_support=locations,
        current_location_distribution={locations[0]: 0.8, locations[1]: 0.2},
        owner_habit_location_distribution={locations[0]: 0.1, locations[1]: 0.9},
    )


def test_typed_location_posterior_uses_the_shared_decoder_for_both_tasks() -> None:
    posterior = _posterior()
    readout = posterior.decode(
        step_index=0,
        run_execution_id=uuid4(),
        visible_observation={"observation": "robot-visible-only"},
    )

    assert readout.selected_search_action.kind is ConstructActionKind.SEARCH
    assert readout.put_back_action.kind is ConstructActionKind.PUT_BACK
    assert readout.selected_search_action.location_id != readout.put_back_action.location_id


def test_typed_location_posterior_rejects_missing_or_forged_support() -> None:
    posterior = _posterior()
    payload = posterior.model_dump(mode="python")
    payload["current_location_distribution"] = payload["current_location_distribution"][:1]
    unsigned = {key: value for key, value in payload.items() if key != "posterior_sha256"}
    payload["posterior_sha256"] = content_sha256(unsigned)

    with pytest.raises(ValidationError, match="exact registered support"):
        TypedLocationPosterior.model_validate(payload)


def _ciav_receipts() -> tuple[MatchedCIAVArmReceipt, ...]:
    episode_id = uuid4()
    step_id = uuid4()
    action_id = uuid4()
    common = {
        "episode_id": episode_id,
        "step_id": step_id,
        "shared_ciav_packet_sha256": content_sha256("packet"),
        "candidate_set_sha256": content_sha256("candidates"),
        "selected_action_id": action_id,
        "realized_observation_sha256": content_sha256("observation"),
        "motion_cost": 0.02,
        "time_cost": 0.04,
        "interruption_cost": 0.01,
        "privacy_cost": 0.02,
        "safety_cost": 0.0,
        "privacy_budget_before": 1.0,
    }
    return tuple(MatchedCIAVArmReceipt.seal(arm=arm, **common) for arm in P5ComparisonArm)


def test_exact_ciav_match_requires_all_three_identical_arm_receipts() -> None:
    verify_exact_three_arm_ciav_match(_ciav_receipts())


def test_exact_ciav_match_rejects_resigned_cost_or_outcome_substitution() -> None:
    receipts = list(_ciav_receipts())
    changed = receipts[1].model_dump(mode="python")
    changed["time_cost"] = 0.05
    unsigned = {key: value for key, value in changed.items() if key != "receipt_sha256"}
    changed["receipt_sha256"] = content_sha256(unsigned)
    receipts[1] = MatchedCIAVArmReceipt.model_validate(changed)

    with pytest.raises(ValueError, match="differs across arms"):
        verify_exact_three_arm_ciav_match(tuple(receipts))


def test_ciav_receipt_rejects_forged_privacy_budget_delta() -> None:
    payload = _ciav_receipts()[0].model_dump(mode="python")
    payload["privacy_budget_after"] = 1.0
    unsigned = {key: value for key, value in payload.items() if key != "receipt_sha256"}
    payload["receipt_sha256"] = content_sha256(unsigned)

    with pytest.raises(ValidationError, match="budget delta"):
        MatchedCIAVArmReceipt.model_validate(payload)
