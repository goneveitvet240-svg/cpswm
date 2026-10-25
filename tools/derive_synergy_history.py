"""Independent retained-statistics audit and truth-labelled readout ceiling probes.

Oracle cell choices below are diagnostic only, never supplied to a running method.
Raw alpha/ridge statistics are separated from a cell's base-blended prediction.
"""

import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path

from analyze_matched_readout import fixed_mass_bound, norm, pick
from run_joint_three_questions import scalar_read
from run_matched_value import save

RECURRENCE = {"a8d4d6c9": (27, 28), "a11287b6": (27, 28, 29)}


def analytic(cell, locations):
    d = norm(dict(zip(locations, cell["location_alpha"], strict=True)))
    r = norm(
        dict(
            zip(
                locations,
                (
                    n / p
                    for n, p in zip(cell["ridge_natural"], cell["ridge_precision"], strict=True)
                ),
                strict=True,
            )
        )
    )
    return {k: (d[k] + r[k]) / 2 for k in locations}


def derive(directory):
    manifest = json.loads((directory / "manifest.json").read_text())
    trajectories, errors = [], []
    for file in sorted(directory.glob("history-*.json.gz")):
        assert hashlib.sha256(file.read_bytes()).hexdigest() == manifest["artifacts"][file.name]
        key = file.name.split("-")[1]
        if key not in RECURRENCE:
            continue
        rows = json.loads(gzip.decompress(file.read_bytes()))
        truth = rows[RECURRENCE[key][0] - 1]["truth"]
        for row in rows:
            for name, trace in row["readings"].items():
                locations = trace["raw"]["locations"]
                index = locations.index(truth)
                totals = dict(retained=0.0, active=0.0, retired=0.0, readable=0.0)
                counts = dict(retained=0, active=0, retired=0, readable=0)
                oracle = copy.deepcopy(trace["raw"])
                for p, raw, oracle_p in zip(
                    trace["particles"], trace["raw"]["particles"], oracle["particles"], strict=True
                ):
                    owner_cells = [
                        c
                        for c in p["cells"]
                        if c["actor"] == trace["raw"]["owner"]
                        and c["cell"]["observation_count"] > 0
                    ]
                    good = [
                        c
                        for c in owner_cells
                        if c["cell"]["location_alpha"][index] > 0.5
                        and c["cell"]["location_alpha"][index] == max(c["cell"]["location_alpha"])
                    ]
                    flags = {
                        "retained": bool(good),
                        "active": any(c["active"] for c in good),
                        "retired": any(c["retired"] for c in good),
                        "readable": any(c["active"] for c in good)
                        and raw["actor"] == trace["raw"]["owner"]
                        and raw["instance"] == "target_instance",
                    }
                    for k, v in flags.items():
                        totals[k] += p["weight"] * v
                        counts[k] += int(v)
                    if owner_cells:
                        chosen = max(
                            owner_cells, key=lambda c: analytic(c["cell"], locations)[truth]
                        )
                        oracle_p["owner_cell"] = chosen["cell"]
                result = {
                    "episode_prefix": key,
                    "step": row["step"],
                    "method": name,
                    "recurrence_location": truth,
                    "dirichlet_max_includes_recurrence_location": {
                        "particle_counts": counts,
                        "posterior_mass": totals,
                    },
                }
                trajectories.append(result)
                if row["step"] in RECURRENCE[key]:
                    probes = {
                        policy: scalar_read(oracle, policy)
                        for policy in ("original", "history_read")
                    }
                    for probe in probes.values():
                        probe["fixed_mass_bound"] = fixed_mass_bound(
                            norm(oracle["base"]),
                            oracle["ledger"],
                            probe["analytic_mass"],
                            pick(oracle["base"]),
                        )
                        probe["correct_action"] = probe["action"] == truth
                    errors.append(
                        {
                            **result,
                            "actual_action": pick(trace["raw"]["actual"]),
                            "actual_readout": trace["decomposition"],
                            "oracle_owner_cell_probes": probes,
                            "oracle_warning": "truth-selected owner cell; diagnosis only",
                        }
                    )
    assert len(errors) == 20
    return {
        "trajectories": trajectories,
        "recurrence_errors": errors,
        "scientific_acceptance": False,
        "definition": "updated Dirichlet argmax includes old location, allowing ties",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    save(args.output, derive(args.directory))
