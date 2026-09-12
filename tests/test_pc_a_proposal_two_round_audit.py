"""Author adversarial re-review. Failing assertions are OPEN findings, not xfails.

Explicit component fixtures/controllers test contracts, not authentic model training
or rendered humans. Original implementation tests supply only a legal seed fixture.
"""

import copy
import hashlib
import importlib.util
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from cpswm.data_preflight.capture_prefix import released_capture_prefix
from cpswm.data_preflight.procthor_execution import execute_schedule
from cpswm.data_preflight.procthor_schedule import ReleaseQueue
from cpswm.data_preflight.proposal_samples import (
    JointProposalProbability,
    ProposalSample,
    bind_probability,
    export_sample,
)
from cpswm.system.reproducibility import content_sha256

spec = importlib.util.spec_from_file_location(
    "original_component_cases", Path(__file__).with_name("test_structure_two_proposal_scheduler.py")
)
original = importlib.util.module_from_spec(spec)
spec.loader.exec_module(original)


@pytest.fixture
def payload():
    return copy.deepcopy(original.sample_payload.__wrapped__())


def probability(sample, target):
    state = target.candidate.state
    root = content_sha256(export_sample(sample)["model_input"])
    values = [
        target.operation.value,
        str(state.parent_particle_id),
        content_sha256([e.model_dump(mode="json") for e in target.candidate.events]),
        content_sha256([r.model_dump(mode="json") for r in state.ordered_actor_roles]),
        state.instance_association_key,
        state.change_cause.value,
        content_sha256({"decision": state.regime_decision.value, "regime_id": state.regime_id}),
        str(state.run_length),
        content_sha256(
            {
                key: state.model_dump(mode="json")[key]
                for key in (
                    "particle_id",
                    "revision_id",
                    "parent_revision_id",
                    "event_hypothesis_id",
                    "statistic_state_ref",
                    "ledger_lineage_ref",
                )
            }
        ),
    ]
    prefix, factors = [], []
    for axis, selected in zip(
        ("operation", "parent", "H", "R", "I", "C", "Z", "r", "V"), values, strict=True
    ):
        factors.append(
            dict(
                axis=axis,
                context_sha256=content_sha256({"root": root, "prefix": prefix}),
                choices=[selected],
                probabilities=[1.0],
                selected=selected,
            )
        )
        prefix.append((axis, selected))
    return JointProposalProbability.model_validate(
        dict(
            root_context_sha256=root,
            proposal_sha256=content_sha256(target.model_dump(mode="json")),
            factors=factors,
            joint_log_probability=0.0,
        )
    )


def test_round1_positive_full_candidate_binding(payload):
    sample = ProposalSample.model_validate(payload)
    bind_probability(
        sample, sample.compatible_targets[4], probability(sample, sample.compatible_targets[4])
    )


def test_round1_probability_must_bind_replay_suffix(payload):
    sample = ProposalSample.model_validate(payload)
    trace = probability(sample, sample.compatible_targets[4])
    payload["compatible_targets"][4]["replaced_revision_ids"] = payload["compatible_targets"][4][
        "replaced_revision_ids"
    ][-1:]
    changed = ProposalSample.model_validate(payload)
    assert export_sample(changed)["model_input"] == export_sample(sample)["model_input"]
    with pytest.raises(ValueError):
        bind_probability(changed, changed.compatible_targets[4], trace)


def test_round1_probability_must_bind_evidence_set(payload):
    sample = ProposalSample.model_validate(payload)
    trace = probability(sample, sample.compatible_targets[0])
    payload["compatible_targets"][0]["evidence_ids"].append(
        payload["visible"]["opportunities"][0]["metadata"]["record_id"]
    )
    changed = ProposalSample.model_validate(payload)
    with pytest.raises(ValueError):
        bind_probability(changed, changed.compatible_targets[0], trace)


def test_round1_legal_delayed_detection_recorded_on_receipt(payload):
    # Occurrence remains one hour before receipt; only record creation uses receipt time.
    payload["visible"]["detections"][0]["metadata"]["recorded_time"] = payload["visible"][
        "arrivals"
    ][1]["received_at"]
    ProposalSample.model_validate(payload)


