"""WP0 baseline harness tests.

The floor these baselines establish is what makes OAM-PHM `§12.1` condition 8
and `§12.2` stop condition 1 checkable at all.  The tests therefore assert two
things: that the harness cannot cheat, and that the floor reproduces the exact
failure mode `§2.2` says a single pooled location distribution has.
"""

from __future__ import annotations

import ast
from datetime import timedelta
from pathlib import Path
from uuid import UUID

import pytest
from test_f0_long_horizon_vertical_slice import (
    build_policy,
    build_routine_config,
    run_benchmark_view,
)

from cpswm.system.evaluation_operations import (
    SECTION_9_1_REGISTRY,
    BaselineRegistryEntry,
    BaselineStatus,
    HouseholdFrequencyPriorBaseline,
    LastSeenLocationBaseline,
    LocationBeliefPrediction,
    LocationQuery,
    MarkovTransitionBaseline,
    compare_baselines,
    default_baselines,
    registry_status_counts,
    score_baseline,
)
from cpswm.system.synthetic_routines import SyntheticRoutineGenerator

BASELINE_MODULE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "cpswm"
    / "system"
    / "evaluation_operations"
    / "oam_phm_baselines.py"
)


@pytest.fixture
def f0_slice():
    """The checked-in F0 fixture: desk -> sofa (anomaly) -> desk."""

    plan = SyntheticRoutineGenerator().generate(build_routine_config())
    view = run_benchmark_view(plan, build_policy())
    return view


@pytest.fixture
def pre_observation_queries(f0_slice):
    """Ask where the object is at each placement, before that day's detection.

    Query time equals the detection time, and detection history is strictly
    earlier, so a baseline must predict rather than read off the answer.
    """

    run = f0_slice.visible_result
    target = run.scheduled_observation_object_id
    queries: list[LocationQuery] = []
    truth: list[UUID] = []
    for event in f0_slice.ground_truth.events:
        if event.object_gt_entity_id != target:
            continue
        queries.append(
            LocationQuery(
                object_instance_id=target,
                query_time=event.event_time + timedelta(hours=1),
            )
        )
        truth.append(event.destination_location_gt_entity_id)
    return tuple(queries), tuple(truth)


# --------------------------------------------------------------------------
# The harness must not be able to cheat
# --------------------------------------------------------------------------


