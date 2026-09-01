"""Fail-closed evidence contracts for the unfinished OAM-PHM comparisons.

This module separates three claims that are easy to conflate:

* an equation-level reference core can be executable;
* an external method can have a complete reproduction package;
* a matched, sealed comparison can support an action/utility claim.

The first never implies the second, and the second never implies the third.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from enum import StrEnum
from itertools import product
from math import isfinite
from random import Random
from statistics import fmean
from typing import Self

from pydantic import Field, field_validator, model_validator

from cpswm.contracts.base import ContractModel, Probability
from cpswm.system.reproducibility import content_sha256


class ExternalMethod(StrEnum):
    O_STAR = "o_star"
    STREAK = "streak"


class FidelityRequirementStatus(StrEnum):
    VERIFIED = "verified"
    MISSING = "missing"
    PENDING_DESIGN_CHOICE = "pending_design_choice"
    NOT_APPLICABLE = "not_applicable"


class ReproductionReadiness(StrEnum):
    SPECIFICATION_ONLY = "specification_only"
    EQUATION_CORE_ONLY = "equation_core_only"
    BLOCKED_PENDING_DESIGN_CHOICE = "blocked_pending_design_choice"
    REPRODUCTION_COMPLETE = "reproduction_complete"


class FidelityRequirement(ContractModel):
    requirement_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    mandatory: bool = True
    status: FidelityRequirementStatus
    evidence_artifact_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    note: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_evidence(self) -> Self:
        if self.status == FidelityRequirementStatus.VERIFIED and not self.evidence_artifact_sha256:
            raise ValueError("verified fidelity requirements need a content-bound artifact")
        if self.status != FidelityRequirementStatus.VERIFIED and self.evidence_artifact_sha256:
            raise ValueError("unverified fidelity requirements cannot cite verification artifacts")
        return self


CANONICAL_FIDELITY_REQUIREMENTS: dict[ExternalMethod, frozenset[str]] = {
    ExternalMethod.O_STAR: frozenset(
        {
            "primary-source-frozen",
            "semantic-prior",
            "geometric-grounding",
            "dirichlet-update-core",
            "relaxed-transition-inference",
            "cost-aware-active-search",
            "opportunistic-multi-target-perception",
            "published-result-recheck",
        }
    ),
    ExternalMethod.STREAK: frozenset(
        {
            "primary-source-frozen",
            "gtm-architecture",
            "streaming-graph-update",
            "three-part-model-loss",
            "fisher-consolidation",
            "mean-feature-rehearsal",
            "independent-hyperparameter-search",
            "homer-sequential-recheck",
        }
    ),
}


class ExternalReproductionManifest(ContractModel):
    method: ExternalMethod
    reproduction_id: str = Field(min_length=1)
    primary_source_url: str = Field(pattern=r"^https://")
    primary_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    official_code_url: str | None = Field(default=None, pattern=r"^https://")
    official_code_commit: str | None = None
    requirements: tuple[FidelityRequirement, ...] = Field(min_length=1)
    readiness: ReproductionReadiness

    @model_validator(mode="after")
    def validate_readiness(self) -> Self:
        ids = [item.requirement_id for item in self.requirements]
        if len(ids) != len(set(ids)):
            raise ValueError("fidelity requirement ids must be unique")
        unresolved = [
            item
            for item in self.requirements
            if item.mandatory and item.status != FidelityRequirementStatus.VERIFIED
        ]
        if self.readiness == ReproductionReadiness.REPRODUCTION_COMPLETE and unresolved:
            raise ValueError(
                "a complete reproduction cannot have unresolved mandatory requirements"
            )
        if self.readiness == ReproductionReadiness.REPRODUCTION_COMPLETE and bool(
            self.official_code_url
        ) != bool(self.official_code_commit):
            raise ValueError("official code URL and commit must be declared together")
        if (
            any(
                item.status == FidelityRequirementStatus.PENDING_DESIGN_CHOICE
                for item in unresolved
            )
            and self.readiness != ReproductionReadiness.BLOCKED_PENDING_DESIGN_CHOICE
        ):
            raise ValueError("pending method-design choices require an explicit blocked readiness")
        return self

    @property
    def content_sha256(self) -> str:
        return content_sha256(self)

    @property
    def eligible_for_formal_competition(self) -> bool:
        return self.readiness == ReproductionReadiness.REPRODUCTION_COMPLETE

    @property
    def has_canonical_fidelity_requirements(self) -> bool:
        return {item.requirement_id for item in self.requirements} == (
            CANONICAL_FIDELITY_REQUIREMENTS[self.method]
        )


O_STAR_PRIMARY_SOURCE_SHA256 = "56217bda3c44ccd751ec1eb9976f7d8a76813a61534f298ab43c2d7ccecf7ff9"
STREAK_PRIMARY_SOURCE_SHA256 = "6532a03a2ed0a0f0507eedbe40c3ee6fa576caf98472448c1cc3c4d3aee64dd6"


def current_o_star_reproduction_manifest(
    *,
    core_artifact_sha256: str,
) -> ExternalReproductionManifest:
    """Describe current O-STaR work without promoting the equation core."""

    source = O_STAR_PRIMARY_SOURCE_SHA256
    return ExternalReproductionManifest(
        method=ExternalMethod.O_STAR,
        reproduction_id="o-star-paper-audit@0.1",
        primary_source_url=(
            "https://www.hrl.uni-bonn.de/publications/2026/menon26grc/"
            "menon26grc_paper_poster.pdf/@@download/file"
        ),
        primary_source_sha256=source,
        requirements=(
            FidelityRequirement(
                requirement_id="primary-source-frozen",
                description="Official paper/poster bundle is content-addressed.",
                status=FidelityRequirementStatus.VERIFIED,
                evidence_artifact_sha256=source,
                note="Downloaded from the University of Bonn publication page.",
            ),
            FidelityRequirement(
                requirement_id="semantic-prior",
                description="LLM rank-to-probability Day-0 semantic prior.",
                status=FidelityRequirementStatus.MISSING,
                note=(
                    "Frozen-response-table route selected; table, raw archive, prompt, "
                    "candidate vocabulary, conversion, and cache-key artifacts are missing."
                ),
            ),
            FidelityRequirement(
                requirement_id="geometric-grounding",
                description="3D object-compartment feasibility pruning.",
                status=FidelityRequirementStatus.MISSING,
                note=(
                    "Recorded-3D-replay route selected; immutable replay, producer, geometry, "
                    "identity, group, and cost manifests are missing."
                ),
            ),
            FidelityRequirement(
                requirement_id="dirichlet-update-core",
                description="Dirichlet initialization, hit, miss, and Stay+Leak equations.",
                status=FidelityRequirementStatus.VERIFIED,
                evidence_artifact_sha256=core_artifact_sha256,
                note="Equation-level reference core and regression tests only.",
            ),
            FidelityRequirement(
                requirement_id="relaxed-transition-inference",
                description="Sparse-time relocation transition learning and propagation.",
                status=FidelityRequirementStatus.MISSING,
                note="The paper-level transition learner is not implemented.",
            ),
            FidelityRequirement(
                requirement_id="cost-aware-active-search",
                description="Navigation and articulated-container cost-aware active search.",
                status=FidelityRequirementStatus.MISSING,
                note="The selected recorded-replay cost and action manifests are not built.",
            ),
            FidelityRequirement(
                requirement_id="opportunistic-multi-target-perception",
                description="Non-target observations collected during target search.",
                status=FidelityRequirementStatus.MISSING,
                note="No O-STaR end-to-end perception/search adapter exists.",
            ),
            FidelityRequirement(
                requirement_id="published-result-recheck",
                description="Paper protocol rerun on HOMER+ and physical-search tracks.",
                status=FidelityRequirementStatus.MISSING,
                note="No published-result reproduction artifact exists.",
            ),
        ),
        readiness=ReproductionReadiness.EQUATION_CORE_ONLY,
    )


def current_streak_reproduction_manifest(
    *, reference_core_artifact_sha256: str
) -> ExternalReproductionManifest:
    """Describe the current STREAK gap from the full public paper specification."""

    source = STREAK_PRIMARY_SOURCE_SHA256
    return ExternalReproductionManifest(
        method=ExternalMethod.STREAK,
        reproduction_id="streak-paper-audit@0.1",
        primary_source_url="https://arxiv.org/pdf/2411.05549",
        primary_source_sha256=source,
        requirements=(
            FidelityRequirement(
                requirement_id="primary-source-frozen",
                description="STREAK arXiv v3 paper is content-addressed.",
                status=FidelityRequirementStatus.VERIFIED,
                evidence_artifact_sha256=source,
                note="The public v3 paper is the current reproduction authority.",
            ),
            FidelityRequirement(
                requirement_id="gtm-architecture",
                description="Underlying spatio-temporal object-dynamics GTM architecture.",
                status=FidelityRequirementStatus.MISSING,
                note=(
                    "Component-factored reproduction route selected; the static GTM first "
                    "stage and its acceptance artifact are missing."
                ),
            ),
            FidelityRequirement(
                requirement_id="streaming-graph-update",
                description="Sequential household graph-state update and future graph prediction.",
                status=FidelityRequirementStatus.MISSING,
                note="No executable STREAK graph model exists in this repository.",
            ),
            FidelityRequirement(
                requirement_id="three-part-model-loss",
                description="Node, location-edge, and context-embedding losses.",
                status=FidelityRequirementStatus.MISSING,
                note="No executable loss implementation exists.",
            ),
            FidelityRequirement(
                requirement_id="fisher-consolidation",
                description="Fisher-weighted previous-task parameter consolidation.",
                status=FidelityRequirementStatus.VERIFIED,
                evidence_artifact_sha256=reference_core_artifact_sha256,
                note="Equation-level named-parameter reference core and tests only.",
            ),
            FidelityRequirement(
                requirement_id="mean-feature-rehearsal",
                description="Mean Feature Criteria rehearsal with age-decayed buffer allocation.",
                status=FidelityRequirementStatus.VERIFIED,
                evidence_artifact_sha256=reference_core_artifact_sha256,
                note="Selection and task-age weighting reference core and tests only.",
            ),
            FidelityRequirement(
                requirement_id="independent-hyperparameter-search",
                description="Independent lambda, beta, epoch, and prediction-horizon search.",
                status=FidelityRequirementStatus.MISSING,
                note="The paper grid is known but has not run on a disjoint validation split.",
            ),
            FidelityRequirement(
                requirement_id="homer-sequential-recheck",
                description="Five-household 50-day train/10-day test sequential evaluation.",
                status=FidelityRequirementStatus.MISSING,
                note="No HOMER result-reproduction artifact exists.",
            ),
        ),
        readiness=ReproductionReadiness.EQUATION_CORE_ONLY,
    )


class DesignDecisionOption(ContractModel):
    option_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    consequence: str = Field(min_length=1)


class BlockingDesignDecision(ContractModel):
    decision_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    blocked_deliverables: tuple[str, ...] = Field(min_length=1)
    options: tuple[DesignDecisionOption, ...] = Field(min_length=1)
    selected_option_id: str | None = None

    @model_validator(mode="after")
    def validate_options(self) -> Self:
        ids = [item.option_id for item in self.options]
        if len(ids) != len(set(ids)):
            raise ValueError("design-decision option ids must be unique")
        if self.selected_option_id is not None and self.selected_option_id not in ids:
            raise ValueError("selected design option must belong to the decision")
        return self

    @property
    def route_selected(self) -> bool:
        return self.selected_option_id is not None


def current_blocking_design_decisions() -> tuple[BlockingDesignDecision, ...]:
    """Return the content-addressable choices that still block the evidence claims."""

    return (
        BlockingDesignDecision(
            decision_id="D-OAM-1",
            question="Which O-STaR input track is authoritative?",
            blocked_deliverables=("o-star-reproduction", "formal-comparison"),
            options=(
                DesignDecisionOption(
                    option_id="paper-native-3d",
                    description="Rebuild the paper-native 3D scene graph and physical costs.",
                    consequence="Supports end-to-end fidelity at the highest engineering cost.",
                ),
                DesignDecisionOption(
                    option_id="symbolic-surrogate",
                    description="Use declared geometry and cost surrogates on the symbolic graph.",
                    consequence="Supports only a matched algorithmic reproduction claim.",
                ),
                DesignDecisionOption(
                    option_id="dual-track",
                    description="Run symbolic death-test and paper-native 3D tracks.",
                    consequence="Preserves speed and fidelity at the highest maintenance cost.",
                ),
                DesignDecisionOption(
                    option_id="recorded-3d-replay",
                    description="Replay immutable 3D scene graphs and physical-cost inputs.",
                    consequence="Matches memory/search inputs without claiming live perception.",
                ),
            ),
            selected_option_id="recorded-3d-replay",
        ),
        BlockingDesignDecision(
            decision_id="D-OAM-2",
            question="Which O-STaR LLM-prior protocol is authoritative?",
            blocked_deliverables=("o-star-reproduction", "formal-comparison"),
            options=(
                DesignDecisionOption(
                    option_id="frozen-paper-style-call",
                    description="Freeze provider, model, prompt, rank conversion, and cache.",
                    consequence="Maximizes fidelity but adds a method-specific LLM protocol.",
                ),
                DesignDecisionOption(
                    option_id="shared-project-llm-protocol",
                    description="Use the common project LLM provenance protocol.",
                    consequence=(
                        "Improves matching but needs evidence that semantics remain intact."
                    ),
                ),
                DesignDecisionOption(
                    option_id="both-as-sensitivity",
                    description=(
                        "Use paper-style as faithful and shared protocol as enhanced tracks."
                    ),
                    consequence="Separates fidelity from enhancement with additional compute.",
                ),
                DesignDecisionOption(
                    option_id="frozen-response-table",
                    description="Freeze raw LLM responses and derived priors before test access.",
                    consequence="Removes online model drift while retaining full provenance.",
                ),
            ),
            selected_option_id="frozen-response-table",
        ),
        BlockingDesignDecision(
            decision_id="D-OAM-3",
            question="How should the STREAK GTM dependency be obtained?",
            blocked_deliverables=("streak-reproduction", "formal-comparison"),
            options=(
                DesignDecisionOption(
                    option_id="reconstruct-from-primary-paper",
                    description="Reconstruct GTM from its primary paper.",
                    consequence="Can proceed locally but retains interpretation risk.",
                ),
                DesignDecisionOption(
                    option_id="author-artifact-first",
                    description="Request author code, configuration, or checkpoints first.",
                    consequence=(
                        "Minimizes interpretation risk but remains blocked until they arrive."
                    ),
                ),
                DesignDecisionOption(
                    option_id="both-and-cross-check",
                    description="Independently reconstruct and cross-check author artifacts.",
                    consequence="Provides strongest fidelity evidence at the highest cost.",
                ),
                DesignDecisionOption(
                    option_id="component-factored-reproduction",
                    description="Reproduce GTM, bounds, CL components, then full STREAK in order.",
                    consequence=(
                        "Localizes discrepancies and forbids skipping failed prerequisites."
                    ),
                ),
            ),
            selected_option_id="component-factored-reproduction",
        ),
        BlockingDesignDecision(
            decision_id="D-OAM-4",
            question="What exact WP2-WP6 composition and write authority defines the full arm?",
            blocked_deliverables=(
                "full-oam-phm-arm",
                "formal-comparison",
                "opportunistic-observation-evidence",
                "anti-contamination-evidence",
            ),
            options=(
                DesignDecisionOption(
                    option_id="submit-wp2-wp6-freeze-manifest",
                    description=(
                        "Declare every component, change/consolidation authority, and final-stage "
                        "write permission."
                    ),
                    consequence=(
                        "This is structured design input; the scaffold cannot choose it without "
                        "changing the full method."
                    ),
                ),
                DesignDecisionOption(
                    option_id="governed-main+learned-sensitivity",
                    description=(
                        "Use the governed WP2-WP6 arm as main and a learned variant as sensitivity."
                    ),
                    consequence=(
                        "Preserves project governance while measuring its performance cost."
                    ),
                ),
            ),
            selected_option_id="governed-main+learned-sensitivity",
        ),
        BlockingDesignDecision(
            decision_id="D-OAM-5",
            question="Which criterion makes anti-contamination complexity worthwhile?",
            blocked_deliverables=("anti-contamination-worth-claim",),
            options=(
                DesignDecisionOption(
                    option_id="pareto-dominance",
                    description="Require no degradation in contamination, recovery, or utility.",
                    consequence="Avoids scalar weights and reports compute overhead separately.",
                ),
                DesignDecisionOption(
                    option_id="resource-capped-dominance",
                    description="Freeze a resource cap and require dominance within it.",
                    consequence="Makes deployability explicit but requires a resource cap now.",
                ),
                DesignDecisionOption(
                    option_id="predeclared-scalar-utility",
                    description="Freeze four-axis weights and a minimum meaningful net gain.",
                    consequence="Produces one number but is sensitive to value weights.",
                ),
                DesignDecisionOption(
                    option_id="non-inferiority-plus-superiority",
                    description="Require contamination superiority and non-inferiority guardrails.",
                    consequence=(
                        "Needs margins and a primary superiority threshold before evaluation."
                    ),
                ),
            ),
            selected_option_id="non-inferiority-plus-superiority",
        ),
        BlockingDesignDecision(
            decision_id="D-OAM-6",
            question="How are development and formal executions isolated?",
            blocked_deliverables=("hard-timeout-enforcement", "formal-comparison"),
            options=(
                DesignDecisionOption(
                    option_id="local-process-dev+container-formal",
                    description="Use a subprocess locally and an OCI container formally.",
                    consequence="Balances development speed with formal resource isolation.",
                ),
            ),
            selected_option_id="local-process-dev+container-formal",
        ),
        BlockingDesignDecision(
            decision_id="D-OAM-7",
            question="How is matched compute and embodied cost budgeted?",
            blocked_deliverables=("matched-compute-receipt", "formal-comparison"),
            options=(
                DesignDecisionOption(
                    option_id="budget-vector",
                    description="Cap tuning, online inference, and embodied-action dimensions.",
                    consequence=(
                        "Avoids invalid scalarization and requires every dimension to pass."
                    ),
                ),
            ),
            selected_option_id="budget-vector",
        ),
    )


class OStarReferenceConfig(ContractModel):
    """Paper-defined Dirichlet update parameters, deliberately not defaults."""

    initial_pseudocount_mass: float = Field(gt=0.0)
    hit_weight: float = Field(gt=0.0)
    miss_weight: float = Field(gt=0.0)
    leak_rate: Probability


class OStarReferenceBelief(ContractModel):
    """Equation-level O-STaR location belief, not an end-to-end reproduction."""

    location_order: tuple[str, ...] = Field(min_length=2)
    alpha: tuple[float, ...] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_state(self) -> Self:
        if len(self.location_order) != len(self.alpha):
            raise ValueError("O-STaR support and alpha vectors must align")
        if len(self.location_order) != len(set(self.location_order)):
            raise ValueError("O-STaR candidate locations must be unique")
        if any(value <= 0.0 or not isfinite(value) for value in self.alpha):
            raise ValueError("O-STaR alpha values must be finite and positive")
        return self

    @classmethod
    def initialize(
        cls,
        *,
        llm_prior: dict[str, float],
        geometrically_feasible_locations: frozenset[str],
        config: OStarReferenceConfig,
    ) -> Self:
        if not geometrically_feasible_locations:
            raise ValueError("geometric pruning removed every O-STaR candidate")
        if not geometrically_feasible_locations.issubset(llm_prior):
            raise ValueError("every feasible candidate needs an LLM-prior score")
        order = tuple(sorted(geometrically_feasible_locations))
        weights = tuple(llm_prior[key] for key in order)
        if any(value < 0.0 or not isfinite(value) for value in weights):
            raise ValueError("LLM-prior scores must be finite and non-negative")
        total = sum(weights)
        if total <= 0.0:
            raise ValueError("LLM-prior mass over feasible candidates must be positive")
        return cls(
            location_order=order,
            alpha=tuple(config.initial_pseudocount_mass * value / total for value in weights),
        )

    @property
    def posterior(self) -> dict[str, float]:
        total = sum(self.alpha)
        return {
            location: value / total
            for location, value in zip(self.location_order, self.alpha, strict=True)
        }

    def observe_hit(self, location: str, config: OStarReferenceConfig) -> Self:
        index = self._index(location)
        updated = list(self.alpha)
        updated[index] += config.hit_weight
        return self.model_copy(update={"alpha": tuple(updated)})

    def observe_miss(self, visited_location: str, config: OStarReferenceConfig) -> Self:
        """Apply the paper's fixed miss evidence equally to all other locations."""

        index = self._index(visited_location)
        increment = config.miss_weight / (len(self.alpha) - 1)
        updated = tuple(
            value if position == index else value + increment
            for position, value in enumerate(self.alpha)
        )
        return self.model_copy(update={"alpha": updated})

    def stay_and_leak(self, config: OStarReferenceConfig) -> Self:
        uniform_alpha = sum(self.alpha) / len(self.alpha)
        updated = tuple(
            (1.0 - config.leak_rate) * value + config.leak_rate * uniform_alpha
            for value in self.alpha
        )
        return self.model_copy(update={"alpha": updated})

    def cost_aware_order(self, search_cost: dict[str, float]) -> tuple[str, ...]:
        """Rank by posterior mass per positive declared search cost."""

        if set(search_cost) != set(self.location_order):
            raise ValueError("search costs must cover exactly the O-STaR candidate support")
        if any(value <= 0.0 or not isfinite(value) for value in search_cost.values()):
            raise ValueError("search costs must be finite and positive")
        posterior = self.posterior
        return tuple(
            sorted(
                self.location_order,
                key=lambda key: (-posterior[key] / search_cost[key], key),
            )
        )

    def _index(self, location: str) -> int:
        try:
            return self.location_order.index(location)
        except ValueError as error:
            raise KeyError(f"unknown O-STaR location: {location}") from error


