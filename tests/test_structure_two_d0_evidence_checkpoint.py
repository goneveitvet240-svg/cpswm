from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "apps/evaluation_runner/run_structure_two_d0_evidence_checkpoint.py"
)
SPEC = importlib.util.spec_from_file_location("run_structure_two_d0_evidence_checkpoint", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_envelope_binds_every_positive_boolean_to_the_full_trust_chain() -> None:
    result = {"passed": True, "nested": [{"verified": True}, {"verified": False}]}
    envelope = MODULE.make_envelope(result=result, command=("--task", "test"))
    assert set(envelope["positive_output_trust_chain"]) == {
        "/passed",
        "/nested/0/verified",
    }
    MODULE.verify_envelope(envelope, fresh_result=result)


def test_envelope_rejects_a_forged_but_fully_rehashed_positive_output() -> None:
    original = {"passed": False}
    envelope = MODULE.make_envelope(result=dict(original), command=("--task", "test"))
    envelope["result"]["passed"] = True
    envelope["positive_output_trust_chain"] = {
        "/passed": (
            "artifact_content+source_bundle+protocol_document+"
            "fresh_task_specific_recomputation_required"
        )
    }
    envelope["deterministic_result_sha256"] = MODULE._canonical_sha256(
        MODULE.deterministic_projection(envelope["result"])
    )
    unsigned = dict(envelope)
    unsigned.pop("content_sha256")
    envelope["content_sha256"] = MODULE._canonical_sha256(unsigned)
    with pytest.raises(ValueError, match="fresh task-specific recomputation"):
        MODULE.verify_envelope(envelope, fresh_result=original)


def test_self_consistency_without_fresh_recomputation_is_not_verification() -> None:
    result = {"passed": False}
    envelope = MODULE.make_envelope(result=result, command=("--task", "test"))
    with pytest.raises(ValueError, match="fresh task-specific recomputation is required"):
        MODULE.verify_envelope(envelope)


def test_timing_is_not_part_of_deterministic_recomputation_hash() -> None:
    left = {"score": 0.5, "cost": {"wall_clock_seconds": 1.0}}
    right = {"score": 0.5, "cost": {"wall_clock_seconds": 99.0}}
    assert MODULE.deterministic_projection(left) == MODULE.deterministic_projection(right)
    assert MODULE._canonical_sha256(MODULE.deterministic_projection(left)) == (
        MODULE._canonical_sha256(MODULE.deterministic_projection(right))
    )


def test_non_timing_metric_remains_in_deterministic_recomputation_hash() -> None:
    left = {"score": 0.5, "cost": {"wall_clock_seconds": 1.0}}
    right = {"score": 0.6, "cost": {"wall_clock_seconds": 1.0}}
    assert MODULE._canonical_sha256(MODULE.deterministic_projection(left)) != (
        MODULE._canonical_sha256(MODULE.deterministic_projection(right))
    )
