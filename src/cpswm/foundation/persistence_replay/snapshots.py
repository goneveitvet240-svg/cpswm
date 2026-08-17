"""Snapshot metadata catalog for M03 A0."""

from __future__ import annotations

from uuid import UUID

from .contracts import SnapshotManifest


class SnapshotCatalog:
    def __init__(self) -> None:
        self._snapshots: dict[UUID, SnapshotManifest] = {}

    def add(self, manifest: SnapshotManifest) -> None:
        existing = self._snapshots.get(manifest.snapshot_id)
        if existing is not None and existing != manifest:
            raise ValueError("snapshot_id already exists with different metadata")
        self._snapshots[manifest.snapshot_id] = manifest

    def get(self, snapshot_id: UUID) -> SnapshotManifest:
        return self._snapshots[snapshot_id]

    def invalidate(self, snapshot_id: UUID, *, reason: str) -> SnapshotManifest:
        if not reason:
            raise ValueError("snapshot invalidation requires a reason")
        current = self._snapshots[snapshot_id]
        reasons = (*current.invalidation_reasons, reason)
        updated = current.model_copy(
            update={"valid": False, "invalidation_reasons": reasons}
        )
        self._snapshots[snapshot_id] = updated
        return updated
