"""G1 post-fix rounds. Component cases are not native training evidence."""

import copy
import hashlib
import importlib.util
import io
import json
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import numpy as np
import pytest

from cpswm.data_preflight.capture_prefix import read_sensor_snapshot, validate_sensor_bytes
from cpswm.data_preflight.prepared_samples import load_prepared_partition, write_prepared_samples
from cpswm.data_preflight.procthor_execution import execute_schedule
from cpswm.data_preflight.procthor_schedule import ReleaseQueue
from cpswm.data_preflight.proposal_samples import ProposalSample, bind_probability
from cpswm.system.reproducibility import content_sha256

spec = importlib.util.spec_from_file_location(
    "prior_audit", Path(__file__).with_name("test_pc_a_proposal_two_round_audit.py")
)
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)


@pytest.fixture
def payload():
    return copy.deepcopy(prior.original.sample_payload.__wrapped__())


def prepared(tmp_path, payload):
    first = ProposalSample.model_validate(payload)
    other = copy.deepcopy(payload)
    other.update(
        sample_id=prior.original.uid("train-g1"),
        partition="train",
        house_id="other-house",
        house_sha256="b" * 64,
        schedule_block_id="other-block",
    )
    directory = tmp_path / "prepared"
    write_prepared_samples(
        (first, ProposalSample.model_validate(other)), directory, input_sha256="c" * 64
    )
    return directory


def manifest_digest(directory):
    return hashlib.sha256((directory / "readiness.json").read_bytes()).hexdigest()


def resign_file(directory, partition, filename):
    """Fully self-consistent forged file/manifest, not trusted original digest."""
    path = directory / "readiness.json"
    manifest = json.loads(path.read_text())
    manifest["partitions"][partition]["files_sha256"][filename] = hashlib.sha256(
        (directory / partition / filename).read_bytes()
    ).hexdigest()
    path.write_text(json.dumps(manifest))


def test_round1_keyed_partition_positive(tmp_path, payload):
    directory = prepared(tmp_path, payload)
    assert not (directory / "features.jsonl").exists()
    for partition in ("train", "development"):
        rows = load_prepared_partition(
            directory, partition, expected_manifest_sha256=manifest_digest(directory)
        )
        assert len(rows) == 1 and rows[0]["partition"] == partition
        assert "sample_id" not in rows[0]["model_input"]
        assert "pair_sha256" not in rows[0]["model_input"]
    assert not json.loads((directory / "readiness.json").read_text())["training_ready"]


@pytest.mark.parametrize(
    "field", ["source_snapshot_id", "source_record_id", "location_entity_id", "location_key"]
)
def test_round1_location_origin_negative(payload, field):
    payload["location_support"][0][field] = prior.original.uid("foreign")
    with pytest.raises(ValueError):
        ProposalSample.model_validate(payload)


def test_round1_visible_discovered_location_and_unknown_positive(payload):
    detection = payload["visible"]["detections"][0]
    payload["location_support"][0] = dict(
        location_key="location_a",
        origin="visible_evidence",
        source_record_id=detection["metadata"]["record_id"],
        location_entity_id=detection["detected_location_id"],
    )
    ProposalSample.model_validate(payload)
    payload["compatible_targets"][0]["candidate"]["events"][-1]["location_key"] = "unknown_location"
    ProposalSample.model_validate(payload)


def test_round1_late_detection_without_actual_delay_rejected(payload):
    op = payload["visible"]["opportunities"][0]
    payload["visible"]["arrivals"][1]["received_at"] = op["opportunity_time"]
    with pytest.raises(ValueError, match="actually delayed"):
        ProposalSample.model_validate(payload)


@pytest.mark.parametrize("clock", [-1, True, False, 1.5, "10", None, float("nan"), float("inf")])
def test_round1_queue_clock_negative(clock):
    queue = ReleaseQueue()
    with pytest.raises(ValueError):
        queue.release(clock)
    assert queue.release(0) == ()


def test_round1_queue_rejection_has_no_side_effects():
    event = replace(prior.original.schedule().events[0], observation_selected=True, release_tick=5)
    queue = ReleaseQueue()
    with pytest.raises(ValueError):
        queue.enqueue(replace(event, release_tick=-1), "000001.json")
    queue.enqueue(event, "000001.json")
    with pytest.raises(ValueError):
        queue.finish(4)
    assert len(queue.finish(5)) == 1
    for action in (
        lambda: queue.release(5),
        lambda: queue.enqueue(replace(event, tick=6, release_tick=6), "000002.json"),
    ):
        with pytest.raises(ValueError):
            action()


@pytest.mark.parametrize("attack", ["object", "extra", "nan", "negative", "shape", "rgb_dtype"])
def test_round1_sensor_array_negative(attack):
    arrays = dict(rgb=np.zeros((4, 4, 3), dtype=np.uint8), depth=np.ones((4, 4), dtype=np.float32))
    if attack == "extra":
        arrays["true_actor"] = np.array([1])
    elif attack == "object":
        arrays["rgb"] = np.array([{"truth": 1}], dtype=object)
    elif attack in {"nan", "negative"}:
        arrays["depth"][0, 0] = float("nan") if attack == "nan" else -1
    elif attack == "shape":
        arrays["depth"] = np.ones((2, 2))
    else:
        arrays["rgb"] = arrays["rgb"].astype(float)
    stream = io.BytesIO()
    np.savez(stream, **arrays)
    with pytest.raises(ValueError):
        validate_sensor_bytes(stream.getvalue(), "m")


