import hashlib
import json
import sys
import tarfile
from pathlib import Path

root = Path(__file__).resolve().parents[5]
out = root / "docs/reviews/pc_a/grounding_readout_feedback_2026-10-11/evidence"
write_index = sys.argv[1:] == ["--write-index"]
if sys.argv[1:] and not write_index:
    raise ValueError("only --write-index is accepted; default is read-only verification")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(name, obj):
    if write_index:
        (out / name).write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")
    else:
        assert json.loads((out / name).read_text()) == obj, name


if not write_index:
    expected = json.loads((out / "files.json").read_text())["files"]
    for name, record in expected.items():
        data = (out / name).read_bytes()
        assert len(data) == record["bytes"] and sha(data) == record["sha256"], name


index = {}
checks = 0
for path in sorted(out.glob("*.tar.gz")):
    members = []
    with tarfile.open(path) as t:
        for member in t:
            if not member.isfile():
                continue
            blob = t.extractfile(member).read()
            assert len(blob) == member.size
            members.append(dict(name=member.name, bytes=len(blob), sha256=sha(blob)))
            checks += 1
    index[path.name] = members
save("archive-members.json", index)
# Recompute task correctness from retained choices; do not trust stored score fields.
cases = []
for seed in (7, 8, 9):
    with tarfile.open(out / f"long32-seed-{seed}-raw.tar.gz") as t:
        for member in t:
            if member.name.endswith(".json"):
                case = json.loads(t.extractfile(member).read())
                rows = case["rows"]
                cases.append(case)
                for row in rows:
                    assert (row["command"] == row["true_habit"]) == row["correct"]["runtime"]
                    checks += 1
                    assert (row["soft_full_history"] == row["true_habit"]) == row["correct"][
                        "soft_full_history"
                    ]
                    checks += 1
                    assert row["command"] == row["command_location"]
                    checks += 1
                    if case["actor_mode"] == "presence_only" and row["ciav_actor"] is not None:
                        assert (
                            max(
                                abs(row["primary_actor"][a] - v)
                                for a, v in row["ciav_actor"].items()
                            )
                            < 1e-12
                        )
                        checks += 1
                assert (
                    sum(r["correct"]["runtime"] for r in rows)
                    == case["metrics"]["all"]["correct"]["runtime"]
                )
                checks += 1
                assert case["recovery_equal"]
                checks += 1
                assert rows[-1]["committed"] == 0
                checks += 1
assert len(cases) == 18
summary = json.loads((out / "long32-summary.json").read_text())
for key, group in summary["totals"].items():
    selected = [c for c in cases if key == c["actor_mode"] + "/" + c["policy"]]
    assert group["n"] == sum(len(c["rows"]) for c in selected)
    checks += 1
    assert group["runtime"] == sum(
        r["command"] == r["true_habit"] for c in selected for r in c["rows"]
    )
    checks += 1
    assert group["soft_full_history"] == sum(
        r["soft_full_history"] == r["true_habit"] for c in selected for r in c["rows"]
    )
    checks += 1
for seed in (7, 8, 9):
    both = [
        c
        for c in cases
        if c["seed"] == seed
        and c["actor_mode"] == "presence_only"
        and c["policy"] in ("repaired", "latest_owner")
    ]
    assert [r["command"] for r in both[0]["rows"]] == [r["command"] for r in both[1]["rows"]]
    checks += 1
live = json.loads((out / "live-evaluation.json").read_text())
assert live["source_unchanged"]
assert all(sha((root / name).read_bytes()) == value for name, value in live["source_files"].items())
checks += 1
assert live["intervention_effects"][0]["depth_changed_gt_0_5mm"] == 0
checks += 1
assert live["intervention_effects"][0]["rgb_changed_pixels"] == 1160
checks += 1
assert live["membership"][0]["identity_correct"] and not live["membership"][0]["joint_correct"]
checks += 1
assert [r["status"] for r in live["public_results"][-1]["reports"]] == ["unknown"] * 3
checks += 1
assert json.loads((out / "frozen-evaluation.json").read_text())["joint_success"] == 6
checks += 1
save(
    "verification.json",
    dict(
        status="PASS",
        checks=checks,
        archived_files=sum(map(len, index.values())),
        cases=18,
        planned_commands=564,
        scope="LOCAL_ARITHMETIC_AND_CONTENT_BINDING_NOT_B_INDEPENDENT_ACCEPTANCE",
    ),
)
save(
    "files.json",
    {
        "files": {
            p.name: dict(bytes=p.stat().st_size, sha256=sha(p.read_bytes()))
            for p in sorted(out.iterdir())
            if p.is_file() and p.name != "files.json"
        }
    },
)
print("PASS", checks, "checks; archive members", sum(map(len, index.values())))
