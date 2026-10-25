"""Evaluator-only object binding; these values must never be policy/core inputs."""

TARGET = "akita_black_bowl_1"
DESTINATIONS = {"plate": "plate_1", "stove": "flat_stove_1"}


def evaluate_goal(environment, destination):
    if destination not in DESTINATIONS:
        raise ValueError("no declared goal predicate for destination")
    inner = environment.env.env
    predicate = ["on", TARGET, DESTINATIONS[destination]]
    if any(name not in inner.object_states_dict for name in predicate[1:]):
        raise ValueError("goal object missing in pinned task")
    return {
        "predicate": predicate,
        "success": bool(inner._eval_predicate(predicate)),
        "scope": "evaluator_only",
    }
