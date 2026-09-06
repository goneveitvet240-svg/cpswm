"""Explicit search-plan and primary-utility contracts for structure two.

Why this module exists
----------------------
The withdrawn ``structure-two-action-death-test@0.1`` evaluator scored a single
search action with two unrelated policies at once:

* ``predict(SEARCH)`` answered "which container do you open first?";
* ``_search_cost`` re-derived a *different* ranking, guessing each method's
  family with ``isinstance`` and silently falling back to the raw
  ``locations`` tuple order for anything it did not recognise.

Two consequences followed.  First, permuting the ``locations`` tuple -- a
relabelling of an unordered registry, not new information -- moved AMG's and
DynaMem's per-day search cost even though their prediction never changed.
Second, every method's cost was charged against a plan it never emitted: on
seed 1 the cost model's first container disagreed with the method's own answer
on 13-19 of 32 days for all five arms.

This module makes the plan the only object in the loop.  A method registers
exactly what it will open and in what order; correctness, inspection count,
path length, cost and time are then all read off that one plan.  There is no
implicit extension of a plan to "the rest of the locations", because a
container the method never named is a container the robot was never told to
open.

What this module deliberately does not do
-----------------------------------------
It does not invent a paper-grade price for search.  The frozen combination-A route
(``docs/结构二/方向结构二_组合A技术路线冻结_2026-08-26.md`` and
``configs/project_two_experiments/structure_two_combination_a_v0_1.json``)
fixes *which* quantity is primary -- cumulative action regret, minimised --
and which guardrails cannot be traded away.  It does not fix how a container
inspection, a failed search, or a put-back error convert into that quantity.
Inventing real-world weights here would manufacture the very result the route
was frozen to test, so an unpriced search-plan run reports
:data:`SEARCH_UTILITY_CONTRACT_UNRESOLVED` and yields no cost number at all.
A caller that supplies its own :class:`SearchUtilityContract` gets numbers
back, but a contract without ``frozen_protocol_reference`` is a diagnostic
price and can never authorise a paper-level claim.

The action benchmark does have one explicitly development-only contract.  It
uses dimensionless task regret: a wrong put-back costs one unit and search
costs the fraction of avoidable inspections beyond the oracle first
inspection.  This makes validation selection, case scoring and the reported
primary statistic consume one formula, while remaining structurally unable to
authorize a paper claim or stand in for measured time, energy or monetary cost.
"""

from __future__ import annotations

from enum import StrEnum
from math import isclose
from typing import Annotated, Final, Literal
from uuid import UUID

from pydantic import Field, StrictFloat, model_validator

from cpswm.contracts.base import ContractModel

SEARCH_UTILITY_PROTOCOL_VERSION: Final = "structure-two-search-utility@0.2"
ROUTE_A_DEVELOPMENT_UTILITY_CONTRACT_ID: Final = "structure-two-route-a-development-utility@0.1"
ROUTE_A_DEVELOPMENT_UTILITY_CONTRACT_REFERENCE: Final = (
    "configs/project_two_experiments/structure_two_route_a_utility_contract_v0_1.json"
)

#: Reported instead of a cost whenever the price of a search action is not
#: registered.  This is a fail-closed marker, never a zero and never a one.
SEARCH_UTILITY_CONTRACT_UNRESOLVED: Final = "SEARCH_UTILITY_CONTRACT_UNRESOLVED"

#: Reported instead of a scientific verdict whenever the frozen route does not
#: pin the composition of its own primary utility.
ROUTE_A_PRIMARY_UTILITY_CONTRACT_UNRESOLVED: Final = "ROUTE_A_PRIMARY_UTILITY_CONTRACT_UNRESOLVED"

ROUTE_A_FROZEN_ROUTE_REFERENCE: Final = (
    "docs/结构二/方向结构二_组合A技术路线冻结_2026-08-26.md"
    " + configs/project_two_experiments/structure_two_combination_a_v0_1.json"
)

#: The one quantity the frozen route names as primary, and its direction.
ROUTE_A_PRIMARY_UTILITY_METRIC: Final = "cumulative_action_regret"
ROUTE_A_OPTIMIZATION_DIRECTION: Final = "minimize"

