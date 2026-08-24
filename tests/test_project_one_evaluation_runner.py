"""阶段 3 / 阶段 4 acceptance: the scenarios carry exact truth and the runner is fair.

The runner's promise is that any difference between arms is attributable to the
arm.  These tests attack that promise from the sides it could actually fail on:
shared state between arms, shared state between streams, a baseline peeking at
the method under test, a failure being silently swallowed, and cost accounting
that does not exist.
"""

from __future__ import annotations

import json

import pytest

from cpswm.system.evaluation_operations.project_one_dataset import ProjectOneDatasetRecord
from cpswm.system.evaluation_operations.project_one_methods import (
    CategoricalBOCPDMethod,
    ContextFrequencyMethod,
    PersistenceMethod,
    StepPrediction,
    build_first_batch,
)
from cpswm.system.evaluation_operations.project_one_metrics import (
    compute_metrics,
    paired_step_differences,
)
from cpswm.system.evaluation_operations.project_one_protocol import ProjectOneDecision
from cpswm.system.evaluation_operations.project_one_runner import ProjectOneRunner
from cpswm.system.evaluation_operations.project_one_scenarios import (
    LOCATIONS,
    SCENARIO_NAMES,
    build_all_scenarios,
    build_scenario,
    build_stream,
)


def _record_at(index: int, location: str, *, context: str = "morning") -> ProjectOneDatasetRecord:
    from datetime import UTC, datetime, timedelta

    return ProjectOneDatasetRecord(
        stream_id="ctx",
        event_id=f"ctx-{index:03d}",
        subject_id="owner",
        household_id="household-1",
        object_id="cup-17",
        actor_id="owner",
        timestamp=datetime(2026, 4, 1, tzinfo=UTC) + timedelta(hours=12 * index),
        context_key=context,
        context_value=0.0 if context == "morning" else 1.0,
        observed_location=location,
        observation_quality=0.9,
    )


def _alternating_records(*, cycles: int) -> list[ProjectOneDatasetRecord]:
    """Morning -> dining table, evening -> desk.  Balcony is never visited."""

    records: list[ProjectOneDatasetRecord] = []
    for cycle in range(cycles):
        records.append(_record_at(2 * cycle, "dining_table", context="morning"))
        records.append(_record_at(2 * cycle + 1, "desk", context="evening"))
    return records


def _arms():  # type: ignore[no-untyped-def]
    return build_first_batch(
        locations=LOCATIONS,
        owner_id="owner",
        household_id="household-1",
        object_id="cup-17",
    )


# ---------------------------------------------------------------------------
# 阶段 3: the controlled scenarios
# ---------------------------------------------------------------------------


def test_all_ten_capabilities_are_covered() -> None:
    assert len(SCENARIO_NAMES) == 10
    assert set(SCENARIO_NAMES) == {
        "stable_habit",
        "periodic_habit",
        "short_disturbance",
        "permanent_change",
        "recurring_regime",
        "context_change",
        "missing_observations",
        "biased_observation",
        "gradual_drift",
        "abrupt_change",
    }


@pytest.mark.parametrize("name", SCENARIO_NAMES)
def test_every_scenario_is_deterministic(name: str) -> None:
    assert build_scenario(name).days == build_scenario(name).days
    first, _ = build_stream(name)
    second, _ = build_stream(name)
    assert first.manifest.content_hash == second.manifest.content_hash


@pytest.mark.parametrize("name", SCENARIO_NAMES)
def test_every_event_has_exact_truth(name: str) -> None:
    stream, truth = build_stream(name)
    assert len(truth) == len(stream)
    for record in stream:
        entry = truth.get(record.event_id)
        assert entry is not None
        assert entry.expected_location in LOCATIONS
        assert entry.true_regime_id is not None


def test_no_false_alarm_scenario_declares_a_change_point() -> None:
    """Stable, periodic, context-switch, gap and bias runs must be change-free."""

    for name in (
        "stable_habit",
        "periodic_habit",
        "context_change",
        "missing_observations",
        "biased_observation",
        "short_disturbance",
    ):
        _, truth = build_stream(name)
        stream, _ = build_stream(name)
        changes = [
            record.event_id
            for record in stream
            if (entry := truth.get(record.event_id)) is not None and entry.true_change_point
        ]
        assert changes == [], name


