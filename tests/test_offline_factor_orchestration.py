"""Controlled orchestration substitutes; no Unity process or natural-data evidence."""

import copy
import hashlib
import json
import signal
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import collect_offline_factor_data as task
import pytest
import verify_offline_factor_capture as verifier


class ControlledProcess:
    def __init__(self, harness, command):
        self.harness = harness
        self.command = command
        self.directory = Path(command[command.index("--output") + 1])
        self.index = int(self.directory.name.split("-")[1])
        self.pid = 50000 + self.index
        self.wait_calls = []

    def wait(self, *, timeout):
        self.wait_calls.append(timeout)
        if timeout == 240:
            behavior = self.harness.failures.get(self.index)
            if behavior == "timeout":
                raise subprocess.TimeoutExpired(self.command, timeout)
            if behavior == "interrupt":
                raise KeyboardInterrupt("controlled interruption")
            if behavior == "nonzero":
                return 7
        return 0


class ControlledMatrix:
    def __init__(self, monkeypatch, tmp_path):
        self.archive = tmp_path / "controlled-source.gz"
        self.archive.write_bytes(b"controlled plan source, not a real archive")
        self.sdk_python = tmp_path / "sdk-python"
        self.binary = tmp_path / "unity-binary"
        self.output = tmp_path / "collection"
        self.source = {"src/controlled.py": "1" * 64}
        self.runtime = {"sdk": "controlled-sdk", "unity_sha256": "2" * 64}
        self.processes = []
        self.dispatches = []
        self.signals = []
        self.verifications = []
        self.plan_verifications = []
        self.failures = {}
        self.identity_attacks = {}
        self.frame_times = {}
        self.scopes = {index: [str(uuid4()) for _ in range(3)] for index in range(1, 13)}
        self.action_ids = {index: [str(uuid4()) for _ in range(8)] for index in range(1, 13)}
        self.plan = {
            "houses": [
                {
                    "index": index,
                    "split": "diagnostic_only"
                    if index == 0
                    else ("train" if index <= 8 else "validation"),
                    "relative_path": f"houses/house-{index:02d}.json",
                    "asset_ids": [f"asset-{index}"],
                    "instances": [
                        {
                            "object_id": f"object-{index}",
                            "asset_id": f"asset-{index}",
                            "exclusion_reasons": [] if index else ["index0_diagnostic_only"],
                        }
                    ],
                }
                for index in range(13)
            ]
        }

        def write_plan(archive, output):
            assert archive == self.archive
            (output / "houses").mkdir(parents=True)
            for house in self.plan["houses"]:
                # Distinct raw bytes bind the exact original index, regardless of path labels.
                (output / house["relative_path"]).write_bytes(
                    f'{{"original_index": {house["index"]}}}\n'.encode()
                )
            return copy.deepcopy(self.plan)

        def verify_plan(archive, output):
            assert archive == self.archive and output == self.output / "plan"
            self.plan_verifications.append(output)
            return copy.deepcopy(self.plan)

        def provenance(house, binary):
            assert binary == self.binary
            return {
                "worker": "3" * 64,
                "unity": "2" * 64,
                "house": hashlib.sha256(house.read_bytes()).hexdigest(),
                "capture_configuration": "4" * 64,
            }

        def popen(command, **kwargs):
            self.dispatches.append((command, kwargs))
            index = int(Path(command[command.index("--output") + 1]).name.split("-")[1])
            if self.failures.get(index) == "spawn":
                raise OSError("controlled process launch failure")
            process = ControlledProcess(self, command)
            self.processes.append(process)
            process.directory.mkdir()
            house = Path(command[command.index("--house") + 1])
            capture = {
                "source_files": copy.deepcopy(self.source),
                "runtime": copy.deepcopy(self.runtime),
                "provenance": provenance(house, self.binary),
            }
            attack = self.identity_attacks.get(index)
            if attack == "source":
                capture["source_files"]["src/controlled.py"] = "9" * 64
            elif attack == "runtime":
                capture["runtime"]["sdk"] = "other-sdk"
            elif attack == "provenance":
                capture["provenance"]["house"] = "9" * 64
            task.write_json(process.directory / "capture.json", capture)
            return process

        def verify_capture(directory, house, expected):
            index = int(directory.name.split("-")[1])
            assert house == self.output / "plan" / f"houses/house-{index:02d}.json"
            assert expected == provenance(house, self.binary)
            self.verifications.append(index)
            if self.failures.get(index) == "verification":
                raise ValueError("controlled frame provenance verification failure")
            self.frame_times.setdefault(index, datetime.now(UTC).isoformat())
            return {
                "scope": self.scopes[index],
                "frame_records": [
                    dict(
                        action_id=action,
                        **{
                            k: self.frame_times[index]
                            for k in ("decision_time", "capture_time", "received_at")
                        },
                    )
                    for action in self.action_ids[index]
                ],
                "all_assets": [f"asset-{index}"],
                "unknown_assets": [],
                "instances": [
                    {
                        "object_id": f"object-{index}",
                        "asset_id": f"asset-{index}",
                        "position_changed_during_initialization": False,
                        "exclusion_reasons": [],
                    }
                ],
            }

        monkeypatch.setattr(task, "write_plan", write_plan)
        monkeypatch.setattr(task, "verify_plan", verify_plan)
        monkeypatch.setattr(task, "source_identity", lambda: copy.deepcopy(self.source))
        monkeypatch.setattr(task, "runtime_identity", lambda *_: copy.deepcopy(self.runtime))
        monkeypatch.setattr(task, "provenance", provenance)
        monkeypatch.setattr(task.subprocess, "Popen", popen)
        monkeypatch.setattr(task.os, "killpg", lambda pid, sig: self.signals.append((pid, sig)))
        monkeypatch.setattr(verifier, "verify_capture", verify_capture)

    def collect(self):
        return task.collect(self.output, self.archive, self.sdk_python, self.binary)

    def attempts(self):
        return json.loads((self.output / "attempts.json").read_text())

    def assert_owned_cleanup(self):
        assert self.signals == [
            (process.pid, sig)
            for process in self.processes
            for sig in (signal.SIGTERM, signal.SIGKILL)
        ]
        assert all(process.wait_calls == [240, 10] for process in self.processes)


