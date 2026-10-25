"""Compare complete fresh runs; no independent scientific or authenticity claim."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from run_matched_value import save, sources


def numerical(value):
    if isinstance(value, dict):
        return {k: numerical(v) for k, v in value.items() if k not in {"seconds", "method_seconds"}}
    if isinstance(value, list):
        return [numerical(v) for v in value]
    return value


def compare(left, right):
    paths = sorted(p.relative_to(left) for p in left.rglob("*.json"))
    if not paths or paths != sorted(p.relative_to(right) for p in right.rglob("*.json")):
        raise ValueError("artifact inventory mismatch")
    for root in (left, right):
        manifest = json.loads((root / "manifest.json").read_text())
        done = json.loads((root / "completion.json").read_text())
        if (
            manifest["files"] != sources()
            or manifest["git_status"].strip()
            or manifest["quick_development"]
            or manifest["scientific_acceptance"]
            or done["quick_development"]
            or not done["source_unchanged"]
        ):
            raise ValueError("source or completion contract mismatch")
    for path in paths:
        a = numerical(json.loads((left / path).read_text()))
        b = numerical(json.loads((right / path).read_text()))
        if a != b:
            raise ValueError(f"fresh replay mismatch: {path}")
    return {
        "status": "FULL_DEVELOPMENT_REPEAT_MATCH",
        "json_files": len(paths),
        "excluded_fields": ["seconds", "method_seconds"],
        "scope": "same source/environment, not independent scientific verification",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("left", type=Path)
    parser.add_argument("right", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    save(args.output, compare(args.left, args.right))
