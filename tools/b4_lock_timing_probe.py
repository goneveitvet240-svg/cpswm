from __future__ import annotations

import argparse
import cProfile
import hashlib
import json
import subprocess
import sys
import tempfile
import time
import types
from pathlib import Path
from threading import Event, Thread


class _Mark:
    def parametrize(self, *args, **kwargs):
        def decorate(function):
            return function
        return decorate


class _PytestStub(types.ModuleType):
    mark = _Mark()
    MonkeyPatch = object

    def raises(self, *args, **kwargs):
        raise RuntimeError("pytest.raises is unavailable in the timing-only probe")


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]
sys.modules.setdefault("pytest", _PytestStub("pytest"))

import test_structure_two_execution_interface as target  # noqa: E402

from cpswm.system.structure_two_execution import (  # noqa: E402
    canonical_legacy_ordinary_transition_plan,
)


def _ns() -> int:
    return time.perf_counter_ns()


def _profile_rows(profile: cProfile.Profile, limit: int) -> list[dict[str, object]]:
    rows = []
    for entry in profile.getstats():
        code = entry.code
        if hasattr(code, "co_filename"):
            path = Path(code.co_filename)
            try:
                filename = str(path.relative_to(ROOT))
            except ValueError:
                filename = str(path)
            symbol = f"{filename}:{code.co_firstlineno}:{code.co_name}"
        else:
            symbol = str(code)
        rows.append(
            {
                "symbol": symbol,
                "calls": entry.callcount,
                "recursive_calls": entry.reccallcount,
                "self_ms": entry.inlinetime * 1000.0,
                "cumulative_ms": entry.totaltime * 1000.0,
            }
        )
    return sorted(rows, key=lambda row: row["cumulative_ms"], reverse=True)[:limit]


def run_case(lock_target: str, *, profile_top: int = 0) -> dict[str, object]:
    setup_start = _ns()
    system, transition = target._system_and_transition()
    setup_end = _ns()
    target_lock = {
        "core": system.core._execution_lock,
        "wrapper": system._execution_lock,
        "ccrr": system.core._automatic_regimes.ccrr._lock,
    }[lock_target]
    worker_has_lock = Event()
    release_worker = Event()
    times: dict[str, int] = {}
    outcome: list[BaseException | None] = []
    worker_box: list[Thread] = []
    profiler = cProfile.Profile() if profile_top else None

    class Sink(target.RecordingSink):
        def commit(self, trace, /):
            times["sink_enter"] = _ns()
            acknowledgement = super().commit(trace)
            times["sink_super_done"] = _ns()
            if lock_target != "ccrr":
                target_lock.release()
            times["target_released"] = _ns()

            def hold_lock() -> None:
                with target_lock:
                    times["worker_acquired"] = _ns()
                    worker_has_lock.set()
                    release_worker.wait(timeout=5.0)

            worker = Thread(target=hold_lock, daemon=True)
            worker_box.append(worker)
            worker.start()
            worker_has_lock.wait(timeout=5.0)
            times["sink_return"] = _ns()
            return acknowledgement

    def invoke() -> None:
        times["invoke_start"] = _ns()
        if profiler is not None:
            profiler.enable()
        try:
            system.process_transition(
                transition,
                execution_plan=canonical_legacy_ordinary_transition_plan(),
                trace_sink=Sink(),
            )
        except BaseException as error:
            outcome.append(error)
        else:
            outcome.append(None)
        finally:
            if profiler is not None:
                profiler.disable()
            times["invoke_done"] = _ns()

    caller = Thread(target=invoke, daemon=True)
    start = _ns()
    caller.start()
    caller.join(timeout=1.0)
    alive_at_deadline = caller.is_alive()
    deadline_observed = _ns()
    release_worker.set()
    if worker_box:
        worker_box[0].join(timeout=5.0)
    caller.join(timeout=5.0)

    phases_ms = {
        "setup": (setup_end - setup_start) / 1e6,
        "start_to_deadline_observation": (deadline_observed - start) / 1e6,
    }
    pairs = {
        "pre_sink": ("invoke_start", "sink_enter"),
        "sink_super": ("sink_enter", "sink_super_done"),
        "release_to_worker": ("target_released", "worker_acquired"),
        "worker_to_sink_return": ("worker_acquired", "sink_return"),
        "post_sink_until_done": ("sink_return", "invoke_done"),
        "total_invoke": ("invoke_start", "invoke_done"),
    }
    for label, (left, right) in pairs.items():
        if left in times and right in times:
            phases_ms[label] = (times[right] - times[left]) / 1e6
    result: dict[str, object] = {
        "target": lock_target,
        "alive_at_1s": alive_at_deadline,
        "outcome": None if not outcome or outcome[0] is None else {
            "type": type(outcome[0]).__qualname__,
            "message": str(outcome[0]),
        },
        "phases_ms": phases_ms,
    }
    if profiler is not None:
        result["profile_top_by_cumulative_time"] = _profile_rows(profiler, profile_top)
    return result


def run_parallel_process_control(workers: int) -> dict[str, object]:
    """Run independent three-lock probes concurrently as an xdist load analogue."""

    started = _ns()
    with tempfile.TemporaryDirectory(prefix="cpswm-lock-contention-") as temporary:
        root = Path(temporary)
        processes = []
        for index in range(workers):
            output_path = root / f"worker-{index}.json"
            process = subprocess.Popen(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--repeats",
                    "1",
                    "--output",
                    str(output_path),
                ],
                cwd=ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            processes.append((index, output_path, process))
        rows = []
        for index, output_path, process in processes:
            _stdout, stderr = process.communicate()
            payload = (
                json.loads(output_path.read_text(encoding="utf-8"))
                if output_path.exists()
                else {}
            )
            rows.append(
                {
                    "worker": index,
                    "returncode": process.returncode,
                    "stderr": stderr,
                    "cases": payload.get("cases", []),
                }
            )
    return {
        "workers": workers,
        "group_elapsed_ms": (_ns() - started) / 1e6,
        "workers_result": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument(
        "--profile-top",
        type=int,
        default=0,
        help="also run one separately labelled profiled case per lock target",
    )
    parser.add_argument(
        "--contention-workers",
        type=int,
        default=0,
        help="run this many independent probe processes concurrently",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    if args.profile_top < 0 or args.contention_workers < 0:
        parser.error("profile-top and contention-workers must be nonnegative")
    probe_system, _ = target._system_and_transition()
    source_path = Path(sys.modules["cpswm.system.structure_two_particle_workspace"].__file__)
    disk_samples = []
    binding_samples = []
    for _ in range(20):
        started = _ns()
        hashlib.sha256(source_path.read_bytes()).hexdigest()
        disk_samples.append((_ns() - started) / 1e6)
        started = _ns()
        probe_system.core._check_particle_workspace_binding()
        binding_samples.append((_ns() - started) / 1e6)
    output = {
        "schema": "cpswm.pc-b.lock-timing-probe@1",
        "python": sys.version,
        "platform": sys.platform,
        "source_path": str(source_path),
        "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "disk_sha_ms": disk_samples,
        "binding_check_ms": binding_samples,
        "cases": [
            run_case(name)
            for _ in range(args.repeats)
            for name in ("core", "wrapper", "ccrr")
        ],
    }
    if args.profile_top:
        output["profiled_cases"] = [
            run_case(name, profile_top=args.profile_top)
            for name in ("core", "wrapper", "ccrr")
        ]
    if args.contention_workers:
        output["parallel_process_control"] = run_parallel_process_control(
            args.contention_workers
        )
    rendered = json.dumps(output, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
