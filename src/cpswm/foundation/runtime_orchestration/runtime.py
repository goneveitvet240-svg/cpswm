"""Deterministic in-process command and event runtime for M04 A0."""

from __future__ import annotations

import hashlib
import random
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from time import sleep
from uuid import UUID, uuid4

from pydantic import BaseModel, JsonValue

from cpswm.contracts.base import BaseRecordMetadata, ContractModel, utc_now
from cpswm.foundation.persistence_replay import (
    AppendOnlyTransactionLog,
    CommitResult,
    ReplayManifest,
)

from .contracts import (
    HandlerExecutionRecord,
    HandlerStatus,
    MessageKind,
    RetryPolicy,
    RuntimeMessage,
    VersionBundle,
)
from .handlers import ExecutionContext, HandlerOutput, MessageHandler
from .provenance import verify_replay_provenance


class HandlerRegistrationError(ValueError):
    pass


class RetryableHandlerError(RuntimeError):
    pass


class HandlerFailedError(RuntimeError):
    def __init__(self, execution: HandlerExecutionRecord) -> None:
        super().__init__(
            f"handler {execution.handler_name!r} failed after "
            f"{execution.attempts} attempt(s): {execution.error_message}"
        )
        self.execution = execution


@dataclass(frozen=True)
class RuntimeDispatchResult:
    executions: tuple[HandlerExecutionRecord, ...]
    commits: tuple[CommitResult, ...]
    emitted_messages: tuple[RuntimeMessage, ...]


@dataclass(frozen=True)
class _RegisteredHandler:
    name: str
    callback: MessageHandler
    retry_policy: RetryPolicy


@dataclass(frozen=True)
class _CachedResult:
    message_fingerprint: str
    execution: HandlerExecutionRecord
    commit: CommitResult | None
    emitted_messages: tuple[RuntimeMessage, ...]


