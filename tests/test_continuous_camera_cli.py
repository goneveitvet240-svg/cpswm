"""CLI mode selection must not silently start the historical fixed scan."""

import subprocess
import sys
from pathlib import Path


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
