"""Capture present interpreters and already fetched remote refs; read-only."""

import hashlib
import json
import subprocess
import time
from pathlib import Path

out = Path(__file__).resolve().parent
repo = out.parents[3]
code = (
    "import sys,json,importlib.metadata as m; "
    "print(json.dumps(dict(executable=sys.executable,prefix=sys.prefix,version=sys.version,"
    'packages=sorted((d.metadata["Name"],d.version) for d in m.distributions()))))'
)
result = {"captured_at": time.time(), "environments": {}, "remote_refs": {}}
for label, python in (
    ("w1", "/private/tmp/cpswm-pc-a-review6-w1.2dQj1v/.venv/bin/python"),
    (
        "w2_w3",
        "/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python",
    ),
):
    result["environments"][label] = json.loads(
        subprocess.check_output([python, "-c", code], text=True)
    )
    result["environments"][label]["binary_sha256"] = hashlib.sha256(
        Path(python).resolve().read_bytes()
    ).hexdigest()
for branch in (
    "codex/dual-pc-handoff-20260912",
    "codex/snapshot-w1-20260912",
    "codex/snapshot-w2-20260912",
    "codex/snapshot-w3-r6-20260912",
):
    result["remote_refs"][branch] = subprocess.check_output(
        ["git", "rev-parse", "origin/" + branch], cwd=repo, text=True
    ).strip()
result["probe_preservation"] = (
    hashlib.sha256((out / "w3_original_independent_probe.py.source.txt").read_bytes()).hexdigest()
    == hashlib.sha256(
        Path(
            "/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/docs/reviews/data/structure_two_three_windows_round5_review_2026-09-12/w3_independent_prepared_probes.py"
        ).read_bytes()
    ).hexdigest()
)
(out / "environment_and_refs.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps({k: v for k, v in result.items() if k != "environments"}, indent=2))
