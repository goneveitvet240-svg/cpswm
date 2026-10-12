from __future__ import annotations

import hashlib
import math
from collections import Counter

import pytest
from run_current_event import build, dataset_for

from cpswm.contracts import ProjectTwoDatasetSplit
from cpswm.system.evaluation_operations.structure_two_stateful_full_joint import (
    FullJointArm,
    StatefulFullJointRuntime,
)
from cpswm.system.evaluation_operations.structure_two_stratified_sampling import (
    stratified_draw_indices,
    stratum_offsets,
)


def seed(i):
    return hashlib.sha256(f"enumerated-support:{i}".encode()).hexdigest()


def test_original_equal_parent_phase_lock_and_fixed_support():
    q = [1 / 72] * 72
    old = StatefulFullJointRuntime._systematic_draw_indices(q, 24, seed(0))
    new = stratified_draw_indices(q, 24, seed(0))
    assert len({i % 3 for i in old}) == 1
    assert len({i % 3 for i in new}) == 3
    assert len(new) == len(old) == 24
    assert [i // 3 for i in new] == list(range(24))


def test_enumerated_posterior_and_proposal_frequencies():
    q_actor = [0.2, 0.3, 0.5]
    likelihood = [9.0, 2.0, 1.0]
    exact = [p * value / 2.9 for p, value in zip(q_actor, likelihood, strict=True)]
    q = [p / 24 for _ in range(24) for p in q_actor]
    counts = Counter()
    means = [0.0] * 3
    old_error = new_error = 0.0
    for i in range(2048):
        for method in ["old", "new"]:
            draw = (
                StatefulFullJointRuntime._systematic_draw_indices
                if method == "old"
                else stratified_draw_indices
            )(q, 24, seed(i))
            c = Counter(j % 3 for j in draw)
            weighted = [c[a] * likelihood[a] for a in range(3)]
            posterior = [v / sum(weighted) for v in weighted]
            error = sum(abs(a - b) for a, b in zip(posterior, exact, strict=True))
            if method == "old":
                old_error += error
            else:
                new_error += error
                counts.update(c)
                means = [a + b / 2048 for a, b in zip(means, posterior, strict=True)]
    assert new_error < old_error * 0.35
    # Self-normalized importance estimates have finite-N bias. Compare their
    # mean against the exact multinomial expectation, not an invented zero-bias bound.
    finite_mean = [0.0] * 3
    for a in range(25):
        for b in range(25 - a):
            c = 24 - a - b
            probability = math.comb(24, a) * math.comb(24 - a, b)
            probability *= 0.2**a * 0.3**b * 0.5**c
            weighted = [a * 9.0, b * 2.0, float(c)]
            for j in range(3):
                finite_mean[j] += probability * weighted[j] / sum(weighted)
    assert max(abs(a - b) for a, b in zip(means, finite_mean, strict=True)) < 0.008
    assert max(abs(counts[a] / (2048 * 24) - q_actor[a]) for a in range(3)) < 0.008


@pytest.mark.parametrize("q", [[0, 0.05, 0.15, 0, 0.8], [0.8, 0, 0.15, 0.05, 0]])
def test_nonuniform_reordered_support_and_zero_mass(q):
    counts = Counter()
    for i in range(512):
        draw = stratified_draw_indices(q, 24, seed(i))
        assert draw == stratified_draw_indices(q, 24, seed(i))
        assert len(draw) == 24 and all(q[j] > 0 for j in draw)
        counts.update(draw)
    assert max(abs(counts[j] / (512 * 24) - q[j]) for j in range(len(q))) < 0.003


@pytest.mark.parametrize(
    "q,n,s",
    [
        ([], 24, seed(0)),
        ([0.5], 24, seed(0)),
        ([-1, 2], 24, seed(0)),
        ([float("nan"), 1], 24, seed(0)),
        ([float("inf")], 24, seed(0)),
        ([1], 0, seed(0)),
        ([1], True, seed(0)),
        ([1], 24, "bad"),
    ],
)
def test_invalid_sampling_inputs(q, n, s):
    with pytest.raises(ValueError):
        stratified_draw_indices(q, n, s)


def test_offsets_are_independent_reproducible_and_half_open():
    offsets = stratum_offsets(24, seed(0))
    assert len(set(offsets)) == 24 and all(0 <= u < 1 for u in offsets)
    assert offsets == stratum_offsets(24, seed(0))
    assert offsets != stratum_offsets(24, seed(1))


@pytest.mark.parametrize("arm", list(FullJointArm))
def test_native_repaired_support_current_event_and_revision_restore(arm):
    dataset = dataset_for("sparse32", [67001])
    episode = dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)[0]
    state = build(dataset, episode, arm)
    for step in episode.steps[:4]:
        state.observe(step)
        state.predict()
        state.feedback(step)
    runtime = state.runtime
    assert len(runtime.sampling_receipts) == runtime.step_index == 4
    assert all(r["method"] == "independent_strata_v1" for r in runtime.sampling_receipts)
    assert len({p.world.placement_actor for p in runtime.particles}) > 1
    before = runtime._capture_mutable_state()
    source = next(iter(runtime.location_sources))
    runtime.revise_location_source(source, runtime.location_sources[source]["sha256"])
    runtime.revise_location_source(source, runtime.location_sources[source]["sha256"], restore=True)
    after = runtime._capture_mutable_state()
    assert vars(after.pop("rgrc_ledger")) == vars(before.pop("rgrc_ledger"))
    assert after == before
    runtime.verify_internal_contracts()
