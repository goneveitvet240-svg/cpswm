"""Offline truth scoring for controlled correction diagnostics, plus component probes.

Does not feed evaluator truth to production, select interventions, or score physical
execution. A forced negative-search intervention is not ground-truth actor evidence.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from uuid import UUID

from run_matched_transition_death_test import digest, load, save

from cpswm.system.evaluation_operations.structure_two_action_death_test import (
    StructureTwoActionScenarioGenerator,
)
from cpswm.system.reproducibility import content_sha256


def score_case(result):
    case = StructureTwoActionScenarioGenerator(duration_days=32, observation_coverage=1.0).generate(
        result["seed"]
    )
    if content_sha256(case.visible) != result["visible_case_sha256"]:
        raise ValueError("evaluator truth does not bind to runtime visible case")
    rows = []
    for step in result["steps"]:
        truth = case.truth_by_day[step["scenario_day"]]
        target = str(truth.true_owner_habit_location)
        rows.append(
            {
                "day": truth.day,
                "true_actor": truth.true_actor,
                "true_habit_location": target,
                "ciav_location_matches_scenario": step.get("ciav_expected_location")
                == str(truth.true_location_after),
                "production_choice": step["state"]["argmax"],
                "soft_memory_choice": step["soft_memory"]["argmax"],
                "production_correct": step["state"]["argmax"] == target,
                "soft_memory_correct": step["soft_memory"]["argmax"] == target,
                "actor_argmax_correct": max(
                    step["actor_posterior"], key=step["actor_posterior"].__getitem__
                )
                == truth.true_actor,
                "committed_sources": len(step["state"]["committed_sources"]),
                "observed_sources": len(step["state"]["observed_sources"]),
            }
        )
    if result.get("status") == "NO_LEGAL_CORRECTION_TARGET":
        return {
            "seed": result["seed"],
            "ciav_outcome": result["ciav_outcome"],
            "truth_visible_binding_verified": True,
            "rows": rows,
            "production_correct": sum(x["production_correct"] for x in rows),
            "soft_memory_correct": sum(x["soft_memory_correct"] for x in rows),
            "actor_argmax_correct": sum(x["actor_argmax_correct"] for x in rows),
            "decision_disagreements": sum(
                x["production_choice"] != x["soft_memory_choice"] for x in rows
            ),
            "correction_status": "NO_LEGAL_CORRECTION_TARGET",
            "correction_targets": 0,
            "post_correction": None,
            "before_committed": len(result["before"]["committed_sources"]),
            "before_observed": len(result["before"]["observed_sources"]),
            "recovery_equal": None,
            "full_semantic_replay": None,
            "scope": "Readout diagnostic only; no eligible correction, recovery or replay claim.",
        }
    target = rows[-1]["true_habit_location"]
    post = {
        "production": result["after"],
        "soft_memory_reversible": result["memory_ablation_reversible_after"],
        "soft_memory_irreversible": result["memory_ablation_irreversible_after"],
    }
    return {
        "seed": result["seed"],
        "ciav_outcome": result.get("ciav_outcome", "legacy_different_location"),
        "truth_visible_binding_verified": True,
        "rows": rows,
        "production_correct": sum(x["production_correct"] for x in rows),
        "soft_memory_correct": sum(x["soft_memory_correct"] for x in rows),
        "actor_argmax_correct": sum(x["actor_argmax_correct"] for x in rows),
        "decision_disagreements": sum(
            x["production_choice"] != x["soft_memory_choice"] for x in rows
        ),
        "post_correction": {
            k: {"choice": v["argmax"], "correct_against_original_habit": v["argmax"] == target}
            for k, v in post.items()
        },
        "correction_targets": result["targets"],
        "actually_invalidated_day_indices": result["actually_invalidated_day_indices"],
        "before_committed": len(result["before"]["committed_sources"]),
        "after_committed": len(result["after"]["committed_sources"]),
        "before_observed": len(result["before"]["observed_sources"]),
        "after_observed": len(result["after"]["observed_sources"]),
        "production_action_changed": result["action_changed"],
        "production_distribution_max_change": max(
            abs(result["before"]["distribution"][k] - v)
            for k, v in result["after"]["distribution"].items()
        ),
        "recovery_equal": result["recovery_semantic_state_equal"],
        "full_semantic_replay": result["full_semantic_replay"],
        "scope": (
            "same inferred events, fixed unit-prior soft-count comparator, no retuning; "
            "argmax recommendation only. Forced correction is an administrative "
            "development intervention, not verified human truth. "
            "No habit switch or recurrence within this prefix."
        ),
    }


def components():
    import test_ccrr_context_conditioned_regime as regime
    import test_project_two_feedback_revision_loop as actor

    actor_rows = []
    for discriminating in (False, True):
        feedback = actor._search_found() if discriminating else actor._search_failed()
        extra = (
            {
                "actor_evidence": actor.ActorDiscriminationEvidence(
                    ratios={actor.OWNER: 0.2, actor.GUEST: 3.0},
                    model_version="actor-channel@0.1",
                    source_record_id=UUID(int=12345),
                )
            }
            if discriminating
            else {}
        )
        _, outcome = actor._loop().ingest_feedback(
            history=actor._history(),
            feedback=feedback,
            binding=actor._binding(feedback),
            likelihood_model=actor._likelihood(),
            owner_key=actor.OWNER,
            **extra,
        )
        before, after = (
            outcome.known_mechanism_actor_mass_before,
            outcome.known_mechanism_actor_mass_after,
        )
        prior_odds, posterior_odds = (
            before[actor.OWNER] / before[actor.GUEST],
            after[actor.OWNER] / after[actor.GUEST],
        )
        expected = prior_odds * (0.2 / 3 if discriminating else 1)
        actor_rows.append(
            {
                "actor_specific": discriminating,
                "owner_guest_odds_before": prior_odds,
                "owner_guest_odds_after": posterior_odds,
                "ordinary_bayes_expected_odds": expected,
                "absolute_difference": abs(expected - posterior_odds),
            }
        )
    regime_rows = []
    for name, snapshot, actor_id, cause, context in (
        (
            "habit_recurrence",
            regime._habit_change_snapshot(),
            regime.OWNER,
            regime.ChangeCause.HABIT,
            (1.0, 0.0),
        ),
        (
            "observation_change",
            regime._observation_change_snapshot(),
            regime.OWNER,
            regime.ChangeCause.HABIT,
            (0.0, 1.0),
        ),
        (
            "actor_change_owner",
            regime._actor_change_snapshot(),
            regime.OWNER,
            regime.ChangeCause.HABIT,
            (0.0, 1.0),
        ),
        (
            "guest_recurrence",
            regime._actor_change_snapshot(),
            regime.GUEST,
            regime.ChangeCause.ACTOR,
            (0.0, 1.0),
        ),
    ):
        reactor = regime.ContextConditionedRegimeReactivator()
        obj = UUID(int=1000)
        reactor.add_regime(
            regime.RegimeLibraryEntry(
                regime_id="old-stage",
                actor_id=actor_id,
                object_instance_id=obj,
                context_fingerprint=context,
                cause_origin=cause,
                created_at=regime.BASE,
            )
        )
        decision = reactor.decide(
            object_instance_id=obj,
            actor_id=actor_id,
            owner_actor_id=regime.OWNER,
            snapshot=snapshot,
            context_features=context,
            now=regime.BASE,
        )
        regime_rows.append(
            {
                "case": name,
                "kind": str(decision.kind),
                "decision_score": {str(k): v for k, v in decision.decision_score.items()},
                "reactivated_regime_id": decision.reactivated_regime_id,
            }
        )
    return {
        "actor": actor_rows,
        "regime": regime_rows,
        "scope": (
            "component fixtures, functional positive/negative paths only; "
            "no matched long-horizon action benefit"
        ),
    }


def run(inputs, output):
    if output.exists():
        raise ValueError("output must be new")
    cases = [score_case(load(path)) for path in inputs]
    result = {
        "schema": "paired-core-diagnostic@1",
        "tool_sha256": digest(Path(__file__)),
        "input_sha256": {str(p): digest(p) for p in inputs},
        "cases": cases,
        "total_step_recommendations": sum(len(c["rows"]) for c in cases),
        "production_correct": sum(c["production_correct"] for c in cases),
        "soft_memory_correct": sum(c["soft_memory_correct"] for c in cases),
        "actor_argmax_correct": sum(c["actor_argmax_correct"] for c in cases),
        "decision_disagreements": sum(c["decision_disagreements"] for c in cases),
        "components": components(),
        "scientific_gate_passed": False,
        "full_framework_acceptance": False,
    }
    save(output, result)
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("inputs", type=Path, nargs="+")
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    r = run(a.inputs, a.output)
    print(
        {
            k: r[k]
            for k in (
                "total_step_recommendations",
                "production_correct",
                "soft_memory_correct",
                "decision_disagreements",
            )
        }
    )
