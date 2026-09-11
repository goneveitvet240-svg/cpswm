#!/usr/bin/env python3
"""Deterministic error attribution and initial-ignorance counterfactual, development only."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path
from uuid import UUID

import numpy as np

from cpswm.contracts import ProjectTwoDatasetSplit
from cpswm.system.evaluation_operations import structure_two_comparison_audit as audit
from cpswm.system.reproducibility import content_sha256, content_uuid


def analyze(bundle: Path, root: Path) -> dict:
    retained = json.loads((bundle / "audit.json").read_text())
    rows = [
        json.loads(v)
        for v in gzip.decompress((bundle / "steps.jsonl.gz").read_bytes()).splitlines()
    ]
    if content_sha256(audit._semantic_rows(rows)) != retained["semantic_steps_sha256"]:
        raise ValueError("step bundle semantic hash mismatch")
    groups = {}
    selectors = {
        "before_first_detection": lambda r: r["observation_age"] is None,
        "after_at_least_one_detection": lambda r: r["observation_age"] is not None,
        "negative_after_detection": lambda r: (
            r["observation_age"] is not None and r["detected_location"] is None
        ),
        "p5_habit_uniform": lambda r: (
            max(r["arms"][audit.P5]["habit"].values()) - min(r["arms"][audit.P5]["habit"].values())
            < 1e-12
        ),
        "p5_habit_nonuniform": lambda r: (
            max(r["arms"][audit.P5]["habit"].values()) - min(r["arms"][audit.P5]["habit"].values())
            >= 1e-12
        ),
        "amg_chooses_first_support": lambda r: r["arms"][audit.AMG]["put_back"] == r["support"][0],
        "p5_win_steps": lambda r: r["category"] == "p5_wins",
        "p5_loss_steps": lambda r: r["category"] == "p5_loses",
        "both_wrong_steps": lambda r: r["category"] == "both_wrong",
        "both_correct_steps": lambda r: r["category"] == "both_correct",
    }
    for key, predicate in selectors.items():
        chosen = [r for r in rows if predicate(r)]
        groups[key] = (
            audit.aggregate(chosen)
            if chosen
            else {"overall": {"steps": 0, "episodes": 0}, "status": "unmeasured_no_samples"}
        )
    dataset = (
        audit.D0SyntheticReplayExperimentConfig.load(root / audit.DATA_CONFIG)
        .build_adapter()
        .build()
    )
    steps = {
        str(s.step_id): s
        for e in dataset.visible_episodes(ProjectTwoDatasetSplit.TEST)
        for s in e.steps
    }
    owner_memory_missing = {}
    for episode in dataset.visible_episodes(ProjectTwoDatasetSplit.TEST):
        state = audit.base.AMGLocationAdapter(
            episode, parameter=retained["selection"]["selected_amg_parameter"]
        )
        schedule = audit.base._episode_schedule_commitment(episode)
        for index, step in enumerate(episode.steps):
            packet = audit.base._packet_for_step(episode, step, schedule_commitment_sha256=schedule)
            state.consume_matched_ciav_packet(packet, step, step_index=index)
            owner_memory_missing[str(step.step_id)] = state.state.amg_owner_location is None
    cold_owner_examples = []
    # Reconstruct AMG's own absence of an owner estimate, independently of P5 or truth.
    # Change only this prior to explicit uniform ignorance, holding observations fixed.
    for row in rows:
        if not owner_memory_missing[row["step_id"]]:
            continue
        step = steps[row["step_id"]]
        if content_sha256(step) != row["visible_step_sha256"]:
            raise ValueError("regenerated visible trajectory differs")
        support = tuple(UUID(v) for v in row["support"])
        uniform = dict.fromkeys(support, 1.0 / len(support))
        posterior = audit.TypedLocationPosterior.seal(
            arm=audit.P5ComparisonArm.TUNED_AMG,
            episode_id=UUID(row["episode_id"]),
            step_id=step.step_id,
            target_object_id=step.object_instance_id,
            source_visible_step_sha256=row["visible_step_sha256"],
            belief_state_sha256=content_sha256({"development_uniform": True}),
            location_support=support,
            current_location_distribution=uniform,
            owner_habit_location_distribution=uniform,
        )
        committed = audit.decode(
            posterior, step, row["step_index"], content_uuid(audit.AUDIT_ID, "initial-ignorance")
        )
        # The alternative action exists before scoring against the opened row's truth.
        truth = row["truth"]
        choice = str(committed.put_back_action.location_id)
        cold_owner_examples.append(
            {
                "episode_id": row["episode_id"],
                "step_id": row["step_id"],
                "step_index": row["step_index"],
                "before_first_detection": row["observation_age"] is None,
                "original_amg": row["arms"][audit.AMG]["put_back"],
                "uniform_amg": choice,
                "p5": row["arms"][audit.P5]["put_back"],
                "uniform_amg_error": int(choice != truth["true_owner_habit_location"]),
                "original_amg_error": row["arms"][audit.AMG]["put_back_error"],
            }
        )
    initial_examples = [e for e in cold_owner_examples if e["before_first_detection"]]
    historical = json.loads((root / audit.HISTORY).read_text())
    action_chain_checks = []
    for metric in historical["holdout_episode_metrics"]:
        episode_rows = [r for r in rows if r["episode_id"] == metric["episode_id"]]
        chain = audit.base._semantic_action_chain_sha256(
            [
                {
                    "search_location_id": r["arms"][metric["arm"]]["search_order"][0],
                    "put_back_location_id": r["arms"][metric["arm"]]["put_back"],
                }
                for r in episode_rows
            ]
        )
        action_chain_checks.append(
            {
                "episode_id": metric["episode_id"],
                "arm": metric["arm"],
                "matches": chain == metric["typed_action_chain_sha256"],
            }
        )
    if not all(check["matches"] for check in action_chain_checks):
        raise ValueError("historical action chain mismatch")
    learned_confusion = Counter()
    for row in rows:
        cause, event = row["derived_cause_event_labels"]
        learned_confusion[
            f"true={cause * 3 + event},"
            f"predicted={int(np.argmax(row['raw_state']['learned_joint']))}"
        ] += 1
    counts = {
        field: dict(Counter(row["raw_state"]["p5_readouts"]["state_counts"][field] for row in rows))
        for field in rows[0]["raw_state"]["p5_readouts"]["state_counts"]
    }
    return {
        "audit_id": audit.AUDIT_ID,
        "development_only": True,
        "source_semantic_steps_sha256": retained["semantic_steps_sha256"],
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "groups": groups,
        "historical_action_chain_checks": action_chain_checks,
        "common_uniform_when_amg_has_no_owner_estimate": {
            "steps": len(cold_owner_examples),
            "examples": cold_owner_examples,
            "original_amg_errors": sum(r["original_amg_error"] for r in cold_owner_examples),
            "uniform_amg_errors": sum(r["uniform_amg_error"] for r in cold_owner_examples),
            "uniform_amg_equals_p5_steps": sum(
                r["uniform_amg"] == r["p5"] for r in cold_owner_examples
            ),
            "trigger": (
                "fresh AMG replay amg_owner_location is None; no P5 or truth-based selection"
            ),
            "development_only": True,
        },
        "learned_joint_confusion": dict(learned_confusion),
        "p5_state_count_histograms": counts,
        "p5_vs_fast_put_back_disagreement_steps": sum(
            r["arms"][audit.P5]["put_back"]
            != r["alternative_readouts_development_only"]["fast"]["put_back"]
            for r in rows
        ),
        "common_uniform_before_first_detection": {
            "steps": len(initial_examples),
            "examples": initial_examples,
            "original_amg_errors": sum(r["original_amg_error"] for r in initial_examples),
            "uniform_amg_errors": sum(r["uniform_amg_error"] for r in initial_examples),
            "uniform_amg_equals_p5_steps": sum(
                r["uniform_amg"] == r["p5"] for r in initial_examples
            ),
            "scope": (
                "fixed observed data/support/public decoder; no fitted parameter or seed changed; "
                "initial-ignorance diagnostic only"
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    result = analyze(args.bundle, root)
    output = args.bundle / "attribution.json"
    if args.verify:
        if json.loads(output.read_text()) != json.loads(json.dumps(result)):
            raise ValueError("fresh attribution differs")
        print("attribution verified")
    else:
        with output.open("x") as handle:
            json.dump(result, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
        print(output)


if __name__ == "__main__":
    main()
