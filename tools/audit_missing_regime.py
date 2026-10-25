"""After-diagnosis targeted replay of the two recurrence episodes, no held-out claim."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from analyze_matched_readout import capture, decompose
from audit_synergy_posteriors import RECURRENCE, recurrence
from run_five_stage_synergy import bound_sources
from run_joint_three_questions import paired_counts
from run_matched_value import NATIVE, action_payload, dataset_for, make_state, save, state_audit
from synergy_missing_regime import MissingRegimeNeutralRuntime

from cpswm.contracts import ProjectTwoDatasetSplit as Split
from cpswm.system.reproducibility import content_sha256

ROOT = Path(__file__).resolve().parents[1]


def run(primary, output):
    code_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    sources = bound_sources()
    for name in ("tools/synergy_missing_regime.py", "tools/audit_missing_regime.py"):
        sources[name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    old = json.loads((primary / "points.json").read_text())
    old = {
        (p["episode_id"], p["step"]): p
        for p in old
        if p["cohort"] == "old" and p["condition"] == "sparse32"
    }
    dataset = dataset_for("sparse32")
    rows = []
    for episode in dataset.visible_episodes(Split.TEST):
        if str(episode.episode_id)[:8] not in RECURRENCE:
            continue
        states = {arm: make_state(episode, arm) for arm in NATIVE}
        for state in states.values():
            r = state.runtime
            state.runtime = MissingRegimeNeutralRuntime(
                arm=r.arm, config=r.config, neural_model=r.neural_model
            )
        for index, step in enumerate(episode.steps):
            predictions = {}
            for arm, state in states.items():
                state.observe(step.model_copy(deep=True))
                predictions[arm] = action_payload(state.predict(), episode.known_location_ids)
            previous = old[str(episode.episode_id), index + 1]
            assert previous["input_sha256"] == content_sha256(step)
            result = {
                "episode": str(episode.episode_id),
                "step": index + 1,
                "truth": previous["truth"],
                "methods": {},
            }
            for arm, state in states.items():
                record = {
                    "action": predictions[arm],
                    "baseline": previous["actions"][arm + "/posterior_parent"],
                    "readout": decompose(capture(state)),
                }
                if index + 1 in RECURRENCE[str(episode.episode_id)[:8]]:
                    record["recurrence"] = recurrence(state.runtime, previous["truth"])
                state.feedback(step.model_copy(deep=True))
                audit = state_audit(state)
                baseline = previous["stats"][arm + "/posterior_parent"]["audit"]
                assert all(
                    audit[k] == baseline[k]
                    for k in (
                        "target_evaluations",
                        "particles",
                        "extra_ciav_queries",
                        "paid_location_sources",
                    )
                )
                record["audit"] = audit
                result["methods"][arm] = record
            rows.append(result)
        print(episode.episode_id, len(rows), flush=True)
    summary = {
        arm: paired_counts(
            [r["methods"][arm]["baseline"]["put_back"] for r in rows],
            [r["methods"][arm]["action"]["put_back"] for r in rows],
            [r["truth"] for r in rows],
        )
        for arm in NATIVE
    }
    assert all(hashlib.sha256((ROOT / n).read_bytes()).hexdigest() == d for n, d in sources.items())
    save(
        output,
        {
            "source_sha": code_sha,
            "sources": sources,
            "rows": rows,
            "summary": summary,
            "scope": "post-hoc target intervention; two development recurrence episodes",
            "scientific_acceptance": False,
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("primary", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.primary, args.output)