class StreakReferenceConfig(ContractModel):
    consolidation_lambda: float = Field(gt=0.0)
    rehearsal_beta: float = Field(gt=0.0)
    epochs: int = Field(gt=0)
    prediction_horizon_minutes: int = Field(gt=0)
    batch_size: int = Field(default=1, gt=0)
    learning_rate: float = Field(default=1e-3, gt=0.0)
    activation: str = Field(default="relu", pattern=r"^relu$")


def streak_paper_parameter_candidates(
    *, prediction_horizon_minutes: tuple[int, ...]
) -> tuple[StreakReferenceConfig, ...]:
    """Build the unambiguous paper grid while making horizon parsing explicit."""

    if not prediction_horizon_minutes or any(
        horizon <= 0 for horizon in prediction_horizon_minutes
    ):
        raise ValueError("STREAK prediction horizons must be declared and positive")
    if len(prediction_horizon_minutes) != len(set(prediction_horizon_minutes)):
        raise ValueError("STREAK prediction horizons must be unique")
    return tuple(
        StreakReferenceConfig(
            consolidation_lambda=consolidation_lambda,
            rehearsal_beta=rehearsal_beta,
            epochs=epochs,
            prediction_horizon_minutes=horizon,
        )
        for consolidation_lambda, rehearsal_beta, epochs, horizon in product(
            (80.0, 100.0, 200.0),
            (5.0, 10.0, 15.0),
            (25, 50, 100),
            prediction_horizon_minutes,
        )
    )


