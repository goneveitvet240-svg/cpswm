"""Content-bound, independently attested counterfactual scenario executor.

The executor deliberately accepts a small declarative program instead of
running arbitrary shell or Python supplied by a method.  It therefore proves
that a concrete scenario was executed and reached its declared final state,
without expanding the reference-core process into a general code-execution
boundary.  It is adaptation infrastructure, not native-protocol parity.
"""

from __future__ import annotations

import hashlib
from math import isfinite
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import Field, model_validator

from cpswm.contracts.base import ContractModel
from cpswm.system.attestation import (
    Attestation,
    AttestationError,
    Ed25519AttestationSigner,
    Ed25519AttestationVerifier,
)
from cpswm.system.reproducibility import content_sha256

PROTOCOL_ID = "structure-two-counterfactual-executor@0.7"
ATTESTATION_DOMAIN = "cpswm.evaluation.structure_two.counterfactual_execution.v0.7"
JsonScalar = str | int | float | bool | None
MAX_PROGRAM_BYTES = 65_536
MAX_INSTRUCTIONS = 256
MAX_STATE_KEYS = 128
MAX_KEY_LENGTH = 128
MAX_STRING_LENGTH = 4_096
MAX_NUMERIC_MAGNITUDE = 1e308


def _validate_scalar(value: JsonScalar, *, field_name: str) -> None:
    if isinstance(value, str) and len(value) > MAX_STRING_LENGTH:
        raise ValueError(f"{field_name} string exceeds resource bound")
    if isinstance(value, float) and not isfinite(value):
        raise ValueError(f"{field_name} number must be finite")
    if (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and abs(value) > MAX_NUMERIC_MAGNITUDE
    ):
        raise ValueError(f"{field_name} number exceeds resource bound")


class ScenarioInstruction(ContractModel):
    operation: Literal["assert_equals", "set", "increment"]
    key: str = Field(min_length=1, max_length=MAX_KEY_LENGTH)
    value: JsonScalar

    @model_validator(mode="after")
    def validate_operation_value(self) -> Self:
        _validate_scalar(self.value, field_name="scenario instruction")
        if self.operation == "increment" and (
            not isinstance(self.value, (int, float)) or isinstance(self.value, bool)
        ):
            raise ValueError("scenario increment value must be numeric")
        return self


class CounterfactualScenarioProgram(ContractModel):
    protocol: Literal["structure-two-counterfactual-scenario@0.7"] = (
        "structure-two-counterfactual-scenario@0.7"
    )
    scenario_id: str = Field(min_length=1, max_length=MAX_KEY_LENGTH)
    cluster_id: int = Field(ge=0)
    failure_set_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_rule_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    initial_state: dict[str, JsonScalar] = Field(max_length=MAX_STATE_KEYS)
    instructions: tuple[ScenarioInstruction, ...] = Field(min_length=1, max_length=MAX_INSTRUCTIONS)
    expected_final_state: dict[str, JsonScalar] = Field(max_length=MAX_STATE_KEYS)

    @model_validator(mode="after")
    def validate_state_resources(self) -> Self:
        for state_name, state in (
            ("initial state", self.initial_state),
            ("expected final state", self.expected_final_state),
        ):
            if any(not key or len(key) > MAX_KEY_LENGTH for key in state):
                raise ValueError(f"scenario {state_name} key exceeds resource bound")
            for value in state.values():
                _validate_scalar(value, field_name=f"scenario {state_name}")
        return self


class ScenarioExecutionLogEntry(ContractModel):
    sequence_index: int = Field(ge=0)
    operation: str = Field(min_length=1)
    key: str = Field(min_length=1)
    input_state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    assertion_passed: bool | None = None
    error_code: (
        Literal[
            "assertion_failed",
            "non_numeric_increment_target",
            "non_finite_numeric_result",
            "numeric_magnitude_exceeded",
            "state_key_limit_exceeded",
        ]
        | None
    ) = None