#: Guardrails the frozen route places outside any weighted score.  A guardrail
#: that was not measured is treated exactly like a guardrail that failed.
ROUTE_A_HARD_GUARDRAILS: Final = (
    "owner_contamination",
    "recovery_latency",
    "full_rerun_equivalence",
)

#: Everything the frozen route leaves open that a cumulative-action-regret
#: number would have to assume.  While this tuple is non-empty, no run may
#: report that the route-A primary utility was evaluated.
ROUTE_A_UNRESOLVED_UTILITY_FIELDS: Final = (
    "cumulative_action_regret.component_set",
    "cumulative_action_regret.component_weights",
    "cumulative_action_regret.unit",
    "cumulative_action_regret.put_back_error_cost",
    "cumulative_action_regret.search_path_cost_term",
    "cumulative_action_regret.search_failure_penalty",
    "search_utility.inspection_cost_per_container",
    "search_utility.unfound_target_penalty",
    "search_utility.seconds_per_container_inspection",
    "superiority_margin",
    "hard_guardrail_thresholds",
    "full_rerun_equivalence_measurement",
)

#: Strictness of the primary-utility comparison.  A tie is not a win.
PRIMARY_UTILITY_EPSILON: Final = 1e-9


class RouteADevelopmentUtilityContract(ContractModel):
    """Fixed D0 action-regret semantics that cannot authorize a paper claim."""

    schema_version: Literal["0.1.0"] = "0.1.0"
    contract_id: Literal["structure-two-route-a-development-utility@0.1"] = (
        ROUTE_A_DEVELOPMENT_UTILITY_CONTRACT_ID
    )
    scope: Literal["d0_development_only"] = "d0_development_only"
    primary_utility_metric: Literal["cumulative_action_regret"] = ROUTE_A_PRIMARY_UTILITY_METRIC
    optimization_direction: Literal["minimize"] = ROUTE_A_OPTIMIZATION_DIRECTION
    put_back_regret_rule: Literal["binary_wrong_put_back"] = "binary_wrong_put_back"
    search_regret_rule: Literal["normalized_extra_inspections"] = "normalized_extra_inspections"
    put_back_weight: Annotated[StrictFloat, Field(ge=1.0, le=1.0)] = 1.0
    search_weight: Annotated[StrictFloat, Field(ge=1.0, le=1.0)] = 1.0
    selection_metric: Literal["cumulative_action_regret"] = ROUTE_A_PRIMARY_UTILITY_METRIC
    reference_scope: Literal["all_registered_non_oracle_arms"] = "all_registered_non_oracle_arms"
    search_time_role: Literal["secondary_unpriced_diagnostic"] = "secondary_unpriced_diagnostic"
    paper_claim_allowed: Literal[False] = False
    unresolved_paper_bindings: tuple[str, ...] = Field(min_length=1)
    retained_capabilities: tuple[str, ...] = Field(min_length=5)

    @model_validator(mode="after")
    def _preserve_scope_and_claim_boundary(self) -> RouteADevelopmentUtilityContract:
        required_capabilities = {
            "hidden_event_inference",
            "multi_actor_reasoning",
            "open_world_unknowns",
            "reversible_attribution",
            "embodied_execution_feedback",
        }
        if not required_capabilities.issubset(self.retained_capabilities):
            raise ValueError("development utility contract narrows Structure Two scope")
        required_open = {
            "real_task_cost_calibration",
            "superiority_margin",
            "owner_contamination_threshold",
            "recovery_latency_threshold",
            "full_rerun_equivalence_measurement",
            "independent_custody",
        }
        if not required_open.issubset(self.unresolved_paper_bindings):
            raise ValueError("development utility contract hides a paper-level open binding")
        return self


def current_route_a_development_utility_contract() -> RouteADevelopmentUtilityContract:
    """Return the only development utility contract implemented by this module."""

    return RouteADevelopmentUtilityContract(
        unresolved_paper_bindings=(
            "real_task_cost_calibration",
            "superiority_margin",
            "owner_contamination_threshold",
            "recovery_latency_threshold",
            "full_rerun_equivalence_measurement",
            "independent_custody",
            "faithful_external_baseline_reproduction",
        ),
        retained_capabilities=(
            "hidden_event_inference",
            "multi_actor_reasoning",
            "open_world_unknowns",
            "reversible_attribution",
            "embodied_execution_feedback",
        ),
    )


