from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from cpswm.system.evaluation_operations.structure_two_combination_a import (
    ExternalComparisonStage,
    OrdinaryGraphBaseline,
    StructureTwoCombinationASelection,
)
from cpswm.system.evaluation_operations.structure_two_evidence_artifacts import (
    InterventionFactor,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/project_two_experiments/structure_two_combination_a_v0_1.json"


def test_combination_a_selection_is_frozen_and_fail_closed() -> None:
    selection = StructureTwoCombinationASelection.load(CONFIG)

    assert selection.selection_id == "structure-two-combination-a@0.1"
    assert set(selection.ordinary_graph_baselines) == set(OrdinaryGraphBaseline)
    assert selection.external_comparison_sequence == (
        ExternalComparisonStage.O_STAR_FAITHFUL,
        ExternalComparisonStage.ENHANCED_O_STAR,
    )
    assert not selection.confirmatory_execution_ready
    assert len(selection.content_sha256) == 64


def test_combination_a_builds_all_32_unique_factorial_cells() -> None:
    cells = StructureTwoCombinationASelection.load(CONFIG).factorial_cells()

    assert len(cells) == 32
    assert len({cell.cell_id for cell in cells}) == 32
    assert (
        len(
            {
                tuple((factor, cell.levels[factor]) for factor in InterventionFactor)
                for cell in cells
            }
        )
        == 32
    )
    assert all(set(cell.levels) == set(InterventionFactor) for cell in cells)


def test_combination_a_rejects_scope_narrowing_and_reordered_external_claim() -> None:
    payload = StructureTwoCombinationASelection.load(CONFIG).model_dump(mode="python")
    with pytest.raises(ValidationError, match="cannot narrow"):
        StructureTwoCombinationASelection.model_validate(
            {**payload, "retained_capabilities": ("hidden_event_inference",)}
        )
    with pytest.raises(ValidationError, match="faithful O-STaR before enhanced"):
        StructureTwoCombinationASelection.model_validate(
            {
                **payload,
                "external_comparison_sequence": tuple(
                    reversed(payload["external_comparison_sequence"])
                ),
            }
        )


def test_combination_a_rejects_a_weak_graph_baseline_suite() -> None:
    payload = StructureTwoCombinationASelection.load(CONFIG).model_dump(mode="python")
    with pytest.raises(ValidationError, match="MLP, R-GCN, and HGT"):
        StructureTwoCombinationASelection.model_validate(
            {**payload, "ordinary_graph_baselines": (OrdinaryGraphBaseline.R_GCN,)}
        )
