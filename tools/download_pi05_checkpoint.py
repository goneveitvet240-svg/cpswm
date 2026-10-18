"""Resumable official GCS checkpoint download with server CRC32C verification."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def main() -> None:
    import google_crc32c

    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    listing = args.output / "official-listing.json"
    subprocess.run(
        [
            "curl",
            "-q",
            "-Lsf",
            "--connect-timeout",
            "15",
            "--max-time",
            "60",
            "https://storage.googleapis.com/storage/v1/b/openpi-assets/o?prefix=checkpoints%2Fpi05_libero%2F&maxResults=500",
            "-o",
            str(listing),
        ],
        check=True,
    )
    data = json.loads(listing.read_text())
    if data.get("nextPageToken") or not data.get("items"):
        raise RuntimeError("unexpected checkpoint listing")

    def fetch(item):
        relative = item["name"].removeprefix("checkpoints/pi05_libero/")
        if relative.startswith("/") or ".." in Path(relative).parts:
            raise ValueError("invalid checkpoint path")
        path = args.output / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or path.stat().st_size != int(item["size"]):
            subprocess.run(
                [
                    "curl",
                    "-q",
                    "-Lsf",
                    "--connect-timeout",
                    "15",
                    "--max-time",
                    "1200",
                    "--retry",
                    "2",
                    "-C",
                    "-",
                    "https://storage.googleapis.com/openpi-assets/"
                    + item["name"]
                    + "?generation="
                    + item["generation"],
                    "-o",
                    str(path),
                ],
                check=True,
            )
        crc, sha = google_crc32c.Checksum(), hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1048576), b""):
                crc.update(chunk)
                sha.update(chunk)
        if (
            path.stat().st_size != int(item["size"])
            or base64.b64encode(crc.digest()).decode() != item["crc32c"]
        ):
            raise RuntimeError(f"checkpoint checksum failed: {relative}")
        print("verified", relative, flush=True)
        return {
            "path": relative,
            "size": path.stat().st_size,
            "sha256": sha.hexdigest(),
            "generation": item["generation"],
            "crc32c": item["crc32c"],
        }

    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = list(pool.map(fetch, data["items"]))
    (args.output / "verified-manifest.json").write_text(json.dumps(receipts, indent=2) + "\n")


if __name__ == "__main__":
    main()
