from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "apps/evaluation_runner/generate_structure_two_engineering_checkpoint.py"
SPEC = importlib.util.spec_from_file_location(
    "generate_structure_two_engineering_checkpoint", SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_legacy_engineering_checkpoint_is_explicitly_revoked() -> None:
    stored = json.loads(MODULE.DEFAULT_OUTPUT.read_text(encoding="utf-8"))
    MODULE.verify_checkpoint(stored)
    assert stored["status"] == "REVOKED_SUPERSEDED_BY_BACKBONE_B_REPAIRS"
    assert stored["recomputable_d0_evidence_allowed"] is False
    assert stored["external_validity_established"] is False
    assert stored["external_immutable_anchor_present"] is False
    assert len(stored["results"]) == 5
    assert all(row["trust_chain_complete"] is False for row in stored["results"])
    assert any(row["present"] is False for row in stored["results"])
    assert len(stored["replacement_results"]) == 2
    assert all(
        row["seven_operator_efficacy_authorized"] is False for row in stored["replacement_results"]
    )


def test_checkpoint_rejects_forged_positive_authorization() -> None:
    stored = json.loads(MODULE.DEFAULT_OUTPUT.read_text(encoding="utf-8"))
    stored["external_validity_established"] = True
    unsigned = dict(stored)
    unsigned.pop("content_sha256")
    stored["content_sha256"] = MODULE._canonical_sha256(unsigned)
    with pytest.raises(ValueError, match="checkpoint drift"):
        MODULE.verify_checkpoint(stored)
