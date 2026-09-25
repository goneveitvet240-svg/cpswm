"""Use all three trained checkpoints in replayable fixture inference sessions.

This is not natural evaluation or selected-model native publication. Runtime
support comes explicitly from a component fixture, never from natural truth.
No optimizer step occurs in this command.
"""

import argparse
import hashlib
import json
import math
import sys
from dataclasses import asdict
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_structure_two_proposal_scheduler import sample_payload  # noqa: E402

from cpswm.data_preflight.proposal_inference_session import (  # noqa: E402
    ProposalInferenceSession,
)
from cpswm.data_preflight.proposal_samples import ProposalSample  # noqa: E402
from cpswm.data_preflight.typed_proposal_networks import ARMS  # noqa: E402


def run(training: Path, output: Path):
    summary_bytes = (training / "summary.json").read_bytes()
    training_summary = json.loads(summary_bytes)
    if (
        training_summary["track"] != "COMPONENT_FIXTURE_OPTIMIZER_DIAGNOSTIC"
        or training_summary["natural_training_runs"] != 0
    ):
        raise ValueError("this diagnostic expects fixture checkpoints only")
    rows = {r["arm"]: r for r in training_summary["runs"]}
    if set(rows) != set(ARMS) or len(training_summary["runs"]) != 3:
        raise ValueError("all three unselected development arms required")
    output.mkdir(parents=True, exist_ok=False)
    sample = ProposalSample.model_validate(sample_payload.__wrapped__())
    context, support = sample.runtime_context(), sample.compatible_targets
    old_threads = torch.get_num_threads()
    torch.set_num_threads(2)
    results = []
    try:
        for arm in ARMS:
            pin = rows[arm]["checkpoint_manifest_sha256"]
            checkpoint = training / arm
            session = ProposalInferenceSession(checkpoint, manifest_sha256=pin, seed=11)
            catalog = session.score_support(context=context, support=support)
            mass = math.fsum(math.exp(t.probability.joint_log_probability) for t in catalog)
            operations = sorted({t.target.operation.value for t in catalog})
            if abs(mass - 1) > 1e-12 or len(operations) != 6:
                raise ValueError("full six-operation probability support required")
            prefix = [
                session.infer(request_id=f"request-{i}", context=context, support=support)
                for i in range(3)
            ]
            blob = session.snapshot()
            restored = ProposalInferenceSession.restore(
                checkpoint,
                manifest_sha256=pin,
                snapshot=blob,
                snapshot_sha256=hashlib.sha256(blob).hexdigest(),
            )
            duplicate = restored.infer(request_id="request-1", context=context, support=support)
            if duplicate != prefix[1] or restored.snapshot() != blob:
                raise RuntimeError("duplicate request changed RNG/history")
            suffix = []
            for i in range(3, 8):
                args = {"request_id": f"request-{i}", "context": context, "support": support}
                before, after = session.infer(**args), restored.infer(**args)
                if before != after:
                    raise RuntimeError("restored continuation changed target or probability")
                suffix.append(before)
            if session.snapshot() != restored.snapshot():
                raise RuntimeError("restored history/RNG changed")
            dest = output / arm
            dest.mkdir()
            (dest / "prefix.snapshot.json").write_bytes(blob)
            (dest / "final.snapshot.json").write_bytes(session.snapshot())
            result = {
                "arm": arm,
                "checkpoint_manifest_sha256": pin,
                "session_binding_sha256": session.binding_sha256,
                "probability_mass": mass,
                "scored_operations": operations,
                "scored_targets": [asdict(t) for t in catalog],
                "prefix_requests": len(prefix),
                "continued_requests": len(suffix),
                "continued_receipts": [asdict(r) for r in suffix],
                "duplicate_request_preserved_rng": True,
                "restored_continuation_equal": True,
                "ledger_authorized": False,
                "native_publication_authorized": False,
            }
            results.append(result)
    finally:
        torch.set_num_threads(old_threads)
    (output / "summary.json").write_text(
        json.dumps(
            {
                "track": "COMPONENT_FIXTURE_CHECKPOINT_INFERENCE",
                "training_summary_sha256": hashlib.sha256(summary_bytes).hexdigest(),
                "runs": results,
                "new_optimizer_steps": 0,
                "natural_evaluation_runs": 0,
                "architecture_selected": None,
                "runtime_support_generator_implemented": False,
                "native_particle_kernel_bound": False,
                "independent_auditors": 0,
            },
            indent=2,
        )
        + "\n"
    )
    print("three checkpoints: six-operation scores and five restored continuations each passed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.training, args.output)
