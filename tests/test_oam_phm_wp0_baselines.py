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
    BaselineParameterCandidate,
    BaselinePerformanceBudget,
    BaselineRegistryEntry,
    BaselineStatus,
    ComputeBudgetUnit,
    F0ExactBijectionIdentityMapping,
    GridBaselineAdapter,
    HabitualTruthTarget,
    HeadConstructionMode,
    HouseholdFrequencyPriorBaseline,
    IdentityAssociationStatus,
    IdentityKind,
    IdentityMappingContract,
    IdentityMappingEntry,
    LastSeenLocationBaseline,
    LocationBeliefPrediction,
    LocationDistributionPrediction,
    LocationQuery,
    LocationTruthChange,
    MarkovTransitionBaseline,
    OAMSplitAuthority,
    PredictionComputeReceipt,
    QueryGridSpec,
    SealedEvaluationQuerySet,
    TemporalIdentityAssociation,
    TemporalIdentityAssociationContract,
    TuningObjective,
    audit_split_disjointness,
    build_expanded_location_query_grid,
    candidate_grid_sha256,
    compare_baselines,
    default_baselines,
    evaluate_tuned_baseline,
    predict_current_and_habitual,
    registry_status_counts,
    score_baseline,
    score_baseline_distributions,
    tune_baseline_adapter,
)
from cpswm.system.reproducibility import content_sha256
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


@pytest.fixture
def explicit_f0_identity_mapping(f0_slice):
    target = f0_slice.visible_result.scheduled_observation_object_id
    location_ids = {
        event.destination_location_gt_entity_id for event in f0_slice.ground_truth.events
    }
    return F0ExactBijectionIdentityMapping(
        mapping_version="f0-explicit-shared-namespace@0.1",
        entries=(
            IdentityMappingEntry(
                identity_kind=IdentityKind.OBJECT,
                gt_entity_id=target,
                perceived_track_id=target,
            ),
            *(
                IdentityMappingEntry(
                    identity_kind=IdentityKind.LOCATION,
                    gt_entity_id=location_id,
                    perceived_track_id=location_id,
                )
                for location_id in sorted(location_ids)
            ),
        ),
    )


@pytest.fixture
def expanded_query_set(f0_slice, explicit_f0_identity_mapping):
    run = f0_slice.visible_result
    target = run.scheduled_observation_object_id
    changes = tuple(
        LocationTruthChange(
            event_time=event.event_time,
            event_group_id=event.gt_event_id,
            object_gt_entity_id=event.object_gt_entity_id,
            location_gt_entity_id=event.destination_location_gt_entity_id,
        )
        for event in f0_slice.ground_truth.events
        if event.object_gt_entity_id == target
    )
    return build_expanded_location_query_grid(
        truth_changes=changes,
        object_gt_entity_id=target,
        identity_mapping=explicit_f0_identity_mapping,
        split_id="f0-development-grid@0.1",
        source_dataset_sha256=run.simulation_content_sha256,
        truth_source_manifest_sha256=content_sha256(f0_slice.ground_truth),
        episode_group_id=run.simulation_run_id,
        household_group_id=run.observation_opportunities[0].metadata.household_id,
        end_time=run.start_time + timedelta(days=run.duration_days),
        spec=QueryGridSpec(cadence=timedelta(hours=6), lead_time=timedelta(hours=1)),
    )


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


# --------------------------------------------------------------------------
# Strong-baseline scaffold required before formal-data evaluation
# --------------------------------------------------------------------------


def test_identity_mapping_is_explicit_and_bijective():
    gt_a, gt_b, track = UUID(int=101), UUID(int=102), UUID(int=201)

    with pytest.raises(ValueError, match="bijective"):
        IdentityMappingContract(
            mapping_version="bad@0.1",
            entries=(
                IdentityMappingEntry(
                    identity_kind=IdentityKind.LOCATION,
                    gt_entity_id=gt_a,
                    perceived_track_id=track,
                ),
                IdentityMappingEntry(
                    identity_kind=IdentityKind.LOCATION,
                    gt_entity_id=gt_b,
                    perceived_track_id=track,
                ),
            ),
        )


def test_expanded_grid_replaces_the_legacy_three_queries(expanded_query_set):
    assert len(expanded_query_set.queries) > 3
    assert len(expanded_query_set.current_truth_gt_ids) == len(expanded_query_set.queries)
    assert len(expanded_query_set.habitual_truth_gt_distributions) == len(
        expanded_query_set.queries
    )


