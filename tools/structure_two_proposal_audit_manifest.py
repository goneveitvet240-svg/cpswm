"""Seal existing audit artifacts and verify no production edits against tested SHA."""

import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/reviews/pc_a/proposal_two_round_audit_2026-09-13"
BASE = "5ec6204dfecc9137523b6c0e5dfb66658e574d41"
changes = subprocess.check_output(
    [
        "git",
        "diff",
        "--name-only",
        BASE,
        "--",
        "src",
        "tools/structure_two_prepare_proposals.py",
        "tools/structure_two_procthor_pilot.py",
        "tests/test_structure_two_proposal_scheduler.py",
    ],
    cwd=ROOT,
    text=True,
).splitlines()
assert not changes, changes
before = json.loads((OUT / "run_03/receipt.json").read_text())
assert before["source_unchanged"]
for name, expected in before["source_after"].items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
results = {}
for name in ("baseline", "round1", "round2"):
    suite = ET.parse(OUT / f"run_03/{name}.xml").getroot().find("testsuite")
    results[name] = {
        key: int(suite.attrib[key]) for key in ("tests", "failures", "errors", "skipped")
    }
artifact_hashes = {
    str(p.relative_to(OUT)): hashlib.sha256(p.read_bytes()).hexdigest()
    for p in sorted(OUT.rglob("*"))
    if p.is_file() and p.name != "manifest.json"
}
receipt = {
    "tested_base": BASE,
    "production_path_changes": changes,
    "final_audit_source_matches_receipt": True,
    "test_results": results,
    "artifact_count": len(artifact_hashes),
    "artifact_sha256": artifact_hashes,
    "verdict": "CHANGES_REQUIRED",
    "production_fixes_applied": False,
}
with (OUT / "manifest.json").open("x") as stream:
    json.dump(receipt, stream, indent=2)
print(json.dumps({k: v for k, v in receipt.items() if k != "artifact_sha256"}))
