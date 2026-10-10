"""Read-only file and archive integrity verification; no evidence regeneration."""

import hashlib
import json
import tarfile
from pathlib import Path

root = Path(__file__).resolve().parent
manifest = json.loads((root / "manifest.json").read_text())
for name, expected in manifest.items():
    payload = (root / name).read_bytes()
    assert len(payload) == expected["bytes"]
    assert hashlib.sha256(payload).hexdigest() == expected["sha256"], name
count = 0
for name, expected in json.loads((root / "archive-members.json").read_text()).items():
    with tarfile.open(root / name) as archive:
        assert [x.name for x in archive.getmembers()] == sorted(expected)
        for item in archive.getmembers():
            assert item.isfile() and not Path(item.name).is_absolute()
            assert ".." not in Path(item.name).parts
            payload = archive.extractfile(item).read()
            assert len(payload) == expected[item.name]["bytes"]
            assert hashlib.sha256(payload).hexdigest() == expected[item.name]["sha256"]
            count += 1
print(json.dumps({"files": len(manifest), "archive_members": count, "status": "PASS"}))