class InProcessRuntime:
    def __init__(
        self,
        *,
        transaction_log: AppendOnlyTransactionLog,
        versions: VersionBundle,
        repository_root: str | Path | None = None,
        active_configuration: JsonValue | None = None,
        clock: Callable[[], datetime] = utc_now,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        self.transaction_log = transaction_log
        self.versions = versions
        self.repository_root = (
            Path(repository_root).resolve() if repository_root is not None else None
        )
        self.active_configuration = active_configuration
        self.clock = clock
        self.sleeper = sleeper
        self._commands: dict[str, _RegisteredHandler] = {}
        self._events: dict[str, dict[str, _RegisteredHandler]] = {}
        self._cache: dict[tuple[UUID, str, str], _CachedResult] = {}
        self.execution_journal: list[HandlerExecutionRecord] = []

    def verify_replay_manifest(self, manifest: ReplayManifest) -> None:
        verify_replay_provenance(
            manifest,
            runtime_versions=self.versions,
            repository_root=self.repository_root,
            active_configuration=self.active_configuration,
        )

    def register_command(
        self,
        message_name: str,
        *,
        handler_name: str,
        handler: MessageHandler,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        if message_name in self._commands:
            raise HandlerRegistrationError(f"command {message_name!r} already has a handler")
        self._commands[message_name] = _RegisteredHandler(
            handler_name, handler, retry_policy or RetryPolicy()
        )

    def subscribe_event(
        self,
        message_name: str,
        *,
        handler_name: str,
        handler: MessageHandler,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        subscribers = self._events.setdefault(message_name, {})
        if handler_name in subscribers:
            raise HandlerRegistrationError(f"event handler {handler_name!r} is already registered")
        subscribers[handler_name] = _RegisteredHandler(
            handler_name, handler, retry_policy or RetryPolicy()
        )

    def dispatch(
        self,
        message: RuntimeMessage,
        *,
        replay_manifest: ReplayManifest | None = None,
    ) -> RuntimeDispatchResult:
        message = self._revalidate_incoming_message(message)
        if message.kind == MessageKind.COMMAND:
            try:
                handlers = (self._commands[message.name],)
            except KeyError as error:
                raise HandlerRegistrationError(
                    f"command {message.name!r} has no handler"
                ) from error
        else:
            handlers = tuple(
                self._events.get(message.name, {})[name]
                for name in sorted(self._events.get(message.name, {}))
            )

        executions: list[HandlerExecutionRecord] = []
        commits: list[CommitResult] = []
        emitted: list[RuntimeMessage] = []
        for registered in handlers:
            execution, commit, messages = self._run_handler(registered, message, replay_manifest)
            executions.append(execution)
            if commit is not None:
                commits.append(commit)
            emitted.extend(messages)
        return RuntimeDispatchResult(
            executions=tuple(executions),
            commits=tuple(commits),
            emitted_messages=tuple(emitted),
        )

    @staticmethod
    def _revalidate_incoming_message(message: RuntimeMessage) -> RuntimeMessage:
        """Rebuild ingress so ``model_copy`` cannot bypass public validators."""

        if not isinstance(message, RuntimeMessage):
            raise TypeError("runtime input must be a RuntimeMessage instance")

        declared_fields = set(RuntimeMessage.model_fields)
        live_fields = set(message.__dict__)
        pydantic_extras = getattr(message, "__pydantic_extra__", None) or {}
        unexpected_fields = (live_fields - declared_fields) | set(pydantic_extras)
        if unexpected_fields:
            names = ", ".join(sorted(unexpected_fields))
            raise ValueError(f"runtime input contains unexpected field(s): {names}")

        return RuntimeMessage.model_validate(
            message.model_dump(mode="python", round_trip=True, warnings=False)
        )

    def _run_handler(
        self,
        registered: _RegisteredHandler,
        message: RuntimeMessage,
        replay_manifest: ReplayManifest | None,
    ) -> tuple[
        HandlerExecutionRecord,
        CommitResult | None,
        tuple[RuntimeMessage, ...],
    ]:
        cache_key = (
            message.household_id,
            registered.name,
            message.idempotency_key,
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            if cached.message_fingerprint != message.fingerprint:
                raise HandlerRegistrationError(
                    "handler idempotency key was reused for a different message"
                )
            replayed = cached.execution.model_copy(
                update={
                    "execution_id": uuid4(),
                    "message_id": message.message_id,
                    "status": HandlerStatus.IDEMPOTENT_REPLAY,
                    "started_at": self._logical_now(replay_manifest),
                    "finished_at": self._logical_now(replay_manifest),
                }
            )
            self.execution_journal.append(replayed)
            return replayed, cached.commit, cached.emitted_messages

        started_at = self._logical_now(replay_manifest)
        last_error: Exception | None = None
        for attempt in range(1, registered.retry_policy.max_attempts + 1):
            context = ExecutionContext(
                handler_name=registered.name,
                message=message,
                versions=self.versions,
                attempt=attempt,
                now=self._logical_now(replay_manifest),
                random=random.Random(self._handler_seed(replay_manifest, message, registered.name)),
            )
            try:
                output = registered.callback(message, context)
                output = self._normalize_output_records(output)
                output = self._normalize_emitted_messages(output, context)
                self._validate_output(message, output)
                commit = None
                if output.records:
                    commit = self.transaction_log.append(
                        output.records,
                        idempotency_key=(f"handler:{registered.name}:{message.idempotency_key}"),
                        committed_at=(
                            replay_manifest.created_at if replay_manifest is not None else None
                        ),
                    )
                finished_at = self._logical_now(replay_manifest)
                execution = HandlerExecutionRecord(
                    handler_name=registered.name,
                    message_id=message.message_id,
                    message_fingerprint=message.fingerprint,
                    trace_id=message.trace_id,
                    status=HandlerStatus.SUCCEEDED,
                    attempts=attempt,
                    versions=self.versions,
                    started_at=started_at,
                    finished_at=finished_at,
                    output_watermark=commit.watermark if commit else None,
                )
                cached_result = _CachedResult(
                    message_fingerprint=message.fingerprint,
                    execution=execution,
                    commit=commit,
                    emitted_messages=output.emitted_messages,
                )
                self._cache[cache_key] = cached_result
                self.execution_journal.append(execution)
                return execution, commit, output.emitted_messages
            except RetryableHandlerError as error:
                last_error = error
                if attempt < registered.retry_policy.max_attempts:
                    if registered.retry_policy.backoff_seconds:
                        self.sleeper(registered.retry_policy.backoff_seconds)
                    continue
                break
            except Exception as error:
                last_error = error
                break

        assert last_error is not None
        failed = HandlerExecutionRecord(
            handler_name=registered.name,
            message_id=message.message_id,
            message_fingerprint=message.fingerprint,
            trace_id=message.trace_id,
            status=HandlerStatus.FAILED,
            attempts=attempt,
            versions=self.versions,
            started_at=started_at,
            finished_at=self._logical_now(replay_manifest),
            error_type=type(last_error).__name__,
            error_message=str(last_error),
        )
        self.execution_journal.append(failed)
        raise HandlerFailedError(failed) from last_error

    def _validate_output(self, message: RuntimeMessage, output: HandlerOutput) -> None:
        for record in output.records:
            metadata = getattr(record, "metadata", None)
            if not isinstance(metadata, BaseRecordMetadata):
                raise TypeError("handler output records require BaseRecordMetadata")
            if metadata.household_id != message.household_id:
                raise ValueError("handler output cannot cross household boundaries")
            if metadata.session_id != message.session_id:
                raise ValueError("handler output must preserve session_id")
            if metadata.trace_id != message.trace_id:
                raise ValueError("handler output must preserve trace_id")
        for emitted in output.emitted_messages:
            if emitted.household_id != message.household_id:
                raise ValueError("emitted messages cannot cross household boundaries")
            if emitted.session_id != message.session_id:
                raise ValueError("emitted messages must preserve session_id")
            if emitted.trace_id != message.trace_id:
                raise ValueError("emitted messages must preserve trace_id")
            if emitted.causation_id != message.message_id:
                raise ValueError("emitted messages must identify their causation_id")

    @classmethod
    def _normalize_output_records(cls, output: HandlerOutput) -> HandlerOutput:
        """Revalidate each concrete public record before persistence."""

        records = tuple(cls._revalidate_output_record(record) for record in output.records)
        return replace(output, records=records)

    @classmethod
    def _revalidate_output_record(cls, record: ContractModel) -> ContractModel:
        if not isinstance(record, ContractModel):
            raise TypeError("handler output records must be ContractModel instances")
        cls._reject_live_model_extras(record, "handler output record")
        return type(record).model_validate(
            record.model_dump(mode="python", round_trip=True, warnings=False)
        )

    @classmethod
    def _reject_live_model_extras(cls, value: object, path: str) -> None:
        if isinstance(value, BaseModel):
            declared_fields = set(type(value).model_fields)
            live_fields = set(value.__dict__)
            pydantic_extras = getattr(value, "__pydantic_extra__", None) or {}
            unexpected_fields = (live_fields - declared_fields) | set(pydantic_extras)
            if unexpected_fields:
                names = ", ".join(sorted(unexpected_fields))
                raise ValueError(f"{path} contains unexpected field(s): {names}")
            for field_name in declared_fields:
                cls._reject_live_model_extras(getattr(value, field_name), f"{path}.{field_name}")
        elif isinstance(value, dict):
            for key, nested in value.items():
                cls._reject_live_model_extras(nested, f"{path}[{key!r}]")
        elif isinstance(value, (list, tuple)):
            for index, nested in enumerate(value):
                cls._reject_live_model_extras(nested, f"{path}[{index}]")

    @staticmethod
    def _normalize_emitted_messages(
        output: HandlerOutput, context: ExecutionContext
    ) -> HandlerOutput:
        """Assign runtime identity, then revalidate the complete public contract.

        ``BaseModel.model_copy`` deliberately does not rerun validation.  A
        handler can therefore return an object whose in-memory fields no longer
        satisfy :class:`RuntimeMessage`, or even inject fields that the normal
        serializer would silently omit.  Emissions cross a public runtime
        boundary, so rebuild every normalized message from plain field data
        instead of trusting the existing model instance.
        """

        emitted_messages = tuple(
            InProcessRuntime._normalize_emitted_message(
                emitted,
                context=context,
                ordinal=ordinal,
            )
            for ordinal, emitted in enumerate(output.emitted_messages)
        )
        return replace(output, emitted_messages=emitted_messages)

    @staticmethod
    def _normalize_emitted_message(
        emitted: RuntimeMessage,
        *,
        context: ExecutionContext,
        ordinal: int,
    ) -> RuntimeMessage:
        if not isinstance(emitted, RuntimeMessage):
            raise TypeError("emitted messages must be RuntimeMessage instances")

        declared_fields = set(RuntimeMessage.model_fields)
        live_fields = set(emitted.__dict__)
        pydantic_extras = getattr(emitted, "__pydantic_extra__", None) or {}
        unexpected_fields = (live_fields - declared_fields) | set(pydantic_extras)
        if unexpected_fields:
            names = ", ".join(sorted(unexpected_fields))
            raise ValueError(f"emitted message contains unexpected field(s): {names}")

        values = emitted.model_dump(
            mode="python",
            round_trip=True,
            warnings=False,
        )
        values.update(
            {
                "message_id": context.deterministic_uuid(f"emitted-message:{ordinal}"),
                "created_at": context.now,
            }
        )
        return RuntimeMessage.model_validate(values)

    def _logical_now(self, manifest: ReplayManifest | None) -> datetime:
        if manifest is not None:
            return manifest.created_at
        return self.clock()

    @staticmethod
    def _handler_seed(
        manifest: ReplayManifest | None,
        message: RuntimeMessage,
        handler_name: str,
    ) -> int:
        base_seed = manifest.random_seed if manifest is not None else 0
        material = f"{base_seed}:{message.fingerprint}:{handler_name}".encode()
        return int.from_bytes(hashlib.sha256(material).digest()[:8], "big")
