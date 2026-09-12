"""Contract/state-machine component tests, not learned-model or real-actor evidence."""

import copy
import json
import math
import os
import subprocess
import sys
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import numpy as np
import pytest

from cpswm.contracts.habit_learning import ActorEvidenceTrack
from cpswm.data_preflight.capture_prefix import released_capture_prefix
from cpswm.data_preflight.procthor_execution import execute_schedule
from cpswm.data_preflight.procthor_schedule import ReleaseQueue, build_schedule, digest, event_chain
from cpswm.data_preflight.proposal_samples import (
    JointProposalProbability,
    ProposalSample,
    audit_samples,
    export_sample,
)
from cpswm.system.evaluation_operations.d0_shift_scenarios import D0ShiftScenarioGenerator
from cpswm.system.reproducibility import content_sha256


def uid(key):
    return str(uuid5(NAMESPACE_URL, "proposal-contract-fixture:" + key))


@pytest.fixture(scope="module")
def sample_payload():
    case = (
        D0ShiftScenarioGenerator()
        .generate(actor_evidence_track=ActorEvidenceTrack.CONTROLLED_NOISE)
        .cases[0]
        .model_input
    )
    actor = case.control_actor_evidence[0]
    det = next(
        x
        for x in case.control_run.detection_results
        if x.metadata.record_id == actor.source_detection_result_id
    )
    op = next(
        x
        for x in case.control_run.observation_opportunities
        if x.metadata.record_id == det.observation_opportunity_id
    )
    now = op.opportunity_time

    def hypothesis(
        name,
        *,
        parent=None,
        instance="instance_a",
        cause="noise",
        regime="stay",
        handoff=False,
        unknown=False,
    ):
        chain = [("pick_up", "actor_a", None), ("carry", "actor_a", None)]
        if handoff:
            chain += [
                ("handoff", "actor_a", "actor_b"),
                ("carry", "actor_b", None),
                ("handoff", "actor_b", "actor_c"),
                ("carry", "actor_c", None),
            ]
        chain += [("place", "actor_c" if handoff else "actor_a", None)]
        if unknown:
            chain = [("unresolved", "unknown_actor", None)]
        events, roles, counts = [], [], {}
        role_names = {"pick_up": "pickup_actor", "carry": "carrier", "place": "placer"}
        for i, (kind, person, receiver) in enumerate(chain):
            events.append(
                {
                    "event_id": uid(f"event-{name}-{i}"),
                    "time": (now - timedelta(seconds=20 - i)).isoformat(),
                    "kind": kind,
                    "instance_key": instance,
                    "actor_key": person,
                    "receiver_key": receiver,
                    "location_key": "location_a",
                }
            )
            bindings = (
                [(role_names[kind], person)]
                if kind in role_names
                else (
                    [("handoff_giver", person), ("handoff_receiver", receiver)]
                    if kind == "handoff"
                    else []
                )
            )
            for role, person in bindings:
                counts[role] = counts.get(role, 0) + 1
                roles.append(
                    {
                        "role": role if counts[role] == 1 else f"{role}:{counts[role]}",
                        "actor_key": person,
                    }
                )
        return {
            "state": {
                "particle_id": uid(name),
                "parent_particle_id": uid(parent) if parent else None,
                "source_snapshot_id": uid("snapshot"),
                "event_hypothesis_id": uid("hypothesis-" + name),
                "revision_id": uid("revision-" + name),
                "parent_revision_id": uid("revision-" + parent) if parent else None,
                "ordered_actor_roles": roles,
                "instance_association_key": instance,
                "change_cause": cause,
                "regime_decision": regime,
                "regime_id": None if regime == "unresolved" else "regime_a",
                "run_length": 3,
                "statistic_state_ref": "component-stat:" + name,
                "ledger_lineage_ref": "component-ledger:a",
            },
            "events": events,
        }

    parents = [
        hypothesis("root"),
        hypothesis("child", parent="root"),
        hypothesis("retired", cause="habit"),
    ]
    candidates = [
        ("branch", hypothesis("branch", parent="child", cause="observation", handoff=True)),
        ("revise", hypothesis("revise", parent="child", instance="instance_b", cause="identity")),
        ("retract", copy.deepcopy(parents[1])),
        (
            "reactivate",
            hypothesis("reactivate", parent="retired", cause="habit", regime="reactivate"),
        ),
        ("rejuvenate", hypothesis("rejuvenate", parent="child", cause="actor")),
        (
            "preserve_unresolved",
            hypothesis(
                "unresolved",
                parent="child",
                instance="unknown_instance",
                cause="unresolved",
                regime="unresolved",
                unknown=True,
            ),
        ),
        ("branch", hypothesis("create", parent="child", cause="habit", regime="create")),
    ]
    candidates[2][1]["state"].update(
        particle_id=uid("retract"),
        parent_particle_id=uid("child"),
        revision_id=uid("revision-retract"),
        parent_revision_id=uid("revision-child"),
    )
    revisions = [
        {
            key: p["state"][key]
            for key in (
                "revision_id",
                "parent_revision_id",
                "particle_id",
                "event_hypothesis_id",
                "statistic_state_ref",
                "ledger_lineage_ref",
            )
        }
        for p in parents
    ]
    for i, revision in enumerate(revisions):
        revision["status"] = "retracted" if i == 2 else "active"
    targets = [
        {
            "operation": operation,
            "candidate": candidate,
            "evidence_ids": [str(det.metadata.record_id)],
            "replaced_revision_ids": [uid("revision-root"), uid("revision-child")]
            if operation == "rejuvenate"
            else [],
            "replay_required": operation == "rejuvenate",
        }
        for operation, candidate in candidates
    ]
    return {
        "sample_id": uid("sample"),
        "partition": "development",
        "house_id": "component-house",
        "house_sha256": "a" * 64,
        "schedule_block_id": "component-block",
        "annotation_kind": "component_fixture",
        "annotation_ref": "unit-test:explicitly-not-native-trace",
        "source_snapshot_id": uid("snapshot"),
        "visible": {
            "opportunities": [op.model_dump(mode="json")],
            "detections": [det.model_dump(mode="json")],
            "actor_evidence": [],
            "arrivals": [
                {"record_id": str(op.metadata.record_id), "received_at": now.isoformat()},
                {
                    "record_id": str(det.metadata.record_id),
                    "received_at": (now + timedelta(hours=1)).isoformat(),
                },
            ],
            "cutoff": (now + timedelta(hours=2)).isoformat(),
        },
        "parents": parents,
        "revisions": revisions,
        "instance_support": ["instance_a", "instance_b", "unknown_instance"],
        "actor_support": ["actor_a", "actor_b", "actor_c", "unknown_actor"],
        "compatible_targets": targets,
    }


