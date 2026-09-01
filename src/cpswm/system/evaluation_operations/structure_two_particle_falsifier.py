"""Exact-enumeration conformance falsifier for the selected Structure Two method.

This finite synthetic world does not establish paper benefit.  It checks a
cheaper prerequisite: whether bounded typed-particle revision can track an
exact posterior under attribution ambiguity, delayed/contradictory feedback,
short regimes, and open-world actors.  A trained neural proposer is
deliberately absent; the corresponding arm remains fail-closed until a real
training artifact exists.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import asdict, dataclass
from enum import StrEnum
from itertools import product
from pathlib import Path
from statistics import mean
from typing import Any

from cpswm.system.evaluation_operations.structure_two_selected_method import (
    NeuralParticleProposal,
    OrderedActorRole,
    ParticleChangeCause,
    ParticleProposalOperation,
    ParticleRegimeDecision,
    ParticleRevisionReceipt,
    StructuredConstraint,
    StructuredWeightFactor,
    TypedParticleState,
    normalize_particle_revisions,
)
from cpswm.system.reproducibility import content_sha256, content_uuid

PROTOCOL_ID = "structure-two-exact-enumeration-falsifier@0.1"
UNRESOLVED_KEY = "__unresolved__"
UNRESOLVED_PRIOR = 0.02


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Mechanism(StrEnum):
    DIRECT = "direct"
    HANDOFF = "handoff"


class ActorPath(StrEnum):
    OWNER_OWNER = "owner_to_owner"
    GUEST_GUEST = "guest_to_guest"
    GUEST_OWNER = "guest_to_owner"
    OWNER_GUEST = "owner_to_guest"
    UNKNOWN_OWNER = "unknown_to_owner"
    UNKNOWN_GUEST = "unknown_to_guest"


class Identity(StrEnum):
    TARGET = "target_instance"
    DECOY = "decoy_instance"


class Cause(StrEnum):
    OBSERVATION = "observation"
    ACTOR = "actor"
    IDENTITY = "identity"
    HABIT = "habit"
    NOISE = "noise"


class Regime(StrEnum):
    OLD = "old_regime"
    NEW = "new_regime"
    REACTIVATED = "reactivated_regime"


class ActionLocation(StrEnum):
    DESK = "desk"
    CABINET = "cabinet"
    SHELF = "shelf"


class ApproximationMethod(StrEnum):
    INCREMENTAL_BEAM = "incremental_beam"
    FULL_RERUN_BEAM = "full_rerun_beam"
    BOOTSTRAP_PARTICLE_FILTER = "bootstrap_particle_filter"
    TYPED_PARTICLE_REVISION = "typed_particle_revision"


@dataclass(frozen=True, slots=True)
class LatentState:
    mechanism: Mechanism
    actor_path: ActorPath
    identity: Identity
    cause: Cause
    regime: Regime

    @property
    def key(self) -> str:
        return "|".join(
            (
                self.mechanism.value,
                self.actor_path.value,
                self.identity.value,
                self.cause.value,
                self.regime.value,
            )
        )

    @property
    def action_location(self) -> ActionLocation:
        return {
            Regime.OLD: ActionLocation.DESK,
            Regime.NEW: ActionLocation.CABINET,
            Regime.REACTIVATED: ActionLocation.SHELF,
        }[self.regime]


@dataclass(frozen=True, slots=True)
class EvidenceFrame:
    mechanism: Mechanism
    actor_path: ActorPath
    identity: Identity
    cause: Cause
    regime: Regime
    mechanism_reliability: float
    actor_reliability: float
    identity_reliability: float
    cause_reliability: float
    regime_reliability: float


@dataclass(frozen=True, slots=True)
class FalsifierScenario:
    scenario_id: str
    high_attribution_ambiguity: bool
    adverse_delayed_feedback: bool
    short_regime: bool
    open_world_actor: bool
    truth: LatentState
    frames: tuple[EvidenceFrame, EvidenceFrame]


@dataclass(frozen=True, slots=True)
class ApproximationResult:
    method: ApproximationMethod
    posterior: dict[str, float]
    support: frozenset[str]
    candidate_evaluations: int


def _opposite[T: StrEnum](value: T, values: tuple[T, ...]) -> T:
    return next(item for item in values if item is not value)


def enumerate_latent_states() -> tuple[LatentState, ...]:
    return tuple(
        LatentState(*values) for values in product(Mechanism, ActorPath, Identity, Cause, Regime)
    )


LATENT_STATES = enumerate_latent_states()
STATE_BY_KEY = {state.key: state for state in LATENT_STATES}


def _categorical_log_likelihood[T: StrEnum](observed: T, candidate: T, reliability: float) -> float:
    values = tuple(type(observed))
    if not 0.0 < reliability < 1.0:
        raise ValueError("evidence reliability must lie strictly between zero and one")
    probability = reliability if observed is candidate else (1.0 - reliability) / (len(values) - 1)
    return math.log(probability)


def _axis_prior(value: StrEnum) -> float:
    priors: dict[type[StrEnum], dict[StrEnum, float]] = {
        Mechanism: {Mechanism.DIRECT: 0.7, Mechanism.HANDOFF: 0.3},
        ActorPath: {
            ActorPath.OWNER_OWNER: 0.50,
            ActorPath.GUEST_GUEST: 0.12,
            ActorPath.GUEST_OWNER: 0.12,
            ActorPath.OWNER_GUEST: 0.10,
            ActorPath.UNKNOWN_OWNER: 0.08,
            ActorPath.UNKNOWN_GUEST: 0.08,
        },
        Identity: {Identity.TARGET: 0.8, Identity.DECOY: 0.2},
        Cause: {
            Cause.OBSERVATION: 0.15,
            Cause.ACTOR: 0.20,
            Cause.IDENTITY: 0.15,
            Cause.HABIT: 0.20,
            Cause.NOISE: 0.30,
        },
        Regime: {Regime.OLD: 0.60, Regime.NEW: 0.25, Regime.REACTIVATED: 0.15},
    }
    return priors[type(value)][value]


def _state_log_prior(state: LatentState) -> float:
    return math.log(1.0 - UNRESOLVED_PRIOR) + sum(
        math.log(_axis_prior(value))
        for value in (
            state.mechanism,
            state.actor_path,
            state.identity,
            state.cause,
            state.regime,
        )
    )


def _frame_log_likelihood(state: LatentState, frame: EvidenceFrame) -> float:
    return sum(
        (
            _categorical_log_likelihood(
                frame.mechanism, state.mechanism, frame.mechanism_reliability
            ),
            _categorical_log_likelihood(
                frame.actor_path, state.actor_path, frame.actor_reliability
            ),
            _categorical_log_likelihood(frame.identity, state.identity, frame.identity_reliability),
            _categorical_log_likelihood(frame.cause, state.cause, frame.cause_reliability),
            _categorical_log_likelihood(frame.regime, state.regime, frame.regime_reliability),
        )
    )


def _unresolved_log_target(frames: tuple[EvidenceFrame, ...]) -> float:
    axis_cardinalities = (
        len(Mechanism),
        len(ActorPath),
        len(Identity),
        len(Cause),
        len(Regime),
    )
    return math.log(UNRESOLVED_PRIOR) + len(frames) * sum(
        math.log(1.0 / size) for size in axis_cardinalities
    )


def _state_log_target(state: LatentState, frames: tuple[EvidenceFrame, ...]) -> float:
    return _state_log_prior(state) + sum(_frame_log_likelihood(state, frame) for frame in frames)


def _normalize_log_targets(
    targets: dict[str, float],
    *,
    unresolved_log_target: float,
) -> dict[str, float]:
    maximum = max(unresolved_log_target, *targets.values())
    masses = {key: math.exp(value - maximum) for key, value in targets.items()}
    unresolved_mass = math.exp(unresolved_log_target - maximum)
    denominator = unresolved_mass + sum(masses.values())
    posterior = {key: value / denominator for key, value in masses.items()}
    posterior[UNRESOLVED_KEY] = unresolved_mass / denominator
    return posterior


def exact_posterior(frames: tuple[EvidenceFrame, ...]) -> dict[str, float]:
    return _normalize_log_targets(
        {state.key: _state_log_target(state, frames) for state in LATENT_STATES},
        unresolved_log_target=_unresolved_log_target(frames),
    )


def _top_states(frames: tuple[EvidenceFrame, ...], budget: int) -> tuple[LatentState, ...]:
    return tuple(
        sorted(
            LATENT_STATES,
            key=lambda state: (-_state_log_target(state, frames), state.key),
        )[:budget]
    )


def _beam_result(
    scenario: FalsifierScenario,
    *,
    budget: int,
    full_rerun: bool,
) -> ApproximationResult:
    initial = _top_states((scenario.frames[0],), budget)
    candidates = _top_states(scenario.frames, budget) if full_rerun else initial
    posterior = _normalize_log_targets(
        {state.key: _state_log_target(state, scenario.frames) for state in candidates},
        unresolved_log_target=_unresolved_log_target(scenario.frames),
    )
    return ApproximationResult(
        method=(
            ApproximationMethod.FULL_RERUN_BEAM
            if full_rerun
            else ApproximationMethod.INCREMENTAL_BEAM
        ),
        posterior=posterior,
        support=frozenset(state.key for state in candidates),
        candidate_evaluations=len(LATENT_STATES) * (2 if full_rerun else 1) + len(candidates),
    )


def _sample_state_from_prior(rng: random.Random) -> LatentState:
    def sample_axis[T: StrEnum](values: tuple[T, ...]) -> T:
        weights = [_axis_prior(value) for value in values]
        return rng.choices(values, weights=weights, k=1)[0]

    return LatentState(
        mechanism=sample_axis(tuple(Mechanism)),
        actor_path=sample_axis(tuple(ActorPath)),
        identity=sample_axis(tuple(Identity)),
        cause=sample_axis(tuple(Cause)),
        regime=sample_axis(tuple(Regime)),
    )


def _bootstrap_particle_result(
    scenario: FalsifierScenario,
    *,
    budget: int,
    seed: int,
) -> ApproximationResult:
    rng = random.Random(f"{PROTOCOL_ID}:{scenario.scenario_id}:{seed}:bootstrap")
    sampled = tuple(_sample_state_from_prior(rng) for _ in range(budget))
    multiplicity: dict[str, int] = {}
    for state in sampled:
        multiplicity[state.key] = multiplicity.get(state.key, 0) + 1
    log_targets = {
        key: math.log(count / budget)
        + sum(_frame_log_likelihood(STATE_BY_KEY[key], frame) for frame in scenario.frames)
        for key, count in multiplicity.items()
    }
    posterior = _normalize_log_targets(
        log_targets,
        unresolved_log_target=_unresolved_log_target(scenario.frames),
    )
    return ApproximationResult(
        method=ApproximationMethod.BOOTSTRAP_PARTICLE_FILTER,
        posterior=posterior,
        support=frozenset(multiplicity),
        candidate_evaluations=budget * len(scenario.frames),
    )


def _neighbors(state: LatentState) -> tuple[LatentState, ...]:
    candidates = {state.key: state}
    axes: tuple[tuple[str, tuple[StrEnum, ...]], ...] = (
        ("mechanism", tuple(Mechanism)),
        ("actor_path", tuple(ActorPath)),
        ("identity", tuple(Identity)),
        ("cause", tuple(Cause)),
        ("regime", tuple(Regime)),
    )
    values = asdict(state)
    for field_name, alternatives in axes:
        for alternative in alternatives:
            if alternative is getattr(state, field_name):
                continue
            revised = LatentState(**{**values, field_name: alternative})
            candidates[revised.key] = revised
    return tuple(candidates[key] for key in sorted(candidates))


def _actor_roles(path: ActorPath) -> tuple[OrderedActorRole, ...]:
    pickup, placement = path.value.split("_to_", maxsplit=1)
    return (
        OrderedActorRole(role="pickup_actor", actor_key=pickup),
        OrderedActorRole(role="placement_actor", actor_key=placement),
    )


def _particle_change_cause(cause: Cause) -> ParticleChangeCause:
    return ParticleChangeCause(cause.value)


def _particle_regime(state: LatentState) -> tuple[ParticleRegimeDecision, str]:
    if state.regime is Regime.NEW and state.cause is Cause.HABIT:
        return ParticleRegimeDecision.CREATE, state.regime.value
    if state.regime is Regime.REACTIVATED and state.cause is Cause.HABIT:
        return ParticleRegimeDecision.REACTIVATE, state.regime.value
    return ParticleRegimeDecision.STAY, state.regime.value


def _accepted_constraints() -> tuple[StructuredConstraint, ...]:
    return tuple(
        StructuredConstraint(factor=factor, accepted=True, log_potential=0.0)
        for factor in (
            StructuredWeightFactor.PHYSICAL_EVENT_CONSTRAINT,
            StructuredWeightFactor.ORDERED_ROLE_CONSTRAINT,
            StructuredWeightFactor.IDENTITY_CONSTRAINT,
            StructuredWeightFactor.PROVENANCE_CONSTRAINT,
        )
    )


def _typed_particle_result(
    scenario: FalsifierScenario,
    *,
    budget: int,
) -> ApproximationResult:
    initial = _top_states((scenario.frames[0],), budget)
    pool_by_key: dict[str, LatentState] = {}
    parent_by_key: dict[str, LatentState] = {}
    for parent in initial:
        for candidate in _neighbors(parent):
            pool_by_key[candidate.key] = candidate
            parent_by_key.setdefault(candidate.key, parent)
    selected = tuple(
        sorted(
            pool_by_key.values(),
            key=lambda state: (-_state_log_target(state, scenario.frames), state.key),
        )[:budget]
    )
    snapshot_id = content_uuid("particle-falsifier-snapshot", scenario.scenario_id)
    cluster_id = content_uuid("particle-falsifier-cluster", scenario.scenario_id)
    receipts = []
    for state in selected:
        parent = parent_by_key[state.key]
        parent_id = content_uuid("particle-falsifier-parent", (scenario.scenario_id, parent.key))
        particle_id = content_uuid("particle-falsifier-particle", (scenario.scenario_id, state.key))
        regime_decision, regime_id = _particle_regime(state)
        typed_state = TypedParticleState(
            particle_id=particle_id,
            parent_particle_id=parent_id,
            source_snapshot_id=snapshot_id,
            event_hypothesis_id=content_uuid("particle-falsifier-event", state.key),
            revision_id=content_uuid(
                "particle-falsifier-revision", (scenario.scenario_id, state.key)
            ),
            parent_revision_id=content_uuid("particle-falsifier-parent-revision", parent.key),
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
                "particle-falsifier-proposal", (scenario.scenario_id, state.key)
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
            proposer_model_version="deterministic-structured-proposal@0.1",
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
    return ApproximationResult(
        method=ApproximationMethod.TYPED_PARTICLE_REVISION,
        posterior=posterior,
        support=frozenset(state.key for state in selected),
        candidate_evaluations=len(LATENT_STATES) + len(pool_by_key),
    )


def registered_scenarios() -> tuple[FalsifierScenario, ...]:
    scenarios = []
    causes = tuple(Cause)
    for index, (ambiguity, adverse, short, open_actor) in enumerate(
        product((False, True), repeat=4)
    ):
        mechanism = Mechanism.HANDOFF if ambiguity else Mechanism.DIRECT
        actor_path = (
            ActorPath.UNKNOWN_OWNER
            if open_actor
            else ActorPath.GUEST_OWNER
            if ambiguity
            else ActorPath.OWNER_OWNER
        )
        cause = causes[index % len(causes)]
        regime = Regime.REACTIVATED if short else Regime.NEW if adverse else Regime.OLD
        truth = LatentState(
            mechanism=mechanism,
            actor_path=actor_path,
            identity=Identity.TARGET,
            cause=cause,
            regime=regime,
        )
        initial = EvidenceFrame(
            mechanism=(Mechanism.DIRECT if ambiguity else mechanism),
            actor_path=(ActorPath.OWNER_OWNER if ambiguity or open_actor else actor_path),
            identity=(Identity.DECOY if adverse else Identity.TARGET),
            cause=(Cause.ACTOR if ambiguity and cause is Cause.HABIT else cause),
            regime=(Regime.OLD if short or adverse else regime),
            mechanism_reliability=(0.55 if ambiguity else 0.86),
            actor_reliability=(0.48 if ambiguity or open_actor else 0.84),
            identity_reliability=(0.62 if adverse else 0.90),
            cause_reliability=(0.58 if ambiguity else 0.82),
            regime_reliability=(0.55 if short or adverse else 0.84),
        )
        delayed = EvidenceFrame(
            mechanism=(_opposite(mechanism, tuple(Mechanism)) if adverse else mechanism),
            actor_path=actor_path,
            identity=Identity.TARGET,
            cause=(causes[(causes.index(cause) + 1) % len(causes)] if adverse else cause),
            regime=regime,
            mechanism_reliability=(0.62 if adverse else 0.90),
            actor_reliability=(0.68 if adverse else 0.90),
            identity_reliability=0.91,
            cause_reliability=(0.60 if adverse else 0.88),
            regime_reliability=(0.90 if short else 0.95),
        )
        scenarios.append(
            FalsifierScenario(
                scenario_id=f"e{index:02d}",
                high_attribution_ambiguity=ambiguity,
                adverse_delayed_feedback=adverse,
                short_regime=short,
                open_world_actor=open_actor,
                truth=truth,
                frames=(initial, delayed),
            )
        )
    return tuple(scenarios)


def _total_variation(exact: dict[str, float], approximate: dict[str, float]) -> float:
    keys = set(exact) | set(approximate)
    return 0.5 * sum(abs(exact.get(key, 0.0) - approximate.get(key, 0.0)) for key in keys)


def _action_marginal(posterior: dict[str, float]) -> dict[ActionLocation, float]:
    result = dict.fromkeys(ActionLocation, 0.0)
    for key, probability in posterior.items():
        if key == UNRESOLVED_KEY:
            for location in ActionLocation:
                result[location] += probability / len(ActionLocation)
        else:
            result[STATE_BY_KEY[key].action_location] += probability
    return result


def _action_regret(exact: dict[str, float], approximate: dict[str, float]) -> float:
    exact_marginal = _action_marginal(exact)
    approximate_marginal = _action_marginal(approximate)
    chosen = max(ActionLocation, key=lambda item: (approximate_marginal[item], item.value))
    optimal = max(ActionLocation, key=lambda item: (exact_marginal[item], item.value))
    return exact_marginal[optimal] - exact_marginal[chosen]


def _evaluate_result(
    scenario: FalsifierScenario,
    exact: dict[str, float],
    result: ApproximationResult,
) -> dict[str, Any]:
    exact_action = max(
        ActionLocation,
        key=lambda item: (_action_marginal(exact)[item], item.value),
    )
    approximate_action = max(
        ActionLocation,
        key=lambda item: (_action_marginal(result.posterior)[item], item.value),
    )
    return {
        "posterior_total_variation": _total_variation(exact, result.posterior),
        "truth_in_support": scenario.truth.key in result.support,
        "truth_posterior": result.posterior.get(scenario.truth.key, 0.0),
        "unresolved_probability": result.posterior.get(UNRESOLVED_KEY, 0.0),
        "action_regret_against_exact_bayes": _action_regret(exact, result.posterior),
        "exact_action": exact_action.value,
        "approximate_action": approximate_action.value,
        "action_matches_exact": exact_action is approximate_action,
        "candidate_evaluations": result.candidate_evaluations,
    }


def _summarize_readings(readings: list[dict[str, Any]]) -> dict[str, float]:
    return {
        "mean_posterior_total_variation": mean(
            row["posterior_total_variation"] for row in readings
        ),
        "truth_support_rate": mean(float(row["truth_in_support"]) for row in readings),
        "mean_truth_posterior": mean(row["truth_posterior"] for row in readings),
        "mean_action_regret_against_exact_bayes": mean(
            row["action_regret_against_exact_bayes"] for row in readings
        ),
        "action_match_rate": mean(float(row["action_matches_exact"]) for row in readings),
        "mean_candidate_evaluations": mean(row["candidate_evaluations"] for row in readings),
    }


def run_exact_enumeration_falsifier(
    *,
    particle_budget: int = 24,
    bootstrap_seed: int = 8701,
) -> dict[str, Any]:
    if particle_budget < 2 or particle_budget >= len(LATENT_STATES):
        raise ValueError("particle_budget must be between 2 and the exact state count")
    rows: dict[str, Any] = {}
    by_method: dict[ApproximationMethod, list[dict[str, Any]]] = {
        method: [] for method in ApproximationMethod
    }
    for scenario in registered_scenarios():
        exact = exact_posterior(scenario.frames)
        results = (
            _beam_result(scenario, budget=particle_budget, full_rerun=False),
            _beam_result(scenario, budget=particle_budget, full_rerun=True),
            _bootstrap_particle_result(
                scenario,
                budget=particle_budget,
                seed=bootstrap_seed,
            ),
            _typed_particle_result(scenario, budget=particle_budget),
        )
        method_rows = {}
        for result in results:
            reading = _evaluate_result(scenario, exact, result)
            method_rows[result.method.value] = reading
            by_method[result.method].append(reading)
        rows[scenario.scenario_id] = {
            "factors": {
                "high_attribution_ambiguity": scenario.high_attribution_ambiguity,
                "adverse_delayed_feedback": scenario.adverse_delayed_feedback,
                "short_regime": scenario.short_regime,
                "open_world_actor": scenario.open_world_actor,
            },
            "truth": asdict(scenario.truth),
            "exact_truth_posterior": exact[scenario.truth.key],
            "exact_unresolved_probability": exact[UNRESOLVED_KEY],
            "methods": method_rows,
        }

    summaries = {
        method.value: _summarize_readings(readings) for method, readings in by_method.items()
    }
    stress_summaries = {
        method.value: _summarize_readings(
            [
                rows[scenario.scenario_id]["methods"][method.value]
                for scenario in registered_scenarios()
                if scenario.high_attribution_ambiguity and scenario.adverse_delayed_feedback
            ]
        )
        for method in ApproximationMethod
    }
    typed = summaries[ApproximationMethod.TYPED_PARTICLE_REVISION.value]
    incremental = summaries[ApproximationMethod.INCREMENTAL_BEAM.value]
    full_rerun = summaries[ApproximationMethod.FULL_RERUN_BEAM.value]
    typed_stress = stress_summaries[ApproximationMethod.TYPED_PARTICLE_REVISION.value]
    incremental_stress = stress_summaries[ApproximationMethod.INCREMENTAL_BEAM.value]
    gates = {
        "typed_tv_not_worse_than_incremental_beam": (
            typed["mean_posterior_total_variation"] <= incremental["mean_posterior_total_variation"]
        ),
        "typed_action_regret_not_worse_than_incremental_beam": (
            typed["mean_action_regret_against_exact_bayes"]
            <= incremental["mean_action_regret_against_exact_bayes"]
        ),
        "typed_truth_support_not_worse_than_incremental_beam": (
            typed["truth_support_rate"] >= incremental["truth_support_rate"]
        ),
        "typed_within_0_05_tv_of_full_rerun_beam": (
            typed["mean_posterior_total_variation"]
            <= full_rerun["mean_posterior_total_variation"] + 0.05
        ),
        "typed_uses_fewer_candidate_evaluations_than_full_rerun_beam": (
            typed["mean_candidate_evaluations"] < full_rerun["mean_candidate_evaluations"]
        ),
        "typed_stress_tv_not_worse_than_incremental_beam": (
            typed_stress["mean_posterior_total_variation"]
            <= incremental_stress["mean_posterior_total_variation"]
        ),
        "typed_stress_action_regret_not_worse_than_incremental_beam": (
            typed_stress["mean_action_regret_against_exact_bayes"]
            <= incremental_stress["mean_action_regret_against_exact_bayes"]
        ),
    }
    repository_root = Path(__file__).resolve().parents[4]
    selected_method_source = repository_root / (
        "src/cpswm/system/evaluation_operations/structure_two_selected_method.py"
    )
    selected_method_receipt = repository_root / (
        "configs/project_two_experiments/structure_two_selected_method_v0_1.json"
    )
    protocol_document = repository_root / (
        "docs/experiments/structure_two_particle_exact_falsifier_protocol_2026-08-28.md"
    )
    report: dict[str, Any] = {
        "protocol": PROTOCOL_ID,
        "evidence_status": "finite synthetic conformance falsifier; not paper evidence",
        "selected_method_receipt_required": "structure-two-nap-rbtpr-rc@0.1",
        "neural_proposer_status": "not_run_no_trained_artifact",
        "state_count": len(LATENT_STATES),
        "scenario_count": len(registered_scenarios()),
        "particle_budget": particle_budget,
        "bootstrap_seed": bootstrap_seed,
        "same_visible_evidence": True,
        "same_particle_budget_for_approximate_methods": True,
        "provenance": {
            "falsifier_source_sha256": _file_sha256(Path(__file__).resolve()),
            "selected_method_source_sha256": _file_sha256(selected_method_source),
            "selected_method_receipt_file_sha256": _file_sha256(selected_method_receipt),
            "protocol_document_file_sha256": _file_sha256(protocol_document),
        },
        "scenarios": rows,
        "method_summaries": summaries,
        "high_ambiguity_adverse_feedback_summaries": stress_summaries,
        "development_gates": gates,
        "all_development_gates_passed": all(gates.values()),
        "limitations": [
            "finite hand-authored likelihood model",
            "deterministic structured proposal is not a trained neural amortized proposer",
            "no RGB-D, household, or robot execution evidence",
            "gate thresholds are development diagnostics, not confirmatory margins",
        ],
    }
    report["content_sha256"] = content_sha256(report)
    return report


def write_exact_enumeration_report(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


__all__ = [
    "PROTOCOL_ID",
    "ActionLocation",
    "ActorPath",
    "ApproximationMethod",
    "ApproximationResult",
    "Cause",
    "EvidenceFrame",
    "FalsifierScenario",
    "Identity",
    "LatentState",
    "Mechanism",
    "Regime",
    "enumerate_latent_states",
    "exact_posterior",
    "registered_scenarios",
    "run_exact_enumeration_falsifier",
    "write_exact_enumeration_report",
]
