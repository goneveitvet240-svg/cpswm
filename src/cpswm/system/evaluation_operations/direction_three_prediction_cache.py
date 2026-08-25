"""Split-bound prediction cache for direction-three evidence providers.

GPU/VLM inference is cached before fusion or policy tuning. Cache records carry
only evidence likelihoods and provenance; evaluator truth is structurally
impossible to serialize through this contract.
"""

from __future__ import annotations

import json
from math import isfinite
from pathlib import Path
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from cpswm.contracts import ContractModel, EvidenceChannel
from cpswm.system.evaluation_operations.direction_three_dataset import (
    DirectionThreeDatasetSplit,
    DirectionThreeEpisodeDataset,
)
from cpswm.system.evaluation_operations.report_output import write_report_atomic
from cpswm.system.reproducibility import content_sha256

DIRECTION_THREE_PREDICTION_CACHE_VERSION = "direction-three-predictions@0.1"


class DirectionThreeCachedPrediction(ContractModel):
    episode_id: UUID
    split: DirectionThreeDatasetSplit
    visible_content_hash: str = Field(min_length=1)
    frame_index: int = Field(ge=0)
    candidate_id: UUID
    channel: EvidenceChannel
    likelihood_given_candidate: float = Field(gt=0.0, le=1.0)
    reliability: float = Field(ge=0.0, le=1.0)
    availability: float = Field(ge=0.0, le=1.0)
    identity_embedding: tuple[float, ...] | None = None
    reid_score: float | None = Field(default=None, ge=0.0, le=1.0)
    visibility: float | None = Field(default=None, ge=0.0, le=1.0)
    miss_likelihood: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    model_version: str = Field(min_length=1)
    calibration_domain: str = Field(min_length=1)
    input_content_hash: str = Field(min_length=1)

    @field_validator("identity_embedding")
    @classmethod
    def _finite_embedding(cls, value: tuple[float, ...] | None) -> tuple[float, ...] | None:
        if value is not None and (not value or any(not isfinite(component) for component in value)):
            raise ValueError("identity embedding must be non-empty and finite")
        return value

    @model_validator(mode="after")
    def _provider_semantics(self) -> DirectionThreeCachedPrediction:
        identity_fields = self.identity_embedding is not None or self.reid_score is not None
        if identity_fields and self.channel is not EvidenceChannel.VISUAL:
            raise ValueError("identity embedding and re-ID score are visual evidence only")
        return self


class DirectionThreePredictionEpisodeBinding(ContractModel):
    episode_id: UUID
    split: DirectionThreeDatasetSplit
    visible_content_hash: str = Field(min_length=1)


class DirectionThreePredictionCacheManifest(ContractModel):
    cache_version: str = DIRECTION_THREE_PREDICTION_CACHE_VERSION
    dataset_manifest_hash: str = Field(min_length=1)
    split: DirectionThreeDatasetSplit
    episode_bindings: tuple[DirectionThreePredictionEpisodeBinding, ...] = Field(min_length=1)
    model_versions: dict[EvidenceChannel, str]
    calibration_domains: dict[EvidenceChannel, str]
    inference_config_hash: str = Field(min_length=1)
    record_content_hashes: tuple[str, ...]

    @model_validator(mode="after")
    def _manifest_semantics(self) -> DirectionThreePredictionCacheManifest:
        if self.cache_version != DIRECTION_THREE_PREDICTION_CACHE_VERSION:
            raise ValueError("unsupported direction-three prediction cache version")
        ids = [binding.episode_id for binding in self.episode_bindings]
        if len(ids) != len(set(ids)):
            raise ValueError("cache episode bindings must be unique")
        if any(binding.split is not self.split for binding in self.episode_bindings):
            raise ValueError("cache episode binding crosses the declared split")
        if set(self.model_versions) != set(self.calibration_domains):
            raise ValueError("model version and calibration domain channels must match")
        if any(not value for value in self.model_versions.values()):
            raise ValueError("model versions must be non-empty")
        if any(not value for value in self.calibration_domains.values()):
            raise ValueError("calibration domains must be non-empty")
        return self


