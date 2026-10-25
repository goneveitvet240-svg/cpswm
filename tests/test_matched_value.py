"""Public-input, causal ordering, selection and fresh-result replacement checks."""

import copy
from dataclasses import replace
from types import SimpleNamespace

import pytest
import run_matched_value as diagnostic
import verify_matched_value as verifier

from cpswm.contracts import ProjectTwoDatasetSplit as Split


@pytest.fixture(scope="module")
def dataset():
    return diagnostic.dataset_for("sparse32")


def test_public_map_and_header_do_not_depend_on_future_steps(dataset):
    episode = dataset.visible_episodes(Split.VALIDATION)[0]
    assert len(episode.known_location_ids) == 4
    assert episode.known_location_ids == tuple(sorted(episode.known_location_ids, key=str))
    truncated = episode.model_copy(update={"steps": episode.steps[:1]})
    assert diagnostic.public_header(episode) == diagnostic.public_header(truncated)
    assert len(diagnostic.public_header(episode).steps) == 1
    with pytest.raises(ValueError, match="catalogue"):
        diagnostic.public_header(episode.model_copy(update={"known_location_ids": ()}))


def test_truth_firewall():
    with pytest.raises(RuntimeError, match="truth"):
        diagnostic.NoTruth().truth_for("anything")
    with pytest.raises(RuntimeError, match="another episode"):
        diagnostic.NoTruth().visible_episodes(Split.TEST)


def test_barrier_requires_all_actions_and_copies_payload():
    barrier = diagnostic.CommitBarrier(["a", "b"], "input")
    action = {"put_back": "left"}
    barrier.commit("a", "input", action)
    action["put_back"] = "right"
    assert barrier.records["a"]["put_back"] == "left"
    called = []
    with pytest.raises(ValueError, match="all method"):
        barrier.release(lambda: called.append(True))
    assert not called
    barrier.commit("b", "input", action)
    assert barrier.release(lambda: 42) == 42
    with pytest.raises(ValueError):
        barrier.commit("b", "input", action)
    with pytest.raises(ValueError):
        barrier.release(lambda: 0)


@pytest.mark.parametrize("method,input_hash", [("foreign", "input"), ("a", "other")])
def test_barrier_rejects_foreign_method_or_unequal_input(method, input_hash):
    with pytest.raises(ValueError):
        diagnostic.CommitBarrier(["a"], "input").commit(method, input_hash, {})


def test_hand_scoring_and_outside_support():
    action = {"put_back": "right", "search_order": ["left", "center", "right"]}
    truth = SimpleNamespace(true_location="center", true_owner_habit_location="right")
    assert diagnostic.score(action, truth) == {"put_error": 0, "search_error": 1, "rank_checks": 2}
    truth.true_location = "outside"
    with pytest.raises(ValueError, match="outside"):
        diagnostic.score(action, truth)


def test_validation_selection_uses_put_error_and_declared_tie_order():
    rows = {}
    for method, parameters in diagnostic.GRIDS.items():
        for i, _ in enumerate(parameters):
            rows[f"{method}:{i}"] = [
                {"score": {"put_error": int(i != 1), "search_error": int(i == 1), "rank_checks": 1}}
            ]
    selected, record = diagnostic.select_configs([{"rows": rows}])
    assert selected["recency"][1] == 0.8
    assert record["simple_champion"] == "latest_owner"
    for value in rows.values():
        value[0]["score"]["put_error"] = 0
    selected, record = diagnostic.select_configs([{"rows": rows}])
    assert selected["recency"][1] == 0.5
    assert record["simple_champion"] == "source_owner_counts"


def test_native_missing_event_and_full_replay_have_equal_state(dataset):
    episode = dataset.visible_episodes(Split.TEST)[0]
    episode = episode.model_copy(update={"steps": episode.steps[:3]})
    assert any(step.after is None for step in episode.steps)
    result = diagnostic.run_episode(
        dataset, episode, {name: (name, None) for name in diagnostic.NATIVE}, check_full_rerun=True
    )
    assert len(result["full_rerun"]) == 2
    for audit in result["final_audits"].values():
        assert audit["steps"] == 3
        assert audit["particles"] == 24
        assert audit["extra_ciav_queries"] == audit["paid_location_sources"] == 0
    assert all(row["equivalent"] for row in result["full_rerun"])


@pytest.mark.parametrize("condition", ["delayed_attribution", "identity_correction"])
def test_revision_simple_is_source_bound_and_recovers(condition):
    scenario, stream = diagnostic.revision_stream(condition, "wrong_then_recorrect")
    memory = diagnostic.RevisionSimpleMemory(scenario.episode_id, "latest_owner", 0.5)
    for observation in stream:
        memory.ingest(observation, observation.available_at)
    assert memory.destination() == scenario.expected_destination
    before = memory.revision
    with pytest.raises(ValueError):
        memory.ingest(stream[-1], stream[-1].available_at)
    assert memory.revision == before
    forged = replace(stream[-1], source_id="new-invalid", revises="non-active")
    with pytest.raises(ValueError):
        memory.ingest(forged, forged.available_at)
    assert memory.revision == before


def test_pairing_requires_same_event_and_input():
    point = {
        "step_id": "a",
        "input_sha256": "same",
        "score": {"put_error": 0},
        "action": {"put_back": "left"},
    }
    result = {
        "episode_id": "e",
        "rows": {"native_joint": [point], "baseline": [copy.deepcopy(point)]},
    }
    assert diagnostic.paired([result], "baseline")[0]["both_correct"] == 1
    result["rows"]["baseline"][0]["input_sha256"] = "different"
    with pytest.raises(ValueError, match="pairing"):
        diagnostic.paired([result], "baseline")


def test_full_result_replacement_and_inventory_are_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(verifier, "sources", lambda: {"source": "bound"})
    left, right = tmp_path / "left", tmp_path / "right"
    for root in (left, right):
        diagnostic.save(
            root / "manifest.json",
            {
                "files": {"source": "bound"},
                "git_status": "",
                "quick_development": False,
                "scientific_acceptance": False,
            },
        )
        diagnostic.save(
            root / "completion.json",
            {
                "quick_development": False,
                "source_unchanged": True,
                "seconds": 1 if root == left else 2,
            },
        )
        diagnostic.save(root / "result.json", {"put_error": 1, "action": "left"})
    assert verifier.compare(left, right)["json_files"] == 3
    diagnostic.save(right / "result.json", {"put_error": 0, "action": "right"})
    with pytest.raises(ValueError, match="fresh replay mismatch"):
        verifier.compare(left, right)
    (right / "result.json").unlink()
    with pytest.raises(ValueError, match="inventory"):
        verifier.compare(left, right)