def streak_fisher_consolidation_loss(
    *,
    current_parameters: dict[str, float],
    previous_parameters: dict[str, float],
    fisher_diagonal: dict[str, float],
    consolidation_lambda: float,
) -> float:
    """Compute STREAK Eq. 5 on a named diagonal-Fisher parameter state."""

    keys = set(current_parameters)
    if keys != set(previous_parameters) or keys != set(fisher_diagonal):
        raise ValueError("STREAK parameter and Fisher supports must match exactly")
    if not keys:
        raise ValueError("STREAK consolidation needs at least one parameter")
    values = (*current_parameters.values(), *previous_parameters.values())
    if any(not isfinite(value) for value in values):
        raise ValueError("STREAK parameters must be finite")
    if consolidation_lambda <= 0.0 or not isfinite(consolidation_lambda):
        raise ValueError("STREAK consolidation lambda must be finite and positive")
    if any(value < 0.0 or not isfinite(value) for value in fisher_diagonal.values()):
        raise ValueError("STREAK Fisher diagonal must be finite and non-negative")
    return (
        0.5
        * consolidation_lambda
        * sum(
            fisher_diagonal[key] * (current_parameters[key] - previous_parameters[key]) ** 2
            for key in sorted(keys)
        )
    )


def streak_rehearsal_weight(
    *, current_task_index: int, source_task_index: int, rehearsal_beta: float
) -> float:
    """Return the age-decayed dataset weight from STREAK Eq. 7."""

    if source_task_index < 0 or current_task_index < source_task_index:
        raise ValueError("STREAK task indices require 0 <= source <= current")
    if rehearsal_beta <= 0.0 or not isfinite(rehearsal_beta):
        raise ValueError("STREAK rehearsal beta must be finite and positive")
    return 1.0 / (rehearsal_beta * (current_task_index - source_task_index + 1))


