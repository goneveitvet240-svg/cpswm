"""Contracts for the fresh-seed seven-operator factorial benchmark."""

from __future__ import annotations

import inspect
import subprocess
import sys
from pathlib import Path

import pytest

from cpswm.system.evaluation_operations import project_two_factorial_benchmark as factorial
from cpswm.system.evaluation_operations.project_two_factorial_benchmark import (
    Factor,
    TrustedSevenOperatorAuthorizationRequired,
    registered_factorial_cells,
    run_project_two_factorial_benchmark,
)


def test_registered_design_is_balanced_resolution_four() -> None:
    cells = registered_factorial_cells()
    assert len(cells) == 16
    assert len({cell.cell_id for cell in cells}) == 16
    for factor in Factor:
        assert sum(cell.levels[factor] == 1 for cell in cells) == 8
        assert sum(cell.levels[factor] == -1 for cell in cells) == 8
    for left_index, left in enumerate(Factor):
        for right in tuple(Factor)[left_index + 1 :]:
            assert sum(cell.levels[left] * cell.levels[right] for cell in cells) == 0


def test_missing_authorization_rejects_before_split_or_workload_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("factorial workload must not be constructed")

    monkeypatch.setattr(factorial, "ProjectTwoActionBenchmarkV02", forbidden)
    monkeypatch.setattr(factorial, "_dataset_for_cell", forbidden)
    with pytest.raises(
        TrustedSevenOperatorAuthorizationRequired,
        match="authorization is missing; workload was not created",
    ):
        run_project_two_factorial_benchmark(
            validation_seeds=(33000,),
            holdout_seeds=(33000,),
            max_steps=12,
        )


def test_direct_core_call_has_no_legacy_unchecked_execution_path() -> None:
    with pytest.raises(TrustedSevenOperatorAuthorizationRequired):
        run_project_two_factorial_benchmark(
            validation_seeds=(33100,),
            holdout_seeds=(34100,),
            max_steps=12,
        )


def test_public_runner_has_no_caller_supplied_verification_time_parameter() -> None:
    parameters = inspect.signature(run_project_two_factorial_benchmark).parameters
    assert "authorization_verification_time_utc" not in parameters
    assert "authorization_registry_authority" in parameters


def test_cli_runner_rejects_before_creating_output(tmp_path: Path) -> None:
    output = tmp_path / "must-not-exist.json"
    completed = subprocess.run(
        [
            sys.executable,
            "apps/evaluation_runner/run_project_two_factorial_benchmark.py",
            "--validation-count",
            "1",
            "--holdout-count",
            "1",
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 2
    assert "authorization is missing; workload was not created" in completed.stderr
    assert not output.exists()
