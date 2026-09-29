"""Feedback re-execution is semantic; recorded native continuation remains exact."""

import sqlite3
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest
from history_loop_scenario import correction_bundles
from run_correction_replay_comparison import OracleProducer, apply_feedback, build, ingest
from run_history_action_loop import validate_feedback_checkpoint
from test_native_joint_production import JointFixture

from cpswm.system.continuous_state_store import ContinuousStateStore
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput


@pytest.fixture(scope="module")
def pair(tmp_path_factory):
    path = tmp_path_factory.mktemp("feedback-semantic-pair")
    probe, backend, stream, store, builder = build(
        path / "first",
        seed=171,
        source=content_sha256("feedback-reexecution-regression"),
        joint_producer=JointFixture(),
    )
    ingest(probe, backend, stream, produce_joint=True)
    with sqlite3.connect(path / "second") as db:
        store._db.backup(db)
    other_store = ContinuousStateStore(
        path / "second",
        source_identity=store.source_identity,
        dependency_identity=store.dependency_identity,
    )
    other = ContinuousEvidenceInput.resume(
        other_store,
        producer=OracleProducer(),
        context_builder=builder,
        joint_producer=JointFixture(),
    )
    bundles = correction_bundles(probe, stream)
    when = stream._last_cutoff + timedelta(seconds=1)
    apply_feedback(stream, bundles, when)
    apply_feedback(other, bundles, when)
    try:
        yield stream, other
    finally:
        store.close()
        other_store.close()


def test_fresh_internal_ids_preserve_external_semantics_and_do_not_fake_byte_identity(pair):
    first, second = pair
    assert (
        first._system.core.current_snapshot.snapshot_id
        != second._system.core.current_snapshot.snapshot_id
    )
    assert (
        first._system.core._hybrid_loop.ledger.export_state()
        != second._system.core._hybrid_loop.ledger.export_state()
    )
    validate_feedback_checkpoint(first, second)


def test_changed_complete_feedback_fingerprint_cannot_keep_positive_claim(pair, monkeypatch):
    first, second = pair
    altered = dict(second._feedback)
    key = next(iter(altered))
    altered[key] = ("f" * 64, altered[key][1])
    monkeypatch.setattr(second, "_feedback", altered)
    with pytest.raises(ValueError, match="input or action binding"):
        validate_feedback_checkpoint(first, second)


def test_missing_raw_source_is_not_alpha_renaming(pair, monkeypatch):
    first, second = pair
    altered = dict(second._raw)
    altered.pop(next(iter(altered)))
    monkeypatch.setattr(second, "_raw", altered)
    with pytest.raises(ValueError, match="input or action binding"):
        validate_feedback_checkpoint(first, second)


def test_forged_complete_feedback_return_cannot_change_action_location(pair, monkeypatch):
    first, second = pair
    altered = dict(second._feedback)
    key = next(iter(altered))
    fingerprint, original = altered[key]
    altered[key] = (fingerprint, replace(original, suggested_location_id=uuid4()))
    monkeypatch.setattr(second, "_feedback", altered)
    with pytest.raises(ValueError, match="returned consequence"):
        validate_feedback_checkpoint(first, second)


def test_different_memory_values_cannot_be_erased_as_internal_ids(pair, monkeypatch):
    first, second = pair
    core = second._system.core
    values = dict(core._committed_events)
    values.pop(next(iter(values)))
    monkeypatch.setattr(core, "_committed_events", values)
    with pytest.raises(ValueError):
        validate_feedback_checkpoint(first, second)
