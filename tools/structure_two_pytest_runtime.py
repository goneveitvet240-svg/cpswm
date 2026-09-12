"""Check the actual pytest controller/workers; local observations, not certificates.

PYTEST_DONT_REWRITE

Loaded explicitly by the source-pinned coordinator through python -m pytest.
Existing project entry/load guards remain responsible for project execution code.
Python, pytest, the OS and process integrity remain trusted.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

_ENTRY = sys._getframe().f_code


def pytest_addoption(parser):
    parser.addoption("--s2-runtime-contract", required=True)


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Runtime:
    def __init__(self, config):
        self.config = config
        for key in (
            "PYTEST_ADDOPTS",
            "PYTEST_PLUGINS",
            "PYTHONPATH",
            "PYTHONOPTIMIZE",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
        ):
            if os.environ.get(key):
                raise pytest.UsageError("UNSAFE_ACTUAL_TEST_ENVIRONMENT: " + key)
        if (
            config.getoption("keyword")
            or config.getoption("markexpr")
            or config.getoption("deselect")
        ):
            raise pytest.UsageError("HIDDEN_MATRIX_FILTER")
        self.contract_path = Path(config.getoption("--s2-runtime-contract"))
        self.raw = self.contract_path.read_bytes()
        self.contract = json.loads(self.raw)
        self.root = Path(self.contract["root"])
        self.modules = {}
        self.worker = getattr(config, "workerinput", {}).get("workerid", "controller")
        self.value = {
            "pid": os.getpid(),
            "worker": self.worker,
            "nonce": self.contract["nonce"],
            "status": "STARTED",
            "collected": [],
            "reports": [],
            "workers": [],
            "executable": sys.executable,
            "prefix": sys.prefix,
            "version": sys.version,
        }
        self.destination = self.contract_path.parent / (self.worker + "-" + str(os.getpid()))
        self.check()
        self.write("start")

    def write(self, suffix):
        self.value["modules"] = self.modules
        with self.destination.with_suffix("." + suffix + ".json").open("x") as stream:
            json.dump(self.value, stream, indent=2)
            stream.write("\n")

    def check(self):
        env = self.contract["environment"]
        if sys.executable != str(self.root / ".venv/bin/python") or sys.prefix != env["prefix"]:
            raise pytest.UsageError("ACTUAL_TEST_INTERPRETER_MISMATCH")
        if (
            sys.version != env["version"]
            or file_sha(Path(sys.executable).resolve()) != env["interpreter_sha256"]
        ):
            raise pytest.UsageError("ACTUAL_TEST_INTERPRETER_CHANGED")
        if self.raw != self.contract_path.read_bytes():
            raise pytest.UsageError("TEST_RUNTIME_CONTRACT_CHANGED")
        entry = self.root / "tools/structure_two_pytest_runtime.py"
        if (
            Path(_ENTRY.co_filename).absolute() != entry
            or compile(entry.read_bytes(), str(entry), "exec", dont_inherit=True) != _ENTRY
        ):
            raise pytest.UsageError("ACTUAL_TEST_PLUGIN_CODE_MISMATCH")
        expected = {**env["pytest_sources"], **self.contract["project_sources"]}
        for name, module in tuple(sys.modules.items()):
            if module is None or not any(
                name == n or name.startswith(n + ".") for n in ("pytest", "_pytest", "cpswm")
            ):
                continue
            origin = getattr(getattr(module, "__spec__", None), "origin", None)
            path = Path(getattr(module, "__file__", ""))
            key = str(path)
            if (
                origin != key
                or not path.is_absolute()
                or path.resolve() != path
                or key not in expected
                or file_sha(path) != expected[key]
            ):
                raise pytest.UsageError("ACTUAL_TEST_MODULE_SOURCE_MISMATCH: " + name + " " + key)
            self.modules[name] = {"path": key, "sha256": expected[key]}

    def collection(self, ids):
        if not ids:
            raise pytest.UsageError("EMPTY_REQUIRED_COLLECTION")
        for requested in self.contract["test_nodes"]:
            if not any(
                n == requested or n.startswith(requested + "::") or n.startswith(requested + "[")
                for n in ids
            ):
                raise pytest.UsageError("REQUIRED_TEST_NODE_NOT_COLLECTED: " + requested)
        if len(ids) != len(set(ids)):
            raise pytest.UsageError("DUPLICATE_REQUIRED_COLLECTION")
        self.value["collected"] = list(ids)
        self.check()


def pytest_configure(config):
    try:
        config._s2_runtime = Runtime(config)
    except BaseException as error:
        # A worker can fail before xdist installs its protocol handler. Notify
        # the actual coordinator so its controller cannot wait forever.
        parent = Path(config.getoption("--s2-runtime-contract")).parent
        with (parent / (str(os.getpid()) + ".reject.json")).open("x") as stream:
            json.dump({"pid": os.getpid(), "error": str(error)}, stream)
        raise


def pytest_collection_finish(session):
    session.config._s2_runtime.collection([item.nodeid for item in session.items])


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_collection_modifyitems(session, config, items):
    original = [item.nodeid for item in items]
    yield
    if sorted(item.nodeid for item in items) != sorted(original):
        raise pytest.UsageError("HIDDEN_MATRIX_COLLECTION_CHANGE")


def pytest_deselected(items):
    if items:
        raise pytest.UsageError("HIDDEN_MATRIX_DESELECTION")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    runtime = item.config._s2_runtime
    runtime.check()
    yield
    runtime.check()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    yield
    item.config._s2_runtime.check()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    item.config._s2_runtime.value["reports"].append(
        {
            "nodeid": report.nodeid,
            "when": report.when,
            "outcome": report.outcome,
            "wasxfail": bool(getattr(report, "wasxfail", False)),
        }
    )


@pytest.hookimpl(optionalhook=True)
def pytest_configure_node(node):
    node.config._s2_runtime.value["workers"].append(node.gateway.id)


@pytest.hookimpl(optionalhook=True)
def pytest_xdist_node_collection_finished(node, ids):
    runtime = node.config._s2_runtime
    if runtime.value["collected"] and runtime.value["collected"] != ids:
        raise pytest.UsageError("WORKER_COLLECTION_MISMATCH")
    runtime.collection(ids)


def pytest_sessionfinish(session, exitstatus):
    runtime = session.config._s2_runtime
    try:
        runtime.check()
        runtime.value.update(status="FINISHED", exit_code=int(exitstatus))
    except BaseException as error:
        runtime.value.update(status="FAILED", error=str(error))
        raise
    finally:
        runtime.write("finish")
