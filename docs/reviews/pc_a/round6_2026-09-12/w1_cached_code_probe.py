"""Real coordinator subprocesses, original project source, stale cache controls.

Only creates disposable checkout fixtures. Does not patch runtime/coordinator,
interpreter, pytest, tests in delivered windows, or live process observations.
This probes direct matrix source identity, not scientific authorization.
"""

import hashlib
import importlib
import json
import os
import py_compile
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DELIVERED = Path(sys.argv[1]).resolve()
OUTPUT = Path(sys.argv[2]).resolve()
root = Path(tempfile.mkdtemp(prefix="cpswm-review6-cache-", dir="/private/tmp"))
shutil.copytree(DELIVERED / ".venv", root / ".venv", symlinks=True)
shutil.copytree(
    DELIVERED / "src", root / "src", ignore=shutil.ignore_patterns("__pycache__", "*.egg-info")
)
(root / "tools").mkdir()
for name in ("structure_two_unified_acceptance.py", "structure_two_pytest_runtime.py"):
    shutil.copy2(DELIVERED / "tools" / name, root / "tools" / name)
(root / "tests").mkdir()
(root / "pyproject.toml").write_text('[tool.pytest.ini_options]\npythonpath = ["src"]\n')
(root / ".gitignore").write_text(".venv/\n__pycache__/\n.pytest_cache/\n")
source = root / "src/cpswm/__init__.py"
original = source.read_bytes()
assert b'"0.1.0"' in original
stale = original.replace(b'"0.1.0"', b'"9.9.9"')
assert len(original) == len(stale)
test = root / "tests/test_cached_source.py"
test.write_text('def test_version():\n import cpswm\n assert cpswm.__version__ == "0.1.0"\n')
subprocess.run(["git", "init", "-q", str(root)], check=True)
subprocess.run(["git", "-C", str(root), "add", "."], check=True)
subprocess.run(
    [
        "git",
        "-C",
        str(root),
        "-c",
        "user.name=Audit fixture",
        "-c",
        "user.email=audit@example.invalid",
        "commit",
        "-qm",
        "Exact project source cache fixture",
    ],
    check=True,
)
sys.path.insert(0, str(root))
m = importlib.import_module("tools.structure_two_unified_acceptance")
rows = []
for label, cache_mode, expected in (
    ("clean_positive", None, "0.1.0"),
    ("unchecked_stale", py_compile.PycInvalidationMode.UNCHECKED_HASH, "9.9.9"),
    ("timestamp_stale", py_compile.PycInvalidationMode.TIMESTAMP, "9.9.9"),
    ("clean_negative", None, "9.9.9"),
):
    cache = Path(importlib.util.cache_from_source(str(source)))
    cache.unlink(missing_ok=True)
    if cache_mode is not None:
        source.write_bytes(stale)
        timestamp = source.stat().st_mtime_ns
        py_compile.compile(str(source), doraise=True, invalidation_mode=cache_mode)
        source.write_bytes(original)
        os.utime(source, ns=(timestamp, timestamp))
    assert source.read_bytes() == original
    test.write_text(
        f"def test_version():\n import cpswm\n assert cpswm.__version__ == {expected!r}\n"
    )
    journal = m.Journal(root / m.RUN_AREA / label)
    stage = m.matrix_stage(root, journal, "matrix", ("tests/test_cached_source.py",))
    frozen = m.source_snapshot(root)
    environment = m.execution_environment(root)
    error = None
    try:
        m.run_stages(root, journal, [stage], frozen, (), environment=environment)
    except ValueError as exc:
        error = str(exc)
    state = json.loads((journal.path / "state.json").read_text())
    row = {
        "case": label,
        "expected_loaded_version": expected,
        "fresh_source_version": "0.1.0",
        "source_sha256": hashlib.sha256(original).hexdigest(),
        "status": state["status"],
        "error": error,
        "journal": str(journal.path),
        "source_unchanged": m.source_snapshot(root) == frozen,
        "stage": state["stages"][0],
    }
    rows.append(row)
    print(json.dumps({k: v for k, v in row.items() if k != "stage"}), flush=True)
    shutil.copytree(journal.path, OUTPUT / ("cache_" + label))
result = {"fixture_root": str(root), "delivered_source": str(DELIVERED), "rows": rows}
(OUTPUT / "w1_cache_results.json").write_text(json.dumps(result, indent=2) + "\n")
assert rows[0]["error"] is None
assert rows[3]["error"] is not None
