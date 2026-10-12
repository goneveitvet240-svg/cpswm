"""Verify the receipt-only repair left all recorded inference and actions unchanged."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def compare(before, after):
    count = 0
    for phase in ["dev", "test"]:
        for file in sorted((before / phase).glob("run-*.json")):
            a = json.loads(file.read_text())
            b = json.loads((after / phase / file.name).read_text())
            a.pop("wall_seconds")
            b.pop("wall_seconds")
            b.pop("task_readout_actions")
            assert a == b, file.name
            count += 1
    a = json.loads((before / "dev/freeze.json").read_text())
    b = json.loads((after / "dev/freeze.json").read_text())
    assert a["selected"] == b["selected"] and a["dev_totals"] == b["dev_totals"]
    return {
        "exact_actual_runs_except_wall_and_added_task_receipt": count,
        "selection_and_dev_costs_exact": True,
        "scope": "same data regression repetition, not another independent holdout",
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--before", type=Path, required=True)
    p.add_argument("--after", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    r = compare(a.before, a.after)
    a.output.write_text(json.dumps(r, indent=2, sort_keys=True) + "\n")
    print(json.dumps(r))