def streak_mean_feature_selection(
    embeddings: dict[str, tuple[float, ...]], *, sample_count: int
) -> tuple[str, ...]:
    """Select samples nearest to the mean embedding with deterministic ties."""

    if not embeddings:
        raise ValueError("Mean Feature Criteria requires embeddings")
    if sample_count <= 0 or sample_count > len(embeddings):
        raise ValueError("sample_count must be within the available embedding count")
    dimensions = {len(value) for value in embeddings.values()}
    if len(dimensions) != 1 or next(iter(dimensions)) == 0:
        raise ValueError("STREAK embeddings need one shared positive dimension")
    if any(not isfinite(value) for vector in embeddings.values() for value in vector):
        raise ValueError("STREAK embeddings must be finite")
    dimension = next(iter(dimensions))
    centroid = tuple(
        fmean(vector[index] for vector in embeddings.values()) for index in range(dimension)
    )
    distance = {
        sample_id: sum((value - mean) ** 2 for value, mean in zip(vector, centroid, strict=True))
        for sample_id, vector in embeddings.items()
    }
    return tuple(sorted(embeddings, key=lambda key: (distance[key], key))[:sample_count])


class ComparisonArmRole(StrEnum):
    EXTERNAL_BASELINE = "external_baseline"
    INTERNAL_BASELINE = "internal_baseline"
    FULL_METHOD = "full_method"
    MATCHED_ABLATION = "matched_ablation"