def test_fixed_original_twelve_houses_are_attempted_once_and_reaped(monkeypatch, tmp_path):
    matrix = ControlledMatrix(monkeypatch, tmp_path)
    audit = matrix.collect()
    attempts = matrix.attempts()
    assert [row["index"] for row in attempts] == list(range(1, 13))
    assert [row["split"] for row in attempts] == ["train"] * 8 + ["validation"] * 4
    assert all(row["status"] == "verified" and row["exit_code"] == 0 for row in attempts)
    assert matrix.verifications == list(range(1, 13))
    assert len(matrix.plan_verifications) == 13
    assert audit["complete_twelve_house_runtime_audit"]
    assert audit["complete_asset_exposure_audit"]
    assert audit["training_performed"] is False
    for index, (command, kwargs) in enumerate(matrix.dispatches, start=1):
        assert command[:3] == [sys.executable, str(Path(task.__file__).resolve()), "--one"]
        house = Path(command[command.index("--house") + 1])
        assert house == matrix.output / "plan" / f"houses/house-{index:02d}.json"
        assert json.loads(house.read_text()) == {"original_index": index}
        assert command[command.index("--sdk-python") + 1] == str(matrix.sdk_python)
        assert command[command.index("--binary") + 1] == str(matrix.binary)
        assert kwargs["start_new_session"] is True
        assert kwargs["stderr"] == subprocess.STDOUT
        assert kwargs["stdout"].name == str(matrix.output / f"house-{index:02d}.log")
    matrix.assert_owned_cleanup()


