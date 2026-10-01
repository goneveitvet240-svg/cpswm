"""Preserve regression diagnostics on failure or timeout; never certify acceptance."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import signal
import subprocess
import sys
import time
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path


def _signal_owned(process: subprocess.Popen, *, force: bool) -> None:
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL if force else signal.SIGINT)
        elif force:
            process.kill()
        else:
            process.send_signal(signal.CTRL_BREAK_EVENT)
    except ProcessLookupError:
        pass


def run(command, *, cwd: Path, output: Path, budget_seconds=3900.0, grace_seconds=60.0):
    """Run one owned process group, retain its actual result and bounded diagnostics."""
    if not command or any(not isinstance(arg, str) or not arg for arg in command):
        raise ValueError("nonempty command arguments required")
    if not all(math.isfinite(v) and v > 0 for v in (budget_seconds, grace_seconds)):
        raise ValueError("positive finite execution and grace budgets required")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    log_path = output / "pytest.log"
    result_path = output / "result.json"
    result = {
        "scope": "REGRESSION_EXECUTION_DIAGNOSTIC_NOT_SCIENTIFIC_ACCEPTANCE",
        "command": command,
        "cwd": str(cwd.resolve()),
        "started_at": datetime.now(UTC).isoformat(),
        "budget_seconds": budget_seconds,
        "grace_seconds": grace_seconds,
        "status": "RUNNING",
        "process_group_cleanup_supported": os.name == "posix",
    }

    def record():
        temporary = result_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(result, indent=2) + "\n")
        temporary.replace(result_path)

    record()
    start = time.monotonic()
    timed_out = interrupted = forced = False
    with log_path.open("wb") as log, log_path.open("rb") as reader:

        def echo():
            while data := reader.read(65536):
                sys.stdout.write(data.decode("utf-8", errors="replace"))
                sys.stdout.flush()

        options = (
            {"start_new_session": True}
            if os.name == "posix"
            else {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        )
        try:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                stdout=log,
                stderr=subprocess.STDOUT,
                env=dict(os.environ, COVERAGE_FILE=str(output / "coverage-data")),
                **options,
            )
        except OSError as error:
            result.update(status="LAUNCH_FAILED", exit_code=127, error=str(error))
        else:
            result["pid"] = process.pid
            record()

            def wait_until(deadline):
                while process.poll() is None:
                    echo()
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return False
                    with suppress(subprocess.TimeoutExpired):
                        process.wait(timeout=min(0.1, remaining))
                echo()
                return True

            try:
                try:
                    timed_out = not wait_until(start + budget_seconds)
                except KeyboardInterrupt:
                    interrupted = True
                if timed_out or interrupted:
                    _signal_owned(process, force=False)
                    try:
                        finished = wait_until(time.monotonic() + grace_seconds)
                    except KeyboardInterrupt:
                        finished = False
                    if not finished:
                        forced = True
                    # A leader that exits zero on SIGINT cannot leave its own
                    # surviving POSIX workers behind or turn a timeout into PASS.
                    _signal_owned(process, force=True)
                    process.wait(timeout=10)
            finally:
                if process.poll() is None:
                    _signal_owned(process, force=True)
                    process.wait(timeout=10)
                echo()
            actual = process.returncode
            code = 124 if timed_out else 130 if interrupted else actual
            if code < 0:
                code = 128 - code
            result.update(
                status="TIMED_OUT"
                if timed_out
                else "INTERRUPTED"
                if interrupted
                else "PASSED"
                if code == 0
                else "FAILED",
                exit_code=code,
                child_exit_code=actual,
                timed_out=timed_out,
                interrupted=interrupted,
                force_required=forced,
                interrupted_group_cleanup_attempted=(timed_out or interrupted)
                and os.name == "posix",
            )
    result.update(
        seconds=time.monotonic() - start,
        log_sha256=hashlib.sha256(log_path.read_bytes()).hexdigest(),
        pytest_junit_present=(output / "pytest.xml").is_file(),
        coverage_xml_present=(output / "coverage.xml").is_file(),
    )
    record()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--budget-seconds", type=float, default=3900)
    parser.add_argument("--grace-seconds", type=float, default=60)
    parser.add_argument("--workers", default="auto")
    parser.add_argument("--inputs", type=Path, help="completed current-input preparation directory")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    if args.inputs is not None:
        from prepare_current_validation_inputs import consumer_environment

        os.environ.update(consumer_environment(root, args.inputs))
    command = [
        sys.executable,
        "-u",
        "-m",
        "pytest",
        "-o",
        "addopts=",
        "-v",
        "--tb=short",
        "-n",
        args.workers,
        "--dist=loadscope",
        "--durations=25",
        "--cov=src",
        "--cov-report=term-missing",
        f"--cov-report=xml:{output / 'coverage.xml'}",
        f"--junitxml={output / 'pytest.xml'}",
    ]
    result = run(
        command,
        cwd=root,
        output=output,
        budget_seconds=args.budget_seconds,
        grace_seconds=args.grace_seconds,
    )
    print(json.dumps(result), flush=True)
    return result["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
