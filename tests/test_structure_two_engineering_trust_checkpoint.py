from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "apps/evaluation_runner/generate_structure_two_engineering_trust_checkpoint.py"
SPEC = importlib.util.spec_from_file_location("structure_two_engineering_trust_checkpoint", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _stored() -> dict[str, object]:
    return json.loads(MODULE.OUTPUT.read_text(encoding="utf-8"))


def test_checkpoint_is_current_without_repeating_the_expensive_fresh_run() -> None:
    stored = _stored()
    MODULE.verify_checkpoint(stored, fresh_recomputation=False)
    assert stored["engineering_trust_gate_passed"] is True
    assert stored["recomputable_d0_evidence_allowed"] is True
    assert stored["seven_operator_ablation_authorized"] is False
    assert stored["external_confirmation"]["combined_status"] == "BLOCKED_FAIL_CLOSED"
    assert len(stored["task_results"]) == 4
    assert all(row["positive_output_trust_chain_complete"] for row in stored["task_results"])


def test_checkpoint_rejects_forged_but_fully_rehashed_positive_scope() -> None:
    stored = _stored()
    stored["seven_operator_ablation_authorized"] = True
    stored["positive_output_trust_chain"]["/seven_operator_ablation_authorized"] = (
        "checkpoint_content+current_p0_manifest+current_source_inventory+"
        "task_artifact_positive_path_map+fresh_task_specific_recomputation+bound_reports"
    )
    unsigned = dict(stored)
    unsigned.pop("content_sha256")
    stored["content_sha256"] = MODULE._canonical_sha256(unsigned)
    with pytest.raises(ValueError, match="drift or forged"):
        MODULE.verify_checkpoint(stored, fresh_recomputation=False)


def test_checkpoint_scope_contains_only_current_task_versions() -> None:
    assert _stored()["recomputable_d0_scope"] == [
        "task_7_v0_4",
        "task_8_v0_4",
        "task_10_g1_v0_1",
        "task_10_g2_v0_1",
    ]


def test_checkpoint_cannot_be_generated_with_fresh_recomputation_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--no-fresh-recomputation"])
    with pytest.raises(ValueError, match="generation always requires"):
        MODULE.main()
