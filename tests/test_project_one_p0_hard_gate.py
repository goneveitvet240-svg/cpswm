from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from cpswm.system.evaluation_operations.fair_ablation import ProjectOneAblationArmId
from cpswm.system.evaluation_operations.project_one_dataset import ProjectOneDatasetRecord
from cpswm.system.evaluation_operations.project_one_evaluation_path import (
    BYPASSED_MODULES,
    OFFLINE_METHOD_EVALUATION,
    FormalB1ClaimError,
    ProjectOneMethodEvidence,
    compare_offline_and_canonical_method_input,
    require_formal_b1_claim_allowed,
)
from cpswm.system.evaluation_operations.project_one_methods import ContextFrequencyMethod
from cpswm.system.evaluation_operations.project_one_protocol import ContextFrequencyConfig
from cpswm.system.evaluation_operations.project_one_runtime_parameters import (
    UnusedProjectOneParameterError,
    build_project_one_runtime_parameter_receipt,
)
from cpswm.system.evaluation_operations.project_one_shift_action_death_test import (
    UnusedShiftParameterError,
    build_shift_runtime_parameter_receipt,
    reject_unused_shift_parameter_change,
)


def _record() -> ProjectOneDatasetRecord:
    return ProjectOneDatasetRecord(
        stream_id="offline",
        event_id="e1",
        subject_id="alice",
        household_id="h1",
        object_id="cup",
        actor_id="alice",
        timestamp=datetime(2026, 8, 25, tzinfo=UTC),
        context_key="morning",
        context_value=0.25,
        observed_location="table",
        observation_quality=0.8,
    )


def test_offline_method_input_matches_an_equal_canonical_m16_view() -> None:
    record = _record()
    canonical = ProjectOneMethodEvidence.from_offline_record(record)
    receipt = compare_offline_and_canonical_method_input(record, canonical)
    assert receipt.equivalent is True
    assert receipt.offline_method_input_sha256 == receipt.canonical_method_input_sha256
    assert receipt.does_not_prove_modules_executed == BYPASSED_MODULES


def test_offline_equivalence_detects_a_changed_canonical_field() -> None:
    record = _record()
    canonical = replace(
        ProjectOneMethodEvidence.from_offline_record(record), observation_quality=0.2
    )
    assert compare_offline_and_canonical_method_input(record, canonical).equivalent is False


def test_offline_method_evaluation_cannot_masquerade_as_formal_b1() -> None:
    with pytest.raises(FormalB1ClaimError, match="bypasses M05-M16"):
        require_formal_b1_claim_allowed(OFFLINE_METHOD_EVALUATION)


def test_joint_shift_receipt_covers_every_runtime_parameter() -> None:
    params = {
        "warmup_days": 2,
        "hazard_probability": 0.05,
        "detection_threshold": 0.35,
        "beam_width": 24,
        "maximum_simultaneous_causes": 1,
        "simultaneous_hazard_scale": 0.25,
    }
    receipt = build_shift_runtime_parameter_receipt(
        ProjectOneAblationArmId.JOINT_CAUSE_FACTORIZED_BOCPD, params
    )
    assert {item.parameter for item in receipt.bindings} == set(params)
    assert all(item.target_component for item in receipt.bindings)


@pytest.mark.parametrize(
    ("parameter", "replacement"),
    (
        ("warmup_days", 3),
        ("hazard_probability", 0.1),
        ("detection_threshold", 0.5),
        ("beam_width", 12),
        ("maximum_simultaneous_causes", 2),
        ("simultaneous_hazard_scale", 0.5),
    ),
)
def test_every_joint_shift_parameter_mutation_changes_a_runtime_receipt(
    parameter: str, replacement: int | float
) -> None:
    before = {
        "warmup_days": 2,
        "hazard_probability": 0.05,
        "detection_threshold": 0.35,
        "beam_width": 24,
        "maximum_simultaneous_causes": 1,
        "simultaneous_hazard_scale": 0.25,
    }
    after = {**before, parameter: replacement}
    reject_unused_shift_parameter_change(
        ProjectOneAblationArmId.JOINT_CAUSE_FACTORIZED_BOCPD, before, after
    )
    left = build_shift_runtime_parameter_receipt(
        ProjectOneAblationArmId.JOINT_CAUSE_FACTORIZED_BOCPD, before
    )
    right = build_shift_runtime_parameter_receipt(
        ProjectOneAblationArmId.JOINT_CAUSE_FACTORIZED_BOCPD, after
    )
    assert left.receipt_sha256 != right.receipt_sha256


def test_an_unbound_shift_parameter_is_rejected() -> None:
    with pytest.raises(UnusedShiftParameterError, match="unbound"):
        build_shift_runtime_parameter_receipt(
            ProjectOneAblationArmId.ORDINARY_BOCPD,
            {
                "warmup_days": 2,
                "hazard_probability": 0.05,
                "detection_threshold": 0.35,
                "decorative_only": 9,
            },
        )


def test_project_one_tuning_knobs_have_runtime_component_receipts() -> None:
    method = ContextFrequencyMethod(
        ("table", "desk"), ContextFrequencyConfig(alpha=2.0, change_threshold=0.7)
    )
    receipt = build_project_one_runtime_parameter_receipt(
        method, {"alpha": 2.0, "change_threshold": 0.7}
    )
    assert {item.target_path for item in receipt.bindings} == {
        "alpha",
        "change_threshold",
    }


def test_project_one_unused_tuning_knob_is_rejected() -> None:
    method = ContextFrequencyMethod(("table", "desk"))
    with pytest.raises(UnusedProjectOneParameterError, match="expected one"):
        build_project_one_runtime_parameter_receipt(method, {"decorative_only": 1})
