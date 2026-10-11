"""Actual paid-prefix revision probes; engineering evidence, not model selection."""

import argparse
import copy
import json
from dataclasses import asdict
from pathlib import Path

from run_shared_location import dataset_for

from cpswm.contracts import ProjectTwoDatasetSplit
from cpswm.system.evaluation_operations.project_two_action_benchmark import _locations
from cpswm.system.evaluation_operations.structure_two_current_location import (
    execute_current_search,
    project_search_input,
)
from cpswm.system.evaluation_operations.structure_two_executed_search import (
    ExecutedD0SearchEnvironment,
)
from cpswm.system.evaluation_operations.structure_two_shared_location import (
    SharedLocationBelief,
    SharedLocationConfig,
)
from cpswm.system.reproducibility import content_sha256


def probe():
    dataset = dataset_for("sparse32")
    episode = dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)[0]
    cases = []
    for view in ("native", "cue_only"):
        for kind in ("joint", "factor"):
            config = SharedLocationConfig(kind, 0.25, 0.9, 2, 2)
            head = SharedLocationBelief(_locations(episode), episode.resident_actor_keys, config)
            env = ExecutedD0SearchEnvironment(
                episode,
                _locations(episode),
                lambda sid: dataset.truth_for(episode.episode_id).truth_by_step[sid].true_location,
            )
            for step in episode.steps[:8]:
                execute_current_search(
                    head, project_search_input(step, head.actors, view=view), env
                )
            original = copy.deepcopy(head)
            history = copy.deepcopy(head.history)
            log_hash = content_sha256(head.records)
            source_id = str(episode.steps[6].step_id)
            source = head.source_digest(source_id)
            withdrawn_receipt = head.revise_location_source(source_id, source)
            withdrawn = copy.deepcopy(head)
            restored_receipt = head.revise_location_source(source_id, source, restore=True)
            assert head.history == history and content_sha256(head.records) == log_hash
            assert head.table() == original.table()
            input_next = project_search_input(episode.steps[8], head.actors, view=view)
            next_rows = {
                label: execute_current_search(model, input_next, copy.deepcopy(env))
                for label, model in (
                    ("control", original),
                    ("withdrawn", withdrawn),
                    ("restored", head),
                )
            }
            assert next_rows["control"] == next_rows["restored"]
            cases.append(
                {
                    "view": view,
                    "config": asdict(config),
                    "locations": head.locations,
                    "actors": head.actors,
                    "original_history": history,
                    "withdrawn_history": withdrawn.history[:-1],
                    "source": head._sources[source_id][0],
                    "source_sha256": source,
                    "withdraw_receipt": withdrawn_receipt,
                    "restore_receipt": restored_receipt,
                    "next_input": input_next,
                    "next_rows": next_rows,
                    "original_action_records_unchanged": True,
                    "target_next": str(
                        dataset.truth_for(episode.episode_id)
                        .truth_by_step[episode.steps[8].step_id]
                        .true_location
                    ),
                }
            )
    return {
        "cases": cases,
        "actual_step_executions": 44,
        "scope": (
            "four paid 8-step development prefixes and 3 actual continuations each; "
            "engineering diagnostic only"
        ),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(probe(), indent=2, sort_keys=True) + "\n")