@pytest.mark.parametrize("field", ["status", "depth_unit"])
def test_round1_nested_oracle_in_sensor_field_rejected(tmp_path, field):
    execute_schedule(
        original.ComponentController(), original.schedule(), tmp_path / "run", **original.bindings()
    )
    directory = tmp_path / "run/observation_candidates"
    journal = json.loads((directory / "release_journal.json").read_text())
    path = directory / journal[0]["capture_ref"]
    data = json.loads(path.read_text())
    data[field] = {"true_actor": "actor_0", "true_cause": "habit"}
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        released_capture_prefix(directory, 10000)


def test_round1_oracle_array_with_valid_sensor_hash_rejected(tmp_path):
    execute_schedule(
        original.ComponentController(), original.schedule(), tmp_path / "run", **original.bindings()
    )
    directory = tmp_path / "run/observation_candidates"
    journal = json.loads((directory / "release_journal.json").read_text())
    path = directory / journal[0]["capture_ref"]
    data = json.loads(path.read_text())
    sensor = directory / data["sensor_file"]
    with np.load(sensor, allow_pickle=False) as arrays:
        rgb, depth = arrays["rgb"].copy(), arrays["depth"].copy()
    np.savez(sensor, rgb=rgb, depth=depth, true_actor=np.array([1]))
    data["sensor_sha256"] = hashlib.sha256(sensor.read_bytes()).hexdigest()
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        released_capture_prefix(directory, 10000)


def test_round2_positive_geometry_preserves_unresolved_gates(tmp_path):
    result = execute_schedule(
        original.ComponentController(), original.schedule(), tmp_path / "run", **original.bindings()
    )
    assert result["complete"] and result["completed_events"] == 42
    assert result["released_captures"] == 36
    assert not result["method_input_authorized"] and not result["rendered_human_roles_verified"]
    assert len(released_capture_prefix(tmp_path / "run/observation_candidates", 10000)) == 36


@pytest.mark.parametrize("clock", [float("nan"), float("inf"), 0.5])
def test_round2_release_clock_must_be_finite_integer(clock):
    schedule = original.schedule()
    events = list(schedule.events)
    events[0] = replace(events[0], release_tick=clock)
    with pytest.raises(ValueError):
        replace(schedule, events=tuple(events)).validate()


def test_round2_duplicate_capture_cannot_represent_two_events():
    first, second = original.schedule().events[:2]
    queue = ReleaseQueue()
    queue.enqueue(first, "000001.json")
    with pytest.raises(ValueError):
        queue.enqueue(replace(second, observation_selected=True), "000001.json")


def test_round2_numeric_pose_alias_rejected_before_sdk(tmp_path):
    data = original.bindings()
    data["anchors"]["c"]["one"] = {"x": 0, "y": 0, "z": 0}
    controller = original.ComponentController()
    with pytest.raises(ValueError, match="alias"):
        execute_schedule(controller, original.schedule(), tmp_path / "run", **data)
    assert controller.calls == 0


def test_round2_schedule_detached_from_mutable_caller_container(tmp_path):
    source = original.schedule()
    events = list(source.events)
    source = replace(source, events=events)

    class MutatingController(original.ComponentController):
        def step(self, **request):
            response = super().step(**request)
            if self.calls == 1:
                # Public caller-owned list, no private core field access.
                events[0] = replace(events[0], actors=("foreign_actor",))
            return response

    try:
        execute_schedule(MutatingController(), source, tmp_path / "run", **original.bindings())
    except ValueError:
        return  # Rejection is an acceptable fail-closed policy.
    execution = json.loads((tmp_path / "run/evaluator_only/execution.json").read_text())
    assert "foreign_actor" not in json.dumps(execution)


def test_round2_nan_release_queue_cannot_silently_drop_capture():
    queue = ReleaseQueue()
    event = replace(
        original.schedule().events[0], observation_selected=True, release_tick=float("nan")
    )
    with pytest.raises(ValueError):
        queue.enqueue(event, "000001.json")
