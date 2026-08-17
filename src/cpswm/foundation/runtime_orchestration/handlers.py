"""Handler protocol and deterministic execution context for M04."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from random import Random
from typing import Callable, Protocol
from uuid import UUID, NAMESPACE_URL, uuid5

from cpswm.contracts.base import ContractModel

from .contracts import RuntimeMessage, VersionBundle


@dataclass(frozen=True)
class HandlerOutput:
    records: tuple[ContractModel, ...] = ()
    emitted_messages: tuple[RuntimeMessage, ...] = ()
    metrics: dict[str, float] = field(default_factory=dict)


@dataclass
class ExecutionContext:
    handler_name: str
    message: RuntimeMessage
    versions: VersionBundle
    attempt: int
    now: datetime
    random: Random

    def deterministic_uuid(self, label: str) -> UUID:
        material = (
            f"cpswm:{self.message.fingerprint}:{self.handler_name}:"
            f"{self.attempt}:{label}"
        )
        return uuid5(NAMESPACE_URL, material)


class MessageHandler(Protocol):
    def __call__(
        self, message: RuntimeMessage, context: ExecutionContext
    ) -> HandlerOutput: ...


HandlerClock = Callable[[], datetime]
