#!/usr/bin/env python3
"""Run existing validators on one explicitly pinned checkout; never issue authorization.

Without --execute this only records WAITING_UNIFIED_SOURCE. There is no import of
old success receipts, no resume, no configurable command replacement, and no
scientific PASSED outcome. Trust still assumes the interpreter/OS/process.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import runpy
import signal
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as ET
from contextlib import suppress
from dataclasses import dataclass, replace
from pathlib import Path

ENTRY_CODE = sys._getframe().f_code
LOCAL_ROOT = Path(__file__).resolve().parents[1]
RUN_AREA = Path("docs/reviews/data/structure_two_unified_acceptance_runs")
NAMES = (
    "three_arm_death_test",
    "readout_posthoc_diagnostic",
    "debt_replay_confirmation",
    "readout_prior_factorial",
    "unseen_d0_holdout",
)
W1_TESTS = (
    "tests/test_structure_two_evidence_versions.py",
    "tests/test_structure_two_evidence_supplement.py",
    "tests/test_structure_two_entry_portability.py",
)
# Concrete Window 2/3 paths are checked, never silently dropped when absent.
W2_TESTS = tuple(
    "tests/" + name + ".py"
    for name in (
        "test_structure_two_comparison_audit",
        "test_structure_two_comparison_audit_verification",
        "test_structure_two_comparison_audit_execution_source",
        "test_structure_two_comparison_fairness",
        "test_structure_two_comparison_dynamic",
    )
)
W3_TESTS = tuple(
    "tests/" + name + ".py"
    for name in (
        "test_structure_two_backbone_operator_wiring",
        "test_core_prototype_spine",
        "test_structure_two_production_system",
        "test_structure_two_execution_interface",
        "test_structure_two_adaptive_runtime",
        "test_structure_two_adaptive_runtime_adversarial_round1",
        "test_structure_two_adaptive_runtime_adversarial_round2",
        "test_structure_two_p5_direct_trace_probe",
        "test_structure_two_p5_debt_replay_confirmation",
        "test_structure_two_backbone_counterexample_regressions",
        "test_structure_two_late_counter_evidence_chain",
        "test_structure_two_operator_causal_matrix",
        "test_structure_two_ciav_negative_observation_layers",
        "test_structure_two_p0_maintenance_fault_injection",
        "test_structure_two_formal_revision_lineage",
        "test_structure_two_operator_coverage_matrix",
        "test_structure_two_w3_revision_acceptance",
        "test_structure_two_w3_operator_acceptance",
        "test_structure_two_w3_supplement",
        "test_project_two_feedback_revision_loop",
        "test_project_two_revision_action_trace",
        "test_orrer_event_revision",
        "test_ccrr_context_conditioned_regime",
        "test_hybrid_ledger_durable_log",
        "test_project_one_automatic_regime_loop",
        "test_structure_two_w3_round5_boundaries",
        "test_structure_two_w3_native_particles",
        "test_structure_two_w3_native_bundle",
        "test_project_two_action_readout",
    )
)
CLOSURE_ROLES = (
    "public_revision_atomicity",
    "refreeze_corrected_history",
    "corrected_semantic_identity",
)
# Round-5 independent review closes these three OLD boundaries. These real
# parametrized nodes do not close the newly found prepared-particle defects.
CLOSURE_TESTS = {
    "public_revision_atomicity": (
        "tests/test_structure_two_w3_round5_boundaries.py"
        "::test_correction_postconditions_every_public_entry",
    ),
    "refreeze_corrected_history": (
        "tests/test_structure_two_w3_round5_boundaries.py::test_refreeze_after_existing_generations",
    ),
    "corrected_semantic_identity": (
        "tests/test_structure_two_w3_round5_boundaries.py::test_revision_semantics_reproduce_across_runs",
    ),
}

NATIVE_LAYOUT_CODE = r"""
import importlib, json, pathlib, runpy, sys
root = pathlib.Path.cwd()
runner = root/'apps/evaluation_runner'
a = runpy.run_path(str(runner/'run_structure_two_evidence_repair.py'))
c = runpy.run_path(str(runner/'generate_structure_two_engineering_trust_checkpoint.py'))
e = runpy.run_path(str(runner/'run_structure_two_engineering_audit_receipt.py'))
p = runpy.run_path(str(runner/'generate_p0_checkpoint_manifest.py'))
def rel(value):
    return (root/pathlib.Path(value)).resolve().relative_to(root).as_posix()
