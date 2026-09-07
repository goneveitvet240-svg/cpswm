"""Fast executable and adversarial checks for the local Task 11/12 diagnostics."""

from __future__ import annotations

import copy
import random
from pathlib import Path

import pytest

from cpswm.system.evaluation_operations.structure_two_backbone_falsifier import (
    UNRESOLVED_KEY,
    registered_scenarios,
)
from cpswm.system.evaluation_operations.structure_two_task11_resampling_diagnostic import (
    FINAL_INVOCATION_ID as TASK11_INVOCATION_ID,
)
from cpswm.system.evaluation_operations.structure_two_task11_resampling_diagnostic import (
    OUTPUT_RELATIVE,
    RECOVERY_RAW_RELATIVE,
    Policy,
    Task11VerificationError,
    _exact_summary,
    _verify_exact_command,
    attach_evaluator_evidence,
    canonical_sha256,
    deterministic_trace_projection,
    resampling_indices,
    run_approximate_trace,
    verify_raw_trace,
    verify_trace_against_fresh_execution,
    write_jsonl,
)
from cpswm.system.evaluation_operations.structure_two_task12_rejuvenation_diagnostic import (
    FINAL_INVOCATION_ID,
    KERNELS,
    execute_kernel,
)
from cpswm.system.evaluation_operations.structure_two_task12_rejuvenation_verifier import (
    verify_trace,
)


def _task11_trace() -> dict:
    scenario = registered_scenarios(1, (11,))[0]
    trace, support = run_approximate_trace(
        scenario,
        context="G1",
        replicate_seed=101,
        budget=24,
        policy=Policy("systematic", 0.5),
        invocation_id="task11-unit-contract-test",
    )
    return attach_evaluator_evidence(trace, support, scenario, _exact_summary(scenario))


@pytest.mark.parametrize(
    "algorithm", ("systematic", "stratified", "residual", "multinomial_negative_control")
)
def test_task11_resamplers_are_deterministic_and_budget_preserving(algorithm: str) -> None:
    weights = (0.55, 0.25, 0.15, 0.05)
    first = resampling_indices(weights, algorithm, random.Random(17))
    second = resampling_indices(weights, algorithm, random.Random(17))
    assert first == second
    assert len(first[0]) == len(weights)
    assert set(first[0]) <= set(range(len(weights)))


def test_task11_trace_recomputes_and_rejects_a_rehashed_state_forgery() -> None:
    trace = _task11_trace()
    assert verify_raw_trace(trace)["gates"]["raw_only_recomputation"]

    forged = copy.deepcopy(trace)
    forged["runtime"]["approximate_posterior"] = {"forged": 1.0}
    forged["deterministic_trace_sha256"] = canonical_sha256(deterministic_trace_projection(forged))
    with pytest.raises(Task11VerificationError):
        verify_raw_trace(forged)


def test_task11_g2_evaluator_annotations_bind_final_support_not_proposal_history() -> None:
    scenario = registered_scenarios(2, (11,))[0]
    trace, support = run_approximate_trace(
        scenario,
        context="G2",
        replicate_seed=101,
        budget=24,
        policy=Policy("no_resampling", None),
        invocation_id="task11-g2-final-support-regression",
    )
    trace = attach_evaluator_evidence(trace, support, scenario, _exact_summary(scenario))

    verified = verify_trace_against_fresh_execution(trace)

    assert verified["gates"]["fresh_source_replay"] is True
    assert set(trace["evaluator"]["support_annotations"]) == (
        set(trace["runtime"]["approximate_posterior"]) - {UNRESOLVED_KEY}
    )


def test_task12_all_kernels_execute_and_are_independently_recomputed() -> None:
    task11 = _task11_trace()
    manifest_hash = "a" * 64
    raw_hash = "b" * 64
    traces = [
        execute_kernel(
            task11,
            kernel=kernel,
            invocation_id=FINAL_INVOCATION_ID,
            task11_manifest_content_sha256=manifest_hash,
            task11_raw_file_sha256=raw_hash,
        )
        for kernel in KERNELS
    ]
    assert [row["coordinate"]["kernel"] for row in traces] == list(KERNELS)
    for trace in traces:
        metrics = verify_trace(
            trace,
            task11_row=task11,
            expected_manifest_content_sha256=manifest_hash,
            expected_task11_raw_file_sha256=raw_hash,
        )
        assert all(metrics["gates"].values())
    assert traces[1]["proposal_matrix_q_y_given_x"] != traces[2]["proposal_matrix_q_y_given_x"]


def test_task12_forged_positive_authorization_is_rejected() -> None:
    task11 = _task11_trace()
    trace = execute_kernel(
        task11,
        kernel=KERNELS[1],
        invocation_id=FINAL_INVOCATION_ID,
        task11_manifest_content_sha256="a" * 64,
        task11_raw_file_sha256="b" * 64,
    )
    forged = copy.deepcopy(trace)
    forged["formal_task_12_passed"] = True
    forged_without_hash = dict(forged)
    forged_without_hash.pop("trace_content_sha256")
    forged["trace_content_sha256"] = canonical_sha256(forged_without_hash)
    with pytest.raises(ValueError, match="forbidden positive"):
        verify_trace(
            forged,
            task11_row=task11,
            expected_manifest_content_sha256="a" * 64,
            expected_task11_raw_file_sha256="b" * 64,
        )


def test_task11_task12_disk_interface_uses_full_budget_gzip_files(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw_traces"
    write_jsonl(
        raw_dir / "task11_g1_full_budget_raw_traces.jsonl.gz",
        ({"context": "G1", "row": 1},),
    )
    write_jsonl(
        raw_dir / "task11_g2_full_budget_raw_traces.jsonl.gz",
        ({"context": "G2", "row": 2},),
    )
    from cpswm.system.evaluation_operations.structure_two_task12_rejuvenation_diagnostic import (
        TASK11_OUTPUT_RELATIVE,
        TASK11_RAW_RELATIVE,
        load_jsonl,
    )

    assert load_jsonl(tmp_path / TASK11_RAW_RELATIVE["G1"]) == [{"context": "G1", "row": 1}]
    assert load_jsonl(tmp_path / TASK11_RAW_RELATIVE["G2"]) == [{"context": "G2", "row": 2}]
    assert TASK11_OUTPUT_RELATIVE == OUTPUT_RELATIVE


def test_task11_recovery_command_is_fixed_to_the_quarantined_raw_identity() -> None:
    prefix = [
        "python",
        "apps/evaluation_runner/run_structure_two_task11_resampling_diagnostic.py",
        "--output-dir",
        OUTPUT_RELATIVE,
        "--invocation-id",
        TASK11_INVOCATION_ID,
        "--recover-raw-dir",
    ]
    _verify_exact_command([*prefix, RECOVERY_RAW_RELATIVE])
    with pytest.raises(Task11VerificationError, match="unexpected or malicious"):
        _verify_exact_command([*prefix, "/tmp/caller-selected-raw"])
