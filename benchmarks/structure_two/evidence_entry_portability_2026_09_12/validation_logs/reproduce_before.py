"""Read-only baseline reproduction using a disposable copy, never reviewer trees."""

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

root = pathlib.Path.cwd()
copy = pathlib.Path(tempfile.mkdtemp(prefix="w1-entry-before-", dir="/private/tmp"))
for name in ("src", "apps", "configs"):
    shutil.copytree(root / name, copy / name, ignore=shutil.ignore_patterns("__pycache__"))
for name in ("conftest.py", "pyproject.toml", "uv.lock"):
    shutil.copy2(root / name, copy / name)
history = pathlib.Path("benchmarks/structure_two/evidence_repair_2026_09_11/history")
shutil.copytree(root / history, copy / history)
for name in ("three_arm_death_test", "readout_posthoc_diagnostic"):
    rel = pathlib.Path(f"benchmarks/structure_two/structure_two_p5_{name}_v0_1.json")
    shutil.copy2(root / rel, copy / rel)
common = subprocess.check_output(["git", "rev-parse", "--git-common-dir"], text=True).strip()
env = {**os.environ, "GIT_DIR": str((root / common).resolve()), "PYTHONPATH": str(copy / "src")}
entry = copy / "apps/evaluation_runner/probe_structure_two_execution_source.py"
original = entry.read_bytes()
entry.write_bytes(
    original.replace(
        b'"diagnostic_only": True,', b'"diagnostic_only": True, "stale_entry_executed": True,'
    )
)
subprocess.run(
    [
        sys.executable,
        "-c",
        "import py_compile,sys; py_compile.compile(sys.argv[1],doraise=True,"
        "invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)",
        str(entry),
    ],
    check=True,
)
entry.write_bytes(original)
for label, args in [
    ("stale_module", ["-m", "apps.evaluation_runner.probe_structure_two_execution_source"]),
    ("normal_file", ["apps/evaluation_runner/probe_structure_two_execution_source.py"]),
]:
    p = subprocess.run([sys.executable, *args], cwd=copy, env=env, text=True, capture_output=True)
    print(
        json.dumps(
            {
                "case": label,
                "argv": p.args,
                "cwd": str(copy),
                "exit_code": p.returncode,
                "stdout": p.stdout,
                "stderr": p.stderr,
                "disk_entry_matches": entry.read_bytes() == original,
            }
        ),
        flush=True,
    )
    assert p.returncode == 0
    assert json.loads(p.stdout).get("stale_entry_executed", False) == (label == "stale_module")
report = (
    root / "benchmarks/structure_two/evidence_repair_supplement_2026_09_11/"
    "historical_source_audit_v0_2.json"
)
p = subprocess.run(
    [
        sys.executable,
        "apps/evaluation_runner/audit_structure_two_evidence_history.py",
        "--verify",
        str(report),
    ],
    cwd=copy,
    env=env,
    text=True,
    capture_output=True,
)
print(
    json.dumps(
        {
            "case": "cross_root_full_history",
            "argv": p.args,
            "cwd": str(copy),
            "exit_code": p.returncode,
            "stdout": p.stdout,
            "stderr": p.stderr,
        }
    ),
    flush=True,
)
assert p.returncode != 0 and "historical source audit differs" in p.stderr
rows = [json.loads(line) for line in p.stdout.splitlines()]
assert len(rows) == 11 and sum(r["numerical_recomputation_performed"] for r in rows) == 1
print(json.dumps({"before_reproductions_confirmed": True, "copy": str(copy)}))
