"""S3-DG-13D pinned acquisition -> immutable artifact -> deterministic adapter.

Hugging Face ``datasets`` is used only in the acquisition layer.  Evaluation
reads a content-hashed JSONL artifact through the existing fail-closed adapter;
it never depends on mutable Hub cache state.  Original Parquet shards remain
supported by the sibling ``pyarrow`` adapter.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Iterable, Mapping
from enum import StrEnum
from importlib import import_module
from itertools import islice
from pathlib import Path
from typing import Protocol, cast
from uuid import uuid4

from pydantic import Field, model_validator

from cpswm.contracts.base import ContractModel

from .findingdory import (
    FINDINGDORY_ADAPTER_VERSION,
    FINDINGDORY_DATASET_ID,
    FindingDoryMetadataBatch,
    FindingDoryMetadataRow,
    FindingDorySourceKind,
    adapt_findingdory_rows,
    load_findingdory_jsonl,
)


class FindingDoryAcquisitionBackend(StrEnum):
    HUGGINGFACE_DATASETS = "huggingface_datasets"
    PROVIDED_PINNED_ROWS = "provided_pinned_rows"


class _HuggingFaceDatasetsModule(Protocol):
    def load_dataset(
        self,
        path: str,
        *,
        split: str,
        revision: str,
        streaming: bool,
    ) -> Iterable[Mapping[str, object]]: ...


class FindingDoryLayeredIngressManifest(ContractModel):
    ingress_version: str = "findingdory-layered-ingress@0.1"
    dataset_id: str = FINDINGDORY_DATASET_ID
    dataset_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    source_split: str = Field(min_length=1)
    acquisition_backend: FindingDoryAcquisitionBackend
    normalized_format: str = "jsonl"
    normalized_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalized_row_count: int = Field(ge=0)
    adapter_version: str = FINDINGDORY_ADAPTER_VERSION

    @model_validator(mode="after")
    def _manifest_semantics(self) -> FindingDoryLayeredIngressManifest:
        if self.dataset_id != FINDINGDORY_DATASET_ID:
            raise ValueError("layered ingress is fixed to the official FindingDory dataset ID")
        if self.normalized_format != "jsonl":
            raise ValueError("the first layered ingress projection must be deterministic JSONL")
        if self.adapter_version != FINDINGDORY_ADAPTER_VERSION:
            raise ValueError("layered ingress adapter version is unsupported")
        return self


class FindingDoryLayeredIngressResult(ContractModel):
    manifest: FindingDoryLayeredIngressManifest
    batch: FindingDoryMetadataBatch

    @model_validator(mode="after")
    def _result_semantics(self) -> FindingDoryLayeredIngressResult:
        if self.batch.audit.accepted_rows != self.manifest.normalized_row_count:
            raise ValueError("layered ingress manifest row count does not match the adapter")
        if self.batch.audit.rejected_rows:
            raise ValueError("a pinned layered ingress artifact cannot contain rejected rows")
        return self


def materialize_findingdory_rows(
    rows: Iterable[Mapping[str, object]],
    destination: Path | str,
    *,
    dataset_revision: str,
    source_split: str,
    acquisition_backend: FindingDoryAcquisitionBackend,
) -> FindingDoryLayeredIngressManifest:
    """Validate all rows, then atomically write a canonical JSONL artifact."""

    if re.fullmatch(r"[0-9a-f]{40}", dataset_revision) is None:
        raise ValueError("FindingDory dataset revision must be a pinned 40-character commit SHA")
    if not source_split:
        raise ValueError("FindingDory source split must be non-empty")
    normalized_rows: list[FindingDoryMetadataRow] = []
    raw_rows: list[Mapping[str, object]] = []
    for row in rows:
        raw_rows.append(row)
        normalized_rows.append(FindingDoryMetadataRow.model_validate(row))
    batch = adapt_findingdory_rows(raw_rows, source_split=source_split)
    if batch.audit.rejected_rows or batch.audit.accepted_rows != len(normalized_rows):
        raise ValueError("layered FindingDory acquisition rejected one or more source rows")

    payload = b"".join(
        (
            json.dumps(
                row.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
        for row in normalized_rows
    )
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise FileExistsError(
            "FindingDory normalized artifacts are immutable; choose a new destination"
        )
    temporary = target.with_name(f".{target.name}.tmp-{os.getpid()}-{uuid4().hex}")
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError as exc:
            raise FileExistsError(
                "FindingDory normalized artifacts are immutable; choose a new destination"
            ) from exc
    finally:
        if temporary.exists():
            temporary.unlink()
    return FindingDoryLayeredIngressManifest(
        dataset_revision=dataset_revision,
        source_split=source_split,
        acquisition_backend=acquisition_backend,
        normalized_artifact_sha256=hashlib.sha256(payload).hexdigest(),
        normalized_row_count=len(normalized_rows),
    )


def load_findingdory_layered_artifact(
    path: Path | str,
    manifest: FindingDoryLayeredIngressManifest,
) -> FindingDoryLayeredIngressResult:
    """Verify immutable acquisition metadata before invoking the core adapter."""

    manifest = FindingDoryLayeredIngressManifest.model_validate(manifest.model_dump(mode="python"))
    source = Path(path)
    actual_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    if actual_hash != manifest.normalized_artifact_sha256:
        raise ValueError("FindingDory normalized artifact hash mismatch")
    batch = load_findingdory_jsonl(source, source_split=manifest.source_split)
    if manifest.acquisition_backend is FindingDoryAcquisitionBackend.HUGGINGFACE_DATASETS:
        source_kind = FindingDorySourceKind.PINNED_HUB_ARTIFACT
        batch = batch.model_copy(
            update={
                "records": tuple(
                    record.model_copy(update={"evidence_status": source_kind.value})
                    for record in batch.records
                ),
                "audit": batch.audit.model_copy(
                    update={
                        "source_kind": source_kind,
                        "real_official_rows_ingested": bool(batch.records),
                    }
                ),
            }
        )
    return FindingDoryLayeredIngressResult(manifest=manifest, batch=batch)


def acquire_findingdory_with_datasets(
    destination: Path | str,
    *,
    dataset_revision: str,
    source_split: str,
    max_rows: int | None = None,
) -> FindingDoryLayeredIngressManifest:
    """Acquire a pinned Hub revision with lazy optional dependency loading."""

    if max_rows is not None and max_rows <= 0:
        raise ValueError("FindingDory acquisition max_rows must be positive")
    try:
        datasets_module = cast(
            _HuggingFaceDatasetsModule,
            import_module("datasets"),
        )
    except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "FindingDory Hub acquisition requires the optional datasets dependency"
        ) from exc
    stream = datasets_module.load_dataset(
        FINDINGDORY_DATASET_ID,
        split=source_split,
        revision=dataset_revision,
        streaming=True,
    )
    rows = stream if max_rows is None else islice(stream, max_rows)
    return materialize_findingdory_rows(
        rows,
        destination,
        dataset_revision=dataset_revision,
        source_split=source_split,
        acquisition_backend=FindingDoryAcquisitionBackend.HUGGINGFACE_DATASETS,
    )
