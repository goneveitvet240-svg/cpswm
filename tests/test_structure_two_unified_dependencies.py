"""Actual pytest process/worker regressions for the local acceptance coordinator.

Minimal checkout fixtures exercise the production matrix launch and observation
implementation. They are not unified-source or scientific acceptance runs.
The full real Window-2 producer/consumer run is retained with the R5 delivery.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import uuid
from dataclasses import replace
from pathlib import Path

import pytest
from test_structure_two_unified_acceptance import ROOT, coordinator, state


@pytest.fixture(scope="module")
def runtime_tree(tmp_path_factory):
    root = tmp_path_factory.mktemp("actual_pytest_checkout").resolve()
    shutil.copytree(ROOT / ".venv", root / ".venv", symlinks=True)
    (root / ".gitignore").write_text(".venv/\n__pycache__/\n.pytest_cache/\n")
    (root / "tools").mkdir()
    for name in ("structure_two_unified_acceptance.py", "structure_two_pytest_runtime.py"):
        shutil.copy2(ROOT / "tools" / name, root / "tools" / name)
    (root / "src/cpswm").mkdir(parents=True)
    (root / "src/cpswm/__init__.py").write_text("VALUE = 7\n")
    (root / "tests").mkdir()
    (root / "pyproject.toml").write_text('[tool.pytest.ini_options]\npythonpath = ["src"]\n')
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Local test fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "Minimal runtime fixture",
        ],
        check=True,
        capture_output=True,
    )
    return root


def prepare(root, code, *, required_nodes=()):
    name = "test_fixture_" + uuid.uuid4().hex
    test = "tests/" + name + ".py"
    (root / test).write_text(code)
    journal = coordinator.Journal(root / coordinator.RUN_AREA / name)
    stage = coordinator.matrix_stage(
        root, journal, "matrix", (test,), required_nodes=required_nodes
    )
    return journal, stage


def execute(root, journal, stage, *, extra_stages=()):
    frozen = coordinator.source_snapshot(root)
    environment = coordinator.execution_environment(root)
    try:
        coordinator.run_stages(
            root, journal, (stage, *extra_stages), frozen, (), environment=environment
        )
    finally:
        print(
            json.dumps({"journal": str(journal.path), "status": state(journal)["status"]}),
            flush=True,
        )


def test_copied_venv_old_shebang_is_not_used_by_real_matrix(runtime_tree):
    root = runtime_tree
    shebang = (root / ".venv/bin/pytest").read_text().splitlines()[0]
    assert str(ROOT / ".venv/bin/python") in shebang
    journal, stage = prepare(root, "def test_live():\n import cpswm\n assert cpswm.VALUE == 7\n")
    execute(root, journal, stage)
    row = state(journal)["stages"][0]
    assert row["argv"][:3] == [str(root / ".venv/bin/python"), "-m", "pytest"]
    record = row["test_runtime"]["processes"][0]
    assert record["pid"] == row["pid"]
    assert record["executable"] == str(root / ".venv/bin/python")
    assert record["modules"]["cpswm"]["path"] == str(root / "src/cpswm/__init__.py")
    assert record["modules"]["pytest"]["path"].startswith(str(root / ".venv/"))
    assert row["pytest_counts"] == {"total": 1, "failure": 0, "error": 0, "skipped": 0}


def test_actual_xdist_workers_use_matching_interpreter_and_modules(runtime_tree):
    journal, stage = prepare(
        runtime_tree,
        "import pytest\n@pytest.mark.parametrize('n', range(4))\n"
        "def test_live(n):\n import cpswm\n assert cpswm.VALUE == 7\n",
    )
    stage = replace(stage, argv=(*stage.argv, "-n", "2"))
    execute(runtime_tree, journal, stage)
    processes = state(journal)["stages"][0]["test_runtime"]["processes"]
    assert {r["worker"] for r in processes} == {"controller", "gw0", "gw1"}
    assert len({r["pid"] for r in processes}) == 3
    assert all(r["executable"] == str(runtime_tree / ".venv/bin/python") for r in processes)
    assert all("cpswm" in r["modules"] for r in processes if r["worker"] != "controller")


def test_actual_foreign_worker_interpreter_refused(runtime_tree):
    journal, stage = prepare(runtime_tree, "def test_live():\n assert True\n")
    stage = replace(
        stage, argv=(*stage.argv, "--dist=load", "--tx=popen//python=" + sys.executable)
    )
    with pytest.raises(ValueError, match=r"STAGE_FAILED|ACTUAL_TEST_RUNTIME_REJECTED"):
        execute(runtime_tree, journal, stage)
    logs = (journal.path / "matrix.stdout.log").read_text() + (
        journal.path / "matrix.stderr.log"
    ).read_text()
    # Coordinator may stop xdist before its buffered stderr is flushed. The
    # worker's exclusive failure observation carries the actual rejection.
    observed = state(journal)["stages"][0].get("runtime_rejections", [])
    assert "ACTUAL_TEST_INTERPRETER_MISMATCH" in logs + json.dumps(observed)
    assert state(journal)["status"] == "FAILED"


@pytest.mark.parametrize("module", ["cpswm", "pytest"])
def test_real_foreign_module_loaded_during_test_refused_before_completion(
    runtime_tree, tmp_path, module
):
    foreign = tmp_path / (module + ".py")
    foreign.write_text("VALUE = 99\n")
    code = f"""def test_foreign():
 import importlib.util, sys
 spec=importlib.util.spec_from_file_location({module!r}, {str(foreign)!r})
 loaded=importlib.util.module_from_spec(spec)
 spec.loader.exec_module(loaded)
 sys.modules[{module!r}]=loaded
 assert loaded.VALUE == 99
