from cpswm.system.evaluation_operations.cross_structure_strata_diagnostic import (
    FROZEN_DECISION_RULES,
    PROJECT_ONE_PARAMS,
    PROJECT_TWO_PARAMS,
    STRATA,
    _project_one_strata,
    _project_two_dataset,
    _transform_project_two_episode,
)
from cpswm.system.evaluation_operations.project_two_action_benchmark import (
    ProjectTwoActionMethod,
)


def test_four_strata_and_decision_rules_are_frozen():
    assert len(STRATA) == 4
    assert set(FROZEN_DECISION_RULES) == {
        "core_technical_failure",
        "data_activation_supported",
        "domain_gap",
        "insufficient_evidence",
    }
    assert len(PROJECT_ONE_PARAMS) == 3
    assert ProjectTwoActionMethod.PROJECT_TWO in PROJECT_TWO_PARAMS


def test_project_one_strata_preserve_seed_and_truth_except_simultaneous_cause():
    strata = _project_one_strata(25)
    assert all(len(items) == 25 for items in strata.values())
    for index in range(25):
        first = strata["s1_known_actor_complete_evidence"][index]
        second = strata["s2_actor_confusion_missing_evidence"][index]
        third = strata["s3_wrong_then_late_correct_evidence"][index]
        assert first.evaluator_truth == second.evaluator_truth == third.evaluator_truth
        assert len(second.model_input.actor_evidence) < len(first.model_input.actor_evidence)


def test_project_two_strata_preserve_truth_and_change_only_visible_input():
    dataset = _project_two_dataset(25)
    episode = dataset.visible_episodes(dataset.episodes[-1].split)[0]
    complete = _transform_project_two_episode(dataset, episode, mode="complete")
    confused = _transform_project_two_episode(dataset, episode, mode="confused_missing")
    delayed = _transform_project_two_episode(dataset, episode, mode="wrong_then_correct")
    simultaneous = _transform_project_two_episode(dataset, episode, mode="observation_plus_habit")
    assert complete.episode_id == confused.episode_id == delayed.episode_id
    assert dataset.truth_for(episode.episode_id) == dataset.truth_for(complete.episode_id)
    assert sum(step.actor_evidence is None for step in confused.steps) > 0
    assert sum(step.after is None for step in simultaneous.steps) > 0


def test_project_two_seed_variation_changes_truth_trajectory_not_only_uuid():
    dataset = _project_two_dataset(25)
    test = dataset.visible_episodes(dataset.episodes[-1].split)
    change_signatures = set()
    for episode in test:
        assert all(step.after is not None for step in episode.steps)
        truth = dataset.truth_for(episode.episode_id)
        assert any(item.true_actor == "guest" for item in truth.truth_by_step.values())
        locations = tuple(item.true_owner_habit_location for item in truth.truth_by_step.values())
        change_signatures.add(tuple(location == locations[0] for location in locations))
    assert len(change_signatures) > 10
