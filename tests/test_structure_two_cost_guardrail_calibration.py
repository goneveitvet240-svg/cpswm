"""Regression and adversarial tests for the Structure Two cost/guardrail gate."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from cpswm.system.continual.hybrid_event_to_task_loop import (
    HybridEventToTaskCoordinatorLoop,
    HybridFullRerunEquivalenceReceipt,
    OwnerPlacementInput,
)
from cpswm.system.evaluation_operations.project_two_action_benchmark import (
    ProjectTwoActionBenchmarkV02,
)
from cpswm.system.evaluation_operations.project_two_experiment_config import (
    D0SyntheticReplayExperimentConfig,
)
from cpswm.system.evaluation_operations.structure_two_cost_guardrail_calibration import (
    PAPER_BINDINGS_STILL_REQUIRED,
    CostGuardrailCalibrationReport,
    PairedCostGuardrailEpisode,
    TrainFullRerunObservation,
    _break_even_envelope,
    build_cost_guardrail_calibration,
    verify_cost_guardrail_calibration_artifact,
)


def _paired_rows() -> tuple[PairedCostGuardrailEpisode, ...]:
    return (
        PairedCostGuardrailEpisode(
            episode_id=UUID(int=101),
            step_count=10,
            reference_minus_candidate_put_back_regret=0.0,
            reference_minus_candidate_search_regret=1.0,
            reference_minus_candidate_inspected_container_count=3.0,
            candidate_minus_reference_contamination_events=0.5,
            candidate_minus_reference_recovery_latency=0.0,
        ),
        PairedCostGuardrailEpisode(
            episode_id=UUID(int=102),
            step_count=10,
            reference_minus_candidate_put_back_regret=0.0,
            reference_minus_candidate_search_regret=0.0,
            reference_minus_candidate_inspected_container_count=0.0,
            candidate_minus_reference_contamination_events=0.0,
            candidate_minus_reference_recovery_latency=0.0,
        ),
    )


def _loop() -> HybridEventToTaskCoordinatorLoop:
    return HybridEventToTaskCoordinatorLoop(
        owner_key="owner",
        object_instance_id=UUID(int=2),
        authorization_scope_id=UUID(int=3),
        model_version="test-model",
        code_version="test-code",
    )


def _ingest(loop: HybridEventToTaskCoordinatorLoop, location: UUID) -> OwnerPlacementInput:
    placement = OwnerPlacementInput(
        event_hypothesis_id=uuid4(),
        revision_id=uuid4(),
        destination_location_id=location,
        owner_mass=0.8,
        source_record_id=uuid4(),
    )
    loop.ingest_owner_placement(placement)
    return placement


def _ingest_mass(
    loop: HybridEventToTaskCoordinatorLoop, location: UUID, mass: float
) -> OwnerPlacementInput:
    placement = OwnerPlacementInput(
        event_hypothesis_id=uuid4(),
        revision_id=uuid4(),
        destination_location_id=location,
        owner_mass=mass,
        source_record_id=uuid4(),
    )
    loop.ingest_owner_placement(placement)
    return placement


def test_break_even_envelope_is_casewise_and_cost_explicit() -> None:
    envelope = _break_even_envelope(_paired_rows())

    assert envelope.put_back_casewise_equal
    assert envelope.recovery_latency_casewise_equal
    assert envelope.search_strictly_better_episode_count == 1
    assert envelope.search_equal_episode_count == 1
    assert envelope.search_worse_episode_count == 0
    assert envelope.primary_advantage.estimate == pytest.approx(0.5)
    assert envelope.contamination_excess_events.estimate == pytest.approx(0.25)
    assert (
        envelope.maximum_contamination_cost_per_event_in_normalized_search_regret_units
        == pytest.approx(2.0)
    )
    assert envelope.maximum_contamination_cost_per_event_in_inspection_cost_units == pytest.approx(
        6.0
    )
    assert "no real-world cost" in envelope.interpretation


def test_nonpositive_inspection_advantage_does_not_emit_a_positive_break_even() -> None:
    rows = tuple(
        item.model_copy(
            update={
                "reference_minus_candidate_search_regret": -0.5,
                "reference_minus_candidate_inspected_container_count": -1.0,
            }
        )
        for item in _paired_rows()
    )
    envelope = _break_even_envelope(rows)

    assert envelope.maximum_contamination_cost_per_event_in_inspection_cost_units == 0.0
    assert envelope.inspection_cost_break_even_ratio is None


def test_hybrid_receipt_covers_each_location_and_rejects_derived_output_forgery() -> None:
    loop = _loop()
    first = _ingest(loop, UUID(int=11))
    _ingest(loop, UUID(int=12))
    loop.retract_revision(first.revision_id)

    receipt = loop.verify_full_rerun_equivalence(location_ids=(UUID(int=12), UUID(int=11)))
    assert receipt.equivalent
    assert receipt.max_absolute_difference <= receipt.absolute_tolerance
    assert tuple(item.location_id for item in receipt.location_checks) == (
        UUID(int=11),
        UUID(int=12),
    )
    assert all(item.equivalent_within_tolerance for item in receipt.location_checks)

    forged = receipt.model_dump(mode="python")
    forged["max_absolute_difference"] = 0.5
    with pytest.raises(ValidationError, match="maximum is not derived"):
        HybridFullRerunEquivalenceReceipt.model_validate(forged)

    forged = receipt.model_dump(mode="python")
    forged["equivalent"] = False
    with pytest.raises(ValidationError, match="equivalence is not derived"):
        HybridFullRerunEquivalenceReceipt.model_validate(forged)


def test_log_order_makes_fresh_identities_numerically_reproducible() -> None:
    location = UUID(int=21)
    loops = (_loop(), _loop())
    for loop in loops:
        placements = [
            _ingest_mass(loop, location, 0.07 + (index % 7) * 0.03) for index in range(40)
        ]
        for placement in placements[::3]:
            loop.retract_revision(placement.revision_id)

    receipts = tuple(loop.verify_full_rerun_equivalence(location_ids=(location,)) for loop in loops)
    assert receipts[0].location_checks[0].cached_projection_sha256 == (
        receipts[1].location_checks[0].cached_projection_sha256
    )
    assert receipts[0].location_checks[0].rebuilt_projection_sha256 == (
        receipts[1].location_checks[0].rebuilt_projection_sha256
    )
    assert receipts[0].max_absolute_difference == receipts[1].max_absolute_difference


def _calibration_payload() -> dict[str, object]:
    rows = _paired_rows()
    loop = _loop()
    _ingest(loop, UUID(int=13))
    report = CostGuardrailCalibrationReport(
        source_action_report_path="/tmp/source.json",
        source_action_report_sha256="a" * 64,
        dataset_config_path="/tmp/config.json",
        dataset_config_sha256="b" * 64,
        selected_candidate_parameters={"owner_threshold": 0.4},
        paired_holdout_rows=rows,
        break_even_envelope=_break_even_envelope(rows),
        train_full_rerun_observations=(
            TrainFullRerunObservation(
                episode_id=UUID(int=201),
                registered_location_ids=(UUID(int=13), UUID(int=14)),
                receipt=loop.verify_full_rerun_equivalence(
                    location_ids=(UUID(int=13), UUID(int=14))
                ),
            ),
        ),
        development_full_rerun_all_equivalent=True,
    )
    return report.model_dump(mode="python")


def test_report_rejects_forged_positive_outputs_and_erased_paper_bindings() -> None:
    forged = deepcopy(_calibration_payload())
    forged["break_even_envelope"][  # type: ignore[index]
        "maximum_contamination_cost_per_event_in_inspection_cost_units"
    ] = 99.0
    with pytest.raises(ValidationError, match="not derived from paired holdout rows"):
        CostGuardrailCalibrationReport.model_validate(forged)

    forged = deepcopy(_calibration_payload())
    forged["development_full_rerun_all_equivalent"] = False
    with pytest.raises(ValidationError, match="not derived from training receipts"):
        CostGuardrailCalibrationReport.model_validate(forged)

    forged = deepcopy(_calibration_payload())
    forged["unresolved_paper_bindings"] = PAPER_BINDINGS_STILL_REQUIRED[:-1]
    with pytest.raises(ValidationError, match="were erased or substituted"):
        CostGuardrailCalibrationReport.model_validate(forged)


def test_report_rejects_relaxed_replay_tolerance_and_incomplete_location_coverage() -> None:
    relaxed = deepcopy(_calibration_payload())
    relaxed["train_full_rerun_observations"][0]["receipt"][  # type: ignore[index]
        "absolute_tolerance"
    ] = 1.0
    with pytest.raises(ValidationError, match="substituted the development replay tolerance"):
        CostGuardrailCalibrationReport.model_validate(relaxed)

    incomplete = deepcopy(_calibration_payload())
    incomplete["train_full_rerun_observations"][0][  # type: ignore[index]
        "registered_location_ids"
    ] = (UUID(int=13), UUID(int=14), UUID(int=15))
    with pytest.raises(ValidationError, match="does not cover the registered locations exactly"):
        CostGuardrailCalibrationReport.model_validate(incomplete)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("reference_minus_candidate_search_regret", float("nan")),
        ("candidate_minus_reference_contamination_events", float("inf")),
        ("reference_minus_candidate_search_regret", True),
        ("reference_minus_candidate_search_regret", "1.0"),
        ("step_count", True),
    ),
)
def test_invalid_case_metric_types_and_values_are_rejected(field: str, value: object) -> None:
    payload = _paired_rows()[0].model_dump(mode="python")
    payload[field] = value
    with pytest.raises(ValidationError):
        PairedCostGuardrailEpisode.model_validate(payload)


def _write_bound_source(tmp_path: Path) -> tuple[Path, Path]:
    config_path = tmp_path / "dataset.json"
    config_payload = {
        "schema_version": "1.0.0",
        "dataset_version": "cost-guardrail-verifier-test@0.1",
        "adapter": "D0SyntheticOracleReplayAdapter",
        "evidence_stage": "unit_test_development",
        "confirmatory": False,
        "train_seed_start": 1,
        "train_seed_count": 1,
        "validation_seed_start": 101,
        "validation_seed_count": 1,
        "test_seed_start": 6003,
        "test_seed_count": 2,
        "steps_per_episode": 8,
        "object_family_bucket_count": 10,
        "development_uuid_seal_secret": "project-two-d0-multiseed-readout-v0.5",
        "split_keys": [
            "household_id",
            "scene_id",
            "object_instance_id",
            "object_family",
        ],
        "truth_store": "separate_evaluator_envelope",
        "external_dataset_selected": False,
        "retained_capabilities": [
            "hidden_event_inference",
            "multi_actor_reasoning",
            "open_world_unknowns",
            "reversible_attribution",
            "embodied_execution_feedback",
        ],
    }
    config_path.write_text(json.dumps(config_payload), encoding="utf-8")
    config = D0SyntheticReplayExperimentConfig.load(config_path)
    action_report = ProjectTwoActionBenchmarkV02().run(config.build_adapter().build())
    config_sha = hashlib.sha256(config_path.read_bytes()).hexdigest()
    source_path = tmp_path / "action.json"
    source_path.write_text(
        json.dumps(
            {
                "experiment_config": {
                    "path": str(config_path.resolve()),
                    "sha256": config_sha,
                    "confirmatory": config.confirmatory,
                    "evidence_stage": config.evidence_stage,
                },
                "benchmark": action_report.model_dump(mode="json"),
            }
        ),
        encoding="utf-8",
    )
    return source_path, config_path


def test_dependency_verifier_rejects_an_internally_consistent_forgery(
    tmp_path: Path,
) -> None:
    source_path, config_path = _write_bound_source(tmp_path)
    report = build_cost_guardrail_calibration(
        source_action_report_path=source_path,
        dataset_config_path=config_path,
    )
    artifact_path = tmp_path / "calibration.json"
    artifact_path.write_text(
        json.dumps({"calibration": report.model_dump(mode="json")}), encoding="utf-8"
    )
    assert verify_cost_guardrail_calibration_artifact(artifact_path) == report

    rows = list(report.paired_holdout_rows)
    rows[0] = rows[0].model_copy(
        update={
            "reference_minus_candidate_search_regret": (
                rows[0].reference_minus_candidate_search_regret + 1.0
            )
        }
    )
    forged = report.model_copy(
        update={
            "paired_holdout_rows": tuple(rows),
            "break_even_envelope": _break_even_envelope(tuple(rows)),
        }
    )
    artifact_path.write_text(
        json.dumps({"calibration": forged.model_dump(mode="json")}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="dependency-derived recomputation"):
        verify_cost_guardrail_calibration_artifact(artifact_path)


def test_builder_rejects_a_different_config_with_the_same_dataset_version(
    tmp_path: Path,
) -> None:
    source_path, config_path = _write_bound_source(tmp_path)
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    payload["evidence_stage"] = "substituted_stage"
    substitute = tmp_path / "substitute.json"
    substitute.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="not the action artifact's bound config"):
        build_cost_guardrail_calibration(
            source_action_report_path=source_path,
            dataset_config_path=substitute,
        )
