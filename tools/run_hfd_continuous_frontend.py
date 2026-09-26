"""Continuous original HFD frames with same-producer hand and object diagnostics.

Every local window retains all declared frames and full candidate support. Windows
are correlated within trials; regional hand candidates are not unique physical hands.
"""

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from itertools import pairwise
from pathlib import Path

import torch
from run_hfd_pixel_frontend import run_window

from cpswm.data_preflight.hfd_observation_alignment import load_runtime_windows
from cpswm.perception_mapping.natural_hands import NaturalHandDetector
from cpswm.perception_mapping.natural_vision import FasterNaturalAppearanceDetector


def run(runtime: Path, manifest_sha256: str, weights: Path, hand_model: Path, output: Path):
    windows = load_runtime_windows(runtime, manifest_sha256=manifest_sha256)
    output.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(2)
    groups = defaultdict(list)
    for key, rows in windows:
        groups[key.split("/")[0]].append((key, rows))
    records, results = [], []
    for source, selected in groups.items():
        identity = selected[0][1][0][1].envelope().identity
        scope = {
            name: getattr(identity, name) for name in ("household_id", "session_id", "trace_id")
        }
        detector = FasterNaturalAppearanceDetector(weights_path=weights, **scope)
        hands = NaturalHandDetector(
            model_path=hand_model, scope=tuple(scope.values()), person_rois=True
        )
        try:
            for window, rows in selected:
                observed, result = run_window(window, rows, detector, hands, output)
                records.extend({"window": window, **row} for row in observed)
                clocks = [raw.archive_timeline()[1] for _, raw in rows]
                result.update(
                    source_sequence=source,
                    original_frames=[int(key.split("/")[-1]) for key, _ in rows],
                    source_clock_gaps_seconds=[b - a for a, b in pairwise(clocks)],
                )
                results.append(result)
                print(
                    json.dumps(
                        {
                            "window": window,
                            "frames": len(rows),
                            "candidate_status": result["support"]["status"],
                        }
                    ),
                    flush=True,
                )
        finally:
            hands.close()
    result = {
        "runtime_manifest_sha256": manifest_sha256,
        "unique_input_frames": len({row["key"] for row in records}),
        "frame_presentations": len(records),
        "source_trials": len(groups),
        "windows": results,
        "detections_per_presentation": dict(
            Counter(d["category"] for r in records for d in r["visual"]["candidates"])
        ),
        "associations_per_presentation": dict(
            Counter(d["status"] for r in records for d in r["association"]["detections"])
        ),
        "role_alternatives": sum(len(r["interaction"]["role_alternatives"]) for r in records),
        "regional_hand_candidates": sum(len(r["hands"]["candidates"]) for r in records),
        "hand_object_measurements": sum(
            len(r["hand_object_evidence"]["measurements"]) for r in records
        ),
        "hand_count_semantics": "regional observations; overlapping crops can duplicate hands",
        "hand_geometry_used_as_proposal_truth": False,
        "continuous_episode_or_independent_window_claim": False,
        "author_labels_read_by_frontend": False,
        "proposal_targets_supervised": 0,
        "proposal_network_training_steps": 0,
        "natural_semantic_publications": 0,
        "memory_writes": 0,
        "executed_actions": 0,
        "records": records,
    }
    raw = json.dumps(result, default=str, indent=2, sort_keys=True).encode()
    (output / "result.json").write_bytes(raw)
    (output / "result.sha256").write_text(hashlib.sha256(raw).hexdigest() + "\n")
    return {k: v for k, v in result.items() if k != "records"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("runtime", "weights", "hand-model", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    print(json.dumps(run(**vars(parser.parse_args())), indent=2, default=str))
