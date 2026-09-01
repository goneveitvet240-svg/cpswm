from __future__ import annotations

import pytest

from cpswm.system.evaluation_operations.structure_two_adapter_input_coverage_v0_6 import (
    run_adapter_input_coverage_gate,
)
from cpswm.system.evaluation_operations.structure_two_external_adapter_fidelity_v0_2 import (
    ExternalMethodSpecification,
    default_external_method_specifications_v0_2,
)


def _spec(arm: str, *inputs: str) -> ExternalMethodSpecification:
    return ExternalMethodSpecification(
        arm=arm,
        method=arm,
        native_domain="native",
        primary_source_url="https://example.org/paper",
        required_native_components=("core",),
        required_adaptation_inputs=inputs,
        official_code_required=False,
    )


def test_missing_method_input_blocks_trace_production() -> None:
    report = run_adapter_input_coverage_gate(
        (_spec("method", "geometry", "cost"),),
        {"method": ("geometry",)},
        enforce_canonical_catalog=False,
        require_content_bound_inputs=False,
    )
    assert report["adapter_input_coverage_gate_passed"] is False
    assert report["gate_b_trace_production_allowed"] is False
    assert report["method_input_results"][0]["missing_adaptation_inputs"] == ("cost",)


def test_complete_declared_inputs_pass_without_upgrading_fidelity_claims() -> None:
    report = run_adapter_input_coverage_gate(
        (_spec("method", "geometry", "cost"),),
        {"method": ("cost", "geometry")},
        enforce_canonical_catalog=False,
        require_content_bound_inputs=False,
    )
    assert report["adapter_input_coverage_gate_passed"] is True
    assert "does not establish correct implementation" in report["claim_boundary"]


def test_undeclared_arm_and_duplicate_input_fail_closed() -> None:
    with pytest.raises(ValueError, match="undeclared external arm"):
        run_adapter_input_coverage_gate(
            (_spec("method", "geometry"),),
            {"other": ()},
            enforce_canonical_catalog=False,
            require_content_bound_inputs=False,
        )
    with pytest.raises(ValueError, match="duplicate available inputs"):
        run_adapter_input_coverage_gate(
            (_spec("method", "geometry"),),
            {"method": ("geometry", "geometry")},
            enforce_canonical_catalog=False,
            require_content_bound_inputs=False,
        )


def test_declared_input_names_without_real_bundles_do_not_pass_formal_coverage() -> None:
    specifications = default_external_method_specifications_v0_2()
    available = {item.arm: item.required_adaptation_inputs for item in specifications}
    report = run_adapter_input_coverage_gate(specifications, available)
    assert report["adapter_input_coverage_gate_passed"] is False
    assert all(row["input_bundle_content_bound"] is False for row in report["method_input_results"])
