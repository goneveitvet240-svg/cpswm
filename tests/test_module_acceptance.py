"""Acceptance must not turn missing execution, skips, or known gaps into a pass."""

import sys
from pathlib import Path

import pytest
from run_module_acceptance import classify, environment, pytest_result, run_stage


@pytest.mark.parametrize(
    "stages,unchanged,expected",
    [
        ([], True, ("FAILED", 1)),
        ([{"status": "PASSED"}], False, ("FAILED", 1)),
        ([{"status": "FAILED"}], True, ("FAILED", 1)),
        ([{"status": "PARTIAL"}], True, ("PARTIAL", 2)),
        ([{"status": "PASSED"}], True, ("PARTIAL", 2)),
    ],
)
def test_execution_success_cannot_override_missing_capabilities(stages, unchanged, expected):
    assert classify(stages, unchanged) == expected


def test_empty_junit_does_not_count_as_execution(tmp_path):
    path = tmp_path / "tests.xml"
    path.write_text('<testsuites><testsuite tests="100"/></testsuites>')
    with pytest.raises(ValueError, match="No executed"):
        pytest_result(path)


def test_junit_counts_actual_cases_not_forged_suite_totals(tmp_path):
    path = tmp_path / "tests.xml"
    path.write_text(
        '<testsuites><testsuite tests="500" failures="0"><testcase/>'
        "<testcase><failure/></testcase><testcase><error/></testcase>"
        "<testcase><skipped/></testcase></testsuite></testsuites>"
    )
    assert pytest_result(path) == dict(tests=4, passed=1, failures=1, errors=1, skipped=1)


def test_base_interpreter_fallback_is_refused(monkeypatch):
    monkeypatch.setattr(sys, "prefix", "/nonexistent/base-python")
    with pytest.raises(ValueError, match=r"pyvenv\.cfg"):
        environment()


def test_exit_zero_without_result_is_failure(tmp_path):
    result = run_stage(tmp_path, "missing", ["-c", "pass"], {}, 10)
    assert result["exit_code"] == 0 and result["status"] == "FAILED"


def test_timeout_is_recorded_and_process_is_terminated(tmp_path):
    result = run_stage(tmp_path, "timeout", ["-c", "import time;time.sleep(10)"], {}, 0.05)
    assert result["exit_code"] == 124 and result["status"] == "FAILED"
    assert (tmp_path / "timeout" / "result.json").is_file()


def test_positive_stage_requires_real_artifact(tmp_path):
    artifact = tmp_path / "ok" / "data" / "result.json"
    code = (
        f'from pathlib import Path;p=Path({str(artifact)!r});p.parent.mkdir();p.write_text("{{}}")'
    )
    result = run_stage(tmp_path, "ok", ["-c", code], {}, 10)
    assert result["status"] == "PASSED"
    assert result["result_sha256"]
    assert Path(result["command"][0]).is_file()
