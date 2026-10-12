"""Stdlib independent arithmetic and sampling-receipt validation."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

from score_current_event import read, verify


def verify_sampling(run):
    assert run["sampling_method"] in {"systematic", "independent_strata_v1"}
    assert run["profile"] == "v06"
    assert len(run["sampling_receipts"]) == len(run["actions"])
    result = Counter()
    for row, native, receipt in zip(
        run["actions"], run["native_evidence"], run["sampling_receipts"], strict=True
    ):
        method = run["sampling_method"]
        assert receipt["method"] == method
        seed = native["fairness"]["common_random_number_sha256"]
        assert receipt["seed_sha256"] == seed and receipt["count"] == 24
        if method == "systematic":
            expected = [int(seed[:16], 16) / 16**16] * 24
        else:
            expected = []
            for i in range(24):
                digest = hashlib.sha256(f"independent_strata_v1:{seed}:{i}".encode()).hexdigest()
                expected.append((int(digest[:16], 16) // 2048) / 9007199254740992)
        assert receipt["offsets"] == expected
        assert (
            len(receipt["indices"])
            == len(receipt["selected_probabilities"])
            == len(receipt["cdf_intervals"])
            == 24
        )
        assert len(native["receipts"]) == 24
        for i, (index, q, interval, importance) in enumerate(
            zip(
                receipt["indices"],
                receipt["selected_probabilities"],
                receipt["cdf_intervals"],
                native["receipts"],
                strict=True,
            )
        ):
            assert 0 <= index < receipt["support_size"] and q > 0
            lo, hi = interval
            point = (i + expected[i]) / 24
            assert -1e-12 <= lo <= point + 1e-12 and point < hi + 1e-12 <= 1 + 2e-12
            assert math.isclose(hi - lo, q, rel_tol=1e-8, abs_tol=1e-12)
            assert math.isclose(
                math.exp(importance["proposal"]["proposal_log_probability"]), q, rel_tol=1e-9
            )
        if row["location_source_id"]:
            likelihood = dict(native["observation"]["location_likelihood"])
            actors = set(native["placement_actors"])
            applied = [likelihood[a] for a in actors]
            result["updates"] += 1
            result["multiple_actor_support"] += len(actors) > 1
            result["informative_full_likelihood"] += (
                max(likelihood.values()) - min(likelihood.values()) > 1e-10
            )
            result["informative_on_sampled_support"] += max(applied) - min(applied) > 1e-10
    return result


def score(root):
    base = verify(root)
    diagnostics = {}
    for item in read(root / "index.json"):
        run = read(root / item["file"])
        assert run["sampling_method"] == item["config"]["sampling_method"]
        assert (
            run["arm"] == item["config"]["arm"]
            and run["consume_new"] == item["config"]["consume_new"]
        )
        key = item["condition"] + "/" + item["label"]
        diagnostics.setdefault(key, Counter()).update(verify_sampling(run))
    return {
        **base,
        "sampling_diagnostics": {k: dict(v) for k, v in sorted(diagnostics.items())},
        "scope": (
            "Independent recorded arithmetic/interval checks; full proposal support checked "
            "in enumerated development probes, not malicious-process isolation"
        ),
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    result = score(a.root)
    a.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
