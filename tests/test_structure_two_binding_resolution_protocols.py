from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid5

import pytest
from pydantic import ValidationError

from cpswm.system.evaluation_operations.structure_two_binding_resolution_protocols import (
    ArmRole,
    BindingArmUnitResult,
    BindingResolutionExecutionTrace,
    MetricDirection,
    MetricObservation,
    NeuralProposerArchitectureProtocol,
    OpenBinding,
    ResolutionSplit,
    load_binding_resolution_protocol,
    recompute_binding_resolution,
)
from cpswm.system.evaluation_operations.structure_two_selected_method import (
    UnresolvedMethodBinding,
)
from cpswm.system.reproducibility import content_sha256

NAMESPACE = UUID("8c94746d-24be-4b78-a976-ad77f18d53e5")
BASE_TIME = datetime(2026, 9, 5, 10, 0, tzinfo=UTC)


def _uuid(label: str) -> UUID:
    return uuid5(NAMESPACE, label)


def _hash(label: str) -> str:
    return content_sha256({"label": label})


def _passing_trace(binding: OpenBinding) -> BindingResolutionExecutionTrace:
    protocol = load_binding_resolution_protocol(binding)
    validation_units = tuple(_uuid(f"{binding}:validation:{index}") for index in range(3))
    confirmatory_units = tuple(_uuid(f"{binding}:confirmatory:{index}") for index in range(5))
    rows: list[BindingArmUnitResult] = []
    for split, units in (
        (ResolutionSplit.VALIDATION, validation_units),
        (ResolutionSplit.CONFIRMATORY, confirmatory_units),
    ):
        for unit_index, unit in enumerate(units):
            for arm_index, arm in enumerate(protocol.arms):
                if split is ResolutionSplit.VALIDATION:
                    value = float(arm_index)
                    if arm.role is ArmRole.DIAGNOSTIC_CONTROL:
                        value = -100.0
                    metrics = (
                        MetricObservation(
                            metric_id=protocol.validation_metric_id,
                            value=value,
                        ),
                    )
                else:
                    metrics = tuple(
                        MetricObservation(
                            metric_id=gate.metric_id,
                            value=(
                                gate.threshold - 0.01
                                if gate.direction is MetricDirection.MINIMIZE
                                else gate.threshold + 0.01
                            ),
                        )
                        for gate in protocol.confirmatory_gates
                    )
                rows.append(
                    BindingArmUnitResult(
                        split=split,
                        independent_unit_id=unit,
                        arm_id=arm.arm_id,
                        information_view_sha256=_hash(f"information:{split}:{unit_index}"),
                        runtime_trace_sha256=_hash(
                            f"runtime:{binding}:{split}:{unit_index}:{arm.arm_id}"
                        ),
                        budget_units=100,
                        metrics=metrics,
                    )
                )
    return BindingResolutionExecutionTrace(
        trace_id=_uuid(f"trace:{binding}"),
        binding=binding,
        protocol_id=protocol.protocol_id,
        protocol_content_sha256=content_sha256(protocol),
        frozen_at_utc=BASE_TIME,
        execution_started_at_utc=BASE_TIME + timedelta(seconds=1),
        execution_completed_at_utc=BASE_TIME + timedelta(minutes=1),
        rows=tuple(rows),
    )


def test_all_five_unresolved_bindings_have_independent_frozen_protocols() -> None:
    protocols = tuple(load_binding_resolution_protocol(binding) for binding in OpenBinding)
    assert {item.binding.value for item in protocols} == {
        UnresolvedMethodBinding.NEURAL_PROPOSER_ARCHITECTURE.value,
        UnresolvedMethodBinding.TRAINING_SCHEDULE.value,
        UnresolvedMethodBinding.CONSOLIDATION_THRESHOLDS.value,
        UnresolvedMethodBinding.CIAV_ACTION_BUDGET.value,
        UnresolvedMethodBinding.EXACT_ENUMERATION_FALSIFIER.value,
    }
    assert len({item.protocol_id for item in protocols}) == 5
    assert len({item.estimand for item in protocols}) == 5
    assert len({item.claim_boundary for item in protocols}) == 5
    for protocol in protocols:
        assert len(protocol.arms) >= 2
        assert protocol.confirmatory_gates
        assert "seven-operator ablation" in protocol.claim_boundary


@pytest.mark.parametrize("binding", tuple(OpenBinding))
def test_resolution_recomputes_validation_selection_and_confirmatory_gates(
    binding: OpenBinding,
) -> None:
    protocol = load_binding_resolution_protocol(binding)
    trace = _passing_trace(binding)
    result = recompute_binding_resolution(protocol, trace)
    assert result.selected_arm_id == next(
        arm.arm_id for arm in protocol.arms if arm.role is ArmRole.ELIGIBLE
    )
    assert result.all_confirmatory_gates_passed is True
    assert all(gate.passed for gate in result.confirmatory_gates)


def test_diagnostic_control_cannot_win_even_with_best_validation_score() -> None:
    protocol = load_binding_resolution_protocol(OpenBinding.NEURAL_PROPOSER_ARCHITECTURE)
    result = recompute_binding_resolution(
        protocol,
        _passing_trace(OpenBinding.NEURAL_PROPOSER_ARCHITECTURE),
    )
    control = next(arm.arm_id for arm in protocol.arms if arm.role is ArmRole.DIAGNOSTIC_CONTROL)
    assert result.selected_arm_id != control


def test_missing_arm_unit_and_unfair_information_or_budget_are_rejected() -> None:
    binding = OpenBinding.TRAINING_SCHEDULE
    protocol = load_binding_resolution_protocol(binding)
    trace = _passing_trace(binding)

    with pytest.raises(ValueError, match="exact arm x independent-unit coverage"):
        recompute_binding_resolution(protocol, trace.model_copy(update={"rows": trace.rows[:-1]}))

    row = trace.rows[1]
    unfair_information = row.model_copy(update={"information_view_sha256": _hash("unfair")})
    rows = (trace.rows[0], unfair_information, *trace.rows[2:])
    with pytest.raises(ValueError, match="identical information view"):
        recompute_binding_resolution(protocol, trace.model_copy(update={"rows": rows}))

    unfair_budget = row.model_copy(update={"budget_units": row.budget_units + 1})
    rows = (trace.rows[0], unfair_budget, *trace.rows[2:])
    with pytest.raises(ValueError, match="identical execution budget"):
        recompute_binding_resolution(protocol, trace.model_copy(update={"rows": rows}))


def test_cross_version_and_cross_binding_protocol_substitution_are_rejected(tmp_path: Path) -> None:
    protocol = load_binding_resolution_protocol(OpenBinding.NEURAL_PROPOSER_ARCHITECTURE)
    with pytest.raises(ValidationError):
        NeuralProposerArchitectureProtocol.model_validate(
            {**protocol.model_dump(mode="python"), "protocol_id": f"{protocol.protocol_id}.forged"}
        )
    foreign_trace = _passing_trace(OpenBinding.TRAINING_SCHEDULE)
    with pytest.raises(ValueError, match="substitutes a different binding protocol"):
        recompute_binding_resolution(protocol, foreign_trace)

    source = Path(
        "configs/project_two_experiments/"
        "structure_two_neural_proposer_architecture_resolution_v0_1.json"
    )
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text(source.read_text().replace("{", '{"binding":"training_schedule",', 1))
    with pytest.raises(ValueError, match="duplicate JSON key"):
        load_binding_resolution_protocol(
            OpenBinding.NEURAL_PROPOSER_ARCHITECTURE,
            path=duplicate,
        )