def normalized_extra_inspection_regret(
    *,
    inspected_container_count: int,
    registered_location_count: int,
    target_found_in_plan: bool,
) -> float:
    """Return dimensionless search regret in ``[0, 1]`` for D0 development.

    The oracle first inspection has zero regret.  The last possible inspection
    has regret one.  A plan that never includes the target also has regret one.
    This is deliberately not seconds, energy or money.
    """

    if registered_location_count < 1:
        raise ValueError("registered location count must be positive")
    if inspected_container_count < 1:
        raise ValueError("inspected container count must be positive")
    if inspected_container_count > registered_location_count:
        raise ValueError("cannot inspect more containers than are registered")
    if not target_found_in_plan:
        return 1.0
    if registered_location_count == 1:
        return 0.0
    return (inspected_container_count - 1) / (registered_location_count - 1)


class SearchPlanKind(StrEnum):
    """Shape of a registered plan, derived from the plan itself."""

    SINGLE_CANDIDATE = "single_candidate"
    PARTIAL_RANKING = "partial_ranking"
    EXHAUSTIVE_RANKING = "exhaustive_ranking"


class SearchUtilityStatus(StrEnum):
    RESOLVED = "resolved"
    UNRESOLVED = SEARCH_UTILITY_CONTRACT_UNRESOLVED


class SearchPlan(ContractModel):
    """The only registered statement of what a method opens, and in what order.

    ``visit_order`` is the robot's actual itinerary: it opens those containers,
    in that sequence, and stops at the target.  Locations absent from
    ``visit_order`` are *not* visited; the evaluator never appends them.
    """

    method_id: str = Field(min_length=1)
    registered_locations: tuple[UUID, ...] = Field(min_length=1)
    visit_order: tuple[UUID, ...] = Field(min_length=1)
    plan_kind: SearchPlanKind

    @staticmethod
    def derive_kind(
        visit_order: tuple[UUID, ...], registered_locations: tuple[UUID, ...]
    ) -> SearchPlanKind:
        if len(visit_order) == len(registered_locations):
            return SearchPlanKind.EXHAUSTIVE_RANKING
        if len(visit_order) == 1:
            return SearchPlanKind.SINGLE_CANDIDATE
        return SearchPlanKind.PARTIAL_RANKING

    @classmethod
    def build(
        cls,
        *,
        method_id: str,
        registered_locations: tuple[UUID, ...],
        visit_order: tuple[UUID, ...],
    ) -> SearchPlan:
        """Build a plan with a canonical registry and derived ``plan_kind``."""

        canonical_locations = tuple(sorted(registered_locations, key=str))

        return cls(
            method_id=method_id,
            registered_locations=canonical_locations,
            visit_order=visit_order,
            plan_kind=cls.derive_kind(visit_order, canonical_locations),
        )

    @model_validator(mode="after")
    def _validate_plan(self) -> SearchPlan:
        if len(set(self.registered_locations)) != len(self.registered_locations):
            raise ValueError("registered search locations must be unique")
        if self.registered_locations != tuple(sorted(self.registered_locations, key=str)):
            raise ValueError("registered search locations must use canonical UUID order")
        if len(set(self.visit_order)) != len(self.visit_order):
            raise ValueError("a search plan cannot inspect the same container twice")
        if not set(self.visit_order) <= set(self.registered_locations):
            raise ValueError("a search plan may only visit registered locations")
        derived = self.derive_kind(self.visit_order, self.registered_locations)
        if self.plan_kind is not derived:
            raise ValueError(
                f"declared search plan kind {self.plan_kind.value} contradicts its contents "
                f"({len(self.visit_order)} of {len(self.registered_locations)} locations); "
                f"the registered shape is {derived.value}"
            )
        return self

    @property
    def first_choice(self) -> UUID:
        """The container the method actually opens first."""

        return self.visit_order[0]


