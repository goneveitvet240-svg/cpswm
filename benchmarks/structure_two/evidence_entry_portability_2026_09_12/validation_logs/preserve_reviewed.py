"""Capture reviewed bytes without altering any reviewed evidence."""

import hashlib
import json
import subprocess
from pathlib import Path

root = Path.cwd()
base = "816a88b242c24b9c6ace6021bba23e4b5b8b526e"
out = root / "benchmarks/structure_two/evidence_entry_portability_2026_09_12"
paths = subprocess.check_output(
    [
        "git",
        "ls-tree",
        "-r",
        "--name-only",
        base,
        "benchmarks/structure_two/evidence_repair_2026_09_11",
        "benchmarks/structure_two/evidence_repair_supplement_2026_09_11",
        "benchmarks/structure_two/engineering_trust_checkpoint_2026_09_11_v0_2",
        "benchmarks/structure_two/engineering_trust_checkpoint_2026_09_05",
    ],
    text=True,
).splitlines()
rows = []
for rel in paths:
    data = subprocess.check_output(["git", "show", base + ":" + rel])
    assert (root / rel).read_bytes() == data, rel
    rows.append({"path": rel, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
for rel, name in [
    ("benchmarks/p0_checkpoint/content_manifest_v0_3.json", "reviewed_p0_manifest.json"),
    (
        "benchmarks/structure_two/structure_two_world_source_bundle_v0_5_compatibility_audit.json",
        "reviewed_v05_compatibility_audit.json",
    ),
]:
    data = subprocess.check_output(["git", "show", base + ":" + rel])
    assert (root / rel).read_bytes() == data
    with (out / name).open("xb") as f:
        f.write(data)
    rows.append(
        {
            "path": rel,
            "preserved_as": str((out / name).relative_to(root)),
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
        }
    )
with (out / "preserved_reviewed_evidence.json").open("x") as f:
    json.dump({"reviewed_commit": base, "entries": rows}, f, indent=2, sort_keys=True)
    f.write("\n")
print(
    json.dumps({"reviewed_commit": base, "preserved_files": len(rows), "matching_git_bytes": True})
)