class ArmExecutionBinding(ContractModel):
    """Content bindings an arm must attest before matched execution."""

    perception_input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    map_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    navigation_stack_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    language_model_protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    action_budget_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    compute_budget_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class FormalCompetitionArm(ContractModel):
    arm_id: str = Field(min_length=1)
    implementation_version: str = Field(min_length=1)
    role: ComparisonArmRole
    reproduction_manifest: ExternalReproductionManifest | None = None
    independently_tuned_selection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    execution_binding: ArmExecutionBinding

    @model_validator(mode="after")
    def validate_external_manifest(self) -> Self:
        if self.role == ComparisonArmRole.EXTERNAL_BASELINE and not self.reproduction_manifest:
            raise ValueError("external competition arms require a faithful reproduction manifest")
        if (
            self.role == ComparisonArmRole.EXTERNAL_BASELINE
            and self.reproduction_manifest
            and not self.reproduction_manifest.eligible_for_formal_competition
        ):
            raise ValueError("incomplete external reproductions cannot enter formal competition")
        if self.role != ComparisonArmRole.EXTERNAL_BASELINE and self.reproduction_manifest:
            raise ValueError("only external baseline arms may carry a reproduction manifest")
        return self

    @property
    def reproduction_manifest_sha256(self) -> str | None:
        if self.reproduction_manifest is None:
            return None
        return self.reproduction_manifest.content_sha256