class SearchUtilityContract(ContractModel):
    """Registered prices for the one search semantics.

    No field has a default price.  A run that wants cost numbers must state
    what a container inspection and a failed search are worth, and say which
    frozen protocol registered those numbers.  ``frozen_protocol_reference`` is
    ``None`` for a development or test price: such a contract still yields
    numbers, but :attr:`authorizes_paper_claim` stays false.
    """

    contract_id: str = Field(min_length=1)
    frozen_protocol_reference: Annotated[str, Field(min_length=1)] | None
    inspection_cost_per_container: Annotated[float, Field(gt=0.0)]
    unfound_target_penalty: Annotated[float, Field(ge=0.0)]
    seconds_per_container_inspection: Annotated[float, Field(gt=0.0)] | None = None

    @property
    def authorizes_paper_claim(self) -> bool:
        """Return false until the referenced protocol has independent custody.

        A caller-selected path or URI is provenance metadata, not proof that a
        protocol was frozen before outcomes were observed.  No independently
        enrolled search-utility contract exists yet, so this local contract is
        deliberately unable to authorize a paper claim by itself.
        """

        return False


class SearchScore(ContractModel):
    """One day of search, scored from exactly one :class:`SearchPlan`."""

    method_id: str = Field(min_length=1)
    plan_kind: SearchPlanKind
    plan_length: int = Field(ge=1)
    registered_location_count: int = Field(ge=1)
    inspected_container_count: int = Field(ge=1)
    search_path_length: int = Field(ge=1)
    target_found_in_plan: bool
    first_choice_correct: bool
    status: SearchUtilityStatus
    contract_id: str | None = None
    search_cost: Annotated[float, Field(ge=0.0)] | None = None
    search_time_seconds: Annotated[float, Field(ge=0.0)] | None = None
    unresolved_fields: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _validate_score(self) -> SearchScore:
        if self.plan_length > self.registered_location_count:
            raise ValueError("a search plan cannot be longer than its location registry")
        expected_kind = (
            SearchPlanKind.EXHAUSTIVE_RANKING
            if self.plan_length == self.registered_location_count
            else SearchPlanKind.SINGLE_CANDIDATE
            if self.plan_length == 1
            else SearchPlanKind.PARTIAL_RANKING
        )
        if self.plan_kind is not expected_kind:
            raise ValueError("search score plan kind contradicts its recorded lengths")
        if self.inspected_container_count > self.plan_length:
            raise ValueError("a search cannot inspect more containers than its plan contains")
        if self.search_path_length != self.inspected_container_count:
            raise ValueError("search path length and inspected container count are the same walk")
        if self.first_choice_correct and not self.target_found_in_plan:
            raise ValueError("a correct first choice is by definition a found target")
        if self.first_choice_correct and self.inspected_container_count != 1:
            raise ValueError("a correct first choice must stop after one inspection")
        if (
            self.target_found_in_plan
            and self.inspected_container_count == 1
            and not self.first_choice_correct
        ):
            raise ValueError("a target found on the first inspection is the correct first choice")
        if not self.target_found_in_plan and self.inspected_container_count != self.plan_length:
            raise ValueError("an unsuccessful search must exhaust its registered plan")
        if (self.status is SearchUtilityStatus.RESOLVED) != (self.search_cost is not None):
            raise ValueError(
                "a resolved search score carries a cost and an unresolved one does not"
            )
        if self.status is SearchUtilityStatus.UNRESOLVED:
            if self.contract_id is not None:
                raise ValueError("an unresolved search score cannot name a pricing contract")
            if self.search_time_seconds is not None:
                raise ValueError("an unpriced search cannot carry a priced time")
            required_unresolved_fields = {
                "search_cost",
                "search_time_seconds",
                "search_utility_contract",
            }
            if set(self.unresolved_fields) != required_unresolved_fields:
                raise ValueError("an unresolved search score must name every missing price field")
        else:
            if self.contract_id is None:
                raise ValueError("a resolved search score must name its pricing contract")
            allowed_unresolved_fields = (
                () if self.search_time_seconds is not None else ("search_time_seconds",)
            )
            if self.unresolved_fields != allowed_unresolved_fields:
                raise ValueError("a resolved search score may leave only search time unpriced")
        return self


