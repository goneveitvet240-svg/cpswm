"""Pinned original HFD RGB -> continuous perception -> full candidate grammar.

Reads only the runtime subtree. Author phase/outcome/wrench files are not inputs.
Produces diagnostic candidates; no calibrated world-state update is authorized.
"""

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
from uuid import uuid5

import torch

from cpswm.data_preflight.full_hfd_training import encoded
from cpswm.data_preflight.hfd_observation_alignment import load_runtime_observations
from cpswm.data_preflight.proposal_perception import ProposalPixelObservation
from cpswm.data_preflight.runtime_candidates import (
    bootstrap_pixel_context,
    generate_runtime_candidates,
)
from cpswm.perception_mapping.natural_vision import (
    FasterNaturalAppearanceDetector,
    NaturalVisionEvidenceProducer,
)
from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput
from cpswm.system.structure_two_production_system import StructureTwoProductionSystem


def run_window(sequence, rows, detector, hand_detector, output):
    identity = rows[0][1].envelope().identity
    scope = {name: getattr(identity, name) for name in ("household_id", "session_id", "trace_id")}
    records, results = [], []
    producer = NaturalVisionEvidenceProducer(detector, hand_detector)
    session = identity.session_id
    system = StructureTwoProductionSystem(
        owner_key="unresolved-visual-observer",
        object_instance_id=uuid5(session, "unresolved-object"),
        locations=(
            uuid5(session, "unresolved-location-1"),
            uuid5(session, "unresolved-location-2"),
        ),
        authorization_scope_id=uuid5(session, "no-semantic-authorization"),
    )
    stream = ContinuousEvidenceInput(
        system=system, execution_lane="legacy_component_diagnostic", producer=producer, **scope
    )
    before = system.core.semantic_memory_identity()
    snapshot = system.core.current_snapshot
    ledger = system.core._hybrid_loop.ledger.export_state()
    for key, raw in rows:
        when = raw.envelope().arrival_time
        stream.admit((raw,), received_at=when)
        result = stream.advance(cutoff=when)
        if result.status != "INSUFFICIENT_SEMANTIC_EVIDENCE":
            raise RuntimeError("uncalibrated pixels advanced semantic state")
        frame = producer.frames()[-1]
        assoc, interaction = next(
            (a, r) for a, r in producer.interactions() if a.observation_id == frame.observation_id
        )
        records.append(
            {
                "key": key,
                "visual": asdict(frame),
                "association": asdict(assoc),
                "interaction": asdict(interaction),
                **(
                    {
                        "hands": asdict(producer.hand_frames()[-1]),
                        "hand_object_evidence": asdict(producer.hand_object_evidence()[-1]),
                    }
                    if hand_detector is not None
                    else {}
                ),
            }
        )
    restored = NaturalVisionEvidenceProducer(detector, hand_detector)
    restored.restore_state(producer.checkpoint_state())
    if (
        restored.frames() != producer.frames()
        or restored.interactions() != producer.interactions()
        or restored.hand_object_evidence() != producer.hand_object_evidence()
    ):
        raise RuntimeError("perception window restore differs")
    observations = tuple(ProposalPixelObservation.from_frame(f) for f in producer.frames())
    context = bootstrap_pixel_context(
        observations, cutoff=when, source_snapshot_id=snapshot.snapshot_id
    )
    directory = output / sequence
    directory.mkdir(parents=True)
    (directory / "context.json").write_bytes(encoded(context.model_dump(mode="json")))
    try:
        support = generate_runtime_candidates(
            context,
            bootstrap_ledger_lineage_ref="hybrid-ledger:" + ledger.manifest.head_hash,
        )
    except ValueError as error:
        # Whole support remains rejected; no truncated target set is exported.
        if str(error) != "complete support exceeds candidate resource limit; no truncation":
            raise
        support_report = {
            "status": "RESOURCE_REJECTED",
            "reason": str(error),
            "candidate_count": None,
        }
    else:
        (directory / "support.json").write_bytes(
            encoded(
                {
                    "targets": [t.model_dump(mode="json") for t in support.targets],
                    "generation": support.report,
                }
            )
        )
        support_report = {
            "status": "COMPLETE_SUPPORT_GENERATED",
            "candidate_count": len(support.targets),
            "generation": support.report,
        }
    if (
        system.core.semantic_memory_identity() != before
        or system.core.current_snapshot != snapshot
        or system.core._hybrid_loop.ledger.export_state() != ledger
        or stream.execution_traces()
    ):
        raise RuntimeError("diagnostic inference changed memory/ledger/action state")
    results.append(
        {
            "sequence": sequence,
            "frames": len(observations),
            "support": support_report,
            "core_ledger_unchanged": True,
            "execution_traces": 0,
            "perception_restore_equal": True,
        }
    )
    return records, results[0]


def run(runtime: Path, manifest_sha256: str, weights: Path, output: Path):
    inputs = load_runtime_observations(runtime, manifest_sha256=manifest_sha256)
    output.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(2)
    groups = defaultdict(list)
    for key, raw in inputs:
        groups[key.split("/")[0]].append((key, raw))
    records, results = [], []
    for sequence, rows in groups.items():
        identity = rows[0][1].envelope().identity
        scope = {
            name: getattr(identity, name) for name in ("household_id", "session_id", "trace_id")
        }
        detector = FasterNaturalAppearanceDetector(weights_path=weights, **scope)
        window_records, window_result = run_window(sequence, rows, detector, None, output)
        records.extend(window_records)
        results.append(window_result)
    result = {
        "runtime_manifest_sha256": manifest_sha256,
        "input_frames": len(inputs),
        "sequences": results,
        "candidates": dict(
            Counter(d["category"] for r in records for d in r["visual"]["candidates"])
        ),
        "associations": dict(
            Counter(d["status"] for r in records for d in r["association"]["detections"])
        ),
        "role_alternatives": sum(len(r["interaction"]["role_alternatives"]) for r in records),
        "author_labels_read_by_frontend": False,
        "proposal_targets_supervised": 0,
        "proposal_network_training_steps": 0,
        "natural_semantic_publications": 0,
        "memory_writes": 0,
        "executed_actions": 0,
        "records": records,
    }
    payload = json.dumps(result, default=str, sort_keys=True, indent=2).encode()
    (output / "result.json").write_bytes(payload)
    (output / "result.sha256").write_text(hashlib.sha256(payload).hexdigest() + "\n")
    return {k: v for k, v in result.items() if k != "records"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    print(json.dumps(run(**vars(parser.parse_args())), indent=2, default=str))