@pytest.mark.parametrize("failure", ["nonzero", "timeout", "verification", "spawn"])
def test_single_failure_is_retained_without_replacement_and_blocks_export(
    monkeypatch, tmp_path, failure
):
    matrix = ControlledMatrix(monkeypatch, tmp_path)
    matrix.failures[4] = failure
    audit = matrix.collect()
    attempts = matrix.attempts()
    assert [row["index"] for row in attempts] == list(range(1, 13))
    assert [
        int(Path(cmd[cmd.index("--output") + 1]).name.split("-")[1]) for cmd, _ in matrix.dispatches
    ] == list(range(1, 13))
    assert attempts[3]["status"] == "failed" and attempts[3]["error"]
    assert all(row["status"] == "verified" for row in attempts if row["index"] != 4)
    assert audit["complete_twelve_house_runtime_audit"] is False
    assert audit["complete_asset_exposure_audit"] is False
    assert audit["supervision_export_performed"] is False
    assert all(not row["eligible"] for row in audit["instances"])
    if failure == "nonzero":
        assert attempts[3]["exit_code"] == 7
    if failure != "verification":
        assert 4 not in matrix.verifications
    matrix.assert_owned_cleanup()


@pytest.mark.parametrize("attack", ["source", "runtime", "provenance"])
def test_matching_zero_exit_cannot_promote_forged_capture_identity(monkeypatch, tmp_path, attack):
    matrix = ControlledMatrix(monkeypatch, tmp_path)
    matrix.identity_attacks[9] = attack
    audit = matrix.collect()
    row = matrix.attempts()[8]
    assert row["exit_code"] == 0 and row["status"] == "failed"
    assert "capture identity differs from frozen matrix" in row["error"]
    assert 9 not in matrix.verifications
    assert len(matrix.attempts()) == 12
    assert audit["complete_asset_exposure_audit"] is False
    matrix.assert_owned_cleanup()


def test_keyboard_interrupt_keeps_failed_attempt_and_reaps_owned_group(monkeypatch, tmp_path):
    matrix = ControlledMatrix(monkeypatch, tmp_path)
    matrix.failures[3] = "interrupt"
    with pytest.raises(KeyboardInterrupt, match="controlled interruption"):
        matrix.collect()
    attempts = matrix.attempts()
    assert [row["index"] for row in attempts] == [1, 2, 3]
    assert attempts[-1]["status"] == "failed"
    assert "KeyboardInterrupt" in attempts[-1]["error"]
    assert attempts[-1]["finished_at"]
    matrix.assert_owned_cleanup()


def test_cleanup_failure_is_saved_and_prevents_next_house(monkeypatch, tmp_path):
    matrix = ControlledMatrix(monkeypatch, tmp_path)

    def uncertain_cleanup(pid, sig):
        matrix.signals.append((pid, sig))
        if pid == 50003:
            raise PermissionError("controlled owned-group cleanup uncertainty")

    monkeypatch.setattr(task.os, "killpg", uncertain_cleanup)
    with pytest.raises(RuntimeError, match="owned process cleanup uncertain; stop matrix"):
        matrix.collect()
    attempts = matrix.attempts()
    assert [row["index"] for row in attempts] == [1, 2, 3]
    assert attempts[-1]["status"] == "cleanup_failed"
    assert "PermissionError" in attempts[-1]["cleanup_error"]
    assert attempts[-1]["finished_at"]
    assert len(matrix.dispatches) == 3
    assert not (matrix.output / "runtime-partition-audit.json").exists()
    assert matrix.signals[-1] == (50003, signal.SIGTERM)
    assert matrix.processes[-1].wait_calls == [240]


