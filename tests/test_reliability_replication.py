"""Consequential validation: full self-consistent forgery versus source replay."""

import copy

import pytest
from analyze_reliability_replication import (
    CANDIDATE,
    cluster_uncertainty,
    match_replay,
    paired,
    record_digest,
    verify_row,
)
from run_memory_action import read_selection_archive
from run_reliability_replication import Split, build_dataset, run_episode

from cpswm.system.reproducibility import content_sha256


@pytest.fixture(scope="module")
def records():
    dataset = build_dataset("complete32", [31])
    episode = dataset.visible_episodes(Split.TEST)[0]
    return list(run_episode(dataset, episode, "complete32", 31, read_selection_archive(), 2))


def test_valid_native_three_block_reconstruction(records):
    for row in records:
        assert verify_row(row) < 1e-12
        match_replay(row, record_digest(row))


def test_action_and_statistics_forgery_rejected_even_after_commit_reseal(records):
    row = copy.deepcopy(records[-1])
    name = CANDIDATE
    old = row["actions"][name]["put_back"]
    row["actions"][name]["put_back"] = next(k for k in row["distributions"][name] if k != old)
    row["scores"][name]["put_error"] = int(
        row["actions"][name]["put_back"] != row["truth"]["true_owner_habit_location"]
    )
    row["pre_truth_commitment"] = content_sha256(
        {k: row[k] for k in ("actions", "readouts", "distributions", "traces")}
    )
    with pytest.raises(AssertionError):
        verify_row(row)


def test_complete_consistent_source_forgery_requires_fresh_replay(records):
    row = copy.deepcopy(records[0])
    expected = record_digest(row)
    row["input"]["detection_confidence"] = 0.4123
    row["input_sha256"] = content_sha256(row["input"])
    # All saved scores, probability algebra, and self-issued hashes still agree.
    assert verify_row(row) < 1e-12
    with pytest.raises(AssertionError, match="fresh replay differs"):
        match_replay(row, expected)


def test_seed_clusters_and_net_benefit_sign():
    rows = []
    for seed in range(6):
        for _ in range(4):
            rows.append(
                {
                    "seed": seed,
                    "scores": {CANDIDATE: {"put_error": 1}, "baseline": {"put_error": 0}},
                }
            )
    assert paired(rows, CANDIDATE, "baseline")["net_fewer_errors"] == -24
    result = cluster_uncertainty(rows, "baseline", draws=100)
    assert result["independent_seed_groups"] == 6
    assert result["descriptive_bootstrap_total_95pct"] == [-24, -24]
    assert result["two_sided_cluster_sign_flip_fraction"] == 2 / 64
