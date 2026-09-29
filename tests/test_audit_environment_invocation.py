"""Real interpreter contexts and complete environment-fingerprint forgeries."""

from __future__ import annotations

import copy
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import subprocess
import sys
import venv
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "apps/evaluation_runner" / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


AUDIT = _load("invocation_audit", "run_structure_two_engineering_audit_receipt.py")
MANIFEST = _load("invocation_manifest", "generate_p0_checkpoint_manifest.py")


@pytest.fixture
def empty_environment(tmp_path):
    environment = tmp_path / ".venv"
    venv.EnvBuilder(with_pip=False, symlinks=os.name != "nt").create(environment)
    return tmp_path, environment


@pytest.mark.parametrize("alias", ["python", "python3"])
def test_real_version_command_keeps_virtual_environment(empty_environment, alias):
    root, environment = empty_environment
    entry = environment / ("Scripts/python.exe" if os.name == "nt" else f"bin/{alias}")
    argv = (str(entry.relative_to(root)), "-I", "-c", "import sys;print(sys.prefix)")
    result = AUDIT._tool_version(argv, repository_root=root)
    assert Path(result["version"]).resolve() == environment.resolve()
    assert result["invocation_executable"] == str(entry)
    assert result["resolved_executable"] == str(entry.resolve())
    assert result["executable_sha256"] == hashlib.sha256(entry.resolve().read_bytes()).hexdigest()
    assert result["version_argv"] == list(argv)


def test_actual_pytest_version_comes_from_project_environment():
    result = AUDIT._tool_version(
        AUDIT.TOOL_VERSION_COMMANDS["pytest"],
        environment_overrides=AUDIT.PYTEST_ENVIRONMENT_OVERRIDES,
    )
    assert result["version"] == "pytest " + importlib.metadata.version("pytest")
    assert Path(result["invocation_executable"]).parent.parent == ROOT / ".venv"
    assert Path(result["resolved_executable"]) == Path(sys.executable).resolve()


def test_missing_module_cannot_fall_back_to_base_environment(empty_environment):
    root, environment = empty_environment
    entry = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    with pytest.raises(subprocess.CalledProcessError) as caught:
        AUDIT._tool_version((str(entry), "-I", "-m", "pytest", "--version"), repository_root=root)
    assert caught.value.returncode != 0
    assert caught.value.cmd[0] == str(entry)
    assert b"No module named pytest" in caught.value.stderr


def test_nonzero_version_command_is_preserved(empty_environment):
    root, environment = empty_environment
    entry = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    with pytest.raises(subprocess.CalledProcessError) as caught:
        AUDIT._tool_version((str(entry), "-I", "-c", "raise SystemExit(17)"), repository_root=root)
    assert caught.value.returncode == 17
    assert caught.value.cmd[0] == str(entry)


@pytest.fixture(scope="module")
def current_manifest():
    # A current in-memory input tests this component. It does not replace the
    # stale P0 file or grant any checkpoint/audit acceptance to this source.
    path = ROOT / "benchmarks/p0_checkpoint/content_manifest_v0_3.json"
    original = path.read_bytes()
    current = MANIFEST.build_manifest(repository_root=ROOT)
    yield current
    assert path.read_bytes() == original


def test_real_fingerprint_recomputes_and_python_alias_is_stable(current_manifest, monkeypatch):
    fingerprint = AUDIT.build_execution_environment_fingerprint(current_manifest)
    AUDIT.verify_execution_environment_fingerprint(fingerprint, current_manifest)
    alias = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python3")
    monkeypatch.setattr(sys, "executable", str(alias))
    assert AUDIT.build_execution_environment_fingerprint(current_manifest) == fingerprint


def test_effective_environment_change_is_still_detected(current_manifest, monkeypatch, tmp_path):
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    fingerprint = AUDIT.build_execution_environment_fingerprint(current_manifest)
    monkeypatch.setenv("VIRTUAL_ENV", sys.prefix)
    assert AUDIT.build_execution_environment_fingerprint(current_manifest) == fingerprint
    monkeypatch.setenv("VIRTUAL_ENV", str(tmp_path / "different-environment"))
    with pytest.raises(ValueError, match="fingerprint is stale"):
        AUDIT.verify_execution_environment_fingerprint(fingerprint, current_manifest)


@pytest.mark.parametrize("attack", ["reported_version", "invocation"])
def test_complete_resealed_fingerprint_still_requires_actual_execution(current_manifest, attack):
    original = AUDIT.build_execution_environment_fingerprint(current_manifest)
    forged = copy.deepcopy(original)
    tool = forged["tools"]["pytest"]
    if attack == "reported_version":
        tool["version"] = "pytest 0.0-forged"
        tool["version_output_sha256"] = hashlib.sha256(b"pytest 0.0-forged\n").hexdigest()
    else:
        tool["invocation_executable"] = tool["resolved_executable"]
        tool["version_argv"][0] = tool["resolved_executable"]
    forged["content_sha256"] = AUDIT._canonical_sha256(
        {key: value for key, value in forged.items() if key != "content_sha256"}
    )
    # Retain the complete forged JSON through the same serialization boundary.
    forged = json.loads(json.dumps(forged))
    with pytest.raises(ValueError, match="fingerprint is stale"):
        AUDIT.verify_execution_environment_fingerprint(forged, current_manifest)
