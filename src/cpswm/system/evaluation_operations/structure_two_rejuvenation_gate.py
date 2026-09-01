"""Preregistered v0.2 gate for structured joint typed-particle rejuvenation."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Any

from cpswm.system.evaluation_operations.structure_two_particle_falsifier import (
    LATENT_STATES,
    UNRESOLVED_KEY,
    ActorPath,
    ApproximationMethod,
    ApproximationResult,
    FalsifierScenario,
    LatentState,
    Mechanism,
    _accepted_constraints,
    _actor_roles,
    _beam_result,
    _evaluate_result,
    _frame_log_likelihood,
    _neighbors,
    _particle_change_cause,
    _particle_regime,
    _state_log_prior,
    _state_log_target,
    _summarize_readings,
    _top_states,
    _typed_particle_result,
    _unresolved_log_target,
    exact_posterior,
    registered_scenarios,
)
from cpswm.system.evaluation_operations.structure_two_selected_method import (
    NeuralParticleProposal,
    ParticleProposalOperation,
    ParticleRevisionReceipt,
    TypedParticleState,
    normalize_particle_revisions,
)
from cpswm.system.reproducibility import content_sha256, content_uuid

PROTOCOL_ID = "structure-two-structured-rejuvenation-gate@0.2"
FROZEN_PARTICLE_BUDGET = 24


class RejuvenationMethod(StrEnum):
    SINGLE_FIELD = "single_field_typed_revision"
    STRUCTURED_JOINT = "structured_joint_typed_revision"
    FULL_RERUN = "full_rerun_beam"


@dataclass(frozen=True, slots=True)
class JointProposalPool:
    states: tuple[LatentState, ...]
    parent_by_key: dict[str, LatentState]
    families_by_key: dict[str, frozenset[str]]


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _add_candidate(
    states: dict[str, LatentState],
    parents: dict[str, LatentState],
    families: dict[str, set[str]],
    *,
    state: LatentState,
    parent: LatentState,
    family: str,
) -> None:
    states[state.key] = state
    parents.setdefault(state.key, parent)
    families.setdefault(state.key, set()).add(family)


def structured_joint_pool(scenario: FalsifierScenario, *, budget: int) -> JointProposalPool:
    """Build the preregistered role-chain and paired-field proposal pool."""

    initial = _top_states((scenario.frames[0],), budget)
    delayed = scenario.frames[1]
    states: dict[str, LatentState] = {}
    parents: dict[str, LatentState] = {}
    families: dict[str, set[str]] = {}
    for parent in initial:
        parent_values = asdict(parent)
        for candidate in _neighbors(parent):
            _add_candidate(
                states,
                parents,
                families,
                state=candidate,
                parent=parent,
                family="single_field",
            )

        observed_role_chain = LatentState(
            **{
                **parent_values,
                "mechanism": delayed.mechanism,
                "actor_path": delayed.actor_path,
            }
        )
        _add_candidate(
            states,
            parents,
            families,
            state=observed_role_chain,
            parent=parent,
            family="mechanism_actor_observed_pair",
        )
        if delayed.actor_path is not ActorPath.OWNER_OWNER:
            physical_role_chain = LatentState(
                **{
                    **parent_values,
                    "mechanism": Mechanism.HANDOFF,
                    "actor_path": delayed.actor_path,
                }
            )
            _add_candidate(
                states,
                parents,
                families,
                state=physical_role_chain,
                parent=parent,
                family="mechanism_actor_physical_role_chain",
            )

        for cause in (parent.cause, delayed.cause):
            cause_regime = LatentState(
                **{**parent_values, "cause": cause, "regime": delayed.regime}
            )
            _add_candidate(
                states,
                parents,
                families,
                state=cause_regime,
                parent=parent,
                family="cause_regime_pair",
            )

        for cause in (parent.cause, delayed.cause):
            identity_cause = LatentState(
                **{**parent_values, "identity": delayed.identity, "cause": cause}
            )
            _add_candidate(
                states,
                parents,
                families,
                state=identity_cause,
                parent=parent,
                family="identity_cause_pair",
            )

    return JointProposalPool(
        states=tuple(states[key] for key in sorted(states)),
        parent_by_key=parents,
        families_by_key={key: frozenset(value) for key, value in families.items()},
    )


def _structured_joint_result(
    scenario: FalsifierScenario,
    *,
    budget: int,
) -> tuple[ApproximationResult, dict[str, int]]:
    pool = structured_joint_pool(scenario, budget=budget)
    selected = tuple(
        sorted(
            pool.states,
            key=lambda state: (-_state_log_target(state, scenario.frames), state.key),
        )[:budget]
    )
    snapshot_id = content_uuid("joint-rejuvenation-snapshot", scenario.scenario_id)
    cluster_id = content_uuid("joint-rejuvenation-cluster", scenario.scenario_id)
    receipts = []
    for state in selected:
        parent = pool.parent_by_key[state.key]
        parent_id = content_uuid("joint-rejuvenation-parent", (scenario.scenario_id, parent.key))
        regime_decision, regime_id = _particle_regime(state)
        typed_state = TypedParticleState(
            particle_id=content_uuid(
                "joint-rejuvenation-particle", (scenario.scenario_id, state.key)
            ),
            parent_particle_id=parent_id,
            source_snapshot_id=snapshot_id,
            event_hypothesis_id=content_uuid("joint-rejuvenation-event", state.key),
            revision_id=content_uuid(
                "joint-rejuvenation-revision", (scenario.scenario_id, state.key)
            ),
            parent_revision_id=content_uuid("joint-rejuvenation-parent-revision", parent.key),
            ordered_actor_roles=_actor_roles(state.actor_path),
            instance_association_key=state.identity.value,
            change_cause=_particle_change_cause(state.cause),
            regime_decision=regime_decision,
            regime_id=regime_id,
            run_length=(1 if scenario.short_regime else 4),
            statistic_state_ref=f"analytic-state:{state.key}",
            ledger_lineage_ref=f"lineage:{parent.key}",
        )
        proposal = NeuralParticleProposal(
            proposal_id=content_uuid(
                "joint-rejuvenation-proposal", (scenario.scenario_id, state.key)
            ),
            evidence_cluster_id=cluster_id,
            operation=(
                ParticleProposalOperation.REVISE
                if state.key == parent.key
                else ParticleProposalOperation.REJUVENATE
            ),
            source_particle_id=parent_id,
            source_snapshot_id=snapshot_id,
            proposed_state=typed_state,
            proposal_log_probability=-math.log(len(selected)),
            proposer_model_version="deterministic-structured-joint-proposal@0.2",
            proposer_code_version=PROTOCOL_ID,
        )
        receipts.append(
            ParticleRevisionReceipt(
                proposal=proposal,
                prior_log_weight=_state_log_prior(state),
                transition_log_probability=0.0,
                observation_log_likelihood=sum(
                    _frame_log_likelihood(state, frame) for frame in scenario.frames
                ),
                constraints=_accepted_constraints(),
            )
        )
    batch = normalize_particle_revisions(
        tuple(receipts),
        unresolved_log_weight=_unresolved_log_target(scenario.frames) + math.log(len(selected)),
    )
    posterior = {
        selected[index].key: weight.posterior_probability
        for index, weight in enumerate(batch.particle_weights)
    }
    posterior[UNRESOLVED_KEY] = batch.unresolved_probability
    selected_family_counts: dict[str, int] = {}
    for state in selected:
        for family in pool.families_by_key[state.key]:
            selected_family_counts[family] = selected_family_counts.get(family, 0) + 1
    result = ApproximationResult(
        method=ApproximationMethod.TYPED_PARTICLE_REVISION,
        posterior=posterior,
        support=frozenset(state.key for state in selected),
        candidate_evaluations=len(LATENT_STATES) + len(pool.states) + len(selected),
    )
    return result, selected_family_counts


def run_structured_rejuvenation_gate(*, particle_budget: int = 24) -> dict[str, Any]:
    if particle_budget != FROZEN_PARTICLE_BUDGET:
        raise ValueError(f"{PROTOCOL_ID} freezes particle_budget={FROZEN_PARTICLE_BUDGET}")
    rows: dict[str, Any] = {}
    readings: dict[RejuvenationMethod, list[dict[str, Any]]] = {
        method: [] for method in RejuvenationMethod
    }
    for scenario in registered_scenarios():
        exact = exact_posterior(scenario.frames)
        single = _typed_particle_result(scenario, budget=particle_budget)
        # v0.1 counted candidate scoring but omitted the final K receipt-weight
        # evaluations.  Add them here so all three v0.2 arms use the same
        # accounting boundary without mutating the frozen v0.1 source.
        single = replace(
            single,
            candidate_evaluations=single.candidate_evaluations + particle_budget,
        )
        joint, family_counts = _structured_joint_result(scenario, budget=particle_budget)
        full = _beam_result(scenario, budget=particle_budget, full_rerun=True)
        method_results = {
            RejuvenationMethod.SINGLE_FIELD: single,
            RejuvenationMethod.STRUCTURED_JOINT: joint,
            RejuvenationMethod.FULL_RERUN: full,
        }
        method_rows = {}
        for method, approximation in method_results.items():
            reading = _evaluate_result(scenario, exact, approximation)
            readings[method].append(reading)
            method_rows[method.value] = reading
        rows[scenario.scenario_id] = {
            "factors": {
                "high_attribution_ambiguity": scenario.high_attribution_ambiguity,
                "adverse_delayed_feedback": scenario.adverse_delayed_feedback,
                "short_regime": scenario.short_regime,
                "open_world_actor": scenario.open_world_actor,
            },
            "truth": asdict(scenario.truth),
            "structured_joint_selected_family_counts": family_counts,
            "methods": method_rows,
        }

    summaries = {method.value: _summarize_readings(values) for method, values in readings.items()}
    stress_summaries = {
        method.value: _summarize_readings(
            [
                rows[scenario.scenario_id]["methods"][method.value]
                for scenario in registered_scenarios()
                if scenario.high_attribution_ambiguity and scenario.adverse_delayed_feedback
            ]
        )
        for method in RejuvenationMethod
    }
    single_summary = summaries[RejuvenationMethod.SINGLE_FIELD.value]
    joint_summary = summaries[RejuvenationMethod.STRUCTURED_JOINT.value]
    full_summary = summaries[RejuvenationMethod.FULL_RERUN.value]
    single_stress = stress_summaries[RejuvenationMethod.SINGLE_FIELD.value]
    joint_stress = stress_summaries[RejuvenationMethod.STRUCTURED_JOINT.value]
    full_stress = stress_summaries[RejuvenationMethod.FULL_RERUN.value]
    gates = {
        "stress_truth_support_not_below_single_field": (
            joint_stress["truth_support_rate"] >= single_stress["truth_support_rate"]
        ),
        "stress_truth_support_reaches_full_rerun": (
            joint_stress["truth_support_rate"] >= full_stress["truth_support_rate"]
        ),
        "stress_tv_not_above_single_field": (
            joint_stress["mean_posterior_total_variation"]
            <= single_stress["mean_posterior_total_variation"]
        ),
        "stress_action_regret_not_above_single_field": (
            joint_stress["mean_action_regret_against_exact_bayes"]
            <= single_stress["mean_action_regret_against_exact_bayes"]
        ),
        "overall_tv_not_above_single_field": (
            joint_summary["mean_posterior_total_variation"]
            <= single_summary["mean_posterior_total_variation"]
        ),
        "overall_truth_support_not_below_single_field": (
            joint_summary["truth_support_rate"] >= single_summary["truth_support_rate"]
        ),
        "candidate_evaluations_at_most_90_percent_of_full_rerun": (
            joint_summary["mean_candidate_evaluations"]
            <= 0.90 * full_summary["mean_candidate_evaluations"]
        ),
    }
    repository_root = Path(__file__).resolve().parents[4]
    provenance_paths = {
        "gate_source_sha256": Path(__file__).resolve(),
        "v0_1_falsifier_source_sha256": repository_root
        / "src/cpswm/system/evaluation_operations/structure_two_particle_falsifier.py",
        "selected_method_source_sha256": repository_root
        / "src/cpswm/system/evaluation_operations/structure_two_selected_method.py",
        "selected_method_receipt_file_sha256": repository_root
        / "configs/project_two_experiments/structure_two_selected_method_v0_1.json",
        "protocol_document_file_sha256": repository_root
        / "docs/experiments/structure_two_structured_rejuvenation_gate_protocol_2026-08-28.md",
    }
    report: dict[str, Any] = {
        "protocol": PROTOCOL_ID,
        "evidence_status": "finite synthetic blocking gate; not paper evidence",
        "selected_method_receipt_required": "structure-two-nap-rbtpr-rc@0.1",
        "neural_proposer_status": "not_run_no_frozen_training_artifact",
        "scope_status": "all_seven_operators_retained_not_evaluated_by_this_local_gate",
        "registration_status": (
            "repository_local_protocol_written_before_recorded_run; "
            "no_independent_timestamp_authority"
        ),
        "development_contamination_status": (
            "kernel_designed_after_v0_1_failure_on_same_scenario_family"
        ),
        "action_readout_status": (
            "regime_only_and_non_discriminative_for_mechanism_actor_identity_cause_repairs"
        ),
        "cost_metric_status": (
            "analytic_state_score_evaluations_only; excludes proposal_generation_contract_"
            "validation_and_runtime_cost"
        ),
        "state_count": len(LATENT_STATES),
        "scenario_count": len(registered_scenarios()),
        "particle_budget": particle_budget,
        "stress_subset_definition": {
            "high_attribution_ambiguity": True,
            "adverse_delayed_feedback": True,
        },
        "same_visible_evidence": True,
        "same_particle_budget": True,
        "provenance": {key: _file_sha256(path) for key, path in provenance_paths.items()},
        "scenarios": rows,
        "method_summaries": summaries,
        "stress_summaries": stress_summaries,
        "preregistered_blocking_gates": gates,
        "all_preregistered_blocking_gates_passed": all(gates.values()),
        "limitations": [
            "finite hand-authored likelihood model",
            "deterministic joint proposal is not a trained neural amortized proposer",
            "same scenario family informed kernel design, so this is development evidence",
            "action readout consumes regime only and cannot validate the other repaired axes",
            "no corrected AMG action-level comparison in this local gate",
            "no RGB-D, household, or robot execution evidence",
        ],
        "next_gate_requirements": [
            "freeze fresh scenario families or sealed seeds before evaluation",
            "use action readouts that consume actor identity cause and regime where relevant",
            "compare corrected AMG old full system and full system plus joint revision",
            "use net action loss as the primary endpoint",
        ],
    }
    report["content_sha256"] = content_sha256(report)
    return report


def write_structured_rejuvenation_report(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def verify_structured_rejuvenation_report(report_path: Path) -> dict[str, Any]:
    """Fail closed unless an artifact exactly matches deterministic recomputation."""

    try:
        stored = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("structured rejuvenation report is unreadable") from error
    if not isinstance(stored, dict):
        raise ValueError("structured rejuvenation report must be a JSON object")
    stored_hash = stored.get("content_sha256")
    unsigned = dict(stored)
    unsigned.pop("content_sha256", None)
    if not isinstance(stored_hash, str) or content_sha256(unsigned) != stored_hash:
        raise ValueError("structured rejuvenation report content hash mismatch")
    budget = stored.get("particle_budget")
    if not isinstance(budget, int):
        raise ValueError("structured rejuvenation report particle budget is invalid")
    expected = run_structured_rejuvenation_gate(particle_budget=budget)
    if stored != expected:
        raise ValueError("structured rejuvenation report differs from deterministic recomputation")
    return stored


__all__ = [
    "FROZEN_PARTICLE_BUDGET",
    "PROTOCOL_ID",
    "RejuvenationMethod",
    "run_structured_rejuvenation_gate",
    "structured_joint_pool",
    "verify_structured_rejuvenation_report",
    "write_structured_rejuvenation_report",
]
