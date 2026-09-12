"""Audit the concrete window-three delivery without writing to it."""
import hashlib
import json
import subprocess
from pathlib import Path

original = Path("/private/tmp/s2-w3-native")
snapshot = Path("/private/tmp/s2-review4-w3.cwwAVs")
manifest_path = original / "docs/reviews/data/w3_repair_2026-09-12_r4/bound_verified/manifest.json"
manifest = json.loads(manifest_path.read_text())
expected = manifest["source_before"]

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

out = {
    "original": str(original), "snapshot": str(snapshot),
    "original_head": subprocess.check_output(["git","rev-parse","HEAD"], cwd=original, text=True).strip(),
    "snapshot_head": subprocess.check_output(["git","rev-parse","HEAD"], cwd=snapshot, text=True).strip(),
    "manifest_sha256": sha(manifest_path),
    "expected_file_count": len(expected),
    "expected_file_map_sha256": hashlib.sha256(json.dumps(expected, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
    "declared_source_before_after_equal": expected == manifest["source_after"],
    "original_mismatches": [p for p, h in expected.items() if not (original/p).is_file() or sha(original/p) != h],
    "snapshot_mismatches": [p for p, h in expected.items() if not (snapshot/p).is_file() or sha(snapshot/p) != h],
    "actual_snapshot_python_file_count": len([p for base in ("src", "tests") for p in (snapshot/base).rglob("*.py")]),
    "original_status": subprocess.check_output(["git","status","--short"], cwd=original, text=True),
}
print(json.dumps(out, indent=2))
