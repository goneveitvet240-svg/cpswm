"""Independently compare preserved artifact bytes to their reviewed Git commits."""
import hashlib
import json
import subprocess
from pathlib import Path

specs = [
    ("window1", Path("/private/tmp/s2-review4-w1.p5JONv"), "benchmarks/structure_two/evidence_entry_portability_2026_09_12/preserved_reviewed_evidence.json"),
    ("window2", Path("/private/tmp/s2-review4-w2.pdinJv"), "docs/reviews/data/structure_two_comparison_audit_window2_fairness_2026-09-12/preserved_previous_artifacts.json"),
]
out = {}
for name, root, manifest_path in specs:
    manifest = json.loads((root/manifest_path).read_text())
    rows = manifest.get("entries", manifest.get("files"))
    commit = manifest.get("reviewed_commit", manifest.get("reviewed_head"))
    errors = []
    for row in rows:
        retained = root / row.get("preserved_as", row["path"])
        actual = retained.read_bytes()
        expected = subprocess.check_output(["git", "show", commit + ":" + row["path"]], cwd=root)
        if actual != expected or hashlib.sha256(actual).hexdigest() != row["sha256"]:
            errors.append(row["path"])
    out[name] = {
        "root": str(root), "reviewed_commit": commit, "checked": len(rows),
        "preserved_elsewhere": sum("preserved_as" in row for row in rows), "mismatches": errors,
    }
print(json.dumps(out, indent=2))