def test_complete_contract_and_all_operations(sample_payload):
    sample = ProposalSample.model_validate(sample_payload)
    result = audit_samples((sample,))
    assert not result["missing_operations"]
    assert len(result["chain_patterns"]) == 3
    assert not result["training_ready"]
    out = export_sample(sample)
    assert "training_targets" not in out["model_input"]
    assert "annotation_kind" not in json.dumps(out["model_input"])
    assert {x["candidate"]["state"]["change_cause"] for x in out["training_targets"]} == {
        "observation",
        "actor",
        "identity",
        "habit",
        "noise",
        "unresolved",
    }
    assert {x["candidate"]["state"]["regime_decision"] for x in out["training_targets"]} == {
        "stay",
        "create",
        "reactivate",
        "unresolved",
    }


@pytest.mark.parametrize(
    "attack",
    [
        "role_order",
        "wrong_carrier",
        "wrong_placer",
        "wrong_receiver",
        "cross_instance",
        "future_event",
        "duplicate_event",
        "cross_snapshot",
        "orphan_parent",
        "orphan_revision",
        "cyclic_lineage",
        "cross_ledger",
        "unreferenced_revision",
        "missing_evidence",
        "late_evidence",
        "retract_changes_identity",
        "reactivate_active",
        "revise_retracted",
        "rejuvenate_append",
        "rejuvenate_wrong_suffix",
        "rejuvenate_no_delay",
        "resolved_fallback",
        "duplicate_support",
        "unknown_removed",
        "duplicate_target",
        "extra_truth",
    ],
)
def test_forged_complete_contracts_rejected(sample_payload, attack):
    data = copy.deepcopy(sample_payload)
    target = data["compatible_targets"][0]
    state = target["candidate"]["state"]
    events = target["candidate"]["events"]
    if attack == "role_order":
        state["ordered_actor_roles"].reverse()
    elif attack == "wrong_carrier":
        events[1]["actor_key"] = "actor_b"
    elif attack == "wrong_placer":
        events[-1]["actor_key"] = "actor_a"
    elif attack == "wrong_receiver":
        events[2]["receiver_key"] = "actor_a"
    elif attack == "cross_instance":
        events[0]["instance_key"] = "instance_b"
    elif attack == "future_event":
        events[-1]["time"] = "2099-01-01T00:00:00Z"
    elif attack == "duplicate_event":
        events[1]["event_id"] = events[0]["event_id"]
    elif attack == "cross_snapshot":
        state["source_snapshot_id"] = uid("foreign")
    elif attack == "orphan_parent":
        state["parent_particle_id"] = uid("foreign")
    elif attack == "orphan_revision":
        state["parent_revision_id"] = uid("foreign")
    elif attack == "cyclic_lineage":
        data["revisions"][0]["parent_revision_id"] = data["revisions"][1]["revision_id"]
    elif attack == "cross_ledger":
        state["ledger_lineage_ref"] = "other-ledger"
    elif attack == "unreferenced_revision":
        data["parents"].pop()
    elif attack == "missing_evidence":
        target["evidence_ids"] = [uid("foreign")]
    elif attack == "late_evidence":
        data["visible"]["arrivals"][1]["received_at"] = "2099-01-01T00:00:00Z"
    elif attack == "retract_changes_identity":
        data["compatible_targets"][2]["candidate"]["state"]["change_cause"] = "identity"
    elif attack == "reactivate_active":
        data["revisions"][2]["status"] = "active"
    elif attack == "revise_retracted":
        data["revisions"][1]["status"] = "retracted"
    elif attack == "rejuvenate_append":
        data["compatible_targets"][4]["replay_required"] = False
    elif attack == "rejuvenate_wrong_suffix":
        data["compatible_targets"][4]["replaced_revision_ids"].reverse()
    elif attack == "rejuvenate_no_delay":
        data["visible"]["arrivals"][1]["received_at"] = data["visible"]["detections"][0][
            "metadata"
        ]["recorded_time"]
    elif attack == "resolved_fallback":
        data["compatible_targets"][5]["candidate"]["state"]["change_cause"] = "noise"
    elif attack == "duplicate_support":
        data["instance_support"].append("instance_a")
    elif attack == "unknown_removed":
        data["actor_support"].remove("unknown_actor")
    elif attack == "duplicate_target":
        data["compatible_targets"].append(target)
    elif attack == "extra_truth":
        data["visible"]["true_actor"] = "actor_a"
    with pytest.raises(ValueError):
        ProposalSample.model_validate(data)


