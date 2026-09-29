"""Owner-issued visual proof catalogue, not a second writable world memory.

The producer receives detached sources, never the owner's registration key.
Hashes prove correspondence within the owned runtime, not physical authenticity.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from cpswm.contracts.base import require_aware
from cpswm.data_preflight.proposal_perception import ProposalPixelObservation
from cpswm.system.owned_visual_support import OwnedVisualSupport
from cpswm.system.reproducibility import content_sha256


@dataclass(frozen=True)
class NativeVisualAuthority:
    key: UUID

    @classmethod
    def create(cls) -> NativeVisualAuthority:
        return cls(uuid4())


@dataclass(frozen=True)
class NativeVisualSource:
    runtime_id: UUID
    scope: tuple[UUID, UUID, UUID]
    cutoff: datetime
    support: OwnedVisualSupport

    @property
    def content_sha256(self) -> str:
        return content_sha256(self)

    def pixels(self) -> tuple[ProposalPixelObservation, ...]:
        require_aware(self.cutoff, "visual source cutoff")
        if any(a.status not in {"DELIVERED", "FAILED"} for a in self.support.actions):
            raise ValueError("native visual source includes mutable or pending actions")
        result = tuple(
            ProposalPixelObservation.from_frame(f.frame, geometry=f.geometry)
            for a in self.support.actions
            for f in a.frames
        )
        if any(
            (p.household_id, p.session_id, p.trace_id) != self.scope or p.arrival_time > self.cutoff
            for p in result
        ):
            raise ValueError("native visual source scope or cutoff differs")
        return result
