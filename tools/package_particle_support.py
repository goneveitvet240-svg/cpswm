"""Archive actual runs and rescore extracted copies with independent arithmetic."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tarfile
import tempfile
from pathlib import Path

from check_particle_support import check
from score_particle_support import score


def read(path):
    return json.loads(path.read_text())


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def package(main, repeat, output, repository):
    checks = check(main, repeat, repository)
    assert checks == read(main / "checks.json")
    output.mkdir(parents=True, exist_ok=False)
    manifest = {}
    for name, root in [("main", main), ("repeat", repeat)]:
        archive = output / f"raw-{name}.tar.gz"
        members = {}
        with tarfile.open(archive, "w:gz") as tar:
            for file in sorted(root.rglob("*")):
                if not file.is_file():
                    continue
                rel = str(file.relative_to(root))
                members[rel] = {
                    "size": file.stat().st_size,
                    "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
                }
                tar.add(file, arcname=f"{name}/{rel}", recursive=False)
        manifest[archive.name] = {
            "size": archive.stat().st_size,
            "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "members": members,
        }
    count = 0
    with tempfile.TemporaryDirectory(prefix="particle-support-extracted-") as tmp:
        target = Path(tmp)
        for name, facts in manifest.items():
            with tarfile.open(output / name, "r:gz") as tar:
                tar.extractall(target, filter="data")
            label = name.removeprefix("raw-").removesuffix(".tar.gz")
            for rel, expected in facts["members"].items():
                file = target / label / rel
                assert file.stat().st_size == expected["size"]
                assert hashlib.sha256(file.read_bytes()).hexdigest() == expected["sha256"]
                count += 1
        for phase in ["dev", "test"]:
            for method in ["systematic", "stratified"]:
                root = target / "main" / phase / method
                computed = json.dumps(score(root), indent=2, sort_keys=True) + "\n"
                assert computed.encode() == (root / "score.json").read_bytes()
                shutil.copy2(root / "score.json", output / f"{phase}-{method}-score.json")
        assert check(target / "main", target / "repeat", repository) == checks
    for name in ["checks.json", "probe.json", "revisions.json", "freeze.json"]:
        shutil.copy2(main / name, output / name)
    save(output / "MANIFEST.json", manifest)
    result = {
        "verified_members": count,
        "four_scores_byte_exact": True,
        "checks_exact": True,
        "scope": "Local integrity and rescoring, not B acceptance",
    }
    save(output / "ARCHIVE_VERIFY.json", result)
    print(json.dumps(result))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--main", type=Path, required=True)
    p.add_argument("--repeat", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--repository", type=Path, default=Path(__file__).resolve().parents[1])
    a = p.parse_args()
    package(a.main, a.repeat, a.output, a.repository)
