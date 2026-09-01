"""Fail-closed adapter for the public FindingDory SFT metadata schema.

The eight public metadata columns support video-question and answer-frame
retrieval evaluation. They do not identify object instances, people, rooms,
containers, poses, or pick/place transitions. This adapter records those gaps
instead of inventing values needed by the full direction-three episode schema.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Iterable, Mapping
from enum import StrEnum
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

from pydantic import Field, field_validator, model_validator

from cpswm.contracts import ContractModel

FINDINGDORY_ADAPTER_VERSION = "findingdory-metadata@0.2"
FINDINGDORY_DATASET_ID = "yali30/findingdory"
FINDINGDORY_SCHEMA_FIELDS = frozenset(
    {
        "ep_id",
        "video",
        "question",
        "answer",
        "task_id",
        "high_level_category",
        "low_level_category",
        "num_interactions",
    }
)
FINDINGDORY_UNAVAILABLE_FIELDS = (
    "object_instance_id",
    "actor_id",
    "activity_event_id",
    "source_location",
    "target_location",
    "pose",
    "room",
    "container",
    "visibility",
    "occlusion",
    "distance",
    "candidate_ids",
    "true_target_id",
)
FINDINGDORY_DATASET_URL = "https://huggingface.co/datasets/yali30/findingdory"
FINDINGDORY_PROJECT_URL = "https://findingdorybenchmark.github.io/"
FINDINGDORY_HABITAT_URL = "https://huggingface.co/datasets/findingdory/findingdory-habitat"


class FindingDorySourceKind(StrEnum):
    UNVERIFIED_ROWS = "unverified_rows"
    LOCAL_JSONL = "local_jsonl"
    DATASET_VIEWER_EXPORT = "dataset_viewer_export"
    DATASET_VIEWER_LIVE = "dataset_viewer_live"
    PINNED_HUB_ARTIFACT = "pinned_hub_artifact"
    LOCAL_PARQUET = "local_parquet"


class FindingDoryMetadataRow(ContractModel):
    """The exact eight-column public SFT metadata row."""

    ep_id: str = Field(min_length=1)
    video: str = Field(min_length=1)
    question: str = Field(min_length=1)
    answer: tuple[tuple[int, ...], ...] = Field(min_length=1)
    task_id: str = Field(pattern=r"^task_[0-9]+$")
    high_level_category: str = Field(min_length=1)
    low_level_category: str = Field(min_length=1)
    num_interactions: int = Field(ge=0)

    @field_validator("video", mode="before")
    @classmethod
    def _video_locator_only(cls, value: object) -> object:
        if isinstance(value, Mapping):
            unknown = set(value) - {"path", "bytes"}
            if unknown:
                raise ValueError(f"video mapping has unsupported keys: {sorted(unknown)}")
            path = value.get("path")
            if not isinstance(path, str) or not path:
                raise ValueError("video mapping requires a non-empty path")
            return path
        return value

    @field_validator("answer", mode="before")
    @classmethod
    def _normalize_answer(cls, value: object) -> object:
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError as exc:
                raise ValueError("answer string must contain valid JSON frame groups") from exc
        if not isinstance(value, list | tuple) or not value:
            raise ValueError("answer must be a non-empty nested frame-index sequence")
        groups: list[tuple[int, ...]] = []
        for group in value:
            if not isinstance(group, list | tuple) or not group:
                raise ValueError("each answer frame group must be non-empty")
            if any(not isinstance(frame, int) or isinstance(frame, bool) for frame in group):
                raise ValueError("answer frame indices must be integers")
            groups.append(tuple(group))
        return tuple(groups)

    @model_validator(mode="after")
    def _answer_semantics(self) -> FindingDoryMetadataRow:
        flattened = tuple(frame for group in self.answer for frame in group)
        if -1 in flattened and self.answer != ((-1,),):
            raise ValueError("-1 is valid only as the sole no-answer marker [[-1]]")
        if any(frame < -1 for frame in flattened):
            raise ValueError("answer frame indices cannot be less than -1")
        return self

    @property
    def target_absent(self) -> bool:
        return self.answer == ((-1,),)


class FindingDoryAdaptationRecord(ContractModel):
    """Safe intermediate record; it is deliberately not a full S3 episode."""

    adapter_version: str = FINDINGDORY_ADAPTER_VERSION
    record_id: str = Field(min_length=1)
    source_split: str = Field(min_length=1)
    metadata: FindingDoryMetadataRow
    answer_frame_groups: tuple[tuple[int, ...], ...]
    target_absent: bool
    evidence_status: str = "official_columns_fixture_validated"
    unavailable_fields: tuple[str, ...] = FINDINGDORY_UNAVAILABLE_FIELDS
    semi_synthetic_fields: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _no_fabrication(self) -> FindingDoryAdaptationRecord:
        if self.answer_frame_groups != self.metadata.answer:
            raise ValueError("adapted answer frames must match source metadata")
        if self.target_absent != self.metadata.target_absent:
            raise ValueError("target-absence marker must match source metadata")
        if self.semi_synthetic_fields:
            raise ValueError("metadata adapter must not inject semi-synthetic fields")
        if set(self.unavailable_fields) != set(FINDINGDORY_UNAVAILABLE_FIELDS):
            raise ValueError("all unavailable direction-three fields must remain explicit")
        return self


class FindingDoryRejection(ContractModel):
    row_number: int = Field(ge=1)
    reason: str = Field(min_length=1)


class FindingDoryReadiness(ContractModel):
    can_build_video_question_baseline: bool
    can_build_frame_retrieval_truth: bool
    can_build_instance_transition_model: bool
    can_build_person_event_habit_truth: bool
    can_build_full_direction_three_episode: bool


class FindingDoryMetadataAudit(ContractModel):
    adapter_version: str = FINDINGDORY_ADAPTER_VERSION
    source_split: str
    total_rows: int = Field(ge=0)
    accepted_rows: int = Field(ge=0)
    rejected_rows: int = Field(ge=0)
    unique_episodes: int = Field(ge=0)
    unique_videos: int = Field(ge=0)
    unique_tasks: int = Field(ge=0)
    high_level_category_counts: dict[str, int]
    low_level_category_counts: dict[str, int]
    interaction_count_min: int | None
    interaction_count_max: int | None
    target_absent_rows: int = Field(ge=0)
    field_availability: dict[str, bool]
    readiness: FindingDoryReadiness
    rejections: tuple[FindingDoryRejection, ...]
    source_kind: FindingDorySourceKind = FindingDorySourceKind.UNVERIFIED_ROWS
    source_payload_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    real_official_rows_ingested: bool = False
    source_urls: tuple[str, ...] = (
        FINDINGDORY_DATASET_URL,
        FINDINGDORY_PROJECT_URL,
        FINDINGDORY_HABITAT_URL,
    )
    dataset_license_status: str = "Apache-2.0 on yali30/findingdory dataset card"
    habitat_derivative_license_status: str = "unverified"


class FindingDoryMetadataBatch(ContractModel):
    records: tuple[FindingDoryAdaptationRecord, ...]
    audit: FindingDoryMetadataAudit


def _record_id(row: FindingDoryMetadataRow, source_split: str) -> str:
    payload = json.dumps(
        {
            "source_split": source_split,
            "ep_id": row.ep_id,
            "task_id": row.task_id,
            "question": row.question,
            "video": row.video,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def adapt_findingdory_rows(
    rows: Iterable[Mapping[str, object]],
    *,
    source_split: str = "train",
    source_kind: FindingDorySourceKind = FindingDorySourceKind.UNVERIFIED_ROWS,
    source_payload_sha256: str | None = None,
) -> FindingDoryMetadataBatch:
    """Validate public rows and produce a non-fabricating readiness audit."""

    return _adapt_findingdory_numbered_rows(
        enumerate(rows, start=1),
        source_split=source_split,
        source_kind=source_kind,
        source_payload_sha256=source_payload_sha256,
    )


def _adapt_findingdory_numbered_rows(
    rows: Iterable[tuple[int, Mapping[str, object]]],
    *,
    source_split: str,
    source_kind: FindingDorySourceKind = FindingDorySourceKind.UNVERIFIED_ROWS,
    source_payload_sha256: str | None = None,
) -> FindingDoryMetadataBatch:

    records: list[FindingDoryAdaptationRecord] = []
    rejections: list[FindingDoryRejection] = []
    total = 0
    for row_number, payload in rows:
        total += 1
        fields = set(payload)
        if fields != FINDINGDORY_SCHEMA_FIELDS:
            missing = sorted(FINDINGDORY_SCHEMA_FIELDS - fields)
            extra = sorted(fields - FINDINGDORY_SCHEMA_FIELDS)
            rejections.append(
                FindingDoryRejection(
                    row_number=row_number,
                    reason=f"schema mismatch: missing={missing}, extra={extra}",
                )
            )
            continue
        try:
            metadata = FindingDoryMetadataRow.model_validate(payload)
            records.append(
                FindingDoryAdaptationRecord(
                    record_id=_record_id(metadata, source_split),
                    source_split=source_split,
                    metadata=metadata,
                    answer_frame_groups=metadata.answer,
                    target_absent=metadata.target_absent,
                    evidence_status=source_kind.value,
                )
            )
        except ValueError as error:
            rejections.append(FindingDoryRejection(row_number=row_number, reason=str(error)))

    interactions = [record.metadata.num_interactions for record in records]
    available = {field: field in FINDINGDORY_SCHEMA_FIELDS for field in FINDINGDORY_SCHEMA_FIELDS}
    available.update({field: False for field in FINDINGDORY_UNAVAILABLE_FIELDS})
    audit = FindingDoryMetadataAudit(
        source_split=source_split,
        total_rows=total,
        accepted_rows=len(records),
        rejected_rows=len(rejections),
        unique_episodes=len({record.metadata.ep_id for record in records}),
        unique_videos=len({record.metadata.video for record in records}),
        unique_tasks=len({record.metadata.task_id for record in records}),
        high_level_category_counts=dict(
            Counter(record.metadata.high_level_category for record in records)
        ),
        low_level_category_counts=dict(
            Counter(record.metadata.low_level_category for record in records)
        ),
        interaction_count_min=min(interactions) if interactions else None,
        interaction_count_max=max(interactions) if interactions else None,
        target_absent_rows=sum(record.target_absent for record in records),
        field_availability=dict(sorted(available.items())),
        readiness=FindingDoryReadiness(
            can_build_video_question_baseline=bool(records),
            can_build_frame_retrieval_truth=bool(records),
            can_build_instance_transition_model=False,
            can_build_person_event_habit_truth=False,
            can_build_full_direction_three_episode=False,
        ),
        rejections=tuple(rejections),
        source_kind=source_kind,
        source_payload_sha256=source_payload_sha256,
        real_official_rows_ingested=(
            source_kind
            in {
                FindingDorySourceKind.DATASET_VIEWER_LIVE,
                FindingDorySourceKind.PINNED_HUB_ARTIFACT,
            }
            and bool(records)
        ),
    )
    return FindingDoryMetadataBatch(records=tuple(records), audit=audit)


def load_findingdory_jsonl(
    path: Path | str, *, source_split: str = "train"
) -> FindingDoryMetadataBatch:
    rows: list[tuple[int, Mapping[str, object]]] = []
    parse_rejections: list[FindingDoryRejection] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
                if not isinstance(payload, dict):
                    raise ValueError("row is not a JSON object")
                rows.append((line_number, payload))
            except (json.JSONDecodeError, ValueError) as error:
                parse_rejections.append(
                    FindingDoryRejection(row_number=line_number, reason=str(error))
                )
    source_hash = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    batch = _adapt_findingdory_numbered_rows(
        rows,
        source_split=source_split,
        source_kind=FindingDorySourceKind.LOCAL_JSONL,
        source_payload_sha256=source_hash,
    )
    if not parse_rejections:
        return batch
    audit = batch.audit.model_copy(
        update={
            "total_rows": batch.audit.total_rows + len(parse_rejections),
            "rejected_rows": batch.audit.rejected_rows + len(parse_rejections),
            "rejections": tuple(parse_rejections) + batch.audit.rejections,
        }
    )
    return batch.model_copy(update={"audit": audit})


def load_findingdory_dataset_viewer_export(path: Path | str) -> FindingDoryMetadataBatch:
    """Load one saved Hugging Face Dataset Viewer row response.

    The response must self-identify the exact public dataset/config/split and
    must not contain truncated cells. Saving the HTTP response first keeps the
    network operation outside the deterministic adapter and gives the audit a
    content hash that can be archived with the experiment.
    """

    source = Path(path)
    raw = source.read_bytes()
    payload = json.loads(raw)
    return _adapt_findingdory_dataset_viewer_payload(
        payload,
        raw=raw,
        source_kind=FindingDorySourceKind.DATASET_VIEWER_EXPORT,
    )


def fetch_findingdory_dataset_viewer_rows(
    *,
    source_split: str,
    offset: int = 0,
    length: int = 100,
    timeout_seconds: float = 30.0,
) -> FindingDoryMetadataBatch:
    """Fetch a row slice from the fixed official Dataset Viewer HTTPS endpoint."""

    if offset < 0 or not 1 <= length <= 100:
        raise ValueError("Dataset Viewer offset must be non-negative and length in [1, 100]")
    if timeout_seconds <= 0.0:
        raise ValueError("Dataset Viewer timeout must be positive")
    query = urlencode(
        {
            "dataset": FINDINGDORY_DATASET_ID,
            "config": "default",
            "split": source_split,
            "offset": offset,
            "length": length,
        }
    )
    with urlopen(
        f"https://datasets-server.huggingface.co/rows?{query}",
        timeout=timeout_seconds,
    ) as response:
        raw = response.read()
    payload = json.loads(raw)
    if isinstance(payload, dict):
        payload = {
            **payload,
            "dataset": payload.get("dataset", FINDINGDORY_DATASET_ID),
            "config": payload.get("config", "default"),
            "split": payload.get("split", source_split),
        }
    return _adapt_findingdory_dataset_viewer_payload(
        payload,
        raw=raw,
        source_kind=FindingDorySourceKind.DATASET_VIEWER_LIVE,
    )


def _adapt_findingdory_dataset_viewer_payload(
    payload: object,
    *,
    raw: bytes,
    source_kind: FindingDorySourceKind,
) -> FindingDoryMetadataBatch:
    if not isinstance(payload, dict):
        raise ValueError("dataset viewer export must be a JSON object")
    if payload.get("dataset") != FINDINGDORY_DATASET_ID:
        raise ValueError("dataset viewer export is not yali30/findingdory")
    if payload.get("config") != "default":
        raise ValueError("dataset viewer export must use the default config")
    source_split = payload.get("split")
    if not isinstance(source_split, str) or not source_split:
        raise ValueError("dataset viewer export requires a split")
    exported_rows = payload.get("rows")
    if not isinstance(exported_rows, list):
        raise ValueError("dataset viewer export requires a rows list")
    numbered_rows: list[tuple[int, Mapping[str, object]]] = []
    for position, exported in enumerate(exported_rows, start=1):
        if not isinstance(exported, dict):
            raise ValueError("dataset viewer row envelope must be an object")
        truncated = exported.get("truncated_cells", [])
        if truncated:
            raise ValueError("truncated dataset viewer cells cannot be treated as source rows")
        row = exported.get("row")
        if not isinstance(row, dict):
            raise ValueError("dataset viewer row envelope requires a row object")
        row_idx = exported.get("row_idx")
        row_number = row_idx + 1 if isinstance(row_idx, int) and row_idx >= 0 else position
        numbered_rows.append((row_number, row))
    return _adapt_findingdory_numbered_rows(
        numbered_rows,
        source_split=source_split,
        source_kind=source_kind,
        source_payload_sha256=hashlib.sha256(raw).hexdigest(),
    )


def load_findingdory_parquet(path: Path | str, *, source_split: str) -> FindingDoryMetadataBatch:
    """Read a local FindingDory parquet shard when the optional reader exists.

    Parquet support stays optional so the core CPSWM package does not acquire a
    heavyweight dataframe dependency. The resulting source is deliberately
    labelled ``local_parquet``; provenance cannot be upgraded to an official
    row claim merely because a file has the right columns.
    """

    try:
        import pyarrow.parquet as parquet  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "FindingDory parquet input requires the optional pyarrow dependency"
        ) from exc
    source = Path(path)
    table = parquet.read_table(source)
    if set(table.column_names) != FINDINGDORY_SCHEMA_FIELDS:
        missing = sorted(FINDINGDORY_SCHEMA_FIELDS - set(table.column_names))
        extra = sorted(set(table.column_names) - FINDINGDORY_SCHEMA_FIELDS)
        raise ValueError(f"parquet schema mismatch: missing={missing}, extra={extra}")
    return adapt_findingdory_rows(
        table.to_pylist(),
        source_split=source_split,
        source_kind=FindingDorySourceKind.LOCAL_PARQUET,
        source_payload_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    )
