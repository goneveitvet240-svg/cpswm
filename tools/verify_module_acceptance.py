"""Recompute module acceptance records; no scientific or full-system certificate."""

from __future__ import annotations

import argparse
from pathlib import Path

from run_module_acceptance import (
    GAPS,
    TEST_GROUPS,
    audit_native,
    classify,
    pytest_result,
    read,
    save,
    sha,
    snapshot,
)


def verify(root, repository):
    manifest = read(root / "MANIFEST.json")
    names = {
        str(p.relative_to(root))
        for p in root.rglob("*")
        if p.is_file() and p.name != "MANIFEST.json"
    }
    assert names == set(manifest), "artifact coverage"
    for name, digest in manifest.items():
        path = (root / name).resolve()
        assert path.is_relative_to(root.resolve()), "external artifact"
        assert sha(path) == digest, name
    summary = read(root / "summary.json")
    assert summary["gaps"] == GAPS
    stages = summary["stages"]
    expected = [
        "environment",
        "default_sampling",
        *TEST_GROUPS,
        "native_run",
        "native_audit",
        "revision_continuation",
    ]
    if stages[0]["status"] == "PASSED":
        if next(s for s in stages if s["name"] == "native_run")["status"] != "PASSED":
            expected.remove("native_audit")
        assert [s["name"] for s in stages] == expected, "missing/reordered stage"
    else:
        assert [s["name"] for s in stages] == ["environment"]
    total = dict(tests=0, passed=0, failures=0, errors=0, skipped=0)
    for stage in stages:
        name = stage["name"]
        folder = root / name
        assert stage == read(folder / "result.json")
        state = "PASSED" if stage["exit_code"] == 0 else "FAILED"
        if name in TEST_GROUPS:
            counts = pytest_result(folder / "tests.xml")
            assert counts == stage["tests"]
            for k in total:
                total[k] += counts[k]
            if counts["failures"] or counts["errors"]:
                state = "FAILED"
            elif counts["skipped"] and state == "PASSED":
                state = "PARTIAL"
        elif stage["exit_code"] == 0:
            assert sha(folder / "data" / "result.json") == stage["result_sha256"]
        assert stage["status"] == state
        assert sha(folder / "stdout.log") == stage["stdout_sha256"]
        assert sha(folder / "stderr.log") == stage["stderr_sha256"]
    if any(s["name"] == "native_audit" and s["status"] == "PASSED" for s in stages):
        assert audit_native(root / "native_audit" / "data") == read(
            root / "native_audit" / "data" / "result.json"
        )
    if any(s["name"] == "revision_continuation" and s["status"] == "PASSED" for s in stages):
        revisions = read(root / "revision_continuation" / "data" / "result.json")
        assert revisions["actual_step_executions"] == 42 and len(revisions["cases"]) == 2
        for case in revisions["cases"]:
            c, w, r = (case["branches"][k] for k in ("control", "withdraw", "restore"))
            assert c["next_action"] == r["next_action"] and c["final_state"] == r["final_state"]
            assert w["before"] != w["after_revision"]
            assert r["before"] == r["after_revision"]
    unchanged = read(root / "source.json")["files"] == snapshot(repository)
    assert summary["source_unchanged"] == unchanged
    status, code = classify(stages, unchanged)
    assert (summary["status"], summary["exit_code"]) == (status, code)
    return dict(
        verified=True,
        status=status,
        tests=total,
        artifact_count=len(manifest),
        source_files=len(snapshot(repository)),
        scope="Recorded execution and native arithmetic; not process authentication",
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("root", type=Path)
    p.add_argument("--repository", type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    assert not args.output.resolve().is_relative_to(args.root.resolve()), (
        "verification output must be outside bundle"
    )
    result = verify(args.root, args.repository)
    save(args.output, result)
    print(result)
