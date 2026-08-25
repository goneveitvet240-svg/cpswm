from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "apps/evaluation_runner/generate_p0_checkpoint_manifest.py"
)
SPEC = importlib.util.spec_from_file_location("generate_p0_checkpoint_manifest", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
build_manifest = MODULE.build_manifest


def test_p0_checkpoint_manifest_is_current_and_self_consistent() -> None:
    expected = build_manifest()
    path = (
        Path(__file__).resolve().parents[1] / "benchmarks/p0_checkpoint/content_manifest_v0_1.json"
    )
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored == expected
    digest = stored.pop("manifest_sha256")
    canonical = json.dumps(stored, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert digest == hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_checkpoint_manifest_has_all_four_required_hash_scopes() -> None:
    scopes = build_manifest()["scopes"]
    assert set(scopes) == {"code", "config", "data_schema", "split_manifest"}
    assert all(item["file_count"] > 0 for item in scopes.values())
