"""Combine two disjoint seed shards, copying run bytes without rescoring/rewriting."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_text())


def save(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def merge(first, second, output):
    output.mkdir(parents=True, exist_ok=False)
    index = []
    mapping = []
    source = read(first / "source.json")
    assert source == read(second / "source.json")
    for offset, root in [(0, first), (2, second)]:
        assert read(root / "completion.json")["actual_runs"] == 16
        for original in read(root / "index.json"):
            item = dict(original)
            assert item["episode"] in (0, 1)
            old = f"{item['condition']}-{item['episode']}"
            item["episode"] += offset
            new = f"{item['condition']}-{item['episode']}"
            for key in ["file", "visible", "truth"]:
                name = item[key].replace(old, new, 1)
                target = output / name
                data = (root / item[key]).read_bytes()
                if target.exists():
                    assert target.read_bytes() == data
                else:
                    target.write_bytes(data)
                    mapping.append(
                        {
                            "source": str(root / item[key]),
                            "target": name,
                            "sha256": hashlib.sha256(data).hexdigest(),
                        }
                    )
                item[key] = name
            index.append(item)
    assert len(index) == 32
    save(output / "index.json", index)
    save(output / "source.json", source)
    save(
        output / "completion.json",
        {"actual_runs": 32, "source_unchanged": True, "merged_disjoint_seed_shards": True},
    )
    save(
        output / "MERGED_SHARDS.json",
        {
            "members": mapping,
            "copied_bytes_exact": True,
            "scope": "Only filenames and index episode offsets remapped",
        },
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--first", type=Path, required=True)
    p.add_argument("--second", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    merge(a.first, a.second, a.output)
