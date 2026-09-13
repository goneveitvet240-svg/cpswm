"""Validate every completed stream without treating hashes as independent custody."""

import gzip
import hashlib
import json
from pathlib import Path

root = Path.cwd()
base = root / "benchmarks/structure_two/evidence_entry_portability_2026_09_12/validation_logs"
rows = [json.loads(line) for line in (base / "commands.jsonl").read_text().splitlines()]
assert len({r["name"] for r in rows}) == len(rows)
streams = 0
for row in rows:
    assert type(row["exit_code"]) is int and row["end"] >= row["start"]
    for key in ("stdout", "stderr"):
        stream = row[key]
        data = gzip.decompress((root / stream["path"]).read_bytes())
        assert hashlib.sha256(data).hexdigest() == stream["uncompressed_sha256"], (row["name"], key)
        streams += 1
receipt_path = (
    root / "benchmarks/structure_two/engineering_trust_checkpoint_2026_09_12_v0_3/"
    "engineering_audit_receipt.json"
)
native = 0
if receipt_path.exists():
    receipt = json.loads(receipt_path.read_text())
    for run in receipt["command_runs"]:
        for key in ("stdout", "stderr"):
            data = (root / run[key + "_path"]).read_bytes()
            assert hashlib.sha256(data).hexdigest() == run[key + "_sha256"], (
                run["command_id"],
                key,
            )
            native += 1
print(
    json.dumps(
        {
            "completed_logged_commands": len(rows),
            "verified_compressed_streams": streams,
            "verified_native_streams": native,
            "scope": "local_byte_integrity_not_independent_custody",
        }
    )
)