def score_search_plan(
    plan: SearchPlan,
    target: UUID,
    contract: SearchUtilityContract | None = None,
) -> SearchScore:
    """Score one search action against the plan the method itself registered.

    The semantics are single and complete:

    #. the robot opens ``plan.visit_order`` in order and stops at ``target``;
    #. ``inspected_container_count`` is how many containers it opened, which is
       also the search path length;
    #. if the plan runs out before ``target`` appears, the search *failed*: the
       robot paid for every inspection it made and owes the registered failure
       penalty on top.  A wrong single-candidate search therefore costs one
       inspection **plus** the penalty, never a flat 1.

    Cost and time are returned only when ``contract`` prices them.  Otherwise
    the score is :data:`SEARCH_UTILITY_CONTRACT_UNRESOLVED` and carries no
    number that a comparison could consume.
    """

    if target in plan.visit_order:
        inspected = plan.visit_order.index(target) + 1
        found = True
    else:
        inspected = len(plan.visit_order)
        found = False
    unresolved: list[str] = []
    cost: float | None = None
    seconds: float | None = None
    if contract is None:
        unresolved.extend(("search_cost", "search_time_seconds", "search_utility_contract"))
    else:
        cost = inspected * contract.inspection_cost_per_container
        if not found:
            cost += contract.unfound_target_penalty
        if contract.seconds_per_container_inspection is None:
            unresolved.append("search_time_seconds")
        else:
            seconds = inspected * contract.seconds_per_container_inspection
    status = SearchUtilityStatus.RESOLVED if cost is not None else SearchUtilityStatus.UNRESOLVED
    if status is SearchUtilityStatus.UNRESOLVED and "search_cost" not in unresolved:
        unresolved.insert(0, "search_cost")
    return SearchScore(
        method_id=plan.method_id,
        plan_kind=plan.plan_kind,
        plan_length=len(plan.visit_order),
        registered_location_count=len(plan.registered_locations),
        inspected_container_count=inspected,
        search_path_length=inspected,
        target_found_in_plan=found,
        first_choice_correct=plan.first_choice == target,
        status=status,
        contract_id=None if contract is None else contract.contract_id,
        search_cost=cost,
        search_time_seconds=seconds,
        unresolved_fields=tuple(unresolved),
    )


class SearchUtilityAggregate(ContractModel):
    """Per-method aggregate that keeps unpriced dimensions visibly absent."""

    method_id: str = Field(min_length=1)
    scored_actions: int = Field(ge=0)
    first_choice_error_rate: float = Field(ge=0.0, le=1.0)
    target_not_found_rate: float = Field(ge=0.0, le=1.0)
    mean_inspected_container_count: float = Field(ge=0.0)
    mean_search_path_length: float = Field(ge=0.0)
    mean_search_cost: float | None = None
    mean_search_time_seconds: float | None = None
    status: SearchUtilityStatus
    unresolved_fields: tuple[str, ...] = ()


def aggregate_search_scores(
    method_id: str, scores: tuple[SearchScore, ...]
) -> SearchUtilityAggregate:
    """Aggregate day scores without averaging an unresolved cost into a number."""

    if not scores:
        raise ValueError("cannot aggregate an empty set of search scores")
    if any(score.method_id != method_id for score in scores):
        raise ValueError("cannot aggregate search scores across method identities")
    if len({score.status for score in scores}) > 1:
        raise ValueError("cannot aggregate resolved and unresolved search scores together")
    if len({score.contract_id for score in scores}) > 1:
        raise ValueError("cannot aggregate search scores priced by different contracts")

    count = len(scores)
    unresolved: tuple[str, ...] = ()
    for score in scores:
        for field_name in score.unresolved_fields:
            if field_name not in unresolved:
                unresolved = (*unresolved, field_name)
    costs = [score.search_cost for score in scores if score.search_cost is not None]
    seconds = [
        score.search_time_seconds for score in scores if score.search_time_seconds is not None
    ]
    mean_cost = sum(costs) / count if count and len(costs) == count else None
    mean_seconds = sum(seconds) / count if count and len(seconds) == count else None
    if mean_cost is None and "search_cost" not in unresolved:
        unresolved = ("search_cost", *unresolved)
    return SearchUtilityAggregate(
        method_id=method_id,
        scored_actions=count,
        first_choice_error_rate=(
            sum(not score.first_choice_correct for score in scores) / count if count else 0.0
        ),
        target_not_found_rate=(
            sum(not score.target_found_in_plan for score in scores) / count if count else 0.0
        ),
        mean_inspected_container_count=(
            sum(score.inspected_container_count for score in scores) / count if count else 0.0
        ),
        mean_search_path_length=(
            sum(score.search_path_length for score in scores) / count if count else 0.0
        ),
        mean_search_cost=mean_cost,
        mean_search_time_seconds=mean_seconds,
        status=(
            SearchUtilityStatus.RESOLVED
            if mean_cost is not None
            else SearchUtilityStatus.UNRESOLVED
        ),
        unresolved_fields=unresolved,
    )


