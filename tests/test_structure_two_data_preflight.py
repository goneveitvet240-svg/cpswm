"""Component tests. Fake controllers here never count as real simulator evidence."""

import json
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import numpy as np
import pytest

from cpswm.contracts.habit_learning import ActorEvidenceTrack, ObservationDetectionResult
from cpswm.data_preflight.simulator_capture import RawCaptureSession, simulator_preflight
from cpswm.data_preflight.train_coverage import audit_train_worlds
from cpswm.data_preflight.visible_prefix import export_visible_prefix
from cpswm.system.evaluation_operations.d0_shift_scenarios import D0ShiftScenarioGenerator


@pytest.fixture(scope="module")
def sample():
    # Existing component-development fixture, NOT the reserved world confirmation set.
    case = (
        D0ShiftScenarioGenerator()
        .generate(actor_evidence_track=ActorEvidenceTrack.CONTROLLED_NOISE)
        .cases[0]
        .model_input
    )
    run = case.control_run
    actor = case.control_actor_evidence[0]
    det = next(
        x for x in run.detection_results if x.metadata.record_id == actor.source_detection_result_id
    )
    op = next(
        x
        for x in run.observation_opportunities
        if x.metadata.record_id == det.observation_opportunity_id
    )
    return op, det, actor


def export(op, det, *, cutoff=None, arrivals=None, actors=()):
    arrivals = arrivals or {
        op.metadata.record_id: op.opportunity_time,
        det.metadata.record_id: det.detection_time or op.opportunity_time,
        **{a.metadata.record_id: a.evidence_time for a in actors},
    }
    return export_visible_prefix(
        (op,),
        (det,),
        received_at=arrivals,
        cutoff=cutoff or op.opportunity_time + timedelta(days=1),
        actor_evidence=actors,
    )


def test_visible_prefix_preserves_legal_fields_and_no_global_truth(sample):
    op, det, actor = sample
    result = export(op, det, actors=(actor,))
    row = result.model_input()["observations"][0]
    assert row["result"]["outcome"] == "detected"
    assert row["actor_evidence"][0]["reference_actor_prior"] == actor.reference_actor_prior
    assert row["actor_evidence"][0]["actor_posterior"] == actor.actor_posterior
    for forbidden in (
        "world_hash",
        "rollout_id",
        "random_seed",
        "true_actor",
        "change_time",
        "metadata",
        "trace_id",
        "evidence_refs",
    ):
        assert forbidden not in result.model_input_json
    detached = result.model_input()
    detached["observations"].clear()
    assert result.model_input()["observations"]


def test_late_detection_is_pending_until_it_arrives(sample):
    op, det, _ = sample
    later = op.opportunity_time + timedelta(days=2)
    arrivals = {op.metadata.record_id: op.opportunity_time, det.metadata.record_id: later}
    assert export(op, det, arrivals=arrivals).model_input()["observations"][0]["result"] is None
    assert export(op, det, arrivals=arrivals, cutoff=later).model_input()["observations"][0][
        "result"
    ]


def test_late_actor_evidence_waits_for_both_arrival_and_parent(sample):
    op, det, actor = sample
    later = op.opportunity_time + timedelta(days=2)
    arrivals = {
        op.metadata.record_id: op.opportunity_time,
        det.metadata.record_id: later,
        actor.metadata.record_id: actor.evidence_time,
    }
    assert not export(op, det, actors=(actor,), arrivals=arrivals).model_input()["observations"][0][
        "actor_evidence"
    ]
    assert export(op, det, actors=(actor,), arrivals=arrivals, cutoff=later).model_input()[
        "observations"
    ][0]["actor_evidence"]


def test_no_future_opportunity_or_support_changes_earlier_features(sample):
    op, det, _ = sample
    first = export(op, det)
    future = op.model_copy(
        update={
            "metadata": op.metadata.model_copy(update={"record_id": uuid4()}),
            "opportunity_time": op.opportunity_time + timedelta(days=4),
            "incidental_context": None,
        }
    )
    combined = export_visible_prefix(
        (op, future),
        (det,),
        cutoff=op.opportunity_time + timedelta(days=1),
        received_at={
            op.metadata.record_id: op.opportunity_time,
            det.metadata.record_id: det.detection_time,
            future.metadata.record_id: future.opportunity_time,
        },
    )
    assert first == combined


