"""Three saved neural checkpoints with explicit synthetic conditional model inputs.

This exercises real network inference and real six-dimensional analytic updates.
Inputs, priors, observation model and parent history are controlled fixtures; no
natural semantic accuracy, calibration, posterior publication or action is claimed.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_conditioned_proposal_runtime import (  # noqa: E402
    FixtureModel,
    bound_posterior,
    inputs,
    prior,
)

from cpswm.data_preflight.proposal_inference_session import encoded  # noqa: E402
from cpswm.data_preflight.proposal_samples import ProposalContext  # noqa: E402
from cpswm.data_preflight.typed_proposal_networks import ARMS  # noqa: E402
from cpswm.system.conditioned_inference_session import ConditionedInferenceSession  # noqa: E402
from cpswm.system.reproducibility import content_sha256  # noqa: E402


def run(training: Path, output: Path):
    summary_bytes = (training / "summary.json").read_bytes()
    summary = json.loads(summary_bytes)
    if summary["track"] != "COMPONENT_FIXTURE_OPTIMIZER_DIAGNOSTIC":
        raise ValueError("requires documented development checkpoints")
    pins = {row["arm"]: row["checkpoint_manifest_sha256"] for row in summary["runs"]}
    if set(pins) != set(ARMS):
        raise ValueError("all three unselected arms required")
    output.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(2)
    context, parents = bound_posterior()
    raw = context.model_dump()
    raw["parents"] = [raw["parents"][0], raw["parents"][2]]
    raw["revisions"] = [raw["revisions"][0], raw["revisions"][2]]
    raw["visible"]["pixel_observations"] = raw["visible"]["pixel_observations"][:2]
    context = ProposalContext.model_validate(raw)
    generated, kwargs = inputs(context)
    parents = {
        key: state
        for key, state in parents.items()
        if key in {p.state.particle_id for p in context.parents}
    }
    results = []
    for arm in ARMS:
        model = FixtureModel()
        session = ConditionedInferenceSession(
            training / arm,
            manifest_sha256=pins[arm],
            seed=11,
            prior=prior(),
            model=model,
            expected_model_binding_sha256=model.binding_sha256,
        )
        args = {
            "request_id": "first",
            "context": context,
            "bootstrap_ledger_lineage_ref": kwargs["bootstrap_ledger_lineage_ref"],
            "groups": kwargs["groups"],
            "parent_statistics": parents,
        }
        first = session.process(**args)
        snapshot = session.snapshot()
        if first != session.process(**args) or session.snapshot() != snapshot:
            raise RuntimeError("repeated conditioned inference is not idempotent")
        model.attack = "source"
        try:
            session.process(**{**args, "request_id": "failed"})
        except ValueError:
            pass
        else:
            raise RuntimeError("false measurement source was accepted")
        model.attack = None
        if session.snapshot() != snapshot:
            raise RuntimeError("conditional failure advanced neural sampling or history")
        restored = ConditionedInferenceSession.restore(
            training / arm,
            manifest_sha256=pins[arm],
            snapshot=snapshot,
            snapshot_sha256=hashlib.sha256(snapshot).hexdigest(),
            prior=prior(),
            model=FixtureModel(),
            expected_model_binding_sha256=model.binding_sha256,
        )
        continued = []
        for index in range(3):
            args["request_id"] = f"continued-{index}"
            actual = session.process(**args)
            replay = restored.process(**args)
            if actual != replay or session.snapshot() != restored.snapshot():
                raise RuntimeError("conditioned continuation differs after restore")
            continued.append(
                {
                    "scored_target_sha256": actual.selected.scored_target_sha256,
                    "computed_statistic_state_ref": actual.selected.statistics.reference,
                    "operation": actual.selected.origin.operation.value,
                }
            )
        rows = []
        for row in first.conditioned.candidates:
            state = row.statistics
            rows.append(
                {
                    "scored_target_sha256": row.scored_target_sha256,
                    "operation": row.origin.operation.value,
                    "proposal_statistic_ref": row.origin.candidate.state.statistic_state_ref,
                    "computed_statistic_state_ref": state.reference,
                    "source_groups": [str(x) for x in state.evidence_cluster_ids],
                    "evaluation_mode": row.evaluation_mode,
                    "alpha": state.alpha,
                    "a": state.a,
                    "b": state.b,
                    "information": state.information,
                    "information_vector": state.information_vector,
                }
            )
        (output / f"{arm}.snapshot.json").write_bytes(session.snapshot())
        results.append(
            {
                "arm": arm,
                "manifest_sha256": pins[arm],
                "candidate_count": len(rows),
                "operation_counts": generated.report["operation_counts"],
                "conditional_states": rows,
                "continuations": continued,
                "restored_exactly_equal": True,
                "failure_left_snapshot_unchanged": True,
            }
        )
        print(arm, "88 six-operation candidates conditioned and restored", flush=True)
    if (training / "summary.json").read_bytes() != summary_bytes:
        raise RuntimeError("training dependency changed")
    report = {
        "track": "CONTROLLED_FULL_AXIS_CONDITIONAL_REPLAY_WITH_FIXTURE_TRAINED_WEIGHTS",
        "training_summary_sha256": hashlib.sha256(summary_bytes).hexdigest(),
        "conditional_model_binding_sha256": FixtureModel.binding_sha256,
        "prior_sha256": content_sha256(prior()),
        "runs": results,
        "new_optimizer_steps": 0,
        "natural_training_runs": 0,
        "native_particle_publications": 0,
        "semantic_memory_updates": 0,
        "executed_actions": 0,
        "architecture_selected": None,
        "resampling_policy_selected": None,
        "empirical_calibration_certified": False,
        "complete_natural_closed_loop": False,
    }
    (output / "result.json").write_bytes(encoded(report))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.training, args.output)