@pytest.mark.parametrize("identity", ["source", "runtime"])
def test_frozen_parent_identity_change_stops_before_further_dispatch(
    monkeypatch, tmp_path, identity
):
    matrix = ControlledMatrix(monkeypatch, tmp_path)
    original_verify = verifier.verify_capture

    def changed_after_verification(*args):
        result = original_verify(*args)
        if len(matrix.verifications) == 2:
            if identity == "source":
                matrix.source["src/controlled.py"] = "changed"
            else:
                matrix.runtime["sdk"] = "changed"
        return result

    monkeypatch.setattr(verifier, "verify_capture", changed_after_verification)
    with pytest.raises(ValueError, match="frozen source/runtime changed"):
        matrix.collect()
    assert [row["index"] for row in matrix.attempts()] == [1, 2]
    assert len(matrix.dispatches) == 2
    matrix.assert_owned_cleanup()


def test_missing_owned_group_is_not_replaced_by_broad_process_kill(monkeypatch):
    calls = []

    class Process:
        pid = 57891

        def wait(self, *, timeout):
            calls.append(("wait", timeout))

    def gone(pid, sig):
        calls.append((pid, sig))
        raise ProcessLookupError("owned group already exited")

    monkeypatch.setattr(task.os, "killpg", gone)
    task.stop_owned_group(Process())
    assert calls == [(57891, signal.SIGTERM), ("wait", 10)]


@pytest.mark.parametrize("failed_house", [None, 4])
def test_saved_collection_reconstructs_without_new_capture(monkeypatch, tmp_path, failed_house):
    matrix = ControlledMatrix(monkeypatch, tmp_path)
    if failed_house is not None:
        matrix.failures[failed_house] = "nonzero"
    audit = matrix.collect()
    dispatch_count = len(matrix.dispatches)
    assert (
        task.verify_collection(matrix.output, matrix.archive, matrix.sdk_python, matrix.binary)
        == audit
    )
    assert len(matrix.dispatches) == dispatch_count == 12
    assert audit["complete_twelve_house_runtime_audit"] == (failed_house is None)


@pytest.mark.parametrize("attack", ["partition_summary", "frame_summary", "configuration"])
def test_rehashed_inventory_cannot_make_forged_summary_match_raw_evidence(
    monkeypatch, tmp_path, attack
):
    matrix = ControlledMatrix(monkeypatch, tmp_path)
    matrix.collect()
    if attack == "partition_summary":
        path = matrix.output / "runtime-partition-audit.json"
        value = json.loads(path.read_text())
        value["instances"][0]["eligible"] = False
        match = "saved partition audit differs"
    elif attack == "frame_summary":
        path = matrix.output / "attempts.json"
        value = json.loads(path.read_text())
        value[0]["verification"]["all_assets"].append("forged-new-asset")
        match = "saved verification differs from raw evidence"
    else:
        path = matrix.output / "configuration.json"
        value = json.loads(path.read_text())
        value["runtime"]["sdk"] = "forged-runtime"
        match = "collection identity differs"
    task.write_json(path, value)
    # A complete attacker updates every self-reported file hash after changing the result.
    task.write_json(
        matrix.output / "inventory.json",
        {
            str(p.relative_to(matrix.output)): task.digest(p)
            for p in sorted(matrix.output.rglob("*"))
            if p.is_file() and p.name != "inventory.json"
        },
    )
    with pytest.raises(ValueError, match=match):
        task.verify_collection(matrix.output, matrix.archive, matrix.sdk_python, matrix.binary)
    assert len(matrix.dispatches) == 12