def test_baseline_module_never_imports_ground_truth():
    """`§5.1` invariant 8: only M29/M31/M32 may read ``gt.*``.

    A baseline is a model, not an evaluator.  Enforcing this by inspecting the
    import graph makes the guarantee structural rather than a convention.
    """

    tree = ast.parse(BASELINE_MODULE.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    assert not any(name.startswith("cpswm_gt") for name in imported)


def test_scoring_rejects_a_mismatched_truth_vector(f0_slice, pre_observation_queries):
    queries, truth = pre_observation_queries

    with pytest.raises(ValueError, match="exactly one truth location"):
        score_baseline(LastSeenLocationBaseline(), f0_slice.visible_result, queries, truth[:-1])


def test_comparison_rejects_duplicate_baseline_versions(f0_slice, pre_observation_queries):
    queries, truth = pre_observation_queries

    with pytest.raises(ValueError, match="unique within one comparison"):
        compare_baselines(
            (LastSeenLocationBaseline(), LastSeenLocationBaseline()),
            f0_slice.visible_result,
            queries,
            truth,
        )


def test_every_baseline_sees_identical_inputs(f0_slice, pre_observation_queries):
    """`§9.4` rules 1 and 6: a score gap must not come from an input gap."""

    queries, truth = pre_observation_queries
    seen: list[tuple[int, int]] = []

    class Recording(LastSeenLocationBaseline):
        baseline_version = "recording@0.1"

        def predict(self, run, query):
            seen.append((len(run.detection_results), len(run.observation_opportunities)))
            return super().predict(run, query)

    compare_baselines(
        (LastSeenLocationBaseline(), Recording()),
        f0_slice.visible_result,
        queries,
        truth,
    )

    assert len(set(seen)) == 1


def test_posterior_must_be_normalised():
    with pytest.raises(ValueError, match="sum to one"):
        LocationBeliefPrediction(
            query=LocationQuery(
                object_instance_id=UUID(int=4),
                query_time=__import__("datetime").datetime(
                    2026, 8, 13, tzinfo=__import__("datetime").UTC
                ),
            ),
            location_posterior={UUID(int=6): 0.4, UUID(int=7): 0.4},
            baseline_version="x@0.1",
        )


def test_zero_sample_scores_are_undefined_not_zero(f0_slice):
    score = score_baseline(LastSeenLocationBaseline(), f0_slice.visible_result, (), ())

    assert score.sample_count == 0
    assert score.top1_accuracy is None
    assert score.mean_negative_log_likelihood is None


def test_smoothing_keeps_every_candidate_reachable(f0_slice, pre_observation_queries):
    """A zero-probability truth would make NLL infinite and hide the failure."""

    queries, truth = pre_observation_queries
    for baseline in default_baselines():
        score = score_baseline(baseline, f0_slice.visible_result, queries, truth)
        assert score.mean_negative_log_likelihood is not None
        assert score.mean_negative_log_likelihood < float("inf")


# --------------------------------------------------------------------------
# The floor must reproduce the failure mode OAM-PHM §2.2 names
# --------------------------------------------------------------------------


def test_last_seen_is_permanently_contaminated_by_one_anomaly(f0_slice, pre_observation_queries):
    """Day 2 is a temporary exception; last-seen still believes it on day 3."""

    queries, truth = pre_observation_queries
    score = score_baseline(LastSeenLocationBaseline(), f0_slice.visible_result, queries, truth)

    assert score.sample_count == 3
    assert score.top1_accuracy == pytest.approx(1 / 3)


def test_pooled_frequency_resists_the_anomaly_but_loses_current_state(
    f0_slice, pre_observation_queries
):
    """Pooling survives day 3 and fails day 2: one distribution cannot do both.

    This is exactly the boundary `§2.2` records as *"one location distribution
    carries both current state and long-term regularity"*.  Beating it requires
    separating the two, which is WP2 — not a better pooled estimator.
    """

    queries, truth = pre_observation_queries
    pooled = score_baseline(
        HouseholdFrequencyPriorBaseline(), f0_slice.visible_result, queries, truth
    )
    last_seen = score_baseline(LastSeenLocationBaseline(), f0_slice.visible_result, queries, truth)

    assert pooled.top1_accuracy == pytest.approx(2 / 3)
    assert pooled.top1_accuracy > last_seen.top1_accuracy
    assert pooled.mean_negative_log_likelihood < last_seen.mean_negative_log_likelihood


def test_first_order_markov_degenerates_under_sparse_selective_observation(
    f0_slice, pre_observation_queries
):
    """Three detections give one transition; the estimate carries no signal."""

    queries, truth = pre_observation_queries
    markov = score_baseline(MarkovTransitionBaseline(), f0_slice.visible_result, queries, truth)
    last_seen = score_baseline(LastSeenLocationBaseline(), f0_slice.visible_result, queries, truth)

    assert markov.top1_accuracy == pytest.approx(last_seen.top1_accuracy)


def test_no_runnable_baseline_solves_the_fixture(f0_slice, pre_observation_queries):
    """The floor leaves real headroom, so WP2-WP6 gains are measurable."""

    queries, truth = pre_observation_queries
    scores = compare_baselines(default_baselines(), f0_slice.visible_result, queries, truth)

    assert all(score.top1_accuracy is not None and score.top1_accuracy < 1.0 for score in scores)


# --------------------------------------------------------------------------
# The registry must show what is missing, not only what exists
# --------------------------------------------------------------------------


def test_registry_covers_every_section_9_1_entry():
    assert len(SECTION_9_1_REGISTRY) == 10
    assert all(isinstance(entry, BaselineRegistryEntry) for entry in SECTION_9_1_REGISTRY)
    assert len({entry.name for entry in SECTION_9_1_REGISTRY}) == 10


def test_registry_reports_unrunnable_baselines_rather_than_omitting_them():
    counts = registry_status_counts()

    assert counts[BaselineStatus.IMPLEMENTED] == 3
    assert counts[BaselineStatus.GATED_BY_REVIEW] > 0
    assert counts[BaselineStatus.EXTERNAL_REIMPLEMENTATION_REQUIRED] > 0


def test_implemented_registry_entries_match_the_runnable_baselines():
    registered = {
        entry.baseline_version
        for entry in SECTION_9_1_REGISTRY
        if entry.status == BaselineStatus.IMPLEMENTED
    }

    assert registered == {baseline.baseline_version for baseline in default_baselines()}


def test_a_non_implemented_entry_cannot_claim_a_version():
    with pytest.raises(ValueError, match="must not declare a version"):
        BaselineRegistryEntry(
            name="O-STaR faithful reproduction",
            status=BaselineStatus.EXTERNAL_REIMPLEMENTATION_REQUIRED,
            baseline_version="o-star@0.1",
            note="not actually implemented",
        )
