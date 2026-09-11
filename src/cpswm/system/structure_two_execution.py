"""Immutable Architecture-A execution and trace contracts for Structure Two.

The historical ordinary-transition lane stays separate from the six registered
adaptive paths.  Adaptive traces are engineering evidence of the calls and
deferrals made by one production transaction; they are not scientific evidence
that adaptive computation improves quality or cost.
"""

from __future__ import annotations

import hashlib
import inspect
import marshal
from collections.abc import Mapping
from pathlib import Path
from types import CodeType, MappingProxyType
from typing import Annotated, Any, Final, Literal, Protocol, cast, runtime_checkable
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from pydantic import Field, model_validator

from cpswm.contracts.base import ContractModel, NonNegativeInt
from cpswm.system.reproducibility import content_sha256

EXECUTION_CONTRACT_VERSION: Final = "structure-two-execution-contract@0.1"
STRUCTURE_TWO_OPERATOR_ORDER: Final = (
    "opceu",
    "orrer_cheh",
    "pchmp",
    "cf_bocpd",
    "ccrr",
    "rgrc",
    "ciav",
)
LEGACY_CONSUMPTION_GRAPH: Final = MappingProxyType(
    {
        "opceu": (),
        "orrer_cheh": (),
        "pchmp": ("orrer_cheh",),
        "cf_bocpd": ("pchmp",),
        "ccrr": ("pchmp", "cf_bocpd"),
        "rgrc": ("opceu", "pchmp", "ccrr"),
        "ciav": (),
    }
)
LEGACY_PLAN_ID: Final = "LEGACY_ORDINARY_TRANSITION"
LEGACY_CIAV_NOT_APPLICABLE_REASON: Final = (
    "PrototypeTransition carries no CIAV candidate-action, utility, privacy-budget, "
    "or observation-realizer contract"
)
TRACE_CLAIM_BOUNDARY: Final = (
    "Engineering trace for the legacy ordinary-transition entrypoint only. It does not establish "
    "execution of a registered adaptive path, CIAV invocation or feedback closure, independent "
    "custody, cross-system trace/state atomicity, production benefit, or scientific evidence."
)
ADAPTIVE_TRACE_CLAIM_BOUNDARY: Final = (
    "Source-bound D0 engineering trace for one registered adaptive production path. "
    "It establishes the recorded live calls, safe deferrals, optional CIAV feedback "
    "closure, and local rollback boundary only. It does not establish path benefit, "
    "recovery equivalence, external validity, independent custody, or durable "
    "cross-system trace/state atomicity."
)
GENESIS_RECEIPT_SHA256: Final = "GENESIS"

REGISTERED_ADAPTIVE_PATH_MODES: Final = MappingProxyType(
    {
        "P0_SAFE_DEFERRED": (
            "mandatory_maintenance_executed",
            "deferred_with_valid_debt_certificate",
            "mandatory_maintenance_executed",
            "mandatory_maintenance_executed",
            "mandatory_maintenance_executed",
            "mandatory_maintenance_executed",
            "deferred_with_valid_debt_certificate",
        ),
        "P1_EVENT_ACTOR_LOCAL": (
            "mandatory_maintenance_executed",
            "refinement_executed",
            "refinement_executed",
            "mandatory_maintenance_executed",
            "mandatory_maintenance_executed",
            "refinement_executed",
            "deferred_with_valid_debt_certificate",
        ),
        "P2_REGIME_RECOVERY_LOCAL": (
            "mandatory_maintenance_executed",
            "mandatory_maintenance_executed",
            "mandatory_maintenance_executed",
            "refinement_executed",
            "refinement_executed",
            "refinement_executed",
            "deferred_with_valid_debt_certificate",
        ),
        "P3_ACTIVE_VERIFY": (
            "refinement_executed",
            "mandatory_maintenance_executed",
            "mandatory_maintenance_executed",
            "mandatory_maintenance_executed",
            "mandatory_maintenance_executed",
            "mandatory_maintenance_executed",
            "refinement_executed",
        ),
        "P4_EVENT_ACTOR_PLUS_REGIME": (
            "refinement_executed",
            "refinement_executed",
            "refinement_executed",
            "refinement_executed",
            "refinement_executed",
            "refinement_executed",
            "deferred_with_valid_debt_certificate",
        ),
        "P5_FULL_EAGER": (
            "refinement_executed",
            "refinement_executed",
            "refinement_executed",
            "refinement_executed",
            "refinement_executed",
            "refinement_executed",
            "refinement_executed",
        ),
    }
)
ADAPTIVE_FEEDBACK_CLOSURE_PATHS: Final = frozenset({"P3_ACTIVE_VERIFY", "P5_FULL_EAGER"})
ADAPTIVE_PRIMARY_CONSUMPTION_GRAPHS: Final = MappingProxyType(
    {
        "P0_SAFE_DEFERRED": MappingProxyType(
            {
                "opceu": (),
                "orrer_cheh": (),
                "pchmp": (),
                "cf_bocpd": (),
                "ccrr": ("cf_bocpd",),
                "rgrc": ("pchmp", "ccrr"),
                "ciav": (),
            }
        ),
        "P1_EVENT_ACTOR_LOCAL": LEGACY_CONSUMPTION_GRAPH,
        "P2_REGIME_RECOVERY_LOCAL": LEGACY_CONSUMPTION_GRAPH,
        "P4_EVENT_ACTOR_PLUS_REGIME": LEGACY_CONSUMPTION_GRAPH,
        "P3_ACTIVE_VERIFY": MappingProxyType(
            {
                **LEGACY_CONSUMPTION_GRAPH,
                "ciav": ("ccrr", "rgrc"),
            }
        ),
        "P5_FULL_EAGER": MappingProxyType(
            {
                **LEGACY_CONSUMPTION_GRAPH,
                "ciav": ("ccrr", "rgrc"),
            }
        ),
    }
)
ADAPTIVE_FEEDBACK_CONSUMPTION_GRAPH: Final = MappingProxyType(
    {
        "opceu": ("ciav",),
        "orrer_cheh": ("ciav",),
        "pchmp": ("orrer_cheh",),
        "cf_bocpd": ("pchmp",),
        "ccrr": ("pchmp", "cf_bocpd"),
        "rgrc": ("opceu", "pchmp", "ccrr"),
    }
)

SHA256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