# --- route-A primary utility --------------------------------------------------


class RouteAPrimaryUtilityDefinition(ContractModel):
    """What a run actually computed for the frozen primary utility, and what it assumed.

    ``implemented_component_terms`` and ``implemented_unit`` describe the number
    the code produces *today*.  ``unresolved_contract_fields`` names everything
    the frozen route did not pin; while it is non-empty the number is a
    development statistic, not the route-A primary utility.
    """

    primary_utility_metric: str = Field(min_length=1)
    optimization_direction: Literal["minimize", "maximize"]
    frozen_route_reference: str = Field(min_length=1)
    implemented_component_terms: tuple[str, ...] = Field(min_length=1)
    implemented_unit: str = Field(min_length=1)
    oracle_reference_method: str = Field(min_length=1)
    oracle_reference_value: float | None = None
    development_contract_id: str | None = None
    development_contract_reference: str | None = None
    development_primary_utility_evaluated: bool = False
    unresolved_contract_fields: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _match_frozen_route(self) -> RouteAPrimaryUtilityDefinition:
        if self.primary_utility_metric != ROUTE_A_PRIMARY_UTILITY_METRIC:
            raise ValueError("a secondary metric cannot be promoted into route A's primary slot")
        if self.optimization_direction != ROUTE_A_OPTIMIZATION_DIRECTION:
            raise ValueError("route A minimizes its primary utility")
        if self.frozen_route_reference != ROUTE_A_FROZEN_ROUTE_REFERENCE:
            raise ValueError("route A must cite the frozen route reference")
        if len(set(self.unresolved_contract_fields)) != len(self.unresolved_contract_fields):
            raise ValueError("unresolved utility fields must be unique")
        if bool(self.development_contract_id) != bool(self.development_contract_reference):
            raise ValueError("development contract identity and reference must appear together")
        if self.development_primary_utility_evaluated != bool(self.development_contract_id):
            raise ValueError(
                "development evaluation status must match the development contract binding"
            )
        return self

    @property
    def route_a_primary_utility_evaluated(self) -> bool:
        return not self.unresolved_contract_fields


class GuardrailObservation(ContractModel):
    """One hard guardrail.  ``passed=None`` means not measured, which fails closed."""

    guardrail: str = Field(min_length=1)
    passed: bool | None
    detail: str = ""


class SecondaryMetricObservation(ContractModel):
    metric: str = Field(min_length=1)
    value: float
    lower_is_better: bool = True


class MethodUtilityObservation(ContractModel):
    method: str = Field(min_length=1)
    primary_utility: float | None = None
    secondary_metrics: tuple[SecondaryMetricObservation, ...] = ()
    guardrails: tuple[GuardrailObservation, ...] = ()

    def secondary(self, metric: str) -> SecondaryMetricObservation | None:
        for item in self.secondary_metrics:
            if item.metric == metric:
                return item
        return None


class ScientificVerdict(ContractModel):
    """A verdict that can only ever be granted by the frozen primary utility."""

    verdict_id: str = Field(min_length=1)
    protocol_version: str = Field(min_length=1)
    primary_utility_metric: str = Field(min_length=1)
    route_a_primary_utility_evaluated: bool
    superiority_authorized: bool
    paper_claim_allowed: bool
    primary_utility_comparison: str = Field(min_length=1)
    reference_methods: tuple[str, ...] = ()
    secondary_regressions: tuple[str, ...] = ()
    blocking_reasons: tuple[str, ...] = ()
    unresolved_contract_fields: tuple[str, ...] = ()
    summary: str = Field(min_length=1)

    @model_validator(mode="after")
    def _fail_closed(self) -> ScientificVerdict:
        if self.protocol_version != SEARCH_UTILITY_PROTOCOL_VERSION:
            raise ValueError("scientific verdict protocol version is not the corrected protocol")
        if self.primary_utility_metric != ROUTE_A_PRIMARY_UTILITY_METRIC:
            raise ValueError("scientific verdict must use route A's primary utility")
        if self.route_a_primary_utility_evaluated != (not self.unresolved_contract_fields):
            raise ValueError("route-A evaluation status must match unresolved contract fields")
        if self.superiority_authorized and self.blocking_reasons:
            raise ValueError("superiority cannot be authorized while a blocking reason stands")
        if self.superiority_authorized and not self.route_a_primary_utility_evaluated:
            raise ValueError("superiority requires the route-A primary utility to be evaluated")
        if self.paper_claim_allowed and not self.superiority_authorized:
            raise ValueError("a paper claim requires authorized superiority")
        if self.superiority_authorized != (not self.blocking_reasons):
            raise ValueError("authorization status must be derived from the blocking reasons")
        if self.paper_claim_allowed != self.superiority_authorized:
            raise ValueError("paper-claim status must match the route-A superiority verdict")
        if bool(self.secondary_regressions) != (
            "SECONDARY_METRIC_REGRESSION" in self.blocking_reasons
        ):
            raise ValueError("secondary regressions must be reflected in blocking reasons")
        return self


