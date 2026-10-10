"""Same learned frontend: ordinary source-history replay vs the real CPSWM owner.

Camera deliveries re-envelope recorded pixels/pose in a controlled semantic
fixture. They are explicitly replay deliveries, not new physical captures.
"""

import argparse
import base64
import json
import sqlite3
import subprocess
from datetime import timedelta
from pathlib import Path

from run_matched_transition_death_test import checked, load, raw_rows, save
from surface_pipeline_fixture import make_case
from test_native_neural_production import checkpoints

from cpswm.perception_mapping.external_object_sequence import ExternalObjectSequence
from cpswm.perception_mapping.natural_mask_surface import NaturalMaskSurfaceDetector
from cpswm.perception_mapping.unity_rgbd import observations_from_response
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_continuous_input import ObservationDelivery
from cpswm.system.surface_episode import (
    collect_scheduled_surface,
    effective_surface_state,
    report_from_surface_state,
)


class ReplayCamera:
    def __init__(self, root, manifest, scope):
        self.root, self.manifest, self.scope = root, manifest, scope
        self.deliveries = []

    def execute(self, command):
        item = self.manifest["frames"][len(self.deliveries)]
        raw = load(checked(self.root, item["raw"], item["raw_sha256"]))
        rows = raw_rows(raw)
        pose = json.loads(rows[2].payload_bytes)
        capture = command.decision_time + timedelta(seconds=1)
        arrival = capture + timedelta(seconds=1)
        fixed = {
            "schema_id",
            "action_id",
            "capture_time",
            "rgb_sha256",
            "depth_sha256",
            "worker_sha256",
            "unity_sha256",
            "scene_sha256",
            "configuration_sha256",
        }
        response = dict(
            action_id=str(command.action_id),
            capture_time=capture.isoformat(),
            success=True,
            error="",
            camera={k: v for k, v in pose.items() if k not in fixed},
            rgb_npy=base64.b64encode(rows[0].payload_bytes).decode(),
            depth_npy=base64.b64encode(rows[1].payload_bytes).decode(),
        )
        paired = observations_from_response(
            response,
            action_id=command.action_id,
            scope=self.scope,
            arrival=arrival,
            provenance=dict(
                worker=content_sha256("controlled-recorded-camera-replay@1"),
                unity=pose["unity_sha256"],
                house=pose["scene_sha256"],
                capture_configuration=pose["configuration_sha256"],
            ),
        )
        delivery = ObservationDelivery(command.action_id, paired, True, "", arrival)
        self.deliveries.append(delivery)
        return delivery


def reports(state, queries, reference):
    return [report_from_surface_state(state, **q, reference_action=reference) for q in queries]


def public_report(value):
    return [{k: v for k, v in r.items() if k != "source_view_sha256"} for r in value]


def frontend_records(state):
    fields = {"new_surface_observations", "unique_surface_counts", "independent_evidence_count"}
    return [{k: v for k, v in r.items() if k not in fields} for r in state["records"]]


def ordinary(deliveries, args):
    scope = deliveries[0].observations[0].envelope().identity
    detector = NaturalMaskSurfaceDetector(
        weights_path=args.mask_weights,
        household_id=scope.household_id,
        session_id=scope.session_id,
        trace_id=scope.trace_id,
    )
    sequence = ExternalObjectSequence(detector, args.frontend)
    records = [sequence.observe(d.observations, cutoff=d.received_at)[0] for d in deliveries]
    return dict(
        records=records,
        history={},
        action_ids=[str(d.action_id) for d in deliveries],
        view_sha256=content_sha256(records),
    )


