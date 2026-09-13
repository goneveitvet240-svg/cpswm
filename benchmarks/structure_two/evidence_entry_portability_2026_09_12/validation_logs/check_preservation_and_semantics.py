"""Check sealed bytes and unchanged scientific results independently of outer hashes."""

import hashlib
import json
import subprocess
from pathlib import Path

root = Path.cwd()
directory = root / "benchmarks/structure_two/evidence_entry_portability_2026_09_12"
manifest = json.loads((directory / "preserved_reviewed_evidence.json").read_text())
for row in manifest["entries"]:
    path = root / row.get("preserved_as", row["path"])
    data = path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == row["sha256"], str(path)
    assert data == subprocess.check_output(
        ["git", "show", manifest["reviewed_commit"] + ":" + row["path"]]
    ), str(path)
print(
    json.dumps({"preserved_reviewed_files": len(manifest["entries"]), "all_exact_git_bytes": True}),
    flush=True,
)
assert not subprocess.check_output(
    [
        "git",
        "diff",
        manifest["reviewed_commit"],
        "--",
        "configs",
        "src/cpswm/system/prototype_spine.py",
        "src/cpswm/system/continual/project_one_regime_loop.py",
    ]
)
results = []
for path in sorted((directory / "current_v0_4").glob("*.json")):
    old = (
        root
        / "benchmarks/structure_two/evidence_repair_supplement_2026_09_11/current_v0_3"
        / path.name.replace("_v0_4.json", "_v0_3.json")
    )
    previous = json.loads(old.read_text())
    current = json.loads(path.read_text())
    for value in (previous, current):
        for key in ("source_binding", "evidence_context", "content_sha256"):
            value.pop(key)
    assert json.dumps(previous, sort_keys=True) == json.dumps(current, sort_keys=True), path.name
    results.append(
        {
            "path": str(path.relative_to(root)),
            "scientific_fields_equal_reviewed_v0_3": True,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    )
assert len(results) == 5
print(
    json.dumps({"current_results": results, "scientific_configuration_unchanged": True}), flush=True
)
