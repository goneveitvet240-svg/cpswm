"""Facade joining M02 identity, clock, and frame registries."""

from .clocks import TimeAlignmentRegistry
from .frames import FrameRegistry
from .identity import IdentityRegistry


class IdentityTimeFrameService:
    def __init__(self) -> None:
        self.identities = IdentityRegistry()
        self.clocks = TimeAlignmentRegistry()
        self.frames = FrameRegistry()
