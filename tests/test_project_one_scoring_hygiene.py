"""Three scoring defects that only real data would have exposed.

Each of these was invisible on the controlled scenarios and would have produced
a confident, wrong number the first time a real log was scored.  They are
grouped because they share a cause: the synthetic path happens to satisfy an
assumption the code never stated, so nothing complained.

1. **Quiet negative.**  A step with no truth entry fell through into the quiet
   population and could be counted as a false alarm.  Synthetic truth is total,
   so the branch never fired; a real log is mostly unlabelled, and the metric
   would have manufactured a false-alarm rate out of ignorance -- punishing
   whichever arm reacted most.

2. **Split cause vocabulary.**  Scenarios said ``transient``, the injector said
   ``planted_one_shot_disturbance``, and the metric recognised neither of the
   injector's spellings.  Every semi-synthetic ``anomaly_detection_rate`` was
   therefore exactly zero -- an arithmetic certainty that reads like a detector
   failure.

3. **Leaky candidate set.**  Deriving candidates from the whole stream tells an
   arm at step zero which locations will ever appear.  The *cardinality alone*
   leaks: a stable binding presents one candidate, a changing binding two.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from cpswm.system.evaluation_operations.dataset_adapters import InMemoryAdapter
from cpswm.system.evaluation_operations.project_one_dataset import (
    ANOMALY_CAUSES,
    REGIME_CAUSES,
    ChangeCause,
    ProjectOneDatasetRecord,
    ProjectOneGroundTruth,
    ProjectOneTruthSet,
)
from cpswm.system.evaluation_operations.project_one_methods import (
    OPEN_SET_LOCATION,
    ContextFrequencyMethod,
    StepPrediction,
)
from cpswm.system.evaluation_operations.project_one_metrics import compute_metrics
from cpswm.system.evaluation_operations.project_one_protocol import ProjectOneDecision
from cpswm.system.evaluation_operations.project_one_semi_synthetic import (
    InjectionKind,
    inject_changes,
)
from cpswm.system.evaluation_operations.project_one_stream_binding import (
    CandidatePolicy,
    ProjectOneBindingKey,
    ProjectOneMethodFactory,
    bind_stream,
)

EPOCH = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


def _prediction(index: int, *, decision: ProjectOneDecision) -> StepPrediction:
    return StepPrediction(
        event_id=f"e{index:03d}",
        predicted_location_probabilities={"table": 0.7, "desk": 0.3},
        change_probability=1.0 if decision is ProjectOneDecision.HABIT_CHANGE else 0.0,
        predicted_cause=decision.value,
        predicted_regime_id=None,
        habit_signal=1.0 if decision is ProjectOneDecision.HABIT_CHANGE else 0.0,
        rls_residual=None,
        decision=decision,
    )


def _truth(count: int, *, annotated: int, change_labels: bool = True) -> ProjectOneTruthSet:
    """Truth for the first ``annotated`` events only."""

    return ProjectOneTruthSet(
        "s",
        [
            ProjectOneGroundTruth(
                stream_id="s", event_id=f"e{index:03d}", expected_location="table"
            )
            for index in range(annotated)
        ],
        carries_change_labels=change_labels,
    )


def _observed(count: int) -> dict[str, str]:
    """Every event landed on the table -- the self-supervised target."""

    return {f"e{index:03d}": "table" for index in range(count)}


# ---------------------------------------------------------------------------
# 1. Quiet negative
# ---------------------------------------------------------------------------


def test_an_unlabelled_step_is_not_counted_as_a_false_alarm() -> None:
    """The defect, stated as a test: alarms on unlabelled steps must not score."""

    predictions = [_prediction(i, decision=ProjectOneDecision.HABIT_CHANGE) for i in range(10)]
    metrics = compute_metrics(
        method="m",
        stream_id="s",
        predictions=predictions,
        truth=_truth(10, annotated=0),
        observed=_observed(10),
    )
    assert metrics.scored_steps == 0
    assert metrics.unscored_steps == 10
    assert metrics.false_switch_rate == 0.0
    assert metrics.expected_false_candidate_rate == 0.0


def test_only_the_annotated_prefix_enters_the_denominator() -> None:
    predictions = [_prediction(i, decision=ProjectOneDecision.HABIT_CHANGE) for i in range(10)]
    metrics = compute_metrics(
        method="m",
        stream_id="s",
        predictions=predictions,
        truth=_truth(10, annotated=4),
        observed=_observed(10),
    )
    assert metrics.scored_steps == 4
    assert metrics.unscored_steps == 6
    assert metrics.false_switch_rate == 1.0  # all four annotated steps alarmed
    assert metrics.truth_coverage == pytest.approx(0.4)


def test_coverage_is_reported_so_a_sparse_run_cannot_pass_as_complete() -> None:
    predictions = [_prediction(i, decision=ProjectOneDecision.STABLE) for i in range(10)]
    metrics = compute_metrics(
        method="m",
        stream_id="s",
        predictions=predictions,
        truth=_truth(10, annotated=1),
        observed=_observed(10),
    )
    assert metrics.as_dict()["truth_coverage"] == pytest.approx(0.1)


def test_full_truth_can_be_demanded() -> None:
    """Synthetic runs generate truth alongside the data; a gap means a bug."""

    predictions = [_prediction(i, decision=ProjectOneDecision.STABLE) for i in range(5)]
    with pytest.raises(ValueError, match="no truth entry"):
        compute_metrics(
            method="m",
            stream_id="s",
            predictions=predictions,
            truth=_truth(5, annotated=3),
            observed=_observed(5),
            require_full_truth=True,
        )


def test_full_truth_passes_when_every_step_is_annotated() -> None:
    predictions = [_prediction(i, decision=ProjectOneDecision.STABLE) for i in range(5)]
    metrics = compute_metrics(
        method="m",
        stream_id="s",
        predictions=predictions,
        truth=_truth(5, annotated=5),
        observed=_observed(5),
        require_full_truth=True,
    )
    assert metrics.truth_coverage == 1.0


# ---------------------------------------------------------------------------
# 1b. Two tracks: what the data can support, and nothing more
# ---------------------------------------------------------------------------


def test_a_raw_log_reports_no_supervised_metric_at_all() -> None:
    """The raw-data track: every change metric must be ``None``, never zero.

    Zero would read as "this arm produced no false alarms".  The truth is
    "nothing was checkable", and those are opposite claims.
    """

    predictions = [_prediction(i, decision=ProjectOneDecision.HABIT_CHANGE) for i in range(8)]
    metrics = compute_metrics(
        method="m",
        stream_id="s",
        predictions=predictions,
        truth=ProjectOneTruthSet("s", [], carries_change_labels=False),
        observed=_observed(8),
    )
    assert metrics.track == "raw_real_data"
    for name in (
        "expected_false_candidate_rate",
        "false_switch_rate",
        "anomaly_detection_rate",
        "habit_change_confirmation_rate",
        "false_regime_count",
        "paired_margin",
        "log_loss",
        "brier",
    ):
        assert getattr(metrics, name) is None, name


def test_a_raw_log_still_reports_next_location_prediction() -> None:
    """Tier one needs no annotation: the target is the next observation."""

    predictions = [_prediction(i, decision=ProjectOneDecision.STABLE) for i in range(8)]
    metrics = compute_metrics(
        method="m",
        stream_id="s",
        predictions=predictions,
        truth=ProjectOneTruthSet("s", [], carries_change_labels=False),
        observed=_observed(8),
    )
    # Every prediction puts 0.7 on "table" and every observation landed there.
    assert metrics.top1_accuracy == 1.0
    assert metrics.topk_accuracy == 1.0
    assert metrics.observed_log_loss == pytest.approx(-__import__("math").log(0.7))
    assert metrics.observed_brier > 0.0


def test_top1_is_wrong_when_the_arm_favours_the_other_location() -> None:
    predictions = [_prediction(i, decision=ProjectOneDecision.STABLE) for i in range(4)]
    metrics = compute_metrics(
        method="m",
        stream_id="s",
        predictions=predictions,
        truth=ProjectOneTruthSet("s", [], carries_change_labels=False),
        observed={f"e{index:03d}": "desk" for index in range(4)},
    )
    assert metrics.top1_accuracy == 0.0
    assert metrics.topk_accuracy == 1.0  # only two candidates, so top-3 always hits


def test_an_annotated_stream_with_zero_changes_still_reports_them() -> None:
    """``stable_habit`` is annotated *and* has no changes.  That is a result."""

    predictions = [_prediction(i, decision=ProjectOneDecision.STABLE) for i in range(6)]
    metrics = compute_metrics(
        method="m",
        stream_id="s",
        predictions=predictions,
        truth=_truth(6, annotated=6, change_labels=True),
        observed=_observed(6),
    )
    assert metrics.track == "change_labelled"
    assert metrics.false_switch_rate == 0.0
    assert metrics.change_label_count == 0


def test_the_declaration_decides_not_the_contents() -> None:
    """Identical truth entries, opposite reportability -- by declaration alone."""

    predictions = [_prediction(i, decision=ProjectOneDecision.STABLE) for i in range(6)]
    common = {
        "method": "m",
        "stream_id": "s",
        "predictions": predictions,
        "observed": _observed(6),
    }
    labelled = compute_metrics(truth=_truth(6, annotated=6, change_labels=True), **common)
    unlabelled = compute_metrics(truth=_truth(6, annotated=6, change_labels=False), **common)
    assert labelled.false_switch_rate == 0.0
    assert unlabelled.false_switch_rate is None
    # Tier two survives either way -- it needs expected_location, not changes.
    assert labelled.log_loss is not None
    assert unlabelled.log_loss is not None


def test_an_open_set_arm_is_scored_on_the_slot_it_was_offered() -> None:
    """Scoring against the raw location would be a guaranteed miss."""

    from cpswm.system.evaluation_operations.project_one_runner import ProjectOneRunner

    stream, truth = _moving_stream()
    (binding,) = bind_stream(stream, policy=CandidatePolicy.OPEN_SET, train_fraction=0.4)
    method = ContextFrequencyMethod(binding.candidate_locations, open_set=True)
    outcome = ProjectOneRunner().run_arm(method, stream, truth)
    assert outcome.metrics is not None
    # ``desk`` is outside the training prefix, so it scores as the open-set slot
    # rather than as a location the arm never had.
    assert outcome.metrics.top1_accuracy > 0.0


# ---------------------------------------------------------------------------
# 2. One cause vocabulary
# ---------------------------------------------------------------------------


def test_a_private_cause_spelling_is_rejected_at_the_contract() -> None:
    with pytest.raises(ValueError, match="unknown true_change_cause"):
        ProjectOneGroundTruth(
            stream_id="s", event_id="e", true_change_cause="planted_one_shot_disturbance"
        )


def test_a_string_cause_is_normalized_to_the_enum() -> None:
    entry = ProjectOneGroundTruth(stream_id="s", event_id="e", true_change_cause="guest")
    assert entry.true_change_cause is ChangeCause.GUEST


def test_the_two_cause_families_are_disjoint() -> None:
    assert not ANOMALY_CAUSES & REGIME_CAUSES


@pytest.mark.parametrize(
    ("kind", "cause"),
    [
        (InjectionKind.ONE_SHOT_DISTURBANCE, ChangeCause.TRANSIENT),
        (InjectionKind.TEMPORARY_DISTURBANCE, ChangeCause.TRANSIENT),
        (InjectionKind.PERMANENT_CHANGE, ChangeCause.OWNER_HABIT),
        (InjectionKind.RECURRING_REGIME, ChangeCause.REGIME_RECURRENCE),
    ],
)
def test_every_injection_kind_maps_onto_the_shared_vocabulary(
    kind: InjectionKind, cause: ChangeCause
) -> None:
    from cpswm.system.evaluation_operations.project_one_scenarios import build_stream

    stream, truth = build_stream("stable_habit", seed=11)
    result = inject_changes(stream, truth, kinds=(kind,), seed=11)
    (injection,) = result.injections
    assert injection.cause is cause
    # The kind survives as provenance, where it cannot affect scoring.
    assert injection.kind is kind
    assert injection.as_dict()["cause"] == cause.value


def test_an_injected_disturbance_is_now_visible_to_the_anomaly_metric() -> None:
    """Before the vocabularies were merged this rate was structurally zero."""

    from cpswm.system.evaluation_operations.project_one_scenarios import build_stream

    stream, truth = build_stream("stable_habit", seed=11)
    result = inject_changes(stream, truth, kinds=(InjectionKind.ONE_SHOT_DISTURBANCE,), seed=11)
    anomalies = [
        record.event_id
        for record in result.stream.records
        if (entry := result.truth.get(record.event_id)) is not None
        and entry.true_change_cause in ANOMALY_CAUSES
    ]
    assert anomalies, "the injected disturbance must be scoreable as an anomaly"


# ---------------------------------------------------------------------------
# 3. Candidate policy
# ---------------------------------------------------------------------------


def _record(index: int, location: str) -> ProjectOneDatasetRecord:
    return ProjectOneDatasetRecord(
        stream_id="s",
        event_id=f"e{index:03d}",
        subject_id="alice",
        household_id="h1",
        object_id="cup",
        actor_id="alice",
        timestamp=EPOCH + timedelta(hours=index),
        context_key="morning",
        context_value=0.0,
        observed_location=location,
        observation_quality=0.9,
    )


def _moving_stream():
    """Ten days on the table, then ten on the desk: the move is in the tail."""

    records = [_record(i, "table" if i < 10 else "desk") for i in range(20)]
    return InMemoryAdapter(records, (), source="test", source_version="0.1").load(
        stream_id="s", split="pilot"
    )


KEY = ProjectOneBindingKey("h1", "alice", "cup")


def test_observed_all_leaks_the_future_location() -> None:
    """The behaviour being replaced, pinned so the contrast is explicit."""

    stream, _truth = _moving_stream()
    (binding,) = bind_stream(stream, policy=CandidatePolicy.OBSERVED_ALL)
    assert set(binding.candidate_locations) == {"table", "desk"}
    assert binding.location_source == "observed_all"


def test_train_only_sees_only_the_prefix() -> None:
    stream, _truth = _moving_stream()
    (binding,) = bind_stream(stream, policy=CandidatePolicy.TRAIN_ONLY, train_fraction=0.4)
    assert binding.candidate_locations == ("table",)
    assert binding.location_source == "train_only"
    # One candidate is not evaluable -- which is the honest consequence, and
    # exactly why TRAIN_ONLY is paired with OPEN_SET in practice.
    assert binding.is_evaluable is False


def test_open_set_adds_a_bucket_instead_of_leaking_or_crashing() -> None:
    stream, _truth = _moving_stream()
    (binding,) = bind_stream(stream, policy=CandidatePolicy.OPEN_SET, train_fraction=0.4)
    assert binding.candidate_locations == ("table", OPEN_SET_LOCATION)
    assert "desk" not in binding.candidate_locations
    assert binding.is_evaluable is True


def test_the_default_policy_is_open_set_when_nothing_is_declared() -> None:
    stream, _truth = _moving_stream()
    (binding,) = bind_stream(stream)
    assert binding.location_source == "open_set"


def test_the_default_policy_is_manifest_when_one_is_declared() -> None:
    stream, _truth = _moving_stream()
    (binding,) = bind_stream(stream, candidate_locations={KEY: ("table", "desk", "sofa")})
    assert binding.location_source == "manifest"
    assert binding.candidate_locations == ("table", "desk", "sofa")


def test_a_manifest_that_contradicts_the_data_is_still_refused() -> None:
    stream, _truth = _moving_stream()
    with pytest.raises(ValueError, match="omits observed location"):
        bind_stream(
            stream,
            policy=CandidatePolicy.MANIFEST,
            candidate_locations={KEY: ("table",)},
        )


def test_manifest_without_a_manifest_is_a_configuration_error() -> None:
    stream, _truth = _moving_stream()
    with pytest.raises(ValueError, match="needs candidate_locations"):
        bind_stream(stream, policy=CandidatePolicy.MANIFEST)


# ---------------------------------------------------------------------------
# Open-set arms
# ---------------------------------------------------------------------------


def test_an_open_set_arm_routes_an_unseen_location_to_the_bucket() -> None:
    method = ContextFrequencyMethod(("table", OPEN_SET_LOCATION), open_set=True)
    method.observe(_record(0, "table"))
    method.observe(_record(1, "sofa"))
    assert method.snapshot()["open_set_hits"] == 1
    assert method.snapshot()["open_set"] is True


def test_a_closed_arm_still_refuses_an_unseen_location() -> None:
    """Under a declared vocabulary a surprise means the manifest is wrong."""

    method = ContextFrequencyMethod(("table", "desk"))
    method.observe(_record(0, "table"))
    with pytest.raises(ValueError, match="outside the candidate set"):
        method.observe(_record(1, "sofa"))


def test_an_open_set_arm_needs_the_bucket_in_its_candidate_set() -> None:
    with pytest.raises(ValueError, match="OPEN_SET_LOCATION"):
        ContextFrequencyMethod(("table", "desk"), open_set=True)


def test_the_factory_gives_open_set_bindings_open_set_arms() -> None:
    stream, _truth = _moving_stream()
    (binding,) = bind_stream(stream, policy=CandidatePolicy.OPEN_SET, train_fraction=0.4)
    for method in ProjectOneMethodFactory().build(binding):
        assert method.open_set is True


def test_the_factory_gives_manifest_bindings_closed_arms() -> None:
    stream, _truth = _moving_stream()
    (binding,) = bind_stream(stream, candidate_locations={KEY: ("table", "desk")})
    for method in ProjectOneMethodFactory().build(binding):
        assert method.open_set is False


def test_open_set_hits_reset_with_the_arm() -> None:
    method = ContextFrequencyMethod(("table", OPEN_SET_LOCATION), open_set=True)
    method.observe(_record(0, "sofa"))
    assert method.snapshot()["open_set_hits"] == 1
    method.reset()
    assert method.snapshot()["open_set_hits"] == 0


def test_an_injected_out_of_vocabulary_location_no_longer_kills_the_arm() -> None:
    """The concrete failure that surfaced this: the injector plants ``sofa``."""

    from cpswm.system.evaluation_operations.project_one_runner import ProjectOneRunner
    from cpswm.system.evaluation_operations.project_one_scenarios import (
        LOCATIONS,
        build_stream,
    )

    stream, truth = build_stream("stable_habit", seed=3)
    result = inject_changes(stream, truth, kinds=(InjectionKind.ONE_SHOT_DISTURBANCE,), seed=3)
    method = ContextFrequencyMethod((*LOCATIONS, OPEN_SET_LOCATION), open_set=True)
    outcome = ProjectOneRunner().run_arm(method, result.stream, result.truth)
    assert outcome.failure is None
    assert outcome.metrics is not None
