"""Real CLI checks against complete committed raw-input archives."""

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]


def _archive(tmp_path: Path, *, defect: str | None = None) -> tuple[Path, str]:
    root = tmp_path / "archive"
    raw = root / "case/schedule_run/evaluator_only/raw"
    raw.mkdir(parents=True)
    obs = raw / "observations"
    obs.mkdir()
    journal = []
    for index in range(2):
        data = io.BytesIO()
        np.savez(
            data,
            rgb=np.full((2, 3, 3), index, dtype=np.uint8),
            depth=np.ones((2, 3), dtype=np.float32),
        )
        payload = data.getvalue()
        internal_index = 0 if defect == "duplicate_internal" else index
        receipt = dict(
            run_id="independent-cli-fixture",
            step_index=internal_index,
            request={"action": "Pass"},
            request_time="2026-09-12T00:00:00+00:00",
            received_at="2026-09-12T00:00:01+00:00",
            last_action_success=True,
            sensor_file=f"{internal_index:06d}.npz",
            sensor_sha256=hashlib.sha256(payload).hexdigest(),
            depth_unit="m",
            status="RAW_OBSERVATION_CANDIDATE_NOT_METHOD_AUTHORIZATION",
        )
        if defect == "wrong_sensor_reference" and index == 1:
            receipt["sensor_file"] = "000000.npz"
        if defect == "late_bad_hash" and index == 0:
            receipt["sensor_sha256"] = "0" * 64
        (obs / f"{index:06d}.json").write_text(json.dumps(receipt))
        (obs / f"{index:06d}.npz").write_bytes(payload)
        # Capture zero arrives later. Delayed arrival must retain both identities.
        journal.append(
            dict(
                capture_ref=f"{index:06d}.json",
                event_tick=index,
                received_tick=2 if index == 0 else 1,
            )
        )
    if defect == "duplicate_release":
        journal[1]["capture_ref"] = "000000.json"
    (raw / "manifest.json").write_text(json.dumps({"run_id": "independent-cli-fixture"}))
    candidate = root / "case/schedule_run/observation_candidates"
    candidate.mkdir()
    (candidate / "release_journal.json").write_text(json.dumps(journal))

    def git(*args: str) -> str:
        return subprocess.check_output(["git", *args], cwd=root, text=True).strip()

    git("init", "-q")
    git("add", ".")
    git(
        "-c",
        "user.name=Local regression fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-qm",
        "Complete raw capture fixture",
    )
    return root, git("rev-parse", "HEAD")


def _run(root: Path, sha: str, output: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools/structure_two_rgbd_ingress_replay.py"),
            "--source-root",
            str(root),
            "--source-sha",
            sha,
            "--run-path",
            "case",
            "--output",
            str(output),
        ],
        env=env,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def test_two_real_cli_captures_keep_unique_outputs_and_verifiable_manifest(tmp_path):
    root, sha = _archive(tmp_path)
    output = tmp_path / "out"
    result = _run(root, sha, output)
    assert result.returncode == 0, result.stderr
    receipt = json.loads((output / "receipt.json").read_text())
    assert receipt["selected_capture_count"] == 2
    assert receipt["observation_count"] == 4
    assert [r["capture_ref"] for r in receipt["captures"]] == ["000001.json", "000000.json"]
    rows = receipt["output_manifest"]
    assert len(rows) == len({r["file"] for r in rows}) == 8
    assert len({r["observation_id"] for r in rows}) == 4
    for row in rows:
        actual = (output / row["file"]).read_bytes()
        assert len(actual) == row["size_bytes"]
        assert hashlib.sha256(actual).hexdigest() == row["sha256"]
    assert not receipt["new_simulator_run"] and not receipt["default_joint_runtime_verified"]
    # Retry cannot overwrite the existing published archive.
    before = {p.name: p.read_bytes() for p in (output / "observations").iterdir()}
    assert _run(root, sha, output).returncode != 0
    assert before == {p.name: p.read_bytes() for p in (output / "observations").iterdir()}


@pytest.mark.parametrize(
    "defect", ["duplicate_internal", "wrong_sensor_reference", "duplicate_release", "late_bad_hash"]
)
def test_complete_archival_forgeries_and_partial_failure_do_not_publish_success(tmp_path, defect):
    root, sha = _archive(tmp_path, defect=defect)
    output = tmp_path / "out"
    result = _run(root, sha, output)
    assert result.returncode != 0
    assert not (output / "receipt.json").exists()
    if defect == "duplicate_internal":
        assert "released reference differs from capture identity" in result.stderr


def test_source_sha_must_identify_a_commit(tmp_path):
    root, _ = _archive(tmp_path)
    tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=root, text=True).strip()
    result = _run(root, tree, tmp_path / "out")
    assert result.returncode != 0
    assert "source SHA must name a commit" in result.stderr
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("object_kind", ["commit", "blob"])
def test_git_replacement_cannot_change_bytes_read_under_original_sha(tmp_path, object_kind):
    root, original = _archive(tmp_path)
    journal_path = "case/schedule_run/observation_candidates/release_journal.json"

    def git(*args):
        return subprocess.check_output(["git", *args], cwd=root, text=True).strip()

    old_blob = git("rev-parse", f"{original}:{journal_path}")
    path = root / journal_path
    path.write_text(json.dumps(json.loads(path.read_text())[:1]))
    git("add", journal_path)
    git(
        "-c",
        "user.name=Local regression fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-qm",
        "Different single-capture archive",
    )
    replacement = git("rev-parse", "HEAD")
    new_blob = git("rev-parse", f"{replacement}:{journal_path}")
    if object_kind == "commit":
        git("replace", original, replacement)
    else:
        git("replace", old_blob, new_blob)
    # Demonstrate the complete source alias really exists in ordinary Git reads.
    assert len(json.loads(git("show", f"{original}:{journal_path}"))) == 1
    output = tmp_path / "out"
    result = _run(root, original, output)
    assert result.returncode == 0, result.stderr
    receipt = json.loads((output / "receipt.json").read_text())
    assert receipt["source_sha"] == original
    assert receipt["selected_capture_count"] == 2
    assert receipt["observation_count"] == 4
    assert len(receipt["output_manifest"]) == 8
