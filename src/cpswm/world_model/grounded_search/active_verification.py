"""Expected-information-gain observation selection baseline."""

from __future__ import annotations

from enum import StrEnum
from math import isclose, isfinite, log2
from random import Random
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import Field, field_validator, model_validator

from cpswm.contracts.base import ContractModel, Probability
from cpswm.contracts.grounded_search import (
    ActiveObservationPlan,
    ObservationActionCandidate,
    ObservationActionScore,
    ObservationPlannerObjective,
)
from cpswm.system.reproducibility import content_sha256
from cpswm.world_model.habits_transitions.cause_factorized_bocpd import ChangeCause
from cpswm.world_model.habits_transitions.joint_cause_bocpd import JointCauseSnapshot


def _entropy(probabilities: list[float]) -> float:
    return -sum(value * log2(value) for value in probabilities if value > 0.0)


class InformationGainPlanner:
    """Rank observation actions by expected entropy reduction minus costs."""

    def __init__(
        self,
        *,
        information_value_weight: float = 1.0,
        motion_cost_weight: float = 1.0,
        time_cost_weight: float = 1.0,
        interruption_cost_weight: float = 1.0,
        privacy_cost_weight: float = 1.0,
        safety_cost_weight: float = 1.0,
    ) -> None:
        self.information_value_weight = information_value_weight
        self.motion_cost_weight = motion_cost_weight
        self.time_cost_weight = time_cost_weight
        self.interruption_cost_weight = interruption_cost_weight
        self.privacy_cost_weight = privacy_cost_weight
        self.safety_cost_weight = safety_cost_weight

    def select(
        self,
        prior: dict[UUID, float],
        actions: tuple[ObservationActionCandidate, ...],
        *,
        minimum_net_value: float = 0.0,
    ) -> ActiveObservationPlan:
        if not actions:
            return ActiveObservationPlan(
                scores=(), should_act=False, stop_reason="no_candidate_observation_action"
            )
        if abs(sum(prior.values()) - 1.0) > 1e-6:
            raise ValueError("prior must sum to one")

        prior_entropy = _entropy(list(prior.values()))
        scores: list[ObservationActionScore] = []
        for action in actions:
            action_hypotheses = set(next(iter(action.outcome_likelihoods.values())))
            if action_hypotheses != set(prior):
                raise ValueError(
                    "every observation action must score exactly the current hypotheses"
                )
            expected_entropy = 0.0
            for likelihoods in action.outcome_likelihoods.values():
                p_outcome = sum(
                    prior[hypothesis_id] * likelihood
                    for hypothesis_id, likelihood in likelihoods.items()
                )
                if p_outcome <= 0.0:
                    continue
                posterior = [
                    prior[hypothesis_id] * likelihood / p_outcome
                    for hypothesis_id, likelihood in likelihoods.items()
                ]
                expected_entropy += p_outcome * _entropy(posterior)
            information_gain = max(0.0, prior_entropy - expected_entropy)
            total_cost = (
                self.motion_cost_weight * action.motion_cost
                + self.time_cost_weight * action.time_cost
                + self.interruption_cost_weight * action.interruption_cost
                + self.privacy_cost_weight * action.privacy_cost
                + self.safety_cost_weight * action.safety_cost
            )
            scores.append(
                ObservationActionScore(
                    action_id=action.action_id,
                    expected_information_gain=information_gain,
                    expected_posterior_entropy=expected_entropy,
                    total_cost=total_cost,
                    net_value=self.information_value_weight * information_gain - total_cost,
                )
            )

        ranked = tuple(sorted(scores, key=lambda item: item.net_value, reverse=True))
        best = ranked[0]
        if best.net_value <= minimum_net_value:
            return ActiveObservationPlan(
                scores=ranked,
                should_act=False,
                stop_reason="no_observation_has_positive_net_information_value",
            )
        return ActiveObservationPlan(
            selected_action_id=best.action_id,
            scores=ranked,
            should_act=True,
            stop_reason="selected_maximum_net_information_value",
        )


