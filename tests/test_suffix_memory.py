"""Exact source-bound equivalence, invalidation and failure atomicity."""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest

from cpswm.simulation.contracts import Observation, Visibility
from cpswm.simulation.memory import SimulationMemory
from cpswm.simulation.suffix_memory import SuffixReplayMemory, runtime_digest

ROOT = Path(__file__).resolve().parents[1]
REGIONS = ("left", "center", "right")


def event(index, **changes):
    return replace(
        Observation(
            "suffix-test",
            f"source:{index}",
            f"event:{index}",
            index,
            index,
            "target",
            Visibility.OBSERVED,
            REGIONS[index % 3],
            (("owner", 0.7), ("guest", 0.3)),
            identity_probability=0.8,
        ),
        **changes,
    )


def compare(full, suffix):
    assert full.revision == suffix.revision
    assert full.records == suffix.records and full.sources == suffix.sources
    assert full.active_sources == suffix.active_sources
    assert full.destination_distribution() == suffix.destination_distribution()
    assert full.current_location == suffix.current_location
    assert runtime_digest(full.runtime) == runtime_digest(suffix.runtime)
    assert len(suffix._checkpoints) <= suffix.max_checkpoints


def ingest_pair(full, suffix, obs):
    full.ingest(obs, obs.available_at)
    suffix.ingest(obs, obs.available_at)
    compare(full, suffix)


@pytest.mark.parametrize("arm", ["native_joint", "native_factorized"])
@pytest.mark.parametrize("stride,bound", [(1, 1), (2, 3), (4, 8)])
def test_append_late_correction_and_correct_again_equal_full_replay(arm, stride, bound):
    full = SimulationMemory("suffix-test", REGIONS, arm)
    suffix = SuffixReplayMemory(
        "suffix-test", REGIONS, arm, checkpoint_stride=stride, max_checkpoints=bound
    )
    for i in range(9):
        ingest_pair(full, suffix, event(i))
    assert suffix.native_target_scores == 9 * 24
    assert full.native_target_scores == sum(range(1, 10)) * 24
    for index, i in enumerate((7, 1, 7, 0)):
        original = event(i)
        obs = replace(
            original,
            source_id=f"correction:{index}",
            revises=suffix.active_sources[original.event_id],
            available_at=20 + index,
            actors=(("guest", 1.0),) if index < 2 else original.actors,
        )
        ingest_pair(full, suffix, obs)


def test_late_insertion_retraction_and_robot_or_predicted_events():
    full = SimulationMemory("suffix-test", REGIONS)
    suffix = SuffixReplayMemory("suffix-test", REGIONS, checkpoint_stride=2)
    for obs in [event(0), event(2), event(4), event(1, available_at=5)]:
        ingest_pair(full, suffix, obs)
    obs = event(
        2,
        source_id="withdraw-location",
        available_at=6,
        revises="source:2",
        visibility=Visibility.LOST,
        location=None,
    )
    ingest_pair(full, suffix, obs)
    ingest_pair(
        full,
        suffix,
        event(2, source_id="restore-location", available_at=7, revises="withdraw-location"),
    )
    scores = suffix.native_target_scores
    ingest_pair(full, suffix, event(8, robot_generated=True))
    ingest_pair(full, suffix, event(9, visibility=Visibility.PREDICTED))
    assert suffix.native_target_scores == scores
    assert suffix.current_location is None  # predicted position is not an observed location


def test_empty_effective_history_and_current_location_are_independent():
    full = SimulationMemory("suffix-test", REGIONS)
    suffix = SuffixReplayMemory("suffix-test", REGIONS)
    ingest_pair(full, suffix, event(0, robot_generated=True))
    assert suffix.native_target_scores == 0 and not suffix._checkpoints
    ingest_pair(full, suffix, event(1))
    ingest_pair(
        full,
        suffix,
        event(
            1,
            source_id="retracted",
            available_at=2,
            revises="source:1",
            visibility=Visibility.LOST,
            location=None,
        ),
    )
    assert not suffix.runtime.particles and not suffix._checkpoints


