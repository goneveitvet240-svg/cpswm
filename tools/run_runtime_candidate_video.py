"""Real cropped pixels -> detector -> automatic candidates -> three proposal arms.

The first requested regular sample frames are fixed before inference. The final frame
is deliberately delayed in a delivery experiment, not an independently labelled
contact event. No evaluator CSV, target annotation, or fixture candidate is read.
"""

import argparse
import hashlib
import json
import math
from collections import defaultdict
from datetime import timedelta
from pathlib import Path
from uuid import uuid5

import torch
from run_bimanual_pixel_frontend import CROP, POLICY, validate_pixel_input
from run_person_interaction_video import run as run_frontend

from cpswm.data_preflight.proposal_inference_session import encoded
from cpswm.data_preflight.proposal_perception import ProposalPixelObservation
from cpswm.data_preflight.runtime_candidate_session import RuntimeCandidateSession
from cpswm.data_preflight.runtime_candidates import (
    bootstrap_pixel_context,
    generate_runtime_candidates,
)
from cpswm.data_preflight.typed_proposal_networks import ARMS
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_production_system import StructureTwoProductionSystem


def run(video: Path, weights: Path, training: Path, output: Path, frames: int = 2):
    if type(frames) is not int or frames not in (2, 3, 4):
        raise ValueError("fixed development prefix must contain two, three or four frames")
    policy_bytes = POLICY.read_bytes()
    policy = json.loads(policy_bytes)
    record = validate_pixel_input(video, policy)
    training_bytes = (training / "summary.json").read_bytes()
    training_report = json.loads(training_bytes)
    if training_report["track"] not in {
        "COMPONENT_FIXTURE_OPTIMIZER_DIAGNOSTIC",
        "COMPONENT_FIXTURE_WEIGHTS_EXECUTION_DERIVATION",
    }:
        raise ValueError("development experiment requires the documented fixture checkpoints")
    if training_report["track"] == "COMPONENT_FIXTURE_WEIGHTS_EXECUTION_DERIVATION" and (
        training_report.get("new_optimizer_steps") != 0
        or training_report.get("production_authorized") is not False
        or training_report.get("architecture_selected") is not None
    ):
        raise ValueError("execution derivation cannot claim training, selection or production")
    pins = {r["arm"]: r["checkpoint_manifest_sha256"] for r in training_report["runs"]}
    if set(pins) != set(ARMS):
        raise ValueError("all three unselected arms required")
    output.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(2)
    # Fixed development prefix, not a selected successful interaction window.
    frontend = run_frontend(
        video=video,
        expected_sha256=record["sha256"],
        source_url=policy["source_url"],
        crop=CROP,
        start=0,
        duration=frames / 10,
        fps=10,
        weights=weights,
        hand_model=None,
        detector_name="fasterrcnn",
        output=output / "pixels",
        include_records=True,
    )
    raw_pixels = tuple(
        ProposalPixelObservation.model_validate(r["visual"]) for r in frontend["records"]
    )
    if len(raw_pixels) != frames:
        raise ValueError("fixed prefix must decode exactly the requested sample frames")
    # Exact bytes were freshly decoded from an enrolled video. The old source
    # records remain intact; only this explicit experimental delivery is delayed.
    delivery = raw_pixels[-1].arrival_time + timedelta(seconds=1)
    late = ProposalPixelObservation.model_validate(
        {
            **raw_pixels[-1].model_dump(),
            "arrival_time": delivery,
            "inference_cutoff": delivery,
        }
    )
    early = raw_pixels[:-1]
    scope = raw_pixels[0]
    core = StructureTwoProductionSystem(
        owner_key="unresolved-visual-observer",
        object_instance_id=uuid5(scope.session_id, "unresolved-object"),
        locations=(
            uuid5(scope.session_id, "unresolved-location-1"),
            uuid5(scope.session_id, "unresolved-location-2"),
        ),
        authorization_scope_id=uuid5(scope.session_id, "no-semantic-authorization"),
    ).core
    before = core.semantic_memory_identity()
    ledger = "hybrid-ledger:" + core._hybrid_loop.ledger.export_state().manifest.head_hash
    snapshot = core.current_snapshot.snapshot_id
    contexts = {
        "before_delivery": bootstrap_pixel_context(
            (*early, late), cutoff=raw_pixels[-1].arrival_time, source_snapshot_id=snapshot
        ),
        "omission_control": bootstrap_pixel_context(
            early, cutoff=delivery, source_snapshot_id=snapshot
        ),
        "after_delivery": bootstrap_pixel_context(
            (*early, late), cutoff=delivery, source_snapshot_id=snapshot
        ),
    }
    supports = {
        k: generate_runtime_candidates(ctx, bootstrap_ledger_lineage_ref=ledger)
        for k, ctx in contexts.items()
    }
    for name, support in supports.items():
        (output / f"{name}.support.json").write_bytes(
            encoded(
                {
                    "context": support.context.model_dump(mode="json"),
                    "targets": [t.model_dump(mode="json") for t in support.targets],
                    "generation": support.report,
                }
            )
        )
    results = []
    for arm in ARMS:
        checkpoint = training / arm
        session = RuntimeCandidateSession(checkpoint, manifest_sha256=pins[arm], seed=11)
        first = session.process(
            request_id="before",
            context=contexts["before_delivery"],
            bootstrap_ledger_lineage_ref=ledger,
        )
        blob = session.snapshot()
        restored = RuntimeCandidateSession.restore(
            checkpoint,
            manifest_sha256=pins[arm],
            snapshot=blob,
            snapshot_sha256=hashlib.sha256(blob).hexdigest(),
        )
        if (
            first
            != restored.process(
                request_id="before",
                context=contexts["before_delivery"],
                bootstrap_ledger_lineage_ref=ledger,
            )
            or restored.snapshot() != blob
        ):
            raise RuntimeError("repeated restored request changed proposal or RNG")
        rows = {}
        for name in ("omission_control", "after_delivery"):
            args = {
                "request_id": name,
                "context": contexts[name],
                "bootstrap_ledger_lineage_ref": ledger,
            }
            online = session.process(**args)
            replay = restored.process(**args)
            if online != replay or session.snapshot() != restored.snapshot():
                raise RuntimeError("late evidence continuation changed after restore")
            scored = session._engine.score_support(
                context=online.support.context, support=online.support.targets
            )
            event_mass: dict[str, float] = defaultdict(float)
            actor_mass: dict[str, float] = defaultdict(float)
            rows[name] = {"candidate_count": len(scored), "scores": []}
            for decoded in scored:
                q = math.exp(decoded.probability.joint_log_probability)
                event_mass[">".join(e.kind for e in decoded.target.candidate.events)] += q
                actor_mass[decoded.target.candidate.events[-1].actor_key] += q
                rows[name]["scores"].append(
                    {
                        "target": decoded.target.model_dump(mode="json"),
                        "probability": decoded.probability.model_dump(mode="json"),
                    }
                )
            if abs(math.fsum(event_mass.values()) - 1) > 1e-10:
                raise RuntimeError("incomplete probability mass")
            rows[name].update(
                {
                    "event_mass": dict(event_mass),
                    "actor_mass": dict(actor_mass),
                    "sampled_target": online.receipt.decoded.target.model_dump(mode="json"),
                    "restored_exactly_equal": True,
                }
            )
        (output / f"{arm}.snapshot.json").write_bytes(session.snapshot())
        results.append(
            {
                "arm": arm,
                "checkpoint_manifest_sha256": pins[arm],
                "conditions": rows,
                "event_mass_changed_at_same_cutoff": rows["omission_control"]["event_mass"]
                != rows["after_delivery"]["event_mass"],
                "generated_history_restore_equal": True,
            }
        )
        print(arm, "real generated candidates and delayed continuation complete", flush=True)
    after = core.semantic_memory_identity()
    if before != after or core._particle_workspace.batch is not None:
        raise RuntimeError("proposal experiment changed semantic core or published particles")
    if (
        POLICY.read_bytes() != policy_bytes
        or (training / "summary.json").read_bytes() != training_bytes
    ):
        raise RuntimeError("experiment dependencies changed")
    result = {
        "track": "REAL_PIXEL_GENERATED_PROPOSALS_WITH_FIXTURE_TRAINED_WEIGHTS",
        "video_sha256": record["sha256"],
        "policy_sha256": hashlib.sha256(policy_bytes).hexdigest(),
        "training_summary_sha256": hashlib.sha256(training_bytes).hexdigest(),
        "training_bundle_kind": training_report["track"],
        "frames": len(raw_pixels),
        "detections": [len(p.candidates) for p in raw_pixels],
        "raw_pixel_sha256s": [p.input_sha256 for p in raw_pixels],
        "frontend_core_unchanged": frontend["core_unchanged_verified"],
        "bootstrap": True,
        "parent_particles_invented": False,
        "contexts": {k: v.report for k, v in supports.items()},
        "runs": results,
        "source_snapshot_id": str(snapshot),
        "core_identity_before": before,
        "core_identity_after": after,
        "core_identity_sha256": content_sha256(before),
        "synthetic_delivery_delay_seconds": 1,
        "candidate_event_time_semantics": "archive_import_acquisition_UTC_not_physical_event_gold",
        "association_clock": "receipt_bound_resampled_media_grid",
        "truth_labels_read": False,
        "natural_training_runs": 0,
        "new_optimizer_steps": 0,
        "architecture_selected": None,
        "probabilities_calibrated": False,
        "native_particle_publications": 0,
        "semantic_memory_updates": 0,
        "executed_actions": 0,
        "complete_natural_closed_loop": False,
    }
    (output / "result.json").write_bytes(encoded(result))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--training", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frames", type=int, choices=(2, 3, 4), default=2)
    args = parser.parse_args()
    run(args.video, args.weights, args.training, args.output, args.frames)
