"""Record independent review commands; no repair or scientific authorization."""

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
PY = "/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python"
ROOTS = {
    "w1": Path("/private/tmp/cpswm-pc-a-review6-w1.2dQj1v"),
    "w2": Path("/private/tmp/cpswm-pc-a-review6-w2.pfIMZc"),
    "w3": Path("/private/tmp/cpswm-pc-a-review6-w3.3ZZ6oR"),
}
BASELINE = Path("/private/tmp/s2-review5-w3.o33e1p")
ORIGINALS = {
    "w1": Path("/private/tmp/cpswm-s2-evidence-repair-window1"),
    "w2": Path("/private/tmp/s2-comparison-audit-window2-20260911"),
    "w3": Path("/private/tmp/s2-w3-native"),
}


def hashes(root):
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for top in ("src", "tests", "configs", "apps", "tools")
        for p in sorted((root / top).rglob("*"))
        if p.is_file()
        and "__pycache__" not in p.parts
        and not any(s.endswith(".egg-info") for s in p.parts)
        and p.suffix not in (".pyc", ".pyo")
    }


if sys.argv[1] in ("snapshot", "check"):
    value = {}
    for k, root in ROOTS.items():
        a, b = hashes(root), hashes(ORIGINALS[k])
        value[k] = {
            "root": str(root),
            "head": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=root, text=True
            ).strip(),
            "original_root": str(ORIGINALS[k]),
            "original_head": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ORIGINALS[k], text=True
            ).strip(),
            "files": a,
            "original_source_equal": a == b,
        }
        assert a == b, (k, [p for p in set(a) | set(b) if a.get(p) != b.get(p)])
    if sys.argv[1] == "snapshot":
        with (BASE / "source_binding.json").open("x") as stream:
            json.dump(value, stream, indent=2)
    else:
        old = json.loads((BASE / "source_binding.json").read_text())
        assert value == old
        (BASE / "source_after.json").write_text(
            json.dumps({"all_sources_unchanged": True, "checked_at": time.time()}, indent=2) + "\n"
        )
    print(
        {
            k: {
                "head": v["head"],
                "files": len(v["files"]),
                "original_source_equal": v["original_source_equal"],
            }
            for k, v in value.items()
        }
    )
else:
    window, label = sys.argv[1:3]
    root = BASELINE if window == "w3baseline" else ROOTS[window]
    env = os.environ.copy()
    env.update(
        PYTHONPATH=str(root / "src"),
        PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
        OMP_NUM_THREADS="1",
        OPENBLAS_NUM_THREADS="1",
        VECLIB_MAXIMUM_THREADS="1",
    )
    if window == "w1":
        for name in (
            "PYTHONPATH",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
            "PYTEST_ADDOPTS",
            "PYTEST_PLUGINS",
        ):
            env.pop(name, None)
    if window == "w2":
        env["S2_AUDIT_BUNDLE"] = str(
            root
            / "docs/reviews/data/structure_two_comparison_dynamic_window2_2026-09-12T1500/bundle_v5"
        )
    argv = [str(root / ".venv/bin/python") if window == "w1" else PY, *sys.argv[3:]]
    record = {
        "argv": argv,
        "cwd": str(root),
        "environment": {
            k: env.get(k)
            for k in (
                "PYTHONPATH",
                "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
                "S2_AUDIT_BUNDLE",
                "OMP_NUM_THREADS",
                "OPENBLAS_NUM_THREADS",
                "VECLIB_MAXIMUM_THREADS",
            )
        },
        "started": time.time(),
    }
    with (
        (BASE / (label + ".stdout.log")).open("x") as out,
        (BASE / (label + ".stderr.log")).open("x") as err,
    ):
        result = subprocess.run(argv, cwd=root, env=env, stdout=out, stderr=err)
    record.update(exit_code=result.returncode, ended=time.time())
    (BASE / (label + ".command.json")).write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record))
    print((BASE / (label + ".stdout.log")).read_text()[-2000:])
    print((BASE / (label + ".stderr.log")).read_text()[-1000:])
    sys.exit(result.returncode)