@pytest.mark.parametrize(
    ("name", "expected_changes"),
    [("permanent_change", 1), ("abrupt_change", 1), ("gradual_drift", 1), ("recurring_regime", 2)],
)
def test_change_scenarios_declare_the_right_number_of_change_points(
    name: str, expected_changes: int
) -> None:
    stream, truth = build_stream(name)
    changes = sum(
        1
        for record in stream
        if (entry := truth.get(record.event_id)) is not None and entry.true_change_point
    )
    assert changes == expected_changes


def test_the_recurring_scenario_returns_to_its_first_regime() -> None:
    stream, truth = build_stream("recurring_regime")
    regimes = [
        truth.get(record.event_id).true_regime_id  # type: ignore[union-attr]
        for record in stream
    ]
    assert regimes[0] == "regime-0"
    assert "regime-1" in regimes
    assert regimes[-1] == "regime-0"


def test_the_short_disturbance_is_an_anomaly_not_a_regime() -> None:
    stream, truth = build_stream("short_disturbance")
    causes = [truth.get(record.event_id).true_change_cause for record in stream]  # type: ignore[union-attr]
    assert causes.count("transient") == 1
    assert all(
        truth.get(record.event_id).true_regime_id == "regime-0"  # type: ignore[union-attr]
        for record in stream
    )


# ---------------------------------------------------------------------------
# 阶段 4: the runner is fair
# ---------------------------------------------------------------------------


def test_every_arm_sees_the_same_events_in_the_same_order() -> None:
    stream, truth = build_stream("permanent_change")
    report = ProjectOneRunner().run(streams=[(stream, truth)], build_methods=_arms)
    expected = [record.event_id for record in stream]
    for result in report.results:
        assert [prediction.event_id for prediction in result.predictions] == expected


def test_arms_do_not_leak_state_between_streams() -> None:
    """Running two streams together must equal running each alone."""

    first = build_stream("stable_habit")
    second = build_stream("permanent_change")
    runner = ProjectOneRunner()

    together = runner.run(streams=[first, second], build_methods=_arms)
    alone_first = runner.run(streams=[first], build_methods=_arms)
    alone_second = runner.run(streams=[second], build_methods=_arms)

    combined = {(r.method, r.stream_id): r for r in together.results}
    for solo in (*alone_first.results, *alone_second.results):
        paired = combined[(solo.method, solo.stream_id)]
        assert [p.decision for p in paired.predictions] == [p.decision for p in solo.predictions]
        assert paired.metrics == solo.metrics


def test_each_stream_gets_freshly_built_arms() -> None:
    built: list[int] = []

    def build():  # type: ignore[no-untyped-def]
        built.append(1)
        return _arms()

    streams = list(build_all_scenarios(["stable_habit", "abrupt_change"]))
    ProjectOneRunner().run(streams=streams, build_methods=build)
    assert len(built) == len(streams)


def test_a_failing_arm_is_recorded_with_the_offending_event() -> None:
    class _Exploding:
        name = "exploding"

        def reset(self) -> None:
            self._seen = 0

        def observe(self, event: ProjectOneDatasetRecord) -> StepPrediction:
            self._seen += 1
            if self._seen == 3:
                raise RuntimeError("boom")
            return StepPrediction(
                event_id=event.event_id,
                predicted_location_probabilities={},
                change_probability=0.0,
                predicted_cause="stable",
                predicted_regime_id=None,
                habit_signal=0.0,
                rls_residual=None,
                decision=ProjectOneDecision.STABLE,
            )

        def snapshot(self) -> dict[str, object]:
            return {"seen": self._seen}

        def config_payload(self) -> dict[str, object]:
            return {"kind": "exploding"}

        def config_hash(self) -> str:
            return "0" * 64

    stream, truth = build_stream("stable_habit")
    result = ProjectOneRunner().run_arm(_Exploding(), stream, truth)  # type: ignore[arg-type]
    assert result.failure is not None
    assert result.failure.error_type == "RuntimeError"
    assert result.failure.event_id == stream.records[2].event_id
    assert result.failure.snapshot["seen"] == 3
    assert result.metrics is None


def test_cost_accounting_is_populated() -> None:
    stream, truth = build_stream("gradual_drift")
    report = ProjectOneRunner().run(streams=[(stream, truth)], build_methods=_arms)
    for result in report.results:
        assert result.elapsed_seconds >= 0.0
        assert result.peak_memory_bytes > 0
        assert result.state_size_bytes > 0