# Literal aliases keep JSON values closed while avoiding a production import of
# the experimental pre-death evaluator.
RuntimeOperatorName = Literal[
    "opceu",
    "orrer_cheh",
    "pchmp",
    "cf_bocpd",
    "ccrr",
    "rgrc",
    "ciav",
]
PlanLaneName = Literal["legacy_ordinary_transition", "registered_adaptive_path"]
ExecutionModeName = Literal[
    "legacy_default_executed",
    "mandatory_maintenance_executed",
    "refinement_executed",
    "deferred_with_valid_debt_certificate",
    "not_applicable_with_recomputed_reason",
]
ReceiptStatusName = Literal["executed", "deferred", "not_applicable"]
TracePhaseName = Literal["ordinary_transition", "selected_path", "feedback_closure"]
FeedbackClosureKind = Literal[
    "none",
    "full_transition",
    "same_location_fast_verification",
]
InvocationBindingKind = Literal[
    "direct_operator_callable",
    "composite_operator_stage",
    "enclosing_runtime_stage",
    "adaptive_safety_maintenance",
    "adaptive_composite_stage",
]
LEGACY_BINDING_KINDS: Final = (
    "direct_operator_callable",
    "direct_operator_callable",
    "direct_operator_callable",
    "direct_operator_callable",
    "composite_operator_stage",
    "enclosing_runtime_stage",
    None,
)


def _runtime_rlock_depth(lock: object) -> int:
    counter = getattr(lock, "_recursion_count", None)
    if not callable(counter):
        raise RuntimeError("runtime RLock does not expose an auditable recursion depth")
    depth = counter()
    if isinstance(depth, bool) or not isinstance(depth, int) or depth < 0:
        raise RuntimeError("runtime RLock returned an invalid recursion depth")
    return depth


def _restore_runtime_rlock_depth(
    lock: object,
    expected_depth: int,
    *,
    verify_unowned_available: bool = True,
) -> bool:
    """Restore this thread's RLock depth without waiting on another thread.

    ``RLock._recursion_count`` is local to the calling thread.  A zero count can
    therefore mean either "unlocked" or "owned by another thread".  A
    non-blocking probe distinguishes those cases whenever the expected depth is
    zero, and every recovery acquisition is non-blocking so an untrusted sink
    cannot stall the transaction indefinitely by handing the lock to a worker.
    """

    observed_depth = _runtime_rlock_depth(lock)
    current_depth = observed_depth
    while current_depth < expected_depth:
        acquire = getattr(lock, "acquire", None)
        if not callable(acquire) or acquire(False) is not True:
            raise RuntimeError("runtime RLock is owned by another thread")
        current_depth = _runtime_rlock_depth(lock)
    while current_depth > expected_depth:
        release = getattr(lock, "release", None)
        if not callable(release):
            raise RuntimeError("runtime RLock ownership could not be restored")
        release()
        current_depth = _runtime_rlock_depth(lock)
    if expected_depth == 0 and verify_unowned_available:
        acquire = getattr(lock, "acquire", None)
        release = getattr(lock, "release", None)
        if not callable(acquire) or not callable(release) or acquire(False) is not True:
            raise RuntimeError("runtime RLock is owned by another thread")
        release()
    return observed_depth != expected_depth


class OperatorExecutionDirective(ContractModel):
    """One immutable operator disposition in an ordered execution plan."""

    operator: RuntimeOperatorName
    mode: ExecutionModeName
    contract_guard_active: Literal[True] = True


class StructureTwoExecutionPlan(ContractModel):
    """Pure-data plan accepted by the Architecture-A production seam."""

    schema_version: Literal["0.1.0"] = "0.1.0"
    contract_version: Literal["structure-two-execution-contract@0.1"] = EXECUTION_CONTRACT_VERSION
    plan_id: str = Field(pattern=r"^[A-Z0-9_]+$")
    lane: PlanLaneName
    adaptive_path_id: str | None = None
    operator_directives: tuple[OperatorExecutionDirective, ...]
    scientific_evidence_authorized: Literal[False] = False

    @model_validator(mode="after")
    def validate_complete_ordered_plan(self) -> StructureTwoExecutionPlan:
        observed = tuple(item.operator for item in self.operator_directives)
        if observed != STRUCTURE_TWO_OPERATOR_ORDER:
            raise ValueError(
                "execution plan must contain the exact ordered seven-operator registry"
            )
        if self.lane == "legacy_ordinary_transition":
            if self.plan_id != LEGACY_PLAN_ID or self.adaptive_path_id is not None:
                raise ValueError("legacy execution plan identity drifted")
            expected_modes = ("legacy_default_executed",) * 6 + (
                "not_applicable_with_recomputed_reason",
            )
            if tuple(item.mode for item in self.operator_directives) != expected_modes:
                raise ValueError("legacy execution plan mode vector drifted")
        else:
            if not self.adaptive_path_id or self.plan_id != self.adaptive_path_id:
                raise ValueError("registered adaptive plan must bind one matching adaptive path id")
            adaptive_expected_modes = REGISTERED_ADAPTIVE_PATH_MODES.get(self.plan_id)
            if adaptive_expected_modes is None:
                raise ValueError("adaptive execution plan is not in the frozen path registry")
            if tuple(item.mode for item in self.operator_directives) != adaptive_expected_modes:
                raise ValueError("adaptive execution plan mode vector drifted")
        return self

    @property
    def content_sha256(self) -> str:
        return content_sha256(self.model_dump(mode="json"))


def canonical_legacy_ordinary_transition_plan() -> StructureTwoExecutionPlan:
    """Return a new immutable copy of the historical compatibility plan."""

    return StructureTwoExecutionPlan(
        plan_id=LEGACY_PLAN_ID,
        lane="legacy_ordinary_transition",
        operator_directives=tuple(
            OperatorExecutionDirective(
                operator=operator,
                mode=(
                    "not_applicable_with_recomputed_reason"
                    if operator == "ciav"
                    else "legacy_default_executed"
                ),
            )
            for operator in STRUCTURE_TWO_OPERATOR_ORDER
        ),
    )


def registered_adaptive_execution_plan(path_id: str) -> StructureTwoExecutionPlan:
    """Return one exact immutable P0--P5 plan; arbitrary bitmasks are rejected."""

    modes = REGISTERED_ADAPTIVE_PATH_MODES.get(path_id)
    if modes is None:
        raise ValueError(f"unknown registered adaptive path: {path_id}")
    return StructureTwoExecutionPlan(
        plan_id=path_id,
        lane="registered_adaptive_path",
        adaptive_path_id=path_id,
        operator_directives=tuple(
            OperatorExecutionDirective(operator=operator, mode=mode)
            for operator, mode in zip(STRUCTURE_TWO_OPERATOR_ORDER, modes, strict=True)
        ),
    )