class CounterfactualExecutionReceipt(ContractModel):
    protocol: Literal["structure-two-counterfactual-execution-receipt@0.7"] = (
        "structure-two-counterfactual-execution-receipt@0.7"
    )
    scenario_id: str = Field(min_length=1, max_length=MAX_KEY_LENGTH)
    cluster_id: int = Field(ge=0)
    failure_set_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_rule_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    executable_payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    executor_implementation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    execution_log: tuple[ScenarioExecutionLogEntry, ...] = Field(
        min_length=1, max_length=MAX_INSTRUCTIONS
    )
    final_state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    execution_succeeded: bool
    exit_code: int
    failure_reason: (
        Literal[
            "assertion_failed",
            "non_numeric_increment_target",
            "non_finite_numeric_result",
            "numeric_magnitude_exceeded",
            "state_key_limit_exceeded",
            "final_state_mismatch",
        ]
        | None
    ) = None
    executor_key_id: str = Field(min_length=1, max_length=MAX_KEY_LENGTH)
    executor_public_key_base64: str = Field(min_length=1, max_length=128)
    executor_public_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    attestation: Attestation | None = None
    claim_boundary: str = (
        "Receipt for a resource-bounded declarative adaptation scenario only; not an "
        "official environment run or native-protocol reproduction."
    )


def attested_execution_payload(receipt: CounterfactualExecutionReceipt) -> dict[str, Any]:
    payload = receipt.model_dump(mode="json")
    payload.pop("attestation", None)
    return payload


def _program_bytes(path: Path) -> bytes:
    if not path.is_file():
        raise ValueError(f"counterfactual scenario program is not a file: {path}")
    payload = path.read_bytes()
    if len(payload) > MAX_PROGRAM_BYTES:
        raise ValueError("counterfactual scenario program exceeds file-size bound")
    return payload


def _load_program(path: Path) -> tuple[CounterfactualScenarioProgram, str]:
    payload = _program_bytes(path)
    return (
        CounterfactualScenarioProgram.model_validate_json(payload),
        hashlib.sha256(payload).hexdigest(),
    )


def _executor_implementation_sha256() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _execute_program(
    program: CounterfactualScenarioProgram,
) -> tuple[
    tuple[ScenarioExecutionLogEntry, ...],
    dict[str, JsonScalar],
    bool,
    str | None,
]:
    state = dict(program.initial_state)
    log: list[ScenarioExecutionLogEntry] = []
    succeeded = True
    failure_reason: str | None = None
    for index, instruction in enumerate(program.instructions):
        before = content_sha256(state)
        assertion_passed: bool | None = None
        error_code: str | None = None
        if instruction.operation == "assert_equals":
            assertion_passed = state.get(instruction.key) == instruction.value
            succeeded = succeeded and assertion_passed
            if not assertion_passed:
                error_code = "assertion_failed"
        elif instruction.operation == "set":
            if instruction.key not in state and len(state) >= MAX_STATE_KEYS:
                succeeded = False
                error_code = "state_key_limit_exceeded"
            else:
                state[instruction.key] = instruction.value
        else:
            current = state.get(instruction.key)
            if (
                not isinstance(current, (int, float))
                or isinstance(current, bool)
                or not isinstance(instruction.value, (int, float))
                or isinstance(instruction.value, bool)
            ):
                succeeded = False
                error_code = "non_numeric_increment_target"
            else:
                result = current + instruction.value
                if isinstance(result, float) and not isfinite(result):
                    succeeded = False
                    error_code = "non_finite_numeric_result"
                elif abs(result) > MAX_NUMERIC_MAGNITUDE:
                    succeeded = False
                    error_code = "numeric_magnitude_exceeded"
                else:
                    state[instruction.key] = result
        after = content_sha256(state)
        log.append(
            ScenarioExecutionLogEntry(
                sequence_index=index,
                operation=instruction.operation,
                key=instruction.key,
                input_state_sha256=before,
                output_state_sha256=after,
                assertion_passed=assertion_passed,
                error_code=error_code,
            )
        )
        if error_code is not None:
            failure_reason = error_code
            break
    if succeeded and state != program.expected_final_state:
        succeeded = False
        failure_reason = "final_state_mismatch"
    return tuple(log), state, succeeded, failure_reason


