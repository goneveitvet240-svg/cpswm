import pytest
from audit_synergy_corrections import run
from verify_synergy_goal_episode import validate_goal_outcomes


def records():
    manifest = {"arguments": {"steps": 220}}
    summary = {
        "steps": 3,
        "requested_steps": 220,
        "goal_success_evaluator_only": True,
        "first_success_step_evaluator_only": 3,
        "stop_reason": "goal_success",
    }
    journal = [
        {"event": "policy_inference", "tick": 100, "plan": {"command": {"destination": "stove"}}},
        {"event": "policy_inference", "tick": 102, "plan": {"command": {"destination": "plate"}}},
    ]
    for i in range(3):
        journal.append(
            {
                "event": "executed_action",
                "policy_tick": 100 if i < 2 else 102,
                "goal_evaluation_only": {
                    "predicate": [
                        "on",
                        "akita_black_bowl_1",
                        "flat_stove_1" if i < 2 else "plate_1",
                    ],
                    "scope": "evaluator_only",
                    "success": i == 2,
                },
                "official_plate_success_evaluator_only": i == 2,
            }
        )
    return manifest, summary, journal


def test_goal_outcomes_accept_legal_positive_and_full_budget_negative():
    manifest, summary, journal = records()
    validate_goal_outcomes(manifest, summary, journal)
    manifest["arguments"]["steps"] = summary["requested_steps"] = 3
    summary.update(
        goal_success_evaluator_only=False,
        first_success_step_evaluator_only=None,
        stop_reason="step_limit",
    )
    journal[-1]["goal_evaluation_only"]["success"] = False
    journal[-1]["official_plate_success_evaluator_only"] = False
    validate_goal_outcomes(manifest, summary, journal)


@pytest.mark.parametrize(
    "corruption", ["object", "destination", "success", "early", "scope", "budget"]
)
def test_plausible_complete_but_wrong_outcomes_rejected(corruption):
    m, s, j = records()
    if corruption == "object":
        j[-1]["goal_evaluation_only"]["predicate"][1] = "akita_black_bowl_2"
    elif corruption == "destination":
        j[-1]["goal_evaluation_only"]["predicate"][2] = "flat_stove_1"
    elif corruption == "success":
        s["goal_success_evaluator_only"] = False
    elif corruption == "early":
        s["first_success_step_evaluator_only"] = 2
    elif corruption == "scope":
        j[-1]["goal_evaluation_only"]["scope"] = "policy_input"
    else:
        s["requested_steps"] = 219
    with pytest.raises(ValueError):
        validate_goal_outcomes(m, s, j)


def test_correction_matrix_covers_positive_restore_and_strong_source_control():
    results = run()["rows"]
    assert len(results) == 8
    for row in results:
        assert len(row["invalid_cases_rejected_without_mutation"]) == 5
        destinations = [p["command"]["destination"] for p in row["plans"]]
        assert destinations == (
            ["stove"] * 3 if row["arm"] == "ordinary_memory" else ["stove", "plate", "stove"]
        )
