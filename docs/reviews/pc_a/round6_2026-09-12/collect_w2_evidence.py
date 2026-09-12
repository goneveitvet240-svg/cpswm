"""Archive this review's real attack inputs after pytest completes, not old ones."""

import hashlib
import json
import shutil
import tarfile
from pathlib import Path

out = Path(__file__).resolve().parent
root = Path("/private/tmp/cpswm-pc-a-review6-w2.pfIMZc")
temp = Path(
    "/private/var/folders/x2/000r8p0n6s393lj2sg8wk5f40000gn/T/pytest-of-pangwei/pytest-1756"
)
command = json.loads((out / "w2_77.command.json").read_text())
assert command["exit_code"] == 0
dest = out / "w2_evidence"
dest.mkdir()
index = {}
for parent in (temp, root / "source-evidence"):
    for path in parent.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        if parent == temp and not any(n in path.parts for n in ("source-evidence", "evidence")):
            continue
        if path.suffix not in (".json", ".log"):
            continue
        rel = Path("temporary" if parent == temp else "source") / path.relative_to(parent)
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        index[str(rel)] = {
            "original": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
matrix_names = ("adversarial_matrix.json", "fairness_forgery_matrix.json", "matrix.json")
counts = (21, 6, 4)
bundles = []
matrices = []
for name, count in zip(matrix_names, counts, strict=True):
    found = list(dest.rglob(name))
    assert len(found) == 1, (name, found)
    result = json.loads(found[0].read_text())["result"]
    records = result["results"]
    assert result["fresh_replay_performed"] is True
    assert len(records) == count + 1
    assert records[0]["status"] == "CURRENT_SOURCE_FRESH_REPLAY_MATCH"
    assert records[0]["formal_scientific_verification"] is False
    assert records[0]["steps"] == 1920
    for row in records[1:]:
        assert row["status"] == "REJECTED" and row["error"]
        path = Path(row["bundle"])
        assert path.is_relative_to(temp) and path.is_dir()
        bundles.append(path)
    matrices.append(
        {"path": str(found[0].relative_to(out)), "positive": records[0], "rejected": count}
    )
archive = out / "w2_actual_attack_packages.tar.gz"
package_files = {}
with tarfile.open(archive, "x:gz") as tar:
    for bundle in bundles:
        for path in sorted(bundle.rglob("*")):
            assert not path.is_symlink()
            if path.is_file():
                rel = str(path.relative_to(temp))
                package_files[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
                tar.add(path, arcname=rel, recursive=False)
source_records = list(dest.rglob("source-evidence/*.json")) + list((dest / "source").glob("*.json"))
assert len(source_records) == 16, len(source_records)
summary = {
    "command": command,
    "matrices": matrices,
    "source_records": len(source_records),
    "evidence_files": index,
    "package_count": len(bundles),
    "package_files": package_files,
    "archive": archive.name,
    "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
    "archive_bytes": archive.stat().st_size,
    "old_historical_packages_reconstructed": False,
}
(out / "w2_evidence_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print(
    json.dumps(
        {
            k: v
            for k, v in summary.items()
            if k not in ("command", "evidence_files", "package_files")
        },
        indent=2,
    )
)
