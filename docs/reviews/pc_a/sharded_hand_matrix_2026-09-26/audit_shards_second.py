"""Actual all-window vs shard inference, not only arithmetic partition identities."""

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [
    str(ROOT / "tools"),
    str(ROOT / "tests"),
    str(ROOT / "docs/reviews/pc_a/full_hand_proposal_matrix_2026-09-26"),
]
from audit_matrix_second import setup_front  # noqa: E402
from run_frozen_shards import checked_shard_coverage  # noqa: E402
from run_hfd_hand_proposals import run  # noqa: E402

from cpswm.data_preflight.typed_proposal_networks import ARMS  # noqa: E402


def actual_cases(directory):
    return {
        json.loads(p.read_bytes())["window"]: json.loads(p.read_bytes())
        for p in directory.glob("*.json")
        if p.name != "summary.json" and not p.name.endswith("snapshot.json")
    }


def test_real_network_partition_union_matches_unsharded_complete_output(tmp_path, monkeypatch):
    front, pin, training = setup_front(tmp_path, monkeypatch)
    whole = tmp_path / "whole"
    run(front, pin, training, whole, ARMS[1], 2, window_scope="all", restore_scope="first")
    expected = actual_cases(whole)
    actual = {}
    for index in range(4):
        part = tmp_path / f"shard-{index}"
        summary = run(
            front,
            pin,
            training,
            part,
            ARMS[1],
            2,
            window_scope="all",
            restore_scope="first",
            shard_index=index,
            shard_count=4,
        )
        cases = actual_cases(part)
        assert not set(cases) & set(actual)
        assert set(cases) == set(summary["selection"]["planned_windows"])
        actual.update(cases)
    assert set(actual) == set(expected) and len(actual) == 8
    for key in expected:
        left = {k: v for k, v in actual[key].items() if k != "seconds"}
        right = {k: v for k, v in expected[key].items() if k != "seconds"}
        assert left == right
    assert sum(v["restore_and_next_draw_equal"] is True for v in actual.values()) == 2


def test_invalid_shard_cannot_write_a_false_success_summary(tmp_path, monkeypatch):
    front, pin, training = setup_front(tmp_path, monkeypatch)
    output = tmp_path / "invalid"
    with pytest.raises(ValueError, match="shard"):
        run(front, pin, training, output, ARMS[0], 2, shard_index=4, shard_count=4)
    assert not output.exists()


@pytest.mark.parametrize("attack", ["omit", "duplicate", "cross_arm", "false_restore"])
def test_complete_looking_coverage_cannot_hide_missing_or_mislabelled_cases(attack):
    keys = ["a" * 64 + "/window-000000", "a" * 64 + "/window-000001"]
    jobs, summaries = [], []
    for arm in ARMS:
        jobs.append({"arm": arm, "windows": keys})
        summaries.append(
            {
                "arm": arm,
                "selection": {"planned_windows": keys},
                "runs": [
                    {
                        "arm": arm,
                        "window": key,
                        "prefix_frames": 4,
                        "restore_and_next_draw_equal": True if index == 0 else None,
                        "repeated_complete_distribution_equal": True if index == 0 else None,
                        "scoring_left_rng_and_requests_unchanged": True,
                        "target_ids_fixed_across_controls": True,
                    }
                    for index, key in enumerate(keys)
                ],
            }
        )
    # Internally consistent fabricated metadata can pass COVERAGE only. Actual
    # network outputs are checked above, and execution/source receipts remain required.
    assert len(checked_shard_coverage(keys, ARMS, jobs, summaries)) == 6
    bad = deepcopy(summaries)
    if attack == "omit":
        bad[0]["runs"].pop()
    elif attack == "duplicate":
        bad[0]["runs"][1] = deepcopy(bad[0]["runs"][0])
    elif attack == "cross_arm":
        bad[0]["runs"][0]["arm"] = ARMS[1]
    else:
        bad[0]["runs"][1]["restore_and_next_draw_equal"] = True
    with pytest.raises(ValueError):
        checked_shard_coverage(keys, ARMS, jobs, bad)
