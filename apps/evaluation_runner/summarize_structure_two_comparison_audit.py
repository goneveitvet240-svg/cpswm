#!/usr/bin/env python3
"""Deterministic error attribution and initial-ignorance counterfactual, development only."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from uuid import UUID

# Bootstrap from this CLI's sibling source bytes before ANY project import.
# Importing the module for descriptive analysis does not authorize verification.
_EXECUTION_SOURCE = None
if __name__ == "__main__":
    import sys

    _guard_path = Path(__file__).resolve().with_name("_structure_two_audit_source.py")
    _guard_bytes = _guard_path.read_bytes()
    _guard_namespace = {"__file__": str(_guard_path), "__name__": "_audit_cli_source_guard"}
    try:
        exec(compile(_guard_bytes, str(_guard_path), "exec", dont_inherit=True), _guard_namespace)
        _EXECUTION_SOURCE = _guard_namespace["bootstrap"](
            __file__, sys._getframe().f_code, _guard_bytes
        )
    except Exception as error:
        print(json.dumps({"status": "EXECUTION_SOURCE_REJECTED", "error": str(error)}))
        raise SystemExit(1) from error

import numpy as np  # noqa: E402

from cpswm.contracts import ProjectTwoDatasetSplit  # noqa: E402
from cpswm.system.evaluation_operations import structure_two_comparison_audit as audit  # noqa: E402
from cpswm.system.reproducibility import content_sha256, content_uuid  # noqa: E402


def analyze(bundle: Path, root: Path) -> dict:
    """Generate descriptive FILE_CONSISTENCY_ONLY analysis, without certifying rows."""
    return analyze_snapshot(audit.load_bundle(bundle), root)


def analyze_snapshot(snapshot: audit.BundleSnapshot, root: Path) -> dict:
    retained, rows = snapshot.payload, snapshot.rows
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
            current_location_distribution={
                UUID(k): v for k, v in row["arms"][audit.AMG]["current"].items()
            },
            owner_habit_location_distribution=uniform,
        )
        committed = audit.decode(
            posterior, step, row["step_index"], content_uuid(audit.AUDIT_ID, "initial-ignorance")
        )
        if [str(a.location_id) for a in committed.search_plan] != row["arms"][audit.AMG][
            "search_order"
        ]:
            raise ValueError("COLD_CONTROL_CHANGED_SEARCH")
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
                "search_order_unchanged": True,
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
        "evidence_level": "FILE_CONSISTENCY_ONLY_UNTIL_FRESH_REPLAY",
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


def verify_bundles(bundles: list[Path], root: Path) -> tuple[list[dict], bool]:
    """Real verification: one internally computed reference per batch, no disk cache.

    All inputs are snapshotted before replay; invalid bundles cannot poison the
    reference or turn another bundle green. No expected-result parameter exists.
    """
    if _EXECUTION_SOURCE is None:
        raise RuntimeError("TRUSTED_CLI_BOOTSTRAP_REQUIRED")
    _EXECUTION_SOURCE.require_root(root)
    _EXECUTION_SOURCE.checkpoint()
    snapshots = {}
    results = {}
    for index, bundle in enumerate(bundles):
        try:
            snapshot = audit.load_bundle(bundle, with_attribution=True)
            audit.check_source_binding(snapshot, root)
            _EXECUTION_SOURCE.checkpoint()
            snapshots[index] = snapshot
        except (ValueError, OSError, KeyError, TypeError) as error:
            results[index] = {
                "bundle": str(bundle),
                "status": "REJECTED",
                "stage": "load_or_source_binding",
                "error": str(error),
            }
    if snapshots:
        before = audit.source_bindings(root)
        # Full train + validation selection + all configured episodes + three arms.
        # Timing is not an attribution dependency; one fixed timing sample suffices here.
        payload, rows, _timing = audit.run_audit(root, timing_repeats=1, timing_episodes=1)
        _EXECUTION_SOURCE.require_bindings(payload["source_bindings"])
        expected = analyze_snapshot(audit.BundleSnapshot(payload, rows), root)
        if audit.source_bindings(root) != before:
            raise ValueError("SOURCE_CHANGED_DURING_VERIFICATION")
        for index, snapshot in snapshots.items():
            try:
                audit.compare_snapshot(snapshot, payload, rows)
                difference = audit.first_difference(
                    snapshot.attribution, json.loads(json.dumps(expected)), "attribution"
                )
                if difference:
                    raise ValueError(f"FRESH_REPLAY_ATTRIBUTION_MISMATCH: {difference}")
                results[index] = {
                    "bundle": str(bundles[index]),
                    "status": "CURRENT_SOURCE_FRESH_REPLAY_MATCH",
                    "input_snapshot_sha256": content_sha256(
                        {
                            "audit": snapshot.payload,
                            "rows": snapshot.rows,
                            "attribution": snapshot.attribution,
                        }
                    ),
                    "steps": len(rows),
                    "episodes": len(payload["summary"]["episodes"]),
                    "semantic_steps_sha256": payload["semantic_steps_sha256"],
                    "formal_scientific_verification": False,
                    "independent_historical_custody": False,
                }
            except (ValueError, KeyError, TypeError) as error:
                results[index] = {
                    "bundle": str(bundles[index]),
                    "status": "REJECTED",
                    "stage": "fresh_replay_comparison",
                    "error": str(error),
                }
    _EXECUTION_SOURCE.checkpoint()
    ordered = [results[index] for index in range(len(bundles))]
    return ordered, bool(snapshots)


def main() -> None:
    if _EXECUTION_SOURCE is None:
        raise RuntimeError("TRUSTED_CLI_BOOTSTRAP_REQUIRED")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bundle",
        type=Path,
        required=True,
        action="append",
        help="repeat to verify multiple bundles against one fresh in-process replay",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--verify",
        action="store_true",
        help="full current-source replay; no precomputed reference accepted",
    )
    mode.add_argument(
        "--check-file-consistency",
        action="store_true",
        help="file self-consistency only; does NOT verify P5 state authenticity",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    if args.verify:
        try:
            results, replayed = verify_bundles(args.bundle, root)
        except Exception as error:
            print(
                json.dumps(
                    {
                        "status": "VERIFICATION_FAILED",
                        "stage": "fresh_replay",
                        "error": f"{type(error).__name__}: {error}",
                    }
                ),
                flush=True,
            )
            raise SystemExit(1) from error
        print(
            json.dumps(
                {
                    "verification_mode": "CURRENT_SOURCE_FRESH_REPLAY",
                    "execution_source": _EXECUTION_SOURCE.identity(),
                    "fresh_replay_performed": replayed,
                    "results": results,
                },
                sort_keys=True,
            )
        )
        if any(result["status"] == "REJECTED" for result in results):
            raise SystemExit(1)
        return
    if len(args.bundle) != 1:
        parser.error("multiple bundles are supported only by --verify")
    bundle = args.bundle[0]
    if args.check_file_consistency:
        snapshot = audit.load_bundle(bundle, with_attribution=True)
        result = analyze_snapshot(snapshot, root)
        difference = audit.first_difference(
            snapshot.attribution, json.loads(json.dumps(result)), "attribution"
        )
        if difference:
            raise ValueError(f"FILE_INCONSISTENCY: {difference}")
        print(
            json.dumps(
                {
                    "status": "FILE_CONSISTENCY_ONLY",
                    "fresh_replay_performed": False,
                    "p5_state_authenticity_verified": False,
                }
            )
        )
    else:
        result = analyze(bundle, root)
        output = bundle / "attribution.json"
        with output.open("x") as handle:
            json.dump(result, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
        print(json.dumps({"status": "UNVERIFIED_ATTRIBUTION_WRITTEN", "output": str(output)}))


if __name__ == "__main__":
    try:
        main()
    except _guard_namespace["ExecutionSourceError"] as error:
        print(json.dumps({"status": "EXECUTION_SOURCE_REJECTED", "error": str(error)}))
        raise SystemExit(1) from error
