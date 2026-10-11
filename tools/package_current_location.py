"""Archive raw runs, verify every member, then rescore the extracted copies."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tarfile
import tempfile
from pathlib import Path

from check_current_location import check
from score_current_location import read, verify
from summarize_current_location import summarize


def save(path, obj):
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")


def package(main, repeat, output, repository):
    output.mkdir(parents=True, exist_ok=False)
    summary = summarize(main)
    save(main / "summary.json", summary)
    checks = check(main, repeat, repository)
    assert checks == read(main / "checks.json")
    manifest = {}
    for label, root in (("main", main), ("repeat", repeat)):
        members = {}
        archive = output / f"raw-{label}.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            for file in sorted(root.rglob("*")):
                if not file.is_file():
                    continue
                relative = str(file.relative_to(root))
                members[relative] = {
                    "size": file.stat().st_size,
                    "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
                }
                tar.add(file, arcname=f"{label}/{relative}", recursive=False)
        manifest[archive.name] = {
            "size": archive.stat().st_size,
            "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "members": members,
        }
    count = 0
    with tempfile.TemporaryDirectory(prefix="cpswm-current-extracted-") as temp:
        target = Path(temp)
        for archive, entry in manifest.items():
            with tarfile.open(output / archive, "r:gz") as tar:
                tar.extractall(target, filter="data")
            label = archive.removeprefix("raw-").removesuffix(".tar.gz")
            for name, facts in entry["members"].items():
                file = target / label / name
                assert file.stat().st_size == facts["size"]
                assert hashlib.sha256(file.read_bytes()).hexdigest() == facts["sha256"]
                count += 1
        rescored = []
        for phase in ("dev", "test", "integrate"):
            computed = verify(target / "main" / phase)
            expected = target / "main" / (phase + "-score.json")
            assert (
                json.dumps(computed, indent=2, sort_keys=True) + "\n"
            ).encode() == expected.read_bytes()
            rescored.append(phase + "-score.json")
        assert check(target / "main", target / "repeat", repository) == checks
        assert summarize(target / "main") == summary
    for name in (
        "dev-score.json",
        "test-score.json",
        "integrate-score.json",
        "checks.json",
        "summary.json",
    ):
        shutil.copy2(main / name, output / name)
    save(output / "MANIFEST.json", manifest)
    receipt = {
        "verified_members": count,
        "exact_rescored_json": rescored,
        "checks_and_summary_exact": True,
        "scope": "local archive integrity and rescoring, not independent-device acceptance",
    }
    save(output / "ARCHIVE_VERIFY.json", receipt)
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--main", type=Path, required=True)
    p.add_argument("--repeat", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--repository", type=Path, default=Path(__file__).resolve().parents[1])
    args = p.parse_args()
    package(args.main, args.repeat, args.output, args.repository)