@pytest.mark.parametrize(
    "outcome,strength", [("not_observed", 0.0), ("ambiguous", 0.0), ("verified_absence", 0.7)]
)
def test_missingness_is_not_fabricated_negative_evidence(sample, outcome, strength):
    op, det, _ = sample
    updated = ObservationDetectionResult.model_validate(
        {
            **det.model_dump(),
            "outcome": outcome,
            "detected_object_instance_id": None,
            "detected_location_id": None,
            "detection_time": None,
            "negative_evidence_strength": strength,
        }
    )
    result = export(op, updated).model_input()["observations"][0]["result"]
    assert result["negative_evidence_strength"] == strength
    assert result["detected_location_id"] is None


@pytest.mark.parametrize(
    "attack",
    [
        "duplicate",
        "orphan",
        "arrival_missing",
        "arrival_early",
        "session",
        "unselected",
        "mutated_result",
        "oracle_actor",
    ],
)
def test_visible_input_boundary_rejects_invalid_paths(sample, attack):
    op, det, actor = sample
    ops, actors = (op,), ()
    arrivals = {
        op.metadata.record_id: op.opportunity_time,
        det.metadata.record_id: det.detection_time,
    }
    if attack == "duplicate":
        ops = (op, op)
    elif attack == "orphan":
        det = det.model_copy(update={"observation_opportunity_id": uuid4()})
    elif attack == "arrival_missing":
        arrivals.pop(det.metadata.record_id)
    elif attack == "arrival_early":
        arrivals[det.metadata.record_id] = op.opportunity_time - timedelta(seconds=1)
    elif attack == "session":
        det = det.model_copy(
            update={"metadata": det.metadata.model_copy(update={"session_id": uuid4()})}
        )
    elif attack == "unselected":
        ops = (op.model_copy(update={"selected": False}),)
    elif attack == "mutated_result":
        det = det.model_copy(update={"outcome": "not_observed"})
    elif attack == "oracle_actor":
        actors = (actor.model_copy(update={"evidence_track": ActorEvidenceTrack.ORACLE}),)
        arrivals[actor.metadata.record_id] = actor.evidence_time
    with pytest.raises(ValueError):
        export_visible_prefix(
            ops,
            (det,),
            actor_evidence=actors,
            received_at=arrivals,
            cutoff=op.opportunity_time + timedelta(days=1),
        )


class FakeController:
    """Explicit test double only."""

    def __init__(self, fault=None):
        self.calls = []
        self.fault = fault

    def step(self, **request):
        self.calls.append(request)
        if self.fault == "interrupt":
            raise KeyboardInterrupt()
        metadata = {
            "lastAction": request["action"],
            "lastActionSuccess": self.fault != "failed",
            "objects": [{"hidden_truth": "never-visible"}],
            "errorMessage": "private detail",
            "actionReturn": "privileged query result",
        }
        if self.fault == "mismatch":
            metadata["lastAction"] = "another-action"
        frame = np.zeros((3, 4, 3), dtype=np.uint8)
        depth = np.ones((3, 4), dtype=np.float32)
        if self.fault == "nan":
            depth[0, 0] = float("nan")
        return SimpleNamespace(metadata=metadata, frame=frame, depth_frame=depth)


def session(tmp_path, controller):
    return RawCaptureSession(
        controller,
        tmp_path / "capture",
        run_id="component-only",
        runtime_provenance={"kind": "explicit-test-double"},
        allowed_actions=("Pass", "MoveAhead"),
        depth_unit="m",
    )


def test_capture_orders_real_interface_calls_and_separates_truth(tmp_path):
    controller = FakeController()
    capture = session(tmp_path, controller)
    a = capture.capture({"action": "Pass"})
    b = capture.capture({"action": "MoveAhead"})
    assert [a["step_index"], b["step_index"]] == [0, 1]
    assert controller.calls == [{"action": "Pass"}, {"action": "MoveAhead"}]
    assert "hidden_truth" not in json.dumps(a)
    assert "privileged query" not in json.dumps(a)
    assert "hidden_truth" in (tmp_path / "capture/evaluator_only/000000.json").read_text()
    with np.load(tmp_path / "capture/observations/000000.npz") as data:
        assert data["rgb"].shape == (3, 4, 3)
        assert data["depth"].shape == (3, 4)
    with pytest.raises(FileExistsError):
        session(tmp_path, controller)