def test_export_revalidates_mutated_nested_data(sample_payload):
    sample = ProposalSample.model_validate(sample_payload)
    bad = sample.model_copy(
        update={
            "compatible_targets": (
                sample.compatible_targets[0].model_copy(update={"evidence_ids": ()}),
            )
        }
    )
    with pytest.raises(ValueError):
        export_sample(bad)


@pytest.mark.parametrize("rename", [False, True])
def test_split_leakage_rejected_even_when_house_renamed(sample_payload, rename):
    first = ProposalSample.model_validate(sample_payload)
    second = copy.deepcopy(sample_payload)
    second.update(sample_id=uid("second"), partition="train", schedule_block_id="another-block")
    if rename:
        second["house_id"] = "renamed"
    with pytest.raises(ValueError, match="house crosses"):
        audit_samples((first, ProposalSample.model_validate(second)))


def probability_payload():
    payload = {
        "root_context_sha256": "a" * 64,
        "factors": [
            {
                "axis": axis,
                "context_sha256": "a" * 64,
                "choices": ["a", "b"],
                "probabilities": [0.3, 0.7],
                "selected": "b",
            }
            for axis in ("operation", "parent", "H", "R", "I", "C", "Z", "r", "V")
        ],
        "joint_log_probability": 9 * math.log(0.7),
    }
    prefix = []
    for factor in payload["factors"]:
        factor["context_sha256"] = content_sha256({"root": "a" * 64, "prefix": prefix})
        prefix.append((factor["axis"], factor["selected"]))
    return payload


def test_complete_conditional_probability_trace():
    JointProposalProbability.model_validate(probability_payload())