class AdaptiveInferenceDebtCertificate(ContractModel):
    """Immutable evidence needed to revisit a production-safe deferral."""

    schema_version: Literal["0.2.0"] = "0.2.0"
    debt_id: UUID
    origin_path_id: str = Field(min_length=1)
    origin_transition_sha256: SHA256
    origin_state_sha256: SHA256
    created_step: NonNegativeInt
    expiry_step: NonNegativeInt
    deferred_operators: tuple[RuntimeOperatorName, ...] = Field(min_length=1)
    deferred_ciav_input_sha256: SHA256
    raw_evidence_content_sha256s: tuple[SHA256, ...]
    skipped_as_negative: Literal[False] = False
    long_term_write_blocked: Literal[True] = True
    certificate_sha256: SHA256

    @model_validator(mode="after")
    def validate_debt(self) -> AdaptiveInferenceDebtCertificate:
        if self.expiry_step <= self.created_step:
            raise ValueError("adaptive inference debt must expire after creation")
        ordered = tuple(
            operator
            for operator in STRUCTURE_TWO_OPERATOR_ORDER
            if operator in set(self.deferred_operators)
        )
        if ordered != self.deferred_operators or len(ordered) != len(set(ordered)):
            raise ValueError("deferred operators must be unique and production ordered")
        expected_id = uuid5(
            NAMESPACE_URL,
            content_sha256(
                {
                    "origin_path_id": self.origin_path_id,
                    "origin_transition_sha256": self.origin_transition_sha256,
                    "origin_state_sha256": self.origin_state_sha256,
                    "created_step": self.created_step,
                    "deferred_operators": self.deferred_operators,
                    "deferred_ciav_input_sha256": self.deferred_ciav_input_sha256,
                }
            ),
        )
        if self.debt_id != expected_id:
            raise ValueError("adaptive inference debt identity mismatch")
        unsigned = self.model_dump(mode="json", exclude={"certificate_sha256"})
        if self.certificate_sha256 != content_sha256(unsigned):
            raise ValueError("adaptive inference debt content hash mismatch")
        return self


def seal_adaptive_inference_debt(
    *,
    origin_path_id: str,
    origin_transition_sha256: str,
    origin_state_sha256: str,
    created_step: int,
    expiry_step: int,
    deferred_operators: tuple[RuntimeOperatorName, ...],
    deferred_ciav_input_sha256: str,
    raw_evidence_content_sha256s: tuple[str, ...],
) -> AdaptiveInferenceDebtCertificate:
    identity_payload = {
        "origin_path_id": origin_path_id,
        "origin_transition_sha256": origin_transition_sha256,
        "origin_state_sha256": origin_state_sha256,
        "created_step": created_step,
        "deferred_operators": deferred_operators,
        "deferred_ciav_input_sha256": deferred_ciav_input_sha256,
    }
    debt_id = uuid5(NAMESPACE_URL, content_sha256(identity_payload))
    payload = {
        "schema_version": "0.2.0",
        "debt_id": debt_id,
        **identity_payload,
        "expiry_step": expiry_step,
        "raw_evidence_content_sha256s": raw_evidence_content_sha256s,
        "skipped_as_negative": False,
        "long_term_write_blocked": True,
    }
    return AdaptiveInferenceDebtCertificate(
        **payload,
        certificate_sha256=content_sha256(payload),
    )


class RuntimeCallableBinding(ContractModel):
    """Source-bound identity for the concrete callable observed at one slot."""

    runtime_execution_id: UUID
    operator: RuntimeOperatorName
    binding_slot: NonNegativeInt
    binding_kind: InvocationBindingKind
    operator_instance_id: SHA256
    implementation_symbol: str = Field(min_length=1)
    implementation_source_sha256: SHA256
    loaded_callable_code_sha256: SHA256
    callable_symbol: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_instance_identity(self) -> RuntimeCallableBinding:
        expected = content_sha256(
            {
                "runtime_execution_id": self.runtime_execution_id,
                "operator": self.operator,
                "binding_slot": self.binding_slot,
                "binding_kind": self.binding_kind,
                "implementation_symbol": self.implementation_symbol,
                "implementation_source_sha256": self.implementation_source_sha256,
                "loaded_callable_code_sha256": self.loaded_callable_code_sha256,
                "callable_symbol": self.callable_symbol,
            }
        )
        if self.operator_instance_id != expected:
            raise ValueError("runtime callable binding instance identity mismatch")
        return self


def _code_object_payload(code: CodeType) -> tuple[object, ...]:
    """Return a stable semantic payload for one loaded Python code object."""

    return (
        code.co_argcount,
        code.co_posonlyargcount,
        code.co_kwonlyargcount,
        code.co_nlocals,
        code.co_stacksize,
        code.co_flags,
        code.co_code,
        tuple(
            _code_object_payload(value) if isinstance(value, CodeType) else value
            for value in code.co_consts
        ),
        code.co_names,
        code.co_varnames,
        code.co_name,
        code.co_qualname,
        code.co_firstlineno,
        code.co_linetable,
        code.co_exceptiontable,
        code.co_freevars,
        code.co_cellvars,
    )


def _code_object_sha256(code: CodeType) -> str:
    return hashlib.sha256(marshal.dumps(cast(Any, _code_object_payload(code)))).hexdigest()


def _source_code_objects(source_path: Path, source_bytes: bytes) -> tuple[CodeType, ...]:
    root = compile(source_bytes, str(source_path), "exec")
    discovered: list[CodeType] = []

    def visit(code: CodeType) -> None:
        discovered.append(code)
        for value in code.co_consts:
            if isinstance(value, CodeType):
                visit(value)

    visit(root)
    return tuple(discovered)


def _require_declared_implementation_member(
    *,
    operator: RuntimeOperatorName,
    implementation_type: type,
    instance: object,
    callable_name: str,
    callable_target: object,
) -> None:
    """Refuse a callable that is not the bound implementation type's own member.

    ``hard_safety_kernel.provenance_and_dependency_checks_always_executed`` is
    ``true`` for every legal path.  Checking only that a callable matches *its own*
    source file is not a provenance check: a function defined in any other module
    (or attached to a single instance) passes that test trivially while being
    receipted under the production implementation symbol.  The round-2 review's
    fault injection did exactly that and still produced seven verified rows.

    The bound callable must therefore be the attribute that the implementation
    type's own MRO declares under ``callable_name``, and it must report the
    defining class's module and qualified name -- which is what makes the
    subsequent source-file hash comparison meaningful.

    Scope, stated honestly: this is applied only where
    ``bind_runtime_callable(..., require_declared_member=True)`` asks for it, which
    today is the adaptive deferred-path safety-maintenance seam.  Those four nodes
    carry the entire write-safety argument of ``P0_SAFE_DEFERRED``, take no
    runtime-visible input that a downstream check could catch, and are instrumented
    by no production or test path.  Applying the same rule to every binding would
    also refuse the project's existing instance-level receipt instrumentation, so
    generalizing it is a separate decision, not a silent change.
    """

    instance_attributes = getattr(instance, "__dict__", None)
    if isinstance(instance_attributes, Mapping) and callable_name in instance_attributes:
        raise ValueError(
            f"bound production callable is shadowed by an instance attribute: "
            f"{operator}.{callable_name}"
        )
    owner = next(
        (base for base in implementation_type.__mro__ if callable_name in vars(base)),
        None,
    )
    if owner is None:
        raise ValueError(
            f"bound production callable is not declared by the bound implementation "
            f"type: {operator}.{callable_name}"
        )
    declared = vars(owner)[callable_name]
    if isinstance(declared, staticmethod | classmethod):
        declared = declared.__func__
    if declared is not callable_target:
        raise ValueError(
            f"bound production callable is not the declared class member: "
            f"{operator}.{callable_name}"
        )
    if (
        getattr(callable_target, "__module__", None) != owner.__module__
        or getattr(callable_target, "__qualname__", None) != f"{owner.__qualname__}.{callable_name}"
    ):
        raise ValueError(
            f"bound production callable does not belong to the bound implementation "
            f"type: {operator}.{callable_name}"
        )


