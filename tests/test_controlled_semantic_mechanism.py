"""Actual P5 oracle fixtures; these are not natural-perception acceptance tests."""

import sqlite3
import sys
from dataclasses import replace
from pathlib import Path
from uuid import UUID, uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from run_controlled_semantic_mechanism import OracleProducer, run_case, source_identity

from cpswm.system.continual.project_one_feedback import EventRevisionKind, EventRevisionOutcome
from cpswm.system.continuous_state_store import ContinuousStateStore
from cpswm.system.prototype_spine import DerivedEvidenceLifecycle
from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput


@pytest.fixture(scope="module")
def controlled_results(tmp_path_factory):
    root = tmp_path_factory.mktemp("controlled-semantic")
    source, _ = source_identity()
    results = {}
    for variant in ("oracle_complete", "missing_and_ambiguous"):
        results[variant] = run_case(root / variant, variant=variant, source=source)
        results[variant]["artifact_directory"] = root / variant
    return results


def test_registered_p5_retracts_and_recovery_preserves_semantic_results(controlled_results):
    for result in controlled_results.values():
        assert result["execution_lane"] == "registered_p5_first"
        assert result["retraction_targets"]
        assert result["all_targets_absent_from_committed"]
        assert result["all_targets_absent_from_observed"]
        assert result["all_feedback_consumed"]
        assert result["recovery_then_rebuild_equal"]
        assert result["targets_inactive_after_recovery_rebuild"]
        assert result["distribution_changed"]
        assert result["recovery_before_equal"]
        assert result["recovery_after_equal"]
        assert result["recovery_feedback_equal"]
        assert result["after"]["full_rerun_equivalent"]
        assert result["physical_executions"] == 0
        assert not result["empirical_feedback_calibration"]
        executed = [row for row in result["steps"] if "path" in row]
        assert all(row["path"] == "P5_FULL_EAGER" for row in executed)
        assert all(row["hypotheses"] > 1 for row in executed)
        assert all(row["executed_operators"] >= 7 for row in executed)
        assert all(row["ciav_receipt"] for row in executed)
        assert any(row.get("operations") == ["retract"] for row in result["feedback"])
        assert all(row["status"] == "CONSUMED" for row in result["feedback"])


def test_missing_semantics_do_not_write_or_invoke_core(controlled_results):
    result = controlled_results["missing_and_ambiguous"]
    missing = [row for row in result["steps"] if row["injected_missing"]]
    assert [row["index"] for row in missing] == [2, 5]
    assert all(row["status"] == "INSUFFICIENT_SEMANTIC_EVIDENCE" for row in missing)
    assert all(row["core_unchanged"] for row in missing)
    assert result["before"]["execution_traces"] == 10
    assert controlled_results["oracle_complete"]["before"]["execution_traces"] == 12
    no_evidence = [row for row in result["steps"] if row["injected_no_role_actor_evidence"]]
    assert [row["index"] for row in no_evidence] == [3, 6]
    for row in no_evidence:
        comparison = controlled_results["oracle_complete"]["steps"][row["index"]]
        assert row["actor_posterior"] != comparison["actor_posterior"]


@pytest.fixture
def retained_core(controlled_results):
    """Reload the already-computed real P5 history; no repeated scenario execution."""
    path = controlled_results["oracle_complete"]["artifact_directory"] / "uninterrupted.db"
    with sqlite3.connect(path) as database:
        source, dependencies = database.execute(
            "SELECT source,dependencies FROM deployment"
        ).fetchone()
    store = ContinuousStateStore(path, source_identity=source, dependency_identity=dependencies)
    stream = ContinuousEvidenceInput.resume(
        store, producer=OracleProducer(), context_builder=lambda *args: None
    )
    yield stream._system
    store.close()


def _outcome(target, *, correction=False, location=None):
    return EventRevisionOutcome(
        kind=EventRevisionKind.CORRECT if correction else EventRevisionKind.RETRACT,
        superseded_revision_id=target,
        evidence_source_record_ids=(uuid4(),),
        rationale="explicit boundary fixture; not calibrated natural evidence",
        corrected_revision_id=uuid4() if correction else None,
        corrected_location_id=location if correction else None,
        corrected_owner_mass=0.5 if correction else None,
    )


@pytest.mark.parametrize("boundary", ["unpublished", "already_removed", "correct_demoted"])
def test_retraction_does_not_expand_binding_or_correction_authority(
    retained_core, controlled_results, boundary
):
    system, core = retained_core, retained_core.core
    if boundary == "already_removed":
        target = UUID(controlled_results["oracle_complete"]["retraction_targets"][0])
        assert core.published_revision_bindings(target)
        assert target not in core._observed_events
    else:
        target = next(iter(core._committed_events))
        event = core._committed_events.pop(target)
        assert target in core._observed_events
        if boundary == "unpublished":
            core._revision_binding_history.pop(target, None)
            assert not core.published_revision_bindings(target)
    before = system.adaptive_router_state_sha256()
    outcome = _outcome(
        target,
        correction=boundary == "correct_demoted",
        location=event.location_id if boundary == "correct_demoted" else None,
    )
    with pytest.raises(KeyError, match="not a committed prototype event"):
        core.apply_event_revision_outcome(outcome)
    assert system.adaptive_router_state_sha256() == before


def _add_suspended_archived_chain(core):
    parent = next(iter(core._committed_events.values()))
    first, second = uuid4(), uuid4()
    for revision, ancestor in ((first, parent.revision_id), (second, first)):
        core._derived_event_archive[revision] = replace(
            parent, revision_id=revision, derived_from_revision_id=ancestor
        )
        core._derived_event_lifecycle[revision] = (
            DerivedEvidenceLifecycle.SUSPENDED_PARENT_QUARANTINED
        )
    return parent.revision_id, (first, second)


def test_retraction_tombstones_suspended_archived_descendants(retained_core):
    core = retained_core.core
    parent, descendants = _add_suspended_archived_chain(core)
    core.apply_event_revision_outcome(_outcome(parent))
    core._rebuild_personalized_models()
    assert parent not in core._observed_events
    for revision in descendants:
        assert (
            core._derived_event_lifecycle[revision]
            is DerivedEvidenceLifecycle.TOMBSTONED_ANCESTOR_INVALIDATED
        )
        assert revision not in core._committed_events
        assert revision not in core._observed_events


def test_retraction_failure_restores_core_and_archive_lifecycle(retained_core, monkeypatch):
    system, core = retained_core, retained_core.core
    parent, descendants = _add_suspended_archived_chain(core)

    def fail(stage):
        if stage == "dirichlet":
            raise RuntimeError("controlled rebuild fault")

    monkeypatch.setattr(core, "_revision_fault_hook", fail)
    # Runtime identity includes instance attribute names, including the injected hook.
    before = system.adaptive_router_state_sha256()
    with pytest.raises(RuntimeError, match="controlled rebuild fault"):
        core.apply_event_revision_outcome(_outcome(parent))
    assert system.adaptive_router_state_sha256() == before
    assert parent in core._committed_events
    assert parent in core._observed_events
    assert all(
        core._derived_event_lifecycle[revision]
        is DerivedEvidenceLifecycle.SUSPENDED_PARENT_QUARANTINED
        for revision in descendants
    )
