"""Fix 3/4 + B preconditions: the gate controls a real HierarchicalDirichlet
model through a full-state hash, an opportunity-bound write, evidence
de-duplication, and an append-only canonical log.

A rejected consolidation must leave the real M17 model's full-state hash
unchanged; an accepted one changes it.  The audit trail lives in a
tamper-evident hash-chained log, not an in-object list.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from cpswm.contracts import (
    HabitEvidenceSource,
    HabitLearningEvidence,
    ObservationOpportunityRecord,
    SourceType,
)
from cpswm.world_model.habits_transitions import (
    CanonicalWriteLog,
    CauseGatedHabitConsolidation,
    CauseSignalFrame,
    ChangeCause,
    GatedHierarchicalDirichletConsolidator,
    HierarchicalDirichletHabitModel,
    JointCauseFactorizedBOCPD,
    ObservationPropensityCorrector,
)

BASE = datetime(2026, 8, 1, tzinfo=UTC)
L1, L2 = UUID(int=1), UUID(int=2)
OBJ = UUID(int=5)


def _bound_pair(metadata_factory, person):
    opportunity = ObservationOpportunityRecord(
        metadata=metadata_factory(
            schema_name="cpswm.ObservationOpportunityRecord",
            source_type=SourceType.SIMULATION,
        ),
        observation_action_id=uuid4(),
        opportunity_time=BASE,
        selected=True,
        selection_probability=1.0,
        p_visible_given_state=1.0,
        p_detect_given_visible=1.0,
        likelihood_model_id="fixture@0.1",
    )
    evidence = HabitLearningEvidence(
        metadata=opportunity.metadata.model_copy(
            update={"record_id": uuid4(), "schema_name": "cpswm.HabitLearningEvidence"}
        ),
        object_instance_id=OBJ,
        location_id=L1,
        event_time=BASE,
        context_key="weekday|breakfast",
        actor_posterior={str(person): 1.0},
        evidence_source=HabitEvidenceSource.DIRECT_OBSERVATION,
        source_record_ids=(uuid4(),),
        observation_opportunity_id=opportunity.metadata.record_id,
    )
    return opportunity, evidence


def _consolidator(metadata_factory, path=None):
    model = HierarchicalDirichletHabitModel(locations=[L1, L2])
    consolidator = GatedHierarchicalDirichletConsolidator(
        model,
        gate=CauseGatedHabitConsolidation(change_threshold=0.3),
        propensity_corrector=ObservationPropensityCorrector(),
        canonical_log=CanonicalWriteLog(path),
    )
    opportunity, evidence = _bound_pair(metadata_factory, uuid4())
    return consolidator, evidence, opportunity


def _obs_shift_frames():
    return tuple(
        CauseSignalFrame(
            timestamp=BASE + timedelta(days=index),
            signals={
                ChangeCause.OBSERVATION: 0.2 if index < 3 else 0.9,
                ChangeCause.ACTOR: 0.2,
                ChangeCause.HABIT: 0.3,
                ChangeCause.NOISE: 0.1,
            },
        )
        for index in range(6)
    )


def _habit_shift_frames():
    return tuple(
        CauseSignalFrame(
            timestamp=BASE + timedelta(days=index),
            signals={
                ChangeCause.OBSERVATION: 0.2,
                ChangeCause.ACTOR: 0.2,
                ChangeCause.HABIT: 0.2 if index < 3 else 0.9,
                ChangeCause.NOISE: 0.1,
            },
        )
        for index in range(6)
    )


def test_rejected_consolidation_leaves_real_model_hash_unchanged(metadata_factory):
    consolidator, evidence, opportunity = _consolidator(metadata_factory)
    result = JointCauseFactorizedBOCPD().run(_obs_shift_frames(), warmup_steps=2)
    before = consolidator.canonical_parameter_hash()
    for snapshot in result.snapshots:
        assert not consolidator.propose_consolidation(snapshot, evidence, opportunity).accepted
    assert consolidator.canonical_parameter_hash() == before


def test_habit_shift_consolidates_into_the_real_model(metadata_factory):
    consolidator, evidence, opportunity = _consolidator(metadata_factory)
    result = JointCauseFactorizedBOCPD().run(_habit_shift_frames(), warmup_steps=2)
    before = consolidator.canonical_parameter_hash()
    accepted = [
        consolidator.propose_consolidation(snapshot, evidence, opportunity).accepted
        for snapshot in result.snapshots
    ]
    assert any(accepted)
    assert consolidator.canonical_parameter_hash() != before


def test_same_evidence_is_consolidated_at_most_once(metadata_factory):
    consolidator, evidence, opportunity = _consolidator(metadata_factory)
    result = JointCauseFactorizedBOCPD().run(_habit_shift_frames(), warmup_steps=2)
    audits = [
        consolidator.propose_consolidation(snapshot, evidence, opportunity)
        for snapshot in result.snapshots
    ]
    # The habit block may open on several snapshots, but the one evidence record
    # is written exactly once; the rest are duplicate-rejected.
    assert sum(audit.accepted for audit in audits) == 1


def test_opportunity_binding_is_required(metadata_factory):
    consolidator, evidence, _opportunity = _consolidator(metadata_factory)
    other_opportunity, _ = _bound_pair(metadata_factory, uuid4())
    snapshot = JointCauseFactorizedBOCPD().run(_habit_shift_frames(), warmup_steps=2).snapshots[3]
    with pytest.raises(ValueError, match="cite the corrected observation opportunity"):
        consolidator.propose_consolidation(snapshot, evidence, other_opportunity)


def test_canonical_log_is_hash_chained_and_tamper_evident(metadata_factory):
    consolidator, evidence, opportunity = _consolidator(metadata_factory)
    for snapshot in JointCauseFactorizedBOCPD().run(_obs_shift_frames(), warmup_steps=2).snapshots:
        consolidator.propose_consolidation(snapshot, evidence, opportunity)
    log = consolidator.canonical_log
    assert log.entries()
    assert log.verify_chain()
    entries = list(log.entries())
    entries[0] = entries[0].__class__(
        sequence=entries[0].sequence,
        previous_hash=entries[0].previous_hash,
        payload={"accepted": True},  # forged
        entry_hash=entries[0].entry_hash,
    )
    log._entries = entries  # type: ignore[attr-defined]
    assert not log.verify_chain()


def test_persistent_log_fails_closed_on_a_tampered_file(tmp_path, metadata_factory):
    path = tmp_path / "audit.jsonl"
    consolidator, evidence, opportunity = _consolidator(metadata_factory, path)
    for snapshot in JointCauseFactorizedBOCPD().run(_obs_shift_frames(), warmup_steps=2).snapshots:
        consolidator.propose_consolidation(snapshot, evidence, opportunity)
    lines = path.read_text().splitlines()
    assert lines, "expected at least one persisted audit line"
    lines[0] = lines[0].replace('"accepted": false', '"accepted": true')
    path.write_text("\n".join(lines) + "\n")
    with pytest.raises(RuntimeError, match="failed chain verification"):
        CanonicalWriteLog(path)