def test_model_context_change_invalidates_all_checkpoints():
    full = SimulationMemory("suffix-test", REGIONS)
    suffix = SuffixReplayMemory("suffix-test", REGIONS)
    for i in range(3):
        ingest_pair(full, suffix, event(i))
    for memory in (full, suffix):
        memory._native_config = replace(memory._native_config, joint_interaction_strength=0.5)
    ingest_pair(full, suffix, event(3))
    assert suffix.replay_history[-1]["checkpoint_prefix"] == 0
    assert suffix.replay_history[-1]["replayed_events"] == 4


def test_published_runtime_cannot_mutate_owned_checkpoints():
    full = SimulationMemory("suffix-test", REGIONS)
    suffix = SuffixReplayMemory("suffix-test", REGIONS)
    ingest_pair(full, suffix, event(0))
    suffix.runtime.particles = ()
    ingest_pair(full, suffix, event(1))


@pytest.mark.parametrize("attack", ["weight", "rb", "journal", "prefix", "context", "count"])
def test_owned_checkpoint_corruption_rejected_without_publication(attack):
    memory = SuffixReplayMemory("suffix-test", REGIONS)
    memory.ingest(event(0), 0)
    checkpoint = memory._checkpoints[1]
    if attack == "weight":
        p = checkpoint.runtime.particles[0]
        checkpoint.runtime.particles = (
            replace(p, posterior_probability=0.1),
            *checkpoint.runtime.particles[1:],
        )
    elif attack == "rb":
        world = next(p.world for p in checkpoint.runtime.particles if p.world.rb_cells)
        world.rb_cells.clear()
    elif attack == "journal":
        checkpoint.runtime.operations.clear()
    else:
        field = {"prefix": "prefix_sha256", "context": "context_sha256", "count": "count"}[attack]
        memory._checkpoints[1] = replace(
            checkpoint, **{field: 2 if attack == "count" else "0" * 64}
        )
    before, cache = memory.audit(), copy.deepcopy(memory._checkpoints)
    with pytest.raises(ValueError, match="checkpoint"):
        memory.ingest(event(1), 1)
    assert memory.audit() == before and len(memory.sources) == 1
    assert memory._checkpoints.keys() == cache.keys()


def test_inference_failure_preserves_cache_and_public_state(monkeypatch):
    memory = SuffixReplayMemory("suffix-test", REGIONS, checkpoint_stride=1)
    for i in range(3):
        memory.ingest(event(i), i)
    before = copy.deepcopy(memory.audit())
    cache = dict(memory._checkpoints)
    history = memory._cached_history
    append = memory._append_native

    def fail_after_actual_inference(runtime, observations):
        append(runtime, observations)
        raise RuntimeError("injected after native update")

    monkeypatch.setattr(memory, "_append_native", fail_after_actual_inference)
    with pytest.raises(RuntimeError, match="injected"):
        memory.ingest(event(1, source_id="late", revises="source:1", available_at=5), 5)
    assert memory.audit() == before
    assert memory._cached_history is history and memory._checkpoints == cache
    monkeypatch.setattr(memory, "_append_native", append)
    memory.ingest(event(3), 3)  # clean continuation still possible


@pytest.mark.parametrize("arm", ["native_joint", "native_factorized"])
def test_refactored_full_and_suffix_match_all_pr119_archived_checkpoints(arm):
    path = ROOT / "docs/reviews/pc_a/research_pilot_2026-10-23/evidence/e2.json"
    report = json.loads(path.read_text())
    for row in report["e2"]["rows"]:
        if row["arm"] != arm:
            continue
        first = row["checkpoints"][0]["input"]
        full = SimulationMemory(first["episode_id"], REGIONS, arm)
        suffix = SuffixReplayMemory(first["episode_id"], REGIONS, arm)
        for point in row["checkpoints"]:
            payload = dict(point["input"])
            payload["visibility"] = Visibility(payload["visibility"])
            payload["actors"] = tuple(tuple(x) for x in payload["actors"])
            ingest_pair(full, suffix, Observation(**payload))
            assert full.audit() == point["audit"]


@pytest.mark.parametrize(
    "obs", [event(0), event(1, revises="nonexistent"), event(1, episode_id="foreign")]
)
def test_invalid_sources_cannot_mutate_cache(obs):
    memory = SuffixReplayMemory("suffix-test", REGIONS)
    memory.ingest(event(0), 0)
    before = memory.audit()
    cache = dict(memory._checkpoints)
    with pytest.raises(ValueError):
        memory.ingest(obs, obs.available_at)
    assert memory.audit() == before and memory._checkpoints == cache
