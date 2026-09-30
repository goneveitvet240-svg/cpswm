"""Split attacks retain hidden context assets and failed/unknown houses."""

from copy import deepcopy

import pytest
from collect_offline_factor_data import runtime_partition_audit


def matrix():
    houses, attempts = [], []
    for index in range(13):
        split = "diagnostic_only" if index == 0 else "train" if index <= 8 else "validation"
        instance = dict(
            object_id=f"instance-{index}", asset_id=f"asset-{index}", exclusion_reasons=[]
        )
        houses.append(
            dict(index=index, split=split, asset_ids=[instance["asset_id"]], instances=[instance])
        )
        if index:
            attempts.append(
                dict(
                    index=index,
                    split=split,
                    status="verified",
                    exit_code=0,
                    started_at=f"2026-09-30T00:00:{index * 2:02d}+00:00",
                    finished_at=f"2026-09-30T00:00:{index * 2 + 1:02d}+00:00",
                    verification=dict(
                        all_assets=[instance["asset_id"]],
                        scope=[f"scope-{index}-{i}" for i in range(3)],
                        frame_records=[dict(action_id=f"action-{index}-{i}") for i in range(8)],
                        unknown_assets=[],
                        instances=[
                            dict(
                                object_id=instance["object_id"],
                                asset_id=instance["asset_id"],
                                position_changed_during_initialization=False,
                                exclusion_reasons=[],
                            )
                        ],
                    ),
                )
            )
    return dict(houses=houses), attempts


def test_complete_disjoint_matrix_allows_static_eligible_targets_only():
    plan, attempts = matrix()
    audit = runtime_partition_audit(plan, attempts)
    assert audit["complete_asset_exposure_audit"]
    assert sum(r["eligible"] for r in audit["instances"]) == 12
    assert not audit["training_performed"] and not audit["supervision_export_performed"]


@pytest.mark.parametrize(
    "attack",
    [
        "unlabelled_train_context",
        "runtime_train_context",
        "old_diagnostic",
        "unknown",
        "failed",
        "moved",
        "static_excluded",
        "renamed_runtime_id",
    ],
)
def test_complete_but_contaminated_matrix_quarantines_affected_validation_target(attack):
    plan, attempts = matrix()
    if attack == "unlabelled_train_context":
        plan["houses"][1]["asset_ids"].append("asset-9")
    elif attack == "runtime_train_context":
        attempts[0]["verification"]["all_assets"].append("asset-9")
    elif attack == "old_diagnostic":
        plan["houses"][0]["asset_ids"].append("asset-9")
    elif attack == "unknown":
        attempts[0]["verification"]["unknown_assets"].append("unidentified")
    elif attack == "failed":
        attempts[0]["status"] = "failed"
        attempts[0].update(exit_code=7, error="controlled failure", traceback="controlled trace")
        attempts[0].pop("verification")
    elif attack == "moved":
        attempts[8]["verification"]["instances"][0]["position_changed_during_initialization"] = True
    elif attack == "static_excluded":
        plan["houses"][9]["instances"][0]["exclusion_reasons"] = [
            "duplicate_house_physical_content"
        ]
    else:
        attempts[8]["verification"]["instances"][0]["object_id"] = "forged-new-instance"
    audit = runtime_partition_audit(plan, attempts)
    target = next(r for r in audit["instances"] if r["house_index"] == 9)
    assert not target["eligible"]


@pytest.mark.parametrize("attack", ["omit_failed_house", "duplicate_house", "change_partition"])
def test_no_complete_claim_after_omission_or_partition_change(attack):
    plan, attempts = matrix()
    if attack == "omit_failed_house":
        attempts.pop()
    elif attack == "duplicate_house":
        attempts[-1] = deepcopy(attempts[0])
    else:
        attempts[8]["split"] = "train"
    with pytest.raises(ValueError):
        runtime_partition_audit(plan, attempts)


@pytest.mark.parametrize("key", ["scope", "frame_records"])
def test_cross_house_complete_replay_rejected(key):
    plan, attempts = matrix()
    attempts[8]["verification"][key] = deepcopy(attempts[0]["verification"][key])
    with pytest.raises(ValueError, match="cross-house"):
        runtime_partition_audit(plan, attempts)
