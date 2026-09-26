"""Explicitly derive three eval artifacts without updating original weight bytes."""

import argparse
import hashlib
import json
from pathlib import Path

import torch

from cpswm.data_preflight.proposal_graph_compute import MAX_BLOCKED_NODES
from cpswm.data_preflight.proposal_trainer import derive_execution_checkpoint, load_checkpoint
from cpswm.data_preflight.typed_proposal_networks import ARMS


def run(training: Path, output: Path, max_nodes: int = MAX_BLOCKED_NODES):
    parent_bytes = (training / "summary.json").read_bytes()
    parent = json.loads(parent_bytes)
    if parent["track"] != "COMPONENT_FIXTURE_OPTIMIZER_DIAGNOSTIC":
        raise ValueError("this development command requires the original fixture training bundle")
    runs = parent["runs"]
    if len(runs) != len(ARMS) or {r["arm"] for r in runs} != set(ARMS):
        raise ValueError("all three unselected development arms required exactly once")
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    for arm in ARMS:
        record = next(r for r in runs if r["arm"] == arm)
        pin = derive_execution_checkpoint(
            training / arm,
            manifest_sha256=record["checkpoint_manifest_sha256"],
            directory=output / arm,
            max_nodes=max_nodes,
        )
        model, manifest = load_checkpoint(output / arm, manifest_sha256=pin)
        if model.arm != arm or manifest["training"]["track"] != "COMPONENT_FIXTURE_ONLY":
            raise ValueError("derived arm or actual training lineage mismatch")
        rows.append(
            {
                "arm": arm,
                "checkpoint_manifest_sha256": pin,
                "source_checkpoint_manifest_sha256": record["checkpoint_manifest_sha256"],
                "weights_sha256": manifest["weights_sha256"],
                "config": manifest["config"],
            }
        )
    if (training / "summary.json").read_bytes() != parent_bytes:
        raise ValueError("source training bundle changed during derivation")
    summary = {
        "track": "COMPONENT_FIXTURE_WEIGHTS_EXECUTION_DERIVATION",
        "source_training_summary_sha256": hashlib.sha256(parent_bytes).hexdigest(),
        "runs": rows,
        "new_optimizer_steps": 0,
        "architecture_selected": None,
        "production_authorized": False,
        "scope": "same weights and full attention graph; evaluation arithmetic order differs",
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2), flush=True)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--max-nodes", type=int, default=MAX_BLOCKED_NODES)
    args = parser.parse_args()
    torch.set_num_threads(2)
    run(args.training, args.output, args.max_nodes)
