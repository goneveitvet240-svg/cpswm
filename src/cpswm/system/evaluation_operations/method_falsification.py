"""Cross-structure preregistration and falsification decisions for CPSWM methods.

This module is deliberately narrower than the experiment implementations.  It
does not manufacture evidence, run a proxy under a famous system's name, or
accept caller supplied pass flags.  It freezes, for every proposed method:

* the strongest direct opponents that must be present;
* the scenario families that must be covered;
* one action-level primary endpoint;
* one route-specific mechanism endpoint; and
* the confidence-interval rule that can reject the method claim.

Existing route-specific verifiers remain authoritative for artifact contents.
This layer supplies the missing common decision vocabulary across Structure
One, Structure Two, Structure Three, and OAM-PHM.
"""

from __future__ import annotations

from enum import StrEnum
from math import isfinite
from typing import Self

from pydantic import Field, model_validator

from cpswm.contracts.base import ContractModel
from cpswm.system.attestation import (
    Attestation,
    AttestationError,
    AttestationVerifier,
    Ed25519AttestationSigner,
    attested_payload,
)
from cpswm.system.reproducibility import content_sha256

REGISTRY_VERSION = "cpswm-method-falsification-registry@0.1"
DOMAIN_METHOD_EVIDENCE_SUBMISSION = "cpswm.method_falsification.verified_submission.v1"


class ResearchScope(StrEnum):
    STRUCTURE_ONE = "structure_one"
    STRUCTURE_TWO = "structure_two"
    STRUCTURE_TWO_UNIFIED = "structure_two_unified"
    STRUCTURE_THREE = "structure_three"
    OAM_PHM = "oam_phm"


class BaselineFidelity(StrEnum):
    REDUCED_SKILL_PROXY = "reduced_skill_proxy"
    MATCHED_REPLAY_ADAPTER = "matched_replay_adapter"
    INDEPENDENTLY_TUNED_MATCHED = "independently_tuned_matched"
    FAITHFUL_EXTERNAL = "faithful_external"


class FalsificationDecision(StrEnum):
    BLOCKED = "blocked"
    FALSIFIED = "falsified"
    INCONCLUSIVE = "inconclusive"
    SURVIVED = "survived"


class ClusterAxis(StrEnum):
    HOUSEHOLD = "household"
    EPISODE = "episode"
    OBJECT_FAMILY = "object_family"
    USER = "user"


class ActionMetric(StrEnum):
    CUMULATIVE_ACTION_REGRET = "cumulative_action_regret"
    EMBODIED_TASK_UTILITY = "embodied_task_utility"
    SEARCH_PATH_COST = "search_path_cost"
    WRONG_PLACEMENT_COST = "wrong_placement_cost"
    TOTAL_VERIFICATION_ADJUSTED_UTILITY = "total_verification_adjusted_utility"


class MechanismMetric(StrEnum):
    EVIDENCE_MULTIPLICITY_ERROR = "evidence_multiplicity_error"
    MOBILITY_STRATIFIED_PREDICTION = "mobility_stratified_prediction"
    SEMANTIC_LAYER_VIOLATION = "semantic_layer_violation"
    SELECTION_BIAS_ERROR = "selection_bias_error"
    LONG_HORIZON_CONTAMINATION_AUC = "long_horizon_contamination_auc"
    PROVENANCE_LEAKAGE_RATE = "provenance_leakage_rate"
    CAUSE_ATTRIBUTION_ERROR = "cause_attribution_error"
    REVERSIBLE_RECOVERY_COST = "reversible_recovery_cost"
    FALSE_REGIME_REACTIVATION = "false_regime_reactivation"
    VERIFICATION_INFORMATION_EFFICIENCY = "verification_information_efficiency"
    LANGUAGE_PARSE_COVERAGE = "language_parse_coverage"
    OPEN_WORLD_IDENTITY_ERROR = "open_world_identity_error"
    DOWNSTREAM_REVISION_ERROR = "downstream_revision_error"
    ANYTIME_UNKNOWN_COVERAGE_ERROR = "anytime_unknown_coverage_error"
    TRANSITION_SURVIVAL_NLL = "transition_survival_nll"
    UNKNOWN_MASS_CALIBRATION_ERROR = "unknown_mass_calibration_error"
    FUTURE_TASK_UTILITY_GAIN = "future_task_utility_gain"
    CROSS_MODULE_CAUSAL_UTILITY = "cross_module_causal_utility"