def test_predictions_are_written_step_by_step(tmp_path) -> None:  # type: ignore[no-untyped-def]
    stream, truth = build_stream("abrupt_change")
    report = ProjectOneRunner().run(streams=[(stream, truth)], build_methods=_arms)
    path = tmp_path / "predictions.jsonl"
    digest = ProjectOneRunner.write_predictions(report, path)

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == sum(len(result.predictions) for result in report.results)
    assert {row["method"] for row in rows} == {result.method for result in report.results}
    assert digest == ProjectOneRunner.write_predictions(report, tmp_path / "again.jsonl")

    chain_rows = [row for row in rows if row["method"] == "full"]
    assert all("trace" in row for row in chain_rows)
    assert set(chain_rows[0]["trace"]) == {
        "dirichlet_surprise",
        "rls_residual",
        "habit_signal",
        "change_probability",
        "ccrr_decision",
        "active_regime",
    }


# ---------------------------------------------------------------------------
# Baselines behave like baselines
# ---------------------------------------------------------------------------


def test_baselines_have_no_residual_channel() -> None:
    stream, truth = build_stream("stable_habit")
    runner = ProjectOneRunner()
    for method in (
        PersistenceMethod(LOCATIONS),
        ContextFrequencyMethod(LOCATIONS),
        CategoricalBOCPDMethod(LOCATIONS),
    ):
        result = runner.run_arm(method, stream, truth)
        assert result.failure is None
        assert all(prediction.rls_residual is None for prediction in result.predictions)


def test_categorical_bocpd_run_length_collapses_on_an_abrupt_change() -> None:
    stream, truth = build_stream("abrupt_change")
    result = ProjectOneRunner().run_arm(CategoricalBOCPDMethod(LOCATIONS), stream, truth)
    probabilities = [prediction.change_probability for prediction in result.predictions]
    # Day 11 is the first day at the new location.
    assert probabilities[11] > probabilities[9]


def test_categorical_bocpd_ranks_locations_a_binary_detector_cannot() -> None:
    """A moved/not-moved bit cannot separate 'sometimes seen here' from 'never seen'.

    The morning context is mostly the dining table but occasionally the desk;
    the balcony never appears.  A categorical model must rank all three, which
    a binary move indicator has no representation for.
    """

    method = CategoricalBOCPDMethod(LOCATIONS)
    method.reset()
    for cycle in range(10):
        morning_location = "desk" if cycle % 4 == 3 else "dining_table"
        method.observe(_record_at(2 * cycle, morning_location, context="morning"))
        method.observe(_record_at(2 * cycle + 1, "desk", context="evening"))

    morning = method._predict(_record_at(20, "dining_table", context="morning"))
    assert morning["dining_table"] > morning["desk"] > morning["balcony"]


def test_categorical_bocpd_conditions_on_context() -> None:
    method = CategoricalBOCPDMethod(LOCATIONS)
    method.reset()
    for record in _alternating_records(cycles=8):
        method.observe(record)

    morning = method._predict(_record_at(16, "dining_table", context="morning"))
    evening = method._predict(_record_at(16, "dining_table", context="evening"))
    assert morning["dining_table"] > evening["dining_table"]
    assert evening["desk"] > morning["desk"]


def test_persistence_never_reports_a_change_on_a_stable_stream() -> None:
    stream, truth = build_stream("stable_habit")
    result = ProjectOneRunner().run_arm(PersistenceMethod(LOCATIONS), stream, truth)
    assert all(
        prediction.decision is ProjectOneDecision.STABLE for prediction in result.predictions
    )


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def test_metrics_are_computed_from_steps_not_from_self_report() -> None:
    stream, truth = build_stream("permanent_change")
    result = ProjectOneRunner().run_arm(_arms()[0], stream, truth)
    assert result.metrics is not None
    recomputed = compute_metrics(
        method=result.method,
        stream_id=result.stream_id,
        predictions=result.predictions,
        truth=truth,
        confirmation_window=3,
    )
    assert recomputed == result.metrics


