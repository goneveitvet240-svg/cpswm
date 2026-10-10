"""Recompute reported counts and verify every archived raw byte, without extraction."""

import argparse
import hashlib
import json
import tarfile
from pathlib import Path


def load(path):
    return json.loads(path.read_text())


def verify(root):
    checks = 0
    archive_manifest = load(root / "raw-files.json")
    with tarfile.open(root / "raw-runs.tar.gz", "r:gz") as archive:
        files = {m.name: m for m in archive if m.isfile()}
        assert set(files) == set(archive_manifest)
        for name, meta in archive_manifest.items():
            value = archive.extractfile(files[name]).read()
            assert len(value) == meta["bytes"]
            assert hashlib.sha256(value).hexdigest() == meta["sha256"]
            checks += 1
    result = load(root / "readout-diagnosis.json")
    totals = {}
    for case in result["cases"]:
        assert case["readouts_do_not_mutate_state"] and case["default_prefix_equal_reference"]
        counts = dict.fromkeys(case["correct"], 0)
        for row in case["rows"]:
            for name, value in row["readouts"].items():
                dist = value["distribution"]
                choice = max(sorted(dist), key=dist.__getitem__)
                assert choice == value["choice"]
                assert row["correct"][name] == (choice == row["true_habit_location"])
                counts[name] += int(row["correct"][name])
                checks += 1
            actor_counts = dict.fromkeys(row["readouts"]["soft_current_actor"]["distribution"], 1.0)
            for event in row["current_actor_events"]:
                actor_counts[event["location"]] += event["current_owner_mass"]
            total = sum(actor_counts.values())
            assert all(
                abs(v / total - row["readouts"]["soft_current_actor"]["distribution"][k]) < 1e-12
                for k, v in actor_counts.items()
            )
            checks += 1
        assert counts == case["correct"]
        mode = totals.setdefault(case["mode"], dict.fromkeys(counts, 0))
        for k, v in counts.items():
            mode[k] += v
    assert result["source_unchanged"]
    geometry = load(root / "geometry/diagnosis.json")
    for name, expected in geometry["counts"].items():
        found = {}
        for row in geometry["rows"]:
            if row["arm"] == name:
                found[row["class"]] = found.get(row["class"], 0) + 1
        assert found == expected and sum(found.values()) == 9
        checks += 1
    for mode in ("detected_same_location", "detected_different_location"):
        for seed in (7, 8, 9):
            raw = load(root / f"{mode}-{seed}.json")
            assert raw["source_unchanged"]
            if mode == "detected_same_location":
                assert raw["status"] == "NO_LEGAL_CORRECTION_TARGET" and raw["targets"] == 0
                assert raw["correction_comparison_completed"] is False
            else:
                assert raw["targets"] == 1 and raw["recovery_semantic_state_equal"]
                assert raw["full_semantic_replay"]["semantic_state_equal"]
                assert raw["full_semantic_replay"]["after_max_abs_difference"] == 0
            checks += 1
    return {"checks": checks, "raw_files_verified": len(archive_manifest), "readout_totals": totals}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("root", type=Path)
    a = p.parse_args()
    print(json.dumps(verify(a.root), indent=2))
