"""Fail-closed input coverage gate for v0.6 external-method adaptations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from cpswm.system.evaluation_operations.structure_two_external_adapter_fidelity_v0_2 import (
    ExternalMethodSpecification,
    default_external_method_specifications_v0_2,
    external_artifact_sha256,
)
from cpswm.system.evaluation_operations.structure_two_external_inputs_v0_6 import (
    CompleteExternalAdaptationInputsV06,
)
from cpswm.system.reproducibility import content_sha256

PROTOCOL_ID = "structure-two-external-adapter-input-coverage@0.6"


def run_adapter_input_coverage_gate(
    specifications: Sequence[ExternalMethodSpecification],
    available_inputs_by_arm: Mapping[str, Sequence[str]],
    *,
    enforce_canonical_catalog: bool = True,
    input_bundle_paths_by_arm: Mapping[str, Path] | None = None,
    input_bundle_sha256_by_arm: Mapping[str, str] | None = None,
    require_content_bound_inputs: bool = True,
) -> dict[str, Any]:
    """Require exact, explicit coverage of every method's adaptation inputs."""

    if not specifications:
        raise ValueError("adapter input coverage requires external method specifications")
    if enforce_canonical_catalog and tuple(specifications) != (
        default_external_method_specifications_v0_2()
    ):
        raise ValueError("adapter input coverage requires the canonical six-arm catalog")
    expected = {item.arm for item in specifications}
    if len(expected) != len(specifications):
        raise ValueError("external method specifications contain duplicate arms")
    if set(available_inputs_by_arm) - expected:
        raise ValueError("input coverage contains an undeclared external arm")
    input_bundle_paths_by_arm = input_bundle_paths_by_arm or {}
    input_bundle_sha256_by_arm = input_bundle_sha256_by_arm or {}
    if set(input_bundle_paths_by_arm) - expected or set(input_bundle_sha256_by_arm) - expected:
        raise ValueError("input bundle evidence contains an undeclared external arm")
    typed_bundle_content_bound = not require_content_bound_inputs
    if require_content_bound_inputs and (
        set(input_bundle_paths_by_arm) == expected and set(input_bundle_sha256_by_arm) == expected
    ):
        unique_paths = {path.resolve() for path in input_bundle_paths_by_arm.values()}
        unique_hashes = set(input_bundle_sha256_by_arm.values())
        if len(unique_paths) == 1 and len(unique_hashes) == 1:
            path = next(iter(unique_paths))
            expected_sha256 = next(iter(unique_hashes))
            try:
                CompleteExternalAdaptationInputsV06.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
                typed_bundle_content_bound = external_artifact_sha256(path) == expected_sha256
            except (OSError, ValueError):
                typed_bundle_content_bound = False
    rows: list[dict[str, Any]] = []
    for specification in specifications:
        required = set(specification.required_adaptation_inputs)
        available_values = tuple(available_inputs_by_arm.get(specification.arm, ()))
        available = set(available_values)
        if len(available) != len(available_values):
            raise ValueError(f"arm {specification.arm} declares duplicate available inputs")
        missing = tuple(sorted(required - available))
        unexpected = tuple(sorted(available - required))
        input_bundle_content_bound = typed_bundle_content_bound
        rows.append(
            {
                "arm": specification.arm,
                "method": specification.method,
                "required_adaptation_inputs": specification.required_adaptation_inputs,
                "available_adaptation_inputs": tuple(sorted(available)),
                "missing_adaptation_inputs": missing,
                "unexpected_adaptation_inputs": unexpected,
                "input_bundle_content_bound": input_bundle_content_bound,
                "typed_six_arm_bundle_validated": typed_bundle_content_bound,
                "passed": not missing and not unexpected and input_bundle_content_bound,
            }
        )
    passed = all(bool(item["passed"]) for item in rows)
    report: dict[str, Any] = {
        "protocol": PROTOCOL_ID,
        "method_input_results": rows,
        "adapter_input_coverage_gate_passed": passed,
        "gate_b_trace_production_allowed": passed,
        "claim_boundary": (
            "Input coverage only establishes that an adapter can receive its declared "
            "semantics. It does not establish correct implementation, native fidelity, "
            "adaptation parity, or efficacy."
        ),
    }
    report["content_sha256"] = content_sha256(report)
    return report


__all__ = ["PROTOCOL_ID", "run_adapter_input_coverage_gate"]