def test_paired_differences_are_aligned_on_event_id() -> None:
    stream, truth = build_stream("permanent_change")
    runner = ProjectOneRunner()
    arms = _arms()
    full = runner.run_arm(arms[0], stream, truth)
    no_rls = runner.run_arm(arms[1], stream, truth)
    rows = paired_step_differences(full.predictions, no_rls.predictions)
    assert len(rows) == len(stream)
    assert all(set(row) == {"habit_signal", "change_probability"} for row in rows)


def test_paired_differences_reject_misaligned_arms() -> None:
    stream, truth = build_stream("permanent_change")
    runner = ProjectOneRunner()
    full = runner.run_arm(_arms()[0], stream, truth)
    with pytest.raises(ValueError, match="same number of steps"):
        paired_step_differences(full.predictions, full.predictions[:-1])


def test_a_stable_stream_produces_no_confirmed_change_for_the_full_arm() -> None:
    stream, truth = build_stream("stable_habit")
    result = ProjectOneRunner().run_arm(_arms()[0], stream, truth)
    assert result.metrics is not None
    assert result.metrics.false_switch_rate == 0.0


# ---------------------------------------------------------------------------
# Prediction timing: no arm may score itself on an event it has already learned
# ---------------------------------------------------------------------------


def _final_prediction(method, records, final):  # type: ignore[no-untyped-def]
    method.reset()
    for record in records:
        method.observe(record)
    return method.observe(final)


@pytest.mark.parametrize(
    "index",
    range(7),
    ids=[
        "full",
        "no_rls",
        "shuffled_rls",
        "rls_only",
        "categorical_bocpd",
        "context_frequency",
        "persistence",
    ],
)
def test_no_arm_peeks_at_the_event_it_is_scored_on(index: int) -> None:
    """The generic leakage check.

    Two runs that share a prefix and differ only in the *final* event's
    location must produce the *same* ``predicted_location_probabilities`` on
    that final step.  A prediction that changes with the observed location was
    made after learning from it, which makes its log-loss meaningless.
    """

    records = _alternating_records(cycles=8)
    expected = _final_prediction(_arms()[index], records, _record_at(16, "dining_table"))
    anomalous = _final_prediction(_arms()[index], records, _record_at(16, "balcony"))
    assert dict(expected.predicted_location_probabilities) == dict(
        anomalous.predicted_location_probabilities
    )


@pytest.mark.parametrize(
    "index",
    range(7),
    ids=[
        "full",
        "no_rls",
        "shuffled_rls",
        "rls_only",
        "categorical_bocpd",
        "context_frequency",
        "persistence",
    ],
)
def test_every_arm_reports_a_config_and_a_hash(index: int) -> None:
    arm = _arms()[index]
    payload = arm.config_payload()
    assert payload
    assert "kind" in payload
    assert len(arm.config_hash()) == 64


def test_arm_config_and_hash_reach_the_run_result() -> None:
    stream, truth = build_stream("stable_habit")
    report = ProjectOneRunner().run(streams=[(stream, truth)], build_methods=_arms)
    for result in report.results:
        assert result.method_config
        assert len(result.method_config_hash) == 64
        assert result.snapshot["config_hash"] == result.method_config_hash


def test_the_four_chain_arms_carry_four_distinct_hashes() -> None:
    hashes = {arm.name: arm.config_hash() for arm in _arms()[:4]}
    assert len(set(hashes.values())) == 4


def test_the_rls_regularization_field_actually_reaches_the_head() -> None:
    """It was declared and unused before v0.2; a dead knob cannot be tuned."""

    from dataclasses import replace as dataclass_replace

    from cpswm.system.evaluation_operations.project_one_methods import CoreHabitChainMethod
    from cpswm.system.evaluation_operations.project_one_protocol import (
        ProjectOneProtocolConfig,
    )

    records = _alternating_records(cycles=8)
    signals = []
    for ridge in (1e-6, 10.0):
        arm = CoreHabitChainMethod(
            name="probe",
            locations=LOCATIONS,
            owner_id="owner",
            household_id="household-1",
            object_id="cup-17",
            config=dataclass_replace(ProjectOneProtocolConfig(), rls_regularization=ridge),
        )
        # Probe a location the head has actually fitted; an unseen location has
        # no model at all, so no ridge value could change its score.
        probe = _record_at(16, "dining_table", context="morning")
        signals.append(_final_prediction(arm, records, probe).rls_residual)
    assert signals[0] != signals[1]