def test_current_belief_and_habitual_distribution_are_separate_heads(
    f0_slice, pre_observation_queries
):
    queries, _ = pre_observation_queries
    prediction = predict_current_and_habitual(
        LastSeenLocationBaseline(), f0_slice.visible_result, queries[-1]
    )

    assert prediction.current_belief != prediction.habitual_distribution
    assert prediction.head_construction == HeadConstructionMode.NATIVE_DUAL_HEAD
    assert prediction.habitual_head_version == "last-seen-cumulative-frequency@0.1"
    assert prediction.compute_receipt.component_model_invocations == 1
    assert sum(prediction.current_belief.values()) == pytest.approx(1.0)
    assert sum(prediction.habitual_distribution.values()) == pytest.approx(1.0)


def test_native_two_head_external_adapter_output_is_preserved(f0_slice, pre_observation_queries):
    queries, _ = pre_observation_queries

    class NativeTwoHead(LastSeenLocationBaseline):
        baseline_version = "native-two-head@0.1"

        def predict_distributions(self, run, query):
            current = super().predict(run, query).location_posterior
            habitual = dict(zip(current, reversed(tuple(current.values())), strict=True))
            return LocationDistributionPrediction(
                query=query,
                current_belief=current,
                habitual_distribution=habitual,
                baseline_version=self.baseline_version,
                head_construction=HeadConstructionMode.NATIVE_DUAL_HEAD,
                habitual_head_version="native-habit@0.1",
                compute_receipt=PredictionComputeReceipt(
                    adapter_invocations=1,
                    component_model_invocations=1,
                    processed_observations=len(run.detection_results),
                ),
            )

    native = NativeTwoHead()
    prediction = predict_current_and_habitual(native, f0_slice.visible_result, queries[-1])

    assert prediction.habitual_distribution != prediction.current_belief
    assert prediction.head_construction == HeadConstructionMode.NATIVE_DUAL_HEAD


def test_internal_baselines_expose_independent_native_habitual_heads(
    f0_slice, pre_observation_queries
):
    queries, _ = pre_observation_queries
    predictions = [
        predict_current_and_habitual(baseline, f0_slice.visible_result, queries[-1])
        for baseline in (
            LastSeenLocationBaseline(smoothing=1e-4),
            HouseholdFrequencyPriorBaseline(smoothing=1e-2),
            MarkovTransitionBaseline(smoothing=0.2),
        )
    ]

    assert len({tuple(item.habitual_distribution.items()) for item in predictions}) > 1
    assert {item.head_construction for item in predictions} == {
        HeadConstructionMode.NATIVE_DUAL_HEAD
    }
    assert {item.compute_receipt.component_model_invocations for item in predictions} == {1}


def test_dual_head_scorer_reports_both_targets_and_resource_usage(
    f0_slice, expanded_query_set, explicit_f0_identity_mapping
):
    score = score_baseline_distributions(
        LastSeenLocationBaseline(),
        f0_slice.visible_result,
        expanded_query_set,
        explicit_f0_identity_mapping,
        performance_budget=BaselinePerformanceBudget(
            max_queries=100,
            compute_unit=ComputeBudgetUnit.COMPONENT_MODEL_INVOCATION,
            max_compute_units=2 * len(expanded_query_set.queries),
            wall_time_compliance_seconds=5.0,
            hardware_profile="pytest-cpu",
        ),
    )

    assert score.current_mean_negative_log_likelihood is not None
    assert score.habitual_mean_cross_entropy is not None
    assert score.habitual_mean_total_variation is not None
    assert score.resource_usage.query_count == len(expanded_query_set.queries)
    assert score.time_grid_query_count == len(expanded_query_set.queries)
    assert score.resource_usage.adapter_invocations == len(expanded_query_set.queries)
    assert score.resource_usage.component_model_invocations == len(expanded_query_set.queries)
    assert score.event_cluster_count == 3
    assert score.episode_cluster_count == 1
    assert score.household_cluster_count == 1
    assert score.habitual_truth_target == (
        HabitualTruthTarget.CUMULATIVE_EMPIRICAL_PLACEMENT_DISTRIBUTION.value
    )
    assert score.resource_usage.wall_time_check_kind == (
        "posthoc_compliance_check_not_hard_timeout"
    )


def test_performance_budget_fails_closed_before_scoring(
    f0_slice, expanded_query_set, explicit_f0_identity_mapping
):
    with pytest.raises(ValueError, match="query count exceeds"):
        score_baseline_distributions(
            LastSeenLocationBaseline(),
            f0_slice.visible_result,
            expanded_query_set,
            explicit_f0_identity_mapping,
            performance_budget=BaselinePerformanceBudget(
                max_queries=4,
                compute_unit=ComputeBudgetUnit.ADAPTER_INVOCATION,
                max_compute_units=100,
                hardware_profile="pytest-cpu",
            ),
        )


