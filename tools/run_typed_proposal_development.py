"""Three-arm fixture-only optimizer/serialization execution, not natural training.

No arm is selected. This small CPU batch is charged against the existing local
development budget; it does not consume validation or confirmatory data.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_structure_two_proposal_scheduler import sample_payload  # noqa: E402

from cpswm.data_preflight.proposal_samples import ProposalSample  # noqa: E402
from cpswm.data_preflight.proposal_trainer import (  # noqa: E402
    distribution,
    load_checkpoint,
    save_checkpoint,
    train_proposer,
)
from cpswm.data_preflight.typed_proposal_networks import ARMS  # noqa: E402


def run(output: Path, steps: int):
    if not 1 <= steps <= 12:
        raise ValueError(
            "fixture diagnostic capped at 12 steps per arm, not a hyperparameter search"
        )
    output.mkdir(parents=True, exist_ok=False)
    sample = ProposalSample.model_validate(sample_payload.__wrapped__())
    support = sample.compatible_targets
    training = ProposalSample.model_validate(
        sample.model_copy(
            update={
                "compatible_targets": tuple(
                    t for t in support if t.operation.value in {"branch", "preserve_unresolved"}
                )
            }
        ).model_dump()
    )
    source_files = {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for folder in ("src", "tests", "tools")
        for p in sorted((ROOT / folder).rglob("*.py"))
    }
    rows = []
    for arm in ARMS:
        model, report = train_proposer(
            arm=arm,
            samples=(training,),
            support_provider=lambda _: support,
            seed=0,
            optimizer_steps=steps,
            max_seconds=300,
            learning_rate=0.001,
            fixture_diagnostic=True,
        )
        pin = save_checkpoint(model, report, output / arm)
        restored, _ = load_checkpoint(output / arm, manifest_sha256=pin)
        old = torch.get_num_threads()
        torch.set_num_threads(2)
        try:
            with torch.no_grad():
                a = distribution(model, sample.runtime_context(), support)
                b = distribution(restored, sample.runtime_context(), support)
                equal = all(a.decode(k) == b.decode(k) for k in a.target_sha256s)
                traces = [a.decode(k).probability.model_dump(mode="json") for k in a.target_sha256s]
        finally:
            torch.set_num_threads(old)
        if not equal:
            raise RuntimeError("checkpoint probabilities changed")
        (output / arm / "probabilities.json").write_text(json.dumps(traces, indent=2) + "\n")
        rows.append(
            {**report, "checkpoint_manifest_sha256": pin, "restored_probabilities_equal": equal}
        )
        print(arm, report["optimizer_steps"], report["losses"][0], report["losses"][-1], flush=True)
    result = {
        "track": "COMPONENT_FIXTURE_OPTIMIZER_DIAGNOSTIC",
        "runs": rows,
        "total_optimizer_steps": sum(r["optimizer_steps"] for r in rows),
        "aggregate_training_seconds": sum(r["seconds"] for r in rows),
        "natural_training_runs": 0,
        "architecture_selected": None,
        "runtime_support_generator_implemented": False,
        "joint_training_schedules_implemented": False,
        "source_files": source_files,
        "source_unchanged": all(
            hashlib.sha256((ROOT / n).read_bytes()).hexdigest() == h
            for n, h in source_files.items()
        ),
    }
    (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    if not result["source_unchanged"]:
        raise RuntimeError("source changed during run")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--steps", type=int, default=4)
    args = parser.parse_args()
    run(args.output, args.steps)