class ActionUtilityPlanner:
    """Select verification by expected downstream decision utility minus costs."""

    def __init__(
        self,
        *,
        motion_cost_weight: float = 1.0,
        time_cost_weight: float = 1.0,
        interruption_cost_weight: float = 1.0,
        privacy_cost_weight: float = 1.0,
        safety_cost_weight: float = 1.0,
    ) -> None:
        weights = (
            motion_cost_weight,
            time_cost_weight,
            interruption_cost_weight,
            privacy_cost_weight,
            safety_cost_weight,
        )
        if any(weight < 0.0 for weight in weights):
            raise ValueError("utility planner cost weights must be non-negative")
        self.motion_cost_weight = motion_cost_weight
        self.time_cost_weight = time_cost_weight
        self.interruption_cost_weight = interruption_cost_weight
        self.privacy_cost_weight = privacy_cost_weight
        self.safety_cost_weight = safety_cost_weight

    def select(
        self,
        prior: dict[UUID, float],
        actions: tuple[ObservationActionCandidate, ...],
        *,
        terminal_decision_utilities: dict[UUID, dict[UUID, float]],
        minimum_net_utility: float = 0.0,
    ) -> ActiveObservationPlan:
        """Maximize expected value of sample information under explicit costs.

        ``terminal_decision_utilities[d][h]`` is the utility of taking terminal
        decision ``d`` when hypothesis ``h`` is true. This makes retrieval gain,
        abstention, and task failure costs explicit instead of using entropy as
        a proxy for usefulness.
        """

        if not prior or abs(sum(prior.values()) - 1.0) > 1e-6:
            raise ValueError("prior must be non-empty and sum to one")
        hypothesis_ids = set(prior)
        if not terminal_decision_utilities:
            raise ValueError("terminal_decision_utilities cannot be empty")
        if any(set(row) != hypothesis_ids for row in terminal_decision_utilities.values()):
            raise ValueError("every terminal decision must score all current hypotheses")
        if any(
            not isfinite(utility)
            for row in terminal_decision_utilities.values()
            for utility in row.values()
        ):
            raise ValueError("terminal decision utilities must be finite")
        if not actions:
            return ActiveObservationPlan(
                scores=(), should_act=False, stop_reason="no_candidate_observation_action"
            )

        baseline_decision, baseline_utility = self._best_terminal_decision(
            prior,
            terminal_decision_utilities,
        )
        del baseline_decision
        scores: list[ObservationActionScore] = []
        prior_entropy = _entropy(list(prior.values()))
        for action in actions:
            action_hypotheses = set(next(iter(action.outcome_likelihoods.values())))
            if action_hypotheses != hypothesis_ids:
                raise ValueError(
                    "every observation action must score exactly the current hypotheses"
                )
            expected_entropy = 0.0
            expected_decision_utility = 0.0
            decisions_by_outcome: dict[str, UUID] = {}
            for outcome, likelihoods in action.outcome_likelihoods.items():
                p_outcome = sum(
                    prior[hypothesis_id] * likelihood
                    for hypothesis_id, likelihood in likelihoods.items()
                )
                if p_outcome <= 0.0:
                    continue
                posterior = {
                    hypothesis_id: prior[hypothesis_id] * likelihood / p_outcome
                    for hypothesis_id, likelihood in likelihoods.items()
                }
                expected_entropy += p_outcome * _entropy(list(posterior.values()))
                decision_id, outcome_utility = self._best_terminal_decision(
                    posterior,
                    terminal_decision_utilities,
                )
                decisions_by_outcome[outcome] = decision_id
                expected_decision_utility += p_outcome * outcome_utility

            expected_gain = max(0.0, expected_decision_utility - baseline_utility)
            total_cost = self._total_cost(action)
            scores.append(
                ObservationActionScore(
                    action_id=action.action_id,
                    expected_information_gain=max(0.0, prior_entropy - expected_entropy),
                    expected_posterior_entropy=expected_entropy,
                    total_cost=total_cost,
                    net_value=expected_gain - total_cost,
                    objective=ObservationPlannerObjective.DECISION_UTILITY,
                    baseline_decision_utility=baseline_utility,
                    expected_decision_utility=expected_decision_utility,
                    expected_utility_gain=expected_gain,
                    recommended_terminal_decision_by_outcome=decisions_by_outcome,
                )
            )

        ranked = tuple(sorted(scores, key=lambda score: (-score.net_value, str(score.action_id))))
        best = ranked[0]
        if best.net_value <= minimum_net_utility:
            return ActiveObservationPlan(
                scores=ranked,
                should_act=False,
                stop_reason="no_observation_has_positive_net_decision_utility",
            )
        return ActiveObservationPlan(
            selected_action_id=best.action_id,
            scores=ranked,
            should_act=True,
            stop_reason="selected_maximum_net_decision_utility",
        )

    def _total_cost(self, action: ObservationActionCandidate) -> float:
        return (
            self.motion_cost_weight * action.motion_cost
            + self.time_cost_weight * action.time_cost
            + self.interruption_cost_weight * action.interruption_cost
            + self.privacy_cost_weight * action.privacy_cost
            + self.safety_cost_weight * action.safety_cost
        )

    @staticmethod
    def _best_terminal_decision(
        posterior: dict[UUID, float],
        utilities: dict[UUID, dict[UUID, float]],
    ) -> tuple[UUID, float]:
        scored = {
            decision_id: sum(
                posterior[hypothesis_id] * utility
                for hypothesis_id, utility in utility_by_hypothesis.items()
            )
            for decision_id, utility_by_hypothesis in utilities.items()
        }
        decision_id = sorted(scored, key=lambda item: (-scored[item], str(item)))[0]
        return decision_id, scored[decision_id]


