import hashlib
import json
import tarfile
from pathlib import Path

out = Path(
    "/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/output/ci-action-report-20260930"
)
evidence = Path(
    "/private/tmp/cpswm-pc-a-ci-action-report-20260930/docs/reviews/pc_a/ci_action_report_2026-09-30/evidence"
)
evidence.mkdir(exist_ok=True)
files = sorted(
    p
    for p in out.rglob("*")
    if p.is_file() and "__pycache__" not in p.parts and ".pytest_cache" not in p.parts
)
records = [
    {
        "path": str(p.relative_to(out)),
        "bytes": p.stat().st_size,
        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
    }
    for p in files
]
archive = evidence / "evidence.tar.gz"
with tarfile.open(archive, "w:gz") as tar:
    for p in files:
        tar.add(p, arcname=p.relative_to(out), recursive=False)
with tarfile.open(archive, "r:gz") as tar:
    assert len(tar.getmembers()) == len(records)
    for r in records:
        f = tar.extractfile(r["path"])
        assert f is not None
        b = f.read()
        assert len(b) == r["bytes"] and hashlib.sha256(b).hexdigest() == r["sha256"]
summary = {
    "source_sha": "c87b6bb1e3c72986afe517f7f29ebf3d028f2283",
    "files": len(files),
    "raw_bytes": sum(r["bytes"] for r in records),
    "archive_bytes": archive.stat().st_size,
    "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
    "all_members_readback_verified": True,
    "excluded_derived_caches": ["__pycache__", ".pytest_cache"],
    "ongoing_remote_ci_not_sealed_as_completed": True,
}
(evidence / "inventory.json").write_text(json.dumps(records, indent=2) + "\n")
(evidence / "archive.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary))