def evaluate_route_a_superiority(
    *,
    definition: RouteAPrimaryUtilityDefinition,
    candidate: MethodUtilityObservation,
    references: tuple[MethodUtilityObservation, ...],
    additional_blocking_reasons: tuple[str, ...] = (),
    verdict_id: str = "structure-two-route-a-superiority",
) -> ScientificVerdict:
    """Decide superiority under the frozen route, failing closed everywhere.

    The order of the checks is the point:

    #. an unresolved utility contract blocks before any number is compared;
    #. a hard guardrail that failed *or was never measured* blocks, and cannot
       be offset by any amount of primary-utility improvement;
    #. the primary utility must beat every reference strictly -- a tie is not a
       win, and a secondary metric can never supply one;
    #. a secondary metric that got worse is recorded and withholds the verdict,
       so "same put-back, longer search" can never read as a complete win.
    """

    blocking: list[str] = []
    if definition.unresolved_contract_fields:
        blocking.append(
            f"{ROUTE_A_PRIMARY_UTILITY_CONTRACT_UNRESOLVED}: "
            + ", ".join(definition.unresolved_contract_fields)
        )

    measured = {item.guardrail for item in candidate.guardrails}
    for guardrail in ROUTE_A_HARD_GUARDRAILS:
        if guardrail not in measured:
            blocking.append(f"HARD_GUARDRAIL_NOT_MEASURED:{guardrail}")
    for item in candidate.guardrails:
        if item.passed is None:
            blocking.append(f"HARD_GUARDRAIL_NOT_MEASURED:{item.guardrail}")
        elif not item.passed:
            blocking.append(f"HARD_GUARDRAIL_FAILED:{item.guardrail}")

    if not references:
        blocking.append("NO_REFERENCE_ARM")
        comparison = "no reference arm was supplied"
    elif candidate.primary_utility is None:
        blocking.append("PRIMARY_UTILITY_NOT_EVALUABLE")
        comparison = f"{definition.primary_utility_metric} is not evaluable for the candidate"
    elif any(item.primary_utility is None for item in references):
        blocking.append("REFERENCE_PRIMARY_UTILITY_NOT_EVALUABLE")
        comparison = f"{definition.primary_utility_metric} is not evaluable for every reference"
    else:
        best_reference = min(
            references,
            key=lambda item: (
                item.primary_utility if item.primary_utility is not None else float("inf"),
                item.method,
            ),
        )
        best = best_reference.primary_utility
        assert best is not None
        candidate_value = candidate.primary_utility
        if candidate_value < best - PRIMARY_UTILITY_EPSILON:
            comparison = (
                f"{definition.primary_utility_metric} {candidate_value:.6g} is strictly better "
                f"than the best reference {best_reference.method} at {best:.6g}"
            )
        elif isclose(candidate_value, best, rel_tol=0.0, abs_tol=PRIMARY_UTILITY_EPSILON):
            blocking.append("PRIMARY_UTILITY_NOT_STRICTLY_BETTER")
            comparison = (
                f"{definition.primary_utility_metric} ties the best reference "
                f"{best_reference.method} at {best:.6g}"
            )
        else:
            blocking.append("PRIMARY_UTILITY_WORSE")
            comparison = (
                f"{definition.primary_utility_metric} {candidate_value:.6g} is worse than the "
                f"best reference {best_reference.method} at {best:.6g}"
            )

    regressions: list[str] = []
    for reference in references:
        for observation in candidate.secondary_metrics:
            other = reference.secondary(observation.metric)
            if other is None:
                continue
            worse = (
                observation.value > other.value + PRIMARY_UTILITY_EPSILON
                if observation.lower_is_better
                else observation.value < other.value - PRIMARY_UTILITY_EPSILON
            )
            if worse:
                regressions.append(
                    f"{observation.metric}: {observation.value:.6g} vs {reference.method} "
                    f"{other.value:.6g}"
                )
    if regressions:
        blocking.append("SECONDARY_METRIC_REGRESSION")

    blocking.extend(additional_blocking_reasons)
    authorized = not blocking
    summary = (
        "route-A superiority authorized"
        if authorized
        else "route-A superiority NOT authorized; " + "; ".join(blocking)
    )
    return ScientificVerdict(
        verdict_id=verdict_id,
        protocol_version=SEARCH_UTILITY_PROTOCOL_VERSION,
        primary_utility_metric=definition.primary_utility_metric,
        route_a_primary_utility_evaluated=definition.route_a_primary_utility_evaluated,
        superiority_authorized=authorized,
        paper_claim_allowed=authorized,
        primary_utility_comparison=comparison,
        reference_methods=tuple(item.method for item in references),
        secondary_regressions=tuple(regressions),
        blocking_reasons=tuple(blocking),
        unresolved_contract_fields=definition.unresolved_contract_fields,
        summary=summary,
    )


