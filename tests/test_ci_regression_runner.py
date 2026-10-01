"""Real child outcomes and timeout attacks against CI diagnostic preservation."""

import json
import os
import select
import signal
import subprocess
import sys
from contextlib import suppress
from pathlib import Path

import pytest
from run_ci_regression import run


def _pytest_project(tmp_path, body, *, budget=30):
    root = tmp_path / "project"
    root.mkdir()
    (root / "src").mkdir()
    (root / "src/sample.py").write_text("def value():\n    return 7\n")
    (root / "pytest.ini").write_text("[pytest]\naddopts =\npythonpath = src\n")
    if body is not None:
        (root / "test_sample.py").write_text(body)
    output = tmp_path / "result"
    command = [
        sys.executable,
        "-u",
        "-m",
        "pytest",
        "-q",
        "--tb=short",
        f"--junitxml={output / 'pytest.xml'}",
        "--cov=sample",
        f"--cov-report=xml:{output / 'coverage.xml'}",
    ]
    return run(command, cwd=root, output=output, budget_seconds=budget, grace_seconds=5), output


@pytest.mark.parametrize("expected", [7, 8])
def test_real_pytest_success_and_failure_keep_logs_junit_and_coverage(tmp_path, expected):
    result, output = _pytest_project(
        tmp_path, f"from sample import value\ndef test_value():\n    assert value() == {expected}\n"
    )
    code = 0 if expected == 7 else 1
    assert result["exit_code"] == result["child_exit_code"] == code
    assert result["status"] == ("PASSED" if code == 0 else "FAILED")
    assert result["pytest_junit_present"] and result["coverage_xml_present"]
    assert (output / "pytest.log").stat().st_size > 0
    assert json.loads((output / "result.json").read_text()) == result
    if code:
        assert "assert 7 == 8" in (output / "pytest.log").read_text()
        assert "<failure" in (output / "pytest.xml").read_text()


def test_empty_collection_does_not_become_success(tmp_path):
    result, _ = _pytest_project(tmp_path, None)
    assert result["exit_code"] == 5 and result["status"] == "FAILED"


def test_collection_error_is_retained(tmp_path):
    result, output = _pytest_project(tmp_path, "def invalid syntax\n")
    assert result["exit_code"] == 2 and result["status"] == "FAILED"
    assert "SyntaxError" in (output / "pytest.log").read_text()
    assert result["pytest_junit_present"]


