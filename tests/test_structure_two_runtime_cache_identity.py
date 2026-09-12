"""Real cache execution attacks; no observation/JUnit forgery or cache disabling."""

from __future__ import annotations

import importlib.util
import json
import marshal
import os
import py_compile
import shutil
import subprocess
import uuid
from dataclasses import replace
from pathlib import Path

import pytest
from test_structure_two_unified_acceptance import ROOT, coordinator, state
from test_structure_two_unified_dependencies import execute, prepare
from test_structure_two_unified_dependencies import runtime_tree as runtime_tree


def seed_cache(path, fresh, stale, mode):
    assert len(fresh) == len(stale)
    path.write_text(stale)
    stamp = path.stat().st_mtime_ns
    py_compile.compile(str(path), doraise=True, invalidation_mode=mode)
    path.write_text(fresh)
    os.utime(path, ns=(stamp, stamp))
    return Path(importlib.util.cache_from_source(str(path)))


@pytest.mark.parametrize("workers", [False, True])
@pytest.mark.parametrize(
    "mode",
    [py_compile.PycInvalidationMode.TIMESTAMP, py_compile.PycInvalidationMode.UNCHECKED_HASH],
)
@pytest.mark.parametrize("location", ["project", "helper"])
def test_real_old_local_cache_never_completes(runtime_tree, workers, mode, location):
    root = runtime_tree
    name = "dependency_" + uuid.uuid4().hex
    path = root / ("src/cpswm/" + name + ".py" if location == "project" else name + ".py")
    import_line = "from cpswm import " + name if location == "project" else "import " + name
    fresh, stale = "VALUE = 1\n", "VALUE = 9\n"
    code = f"def test_live():\n {import_line}\n assert {name}.VALUE == 9\n"
    cache = seed_cache(path, fresh, stale, mode)
    cached_bytes = cache.read_bytes()
    journal, stage = prepare(root, code)
    if workers:
        stage = replace(stage, argv=(*stage.argv, "-n", "2"))
    with pytest.raises(ValueError):
        execute(root, journal, stage)
    assert state(journal)["status"] == "FAILED"
    observed = "".join(p.read_text() for p in journal.path.rglob("*.reject.json"))
    assert "EXECUTED_LOCAL_CODE_MISMATCH" in observed
    assert cache.read_bytes() == cached_bytes
    assert path.read_text() == fresh


@pytest.mark.parametrize("workers", [False, True])
def test_real_pytest_rewrite_cache_is_compared_to_current_assertions(runtime_tree, workers):
    root = runtime_tree
    journal, stage = prepare(root, "def test_live():\n assert 1 == 1\n")
    path = root / stage.test_nodes[0]
    stamp = path.stat().st_mtime_ns
    if workers:
        stage = replace(stage, argv=(*stage.argv, "-n", "2"))
    execute(root, journal, stage)
    caches = list(path.parent.glob("__pycache__/" + path.stem + ".*pytest*.pyc"))
    assert caches  # Real rewriting remains enabled and creates a real cache.
    old = {str(p): p.read_bytes() for p in caches}
    path.write_text("def test_live():\n assert 1 == 9\n")
    os.utime(path, ns=(stamp, stamp))
    frozen_sha = coordinator.source_snapshot(root)["files"][stage.test_nodes[0]]
    bad = coordinator.Journal(root / coordinator.RUN_AREA / ("rewrite_" + uuid.uuid4().hex))
    bad_stage = coordinator.matrix_stage(root, bad, "matrix", stage.test_nodes)
    if workers:
        bad_stage = replace(bad_stage, argv=(*bad_stage.argv, "-n", "2"))
    with pytest.raises(ValueError):
        execute(root, bad, bad_stage)
    assert "EXECUTED_LOCAL_CODE_MISMATCH" in "".join(
        p.read_text() for p in bad.path.rglob("*.reject.json")
    )
    assert all(Path(p).read_bytes() == value for p, value in old.items())
    # Independent clean-cache negative with the exact same source hash.
    for p in caches:
        p.unlink()
    clean = coordinator.Journal(
        root / coordinator.RUN_AREA / ("fresh_negative_" + uuid.uuid4().hex)
    )
    clean_stage = coordinator.matrix_stage(root, clean, "matrix", stage.test_nodes)
    with pytest.raises(ValueError):
        execute(root, clean, clean_stage)
    assert coordinator.source_snapshot(root)["files"][stage.test_nodes[0]] == frozen_sha
    assert "assert 1 == 9" in (clean.path / "matrix.stdout.log").read_text()


