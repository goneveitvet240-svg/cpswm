"""Independent W1 review probes, confined to disposable copied fixtures."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

SOURCE = Path(sys.argv[1]).resolve()
MODE = sys.argv[2]

with tempfile.TemporaryDirectory(prefix="s2-w1-counterexample-", dir="/private/tmp") as folder:
    root = Path(folder)
    shutil.copytree(SOURCE / "src", root / "src", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(SOURCE / "configs", root / "configs")
    shutil.copytree(SOURCE / "apps", root / "apps", ignore=shutil.ignore_patterns("__pycache__"))
    for name in ("pyproject.toml", "uv.lock"):
        shutil.copy2(SOURCE / name, root / name)
    common_git = Path(subprocess.check_output(["git", "rev-parse", "--git-common-dir"], cwd=SOURCE, text=True).strip())
    if not common_git.is_absolute():
        common_git = SOURCE / common_git
    environment = {**os.environ, "PYTHONPATH": str(root / "src"), "GIT_DIR": str(common_git.resolve())}

    if MODE in {"late_import", "stale_pyc"}:
        for name in ("three_arm_death_test", "readout_posthoc_diagnostic"):
            relative = Path(f"benchmarks/structure_two/structure_two_p5_{name}_v0_1.json")
            (root / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(SOURCE / relative, root / relative)
        if MODE == "stale_pyc":
            baseline = subprocess.check_output([sys.executable, "-c", "from cpswm.system.continual.project_one_regime_loop import PrototypeLoopConfig; print(PrototypeLoopConfig().owner_evidence_threshold)"], cwd=root, env=environment, text=True).strip()
            source = root / "src/cpswm/system/continual/project_one_regime_loop.py"
            metadata = source.stat()
            text = source.read_text()
            source.write_text(text.replace("owner_evidence_threshold: float = 0.5", "owner_evidence_threshold: float = 0.9", 1))
            os.utime(source, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
            code = '''
import json, subprocess, sys
from pathlib import Path
root = Path.cwd()
from cpswm.system.evaluation_operations.structure_two_p5_three_arm_death_test import _source_binding, _load_config
from cpswm.system.continual.project_one_regime_loop import PrototypeLoopConfig
binding = _source_binding(root, _load_config(root))
clean = subprocess.check_output([sys.executable, "-X", f"pycache_prefix={root / 'fresh-bytecode-cache'}", "-c", "from cpswm.system.continual.project_one_regime_loop import PrototypeLoopConfig; print(PrototypeLoopConfig().owner_evidence_threshold)"], text=True).strip()
print(json.dumps({"fresh_process_with_existing_pyc_threshold": PrototypeLoopConfig().owner_evidence_threshold, "fresh_cache_threshold": float(clean), "p5_source_binding_accepted": True, "current_assembly_sha256": binding["production_assembly_manifest_sha256"]}, indent=2))
'''
        else:
            code = '''
import hashlib, json, subprocess, sys
from pathlib import Path
from cpswm.system.continual.project_one_regime_loop import PrototypeLoopConfig
root = Path.cwd()
version_module = "cpswm.system.evaluation_operations.structure_two_evidence_versions"
assert version_module not in sys.modules
source = root / "src/cpswm/system/continual/project_one_regime_loop.py"
text = source.read_text()
assert "owner_evidence_threshold: float = 0.5" in text
source.write_text(text.replace("owner_evidence_threshold: float = 0.5", "owner_evidence_threshold: float = 0.9", 1))
from cpswm.system.evaluation_operations.structure_two_evidence_versions import require_execution_source
require_execution_source(root)
from cpswm.system.evaluation_operations.structure_two_p5_three_arm_death_test import _source_binding, _load_config
binding = _source_binding(root, _load_config(root))
from cpswm.system.structure_two_production_system import build_production_assembly_manifest
manifest = build_production_assembly_manifest(root)
fresh = subprocess.check_output([sys.executable, "-c", "from cpswm.system.continual.project_one_regime_loop import PrototypeLoopConfig; print(PrototypeLoopConfig().owner_evidence_threshold)"], text=True).strip()
print(json.dumps({"guard_accepted": True, "p5_source_binding_accepted": True, "cached_runtime_threshold": PrototypeLoopConfig().owner_evidence_threshold, "fresh_runtime_threshold": float(fresh), "binding_matches_current_disk_manifest": binding["production_assembly_manifest_sha256"] == manifest["content_sha256"]}, indent=2))
'''
    elif MODE in {"empty_history", "renamed_history"}:
        config = root / "configs/project_two_experiments/structure_two_evidence_history_v0_1.json"
        payload = json.loads(config.read_text())
        if MODE == "empty_history":
            payload["entries"] = []
        else:
            for entry in payload["entries"]:
                if entry["id"] == "three_arm_failed_replay_4103bea":
                    entry["id"] = "three_arm_failed_replay_4103bea_unchecked"
            relative = Path("benchmarks/structure_two/evidence_repair_2026_09_11/history")
            shutil.copytree(SOURCE / relative, root / relative)
        config.write_text(json.dumps(payload))
        report = root / "empty-history.json"
        report.write_text(json.dumps({"protocol": "structure-two-historical-local-git-audit@0.1", "authority": "LOCAL_GIT_AND_EXPLICIT_RECOMPUTATION_ONLY", "first_use_or_unseen_status_established": False, "independent_custody_established": False, "records": []}))
        if MODE == "renamed_history":
            build = subprocess.run([sys.executable, str(root / "apps/evaluation_runner/audit_structure_two_evidence_history.py"), "--recompute-first-failure", "--recompute-failed-replay", "--output", str(report)], cwd=root, env=environment, text=True, capture_output=True)
            if build.returncode:
                print(build.stdout, build.stderr)
                sys.exit(build.returncode)
        for command in (
            [sys.executable, str(root / "apps/evaluation_runner/run_structure_two_evidence_repair.py"), "--verify-history"],
            [sys.executable, str(root / "apps/evaluation_runner/audit_structure_two_evidence_history.py"), "--verify", str(report)],
        ):
            run = subprocess.run(command, cwd=root, env=environment, text=True, capture_output=True)
            print(json.dumps({"command": command[1:], "exit_code": run.returncode, "stdout": run.stdout if MODE == "empty_history" else run.stdout.splitlines()[-1:], "stderr": run.stderr}, indent=2))
        if MODE == "renamed_history":
            final = json.loads(report.read_text())
            print(json.dumps({"record_count": len(final["records"]), "numerical_recomputation_count": sum(row["numerical_recomputation_performed"] for row in final["records"]), "renamed_record_git_bytes_verified": next(row["local_git_bytes_verified"] for row in final["records"] if row["id"].endswith("unchecked"))}, indent=2))
        sys.exit(0)
    elif MODE == "hardlink":
        code = '''
import json, os
from pathlib import Path
from cpswm.system.evaluation_operations.structure_two_evidence_versions import CURRENT_DIRECTORY, require_current_output
root = Path.cwd()
historical = root / "benchmarks/structure_two/old-history.json"
historical.parent.mkdir(parents=True, exist_ok=True)
historical.write_text("historical evidence bytes")
output = root / CURRENT_DIRECTORY / "alias.json"
output.parent.mkdir(parents=True)
os.link(historical, output)
require_current_output(root, output)
# This is the same write primitive used by the CLI after its expensive run.
output.write_text("new current result")
print(json.dumps({"output_guard_accepted": True, "is_symlink": output.is_symlink(), "hardlink_count": output.stat().st_nlink, "historical_bytes_overwritten": historical.read_text() == "new current result"}, indent=2))
'''
    else:
        raise ValueError(MODE)
    completed = subprocess.run([sys.executable, "-c", code], cwd=root, env=environment, text=True, capture_output=True)
    print(completed.stdout, end="")
    print(completed.stderr, end="", file=sys.stderr)
    sys.exit(completed.returncode)
