"""Replaceable M03 storage interfaces."""

from __future__ import annotations

from typing import Protocol, Sequence
from uuid import UUID

from cpswm.contracts.base import ContractModel, InputWatermark

from .contracts import CommitResult, CommittedTransaction


class TransactionLog(Protocol):
    def append(
        self,
        records: Sequence[ContractModel],
        *,
        idempotency_key: str,
    ) -> CommitResult: ...

    def read(
        self,
        *,
        after_commit_seq: int = 0,
        through_commit_seq: int | None = None,
        household_id: UUID | None = None,
    ) -> tuple[CommittedTransaction, ...]: ...

    def latest_watermark(self) -> InputWatermark: ...
