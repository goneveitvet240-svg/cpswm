"""Real-process regression tests for v0.1/v0.2 CLI compatibility and output safety."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from shutil import copy2, copytree

from cpswm.system.evaluation_operations.project_one_ablation_pilot import (
    ProjectOneProtocolPilotReport,
)
from cpswm.system.evaluation_operations.project_one_ablation_v0_2 import (
    ProjectOneProtocolPilotReportV2,
)
from cpswm.system.evaluation_operations.report_output import (
    ProtectedReportOutputError,
    write_report_atomic,
)

REPO = Path(__file__).resolve().parents[1]
V01_CLI = REPO / "apps/evaluation_runner/run_project_one_ablation_pilot.py"
V02_CLI = REPO / "apps/evaluation_runner/run_project_one_ablation_pilot_v0_2.py"
V01_CONFIG = REPO / "benchmarks/project_one_ablation/project_one_protocol_pilot_v0.1.json"
V02_CONFIG = REPO / "benchmarks/project_one_ablation/project_one_protocol_pilot_v0.2.json"
V01_FIXTURE = (
    REPO / "benchmarks/project_one_ablation/project_one_protocol_pilot_report_v0.1.fixture.json"
)


def _run(*args: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *(str(arg) for arg in args)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )


def test_v02_cli_refuses_output_equal_to_config_and_preserves_bytes(tmp_path):
    config = tmp_path / "v0.2.json"
    original = V02_CONFIG.read_bytes()
    config.write_bytes(original)

    completed = _run(V02_CLI, "--config", config, "--output", config)

    assert completed.returncode != 0
    assert "must not equal" in completed.stderr
    assert config.read_bytes() == original


def test_v02_cli_refuses_existing_output_unless_force_and_publishes_atomically(tmp_path):
    output = tmp_path / "report.json"
    output.write_text("sentinel", encoding="utf-8")

    refused = _run(V02_CLI, "--config", V02_CONFIG, "--output", output)
    assert refused.returncode != 0
    assert output.read_text(encoding="utf-8") == "sentinel"

    completed = _run(V02_CLI, "--config", V02_CONFIG, "--output", output, "--force")
    assert completed.returncode == 0, completed.stderr
    ProjectOneProtocolPilotReportV2.model_validate_json(output.read_text(encoding="utf-8"))
    assert not tuple(tmp_path.glob(".report.json.*.tmp"))


def test_report_writer_rejects_any_benchmark_output(tmp_path):
    repository = tmp_path / "repository"
    config = repository / "config.json"
    protected = repository / "benchmarks/project/report.fixture.json"
    config.parent.mkdir(parents=True)
    config.write_text("{}", encoding="utf-8")

    try:
        write_report_atomic(
            "{}\n",
            output_path=protected,
            config_path=config,
            repository_root=repository,
        )
    except ProtectedReportOutputError as exc:
        assert "only under output/" in str(exc)
    else:
        raise AssertionError("benchmark output was not protected")
    assert not protected.exists()


def test_force_cannot_overwrite_repository_pyproject(tmp_path):
    repository = tmp_path / "repository"
    config = tmp_path / "config.json"
    protected = repository / "pyproject.toml"
    repository.mkdir()
    config.write_text("{}", encoding="utf-8")
    protected.write_text("sentinel-project-config", encoding="utf-8")

    try:
        write_report_atomic(
            "{}\n",
            output_path=protected,
            config_path=config,
            repository_root=repository,
            force=True,
        )
    except ProtectedReportOutputError as exc:
        assert "only under output/" in str(exc)
    else:
        raise AssertionError("--force expanded the allowed repository output root")
    assert protected.read_text(encoding="utf-8") == "sentinel-project-config"


def test_v02_cli_force_refuses_repository_pyproject_in_subprocess(tmp_path):
    repository = tmp_path / "repository"
    copied_cli = repository / "apps/evaluation_runner/run_project_one_ablation_pilot_v0_2.py"
    copied_cli.parent.mkdir(parents=True)
    copy2(V02_CLI, copied_cli)
    copytree(REPO / "src", repository / "src")
    protected = repository / "pyproject.toml"
    protected.write_text("sentinel-project-config", encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            str(copied_cli),
            "--config",
            str(V02_CONFIG),
            "--output",
            str(protected),
            "--force",
        ],
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "only under output/" in completed.stderr
    assert protected.read_text(encoding="utf-8") == "sentinel-project-config"


def test_v01_cli_is_retained_and_regenerates_authoritative_fixture(tmp_path):
    output = tmp_path / "v0.1-report.json"

    completed = _run(V01_CLI, "--config", V01_CONFIG, "--output", output)

    assert completed.returncode == 0, completed.stderr
    regenerated = ProjectOneProtocolPilotReport.model_validate_json(
        output.read_text(encoding="utf-8")
    )
    authoritative = ProjectOneProtocolPilotReport.model_validate_json(
        V01_FIXTURE.read_text(encoding="utf-8")
    )
    assert regenerated == authoritative
    assert output.read_bytes() == V01_FIXTURE.read_bytes()