class MatchedCompetitionProtocol(ContractModel):
    protocol_id: str = Field(min_length=1)
    validation_split_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sealed_test_split_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    perception_input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    map_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    navigation_stack_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    language_model_protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    action_budget_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    compute_budget_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    arms: tuple[FormalCompetitionArm, ...] = Field(min_length=2)
    test_access_count_before_tuning_complete: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_protocol(self) -> Self:
        if self.validation_split_sha256 == self.sealed_test_split_sha256:
            raise ValueError("validation and sealed test content must differ")
        ids = [arm.arm_id for arm in self.arms]
        if len(ids) != len(set(ids)):
            raise ValueError("formal competition arm ids must be unique")
        if self.test_access_count_before_tuning_complete:
            raise ValueError("test access before tuning completion invalidates the competition")
        if not any(arm.role == ComparisonArmRole.FULL_METHOD for arm in self.arms):
            raise ValueError("formal competition requires the full OAM-PHM arm")
        if not any(arm.role == ComparisonArmRole.EXTERNAL_BASELINE for arm in self.arms):
            raise ValueError("formal competition requires an external strong baseline")
        expected_binding = ArmExecutionBinding(
            perception_input_sha256=self.perception_input_sha256,
            map_sha256=self.map_sha256,
            navigation_stack_sha256=self.navigation_stack_sha256,
            language_model_protocol_sha256=self.language_model_protocol_sha256,
            action_budget_sha256=self.action_budget_sha256,
            compute_budget_sha256=self.compute_budget_sha256,
        )
        mismatched = [arm.arm_id for arm in self.arms if arm.execution_binding != expected_binding]
        if mismatched:
            raise ValueError(
                "competition arms are not bound to shared execution inputs and budgets: "
                + ", ".join(mismatched)
            )
        return self