class VerificationCause(StrEnum):
    OBSERVATION = "observation"
    ACTOR = "actor"
    IDENTITY = "identity"
    HABIT = "habit"
    NOISE = "noise"
    UNRESOLVED = "unresolved"


def verification_cause_hypothesis_id(cause: VerificationCause) -> UUID:
    return uuid5(NAMESPACE_URL, f"cpswm:structure-two:verification-cause:{cause.value}")


def _joint_cause_snapshot_payload(snapshot: JointCauseSnapshot) -> dict[str, object]:
    """Canonicalize mappings whose tuple/frozenset keys are not JSON-native."""

    def cause_set(causes: frozenset[ChangeCause]) -> tuple[str, ...]:
        return tuple(sorted(cause.value for cause in causes))

    return {
        "timestamp": snapshot.timestamp,
        "joint_run_length_cause_posterior": tuple(
            sorted(
                (run_length, cause.value, probability)
                for (run_length, cause), probability in (
                    snapshot.joint_run_length_cause_posterior.items()
                )
            )
        ),
        "joint_run_length_cause_set_posterior": tuple(
            sorted(
                (run_length, cause_set(causes), probability)
                for (run_length, causes), probability in (
                    snapshot.joint_run_length_cause_set_posterior.items()
                )
            )
        ),
        "continue_probability": snapshot.continue_probability,
        "segment_change_probability": snapshot.segment_change_probability,
        "segment_cause_posterior": tuple(
            sorted(
                (cause.value, value) for cause, value in snapshot.segment_cause_posterior.items()
            )
        ),
        "segment_cause_set_posterior": tuple(
            sorted(
                (cause_set(causes), value)
                for causes, value in snapshot.segment_cause_set_posterior.items()
            )
        ),
        "active_regime_cause_set_posterior": tuple(
            sorted(
                (cause_set(causes), value)
                for causes, value in snapshot.active_regime_cause_set_posterior.items()
            )
        ),
        "active_regime_cause_posterior": tuple(
            sorted(
                (cause.value, value)
                for cause, value in snapshot.active_regime_cause_posterior.items()
            )
        ),
        "transient_noise_probability": snapshot.transient_noise_probability,
        "block_reference": tuple(
            sorted((cause.value, value) for cause, value in snapshot.block_reference.items())
        ),
        "beam_size": snapshot.beam_size,
    }


