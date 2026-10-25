from types import SimpleNamespace

import pytest
from synergy_goal_evaluator import evaluate_goal


def test_scores_selected_target_and_destination_not_official_done_or_other_bowl():
    calls = []

    def predicate(state):
        calls.append(state)
        return state == ["on", "akita_black_bowl_1", "plate_1"]

    inner = SimpleNamespace(
        object_states_dict=dict.fromkeys(
            ("akita_black_bowl_1", "akita_black_bowl_2", "plate_1", "flat_stove_1")
        ),
        _eval_predicate=predicate,
    )
    env = SimpleNamespace(env=SimpleNamespace(env=inner), evaluator_success=True)
    assert evaluate_goal(env, "plate")["success"] is True
    assert evaluate_goal(env, "stove")["success"] is False
    assert calls == [
        ["on", "akita_black_bowl_1", "plate_1"],
        ["on", "akita_black_bowl_1", "flat_stove_1"],
    ]
    with pytest.raises(ValueError):
        evaluate_goal(env, "flat_stove_1_cook_region")
    del inner.object_states_dict["akita_black_bowl_1"]
    with pytest.raises(ValueError):
        evaluate_goal(env, "plate")
