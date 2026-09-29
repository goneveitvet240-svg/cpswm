"""Controlled semantic correction and real camera feedback in ONE durable history.

This is a mixed engineering experiment. Semantic observations and late execution
evidence are explicit fixtures; camera pixels are never promoted to memory rights.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import tempfile
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "tools")]
from clarification_camera_model import CLARIFICATION_SOURCES, ClarificationViewModel  # noqa: E402
from history_loop_scenario import correction_bundles  # noqa: E402
from run_correction_replay_comparison import (  # noqa: E402
    BackboneWiringProbe,
    OracleProducer,
    apply_feedback,
    build,
    ingest,
    summary,
)
from run_neural_pixel_camera_loop import (  # noqa: E402
    SOURCES,
    DiagnosticViewModel,
    diagnostic_house,
    source_identity,
)
from test_native_neural_recovery import OpenWorldJointFixture  # noqa: E402

from cpswm.perception_mapping.pixel_camera_feedback import PixelCategoryOutcomeDecoder  # noqa: E402
from cpswm.system.continuous_state_codec import StateCodec  # noqa: E402
from cpswm.system.continuous_state_store import ContinuousStateStore  # noqa: E402
from cpswm.system.native_neural_production import NeuralNativeProducer  # noqa: E402
from cpswm.system.reproducibility import content_sha256  # noqa: E402
from cpswm.system.revised_camera_collection import collect_revised_posterior_step  # noqa: E402
from cpswm.system.structure_two_continuous_input import (  # noqa: E402
    ContinuousEvidenceInput,
    ObservationDelivery,
)
from cpswm.system.structure_two_particle_workspace import native_content_sha256  # noqa: E402
from cpswm.system.structure_two_semantic_identity import semantic_memory_state  # noqa: E402
from cpswm.system.unity_observation import UnityObservationExecutor  # noqa: E402

SCOPE = "CONTROLLED_SEMANTICS_AND_RETRACTION_WITH_REAL_CAMERA_SAME_HISTORY"


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def save(path, value):
    path.write_text(StateCodec().dumps(value) + "\n")


def load(path):
    return StateCodec().loads(path.read_text())


def decoder_for(weights, task, detector_kind="ssdlite"):
    if task not in ("classification", "clarification"):
        raise ValueError("explicit development task required")
    probe = BackboneWiringProbe.build(seed=171)
    meta = probe.observed_days()[0].after.metadata
    scope = dict(household_id=meta.household_id, session_id=meta.session_id, trace_id=meta.trace_id)
    return PixelCategoryOutcomeDecoder(
        weights_path=weights,
        category="apple",
        sources=CLARIFICATION_SOURCES if task == "clarification" else SOURCES,
        detector_kind=detector_kind,
        **scope,
    ), scope


def open_joint(checkpoint):
    pin = hashlib.sha256((checkpoint / "manifest.json").read_bytes()).hexdigest()
    return NeuralNativeProducer(OpenWorldJointFixture(), checkpoint, manifest_sha256=pin)


def backup(store, path):
    with sqlite3.connect(path) as connection:
        store._db.backup(connection)


def action_key(command):
    return None if command is None else [command.action, command.degrees]


def next_time(stream):
    return max(
        datetime.now(UTC),
        stream._last_arrival + timedelta(microseconds=1),
        stream._last_cutoff + timedelta(microseconds=1),
    )


def validate_feedback_checkpoint(recomputed, recorded):
    """Re-execution allocates fresh ledger/snapshot UUIDs; compare their semantics.

    The existing semantic verifier checks raw ledger hashes before alpha-renaming
    internal IDs. External evidence, authorization and memory values stay exact.
    The recorded accepted checkpoint is then the origin for exact neural replay.
    """
    a, b = recomputed._system.core, recorded._system.core
    if semantic_memory_state(a) != semantic_memory_state(b):
        raise ValueError("accepted feedback semantic checkpoint differs")
    sa, sb = asdict(a.current_snapshot), asdict(b.current_snapshot)
    sa.pop("snapshot_id")
    sb.pop("snapshot_id")
    if sa != sb or a.current_cause_snapshot != b.current_cause_snapshot:
        raise ValueError("accepted feedback snapshot content differs")
    if native_content_sha256(vars(a._particle_workspace)) != native_content_sha256(
        vars(b._particle_workspace)
    ):
        raise ValueError("accepted feedback original native workspace differs")
    fields = (
        "_scope",
        "_raw",
        "_last_arrival",
        "_last_cutoff",
        "_observation_commands",
        "_observation_status",
        "_observation_native_origins",
        "_joint_initial_state_sha256",
        "_joint_dependency_binding",
        "_observation_decoder_binding",
    )
    if any(getattr(recomputed, key) != getattr(recorded, key) for key in fields) or {
        k: v[0] for k, v in recomputed._feedback.items()
    } != {k: v[0] for k, v in recorded._feedback.items()}:
        raise ValueError("accepted feedback input or action binding differs")
    for key in recomputed._feedback:
        left, right = (asdict(s._feedback[key][1]) for s in (recomputed, recorded))
        for row, core in ((left, a), (right, b)):
            if row["snapshot_id"] == core.current_snapshot.snapshot_id:
                row["snapshot_id"] = "current_accepted_snapshot"
        if left != right:
            raise ValueError("accepted feedback returned consequence differs")


def verify_revision_chain(output, *, final_stream, checkpoint, decoder, builder, manifest):
    """Reapply the actual bound correction and rerun neural replay from the earlier DB."""
    with tempfile.TemporaryDirectory(prefix="history-recompute-") as folder:
        path = Path(folder) / "state.sqlite"
        with (
            sqlite3.connect(output / "before-feedback.sqlite") as old,
            sqlite3.connect(path) as new,
        ):
            old.backup(new)
        store = ContinuousStateStore(
            path,
            source_identity=manifest["source_store"],
            dependency_identity=manifest["dependency_store"],
        )
        joint = open_joint(checkpoint)
        try:
            stream = ContinuousEvidenceInput.resume(
                store,
                producer=OracleProducer(),
                context_builder=builder,
                joint_producer=joint,
                observation_decoder=decoder,
            )
            before = summary(stream)
            if before != json.loads(
                (output / "before-memory.json").read_text()
            ) or stream.current_joint_decision_view() != load(output / "before-view.json"):
                raise ValueError("history pre-correction evidence differs")
            stream.visual_observation_support(expected=load(output / "before-visual-support.json"))
            pending = load(output / "old-pending.json")
            if (
                pending is not None
                and stream._observation_commands[pending.action_id][0] != pending
            ):
                raise ValueError("history pending plan differs")
            bundles = load(output / "controlled-feedback.json")
            dates = {
                d.after.detection_time.date()
                for d in BackboneWiringProbe.build(seed=171).observed_days()[:7]
            }
            expected = {
                str(rid)
                for rid, event in stream._system.core._committed_events.items()
                if event.evidence.event_time.date() in dates
            }
            if {b[0].diagnostics["source_revision_id"] for b in bundles} != expected or len(
                bundles
            ) != len(expected):
                raise ValueError("history correction target set differs")
            operations = apply_feedback(stream, bundles, load(output / "feedback-received-at.json"))
            expected_operations = json.loads((output / "feedback-results.json").read_text())
            if [r["operations"] for r in operations] != [
                r["operations"] for r in expected_operations
            ] or summary(stream) != json.loads((output / "after-feedback-memory.json").read_text()):
                raise ValueError("history feedback replay differs")
            # Fresh semantic re-execution intentionally issues new internal UUIDs.
            # Validate all semantic/external bindings first, then replay from the
            # actually accepted post-feedback snapshot for byte-exact identities.
            recomputed = stream
            store.close()
            accepted_path = Path(folder) / "accepted.sqlite"
            with (
                sqlite3.connect(output / "after-feedback.sqlite") as old,
                sqlite3.connect(accepted_path) as new,
            ):
                old.backup(new)
            store = ContinuousStateStore(
                accepted_path,
                source_identity=manifest["source_store"],
                dependency_identity=manifest["dependency_store"],
            )
            joint = open_joint(checkpoint)
            stream = ContinuousEvidenceInput.resume(
                store,
                producer=OracleProducer(),
                context_builder=builder,
                joint_producer=joint,
                observation_decoder=decoder,
            )
            validate_feedback_checkpoint(recomputed, stream)
            old_runtime = stream._system.core._particle_workspace.runtime_id
            invalidated = tuple(
                sorted(stream._system.core._particle_workspace.invalidated_revisions, key=str)
            )
            ledger = native_content_sha256(stream._system.core._hybrid_loop.ledger.export_state())
            stream.replay_joint_posterior()
            if stream._native_joint_decision_view() != final_stream._native_joint_decision_view():
                raise ValueError("fresh neural full-history replay differs")
            steps = load(output / "post-actions.json")
            if not 1 <= len(steps) <= 2 or any(step.replayed for step in steps[1:]):
                raise ValueError("history continuation budget or replay count differs")
            first = steps[0]
            if (
                not first.replayed
                or first.invalidated_revisions != invalidated
                or first.previous_runtime_id != old_runtime
                or first.current_runtime_id != stream._system.core._particle_workspace.runtime_id
                or first.ledger_before_replay_sha256 != ledger
                or first.ledger_after_replay_sha256 != ledger
            ):
                raise ValueError("history replay receipt differs")
            cancelled = tuple(
                sorted(
                    (
                        k
                        for k, v in stream._observation_status.items()
                        if v == "CANCELLED_STALE_JOINT"
                    ),
                    key=str,
                )
            )
            if first.cancelled_command_ids != cancelled:
                raise ValueError("history cancellation receipt differs")
            for step in (load(output / "pre-action.json"), *steps):
                command, delivery = step.collection.command, step.collection.delivery
                if command is not None and (
                    final_stream._observation_commands[command.action_id][0] != command
                    or final_stream._observation_status[command.action_id] != delivery
                ):
                    raise ValueError("history step dispatch differs")
            after = summary(final_stream)
            observed = dict(
                scope=SCOPE,
                executed_actions=sum(
                    type(d) is ObservationDelivery for _, d in final_stream.observation_history()
                ),
                invalidated_sources=len(invalidated),
                neural_calls_after_replay=joint.calls,
                native_records=len(stream._system.core._particle_workspace.records),
                replay_generations=len(stream._system.core._particle_replay_generations),
                replay_ledger_unchanged=ledger
                == native_content_sha256(stream._system.core._hybrid_loop.ledger.export_state()),
                old_pending_cancelled=pending is not None and pending.action_id in cancelled,
                old_pending_action=action_key(pending),
                new_action=action_key(first.collection.command),
                action_changed_at_same_physical_history=action_key(pending)
                != action_key(first.collection.command),
                memory_changed=before["semantic_sha256"] != after["semantic_sha256"],
                memory_argmax_changed=before["argmax"] != after["argmax"],
                source_unchanged=True,
                natural_semantic_transitions=0,
                physical_manipulations=0,
                complete_natural_closed_loop=False,
                empirical_calibration=False,
            )
            if observed != json.loads((output / "result.json").read_text()):
                raise ValueError("history claimed result differs from recomputation")
        finally:
            store.close()


def run(output, *, sdk_python, binary, weights, checkpoint, site, task, detector_kind="ssdlite"):
    if task not in ("classification", "clarification"):
        raise ValueError("explicit development task required")
    output.mkdir(parents=True, exist_ok=False)
    source, files = source_identity()
    decoder, scope = decoder_for(weights, task, detector_kind)
    joint = open_joint(checkpoint)
    probe, backend, stream, store, builder = build(
        output / "state.sqlite",
        seed=171,
        source=source,
        joint_producer=joint,
        observation_decoder=decoder,
    )
    assert tuple(scope.values()) == stream._scope
    write(
        output / "manifest.json",
        dict(
            scope=SCOPE,
            task=task,
            detector_kind=detector_kind,
            private_instance_evaluation=True,
            site=site,
            source=source,
            source_files=files,
            checkpoint_manifest_sha256=hashlib.sha256(
                (checkpoint / "manifest.json").read_bytes()
            ).hexdigest(),
            decoder_binding=decoder.binding_sha256,
            joint_binding=joint.binding_sha256,
            source_store=store.source_identity,
            dependency_store=store.dependency_identity,
            image_size=320,
            pre_correction_actions=1,
            post_correction_budget=2,
            semantic_and_correction_input="CONTROLLED_EXISTING_FIXTURE_NOT_NATURAL",
            status="RUNNING",
        ),
    )
    original = (
        ROOT / "docs/reviews/pc_a/proposal_scheduler_2026-09-13/procthor_run_07/train_house.json"
    )
    house = output / "evaluator_house.json"
    write(house, diagnostic_house(json.loads(original.read_text()), site))
    executor = None
    try:
        write(output / "semantic-ingest.json", ingest(probe, backend, stream, produce_joint=True))
        executor = UnityObservationExecutor(
            python=sdk_python,
            worker=ROOT / "tools/unity_visual_history_worker.py",
            binary=binary,
            house=house,
            log_dir=output / "unity-logs",
            image_size=320,
            **scope,
        )
        model = (ClarificationViewModel if task == "clarification" else DiagnosticViewModel)(
            decoder
        )
        before = collect_revised_posterior_step(
            stream, model=model, executor=executor, decision_time=next_time(stream)
        )
        if before.collection.delivery is not None and not before.collection.delivery.success:
            raise ValueError("pre-correction live action failed")
        save(output / "pre-action.json", before)
        save(output / "before-view.json", stream.current_joint_decision_view())
        before_memory = summary(stream)
        write(output / "before-memory.json", before_memory)
        when = next_time(stream)
        view = stream.current_joint_decision_view()
        problem = model.problem(
            view,
            stream.visible_prefix(cutoff=when),
            decision_time=when,
            execution_history=stream.observation_history(),
        )
        _, pending = stream.prepare_posterior_observation(problem, decision_time=when)
        save(output / "old-pending.json", pending)
        save(output / "before-visual-support.json", stream.visual_observation_support())
        backup(store, output / "before-feedback.sqlite")
        bundles = correction_bundles(probe, stream)
        if not bundles:
            raise ValueError("fixed correction intervention produced no legal target")
        save(output / "controlled-feedback.json", bundles)
        received = next_time(stream)
        save(output / "feedback-received-at.json", received)
        write(output / "feedback-results.json", apply_feedback(stream, bundles, received))
        invalidated = tuple(stream._system.core._particle_workspace.invalidated_revisions)
        if not invalidated:
            raise ValueError("fixed correction did not invalidate native sources")
        write(output / "after-feedback-memory.json", summary(stream))
        backup(store, output / "after-feedback.sqlite")
        store.close()
        store = ContinuousStateStore(
            output / "state.sqlite",
            source_identity=source,
            dependency_identity=content_sha256(sys.version),
        )
        decoder, _ = decoder_for(weights, task, detector_kind)
        joint = open_joint(checkpoint)
        stream = ContinuousEvidenceInput.resume(
            store,
            producer=OracleProducer(),
            context_builder=builder,
            joint_producer=joint,
            observation_decoder=decoder,
        )
        model = (ClarificationViewModel if task == "clarification" else DiagnosticViewModel)(
            decoder
        )
        if stream.visual_observation_support() != load(output / "before-visual-support.json"):
            raise ValueError("visual support changed across feedback and store recovery")
        steps = []
        for _ in range(2):
            result = collect_revised_posterior_step(
                stream, model=model, executor=executor, decision_time=next_time(stream)
            )
            if result.collection.delivery is not None and not result.collection.delivery.success:
                raise ValueError("post-correction live action failed")
            steps.append(result)
            if result.collection.command is None:
                break
        save(output / "post-actions.json", tuple(steps))
        save(output / "final-view.json", stream.current_joint_decision_view())
        save(output / "camera-updates.json", stream.joint_observation_updates())
        save(output / "owned-history.json", stream.observation_history())
        save(output / "visual-support.json", stream.visual_observation_support())
        write(output / "final-memory.json", summary(stream))
        first = steps[0]
        result = dict(
            scope=SCOPE,
            executed_actions=sum(
                type(d) is ObservationDelivery for _, d in stream.observation_history()
            ),
            invalidated_sources=len(invalidated),
            neural_calls_after_replay=joint.calls,
            native_records=len(stream._system.core._particle_workspace.records),
            replay_generations=len(stream._system.core._particle_replay_generations),
            replay_ledger_unchanged=first.ledger_before_replay_sha256
            == first.ledger_after_replay_sha256,
            old_pending_cancelled=pending is not None
            and pending.action_id in first.cancelled_command_ids,
            old_pending_action=action_key(pending),
            new_action=action_key(first.collection.command),
            action_changed_at_same_physical_history=action_key(pending)
            != action_key(first.collection.command),
            memory_changed=before_memory["semantic_sha256"] != summary(stream)["semantic_sha256"],
            memory_argmax_changed=before_memory["argmax"] != summary(stream)["argmax"],
            source_unchanged=source_identity()[0] == source,
            natural_semantic_transitions=0,
            physical_manipulations=0,
            complete_natural_closed_loop=False,
            empirical_calibration=False,
        )
        write(output / "result.json", result)
        assert result["source_unchanged"] and first.replayed and result["replay_ledger_unchanged"]
        if pending is not None:
            assert result["old_pending_cancelled"]
        manifest = json.loads((output / "manifest.json").read_text())
        manifest["status"] = "COMPLETE"
        write(output / "manifest.json", manifest)
    finally:
        if executor is not None:
            executor.close()
        store.close()
    verify(output, weights=weights, checkpoint=checkpoint)
    return result


def verify(output, *, weights, checkpoint):
    manifest = json.loads((output / "manifest.json").read_text())
    if (
        manifest["scope"] != SCOPE
        or manifest["status"] != "COMPLETE"
        or (manifest["source"], manifest["source_files"]) != source_identity()
    ):
        raise ValueError("history manifest/source incomplete or changed")
    task = manifest["task"]
    if (
        manifest["site"] not in ("north", "south")
        or manifest["image_size"] != 320
        or manifest["pre_correction_actions"] != 1
        or manifest["post_correction_budget"] != 2
        or manifest["private_instance_evaluation"] is not True
        or manifest["semantic_and_correction_input"] != "CONTROLLED_EXISTING_FIXTURE_NOT_NATURAL"
    ):
        raise ValueError("history declared configuration differs")
    decoder, _ = decoder_for(weights, task, manifest["detector_kind"])
    original = (
        ROOT / "docs/reviews/pc_a/proposal_scheduler_2026-09-13/procthor_run_07/train_house.json"
    )
    if json.loads((output / "evaluator_house.json").read_text()) != diagnostic_house(
        json.loads(original.read_text()), manifest["site"]
    ):
        raise ValueError("history declared scene differs")
    joint = open_joint(checkpoint)
    if (
        decoder.binding_sha256 != manifest["decoder_binding"]
        or joint.binding_sha256 != manifest["joint_binding"]
    ):
        raise ValueError("history dependencies changed")
    # Build the same callback implementation; this fresh empty owner never supplies evidence.
    with tempfile.TemporaryDirectory(prefix="history-context-") as folder:
        _, _, _, temporary, builder = build(
            Path(folder) / "context.sqlite",
            seed=171,
            source=manifest["source"],
            joint_producer=open_joint(checkpoint),
            observation_decoder=decoder,
        )
        temporary.close()
    store = ContinuousStateStore(
        output / "state.sqlite",
        source_identity=manifest["source_store"],
        dependency_identity=manifest["dependency_store"],
    )
    try:
        stream = ContinuousEvidenceInput.resume(
            store,
            producer=OracleProducer(),
            context_builder=builder,
            joint_producer=joint,
            observation_decoder=decoder,
        )
        final = stream.current_joint_decision_view()
        if final != load(output / "final-view.json") or summary(stream) != json.loads(
            (output / "final-memory.json").read_text()
        ):
            raise ValueError("history final state differs on actual recovery")
        history = stream.observation_history()
        if history != load(output / "owned-history.json"):
            raise ValueError("history action chain differs")
        if stream.joint_observation_updates() != load(output / "camera-updates.json"):
            raise ValueError("history camera update consequences differ")
        stream.visual_observation_support(expected=load(output / "visual-support.json"))
        verify_revision_chain(
            output,
            final_stream=stream,
            checkpoint=checkpoint,
            decoder=decoder,
            builder=builder,
            manifest=manifest,
        )
        private = output / "unity-logs/evaluator_only/sdk-events"
        sdk = [json.loads(p.read_text()) for p in sorted(private.glob("*.json"))]
        delivered = [(c, d) for c, d in history if type(d) is ObservationDelivery]
        if len(sdk) != 4 + len(delivered):
            raise ValueError("SDK history coverage differs")
        if [r["index"] for r in sdk] != list(range(len(sdk))) or [r["owner"] for r in sdk[4:]] != [
            str(c.action_id) for c, _ in delivered
        ]:
            raise ValueError("SDK history order or owner differs")
        if [r["requested"] for r in sdk[:4]] != [
            None,
            dict(action="PausePhysicsAutoSim"),
            dict(action="Pass"),
            dict(action="Pass"),
        ]:
            raise ValueError("SDK preparation differs")
        for row in sdk[1:4]:
            if (
                row["owner"] is not None
                or row["metadata"]["lastAction"] != row["requested"]["action"]
                or row["metadata"]["lastActionSuccess"] is not True
            ):
                raise ValueError("SDK preparation did not actually succeed")
        measurements, evaluation = [], []
        from run_simulator_repeatability import geometry_delta

        if any(
            geometry_delta(sdk[1]["metadata"], row["metadata"])["max_object_translation"] != 0
            or geometry_delta(sdk[1]["metadata"], row["metadata"])["max_object_rotation"] != 0
            for row in sdk[1:]
        ):
            raise ValueError("history frozen objects moved")
        for row in sdk[4:]:
            command, delivery = next(
                (c, d) for c, d in delivered if str(c.action_id) == row["owner"]
            )
            expected = dict(action=command.action)
            if command.action != "Pass":
                expected["degrees"] = command.degrees
            if (
                row["requested"] != expected
                or row["metadata"]["lastAction"] != command.action
                or row["metadata"]["lastActionSuccess"] != delivery.success
            ):
                raise ValueError("SDK history action differs")
            raw = (private / f"{row['index']:03d}-rgb.npy").read_bytes()
            if len(delivery.observations) != 1 or delivery.observations[0].payload_bytes != raw:
                raise ValueError("SDK history RGB differs")
            frames = decoder.measurements(delivery.observations, cutoff=delivery.received_at)
            measurements.extend(frames)
            mask = np.load(private / f"{row['index']:03d}-mask.npy", allow_pickle=False)
            rgb = np.load(private / f"{row['index']:03d}-rgb.npy", allow_pickle=False)
            if rgb.shape != (320, 320, 3) or mask.shape != (320, 320) or mask.dtype != np.bool_:
                raise ValueError("history evaluator image geometry differs")
            evaluation.append(
                dict(
                    action_id=str(command.action_id),
                    action=command.action,
                    degrees=command.degrees,
                    target_pixels=int(mask.sum()),
                    category_candidates=sum(
                        c.category == "apple" for f in frames for c in f.candidates
                    ),
                    target_identity_authorized=False,
                )
            )
        encoded = json.loads(json.dumps([asdict(m) for m in measurements], default=str))
        p = output / "fresh-measurements.json"
        if p.exists() and json.loads(p.read_text()) != encoded:
            raise ValueError("fresh history detections differ")
        write(p, encoded)
        p = output / "private-evaluation.json"
        if p.exists() and json.loads(p.read_text()) != evaluation:
            raise ValueError("history private evaluation differs")
        write(p, evaluation)
        write(
            output / "verification.json",
            dict(
                frames=len(delivered),
                same_final_view=True,
                same_final_memory=True,
                live_unity_rerun=False,
                source_unchanged=True,
            ),
        )
    finally:
        store.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=("run", "verify"), required=True)
    p.add_argument("--site", choices=("north", "south"), default="north")
    p.add_argument("--task", choices=("classification", "clarification"), required=True)
    p.add_argument("--detector-kind", choices=("ssdlite", "fasterrcnn"), default="ssdlite")
    for name in ("output", "sdk-python", "binary", "weights", "checkpoint"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    torch.set_num_threads(2)
    if a.mode == "run":
        print(
            json.dumps(
                run(
                    a.output,
                    sdk_python=a.sdk_python,
                    binary=a.binary,
                    weights=a.weights,
                    checkpoint=a.checkpoint,
                    site=a.site,
                    task=a.task,
                    detector_kind=a.detector_kind,
                )
            )
        )
    else:
        verify(a.output, weights=a.weights, checkpoint=a.checkpoint)