def bind_runtime_callable(
    *,
    runtime_execution_id: UUID,
    operator: RuntimeOperatorName,
    binding_slot: int,
    binding_kind: InvocationBindingKind,
    instance: object,
    callable_name: str,
    require_declared_member: bool = False,
) -> RuntimeCallableBinding:
    """Bind an actual live object, callable, and its loaded source bytes.

    ``require_declared_member`` additionally refuses a callable that is not the
    implementation type's own declared member; see
    :func:`_require_declared_implementation_member` for why it is opt-in.
    """

    implementation_type = type(instance)
    method = getattr(instance, callable_name, None)
    if not callable(method):
        raise ValueError(f"bound production callable is missing: {operator}.{callable_name}")
    callable_target = method.__func__ if inspect.ismethod(method) else method
    if require_declared_member:
        _require_declared_implementation_member(
            operator=operator,
            implementation_type=implementation_type,
            instance=instance,
            callable_name=callable_name,
            callable_target=callable_target,
        )
    source_name = inspect.getsourcefile(callable_target)
    if source_name is None:
        raise ValueError(f"bound production implementation has no inspectable source: {operator}")
    source_path = Path(source_name).resolve()
    if not source_path.is_file():
        raise ValueError(f"bound production implementation source is unavailable: {operator}")
    implementation_symbol = f"{implementation_type.__module__}.{implementation_type.__qualname__}"
    callable_module = getattr(callable_target, "__module__", None)
    callable_qualname = getattr(callable_target, "__qualname__", None)
    if not isinstance(callable_module, str) or not isinstance(callable_qualname, str):
        raise ValueError(f"bound production callable has no stable symbol: {operator}")
    loaded_code = getattr(callable_target, "__code__", None)
    if not isinstance(loaded_code, CodeType):
        raise ValueError(f"bound production callable has no inspectable code object: {operator}")
    loaded_code_sha256 = _code_object_sha256(loaded_code)
    source_bytes = source_path.read_bytes()
    matching_source_codes = tuple(
        code
        for code in _source_code_objects(source_path, source_bytes)
        if code.co_qualname == loaded_code.co_qualname
    )
    if (
        len(matching_source_codes) != 1
        or _code_object_sha256(matching_source_codes[0]) != loaded_code_sha256
    ):
        raise ValueError(
            f"loaded production callable does not match the current source file: {operator}"
        )
    callable_symbol = f"{callable_module}.{callable_qualname}"
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    instance_id = content_sha256(
        {
            "runtime_execution_id": runtime_execution_id,
            "operator": operator,
            "binding_slot": binding_slot,
            "binding_kind": binding_kind,
            "implementation_symbol": implementation_symbol,
            "implementation_source_sha256": source_sha256,
            "loaded_callable_code_sha256": loaded_code_sha256,
            "callable_symbol": callable_symbol,
        }
    )
    return RuntimeCallableBinding(
        runtime_execution_id=runtime_execution_id,
        operator=operator,
        binding_slot=binding_slot,
        binding_kind=binding_kind,
        operator_instance_id=instance_id,
        implementation_symbol=implementation_symbol,
        implementation_source_sha256=source_sha256,
        loaded_callable_code_sha256=loaded_code_sha256,
        callable_symbol=callable_symbol,
    )


class OperatorInvocationReceipt(ContractModel):
    """Hash-chained receipt for a real call or a non-call disposition."""

    runtime_execution_id: UUID
    sequence: NonNegativeInt
    phase: TracePhaseName
    plan_id: str = Field(min_length=1)
    plan_sha256: SHA256
    operator: RuntimeOperatorName
    mode: ExecutionModeName
    status: ReceiptStatusName
    binding_slot: NonNegativeInt | None
    binding_kind: InvocationBindingKind | None
    operator_instance_id: SHA256 | None
    implementation_symbol: str | None
    implementation_source_sha256: SHA256 | None
    loaded_callable_code_sha256: SHA256 | None
    callable_symbol: str | None
    invocation_id: SHA256 | None
    consumed_output_ids: tuple[SHA256, ...]
    raw_input_sha256: SHA256
    input_payload_sha256: SHA256
    output_payload_sha256: SHA256
    output_id: SHA256
    elapsed_ns: NonNegativeInt = 0
    debt_certificate_sha256: SHA256 | None = None
    recomputed_reason: str | None = None
    previous_receipt_sha256: str
    receipt_sha256: SHA256

    @model_validator(mode="after")
    def validate_receipt(self) -> OperatorInvocationReceipt:
        expected_input = content_sha256(
            {
                "raw_input_sha256": self.raw_input_sha256,
                "consumed_output_ids": list(self.consumed_output_ids),
            }
        )
        if self.input_payload_sha256 != expected_input:
            raise ValueError("operator receipt input payload hash mismatch")
        expected_output_id = content_sha256(
            {
                "runtime_execution_id": self.runtime_execution_id,
                "sequence": self.sequence,
                "output_payload_sha256": self.output_payload_sha256,
            }
        )
        if self.output_id != expected_output_id:
            raise ValueError("operator receipt output identity mismatch")
        invocation_fields = (
            self.binding_slot,
            self.binding_kind,
            self.operator_instance_id,
            self.implementation_symbol,
            self.implementation_source_sha256,
            self.loaded_callable_code_sha256,
            self.callable_symbol,
            self.invocation_id,
        )
        if self.status == "executed":
            if self.mode not in {
                "legacy_default_executed",
                "mandatory_maintenance_executed",
                "refinement_executed",
            } or any(value is None for value in invocation_fields):
                raise ValueError("executed receipt lacks a complete live-call binding")
            if self.debt_certificate_sha256 is not None or self.recomputed_reason is not None:
                raise ValueError("executed receipt cannot claim a deferred or N/A disposition")
            expected_instance = content_sha256(
                {
                    "runtime_execution_id": self.runtime_execution_id,
                    "operator": self.operator,
                    "binding_slot": self.binding_slot,
                    "binding_kind": self.binding_kind,
                    "implementation_symbol": self.implementation_symbol,
                    "implementation_source_sha256": self.implementation_source_sha256,
                    "loaded_callable_code_sha256": self.loaded_callable_code_sha256,
                    "callable_symbol": self.callable_symbol,
                }
            )
            if self.operator_instance_id != expected_instance:
                raise ValueError("operator receipt instance identity mismatch")
            expected_invocation = content_sha256(
                {
                    "runtime_execution_id": self.runtime_execution_id,
                    "sequence": self.sequence,
                    "operator": self.operator,
                    "operator_instance_id": self.operator_instance_id,
                    "callable_symbol": self.callable_symbol,
                    "input_payload_sha256": self.input_payload_sha256,
                }
            )
            if self.invocation_id != expected_invocation:
                raise ValueError("operator receipt invocation identity mismatch")
        elif self.status == "deferred":
            if self.mode != "deferred_with_valid_debt_certificate":
                raise ValueError("deferred receipt mode mismatch")
            if any(value is not None for value in invocation_fields):
                raise ValueError("deferred disposition cannot impersonate a live invocation")
            if self.debt_certificate_sha256 is None or self.recomputed_reason is not None:
                raise ValueError("deferred disposition lacks its debt certificate")
        else:
            if self.mode != "not_applicable_with_recomputed_reason":
                raise ValueError("not-applicable receipt mode mismatch")
            if any(value is not None for value in invocation_fields):
                raise ValueError("not-applicable disposition cannot impersonate a live invocation")
            if self.debt_certificate_sha256 is not None or not self.recomputed_reason:
                raise ValueError("not-applicable disposition lacks a recomputed reason")
        unsigned = self.model_dump(mode="json", exclude={"receipt_sha256"})
        if self.receipt_sha256 != content_sha256(unsigned):
            raise ValueError("operator receipt content hash mismatch")
        return self


