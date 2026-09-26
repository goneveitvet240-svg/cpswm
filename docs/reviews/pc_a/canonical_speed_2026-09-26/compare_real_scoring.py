"""Same frozen real first window, exact full receipts under old/new canonicalization."""

import argparse
import hashlib
import json
import sys
from contextlib import contextmanager
from pathlib import Path
from time import monotonic

import torch

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tests")]
from run_hfd_hand_proposals import checked_scores, load_frontend  # noqa: E402
from test_canonical_fast_path import reference  # noqa: E402

from cpswm.data_preflight.runtime_candidate_session import RuntimeCandidateSession  # noqa: E402
from cpswm.data_preflight.runtime_candidates import generate_runtime_candidates  # noqa: E402
from cpswm.data_preflight.typed_proposal_networks import ARMS  # noqa: E402
from cpswm.system import reproducibility  # noqa: E402


@contextmanager
def canonical_mode(legacy):
    original = reproducibility._canonical_value
    if legacy:
        reproducibility._canonical_value = reference._canonical_value
    try:
        yield
    finally:
        reproducibility._canonical_value = original


def run(main, output):
    output.mkdir(parents=True, exist_ok=False)
    front = main / "output/hand-proposal-input-20260926/closed/final-01/frontend"
    training = front.parent / "derived"
    pin = "677505fa2891aab0b2602a5ec002ea3fb3612d5e219ad788437b5b03feaf3c48"
    contexts, _, features = load_frontend(front, pin)
    key = sorted(contexts)[0]
    ctx, ledger = contexts[key]
    rows = json.loads((training / "summary.json").read_bytes())["runs"]
    torch.set_num_threads(2)
    outcomes = []
    for index, arm in enumerate(ARMS):
        model_pin = next(r["checkpoint_manifest_sha256"] for r in rows if r["arm"] == arm)
        outputs, details = {}, {}
        # Alternate the first implementation across arms. This is a host-shared
        # diagnostic, not an isolated architecture performance benchmark.
        order = ("legacy", "fast") if index % 2 == 0 else ("fast", "legacy")
        for mode in order:
            with canonical_mode(mode == "legacy"):
                support = generate_runtime_candidates(
                    ctx, bootstrap_ledger_lineage_ref=ledger
                ).targets
                session = RuntimeCandidateSession(
                    training / arm, manifest_sha256=model_pin, seed=11
                )
                before = session.snapshot()
                started = monotonic()
                scores = session._engine.score_support(context=ctx, support=support)
                seconds = monotonic() - started
                flat, mass = checked_scores(scores, support)
                if session.snapshot() != before:
                    raise RuntimeError("scoring changed sampling state")
                outputs[mode] = scores
                details[mode] = {
                    "seconds": seconds,
                    "mass": mass,
                    "candidates": len(support),
                    "score_sha256": hashlib.sha256(
                        json.dumps(flat, sort_keys=True).encode()
                    ).hexdigest(),
                }
        if outputs["legacy"] != outputs["fast"]:
            raise RuntimeError("full target/factor/probability receipts differ from predecessor")
        (output / (arm + ".json")).write_text(
            json.dumps(
                [
                    {"target_json": row.target_json, "trace_json": row.trace_json}
                    for row in outputs["fast"]
                ],
                indent=2,
            )
            + "\n"
        )
        result = {
            "arm": arm,
            "window": key,
            "prefix_frames": len(ctx.visible.pixel_observations),
            "full_receipts_exact_equal": True,
            "scoring_state_unchanged": True,
            "measurement_order": order,
            "measurements": details,
        }
        outcomes.append(result)
        print(json.dumps(result), flush=True)
    summary = {
        "scope": "three-arm exact old/new comparison on fixed first four-frame real window",
        "frontend_sha256": pin,
        "available_frontend_coverage": features,
        "cases": outcomes,
        "new_optimizer_steps": 0,
        "natural_publications": 0,
        "executed_actions": 0,
        "timing_limit": (
            "Shared host and concurrent matrix load; not isolated speed or accuracy benchmark."
        ),
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.main.resolve(), args.output.resolve())
