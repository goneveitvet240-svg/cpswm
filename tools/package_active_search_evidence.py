"""Archive raw runs, verify every member, and rescore extracted originals."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tarfile
import tempfile
from pathlib import Path

from check_active_search_artifacts import check
from score_active_location_search import read, verify
from summarize_active_search_value import summarize


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def package(main, repeat, output, root):
    output.mkdir(parents=True, exist_ok=False)
    manifest = {}
    for label, folder in (("main", main), ("repeat", repeat)):
        archive = output / f"raw-{label}.tar.gz"
        files = sorted(p for p in folder.rglob("*") if p.is_file())
        members = {
            str(p.relative_to(folder)): {"size": p.stat().st_size, "sha256": sha(p)} for p in files
        }
        with tarfile.open(archive, "w:gz") as tar:
            for p in files:
                tar.add(p, arcname=str(p.relative_to(folder)), recursive=False)
        manifest[archive.name] = {
            "sha256": sha(archive),
            "size": archive.stat().st_size,
            "raw_size": sum(v["size"] for v in members.values()),
            "members": members,
        }
    matched = 0
    rescored = []
    with tempfile.TemporaryDirectory(prefix="active-search-extracted-") as name:
        extracted = Path(name)
        for archive_name, info in manifest.items():
            dest = extracted / archive_name.removesuffix(".tar.gz")
            dest.mkdir()
            with tarfile.open(output / archive_name) as tar:
                assert set(tar.getnames()) == set(info["members"])
                tar.extractall(dest, filter="data")
            for member, expected in info["members"].items():
                p = dest / member
                assert p.stat().st_size == expected["size"] and sha(p) == expected["sha256"]
                matched += 1
        a, b = extracted / "raw-main", extracted / "raw-repeat"
        for condition in ("dev-sparse32", "test-complete32", "test-sparse32", "test-long64"):
            value = verify(a / condition, root)
            name = f"{condition}-score.json"
            assert (json.dumps(value, indent=2, sort_keys=True) + "\n").encode() == (
                a / name
            ).read_bytes()
            rescored.append(name)
        checks = check(a / "test-sparse32", b / "sparse32", root)
        assert checks == read(a / "artifact-checks.json")
        assert summarize(a, root) == read(a / "combined.json")
        rescored.extend(("artifact-checks.json", "combined.json"))
    for name in (*rescored,):
        shutil.copy2(main / name, output / name)
    save(output / "MANIFEST.json", manifest)
    value = {
        "verified_members": matched,
        "exact_rescoring_outputs": rescored,
        "archives": {
            k: {field: v[field] for field in ("sha256", "size", "raw_size")}
            for k, v in manifest.items()
        },
        "scope": "A-machine archive integrity and deterministic rescoring, not B acceptance",
    }
    save(output / "ARCHIVE_VERIFY.json", value)
    return value


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--main", type=Path, required=True)
    p.add_argument("--repeat", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    print(
        json.dumps(
            package(args.main, args.repeat, args.output, Path(__file__).resolve().parents[1])
        )
    )