def test_simulator_failure_is_recorded_not_forged_success(tmp_path):
    capture = session(tmp_path, FakeController("failed"))
    assert capture.capture({"action": "Pass"})["last_action_success"] is False


@pytest.mark.parametrize("fault", ["nan", "mismatch", "interrupt"])
def test_uncertain_capture_never_retries_action(tmp_path, fault):
    controller = FakeController(fault)
    capture = session(tmp_path, controller)
    with pytest.raises((ValueError, KeyboardInterrupt)):
        capture.capture({"action": "Pass"})
    with pytest.raises(RuntimeError, match="uncertain"):
        capture.capture({"action": "Pass"})
    assert len(controller.calls) == 1
    assert (tmp_path / "capture/uncertain_step_000000.json").exists()


def test_out_of_contract_action_rejected_before_execution(tmp_path):
    controller = FakeController()
    capture = session(tmp_path, controller)
    with pytest.raises(ValueError):
        capture.capture({"action": "GetReachablePositions"})
    assert not controller.calls
    assert capture.capture({"action": "Pass"})["last_action_success"]


def test_preflight_does_not_claim_simulator_execution():
    assert simulator_preflight()["real_simulator_run_verified"] is False


def test_train_profile_exact_grain_and_explicit_full_scope_gaps():
    report = audit_train_worlds(Path(__file__).resolve().parents[1])
    assert report["world_count"] == 24
    assert report["rollout_count"] == 144
    assert report["counts"]["steps"] == 49428
    assert sum(report["regimes"].values()) == report["counts"]["steps"]
    assert report["counts"]["true_identity_match_false"] == 0
    assert report["counts"]["perceived_location_mismatch"] == 3505
    assert set(report["axes"]) == set("HRICZrV")
    assert not report["full_scope_training_ready"]
    assert not any(report["proposal_operation_labels"].values())


@pytest.mark.parametrize("attack", [None, "confirmation", "truth", "overwrite"])
def test_actual_export_cli_positive_and_rejected_envelopes(tmp_path, sample, attack):
    op, det, actor = sample
    envelope = {
        "partition": "development",
        "opportunities": [op.model_dump(mode="json")],
        "detections": [det.model_dump(mode="json")],
        "actor_evidence": [actor.model_dump(mode="json")],
        "received_at": {
            str(op.metadata.record_id): op.opportunity_time.isoformat(),
            str(det.metadata.record_id): det.detection_time.isoformat(),
            str(actor.metadata.record_id): actor.evidence_time.isoformat(),
        },
    }
    if attack == "confirmation":
        envelope["partition"] = "confirmation"
    if attack == "truth":
        envelope["evaluator_truth"] = {"true_actor": "hidden"}
    source, output = tmp_path / "input.json", tmp_path / "prefix.json"
    source.write_text(json.dumps(envelope), encoding="utf-8")
    if attack == "overwrite":
        output.write_text("preserve earlier evidence", encoding="utf-8")
    root = Path(__file__).resolve().parents[1]
    command = [
        sys.executable,
        str(root / "tools/structure_two_data_preflight.py"),
        "export-visible",
        "--input",
        str(source),
        "--output",
        str(output),
        "--cutoff",
        (op.opportunity_time + timedelta(days=1)).isoformat(),
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        env=dict(os.environ, PYTHONPATH=str(root / "src")),
        timeout=30,
    )
    if attack:
        assert result.returncode != 0
        if attack == "overwrite":
            assert output.read_text() == "preserve earlier evidence"
        else:
            assert not output.exists()
    else:
        assert result.returncode == 0, result.stderr
        parsed = json.loads(output.read_text())
        assert parsed["model_input"]["observations"][0]["actor_evidence"]
        assert not parsed["audit_only"]["partition_custody_verified"]


def test_all_future_input_returns_empty_not_negative(sample):
    op, det, _ = sample
    result = export(op, det, cutoff=op.opportunity_time - timedelta(seconds=1))
    assert result.model_input()["observations"] == []


def test_mutable_actor_probabilities_are_revalidated(sample):
    op, det, actor = sample
    mutated = actor.model_copy(deep=True)
    mutated.actor_posterior[next(iter(mutated.actor_posterior))] = 0.99
    with pytest.raises(ValueError):
        export(op, det, actors=(mutated,))