@pytest.mark.parametrize(
    "mode",
    [py_compile.PycInvalidationMode.TIMESTAMP, py_compile.PycInvalidationMode.UNCHECKED_HASH],
)
def test_legal_existing_project_and_helper_cache_still_runs(runtime_tree, mode):
    root = runtime_tree
    name = "legal_" + uuid.uuid4().hex
    path = root / "src/cpswm" / (name + ".py")
    seed_cache(path, "VALUE = 7\n", "VALUE = 7\n", mode)
    journal, stage = prepare(
        root, f"def test_live():\n from cpswm import {name}\n assert {name}.VALUE == 7\n"
    )
    execute(root, journal, replace(stage, argv=(*stage.argv, "-n", "2")))
    records = state(journal)["stages"][0]["test_runtime"]["processes"]
    assert len(records) == 3
    assert any(str(path) in p["executed_local_sources"] for p in records)


def test_caught_bad_import_cannot_erase_execution_rejection(runtime_tree):
    root = runtime_tree
    path = root / "src/cpswm/caught_bad_cache.py"
    seed_cache(path, "VALUE = 1\n", "VALUE = 9\n", py_compile.PycInvalidationMode.TIMESTAMP)
    journal, stage = prepare(
        root,
        "def test_live():\n try:\n  import cpswm.caught_bad_cache\n"
        " except BaseException:\n  pass\n assert True\n",
    )
    with pytest.raises(ValueError):
        execute(root, journal, stage)
    assert state(journal)["status"] == "FAILED"
    assert list(journal.path.rglob("*.code.reject.json"))


@pytest.mark.parametrize("command_id", ["p0_adversarial_tests", "core_pytest"])
def test_real_nested_audit_launcher_positive_and_cached_negative(tmp_path, command_id):
    """Actual public nested command; minimal test payload, explicitly not global audit."""
    root = tmp_path / "native"
    shutil.copytree(ROOT / ".venv", root / ".venv", symlinks=True)
    for directory in ("tools", "apps/evaluation_runner", "tests", "src/cpswm"):
        (root / directory).mkdir(parents=True, exist_ok=True)
    for name in ("structure_two_unified_acceptance.py", "structure_two_pytest_runtime.py"):
        shutil.copy2(ROOT / "tools" / name, root / "tools" / name)
    audit = "apps/evaluation_runner/run_structure_two_engineering_audit_receipt.py"
    shutil.copy2(ROOT / audit, root / audit)
    (root / "src/cpswm/__init__.py").write_text("VALUE = 7\n")
    (root / "pyproject.toml").write_text('[tool.pytest.ini_options]\npythonpath = ["src"]\n')
    (root / ".gitignore").write_text(".venv/\n__pycache__/\n.pytest_cache/\n")
    namespace = {}
    exec(
        compile((root / audit).read_bytes(), str(root / audit), "exec"),
        {"__file__": str(root / audit), "__name__": "fixture_audit"},
        namespace,
    )
    for name in namespace["NATIVE_PYTEST_ARGUMENTS"]["p0_adversarial_tests"]:
        if name.startswith("tests/"):
            (root / name).write_text("def test_live():\n assert 1 == 1\n")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "Minimal nested fixture",
        ],
        check=True,
    )
    env = {
        **os.environ,
        **namespace["PYTEST_ENVIRONMENT_OVERRIDES"],
        "PYTEST_XDIST_AUTO_NUM_WORKERS": "2",
    }
    argv = [str(root / ".venv/bin/python"), *namespace["COMMANDS"][command_id][1:]]
    positive = subprocess.run(argv, cwd=root, env=env, capture_output=True, text=True)
    assert positive.returncode == 0, positive.stdout + positive.stderr
    test = root / "tests/test_p0_checkpoint_manifest.py"
    stamp = test.stat().st_mtime_ns
    test.write_text("def test_live():\n assert 1 == 9\n")
    os.utime(test, ns=(stamp, stamp))
    negative = subprocess.run(argv, cwd=root, env=env, capture_output=True, text=True)
    assert negative.returncode != 0
    journals = [
        json.loads(p.read_text()) for p in (root / coordinator.RUN_AREA).glob("*/state.json")
    ]
    assert sorted(d["status"] for d in journals) == ["FAILED", "STAGES_COMPLETED_NOT_AUTHORIZATION"]
    print(
        json.dumps(
            {
                "root": str(root),
                "argv": argv,
                "positive_stdout": positive.stdout,
                "negative_stderr": negative.stderr,
            }
        )
    )


