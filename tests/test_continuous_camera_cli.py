"""CLI mode selection must not silently start the historical fixed scan."""

import runpy
import subprocess
import sys
from pathlib import Path

import pytest


def test_default_mode_requires_configured_runtime_before_any_file_or_effect(tmp_path):
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "output"
    result = subprocess.run(
        [
            sys.executable,
            str(root / "tools/run_continuous_unity_camera.py"),
            "--sdk-python",
            "/not-started",
            "--binary",
            "/not-started",
            "--weights",
            "/not-read",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "posterior mode requires --runtime-factory" in result.stderr
    assert not output.exists()


def test_transport_probe_rejects_posterior_factory_ambiguity(tmp_path):
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            str(root / "tools/run_continuous_unity_camera.py"),
            "--sdk-python",
            "/not-started",
            "--binary",
            "/not-started",
            "--weights",
            "/not-read",
            "--output",
            str(tmp_path / "output"),
            "--mode",
            "transport-probe",
            "--runtime-factory",
            "not.imported:factory",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "transport-probe does not accept" in result.stderr
    assert not (tmp_path / "output").exists()


def test_runtime_factory_is_resolved_inside_source_tree_before_import():
    root = Path(__file__).resolve().parents[1]
    loader = runpy.run_path(str(root / "tools/run_continuous_unity_camera.py"))[
        "load_runtime_factory"
    ]
    with pytest.raises(ValueError, match="before import"):
        loader("os:system", root)
    with pytest.raises(ValueError, match="does not exist"):
        loader("cpswm.nonexistent_factory:create", root)
    assert callable(
        loader("cpswm.system.continuous_camera_collection:collect_posterior_step", root)
    )