def test_round1_sensor_snapshot_survives_path_rebinding(tmp_path):
    stream = io.BytesIO()
    np.savez(stream, rgb=np.zeros((2, 2, 3), dtype=np.uint8))
    path = tmp_path / "sensor.npz"
    path.write_bytes(stream.getvalue())
    snapshot = read_sensor_snapshot(
        path, expected_sha256=hashlib.sha256(stream.getvalue()).hexdigest(), depth_unit=None
    )
    path.write_bytes(b"later replacement")
    assert snapshot == stream.getvalue()
    with pytest.raises(ValueError):
        read_sensor_snapshot(
            path, expected_sha256=hashlib.sha256(snapshot).hexdigest(), depth_unit=None
        )


def test_round2_full_manifest_forgery_rejected_by_retained_digest(tmp_path, payload):
    directory = prepared(tmp_path, payload)
    retained = manifest_digest(directory)
    path = directory / "train/features.jsonl"
    row = json.loads(path.read_text())
    row["payload"]["actor_support"] = ["forged"]
    path.write_text(json.dumps(row) + "\n")
    resign_file(directory, "train", "features.jsonl")
    with pytest.raises(ValueError, match="independently retained"):
        load_prepared_partition(directory, "train", expected_manifest_sha256=retained)


@pytest.mark.parametrize(
    "attack",
    ["partition", "sample_id", "duplicate", "missing", "target_swap", "extra_field", "pair_digest"],
)
def test_round2_resigned_internal_pairing_attacks(tmp_path, payload, attack):
    directory = prepared(tmp_path, payload)
    path = directory / "train/targets.jsonl"
    row = json.loads(path.read_text())
    if attack == "partition":
        row["partition"] = "development"
    elif attack == "sample_id":
        row["sample_id"] = prior.original.uid("other-id")
    elif attack == "target_swap":
        row["payload"][0]["evidence_ids"] = []
    elif attack == "extra_field":
        row["true_actor"] = 1
    elif attack == "pair_digest":
        row["pair_sha256"] = "0" * 64
    data = json.dumps(row) + "\n"
    path.write_text(data * 2 if attack == "duplicate" else "" if attack == "missing" else data)
    resign_file(directory, "train", "targets.jsonl")
    with pytest.raises(ValueError):
        load_prepared_partition(
            directory, "train", expected_manifest_sha256=manifest_digest(directory)
        )


def test_round2_legacy_unbound_probability_rejected_but_bound_positive_passes(payload):
    sample = ProposalSample.model_validate(payload)
    target = sample.compatible_targets[0]
    trace = prior.probability(sample, target)
    bind_probability(sample, target, trace)
    with pytest.raises(ValueError, match="full proposal"):
        bind_probability(sample, target, trace.model_copy(update={"proposal_sha256": None}))


def test_round2_location_discovery_wrong_entity_rejected(payload):
    detection = payload["visible"]["detections"][0]
    payload["location_support"][0] = dict(
        location_key="location_a",
        origin="visible_evidence",
        source_record_id=detection["metadata"]["record_id"],
        location_entity_id=prior.original.uid("foreign-place"),
    )
    with pytest.raises(ValueError, match="arrived detection"):
        ProposalSample.model_validate(payload)


def test_round2_complete_replay_effect_change_with_old_q_rejected(payload):
    sample = ProposalSample.model_validate(payload)
    old_trace = prior.probability(sample, sample.compatible_targets[4])
    payload["compatible_targets"][4]["replaced_revision_ids"] = payload["compatible_targets"][4][
        "replaced_revision_ids"
    ][-1:]
    changed = ProposalSample.model_validate(payload)
    target = changed.compatible_targets[4]
    assert old_trace.proposal_sha256 != content_sha256(target.model_dump(mode="json"))
    with pytest.raises(ValueError, match="full proposal"):
        bind_probability(changed, target, old_trace)
    bind_probability(changed, target, prior.probability(changed, target))


def test_round2_immutable_schedule_actor_list_and_partial_failure(tmp_path):
    source = prior.original.schedule()
    actors = list(source.events[0].actors)
    events = [replace(source.events[0], actors=actors), *source.events[1:]]
    source = replace(source, events=events)
    actors[0] = "foreign"
    events.clear()
    source.validate()
    with pytest.raises(RuntimeError):
        execute_schedule(
            prior.original.ComponentController(fail=True),
            source,
            tmp_path / "failure",
            **prior.original.bindings(),
        )
    result = json.loads((tmp_path / "failure/result.json").read_text())
    assert not result["complete"] and result["completed_events"] == 0
    assert not json.loads(
        (tmp_path / "failure/observation_candidates/release_journal.json").read_text()
    )


def test_round2_missing_completion_marker_rejected(tmp_path):
    directory = tmp_path / "incomplete"
    directory.mkdir()
    with pytest.raises(FileNotFoundError):
        load_prepared_partition(directory, "train", expected_manifest_sha256="0" * 64)


def test_round2_future_discovery_not_imported_into_past(payload):
    detection = payload["visible"]["detections"][0]
    payload["location_support"][0] = dict(
        location_key="location_a",
        origin="visible_evidence",
        source_record_id=detection["metadata"]["record_id"],
        location_entity_id=detection["detected_location_id"],
    )
    sample = ProposalSample.model_validate(payload)
    payload["visible"]["cutoff"] = (
        sample.visible.arrivals[1].received_at - timedelta(seconds=1)
    ).isoformat()
    with pytest.raises(ValueError):
        ProposalSample.model_validate(payload)
