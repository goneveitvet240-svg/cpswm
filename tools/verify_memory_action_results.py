"""Recompute all reported paired outcomes and readout algebra from saved evidence."""

import argparse
import hashlib
import io
import json
import math
import subprocess
from collections import Counter
from pathlib import Path

from cpswm.system.reproducibility import content_sha256


def verify(path):
    manifest = json.loads((path / "source.json").read_text())
    sha = manifest["sha"]
    if len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha) or manifest["status"]:
        raise ValueError("clean full source SHA required")
    names = list(manifest["files"])
    result = subprocess.run(
        ["git", "cat-file", "--batch"],
        input="".join(f"{sha}:{name}\n" for name in names).encode(),
        capture_output=True,
        check=True,
    )
    blobs = io.BytesIO(result.stdout)
    for name in names:
        header = blobs.readline().split()
        assert len(header) == 3 and header[1] == b"blob", name
        data = blobs.read(int(header[2]))
        assert blobs.read(1) == b"\n"
        assert hashlib.sha256(data).hexdigest() == manifest["files"][name], name
    rows = json.loads((path / "points.json").read_text())
    summary = json.loads((path / "summary.json").read_text())
    assert len(rows) == summary["points"] == 768
    assert len({(r["cohort"], r["episode"], r["step"]) for r in rows}) == 768
    checked, max_error, groups = 0, 0.0, {}
    for row in rows:
        for name, receipt in row["readouts"].items():
            body = {k: v for k, v in receipt.items() if k != "sha256"}
            assert content_sha256(body) == receipt["sha256"]
            components = receipt["components"]
            assert math.isclose(
                math.fsum(c["weight"] for c in components), receipt["consumed_mass"], abs_tol=1e-12
            )
            assert math.isclose(
                receipt["fallback_mass"] + receipt["consumed_mass"], 1.0, abs_tol=1e-12
            )
            scores = {
                k: math.fsum(c["weight"] * c["distribution"][k] for c in components)
                + receipt["fallback_mass"] * receipt["base"][k]
                for k in receipt["distribution"]
            }
            total = math.fsum(scores.values())
            expected = {k: v / total for k, v in scores.items()}
            error = max(abs(expected[k] - receipt["distribution"][k]) for k in expected)
            assert error < 1e-12
            max_error = max(max_error, error)
            if not name.endswith("parent_only"):
                assert row["actions"][name]["put_back"] == min(
                    expected, key=lambda k: (-expected[k], k)
                )
            checked += 1
        for arm in ("native_joint", "native_six_potential_ablation"):
            baseline = row["budgets"][arm + "/parent_only"]
            for mode in ("owner_only", "owner_missing"):
                for key in (
                    "target_evaluations",
                    "particles",
                    "extra_ciav_queries",
                    "paid_location_sources",
                ):
                    assert row["budgets"][arm + "/" + mode][key] == baseline[key]
        for name, action in row["actions"].items():
            key = row["cohort"], row["condition"], name
            count = groups.setdefault(key, Counter())
            base = row["actions"]["latest_owner"]["put_back"]
            choice, truth = action["put_back"], row["truth"]
            count.update(
                points=1,
                errors=int(choice != truth),
                changed_actions=int(choice != base),
                fixed=int(base != truth and choice == truth),
                harmed=int(base == truth and choice != truth),
                both_wrong=int(base != truth and choice != truth),
            )
    for cohort, methods in summary["results"].items():
        for name, recorded in methods.items():
            total = Counter()
            for (c, _, n), counts in groups.items():
                if c == cohort and n == name:
                    total.update(counts)
            assert recorded["errors"] == total["errors"]
            assert recorded["versus_latest"] == dict(total)
    return {
        "source_sha": sha,
        "source_blobs": len(names),
        "points": len(rows),
        "readout_recomputations": checked,
        "max_scalar_error": max_error,
        "paired_outcomes_verified": True,
        "budget_checks_passed": True,
        "by_condition": [
            {"cohort": c, "condition": cond, "method": n, **counts}
            for (c, cond, n), counts in sorted(groups.items())
        ],
        "scope": "source-bound arithmetic; not a second full native-state rerun",
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("path", type=Path)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    result = verify(a.path)
    a.output.write_text(json.dumps(result, indent=2))
    print({k: v for k, v in result.items() if k != "by_condition"})
