"""Full fixed-window set is invariant under execution partitioning."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from run_hfd_hand_proposals import partition_windows


def full_plan():
    return tuple(f"{i:064x}/window-{j:06d}" for i in range(8) for j in (0, 5, 15, 25))


@pytest.mark.parametrize("count", [1, 2, 3, 4, 8])
def test_partition_has_no_overlap_omission_or_input_order_dependence(count):
    plan = full_plan()
    pieces = [partition_windows(plan, i, count) for i in range(count)]
    flattened = [key for part in pieces for key in part]
    assert len(flattened) == len(set(flattened)) == len(plan)
    assert set(flattened) == set(plan)
    assert all(
        pieces[i] == partition_windows(tuple(reversed(plan)), i, count) for i in range(count)
    )
    if count == 8:
        assert [len(p) for p in pieces] == [4] * 8
        assert [sum(k.endswith("000000") for k in p) for p in pieces] == [1] * 8
    if count == 4:
        assert [len(p) for p in pieces] == [8] * 4
        assert [sum(k.endswith("000000") for k in p) for p in pieces] == [2] * 4


@pytest.mark.parametrize("index,count", [(-1, 4), (4, 4), (0, 0), (0, 9), (True, 4), (0, True)])
def test_invalid_partition_cannot_silently_drop_windows(index, count):
    with pytest.raises(ValueError):
        partition_windows(full_plan(), index, count)


def test_duplicate_plan_is_rejected_and_default_is_exact_original_order():
    plan = full_plan()
    assert partition_windows(plan) == plan
    with pytest.raises(ValueError):
        partition_windows((*plan, plan[0]), 0, 4)
