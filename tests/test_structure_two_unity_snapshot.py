"""Input recorder unit checks only; these do not emulate or certify Unity execution."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[1] / "tools/structure_two_unity_snapshot.py"
SPEC = importlib.util.spec_from_file_location("unity_snapshot", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "source"
    for name in ("Assets", "Packages", "ProjectSettings", "Library"):
        (root / "unity" / name).mkdir(parents=True)
    (root / "unity/Assets/real.txt").write_text("input")
    (root / "unity/Library/private.log").write_text("must not be captured")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "add", "unity/Assets/real.txt"], cwd=root, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
        cwd=root,
        check=True,
    )
    return root


def test_generated_inputs_included_and_cache_excluded(source):
    generated = source / "unity/Assets/generated.mat"
    generated.write_text("generated material")
    result = MODULE.snapshot(source)
    assert result["file_count"] == 2
    assert "unity/Assets/generated.mat" in result["files"]
    assert all("Library" not in path for path in result["files"])
    assert result["snapshot_is_not_runtime_acceptance"] is True
    assert len(result["revision"]) == 40


@pytest.mark.parametrize("root_name", ["Assets", "Packages", "ProjectSettings"])
def test_missing_root_rejected(source, root_name):
    root = source / "unity" / root_name
    root.rename(source / f"moved-{root_name}")
    with pytest.raises(ValueError, match="Missing"):
        MODULE.snapshot(source)


@pytest.mark.parametrize("directory", [False, True])
def test_symlink_input_rejected(source, directory):
    target = source / "unity/Library" if directory else source / "unity/Library/private.log"
    (source / "unity/Assets/link").symlink_to(target, target_is_directory=directory)
    with pytest.raises(ValueError, match="Symlinked"):
        MODULE.snapshot(source)


def test_mutated_input_rejected(source, monkeypatch):
    digest = MODULE.sha256

    def mutate(path):
        value = digest(path)
        path.write_text("mutated while hashing")
        return value

    monkeypatch.setattr(MODULE, "sha256", mutate)
    with pytest.raises(RuntimeError, match="changed during"):
        MODULE.snapshot(source)


def test_cli_fresh_output_and_no_overwrite(source, tmp_path):
    output = tmp_path / "snapshot.json"
    command = [sys.executable, str(TOOL), "--source", str(source), "--output", str(output)]
    first = subprocess.run(command, capture_output=True, text=True)
    assert first.returncode == 0, first.stderr
    saved = output.read_bytes()
    assert json.loads(saved)["file_count"] == 1
    second = subprocess.run(command, capture_output=True, text=True)
    assert second.returncode != 0
    assert output.read_bytes() == saved


def test_cli_output_inside_source_rejected(source):
    output = source / "unity/Assets/snapshot.json"
    result = subprocess.run(
        [sys.executable, str(TOOL), "--source", str(source), "--output", str(output)],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert not output.exists()