@pytest.mark.parametrize(
    "attack",
    [
        "missing_axis",
        "reorder",
        "wrong_sum",
        "nan",
        "unnormalized",
        "duplicate_choice",
        "zero_choice",
    ],
)
def test_probability_omissions_rejected(attack):
    data = probability_payload()
    if attack == "missing_axis":
        data["factors"].pop()
    elif attack == "reorder":
        data["factors"].reverse()
    elif attack == "wrong_sum":
        data["joint_log_probability"] = math.log(0.7)
    elif attack == "nan":
        data["factors"][0]["probabilities"][0] = float("nan")
    elif attack == "unnormalized":
        data["factors"][0]["probabilities"][0] = 0.4
    elif attack == "duplicate_choice":
        data["factors"][0]["choices"][0] = "b"
    elif attack == "zero_choice":
        data["factors"][0]["probabilities"] = [1, 0]
    with pytest.raises(ValueError):
        JointProposalProbability.model_validate(data)


def schedule(seed=13, days=7, actors=3):
    return build_schedule(
        house_id="component-house",
        house_sha256="a" * 64,
        schedule_block_id=f"component:{seed}",
        seed=seed,
        days=days,
        actors=tuple(f"actor_{i}" for i in range(actors)),
        instance_keys=("one", "two"),
        location_keys=("a", "b", "c"),
    )


@pytest.mark.parametrize("seed", [0, 1, 13, 29, 41])
@pytest.mark.parametrize("days,actors", [(7, 3), (10, 4), (14, 5)])
def test_variable_schedule_frozen_scope_and_determinism(seed, days, actors):
    result = schedule(seed, days, actors)
    result.validate()
    assert digest(result.payload()) == digest(schedule(seed, days, actors).payload())
    assert len(result.events) == days * 6
    assert len({tuple(x["kind"] for x in event_chain(e)) for e in result.events}) >= 3
    assert {e.phase for e in result.events} == {"baseline", "shifted", "recurrent"}


@pytest.mark.parametrize(
    "attack",
    [
        "clock",
        "cross_instance",
        "wrong_source",
        "future_parent",
        "same_handoff_actor",
        "policy_moves",
        "heldout",
        "short",
        "missing_day",
    ],
)
def test_schedule_abuse_rejected(attack):
    source = schedule()
    events = list(source.events)
    if attack == "clock":
        events[1] = replace(events[1], tick=events[0].tick)
    elif attack == "cross_instance":
        events[0] = replace(events[0], instance_key="foreign")
    elif attack == "wrong_source":
        events[0] = replace(events[0], source_location="foreign")
    elif attack == "future_parent":
        index = next(i for i, e in enumerate(events) if e.kind == "late_correction")
        events[index] = replace(events[index], correction_of=events[-1].event_id)
    elif attack == "same_handoff_actor":
        index = next(i for i, e in enumerate(events) if e.kind == "ordered_handoff")
        events[index] = replace(events[index], actors=("actor_0", "actor_0"))
    elif attack == "policy_moves":
        index = next(
            i for i, e in enumerate(events) if e.kind == "no_move_observation_policy_change"
        )
        events[index] = replace(events[index], destination_location="foreign")
    elif attack == "heldout":
        source = replace(source, partition="sealed_confirmation")
    elif attack == "short":
        source = replace(source, days=6)
    elif attack == "missing_day":
        events = [e for e in events if e.day != 3]
    with pytest.raises(ValueError):
        replace(source, events=tuple(events)).validate()


def test_release_queue_no_truth_no_repeat_no_backdated_arrival():
    source = schedule()
    event = next(e for e in source.events if e.kind == "late_correction")
    queue = ReleaseQueue()
    queue.enqueue(event, "capture.json")
    assert not queue.release(event.tick)
    released = queue.release(event.release_tick)
    assert released == (
        {
            "capture_ref": "capture.json",
            "event_tick": event.tick,
            "received_tick": event.release_tick,
        },
    )
    assert not queue.release(event.release_tick)
    with pytest.raises(ValueError):
        queue.enqueue(event, "capture.json")
    with pytest.raises(ValueError):
        queue.release(event.tick)