LEGACY_PUT_BACK_ONLY_DIAGNOSTIC_ID: Final = "legacy_put_back_only_diagnostic"


class LegacyPutBackOnlyDiagnostic(ContractModel):
    """A put-back-only comparison, structurally unable to read as a scientific win.

    The withdrawn v0.1 status string ranked methods on ``put_back_error_rate``
    alone and phrased the outcome as "new method strictly better".  Under the
    frozen route that sentence is not available: put-back error is one term of
    an unresolved utility, and search was not scored at all.
    """

    diagnostic_id: Literal["legacy_put_back_only_diagnostic"] = LEGACY_PUT_BACK_ONLY_DIAGNOSTIC_ID
    superseded_protocol_version: str = Field(min_length=1)
    comparison_scope: Literal["put_back_error_rate_only"] = "put_back_error_rate_only"
    put_back_comparison: str = Field(min_length=1)
    paper_claim_allowed: Literal[False] = False
    route_a_primary_utility_evaluated: Literal[False] = False
    primary_utility_metric: str = ROUTE_A_PRIMARY_UTILITY_METRIC
    unresolved_contract_fields: tuple[str, ...] = ()
    note: str = Field(min_length=1)

    @property
    def scientific_status(self) -> str:
        return f"{self.diagnostic_id}: {self.put_back_comparison}"


__all__ = [
    "LEGACY_PUT_BACK_ONLY_DIAGNOSTIC_ID",
    "PRIMARY_UTILITY_EPSILON",
    "ROUTE_A_DEVELOPMENT_UTILITY_CONTRACT_ID",
    "ROUTE_A_DEVELOPMENT_UTILITY_CONTRACT_REFERENCE",
    "ROUTE_A_FROZEN_ROUTE_REFERENCE",
    "ROUTE_A_HARD_GUARDRAILS",
    "ROUTE_A_OPTIMIZATION_DIRECTION",
    "ROUTE_A_PRIMARY_UTILITY_CONTRACT_UNRESOLVED",
    "ROUTE_A_PRIMARY_UTILITY_METRIC",
    "ROUTE_A_UNRESOLVED_UTILITY_FIELDS",
    "SEARCH_UTILITY_CONTRACT_UNRESOLVED",
    "SEARCH_UTILITY_PROTOCOL_VERSION",
    "GuardrailObservation",
    "LegacyPutBackOnlyDiagnostic",
    "MethodUtilityObservation",
    "RouteADevelopmentUtilityContract",
    "RouteAPrimaryUtilityDefinition",
    "ScientificVerdict",
    "SearchPlan",
    "SearchPlanKind",
    "SearchScore",
    "SearchUtilityAggregate",
    "SearchUtilityContract",
    "SearchUtilityStatus",
    "SecondaryMetricObservation",
    "aggregate_search_scores",
    "current_route_a_development_utility_contract",
    "evaluate_route_a_superiority",
    "normalized_extra_inspection_regret",
    "score_search_plan",
]
