"""Current-position inference, information boundaries and actual adapter paths."""

from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from uuid import UUID

import pytest
from run_current_location import dataset_for, evaluate
from score_current_location import score_run

from cpswm.contracts import ProjectTwoDatasetSplit
from cpswm.system.evaluation_operations.structure_two_active_location_search import (
    LocationInspectionRequest,
)
from cpswm.system.evaluation_operations.structure_two_current_location import (
    CurrentLocationBelief,
    LocationModelConfig,
    execute_current_search,
    project_search_input,
)
from cpswm.system.evaluation_operations.structure_two_executed_search import (
    ExecutedD0SearchEnvironment,
)
from cpswm.system.reproducibility import content_sha256

LOCS = [str(UUID(int=i)) for i in (10, 11)]
ACTORS = ("a", "b")


def setup(target=10, config=None):
    episode = SimpleNamespace(
        episode_id=UUID(int=1),
        steps=[SimpleNamespace(step_id=UUID(int=2), object_instance_id=UUID(int=3))],
    )
    env = ExecutedD0SearchEnvironment(episode, tuple(map(UUID, LOCS)), lambda sid: UUID(int=target))
    head = CurrentLocationBelief(LOCS, ACTORS, config or LocationModelConfig("joint"))
    projection = {
        "step_id": str(UUID(int=2)),
        "object_id": str(UUID(int=3)),
        "view": "native",
        "visible_location": None,
        "actor_cue": None,
    }
    return head, env, projection


def xor_history():
    return [
        {
            "step_id": f"history-{index}",
            "previous": LOCS[p],
            "actor_cue": {"a": float(a == 0), "b": float(a == 1)},
            "found": LOCS[p ^ a],
        }
        for index, (p, a) in enumerate([(p, a) for _ in range(5) for p in (0, 1) for a in (0, 1)])
    ]


def test_conditional_relation_changes_action_and_negative_observation_changes_actor():
    joint, env, projection = setup(target=11)
    joint.history = xor_history()
    joint.previous = LOCS[0]
    factor = CurrentLocationBelief(LOCS, ACTORS, LocationModelConfig("factor"))
    factor.history = deepcopy(joint.history)
    factor.previous = joint.previous
    cue_projection = {**projection, "actor_cue": {"a": 0.1, "b": 0.9}}
    joint.begin(cue_projection)
    factor.begin(cue_projection)
    assert joint.rank()[0] == LOCS[1] and factor.rank()[0] == LOCS[0]
    # This constructed witness tests an interface; it is not research evidence.
    joint, env, projection = setup(target=11)
    joint.history = xor_history()
    joint.previous = LOCS[0]
    joint.begin(projection)
    env.begin_step(UUID(int=2))
    env.finish_probing()
    request = LocationInspectionRequest(
        UUID(int=5), UUID(int=1), UUID(int=2), UUID(int=3), UUID(int=10)
    )
    joint.consume(request, env.inspect(request), env)
    assert sum(joint.export_joint()["b"].values()) > 0.9
    assert joint.location_distribution()[LOCS[0]] == 0
    assert len(joint.history) == 20  # no learning before terminal evidence


def test_no_actor_cue_marginalizes_both_relations_to_same_markov_prediction():
    probabilities = []
    for kind in ("joint", "factor", "markov"):
        head, _, projection = setup(config=LocationModelConfig(kind))
        head.history = xor_history()[:-3]
        head.previous = LOCS[0]
        head.begin(projection)
        probabilities.append(head.location_distribution())
    for value in probabilities[1:]:
        assert value == pytest.approx(probabilities[0])


def test_paid_support_exhaustion_clears_memory_without_fabricating_actor_label():
    head, env, projection = setup(target=99)
    head.previous = LOCS[0]
    row = execute_current_search(head, projection, env)
    assert row["status"] == "support_exhausted" and row["paid_checks"] == 2
    assert head.previous is None and head.history[-1]["found"] is None
    assert all(v == 0 for v in head.location_distribution().values())