def seal_operator_receipt(
    *,
    runtime_execution_id: UUID,
    sequence: int,
    plan: StructureTwoExecutionPlan,
    operator: RuntimeOperatorName,
    mode: ExecutionModeName,
    status: ReceiptStatusName,
    raw_input: object,
    output: object,
    consumed_output_ids: tuple[str, ...],
    previous_receipt_sha256: str,
    phase: TracePhaseName = "ordinary_transition",
    elapsed_ns: int = 0,
    binding: RuntimeCallableBinding | None = None,
    debt_certificate_sha256: str | None = None,
    recomputed_reason: str | None = None,
) -> OperatorInvocationReceipt:
    """Seal one receipt; caller data never supplies identities or hashes directly."""

    if binding is not None and (
        binding.runtime_execution_id != runtime_execution_id or binding.operator != operator
    ):
        raise ValueError("runtime callable binding does not match this invocation")
    raw_input_sha256 = content_sha256(raw_input)
    input_payload_sha256 = content_sha256(
        {
            "raw_input_sha256": raw_input_sha256,
            "consumed_output_ids": list(consumed_output_ids),
        }
    )
    output_payload_sha256 = content_sha256(output)
    output_id = content_sha256(
        {
            "runtime_execution_id": runtime_execution_id,
            "sequence": sequence,
            "output_payload_sha256": output_payload_sha256,
        }
    )
    invocation_id = (
        content_sha256(
            {
                "runtime_execution_id": runtime_execution_id,
                "sequence": sequence,
                "operator": operator,
                "operator_instance_id": binding.operator_instance_id,
                "callable_symbol": binding.callable_symbol,
                "input_payload_sha256": input_payload_sha256,
            }
        )
        if binding is not None
        else None
    )
    payload = {
        "runtime_execution_id": runtime_execution_id,
        "sequence": sequence,
        "phase": phase,
        "plan_id": plan.plan_id,
        "plan_sha256": plan.content_sha256,
        "operator": operator,
        "mode": mode,
        "status": status,
        "binding_slot": binding.binding_slot if binding else None,
        "binding_kind": binding.binding_kind if binding else None,
        "operator_instance_id": binding.operator_instance_id if binding else None,
        "implementation_symbol": binding.implementation_symbol if binding else None,
        "implementation_source_sha256": (binding.implementation_source_sha256 if binding else None),
        "loaded_callable_code_sha256": (binding.loaded_callable_code_sha256 if binding else None),
        "callable_symbol": binding.callable_symbol if binding else None,
        "invocation_id": invocation_id,
        "consumed_output_ids": consumed_output_ids,
        "raw_input_sha256": raw_input_sha256,
        "input_payload_sha256": input_payload_sha256,
        "output_payload_sha256": output_payload_sha256,
        "output_id": output_id,
        "elapsed_ns": elapsed_ns,
        "debt_certificate_sha256": debt_certificate_sha256,
        "recomputed_reason": recomputed_reason,
        "previous_receipt_sha256": previous_receipt_sha256,
    }
    return OperatorInvocationReceipt(**payload, receipt_sha256=content_sha256(payload))


