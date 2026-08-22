"""DecisionContext belief->action traceability (结构二 §4.6)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from cpswm.contracts import (
    DecisionContext,
    DecisionContextBinding,
    DecisionSurface,
)


def _context():
    return DecisionContext(
        decision_id=uuid4(),
        decision_time=datetime(2026, 8, 22, 9, 0, tzinfo=UTC),
        belief_snapshot_id=uuid4(),
        segment_change_probability=0.7,
        transient_noise_probability=0.1,
        attributed_cause="habit",
        consolidation_ledger_ref="ledger:head@abc",
        model_versions={"cf_bocpd": "joint-cause-factorized-bocpd@0.3"},
        code_version="git:deadbeef",
        rationale="habit regime change attributed and consolidated",
    )


def test_decision_time_must_be_timezone_aware():
    with pytest.raises(ValidationError, match="decision_time"):
        DecisionContext(
            decision_id=uuid4(),
            decision_time=datetime(2026, 8, 22, 9, 0),  # naive
            rationale="x",
        )


def test_probabilities_are_bounded():
    with pytest.raises(ValidationError):
        DecisionContext(
            decision_id=uuid4(),
            decision_time=datetime(2026, 8, 22, 9, 0, tzinfo=UTC),
            segment_change_probability=1.5,
            rationale="x",
        )


def test_binding_attaches_context_to_all_three_surfaces(metadata_factory):
    context = _context()
    task_id, map_id, feedback_id = uuid4(), uuid4(), uuid4()

    task = DecisionContextBinding.for_task_request(
        metadata=metadata_factory(schema_name="cpswm.DecisionContextBinding"),
        task_request_id=task_id,
        decision_context=context,
    )
    snapshot = DecisionContextBinding.for_map_snapshot(
        metadata=metadata_factory(schema_name="cpswm.DecisionContextBinding"),
        map_snapshot_id=map_id,
        decision_context=context,
    )
    feedback = DecisionContextBinding.for_execution_feedback(
        metadata=metadata_factory(schema_name="cpswm.DecisionContextBinding"),
        execution_feedback_id=feedback_id,
        decision_context=context,
    )

    assert task.surface is DecisionSurface.TASK_REQUEST
    assert task.subject_record_id == task_id
    assert snapshot.surface is DecisionSurface.MAP_SNAPSHOT
    assert snapshot.subject_record_id == map_id
    assert feedback.surface is DecisionSurface.EXECUTION_FEEDBACK
    assert feedback.subject_record_id == feedback_id
    # The same belief provenance is traceable across all three surfaces.
    assert {b.decision_context.decision_id for b in (task, snapshot, feedback)} == {
        context.decision_id
    }


def test_binding_is_immutable(metadata_factory):
    binding = DecisionContextBinding.for_task_request(
        metadata=metadata_factory(schema_name="cpswm.DecisionContextBinding"),
        task_request_id=uuid4(),
        decision_context=_context(),
    )
    with pytest.raises(ValidationError):
        binding.subject_record_id = uuid4()  # frozen contract