class StructureTwoCauseBelief(ContractModel):
    """CIAV-facing cause posterior derived from CF-BOCPD plus identity uncertainty."""

    posterior: dict[VerificationCause, Probability]
    source_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_posterior(self) -> StructureTwoCauseBelief:
        if set(self.posterior) != set(VerificationCause):
            raise ValueError("CIAV cause posterior must cover every cause including unresolved")
        if not isclose(sum(self.posterior.values()), 1.0, rel_tol=0.0, abs_tol=1e-6):
            raise ValueError("CIAV cause posterior must sum to one")
        return self

    @classmethod
    def from_snapshot(
        cls,
        snapshot: JointCauseSnapshot,
        *,
        identity_switch_probability: float,
    ) -> StructureTwoCauseBelief:
        if not 0.0 <= identity_switch_probability <= 1.0:
            raise ValueError("identity_switch_probability must lie in [0, 1]")
        base = dict.fromkeys(VerificationCause, 0.0)
        base[VerificationCause.NOISE] = snapshot.transient_noise_probability
        base[VerificationCause.UNRESOLVED] = snapshot.continue_probability
        mapped = {
            ChangeCause.OBSERVATION: VerificationCause.OBSERVATION,
            ChangeCause.ACTOR: VerificationCause.ACTOR,
            ChangeCause.HABIT: VerificationCause.HABIT,
        }
        for causes, probability in snapshot.segment_cause_set_posterior.items():
            if not causes:
                base[VerificationCause.UNRESOLVED] += (
                    snapshot.segment_change_probability * probability
                )
                continue
            share = snapshot.segment_change_probability * probability / len(causes)
            for cause in causes:
                target = mapped.get(cause)
                if target is not None:
                    base[target] += share
        posterior = {
            cause: value * (1.0 - identity_switch_probability) for cause, value in base.items()
        }
        posterior[VerificationCause.IDENTITY] = identity_switch_probability
        total = sum(posterior.values())
        if total <= 0.0:
            raise ValueError("CF-BOCPD snapshot produced no CIAV cause mass")
        normalized = {cause: value / total for cause, value in posterior.items()}
        return cls(
            posterior=normalized,
            source_snapshot_sha256=content_sha256(_joint_cause_snapshot_payload(snapshot)),
        )

    def as_uuid_prior(self) -> dict[UUID, float]:
        return {
            verification_cause_hypothesis_id(cause): probability
            for cause, probability in self.posterior.items()
        }


class JointParticleVerificationBelief(ContractModel):
    """Full particle atoms for EVSI; cause entropy remains a cause marginal.

    Atom IDs name complete joint states, not independent marginal combinations.
    The snapshot digest is a content binding, not a producer/commit authority.
    Callers must bind outcome/utility tables to this exact snapshot before use.
    """

    posterior: dict[UUID, Probability]
    cause_by_atom: dict[UUID, VerificationCause]
    source_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_joint(self) -> JointParticleVerificationBelief:
        if not self.posterior or set(self.posterior) != set(self.cause_by_atom):
            raise ValueError("joint CIAV requires one cause label per complete particle atom")
        if not isclose(sum(self.posterior.values()), 1.0, rel_tol=0.0, abs_tol=1e-6):
            raise ValueError("joint CIAV probabilities must sum to one")
        return self

    def as_uuid_prior(self) -> dict[UUID, float]:
        return dict(self.posterior)

    def cause_marginal(self, posterior: dict[UUID, float]) -> dict[VerificationCause, float]:
        result = dict.fromkeys(VerificationCause, 0.0)
        for atom, probability in posterior.items():
            result[self.cause_by_atom[atom]] += probability
        return result