class StructureTwoExecutionTrace(ContractModel):
    """Immutable batch submitted to a trace sink after one successful transition."""

    schema_version: Literal["0.1.0"] = "0.1.0"
    contract_version: Literal["structure-two-execution-contract@0.1"] = EXECUTION_CONTRACT_VERSION
    runtime_execution_id: UUID
    runtime_symbol: str = Field(min_length=1)
    system_version: str = Field(min_length=1)
    plan: StructureTwoExecutionPlan
    plan_sha256: SHA256
    transition_sha256: SHA256
    initial_state_sha256: SHA256
    final_state_sha256: SHA256
    final_output_sha256: SHA256
    adaptive_router_feature_sha256: SHA256 | None = None
    adaptive_router_source_state_sha256: SHA256 | None = None
    adaptive_authorization_policy_sha256: SHA256 | None = None
    adaptive_path_selection_receipt_sha256: SHA256 | None = None
    adaptive_ciav_input_sha256: SHA256 | None = None
    adaptive_step_index: NonNegativeInt | None = None
    adaptive_debt_expiry_steps: NonNegativeInt | None = None
    receipts: tuple[OperatorInvocationReceipt, ...]
    debt_certificates: tuple[AdaptiveInferenceDebtCertificate, ...] = ()
    replayed_debt_certificates: tuple[AdaptiveInferenceDebtCertificate, ...] = ()
    feedback_observation_acquired: bool = False
    feedback_closure_kind: FeedbackClosureKind = "none"
    all_seven_operators_invoked: bool = False
    adaptive_legal_path_executed: bool = False
    ciav_invoked: bool = False
    scientific_evidence_authorized: Literal[False] = False
    cross_system_trace_state_atomicity_established: Literal[False] = False
    claim_boundary: str = Field(min_length=1, default=TRACE_CLAIM_BOUNDARY)
    trace_sha256: SHA256

    @model_validator(mode="after")
    def validate_trace(self) -> StructureTwoExecutionTrace:
        if self.plan_sha256 != self.plan.content_sha256:
            raise ValueError("execution trace plan hash mismatch")
        if self.plan.lane == "legacy_ordinary_transition":
            self._validate_legacy_trace()
        else:
            self._validate_adaptive_trace()
        unsigned = self.model_dump(mode="json", exclude={"trace_sha256"})
        if self.trace_sha256 != content_sha256(unsigned):
            raise ValueError("execution trace content hash mismatch")
        return self

    def _validate_receipt_chain(self) -> None:
        previous = GENESIS_RECEIPT_SHA256
        invocation_ids: set[str] = set()
        output_ids: set[str] = set()
        for index, receipt in enumerate(self.receipts):
            if (
                receipt.runtime_execution_id != self.runtime_execution_id
                or receipt.sequence != index
                or receipt.plan_id != self.plan.plan_id
                or receipt.plan_sha256 != self.plan_sha256
                or receipt.previous_receipt_sha256 != previous
            ):
                raise ValueError("execution trace receipt order or plan binding mismatch")
            if any(item not in output_ids for item in receipt.consumed_output_ids):
                raise ValueError("execution trace consumed an unavailable prior output")
            if receipt.output_id in output_ids:
                raise ValueError("execution trace contains a duplicate output identity")
            output_ids.add(receipt.output_id)
            if receipt.invocation_id is not None:
                if receipt.invocation_id in invocation_ids:
                    raise ValueError("execution trace contains a duplicate invocation identity")
                invocation_ids.add(receipt.invocation_id)
            previous = receipt.receipt_sha256

    def _validate_legacy_trace(self) -> None:
        if len(self.receipts) != len(STRUCTURE_TWO_OPERATOR_ORDER):
            raise ValueError("legacy execution trace must contain seven dispositions")
        if (
            self.debt_certificates
            or self.replayed_debt_certificates
            or self.feedback_observation_acquired
            or self.feedback_closure_kind != "none"
            or any(
                value is not None
                for value in (
                    self.adaptive_router_feature_sha256,
                    self.adaptive_router_source_state_sha256,
                    self.adaptive_authorization_policy_sha256,
                    self.adaptive_path_selection_receipt_sha256,
                    self.adaptive_ciav_input_sha256,
                    self.adaptive_step_index,
                    self.adaptive_debt_expiry_steps,
                )
            )
        ):
            raise ValueError("legacy execution trace cannot carry adaptive routing evidence")
        self._validate_receipt_chain()
        outputs_by_operator: dict[str, str] = {}
        for directive, receipt in zip(
            self.plan.operator_directives,
            self.receipts,
            strict=True,
        ):
            if (
                receipt.phase != "ordinary_transition"
                or receipt.operator != directive.operator
                or receipt.mode != directive.mode
            ):
                raise ValueError("legacy receipt disposition drifted")
            expected_consumed = tuple(
                outputs_by_operator[operator]
                for operator in LEGACY_CONSUMPTION_GRAPH[directive.operator]
            )
            if receipt.consumed_output_ids != expected_consumed:
                raise ValueError("legacy execution trace output-consumption DAG mismatch")
            outputs_by_operator[directive.operator] = receipt.output_id
        if any(receipt.status != "executed" for receipt in self.receipts[:6]):
            raise ValueError("legacy transition must bind its six real executed stages")
        if tuple(receipt.binding_kind for receipt in self.receipts) != LEGACY_BINDING_KINDS:
            raise ValueError("legacy transition callable-binding semantics drifted")
        if self.receipts[-1].status != "not_applicable":
            raise ValueError("legacy transition must keep CIAV as a non-invocation disposition")
        if (
            self.all_seven_operators_invoked
            or self.adaptive_legal_path_executed
            or self.ciav_invoked
        ):
            raise ValueError("legacy trace cannot claim adaptive or seven-operator execution")
        if self.claim_boundary != TRACE_CLAIM_BOUNDARY:
            raise ValueError("execution trace claim boundary drifted")

    def _validate_adaptive_trace(self) -> None:
        if len(self.receipts) < len(STRUCTURE_TWO_OPERATOR_ORDER):
            raise ValueError("adaptive trace lacks the seven selected-path dispositions")
        if any(
            value is None
            for value in (
                self.adaptive_router_feature_sha256,
                self.adaptive_router_source_state_sha256,
                self.adaptive_authorization_policy_sha256,
                self.adaptive_path_selection_receipt_sha256,
                self.adaptive_step_index,
                self.adaptive_debt_expiry_steps,
            )
        ):
            raise ValueError("adaptive trace lacks its source-bound routing evidence")
        if self.adaptive_debt_expiry_steps == 0:
            raise ValueError("adaptive trace debt expiry horizon must be positive")
        if (
            self.plan.plan_id in ADAPTIVE_FEEDBACK_CLOSURE_PATHS
            and self.adaptive_ciav_input_sha256 is None
        ):
            raise ValueError("CIAV execution path lacks its runtime-input binding")
        assert self.adaptive_step_index is not None
        assert self.adaptive_debt_expiry_steps is not None
        self._validate_receipt_chain()
        primary = self.receipts[: len(STRUCTURE_TWO_OPERATOR_ORDER)]
        primary_outputs: dict[str, str] = {}
        primary_graph = ADAPTIVE_PRIMARY_CONSUMPTION_GRAPHS[self.plan.plan_id]
        for directive, receipt in zip(
            self.plan.operator_directives,
            primary,
            strict=True,
        ):
            if (
                receipt.phase != "selected_path"
                or receipt.operator != directive.operator
                or receipt.mode != directive.mode
            ):
                raise ValueError("adaptive selected-path disposition drifted")
            expected_status = (
                "deferred"
                if directive.mode == "deferred_with_valid_debt_certificate"
                else "not_applicable"
                if directive.mode == "not_applicable_with_recomputed_reason"
                else "executed"
            )
            if receipt.status != expected_status:
                raise ValueError("adaptive selected-path execution status mismatch")
            expected_consumed = tuple(
                primary_outputs[operator] for operator in primary_graph[directive.operator]
            )
            if receipt.consumed_output_ids != expected_consumed:
                raise ValueError("adaptive selected-path output-consumption DAG mismatch")
            primary_outputs[directive.operator] = receipt.output_id

        certificate_by_hash = {item.certificate_sha256: item for item in self.debt_certificates}
        if len(certificate_by_hash) != len(self.debt_certificates):
            raise ValueError("adaptive trace repeats an inference debt certificate")
        referenced_debt_hashes: set[str] = set()
        for receipt in primary:
            if receipt.status != "deferred":
                continue
            certificate = certificate_by_hash.get(receipt.debt_certificate_sha256 or "")
            if certificate is None or receipt.operator not in certificate.deferred_operators:
                raise ValueError("adaptive deferral is not covered by a valid debt certificate")
            if certificate.origin_path_id != self.plan.plan_id:
                raise ValueError("adaptive debt certificate path mismatch")
            if (
                certificate.origin_transition_sha256 != self.transition_sha256
                or certificate.origin_state_sha256 != self.adaptive_router_source_state_sha256
                or certificate.created_step != self.adaptive_step_index
                or certificate.expiry_step
                != self.adaptive_step_index + self.adaptive_debt_expiry_steps
            ):
                raise ValueError("adaptive debt certificate origin binding mismatch")
            referenced_debt_hashes.add(certificate.certificate_sha256)
        if referenced_debt_hashes != set(certificate_by_hash):
            raise ValueError("adaptive trace contains unreferenced debt certificates")
        replayed_hashes = [item.certificate_sha256 for item in self.replayed_debt_certificates]
        if len(replayed_hashes) != len(set(replayed_hashes)):
            raise ValueError("adaptive trace repeats a replayed debt certificate")
        if set(replayed_hashes) & set(certificate_by_hash):
            raise ValueError("adaptive trace cannot create and settle the same debt")
        if self.replayed_debt_certificates:
            if self.plan.plan_id != "P5_FULL_EAGER":
                raise ValueError("only P5 can settle production inference debt")
            if any(
                item.origin_transition_sha256 != self.transition_sha256
                for item in self.replayed_debt_certificates
            ):
                raise ValueError("replayed debt does not bind the executed transition")

        ciav_receipt = primary[-1]
        ciav_invoked = ciav_receipt.status == "executed"
        all_seven = all(receipt.status == "executed" for receipt in primary)
        if self.ciav_invoked != ciav_invoked or self.all_seven_operators_invoked != all_seven:
            raise ValueError("adaptive trace invocation summary mismatch")
        if not self.adaptive_legal_path_executed:
            raise ValueError("valid adaptive trace must identify its registered path execution")

        closure = self.receipts[len(STRUCTURE_TWO_OPERATOR_ORDER) :]
        if self.feedback_observation_acquired:
            if not ciav_invoked or self.plan.plan_id not in ADAPTIVE_FEEDBACK_CLOSURE_PATHS:
                raise ValueError("feedback closure requires an eligible executed CIAV path")
            if self.feedback_closure_kind == "full_transition":
                if len(closure) != 6:
                    raise ValueError(
                        "adaptive transition feedback must execute six downstream stages"
                    )
                if (
                    tuple(receipt.operator for receipt in closure)
                    != STRUCTURE_TWO_OPERATOR_ORDER[:6]
                ):
                    raise ValueError("adaptive feedback closure operator order drifted")
                if any(
                    receipt.phase != "feedback_closure"
                    or receipt.status != "executed"
                    or receipt.mode != "refinement_executed"
                    for receipt in closure
                ):
                    raise ValueError("adaptive feedback closure disposition mismatch")
                closure_outputs: dict[str, str] = {}
                for receipt in closure:
                    expected_ids: list[str] = []
                    for operator in ADAPTIVE_FEEDBACK_CONSUMPTION_GRAPH[receipt.operator]:
                        if operator == "ciav":
                            expected_ids.append(primary_outputs["ciav"])
                        else:
                            expected_ids.append(closure_outputs[operator])
                    if receipt.consumed_output_ids != tuple(expected_ids):
                        raise ValueError("adaptive feedback output-consumption DAG mismatch")
                    closure_outputs[receipt.operator] = receipt.output_id
            elif self.feedback_closure_kind == "same_location_fast_verification":
                if (
                    len(closure) != 1
                    or closure[0].operator != "opceu"
                    or closure[0].phase != "feedback_closure"
                    or closure[0].status != "executed"
                    or closure[0].mode != "refinement_executed"
                    or closure[0].binding_kind != "adaptive_composite_stage"
                    or closure[0].consumed_output_ids != (primary_outputs["ciav"],)
                ):
                    raise ValueError("same-location fast verification closure drifted")
            else:
                raise ValueError("acquired CIAV observation lacks a closure kind")
        elif closure or self.feedback_closure_kind != "none":
            raise ValueError("adaptive trace has feedback calls without an acquired observation")
        if self.claim_boundary != ADAPTIVE_TRACE_CLAIM_BOUNDARY:
            raise ValueError("adaptive execution trace claim boundary drifted")


