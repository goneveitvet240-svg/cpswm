from __future__ import annotations

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CHECK_SCRIPT = REPOSITORY_ROOT / "check.sh"


def test_check_script_does_not_depend_on_user_uv_cache() -> None:
    source = CHECK_SCRIPT.read_text(encoding="utf-8")

    assert 'UV_CACHE_DIR="$(pwd)/.checkout/uv-cache"' in source
    assert "export UV_CACHE_DIR" in source
    assert ".venv/bin/pytest" in source
    assert ".venv/bin/mypy" in source
    assert ".venv/bin/ruff" in source
    assert "${HOME}" not in source
    assert "$HOME" not in source
    assert "~/.cache" not in source


def test_check_script_propagates_every_quality_gate_failure() -> None:
    source = CHECK_SCRIPT.read_text(encoding="utf-8")

    for status in ("PYTEST_RC", "MYPY_RC", "RUFF_RC", "RUFF_FORMAT_RC"):
        assert f"{status}=$?" in source
    assert (
        "if (( PYTEST_RC != 0 || MYPY_RC != 0 || RUFF_RC != 0 || RUFF_FORMAT_RC != 0 )); then"
    ) in source
