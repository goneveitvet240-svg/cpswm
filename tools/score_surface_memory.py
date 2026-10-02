"""Score actual restored/withdrawn reports with the unchanged isolated evaluator."""

import argparse
import json
import os
from pathlib import Path

from evaluate_surface_episode import evaluate
from run_surface_episode import save


def score(episode, memory, targets, output):
    output.mkdir(parents=True, exist_ok=False)
    original = json.loads((episode / "result.json").read_text())
    results = []
    for phase in ("retain", "withdraw-first", "withdraw-last", "reset"):
        control = json.loads((memory / phase / "control.json").read_text())
        fresh = json.loads((memory / phase / "fresh-verification.json").read_text())
        if fresh != dict(equal=True, no_external_executor=True, physical_actions_preserved=True):
            raise ValueError("memory control lacks fresh replay verification")
        if control["later_task_actions"] != 0:
            raise ValueError("memory controls must share zero additional action budget")
        folder = output / phase
        folder.mkdir()
        for name in ("public", "transport"):
            os.symlink(episode / name, folder / name, target_is_directory=True)
        # This detached projection is expressly a scored memory intervention, not
        # a forged raw acquisition run. Actual reports are from owner replay above.
        result = dict(
            original,
            final_reports=control["after"],
            memory_intervention=phase,
            scope=control["scope"],
            control_path=str(memory / phase / "control.json"),
        )
        save(folder / "result.json", result)
        evaluate(folder, targets, folder / "evaluation.json")
        value = json.loads((folder / "evaluation.json").read_text())
        results.append(
            dict(
                phase=phase,
                joint_success=value["joint_success"],
                identity_correct=value["identity_correct"],
                position_correct=value["position_correct"],
                task_count=value["task_count"],
                additional_actions=0,
            )
        )
    save(
        output / "summary.json",
        dict(
            groups=results,
            paired_budget=0,
            scope="static re-query at recorded epoch, not novel task or changed-world benefit",
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("episode", type=Path)
    p.add_argument("memory", type=Path)
    p.add_argument("targets", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    score(a.episode, a.memory, json.loads(a.targets.read_text()), a.output)