def seal_execution_trace(
    *,
    runtime_execution_id: UUID,
    runtime_symbol: str,
    system_version: str,
    plan: StructureTwoExecutionPlan,
    transition_sha256: str,
    initial_state_sha256: str,
    final_state_sha256: str,
    final_output_sha256: str,
    receipts: tuple[OperatorInvocationReceipt, ...],
    adaptive_router_feature_sha256: str | None = None,
    adaptive_router_source_state_sha256: str | None = None,
    adaptive_authorization_policy_sha256: str | None = None,
    adaptive_path_selection_receipt_sha256: str | None = None,
    adaptive_ciav_input_sha256: str | None = None,
    adaptive_step_index: int | None = None,
    adaptive_debt_expiry_steps: int | None = None,
    debt_certificates: tuple[AdaptiveInferenceDebtCertificate, ...] = (),
    replayed_debt_certificates: tuple[AdaptiveInferenceDebtCertificate, ...] = (),
    feedback_observation_acquired: bool = False,
    feedback_closure_kind: FeedbackClosureKind = "none",
) -> StructureTwoExecutionTrace:
    adaptive = plan.lane == "registered_adaptive_path"
    primary = receipts[: len(STRUCTURE_TWO_OPERATOR_ORDER)]
    ciav_invoked = bool(adaptive and len(primary) == 7 and primary[-1].status == "executed")
    all_seven_invoked = bool(
        adaptive and len(primary) == 7 and all(receipt.status == "executed" for receipt in primary)
    )
    payload = {
        "schema_version": "0.1.0",
        "contract_version": EXECUTION_CONTRACT_VERSION,
        "runtime_execution_id": runtime_execution_id,
        "runtime_symbol": runtime_symbol,
        "system_version": system_version,
        "plan": plan,
        "plan_sha256": plan.content_sha256,
        "transition_sha256": transition_sha256,
        "initial_state_sha256": initial_state_sha256,
        "final_state_sha256": final_state_sha256,
        "final_output_sha256": final_output_sha256,
        "adaptive_router_feature_sha256": adaptive_router_feature_sha256,
        "adaptive_router_source_state_sha256": adaptive_router_source_state_sha256,
        "adaptive_authorization_policy_sha256": adaptive_authorization_policy_sha256,
        "adaptive_path_selection_receipt_sha256": (adaptive_path_selection_receipt_sha256),
        "adaptive_ciav_input_sha256": adaptive_ciav_input_sha256,
        "adaptive_step_index": adaptive_step_index,
        "adaptive_debt_expiry_steps": adaptive_debt_expiry_steps,
        "receipts": receipts,
        "debt_certificates": debt_certificates,
        "replayed_debt_certificates": replayed_debt_certificates,
        "feedback_observation_acquired": feedback_observation_acquired,
        "feedback_closure_kind": feedback_closure_kind,
        "all_seven_operators_invoked": all_seven_invoked,
        "adaptive_legal_path_executed": adaptive,
        "ciav_invoked": ciav_invoked,
        "scientific_evidence_authorized": False,
        "cross_system_trace_state_atomicity_established": False,
        "claim_boundary": ADAPTIVE_TRACE_CLAIM_BOUNDARY if adaptive else TRACE_CLAIM_BOUNDARY,
    }
    return StructureTwoExecutionTrace(**payload, trace_sha256=content_sha256(payload))