@pytest.mark.parametrize("workers", [False, True])
def test_real_conftest_rewrite_cache_cannot_change_fixture_behavior(runtime_tree, workers):
    root = runtime_tree
    conftest = root / "tests/conftest.py"
    conftest.write_text("import pytest\n@pytest.fixture\ndef value():\n return 9\n")
    stamp = conftest.stat().st_mtime_ns
    try:
        journal, stage = prepare(root, "def test_live(value):\n assert value == 9\n")
        if workers:
            stage = replace(stage, argv=(*stage.argv, "-n", "2"))
        execute(root, journal, stage)
        caches = list(conftest.parent.glob("__pycache__/conftest.*pytest*.pyc"))
        assert caches
        original = {str(p): p.read_bytes() for p in caches}
        conftest.write_text("import pytest\n@pytest.fixture\ndef value():\n return 1\n")
        os.utime(conftest, ns=(stamp, stamp))
        bad = coordinator.Journal(root / coordinator.RUN_AREA / ("conftest_" + uuid.uuid4().hex))
        bad_stage = coordinator.matrix_stage(root, bad, "matrix", stage.test_nodes)
        if workers:
            bad_stage = replace(bad_stage, argv=(*bad_stage.argv, "-n", "2"))
        with pytest.raises(ValueError):
            execute(root, bad, bad_stage)
        assert "EXECUTED_LOCAL_CODE_MISMATCH" in "".join(
            p.read_text() for p in bad.path.rglob("*.reject.json")
        )
        assert all(Path(p).read_bytes() == raw for p, raw in original.items())
    finally:
        conftest.unlink()


def test_rewrite_cache_cannot_hide_its_filename_outside_bound_sources(runtime_tree):
    root = runtime_tree
    journal, stage = prepare(root, "def test_live():\n assert 1 == 1\n")
    execute(root, journal, stage)
    path = root / stage.test_nodes[0]
    cache = next(path.parent.glob("__pycache__/" + path.stem + ".*pytest*.pyc"))
    raw = cache.read_bytes()
    code = marshal.loads(raw[16:]).replace(co_filename="/private/tmp/foreign_test_identity.py")
    cache.write_bytes(raw[:16] + marshal.dumps(code))
    bad = coordinator.Journal(
        root / coordinator.RUN_AREA / ("foreign_code_path_" + uuid.uuid4().hex)
    )
    with pytest.raises(ValueError):
        execute(root, bad, coordinator.matrix_stage(root, bad, "matrix", stage.test_nodes))
    assert "WITHOUT" in "".join(p.read_text() for p in bad.path.rglob("*.reject.json"))


def test_bad_cache_in_background_thread_cannot_be_hidden(runtime_tree):
    root = runtime_tree
    path = root / "src/cpswm/thread_bad_cache.py"
    seed_cache(path, "VALUE = 1\n", "VALUE = 9\n", py_compile.PycInvalidationMode.UNCHECKED_HASH)
    journal, stage = prepare(
        root,
        """def test_live():
 import threading
 def work():
  try:
   import cpswm.thread_bad_cache
  except BaseException:
   pass
 thread = threading.Thread(target=work)
 thread.start()
 thread.join()
 assert True
""",
    )
    with pytest.raises(ValueError):
        execute(root, journal, stage)
    assert list(journal.path.rglob("*.code.reject.json"))