def test_temporal_identity_contract_allows_fragmentation_and_unknown_tracks():
    gt, first, second = UUID(int=101), UUID(int=201), UUID(int=202)
    contract = TemporalIdentityAssociationContract(
        mapping_version="b1-many-to-many@0.1",
        associations=(
            TemporalIdentityAssociation(
                identity_kind=IdentityKind.OBJECT,
                gt_entity_id=gt,
                perceived_track_id=first,
                valid_from=__import__("datetime").datetime(
                    2026, 8, 1, tzinfo=__import__("datetime").UTC
                ),
                association_probability=0.7,
                status=IdentityAssociationStatus.FRAGMENT,
            ),
            TemporalIdentityAssociation(
                identity_kind=IdentityKind.OBJECT,
                gt_entity_id=gt,
                perceived_track_id=second,
                valid_from=__import__("datetime").datetime(
                    2026, 8, 2, tzinfo=__import__("datetime").UTC
                ),
                association_probability=0.6,
                status=IdentityAssociationStatus.FRAGMENT,
            ),
        ),
    )

    assert len(contract.associations) == 2


def _last_seen_adapter():
    candidates = tuple(
        BaselineParameterCandidate(
            candidate_id=f"smoothing-{value:g}", parameters={"smoothing": value}
        )
        for value in (1e-4, 1e-3, 1e-2)
    )
    return GridBaselineAdapter(
        adapter_id="last-seen",
        adapter_version="last-seen-adapter@0.1",
        factory=LastSeenLocationBaseline,
        parameter_candidates=candidates,
    )


def _disjoint_evaluation_copy(expanded_query_set, explicit_f0_identity_mapping):
    new_track = UUID(int=9001)
    new_gt_object = UUID(int=9002)
    evaluation = expanded_query_set.model_copy(
        update={
            "split_id": "formal-sealed-test@0.1",
            "source_dataset_sha256": "e" * 64,
            "truth_source_manifest_sha256": "f" * 64,
            "queries": tuple(
                query.model_copy(
                    update={
                        "object_instance_id": new_track,
                        "query_time": query.query_time + timedelta(days=365),
                    }
                )
                for query in expanded_query_set.queries
            ),
            "group_bindings": tuple(
                binding.model_copy(
                    update={
                        "episode_group_id": UUID(int=10_000 + index),
                        "household_group_id": UUID(int=20_000 + index),
                        "object_group_id": new_track,
                        "event_group_id": UUID(int=30_000 + index),
                    }
                )
                for index, binding in enumerate(expanded_query_set.group_bindings)
            ),
        }
    )
    location_entries = tuple(
        entry
        for entry in explicit_f0_identity_mapping.entries
        if entry.identity_kind == IdentityKind.LOCATION
    )
    mapping = F0ExactBijectionIdentityMapping(
        mapping_version="sealed-evaluation-mapping@0.1",
        entries=(
            IdentityMappingEntry(
                identity_kind=IdentityKind.OBJECT,
                gt_entity_id=new_gt_object,
                perceived_track_id=new_track,
            ),
            *location_entries,
        ),
    )
    return evaluation, mapping


def test_same_data_cannot_be_relabelled_and_sealed(
    expanded_query_set, explicit_f0_identity_mapping
):
    adapter = _last_seen_adapter()
    renamed = expanded_query_set.model_copy(update={"split_id": "formal-sealed-test@0.1"})
    audit = audit_split_disjointness(expanded_query_set, renamed)

    assert not audit.passed
    assert audit.overlapping_sample_fingerprints
    with pytest.raises(ValueError, match="disjointness audit failed"):
        OAMSplitAuthority(secret=b"pytest-split-authority").prepare_protocol(
            protocol_id="last-seen-formal@0.2",
            adapter=adapter,
            tuning_queries=expanded_query_set,
            evaluation_queries=renamed,
            tuning_identity_mapping=explicit_f0_identity_mapping,
            evaluation_identity_mapping=explicit_f0_identity_mapping,
            objective=TuningObjective.CURRENT_NLL,
            max_trials=3,
            random_seed=7,
        )


def test_sealed_evaluation_object_cannot_be_directly_constructed(expanded_query_set):
    with pytest.raises(PermissionError, match="issued by an authority"):
        SealedEvaluationQuerySet(
            expanded_query_set,
            protocol_id="forged",
            authority_hmac_sha256="0" * 64,
            _constructor_token=object(),
        )