class ComponentController:
    """Explicit test double: never counted in actual simulator evidence."""

    def __init__(self, fail=False):
        self.points = {
            "sdk-1": {"x": 0.0, "y": 0.0, "z": 0.0},
            "sdk-2": {"x": 1.0, "y": 0.0, "z": 1.0},
        }
        self.fail = fail
        self.calls = 0

    def step(self, **request):
        from types import SimpleNamespace

        self.calls += 1
        success = not (self.fail and self.calls > 1)
        if request["action"] == "TeleportObject" and success:
            self.points[request["objectId"]] = request["position"]
        return SimpleNamespace(
            metadata={
                "lastAction": request["action"],
                "lastActionSuccess": success,
                "objects": [
                    {"objectId": key, "position": value} for key, value in self.points.items()
                ],
            },
            frame=np.zeros((4, 4, 3), dtype=np.uint8),
            depth_frame=np.ones((4, 4), dtype=np.float32),
        )


def bindings():
    return {
        "rotations": {key: {"x": 0.0, "y": 0.0, "z": 0.0} for key in ("one", "two")},
        "object_ids": {"one": "sdk-1", "two": "sdk-2"},
        "anchors": {
            location: {
                instance: {"x": float(i), "y": 0.0, "z": float(j)}
                for j, instance in enumerate(("one", "two"))
            }
            for i, location in enumerate(("a", "b", "c"))
        },
        "runtime_provenance": {"scope": "component_test_double"},
    }


def test_executor_component_positive_continuity_and_private_requests(tmp_path):
    result = execute_schedule(ComponentController(), schedule(), tmp_path / "run", **bindings())
    assert result["complete"] and result["completed_events"] == 42
    assert not result["rendered_human_roles_verified"]
    for path in (tmp_path / "run/observation_candidates").glob("*.json"):
        text = path.read_text()
        for key in ("objectId", "actors", "phase", "TeleportObject", "correction_of"):
            assert key not in text


def test_executor_failure_preserved_and_no_retry(tmp_path):
    controller = ComponentController(fail=True)
    with pytest.raises(RuntimeError):
        execute_schedule(controller, schedule(), tmp_path / "run", **bindings())
    result = json.loads((tmp_path / "run/result.json").read_text())
    assert not result["complete"] and controller.calls == 2


def test_executor_rejects_initial_state_mismatch_before_mutation(tmp_path):
    data = bindings()
    data["anchors"]["a"]["one"]["x"] = 99.0
    controller = ComponentController()
    with pytest.raises(ValueError, match="initial location"):
        execute_schedule(controller, schedule(), tmp_path / "run", **data)
    assert controller.calls == 1


def test_habit_schedule_has_same_actor_phase_shift_and_recurrence():
    result = schedule()
    habits = [e for e in result.events if e.kind == "habit_drift"]
    assert {e.actors for e in habits} == {("actor_0",)}
    assert {e.destination_location for e in habits if e.phase == "baseline"} == {"a"}
    assert {e.destination_location for e in habits if e.phase == "shifted"} == {"b"}
    assert {e.destination_location for e in habits if e.phase == "recurrent"} == {"a"}


def test_probability_stale_context_rejected():
    data = probability_payload()
    data["factors"][-1]["context_sha256"] = "b" * 64
    with pytest.raises(ValueError, match="preceding choices"):
        JointProposalProbability.model_validate(data)


def test_missing_open_fallback_rejected(sample_payload):
    data = copy.deepcopy(sample_payload)
    data["compatible_targets"] = [
        t for t in data["compatible_targets"] if t["operation"] != "preserve_unresolved"
    ]
    with pytest.raises(ValueError, match="unresolved fallback"):
        ProposalSample.model_validate(data)


def test_empty_history_unresolved_bootstrap(sample_payload):
    data = copy.deepcopy(sample_payload)
    data["parents"], data["revisions"] = [], []
    target = next(t for t in data["compatible_targets"] if t["operation"] == "preserve_unresolved")
    target["candidate"]["state"].update(parent_particle_id=None, parent_revision_id=None)
    data["compatible_targets"] = [target]
    assert not ProposalSample.model_validate(data).parents


def test_parent_particle_cannot_disagree_with_revision_ancestry(sample_payload):
    data = copy.deepcopy(sample_payload)
    data["parents"][1]["state"]["parent_particle_id"] = uid("foreign")
    with pytest.raises(ValueError, match="ancestry"):
        ProposalSample.model_validate(data)