def execute_counterfactual_scenario(
    program_path: Path,
    *,
    signer: Ed25519AttestationSigner,
) -> CounterfactualExecutionReceipt:
    program, executable_payload_sha256 = _load_program(program_path)
    execution_log, final_state, succeeded, failure_reason = _execute_program(program)
    verifier = signer.verifier()
    unsigned = CounterfactualExecutionReceipt(
        scenario_id=program.scenario_id,
        cluster_id=program.cluster_id,
        failure_set_sha256=program.failure_set_sha256,
        candidate_rule_sha256=program.candidate_rule_sha256,
        executable_payload_sha256=executable_payload_sha256,
        executor_implementation_sha256=_executor_implementation_sha256(),
        execution_log=execution_log,
        final_state_sha256=content_sha256(final_state),
        execution_succeeded=succeeded,
        exit_code=0 if succeeded else 1,
        failure_reason=failure_reason,
        executor_key_id=verifier.key_id,
        executor_public_key_base64=verifier.public_key_base64,
        executor_public_key_sha256=verifier.public_key_sha256,
    )
    return unsigned.model_copy(
        update={
            "attestation": signer.sign(
                ATTESTATION_DOMAIN,
                attested_execution_payload(unsigned),
            )
        }
    )


def verify_counterfactual_execution(
    receipt: CounterfactualExecutionReceipt,
    *,
    program_path: Path,
    expected_payload_sha256: str,
    expected_cluster_id: int,
    expected_failure_set_sha256: str,
    expected_candidate_rule_sha256: str,
    trusted_executor_key_id: str,
    trusted_executor_public_key_sha256: str,
) -> None:
    if receipt.scenario_id == "":
        raise ValueError("counterfactual execution scenario id is empty")
    program, actual_payload_sha256 = _load_program(program_path)
    if actual_payload_sha256 != expected_payload_sha256:
        raise ValueError("counterfactual scenario payload hash mismatch")
    if receipt.executable_payload_sha256 != actual_payload_sha256:
        raise ValueError("counterfactual receipt is bound to a different payload")
    if receipt.executor_implementation_sha256 != _executor_implementation_sha256():
        raise ValueError("counterfactual executor implementation hash mismatch")
    if (
        receipt.executor_key_id != trusted_executor_key_id
        or receipt.executor_public_key_sha256 != trusted_executor_public_key_sha256
    ):
        raise AttestationError("counterfactual receipt executor is not trusted")
    verifier = Ed25519AttestationVerifier.from_public_key_base64(
        key_id=receipt.executor_key_id,
        public_key_base64=receipt.executor_public_key_base64,
    )
    if verifier.public_key_sha256 != trusted_executor_public_key_sha256:
        raise AttestationError("counterfactual embedded executor key hash mismatch")
    verifier.verify(
        ATTESTATION_DOMAIN,
        attested_execution_payload(receipt),
        receipt.attestation,
    )
    if receipt.scenario_id != program.scenario_id:
        raise ValueError("counterfactual receipt scenario id mismatch")
    expected_binding = (
        expected_cluster_id,
        expected_failure_set_sha256,
        expected_candidate_rule_sha256,
    )
    if (
        program.cluster_id,
        program.failure_set_sha256,
        program.candidate_rule_sha256,
    ) != expected_binding:
        raise ValueError("counterfactual program cluster/failure/rule binding mismatch")
    if (
        receipt.cluster_id,
        receipt.failure_set_sha256,
        receipt.candidate_rule_sha256,
    ) != expected_binding:
        raise ValueError("counterfactual receipt cluster/failure/rule binding mismatch")
    expected_log, final_state, succeeded, failure_reason = _execute_program(program)
    if receipt.execution_log != expected_log:
        raise ValueError("counterfactual execution log is not reproducible")
    if receipt.final_state_sha256 != content_sha256(final_state):
        raise ValueError("counterfactual final-state hash mismatch")
    if receipt.execution_succeeded != succeeded or receipt.exit_code != (0 if succeeded else 1):
        raise ValueError("counterfactual receipt success semantics mismatch")
    if receipt.failure_reason != failure_reason:
        raise ValueError("counterfactual receipt failure reason mismatch")
    if not receipt.execution_succeeded:
        raise ValueError("counterfactual scenario execution did not succeed")


__all__ = [
    "ATTESTATION_DOMAIN",
    "MAX_INSTRUCTIONS",
    "MAX_KEY_LENGTH",
    "MAX_PROGRAM_BYTES",
    "MAX_STATE_KEYS",
    "MAX_STRING_LENGTH",
    "PROTOCOL_ID",
    "CounterfactualExecutionReceipt",
    "CounterfactualScenarioProgram",
    "ScenarioExecutionLogEntry",
    "ScenarioInstruction",
    "attested_execution_payload",
    "execute_counterfactual_scenario",
    "verify_counterfactual_execution",
]
