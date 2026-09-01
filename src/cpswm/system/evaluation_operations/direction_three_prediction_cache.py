"""Split-bound prediction cache for direction-three evidence providers.

GPU/VLM inference is cached before fusion or policy tuning. Cache records carry
only evidence likelihoods and provenance; evaluator truth is structurally
impossible to serialize through this contract.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from math import isfinite
from pathlib import Path
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from cpswm.contracts import ContractModel, EvidenceChannel
from cpswm.system.attestation import (
    Attestation,
    Ed25519AttestationSigner,
    Ed25519AttestationVerifier,
    attested_payload,
)
from cpswm.system.evaluation_operations.direction_three_dataset import (
    DirectionThreeDatasetSplit,
    DirectionThreeEpisodeDataset,
)
from cpswm.system.evaluation_operations.raw_data_signatures import (
    RawDataArtifactSignature,
    verify_raw_data_file,
)
from cpswm.system.evaluation_operations.report_output import write_report_atomic
from cpswm.system.reproducibility import content_sha256

DIRECTION_THREE_PREDICTION_CACHE_VERSION = "direction-three-predictions@0.2"
DOMAIN_DIRECTION_THREE_FRAME_MANIFEST = "cpswm.direction_three.frame_manifest.v1"


class DirectionThreeFrameContentBinding(ContractModel):
    episode_id: UUID
    frame_index: int = Field(ge=0)
    source_uri: str = Field(min_length=1)
    source_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    raw_byte_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    preprocessing_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    decoded_input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class DirectionThreeFrameContentManifest(ContractModel):
    dataset_manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    raw_data_signature_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    raw_data_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    split: DirectionThreeDatasetSplit
    producer_run_id: str = Field(min_length=1)
    bindings: tuple[DirectionThreeFrameContentBinding, ...] = Field(min_length=1)
    attestation: Attestation | None = None

    @model_validator(mode="after")
    def _unique_frames(self) -> DirectionThreeFrameContentManifest:
        keys = [(item.episode_id, item.frame_index) for item in self.bindings]
        if len(keys) != len(set(keys)):
            raise ValueError("frame manifest bindings must be unique")
        if any(
            item.source_artifact_sha256 != self.raw_data_content_sha256 for item in self.bindings
        ):
            raise ValueError("frame binding crosses the raw-data content boundary")
        return self


def issue_direction_three_frame_manifest(
    manifest: DirectionThreeFrameContentManifest,
    *,
    raw_data_path: Path | str,
    raw_data_signature: RawDataArtifactSignature,
    raw_data_signature_verifier: Ed25519AttestationVerifier,
    materialize_frame: Callable[[Path, DirectionThreeFrameContentBinding], tuple[bytes, bytes]],
    signer: Ed25519AttestationSigner,
) -> DirectionThreeFrameContentManifest:
    source = Path(raw_data_path).resolve(strict=True)
    verify_raw_data_file(
        source,
        raw_data_signature,
        verifier=raw_data_signature_verifier,
    )
    if manifest.raw_data_signature_sha256 != raw_data_signature.signature_sha256:
        raise ValueError("frame manifest does not bind the verified raw-data signature")
    if manifest.raw_data_content_sha256 != raw_data_signature.content_sha256:
        raise ValueError("frame manifest does not bind the verified raw-data content")
    for binding in manifest.bindings:
        source_locator = binding.source_uri.split("#", maxsplit=1)[0]
        if Path(source_locator).resolve() != source:
            raise ValueError("frame binding source locator does not match signed raw data")
        raw_frame_bytes, decoded_input_bytes = materialize_frame(source, binding)
        if hashlib.sha256(raw_frame_bytes).hexdigest() != binding.raw_byte_sha256:
            raise ValueError("frame manifest raw-frame hash was not reproduced from source")
        if hashlib.sha256(decoded_input_bytes).hexdigest() != binding.decoded_input_sha256:
            raise ValueError("frame manifest decoded-input hash was not reproduced from source")
    unsigned = manifest.model_copy(update={"attestation": None})
    return unsigned.model_copy(
        update={
            "attestation": signer.sign(
                DOMAIN_DIRECTION_THREE_FRAME_MANIFEST,
                attested_payload(unsigned),
            )
        }
    )


def verify_direction_three_frame_manifest(
    manifest: DirectionThreeFrameContentManifest,
    *,
    dataset: DirectionThreeEpisodeDataset,
    split: DirectionThreeDatasetSplit,
    verifier: Ed25519AttestationVerifier,
) -> None:
    if manifest.dataset_manifest_hash != content_sha256(dataset.manifest):
        raise ValueError("frame manifest belongs to a different dataset")
    if manifest.split is not split:
        raise ValueError("frame manifest belongs to a different split")
    verifier.verify(
        DOMAIN_DIRECTION_THREE_FRAME_MANIFEST,
        attested_payload(manifest),
        manifest.attestation,
    )
    episodes = {item.episode_id: item for item in dataset.episodes if item.split is split}
    for binding in manifest.bindings:
        episode = episodes.get(binding.episode_id)
        if episode is None:
            raise ValueError("frame manifest episode is outside the dataset split")
        if not episode.frame_start <= binding.frame_index <= episode.frame_end:
            raise ValueError("frame manifest index is outside the episode interval")


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
    source_name: str = Field(min_length=1)
    source_version: str = Field(min_length=1)
    split: DirectionThreeDatasetSplit
    session_id: str = Field(min_length=1)
    object_instance_ids: tuple[str, ...] = Field(min_length=1)
    source_record_refs: tuple[str, ...] = ()
    visible_content_hash: str = Field(min_length=1)


class DirectionThreePredictionCacheManifest(ContractModel):
    cache_version: str = DIRECTION_THREE_PREDICTION_CACHE_VERSION
    dataset_manifest_hash: str = Field(min_length=1)
    split: DirectionThreeDatasetSplit
    episode_bindings: tuple[DirectionThreePredictionEpisodeBinding, ...] = Field(min_length=1)
    model_versions: dict[EvidenceChannel, str]
    calibration_domains: dict[EvidenceChannel, str]
    inference_config_hash: str = Field(min_length=1)
    frame_content_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
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
    frame_manifest: DirectionThreeFrameContentManifest,
    frame_manifest_verifier: Ed25519AttestationVerifier,
) -> DirectionThreePredictionCache:
    verify_direction_three_frame_manifest(
        frame_manifest,
        dataset=dataset,
        split=split,
        verifier=frame_manifest_verifier,
    )
    frame_bindings = {
        (binding.episode_id, binding.frame_index): binding for binding in frame_manifest.bindings
    }
    entry_by_id = {entry.episode_id: entry for entry in dataset.manifest.entries}
    episode_by_id = {episode.episode_id: episode for episode in dataset.episodes}
    bindings = tuple(
        DirectionThreePredictionEpisodeBinding(
            episode_id=entry.episode_id,
            source_name=entry.source_name,
            source_version=entry.source_version,
            split=entry.split,
            session_id=entry.session_id,
            object_instance_ids=entry.object_instance_ids,
            source_record_refs=entry.source_record_refs,
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
        episode = episode_by_id[record.episode_id]
        if record.candidate_id not in episode.candidate_ids:
            raise ValueError("prediction candidate is outside the episode candidate support")
        if not episode.frame_start <= record.frame_index <= episode.frame_end:
            raise ValueError("prediction frame is outside the episode frame interval")
        frame_binding = frame_bindings.get((record.episode_id, record.frame_index))
        if frame_binding is None:
            raise ValueError("prediction frame is absent from the signed frame manifest")
        if record.input_content_hash != frame_binding.decoded_input_sha256:
            raise ValueError("prediction input hash does not match signed frame content")
    manifest = DirectionThreePredictionCacheManifest(
        dataset_manifest_hash=content_sha256(dataset.manifest),
        split=split,
        episode_bindings=bindings,
        model_versions=model_versions,
        calibration_domains=calibration_domains,
        inference_config_hash=inference_config_hash,
        frame_content_manifest_sha256=content_sha256(frame_manifest),
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


def validate_direction_three_prediction_cache_binding(
    cache: DirectionThreePredictionCache,
    *,
    dataset: DirectionThreeEpisodeDataset,
    split: DirectionThreeDatasetSplit,
    model_versions: dict[EvidenceChannel, str],
    calibration_domains: dict[EvidenceChannel, str],
    inference_config_hash: str,
    frame_manifest: DirectionThreeFrameContentManifest,
    frame_manifest_verifier: Ed25519AttestationVerifier,
) -> DirectionThreePredictionCache:
    """Rebind an internally valid cache to the caller's current external expectations."""

    manifest = cache.manifest
    if manifest.dataset_manifest_hash != content_sha256(dataset.manifest):
        raise ValueError("prediction cache belongs to a different dataset manifest")
    if manifest.split is not split:
        raise ValueError("prediction cache split does not match the requested split")
    verify_direction_three_frame_manifest(
        frame_manifest,
        dataset=dataset,
        split=split,
        verifier=frame_manifest_verifier,
    )
    expected_bindings = tuple(
        DirectionThreePredictionEpisodeBinding(
            episode_id=entry.episode_id,
            source_name=entry.source_name,
            source_version=entry.source_version,
            split=entry.split,
            session_id=entry.session_id,
            object_instance_ids=entry.object_instance_ids,
            source_record_refs=entry.source_record_refs,
            visible_content_hash=entry.visible_content_hash,
        )
        for entry in dataset.manifest.entries
        if entry.split is split
    )
    if manifest.episode_bindings != expected_bindings:
        raise ValueError("prediction cache episode bindings do not match the current dataset")
    if manifest.model_versions != model_versions:
        raise ValueError("prediction cache model versions do not match external expectations")
    if manifest.calibration_domains != calibration_domains:
        raise ValueError("prediction cache calibration domains do not match external expectations")
    if manifest.inference_config_hash != inference_config_hash:
        raise ValueError("prediction cache inference config does not match external expectations")
    if manifest.frame_content_manifest_sha256 != content_sha256(frame_manifest):
        raise ValueError("prediction cache frame manifest does not match external expectations")
    return cache


def read_direction_three_prediction_cache(
    path: Path | str,
    *,
    dataset: DirectionThreeEpisodeDataset,
    split: DirectionThreeDatasetSplit,
    model_versions: dict[EvidenceChannel, str],
    calibration_domains: dict[EvidenceChannel, str],
    inference_config_hash: str,
    frame_manifest: DirectionThreeFrameContentManifest,
    frame_manifest_verifier: Ed25519AttestationVerifier,
) -> DirectionThreePredictionCache:
    cache = DirectionThreePredictionCache.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )
    return validate_direction_three_prediction_cache_binding(
        cache,
        dataset=dataset,
        split=split,
        model_versions=model_versions,
        calibration_domains=calibration_domains,
        inference_config_hash=inference_config_hash,
        frame_manifest=frame_manifest,
        frame_manifest_verifier=frame_manifest_verifier,
    )
