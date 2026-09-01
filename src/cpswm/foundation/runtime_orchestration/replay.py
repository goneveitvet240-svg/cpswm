"""Log-bound replay execution and exact/tolerant comparison for M04."""

from __future__ import annotations

from decimal import Decimal
from math import isfinite
from typing import Annotated, Any

from pydantic import Field, JsonValue, model_validator

from cpswm.contracts.base import ContractModel, InputWatermark
from cpswm.foundation.persistence_replay import AppendOnlyTransactionLog, ReplayManifest
from cpswm.foundation.persistence_replay.contracts import content_hash

from .contracts import RuntimeMessage, RuntimeMessageRecord
from .runtime import InProcessRuntime


class ReplayRun(ContractModel):
    manifest_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_numeric_tolerance: float = Field(ge=0.0, allow_inf_nan=False)
    input_log_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_watermark: InputWatermark
    input_fingerprints: tuple[str, ...]
    output_payloads: tuple[JsonValue, ...]
    output_fingerprints: tuple[Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")], ...]
    emitted_message_fingerprints: tuple[str, ...]
    execution_provenance: tuple[JsonValue, ...]

    @model_validator(mode="after")
    def validate_output_bindings(self) -> ReplayRun:
        if len(self.output_payloads) != len(self.output_fingerprints):
            raise ValueError("output_payloads and output_fingerprints must have equal length")
        for index, (payload, fingerprint) in enumerate(
            zip(self.output_payloads, self.output_fingerprints, strict=True)
        ):
            if content_hash(payload) != fingerprint:
                raise ValueError(
                    f"output_fingerprints[{index}] does not match output_payloads[{index}]"
                )
        return self


class ReplayInputBindingError(ValueError):
    """Raised when a manifest does not identify the supplied canonical log."""


def _reject_live_model_extras(value: object, path: str) -> None:
    """Reject fields injected through Pydantic ``model_copy`` at a boundary."""

    if isinstance(value, ContractModel):
        declared_fields = set(type(value).model_fields)
        live_fields = set(value.__dict__)
        pydantic_extras = getattr(value, "__pydantic_extra__", None) or {}
        unexpected_fields = (live_fields - declared_fields) | set(pydantic_extras)
        if unexpected_fields:
            names = ", ".join(sorted(unexpected_fields))
            raise ValueError(f"{path} contains unexpected field(s): {names}")
        for field_name in declared_fields:
            _reject_live_model_extras(getattr(value, field_name), f"{path}.{field_name}")
    elif isinstance(value, dict):
        for key, nested in value.items():
            _reject_live_model_extras(nested, f"{path}[{key!r}]")
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            _reject_live_model_extras(nested, f"{path}[{index}]")


def _revalidate_replay_run(value: ReplayRun, label: str) -> ReplayRun:
    _reject_live_model_extras(value, label)
    return ReplayRun.model_validate(
        value.model_dump(mode="python", round_trip=True, warnings=False)
    )


def _revalidate_replay_manifest(value: ReplayManifest) -> ReplayManifest:
    _reject_live_model_extras(value, "replay manifest")
    return ReplayManifest.model_validate(
        value.model_dump(mode="python", round_trip=True, warnings=False)
    )


class ReplayRunner:
    def run(
        self,
        *,
        runtime: InProcessRuntime,
        manifest: ReplayManifest,
        input_log: AppendOnlyTransactionLog,
    ) -> ReplayRun:
        try:
            manifest = _revalidate_replay_manifest(manifest)
            # Compute every manifest-derived value before dispatch.  Besides
            # proving that the canonical manifest is hashable, this prevents a
            # malformed manifest from failing only after handler output was
            # already appended to the replay log.
            manifest_fingerprint = manifest.fingerprint
        except (AttributeError, TypeError, ValueError) as error:
            raise ReplayInputBindingError(
                f"invalid ReplayManifest at replay boundary: {error}"
            ) from error
        if runtime.transaction_log is input_log:
            raise ReplayInputBindingError(
                "replay input log and runtime output log must be separate"
            )
        runtime.verify_replay_manifest(manifest)
        try:
            actual_watermark = input_log.watermark_at(manifest.input_watermark.global_commit_seq)
        except LookupError as error:
            raise ReplayInputBindingError(
                "ReplayManifest input watermark is absent from the supplied log"
            ) from error
        if actual_watermark != manifest.input_watermark:
            raise ReplayInputBindingError(
                "ReplayManifest input watermark does not match the supplied log"
            )
        actual_log_sha256 = input_log.fingerprint(
            through_commit_seq=manifest.input_watermark.global_commit_seq
        )
        if actual_log_sha256 != manifest.input_log_sha256:
            raise ReplayInputBindingError(
                "ReplayManifest input_log_sha256 does not match the supplied log"
            )

        messages = self._decode_messages(input_log, manifest)
        ordered = sorted(messages, key=lambda item: item.sequence_no)
        sequence_numbers = [item.sequence_no for item in ordered]
        if len(sequence_numbers) != len(set(sequence_numbers)):
            raise ValueError("replay input sequence_no values must be unique")
        payloads: list[JsonValue] = []
        output_fingerprints: list[str] = []
        emitted_fingerprints: list[str] = []
        execution_provenance: list[JsonValue] = []
        for message in ordered:
            result = runtime.dispatch(message, replay_manifest=manifest)
            for commit in result.commits:
                for record in commit.transaction.records:
                    payloads.append(record.envelope.payload)
                    output_fingerprints.append(record.envelope.payload_sha256)
            # RuntimeMessage.fingerprint covers the complete message, while tuple
            # order preserves the exact handler emission order for comparison.
            emitted_fingerprints.extend(item.fingerprint for item in result.emitted_messages)
            for execution in result.executions:
                watermark = execution.output_watermark
                execution_provenance.append(
                    {
                        "handler_name": execution.handler_name,
                        "message_fingerprint": execution.message_fingerprint,
                        "trace_id": str(execution.trace_id),
                        "status": execution.status.value,
                        "attempts": execution.attempts,
                        "versions": execution.versions.model_dump(mode="json"),
                        "output_watermark": (
                            # The complete watermark includes recorded_at, which
                            # is copied from canonical transaction committed_at.
                            # Replay comparison therefore covers output-log time
                            # without making tolerant payload comparison exact.
                            watermark.model_dump(mode="json") if watermark is not None else None
                        ),
                    }
                )
        return ReplayRun(
            manifest_fingerprint=manifest_fingerprint,
            manifest_numeric_tolerance=manifest.numeric_tolerance,
            input_log_sha256=actual_log_sha256,
            input_watermark=actual_watermark,
            input_fingerprints=tuple(item.fingerprint for item in ordered),
            output_payloads=tuple(payloads),
            output_fingerprints=tuple(output_fingerprints),
            emitted_message_fingerprints=tuple(emitted_fingerprints),
            execution_provenance=tuple(execution_provenance),
        )

    @staticmethod
    def _decode_messages(
        input_log: AppendOnlyTransactionLog, manifest: ReplayManifest
    ) -> tuple[RuntimeMessage, ...]:
        messages: list[RuntimeMessage] = []
        transactions = input_log.read(through_commit_seq=manifest.input_watermark.global_commit_seq)
        for transaction in transactions:
            for record in transaction.records:
                if record.envelope.schema_name != "cpswm.RuntimeMessageRecord":
                    raise ReplayInputBindingError(
                        "strict replay input log contains a non-message record"
                    )
                decoded = RuntimeMessageRecord.model_validate(record.envelope.payload)
                if decoded.metadata.schema_version != manifest.schema_version:
                    raise ReplayInputBindingError(
                        "input message schema version differs from ReplayManifest"
                    )
                messages.append(decoded.message)
        return tuple(messages)


def compare_replay_runs(
    first: ReplayRun,
    second: ReplayRun,
    *,
    numeric_tolerance: float | None = None,
) -> bool:
    if numeric_tolerance is not None and (not isfinite(numeric_tolerance) or numeric_tolerance < 0):
        raise ValueError("numeric_tolerance must be finite and non-negative")
    try:
        first = _revalidate_replay_run(first, "first replay run")
        second = _revalidate_replay_run(second, "second replay run")
    except (TypeError, ValueError):
        # model_copy can bypass Pydantic validators. A comparison boundary must
        # not accept an internally inconsistent ReplayRun as valid evidence.
        return False
    if first.manifest_fingerprint != second.manifest_fingerprint:
        return False
    if first.manifest_numeric_tolerance != second.manifest_numeric_tolerance:
        return False
    declared_tolerance = first.manifest_numeric_tolerance
    if numeric_tolerance is None:
        effective_tolerance = declared_tolerance
    else:
        if numeric_tolerance > declared_tolerance:
            raise ValueError("numeric_tolerance cannot exceed the ReplayManifest declaration")
        effective_tolerance = numeric_tolerance
    if first.input_log_sha256 != second.input_log_sha256:
        return False
    if first.input_watermark != second.input_watermark:
        return False
    if first.input_fingerprints != second.input_fingerprints:
        return False
    if first.emitted_message_fingerprints != second.emitted_message_fingerprints:
        return False
    if not _values_equal(
        first.execution_provenance, second.execution_provenance, effective_tolerance
    ):
        return False
    if len(first.output_payloads) != len(second.output_payloads):
        return False
    if effective_tolerance == 0 and (first.output_fingerprints != second.output_fingerprints):
        return False
    return all(
        _values_equal(left, right, effective_tolerance)
        for left, right in zip(first.output_payloads, second.output_payloads, strict=True)
    )


def _values_equal(left: Any, right: Any, tolerance: float) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return left is right
    if isinstance(left, int) and isinstance(right, int):
        return left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        if tolerance == 0:
            return type(left) is type(right) and left == right
        return abs(Decimal(str(left)) - Decimal(str(right))) <= Decimal(str(tolerance))
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(
            _values_equal(left[key], right[key], tolerance) for key in left
        )
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        return len(left) == len(right) and all(
            _values_equal(a, b, tolerance) for a, b in zip(left, right, strict=True)
        )
    return bool(left == right)