"""
    journal, stage = prepare(runtime_tree, code)
    with pytest.raises(ValueError, match=r"STAGE_FAILED|ACTUAL_TEST_RUNTIME_REJECTED"):
        execute(runtime_tree, journal, stage)
    logs = (journal.path / "matrix.stdout.log").read_text() + (
        journal.path / "matrix.stderr.log"
    ).read_text()
    assert "ACTUAL_TEST_MODULE_SOURCE_MISMATCH" in logs


@pytest.mark.parametrize(
    "kind", ["failed", "empty", "skip", "xfail", "filter", "missing_node", "interrupt"]
)
def test_actual_matrix_incomplete_paths_refuse_downstream(runtime_tree, kind):
    code = {
        "failed": "def test_live():\n assert False\n",
        "interrupt": "def test_live():\n raise KeyboardInterrupt()\n",
        "empty": "VALUE = 1\n",
        "skip": "import pytest\ndef test_live():\n pytest.skip('required case')\n",
        "xfail": (
            "import pytest\n@pytest.mark.xfail(reason='required case')\n"
            "def test_live():\n assert False\n"
        ),
    }.get(kind, "def test_live():\n assert True\n")
    journal, stage = prepare(runtime_tree, code)
    if kind == "filter":
        stage = replace(stage, argv=(*stage.argv, "-k", "live"))
    if kind == "missing_node":
        stage = replace(
            stage, test_nodes=(*stage.test_nodes, stage.test_nodes[0] + "::test_missing")
        )
    downstream = coordinator.Stage(
        "downstream", (sys.executable, "-c", "raise RuntimeError('never')")
    )
    with pytest.raises(ValueError):
        execute(runtime_tree, journal, stage, extra_stages=(downstream,))
    value = state(journal)
    assert value["status"] == "FAILED"
    assert len(value["stages"]) == 1 and value["stages"][0]["status"] == "FAILED"


def test_real_matrix_retry_keeps_failed_journal_and_executes_again(runtime_tree):
    first, broken = prepare(runtime_tree, "def test_live():\n assert False\n")
    with pytest.raises(ValueError):
        execute(runtime_tree, first, broken)
    retained = (first.path / "state.json").read_bytes()
    second, fixed = prepare(runtime_tree, "def test_live():\n assert True\n")
    execute(runtime_tree, second, fixed)
    assert (first.path / "state.json").read_bytes() == retained
    assert state(second)["status"] == "STAGES_COMPLETED_NOT_AUTHORIZATION"
    assert state(first)["stages"][0]["pid"] != state(second)["stages"][0]["pid"]


def test_real_test_evidence_stays_in_run_but_real_source_changes_refused(runtime_tree):
    root = runtime_tree
    code = """def test_live():
 import os
 from pathlib import Path
 p=Path(os.environ['S2_SOURCE_EVIDENCE_DIR'])
 p.mkdir(parents=True)
 (p/'actual.log').write_text('actual evidence')
