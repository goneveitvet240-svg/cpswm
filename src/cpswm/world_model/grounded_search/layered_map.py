"""Static-anchor plus dynamic-object map reference implementation."""

from __future__ import annotations

from uuid import UUID

from cpswm.contracts.grounded_search import DynamicObjectState, StaticGeometryAnchor


class LayeredSemanticMap:
    """Update moving objects without mutating static geometry revisions."""

    def __init__(self) -> None:
        self._static: dict[UUID, StaticGeometryAnchor] = {}
        self._dynamic: dict[UUID, DynamicObjectState] = {}
        self._static_revision = 0
        self._dynamic_revision = 0

    @property
    def static_revision(self) -> int:
        return self._static_revision

    @property
    def dynamic_revision(self) -> int:
        return self._dynamic_revision

    def add_static_anchor(self, anchor: StaticGeometryAnchor) -> None:
        if anchor.anchor_id in self._static:
            raise ValueError("static anchor already exists; append a new map revision")
        if anchor.parent_anchor_id is not None and anchor.parent_anchor_id not in self._static:
            raise LookupError("parent static anchor is unknown")
        if anchor.parent_anchor_id is not None:
            parent = self._static[anchor.parent_anchor_id]
            if anchor.frame_id != parent.frame_id:
                raise ValueError(
                    "child static anchor frame must match its parent frame"
                )
        self._static[anchor.anchor_id] = anchor
        self._static_revision += 1

    def upsert_dynamic_object(self, state: DynamicObjectState) -> None:
        if state.anchor_id not in self._static:
            raise LookupError("dynamic object must reference a static anchor")
        anchor = self._static[state.anchor_id]
        if state.pose.frame_id != anchor.frame_id:
            raise ValueError(
                "dynamic object pose frame must match its static anchor frame"
            )
        self._dynamic[state.object_instance.entity_id] = state
        self._dynamic_revision += 1

    def move_dynamic_object(self, state: DynamicObjectState) -> None:
        if state.object_instance.entity_id not in self._dynamic:
            raise LookupError("cannot move an unregistered dynamic object")
        self.upsert_dynamic_object(state)

    def static_anchor(self, anchor_id: UUID) -> StaticGeometryAnchor:
        return self._static[anchor_id]

    def dynamic_object(self, entity_id: UUID) -> DynamicObjectState:
        return self._dynamic[entity_id]
