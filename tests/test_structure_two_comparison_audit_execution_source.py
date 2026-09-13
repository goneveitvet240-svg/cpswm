"""Real CLI origin attacks; no replay mocks or caller-provided references."""

from __future__ import annotations

import hashlib
import json
import os
import py_compile
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from structure_two_comparison_audit_adversary import build_attack

from cpswm.system.evaluation_operations import structure_two_comparison_audit as audit

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = Path(os.environ.get("S2_AUDIT_BUNDLE", str(ROOT / "not-generated-round3-bundle")))
DIAGNOSTIC = Path("src/cpswm/system/evaluation_operations/structure_two_comparison_audit.py")
CLI_NAMES = {
    "main": "run_structure_two_comparison_audit.py",
    "attribution": "summarize_structure_two_comparison_audit.py",
}


def mirror(target):
    shutil.copytree(ROOT / "src", target / "src", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(ROOT / "configs", target / "configs")
    app = target / "apps/evaluation_runner"
    app.mkdir(parents=True)
    for name in (*CLI_NAMES.values(), "_structure_two_audit_source.py"):
        shutil.copy2(ROOT / "apps/evaluation_runner" / name, app / name)
    (target / audit.HISTORY).parent.mkdir(parents=True)
    shutil.copy2(ROOT / audit.HISTORY, target / audit.HISTORY)
    return target


def arguments(kind, bundle=BUNDLE):
    if kind == "main":
        return [
            "--output",
            str(bundle),
            "--verify",
            "--timing-repeats",
            "1",
            "--timing-episodes",
            "1",
        ]
    return ["--bundle", str(bundle), "--verify"]


def invoke(root, kind, args, *, pythonpath=None, wrapper=None, evidence_name):
    cli = root / "apps/evaluation_runner" / CLI_NAMES[kind]
    if wrapper:
        command = [sys.executable, "-c", wrapper, str(cli), *args]
    else:
        command = [sys.executable, str(cli), *args]
    env = {**os.environ, "PYTHONPATH": str(pythonpath or root / "src")}
    result = subprocess.run(
        command, cwd=root, env=env, capture_output=True, text=True, timeout=3600
    )
    evidence = Path(os.environ.get("S2_SOURCE_EVIDENCE_DIR", str(root / "source-evidence")))
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / f"{evidence_name}.log").write_text(result.stdout + result.stderr)
    (evidence / f"{evidence_name}.json").write_text(
        json.dumps(
            {
                "command": command,
                "cwd": str(root),
                "PYTHONPATH": env["PYTHONPATH"],
                "exit_code": result.returncode,
                "stdout_json": [
                    json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")
                ],
            },
            indent=2,
        )
        + "\n"
    )
    return result


def rejected(result, reason):
    assert result.returncode != 0, result.stdout
    assert reason in result.stdout + result.stderr, result.stdout + result.stderr
    # A batch exit 1 is insufficient: inspect every positive statement.
    assert '"status": "CURRENT_SOURCE_FRESH_REPLAY_MATCH"' not in result.stdout
    assert '"verified":' not in result.stdout
    assert '"status": "FILE_CONSISTENCY_ONLY"' not in result.stdout


@pytest.mark.parametrize("mode", ["main", "attribution_single", "attribution_mixed"])
def test_cross_tree_current_bound_forgery_is_never_certified(tmp_path, mode):
    assert BUNDLE.exists(), "generate the current round3 bundle first"
    b = mirror(tmp_path / "B")
    path = b / DIAGNOSTIC
    path.write_text(
        path.read_text().replace(
            "name: len(getattr(core, name))",
            "name: 999 if name == '_committed_events' else len(getattr(core, name))",
        )
    )
    forged = tmp_path / "forged"
    build_attack(BUNDLE, forged, "r1_commits_999", ROOT)
    # All declared current-source bindings, semantic hashes and attribution are fresh.
    audit.check_source_binding(audit.load_bundle(forged), ROOT)
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in forged.iterdir()}
    kind = "main" if mode == "main" else "attribution"
    args = arguments(kind, forged)
    if mode == "attribution_mixed":
        args.extend(["--bundle", str(BUNDLE)])
    result = invoke(ROOT, kind, args, pythonpath=b / "src", evidence_name=mode)
    rejected(result, "LOCAL_IMPORT_ORIGIN_MISMATCH")
    assert before == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in forged.iterdir()}


@pytest.mark.parametrize("kind", CLI_NAMES)
def test_only_downstream_source_symlink_to_foreign_tree(tmp_path, kind):
    a = mirror(tmp_path / "A")
    downstream = Path("src/cpswm/system/reproducibility.py")
    b = tmp_path / "foreign_dependency.py"
    b.write_text((a / downstream).read_text() + "\nFOREIGN_DEPENDENCY = True\n")
    (a / downstream).unlink()
    (a / downstream).symlink_to(b)
    result = invoke(a, kind, arguments(kind), evidence_name=f"downstream_symlink_{kind}")
    rejected(result, "LOCAL_SOURCE_SYMLINK")


def test_repository_root_cannot_declare_another_execution_tree(tmp_path):
    other = mirror(tmp_path / "B")
    result = invoke(
        ROOT,
        "main",
        [*arguments("main"), "--repository-root", str(other)],
        evidence_name="repository_root_mismatch",
    )
    rejected(result, "REPOSITORY_ROOT_MISMATCH")