def run(args):
    import torch

    torch.set_num_threads(2)
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = load(args.manifest)
    if manifest["input_sha256"] != content_sha256(
        {k: v for k, v in manifest.items() if k != "input_sha256"}
    ):
        raise ValueError("manifest differs")

    class Factory:
        def mktemp(self, name):
            p = args.output / name
            p.mkdir()
            return p

    case = make_case(
        args.output / "state.sqlite",
        checkpoints.__wrapped__(Factory()),
        args.ssdlite_weights,
        args.mask_weights,
        schedule=manifest["schedule"],
        object_frontend=args.frontend,
    )
    stream = case["stream"]
    camera = ReplayCamera(args.root, manifest, stream._scope)
    when = case["when"]
    steps = []
    for index in range(manifest["budget"]):
        command, delivery, update = collect_scheduled_surface(
            stream, executor=camera, decision_time=when
        )
        reference = str(camera.deliveries[0].action_id)
        state = effective_surface_state(stream)
        plain = ordinary(camera.deliveries, args)
        ours, baseline = (
            reports(state, manifest["queries"], reference),
            reports(plain, manifest["queries"], reference),
        )
        comparison = dict(
            frontend_equal=content_sha256(frontend_records(state))
            == content_sha256(frontend_records(plain)),
            readout_equal=content_sha256(public_report(ours))
            == content_sha256(public_report(baseline)),
            raw_python_frontend_equal=frontend_records(state) == frontend_records(plain),
            comparison_scope="canonical JSON; owner persistence normalizes tuples to lists",
        )
        save(args.output / f"comparison-{index}.json", comparison)
        if not comparison["frontend_equal"] or not comparison["readout_equal"]:
            raise ValueError("same frontend / memory readout differs on normal replay")
        steps.append(
            dict(
                index=index,
                action_id=str(command.action_id),
                reports=ours,
                ordinary_reports=baseline,
                same_frontend=True,
            )
        )
        save(args.output / f"state-{index}.json", state)
        save(
            args.output / f"delivery-{index}.json",
            dict(
                action_id=str(command.action_id),
                received_at=delivery.received_at.isoformat(),
                observations=[
                    dict(
                        envelope_json=r.envelope_json,
                        payload_base64=base64.b64encode(r.payload_bytes).decode(),
                        capture_receipt_sha256=r.capture_receipt_sha256,
                        depth_unit=r.depth_unit,
                    )
                    for r in delivery.observations
                ],
            ),
        )
        print(
            json.dumps(dict(index=index, owner_update=str(update), same_frontend=True))[:300],
            flush=True,
        )
        when = delivery.received_at + timedelta(seconds=1)
    final = reports(effective_surface_state(stream), manifest["queries"], reference)
    save(
        args.output / "restore.json",
        dict(
            config=case["config"],
            models=case["models"],
            checkpoint=str(case["checkpoint"]),
            pin=case["pin"],
            queries=manifest["queries"],
            reference_action=reference,
        ),
    )
    with sqlite3.connect(args.output / "copy.db") as db:
        case["store"]._db.backup(db)
    physical_before = len(stream.observation_history())
    removed = camera.deliveries[1].action_id
    stream.withdraw_owned_position_observation(
        removed, reason="predeclared middle-source withdrawal in controlled replay"
    )
    state = effective_surface_state(stream)
    kept = [d for d in camera.deliveries if str(d.action_id) in state["action_ids"]]
    plain = ordinary(kept, args)
    after, baseline = (
        reports(state, manifest["queries"], reference),
        reports(plain, manifest["queries"], reference),
    )
    if content_sha256(frontend_records(state)) != content_sha256(
        frontend_records(plain)
    ) or content_sha256(public_report(after)) != content_sha256(public_report(baseline)):
        raise ValueError("ordinary source-aware rebuilding differs after same effective withdrawal")
    removed_ids = {
        str(r.envelope().identity.observation_id) for r in camera.deliveries[1].observations
    }
    if removed_ids.intersection(
        str(k) for h in state["history"].values() for o in h for k in o["observation_ids"]
    ):
        raise ValueError("withdrawn source still contributes")
    if len(stream.observation_history()) != physical_before:
        raise ValueError("physical journal changed during withdrawal")
    save(args.output / "withdraw-state.json", state)
    result = dict(
        status="COMPLETED",
        code_sha=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        frontend_configuration=args.frontend,
        steps=steps,
        final_reports=final,
        withdrawn_action=str(removed),
        after=after,
        ordinary_after=baseline,
        effective_actions=state["action_ids"],
        same_after_withdraw=True,
        physical_journal_unchanged=True,
        new_physical_dispatches=0,
        replay_deliveries=len(camera.deliveries),
        scope="controlled semantics; recorded pixels; ordinary full history + source-aware rebuild",
    )
    save(args.output / "result.json", result)
    case["store"].close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "manifest", "output", "mask-weights", "ssdlite-weights", "frontend"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    args.frontend = load(args.frontend)
    run(args)