class CauseInformationActiveVerificationPlanner:
    """CIAV: couple cause information, reversible memory change, and task utility."""

    def __init__(
        self,
        *,
        cause_information_weight: float = 1.0,
        consolidation_change_weight: float = 1.0,
        task_utility_weight: float = 1.0,
        motion_cost_weight: float = 1.0,
        time_cost_weight: float = 1.0,
        interruption_cost_weight: float = 1.0,
        privacy_cost_weight: float = 1.0,
        safety_cost_weight: float = 1.0,
    ) -> None:
        weights = (
            cause_information_weight,
            consolidation_change_weight,
            task_utility_weight,
            motion_cost_weight,
            time_cost_weight,
            interruption_cost_weight,
            privacy_cost_weight,
            safety_cost_weight,
        )
        if any(weight < 0.0 for weight in weights):
            raise ValueError("CIAV objective weights must be non-negative")
        self.cause_information_weight = cause_information_weight
        self.consolidation_change_weight = consolidation_change_weight
        self.task_utility_weight = task_utility_weight
        self.motion_cost_weight = motion_cost_weight
        self.time_cost_weight = time_cost_weight
        self.interruption_cost_weight = interruption_cost_weight
        self.privacy_cost_weight = privacy_cost_weight
        self.safety_cost_weight = safety_cost_weight

    def select(
        self,
        belief: StructureTwoCauseBelief | JointParticleVerificationBelief,
        actions: tuple[ObservationActionCandidate, ...],
        *,
        consolidation_decision_utilities: dict[UUID, dict[UUID, float]],
        terminal_decision_utilities: dict[UUID, dict[UUID, float]],
        privacy_budget: float,
        minimum_net_value: float = 0.0,
    ) -> ActiveObservationPlan:
        if not isfinite(privacy_budget) or privacy_budget < 0.0:
            raise ValueError("privacy_budget must be finite and non-negative")
        if isinstance(belief, JointParticleVerificationBelief):
            # Frozen Pydantic models can still contain caller-mutated dicts.
            belief = JointParticleVerificationBelief.model_validate(belief.model_dump())
            actions = tuple(
                ObservationActionCandidate.model_validate(a.model_dump()) for a in actions
            )
            if len({a.action_id for a in actions}) != len(actions):
                raise ValueError("joint CIAV action IDs must be unique")
            if not isfinite(minimum_net_value):
                raise ValueError("joint CIAV minimum net value must be finite")
            objective_weights = (
                self.cause_information_weight,
                self.consolidation_change_weight,
                self.task_utility_weight,
                self.motion_cost_weight,
                self.time_cost_weight,
                self.interruption_cost_weight,
                self.privacy_cost_weight,
                self.safety_cost_weight,
            )
            if any(not isfinite(w) or w < 0.0 for w in objective_weights):
                raise ValueError("joint CIAV weights must be finite and non-negative")
            if any(
                not isfinite(cost)
                for action in actions
                for cost in (
                    action.motion_cost,
                    action.time_cost,
                    action.interruption_cost,
                    action.privacy_cost,
                    action.safety_cost,
                )
            ):
                raise ValueError("joint CIAV action costs must be finite")
        prior = belief.as_uuid_prior()
        if not terminal_decision_utilities or any(
            set(row) != set(prior) for row in terminal_decision_utilities.values()
        ):
            raise ValueError("terminal decisions must score every CIAV cause hypothesis")
        if any(
            not isfinite(value)
            for row in terminal_decision_utilities.values()
            for value in row.values()
        ):
            raise ValueError("terminal decision utilities must be finite")
        if not consolidation_decision_utilities or any(
            set(row) != set(prior) for row in consolidation_decision_utilities.values()
        ):
            raise ValueError("consolidation decisions must score every CIAV cause hypothesis")
        if any(
            not isfinite(value)
            for row in consolidation_decision_utilities.values()
            for value in row.values()
        ):
            raise ValueError("consolidation decision utilities must be finite")

        blocked = tuple(
            action.action_id for action in actions if action.privacy_cost > privacy_budget
        )
        eligible = tuple(action for action in actions if action.action_id not in set(blocked))
        if not eligible:
            return ActiveObservationPlan(
                scores=(),
                should_act=False,
                stop_reason="privacy_hard_constraint_blocked_all_actions",
                blocked_action_ids=blocked,
            )

        prior_entropy = _entropy(
            list(belief.cause_marginal(prior).values())
            if isinstance(belief, JointParticleVerificationBelief)
            else list(prior.values())
        )
        _baseline_decision, baseline_utility = ActionUtilityPlanner._best_terminal_decision(
            prior, terminal_decision_utilities
        )
        (
            _baseline_consolidation_decision,
            baseline_consolidation_utility,
        ) = ActionUtilityPlanner._best_terminal_decision(
            prior,
            consolidation_decision_utilities,
        )
        scores: list[ObservationActionScore] = []
        for action in eligible:
            if any(
                set(likelihoods) != set(prior)
                for likelihoods in action.outcome_likelihoods.values()
            ):
                raise ValueError("every CIAV action outcome must score every cause hypothesis")
            expected_entropy = 0.0
            expected_utility = 0.0
            expected_consolidation_utility = 0.0
            decisions_by_outcome: dict[str, UUID] = {}
            consolidation_decisions_by_outcome: dict[str, UUID] = {}
            for outcome, likelihoods in action.outcome_likelihoods.items():
                p_outcome = sum(
                    prior[hypothesis_id] * likelihood
                    for hypothesis_id, likelihood in likelihoods.items()
                )
                if p_outcome <= 0.0:
                    continue
                posterior = {
                    hypothesis_id: prior[hypothesis_id] * likelihood / p_outcome
                    for hypothesis_id, likelihood in likelihoods.items()
                }
                expected_entropy += p_outcome * _entropy(
                    list(belief.cause_marginal(posterior).values())
                    if isinstance(belief, JointParticleVerificationBelief)
                    else list(posterior.values())
                )
                decision_id, utility = ActionUtilityPlanner._best_terminal_decision(
                    posterior, terminal_decision_utilities
                )
                decisions_by_outcome[outcome] = decision_id
                expected_utility += p_outcome * utility
                consolidation_decision_id, consolidation_utility = (
                    ActionUtilityPlanner._best_terminal_decision(
                        posterior,
                        consolidation_decision_utilities,
                    )
                )
                consolidation_decisions_by_outcome[outcome] = consolidation_decision_id
                expected_consolidation_utility += p_outcome * consolidation_utility

            information_gain = max(0.0, prior_entropy - expected_entropy)
            utility_gain = max(0.0, expected_utility - baseline_utility)
            consolidation_gain = max(
                0.0,
                expected_consolidation_utility - baseline_consolidation_utility,
            )
            total_cost = (
                self.motion_cost_weight * action.motion_cost
                + self.time_cost_weight * action.time_cost
                + self.interruption_cost_weight * action.interruption_cost
                + self.privacy_cost_weight * action.privacy_cost
                + self.safety_cost_weight * action.safety_cost
            )
            net = (
                self.cause_information_weight * information_gain
                + self.consolidation_change_weight * consolidation_gain
                + self.task_utility_weight * utility_gain
                - total_cost
            )
            scores.append(
                ObservationActionScore(
                    action_id=action.action_id,
                    expected_information_gain=information_gain,
                    expected_posterior_entropy=expected_entropy,
                    total_cost=total_cost,
                    net_value=net,
                    objective=ObservationPlannerObjective.CAUSE_INFORMATION_UTILITY,
                    baseline_decision_utility=baseline_utility,
                    expected_decision_utility=expected_utility,
                    expected_utility_gain=utility_gain,
                    expected_cause_information_gain=information_gain,
                    baseline_consolidation_decision_utility=(baseline_consolidation_utility),
                    expected_consolidation_decision_utility=(expected_consolidation_utility),
                    expected_consolidation_decision_value_gain=consolidation_gain,
                    privacy_hard_constraint_satisfied=True,
                    recommended_terminal_decision_by_outcome=decisions_by_outcome,
                    recommended_consolidation_decision_by_outcome=(
                        consolidation_decisions_by_outcome
                    ),
                )
            )
        ranked = tuple(sorted(scores, key=lambda item: (-item.net_value, str(item.action_id))))
        best = ranked[0]
        if best.net_value <= minimum_net_value:
            return ActiveObservationPlan(
                scores=ranked,
                should_act=False,
                stop_reason="no_verification_improves_cause_memory_task_utility",
                blocked_action_ids=blocked,
            )
        return ActiveObservationPlan(
            selected_action_id=best.action_id,
            scores=ranked,
            should_act=True,
            stop_reason="selected_cause_memory_task_verification",
            blocked_action_ids=blocked,
        )