class DirectionThreePredictionCache(ContractModel):
    manifest: DirectionThreePredictionCacheManifest
    records: tuple[DirectionThreeCachedPrediction, ...]

    @model_validator(mode="after")
    def _cache_semantics(self) -> DirectionThreePredictionCache:
        bindings = {binding.episode_id: binding for binding in self.manifest.episode_bindings}
        if len(self.records) != len(self.manifest.record_content_hashes):
            raise ValueError("cache manifest must hash every prediction record")
        seen_keys: set[tuple[UUID, int, UUID, EvidenceChannel]] = set()
        for index, record in enumerate(self.records):
            binding = bindings.get(record.episode_id)
            if binding is None:
                raise ValueError("prediction episode is outside the cache split boundary")
            if record.split is not self.manifest.split or record.split is not binding.split:
                raise ValueError("prediction record crosses the cache split boundary")
            if record.visible_content_hash != binding.visible_content_hash:
                raise ValueError("prediction visible-content hash does not match the episode")
            if record.channel not in self.manifest.model_versions:
                raise ValueError("prediction channel is absent from the cache manifest")
            if record.model_version != self.manifest.model_versions[record.channel]:
                raise ValueError("prediction model version does not match the cache manifest")
            if record.calibration_domain != self.manifest.calibration_domains[record.channel]:
                raise ValueError("prediction calibration domain does not match the cache manifest")
            if content_sha256(record) != self.manifest.record_content_hashes[index]:
                raise ValueError("prediction record content hash mismatch")
            key = (record.episode_id, record.frame_index, record.candidate_id, record.channel)
            if key in seen_keys:
                raise ValueError("prediction cache keys must be unique")
            seen_keys.add(key)
        return self


def build_direction_three_prediction_cache(
    dataset: DirectionThreeEpisodeDataset,
    *,
    split: DirectionThreeDatasetSplit,
    records: tuple[DirectionThreeCachedPrediction, ...],
    model_versions: dict[EvidenceChannel, str],
    calibration_domains: dict[EvidenceChannel, str],
    inference_config_hash: str,
) -> DirectionThreePredictionCache:
    entry_by_id = {entry.episode_id: entry for entry in dataset.manifest.entries}
    bindings = tuple(
        DirectionThreePredictionEpisodeBinding(
            episode_id=entry.episode_id,
            split=entry.split,
            visible_content_hash=entry.visible_content_hash,
        )
        for entry in dataset.manifest.entries
        if entry.split is split
    )
    if not bindings:
        raise ValueError(f"dataset contains no episodes for split {split.value}")
    for record in records:
        entry = entry_by_id.get(record.episode_id)
        if entry is None or entry.split is not split:
            raise ValueError("prediction record is not bound to the requested dataset split")
    manifest = DirectionThreePredictionCacheManifest(
        dataset_manifest_hash=content_sha256(dataset.manifest),
        split=split,
        episode_bindings=bindings,
        model_versions=model_versions,
        calibration_domains=calibration_domains,
        inference_config_hash=inference_config_hash,
        record_content_hashes=tuple(content_sha256(record) for record in records),
    )
    return DirectionThreePredictionCache(manifest=manifest, records=records)


def write_direction_three_prediction_cache(
    cache: DirectionThreePredictionCache, path: Path | str, *, force: bool = False
) -> Path:
    output = Path(path)
    repository_root = Path(__file__).resolve().parents[4]
    rendered = json.dumps(cache.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    return write_report_atomic(
        rendered,
        output_path=output,
        config_path=Path(__file__),
        repository_root=repository_root,
        force=force,
    )


def read_direction_three_prediction_cache(path: Path | str) -> DirectionThreePredictionCache:
    return DirectionThreePredictionCache.model_validate_json(Path(path).read_text(encoding="utf-8"))