def test_each_adapter_is_tuned_only_under_its_own_protocol(
    f0_slice, expanded_query_set, explicit_f0_identity_mapping
):
    adapter = _last_seen_adapter()
    candidates = adapter.candidates()
    evaluation_queries, evaluation_mapping = _disjoint_evaluation_copy(
        expanded_query_set, explicit_f0_identity_mapping
    )
    authority = OAMSplitAuthority(secret=b"pytest-split-authority")
    protocol, sealed_evaluation, audit = authority.prepare_protocol(
        protocol_id="last-seen-tuning@0.2",
        adapter=adapter,
        tuning_queries=expanded_query_set,
        evaluation_queries=evaluation_queries,
        tuning_identity_mapping=explicit_f0_identity_mapping,
        evaluation_identity_mapping=evaluation_mapping,
        objective=TuningObjective.CURRENT_NLL,
        max_trials=3,
        random_seed=7,
    )
    assert audit.passed
    selection = tune_baseline_adapter(
        adapter=adapter,
        protocol=protocol,
        run=f0_slice.visible_result,
        tuning_queries=expanded_query_set,
        identity_mapping=explicit_f0_identity_mapping,
        performance_budget=BaselinePerformanceBudget(
            max_queries=100,
            compute_unit=ComputeBudgetUnit.ADAPTER_INVOCATION,
            max_compute_units=100,
            wall_time_compliance_seconds=5.0,
            hardware_profile="pytest-cpu",
        ),
    )

    assert selection.protocol.adapter_id == adapter.adapter_id
    assert len(selection.trials) == 3
    assert selection.selected_candidate in candidates

    certified = authority.certify_tuning_selection(
        selection,
        adapter=adapter,
        tuning_queries=expanded_query_set,
        tuning_identity_mapping=explicit_f0_identity_mapping,
    )

    sealed_score = evaluate_tuned_baseline(
        adapter=adapter,
        certified_selection=certified,
        run=f0_slice.visible_result,
        sealed_evaluation=sealed_evaluation,
        split_authority=authority,
        identity_mapping=evaluation_mapping,
    )
    assert sealed_score.time_grid_query_count == len(evaluation_queries.queries)

    forged_certification = certified.model_copy(update={"authority_hmac_sha256": "0" * 64})
    with pytest.raises(PermissionError, match="authority certification"):
        evaluate_tuned_baseline(
            adapter=adapter,
            certified_selection=forged_certification,
            run=f0_slice.visible_result,
            sealed_evaluation=sealed_evaluation,
            split_authority=authority,
            identity_mapping=evaluation_mapping,
        )

    wrong_protocol = protocol.model_copy(update={"adapter_id": "markov-transition"})
    with pytest.raises(ValueError, match="does not match"):
        tune_baseline_adapter(
            adapter=adapter,
            protocol=wrong_protocol,
            run=f0_slice.visible_result,
            tuning_queries=expanded_query_set,
            identity_mapping=explicit_f0_identity_mapping,
        )


def test_native_habitual_head_can_drive_joint_tuning(
    f0_slice, expanded_query_set, explicit_f0_identity_mapping
):
    adapter = _last_seen_adapter()
    evaluation_queries, evaluation_mapping = _disjoint_evaluation_copy(
        expanded_query_set, explicit_f0_identity_mapping
    )
    authority = OAMSplitAuthority(secret=b"pytest-split-authority")
    protocol, _, _ = authority.prepare_protocol(
        protocol_id="last-seen-joint@0.2",
        adapter=adapter,
        tuning_queries=expanded_query_set,
        evaluation_queries=evaluation_queries,
        tuning_identity_mapping=explicit_f0_identity_mapping,
        evaluation_identity_mapping=evaluation_mapping,
        objective=TuningObjective.JOINT_NLL,
        max_trials=3,
        random_seed=7,
    )

    selection = tune_baseline_adapter(
        adapter=adapter,
        protocol=protocol,
        run=f0_slice.visible_result,
        tuning_queries=expanded_query_set,
        identity_mapping=explicit_f0_identity_mapping,
    )
    assert selection.selected_candidate in adapter.candidates()


def test_tuning_content_and_candidate_grid_are_hash_bound(
    f0_slice, expanded_query_set, explicit_f0_identity_mapping
):
    adapter = _last_seen_adapter()
    evaluation_queries, evaluation_mapping = _disjoint_evaluation_copy(
        expanded_query_set, explicit_f0_identity_mapping
    )
    protocol, _, _ = OAMSplitAuthority(secret=b"pytest-split-authority").prepare_protocol(
        protocol_id="last-seen-hash-bound@0.2",
        adapter=adapter,
        tuning_queries=expanded_query_set,
        evaluation_queries=evaluation_queries,
        tuning_identity_mapping=explicit_f0_identity_mapping,
        evaluation_identity_mapping=evaluation_mapping,
        objective=TuningObjective.CURRENT_NLL,
        max_trials=3,
        random_seed=7,
    )
    mutated = expanded_query_set.model_copy(
        update={"queries": tuple(reversed(expanded_query_set.queries))}
    )
    with pytest.raises(ValueError, match="content does not match"):
        tune_baseline_adapter(
            adapter=adapter,
            protocol=protocol,
            run=f0_slice.visible_result,
            tuning_queries=mutated,
            identity_mapping=explicit_f0_identity_mapping,
        )

    assert protocol.frozen_candidate_grid_sha256 == candidate_grid_sha256(adapter)