@pytest.mark.skipif(os.name != "posix", reason="POSIX graceful interrupt contract")
def test_real_pytest_timeout_preserves_partial_junit_without_claiming_success(tmp_path):
    result, output = _pytest_project(
        tmp_path,
        "import time\ndef test_first():\n    assert True\ndef test_later():\n    time.sleep(60)\n",
        budget=10,
    )
    assert result["exit_code"] == 124 and result["status"] == "TIMED_OUT"
    assert result["pytest_junit_present"]
    assert "KeyboardInterrupt" in (output / "pytest.log").read_text()
    assert not result["force_required"]


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group contract")
def test_timeout_cannot_be_forged_into_success_by_zero_exit_on_interrupt(tmp_path):
    command = [
        sys.executable,
        "-u",
        "-c",
        (
            "import signal,sys,time\n"
            "signal.signal(signal.SIGINT, lambda *_: sys.exit(0))\n"
            "print('child ready', flush=True)\n"
            "time.sleep(60)\n"
        ),
    ]
    result = run(
        command, cwd=tmp_path, output=tmp_path / "result", budget_seconds=2, grace_seconds=1
    )
    assert result["child_exit_code"] == 0
    assert result["exit_code"] == 124 and result["status"] == "TIMED_OUT"
    assert result["timed_out"] and result["interrupted_group_cleanup_attempted"]
    assert "child ready" in (tmp_path / "result/pytest.log").read_text()


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group contract")
def test_ignored_interrupt_is_forcibly_bounded_and_recorded(tmp_path):
    command = [
        sys.executable,
        "-u",
        "-c",
        (
            "import signal,time\n"
            "signal.signal(signal.SIGINT, signal.SIG_IGN)\n"
            "print('ignoring interrupt', flush=True)\n"
            "time.sleep(60)\n"
        ),
    ]
    result = run(
        command, cwd=tmp_path, output=tmp_path / "result", budget_seconds=2, grace_seconds=0.2
    )
    assert result["child_exit_code"] == -signal.SIGKILL
    assert result["exit_code"] == 124 and result["force_required"]
    assert result["seconds"] < 15


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group and FIFO contract")
def test_zero_exit_parent_cannot_leave_an_interrupt_ignoring_child(tmp_path):
    fifo = tmp_path / "child-lifetime"
    os.mkfifo(fifo)
    reader = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)
    child = (
        "import os,signal,time\n"
        "signal.signal(signal.SIGINT, signal.SIG_IGN)\n"
        f"fd=os.open({str(fifo)!r}, os.O_WRONLY)\n"
        "os.write(fd, str(os.getpgrp()).encode())\n"
        "time.sleep(60)\n"
    )
    parent = (
        "import subprocess,sys,signal,time\n"
        "signal.signal(signal.SIGINT, lambda *_: sys.exit(0))\n"
        f"subprocess.Popen([sys.executable, '-u', '-c', {child!r}])\n"
        "time.sleep(60)\n"
    )
    result = None
    writer_closed = False
    try:
        result = run(
            [sys.executable, "-u", "-c", parent],
            cwd=tmp_path,
            output=tmp_path / "result",
            budget_seconds=3,
            grace_seconds=1,
        )
        assert result["child_exit_code"] == 0 and result["exit_code"] == 124
        assert os.read(reader, 100) == str(result["pid"]).encode()
        # EOF proves every writer closed. A surviving child would instead
        # cause BlockingIOError here, even if CPU scheduling delayed its work.
        assert select.select([reader], [], [], 5)[0], "owned child retained its writer"
        assert os.read(reader, 1) == b""
        writer_closed = True
    finally:
        os.close(reader)
        # The parent has been reaped and EOF proves its only child closed the
        # writer. Do not signal this already-finished group again (or a reused ID).
        if result is not None and not writer_closed:
            with suppress(ProcessLookupError):
                os.killpg(result["pid"], signal.SIGKILL)


@pytest.mark.skipif(os.name != "posix", reason="POSIX CLI interruption contract")
def test_real_cli_propagates_timeout_instead_of_returning_zero(tmp_path):
    tool = Path(__file__).resolve().parents[1] / "tools/run_ci_regression.py"
    output = tmp_path / "cli-result"
    completed = subprocess.run(
        [
            sys.executable,
            str(tool),
            "--output",
            str(output),
            "--budget-seconds",
            "0.2",
            "--grace-seconds",
            "1",
            "--workers",
            "1",
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert completed.returncode == 124, completed.stderr
    result = json.loads((output / "result.json").read_text())
    assert result["status"] == "TIMED_OUT" and result["exit_code"] == 124


def test_launch_failure_remains_nonzero_with_a_record(tmp_path):
    result = run([str(tmp_path / "nonexistent")], cwd=tmp_path, output=tmp_path / "result")
    assert result["exit_code"] == 127 and result["status"] == "LAUNCH_FAILED"
    assert "error" in json.loads((tmp_path / "result/result.json").read_text())


def test_existing_evidence_cannot_be_overwritten(tmp_path):
    output = tmp_path / "result"
    output.mkdir()
    marker = output / "result.json"
    marker.write_text('{"status":"FAILED"}\n')
    with pytest.raises(FileExistsError):
        run([sys.executable, "-c", "pass"], cwd=tmp_path, output=output)
    assert marker.read_text() == '{"status":"FAILED"}\n'


@pytest.mark.parametrize("budget", [0, -1, float("inf"), float("nan")])
def test_invalid_deadline_never_launches_a_child(tmp_path, budget):
    marker = tmp_path / "launched"
    with pytest.raises(ValueError, match="positive finite"):
        run(
            [sys.executable, "-c", f"open({str(marker)!r}, 'w').close()"],
            cwd=tmp_path,
            output=tmp_path / "result",
            budget_seconds=budget,
        )
    assert not marker.exists() and not (tmp_path / "result").exists()
