"""Adversarial checks for the independent external-adapter fidelity gate."""

from __future__ import annotations

from cpswm.system.evaluation_operations.structure_two_external_adapter_fidelity import (
    AdapterFidelityVerdict,
    build_external_adapter_fidelity_audit,
)

EXTERNAL_ARMS = (
    "corrected_amg",
    "o_star_matched",
    "active_dreaming_matched",
    "auto_dreamer_matched",
    "trustmem_matched",
    "brainctl_matched",
)


def test_current_external_adapters_fail_closed_for_method_comparison() -> None:
    audit = build_external_adapter_fidelity_audit(EXTERNAL_ARMS)

    assert audit["external_fidelity_gate_passed"] is False
    assert audit["external_method_efficacy_comparison_allowed"] is False
    assert audit["required_external_arm_count"] == len(EXTERNAL_ARMS)


def test_three_independently_inspected_adapters_are_explicit_nonfaithful_proxies() -> None:
    audit = build_external_adapter_fidelity_audit(EXTERNAL_ARMS)
    by_arm = {row["arm"]: row for row in audit["audited_external_arms"]}

    for arm in ("o_star_matched", "active_dreaming_matched", "brainctl_matched"):
        assert by_arm[arm]["verdict"] == AdapterFidelityVerdict.NON_FAITHFUL_PROXY
        assert by_arm[arm]["missing_or_changed_components"]


def test_unaudited_external_arms_cannot_inherit_a_pass() -> None:
    audit = build_external_adapter_fidelity_audit(EXTERNAL_ARMS)
    by_arm = {row["arm"]: row for row in audit["audited_external_arms"]}

    for arm in ("corrected_amg", "auto_dreamer_matched", "trustmem_matched"):
        assert by_arm[arm]["verdict"] == AdapterFidelityVerdict.NOT_INDEPENDENTLY_AUDITED