def test_causal_raw_prefix_and_late_release(tmp_path):
    execute_schedule(ComponentController(), schedule(), tmp_path / "run", **bindings())
    directory = tmp_path / "run/observation_candidates"
    early = released_capture_prefix(directory, 50)
    all_rows = released_capture_prefix(directory, 10000)
    assert len(early) < len(all_rows)
    assert all(x["received_tick"] <= 50 for x in early)
    assert any(x["received_tick"] > x["event_tick"] for x in all_rows)
    for row in all_rows:
        assert set(row) == {
            "sensor_file",
            "sensor_sha256",
            "depth_unit",
            "status",
            "event_tick",
            "received_tick",
        }


@pytest.mark.parametrize(
    "attack", ["duplicate", "traversal", "early_arrival", "extra_truth", "sensor_swap"]
)
def test_raw_capture_forgery_rejected(tmp_path, attack):
    execute_schedule(ComponentController(), schedule(), tmp_path / "run", **bindings())
    directory = tmp_path / "run/observation_candidates"
    journal_path = directory / "release_journal.json"
    journal = json.loads(journal_path.read_text())
    if attack == "duplicate":
        journal.append(journal[0])
    elif attack == "traversal":
        journal[0]["capture_ref"] = "../evaluator_only/secret.json"
    elif attack == "early_arrival":
        journal[0]["received_tick"] = -1
    elif attack == "extra_truth":
        path = directory / journal[0]["capture_ref"]
        payload = json.loads(path.read_text())
        payload["actor_truth"] = "hidden"
        path.write_text(json.dumps(payload))
    elif attack == "sensor_swap":
        path = directory / journal[0]["capture_ref"]
        payload = json.loads(path.read_text())
        payload["sensor_sha256"] = "b" * 64
        path.write_text(json.dumps(payload))
    journal_path.write_text(json.dumps(journal))
    with pytest.raises(ValueError):
        released_capture_prefix(directory, 10000)


def test_preparation_cli_separates_targets_refuses_training_and_overwrite(tmp_path, sample_payload):
    source = tmp_path / "input.json"
    source.write_text(json.dumps([sample_payload]))
    root = Path(__file__).resolve().parents[1]
    command = [
        sys.executable,
        str(root / "tools/structure_two_prepare_proposals.py"),
        "--input",
        str(source),
        "--output",
        str(tmp_path / "prepared"),
    ]
    env = dict(os.environ, PYTHONPATH=str(root / "src"))
    refused = subprocess.run(command, env=env, capture_output=True, text=True)
    assert refused.returncode != 0 and not (tmp_path / "prepared").exists()
    command.append("--allow-component-fixtures")
    result = subprocess.run(command, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    ready = json.loads((tmp_path / "prepared/readiness.json").read_text())
    assert not ready["training_ready"] and not ready["training_started"]
    features = (tmp_path / "prepared/features.jsonl").read_text()
    assert "compatible_targets" not in features and "annotation_kind" not in features
    assert subprocess.run(command, env=env, capture_output=True).returncode != 0


def test_fixed_observer_route_executes_without_target_requests(tmp_path):
    route = (
        {
            "position": {"x": 3.0, "y": 1.0, "z": 3.0},
            "rotation": {"x": 0.0, "y": 90.0, "z": 0.0},
            "horizon": 45.0,
            "standing": True,
        },
    )
    controller = ComponentController()
    result = execute_schedule(
        controller, schedule(), tmp_path / "run", observer_route=route, **bindings()
    )
    assert result["complete"] and controller.calls == 1 + 42 + 36


@pytest.mark.parametrize("attack", ["truth_target", "bad_horizon", "missing_rotation"])
def test_illegal_observer_route_rejected_before_sdk(tmp_path, attack):
    view = {
        "position": {"x": 3.0, "y": 1.0, "z": 3.0},
        "rotation": {"x": 0.0, "y": 90.0, "z": 0.0},
        "horizon": 45.0,
        "standing": True,
    }
    if attack == "truth_target":
        view["objectId"] = "oracle-target"
    elif attack == "bad_horizon":
        view["horizon"] = float("nan")
    elif attack == "missing_rotation":
        view.pop("rotation")
    controller = ComponentController()
    with pytest.raises(ValueError):
        execute_schedule(
            controller, schedule(), tmp_path / "run", observer_route=(view,), **bindings()
        )
    assert controller.calls == 0 and not (tmp_path / "run").exists()
