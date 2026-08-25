from __future__ import annotations

import json
from pathlib import Path

import pytest

from cpswm.system.evaluation_operations.real_data_adapters.findingdory import (
    FINDINGDORY_SCHEMA_FIELDS,
    FINDINGDORY_UNAVAILABLE_FIELDS,
    FindingDoryMetadataRow,
    adapt_findingdory_rows,
    load_findingdory_jsonl,
)

FIXTURE = (
    Path(__file__).parent / "fixtures" / "direction_three" / "findingdory_metadata_sample.jsonl"
)


def _row() -> dict[str, object]:
    return {
        "ep_id": "ep-001",
        "video": "videos/ep-001.mp4",
        "question": "Where is it?",
        "answer": [[1, 2]],
        "task_id": 1,
        "high_level_category": "retrieval",
        "low_level_category": "single",
        "num_interactions": 1,
    }


def test_exact_official_metadata_columns_are_required():
    row = _row()
    row["actor_id"] = "invented"
    batch = adapt_findingdory_rows([row])

    assert set(_row()) == FINDINGDORY_SCHEMA_FIELDS
    assert batch.audit.accepted_rows == 0
    assert "extra=['actor_id']" in batch.audit.rejections[0].reason


def test_answer_frame_groups_and_no_answer_marker_are_preserved():
    batch = load_findingdory_jsonl(FIXTURE)

    assert batch.records[1].answer_frame_groups == ((8, 9), (42, 43))
    assert batch.records[2].target_absent
    assert batch.audit.target_absent_rows == 1


def test_invalid_mixed_no_answer_marker_is_rejected():
    row = _row()
    row["answer"] = [[-1, 3]]
    batch = adapt_findingdory_rows([row])

    assert batch.audit.rejected_rows == 1
    assert "sole no-answer marker" in batch.audit.rejections[0].reason


def test_metadata_gaps_are_explicit_and_no_semi_synthetic_truth_is_added():
    batch = load_findingdory_jsonl(FIXTURE)

    assert all(
        not batch.audit.field_availability[field] for field in FINDINGDORY_UNAVAILABLE_FIELDS
    )
    assert all(not record.semi_synthetic_fields for record in batch.records)
    assert not batch.audit.readiness.can_build_full_direction_three_episode
    assert not batch.audit.readiness.can_build_person_event_habit_truth


def test_metadata_is_ready_only_for_video_question_and_frame_retrieval_tracks():
    batch = load_findingdory_jsonl(FIXTURE)

    assert batch.audit.accepted_rows == 3
    assert batch.audit.readiness.can_build_video_question_baseline
    assert batch.audit.readiness.can_build_frame_retrieval_truth
    assert not batch.audit.readiness.can_build_instance_transition_model


def test_record_ids_are_stable_and_source_split_sensitive():
    first = adapt_findingdory_rows([_row()], source_split="train")
    repeated = adapt_findingdory_rows([_row()], source_split="train")
    validation = adapt_findingdory_rows([_row()], source_split="validation")

    assert first.records[0].record_id == repeated.records[0].record_id
    assert first.records[0].record_id != validation.records[0].record_id


def test_row_contract_rejects_unknown_fields_even_when_called_directly():
    with pytest.raises(ValueError, match="Extra inputs"):
        FindingDoryMetadataRow.model_validate({**_row(), "true_target_id": "leak"})


def test_jsonl_loader_accounts_for_malformed_lines(tmp_path: Path):
    path = tmp_path / "rows.jsonl"
    path.write_text(json.dumps(_row()) + "\nnot-json\n", encoding="utf-8")

    batch = load_findingdory_jsonl(path)

    assert batch.audit.total_rows == 2
    assert batch.audit.accepted_rows == 1
    assert batch.audit.rejected_rows == 1


def test_jsonl_loader_preserves_source_line_numbers_after_parse_errors(tmp_path: Path):
    invalid_schema = _row()
    invalid_schema["actor_id"] = "not-official"
    path = tmp_path / "rows.jsonl"
    path.write_text(
        "not-json\n" + json.dumps(_row()) + "\n" + json.dumps(invalid_schema) + "\n",
        encoding="utf-8",
    )

    batch = load_findingdory_jsonl(path)

    assert {rejection.row_number for rejection in batch.audit.rejections} == {1, 3}
