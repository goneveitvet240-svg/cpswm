"""Tamper diagnostics over archived output; never mutates files."""

import argparse
import copy
import json
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("folder", type=Path)
parser.add_argument("--root", type=Path, default=Path.cwd())
a = parser.parse_args()
sys.path.insert(0, str(a.root / "tools"))
import score_full_mechanism_value as score  # noqa: E402

original = score.read
results = {}
for attack in ("action", "metric", "fairness", "selection"):

    def altered(path, attack=attack):
        data = original(path)
        if path.name == "test-0-stateful_full_joint.json":
            data = copy.deepcopy(data)
            if attack == "action":
                row = data["actions"][0]
                row["put_back"] = next(x for x in row["search_order"] if x != row["put_back"])
            if attack == "metric":
                data["metric"]["put_back_error_rate"] = 0.5
            if attack == "fairness":
                data["runtime_audit"]["fairness_receipts"][0]["particle_budget"] = 25
        if attack == "selection" and path.name == "selection.json":
            data = copy.deepcopy(data)
            data["selected"]["shared_spine_latest"] = 0.99
        return data

    score.read = altered
    try:
        score.verify(a.folder, a.root)
    except AssertionError:
        results[attack] = "REJECTED"
    else:
        raise AssertionError("tampering accepted: " + attack)
    finally:
        score.read = original
print(json.dumps(results, indent=2))