@pytest.mark.parametrize(
    "attack",
    [
        "nonzero_exit",
        "bool_exit",
        "success_with_error",
        "unknown_status",
        "failed_with_verification",
        "no_failure_trace",
        "time_reversal",
        "naive_time",
        "reorder",
    ],
)
def test_fully_rehashed_attempt_state_cannot_promote_contradictory_outcome(
    monkeypatch, tmp_path, attack
):
    matrix = ControlledMatrix(monkeypatch, tmp_path)
    matrix.collect()
    path = matrix.output / "attempts.json"
    rows = json.loads(path.read_text())
    if attack == "nonzero_exit":
        rows[0]["exit_code"] = 7
    elif attack == "bool_exit":
        rows[0]["exit_code"] = False
    elif attack == "success_with_error":
        rows[0]["error"] = "capture failed"
    elif attack == "unknown_status":
        rows[0]["status"] = "passed_anyway"
    elif attack == "failed_with_verification":
        rows[0].update(status="failed", error="failure", traceback="trace")
    elif attack == "no_failure_trace":
        rows[0].update(status="failed", error="failure")
        rows[0].pop("verification")
    elif attack == "time_reversal":
        rows[0]["finished_at"] = "2000-01-01T00:00:00+00:00"
    elif attack == "naive_time":
        rows[0]["started_at"] = "2000-01-01T00:00:00"
    else:
        rows[0], rows[1] = rows[1], rows[0]
    task.write_json(path, rows)
    task.write_json(
        matrix.output / "inventory.json",
        {
            str(p.relative_to(matrix.output)): task.digest(p)
            for p in sorted(matrix.output.rglob("*"))
            if p.is_file() and p.name != "inventory.json"
        },
    )
    with pytest.raises(ValueError, match="attempt state"):
        task.verify_collection(matrix.output, matrix.archive, matrix.sdk_python, matrix.binary)


@pytest.mark.parametrize(
    "attack", ["whole_decade_shift", "decision_before_start", "receive_after_finish"]
)
def test_rehashed_causal_utc_intervals_must_enclose_public_capture(monkeypatch, tmp_path, attack):
    matrix = ControlledMatrix(monkeypatch, tmp_path)
    matrix.collect()
    path = matrix.output / "attempts.json"
    rows = json.loads(path.read_text())
    if attack == "whole_decade_shift":
        for row in rows:
            for key in ("started_at", "finished_at"):
                row[key] = (datetime.fromisoformat(row[key]) - timedelta(days=3650)).isoformat()
    elif attack == "decision_before_start":
        rows[0]["started_at"] = (
            datetime.fromisoformat(rows[0]["verification"]["frame_records"][0]["decision_time"])
            + timedelta(microseconds=1)
        ).isoformat()
    else:
        rows[0]["finished_at"] = (
            datetime.fromisoformat(rows[0]["verification"]["frame_records"][-1]["received_at"])
            - timedelta(microseconds=1)
        ).isoformat()
    task.write_json(path, rows)
    task.write_json(
        matrix.output / "inventory.json",
        {
            str(p.relative_to(matrix.output)): task.digest(p)
            for p in sorted(matrix.output.rglob("*"))
            if p.is_file() and p.name != "inventory.json"
        },
    )
    with pytest.raises(ValueError, match="attempt state"):
        task.verify_collection(matrix.output, matrix.archive, matrix.sdk_python, matrix.binary)


def test_rehashed_entire_archive_cannot_replace_external_capture_pin(monkeypatch, tmp_path):
    matrix = ControlledMatrix(monkeypatch, tmp_path)
    baseline = matrix.collect()
    pin = task.digest(matrix.output / "inventory.json")
    assert (
        task.verify_collection(
            matrix.output, matrix.archive, matrix.sdk_python, matrix.binary, inventory_sha256=pin
        )
        == baseline
    )
    # This test is the external custody boundary; other rehash tests intentionally
    # exercise only structural consistency with a new self-reported inventory.
    path = matrix.output / "house-01.log"
    path.write_text("whole-SDK transcript replaced after capture")
    task.write_json(
        matrix.output / "inventory.json",
        {
            str(p.relative_to(matrix.output)): task.digest(p)
            for p in sorted(matrix.output.rglob("*"))
            if p.is_file() and p.name != "inventory.json"
        },
    )
    with pytest.raises(ValueError, match="trusted external pin"):
        task.verify_collection(
            matrix.output, matrix.archive, matrix.sdk_python, matrix.binary, inventory_sha256=pin
        )
