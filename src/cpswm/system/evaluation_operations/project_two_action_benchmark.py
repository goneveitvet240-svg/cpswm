"""Project-two action benchmark v0.6 over replay episodes.

The full arm composes the existing prototype spine and feedback revision loop;
it does not reimplement CHEH, ORRER, PCHMP, feedback projection, or project-one
statistics.  Reference adapters are labelled by fidelity so reduced-skill
proxies can never be reported as faithful baselines.

The historical ``ProjectTwoActionBenchmarkV02`` class name remains as an API
compatibility alias; emitted reports carry the v0.6 protocol version.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from itertools import permutations
from math import isclose
from statistics import mean
from typing import Any, Literal, Protocol
from uuid import UUID, uuid4

from pydantic import Field, model_validator

from cpswm.contracts import (
    ActionOutcomeLikelihoodModel,
    ActionProbability,
    AttributedCause,
    ContractModel,
    DecisionContext,
    DecisionContextBinding,
    DecisionSurface,
    EventMechanism,
    MapConsistencyRevisions,
    OperatorDiagnostic,
    ProbabilityMass,
    ProjectOneRequestApplicationStatus,
    ProjectOneStatRequestTrace,
    ProjectTwoDatasetSplit,
    ProjectTwoReplayEpisode,
    ProjectTwoReplayStep,
    ProjectTwoRevisionActionTrace,
    RevisionActionOperator,
    RobotActionOutcome,
    RobotActionType,
    TargetPresenceBeliefRef,
    UUIDProbabilityMass,
    ValidTimeInterval,
    ordered_role_key,
    reject_truth_leakage,
)
from cpswm.system.continual.execution_feedback_projector import ExecutionFeedbackProjector
from cpswm.system.continual.project_one_regime_loop import PrototypeLoopConfig
from cpswm.system.counterfactual_event_hypergraph import (
    DamenHogg2012AMGMatchedEvidenceBaseline,
    ProjectTwoFeedbackRevisionLoop,
)
from cpswm.system.counterfactual_event_hypergraph.feedback_revision_loop import (
    ActorDiscriminationEvidence,
    FeedbackProvenanceError,
    TransitionRevisionModel,
    apply_project_one_request,
)
from cpswm.system.evaluation_operations.project_two_dataset import (
    ProjectTwoReplayDataset,
    enforce_project_two_replay_gate,
)
from cpswm.system.evaluation_operations.structure_two_search_utility import (
    ROUTE_A_DEVELOPMENT_UTILITY_CONTRACT_REFERENCE,
    ROUTE_A_FROZEN_ROUTE_REFERENCE,
    ROUTE_A_HARD_GUARDRAILS,
    ROUTE_A_OPTIMIZATION_DIRECTION,
    ROUTE_A_PRIMARY_UTILITY_CONTRACT_UNRESOLVED,
    ROUTE_A_PRIMARY_UTILITY_METRIC,
    ROUTE_A_UNRESOLVED_UTILITY_FIELDS,
    GuardrailObservation,
    MethodUtilityObservation,
    RouteADevelopmentUtilityContract,
    RouteAPrimaryUtilityDefinition,
    ScientificVerdict,
    SecondaryMetricObservation,
    current_route_a_development_utility_contract,
    evaluate_route_a_superiority,
    normalized_extra_inspection_regret,
)
from cpswm.system.prototype_spine import (
    ActionReadout,
    ActionReadoutConfig,
    CorePrototypeSpine,
    PrototypeStepResult,
    PrototypeTransition,
)
from cpswm.system.reproducibility import content_uuid
from cpswm.world_model.habits_transitions import PropensityCorrectionMode

BENCHMARK_VERSION = "project-two-action-benchmark@0.6-dual-timescale-readout"

#: What ``cumulative_action_regret`` is *actually* computed from today, stated
#: term by term so no reader has to infer it from the code.  Both terms are
#: dimensionless task regret in [0, 1] per step.  This development formula is
#: not a substitute for measured robot time, energy or monetary cost.
IMPLEMENTED_REGRET_COMPONENT_TERMS: tuple[str, ...] = (
    "put_back_error_count (0/1 per step, weight 1)",
    "normalized_extra_inspection_regret (0..1 per step, weight 1)",
)
IMPLEMENTED_REGRET_UNIT = "dimensionless task-regret units per episode (D0 development only)"

#: Search metrics this report emits that rest on constants no frozen protocol
#: registers.  Their numbers are preserved for historical reproducibility and
#: reported as unresolved rather than silently repriced.
UNREGISTERED_SEARCH_METRIC_ASSUMPTIONS: tuple[str, ...] = (
    "mean_search_time_seconds assumes 5.0 s per inspected container "
    "(constant not registered by any frozen protocol)",
    "mean search path records emitted-plan inspections only; it is a count, not a registered "
    "real-world cost",
    "mean_search_path_cost, mean_search_path_length and mean_search_cost are three names for "
    "one quantity: mean inspected containers per step",
)

PAPER_LEVEL_GATE_FAILURES: tuple[str, ...] = (
    f"{ROUTE_A_PRIMARY_UTILITY_CONTRACT_UNRESOLVED}: the D0 development formula is "
    "registered, but real task-cost calibration, the superiority margin and hard-guardrail "
    "thresholds remain unregistered for paper-level use",
    "D0 synthetic replay cannot establish real-world external validity",
    "AMG lacks source video likelihoods and source inference machinery for faithful reproduction",
    "O-STaR/DynaMem/STAR lack RGB-D, pose, voxel, caption, and embodied-skill inputs required "
    "for faithful reproduction",
)


class BenchmarkFidelity(StrEnum):
    FULL_PROJECT_TWO = "full_project_two"
    FAITHFUL_MATCHED = "faithful_matched"
    REDUCED_SKILL_PROXY = "reduced_skill_proxy"
    MATCHED_REPLAY_ADAPTER = "matched_replay_adapter"
    FULL_RERUN_CONTROL = "full_rerun_control"
    ORACLE_UPPER_BOUND = "oracle_upper_bound"


class ProjectTwoActionMethod(StrEnum):
    FREQUENCY = "independently_tuned_frequency"
    RECENCY = "independently_tuned_recency"
    MARKOV = "independently_tuned_markov"
    AMG_MATCHED = "damen_hogg_amg_matched_open_world"
    O_STAR = "o_star"
    DYNAMEM = "dynamem"
    STAR = "star"
    FULL_RERUN = "full_rerun_without_reversible_revision"
    PROJECT_TWO = "project_two_full_feedback_loop"
    ORACLE = "oracle_upper_bound"


FIDELITY: dict[ProjectTwoActionMethod, BenchmarkFidelity] = {
    ProjectTwoActionMethod.FREQUENCY: BenchmarkFidelity.FAITHFUL_MATCHED,
    ProjectTwoActionMethod.RECENCY: BenchmarkFidelity.FAITHFUL_MATCHED,
    ProjectTwoActionMethod.MARKOV: BenchmarkFidelity.FAITHFUL_MATCHED,
    # This is a generous object-relocation adaptation.  It does not reproduce
    # the source video likelihoods, RJMCMC-SA, or IP solver.
    ProjectTwoActionMethod.AMG_MATCHED: BenchmarkFidelity.MATCHED_REPLAY_ADAPTER,
    # These three are honest replay adapters to the repository's documented
    # reduced-skill implementations, not claims of external-code fidelity.
    ProjectTwoActionMethod.O_STAR: BenchmarkFidelity.MATCHED_REPLAY_ADAPTER,
    ProjectTwoActionMethod.DYNAMEM: BenchmarkFidelity.MATCHED_REPLAY_ADAPTER,
    ProjectTwoActionMethod.STAR: BenchmarkFidelity.MATCHED_REPLAY_ADAPTER,
    ProjectTwoActionMethod.FULL_RERUN: BenchmarkFidelity.FULL_RERUN_CONTROL,
    ProjectTwoActionMethod.PROJECT_TWO: BenchmarkFidelity.FULL_PROJECT_TWO,
    ProjectTwoActionMethod.ORACLE: BenchmarkFidelity.ORACLE_UPPER_BOUND,
}


class ValidationTuningTrial(ContractModel):
    parameters: dict[str, float | str]
    primary_utility_by_validation_episode: tuple[float, ...] = Field(min_length=1)
    mean_primary_utility: float = Field(ge=0.0)

    @model_validator(mode="after")
    def _mean_is_derived(self) -> ValidationTuningTrial:
        if not isclose(
            self.mean_primary_utility,
            mean(self.primary_utility_by_validation_episode),
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ValueError("validation tuning mean is not derived from its episode values")
        return self


class MethodTuningSelection(ContractModel):
    method: ProjectTwoActionMethod
    selection_metric: Literal["cumulative_action_regret"] = ROUTE_A_PRIMARY_UTILITY_METRIC
    parameter_space: tuple[dict[str, float | str], ...]
    selected_parameters: dict[str, float | str]
    validation_episode_ids: tuple[UUID, ...]
    validation_trials: tuple[ValidationTuningTrial, ...] = Field(min_length=1)
    test_episode_ids_seen: tuple[UUID, ...] = ()
    search_budget: int = Field(gt=0)

    @model_validator(mode="after")
    def _sealed(self) -> MethodTuningSelection:
        if self.test_episode_ids_seen:
            raise ValueError("test episodes cannot participate in tuning")
        if len(self.parameter_space) != self.search_budget:
            raise ValueError("tuning search budget must equal parameter-space size")
        if tuple(item.parameters for item in self.validation_trials) != self.parameter_space:
            raise ValueError("validation trials must cover the exact ordered parameter space")
        if any(
            len(item.primary_utility_by_validation_episode) != len(self.validation_episode_ids)
            for item in self.validation_trials
        ):
            raise ValueError("every tuning trial must cover every validation episode exactly once")
        selected = min(
            self.validation_trials,
            key=lambda item: (
                item.mean_primary_utility,
                json.dumps(item.parameters, sort_keys=True),
            ),
        ).parameters
        if self.selected_parameters != selected:
            raise ValueError("selected parameters are not the validation primary-utility optimum")
        return self


class ActionCaseMetric(ContractModel):
    episode_id: UUID
    method: ProjectTwoActionMethod
    step_count: int = Field(ge=0)
    put_back_error_rate: float = Field(ge=0.0, le=1.0)
    persistent_owner_mode_error_rate: float = Field(ge=0.0, le=1.0)
    cumulative_put_back_regret: float = Field(ge=0.0)
    cumulative_search_regret: float = Field(ge=0.0)
    cumulative_action_regret: float = Field(ge=0.0)
    owner_habit_contamination: float = Field(ge=0.0)
    incorrect_statistic_recovery_cost: float = Field(ge=0.0)
    search_error_rate: float = Field(ge=0.0, le=1.0)
    search_success_rate: float = Field(ge=0.0, le=1.0)
    mean_search_path_cost: float = Field(ge=0.0)
    mean_search_path_length: float = Field(ge=0.0)
    mean_search_time_seconds: float = Field(ge=0.0)
    mean_search_cost: float = Field(ge=0.0)
    late_feedback_recovery_latency: float = Field(ge=0.0)
    unnecessary_revision_count: int = Field(ge=0)
    unknown_calibration_brier: float = Field(ge=0.0)
    provenance_dedup_rejection_correctness: float = Field(ge=0.0, le=1.0)
    full_feedback_revision_calls: int = Field(ge=0)
    project_one_stat_requests: int = Field(ge=0)
    project_one_stat_applications: int = Field(ge=0)
    project_one_stat_rejections: int = Field(ge=0)
    project_one_stat_deferred: int = Field(default=0, ge=0)
    project_one_stat_replay_noops: int = Field(default=0, ge=0)
    revision_action_traces: tuple[ProjectTwoRevisionActionTrace, ...] = ()
    visible_input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class AggregateMetric(ContractModel):
    method: ProjectTwoActionMethod
    fidelity: BenchmarkFidelity
    metric: str
    value: float
    value_confidence_interval_95: tuple[float, float]
    worst_group_value: float
    paired_difference_vs_project_two: float | None = None
    confidence_interval_95: tuple[float, float] | None = None
    statistically_significant: bool | None = None
    engineering_significant: bool | None = None


class ProjectTwoActionBenchmarkReport(ContractModel):
    benchmark_version: Literal["project-two-action-benchmark@0.6-dual-timescale-readout"] = (
        "project-two-action-benchmark@0.6-dual-timescale-readout"
    )
    dataset_version: str
    train_episode_ids: tuple[UUID, ...]
    validation_episode_ids: tuple[UUID, ...]
    sealed_test_episode_ids: tuple[UUID, ...]
    action_budget_per_episode: int
    observation_coverage_by_episode: dict[UUID, float]
    tuning: tuple[MethodTuningSelection, ...]
    case_metrics: tuple[ActionCaseMetric, ...]
    aggregate_metrics: tuple[AggregateMetric, ...]
    fairness_visible_hashes: dict[UUID, str]
    complete_chain: tuple[str, ...]
    scientific_status: str
    superiority_supported: bool
    limitations: tuple[str, ...]
    baseline_fairness: tuple[BaselineFairnessRecord, ...]
    paper_level_gate_failures: tuple[str, ...]
    development_utility_contract: RouteADevelopmentUtilityContract
    primary_utility_definition: RouteAPrimaryUtilityDefinition
    scientific_verdict: ScientificVerdict
    development_primary_utility_evaluated: Literal[True] = True
    route_a_primary_utility_evaluated: bool
    unresolved_utility_contract_fields: tuple[str, ...]
    unregistered_search_metric_assumptions: tuple[str, ...]

    @model_validator(mode="after")
    def _verdict_is_the_only_authority(self) -> ProjectTwoActionBenchmarkReport:
        split_sets = tuple(
            set(items)
            for items in (
                self.train_episode_ids,
                self.validation_episode_ids,
                self.sealed_test_episode_ids,
            )
        )
        if any(
            split_sets[left] & split_sets[right]
            for left in range(len(split_sets))
            for right in range(left + 1, len(split_sets))
        ):
            raise ValueError("train, validation and sealed-test episodes must be disjoint")
        evaluated_episode_ids = (*self.validation_episode_ids, *self.sealed_test_episode_ids)
        expected_hash_keys = set(evaluated_episode_ids)
        if set(self.fairness_visible_hashes) != expected_hash_keys:
            raise ValueError("fairness visible hashes must cover validation and test exactly")
        if set(self.observation_coverage_by_episode) != expected_hash_keys:
            raise ValueError("observation coverage must cover validation and test exactly")
        if any(
            len(value) != 64 or any(character not in "0123456789abcdef" for character in value)
            for value in self.fairness_visible_hashes.values()
        ):
            raise ValueError("fairness visible hash is not a lowercase SHA-256 digest")
        if any(
            isinstance(value, bool) or not 0.0 <= value <= 1.0
            for value in self.observation_coverage_by_episode.values()
        ):
            raise ValueError("observation coverage must be numeric and lie in [0, 1]")
        expected_tuning_methods = tuple(
            method
            for method in ProjectTwoActionMethod
            if method is not ProjectTwoActionMethod.ORACLE
        )
        if tuple(tuning_item.method for tuning_item in self.tuning) != expected_tuning_methods:
            raise ValueError("tuning records must cover every non-oracle method exactly once")
        for tuning_item in self.tuning:
            if tuning_item.validation_episode_ids != self.validation_episode_ids:
                raise ValueError("tuning record substituted the registered validation episodes")
            if tuning_item.parameter_space != PARAMETER_SPACE[tuning_item.method]:
                raise ValueError("tuning record substituted the registered parameter space")
        expected_case_keys = tuple(
            (episode_id, method)
            for episode_id in self.sealed_test_episode_ids
            for method in ProjectTwoActionMethod
        )
        case_keys = tuple(
            (case_item.episode_id, case_item.method) for case_item in self.case_metrics
        )
        if case_keys != expected_case_keys:
            raise ValueError("case rows must cover sealed episode x method exactly once in order")
        if any(
            case_item.visible_input_hash != self.fairness_visible_hashes[case_item.episode_id]
            for case_item in self.case_metrics
        ):
            raise ValueError("case row visible hash disagrees with the fairness registry")
        if self.development_utility_contract.paper_claim_allowed:
            raise ValueError("the D0 development utility contract cannot authorize a paper claim")
        if self.development_utility_contract != current_route_a_development_utility_contract():
            raise ValueError("the report's development utility contract is not the registered one")
        if (
            self.primary_utility_definition.development_contract_id
            != self.development_utility_contract.contract_id
        ):
            raise ValueError("primary utility definition is not bound to its development contract")
        if self.development_primary_utility_evaluated is not True:
            raise ValueError("the v0.6 benchmark must evaluate its registered development utility")
        for case_item in self.case_metrics:
            if not isclose(
                case_item.cumulative_action_regret,
                case_item.cumulative_put_back_regret + case_item.cumulative_search_regret,
                rel_tol=0.0,
                abs_tol=1e-9,
            ):
                raise ValueError("case action regret does not equal its registered components")
        aggregate_keys = [(item.method, item.metric) for item in self.aggregate_metrics]
        if len(aggregate_keys) != len(set(aggregate_keys)):
            raise ValueError("aggregate metric identities must be unique")
        expected_aggregates = tuple(
            ProjectTwoActionBenchmarkV02()._aggregate(list(self.case_metrics))
        )
        if self.aggregate_metrics != expected_aggregates:
            raise ValueError("aggregate metrics are not fully derived from the sealed case rows")
        expected_references = tuple(
            method.value
            for method in ProjectTwoActionMethod
            if method not in {ProjectTwoActionMethod.PROJECT_TWO, ProjectTwoActionMethod.ORACLE}
        )
        if self.scientific_verdict.reference_methods != expected_references:
            raise ValueError("scientific verdict omits or substitutes a registered reference arm")
        aggregate_primary = {
            item.method: item.value
            for item in self.aggregate_metrics
            if item.metric == ROUTE_A_PRIMARY_UTILITY_METRIC
        }
        if set(aggregate_primary) != set(ProjectTwoActionMethod):
            raise ValueError("aggregate primary utility does not cover every registered method")
        for method in ProjectTwoActionMethod:
            case_values = [
                item.cumulative_action_regret for item in self.case_metrics if item.method is method
            ]
            if not case_values or not isclose(
                aggregate_primary[method], mean(case_values), rel_tol=0.0, abs_tol=1e-9
            ):
                raise ValueError("aggregate primary utility is not derived from case metrics")
        best_method = min(
            (
                method
                for method in ProjectTwoActionMethod
                if method not in {ProjectTwoActionMethod.PROJECT_TWO, ProjectTwoActionMethod.ORACLE}
            ),
            key=lambda method: (aggregate_primary[method], method.value),
        )
        if best_method.value not in self.scientific_verdict.primary_utility_comparison:
            raise ValueError("scientific verdict does not name the actual best reference arm")
        if self.superiority_supported and not self.scientific_verdict.superiority_authorized:
            raise ValueError(
                "superiority cannot be reported while the route-A verdict withholds it"
            )
        if self.route_a_primary_utility_evaluated != (not self.unresolved_utility_contract_fields):
            raise ValueError("route-A evaluation status must match the unresolved contract fields")
        if (
            self.unresolved_utility_contract_fields
            != self.primary_utility_definition.unresolved_contract_fields
        ):
            raise ValueError("report and primary definition disagree on unresolved utility fields")
        if self.superiority_supported and self.unresolved_utility_contract_fields:
            raise ValueError("superiority cannot be reported while the utility contract is open")
        if self.primary_utility_definition.primary_utility_metric != ROUTE_A_PRIMARY_UTILITY_METRIC:
            raise ValueError(
                "the frozen route's primary utility is "
                f"{ROUTE_A_PRIMARY_UTILITY_METRIC!r}; a secondary metric cannot be promoted "
                "into its place"
            )
        if (
            self.scientific_verdict.primary_utility_metric
            != self.primary_utility_definition.primary_utility_metric
        ):
            raise ValueError("the verdict must be decided on the declared primary utility")
        if self.primary_utility_definition.optimization_direction != (
            ROUTE_A_OPTIMIZATION_DIRECTION
        ):
            raise ValueError("the frozen route minimizes its primary utility")
        expected_definition = ProjectTwoActionBenchmarkV02._primary_utility_definition(
            list(self.aggregate_metrics), self.development_utility_contract
        )
        if self.primary_utility_definition != expected_definition:
            raise ValueError(
                "primary utility definition is not derived from the registered contract"
            )
        if self.paper_level_gate_failures != PAPER_LEVEL_GATE_FAILURES:
            raise ValueError("paper-level gates were erased, substituted or reordered")
        if self.unregistered_search_metric_assumptions != UNREGISTERED_SEARCH_METRIC_ASSUMPTIONS:
            raise ValueError("unregistered search assumptions were erased or substituted")
        if self.baseline_fairness != _expected_baseline_fairness():
            raise ValueError("baseline fairness identities or fidelity declarations were altered")
        engineering_superiority = _development_engineering_superiority(self.aggregate_metrics)
        expected_verdict = ProjectTwoActionBenchmarkV02._route_a_verdict(
            list(self.aggregate_metrics),
            definition=expected_definition,
            paper_gate_failures=PAPER_LEVEL_GATE_FAILURES,
            engineering_superiority=engineering_superiority,
        )
        if self.scientific_verdict != expected_verdict:
            raise ValueError("scientific verdict is not derived from report metrics and gates")
        expected_superiority = (
            engineering_superiority
            and not PAPER_LEVEL_GATE_FAILURES
            and expected_verdict.superiority_authorized
            and expected_definition.route_a_primary_utility_evaluated
        )
        if self.superiority_supported != expected_superiority:
            raise ValueError("superiority output is not derived from the registered verdict")
        expected_status = (
            "paper-level superiority supported"
            if expected_superiority
            else "paper-level superiority NOT supported; " + expected_verdict.summary
        )
        if self.scientific_status != expected_status:
            raise ValueError("scientific status is not derived from the registered verdict")
        return self


class BaselineFairnessRecord(ContractModel):
    method: ProjectTwoActionMethod
    fidelity: BenchmarkFidelity
    independently_tuned: bool
    tuning_budget: int = Field(gt=0)
    same_visible_stream: bool
    same_feedback_stream: bool
    same_action_budget: bool
    missing_faithful_inputs: tuple[str, ...] = ()
    qualifies_for_paper_superiority: bool


def _development_engineering_superiority(
    aggregates: tuple[AggregateMetric, ...] | list[AggregateMetric],
) -> bool:
    """Check the D0 primary metric against every registered non-oracle arm."""

    candidate = next(
        item
        for item in aggregates
        if item.method is ProjectTwoActionMethod.PROJECT_TWO
        and item.metric == ROUTE_A_PRIMARY_UTILITY_METRIC
    )
    references = [
        item
        for item in aggregates
        if item.method not in {ProjectTwoActionMethod.PROJECT_TWO, ProjectTwoActionMethod.ORACLE}
        and item.metric == ROUTE_A_PRIMARY_UTILITY_METRIC
    ]
    if not references:
        return False
    best = min(references, key=lambda item: (item.value, item.method.value))
    return bool(
        candidate.value < best.value
        and best.paired_difference_vs_project_two is not None
        and best.paired_difference_vs_project_two > 0
        and best.confidence_interval_95 is not None
        and best.confidence_interval_95[0] > 0
    )


def _missing_faithful_inputs(method: ProjectTwoActionMethod) -> tuple[str, ...]:
    if method in {
        ProjectTwoActionMethod.O_STAR,
        ProjectTwoActionMethod.DYNAMEM,
        ProjectTwoActionMethod.STAR,
    }:
        return (
            "RGB-D frames",
            "camera/robot poses",
            "3D voxel memory",
            "language captions/queries",
            "navigation/manipulation skill observations",
        )
    if method is ProjectTwoActionMethod.AMG_MATCHED:
        return (
            "learned Damen-Hogg source likelihoods",
            "source RJMCMC-SA or integer-programming inference",
        )
    return ()


def _expected_baseline_fairness() -> tuple[BaselineFairnessRecord, ...]:
    common_budget = len(next(iter(PARAMETER_SPACE.values())))
    paper_fidelities = {
        BenchmarkFidelity.FAITHFUL_MATCHED,
        BenchmarkFidelity.FULL_RERUN_CONTROL,
    }
    return tuple(
        BaselineFairnessRecord(
            method=method,
            fidelity=FIDELITY[method],
            independently_tuned=(method is not ProjectTwoActionMethod.ORACLE),
            tuning_budget=(
                common_budget
                if method is ProjectTwoActionMethod.ORACLE
                else len(PARAMETER_SPACE[method])
            ),
            same_visible_stream=True,
            same_feedback_stream=True,
            same_action_budget=True,
            missing_faithful_inputs=_missing_faithful_inputs(method),
            qualifies_for_paper_superiority=FIDELITY[method] in paper_fidelities,
        )
        for method in ProjectTwoActionMethod
    )


@dataclass(slots=True)
class _Prediction:
    put_back: UUID
    search_order: tuple[UUID, ...]
    unknown_probability: float = 0.0


class _ReplayMethod(Protocol):
    revision_calls: int
    project_one_requests: int
    project_one_applications: int
    rejected_feedback: int
    unnecessary_revisions: int
    project_one_rejections: int

    def observe(self, step: ProjectTwoReplayStep) -> None: ...
    def predict(self) -> _Prediction: ...
    def feedback(self, step: ProjectTwoReplayStep) -> None: ...


class _CountMethod:
    def __init__(self, episode: ProjectTwoReplayEpisode, *, mode: str, parameter: float) -> None:
        self.episode = episode
        self.mode = mode
        self.parameter = parameter
        self.locations = _locations(episode)
        self.counts: dict[UUID, float] = defaultdict(
            float,
            {location: parameter for location in self.locations} if mode == "frequency" else {},
        )
        self.last: UUID | None = None
        self.last_confidence = 0.0
        self.transitions: dict[UUID, dict[UUID, float]] = defaultdict(lambda: defaultdict(float))
        self.previous: UUID | None = None
        self.log: list[tuple[UUID, float]] = []
        self.revision_calls = self.project_one_requests = self.project_one_applications = 0
        self.rejected_feedback = self.unnecessary_revisions = 0
        self.project_one_rejections = 0

    def observe(self, step: ProjectTwoReplayStep) -> None:
        if step.before is None or step.after is None or step.after.detected_location_id is None:
            return
        location = step.after.detected_location_id
        if self.mode in {"recency", "o_star", "star"}:
            for key in tuple(self.counts):
                self.counts[key] *= self.parameter
        self.counts[location] += 1.0
        self.log.append((location, 1.0))
        if self.previous is not None:
            self.transitions[self.previous][location] += 1.0
        self.previous = location
        self.last = location
        self.last_confidence = step.detection_confidence or 0.0

    def predict(self) -> _Prediction:
        if self.mode == "dynamem" and self.last is not None:
            put_back = (
                self.last
                if self.last_confidence >= self.parameter
                else _argmax(self.locations, self.counts)
            )
        elif self.mode == "markov" and self.last is not None and self.transitions[self.last]:
            scores = {
                location: self.transitions[self.last][location]
                + self.parameter * self.counts[location]
                for location in self.locations
            }
            put_back = _argmax(self.locations, scores)
        else:
            put_back = _argmax(self.locations, self.counts)
        search_first = self.last or put_back
        ranking = (
            search_first,
            *tuple(loc for loc in _rank(self.locations, self.counts) if loc != search_first),
        )
        return _Prediction(put_back=put_back, search_order=ranking)

    def feedback(self, step: ProjectTwoReplayStep) -> None:
        del step


class _AMGOpenWorldMethod(_CountMethod):
    """Matched open-world evidence adaptation: soft owner/unknown weighted counts."""

    def __init__(self, episode: ProjectTwoReplayEpisode, *, mode: str, parameter: float) -> None:
        super().__init__(episode, mode=mode, parameter=parameter)
        self.amg = DamenHogg2012AMGMatchedEvidenceBaseline()
        self.amg_owner_location: UUID | None = None

    def observe(self, step: ProjectTwoReplayStep) -> None:
        if step.before is None or step.after is None or step.after.detected_location_id is None:
            return
        location = step.after.detected_location_id
        actors = self.episode.resident_actor_keys
        actor_probabilities = (
            dict(step.actor_evidence.actor_posterior)
            if step.actor_evidence is not None
            else {actor: 1.0 / len(actors) for actor in actors}
        )
        actor_priors = (
            dict(step.actor_evidence.reference_actor_prior)
            if step.actor_evidence is not None
            else {actor: 1.0 / len(actors) for actor in actors}
        )
        # AMG consumes binary event evidence through log-odds.  A categorical
        # posterior is therefore first prior-corrected into an evidence ratio,
        # then mapped to (0, 1); passing the posterior directly double-counts
        # actor priors and creates a favorable interface for this baseline.
        actor_likelihoods: dict[str, float] = {}
        for key, posterior in actor_probabilities.items():
            prior = max(1e-12, actor_priors.get(key, 1.0 / len(actor_probabilities)))
            evidence_ratio = max(1e-12, posterior) / prior
            actor_likelihoods[key] = evidence_ratio / (1.0 + evidence_ratio)
        mechanism_probabilities = (
            dict(step.mechanism_evidence.mechanism_posterior)
            if step.mechanism_evidence is not None
            else {
                EventMechanism.DIRECT_RELOCATION: 0.5,
                EventMechanism.HANDOFF_RELOCATION: 0.5,
            }
        )
        roles = {pair: self.parameter for pair in permutations(actors, 2)}
        if step.ordered_role_evidence is not None:
            from cpswm.contracts import parse_ordered_role_key

            for key, value in step.ordered_role_evidence.ordered_role_posterior.items():
                roles[parse_ordered_role_key(key)] = min(1.0 - 1e-6, max(1e-6, value))
        try:
            prediction = self.amg.predict_matched(
                before=step.before,
                after=step.after,
                actor_event_likelihoods={
                    key: min(1.0 - 1e-6, max(1e-6, value))
                    for key, value in actor_likelihoods.items()
                },
                mechanism_likelihoods=mechanism_probabilities,
                handoff_role_likelihoods=roles,
            )
        except ValueError:
            return
        self.last = location
        # A label-dependent selected representative is not action evidence when
        # multiple responsible actors share the exact MAP score.
        if set(prediction.maximizing_responsible_actor_keys) == {self.episode.owner_actor_key}:
            self.amg_owner_location = location

    def predict(self) -> _Prediction:
        put_back = self.amg_owner_location or _argmax(self.locations, self.counts)
        search_first = self.last or put_back
        order = (search_first, *tuple(item for item in self.locations if item != search_first))
        return _Prediction(put_back, order, unknown_probability=0.2)


class _FullRerunMethod(_CountMethod):
    """Rebuild statistics from the entire visible log after every feedback."""

    def feedback(self, step: ProjectTwoReplayStep) -> None:
        if not step.execution_feedback:
            return
        success = mean(
            item.outcome_distribution.get(RobotActionOutcome.SUCCESS, 0.0)
            for item in step.execution_feedback
        )
        if self.log and success < self.parameter:
            location, _weight = self.log[-1]
            self.log[-1] = (location, 0.0)
        accepted: list[tuple[UUID, float]] = []
        for location, weight in self.log:
            accepted.append((location, weight))
        # Full rerun is deliberately O(N); it has no reversible revision index.
        self.counts.clear()
        for location, weight in accepted:
            self.counts[location] += weight


class _FullProjectTwoMethod:
    """Existing full spine + real feedback loop + explicit project-one requests."""

    def __init__(
        self,
        episode: ProjectTwoReplayEpisode,
        *,
        owner_threshold: float,
        evidence_transform: Callable[[ProjectTwoReplayStep], ProjectTwoReplayStep] | None = None,
        actor_prior_transform: (
            Callable[[ProjectTwoReplayStep, Mapping[str, float]], Mapping[str, float]] | None
        ) = None,
        feedback_mode: str = "success_and_failure",
        apply_project_one_revisions: bool = True,
        unresolved_probability: float = 0.1,
        message_passing: Any | None = None,
        loop_config: PrototypeLoopConfig | None = None,
        rgrc_gate_enabled: bool = True,
        revision_strategy: str = "orrer",
        include_unknown_actor: bool = True,
        likelihood_calibration: float = 1.0,
        actor_evidence_weight: float = 1.0,
        mechanism_evidence_weight: float = 1.0,
        role_evidence_weight: float = 1.0,
        pchmp_evidence_weight: float = 1.0,
        unknown_actor_prior: float | None = None,
        unknown_mechanism_prior: float | None = None,
        orrer_retraction_threshold: float = 0.0,
        orrer_reactivation_threshold: float = 0.5,
        action_utility_threshold: float = 0.0,
        action_readout: ActionReadoutConfig | None = None,
        propensity_correction_mode: PropensityCorrectionMode = PropensityCorrectionMode.INVERSE,
    ) -> None:
        self.episode = episode
        self.locations = _locations(episode)
        self.owner_threshold = owner_threshold
        self.message_passing = message_passing
        self.loop_config = loop_config or PrototypeLoopConfig(
            owner_evidence_threshold=owner_threshold
        )
        self.rgrc_gate_enabled = rgrc_gate_enabled
        self.revision_strategy = revision_strategy
        self.include_unknown_actor = include_unknown_actor
        self.likelihood_calibration = likelihood_calibration
        self.actor_evidence_weight = actor_evidence_weight
        self.mechanism_evidence_weight = mechanism_evidence_weight
        self.role_evidence_weight = role_evidence_weight
        self.pchmp_evidence_weight = pchmp_evidence_weight
        self.unknown_actor_prior = unknown_actor_prior
        self.unknown_mechanism_prior = unknown_mechanism_prior
        self.orrer_retraction_threshold = orrer_retraction_threshold
        self.orrer_reactivation_threshold = orrer_reactivation_threshold
        self.action_utility_threshold = action_utility_threshold
        self.action_readout = action_readout or ActionReadoutConfig()
        self.propensity_correction_mode = propensity_correction_mode
        self.spine = CorePrototypeSpine(
            owner_key=episode.owner_actor_key,
            object_instance_id=episode.steps[0].object_instance_id,
            locations=self.locations,
            authorization_scope_id=uuid4(),
            loop_config=self.loop_config,
            message_passing=message_passing,
            rgrc_gate_enabled=rgrc_gate_enabled,
            action_readout=self.action_readout,
            correction_mode=propensity_correction_mode,
        )
        self.feedback_loop = ProjectTwoFeedbackRevisionLoop(
            projector=ExecutionFeedbackProjector(),
            retraction_threshold=orrer_retraction_threshold,
            reactivation_threshold=orrer_reactivation_threshold,
        )
        self.evidence_transform = evidence_transform or (lambda step: step)
        self.actor_prior_transform = actor_prior_transform
        self.feedback_mode = feedback_mode
        self.apply_project_one_revisions = apply_project_one_revisions
        self.unresolved_probability = unresolved_probability
        self.histories: dict[UUID, Any] = {}
        self.step_results: dict[UUID, Any] = {}
        self.last_location = self.locations[0]
        self.suggested = self.locations[0]
        self.unknown_probability = 1.0
        self.revision_calls = self.project_one_requests = self.project_one_applications = 0
        self.rejected_feedback = self.unnecessary_revisions = 0
        self.project_one_rejections = 0
        self.project_one_deferred = 0
        self.project_one_replay_noops = 0
        self.revision_action_traces: list[ProjectTwoRevisionActionTrace] = []
        self._pending_trace_indices: list[int] = []
        self._prediction_index = 0
        self._observed_steps: list[ProjectTwoReplayStep] = []
        self.formal_evidence_records_consumed = 0

    def observe(self, step: ProjectTwoReplayStep) -> None:
        step = self.evidence_transform(step)
        if step.unified_evidence is not None:
            self.formal_evidence_records_consumed += 1
        if step.before is None or step.after is None or step.observation_opportunity is None:
            return
        evidence = tuple(
            item
            for item in (
                self._weighted_axis_evidence(
                    step.actor_evidence,
                    self.actor_evidence_weight * self.pchmp_evidence_weight,
                ),
                self._weighted_axis_evidence(
                    step.mechanism_evidence,
                    self.mechanism_evidence_weight * self.pchmp_evidence_weight,
                    unknown_prior=self.unknown_mechanism_prior,
                ),
                self._weighted_axis_evidence(
                    step.ordered_role_evidence,
                    self.role_evidence_weight * self.pchmp_evidence_weight,
                ),
            )
            if item is not None
        )
        actors = tuple(
            actor
            for actor in self.episode.resident_actor_keys
            if self.include_unknown_actor or actor != "unknown_actor"
        )
        if self.unknown_actor_prior is not None and "unknown_actor" in actors:
            known = tuple(actor for actor in actors if actor != "unknown_actor")
            prior = {
                actor: (
                    self.unknown_actor_prior
                    if actor == "unknown_actor"
                    else (1.0 - self.unknown_actor_prior) / max(len(known), 1)
                )
                for actor in actors
            }
        else:
            prior = {actor: 1.0 / len(actors) for actor in actors}
        if self.actor_prior_transform is not None:
            prior = dict(self.actor_prior_transform(step, prior))
            if set(prior) != set(actors) or abs(sum(prior.values()) - 1.0) > 1e-6:
                raise ValueError("actor prior transform must normalize over resident actors")
        result = self.spine.process_transition(
            PrototypeTransition(
                opportunity=step.observation_opportunity,
                before=step.before,
                after=step.after,
                actor_prior=prior,
                evidence=evidence,
                context_key="replay",
                context_value=float(step.timestamp.weekday()) / 6.0,
                unresolved_probability=self.unresolved_probability,
            )
        )
        self.histories[step.step_id] = result.event_history
        self.step_results[step.step_id] = result
        self.suggested = result.suggested_location_id
        self.last_location = step.after.detected_location_id or self.last_location
        self.unknown_probability = result.actor_posterior.get("unknown_actor", 0.0)
        self._observed_steps.append(step)
        # A transition may promote a corrected event that CCRR had quarantined.
        # Refresh its originating trace before the next real planner call.
        self._refresh_application_receipts()

    def predict(self) -> _Prediction:
        snapshot = self.spine.current_snapshot
        distribution = self.spine.action_location_distribution(
            snapshot, readout=self.action_readout
        )
        action_distribution = self._next_action_distribution(distribution)
        for index in self._pending_trace_indices:
            self.revision_action_traces[index] = self.revision_action_traces[index].model_copy(
                update={
                    "planner_read_snapshot_id": snapshot.snapshot_id,
                    "planner_prediction_index": self._prediction_index,
                    "next_action_distribution": action_distribution,
                    "operator_diagnostics": (
                        *self.revision_action_traces[index].operator_diagnostics,
                        OperatorDiagnostic(
                            operator=RevisionActionOperator.PLANNER_BELIEF_READ,
                            executed=True,
                            changed_state=False,
                            detail=f"planner consumed snapshot {snapshot.snapshot_id}",
                        ),
                    ),
                }
            )
        self._pending_trace_indices.clear()
        self._prediction_index += 1
        return _Prediction(
            put_back=_argmax(self.locations, distribution),
            search_order=tuple(_rank(self.locations, distribution, first=self.last_location)),
            unknown_probability=self.unknown_probability,
        )

    def _refresh_application_receipts(self) -> None:
        """Project deferred receipts into their final exactly-once trace state."""

        for index, trace in enumerate(self.revision_action_traces):
            if trace.project_one_request is None:
                continue
            receipts = self.spine.application_receipts_for_feedback(trace.feedback_record_id)
            if not receipts:
                continue
            applied = next(
                (
                    item
                    for item in reversed(receipts)
                    if item.status is ProjectOneRequestApplicationStatus.APPLIED
                ),
                None,
            )
            receipt = applied or receipts[-1]
            became_applied = (
                trace.request_application_status
                is ProjectOneRequestApplicationStatus.DEFERRED_DUE_TO_QUARANTINE
                and receipt.status is ProjectOneRequestApplicationStatus.APPLIED
            )
            update: dict[str, Any] = {
                "request_application_status": receipt.status,
                "application_receipt_id": receipt.receipt_id,
                "dirichlet_deltas": receipt.dirichlet_deltas,
                "rls_deltas": receipt.rls_deltas,
                "hybrid_rgrc_deltas": receipt.hybrid_rgrc_deltas,
                "ccrr_decision": receipt.ccrr_decision,
                "operator_diagnostics": tuple(
                    diagnostic.model_copy(
                        update={
                            "executed": receipt.status
                            is ProjectOneRequestApplicationStatus.APPLIED,
                            "changed_state": bool(
                                receipt.dirichlet_deltas
                                or receipt.rls_deltas
                                or receipt.hybrid_rgrc_deltas
                            ),
                            "detail": receipt.status.value,
                        }
                    )
                    if diagnostic.operator is RevisionActionOperator.DIRICHLET_RLS_APPLICATION
                    else diagnostic.model_copy(
                        update={
                            "executed": True,
                            "changed_state": receipt.ccrr_decision in {"create", "reactivate"},
                            "detail": receipt.ccrr_decision,
                        }
                    )
                    if diagnostic.operator is RevisionActionOperator.CCRR_REGIME_DECISION
                    else diagnostic
                    for diagnostic in trace.operator_diagnostics
                ),
            }
            if became_applied:
                snapshot = self.spine.current_snapshot
                update.update(
                    {
                        "new_belief_snapshot_id": snapshot.snapshot_id,
                        "planner_read_snapshot_id": None,
                        "planner_prediction_index": None,
                        "next_action_distribution": (),
                    }
                )
                if index not in self._pending_trace_indices:
                    self._pending_trace_indices.append(index)
            self.revision_action_traces[index] = trace.model_copy(update=update)

        request_traces = [
            item for item in self.revision_action_traces if item.project_one_request is not None
        ]
        self.project_one_requests = len(request_traces)
        self.project_one_applications = sum(
            item.request_application_status is ProjectOneRequestApplicationStatus.APPLIED
            for item in request_traces
        )
        self.project_one_deferred = sum(
            item.request_application_status
            is ProjectOneRequestApplicationStatus.DEFERRED_DUE_TO_QUARANTINE
            for item in request_traces
        )
        self.project_one_rejections = sum(
            item.request_application_status is ProjectOneRequestApplicationStatus.REJECTED
            for item in request_traces
        )
        self.project_one_replay_noops = sum(
            item.request_application_status is ProjectOneRequestApplicationStatus.REPLAY_NOOP
            for item in request_traces
        )

    def _next_action_distribution(
        self, location_distribution: Mapping[UUID, float]
    ) -> tuple[ActionProbability, ...]:
        confidence = max(location_distribution.values(), default=0.0)
        threshold_gap = max(0.0, self.action_utility_threshold - confidence)
        ask_mass = min(0.5, 0.25 * self.unknown_probability + threshold_gap)
        remaining = 1.0 - ask_mass
        action_weights = {"put_back": 0.45, "search": 0.40, "deliver": 0.15}
        items = [
            ActionProbability(
                action=action,
                location_id=location,
                probability=remaining * action_weight * probability,
            )
            for action, action_weight in action_weights.items()
            for location, probability in location_distribution.items()
        ]
        if ask_mass > 0.0:
            items.append(ActionProbability(action="ask", probability=ask_mass))
        return tuple(items)

    @staticmethod
    def _weighted_axis_evidence(
        evidence: Any, weight: float, *, unknown_prior: float | None = None
    ) -> Any:
        if evidence is None:
            return None
        if weight < 0.0:
            raise ValueError("evidence weight must be non-negative")
        if hasattr(evidence, "actor_posterior"):
            posterior_name, prior_name = "actor_posterior", "reference_actor_prior"
        elif hasattr(evidence, "mechanism_posterior"):
            posterior_name, prior_name = (
                "mechanism_posterior",
                "reference_mechanism_prior",
            )
        else:
            posterior_name, prior_name = (
                "ordered_role_posterior",
                "reference_ordered_role_prior",
            )
        posterior = dict(getattr(evidence, posterior_name))
        prior = dict(getattr(evidence, prior_name))
        if unknown_prior is not None and EventMechanism.UNKNOWN_MECHANISM in posterior:
            known = [key for key in posterior if key is not EventMechanism.UNKNOWN_MECHANISM]
            prior = {
                key: (
                    unknown_prior
                    if key is EventMechanism.UNKNOWN_MECHANISM
                    else (1.0 - unknown_prior) / max(len(known), 1)
                )
                for key in posterior
            }
        weighted = {
            key: max(prior[key], 1e-12) * (max(value, 1e-12) / max(prior[key], 1e-12)) ** weight
            for key, value in posterior.items()
        }
        total = sum(weighted.values())
        return evidence.model_copy(
            update={
                posterior_name: {key: value / total for key, value in weighted.items()},
                prior_name: prior,
            }
        )

    def feedback(self, step: ProjectTwoReplayStep) -> None:
        step = self.evidence_transform(step)
        history = self.histories.get(step.step_id)
        result = self.step_results.get(step.step_id)
        if history is None or result is None:
            return
        if self.revision_strategy == "in_place":
            self.revision_calls += len(step.execution_feedback)
            return
        if self.revision_strategy == "full_rerun" and step.execution_feedback:
            self.revision_calls += len(step.execution_feedback)
            self.spine = CorePrototypeSpine(
                owner_key=self.episode.owner_actor_key,
                object_instance_id=self.episode.steps[0].object_instance_id,
                locations=self.locations,
                authorization_scope_id=uuid4(),
                loop_config=self.loop_config,
                message_passing=self.message_passing,
                rgrc_gate_enabled=self.rgrc_gate_enabled,
                correction_mode=self.propensity_correction_mode,
                action_readout=self.action_readout,
            )
            self.histories.clear()
            self.step_results.clear()
            replay = tuple(self._observed_steps)
            self._observed_steps.clear()
            for observed in replay:
                self.observe(observed)
            return
        for feedback in step.execution_feedback:
            success = feedback.outcome_distribution.get(RobotActionOutcome.SUCCESS, 0.0)
            if self.feedback_mode == "none":
                continue
            if self.feedback_mode == "failure_only" and success > 0.5:
                continue
            if self.feedback_mode == "success_only" and success <= 0.5:
                continue
            try:
                old_snapshot = self.spine.current_snapshot
                revised, outcome = self.feedback_loop.ingest_feedback(
                    history=history,
                    feedback=feedback,
                    binding=_binding(feedback, result, self.spine.authorization_scope_id),
                    likelihood_model=_likelihood(
                        feedback.action_type,
                        calibration=self.likelihood_calibration,
                    ),
                    owner_key=self.episode.owner_actor_key,
                    transition_model=(
                        _transition_model(step, self.episode)
                        if feedback.action_type in {RobotActionType.PLACE, RobotActionType.TRANSFER}
                        else None
                    ),
                    observed_destination_location_id=step.observed_destination_location_id,
                    post_action_observation_record_id=(
                        step.after.metadata.record_id
                        if step.observed_destination_location_id is not None
                        and step.after is not None
                        else None
                    ),
                )
            except (FeedbackProvenanceError, ValueError, KeyError):
                self.rejected_feedback += 1
                continue
            self.revision_calls += 1
            history = revised
            self.histories[step.step_id] = revised
            self.unknown_probability = outcome.actor_posterior_after.get("unknown_actor", 0.0)
            if not outcome.project_one_requests:
                self.unnecessary_revisions += 1
            receipt = None
            for request in outcome.project_one_requests:
                self.project_one_requests += 1
                if not self.apply_project_one_revisions:
                    self.project_one_rejections += 1
                    continue
                apply_project_one_request(request, self.spine)
                receipt = self.spine.application_receipts_for_feedback(
                    request.source_feedback_record_id
                )[-1]
                if receipt.status is ProjectOneRequestApplicationStatus.APPLIED:
                    self.project_one_applications += 1
                elif (
                    receipt.status is ProjectOneRequestApplicationStatus.DEFERRED_DUE_TO_QUARANTINE
                ):
                    self.project_one_deferred += 1
                elif receipt.status is ProjectOneRequestApplicationStatus.REPLAY_NOOP:
                    self.project_one_replay_noops += 1
                else:
                    self.project_one_rejections += 1
            new_snapshot = self.spine.publish_project_two_revision_snapshot(outcome)
            # Multiple feedback records can arrive before one planner tick. Every
            # record in that causal batch points to the final corrected snapshot
            # that the next planner will actually consume.
            for index in self._pending_trace_indices:
                self.revision_action_traces[index] = self.revision_action_traces[index].model_copy(
                    update={"new_belief_snapshot_id": new_snapshot.snapshot_id}
                )
            trace = self._trace(
                feedback=feedback,
                outcome=outcome,
                receipt=receipt,
                old_snapshot_id=old_snapshot.snapshot_id,
                new_snapshot_id=new_snapshot.snapshot_id,
            )
            self.revision_action_traces.append(trace)
            self._pending_trace_indices.append(len(self.revision_action_traces) - 1)

        # Close the feedback -> corrected snapshot -> planner edge immediately.
        # A later robot observation may legitimately create yet another snapshot,
        # but cannot be used as a substitute for proving this feedback was read.
        if self._pending_trace_indices:
            snapshot = self.spine.current_snapshot
            distribution = self.spine.action_location_distribution(snapshot)
            action_distribution = self._next_action_distribution(distribution)
            for index in self._pending_trace_indices:
                self.revision_action_traces[index] = self.revision_action_traces[index].model_copy(
                    update={
                        "new_belief_snapshot_id": snapshot.snapshot_id,
                        "planner_read_snapshot_id": snapshot.snapshot_id,
                        "planner_prediction_index": self._prediction_index,
                        "next_action_distribution": action_distribution,
                        "operator_diagnostics": (
                            *self.revision_action_traces[index].operator_diagnostics,
                            OperatorDiagnostic(
                                operator=RevisionActionOperator.PLANNER_BELIEF_READ,
                                executed=True,
                                changed_state=False,
                                detail=(
                                    f"planner consumed corrected snapshot {snapshot.snapshot_id}"
                                ),
                            ),
                        ),
                    }
                )
            self._pending_trace_indices.clear()

    @staticmethod
    def _mass(values: Mapping[str, float]) -> tuple[ProbabilityMass, ...]:
        return tuple(
            ProbabilityMass(key=key, probability=min(1.0, max(0.0, value)))
            for key, value in sorted(values.items())
        )

    @staticmethod
    def _uuid_mass(values: Mapping[UUID, float]) -> tuple[UUIDProbabilityMass, ...]:
        return tuple(
            UUIDProbabilityMass(key=key, probability=min(1.0, max(0.0, value)))
            for key, value in sorted(values.items(), key=lambda item: str(item[0]))
        )

    def _trace(
        self,
        *,
        feedback: Any,
        outcome: Any,
        receipt: Any,
        old_snapshot_id: UUID,
        new_snapshot_id: UUID,
    ) -> ProjectTwoRevisionActionTrace:
        request = outcome.project_one_requests[0] if outcome.project_one_requests else None
        request_trace = (
            None
            if request is None
            else ProjectOneStatRequestTrace(
                kind=request.kind.value,
                superseded_revision_id=request.superseded_revision_id,
                corrected_revision_id=request.corrected_revision_id,
                event_hypothesis_id=request.event_hypothesis_id,
                owner_key=request.owner_key,
                object_instance_id=request.object_instance_id,
                location_id=request.location_id,
                owner_mass_before=request.owner_mass_before,
                owner_mass_after=request.owner_mass_after,
                owner_mass_delta=request.owner_mass_delta,
                source_feedback_record_id=request.source_feedback_record_id,
            )
        )
        status = None if receipt is None else receipt.status
        diagnostics = (
            OperatorDiagnostic(
                operator=RevisionActionOperator.CHEH_HYPOTHESIS_SUPPORT,
                executed=True,
                changed_state=bool(outcome.hypothesis_posterior_after),
                detail=f"{len(outcome.hypothesis_posterior_after)} supported hypotheses",
            ),
            OperatorDiagnostic(
                operator=RevisionActionOperator.PCHMP_REPROPAGATION,
                executed=True,
                changed_state=(
                    outcome.hypothesis_posterior_before != outcome.hypothesis_posterior_after
                ),
                detail="joint posterior re-propagated with provenance constraints",
            ),
            OperatorDiagnostic(
                operator=RevisionActionOperator.ORRER_REVISION,
                executed=True,
                changed_state=(outcome.superseded_revision_id != outcome.corrected_revision_id),
                detail="append-only corrected revision produced",
            ),
            OperatorDiagnostic(
                operator=RevisionActionOperator.PROJECT_ONE_REQUEST_GENERATION,
                executed=True,
                changed_state=request is not None,
                detail=("typed request emitted" if request else "no statistic delta required"),
            ),
            OperatorDiagnostic(
                operator=RevisionActionOperator.QUARANTINE_HANDOFF,
                executed=request is not None,
                changed_state=(
                    status is ProjectOneRequestApplicationStatus.DEFERRED_DUE_TO_QUARANTINE
                ),
                detail=(status.value if status is not None else "not requested"),
            ),
            OperatorDiagnostic(
                operator=RevisionActionOperator.DIRICHLET_RLS_APPLICATION,
                executed=(status is ProjectOneRequestApplicationStatus.APPLIED),
                changed_state=bool(
                    receipt
                    and (
                        receipt.dirichlet_deltas or receipt.rls_deltas or receipt.hybrid_rgrc_deltas
                    )
                ),
                detail=(status.value if status is not None else "not requested"),
            ),
            OperatorDiagnostic(
                operator=RevisionActionOperator.CCRR_REGIME_DECISION,
                executed=receipt is not None,
                changed_state=bool(receipt and receipt.ccrr_decision in {"create", "reactivate"}),
                detail=(receipt.ccrr_decision if receipt is not None else "not requested"),
            ),
        )
        return ProjectTwoRevisionActionTrace(
            feedback_record_id=feedback.metadata.record_id,
            evidence_source_record_ids=outcome.evidence_source_record_ids,
            superseded_revision_id=outcome.superseded_revision_id,
            corrected_revision_id=outcome.corrected_revision_id,
            hypothesis_posterior_before=self._uuid_mass(outcome.hypothesis_posterior_before),
            hypothesis_posterior_after=self._uuid_mass(outcome.hypothesis_posterior_after),
            actor_posterior_before=self._mass(outcome.actor_posterior_before),
            actor_posterior_after=self._mass(outcome.actor_posterior_after),
            known_mechanism_actor_mass_before=self._mass(outcome.known_mechanism_actor_mass_before),
            known_mechanism_actor_mass_after=self._mass(outcome.known_mechanism_actor_mass_after),
            mechanism_posterior_before=self._mass(outcome.mechanism_posterior_before),
            mechanism_posterior_after=self._mass(outcome.mechanism_posterior_after),
            role_posterior_before=self._mass(outcome.role_posterior_before),
            role_posterior_after=self._mass(outcome.role_posterior_after),
            location_posterior_before=self._mass(outcome.location_posterior_before),
            location_posterior_after=self._mass(outcome.location_posterior_after),
            unknown_actor_before=outcome.actor_posterior_before.get("unknown_actor", 0.0),
            unknown_actor_after=outcome.actor_posterior_after.get("unknown_actor", 0.0),
            unknown_mechanism_before=outcome.unknown_mechanism_before,
            unknown_mechanism_after=outcome.unknown_mechanism_after,
            unresolved_before=outcome.unresolved_before,
            unresolved_after=outcome.unresolved_after,
            unknown_mechanism_actor_mass_before=self._mass(
                outcome.unknown_mechanism_actor_mass_before
            ),
            unknown_mechanism_actor_mass_after=self._mass(
                outcome.unknown_mechanism_actor_mass_after
            ),
            owner_mass_before=outcome.owner_mass_before,
            owner_mass_after=outcome.owner_mass_after,
            project_one_request=request_trace,
            request_application_status=status,
            application_receipt_id=(None if receipt is None else receipt.receipt_id),
            dirichlet_deltas=(() if receipt is None else receipt.dirichlet_deltas),
            rls_deltas=(() if receipt is None else receipt.rls_deltas),
            hybrid_rgrc_deltas=(() if receipt is None else receipt.hybrid_rgrc_deltas),
            ccrr_decision=("not_requested" if receipt is None else receipt.ccrr_decision),
            old_belief_snapshot_id=old_snapshot_id,
            new_belief_snapshot_id=new_snapshot_id,
            attempted_location_id=feedback.attempted_location_id,
            observed_destination_location_id=outcome.observed_destination_location_id,
            confirmed_location_evidence_id=outcome.confirmed_location_evidence_id,
            operator_diagnostics=diagnostics,
        )


def _binding(
    feedback: Any, result: PrototypeStepResult, authorization_scope_id: UUID
) -> DecisionContextBinding:
    revisions = MapConsistencyRevisions(
        belief_snapshot_id=result.belief_snapshot.snapshot_id,
        projection_id=uuid4(),
        projection_version=1,
        static_map_revision=0,
        dynamic_map_revision=result.belief_snapshot.map_version,
        event_history_revision=len(result.event_history.revisions),
        input_watermark=1,
    )
    belief = TargetPresenceBeliefRef(
        object_instance_id=feedback.target_entity.entity_id,
        location_id=feedback.attempted_location_id,
        belief_node_id=f"replay:{feedback.target_entity.entity_id}:{feedback.attempted_location_id}",
        belief_snapshot_id=revisions.belief_snapshot_id,
        node_content_hash="0" * 64,
        prior_probability=0.6,
    )
    start = feedback.valid_time.start
    end = feedback.valid_time.end or (start + timedelta(minutes=1))
    context = DecisionContext.create(
        decision_id=feedback.action_id,
        decision_time=start,
        valid_time=ValidTimeInterval(start=start, end=end + timedelta(minutes=1)),
        staleness_budget_seconds=3600.0,
        revisions=revisions,
        attributed_cause=AttributedCause.UNRESOLVED,
        target_presence_belief=belief,
        authorization_scope_id=authorization_scope_id,
        habit_regime_model_version="project-two-replay@0.2",
        model_versions=(("feedback-loop", "0.2"),),
        code_version="benchmark-v0.2",
        rationale="replay action decision bound to exact project-one snapshot",
    )
    return DecisionContextBinding(
        metadata=feedback.metadata.model_copy(
            update={
                "record_id": uuid4(),
                "schema_name": "cpswm.DecisionContextBinding",
            }
        ),
        surface=DecisionSurface.EXECUTION_FEEDBACK,
        subject_record_id=feedback.metadata.record_id,
        subject_household_id=feedback.metadata.household_id,
        subject_session_id=feedback.metadata.session_id,
        subject_trace_id=feedback.metadata.trace_id,
        decision_context=context,
    )


def _likelihood(
    action_type: RobotActionType, *, calibration: float = 1.0
) -> ActionOutcomeLikelihoodModel:
    if calibration <= 0.0:
        raise ValueError("likelihood calibration must be positive")
    if action_type in {RobotActionType.PLACE, RobotActionType.TRANSFER}:
        present = {RobotActionOutcome.SUCCESS: 0.85, RobotActionOutcome.OBJECT_SLIPPED: 0.15}
        absent = {RobotActionOutcome.SUCCESS: 0.25, RobotActionOutcome.OBJECT_SLIPPED: 0.75}
    else:
        present = {RobotActionOutcome.SUCCESS: 0.85, RobotActionOutcome.NOT_FOUND: 0.15}
        absent = {RobotActionOutcome.SUCCESS: 0.1, RobotActionOutcome.NOT_FOUND: 0.9}

    def calibrated(
        values: Mapping[RobotActionOutcome, float],
    ) -> dict[RobotActionOutcome, float]:
        powered = {key: value**calibration for key, value in values.items()}
        total = sum(powered.values())
        return {key: value / total for key, value in powered.items()}

    return ActionOutcomeLikelihoodModel(
        action_type=action_type,
        p_outcome_given_target_present=calibrated(present),
        p_outcome_given_target_absent=calibrated(absent),
        calibration_domain="D0 replay pilot",
        model_version=f"matched-feedback-likelihood@0.3-calibration-{calibration:g}",
    )


def _transition_model(
    step: ProjectTwoReplayStep, episode: ProjectTwoReplayEpisode
) -> TransitionRevisionModel:
    mechanisms = step.mechanism_evidence
    if mechanisms is None:
        mp = {EventMechanism.DIRECT_RELOCATION: 0.5, EventMechanism.HANDOFF_RELOCATION: 0.5}
        mr = dict(mp)
        source = step.step_id
    else:
        mp = dict(mechanisms.mechanism_posterior)
        mr = dict(mechanisms.reference_mechanism_prior)
        # TransitionRevisionModel currently operates on modelled mechanisms.
        mp.pop(EventMechanism.UNKNOWN_MECHANISM, None)
        mr.pop(EventMechanism.UNKNOWN_MECHANISM, None)
        mp = _normalize(mp)
        mr = _normalize(mr)
        source = mechanisms.metadata.record_id
    role = step.ordered_role_evidence
    known = [key for key in episode.resident_actor_keys if key != "unknown_actor"]
    if len(known) < 2:
        known.append("other_actor")
    neutral_roles = {
        ordered_role_key(known[0], known[1]): 0.5,
        ordered_role_key(known[1], known[0]): 0.5,
    }
    rp = dict(role.ordered_role_posterior) if role is not None else neutral_roles
    rr = dict(role.reference_ordered_role_prior) if role is not None else neutral_roles
    actor = None
    if step.actor_evidence is not None:
        ratios = {
            key: max(value, 1e-6)
            for key, value in step.actor_evidence.actor_likelihood_ratios.items()
        }
        actor = ActorDiscriminationEvidence(
            ratios=ratios,
            model_version=step.actor_evidence.evidence_model_id,
            source_record_id=step.actor_evidence.metadata.record_id,
        )
    return TransitionRevisionModel(
        mechanism_posterior=mp,
        mechanism_prior=mr,
        ordered_role_posterior=rp,
        ordered_role_prior=rr,
        model_version="visible-transition-evidence@0.2",
        source_record_id=source,
        actor=actor,
    )


def _normalize(values: Mapping[Any, float]) -> dict[Any, float]:
    total = sum(values.values())
    return {key: value / total for key, value in values.items()}


def _locations(episode: ProjectTwoReplayEpisode) -> tuple[UUID, ...]:
    if episode.known_location_ids:
        if len(episode.known_location_ids) < 2:
            raise ValueError("benchmark episode requires at least two known locations")
        return episode.known_location_ids
    values: list[UUID] = []
    for step in episode.steps:
        values.extend(
            value
            for value in (
                step.source_location_id,
                step.attempted_location_id,
                step.observed_destination_location_id,
            )
            if value is not None
        )
    locations = tuple(dict.fromkeys(values))
    if len(locations) < 2:
        raise ValueError("benchmark episode requires at least two visible locations")
    return locations


def _argmax(locations: tuple[UUID, ...], scores: Mapping[UUID, float]) -> UUID:
    # Location UUIDs are identity, never a model feature or a tie-break signal.
    # Preserve robot-visible encounter order so UUID/label permutations cannot
    # change an otherwise tied decision.
    return max(
        enumerate(locations),
        key=lambda item: (scores.get(item[1], 0.0), -item[0]),
    )[1]


def _rank(
    locations: tuple[UUID, ...], scores: Mapping[UUID, float], first: UUID | None = None
) -> list[UUID]:
    encounter_order = {location: index for index, location in enumerate(locations)}
    ordered = sorted(
        locations,
        key=lambda loc: (-scores.get(loc, 0.0), encounter_order[loc]),
    )
    if first in ordered:
        ordered.remove(first)
        ordered.insert(0, first)
    return ordered


def _visible_hash(episode: ProjectTwoReplayEpisode) -> str:
    reject_truth_leakage(episode.model_dump(mode="python"))
    return hashlib.sha256(
        json.dumps(episode.model_dump(mode="json"), sort_keys=True).encode()
    ).hexdigest()


PARAMETER_SPACE: dict[ProjectTwoActionMethod, tuple[dict[str, float | str], ...]] = {
    ProjectTwoActionMethod.FREQUENCY: ({"parameter": 0.0}, {"parameter": 0.5}, {"parameter": 1.0}),
    ProjectTwoActionMethod.RECENCY: ({"parameter": 0.5}, {"parameter": 0.8}, {"parameter": 0.95}),
    ProjectTwoActionMethod.MARKOV: ({"parameter": 0.1}, {"parameter": 0.5}, {"parameter": 1.0}),
    ProjectTwoActionMethod.AMG_MATCHED: (
        {"parameter": 0.2},
        {"parameter": 0.33},
        {"parameter": 0.5},
    ),
    ProjectTwoActionMethod.O_STAR: ({"parameter": 0.7}, {"parameter": 0.85}, {"parameter": 1.0}),
    ProjectTwoActionMethod.DYNAMEM: ({"parameter": 0.5}, {"parameter": 0.8}, {"parameter": 0.95}),
    ProjectTwoActionMethod.STAR: ({"parameter": 0.8}, {"parameter": 0.9}, {"parameter": 1.0}),
    ProjectTwoActionMethod.FULL_RERUN: ({"parameter": 0.0}, {"parameter": 0.5}, {"parameter": 1.0}),
    # v0.6 readout search space.  The three mechanism-level candidates were
    # frozen after inspecting TRAIN seeds 1--20 only.  The superseded v0.5
    # slow/revision-aware/pooled points remain in its immutable report; they are
    # not silently relabelled.  Budget stays at three points, matching every
    # reference arm.  All three candidates retain the complete seven-operator
    # system and differ only in the planner read boundary: pure reversible fast
    # evidence, fast+surviving evidence, or fast+surviving+regime-local evidence.
    # No evaluator truth enters any readout.
    ProjectTwoActionMethod.PROJECT_TWO: (
        {
            "owner_threshold": 0.4,
            "readout": ActionReadout.LATEST_OWNER_EVENT.value,
            "fast_owner_mass_floor": 0.5,
        },
        {
            "owner_threshold": 0.4,
            "readout": ActionReadout.DUAL_TIMESCALE_REVERSIBLE.value,
            "hybrid_alpha_weight": 0.0,
            "fast_action_weight": 0.8,
            "surviving_revision_weight": 0.2,
            "regime_local_weight": 0.0,
            "fast_owner_mass_floor": 0.5,
            "owner_mass_floor": 0.5,
            "recency_half_life": 1.0,
        },
        {
            "owner_threshold": 0.4,
            "readout": ActionReadout.DUAL_TIMESCALE_REVERSIBLE.value,
            "hybrid_alpha_weight": 0.0,
            "fast_action_weight": 0.7,
            "surviving_revision_weight": 0.2,
            "regime_local_weight": 0.1,
            "fast_owner_mass_floor": 0.5,
            "owner_mass_floor": 0.5,
            "recency_half_life": 1.0,
        },
    ),
}


class ProjectTwoActionBenchmarkV02:
    primary_metrics = (
        "put_back_error_rate",
        "cumulative_action_regret",
        "owner_habit_contamination",
        "incorrect_statistic_recovery_cost",
    )

    def run(self, dataset: ProjectTwoReplayDataset) -> ProjectTwoActionBenchmarkReport:
        enforce_project_two_replay_gate(dataset)
        train = dataset.visible_episodes(ProjectTwoDatasetSplit.TRAIN)
        validation = dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)
        test = dataset.visible_episodes(ProjectTwoDatasetSplit.TEST)
        if not validation or not test:
            raise ValueError("benchmark requires non-empty validation and sealed test splits")
        methods = tuple(
            method
            for method in ProjectTwoActionMethod
            if method is not ProjectTwoActionMethod.ORACLE
        )
        selections: list[MethodTuningSelection] = []
        chosen: dict[ProjectTwoActionMethod, dict[str, float | str]] = {}
        development_contract = current_route_a_development_utility_contract()
        for method in methods:
            space = PARAMETER_SPACE[method]
            scores = []
            trials: list[ValidationTuningTrial] = []
            for params in space:
                cases = [
                    self._evaluate_episode(dataset, episode, method, params)
                    for episode in validation
                ]
                case_values = tuple(item.cumulative_action_regret for item in cases)
                trial = ValidationTuningTrial(
                    parameters=params,
                    primary_utility_by_validation_episode=case_values,
                    mean_primary_utility=mean(case_values),
                )
                trials.append(trial)
                scores.append(
                    (
                        trial.mean_primary_utility,
                        json.dumps(params, sort_keys=True),
                        params,
                    )
                )
            selected = min(scores, key=lambda item: (item[0], item[1]))[2]
            chosen[method] = selected
            selections.append(
                MethodTuningSelection(
                    method=method,
                    selection_metric=development_contract.selection_metric,
                    parameter_space=space,
                    selected_parameters=selected,
                    validation_episode_ids=tuple(item.episode_id for item in validation),
                    validation_trials=tuple(trials),
                    search_budget=len(space),
                )
            )
        case_metrics: list[ActionCaseMetric] = []
        for episode in test:
            for method in methods:
                case_metrics.append(
                    self._evaluate_episode(dataset, episode, method, chosen[method])
                )
            case_metrics.append(
                self._evaluate_episode(dataset, episode, ProjectTwoActionMethod.ORACLE, {})
            )
        aggregates = self._aggregate(case_metrics)
        engineering_superiority = _development_engineering_superiority(aggregates)
        definition = self._primary_utility_definition(aggregates, development_contract)
        verdict = self._route_a_verdict(
            aggregates,
            definition=definition,
            paper_gate_failures=PAPER_LEVEL_GATE_FAILURES,
            engineering_superiority=engineering_superiority,
        )
        superiority = (
            engineering_superiority
            and not PAPER_LEVEL_GATE_FAILURES
            and verdict.superiority_authorized
            and definition.route_a_primary_utility_evaluated
        )
        baseline_fairness = _expected_baseline_fairness()
        return ProjectTwoActionBenchmarkReport(
            dataset_version=dataset.manifest.dataset_version,
            train_episode_ids=tuple(item.episode_id for item in train),
            validation_episode_ids=tuple(item.episode_id for item in validation),
            sealed_test_episode_ids=tuple(item.episode_id for item in test),
            action_budget_per_episode=max(len(item.steps) for item in test),
            observation_coverage_by_episode={
                item.episode_id: sum(step.after is not None for step in item.steps)
                / len(item.steps)
                for item in (*validation, *test)
            },
            tuning=tuple(selections),
            case_metrics=tuple(case_metrics),
            aggregate_metrics=tuple(aggregates),
            fairness_visible_hashes={
                item.episode_id: _visible_hash(item) for item in (*validation, *test)
            },
            complete_chain=(
                "ObservationDetectionResult",
                "CHEH",
                "ORRER",
                "PCHMP",
                "actor/role/mechanism posterior",
                "search/put-back action",
                "ExecutionFeedbackRecord",
                "ExecutionFeedbackProjector",
                "ProjectTwoFeedbackRevisionLoop",
                "new ORRER revision",
                "EventRevisionOutcome",
                "ProjectOneStatRequest",
                "project-one retract/correct/reinforce",
                "next action decision",
            ),
            scientific_status=(
                "paper-level superiority supported"
                if superiority
                else "paper-level superiority NOT supported; " + verdict.summary
            ),
            superiority_supported=superiority,
            limitations=(
                "D0 synthetic replay pilot only; not real-world external validity",
                "AMG is a matched object-relocation adapter, not a faithful source reproduction",
                "O-STaR, DynaMem, and STAR are matched replay adapters, not faithful reproductions",
                "D1-D4 real perception, household, and robot execution gates remain closed",
            ),
            baseline_fairness=baseline_fairness,
            paper_level_gate_failures=PAPER_LEVEL_GATE_FAILURES,
            development_utility_contract=development_contract,
            primary_utility_definition=definition,
            scientific_verdict=verdict,
            development_primary_utility_evaluated=(
                definition.development_primary_utility_evaluated
            ),
            route_a_primary_utility_evaluated=definition.route_a_primary_utility_evaluated,
            unresolved_utility_contract_fields=definition.unresolved_contract_fields,
            unregistered_search_metric_assumptions=UNREGISTERED_SEARCH_METRIC_ASSUMPTIONS,
        )

    @staticmethod
    def _primary_utility_definition(
        aggregates: list[AggregateMetric],
        development_contract: RouteADevelopmentUtilityContract,
    ) -> RouteAPrimaryUtilityDefinition:
        """State what this run computes for the frozen primary utility, and what it assumes.

        The frozen combination-A route pins *which* quantity is primary and
        which guardrails sit outside any weighted score.  It does not pin how a
        put-back error, a search path and a failed search convert into that
        quantity, so those weights stay unresolved here rather than being
        chosen by the evaluator.
        """

        oracle = next(
            (
                item.value
                for item in aggregates
                if item.method is ProjectTwoActionMethod.ORACLE
                and item.metric == ROUTE_A_PRIMARY_UTILITY_METRIC
            ),
            None,
        )
        return RouteAPrimaryUtilityDefinition(
            primary_utility_metric=ROUTE_A_PRIMARY_UTILITY_METRIC,
            optimization_direction=ROUTE_A_OPTIMIZATION_DIRECTION,
            frozen_route_reference=ROUTE_A_FROZEN_ROUTE_REFERENCE,
            implemented_component_terms=IMPLEMENTED_REGRET_COMPONENT_TERMS,
            implemented_unit=IMPLEMENTED_REGRET_UNIT,
            oracle_reference_method=ProjectTwoActionMethod.ORACLE.value,
            oracle_reference_value=oracle,
            development_contract_id=development_contract.contract_id,
            development_contract_reference=ROUTE_A_DEVELOPMENT_UTILITY_CONTRACT_REFERENCE,
            development_primary_utility_evaluated=True,
            unresolved_contract_fields=ROUTE_A_UNRESOLVED_UTILITY_FIELDS,
        )

    @staticmethod
    def _route_a_verdict(
        aggregates: list[AggregateMetric],
        *,
        definition: RouteAPrimaryUtilityDefinition,
        paper_gate_failures: tuple[str, ...],
        engineering_superiority: bool,
    ) -> ScientificVerdict:
        """Decide superiority from the frozen primary utility and the hard guardrails.

        Secondary search metrics enter as regressions only: they can withhold a
        verdict but can never supply one, so a run that improves only
        ``mean_search_path_cost`` cannot promote its scientific status.
        """

        def value(method: ProjectTwoActionMethod, metric: str) -> float | None:
            return next(
                (
                    item.value
                    for item in aggregates
                    if item.method is method and item.metric == metric
                ),
                None,
            )

        secondary_metrics = (
            ("search_error_rate", True),
            ("mean_search_path_cost", True),
            ("mean_search_path_length", True),
            ("mean_search_time_seconds", True),
        )

        def observation(method: ProjectTwoActionMethod) -> MethodUtilityObservation:
            return MethodUtilityObservation(
                method=method.value,
                primary_utility=value(method, ROUTE_A_PRIMARY_UTILITY_METRIC),
                secondary_metrics=tuple(
                    SecondaryMetricObservation(
                        metric=metric,
                        value=observed,
                        lower_is_better=lower_is_better,
                    )
                    for metric, lower_is_better in secondary_metrics
                    if (observed := value(method, metric)) is not None
                ),
                guardrails=(
                    # Guardrail thresholds are themselves unresolved, so every
                    # hard guardrail reports "not measured" and fails closed.
                    # They can never be averaged against the primary utility.
                    GuardrailObservation(
                        guardrail=guardrail,
                        passed=None,
                        detail="no frozen numeric threshold is registered for this guardrail",
                    )
                    for guardrail in ROUTE_A_HARD_GUARDRAILS
                ),
            )

        # Development falsification is deliberately stricter than paper-level
        # fidelity admission: every registered non-oracle arm can defeat the
        # candidate, even when that arm is only a matched replay adapter.  Its
        # fidelity label remains separate and can never be upgraded by winning.
        references = tuple(
            observation(method)
            for method in ProjectTwoActionMethod
            if method not in {ProjectTwoActionMethod.PROJECT_TWO, ProjectTwoActionMethod.ORACLE}
        )
        blocking = tuple(f"PAPER_LEVEL_GATE: {item}" for item in paper_gate_failures)
        if not engineering_superiority:
            blocking = (*blocking, "ENGINEERING_SUPERIORITY_NOT_ESTABLISHED")
        return evaluate_route_a_superiority(
            definition=definition,
            candidate=observation(ProjectTwoActionMethod.PROJECT_TWO),
            references=references,
            additional_blocking_reasons=blocking,
            verdict_id=f"{BENCHMARK_VERSION}:route-a-superiority",
        )

    @staticmethod
    def _readout_from_params(params: Mapping[str, Any]) -> ActionReadoutConfig:
        """Build the planner read policy from one tuning point.

        Absent keys reproduce the frozen v0.2 pooled-alpha readout exactly, so an
        old parameter dict keeps its old behaviour.
        """

        name = str(params.get("readout", ActionReadout.HYBRID_ALPHA.value))
        return ActionReadoutConfig(
            readout=ActionReadout(name),
            owner_mass_floor=float(params.get("owner_mass_floor", 0.0)),
            recency_half_life=float(params.get("recency_half_life", 0.0)),
            hybrid_alpha_weight=float(params.get("hybrid_alpha_weight", 1.0)),
            regime_local_weight=float(params.get("regime_local_weight", 0.0)),
            surviving_revision_weight=float(params.get("surviving_revision_weight", 0.0)),
            fast_action_weight=float(params.get("fast_action_weight", 0.0)),
            fast_owner_mass_floor=float(params.get("fast_owner_mass_floor", 0.5)),
            fast_confirmation_observations=int(params.get("fast_confirmation_observations", 1)),
            unconfirmed_fast_discount=float(params.get("unconfirmed_fast_discount", 1.0)),
            pending_correction_discount=float(params.get("pending_correction_discount", 1.0)),
            active_regime_only=bool(params.get("active_regime_only", False)),
        )

    def _method(
        self,
        episode: ProjectTwoReplayEpisode,
        method: ProjectTwoActionMethod,
        params: Mapping[str, Any],
    ) -> _ReplayMethod:
        if method is ProjectTwoActionMethod.PROJECT_TWO:
            return _FullProjectTwoMethod(
                episode,
                owner_threshold=params["owner_threshold"],
                action_readout=self._readout_from_params(params),
            )
        if method is ProjectTwoActionMethod.AMG_MATCHED:
            return _AMGOpenWorldMethod(episode, mode="amg", parameter=params["parameter"])
        if method is ProjectTwoActionMethod.FULL_RERUN:
            return _FullRerunMethod(episode, mode="frequency", parameter=params["parameter"])
        modes = {
            ProjectTwoActionMethod.FREQUENCY: "frequency",
            ProjectTwoActionMethod.RECENCY: "recency",
            ProjectTwoActionMethod.MARKOV: "markov",
            ProjectTwoActionMethod.O_STAR: "o_star",
            ProjectTwoActionMethod.DYNAMEM: "dynamem",
            ProjectTwoActionMethod.STAR: "star",
        }
        return _CountMethod(episode, mode=modes[method], parameter=params["parameter"])

    def _evaluate_episode(
        self,
        dataset: ProjectTwoReplayDataset,
        episode: ProjectTwoReplayEpisode,
        method: ProjectTwoActionMethod,
        params: Mapping[str, Any],
    ) -> ActionCaseMetric:
        truth = dataset.truth_for(episode.episode_id)
        if method is ProjectTwoActionMethod.ORACLE:
            predictions = []
            for step in episode.steps:
                item = truth.truth_by_step[step.step_id]
                predictions.append(
                    _Prediction(
                        item.true_owner_habit_location,
                        (item.true_location,),
                        1.0 if item.true_actor == "unknown_actor" else 0.0,
                    )
                )
            stats = (0, 0, 0, 0, 0, 0, 0, 0, ())
        else:
            state = self._method(episode, method, params)
            predictions = []
            for step in episode.steps:
                state.observe(step)
                predictions.append(state.predict())
                state.feedback(step)
            stats = (
                state.revision_calls,
                state.project_one_requests,
                state.project_one_applications,
                state.rejected_feedback,
                state.unnecessary_revisions,
                state.project_one_rejections,
                getattr(state, "project_one_deferred", 0),
                getattr(state, "project_one_replay_noops", 0),
                tuple(getattr(state, "revision_action_traces", ())),
            )
        return self._score_predictions(
            dataset=dataset,
            episode=episode,
            method=method,
            predictions=predictions,
            stats=stats,
        )

    def evaluate_custom_state(
        self,
        dataset: ProjectTwoReplayDataset,
        episode: ProjectTwoReplayEpisode,
        state: _ReplayMethod,
    ) -> ActionCaseMetric:
        """Score a plug-in method through the frozen v0.2 action evaluator.

        The returned enum label is the project-two slot; callers retain their
        own track/ablation label. This avoids copying metric or truth handling.
        """

        predictions = []
        for step in episode.steps:
            state.observe(step)
            predictions.append(state.predict())
            state.feedback(step)
        return self._score_predictions(
            dataset=dataset,
            episode=episode,
            method=ProjectTwoActionMethod.PROJECT_TWO,
            predictions=predictions,
            stats=(
                state.revision_calls,
                state.project_one_requests,
                state.project_one_applications,
                state.rejected_feedback,
                state.unnecessary_revisions,
                state.project_one_rejections,
                getattr(state, "project_one_deferred", 0),
                getattr(state, "project_one_replay_noops", 0),
                tuple(getattr(state, "revision_action_traces", ())),
            ),
        )

    def _score_predictions(
        self,
        *,
        dataset: ProjectTwoReplayDataset,
        episode: ProjectTwoReplayEpisode,
        method: ProjectTwoActionMethod,
        predictions: list[_Prediction],
        stats: tuple[
            int,
            int,
            int,
            int,
            int,
            int,
            int,
            int,
            tuple[ProjectTwoRevisionActionTrace, ...],
        ],
    ) -> ActionCaseMetric:
        """Frozen evaluator shared by built-in and plug-in experiment tracks."""
        visible_hash = _visible_hash(episode)
        truth = dataset.truth_for(episode.episode_id)
        put_errors = persistent_errors = search_errors = search_cost = 0.0
        cumulative_search_regret = 0.0
        contamination = unknown_brier = 0.0
        incorrect_feedback_cases = 0
        recovery_cost = 0.0
        ordered_truth = [truth.truth_by_step[step.step_id] for step in episode.steps]
        locations = _locations(episode)
        registered_locations = set(locations)
        for prediction in predictions:
            if not isinstance(prediction, _Prediction):
                raise TypeError("method prediction must use the registered _Prediction contract")
            if prediction.put_back not in registered_locations:
                raise ValueError("put-back action names an unregistered location")
            if not prediction.search_order:
                raise ValueError("search plan must contain at least one registered location")
            if len(set(prediction.search_order)) != len(prediction.search_order):
                raise ValueError("search plan cannot inspect the same location twice")
            if not set(prediction.search_order) <= registered_locations:
                raise ValueError("search plan names an unregistered location")
            if isinstance(prediction.unknown_probability, bool) or not isinstance(
                prediction.unknown_probability, (float, int)
            ):
                raise TypeError("unknown probability must be a real number, not bool")
            if not 0.0 <= prediction.unknown_probability <= 1.0:
                raise ValueError("unknown probability must be in [0, 1]")
        # Evaluator truth may name a location that never entered the visible
        # replay under low observation coverage.  Keep it countable for scoring
        # without adding it to the model-visible action candidates in
        # ``locations`` below.
        persistent_counts: defaultdict[UUID, float] = defaultdict(
            float,
            {location: 0.0 for location in locations},
        )
        # One explicit pseudo-observation anchors the pre-episode owner habit.
        persistent_counts[ordered_truth[0].true_owner_habit_location] = 1.0
        for index, (step, prediction, target) in enumerate(
            zip(episode.steps, predictions, ordered_truth, strict=True)
        ):
            if target.true_actor == episode.owner_actor_key:
                persistent_counts[target.true_location] += 1.0
            persistent_target = _argmax(locations, persistent_counts)
            put_errors += prediction.put_back != target.true_owner_habit_location
            persistent_errors += prediction.put_back != persistent_target
            search_errors += prediction.search_order[0] != target.true_location
            try:
                inspected = prediction.search_order.index(target.true_location) + 1
                target_found = True
            except ValueError:
                inspected = len(prediction.search_order)
                target_found = False
            search_cost += inspected
            cumulative_search_regret += normalized_extra_inspection_regret(
                inspected_container_count=inspected,
                registered_location_count=len(locations),
                target_found_in_plan=target_found,
            )
            if target.true_actor != episode.owner_actor_key:
                contamination += prediction.put_back == target.true_location
            unknown_brier += (
                prediction.unknown_probability - float(target.true_actor == "unknown_actor")
            ) ** 2
            for feedback in step.execution_feedback:
                success = feedback.outcome_distribution.get(RobotActionOutcome.SUCCESS, 0.0)
                if success <= 0.5 and prediction.put_back != target.true_owner_habit_location:
                    incorrect_feedback_cases += 1
                    latency = len(predictions) - index
                    for future in range(index + 1, len(predictions)):
                        if (
                            predictions[future].put_back
                            == ordered_truth[future].true_owner_habit_location
                        ):
                            latency = future - index
                            break
                    recovery_cost += latency
        n = len(predictions)
        enriched_traces: list[ProjectTwoRevisionActionTrace] = []
        for trace_number, raw_trace in enumerate(stats[8]):
            identity = {
                "benchmark_version": BENCHMARK_VERSION,
                "episode_id": str(episode.episode_id),
                "feedback_record_id": str(raw_trace.feedback_record_id),
                "trace_number": trace_number,
            }
            corrected_id = (
                raw_trace.superseded_revision_id
                if raw_trace.corrected_revision_id == raw_trace.superseded_revision_id
                else content_uuid("benchmark-corrected-revision", identity)
            )
            old_snapshot_id = content_uuid("benchmark-old-belief-snapshot", identity)
            new_snapshot_id = (
                old_snapshot_id
                if raw_trace.new_belief_snapshot_id == raw_trace.old_belief_snapshot_id
                else content_uuid("benchmark-new-belief-snapshot", identity)
            )
            planner_snapshot_id = (
                None
                if raw_trace.planner_read_snapshot_id is None
                else (
                    new_snapshot_id
                    if raw_trace.planner_read_snapshot_id == raw_trace.new_belief_snapshot_id
                    else content_uuid("benchmark-planner-read-snapshot", identity)
                )
            )
            id_replacements = {
                str(raw_trace.corrected_revision_id): str(corrected_id),
                str(raw_trace.old_belief_snapshot_id): str(old_snapshot_id),
                str(raw_trace.new_belief_snapshot_id): str(new_snapshot_id),
            }
            if raw_trace.planner_read_snapshot_id is not None and planner_snapshot_id is not None:
                id_replacements[str(raw_trace.planner_read_snapshot_id)] = str(planner_snapshot_id)

            diagnostics = []
            for diagnostic in raw_trace.operator_diagnostics:
                detail = diagnostic.detail
                for source, replacement in id_replacements.items():
                    detail = detail.replace(source, replacement)
                diagnostics.append(diagnostic.model_copy(update={"detail": detail}))
            request = raw_trace.project_one_request
            trace = raw_trace.model_copy(
                update={
                    "corrected_revision_id": corrected_id,
                    "project_one_request": (
                        None
                        if request is None
                        else request.model_copy(update={"corrected_revision_id": corrected_id})
                    ),
                    "application_receipt_id": (
                        None
                        if raw_trace.application_receipt_id is None
                        else content_uuid("benchmark-application-receipt", identity)
                    ),
                    "old_belief_snapshot_id": old_snapshot_id,
                    "new_belief_snapshot_id": new_snapshot_id,
                    "planner_read_snapshot_id": planner_snapshot_id,
                    "operator_diagnostics": tuple(diagnostics),
                }
            )
            trace_index = min(trace.planner_prediction_index or 0, n - 1)
            target = ordered_truth[trace_index]
            put_candidates = [
                item for item in trace.next_action_distribution if item.action == "put_back"
            ]
            search_candidates = [
                item for item in trace.next_action_distribution if item.action == "search"
            ]
            selected_put = (
                max(put_candidates, key=lambda item: item.probability).location_id
                if put_candidates
                else None
            )
            ranked_search_locations = tuple(
                item.location_id
                for item in sorted(
                    search_candidates,
                    key=lambda item: (-item.probability, str(item.location_id)),
                )
                if item.location_id is not None
            )
            try:
                trace_inspected = ranked_search_locations.index(target.true_location) + 1
                trace_target_found = True
            except ValueError:
                trace_inspected = len(ranked_search_locations) or len(locations)
                trace_target_found = False
            trace_search_regret = normalized_extra_inspection_regret(
                inspected_container_count=trace_inspected,
                registered_location_count=len(locations),
                target_found_in_plan=trace_target_found,
            )
            regret = float(selected_put != target.true_owner_habit_location) + trace_search_regret
            enriched_traces.append(
                trace.model_copy(
                    update={
                        "evaluator_utility": 2.0 - regret,
                        "evaluator_regret": regret,
                        "operator_diagnostics": (
                            *trace.operator_diagnostics,
                            OperatorDiagnostic(
                                operator=RevisionActionOperator.UTILITY_ACTION_SELECTION,
                                executed=True,
                                changed_state=False,
                                detail=(
                                    f"frozen evaluator scored planner index {trace_index}: "
                                    f"utility={2.0 - regret}, regret={regret}, "
                                    f"search_regret={trace_search_regret}"
                                ),
                            ),
                        ),
                    }
                )
            )
        return ActionCaseMetric(
            episode_id=episode.episode_id,
            method=method,
            step_count=n,
            put_back_error_rate=put_errors / n,
            persistent_owner_mode_error_rate=persistent_errors / n,
            cumulative_put_back_regret=put_errors,
            cumulative_search_regret=cumulative_search_regret,
            cumulative_action_regret=put_errors + cumulative_search_regret,
            owner_habit_contamination=contamination / n,
            incorrect_statistic_recovery_cost=(
                recovery_cost / incorrect_feedback_cases if incorrect_feedback_cases else 0.0
            ),
            search_error_rate=search_errors / n,
            search_success_rate=1.0 - search_errors / n,
            mean_search_path_cost=search_cost / n,
            mean_search_path_length=search_cost / n,
            mean_search_time_seconds=5.0 * search_cost / n,
            mean_search_cost=search_cost / n,
            late_feedback_recovery_latency=(
                recovery_cost / incorrect_feedback_cases if incorrect_feedback_cases else 0.0
            ),
            unnecessary_revision_count=stats[4],
            unknown_calibration_brier=unknown_brier / n,
            provenance_dedup_rejection_correctness=1.0 if stats[3] == 0 else 0.0,
            full_feedback_revision_calls=stats[0],
            project_one_stat_requests=stats[1],
            project_one_stat_applications=stats[2],
            project_one_stat_rejections=stats[5],
            project_one_stat_deferred=stats[6],
            project_one_stat_replay_noops=stats[7],
            revision_action_traces=tuple(enriched_traces),
            visible_input_hash=visible_hash,
        )

    def _aggregate(self, cases: list[ActionCaseMetric]) -> list[AggregateMetric]:
        metrics = (
            "put_back_error_rate",
            "persistent_owner_mode_error_rate",
            "cumulative_put_back_regret",
            "cumulative_search_regret",
            "cumulative_action_regret",
            "owner_habit_contamination",
            "incorrect_statistic_recovery_cost",
            "search_error_rate",
            "search_success_rate",
            "mean_search_path_cost",
            "mean_search_path_length",
            "mean_search_time_seconds",
            "mean_search_cost",
            "late_feedback_recovery_latency",
            "unnecessary_revision_count",
            "unknown_calibration_brier",
            "provenance_dedup_rejection_correctness",
        )
        grouped = {
            (method, metric): [
                float(getattr(item, metric)) for item in cases if item.method is method
            ]
            for method in ProjectTwoActionMethod
            for metric in metrics
        }
        output: list[AggregateMetric] = []
        full = {metric: grouped[(ProjectTwoActionMethod.PROJECT_TWO, metric)] for metric in metrics}
        for method in ProjectTwoActionMethod:
            for metric in metrics:
                values = grouped[(method, metric)]
                if not values:
                    continue
                diff = ci = significant = engineering = None
                if method is not ProjectTwoActionMethod.PROJECT_TWO and len(values) == len(
                    full[metric]
                ):
                    paired = [
                        value - project for value, project in zip(values, full[metric], strict=True)
                    ]
                    diff = mean(paired)
                    ci = _bootstrap_ci(paired)
                    significant = ci[0] > 0.0 or ci[1] < 0.0
                    engineering = abs(diff) >= (
                        0.02 if "rate" in metric or "contamination" in metric else 0.1
                    )
                output.append(
                    AggregateMetric(
                        method=method,
                        fidelity=FIDELITY[method],
                        metric=metric,
                        value=mean(values),
                        value_confidence_interval_95=_bootstrap_ci(values),
                        worst_group_value=max(values),
                        paired_difference_vs_project_two=diff,
                        confidence_interval_95=ci,
                        statistically_significant=significant,
                        engineering_significant=engineering,
                    )
                )
        return output


def _bootstrap_ci(values: list[float], draws: int = 1000) -> tuple[float, float]:
    if not values:
        return (0.0, 0.0)
    rng = random.Random("project-two-v0.2-ci")
    samples = sorted(mean(rng.choices(values, k=len(values))) for _ in range(draws))
    return (samples[int(0.025 * draws)], samples[min(draws - 1, int(0.975 * draws))])


__all__ = [
    "BENCHMARK_VERSION",
    "FIDELITY",
    "PARAMETER_SPACE",
    "ActionCaseMetric",
    "AggregateMetric",
    "BenchmarkFidelity",
    "MethodTuningSelection",
    "ProjectTwoActionBenchmarkReport",
    "ProjectTwoActionBenchmarkV02",
    "ProjectTwoActionMethod",
    "ValidationTuningTrial",
]
