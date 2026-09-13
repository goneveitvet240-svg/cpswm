"""Record real Unity build inputs, including generated assets, without account logs."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def sha256(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def snapshot(source: Path) -> dict:
    source = source.resolve(strict=True)
    roots = [source / "unity" / name for name in ("Assets", "Packages", "ProjectSettings")]
    files = {}
    for root in roots:
        if not root.is_dir() or root.is_symlink():
            raise ValueError(f"Missing or symlinked input root: {root.name}")
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                raise ValueError("Symlinked build inputs require separate provenance review")
            if path.is_file():
                before = path.stat()
                digest = sha256(path)
                after = path.stat()
                if (before.st_size, before.st_mtime_ns, before.st_ino) != (
                    after.st_size,
                    after.st_mtime_ns,
                    after.st_ino,
                ):
                    raise RuntimeError("Input changed during hashing; retry after import completes")
                files[path.relative_to(source).as_posix()] = {
                    "sha256": digest,
                    "bytes": after.st_size,
                }
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    status = subprocess.check_output(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"], cwd=source, text=True
    )
    return {
        "schema": "cpswm-unity-input-snapshot@1",
        "source": str(source),
        "revision": revision,
        "git_status": status,
        "files": files,
        "file_count": len(files),
        "snapshot_is_not_runtime_acceptance": True,
        "scope": "Assets, Packages and ProjectSettings; not Library caches or installed toolchain",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    source = args.source.resolve(strict=True)
    if source == output or source in output.parents:
        raise ValueError("Snapshot output must be outside the source checkout")
    result = snapshot(source)
    with output.open("x") as destination:
        json.dump(result, destination, indent=2)
    print(json.dumps({"output": str(output), "file_count": result["file_count"]}))


if __name__ == "__main__":
    main()
