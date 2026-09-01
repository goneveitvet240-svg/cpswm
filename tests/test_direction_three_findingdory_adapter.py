from __future__ import annotations

import json
from pathlib import Path

import pytest

from cpswm.system.evaluation_operations.real_data_adapters import findingdory as findingdory_module
from cpswm.system.evaluation_operations.real_data_adapters.findingdory import (
    FINDINGDORY_SCHEMA_FIELDS,
    FINDINGDORY_UNAVAILABLE_FIELDS,
    FindingDoryMetadataRow,
    FindingDorySourceKind,
    adapt_findingdory_rows,
    fetch_findingdory_dataset_viewer_rows,
    load_findingdory_dataset_viewer_export,
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
        "task_id": "task_41",
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


def test_official_string_task_id_is_accepted_and_integer_is_rejected():
    accepted = adapt_findingdory_rows([_row()])
    integer_row = {**_row(), "task_id": 41}
    rejected = adapt_findingdory_rows([integer_row])

    assert accepted.records[0].metadata.task_id == "task_41"
    assert rejected.audit.accepted_rows == 0
    assert rejected.audit.rejected_rows == 1


def test_answer_frame_groups_and_no_answer_marker_are_preserved():
    batch = load_findingdory_jsonl(FIXTURE)

    assert batch.records[1].answer_frame_groups == ((8, 9), (42, 43))
    assert batch.records[2].target_absent
    assert batch.audit.target_absent_rows == 1


def test_official_string_encoded_answer_is_strictly_parsed():
    row = _row()
    row["answer"] = "[[8, 9], [42, 43]]"

    batch = adapt_findingdory_rows([row])

    assert batch.records[0].answer_frame_groups == ((8, 9), (42, 43))

    row["answer"] = "not-json"
    rejected = adapt_findingdory_rows([row])
    assert rejected.audit.rejected_rows == 1
    assert "valid JSON frame groups" in rejected.audit.rejections[0].reason


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


def test_saved_dataset_viewer_export_preserves_source_without_claiming_live_retrieval(
    tmp_path: Path,
):
    payload = {
        "dataset": "yali30/findingdory",
        "config": "default",
        "split": "validation",
        "features": [],
        "rows": [
            {"row_idx": 41, "row": _row(), "truncated_cells": []},
        ],
    }
    path = tmp_path / "findingdory-first-rows.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    batch = load_findingdory_dataset_viewer_export(path)

    assert batch.audit.source_kind is FindingDorySourceKind.DATASET_VIEWER_EXPORT
    assert batch.audit.source_split == "validation"
    assert not batch.audit.real_official_rows_ingested
    assert batch.audit.source_payload_sha256
    assert batch.records[0].evidence_status == "dataset_viewer_export"
    assert not batch.audit.readiness.can_build_full_direction_three_episode


def test_fixed_live_dataset_viewer_fetch_can_attest_transport_source(monkeypatch):
    payload = {
        "features": [],
        "rows": [{"row_idx": 0, "row": _row(), "truncated_cells": []}],
    }

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        @staticmethod
        def read():
            return json.dumps(payload).encode()

    def fake_urlopen(url, *, timeout):
        assert url.startswith("https://datasets-server.huggingface.co/rows?")
        assert "dataset=yali30%2Ffindingdory" in url
        assert timeout == 5.0
        return Response()

    monkeypatch.setattr(findingdory_module, "urlopen", fake_urlopen)
    batch = fetch_findingdory_dataset_viewer_rows(source_split="validation", timeout_seconds=5.0)

    assert batch.audit.source_kind is FindingDorySourceKind.DATASET_VIEWER_LIVE
    assert batch.audit.real_official_rows_ingested


def test_dataset_viewer_export_rejects_wrong_dataset_and_truncated_cells(tmp_path: Path):
    payload = {
        "dataset": "someone/other-data",
        "config": "default",
        "split": "validation",
        "rows": [],
    }
    path = tmp_path / "wrong.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="not yali30/findingdory"):
        load_findingdory_dataset_viewer_export(path)

    payload["dataset"] = "yali30/findingdory"
    payload["rows"] = [
        {"row_idx": 0, "row": _row(), "truncated_cells": ["video"]},
    ]
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="truncated"):
        load_findingdory_dataset_viewer_export(path)


def test_local_jsonl_never_claims_official_real_row_ingestion():
    batch = load_findingdory_jsonl(FIXTURE)

    assert batch.audit.source_kind is FindingDorySourceKind.LOCAL_JSONL
    assert not batch.audit.real_official_rows_ingested
    assert batch.audit.source_payload_sha256
