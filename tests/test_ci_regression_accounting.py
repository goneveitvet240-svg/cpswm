"""Real pytest/CLI positives and complete edited-result attacks on CI accounting."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from copy import deepcopy
from pathlib import Path

import pytest
from reconcile_ci_regression import reconcile

TOOLS = Path(__file__).resolve().parents[1] / "tools"
SUCCESS = {"status": "PASSED", "exit_code": 0, "child_exit_code": 0}


@pytest.fixture(scope="module")
def actual_reports(tmp_path_factory):
    root = tmp_path_factory.mktemp("accounting-real-pytest")
    (root / "tests").mkdir()
    (root / "pytest.ini").write_text("[pytest]\naddopts =\ntestpaths = tests\n")
    (root / "tests/test_example.py").write_text(
        "import pytest\n"
        "@pytest.mark.parametrize('value', ['a::b'], ids=['a::b'])\n"
        "def test_parameter(value): assert value == 'a::b'\n"
        "class TestGroup:\n    def test_ok(self): pass\n"
        "@pytest.mark.skip(reason='required fixture absent')\n"
        "def test_skip(): pass\n"
        "@pytest.mark.xfail(strict=True, reason='known open defect')\n"
        "def test_xfail(): assert False\n"
    )
    collect = subprocess.run(
        [sys.executable, "-m", "pytest", "-o", "addopts=", "--collect-only", "-q"],
        cwd=root,
        capture_output=True,
        timeout=30,
    )
    run = subprocess.run(
        [sys.executable, "-m", "pytest", "-o", "addopts=", "-n", "2", "--junitxml=result.xml"],
        cwd=root,
        capture_output=True,
        timeout=30,
    )
    assert collect.returncode == run.returncode == 0, (collect.stderr, run.stderr)
    return collect.stdout, (root / "result.xml").read_bytes()


def test_actual_parallel_pytest_maps_classes_parameters_skips_and_xfails(actual_reports):
    collection, junit = actual_reports
    result = reconcile(collection, 0, junit, SUCCESS, source_unchanged=True)
    assert result["collected_count"] == 4
    assert result["all_nodes_have_one_terminal_result"]
    assert result["ordinary_regression_passed"]
    assert not result["strict_all_nodes_passed"]
    assert result["outcomes"] == {"passed": 2, "skipped": 1, "xfailed": 1}


@pytest.mark.parametrize(
    "attack",
    ["missing", "duplicate", "anonymous", "foreign", "failure", "bad_xml", "multiple_outcomes"],
)
def test_edited_real_junit_cannot_become_a_complete_pass(actual_reports, attack):
    collection, junit = actual_reports
    tree = ET.fromstring(junit)
    suite = next(tree.iter("testsuite"))
    case = next(suite.iter("testcase"))
    if attack == "missing":
        suite.remove(case)
    elif attack == "duplicate":
        suite.append(deepcopy(case))
    elif attack == "anonymous":
        suite.append(ET.Element("testcase", {"time": "0"}))
    elif attack == "foreign":
        case.set("name", "unknown_node")
    elif attack == "failure":
        case.clear()
        case.attrib.update(classname="tests.test_example", name="test_parameter[a::b]")
        ET.SubElement(case, "failure", message="actual failure")
    elif attack == "multiple_outcomes":
        ET.SubElement(case, "failure")
        ET.SubElement(case, "error")
    mutated = b"not XML" if attack == "bad_xml" else ET.tostring(tree)
    result = reconcile(collection, 0, mutated, SUCCESS, source_unchanged=True)
    assert not result["ordinary_regression_passed"]
    assert not result["strict_all_nodes_passed"]


@pytest.mark.parametrize(
    "attack",
    [
        "duplicate",
        "omit",
        "empty",
        "wrong_total",
        "collection_failed",
        "source_changed",
        "timeout",
        "failed",
        "child_failed",
        "interrupted",
    ],
)
def test_collection_and_execution_cannot_hide_incompleteness(actual_reports, attack):
    collection, junit = actual_reports
    execution, code, source = dict(SUCCESS), 0, True
    node = next(line for line in collection.splitlines() if line.startswith(b"tests/"))
    if attack == "duplicate":
        collection += node + b"\n"
    elif attack == "omit":
        collection = collection.replace(node + b"\n", b"")
    elif attack == "empty":
        collection = b"0 tests collected in 0s\n"
    elif attack == "wrong_total":
        collection = collection.replace(b"4 tests collected", b"5 tests collected")
    elif attack == "collection_failed":
        code = 2
    elif attack == "source_changed":
        source = False
    elif attack == "timeout":
        execution.update(status="TIMED_OUT", exit_code=124)
    elif attack == "failed":
        execution.update(status="FAILED", exit_code=1)
    elif attack == "child_failed":
        execution["child_exit_code"] = 1
    elif attack == "interrupted":
        execution["interrupted"] = True
    result = reconcile(collection, code, junit, execution, source_unchanged=source)
    assert not result["ordinary_regression_passed"]


@pytest.mark.parametrize("mode", ["clean", "missing_node", "source_changed", "test_failed"])
def test_actual_cli_controls_exit_code_and_retains_original_execution(tmp_path, mode):
    for directory in ("tools", "tests", "src"):
        (tmp_path / directory).mkdir()
    for name in (
        "run_ci_regression.py",
        "reconcile_ci_regression.py",
        "prepare_current_validation_inputs.py",
    ):
        shutil.copyfile(TOOLS / name, tmp_path / "tools" / name)
    for name in ("pyproject.toml", "uv.lock", ".python-version"):
        (tmp_path / name).write_text("")
    (tmp_path / "pytest.ini").write_text("[pytest]\naddopts =\ntestpaths = tests\n")
    body = "from pathlib import Path\ndef test_ok():\n    assert True\n"
    if mode == "source_changed":
        body += "    Path('src/new_source.py').write_text('CHANGED = True')\n"
    if mode == "test_failed":
        body += "    assert False\n"
    (tmp_path / "tests/test_example.py").write_text(body)
    collected = subprocess.run(
        [sys.executable, "-m", "pytest", "-o", "addopts=", "--collect-only", "-q"],
        cwd=tmp_path,
        capture_output=True,
        timeout=30,
    )
    assert collected.returncode == 0
    collection = collected.stdout
    if mode == "missing_node":
        collection = collection.replace(b"1 test collected", b"2 tests collected")
        collection = b"tests/test_example.py::test_unexecuted\n" + collection
    (tmp_path / "collection.log").write_bytes(collection)
    (tmp_path / "collection-exit.txt").write_text("0")
    completed = subprocess.run(
        [
            sys.executable,
            str(tmp_path / "tools/run_ci_regression.py"),
            "--output",
            str(tmp_path / "execution"),
            "--workers",
            "1",
            "--budget-seconds",
            "30",
            "--collection-log",
            str(tmp_path / "collection.log"),
            "--collection-exit-code-file",
            str(tmp_path / "collection-exit.txt"),
        ],
        cwd=tmp_path,
        capture_output=True,
        timeout=45,
    )
    assert completed.returncode == (0 if mode == "clean" else 1), completed.stderr
    result = json.loads((tmp_path / "execution/result.json").read_text())
    accounting = json.loads((tmp_path / "execution/accounting.json").read_text())
    assert result["exit_code"] == (1 if mode == "test_failed" else 0)
    assert accounting["ordinary_regression_passed"] is (mode == "clean")
    assert accounting["strict_all_nodes_passed"] is (mode == "clean")
    if mode == "source_changed":
        assert not accounting["source_unchanged"]
    if mode == "missing_node":
        assert accounting["missing_nodes"] == ["tests/test_example.py::test_unexecuted"]