class PairedObservationOutcome(ContractModel):
    """One matched episode under incidental-observation off/on intervention."""

    pair_id: str = Field(min_length=1)
    episode_id: str = Field(min_length=1)
    household_id: str = Field(min_length=1)
    object_family_id: str = Field(min_length=1)
    task_and_randomness_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    future_task_count: int = Field(gt=0)
    disabled_future_task_utility: float
    enabled_future_task_utility: float
    disabled_primary_task_cost: float = Field(ge=0.0)
    enabled_primary_task_cost: float = Field(ge=0.0)
    disabled_observation_count: int = Field(ge=0)
    enabled_observation_count: int = Field(ge=0)

    @field_validator(
        "disabled_future_task_utility",
        "enabled_future_task_utility",
        "disabled_primary_task_cost",
        "enabled_primary_task_cost",
    )
    @classmethod
    def finite_metrics(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("paired outcome metrics must be finite")
        return value

    @model_validator(mode="after")
    def validate_intervention(self) -> Self:
        if self.enabled_observation_count <= self.disabled_observation_count:
            raise ValueError("enabled arm must realize additional incidental observations")
        return self

    @property
    def future_utility_effect(self) -> float:
        return self.enabled_future_task_utility - self.disabled_future_task_utility

    @property
    def primary_task_cost_effect(self) -> float:
        return self.enabled_primary_task_cost - self.disabled_primary_task_cost


class ClusterAxis(StrEnum):
    EPISODE = "episode"
    HOUSEHOLD = "household"
    OBJECT_FAMILY = "object_family"


class ClusterBootstrapEstimate(ContractModel):
    estimand: str = Field(min_length=1)
    cluster_axis: ClusterAxis
    estimate: float
    confidence_interval_95: tuple[float, float]
    cluster_count: int = Field(gt=0)
    resamples: int = Field(ge=1000)
    seed: int = Field(ge=0)


def paired_cluster_bootstrap(
    outcomes: tuple[PairedObservationOutcome, ...],
    *,
    cluster_axis: ClusterAxis,
    metric: str,
    resamples: int = 2000,
    seed: int = 0,
) -> ClusterBootstrapEstimate:
    """Estimate a paired intervention effect without treating steps as IID."""

    if not outcomes:
        raise ValueError("paired cluster bootstrap requires outcomes")
    if len({item.pair_id for item in outcomes}) != len(outcomes):
        raise ValueError("paired outcome ids must be unique")
    metric_getters: dict[str, Callable[[PairedObservationOutcome], float]] = {
        "future_task_utility": lambda item: item.future_utility_effect,
        "primary_task_cost": lambda item: item.primary_task_cost_effect,
    }
    metric_getter = metric_getters.get(metric)
    if metric_getter is None:
        raise ValueError("unsupported paired observation estimand")
    cluster_getters: dict[ClusterAxis, Callable[[PairedObservationOutcome], str]] = {
        ClusterAxis.EPISODE: lambda item: item.episode_id,
        ClusterAxis.HOUSEHOLD: lambda item: item.household_id,
        ClusterAxis.OBJECT_FAMILY: lambda item: item.object_family_id,
    }
    cluster_getter = cluster_getters[cluster_axis]
    grouped: dict[str, list[float]] = defaultdict(list)
    for item in outcomes:
        grouped[cluster_getter(item)].append(metric_getter(item))
    cluster_means = {key: fmean(values) for key, values in grouped.items()}
    keys = sorted(cluster_means)
    rng = Random(seed)
    draws = sorted(fmean(cluster_means[rng.choice(keys)] for _ in keys) for _ in range(resamples))
    lower = draws[int(0.025 * (resamples - 1))]
    upper = draws[int(0.975 * (resamples - 1))]
    estimate = fmean(cluster_means.values())
    return ClusterBootstrapEstimate(
        estimand=metric,
        cluster_axis=cluster_axis,
        estimate=estimate,
        confidence_interval_95=(min(lower, estimate), max(upper, estimate)),
        cluster_count=len(keys),
        resamples=resamples,
        seed=seed,
    )


class AntiContaminationOutcome(ContractModel):
    """Matched full-vs-ablation evidence; no scalar complexity trade-off is assumed."""

    pair_id: str = Field(min_length=1)
    episode_id: str = Field(min_length=1)
    household_id: str = Field(min_length=1)
    full_owner_contamination: Probability
    ablated_owner_contamination: Probability
    full_recovery_latency: float = Field(ge=0.0)
    ablated_recovery_latency: float = Field(ge=0.0)
    full_action_utility: float
    ablated_action_utility: float
    full_compute_units: int = Field(gt=0)
    ablated_compute_units: int = Field(gt=0)
    matched_non_target_components_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("full_action_utility", "ablated_action_utility")
    @classmethod
    def finite_utility(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("action utility must be finite")
        return value


class ComplexityWorthDecisionStatus(StrEnum):
    AWAITING_USER_CRITERION = "awaiting_user_criterion"
    EVIDENCE_INCOMPLETE = "evidence_incomplete"
    CRITERION_SATISFIED = "criterion_satisfied"
    CRITERION_NOT_SATISFIED = "criterion_not_satisfied"


class ComplexityWorthEvidence(ContractModel):
    contamination_reduction: float
    recovery_latency_reduction: float
    action_utility_gain: float
    compute_overhead: float
    pair_count: int = Field(gt=0)
    decision_status: ComplexityWorthDecisionStatus
    decision_criterion_id: str | None = None


class AntiContaminationBootstrapReport(ContractModel):
    cluster_axis: ClusterAxis
    contamination_reduction: ClusterBootstrapEstimate
    recovery_latency_reduction: ClusterBootstrapEstimate
    action_utility_gain: ClusterBootstrapEstimate
    compute_overhead: ClusterBootstrapEstimate


def anti_contamination_cluster_bootstrap(
    outcomes: tuple[AntiContaminationOutcome, ...],
    *,
    cluster_axis: ClusterAxis,
    resamples: int = 2000,
    seed: int = 0,
) -> AntiContaminationBootstrapReport:
    """Cluster-bootstrap every matched benefit/cost axis without scalarizing it."""

    if not outcomes:
        raise ValueError("anti-contamination bootstrap requires outcomes")
    if len({item.pair_id for item in outcomes}) != len(outcomes):
        raise ValueError("anti-contamination pair ids must be unique")
    hashes = {item.matched_non_target_components_sha256 for item in outcomes}
    if len(hashes) != 1:
        raise ValueError("anti-contamination outcomes use unmatched non-target components")
    cluster_getters: dict[ClusterAxis, Callable[[AntiContaminationOutcome], str] | None] = {
        ClusterAxis.EPISODE: lambda item: item.episode_id,
        ClusterAxis.HOUSEHOLD: lambda item: item.household_id,
        ClusterAxis.OBJECT_FAMILY: None,
    }
    cluster_getter = cluster_getters[cluster_axis]
    if cluster_getter is None:
        raise ValueError("anti-contamination outcomes do not bind object-family clusters")
    metrics: dict[str, Callable[[AntiContaminationOutcome], float]] = {
        "contamination_reduction": lambda item: (
            item.ablated_owner_contamination - item.full_owner_contamination
        ),
        "recovery_latency_reduction": lambda item: (
            item.ablated_recovery_latency - item.full_recovery_latency
        ),
        "action_utility_gain": lambda item: item.full_action_utility - item.ablated_action_utility,
        "compute_overhead": lambda item: item.full_compute_units - item.ablated_compute_units,
    }

    def estimate(name: str) -> ClusterBootstrapEstimate:
        grouped: dict[str, list[float]] = defaultdict(list)
        getter = metrics[name]
        for item in outcomes:
            grouped[cluster_getter(item)].append(getter(item))
        cluster_means = {key: fmean(values) for key, values in grouped.items()}
        keys = sorted(cluster_means)
        rng = Random(seed)
        draws = sorted(
            fmean(cluster_means[rng.choice(keys)] for _ in keys) for _ in range(resamples)
        )
        point = fmean(cluster_means.values())
        return ClusterBootstrapEstimate(
            estimand=name,
            cluster_axis=cluster_axis,
            estimate=point,
            confidence_interval_95=(
                min(draws[int(0.025 * (resamples - 1))], point),
                max(draws[int(0.975 * (resamples - 1))], point),
            ),
            cluster_count=len(keys),
            resamples=resamples,
            seed=seed,
        )

    return AntiContaminationBootstrapReport(
        cluster_axis=cluster_axis,
        contamination_reduction=estimate("contamination_reduction"),
        recovery_latency_reduction=estimate("recovery_latency_reduction"),
        action_utility_gain=estimate("action_utility_gain"),
        compute_overhead=estimate("compute_overhead"),
    )


def summarize_anti_contamination(
    outcomes: tuple[AntiContaminationOutcome, ...],
    *,
    decision_criterion_id: str | None = None,
    criterion_satisfied: bool | None = None,
) -> ComplexityWorthEvidence:
    """Report the four trade-off axes while leaving their valuation explicit."""

    if not outcomes:
        raise ValueError("anti-contamination evidence requires matched outcomes")
    if len({item.pair_id for item in outcomes}) != len(outcomes):
        raise ValueError("anti-contamination pair ids must be unique")
    hashes = {item.matched_non_target_components_sha256 for item in outcomes}
    if len(hashes) != 1:
        raise ValueError("anti-contamination outcomes use unmatched non-target components")
    if (decision_criterion_id is None) != (criterion_satisfied is None):
        raise ValueError("criterion id and decision must be supplied together")
    if decision_criterion_id is None:
        status = ComplexityWorthDecisionStatus.AWAITING_USER_CRITERION
    else:
        status = (
            ComplexityWorthDecisionStatus.CRITERION_SATISFIED
            if criterion_satisfied
            else ComplexityWorthDecisionStatus.CRITERION_NOT_SATISFIED
        )
    return ComplexityWorthEvidence(
        contamination_reduction=fmean(
            item.ablated_owner_contamination - item.full_owner_contamination for item in outcomes
        ),
        recovery_latency_reduction=fmean(
            item.ablated_recovery_latency - item.full_recovery_latency for item in outcomes
        ),
        action_utility_gain=fmean(
            item.full_action_utility - item.ablated_action_utility for item in outcomes
        ),
        compute_overhead=fmean(
            item.full_compute_units - item.ablated_compute_units for item in outcomes
        ),
        pair_count=len(outcomes),
        decision_status=status,
        decision_criterion_id=decision_criterion_id,
    )