class VerificationBaselinePolicy(StrEnum):
    NEVER_ACT = "never_act"
    ALWAYS_VERIFY = "always_verify"
    RANDOM = "random"
    MAX_ENTROPY = "max_entropy"


def select_verification_baseline(
    policy: VerificationBaselinePolicy,
    prior: dict[UUID, float],
    actions: tuple[ObservationActionCandidate, ...],
    *,
    privacy_budget: float,
    random_seed: int = 0,
) -> ActiveObservationPlan:
    """Matched CIAV baselines under the same action set and privacy constraint."""

    blocked = tuple(action.action_id for action in actions if action.privacy_cost > privacy_budget)
    eligible = tuple(action for action in actions if action.action_id not in set(blocked))
    if policy is VerificationBaselinePolicy.NEVER_ACT:
        return ActiveObservationPlan(
            scores=(),
            should_act=False,
            stop_reason="never_act_baseline",
            blocked_action_ids=blocked,
        )
    if not eligible:
        return ActiveObservationPlan(
            scores=(),
            should_act=False,
            stop_reason="privacy_hard_constraint_blocked_all_actions",
            blocked_action_ids=blocked,
        )
    scored = InformationGainPlanner(
        motion_cost_weight=0.0,
        time_cost_weight=0.0,
        interruption_cost_weight=0.0,
        privacy_cost_weight=0.0,
        safety_cost_weight=0.0,
    ).select(prior, eligible, minimum_net_value=-1.0)
    if policy is VerificationBaselinePolicy.MAX_ENTROPY:
        selected = scored.selected_action_id
        reason = "max_entropy_baseline"
    elif policy is VerificationBaselinePolicy.ALWAYS_VERIFY:
        selected = sorted((action.action_id for action in eligible), key=str)[0]
        reason = "always_verify_baseline"
    else:
        selected = Random(random_seed).choice(
            sorted((action.action_id for action in eligible), key=str)
        )
        reason = "random_baseline"
    return ActiveObservationPlan(
        selected_action_id=selected,
        scores=scored.scores,
        should_act=True,
        stop_reason=reason,
        blocked_action_ids=blocked,
    )