outputs = {
    n: rel(importlib.import_module(
        'cpswm.system.evaluation_operations.structure_two_p5_'+n).DEFAULT_OUTPUT)
    for n in a['EXPERIMENTS']
}
checks = [
    rel(e['DEFAULT_OUTPUT']) == rel(c['AUDIT_RECEIPT']),
    rel(p['DEFAULT_OUTPUT']) == rel(c['P0_MANIFEST']),
    c['AUDIT_RECEIPT'] in p['TEST_FIXTURE_EXCLUDED_PATHS'],
    pathlib.Path(rel(c['OUTPUT'])) in p['TEST_FIXTURE_EXCLUDED_PATHS'],
    list(a['EXPERIMENTS']) == ['three_arm_death_test', 'readout_posthoc_diagnostic',
        'debt_replay_confirmation', 'readout_prior_factorial', 'unseen_d0_holdout'],
]
if not all(checks):
    raise ValueError('native output/consumer contract mismatch')
print(json.dumps({
    'root': str(root),
    'execution_source': sys.modules['_cpswm_source_bootstrap'].guard.require(root),
    'p5': outputs, 'history': e['COMMANDS']['p5_evidence_history'][3],
    'p0': rel(c['P0_MANIFEST']), 'receipt': rel(c['AUDIT_RECEIPT']),
    'checkpoint': rel(c['OUTPUT']), 'v05': rel(c['V05_AUDIT'])
}))
"""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def execution_environment(root):
    """Actual matching venv, not caller-supplied environment fingerprints."""
    python = root / ".venv/bin/python"
    code = (
        "import sys,json,importlib.metadata as m; "
        "print(json.dumps({'prefix':sys.prefix,'executable':sys.executable,"
        "'version':sys.version,'packages':sorted((d.metadata['Name'],d.version) "
        "for d in m.distributions())}))"
    )
    value = json.loads(subprocess.check_output([str(python), "-c", code], cwd=root, text=True))
    if (root / ".venv").is_symlink() or Path(value["prefix"]).absolute() != root / ".venv":
        raise ValueError("native interpreter belongs to another virtual environment")
    if not value["version"].startswith("3.13."):
        raise ValueError("native Python 3.13 required")
    value["interpreter_sha256"] = hashlib.sha256(python.resolve().read_bytes()).hexdigest()
    site = root / ".venv/lib/python3.13/site-packages"
    value["pytest_sources"] = {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest()
        for package in ("pytest", "_pytest")
        for p in sorted((site / package).rglob("*.py"))
        if not p.is_symlink()
    }
    if not all(
        str(site / n / "__init__.py") in value["pytest_sources"] for n in ("pytest", "_pytest")
    ):
        raise ValueError("native pytest source absent")
    value["environment_hashes"] = {
        name: hashlib.sha256(os.environ[name].encode()).hexdigest() if name in os.environ else None
        for name in (
            "PATH",
            "PYTHONPATH",
            "VIRTUAL_ENV",
            "PYTEST_ADDOPTS",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
            "PYTEST_PLUGINS",
            "PYTHONHASHSEED",
        )
    }
    return value


def source_snapshot(root, excluded=()):
    """Include tracked and new inputs, not merely Git HEAD or top-level source fields."""
    paths = (
        subprocess.check_output(
            ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard", "-z"]
        )
        .decode()
        .split("\0")
    )
    # Ignored source/data can still be loaded; Git is not the loader inventory.
    for top in (
        "src",
        "apps",
        "tests",
        "configs",
        "tools",
        "data",
        "benchmarks",
        "artifacts",
        "output",
    ):
        for path in (root / top).rglob("*"):
            if path.is_file() or path.is_symlink():
                paths.append(path.relative_to(root).as_posix())
    rows = {}
    excluded = (*excluded, RUN_AREA)
    for name in sorted(set(paths) - {""}):
        relative = Path(name)
        if any(relative == x or x in relative.parents for x in excluded):
            continue
        if any(
            p in {"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"}
            for p in relative.parts
        ):
            continue
        if relative.suffix in {".pyc", ".pyo"}:
            continue
        path = root / relative
        if any(p.is_symlink() for p in [path, *path.parents] if p != root.parent):
            raise ValueError(f"input symlink refused: {name}")
        if not path.is_file():
            raise ValueError(f"input absent/not regular: {name}")
        rows[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"head": git(root, "rev-parse", "HEAD"), "files": rows, "sha256": digest(rows)}


def require_snapshot(root, expected, excluded):
    actual = source_snapshot(root, excluded)
    if actual != expected:
        raise ValueError("SOURCE_CHANGED: pinned inputs or HEAD changed")
    return actual


def check_entry():
    path = Path(ENTRY_CODE.co_filename).absolute()
    expected = LOCAL_ROOT / "tools/structure_two_unified_acceptance.py"
    if (
        path != expected
        or compile(expected.read_bytes(), str(path), "exec", dont_inherit=True) != ENTRY_CODE
    ):
        raise ValueError("executing coordinator entry differs from declared source")
    if any(n == "cpswm" or n.startswith("cpswm.") for n in sys.modules):
        raise ValueError("coordinator must precede project imports; native stages run fresh")


@dataclass(frozen=True)
class Stage:
    name: str
    argv: tuple[str, ...]
    junit: str | None = None
    freeze_outputs: tuple[str, ...] = ()
    environment: tuple[tuple[str, str], ...] = ()
    requires: tuple[str, ...] = ()
    required_artifacts: tuple[str, ...] = ()
    new_outputs: tuple[str, ...] = ()
    test_nodes: tuple[str, ...] = ()
    native_plugin_policy: bool = False


class Journal:
    """A local progress journal, never accepted as a reusable proof of execution."""

    def __init__(self, path):
        self.path = path.absolute()
        if self.path != self.path.resolve():
            raise ValueError("run directory must be a canonical path without escape aliases")
        if any(p.is_symlink() for p in [self.path, *self.path.parents]):
            raise ValueError("run directory symlink refused")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.mkdir()  # exclusive: retry must choose another directory
        self.identity = self.path.stat().st_dev, self.path.stat().st_ino
        self.value = {
            "status": "STARTING",
            "scientific_gate": "NOT_PASSED",
            "ablation_authorized": False,
            "stages": [],
            "pid": os.getpid(),
        }
        self.save()

    def save(self):
        current = self.path.stat()
        if self.path.is_symlink() or (current.st_dev, current.st_ino) != self.identity:
            raise ValueError("run directory replaced")
        target = self.path / (".state-" + uuid.uuid4().hex)
        try:
            with target.open("x") as stream:
                stream.write(json.dumps(self.value, indent=2, allow_nan=False) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(target, self.path / "state.json")
        finally:
            target.unlink(missing_ok=True)


def stop_process(proc):
    # Reap an exited leader before signaling its process group (Darwin can
    # report EPERM for an unreaped, exiting group). Descendants still get killed.
    proc.poll()
    # An ignored-TERM descendant can outlive an already-exited leader.
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except PermissionError:
        # Retry only after actually observing/reaping the leader's exit. A live
        # process or a still-inaccessible group remains a hard cleanup failure.
        proc.wait(timeout=1)
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
    except ProcessLookupError:
        proc.wait()
        return
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        proc.poll()
        try:
            os.killpg(proc.pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.02)
    else:
        with suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)
    proc.wait()


def artifact_snapshot(root, paths):
    result = {}
    for name in paths:
        path = root / name
        if path.resolve() != path or not path.is_relative_to(root):
            raise ValueError("generated artifact path escapes canonical checkout")
        path.relative_to(root)
        if not path.exists():
            raise ValueError("required generated artifact absent: " + name)
        members = [path, *path.rglob("*")] if path.is_dir() else [path]
        rows = {}
        for member in members:
            if any(p.is_symlink() for p in [member, *member.parents]):
                raise ValueError("generated artifact alias refused")
            key = member.relative_to(root).as_posix()
            rows[key] = (
                hashlib.sha256(member.read_bytes()).hexdigest() if member.is_file() else "directory"
            )
        result[name] = rows
    return result


def require_artifacts(root, locked):
    for paths, expected in locked:
        if artifact_snapshot(root, paths) != expected:
            raise ValueError("VERIFIED_ARTIFACT_CHANGED: cannot splice downstream green results")


def matrix_stage(
    root,
    journal,
    name,
    paths,
    *,
    required_nodes=(),
    environment=(),
    requires=(),
    required_artifacts=(),
):
    if not paths:
        raise ValueError("empty required matrix")
    for node in (*paths, *required_nodes):
        path = root / node.split("::")[0]
        if path.resolve() != path or not path.is_file():
            raise ValueError("required test missing or noncanonical: " + node)
    xml = name + ".xml"
    return Stage(
        name,
        (
            str(root / ".venv/bin/python"),
            "-m",
            "pytest",
            "-p",
            "tools.structure_two_pytest_runtime",
            "-o",
            "addopts=",
            "-q",
            "--confcutdir=.",
            "--junitxml=" + str(journal.path / xml),
            "--s2-runtime-contract=" + str(journal.path / (name + "_runtime") / "contract.json"),
            *paths,
        ),
        xml,
        environment=tuple(environment),
        requires=tuple(requires),
        required_artifacts=tuple(required_artifacts),
        test_nodes=tuple((*paths, *required_nodes)),
    )


def comparison_plan(root, journal):
    """Real Window-2 producers and their actual consumer matrix, also used in fixtures."""
    comparison = str(journal.path / "comparison")
    python = str(root / ".venv/bin/python")
    main = "apps/evaluation_runner/run_structure_two_comparison_audit.py"
    attribution = "apps/evaluation_runner/summarize_structure_two_comparison_audit.py"
    files = tuple(
        str(Path(comparison) / n) for n in ("audit.json", "steps.jsonl.gz", "timing.json")
    )
    generated = Stage(
        "comparison_generate",
        (python, main, "--repository-root", str(root), "--output", comparison),
        freeze_outputs=files,
        new_outputs=(comparison,),
    )
    replay = Stage(
        "comparison_recompute",
        (*generated.argv, "--verify"),
        requires=(generated.name,),
        required_artifacts=files,
    )
    summarized = Stage(
        "attribution_generate",
        (python, attribution, "--bundle", comparison),
        freeze_outputs=(str(Path(comparison) / "attribution.json"),),
        requires=(replay.name,),
        required_artifacts=files,
    )
    verified = Stage(
        "attribution_recompute",
        (*summarized.argv, "--verify"),
        freeze_outputs=(comparison,),
        requires=(summarized.name,),
    )
    environment = {"S2_AUDIT_BUNDLE": comparison}
    for key, directory in (
        ("S2_AUDIT_EVIDENCE_DIR", "forgery"),
        ("S2_SOURCE_EVIDENCE_DIR", "source"),
        ("S2_FAIRNESS_EVIDENCE_DIR", "fairness"),
        ("S2_DYNAMIC_EVIDENCE_DIR", "dynamic"),
    ):
        environment[key] = str(journal.path / "window2_evidence" / directory)
    consumer = matrix_stage(
        root,
        journal,
        "window2_comparison_and_forgery",
        W2_TESTS,
        environment=tuple(environment.items()),
        requires=(replay.name, verified.name),
        required_artifacts=(comparison,),
    )
    return [generated, replay, summarized, verified, consumer]


def prepare_test_runtime(root, journal, stage, frozen, environment):
    if environment is None:
        raise ValueError("matrix requires verified native execution environment")
    if stage.argv[:3] != (str(root / ".venv/bin/python"), "-m", "pytest"):
        raise ValueError("matrix must use verified python -m pytest")
    path = journal.path / (stage.name + "_runtime")
    path.mkdir()
    contract = {
        "root": str(root),
        "nonce": uuid.uuid4().hex,
        "environment": environment,
        "test_nodes": stage.test_nodes,
        "native_pytest_plugin_policy": (
            "explicit_plugins_only" if stage.native_plugin_policy else None
        ),
        "local_sources": {
            str(root / p): sha for p, sha in frozen["files"].items() if p.endswith(".py")
        },
        "project_sources": {
            str(root / p): sha
            for p, sha in frozen["files"].items()
            if p.startswith("src/cpswm/") and p.endswith(".py")
        },
    }
    with (path / "contract.json").open("x") as stream:
        stream.write(json.dumps(contract, indent=2) + "\n")
    return path, contract


def verify_test_runtime(path, contract, pid):
    records = [json.loads(p.read_text()) for p in sorted(path.glob("*.finish.json"))]
    masters = [r for r in records if r["worker"] == "controller"]
    if len(masters) != 1 or masters[0]["pid"] != pid:
        raise ValueError("actual pytest controller observation absent or mismatched")
    master = masters[0]
    if len(records) != 1 + len(master["workers"]) or {r["worker"] for r in records} != {
        "controller",
        *master["workers"],
    }:
        raise ValueError("actual pytest worker observations incomplete")
    reports = []
    for r in records:
        if r["nonce"] != contract["nonce"] or r["status"] != "FINISHED" or r["exit_code"] != 0:
            raise ValueError("actual pytest process did not complete successfully")
        if (
            r["executable"] != str(Path(contract["root"]) / ".venv/bin/python")
            or r["prefix"] != contract["environment"]["prefix"]
        ):
            raise ValueError("actual pytest process interpreter differs")
        if not r["collected"] or r["collected"] != master["collected"]:
            raise ValueError("actual pytest collection missing or inconsistent")
        reports.extend(r["reports"])
    if any(r["outcome"] != "passed" or r["wasxfail"] for r in reports):
        raise ValueError("actual pytest failed/skipped/xfail cannot complete matrix")
    for phase in ("setup", "call", "teardown"):
        ids = [r["nodeid"] for r in reports if r["when"] == phase]
        if sorted(ids) != sorted(master["collected"]):
            raise ValueError("actual pytest required tests not fully executed: " + phase)
    return {"processes": records, "contract_sha256": digest(contract)}


def run_stages(root, journal, stages, frozen, excluded, *, environment=None, before_stage=None):
    """Shared execution engine. No loaded journal can skip a stage or grant success."""
    journal.value.update(
        status="RUNNING", source_before=frozen, required_stages=[s.name for s in stages]
    )
    journal.save()
    locked = []
    completed = set()
    try:
        for stage in stages:
            if not set(stage.requires).issubset(completed):
                raise ValueError("REQUIRED_PRODUCER_NOT_COMPLETED: " + stage.name)
            frozen_paths = {p for paths, _ in locked for p in paths}
            if not set(stage.required_artifacts).issubset(frozen_paths):
                raise ValueError("REQUIRED_VERIFIED_ARTIFACT_ABSENT: " + stage.name)
            for name in stage.new_outputs:
                path = root / name
                if path.exists() or path.is_symlink():
                    raise ValueError("generation requires new output: " + name)
            require_artifacts(root, locked)
            require_snapshot(root, frozen, excluded)
            if environment is not None and execution_environment(root) != environment:
                raise ValueError("execution environment changed before stage")
            if before_stage is not None:
                before_stage(stage.name)
            if not stage.name.replace("_", "").isalnum():
                raise ValueError("unsafe stage name")
            row = {
                "name": stage.name,
                "argv": list(stage.argv),
                "cwd": str(root),
                "status": "RUNNING",
                "environment_overrides": dict(stage.environment),
                "started_unix": time.time(),
            }
            journal.value["stages"].append(row)
            journal.save()
            output = journal.path / (stage.name + ".stdout.log")
            error = journal.path / (stage.name + ".stderr.log")
            proc = None
            runtime = None
            if stage.test_nodes:
                runtime = prepare_test_runtime(root, journal, stage, frozen, environment)
            elif stage.junit and environment is not None:
                raise ValueError("native test matrix requires actual runtime observations")
            try:
                with output.open("xb") as stdout, error.open("xb") as stderr:
                    proc = subprocess.Popen(
                        stage.argv,
                        cwd=root,
                        stdout=stdout,
                        stderr=stderr,
                        start_new_session=True,
                        env={**os.environ, **dict(stage.environment)},
                    )
                    row["pid"] = proc.pid
                    journal.save()
                    if runtime is not None:
                        while proc.poll() is None:
                            rejections = list(runtime[0].glob("*.reject.json"))
                            if rejections:
                                row["runtime_rejections"] = [
                                    json.loads(p.read_text()) for p in rejections
                                ]
                                # Most rejecting pytest processes exit immediately. Let
                                # them flush real diagnostics; early worker failures may
                                # instead wait for xdist, so bound this grace period.
                                with suppress(subprocess.TimeoutExpired):
                                    proc.wait(timeout=1)
                                raise ValueError("ACTUAL_TEST_RUNTIME_REJECTED: " + stage.name)
                            time.sleep(0.05)
                    row["exit_code"] = proc.wait()
            finally:
                if proc is not None:
                    stop_process(proc)
                    row["exit_code"] = proc.returncode
                row["ended_unix"] = time.time()
                for key, path in (("stdout", output), ("stderr", error)):
                    if path.exists():
                        row[key] = {
                            "path": path.name,
                            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        }
                journal.save()
            require_snapshot(root, frozen, excluded)
            require_artifacts(root, locked)
            if environment is not None and execution_environment(root) != environment:
                raise ValueError("execution environment changed during stage")
            if row["exit_code"] != 0:
                raise ValueError(f"STAGE_FAILED: {stage.name} exit {row['exit_code']}")
            if runtime is not None:
                row["test_runtime"] = verify_test_runtime(*runtime, row["pid"])
            if stage.junit:
                cases = ET.parse(journal.path / stage.junit).findall(".//testcase")
                counts = {
                    k: sum(c.find(k) is not None for c in cases)
                    for k in ("failure", "error", "skipped")
                }
                row["pytest_counts"] = {"total": len(cases), **counts}
                if not cases or any(counts.values()):
                    raise ValueError("required matrix has absent, failed, skipped or xfailed cases")
            if stage.freeze_outputs:
                captured = artifact_snapshot(root, stage.freeze_outputs)
                locked.append((stage.freeze_outputs, captured))
                row["frozen_outputs"] = captured
            row["status"] = "COMPLETED"
            completed.add(stage.name)
            journal.save()
        require_artifacts(root, locked)
        journal.value["locked_artifacts"] = locked
        journal.value["source_after"] = require_snapshot(root, frozen, excluded)
        journal.value["status"] = "STAGES_COMPLETED_NOT_AUTHORIZATION"
        journal.save()
    except BaseException as error:
        journal.value["status"] = (
            "INTERRUPTED" if isinstance(error, (KeyboardInterrupt, InterruptedError)) else "FAILED"
        )
        if journal.value["stages"] and journal.value["stages"][-1]["status"] == "RUNNING":
            journal.value["stages"][-1]["status"] = journal.value["status"]
        journal.value["error"] = f"{type(error).__name__}: {error}"
        try:
            journal.value["source_after_failure"] = source_snapshot(root, excluded)
        except Exception as snapshot_error:
            journal.value["source_after_failure_error"] = str(snapshot_error)
        journal.save()
        raise


def native_layout(root, journal):
    argv = [str(root / ".venv/bin/python"), "-c", NATIVE_LAYOUT_CODE]
    result = subprocess.run(argv, cwd=root, text=True, capture_output=True)
    number = len(journal.value.get("layout_probes", []))
    for key, data in (("stdout", result.stdout), ("stderr", result.stderr)):
        with (journal.path / f"layout_{number}.{key}.log").open("x") as stream:
            stream.write(data)
    journal.value.setdefault("layout_probes", []).append(
        {"argv": argv, "exit_code": result.returncode}
    )
    if result.returncode:
        raise ValueError("native layout/entry/source verification failed")
    value = json.loads(result.stdout)
    if set(value["p5"]) != set(NAMES):
        raise ValueError("native layout must contain exactly five experiments")
    if value["root"] != str(root):
        raise ValueError("native layout root differs")
    return value


def relative_outputs(root, layout):
    values = [
        *layout["p5"].values(),
        *(layout[n] for n in ("history", "receipt", "checkpoint", "p0", "v05")),
    ]
    result = []
    for value in values:
        p = Path(value)
        if p.is_absolute() or ".." in p.parts or (root / p).resolve() != root / p:
            raise ValueError("native output path escapes frozen checkout")
        result.append(p)
    if len(set(result)) != len(result):
        raise ValueError("native outputs overlap")
    return result


def build_plan(root, journal, layout, closure):
    python = str(root / ".venv/bin/python")
    stages = []

    def cli(name, script, *args, freeze=()):
        stages.append(
            Stage(
                name,
                (python, "apps/evaluation_runner/" + script, *map(str, args)),
                freeze_outputs=tuple(freeze),
            )
        )

    def matrix(name, paths, **kwargs):
        stages.append(matrix_stage(root, journal, name, paths, **kwargs))

    if set(closure) != set(CLOSURE_ROLES) or any(
        not isinstance(v, (list, tuple)) or not v for v in closure.values()
    ):
        raise ValueError("explicit tests for all three round-4 closure roles required")
    closure_nodes = [node for nodes in closure.values() for node in nodes]
    if len(closure_nodes) != len(set(closure_nodes)):
        raise ValueError("closure roles require distinct reviewed tests")
    if any(
        not isinstance(n, str)
        or not n.startswith("tests/")
        or ".." in Path(n.split("::")[0]).parts
        or "::" not in n
        for n in closure_nodes
    ):
        raise ValueError("closure mappings must name source-bound test node IDs")
    matrix("window1_protection", W1_TESTS)
    stages.extend(comparison_plan(root, journal))
    # Full files already cover the reviewed nodes; do not execute them twice.
    matrix("window3_revision_and_backbone", W3_TESTS, required_nodes=tuple(closure_nodes))
    cli("five_generate", "run_structure_two_evidence_repair.py", "--generate-current")
    cli("five_recompute", "run_structure_two_evidence_repair.py", "--verify-current")
    cli(
        "history_generate",
        "audit_structure_two_evidence_history.py",
        "--recompute-first-failure",
        "--recompute-failed-replay",
        "--output",
        layout["history"],
    )
    cli(
        "history_recompute",
        "audit_structure_two_evidence_history.py",
        "--verify",
        layout["history"],
    )
    cli("history_aggregate", "run_structure_two_evidence_repair.py", "--verify-history")
    cli("v05_compatibility", "audit_structure_two_world_source_bundle_v0_5.py")
    cli("p0_generate", "generate_p0_checkpoint_manifest.py")
    cli("native_engineering_matrix", "run_structure_two_engineering_audit_receipt.py")
    cli("checkpoint_generate_fresh", "generate_structure_two_engineering_trust_checkpoint.py")
    cli(
        "checkpoint_verify_fresh",
        "generate_structure_two_engineering_trust_checkpoint.py",
        "--verify",
        layout["checkpoint"],
    )
    matrix("checkpoint_adversarial", ("tests/test_structure_two_engineering_trust_checkpoint.py",))
    freeze_by_stage = {
        "five_generate": tuple(layout["p5"].values()),
        "history_generate": (layout["history"],),
        "v05_compatibility": (layout["v05"],),
        "p0_generate": (layout["p0"],),
        "native_engineering_matrix": (
            layout["receipt"],
            str(Path(layout["receipt"]).parent / "engineering_audit_logs"),
        ),
        "checkpoint_generate_fresh": (layout["checkpoint"],),
    }
    return [
        replace(s, freeze_outputs=freeze_by_stage.get(s.name, s.freeze_outputs)) for s in stages
    ]


def interrupted(_signum, _frame):
    raise InterruptedError("coordinator interrupted; a new full run is required")


def native_audit_pytest(command_id):
    """Native receipt test commands use the same observed real pytest engine."""
    root = LOCAL_ROOT
    journal = Journal(root / RUN_AREA / ("native_" + command_id + "_" + uuid.uuid4().hex))
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        namespace = runpy.run_path(
            str(root / "apps/evaluation_runner/run_structure_two_engineering_audit_receipt.py")
        )
        arguments = namespace["NATIVE_PYTEST_ARGUMENTS"][command_id]
        expected_env = namespace["PYTEST_ENVIRONMENT_OVERRIDES"]
        if any(os.environ.get(k) != v for k, v in expected_env.items()):
            raise ValueError("native audit test environment differs from frozen command policy")
        paths = (
            tuple(a for a in arguments if a.startswith("tests/"))
            if command_id == "p0_adversarial_tests"
            else tuple(
                p.relative_to(root).as_posix()
                for p in sorted((root / "tests").rglob("test_*.py"))
                if p.name != "test_structure_two_engineering_trust_checkpoint.py"
            )
        )
        stage = replace(matrix_stage(root, journal, command_id, paths), native_plugin_policy=True)
        # Preserve the complete frozen native selection/scheduling arguments.
        # matrix_stage contributes only the explicit runtime/JUnit observation flags.
        stage = replace(
            stage,
            argv=(
                str(root / ".venv/bin/python"),
                "-m",
                "pytest",
                "-p",
                "tools.structure_two_pytest_runtime",
                *(a for a in stage.argv if a.startswith(("--junitxml=", "--s2-runtime-contract="))),
                *arguments,
            ),
        )
        frozen = source_snapshot(root)
        environment = execution_environment(root)

        run_stages(root, journal, [stage], frozen, (), environment=environment)
        print((journal.path / (command_id + ".stdout.log")).read_text(), end="")
        print(
            json.dumps(
                {"native_test_journal": str(journal.path), "status": journal.value["status"]}
            )
        )
        return 0
    except BaseException as error:
        if journal.value["status"] not in {"FAILED", "INTERRUPTED"}:
            journal.value.update(status="FAILED", error=str(error))
            journal.save()
        print(
            json.dumps({"native_test_journal": str(journal.path), "error": str(error)}),
            file=sys.stderr,
        )
        return 130 if isinstance(error, KeyboardInterrupt) else 1


def main():
    check_entry()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--unified-root", type=Path)
    parser.add_argument("--expected-head")
    parser.add_argument("--expected-input-sha256")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--native-audit-command", choices=("p0_adversarial_tests", "core_pytest"))
    parser.add_argument("--inspect-run", type=Path)
    args = parser.parse_args()
    if args.native_audit_command:
        if args.execute or args.unified_root or args.run_dir or args.inspect_run:
            parser.error("native audit tests cannot designate unified acceptance")
        return native_audit_pytest(args.native_audit_command)
    if args.inspect_run:
        state = json.loads((args.inspect_run / "state.json").read_text())
        # A journal is diagnostic data, never imported to authorize/resume execution.
        print(
            json.dumps(
                {
                    "recorded_status": state["status"],
                    "status": "INCOMPLETE_RUN"
                    if state["status"] in {"RUNNING", "STARTING"}
                    else "RECORDED_STATE_ONLY",
                    "reusable_execution_proof": False,
                }
            )
        )
        return 0
    if not args.run_dir:
        parser.error("--run-dir is required")
    root = LOCAL_ROOT
    if not args.run_dir.absolute().is_relative_to(root / RUN_AREA):
        parser.error("--run-dir must be a new child of " + str(root / RUN_AREA))
    journal = Journal(args.run_dir)
    root = LOCAL_ROOT
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        if args.unified_root and args.unified_root.resolve() != root:
            raise ValueError("declared unified root differs from executing coordinator checkout")
        for name in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTHONPATH", "PYTHONOPTIMIZE"):
            if os.environ.get(name):
                raise ValueError("unsafe test/import environment: " + name)
        if os.environ.get("PYTEST_DISABLE_PLUGIN_AUTOLOAD") not in (None, ""):
            raise ValueError("unexpected pytest plugin suppression")
        run_relative = journal.path.relative_to(root)
        # All other inputs, including the coordinator and tests, remain bound.
        layout = native_layout(root, journal)
        outputs = relative_outputs(root, layout)
        excluded = (
            run_relative,
            *outputs,
            Path(layout["receipt"]).parent / "engineering_audit_logs",
        )
        frozen = source_snapshot(root, excluded)
        environment = execution_environment(root)
        journal.value.update(
            root=str(root),
            source_before=frozen,
            environment_before=environment,
            layout=layout,
            excluded_generated_paths=[str(p) for p in excluded],
        )
        if not args.execute:
            journal.value.update(
                status="WAITING_UNIFIED_SOURCE",
                reason="No explicitly selected, fixed unified checkout has been executed",
            )
            journal.save()
            print(
                json.dumps(
                    {
                        "status": journal.value["status"],
                        "head": frozen["head"],
                        "input_sha256": frozen["sha256"],
                    }
                )
            )
            return 0
        if args.unified_root is None or not args.expected_head or not args.expected_input_sha256:
            raise ValueError("execution requires explicit unified root, HEAD, full input digest")
        if args.expected_head != frozen["head"] or args.expected_input_sha256 != frozen["sha256"]:
            raise ValueError("explicit source pin does not match actual checkout")
        # Old sealed artifacts are not inputs to a new-generation success claim.
        for p in outputs:
            if p.as_posix() not in {layout["p0"], layout["v05"]} and (root / p).exists():
                raise ValueError(
                    "sealed output exists; freeze new evidence paths before acceptance: " + str(p)
                )
        audit_logs = Path(layout["receipt"]).parent / "engineering_audit_logs"
        if (root / audit_logs).exists() or (root / audit_logs).is_symlink():
            raise ValueError("sealed audit log directory exists; choose a new frozen version")
        for name in ("p0", "v05"):
            path = root / layout[name]
            if path.exists():
                (journal.path / ("preserved_" + name + ".json")).write_bytes(path.read_bytes())
        closure = CLOSURE_TESTS
        stages = build_plan(root, journal, layout, closure)
        produced = {
            "five_generate": list(layout["p5"].values()),
            "history_generate": [layout["history"]],
            "native_engineering_matrix": [layout["receipt"], str(audit_logs)],
            "checkpoint_generate_fresh": [layout["checkpoint"]],
        }

        def before_stage(name):
            for value in produced.get(name, []):
                if (root / value).exists() or (root / value).is_symlink():
                    raise ValueError("output appeared before its generation: " + value)
            for key in ("p0", "v05"):
                path = root / layout[key]
                if path.exists() and (path.is_symlink() or path.stat().st_nlink != 1):
                    raise ValueError("mutable index has unsafe alias: " + str(path))

        run_stages(
            root,
            journal,
            stages,
            frozen,
            excluded,
            environment=environment,
            before_stage=before_stage,
        )
        final_layout = native_layout(root, journal)
        if final_layout != layout:
            raise ValueError("native execution source/layout changed")
        journal.value["output_inventory"] = {
            str(path): hashlib.sha256((root / path).read_bytes()).hexdigest() for path in outputs
        }
        after = execution_environment(root)
        if after != environment:
            raise ValueError("execution environment changed during acceptance")
        require_artifacts(root, journal.value["locked_artifacts"])
        journal.value["source_after"] = require_snapshot(root, frozen, excluded)
        journal.value.update(environment_after=after, status="COMPLETED_REQUIRED_RECOMPUTATION")
        journal.save()
        print(json.dumps({"status": journal.value["status"], "scientific_gate": "NOT_PASSED"}))
        return 0
    except BaseException as error:
        journal.value.update(
            status="INTERRUPTED"
            if isinstance(error, (KeyboardInterrupt, InterruptedError))
            else "FAILED",
            error=f"{type(error).__name__}: {error}",
        )
        journal.save()
        print(json.dumps({"status": journal.value["status"], "error": str(error)}), file=sys.stderr)
        return 130 if journal.value["status"] == "INTERRUPTED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