@pytest.mark.parametrize("kind", CLI_NAMES)
def test_preloaded_old_module_with_restored_current_source(tmp_path, kind):
    a = mirror(tmp_path / "A")
    wrapper = """
import hashlib, json, pathlib, runpy, sys
root = pathlib.Path(sys.argv[1]).resolve().parents[2]
path = root / "src/cpswm/system/evaluation_operations/structure_two_comparison_audit.py"
current = path.read_bytes()
path.write_bytes(current.replace(b"name: len(getattr(core, name))", b"name: 314159"))
try:
    from cpswm.system.evaluation_operations import structure_two_comparison_audit as loaded
    old_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    print(json.dumps({"preloaded": loaded.__file__, "old_source_sha256": old_sha}))
finally:
    path.write_bytes(current)
sys.argv = sys.argv[1:]
runpy.run_path(sys.argv[0], run_name="__main__")
"""
    result = invoke(
        a, kind, arguments(kind), wrapper=wrapper, evidence_name=f"preloaded_old_{kind}"
    )
    rejected(result, "PRELOADED_LOCAL_MODULES")


@pytest.mark.parametrize("kind", CLI_NAMES)
def test_preloaded_foreign_downstream_without_top_audit_import(tmp_path, kind):
    b = mirror(tmp_path / "B")
    dependency = b / "src/cpswm/system/reproducibility.py"
    dependency.write_text(
        dependency.read_text() + '\ndef content_sha256(value):\n    return "b" * 64\n'
    )
    wrapper = f"""
import json, runpy, sys
sys.path.insert(0, {str(b / "src")!r})
import cpswm.system.reproducibility as loaded
audit_name = "cpswm.system.evaluation_operations.structure_two_comparison_audit"
print(json.dumps({{"preloaded": loaded.__file__, "audit_preloaded": audit_name in sys.modules}}))
sys.path.pop(0)
sys.argv = sys.argv[1:]
runpy.run_path(sys.argv[0], run_name="__main__")
"""
    result = invoke(
        ROOT, kind, arguments(kind), wrapper=wrapper, evidence_name=f"preloaded_downstream_{kind}"
    )
    rejected(result, "PRELOADED_LOCAL_MODULES")


@pytest.mark.parametrize("kind", CLI_NAMES)
def test_source_drift_after_input_binding_before_replay_fails_closed(tmp_path, kind):
    a = mirror(tmp_path / "A")
    wrapper = """
import json, pathlib, runpy, sys
root = pathlib.Path(sys.argv[1]).resolve().parents[2]
def drift(frame, event, arg):
    if event == "return" and frame.f_code.co_name == "check_source_binding":
        sys.setprofile(None)
        path = root / "src/cpswm/system/reproducibility.py"
        path.write_text(path.read_text() + "\\n# controlled in-flight source drift\\n")
        print(json.dumps({"drift_after_real_binding_check": str(path)}))
sys.setprofile(drift)
sys.argv = sys.argv[1:]
runpy.run_path(sys.argv[0], run_name="__main__")
"""
    result = invoke(
        a, kind, arguments(kind), wrapper=wrapper, evidence_name=f"runtime_drift_{kind}"
    )
    rejected(result, "EXECUTION_SOURCE_DRIFT")


@pytest.mark.parametrize("kind", CLI_NAMES)
def test_stale_entry_code_rejected_against_declared_cli_source(tmp_path, kind):
    a = mirror(tmp_path / "A")
    wrapper = """
import pathlib, sys
path = pathlib.Path(sys.argv[1]).resolve()
old_code = compile(path.read_bytes(), str(path), "exec", dont_inherit=True)
path.write_text(path.read_text() + "\\nSOURCE_VERSION_CHANGED = True\\n")
sys.argv = sys.argv[1:]
exec(old_code, {"__file__": str(path), "__name__": "__main__"})
"""
    result = invoke(a, kind, arguments(kind), wrapper=wrapper, evidence_name=f"stale_entry_{kind}")
    rejected(result, "CLI_CODE_DIFFERS_FROM_SOURCE")


@pytest.mark.parametrize("kind", CLI_NAMES)
def test_real_full_positive_compiles_source_ignoring_poisoned_unchecked_pyc(tmp_path, kind):
    assert BUNDLE.exists(), "generate current round3 bundle first"
    a = mirror(tmp_path / "A")
    path = a / DIAGNOSTIC
    raw = path.read_bytes()
    path.write_text("raise RuntimeError('STALE_BYTECODE_EXECUTED')\n")
    py_compile.compile(
        str(path), doraise=True, invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH
    )
    path.write_bytes(raw)
    result = invoke(a, kind, arguments(kind), evidence_name=f"full_positive_stale_pyc_{kind}")
    assert result.returncode == 0, result.stdout + result.stderr
    response = json.loads(result.stdout.splitlines()[-1])
    identity = response["execution_source"]
    assert identity["local_bytecode_cache_used"] is False
    assert identity["declared_root"] == str(a)
    record = identity["loaded_modules"][
        "cpswm.system.evaluation_operations.structure_two_comparison_audit"
    ]
    assert record["source_sha256"] == hashlib.sha256(raw).hexdigest()
    assert len(identity["loaded_modules"]) > 1
    if kind == "attribution":
        assert response["results"][0]["status"] == "CURRENT_SOURCE_FRESH_REPLAY_MATCH"
    else:
        assert response["verified"] == str(BUNDLE.resolve())
