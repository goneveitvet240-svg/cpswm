"""Verify archive inventory, committed source bytes and derived scientific counts."""

import gzip
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tools")]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sources_at_commit(code_sha, sources):
    names = sorted(sources)
    request = "".join(code_sha + ":" + name + "\n" for name in names).encode()
    data = subprocess.check_output(["git", "cat-file", "--batch"], cwd=ROOT, input=request)
    offset = 0
    for name in names:
        assert not Path(name).is_absolute() and ".." not in Path(name).parts
        end = data.index(b"\n", offset)
        _, kind, size = data[offset:end].split()
        assert kind == b"blob"
        start = end + 1
        stop = start + int(size)
        assert digest(data[start:stop]) == sources[name], (code_sha, name)
        assert digest((ROOT / name).read_bytes()) == sources[name], name
        assert data[stop : stop + 1] == b"\n"
        offset = stop + 1
    assert offset == len(data)
    return len(names)


def main():
    from derive_synergy_history import derive
    from run_five_stage_synergy import summarize
    from verify_synergy_goal_episode import validate_goal_outcomes

    manifest = json.loads((HERE / "MANIFEST.json").read_text())
    files = {
        str(p.relative_to(HERE))
        for p in HERE.rglob("*")
        if p.is_file()
        and p.name not in {"MANIFEST.json", "VERIFICATION.json"}
        and "__pycache__" not in p.parts
    }
    assert files == set(manifest["files"])
    for name, expected in manifest["files"].items():
        data = (HERE / name).read_bytes()
        assert len(data) == expected["bytes"] and digest(data) == expected["sha256"], name
    evidence = HERE / "evidence"
    primary = json.loads((evidence / "paired-manifest.json").read_text())
    points_data = gzip.decompress((evidence / "paired-points.json.gz").read_bytes())
    points = json.loads(points_data)
    assert len(points) == 768
    assert summarize(points) == json.loads((evidence / "paired-summary.json").read_text())
    with tempfile.TemporaryDirectory(prefix="synergy-archive-") as scratch:
        scratch = Path(scratch)
        (scratch / "manifest.json").write_bytes((evidence / "paired-manifest.json").read_bytes())
        for name, expected in primary["artifacts"].items():
            data = (
                points_data
                if name == "points.json"
                else (evidence / ("paired-" + name)).read_bytes()
            )
            assert digest(data) == expected
            (scratch / name).write_bytes(data)
        assert derive(scratch) == json.loads((evidence / "history.json").read_text())
    posterior = json.loads(gzip.decompress((evidence / "posteriors.json.gz").read_bytes()))
    assert posterior["complete"] and len(posterior["rows"]) == 768
    assert posterior["primary_manifest_sha256"] == digest(
        (evidence / "paired-manifest.json").read_bytes()
    )
    assert all(m["state_replay_match"] for r in posterior["rows"] for m in r["methods"].values())
    correction = json.loads((evidence / "corrections.json").read_text())
    assert len(correction["rows"]) == 8
    assert sum(len(r["invalid_cases_rejected_without_mutation"]) for r in correction["rows"]) == 40
    missing = json.loads((evidence / "missing_regime.json").read_text())
    assert len(missing["rows"]) == 64
    assert all(
        s["errors"] == 7 and s["fixed"] == s["harmed"] == 0 for s in missing["summary"].values()
    )
    run = evidence / "pi05_run"
    physical_manifest = json.loads((run / "manifest.json").read_text())
    summary = json.loads((run / "summary.json").read_text())
    journal = json.loads((run / "journal.json").read_text())
    validate_goal_outcomes(physical_manifest, summary, journal)
    assert summary["steps"] == 105 and summary["goal_success_evaluator_only"]
    controls = json.loads(gzip.decompress((evidence / "goal_controls.json.gz").read_bytes()))
    assert controls["actual_manifest_sha256"] == digest((run / "manifest.json").read_bytes())
    assert controls["actual_journal_sha256"] == digest((run / "journal.json").read_bytes())
    assert len(controls["inferences"]) == 22 and len(controls["actions"]) == 105
    assert (
        json.loads((evidence / "goal-physics-verification.json").read_text())["status"]
        == "GOAL_ACTION_PHYSICS_REPLAY_PASS"
    )
    assert (
        json.loads((evidence / "goal-physics-negative.json").read_text())["status"]
        == "STRUCTURALLY_VALID_PHYSICS_FORGERY_REJECTED"
    )
    counts = [
        sources_at_commit(primary["source_sha"], primary["sources"]),
        sources_at_commit(posterior["source_sha"], posterior["sources"]),
        sources_at_commit(missing["source_sha"], missing["sources"]),
        sources_at_commit(physical_manifest["code_sha"], physical_manifest["sources"]),
    ]
    print(
        json.dumps(
            {
                "status": "DELIVERY_VERIFIED",
                "files": len(files),
                "source_bindings_checked": counts,
                "paired_decisions": 768 * 6,
                "native_state_replays": 768 * 4,
                "recurrence_target_probe_points": 64 * 2,
                "pi05_actions": 105,
                "scientific_acceptance": False,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
