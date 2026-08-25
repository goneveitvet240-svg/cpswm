"""The real-data pilot: adapter -> bindings -> arms -> artifacts, end to end.

This is the integration seam.  Each piece is unit-tested elsewhere; what is
asserted here is that they compose without any of them quietly weakening a
guarantee the others depend on -- and that the run produces artifacts someone
else can audit without access to this machine.

Two properties are worth naming.

**Nothing is silently skipped.**  Real logs contain bindings no arm can run on
(one location, three events).  They are reported in the manifest with a reason,
so a pilot that evaluated 4 of 40 objects cannot be mistaken for one that
evaluated 40.

**``full_as_is`` and ``full_raw_clip`` must agree.**  After the 2026-08-24
source fix they read the same score by two different routes -- raw, versus
sigmoid-then-inverted.  Divergence would mean the head is not emitting what the
harness thinks it is, so the pilot carries that consistency check on real data
for free.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cpswm.system.evaluation_operations.dataset_adapters import InMemoryAdapter
from cpswm.system.evaluation_operations.project_one_data_pilot import (
    DATA_PILOT_ARMS,
    LLM_PILOT_ARMS,
    run_data_pilot,
    write_pilot_outputs,
)
from cpswm.system.evaluation_operations.project_one_dataset import ProjectOneDatasetRecord
from cpswm.system.evaluation_operations.project_one_llm_method import (
    FakeLLMClient,
    LLMMethodConfig,
)
from cpswm.system.evaluation_operations.project_one_stream_binding import CandidatePolicy

EPOCH = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)


def _record(index: int, *, object_id: str, location: str) -> ProjectOneDatasetRecord:
    return ProjectOneDatasetRecord(
        stream_id="pilot",
        event_id=f"p{object_id}-{index:03d}",
        subject_id="alice",
        household_id="h1",
        object_id=object_id,
        actor_id="alice",
        timestamp=EPOCH + timedelta(hours=index),
        context_key="morning" if index % 2 == 0 else "evening",
        context_value=0.0 if index % 2 == 0 else 1.0,
        observed_location=location,
        observation_quality=0.9,
    )


def _streams():
    """One evaluable object (cup, moves) and one that never moves (keys)."""

    records: list[ProjectOneDatasetRecord] = []
    for index in range(16):
        records.append(_record(index, object_id="cup", location="table" if index < 10 else "desk"))
        records.append(_record(index, object_id="keys", location="hook"))
    return [
        InMemoryAdapter(records, (), source="test", source_version="0.1").load(
            stream_id="pilot", split="pilot"
        )
    ]


def _llm_config() -> LLMMethodConfig:
    return LLMMethodConfig(model="fake-1", cache=True)


def _fake_client() -> FakeLLMClient:
    reply = json.dumps(
        {
            "next_location_probabilities": {"table": 0.6, "desk": 0.4},
            "change_probability": 0.2,
            "cause": "stable",
            "confidence": 0.7,
        }
    )
    return FakeLLMClient(replies=[reply] * 500)


# ---------------------------------------------------------------------------
# Arms
# ---------------------------------------------------------------------------


def test_the_data_pilot_runs_exactly_the_seven_specified_arms() -> None:
    assert DATA_PILOT_ARMS == (
        "full_as_is",
        "full_raw_clip",
        "no_rls",
        "rls_only",
        "categorical_bocpd",
        "context_frequency",
        "persistence",
    )


def test_the_llm_pilot_adds_exactly_one_arm() -> None:
    assert (*DATA_PILOT_ARMS, "llm_direct") == LLM_PILOT_ARMS


def test_a_run_produces_one_result_per_arm_per_evaluable_binding() -> None:
    report = run_data_pilot(
        streams=_streams(),
        candidate_policy=CandidatePolicy.OBSERVED_ALL,
        allow_leaky_observed_all=True,
    )
    evaluable = [item for item in report.bindings if item.is_evaluable]
    assert len(evaluable) == 1
    assert len(report.results) == len(DATA_PILOT_ARMS)
    assert {result.method for result in report.results} == set(DATA_PILOT_ARMS)


def test_the_llm_arm_appears_only_when_a_client_is_supplied() -> None:
    report = run_data_pilot(streams=_streams(), llm_config=_llm_config(), llm_client=_fake_client())
    assert {result.method for result in report.results} == set(LLM_PILOT_ARMS)


# ---------------------------------------------------------------------------
# Nothing silently skipped
# ---------------------------------------------------------------------------


def test_a_non_evaluable_binding_is_reported_with_a_reason() -> None:
    report = run_data_pilot(
        streams=_streams(),
        candidate_policy=CandidatePolicy.OBSERVED_ALL,
        allow_leaky_observed_all=True,
    )
    skipped = [item for item in report.bindings if not item.is_evaluable]
    assert len(skipped) == 1
    assert skipped[0].key.object_id == "keys"
    assert skipped[0].skip_reason


def test_the_report_accounts_for_every_binding() -> None:
    report = run_data_pilot(streams=_streams())
    assert len(report.bindings) == 2
    evaluated = {result.binding_id for result in report.results}
    reported = {item.binding_id for item in report.bindings if item.is_evaluable}
    assert evaluated == reported


def test_a_stream_with_no_evaluable_binding_fails_loudly() -> None:
    records = [_record(index, object_id="keys", location="hook") for index in range(6)]
    streams = [
        InMemoryAdapter(records, (), source="test", source_version="0.1").load(
            stream_id="pilot", split="pilot"
        )
    ]
    with pytest.raises(ValueError, match="no evaluable"):
        run_data_pilot(
            streams=streams,
            candidate_policy=CandidatePolicy.OBSERVED_ALL,
            allow_leaky_observed_all=True,
        )


# ---------------------------------------------------------------------------
# The post-fix consistency check
# ---------------------------------------------------------------------------


def test_as_is_and_raw_clip_agree_on_real_shaped_data() -> None:
    report = run_data_pilot(streams=_streams())
    by_arm = {result.method: result for result in report.results}
    first = by_arm["full_as_is"].predictions
    second = by_arm["full_raw_clip"].predictions

    assert len(first) == len(second)
    for left, right in zip(first, second, strict=True):
        assert left.change_probability == pytest.approx(right.change_probability, abs=1e-9)
        assert left.habit_signal == pytest.approx(right.habit_signal, abs=1e-9)
        assert left.decision is right.decision


def test_the_report_states_whether_the_two_routes_agreed() -> None:
    report = run_data_pilot(streams=_streams())
    assert report.calibration_consistency["agree"] is True
    assert report.calibration_consistency["max_abs_difference"] == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Artifacts
# ---------------------------------------------------------------------------


def test_it_writes_the_four_required_files(tmp_path: Path) -> None:
    report = run_data_pilot(streams=_streams())
    written = write_pilot_outputs(report, tmp_path)

    for name in ("predictions.jsonl", "metrics.json", "paired.json", "manifest.json"):
        assert (tmp_path / name).exists(), name
    assert written["predictions_sha256"]


def test_metrics_carry_arm_configs_and_config_hashes(tmp_path: Path) -> None:
    report = run_data_pilot(streams=_streams())
    write_pilot_outputs(report, tmp_path)
    metrics = json.loads((tmp_path / "metrics.json").read_text(encoding="utf-8"))

    assert set(metrics["arm_configs"]) == set(DATA_PILOT_ARMS)
    hashes = {name: item["config_hash"] for name, item in metrics["arm_configs"].items()}
    assert len(set(hashes.values())) == len(hashes)


def test_every_prediction_row_carries_its_binding_and_config_hash(tmp_path: Path) -> None:
    report = run_data_pilot(streams=_streams())
    write_pilot_outputs(report, tmp_path)
    rows = [
        json.loads(line)
        for line in (tmp_path / "predictions.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert rows
    for row in rows:
        assert row["binding_id"]
        assert row["method_config_hash"]
        assert row["method"] in DATA_PILOT_ARMS


def test_the_manifest_records_the_dataset_provenance(tmp_path: Path) -> None:
    report = run_data_pilot(
        streams=_streams(),
        candidate_policy=CandidatePolicy.OBSERVED_ALL,
        allow_leaky_observed_all=True,
    )
    write_pilot_outputs(report, tmp_path)
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["stream_manifests"][0]["content_hash"]
    assert manifest["stream_manifests"][0]["source"] == "test"
    assert manifest["bindings"]
    assert any(item["skip_reason"] for item in manifest["bindings"])


def test_llm_usage_and_cost_are_written(tmp_path: Path) -> None:
    report = run_data_pilot(streams=_streams(), llm_config=_llm_config(), llm_client=_fake_client())
    write_pilot_outputs(report, tmp_path)
    metrics = json.loads((tmp_path / "metrics.json").read_text(encoding="utf-8"))

    usage = metrics["llm_usage"]
    assert usage["calls"] >= 1
    assert "estimated_cost_usd" in usage
    assert "total_latency_seconds" in usage
    assert "cache_hits" in usage


def test_no_llm_usage_block_when_no_llm_arm_ran(tmp_path: Path) -> None:
    report = run_data_pilot(streams=_streams())
    write_pilot_outputs(report, tmp_path)
    metrics = json.loads((tmp_path / "metrics.json").read_text(encoding="utf-8"))
    assert metrics.get("llm_usage") is None


def test_paired_rows_reference_the_full_as_is_arm(tmp_path: Path) -> None:
    report = run_data_pilot(streams=_streams())
    write_pilot_outputs(report, tmp_path)
    paired = json.loads((tmp_path / "paired.json").read_text(encoding="utf-8"))
    assert paired
    assert all(row["method"] != "full_as_is" for row in paired)
    assert all(row["reference"] == "full_as_is" for row in paired)


# ---------------------------------------------------------------------------
# Fixed parameters only, this round
# ---------------------------------------------------------------------------


def test_the_pilot_does_no_tuning() -> None:
    """阶段 1 is a fixed-parameter pilot; a search would need its own sealing."""

    import inspect

    source = inspect.getsource(run_data_pilot)
    for forbidden in ("grid", "tune", "budget", "search"):
        assert forbidden not in source.lower()


def test_two_runs_of_the_same_input_agree(tmp_path: Path) -> None:
    first = write_pilot_outputs(run_data_pilot(streams=_streams()), tmp_path / "a")
    second = write_pilot_outputs(run_data_pilot(streams=_streams()), tmp_path / "b")
    assert first["predictions_sha256"] == second["predictions_sha256"]
