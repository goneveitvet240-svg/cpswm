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
import signal
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as ET
from contextlib import suppress
from dataclasses import dataclass
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
    )
)
CLOSURE_ROLES = (
    "public_revision_atomicity",
    "refreeze_corrected_history",
    "corrected_semantic_identity",
)
# These are deliberately unset: Window 3 must supply reviewed new node IDs,
# committed with the unified source before its digest is pinned. A caller JSON
# map or three old positive tests must never be accepted as closure evidence.
CLOSURE_TESTS = {role: () for role in CLOSURE_ROLES}

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


class Journal:
    """A local progress journal, never accepted as a reusable proof of execution."""

    def __init__(self, path):
        self.path = path.absolute()
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
    # An ignored-TERM descendant can outlive an already-exited leader.
    try:
        os.killpg(proc.pid, signal.SIGTERM)
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


def run_stages(root, journal, stages, frozen, excluded, *, environment=None, before_stage=None):
    """Shared execution engine. No loaded journal can skip a stage or grant success."""
    journal.value.update(
        status="RUNNING", source_before=frozen, required_stages=[s.name for s in stages]
    )
    journal.save()
    locked = []
    try:
        for stage in stages:
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
                "started_unix": time.time(),
            }
            journal.value["stages"].append(row)
            journal.save()
            output = journal.path / (stage.name + ".stdout.log")
            error = journal.path / (stage.name + ".stderr.log")
            proc = None
            try:
                with output.open("xb") as stdout, error.open("xb") as stderr:
                    proc = subprocess.Popen(
                        stage.argv, cwd=root, stdout=stdout, stderr=stderr, start_new_session=True
                    )
                    row["pid"] = proc.pid
                    journal.save()
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
    pytest = str(root / ".venv/bin/pytest")
    stages = []

    def cli(name, script, *args, freeze=()):
        stages.append(
            Stage(
                name,
                (python, "apps/evaluation_runner/" + script, *map(str, args)),
                freeze_outputs=tuple(freeze),
            )
        )

    def matrix(name, paths):
        if not paths:
            raise ValueError("empty required matrix")
        for node in paths:
            if not (root / node.split("::")[0]).is_file():
                raise ValueError("required test missing: " + node)
        xml = name + ".xml"
        stages.append(
            Stage(
                name,
                (
                    pytest,
                    "-o",
                    "addopts=",
                    "-q",
                    "--confcutdir=.",
                    "--junitxml=" + str(journal.path / xml),
                    *paths,
                ),
                xml,
            )
        )

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
    matrix("window2_comparison_and_forgery", W2_TESTS)
    matrix("window3_revision_and_backbone", (*W3_TESTS, *closure_nodes))
    comparison = str(journal.path / "comparison")
    comparison_files = tuple(
        str(Path(comparison) / n) for n in ("audit.json", "steps.jsonl.gz", "timing.json")
    )
    cli(
        "comparison_generate",
        "run_structure_two_comparison_audit.py",
        "--repository-root",
        root,
        "--output",
        comparison,
    )
    cli(
        "comparison_recompute",
        "run_structure_two_comparison_audit.py",
        "--repository-root",
        root,
        "--output",
        comparison,
        "--verify",
    )
    cli(
        "attribution_generate",
        "summarize_structure_two_comparison_audit.py",
        "--bundle",
        comparison,
    )
    cli(
        "attribution_recompute",
        "summarize_structure_two_comparison_audit.py",
        "--bundle",
        comparison,
        "--verify",
    )
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
        "comparison_generate": comparison_files,
        "attribution_generate": (str(Path(comparison) / "attribution.json"),),
        "attribution_recompute": (comparison,),
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
    return [Stage(s.name, s.argv, s.junit, freeze_by_stage.get(s.name, ())) for s in stages]


def interrupted(_signum, _frame):
    raise InterruptedError("coordinator interrupted; a new full run is required")


def main():
    check_entry()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--unified-root", type=Path)
    parser.add_argument("--expected-head")
    parser.add_argument("--expected-input-sha256")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--inspect-run", type=Path)
    args = parser.parse_args()
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