"""
    journal, stage = prepare(root, code)
    stage = replace(
        stage, environment=(("S2_SOURCE_EVIDENCE_DIR", str(journal.path / "evidence")),)
    )
    execute(root, journal, stage)
    assert (journal.path / "evidence/actual.log").read_text() == "actual evidence"
    assert state(journal)["source_before"] == state(journal)["source_after"]
    changed, stage = prepare(
        root,
        "def test_live():\n from pathlib import Path\n"
        " Path('src/actual_new_dependency.py').write_text('VALUE = 2\\n')\n",
    )
    with pytest.raises(ValueError, match="SOURCE_CHANGED"):
        execute(root, changed, stage)
    assert state(changed)["status"] == "FAILED"


def test_comparison_plan_produces_replays_then_consumes_exact_locked_bundle(runtime_tree):
    root = runtime_tree
    for path in coordinator.W2_TESTS:
        (root / path).touch()
    journal = coordinator.Journal(root / coordinator.RUN_AREA / ("plan_" + uuid.uuid4().hex))
    plan = coordinator.comparison_plan(root, journal)
    assert [s.name for s in plan] == [
        "comparison_generate",
        "comparison_recompute",
        "attribution_generate",
        "attribution_recompute",
        "window2_comparison_and_forgery",
    ]
    consumer = plan[-1]
    assert dict(consumer.environment)["S2_AUDIT_BUNDLE"] == str(journal.path / "comparison")
    assert all(Path(v).is_relative_to(journal.path) for _, v in consumer.environment)
    assert (
        consumer.required_artifacts
        == plan[-2].freeze_outputs
        == (str(journal.path / "comparison"),)
    )
    assert "tests/test_structure_two_comparison_dynamic.py" in consumer.test_nodes
    assert "tests/test_structure_two_w3_round5_boundaries.py" in coordinator.W3_TESTS
    for nodes in coordinator.CLOSURE_TESTS.values():
        assert nodes and all("test_structure_two_w3_round5_boundaries.py::" in n for n in nodes)
    with pytest.raises(ValueError, match="REQUIRED_PRODUCER_NOT_COMPLETED"):
        execute(root, journal, consumer)
    assert state(journal)["stages"] == []


@pytest.mark.parametrize("source", ["old", "foreign_resealed"])
def test_preexisting_bundle_cannot_be_imported_as_this_run_generation(runtime_tree, source):
    root = runtime_tree
    journal = coordinator.Journal(root / coordinator.RUN_AREA / (source + uuid.uuid4().hex))
    plan = coordinator.comparison_plan(root, journal)
    bundle = journal.path / "comparison"
    bundle.mkdir()
    (bundle / "audit.json").write_text(json.dumps({"source": source, "passed": True}))
    with pytest.raises(ValueError, match="generation requires new output"):
        execute(root, journal, plan[0])
    assert state(journal)["stages"] == []
    assert json.loads((bundle / "audit.json").read_text())["source"] == source


def test_missing_matrix_file_is_not_dropped(runtime_tree):
    journal = coordinator.Journal(
        runtime_tree / coordinator.RUN_AREA / ("missing_" + uuid.uuid4().hex)
    )
    with pytest.raises(ValueError, match="required test missing"):
        coordinator.matrix_stage(runtime_tree, journal, "required", ("tests/not_present.py",))


def test_old_console_script_cannot_replace_verified_module_invocation(runtime_tree):
    journal, stage = prepare(runtime_tree, "def test_live():\n assert True\n")
    stage = replace(stage, argv=(str(runtime_tree / ".venv/bin/pytest"), *stage.argv[3:]))
    with pytest.raises(ValueError, match="verified python -m pytest"):
        execute(runtime_tree, journal, stage)
    assert "pid" not in state(journal)["stages"][0]


@pytest.mark.parametrize("value", ["-k live", "--deselect=notpresent", "-p no:cacheprovider"])
def test_actual_process_refuses_hidden_pytest_environment(runtime_tree, monkeypatch, value):
    monkeypatch.setenv("PYTEST_ADDOPTS", value)
    journal, stage = prepare(runtime_tree, "def test_live():\n assert True\n")
    with pytest.raises(ValueError, match=r"STAGE_FAILED|ACTUAL_TEST_RUNTIME_REJECTED"):
        execute(runtime_tree, journal, stage)
    assert state(journal)["status"] == "FAILED"
    row = state(journal)["stages"][0]
    logs = (journal.path / "matrix.stdout.log").read_text() + (
        journal.path / "matrix.stderr.log"
    ).read_text()
    assert "UNSAFE_ACTUAL_TEST_ENVIRONMENT" in logs + json.dumps(row.get("runtime_rejections", []))


def test_existing_verified_artifact_cannot_skip_failed_producer(runtime_tree):
    root = runtime_tree
    journal = coordinator.Journal(
        root / coordinator.RUN_AREA / ("failed_producer_" + uuid.uuid4().hex)
    )
    producer = coordinator.Stage("producer", (sys.executable, "-c", "raise SystemExit(9)"))
    consumer = coordinator.Stage(
        "consumer", (sys.executable, "-c", "raise RuntimeError('never')"), requires=("producer",)
    )
    with pytest.raises(ValueError, match="producer exit 9"):
        execute(root, journal, producer, extra_stages=(consumer,))
    assert len(state(journal)["stages"]) == 1


def test_conftest_cannot_silently_reduce_a_nonempty_required_matrix(runtime_tree):
    conftest = runtime_tree / "tests/conftest.py"
    conftest.write_text("def pytest_collection_modifyitems(items):\n items.pop()\n")
    try:
        journal, stage = prepare(
            runtime_tree, "def test_one():\n assert True\ndef test_two():\n assert True\n"
        )
        with pytest.raises(ValueError, match="STAGE_FAILED"):
            execute(runtime_tree, journal, stage)
        logs = (journal.path / "matrix.stdout.log").read_text() + (
            journal.path / "matrix.stderr.log"
        ).read_text()
        assert "HIDDEN_MATRIX_COLLECTION_CHANGE" in logs
    finally:
        conftest.unlink()


def test_outside_checkout_attack_fixture_remains_outside_while_logs_are_bound(runtime_tree):
    code = f"""def test_external(tmp_path):
 from pathlib import Path
 assert not tmp_path.is_relative_to(Path({str(runtime_tree)!r}))
"""
    journal, stage = prepare(runtime_tree, code)
    assert not any(arg.startswith("--basetemp") for arg in stage.argv)
    execute(runtime_tree, journal, stage)
    assert state(journal)["stages"][0]["pytest_counts"]["total"] == 1
