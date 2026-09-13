"""Archive selected simulator evidence; never publish Editor licensing logs or binaries."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--run", action="append", default=[], type=Path)
    parser.add_argument("--snapshot", action="append", default=[], type=Path)
    parser.add_argument("--build", action="append", default=[], type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = {}

    def store(relative, data, compressed=False):
        path = args.output / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        encoded = gzip.compress(data, mtime=0) if compressed else data
        with path.open("xb") as stream:
            stream.write(encoded)
        manifest[relative] = {
            "sha256": sha(encoded),
            "original_sha256": sha(data),
            "original_bytes": len(data),
            "gzip": compressed,
        }

    for run in args.run:
        for path in sorted(run.rglob("*")):
            if "unity_logs" in path.parts or not path.is_file():
                continue
            if path.name not in ("receipt.json", "transport.jsonl", "trace_summary.json"):
                continue
            relative = f"runs/{run.name}/{path.relative_to(run)}"
            compressed = path.suffix == ".jsonl" or path.name == "trace_summary.json"
            store(relative + (".gz" if compressed else ""), path.read_bytes(), compressed)
    for path in args.snapshot:
        store(f"inputs/{path.name}.gz", path.read_bytes(), True)
    for directory in args.build:
        receipt = directory / "unity-result.json"
        data = json.loads(receipt.read_text())
        application = Path(data["outputPath"])
        if application.resolve().parent != directory.resolve():
            raise ValueError("Build receipt points outside the specified build directory")
        files = {}
        for path in sorted(application.rglob("*")):
            if path.is_symlink():
                files[str(path.relative_to(application))] = {"symlink": str(path.readlink())}
            elif path.is_file():
                with path.open("rb") as stream:
                    digest = hashlib.file_digest(stream, "sha256").hexdigest()
                files[str(path.relative_to(application))] = {
                    "sha256": digest,
                    "bytes": path.stat().st_size,
                }
        store(f"builds/{directory.name}/unity-result.json", receipt.read_bytes())
        store(f"builds/{directory.name}/artifact-files.json", json.dumps(files, indent=2).encode())
    store(
        "scope.json",
        json.dumps(
            {
                "human_execution_verified": False,
                "training_started": False,
                "raw_editor_license_logs_published": False,
                "binary_payloads_published": False,
                "tests_are_author_partial_audits": True,
            },
            indent=2,
        ).encode(),
    )
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps({"archived_files": len(manifest), "output": str(args.output)}))


if __name__ == "__main__":
    main()