class OpponentRequirement(ContractModel):
    opponent_id: str = Field(min_length=1)
    accepted_fidelities: tuple[BaselineFidelity, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_fidelities(self) -> Self:
        if len(self.accepted_fidelities) != len(set(self.accepted_fidelities)):
            raise ValueError("accepted baseline fidelities must be unique")
        if BaselineFidelity.REDUCED_SKILL_PROXY in self.accepted_fidelities:
            raise ValueError("a reduced-skill proxy can never satisfy a strongest-opponent gate")
        if BaselineFidelity.MATCHED_REPLAY_ADAPTER in self.accepted_fidelities:
            raise ValueError("a replay adapter can never satisfy a strongest-opponent gate")
        return self


class MethodFalsificationSpec(ContractModel):
    method_id: str = Field(min_length=1)
    scope: ResearchScope
    claim: str = Field(min_length=1)
    strongest_opponents: tuple[OpponentRequirement, ...] = Field(min_length=1)
    frozen_scenario_families: tuple[str, ...] = Field(min_length=2)
    primary_action_metric: ActionMetric
    mechanism_metric: MechanismMetric
    cluster_axis: ClusterAxis
    action_noninferiority_margin: float = Field(ge=0.0)
    mechanism_superiority_margin: float = Field(ge=0.0)
    falsification_rule: str = Field(min_length=1)
    retained_capabilities: tuple[str, ...] = Field(min_length=1)
    external_validity_required: bool

    @model_validator(mode="after")
    def _frozen_semantics(self) -> Self:
        opponents = [item.opponent_id for item in self.strongest_opponents]
        if len(opponents) != len(set(opponents)):
            raise ValueError("strongest opponents must be unique")
        if len(self.frozen_scenario_families) != len(set(self.frozen_scenario_families)):
            raise ValueError("frozen scenario families must be unique")
        if len(self.retained_capabilities) != len(set(self.retained_capabilities)):
            raise ValueError("retained capabilities must be unique")
        return self

    @property
    def preregistration_sha256(self) -> str:
        return content_sha256(self)


class MethodFalsificationRegistry(ContractModel):
    registry_version: str
    methods: tuple[MethodFalsificationSpec, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _registry_semantics(self) -> Self:
        if self.registry_version != REGISTRY_VERSION:
            raise ValueError("unknown method falsification registry version")
        method_ids = [item.method_id for item in self.methods]
        if len(method_ids) != len(set(method_ids)):
            raise ValueError("method falsification registry IDs must be unique")
        required_scopes = set(ResearchScope)
        actual_scopes = {item.scope for item in self.methods}
        if actual_scopes != required_scopes:
            raise ValueError("registry must cover every CPSWM research scope")
        return self

    @property
    def registry_sha256(self) -> str:
        return content_sha256(self)

    def by_id(self, method_id: str) -> MethodFalsificationSpec:
        for method in self.methods:
            if method.method_id == method_id:
                return method
        raise KeyError(f"unknown registered method: {method_id}")


class OrientedEffectInterval(ContractModel):
    """Candidate-minus-opponent effect after orienting larger as better."""

    estimate: float
    confidence_interval_low: float
    confidence_interval_high: float
    confidence_level: float = Field(gt=0.0, lt=1.0)

    @model_validator(mode="after")
    def _ordered_finite_interval(self) -> Self:
        values = (
            self.estimate,
            self.confidence_interval_low,
            self.confidence_interval_high,
        )
        if any(not isfinite(value) for value in values):
            raise ValueError("effect interval values must be finite")
        if not self.confidence_interval_low <= self.estimate <= self.confidence_interval_high:
            raise ValueError("effect estimate must lie inside its confidence interval")
        return self


class OpponentComparisonEvidence(ContractModel):
    opponent_id: str = Field(min_length=1)
    fidelity: BaselineFidelity
    independently_tuned: bool
    same_visible_input: bool
    same_action_budget: bool
    primary_action_effect: OrientedEffectInterval
    mechanism_effect: OrientedEffectInterval


class MethodEvidenceSubmission(ContractModel):
    method_id: str = Field(min_length=1)
    preregistration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    validation_split_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sealed_test_split_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    shared_visible_input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    shared_action_budget_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    power_analysis_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    covered_scenario_families: tuple[str, ...] = Field(min_length=1)
    independent_unit_count: int = Field(gt=0)
    cluster_axis: ClusterAxis
    comparisons: tuple[OpponentComparisonEvidence, ...] = Field(min_length=1)
    external_validity_artifact_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    attestation: Attestation | None = None

    @model_validator(mode="after")
    def _sealed_submission(self) -> Self:
        if self.validation_split_sha256 == self.sealed_test_split_sha256:
            raise ValueError("validation and sealed-test splits must differ")
        if len(self.covered_scenario_families) != len(set(self.covered_scenario_families)):
            raise ValueError("covered scenario families must be unique")
        opponents = [item.opponent_id for item in self.comparisons]
        if len(opponents) != len(set(opponents)):
            raise ValueError("opponent comparison evidence must be unique")
        return self


class MethodFalsificationResult(ContractModel):
    method_id: str
    decision: FalsificationDecision
    preregistration_sha256: str
    blockers: tuple[str, ...]
    failed_opponents: tuple[str, ...]
    inconclusive_opponents: tuple[str, ...]
    survived_opponents: tuple[str, ...]
    paper_claim_allowed: bool


class MethodFalsificationAudit(ContractModel):
    registry_version: str
    registry_sha256: str
    results: tuple[MethodFalsificationResult, ...]

    @property
    def decision_counts(self) -> dict[FalsificationDecision, int]:
        return {
            decision: sum(result.decision is decision for result in self.results)
            for decision in FalsificationDecision
        }


def evaluate_method_submission(
    spec: MethodFalsificationSpec,
    submission: MethodEvidenceSubmission | None,
    *,
    authority: AttestationVerifier | None = None,
) -> MethodFalsificationResult:
    """Apply the frozen two-endpoint rule without caller-controlled outcomes."""

    if submission is None:
        return MethodFalsificationResult(
            method_id=spec.method_id,
            decision=FalsificationDecision.BLOCKED,
            preregistration_sha256=spec.preregistration_sha256,
            blockers=("missing_evidence_submission",),
            failed_opponents=(),
            inconclusive_opponents=(),
            survived_opponents=(),
            paper_claim_allowed=False,
        )
    if submission.method_id != spec.method_id:
        raise ValueError("method evidence submission is bound to a different method")
    if submission.preregistration_sha256 != spec.preregistration_sha256:
        raise ValueError("method evidence submission is bound to a different preregistration")

    if authority is None or not authority.formal_grade:
        return MethodFalsificationResult(
            method_id=spec.method_id,
            decision=FalsificationDecision.BLOCKED,
            preregistration_sha256=spec.preregistration_sha256,
            blockers=("missing_formal_public_key_verifier",),
            failed_opponents=(),
            inconclusive_opponents=(),
            survived_opponents=(),
            paper_claim_allowed=False,
        )
    try:
        authority.verify(
            DOMAIN_METHOD_EVIDENCE_SUBMISSION,
            attested_payload(submission),
            submission.attestation,
        )
    except AttestationError:
        return MethodFalsificationResult(
            method_id=spec.method_id,
            decision=FalsificationDecision.BLOCKED,
            preregistration_sha256=spec.preregistration_sha256,
            blockers=("unverified_evidence_submission",),
            failed_opponents=(),
            inconclusive_opponents=(),
            survived_opponents=(),
            paper_claim_allowed=False,
        )

    blockers: list[str] = []
    if submission.cluster_axis is not spec.cluster_axis:
        blockers.append("wrong_cluster_axis")
    missing_scenarios = set(spec.frozen_scenario_families) - set(
        submission.covered_scenario_families
    )
    blockers.extend(f"missing_scenario:{item}" for item in sorted(missing_scenarios))
    if spec.external_validity_required and submission.external_validity_artifact_sha256 is None:
        blockers.append("missing_external_validity_artifact")

    evidence_by_opponent = {item.opponent_id: item for item in submission.comparisons}
    for requirement in spec.strongest_opponents:
        evidence = evidence_by_opponent.get(requirement.opponent_id)
        if evidence is None:
            blockers.append(f"missing_strongest_opponent:{requirement.opponent_id}")
            continue
        if evidence.fidelity not in requirement.accepted_fidelities:
            blockers.append(f"insufficient_fidelity:{requirement.opponent_id}")
        if not evidence.independently_tuned:
            blockers.append(f"not_independently_tuned:{requirement.opponent_id}")
        if not evidence.same_visible_input:
            blockers.append(f"visible_input_mismatch:{requirement.opponent_id}")
        if not evidence.same_action_budget:
            blockers.append(f"action_budget_mismatch:{requirement.opponent_id}")

    if blockers:
        return MethodFalsificationResult(
            method_id=spec.method_id,
            decision=FalsificationDecision.BLOCKED,
            preregistration_sha256=spec.preregistration_sha256,
            blockers=tuple(blockers),
            failed_opponents=(),
            inconclusive_opponents=(),
            survived_opponents=(),
            paper_claim_allowed=False,
        )

    failed: list[str] = []
    inconclusive: list[str] = []
    survived: list[str] = []
    for requirement in spec.strongest_opponents:
        evidence = evidence_by_opponent[requirement.opponent_id]
        action = evidence.primary_action_effect
        mechanism = evidence.mechanism_effect
        clearly_action_inferior = (
            action.confidence_interval_high < -spec.action_noninferiority_margin
        )
        clearly_mechanism_inferior = (
            mechanism.confidence_interval_high <= spec.mechanism_superiority_margin
        )
        action_noninferior = action.confidence_interval_low >= -spec.action_noninferiority_margin
        mechanism_superior = mechanism.confidence_interval_low > spec.mechanism_superiority_margin
        if clearly_action_inferior or clearly_mechanism_inferior:
            failed.append(requirement.opponent_id)
        elif action_noninferior and mechanism_superior:
            survived.append(requirement.opponent_id)
        else:
            inconclusive.append(requirement.opponent_id)

    if failed:
        decision = FalsificationDecision.FALSIFIED
    elif inconclusive:
        decision = FalsificationDecision.INCONCLUSIVE
    else:
        decision = FalsificationDecision.SURVIVED
    return MethodFalsificationResult(
        method_id=spec.method_id,
        decision=decision,
        preregistration_sha256=spec.preregistration_sha256,
        blockers=(),
        failed_opponents=tuple(failed),
        inconclusive_opponents=tuple(inconclusive),
        survived_opponents=tuple(survived),
        paper_claim_allowed=decision is FalsificationDecision.SURVIVED,
    )


def evaluate_registry(
    registry: MethodFalsificationRegistry,
    submissions: tuple[MethodEvidenceSubmission, ...] = (),
    *,
    authority: AttestationVerifier | None = None,
) -> MethodFalsificationAudit:
    submission_by_method = {item.method_id: item for item in submissions}
    if len(submission_by_method) != len(submissions):
        raise ValueError("method evidence submissions must be unique")
    unknown = set(submission_by_method) - {item.method_id for item in registry.methods}
    if unknown:
        raise ValueError(f"evidence submitted for unregistered methods: {sorted(unknown)}")
    return MethodFalsificationAudit(
        registry_version=registry.registry_version,
        registry_sha256=registry.registry_sha256,
        results=tuple(
            evaluate_method_submission(
                spec,
                submission_by_method.get(spec.method_id),
                authority=authority,
            )
            for spec in registry.methods
        ),
    )


def attest_method_evidence_submission(
    submission: MethodEvidenceSubmission,
    *,
    authority: Ed25519AttestationSigner,
) -> MethodEvidenceSubmission:
    """Bind every evidence field to an independent verifier attestation."""

    unsigned = submission.model_copy(update={"attestation": None})
    return unsigned.model_copy(
        update={
            "attestation": authority.sign(
                DOMAIN_METHOD_EVIDENCE_SUBMISSION,
                attested_payload(unsigned),
            )
        }
    )


_MATCHED = (BaselineFidelity.INDEPENDENTLY_TUNED_MATCHED,)
_AMG = (BaselineFidelity.INDEPENDENTLY_TUNED_MATCHED,)
_EXTERNAL = (BaselineFidelity.FAITHFUL_EXTERNAL,)


def _opponent(opponent_id: str, fidelities: tuple[BaselineFidelity, ...]) -> OpponentRequirement:
    return OpponentRequirement(opponent_id=opponent_id, accepted_fidelities=fidelities)


def _spec(
    method_id: str,
    scope: ResearchScope,
    claim: str,
    opponents: tuple[OpponentRequirement, ...],
    scenarios: tuple[str, ...],
    action_metric: ActionMetric,
    mechanism_metric: MechanismMetric,
    cluster_axis: ClusterAxis,
    retained: tuple[str, ...],
    *,
    external: bool = False,
) -> MethodFalsificationSpec:
    return MethodFalsificationSpec(
        method_id=method_id,
        scope=scope,
        claim=claim,
        strongest_opponents=opponents,
        frozen_scenario_families=scenarios,
        primary_action_metric=action_metric,
        mechanism_metric=mechanism_metric,
        cluster_axis=cluster_axis,
        action_noninferiority_margin=0.0,
        mechanism_superiority_margin=0.0,
        falsification_rule=(
            "FALSIFIED when any required strongest opponent is clearly better on the "
            "oriented primary action endpoint, or the candidate has no positive "
            "route-specific mechanism benefit; SURVIVED requires action non-inferiority "
            "and mechanism superiority against every required opponent."
        ),
        retained_capabilities=retained,
        external_validity_required=external,
    )


def current_method_falsification_registry() -> MethodFalsificationRegistry:
    """Frozen v0.1 registry; ordering is part of its content identity."""

    methods = (
        _spec(
            "s1.leave_one_out_layered_habit",
            ResearchScope.STRUCTURE_ONE,
            (
                "Partitioned hierarchical evidence avoids duplicate confidence "
                "without losing action utility."
            ),
            (
                _opponent("additive_hierarchical_dirichlet", _MATCHED),
                _opponent("nested_backoff_habit", _MATCHED),
            ),
            ("single_context_repetition", "cross_context_transfer", "household_person_conflict"),
            ActionMetric.WRONG_PLACEMENT_COST,
            MechanismMetric.EVIDENCE_MULTIPLICITY_ERROR,
            ClusterAxis.HOUSEHOLD,
            ("personalized_habit", "household_prior", "context_conditioning"),
        ),
        _spec(
            "s1.five_axis_mobility",
            ResearchScope.STRUCTURE_ONE,
            (
                "Non-exclusive mobility axes improve decisions for multimodal, "
                "activity-coupled, and drifting objects."
            ),
            (
                _opponent("binary_stationarity", _MATCHED),
                _opponent("three_bin_rigidity", _MATCHED),
            ),
            ("multimodal_return", "activity_carried", "equal_entropy_regime_drift"),
            ActionMetric.SEARCH_PATH_COST,
            MechanismMetric.MOBILITY_STRATIFIED_PREDICTION,
            ClusterAxis.OBJECT_FAMILY,
            ("mobility_profile", "multiple_locations", "next_location_prediction"),
        ),
        _spec(
            "s1.four_layer_placement_semantics",
            ResearchScope.STRUCTURE_ONE,
            (
                "Separating behavior, stated preference, household norm, and "
                "commonsense prevents unsafe placement decisions."
            ),
            (
                _opponent("collapsed_placement_memory", _MATCHED),
                _opponent("authority_agnostic_rule_resolver", _MATCHED),
            ),
            ("behavior_preference_conflict", "visitor_owner_conflict", "hard_safety_retraction"),
            ActionMetric.WRONG_PLACEMENT_COST,
            MechanismMetric.SEMANTIC_LAYER_VIOLATION,
            ClusterAxis.USER,
            ("observed_behavior", "stated_preference", "household_norm", "commonsense_norm"),
        ),
        _spec(
            "s2.opceu",
            ResearchScope.STRUCTURE_TWO,
            (
                "Observation-process correction reduces selection bias without "
                "treating unobserved as absent."
            ),
            (
                _opponent("doubly_robust_observation_correction", _MATCHED),
                _opponent("learned_object_state_estimator", _MATCHED),
            ),
            ("complete_observation", "selective_mnar_observation", "weak_overlap"),
            ActionMetric.CUMULATIVE_ACTION_REGRET,
            MechanismMetric.SELECTION_BIAS_ERROR,
            ClusterAxis.HOUSEHOLD,
            ("selective_observation", "negative_evidence", "observation_opportunity"),
        ),
        _spec(
            "s2.orrer",
            ResearchScope.STRUCTURE_TWO,
            (
                "Open-world reversible event revision limits long-horizon harm from "
                "late actor and mechanism corrections."
            ),
            (
                _opponent("damen_hogg_amg_matched_open_world", _AMG),
                _opponent("fixed_lag_smoother", _MATCHED),
            ),
            ("direct_handoff", "unknown_actor_handoff", "late_independent_correction"),
            ActionMetric.CUMULATIVE_ACTION_REGRET,
            MechanismMetric.LONG_HORIZON_CONTAMINATION_AUC,
            ClusterAxis.HOUSEHOLD,
            ("hidden_event_inference", "multi_actor_reasoning", "open_world_unknowns"),
        ),
        _spec(
            "s2.pchmp",
            ResearchScope.STRUCTURE_TWO,
            (
                "Provenance-constrained message passing prevents evidence recycling "
                "while preserving useful joint inference."
            ),
            (
                _opponent("independently_tuned_hgt", _MATCHED),
                _opponent("independently_tuned_r_gcn", _MATCHED),
            ),
            ("duplicate_semantic_cluster", "actor_permutation", "prediction_feedback_cycle"),
            ActionMetric.CUMULATIVE_ACTION_REGRET,
            MechanismMetric.PROVENANCE_LEAKAGE_RATE,
            ClusterAxis.HOUSEHOLD,
            ("provenance", "joint_hypothesis_inference", "evidence_firewall"),
        ),
        _spec(
            "s2.cf_bocpd",
            ResearchScope.STRUCTURE_TWO,
            (
                "Cause-factored change detection avoids resetting owner habits for "
                "observation, identity, visitor, or noise shifts."
            ),
            (
                _opponent("bocpdms", _MATCHED),
                _opponent("switching_hmm", _MATCHED),
            ),
            ("owner_habit_change", "visitor_shift", "identity_and_sensor_shift"),
            ActionMetric.CUMULATIVE_ACTION_REGRET,
            MechanismMetric.CAUSE_ATTRIBUTION_ERROR,
            ClusterAxis.HOUSEHOLD,
            ("non_stationary_habits", "cause_attribution", "selective_parameter_reset"),
        ),
        _spec(
            "s2.rgrc",
            ResearchScope.STRUCTURE_TWO,
            (
                "Responsibility-gated reversible consolidation repairs derived memory "
                "more cheaply and safely than matched rebuilds."
            ),
            (
                _opponent("full_history_rerun", _MATCHED),
                _opponent("fisher_replay_consolidation", _MATCHED),
            ),
            ("wrong_actor_commit", "wrong_identity_commit", "late_retraction_and_recurrence"),
            ActionMetric.CUMULATIVE_ACTION_REGRET,
            MechanismMetric.REVERSIBLE_RECOVERY_COST,
            ClusterAxis.HOUSEHOLD,
            ("reversible_attribution", "anti_contamination", "full_rerun_equivalence"),
        ),
        _spec(
            "s2.ccrr",
            ResearchScope.STRUCTURE_TWO,
            (
                "Context-conditioned reactivation recovers true historical habits "
                "without reviving visitor or sensor regimes."
            ),
            (
                _opponent("sticky_hdp_hsmm", _MATCHED),
                _opponent("factorized_sticky_finite_hmm", _MATCHED),
            ),
            ("true_old_habit_return", "visitor_recurrence", "observation_policy_recurrence"),
            ActionMetric.CUMULATIVE_ACTION_REGRET,
            MechanismMetric.FALSE_REGIME_REACTIVATION,
            ClusterAxis.HOUSEHOLD,
            ("habit_regime", "historical_version", "unresolved_state"),
        ),
        _spec(
            "s2.ciav",
            ResearchScope.STRUCTURE_TWO,
            (
                "Cause-information verification improves future action utility per "
                "unit motion, interruption, privacy, and time cost."
            ),
            (
                _opponent("cost_aware_value_of_information", _MATCHED),
                _opponent("max_entropy_verification", _MATCHED),
            ),
            ("identifiable_anomaly", "non_identifiable_actor", "privacy_constrained_query"),
            ActionMetric.TOTAL_VERIFICATION_ADJUSTED_UTILITY,
            MechanismMetric.VERIFICATION_INFORMATION_EFFICIENCY,
            ClusterAxis.HOUSEHOLD,
            ("active_verification", "privacy", "embodied_action_budget"),
        ),
        _spec(
            "s2.unified_combination_a",
            ResearchScope.STRUCTURE_TWO_UNIFIED,
            (
                "The coupled seven-operator method yields action benefit not "
                "reproduced by independently tuned ordinary combinations."
            ),
            (
                _opponent("enhanced_o_star", _EXTERNAL),
                _opponent("ordinary_hgt_plus_hmm_plus_full_rerun", _MATCHED),
            ),
            (
                "five_factor_full_factorial",
                "long_horizon_contamination_recovery",
                "closed_loop_embodied_feedback",
            ),
            ActionMetric.CUMULATIVE_ACTION_REGRET,
            MechanismMetric.CROSS_MODULE_CAUSAL_UTILITY,
            ClusterAxis.HOUSEHOLD,
            (
                "hidden_event_inference",
                "multi_actor_reasoning",
                "open_world_unknowns",
                "reversible_attribution",
                "embodied_execution_feedback",
            ),
            external=True,
        ),
        _spec(
            "s3.multi_parse_posterior",
            ResearchScope.STRUCTURE_THREE,
            (
                "Marginalizing multiple language parses improves embodied decisions "
                "without hiding unparsed mass."
            ),
            (
                _opponent("top1_llm_parse", _MATCHED),
                _opponent("llm_self_consistency_vote", _MATCHED),
            ),
            ("temporal_reference", "person_reference", "functional_and_relational_reference"),
            ActionMetric.EMBODIED_TASK_UTILITY,
            MechanismMetric.LANGUAGE_PARSE_COVERAGE,
            ClusterAxis.EPISODE,
            ("ambiguous_language", "unknown", "clarification"),
        ),
        _spec(
            "s3.probabilistic_dynamic_instance_graph",
            ResearchScope.STRUCTURE_THREE,
            (
                "Explicit existing/new/unknown association prevents hard identity "
                "errors from contaminating action and memory."
            ),
            (
                _opponent("learned_object_state_estimator", _MATCHED),
                _opponent("hard_metric_association", _MATCHED),
            ),
            ("similar_instances", "occlusion_and_reappearance", "new_or_unmapped_instance"),
            ActionMetric.EMBODIED_TASK_UTILITY,
            MechanismMetric.OPEN_WORLD_IDENTITY_ERROR,
            ClusterAxis.OBJECT_FAMILY,
            ("instance_identity", "dynamic_object_layer", "open_world_unknowns"),
        ),
        _spec(
            "s3.revision_aware_evidence_graph",
            ResearchScope.STRUCTURE_THREE,
            (
                "Revision-aware evidence propagation repairs actor, event, habit, "
                "and action descendants after corrections."
            ),
            (
                _opponent("full_history_rerun", _MATCHED),
                _opponent("overwrite_scene_graph", _MATCHED),
            ),
            ("actor_claim_retraction", "event_supersession", "failed_action_feedback_revision"),
            ActionMetric.EMBODIED_TASK_UTILITY,
            MechanismMetric.DOWNSTREAM_REVISION_ERROR,
            ClusterAxis.EPISODE,
            ("revision", "provenance", "execution_feedback"),
        ),
        _spec(
            "s3.co_cip",
            ResearchScope.STRUCTURE_THREE,
            (
                "Cost-aware open-set conformal information pursuit remains valid "
                "under adaptive stopping and improves decisions."
            ),
            (
                _opponent("conformal_information_pursuit", _MATCHED),
                _opponent("cost_aware_entropy_search", _MATCHED),
            ),
            ("adaptive_stopping", "unmapped_target", "heterogeneous_observation_cost"),
            ActionMetric.TOTAL_VERIFICATION_ADJUSTED_UTILITY,
            MechanismMetric.ANYTIME_UNKNOWN_COVERAGE_ERROR,
            ClusterAxis.EPISODE,
            ("active_observation", "unknown", "abstention"),
        ),
        _spec(
            "s3.habit_conditioned_survival",
            ResearchScope.STRUCTURE_THREE,
            (
                "Activity- and regime-conditioned survival likelihood outperforms "
                "elapsed-time decay for memory reliability."
            ),
            (
                _opponent("exponential_time_decay", _MATCHED),
                _opponent("flexible_elapsed_time_hazard", _MATCHED),
            ),
            ("same_elapsed_different_activity", "regime_switch", "object_location_family_shift"),
            ActionMetric.SEARCH_PATH_COST,
            MechanismMetric.TRANSITION_SURVIVAL_NLL,
            ClusterAxis.OBJECT_FAMILY,
            ("memory_reliability", "activity_context", "habit_regime"),
        ),
        _spec(
            "s3.coverage_derived_unknown_mass",
            ResearchScope.STRUCTURE_THREE,
            (
                "Spatial coverage and miss probability estimate open-world mass "
                "better than fixed or frequency-only unknown priors."
            ),
            (
                _opponent("conformal_good_turing_unknown", _MATCHED),
                _opponent("learned_unknown_mass", _MATCHED),
            ),
            ("unobserved_volume", "occluded_miss", "target_absent_from_scene"),
            ActionMetric.EMBODIED_TASK_UTILITY,
            MechanismMetric.UNKNOWN_MASS_CALIBRATION_ERROR,
            ClusterAxis.EPISODE,
            ("unknown", "observation_coverage", "miss_probability"),
        ),
        _spec(
            "oam_phm.full_loop",
            ResearchScope.OAM_PHM,
            (
                "Opportunistic observation produces future-task value after actor "
                "attribution and anti-contamination costs are counted."
            ),
            (
                _opponent("enhanced_o_star", _EXTERNAL),
                _opponent("dynamem", _EXTERNAL),
                _opponent("star", _EXTERNAL),
            ),
            (
                "passive_vs_opportunistic_observation",
                "multi_resident_contamination",
                "future_query_search_and_putback",
            ),
            ActionMetric.TOTAL_VERIFICATION_ADJUSTED_UTILITY,
            MechanismMetric.FUTURE_TASK_UTILITY_GAIN,
            ClusterAxis.HOUSEHOLD,
            (
                "opportunistic_observation",
                "multi_actor_reasoning",
                "anti_contamination",
                "future_embodied_tasks",
            ),
            external=True,
        ),
    )
    return MethodFalsificationRegistry(registry_version=REGISTRY_VERSION, methods=methods)


__all__ = [
    "DOMAIN_METHOD_EVIDENCE_SUBMISSION",
    "REGISTRY_VERSION",
    "ActionMetric",
    "BaselineFidelity",
    "ClusterAxis",
    "FalsificationDecision",
    "MechanismMetric",
    "MethodEvidenceSubmission",
    "MethodFalsificationAudit",
    "MethodFalsificationRegistry",
    "MethodFalsificationResult",
    "MethodFalsificationSpec",
    "OpponentComparisonEvidence",
    "OpponentRequirement",
    "OrientedEffectInterval",
    "ResearchScope",
    "attest_method_evidence_submission",
    "current_method_falsification_registry",
    "evaluate_method_submission",
    "evaluate_registry",
]