class OffPolicyOverlapStatus(StrEnum):
    IDENTIFIABLE = "identifiable"
    WEAK_OVERLAP = "weak_overlap"
    NON_IDENTIFIABLE = "non_identifiable"


class OffPolicyVerificationSample(ContractModel):
    logged_action_id: UUID
    logged_propensity: float = Field(gt=0.0, le=1.0)
    target_action_probability: Probability
    realized_utility: float
    privacy_eligible: bool = True

    @field_validator("realized_utility")
    @classmethod
    def require_finite_utility(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("realized utility must be finite")
        return value


class OffPolicyVerificationReport(ContractModel):
    status: OffPolicyOverlapStatus
    sample_count: int = Field(gt=0)
    effective_sample_size: float = Field(ge=0.0)
    minimum_logged_propensity: float = Field(gt=0.0, le=1.0)
    ips_utility: float | None = None
    self_normalized_ips_utility: float | None = None
    rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_identification(self) -> OffPolicyVerificationReport:
        estimates = (self.ips_utility, self.self_normalized_ips_utility)
        if self.status is OffPolicyOverlapStatus.NON_IDENTIFIABLE and any(
            value is not None for value in estimates
        ):
            raise ValueError("non-identifiable OPE cannot report a utility estimate")
        if self.status is not OffPolicyOverlapStatus.NON_IDENTIFIABLE and any(
            value is None for value in estimates
        ):
            raise ValueError("identified OPE requires both utility estimates")
        return self


class OffPolicyVerificationEvaluator:
    """Inverse-propensity evaluation with explicit overlap/non-identification."""

    def evaluate(
        self,
        samples: tuple[OffPolicyVerificationSample, ...],
        *,
        target_policy_support_complete: bool,
        overlap_threshold: float = 0.05,
    ) -> OffPolicyVerificationReport:
        if not samples:
            raise ValueError("off-policy evaluation requires logged samples")
        if not 0.0 < overlap_threshold <= 1.0:
            raise ValueError("overlap_threshold must lie in (0, 1]")
        if any(
            sample.target_action_probability > 0.0 and not sample.privacy_eligible
            for sample in samples
        ):
            raise ValueError("target policy assigns mass to a privacy-ineligible action")
        minimum = min(sample.logged_propensity for sample in samples)
        if not target_policy_support_complete:
            return OffPolicyVerificationReport(
                status=OffPolicyOverlapStatus.NON_IDENTIFIABLE,
                sample_count=len(samples),
                effective_sample_size=0.0,
                minimum_logged_propensity=minimum,
                rationale="target action support is absent from the logged policy",
            )
        weights = tuple(
            sample.target_action_probability / sample.logged_propensity for sample in samples
        )
        weight_total = sum(weights)
        effective_sample_size = (
            weight_total**2 / sum(weight * weight for weight in weights)
            if any(weight > 0.0 for weight in weights)
            else 0.0
        )
        ips = sum(
            weight * sample.realized_utility
            for weight, sample in zip(weights, samples, strict=True)
        ) / len(samples)
        snips = (
            sum(
                weight * sample.realized_utility
                for weight, sample in zip(weights, samples, strict=True)
            )
            / weight_total
            if weight_total > 0.0
            else 0.0
        )
        weak = any(
            sample.target_action_probability > 0.0 and sample.logged_propensity < overlap_threshold
            for sample in samples
        )
        return OffPolicyVerificationReport(
            status=(
                OffPolicyOverlapStatus.WEAK_OVERLAP if weak else OffPolicyOverlapStatus.IDENTIFIABLE
            ),
            sample_count=len(samples),
            effective_sample_size=effective_sample_size,
            minimum_logged_propensity=minimum,
            ips_utility=ips,
            self_normalized_ips_utility=snips,
            rationale=(
                "logged support exists but falls below the overlap threshold"
                if weak
                else "logged policy covers the target verification policy"
            ),
        )
