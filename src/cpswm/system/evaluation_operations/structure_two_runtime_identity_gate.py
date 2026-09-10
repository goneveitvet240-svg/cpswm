"""Fail-closed runtime-identity audit for the historical Route-C v0.2 run.

The v0.2 artifact contains useful semantic and state-machine receipts, but its
production assembly manifest is a post-run sidecar.  It does not bind the
``LearnedInteractionRuntime`` object that emitted the trajectories to concrete
operator instances, calls, or downstream consumption.  This module records that
boundary without rewriting the historical artifact.  Architecture A now binds
legacy ordinary transitions to ``StructureTwoProductionSystem`` and hosts the
current partial P0-P5 control-flow lane.  That lane's full consequential
runtime-identity gate remains false until production-owned feature extraction,
distinct path kernels, and registered fallback are bound; neither fact
retroactively binds the historical Route-C trajectories to that runtime.

The module also defines a small, pure structural verifier for a prospective
evidence contract.  It checks schema, hashes, and dependency-DAG non-vacuity,
but it cannot observe a live call and therefore can never establish runtime
identity or pass the runtime-identity gate.  Architecture A may reuse the
structural pieces only after adding run/step state-machine semantics and an
execution witness controlled outside the evidence producer.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

from cpswm.system.evaluation_operations.structure_two_full_scientific_loop import (
    verify_full_scientific_loop_result,
)
from cpswm.system.reproducibility import content_sha256

PROTOCOL_ID: Final = "structure-two-runtime-identity-gate@0.1"
SCHEMA_VERSION: Final = "0.1.0"
DEFAULT_CONFIG: Final = Path(
    "configs/project_two_experiments/structure_two_runtime_identity_gate_v0_1.json"
)
DEFAULT_RUNNER: Final = Path("apps/evaluation_runner/run_structure_two_runtime_identity_gate.py")
SHA256_LENGTH: Final = 64
GENESIS: Final = "GENESIS"
CANONICAL_OPERATORS: Final = (
    "opceu",
    "orrer_cheh",
    "pchmp",
    "cf_bocpd",
    "ccrr",
    "rgrc",
    "ciav",
)
REQUIRED_TRACE_BINDING_FIELDS: Final = (
    "runtime_execution_id",
    "operator_instance_id",
    "callable_symbol",
    "invocation_id",
    "consumed_output_ids",
)
SELECTED_GLOBAL_RUNTIME: Final = (
    "cpswm.system.structure_two_production_system.StructureTwoProductionSystem"
)

CLAIM_BOUNDARY: Final = (
    "This local gate audits whether a Route-C trajectory is bound to the runtime and "
    "operator instances that produced it. Architecture A now binds legacy ordinary transitions "
    "to StructureTwoProductionSystem and hosts the current partial P0-P5 control-flow lane. "
    "This historical gate does not establish that lane's production-state-derived path choice, "
    "distinct path kernels, fallback state machine, or full consequential identity; retroactively "
    "establish historical Route-C equivalence; provide independent custody; or promote "
    "development evidence."
)


class ArchitectureSelectionStatus(StrEnum):
    A_SELECTED_STRUCTURE_TWO_PRODUCTION_SYSTEM = "A_SELECTED_STRUCTURE_TWO_PRODUCTION_SYSTEM"


class RuntimeIdentityEvidenceStatus(StrEnum):
    MISSING_LIVE_RUNTIME_OPERATOR_CALL_CONSUMPTION_BINDING = (
        "MISSING_LIVE_RUNTIME_OPERATOR_CALL_CONSUMPTION_BINDING"
    )
    STRUCTURAL_CANDIDATE_ONLY_NO_LIVE_EXECUTION_AUTHORITY = (
        "STRUCTURAL_CANDIDATE_ONLY_NO_LIVE_EXECUTION_AUTHORITY"
    )


class TraceEventKind(StrEnum):
    OPERATOR_CALL = "operator_call"
    CONSUMER = "consumer"


class ConsequentialConsumer(StrEnum):
    ACTION_READOUT = "action_readout"
    ENVIRONMENT_TRANSITION = "environment_transition"
    NEXT_STEP_STATE = "next_step_state"


@dataclass(frozen=True, slots=True)
class RuntimeIdentityGateConfig:
    source_artifact: Path
    full_loop_implementation: Path
    stateful_runtime_implementation: Path
    production_system_implementation: Path
    expected_observed_route_runtime: str
    expected_sidecar_runtime: str
    route_run_function: str
    top_level_run_function: str
    sidecar_builder_function: str
    required_operators: tuple[str, ...]
    required_trace_binding_fields: tuple[str, ...]
    architecture_selection_status: ArchitectureSelectionStatus


@dataclass(frozen=True, slots=True)
class RuntimeIdentityEvidenceAssessment:
    """Non-authoritative result of validating a caller-controlled candidate."""

    structural_candidate: bool
    enrollment_reference_matched: bool
    evidence_reference_matched: bool
    independent_execution_authority_verified: bool
    live_runtime_identity_established: bool
    runtime_identity_gate_passed: bool
    evidence_status: RuntimeIdentityEvidenceStatus


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{label} schema drift or extra claim field")


def _strict_json(path: Path) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key in {path}: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> Any:
        raise ValueError(f"non-standard JSON numeric constant in {path}: {value}")

    value = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=reject_duplicates,
        parse_constant=reject_constant,
    )
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _reject_nonfinite(value: Any, path: str = "$") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"non-finite number at {path}")
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_nonfinite(item, f"{path}/{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            _reject_nonfinite(item, f"{path}/{index}")


def _safe_repository_file(repository_root: Path, relative: Path) -> Path:
    root = repository_root.resolve()
    resolved = (root / relative).resolve()
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or not resolved.is_relative_to(root)
        or not resolved.is_file()
    ):
        raise ValueError(f"runtime-identity input is not a repository-local file: {relative}")
    return resolved


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == SHA256_LENGTH
        and all(character in "0123456789abcdef" for character in value)
    )


def _verify_historical_artifact_integrity(artifact: Mapping[str, Any]) -> None:
    """Verify retained bytes without requiring their source snapshot to be current."""

    stored = artifact.get("content_sha256")
    unsigned = dict(artifact)
    unsigned.pop("content_sha256", None)
    if not _is_sha256(stored) or stored != content_sha256(unsigned):
        raise ValueError("historical Route-C artifact content hash mismatch")
    assembly = artifact.get("production_system_assembly")
    if not isinstance(assembly, Mapping):
        raise ValueError("historical Route-C production assembly is missing")
    assembly_stored = assembly.get("content_sha256")
    assembly_unsigned = dict(assembly)
    assembly_unsigned.pop("content_sha256", None)
    if not _is_sha256(assembly_stored) or assembly_stored != content_sha256(assembly_unsigned):
        raise ValueError("historical Route-C production assembly content hash mismatch")


def _current_source_verification_failure_code(error: ValueError) -> str | None:
    """Return a stable category without recording brittle paths or exception text."""

    message = str(error)
    if "full scientific loop source binding mismatch" in message:
        return "FULL_LOOP_CURRENT_SOURCE_BINDING_MISMATCH"
    if "Structure-Two production assembly manifest mismatch" in message:
        return "PRODUCTION_ASSEMBLY_CURRENT_SOURCE_BINDING_MISMATCH"
    return None


def load_runtime_identity_gate_config(
    repository_root: Path,
    path: Path = DEFAULT_CONFIG,
) -> RuntimeIdentityGateConfig:
    config_path = _safe_repository_file(repository_root, path)
    payload = _strict_json(config_path)
    _require_exact_keys(
        payload,
        {
            "schema_version",
            "protocol_id",
            "source_artifact",
            "full_loop_implementation",
            "stateful_runtime_implementation",
            "production_system_implementation",
            "expected_observed_route_runtime",
            "expected_sidecar_runtime",
            "route_run_function",
            "top_level_run_function",
            "sidecar_builder_function",
            "required_operators",
            "required_trace_binding_fields",
            "architecture_selection_status",
            "claim_boundary",
        },
        "runtime-identity configuration",
    )
    if payload["schema_version"] != SCHEMA_VERSION or payload["protocol_id"] != PROTOCOL_ID:
        raise ValueError("runtime-identity configuration protocol/version mismatch")
    if payload["architecture_selection_status"] != (
        ArchitectureSelectionStatus.A_SELECTED_STRUCTURE_TWO_PRODUCTION_SYSTEM.value
    ):
        raise ValueError("runtime-identity configuration architecture-A selection drifted")
    if payload["claim_boundary"] != CLAIM_BOUNDARY:
        raise ValueError("runtime-identity claim boundary drifted")
    sequence_fields = ("required_operators", "required_trace_binding_fields")
    if any(
        not isinstance(payload[field], list)
        or not payload[field]
        or not all(isinstance(item, str) and item for item in payload[field])
        or len(payload[field]) != len(set(payload[field]))
        for field in sequence_fields
    ):
        raise ValueError("runtime-identity required fields are malformed")
    if tuple(payload["required_operators"]) != CANONICAL_OPERATORS:
        raise ValueError("runtime-identity configuration changed the canonical operator set")
    if tuple(payload["required_trace_binding_fields"]) != REQUIRED_TRACE_BINDING_FIELDS:
        raise ValueError("runtime-identity configuration weakened the required trace binding")
    path_fields = (
        "source_artifact",
        "full_loop_implementation",
        "stateful_runtime_implementation",
        "production_system_implementation",
    )
    paths = {field: Path(payload[field]) for field in path_fields}
    for relative in paths.values():
        _safe_repository_file(repository_root, relative)
    scalar_fields = (
        "expected_observed_route_runtime",
        "expected_sidecar_runtime",
        "route_run_function",
        "top_level_run_function",
        "sidecar_builder_function",
    )
    if any(not isinstance(payload[field], str) or not payload[field] for field in scalar_fields):
        raise ValueError("runtime-identity symbolic binding is malformed")
    if payload["expected_sidecar_runtime"] != SELECTED_GLOBAL_RUNTIME:
        raise ValueError("runtime-identity configuration selected the wrong production runtime")
    return RuntimeIdentityGateConfig(
        source_artifact=paths["source_artifact"],
        full_loop_implementation=paths["full_loop_implementation"],
        stateful_runtime_implementation=paths["stateful_runtime_implementation"],
        production_system_implementation=paths["production_system_implementation"],
        expected_observed_route_runtime=payload["expected_observed_route_runtime"],
        expected_sidecar_runtime=payload["expected_sidecar_runtime"],
        route_run_function=payload["route_run_function"],
        top_level_run_function=payload["top_level_run_function"],
        sidecar_builder_function=payload["sidecar_builder_function"],
        required_operators=tuple(payload["required_operators"]),
        required_trace_binding_fields=tuple(payload["required_trace_binding_fields"]),
        architecture_selection_status=(
            ArchitectureSelectionStatus.A_SELECTED_STRUCTURE_TWO_PRODUCTION_SYSTEM
        ),
    )


def _function_node(tree: ast.Module, name: str) -> ast.FunctionDef:
    matches = [
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one function named {name!r}")
    return matches[0]


def _call_name(call: ast.Call) -> str:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return ""


def _assigned_constructor(function: ast.FunctionDef, target_name: str) -> tuple[str, int]:
    matches: list[tuple[str, int]] = []
    for node in ast.walk(function):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        if any(
            isinstance(target, ast.Name) and target.id == target_name for target in node.targets
        ):
            matches.append((_call_name(node.value), node.lineno))
    if len(matches) != 1 or not matches[0][0]:
        raise ValueError(f"cannot uniquely resolve constructor assigned to {target_name!r}")
    return matches[0]


def _call_lines(function: ast.FunctionDef, name: str) -> tuple[int, ...]:
    return tuple(
        sorted(
            node.lineno
            for node in ast.walk(function)
            if isinstance(node, ast.Call) and _call_name(node) == name
        )
    )


def _closed_loop_rows(artifact: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    rows: list[Mapping[str, Any]] = []
    closed = artifact.get("closed_loop_runs")
    if not isinstance(closed, Mapping):
        raise ValueError("Route-C artifact has no closed-loop run matrix")
    for arm_rows in closed.values():
        if not isinstance(arm_rows, Sequence) or isinstance(arm_rows, (str, bytes, bytearray)):
            raise ValueError("Route-C closed-loop arm rows are malformed")
        if not all(isinstance(row, Mapping) for row in arm_rows):
            raise ValueError("Route-C closed-loop run is malformed")
        rows.extend(arm_rows)
    ablation = artifact.get("seven_operator_neutralization")
    if not isinstance(ablation, Mapping) or not isinstance(ablation.get("runs"), Mapping):
        raise ValueError("Route-C artifact has no seven-operator neutralization matrix")
    for arm_rows in ablation["runs"].values():
        if not isinstance(arm_rows, Sequence) or isinstance(arm_rows, (str, bytes, bytearray)):
            raise ValueError("Route-C neutralization rows are malformed")
        if not all(isinstance(row, Mapping) for row in arm_rows):
            raise ValueError("Route-C neutralization run is malformed")
        rows.extend(arm_rows)
    if not rows:
        raise ValueError("Route-C artifact contains no auditable runs")
    return tuple(rows)


def run_runtime_identity_gate_audit(*, repository_root: Path) -> dict[str, Any]:
    """Audit the checked-in v0.2 artifact and fail closed on missing live bindings."""

    root = repository_root.resolve()
    config = load_runtime_identity_gate_config(root)
    artifact_path = _safe_repository_file(root, config.source_artifact)
    artifact = _strict_json(artifact_path)
    _reject_nonfinite(artifact)
    _verify_historical_artifact_integrity(artifact)
    historical_source_binding_currently_fresh = True
    source_verification_failure_code: str | None = None
    try:
        verify_full_scientific_loop_result(artifact, repository_root=root, fresh_replay=False)
    except ValueError as error:
        source_verification_failure_code = _current_source_verification_failure_code(error)
        if source_verification_failure_code is None:
            raise
        historical_source_binding_currently_fresh = False

    full_loop_path = _safe_repository_file(root, config.full_loop_implementation)
    production_path = _safe_repository_file(root, config.production_system_implementation)
    tree = ast.parse(full_loop_path.read_text(encoding="utf-8"), filename=str(full_loop_path))
    route_function = _function_node(tree, config.route_run_function)
    top_level_function = _function_node(tree, config.top_level_run_function)
    constructor_name, constructor_line = _assigned_constructor(route_function, "runtime")
    route_call_lines = _call_lines(top_level_function, config.route_run_function)
    sidecar_call_lines = _call_lines(top_level_function, config.sidecar_builder_function)
    if not route_call_lines or len(sidecar_call_lines) != 1:
        raise ValueError("cannot resolve Route-C run/sidecar construction order")

    production_tree = ast.parse(
        production_path.read_text(encoding="utf-8"), filename=str(production_path)
    )
    sidecar_builder = _function_node(production_tree, config.sidecar_builder_function)
    sidecar_constructor_lines = _call_lines(sidecar_builder, "StructureTwoProductionSystem")
    if len(sidecar_constructor_lines) != 1:
        raise ValueError(
            "production sidecar builder no longer has one explicit runtime construction"
        )

    observed_runtime = (
        f"cpswm.system.evaluation_operations.structure_two_full_scientific_loop.{constructor_name}"
    )
    if observed_runtime != config.expected_observed_route_runtime:
        raise ValueError("observed Route-C runtime constructor drifted")
    assembly = artifact.get("production_system_assembly")
    if not isinstance(assembly, Mapping):
        raise ValueError("Route-C artifact production sidecar is missing")
    sidecar_runtime = assembly.get("assembly_class")
    if sidecar_runtime != config.expected_sidecar_runtime:
        raise ValueError("production sidecar runtime identity drifted")

    rows = _closed_loop_rows(artifact)
    receipts = [
        receipt
        for row in rows
        for receipt in row.get("operator_flow_receipts", ())
        if isinstance(receipt, Mapping)
    ]
    if not receipts:
        raise ValueError("Route-C artifact contains no operator-flow receipts")
    required_fields = set(config.required_trace_binding_fields)
    runtime_binding_present = all("runtime_execution_binding" in row for row in rows)
    operator_binding_present = all(
        {"runtime_execution_id", "operator_instance_id"} <= set(receipt) for receipt in receipts
    )
    callable_binding_present = all(
        {"callable_symbol", "invocation_id"} <= set(receipt) for receipt in receipts
    )
    consumption_binding_present = all("consumed_output_ids" in receipt for receipt in receipts)
    complete_required_fields_present = all(required_fields <= set(receipt) for receipt in receipts)
    post_run_sidecar = sidecar_call_lines[0] > max(route_call_lines)
    sidecar_constructs_distinct_runtime = bool(sidecar_constructor_lines)
    sidecar_is_trajectory_binding = bool(
        runtime_binding_present
        and observed_runtime == sidecar_runtime
        and not sidecar_constructs_distinct_runtime
    )
    gate_passed = bool(
        runtime_binding_present
        and operator_binding_present
        and callable_binding_present
        and consumption_binding_present
        and complete_required_fields_present
        and sidecar_is_trajectory_binding
    )
    if gate_passed:
        raise ValueError("historical Route-C v0.2 unexpectedly satisfied the new identity gate")

    blocking_reasons = [
        "route_trace_has_no_runtime_execution_binding",
        "operator_receipts_have_no_live_operator_instance_identity",
        "operator_receipts_have_no_bound_callable_invocation_identity",
        "operator_outputs_have_no_downstream_consumption_dependencies",
        "production_manifest_was_built_from_a_distinct_post_run_runtime",
    ]
    if not historical_source_binding_currently_fresh:
        blocking_reasons.append("historical_source_binding_not_currently_fresh")

    config_path = _safe_repository_file(root, DEFAULT_CONFIG)
    gate_path = Path(__file__).resolve()
    runner_path = _safe_repository_file(root, DEFAULT_RUNNER)
    stateful_path = _safe_repository_file(root, config.stateful_runtime_implementation)
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "protocol_id": PROTOCOL_ID,
        "evidence_status": (
            RuntimeIdentityEvidenceStatus.MISSING_LIVE_RUNTIME_OPERATOR_CALL_CONSUMPTION_BINDING.value
        ),
        "architecture_selection_status": config.architecture_selection_status.value,
        "selected_global_runtime": SELECTED_GLOBAL_RUNTIME,
        "global_architecture_selected": True,
        "historical_artifact_integrity": {
            "content_sha256_verified": True,
            "embedded_production_manifest_content_sha256_verified": True,
        },
        "historical_source_binding_currently_fresh": (historical_source_binding_currently_fresh),
        "historical_source_binding_check": {
            "scope": "CURRENT_CHECKOUT_SOURCE_AND_PRODUCTION_MANIFEST",
            "status": (
                "CURRENTLY_FRESH"
                if historical_source_binding_currently_fresh
                else "HISTORICAL_SNAPSHOT_STALE_AGAINST_CURRENT_CHECKOUT"
            ),
            "failure_code": source_verification_failure_code,
        },
        "source_binding": {
            "configuration": {
                "path": str(DEFAULT_CONFIG),
                "sha256": _file_sha256(config_path),
            },
            "gate_implementation": {
                "path": str(gate_path.relative_to(root)),
                "sha256": _file_sha256(gate_path),
            },
            "gate_runner": {
                "path": str(DEFAULT_RUNNER),
                "sha256": _file_sha256(runner_path),
            },
            "source_artifact": {
                "path": str(config.source_artifact),
                "sha256": _file_sha256(artifact_path),
                "content_sha256": artifact["content_sha256"],
            },
            "full_loop_implementation": {
                "path": str(config.full_loop_implementation),
                "sha256": _file_sha256(full_loop_path),
            },
            "stateful_runtime_implementation": {
                "path": str(config.stateful_runtime_implementation),
                "sha256": _file_sha256(stateful_path),
            },
            "production_system_implementation": {
                "path": str(config.production_system_implementation),
                "sha256": _file_sha256(production_path),
            },
        },
        "observed_route_runtime": {
            "symbol": observed_runtime,
            "constructor_line": constructor_line,
            "produces_closed_loop_rows": True,
            "run_count": len(rows),
        },
        "sidecar_production_manifest": {
            "assembly_class": sidecar_runtime,
            "manifest_content_sha256": assembly.get("content_sha256"),
            "built_after_all_registered_route_calls": post_run_sidecar,
            "builder_constructs_a_distinct_runtime": sidecar_constructs_distinct_runtime,
            "trajectory_runtime_bound": sidecar_is_trajectory_binding,
            "role": "POST_RUN_STATIC_SIDECAR_NOT_TRAJECTORY_RUNTIME_EVIDENCE",
        },
        "trace_binding_audit": {
            "audited_run_count": len(rows),
            "audited_operator_receipt_count": len(receipts),
            "required_receipt_fields": list(config.required_trace_binding_fields),
            "per_run_runtime_execution_binding_present": runtime_binding_present,
            "operator_instance_binding_present": operator_binding_present,
            "callable_invocation_binding_present": callable_binding_present,
            "call_consumption_binding_present": consumption_binding_present,
            "all_required_receipt_fields_present": complete_required_fields_present,
        },
        "runtime_identity_gate_passed": gate_passed,
        "production_runtime_equivalence_established": False,
        "independent_custody_established": False,
        "blocking_reasons": blocking_reasons,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    report["content_sha256"] = content_sha256(report)
    return report


def verify_runtime_identity_gate_report(
    report: Mapping[str, Any], *, repository_root: Path
) -> None:
    """Verify a diagnostic report by regenerating it from the trusted checkout."""

    _reject_nonfinite(report)
    stored = report.get("content_sha256")
    unsigned = dict(report)
    unsigned.pop("content_sha256", None)
    if not _is_sha256(stored) or stored != content_sha256(unsigned):
        raise ValueError("runtime-identity report content hash mismatch")
    expected = run_runtime_identity_gate_audit(repository_root=repository_root)
    if dict(report) != expected:
        raise ValueError("runtime-identity report differs from fresh source-bound audit")


_ENROLLMENT_KEYS: Final = {
    "protocol_id",
    "runtime_symbol",
    "runtime_source_sha256",
    "operator_bindings",
    "content_sha256",
}
_OPERATOR_BINDING_KEYS: Final = {
    "operator",
    "binding_slot",
    "implementation_symbol",
    "implementation_source_sha256",
    "callable_symbol",
}
_RUNTIME_BINDING_KEYS: Final = {
    "runtime_execution_id",
    "runtime_symbol",
    "runtime_source_sha256",
    "enrollment_sha256",
    "operator_instances",
    "content_sha256",
}
_OPERATOR_INSTANCE_KEYS: Final = {
    "operator",
    "binding_slot",
    "operator_instance_id",
    "implementation_symbol",
    "implementation_source_sha256",
    "callable_symbol",
}
_EVIDENCE_KEYS: Final = {
    "protocol_id",
    "run_id",
    "runtime_binding",
    "events",
    "event_head_sha256",
    "content_sha256",
}
_EVENT_KEYS: Final = {
    "sequence",
    "step_index",
    "event_kind",
    "phase",
    "runtime_execution_id",
    "operator",
    "operator_instance_id",
    "callable_symbol",
    "invocation_id",
    "consumer_kind",
    "consumed_output_ids",
    "raw_input_sha256",
    "input_payload_sha256",
    "output_payload_sha256",
    "output_id",
    "previous_receipt_sha256",
    "receipt_sha256",
}


def _operator_instance_id(runtime_execution_id: str, binding: Mapping[str, Any]) -> str:
    return content_sha256(
        {
            "runtime_execution_id": runtime_execution_id,
            "operator": binding["operator"],
            "binding_slot": binding["binding_slot"],
            "implementation_symbol": binding["implementation_symbol"],
            "callable_symbol": binding["callable_symbol"],
        }
    )


def _invocation_id(
    *,
    runtime_execution_id: str,
    sequence: int,
    step_index: int,
    event_kind: str,
    phase: str,
    operator: str | None,
    callable_symbol: str | None,
    consumer_kind: str | None,
) -> str:
    """Derive a structural call identifier; this is not an authority token."""

    return content_sha256(
        {
            "runtime_execution_id": runtime_execution_id,
            "sequence": sequence,
            "step_index": step_index,
            "event_kind": event_kind,
            "phase": phase,
            "operator": operator,
            "callable_symbol": callable_symbol,
            "consumer_kind": consumer_kind,
        }
    )


def build_structural_non_vacuity_fixture(
    *,
    runtime_symbol: str = "fixture.runtime.StructuralCandidateRuntime",
) -> tuple[dict[str, Any], dict[str, Any], str]:
    """Return a deterministic, non-empty schema/DAG candidate.

    The fixture performs no live calls and carries no independently controlled
    execution witness.  Its returned hash is only an integrity reference for
    tests; neither the fixture nor a matching caller-supplied hash is a positive
    runtime-identity proof.
    """

    runtime_source_sha256 = content_sha256({"fixture_runtime_source": runtime_symbol})
    operator_bindings = [
        {
            "operator": operator,
            "binding_slot": f"operators.{operator}",
            "implementation_symbol": f"{runtime_symbol}.{operator}_operator",
            "implementation_source_sha256": content_sha256(
                {"fixture_operator_source": runtime_symbol, "operator": operator}
            ),
            "callable_symbol": f"{runtime_symbol}.{operator}_operator.invoke",
        }
        for operator in CANONICAL_OPERATORS
    ]
    enrollment: dict[str, Any] = {
        "protocol_id": PROTOCOL_ID,
        "runtime_symbol": runtime_symbol,
        "runtime_source_sha256": runtime_source_sha256,
        "operator_bindings": operator_bindings,
    }
    enrollment["content_sha256"] = content_sha256(enrollment)
    run_id = "pure-fixture/run-001"
    runtime_execution_id = content_sha256(
        {
            "protocol_id": PROTOCOL_ID,
            "run_id": run_id,
            "enrollment_sha256": enrollment["content_sha256"],
        }
    )
    operator_instances = [
        {
            **binding,
            "operator_instance_id": _operator_instance_id(runtime_execution_id, binding),
        }
        for binding in operator_bindings
    ]
    runtime_binding: dict[str, Any] = {
        "runtime_execution_id": runtime_execution_id,
        "runtime_symbol": runtime_symbol,
        "runtime_source_sha256": runtime_source_sha256,
        "enrollment_sha256": enrollment["content_sha256"],
        "operator_instances": operator_instances,
    }
    runtime_binding["content_sha256"] = content_sha256(runtime_binding)

    binding_by_operator = {row["operator"]: row for row in operator_instances}
    events: list[dict[str, Any]] = []
    previous_receipt = GENESIS
    outputs: dict[str, str] = {}

    def append_event(
        *,
        event_kind: TraceEventKind,
        phase: str,
        operator: str | None,
        consumer_kind: str | None,
        consumed: tuple[str, ...],
    ) -> str:
        nonlocal previous_receipt
        sequence = len(events)
        instance = None if operator is None else binding_by_operator[operator]
        callable_symbol = None if instance is None else str(instance["callable_symbol"])
        invocation_id = _invocation_id(
            runtime_execution_id=runtime_execution_id,
            sequence=sequence,
            step_index=1,
            event_kind=event_kind.value,
            phase=phase,
            operator=operator,
            callable_symbol=callable_symbol,
            consumer_kind=consumer_kind,
        )
        raw_input_hash = content_sha256({"fixture_raw_input": phase})
        input_hash = content_sha256(
            {
                "raw_input_sha256": raw_input_hash,
                "consumed_outputs": [(output_id, outputs[output_id]) for output_id in consumed],
            }
        )
        output_hash = content_sha256(
            {"fixture_output": phase, "sequence": sequence, "input": input_hash}
        )
        output_id = content_sha256(
            {
                "runtime_execution_id": runtime_execution_id,
                "sequence": sequence,
                "output_payload_sha256": output_hash,
            }
        )
        unsigned = {
            "sequence": sequence,
            "step_index": 1,
            "event_kind": event_kind.value,
            "phase": phase,
            "runtime_execution_id": runtime_execution_id,
            "operator": operator,
            "operator_instance_id": (
                None if instance is None else instance["operator_instance_id"]
            ),
            "callable_symbol": callable_symbol,
            "invocation_id": invocation_id,
            "consumer_kind": consumer_kind,
            "consumed_output_ids": list(consumed),
            "raw_input_sha256": raw_input_hash,
            "input_payload_sha256": input_hash,
            "output_payload_sha256": output_hash,
            "output_id": output_id,
            "previous_receipt_sha256": previous_receipt,
        }
        receipt = {**unsigned, "receipt_sha256": content_sha256(unsigned)}
        events.append(receipt)
        outputs[output_id] = output_hash
        previous_receipt = str(receipt["receipt_sha256"])
        return output_id

    ciav = append_event(
        event_kind=TraceEventKind.OPERATOR_CALL,
        phase="verification",
        operator="ciav",
        consumer_kind=None,
        consumed=(),
    )
    opceu = append_event(
        event_kind=TraceEventKind.OPERATOR_CALL,
        phase="observation_correction",
        operator="opceu",
        consumer_kind=None,
        consumed=(ciav,),
    )
    pchmp = append_event(
        event_kind=TraceEventKind.OPERATOR_CALL,
        phase="event_message_passing",
        operator="pchmp",
        consumer_kind=None,
        consumed=(opceu,),
    )
    cf_bocpd = append_event(
        event_kind=TraceEventKind.OPERATOR_CALL,
        phase="cause_run_length_revision",
        operator="cf_bocpd",
        consumer_kind=None,
        consumed=(pchmp,),
    )
    ccrr = append_event(
        event_kind=TraceEventKind.OPERATOR_CALL,
        phase="regime_resolution",
        operator="ccrr",
        consumer_kind=None,
        consumed=(cf_bocpd,),
    )
    rgrc = append_event(
        event_kind=TraceEventKind.OPERATOR_CALL,
        phase="reversible_consolidation",
        operator="rgrc",
        consumer_kind=None,
        consumed=(ccrr,),
    )
    action = append_event(
        event_kind=TraceEventKind.CONSUMER,
        phase="action_readout",
        operator=None,
        consumer_kind=ConsequentialConsumer.ACTION_READOUT.value,
        consumed=(rgrc,),
    )
    transition = append_event(
        event_kind=TraceEventKind.CONSUMER,
        phase="environment_transition",
        operator=None,
        consumer_kind=ConsequentialConsumer.ENVIRONMENT_TRANSITION.value,
        consumed=(action,),
    )
    orrer = append_event(
        event_kind=TraceEventKind.OPERATOR_CALL,
        phase="feedback_revision",
        operator="orrer_cheh",
        consumer_kind=None,
        consumed=(transition,),
    )
    append_event(
        event_kind=TraceEventKind.CONSUMER,
        phase="next_step_state",
        operator=None,
        consumer_kind=ConsequentialConsumer.NEXT_STEP_STATE.value,
        consumed=(orrer,),
    )
    evidence: dict[str, Any] = {
        "protocol_id": PROTOCOL_ID,
        "run_id": run_id,
        "runtime_binding": runtime_binding,
        "events": events,
        "event_head_sha256": previous_receipt,
    }
    evidence["content_sha256"] = content_sha256(evidence)
    return evidence, enrollment, str(evidence["content_sha256"])


def verify_runtime_identity_evidence(
    evidence: Mapping[str, Any],
    enrollment_reference: Mapping[str, Any],
    *,
    evidence_reference_sha256: str,
) -> RuntimeIdentityEvidenceAssessment:
    """Validate only a caller-controlled structural evidence candidate.

    ``evidence_reference_sha256`` can detect a change relative to a reference
    retained elsewhere, but this pure function has no independent execution
    authority and cannot tell whether any represented call actually ran.  A
    successful return is therefore deliberately fail-closed for live runtime
    identity, even when the caller supplies a matching reference hash.
    """

    _reject_nonfinite(evidence)
    _reject_nonfinite(enrollment_reference)
    if not _is_sha256(evidence_reference_sha256):
        raise ValueError("runtime identity evidence reference hash is malformed")
    _require_exact_keys(enrollment_reference, _ENROLLMENT_KEYS, "runtime enrollment")
    enrollment_unsigned = dict(enrollment_reference)
    enrollment_hash = enrollment_unsigned.pop("content_sha256", None)
    if not _is_sha256(enrollment_hash) or enrollment_hash != content_sha256(enrollment_unsigned):
        raise ValueError("runtime enrollment reference content hash mismatch")
    if enrollment_reference["protocol_id"] != PROTOCOL_ID:
        raise ValueError("runtime enrollment reference protocol mismatch")
    enrollment_runtime_symbol = enrollment_reference["runtime_symbol"]
    if not isinstance(enrollment_runtime_symbol, str) or not enrollment_runtime_symbol.strip():
        raise ValueError("runtime enrollment symbol is malformed")
    if not _is_sha256(enrollment_reference["runtime_source_sha256"]):
        raise ValueError("runtime source reference hash is malformed")
    enrollment_bindings = enrollment_reference["operator_bindings"]
    if not isinstance(enrollment_bindings, list) or len(enrollment_bindings) != 7:
        raise ValueError("enrollment reference does not contain exactly seven operators")
    for binding in enrollment_bindings:
        if not isinstance(binding, Mapping):
            raise ValueError("operator binding reference is malformed")
        _require_exact_keys(binding, _OPERATOR_BINDING_KEYS, "operator binding reference")
        if not all(
            isinstance(binding[field], str) and binding[field]
            for field in (
                "operator",
                "binding_slot",
                "implementation_symbol",
                "callable_symbol",
            )
        ) or not _is_sha256(binding["implementation_source_sha256"]):
            raise ValueError("operator binding reference field is malformed")
    enrolled_operators = [str(binding["operator"]) for binding in enrollment_bindings]
    if tuple(enrolled_operators) != CANONICAL_OPERATORS:
        raise ValueError("enrollment reference does not bind the canonical seven operators")

    _require_exact_keys(evidence, _EVIDENCE_KEYS, "runtime identity evidence")
    evidence_unsigned = dict(evidence)
    evidence_hash = evidence_unsigned.pop("content_sha256", None)
    if not _is_sha256(evidence_hash) or evidence_hash != content_sha256(evidence_unsigned):
        raise ValueError("runtime identity evidence content hash mismatch")
    if evidence_hash != evidence_reference_sha256:
        raise ValueError("runtime identity evidence differs from its retained reference")
    if evidence["protocol_id"] != PROTOCOL_ID:
        raise ValueError("runtime identity evidence protocol mismatch")
    if not isinstance(evidence["run_id"], str) or not evidence["run_id"]:
        raise ValueError("runtime identity evidence run id is malformed")

    runtime_binding = evidence["runtime_binding"]
    if not isinstance(runtime_binding, Mapping):
        raise ValueError("runtime execution binding is missing")
    _require_exact_keys(runtime_binding, _RUNTIME_BINDING_KEYS, "runtime execution binding")
    binding_unsigned = dict(runtime_binding)
    binding_hash = binding_unsigned.pop("content_sha256", None)
    if not _is_sha256(binding_hash) or binding_hash != content_sha256(binding_unsigned):
        raise ValueError("runtime execution binding content hash mismatch")
    runtime_symbol = runtime_binding["runtime_symbol"]
    if not isinstance(runtime_symbol, str) or not runtime_symbol.strip():
        raise ValueError("runtime execution symbol is malformed")
    if (
        runtime_binding["enrollment_sha256"] != enrollment_hash
        or runtime_symbol != enrollment_runtime_symbol
        or runtime_binding["runtime_source_sha256"] != enrollment_reference["runtime_source_sha256"]
    ):
        raise ValueError("runtime execution binding does not match enrollment reference")
    runtime_execution_id = runtime_binding["runtime_execution_id"]
    if not _is_sha256(runtime_execution_id):
        raise ValueError("runtime execution id is malformed")
    expected_runtime_execution_id = content_sha256(
        {
            "protocol_id": PROTOCOL_ID,
            "run_id": evidence["run_id"],
            "enrollment_sha256": enrollment_hash,
        }
    )
    if runtime_execution_id != expected_runtime_execution_id:
        raise ValueError("runtime execution id is not structurally derived")
    instances = runtime_binding["operator_instances"]
    if not isinstance(instances, list) or len(instances) != len(enrollment_bindings):
        raise ValueError("runtime execution does not bind exactly seven operator instances")
    instance_by_operator: dict[str, Mapping[str, Any]] = {}
    for expected, instance in zip(enrollment_bindings, instances, strict=True):
        if not isinstance(instance, Mapping):
            raise ValueError("runtime operator instance binding is malformed")
        _require_exact_keys(instance, _OPERATOR_INSTANCE_KEYS, "runtime operator instance")
        expected_instance = {
            **dict(expected),
            "operator_instance_id": _operator_instance_id(str(runtime_execution_id), expected),
        }
        if dict(instance) != expected_instance:
            raise ValueError("runtime operator instance differs from enrollment reference")
        instance_by_operator[str(instance["operator"])] = instance
    if set(instance_by_operator) != set(enrolled_operators):
        raise ValueError("runtime operator instance coverage is incomplete")

    events = evidence["events"]
    if not isinstance(events, list) or not events:
        raise ValueError("runtime identity event log is empty")
    previous = GENESIS
    outputs: dict[str, Mapping[str, Any]] = {}
    ancestors: dict[str, set[str]] = {}
    operator_coverage: set[str] = set()
    consumer_outputs: dict[str, list[str]] = {}
    for sequence, event in enumerate(events):
        if not isinstance(event, Mapping):
            raise ValueError("runtime identity event is malformed")
        _require_exact_keys(event, _EVENT_KEYS, "runtime identity event")
        if type(event["sequence"]) is not int or event["sequence"] != sequence:
            raise ValueError("runtime identity event sequence is malformed")
        if type(event["step_index"]) is not int or event["step_index"] < 0:
            raise ValueError("runtime identity event step index is malformed")
        if event["runtime_execution_id"] != runtime_execution_id:
            raise ValueError("runtime identity event was emitted by another runtime")
        if event["previous_receipt_sha256"] != previous:
            raise ValueError("runtime identity event hash chain is broken")
        unsigned = dict(event)
        receipt_hash = unsigned.pop("receipt_sha256", None)
        if not _is_sha256(receipt_hash) or receipt_hash != content_sha256(unsigned):
            raise ValueError("runtime identity event content hash mismatch")
        for field in (
            "invocation_id",
            "raw_input_sha256",
            "input_payload_sha256",
            "output_payload_sha256",
            "output_id",
        ):
            if not _is_sha256(event[field]):
                raise ValueError("runtime identity event payload binding is malformed")
        output_id = str(event["output_id"])
        if output_id in outputs:
            raise ValueError("runtime identity event reused an output id")
        consumed = event["consumed_output_ids"]
        if (
            not isinstance(consumed, list)
            or len(consumed) != len(set(consumed))
            or not all(isinstance(output, str) and output in outputs for output in consumed)
        ):
            raise ValueError("runtime identity event consumes a missing or duplicate output")
        expected_input_hash = content_sha256(
            {
                "raw_input_sha256": event["raw_input_sha256"],
                "consumed_outputs": [
                    (source, outputs[source]["output_payload_sha256"]) for source in consumed
                ],
            }
        )
        if event["input_payload_sha256"] != expected_input_hash:
            raise ValueError("runtime identity event input is not consumption-derived")
        expected_output_id = content_sha256(
            {
                "runtime_execution_id": runtime_execution_id,
                "sequence": sequence,
                "output_payload_sha256": event["output_payload_sha256"],
            }
        )
        if output_id != expected_output_id:
            raise ValueError("runtime identity event output id is not call-derived")
        inherited_operators: set[str] = set()
        for source in consumed:
            inherited_operators.update(ancestors[source])

        kind = event["event_kind"]
        phase = event["phase"]
        operator_value = event["operator"]
        callable_value = event["callable_symbol"]
        consumer_value = event["consumer_kind"]
        if not isinstance(kind, str) or not isinstance(phase, str) or not phase:
            raise ValueError("runtime identity event kind or phase is malformed")
        if operator_value is not None and not isinstance(operator_value, str):
            raise ValueError("runtime identity event operator is malformed")
        if callable_value is not None and not isinstance(callable_value, str):
            raise ValueError("runtime identity event callable is malformed")
        if consumer_value is not None and not isinstance(consumer_value, str):
            raise ValueError("runtime identity event consumer is malformed")
        expected_invocation_id = _invocation_id(
            runtime_execution_id=str(runtime_execution_id),
            sequence=sequence,
            step_index=event["step_index"],
            event_kind=kind,
            phase=phase,
            operator=operator_value,
            callable_symbol=callable_value,
            consumer_kind=consumer_value,
        )
        if event["invocation_id"] != expected_invocation_id:
            raise ValueError("runtime identity invocation id is not structurally derived")
        if kind == TraceEventKind.OPERATOR_CALL.value:
            if event["consumer_kind"] is not None:
                raise ValueError("operator call cannot claim a consequential consumer kind")
            operator = event["operator"]
            if not isinstance(operator, str) or operator not in instance_by_operator:
                raise ValueError("operator call names an unenrolled operator")
            instance = instance_by_operator[operator]
            if (
                event["operator_instance_id"] != instance["operator_instance_id"]
                or event["callable_symbol"] != instance["callable_symbol"]
            ):
                raise ValueError("operator call is not bound to its enrolled live instance")
            inherited_operators.add(operator)
            operator_coverage.add(operator)
        elif kind == TraceEventKind.CONSUMER.value:
            if event["operator"] is not None or event["operator_instance_id"] is not None:
                raise ValueError("consequential consumer cannot masquerade as an operator call")
            if event["callable_symbol"] is not None:
                raise ValueError("consequential consumer has an unexpected callable claim")
            consumer_kind = event["consumer_kind"]
            if consumer_kind not in {item.value for item in ConsequentialConsumer}:
                raise ValueError("runtime identity event has an unknown consequential consumer")
            if not consumed:
                raise ValueError("consequential consumer did not consume a runtime output")
            consumer_outputs.setdefault(str(consumer_kind), []).append(output_id)
        else:
            raise ValueError("runtime identity event kind is unknown")
        outputs[output_id] = event
        ancestors[output_id] = inherited_operators
        previous = str(receipt_hash)
    if evidence["event_head_sha256"] != previous:
        raise ValueError("runtime identity event head hash mismatch")
    if operator_coverage != set(enrolled_operators):
        raise ValueError("runtime identity evidence did not call all seven operators")

    for consumer in ConsequentialConsumer:
        if len(consumer_outputs.get(consumer.value, ())) != 1:
            raise ValueError(f"runtime identity evidence lacks one {consumer.value} consumer")
    action_output = consumer_outputs[ConsequentialConsumer.ACTION_READOUT.value][0]
    environment_output = consumer_outputs[ConsequentialConsumer.ENVIRONMENT_TRANSITION.value][0]
    next_state_output = consumer_outputs[ConsequentialConsumer.NEXT_STEP_STATE.value][0]
    environment_event = outputs[environment_output]
    next_state_event = outputs[next_state_output]
    pre_action_operators = {"ciav", "opceu", "pchmp", "cf_bocpd", "ccrr", "rgrc"}
    if not pre_action_operators <= ancestors[action_output]:
        raise ValueError("action readout is not downstream of all pre-action operators")
    if action_output not in environment_event["consumed_output_ids"]:
        raise ValueError("environment transition did not consume the runtime action output")
    orrer_outputs = [
        output
        for output, event in outputs.items()
        if event["event_kind"] == TraceEventKind.OPERATOR_CALL.value
        and event["operator"] == "orrer_cheh"
        and environment_output in event["consumed_output_ids"]
    ]
    if len(orrer_outputs) != 1:
        raise ValueError("ORRER/CHEH did not consume the environment feedback output")
    if orrer_outputs[0] not in next_state_event["consumed_output_ids"]:
        raise ValueError("next-step state did not consume the ORRER/CHEH output")
    if ancestors[next_state_output] != set(enrolled_operators):
        raise ValueError("not every operator output reaches the next consequential state")

    return RuntimeIdentityEvidenceAssessment(
        structural_candidate=True,
        enrollment_reference_matched=True,
        evidence_reference_matched=True,
        independent_execution_authority_verified=False,
        live_runtime_identity_established=False,
        runtime_identity_gate_passed=False,
        evidence_status=(
            RuntimeIdentityEvidenceStatus.STRUCTURAL_CANDIDATE_ONLY_NO_LIVE_EXECUTION_AUTHORITY
        ),
    )


def copy_and_rehash_report(report: Mapping[str, Any]) -> dict[str, Any]:
    """Test helper: make a self-consistently rehashed copy after caller mutation."""

    result = copy.deepcopy(dict(report))
    result.pop("content_sha256", None)
    result["content_sha256"] = content_sha256(result)
    return result


__all__ = [
    "CLAIM_BOUNDARY",
    "DEFAULT_CONFIG",
    "DEFAULT_RUNNER",
    "PROTOCOL_ID",
    "ArchitectureSelectionStatus",
    "RuntimeIdentityEvidenceAssessment",
    "RuntimeIdentityEvidenceStatus",
    "RuntimeIdentityGateConfig",
    "build_structural_non_vacuity_fixture",
    "copy_and_rehash_report",
    "load_runtime_identity_gate_config",
    "run_runtime_identity_gate_audit",
    "verify_runtime_identity_evidence",
    "verify_runtime_identity_gate_report",
]