def verify_execution_trace(trace: StructureTwoExecutionTrace) -> None:
    """Revalidate hashes and semantics even if a caller used model construction tricks."""

    StructureTwoExecutionTrace.model_validate(trace.model_dump(mode="json"))


class TraceCommitAck(ContractModel):
    """Exact acknowledgement required before a traced model transition may return."""

    runtime_execution_id: UUID
    trace_sha256: SHA256
    accepted_receipt_count: NonNegativeInt
    accepted: Literal[True] = True
    sink_commit_id: UUID
    ack_sha256: SHA256

    @model_validator(mode="after")
    def validate_ack_hash(self) -> TraceCommitAck:
        unsigned = self.model_dump(mode="json", exclude={"ack_sha256"})
        if self.ack_sha256 != content_sha256(unsigned):
            raise ValueError("trace sink acknowledgement hash mismatch")
        return self


def seal_trace_commit_ack(
    trace: StructureTwoExecutionTrace, *, sink_commit_id: UUID | None = None
) -> TraceCommitAck:
    payload = {
        "runtime_execution_id": trace.runtime_execution_id,
        "trace_sha256": trace.trace_sha256,
        "accepted_receipt_count": len(trace.receipts),
        "accepted": True,
        "sink_commit_id": sink_commit_id or uuid4(),
    }
    return TraceCommitAck(**payload, ack_sha256=content_sha256(payload))


def verify_trace_commit_ack(
    ack: TraceCommitAck,
    *,
    trace: StructureTwoExecutionTrace,
) -> None:
    verify_execution_trace(trace)
    TraceCommitAck.model_validate(ack.model_dump(mode="json"))
    if (
        ack.runtime_execution_id != trace.runtime_execution_id
        or ack.trace_sha256 != trace.trace_sha256
        or ack.accepted_receipt_count != len(trace.receipts)
    ):
        raise ValueError("trace sink acknowledgement does not match the committed trace")


class TraceAbortAck(ContractModel):
    """Tombstone acknowledgement for a failed or invalid trace commit attempt."""

    runtime_execution_id: UUID
    trace_sha256: SHA256
    reason_sha256: SHA256
    aborted: Literal[True] = True
    sink_abort_id: UUID
    ack_sha256: SHA256

    @model_validator(mode="after")
    def validate_ack_hash(self) -> TraceAbortAck:
        unsigned = self.model_dump(mode="json", exclude={"ack_sha256"})
        if self.ack_sha256 != content_sha256(unsigned):
            raise ValueError("trace sink abort acknowledgement hash mismatch")
        return self


def seal_trace_abort_ack(
    trace: StructureTwoExecutionTrace,
    *,
    reason: str,
    sink_abort_id: UUID | None = None,
) -> TraceAbortAck:
    payload = {
        "runtime_execution_id": trace.runtime_execution_id,
        "trace_sha256": trace.trace_sha256,
        "reason_sha256": content_sha256(reason),
        "aborted": True,
        "sink_abort_id": sink_abort_id or uuid4(),
    }
    return TraceAbortAck(**payload, ack_sha256=content_sha256(payload))


def verify_trace_abort_ack(
    ack: TraceAbortAck,
    *,
    trace: StructureTwoExecutionTrace,
    reason: str,
) -> None:
    verify_execution_trace(trace)
    TraceAbortAck.model_validate(ack.model_dump(mode="json"))
    if (
        ack.runtime_execution_id != trace.runtime_execution_id
        or ack.trace_sha256 != trace.trace_sha256
        or ack.reason_sha256 != content_sha256(reason)
    ):
        raise ValueError("trace sink abort acknowledgement does not match the attempted trace")


@runtime_checkable
class TraceSink(Protocol):
    """Sink must idempotently commit or tombstone one complete trace batch.

    This protocol supplies compensation for a commit that raises or returns an
    invalid acknowledgement.  It does not by itself prove a distributed atomic
    transaction or independent custody; those remain separate readiness gates.
    """

    def commit(self, trace: StructureTwoExecutionTrace, /) -> TraceCommitAck: ...

    def abort(self, trace: StructureTwoExecutionTrace, /, *, reason: str) -> TraceAbortAck: ...


class UnsupportedStructureTwoExecutionPlan(ValueError):
    """Raised before state mutation for a plan whose kernels are not production-bound."""


class TraceCompensationError(RuntimeError):
    """Raised when rollback succeeds but sink/lock compensation is not verifiable."""


class AdaptiveMaintenanceContractError(ValueError):
    """Raised, before any state mutation, by a deferred path's maintenance checks.

    The frozen pre-death protocol's ``hard_safety_kernel`` requires
    ``provenance_and_dependency_checks_always_executed`` and caps
    ``maximum_safety_violations`` / ``maximum_provenance_violations`` /
    ``maximum_unresolved_as_negative_events`` at zero.  A deferred path whose
    declared upstream dependency arrives absent, malformed, stale, foreign, or
    self-contradicting has failed that kernel, so the transaction fails closed
    instead of emitting a receipt that claims a check which did not happen.
    """


__all__ = [
    "ADAPTIVE_FEEDBACK_CLOSURE_PATHS",
    "ADAPTIVE_TRACE_CLAIM_BOUNDARY",
    "EXECUTION_CONTRACT_VERSION",
    "GENESIS_RECEIPT_SHA256",
    "LEGACY_CIAV_NOT_APPLICABLE_REASON",
    "LEGACY_PLAN_ID",
    "REGISTERED_ADAPTIVE_PATH_MODES",
    "STRUCTURE_TWO_OPERATOR_ORDER",
    "AdaptiveInferenceDebtCertificate",
    "AdaptiveMaintenanceContractError",
    "FeedbackClosureKind",
    "OperatorExecutionDirective",
    "OperatorInvocationReceipt",
    "RuntimeCallableBinding",
    "StructureTwoExecutionPlan",
    "StructureTwoExecutionTrace",
    "TraceAbortAck",
    "TraceCommitAck",
    "TraceCompensationError",
    "TraceSink",
    "UnsupportedStructureTwoExecutionPlan",
    "bind_runtime_callable",
    "canonical_legacy_ordinary_transition_plan",
    "registered_adaptive_execution_plan",
    "seal_adaptive_inference_debt",
    "seal_execution_trace",
    "seal_operator_receipt",
    "seal_trace_abort_ack",
    "seal_trace_commit_ack",
    "verify_execution_trace",
    "verify_trace_abort_ack",
    "verify_trace_commit_ack",
]