@pytest.mark.parametrize(
    "attack",
    [
        "extra_field",
        "cue_outside",
        "cue_negative",
        "cue_nan",
        "visible_outside",
        "duplicate_step",
        "unfinished_begin",
        "early_finish",
        "forged_receipt",
    ],
)
def test_reject_invalid_inputs_and_complete_forgery_without_learning(attack):
    head, env, projection = setup()
    if attack == "extra_field":
        projection["true_actor"] = "a"
    if attack == "cue_outside":
        projection["actor_cue"] = {"x": 1.0}
    if attack == "cue_negative":
        projection["actor_cue"] = {"a": -0.1, "b": 1.1}
    if attack == "cue_nan":
        projection["actor_cue"] = {"a": float("nan"), "b": 0.0}
    if attack == "visible_outside":
        projection["visible_location"] = str(UUID(int=99))
    if attack == "duplicate_step":
        head.history.append({"step_id": projection["step_id"]})
    if attack in {"unfinished_begin", "early_finish", "forged_receipt"}:
        head.begin(projection)
    before = deepcopy(head.history)
    with pytest.raises(ValueError):
        if attack == "early_finish":
            head.finish()
        elif attack == "forged_receipt":
            env.begin_step(UUID(int=2))
            env.finish_probing()
            request = LocationInspectionRequest(
                UUID(int=5), UUID(int=1), UUID(int=2), UUID(int=3), UUID(int=10)
            )
            real = env.inspect(request)
            forged = replace(
                real,
                found=False,
                receipt_sha256=content_sha256({"request": request, "ordinal": 1, "found": False}),
            )
            head.consume(request, forged, env)
        else:
            head.begin(projection)
    assert head.history == before


def test_terminal_learning_uses_public_cue_not_inferred_actor_responsibility():
    head, env, projection = setup(target=11)
    head.history = xor_history()
    head.previous = LOCS[0]
    execute_current_search(head, projection, env)
    assert head.history[-1]["actor_cue"] is None
    table = head.table()
    baseline, _, _ = setup()
    baseline.history = xor_history()
    old = baseline.table()
    assert table[LOCS[0], "a", LOCS[1]] - old[LOCS[0], "a", LOCS[1]] == pytest.approx(0.5)
    assert table[LOCS[0], "b", LOCS[1]] - old[LOCS[0], "b", LOCS[1]] == pytest.approx(0.5)


def test_projection_and_full_framework_adapter_match_isolated_actual_search():
    dataset = dataset_for("sparse32", seeds=[64001])
    episode = dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)[0]
    # The head cannot see after/source/attempted coordinates through cue_only.
    observed = next(s for s in episode.steps if s.after is not None)
    projection = project_search_input(observed, episode.resident_actor_keys, view="cue_only")
    assert projection["visible_location"] is None and projection["actor_cue"] is not None
    altered = observed.model_copy(
        update={
            "after": None,
            "source_location_id": UUID(int=999),
            "attempted_location_id": UUID(int=998),
        }
    )
    assert project_search_input(altered, episode.resident_actor_keys, view="cue_only") == projection
    runs = []
    for kind in ("joint", "factor"):
        config = LocationModelConfig(kind)
        isolated = evaluate(dataset, episode, config, "cue_only")
        integrated = evaluate(dataset, episode, config, "cue_only", integrate=True)
        assert integrated["actions"] == isolated["actions"]
        assert all(
            a["planned_order"] == b["search_order"]
            for a, b in zip(integrated["actions"], integrated["framework_actions"], strict=True)
        )
        runs.append(integrated)
        import json

        counts, _ = score_run(
            json.loads(json.dumps(integrated)),
            episode.model_dump(mode="json"),
            dataset.truth_for(episode.episode_id).model_dump(mode="json"),
        )
        assert counts["n"] == len(episode.steps) and counts["bound_feedback_actions"] > 0
    assert (
        runs[0]["runtime_audit"]["final_state_sha256"]
        == runs[1]["runtime_audit"]["final_state_sha256"]
    )
    assert [r["put_back"] for r in runs[0]["framework_actions"]] == [
        r["put_back"] for r in runs[1]["framework_actions"]
    ]
