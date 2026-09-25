"""Fetch only the pinned public auxiliary files needed by this review.

Requires gh for GitHub blob JSON; no executable author code is imported/run.
Use a fresh output directory, then fetch_handover_training_sample.py for videos.
"""

import base64
import hashlib
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = Path(sys.argv[1]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
source = json.loads((ROOT / "PUBLIC_SOURCES.json").read_text())


def save(name, data, digest=None, md5=None):
    if digest and hashlib.sha256(data).hexdigest() != digest:
        raise ValueError("SHA256 differs: " + name)
    if md5 and hashlib.md5(data).hexdigest() != md5:
        raise ValueError("author MD5 differs: " + name)
    dest = OUT / name
    if dest.exists() and dest.read_bytes() != data:
        raise ValueError("different existing file: " + name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)


def download(url, cap=64 * 1024 * 1024):
    with urllib.request.urlopen(url, timeout=40) as response:
        data = response.read(cap + 1)
    if len(data) > cap:
        raise ValueError("public download exceeds bounded file size")
    return data


for row in source["hocap"]:
    name = row["name"] + ".json"
    data = (OUT / name).read_bytes() if (OUT / name).exists() else download(row["url"])
    save(name, data, digest=row["sha256"])
save("ope-receipts.json", (json.dumps(source["hocap"], indent=2) + "\n").encode())
for row in source["rpl"]:
    name = "rpl/" + row["path"]
    if (OUT / name).exists():
        data = (OUT / name).read_bytes()
    else:
        blob = json.loads(
            subprocess.check_output(
                ["gh", "api", f"repos/paragkhanna1/dataset/git/blobs/{row['git_blob']}"], timeout=60
            )
        )
        data = base64.b64decode(blob["content"])
    if hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest() != row["git_blob"]:
        raise ValueError("author Git blob mismatch")
    save(name, data, digest=row["sha256"])
save("rpl/receipts.json", (json.dumps(source["rpl"], indent=2) + "\n").encode())
for name, digest in source["author_metadata"]["md5"].items():
    data = (
        (OUT / name).read_bytes()
        if (OUT / name).exists()
        else download(
            f"https://zenodo.org/records/10708763/files/{name}?download=1", cap=1024 * 1024
        )
    )
    save(name, data, md5=digest.removeprefix("md5:"))
save("handover-record.json", (ROOT / "evidence/handover-record.json").read_bytes())
print("Verified public auxiliary files; fetch the two-trial archive separately.")
