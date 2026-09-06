"""Structure-two action-level proxy death test.

Protocol versions
-----------------
``structure-two-action-death-test@0.1`` is **withdrawn** for everything it said
about search.  Its evaluator asked each method one question -- "which container
do you open?" -- and then scored a completely different itinerary, guessed from
the method's Python class and, for anything it did not recognise, from the raw
order of the ``locations`` tuple.  Permuting that tuple moved AMG's and
DynaMem's per-day search cost while their prediction stayed identical, and on
seed 1 the scored itinerary's first container disagreed with the method's own
answer on 13-19 of 32 days for all five arms.  Every ``mean_search_cost`` and
every ``search_cost`` emitted under ``@0.1`` is therefore withdrawn.  The
withdrawn computation itself is kept, unexecuted, as
:func:`withdrawn_v0_1_search_cost` so the defect stays pinned by a test.

``structure-two-action-death-test@0.2-search-utility-corrected`` is the
corrected protocol implemented here.  Every method registers an explicit
:class:`~cpswm.system.evaluation_operations.structure_two_search_utility.SearchPlan`,
and search correctness, inspected-container count, path length, cost and time
are all read off that single plan.  Search *cost* is reported only when the
caller supplies a registered price; otherwise the report carries
``SEARCH_UTILITY_CONTRACT_UNRESOLVED`` and no number.

The authoritative matched benchmark is implemented by
``ProjectTwoActionBenchmarkV02`` and is the target of the application runner.
This module's runner is retained only for regression compatibility.

Structure-two action-level matched death test: PCHMP x CCRR x RGRC vs
four reference baselines (AMG / O-STaR / DynaMem / STAR).

This is the *research gate* the structure-two specification demands after the
hidden-event death tests (§4.7 #2 x #5 were only "representation repaired").
A belief model is only a paper contribution if it changes embodied action.

The baselines are reduced-skill re-implementations that share the same
robot-visible contracts and the same deterministic scenario: each baseline is a
minimal, documented strawman of its family (e.g. DynaMem keeps only the latest
state; STAR keeps unpruned frequency counts; AMG keeps a stateless MAP chain).
No baseline sees ground truth. The legacy new-method arm below contains a
stand-in owner-attribution write gate and is therefore classified as a
``reduced-skill proxy`` by v0.2, never as the full project-two arm. Claims from
this legacy class are limited to what this action-level,
single-household scenario can support.  The put-back comparison this module
emits is a ``legacy_put_back_only_diagnostic``: it ranks methods on put-back
error alone, which is one unweighted term of the frozen route's unresolved
cumulative action regret, so it can never read as a scientific win.

Equivariance scope (honest boundary): every method is invariant to the *order*
of the ``locations`` tuple (tuple-order invariance, tested).  The baselines are
label-permutation equivariant after their first observation (their state is
relational: counts and last-observed location).  The new method's habit signal
and context fingerprint are derived from absolute location UUIDs, and the
shared "no information" fallback is a single point; neither can covary with an
arbitrary relabelling of location labels.  This is a documented limitation of
absolute position features plus single-point prediction, not a hidden shortcut.
"""

from __future__ import annotations

import hashlib
import random
import secrets
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from math import isclose
from typing import Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import Field, model_validator

from cpswm.contracts import (
    ActorEvidenceTrack,
    ActorResponsibilityEvidence,
    BaseRecordMetadata,
    EventMechanism,
    EventMechanismEvidence,
    HiddenEventEvidenceTrack,
    ObservationDetectionResult,
    ObservationOutcome,
    RoleBindingEvidence,
    SourceType,
    ordered_role_key,
    parse_ordered_role_key,
)
from cpswm.contracts.base import ContractModel
from cpswm.system.counterfactual_event_hypergraph import (
    DamenHogg2012AMGMatchedEvidenceBaseline,
    OpenWorldRoleConditionedReversibleEventRevisionEngine,
    ProvenanceConstrainedMessagePassing,
)
from cpswm.system.evaluation_operations.structure_two_search_utility import (
    ROUTE_A_PRIMARY_UTILITY_METRIC,
    ROUTE_A_UNRESOLVED_UTILITY_FIELDS,
    LegacyPutBackOnlyDiagnostic,
    SearchPlan,
    SearchPlanKind,
    SearchScore,
    SearchUtilityContract,
    SearchUtilityStatus,
    aggregate_search_scores,
    score_search_plan,
)
from cpswm.system.reproducibility import content_sha256
from cpswm.world_model.habits_transitions import (
    CauseSignalFrame,
    ChangeCause,
    ContextConditionedRegimeReactivator,
    JointCauseFactorizedBOCPD,
    RegimeDecisionKind,
    RegimeLibraryEntry,
)

SCHEMA_VERSION = "0.1.0"

#: Stamped into generated records.  It identifies the *scenario generator*,
#: which this correction does not change, so it stays at ``@0.1``; regenerating
#: a sealed case must keep producing byte-identical historical artifacts.
MODEL_VERSION = "structure-two-action-death-test@0.1"

#: The protocol every report emitted by this module now carries.
PROTOCOL_VERSION = "structure-two-action-death-test@0.2-search-utility-corrected"

#: Retained as a historical regression proxy.  Its search numbers are withdrawn.
SUPERSEDED_PROTOCOL_VERSION = "structure-two-action-death-test@0.1"

ACTION_SCENARIO_GENERATOR_VERSION = "structure-two-action-scenario@0.1"

#: Report fields that record how the input happened to be ordered rather than
#: what was measured.  A location permutation may change these and nothing else.
NON_SEMANTIC_REPORT_FIELDS: tuple[str, ...] = (
    "location_tuple_inputs",
    "location_tuple_digest",
)


def _public_deterministic_uuid(seed: int, *parts: object) -> UUID:
    """The *public* seed->UUID mapping this benchmark must no longer use.

    It is kept only to demonstrate the attack: anyone who knows the seed can
    reproduce every UUID (and hence the truth) from ``uuid5(NAMESPACE_URL,
    "structure-two-action:{seed}:...")``.  Sealed generation uses
    :func:`_sealed_uuid` instead.
    """

    key = f"structure-two-action:{seed}:" + ":".join(str(part) for part in parts)
    return uuid5(NAMESPACE_URL, key)


def _sealed_uuid(sealed_secret: str, seed: int, *parts: object) -> UUID:
    """A seed-derived UUID bound to a secret only the evaluator holds.

    Without ``sealed_secret`` there is no public, enumerable mapping from
    ``seed`` to the generated UUIDs, so a model that only sees the visible
    payload cannot recover the generating seed (or the truth).
    """

    key = content_sha256(f"{sealed_secret}|{seed}|" + "|".join(str(part) for part in parts))
    return UUID(key[:32])


def new_sealed_secret() -> str:
    """A fresh high-entropy evaluator secret (kept private, never sent to models)."""

    return secrets.token_hex(32)


def adversarial_seed_oracle(visible: VisibleActionCase, *, max_seed: int = 99_999) -> int | None:
    """The cheating probe: try to recover the generating seed from the public
    UUID mapping.  Returns the recovered seed, or ``None`` when the evaluator is
    sealed (visible UUIDs do not follow the public mapping).
    """

    for seed in range(max_seed + 1):
        if _public_deterministic_uuid(seed, "object") == visible.object_instance_id:
            return seed
    return None


def _position_value(location: UUID) -> float:
    """A location-order-independent [0, 1] feature for one location UUID.

    This is the location-permutation-equivariant replacement for the former
    ``locations.index(location)`` signal: it depends only on the UUID, never on
    the order of the ``locations`` tuple.
    """

    return float((location.int & 0xFFFF) / 65536.0)


def _position_fingerprint(location: UUID) -> tuple[float, ...]:
    """A centered, multi-component, order-independent context fingerprint.

    SHA-256 bytes are centered to [-0.5, 0.5] so two distinct locations have
    (with overwhelming probability) near-zero cosine similarity.  This is the
    location-permutation-equivariant replacement for the former one-hot index.
    """

    digest = hashlib.sha256(location.bytes).digest()
    return tuple((byte - 128.0) / 128.0 for byte in digest[:16])


class ActionTaskType(StrEnum):
    PUT_BACK = "put_back"
    SEARCH = "search"


class ActionBaselineMethod(StrEnum):
    AMG_2012 = "damen_hogg_2012_amg"
    O_STAR = "o_star_dirichlet"
    DYNAMEM = "dynamem_latest_state"
    STAR = "star_retrieval"
    PCHMP_CCRR_RGRC = "pchmp_ccrr_rgrc"


class ActionDayObservation(ContractModel):
    """Robot-visible inputs for one day; deliberately contains no truth."""

    day: int = Field(ge=0)
    before: ObservationDetectionResult | None = None
    after: ObservationDetectionResult | None = None
    actor_evidence: ActorResponsibilityEvidence | None = None
    mechanism_evidence: EventMechanismEvidence | None = None
    role_evidence: RoleBindingEvidence | None = None

    @model_validator(mode="after")
    def validate_observation(self) -> ActionDayObservation:
        if self.after is not None and self.before is None:
            raise ValueError("an after endpoint requires a before endpoint")
        if self.after is None and any(
            item is not None
            for item in (self.actor_evidence, self.mechanism_evidence, self.role_evidence)
        ):
            raise ValueError("evidence without an observed transition is not robot-visible")
        return self


class ActionDayTruth(ContractModel):
    """Evaluator-only truth for one day."""

    day: int = Field(ge=0)
    true_location_after: UUID
    true_owner_habit_location: UUID
    true_actor: str = Field(min_length=1)
    mechanism: EventMechanism


class VisibleActionCase(ContractModel):
    """Model-visible inputs only; this contract structurally excludes truth.

    ``case_id`` is an opaque UUID so a model cannot recover the generating seed
    from the case identity, and the seed lives only in the evaluator envelope
    (:class:`ActionGeneratedCase`), which models never receive.
    """

    case_id: UUID
    object_instance_id: UUID
    owner_actor: str = Field(min_length=1)
    guest_actor: str = Field(min_length=1)
    locations: tuple[UUID, ...] = Field(min_length=2)
    days: tuple[ActionDayObservation, ...] = Field(min_length=1)


class ActionGeneratedCase(ContractModel):
    """An evaluator case: a visible slice plus evaluator-only truth and seed."""

    seed: int = Field(ge=0)
    visible: VisibleActionCase
    truth_by_day: dict[int, ActionDayTruth]

    @model_validator(mode="after")
    def validate_binding(self) -> ActionGeneratedCase:
        if set(self.truth_by_day) != {obs.day for obs in self.visible.days}:
            raise ValueError("truth must cover exactly the observed days")
        return self


class ActionSuite(ContractModel):
    generator_version: str = Field(min_length=1)
    cases: tuple[ActionGeneratedCase, ...] = Field(min_length=1)


class ActionMethodPrediction(ContractModel):
    case_id: UUID
    method: ActionBaselineMethod
    day: int = Field(ge=0)
    put_back_location: UUID
    search_location: UUID


class ActionDayResult(ContractModel):
    """One scored day.

    ``search_correct``, ``inspected_container_count``, ``search_path_length``,
    ``search_cost`` and ``search_time_seconds`` are all read off the single
    :class:`SearchPlan` the method registered for that day.  ``search_cost`` is
    ``None`` -- never a flat ``1`` -- whenever the price of an inspection or of
    a failed search is not registered.
    """

    case_id: UUID
    method: ActionBaselineMethod
    day: int = Field(ge=0)
    guest_move_day: bool
    put_back_correct: bool
    search_plan: SearchPlan
    search_target: UUID
    search_correct: bool
    search_plan_kind: SearchPlanKind
    search_plan_length: int = Field(ge=1)
    registered_location_count: int = Field(ge=1)
    inspected_container_count: int = Field(ge=1)
    search_path_length: int = Field(ge=1)
    search_target_found: bool
    search_utility_status: SearchUtilityStatus
    search_utility_contract_id: str | None = None
    search_cost: float | None = None
    search_time_seconds: float | None = None
    search_unresolved_fields: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _bind_to_raw_search_inputs(self) -> ActionDayResult:
        if self.search_plan.method_id != self.method.value:
            raise ValueError("day result method does not own its recorded search plan")
        expected = score_search_plan(self.search_plan, self.search_target)
        structural = (
            (self.search_plan_kind, expected.plan_kind, "plan kind"),
            (self.search_plan_length, expected.plan_length, "plan length"),
            (
                self.registered_location_count,
                expected.registered_location_count,
                "registered location count",
            ),
            (
                self.inspected_container_count,
                expected.inspected_container_count,
                "inspected container count",
            ),
            (self.search_path_length, expected.search_path_length, "search path length"),
            (self.search_target_found, expected.target_found_in_plan, "target-found flag"),
            (self.search_correct, expected.first_choice_correct, "first-choice correctness"),
        )
        for observed, derived, label in structural:
            if observed != derived:
                raise ValueError(f"day result {label} is not derived from its search plan")
        return self


class ActionMethodReport(ContractModel):
    method: ActionBaselineMethod
    case_count: int = Field(ge=0)
    put_back_error_rate: float = Field(ge=0.0, le=1.0)
    search_error_rate: float = Field(ge=0.0, le=1.0)
    search_target_not_found_rate: float = Field(ge=0.0, le=1.0)
    mean_inspected_container_count: float = Field(ge=0.0)
    mean_search_path_length: float = Field(ge=0.0)
    mean_search_cost: float | None = None
    mean_search_time_seconds: float | None = None
    search_utility_status: SearchUtilityStatus
    search_unresolved_fields: tuple[str, ...] = ()
    guest_day_put_back_error_days: int = Field(ge=0)
    total_put_back_errors: int = Field(ge=0)
    total_search_errors: int = Field(ge=0)


class ActionLocationTupleInput(ContractModel):
    """Raw registry order retained solely to make its audit digest recomputable."""

    case_id: UUID
    locations: tuple[UUID, ...] = Field(min_length=2)

    @model_validator(mode="after")
    def _require_unique_locations(self) -> ActionLocationTupleInput:
        if len(set(self.locations)) != len(self.locations):
            raise ValueError("raw location tuple inputs must contain unique locations")
        return self


class StructureTwoActionDeathTestReport(ContractModel):
    """A report whose only scientific claim is an explicitly labelled diagnostic."""

    protocol_version: str = Field(min_length=1)
    superseded_protocol_version: str = Field(min_length=1)
    generator_version: str = Field(min_length=1)
    location_tuple_inputs: tuple[ActionLocationTupleInput, ...] = Field(min_length=1)
    location_tuple_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    search_utility_contract: SearchUtilityContract | None = None
    search_utility_contract_id: str | None = None
    search_utility_status: SearchUtilityStatus
    method_reports: tuple[ActionMethodReport, ...]
    case_results: tuple[ActionDayResult, ...]
    legacy_diagnostic: LegacyPutBackOnlyDiagnostic
    scientific_status: str

    @model_validator(mode="after")
    def _reject_protocol_substitution(self) -> StructureTwoActionDeathTestReport:
        """A corrected report cannot be relabelled as the withdrawn protocol, or vice versa.

        Both directions matter.  Stamping ``@0.1`` on these numbers would let a
        withdrawn ``mean_search_cost`` be quietly reinstated; stamping ``@0.2``
        on an old artifact would upgrade withdrawn numbers into corrected ones.
        """

        if self.protocol_version != PROTOCOL_VERSION:
            raise ValueError(
                f"this contract emits {PROTOCOL_VERSION!r}; it cannot carry "
                f"{self.protocol_version!r}"
            )
        if self.generator_version != ACTION_SCENARIO_GENERATOR_VERSION:
            raise ValueError("action scenario generator protocol substitution")
        if self.superseded_protocol_version != SUPERSEDED_PROTOCOL_VERSION:
            raise ValueError(f"the superseded protocol is fixed at {SUPERSEDED_PROTOCOL_VERSION!r}")
        if self.protocol_version == self.superseded_protocol_version:
            raise ValueError("a protocol cannot supersede itself")
        if self.legacy_diagnostic.superseded_protocol_version != SUPERSEDED_PROTOCOL_VERSION:
            raise ValueError("the legacy diagnostic must name the protocol it supersedes")
        if self.scientific_status != self.legacy_diagnostic.scientific_status:
            raise ValueError("scientific status must be derived from the legacy diagnostic")
        if self.legacy_diagnostic.primary_utility_metric != ROUTE_A_PRIMARY_UTILITY_METRIC:
            raise ValueError("legacy diagnostic must name route A's primary utility")
        if self.legacy_diagnostic.unresolved_contract_fields != (ROUTE_A_UNRESOLVED_UTILITY_FIELDS):
            raise ValueError("legacy diagnostic must preserve every unresolved utility field")
        if (self.search_utility_status is SearchUtilityStatus.RESOLVED) != (
            self.search_utility_contract_id is not None
        ):
            raise ValueError("a resolved search utility must name the contract that priced it")
        if (self.search_utility_contract is None) != (self.search_utility_contract_id is None):
            raise ValueError("the report must retain the pricing contract used for recomputation")
        if (
            self.search_utility_contract is not None
            and self.search_utility_contract.contract_id != self.search_utility_contract_id
        ):
            raise ValueError("search utility contract id does not match the retained contract")

        tuple_inputs = {item.case_id: item.locations for item in self.location_tuple_inputs}
        if len(tuple_inputs) != len(self.location_tuple_inputs):
            raise ValueError("raw location tuple inputs must have unique case identities")
        expected_tuple_digest = content_sha256(
            [[str(location) for location in item.locations] for item in self.location_tuple_inputs]
        )
        if self.location_tuple_digest != expected_tuple_digest:
            raise ValueError("location tuple digest is not derived from retained raw inputs")

        seen: set[tuple[ActionBaselineMethod, UUID, int]] = set()
        grouped: dict[ActionBaselineMethod, list[ActionDayResult]] = {}
        for result in self.case_results:
            key = (result.method, result.case_id, result.day)
            if key in seen:
                raise ValueError("duplicate method/case/day result")
            seen.add(key)
            grouped.setdefault(result.method, []).append(result)
            raw_locations = tuple_inputs.get(result.case_id)
            if raw_locations is None or set(result.search_plan.registered_locations) != set(
                raw_locations
            ):
                raise ValueError("day result search registry is not bound to raw tuple inputs")
            expected = score_search_plan(
                result.search_plan,
                result.search_target,
                self.search_utility_contract,
            )
            observed_score = (
                result.search_utility_status,
                result.search_utility_contract_id,
                result.search_cost,
                result.search_time_seconds,
                result.search_unresolved_fields,
            )
            expected_score = (
                expected.status,
                expected.contract_id,
                expected.search_cost,
                expected.search_time_seconds,
                expected.unresolved_fields,
            )
            if observed_score != expected_score:
                raise ValueError("day result pricing fields fail deterministic recomputation")

        reports = {report.method: report for report in self.method_reports}
        if len(reports) != len(self.method_reports):
            raise ValueError("method reports must have unique identities")
        if set(reports) != set(grouped):
            raise ValueError("method reports must cover exactly the recorded day results")
        expected_case_ids = set(tuple_inputs)
        coordinate_sets = [
            {(result.case_id, result.day) for result in results} for results in grouped.values()
        ]
        if any(
            {result.case_id for result in results} != expected_case_ids
            for results in grouped.values()
        ):
            raise ValueError("every method must cover every retained action case")
        if coordinate_sets and any(
            coordinates != coordinate_sets[0] for coordinates in coordinate_sets[1:]
        ):
            raise ValueError("every method must cover the same case/day evaluation units")
        for method, results in grouped.items():
            report = reports[method]
            scores = tuple(
                score_search_plan(
                    result.search_plan,
                    result.search_target,
                    self.search_utility_contract,
                )
                for result in results
            )
            aggregate = aggregate_search_scores(method.value, scores)
            total = len(results)
            put_errors = sum(not result.put_back_correct for result in results)
            search_errors = sum(not result.search_correct for result in results)
            guest_errors = sum(
                result.guest_move_day and not result.put_back_correct for result in results
            )
            expected_report = {
                "case_count": len({result.case_id for result in results}),
                "put_back_error_rate": put_errors / total,
                "search_error_rate": aggregate.first_choice_error_rate,
                "search_target_not_found_rate": aggregate.target_not_found_rate,
                "mean_inspected_container_count": aggregate.mean_inspected_container_count,
                "mean_search_path_length": aggregate.mean_search_path_length,
                "mean_search_cost": aggregate.mean_search_cost,
                "mean_search_time_seconds": aggregate.mean_search_time_seconds,
                "search_utility_status": aggregate.status,
                "search_unresolved_fields": aggregate.unresolved_fields,
                "guest_day_put_back_error_days": guest_errors,
                "total_put_back_errors": put_errors,
                "total_search_errors": search_errors,
            }
            for field_name, expected_value in expected_report.items():
                if getattr(report, field_name) != expected_value:
                    raise ValueError(
                        f"method report {field_name} fails deterministic recomputation"
                    )

        new = reports.get(ActionBaselineMethod.PCHMP_CCRR_RGRC)
        baselines = [
            report
            for method, report in reports.items()
            if method is not ActionBaselineMethod.PCHMP_CCRR_RGRC
        ]
        if new is None:
            expected_comparison = "new method not run"
        elif not baselines:
            expected_comparison = "no baselines run"
        else:
            best = min(report.put_back_error_rate for report in baselines)
            if new.put_back_error_rate < best - 1e-9:
                expected_comparison = "new method lower put-back error than every baseline"
            elif isclose(new.put_back_error_rate, best, rel_tol=0.0, abs_tol=1e-9):
                expected_comparison = "new method ties the best baseline on put-back error"
            else:
                expected_comparison = "new method higher put-back error than the best baseline"
        if self.legacy_diagnostic.put_back_comparison != expected_comparison:
            raise ValueError("legacy diagnostic fails deterministic recomputation")
        return self


# --- scenario generation -----------------------------------------------------


class StructureTwoActionScenarioGenerator:
    """Deterministic household action scenario generator.

    Timeline (per object, ``duration_days``):

    * days 0..abrupt-1: stable regime at ``loc_0``;
    * guest days (inclusive window): guest relocates the object to ``loc_guest``
      (direct or handoff) while the owner's true habit stays at ``loc_0``;
    * abrupt..recurrence-1: owner habit shifts to ``loc_1``;
    * recurrence..end: owner resumes ``loc_0`` (the CCRR reactivation signal).

    Selective observation drops a deterministic fraction of transition days.

    UUIDs are bound to ``sealed_secret``: an evaluator that keeps the secret
    private produces a sealed artifact whose visible UUIDs cannot be inverted
    to the generating seed (see :func:`adversarial_seed_oracle`).
    """

    generator_version = ACTION_SCENARIO_GENERATOR_VERSION

    def __init__(
        self,
        *,
        duration_days: int = 32,
        guest_window: tuple[int, int] = (7, 14),
        abrupt_day: int = 17,
        recurrence_day: int = 26,
        observation_coverage: float = 0.7,
        sealed_secret: str = "structure-two-action-dev-secret-v0.1",
        include_open_world_unknown_events: bool = False,
        unknown_event_days: tuple[int, ...] = (1,),
    ) -> None:
        if duration_days < 10:
            raise ValueError("duration_days must be at least 10")
        if not 0.0 < observation_coverage <= 1.0:
            raise ValueError("observation_coverage must lie in (0, 1]")
        if not guest_window[0] < guest_window[1] < abrupt_day < recurrence_day < duration_days:
            raise ValueError("scenario windows must be strictly ordered")
        if not sealed_secret.strip():
            raise ValueError("sealed_secret must be non-empty")
        if any(day < 0 or day >= duration_days for day in unknown_event_days):
            raise ValueError("unknown event days must lie inside the scenario")
        self.duration_days = duration_days
        self.guest_window = guest_window
        self.abrupt_day = abrupt_day
        self.recurrence_day = recurrence_day
        self.observation_coverage = observation_coverage
        self.sealed_secret = sealed_secret
        self.include_open_world_unknown_events = include_open_world_unknown_events
        self.unknown_event_days = frozenset(unknown_event_days)

    def generate(self, seed: int) -> ActionGeneratedCase:
        rng = random.Random(f"structure-two-action-{seed}")
        owner = "owner"
        guest = "guest"
        secret = self.sealed_secret
        object_id = _sealed_uuid(secret, seed, "object")
        household_id = _sealed_uuid(secret, seed, "household")
        session_id = _sealed_uuid(secret, seed, "session")
        trace_id = _sealed_uuid(secret, seed, "trace")
        locations = tuple(_sealed_uuid(secret, seed, "location", i) for i in range(4))
        loc_0, loc_1, loc_guest, loc_decoy = locations

        observations: list[ActionDayObservation] = []
        truth: dict[int, ActionDayTruth] = {}
        for day in range(self.duration_days):
            in_guest_window = self.guest_window[0] <= day <= self.guest_window[1]
            if day < self.abrupt_day:
                owner_habit = loc_0
            elif day < self.recurrence_day:
                owner_habit = loc_1
            else:
                owner_habit = loc_0

            # Every day is a real relocation: the object is taken from its
            # overnight decoy spot to the daytime spot (owner habit location or
            # the guest's location).  This guarantees before != after on every
            # observed day while keeping the owner habit location meaningful.
            if self.include_open_world_unknown_events and day in self.unknown_event_days:
                true_actor = "unknown_actor"
                true_location = loc_guest
                mechanism = EventMechanism.UNKNOWN_MECHANISM
            elif in_guest_window:
                true_actor = guest
                true_location = loc_guest
                mechanism = (
                    EventMechanism.HANDOFF_RELOCATION
                    if rng.random() < 0.5
                    else (EventMechanism.DIRECT_RELOCATION)
                )
            else:
                true_actor = owner
                true_location = owner_habit
                mechanism = EventMechanism.DIRECT_RELOCATION

            truth[day] = ActionDayTruth(
                day=day,
                true_location_after=true_location,
                true_owner_habit_location=owner_habit,
                true_actor=true_actor,
                mechanism=mechanism,
            )

            # Selective observation: guest days are slightly more likely to be
            # missed (the observation process is not uniform).
            if in_guest_window:
                observed = rng.random() < self.observation_coverage * 0.8
            else:
                observed = rng.random() < self.observation_coverage
            if not observed:
                observations.append(ActionDayObservation(day=day))
                continue

            base = datetime(2026, 1, 1, 8, 0, tzinfo=UTC) + timedelta(days=day)
            before = self._detection(
                object_id=object_id,
                location_id=loc_decoy,
                at=base,
                record_id=_sealed_uuid(secret, seed, day, "before"),
                household_id=household_id,
                session_id=session_id,
                trace_id=trace_id,
            )
            after = self._detection(
                object_id=object_id,
                location_id=true_location,
                at=base + timedelta(minutes=10),
                record_id=_sealed_uuid(secret, seed, day, "after"),
                household_id=household_id,
                session_id=session_id,
                trace_id=trace_id,
            )
            actor_evidence = self._actor_evidence(
                before=before,
                after=after,
                true_actor=true_actor,
                owner=owner,
                guest=guest,
                at=base + timedelta(minutes=10),
                trace_id=trace_id,
                evidence_cluster_id=_sealed_uuid(secret, seed, day, "actor-cluster"),
                evidence_record_id=_sealed_uuid(secret, seed, day, "actor-record"),
            )
            mechanism_evidence = None
            role_evidence = None
            if mechanism in {
                EventMechanism.HANDOFF_RELOCATION,
                EventMechanism.UNKNOWN_MECHANISM,
            }:
                mechanism_evidence = self._mechanism_evidence(
                    after=after,
                    mechanism=mechanism,
                    at=base + timedelta(minutes=10),
                    trace_id=trace_id,
                    evidence_cluster_id=_sealed_uuid(secret, seed, day, "mechanism-cluster"),
                    evidence_record_id=_sealed_uuid(secret, seed, day, "mechanism-record"),
                )
                if mechanism == EventMechanism.HANDOFF_RELOCATION:
                    role_evidence = self._role_evidence(
                        after=after,
                        owner=owner,
                        guest=guest,
                        true_actor=true_actor,
                        at=base + timedelta(minutes=10),
                        trace_id=trace_id,
                        evidence_cluster_id=_sealed_uuid(secret, seed, day, "role-cluster"),
                        evidence_record_id=_sealed_uuid(secret, seed, day, "role-record"),
                    )
            observations.append(
                ActionDayObservation(
                    day=day,
                    before=before,
                    after=after,
                    actor_evidence=actor_evidence,
                    mechanism_evidence=mechanism_evidence,
                    role_evidence=role_evidence,
                )
            )
        return ActionGeneratedCase(
            seed=seed,
            visible=VisibleActionCase(
                case_id=_sealed_uuid(secret, seed, "case-id"),
                object_instance_id=object_id,
                owner_actor=owner,
                guest_actor=guest,
                locations=locations,
                days=tuple(observations),
            ),
            truth_by_day=truth,
        )

    @staticmethod
    def _detection(
        *,
        object_id: UUID,
        location_id: UUID,
        at: datetime,
        record_id: UUID,
        household_id: UUID,
        session_id: UUID,
        trace_id: UUID,
    ) -> ObservationDetectionResult:
        return ObservationDetectionResult(
            metadata=BaseRecordMetadata(
                schema_name="cpswm.ObservationDetectionResult",
                schema_version=SCHEMA_VERSION,
                record_id=record_id,
                household_id=household_id,
                session_id=session_id,
                trace_id=trace_id,
                recorded_time=at,
                source_type=SourceType.SIMULATION,
                source_id="structure-two-action-scenario",
                model_version=MODEL_VERSION,
            ),
            observation_opportunity_id=record_id,
            outcome=ObservationOutcome.DETECTED,
            detected_object_instance_id=object_id,
            detected_location_id=location_id,
            detection_time=at,
        )

    @staticmethod
    def _actor_evidence(
        *,
        before: ObservationDetectionResult,
        after: ObservationDetectionResult,
        true_actor: str,
        owner: str,
        guest: str,
        at: datetime,
        trace_id: UUID,
        evidence_cluster_id: UUID,
        evidence_record_id: UUID,
    ) -> ActorResponsibilityEvidence:
        assert after.detected_object_instance_id is not None
        if true_actor == "unknown_actor":
            posterior = {owner: 0.1, guest: 0.1, "unknown_actor": 0.8}
        else:
            posterior = {
                owner: 0.80 if true_actor == owner else 0.15,
                guest: 0.15 if true_actor == owner else 0.80,
                "unknown_actor": 0.05,
            }
        return ActorResponsibilityEvidence(
            metadata=BaseRecordMetadata(
                schema_name="cpswm.ActorResponsibilityEvidence",
                schema_version=SCHEMA_VERSION,
                record_id=evidence_record_id,
                household_id=before.metadata.household_id,
                session_id=before.metadata.session_id,
                trace_id=trace_id,
                recorded_time=at,
                source_type=SourceType.SIMULATION,
                source_id="structure-two-action-scenario",
                model_version=MODEL_VERSION,
            ),
            source_detection_result_id=after.metadata.record_id,
            object_instance_id=after.detected_object_instance_id,
            evidence_time=at,
            actor_posterior=posterior,
            reference_actor_prior={owner: 1 / 3, guest: 1 / 3, "unknown_actor": 1 / 3},
            evidence_cluster_id=evidence_cluster_id,
            evidence_track=ActorEvidenceTrack.CONTROLLED_NOISE,
            evidence_model_id="structure-two-action-actor-model@0.1",
        )

    @staticmethod
    def _mechanism_evidence(
        *,
        after: ObservationDetectionResult,
        mechanism: EventMechanism,
        at: datetime,
        trace_id: UUID,
        evidence_cluster_id: UUID,
        evidence_record_id: UUID,
    ) -> EventMechanismEvidence:
        assert after.detected_object_instance_id is not None
        if mechanism is EventMechanism.UNKNOWN_MECHANISM:
            posterior = {
                EventMechanism.DIRECT_RELOCATION: 0.1,
                EventMechanism.HANDOFF_RELOCATION: 0.1,
                EventMechanism.UNKNOWN_MECHANISM: 0.8,
            }
        else:
            posterior = {
                EventMechanism.DIRECT_RELOCATION: (
                    0.1 if mechanism == EventMechanism.HANDOFF_RELOCATION else 0.9
                ),
                EventMechanism.HANDOFF_RELOCATION: (
                    0.9 if mechanism == EventMechanism.HANDOFF_RELOCATION else 0.1
                ),
            }
        return EventMechanismEvidence(
            metadata=BaseRecordMetadata(
                schema_name="cpswm.EventMechanismEvidence",
                schema_version=SCHEMA_VERSION,
                record_id=evidence_record_id,
                household_id=after.metadata.household_id,
                session_id=after.metadata.session_id,
                trace_id=trace_id,
                recorded_time=at,
                source_type=SourceType.SIMULATION,
                source_id="structure-two-action-scenario",
                model_version=MODEL_VERSION,
            ),
            source_detection_result_id=after.metadata.record_id,
            object_instance_id=after.detected_object_instance_id,
            evidence_time=at,
            mechanism_posterior=posterior,
            reference_mechanism_prior={key: 1.0 / len(posterior) for key in posterior},
            evidence_cluster_id=evidence_cluster_id,
            evidence_track=HiddenEventEvidenceTrack.CONTROLLED_NOISE,
            evidence_model_id="structure-two-action-mechanism-model@0.1",
        )

    @staticmethod
    def _role_evidence(
        *,
        after: ObservationDetectionResult,
        owner: str,
        guest: str,
        true_actor: str,
        at: datetime,
        trace_id: UUID,
        evidence_cluster_id: UUID,
        evidence_record_id: UUID,
    ) -> RoleBindingEvidence:
        assert after.detected_object_instance_id is not None
        roles = {
            ordered_role_key(owner, guest): 0.8 if true_actor == guest else 0.2,
            ordered_role_key(guest, owner): 0.2 if true_actor == guest else 0.8,
        }
        return RoleBindingEvidence(
            metadata=BaseRecordMetadata(
                schema_name="cpswm.RoleBindingEvidence",
                schema_version=SCHEMA_VERSION,
                record_id=evidence_record_id,
                household_id=after.metadata.household_id,
                session_id=after.metadata.session_id,
                trace_id=trace_id,
                recorded_time=at,
                source_type=SourceType.SIMULATION,
                source_id="structure-two-action-scenario",
                model_version=MODEL_VERSION,
            ),
            source_detection_result_id=after.metadata.record_id,
            object_instance_id=after.detected_object_instance_id,
            evidence_time=at,
            ordered_role_posterior=roles,
            reference_ordered_role_prior={
                ordered_role_key(owner, guest): 0.5,
                ordered_role_key(guest, owner): 0.5,
            },
            evidence_cluster_id=evidence_cluster_id,
            evidence_track=HiddenEventEvidenceTrack.CONTROLLED_NOISE,
            evidence_model_id="structure-two-action-role-model@0.1",
        )


# --- method implementations ---------------------------------------------------


def _fallback_location(locations: tuple[UUID, ...]) -> UUID:
    """Order-independent default location: the UUID-smallest location.

    This makes every baseline's "no information yet" fallback invariant to the
    order of the ``locations`` tuple (tuple-order invariance).  It is *not*
    label-permutation equivariant: a single-point fallback that depends only on
    location labels cannot covary with an arbitrary relabelling of those labels.
    """

    return min(locations, key=str)


def _single_candidate_plan(
    method: ActionBaselineMethod, locations: tuple[UUID, ...], candidate: UUID
) -> SearchPlan:
    """Register the one container a single-point search method actually opens.

    Every method in this module answers the search task with one location, so
    every plan here is a ``single_candidate`` plan.  The withdrawn v0.1 cost
    model quietly handed O-STaR, STAR and the new method a free multi-container
    belief ranking their action interface never emitted, and handed AMG and
    DynaMem the raw ``locations`` tuple order.  Neither was a plan any method
    had registered.
    """

    return SearchPlan.build(
        method_id=method.value,
        registered_locations=locations,
        visit_order=(candidate,),
    )


@dataclass(slots=True)
class _OwnerHabitState:
    """Per-regime owner-habit soft counts (CCRR stage memory).

    The key CCRR behaviour: counts are stored **per regime**, so a ``create``
    decision archives the old stage and starts a fresh one (fast adaptation to
    a new habit), while a ``reactivate`` decision swaps back to an archived
    stage and immediately reuses its counts (fast recovery of an old habit).
    A single flat count vector cannot do this.
    """

    owner: str
    guest: str
    locations: tuple[UUID, ...]
    active_regime_id: str = "stable"
    regimes: dict[str, dict[UUID, float]] = field(default_factory=dict)
    last_location: UUID | None = None
    guest_recent_location: UUID | None = None

    def __post_init__(self) -> None:
        self.regimes.setdefault("stable", {})

    def _active_counts(self) -> dict[UUID, float]:
        return self.regimes.setdefault(self.active_regime_id, {})

    def owner_posterior(self) -> dict[UUID, float]:
        counts = self._active_counts()
        total = sum(counts.values())
        if total <= 0.0:
            uniform = 1.0 / len(self.locations)
            return {location: uniform for location in self.locations}
        return {location: counts.get(location, 0.0) / total for location in self.locations}

    def argmax_owner(self) -> UUID:
        posterior = self.owner_posterior()
        # Tie-break on the location UUID itself so the argmax is invariant to
        # the order of the ``locations`` tuple (location permutation
        # equivariance).
        return max(
            self.locations,
            key=lambda location: (posterior[location], str(location)),
        )

    def write_owner(self, location: UUID) -> None:
        counts = self._active_counts()
        counts[location] = counts.get(location, 0.0) + 1.0


class _AMGMethod:
    """Damen-Hogg 2012 AMG adaptation: MAP event chain, no habit / no regime."""

    name = ActionBaselineMethod.AMG_2012

    def __init__(self, case: VisibleActionCase) -> None:
        self.case = case
        self.engine = OpenWorldRoleConditionedReversibleEventRevisionEngine()
        self.amg = DamenHogg2012AMGMatchedEvidenceBaseline()
        self.last_location: UUID | None = None
        self.owner_habit_location: UUID | None = None

    def observe(self, obs: ActionDayObservation) -> None:
        if obs.after is None or obs.before is None:
            return
        self.last_location = obs.after.detected_location_id
        # AMG has no habit memory; it commits to the MAP event chain's final
        # placement actor.  If the MAP places by the owner, record the location
        # as the (stateless) owner belief; otherwise ignore it.
        if obs.actor_evidence is not None:
            actor_likelihoods = {}
            for actor, posterior in obs.actor_evidence.actor_posterior.items():
                prior = max(1e-12, obs.actor_evidence.reference_actor_prior[actor])
                evidence_ratio = max(1e-12, posterior) / prior
                actor_likelihoods[actor] = evidence_ratio / (1.0 + evidence_ratio)
            mechanism_likelihoods = {
                EventMechanism.DIRECT_RELOCATION: 0.5,
                EventMechanism.HANDOFF_RELOCATION: 0.5,
            }
            if obs.mechanism_evidence is not None:
                mechanism_likelihoods = obs.mechanism_evidence.mechanism_posterior
            role_likelihoods = {
                (self.case.owner_actor, self.case.guest_actor): 0.5,
                (self.case.guest_actor, self.case.owner_actor): 0.5,
            }
            if obs.role_evidence is not None:
                role_likelihoods = {
                    parse_ordered_role_key(key): value
                    for key, value in obs.role_evidence.ordered_role_posterior.items()
                }
            try:
                prediction = self.amg.predict_matched(
                    before=obs.before,
                    after=obs.after,
                    actor_event_likelihoods=actor_likelihoods,
                    mechanism_likelihoods=mechanism_likelihoods,
                    handoff_role_likelihoods=role_likelihoods,
                )
                if set(prediction.maximizing_responsible_actor_keys) == {self.case.owner_actor}:
                    self.owner_habit_location = obs.after.detected_location_id
            except ValueError:
                pass

    def search_plan(self) -> SearchPlan:
        candidate = self.last_location or _fallback_location(self.case.locations)
        return _single_candidate_plan(self.name, self.case.locations, candidate)

    def predict(self, task: ActionTaskType) -> UUID:
        if task == ActionTaskType.SEARCH:
            return self.search_plan().first_choice
        if self.owner_habit_location is not None:
            return self.owner_habit_location
        return _fallback_location(self.case.locations)


class _OStarMethod:
    """O-STaR adaptation: Dirichlet location counts, no actor isolation."""

    name = ActionBaselineMethod.O_STAR

    def __init__(self, case: VisibleActionCase) -> None:
        self.case = case
        self.counts: dict[UUID, float] = {location: 1.0 for location in case.locations}
        self.last_location: UUID | None = None

    def observe(self, obs: ActionDayObservation) -> None:
        if obs.after is None:
            return
        location = obs.after.detected_location_id
        if location is not None:
            self.last_location = location
            self.counts[location] += 1.0

    def search_plan(self) -> SearchPlan:
        candidate = self.last_location or _fallback_location(self.case.locations)
        return _single_candidate_plan(self.name, self.case.locations, candidate)

    def predict(self, task: ActionTaskType) -> UUID:
        if task == ActionTaskType.SEARCH:
            return self.search_plan().first_choice
        return max(
            self.counts,
            key=lambda location: (self.counts[location], str(location)),
        )


class _DynaMemMethod:
    """DynaMem adaptation: latest observed state only, no habit model."""

    name = ActionBaselineMethod.DYNAMEM

    def __init__(self, case: VisibleActionCase) -> None:
        self.case = case
        self.last_location: UUID | None = None

    def observe(self, obs: ActionDayObservation) -> None:
        if obs.after is not None:
            self.last_location = obs.after.detected_location_id

    def search_plan(self) -> SearchPlan:
        candidate = self.last_location or _fallback_location(self.case.locations)
        return _single_candidate_plan(self.name, self.case.locations, candidate)

    def predict(self, task: ActionTaskType) -> UUID:
        del task
        return self.search_plan().first_choice


class _STARMethod:
    """STAR adaptation: frequency retrieval over all observed placements."""

    name = ActionBaselineMethod.STAR

    def __init__(self, case: VisibleActionCase) -> None:
        self.case = case
        self.counts: dict[UUID, float] = {location: 0.0 for location in case.locations}
        self.last_location: UUID | None = None

    def observe(self, obs: ActionDayObservation) -> None:
        if obs.after is None:
            return
        location = obs.after.detected_location_id
        if location is not None:
            self.last_location = location
            self.counts[location] += 1.0

    def search_plan(self) -> SearchPlan:
        candidate = self.last_location or _fallback_location(self.case.locations)
        return _single_candidate_plan(self.name, self.case.locations, candidate)

    def predict(self, task: ActionTaskType) -> UUID:
        if task == ActionTaskType.SEARCH:
            return self.search_plan().first_choice
        if sum(self.counts.values()) <= 0.0:
            return _fallback_location(self.case.locations)
        return max(
            self.counts,
            key=lambda location: (self.counts[location], str(location)),
        )


class _PchmpCcrrRgrcMethod:
    """New method: PCHMP joint event posterior -> CF-BOCPD cause -> CCRR regime
    -> owner-attribution write gate (a stand-in for full Hybrid RGRC)."""

    name = ActionBaselineMethod.PCHMP_CCRR_RGRC

    def __init__(self, case: VisibleActionCase) -> None:
        self.case = case
        self.orrer = OpenWorldRoleConditionedReversibleEventRevisionEngine()
        self.pchmp = ProvenanceConstrainedMessagePassing()
        self.bocpd = JointCauseFactorizedBOCPD()
        self.reactor = ContextConditionedRegimeReactivator()
        self.state = _OwnerHabitState(
            owner=case.owner_actor,
            guest=case.guest_actor,
            locations=case.locations,
        )
        self._frames: list[CauseSignalFrame] = []
        self._base = datetime(2026, 1, 1, 8, 0, tzinfo=UTC)
        # The default stage is seeded lazily on the first owner placement so
        # its context fingerprint is learned from observation, not assumed.
        self._stable_seeded = False

    def observe(self, obs: ActionDayObservation) -> None:
        if obs.after is None or obs.before is None:
            return
        owner = self.case.owner_actor
        guest = self.case.guest_actor
        location = obs.after.detected_location_id
        if location is None:
            return

        # 1. Branch a counterfactual hypothesis set and pass the *incremental*
        #    evidence through PCHMP (the evidence is not first consumed by an
        #    ORRER revise call, so it is not double-counted).
        actor_prior = {owner: 0.4, guest: 0.3, "unknown_actor": 0.3}
        try:
            history = self.orrer.branch(
                before=obs.before,
                after=obs.after,
                actor_prior=actor_prior,
                unresolved_probability=0.1,
            )
            evidence: list[
                ActorResponsibilityEvidence | EventMechanismEvidence | RoleBindingEvidence
            ] = []
            if obs.actor_evidence is not None:
                evidence.append(obs.actor_evidence)
            if obs.mechanism_evidence is not None:
                evidence.append(obs.mechanism_evidence)
            if obs.role_evidence is not None:
                evidence.append(obs.role_evidence)
            posterior = self.pchmp.infer(history, evidence)
        except ValueError:
            return

        # 2. Derive the owner- vs guest-attributed placement from the PCHMP
        #    joint posterior.
        owner_mass = 0.0
        guest_mass = 0.0
        for hypothesis in history.latest.hypotheses:
            mass = posterior.posterior_by_hypothesis_id.get(hypothesis.hypothesis_id, 0.0)
            if hypothesis.responsible_actor_key == owner:
                owner_mass += mass
            elif hypothesis.responsible_actor_key == guest:
                guest_mass += mass
        attributed_owner = owner_mass >= guest_mass

        # 3. Build the location-order-independent cause signal frame.  The
        #    habit channel is the position feature of an owner-attributed
        #    placement (a full-scale jump when the owner's habit location
        #    changes or returns); guest placements hold the habit channel and
        #    raise the actor channel instead.
        position_value = _position_value(location)
        if attributed_owner:
            habit_signal = position_value
            actor_signal = 0.1
        else:
            habit_signal = self._frames[-1].signals[ChangeCause.HABIT] if self._frames else 0.0
            actor_signal = 0.9
        frame = CauseSignalFrame(
            timestamp=self._base + timedelta(days=obs.day),
            signals={
                ChangeCause.OBSERVATION: 0.3,
                ChangeCause.ACTOR: actor_signal,
                ChangeCause.HABIT: habit_signal,
                ChangeCause.NOISE: 0.1,
            },
        )
        self._frames.append(frame)
        warmup = 2 if len(self._frames) > 2 else 0
        result = self.bocpd.run(self._frames, warmup_steps=warmup)
        snapshot = result.snapshots[-1]

        # 4. Seed the default stage from the first observed owner placement so
        #    its context fingerprint is learned, not assumed.
        if attributed_owner and not self._stable_seeded:
            self.reactor.add_regime(
                RegimeLibraryEntry(
                    regime_id="stable",
                    actor_id=owner,
                    object_instance_id=self.case.object_instance_id,
                    context_fingerprint=_position_fingerprint(location),
                    cause_origin=ChangeCause.HABIT,
                    created_at=frame.timestamp,
                ),
                make_active=True,
            )
            self._stable_seeded = True

        # 5. CCRR regime decision: score against an immutable view then apply
        #    under the reactor's compare-and-swap (score-then-apply is atomic).
        context_features = _position_fingerprint(location)
        view = self.reactor.view(object_instance_id=self.case.object_instance_id, actor_id=owner)
        decision = self.reactor.score_decision(
            owner_actor_id=owner,
            snapshot=snapshot,
            context_features=context_features,
            now=frame.timestamp,
            view=view,
        )
        self.reactor.apply_decision(decision)

        # 6. Owner-attribution write gate (a stand-in for full Hybrid RGRC):
        #    only owner-attributed placements under a non-unresolved regime
        #    decision write to the active owner stage.  STAY keeps the active
        #    stage; REACTIVATE/CREATE switch it first.
        if attributed_owner:
            self.state.last_location = location
            if decision.kind == RegimeDecisionKind.UNRESOLVED:
                # Unresolved: quarantine the placement (do not write).
                pass
            else:
                if decision.kind == RegimeDecisionKind.REACTIVATE:
                    assert decision.reactivated_regime_id is not None
                    self.state.active_regime_id = decision.reactivated_regime_id
                elif decision.kind == RegimeDecisionKind.CREATE:
                    assert decision.created_regime_id is not None
                    self.state.active_regime_id = decision.created_regime_id
                self.state.write_owner(location)
        else:
            self.state.guest_recent_location = location
            self.state.last_location = location

    def search_plan(self) -> SearchPlan:
        candidate = self.state.last_location or self.state.argmax_owner()
        return _single_candidate_plan(self.name, self.case.locations, candidate)

    def predict(self, task: ActionTaskType) -> UUID:
        if task == ActionTaskType.SEARCH:
            return self.search_plan().first_choice
        return self.state.argmax_owner()


class _ActionMethod(Protocol):
    """Uniform observe/predict/plan surface shared by every method implementation.

    ``search_plan`` is a *required* output contract: the evaluator has no way to
    guess a method's search strategy and is forbidden from inferring one from
    the class or from the ``locations`` tuple.
    """

    def observe(self, obs: ActionDayObservation) -> None: ...

    def predict(self, task: ActionTaskType) -> UUID: ...

    def search_plan(self) -> SearchPlan: ...


_METHOD_FACTORIES: dict[ActionBaselineMethod, Callable[[VisibleActionCase], _ActionMethod]] = {
    ActionBaselineMethod.AMG_2012: _AMGMethod,
    ActionBaselineMethod.O_STAR: _OStarMethod,
    ActionBaselineMethod.DYNAMEM: _DynaMemMethod,
    ActionBaselineMethod.STAR: _STARMethod,
    ActionBaselineMethod.PCHMP_CCRR_RGRC: _PchmpCcrrRgrcMethod,
}


#: Every arm the death test runs by default.
DEFAULT_METHODS: tuple[ActionBaselineMethod, ...] = (
    ActionBaselineMethod.AMG_2012,
    ActionBaselineMethod.O_STAR,
    ActionBaselineMethod.DYNAMEM,
    ActionBaselineMethod.STAR,
    ActionBaselineMethod.PCHMP_CCRR_RGRC,
)


def _location_tuple_digest(cases: tuple[ActionGeneratedCase, ...]) -> str:
    """Record how the input registry happened to be ordered.

    This is the one report field a location permutation is allowed to move.  It
    is registered in :data:`NON_SEMANTIC_REPORT_FIELDS` precisely so a
    permutation test can assert that *nothing else* moved.
    """

    return content_sha256(
        [[str(location) for location in case.visible.locations] for case in cases]
    )


# --- evaluation ---------------------------------------------------------------


class StructureTwoActionDeathTest:
    """Run the action-level matched death test over generated cases.

    Search is scored through exactly one object per method per day: the
    :class:`SearchPlan` that method registered.  Pass ``search_utility_contract``
    to price inspections and failed searches; without one the report stays
    fail-closed at ``SEARCH_UTILITY_CONTRACT_UNRESOLVED`` and emits no cost.
    """

    def __init__(
        self,
        generator: StructureTwoActionScenarioGenerator | None = None,
    ) -> None:
        self.generator = generator or StructureTwoActionScenarioGenerator()

    def run(
        self,
        seeds: tuple[int, ...],
        *,
        methods: tuple[ActionBaselineMethod, ...] = DEFAULT_METHODS,
        search_utility_contract: SearchUtilityContract | None = None,
    ) -> StructureTwoActionDeathTestReport:
        cases = tuple(self.generator.generate(seed) for seed in seeds)
        return self.run_cases(
            cases,
            methods=methods,
            search_utility_contract=search_utility_contract,
        )

    def run_cases(
        self,
        cases: tuple[ActionGeneratedCase, ...],
        *,
        methods: tuple[ActionBaselineMethod, ...] = DEFAULT_METHODS,
        search_utility_contract: SearchUtilityContract | None = None,
    ) -> StructureTwoActionDeathTestReport:
        """Score already-generated cases, so a caller can permute or relabel them."""

        if not cases:
            raise ValueError("at least one case is required")
        day_results: list[ActionDayResult] = []
        method_reports: list[ActionMethodReport] = []

        for method in methods:
            case_results: list[ActionDayResult] = []
            scores: list[SearchScore] = []
            per_case_error: Counter[UUID] = Counter()
            per_case_search_error: Counter[UUID] = Counter()
            guest_day_put_back_error_days = 0
            for case in cases:
                state = _METHOD_FACTORIES[method](case.visible)
                for obs in case.visible.days:
                    state.observe(obs)
                    truth = case.truth_by_day[obs.day]
                    put_back = state.predict(ActionTaskType.PUT_BACK)
                    # One plan, then everything about search is read off it.
                    plan = state.search_plan()
                    self._verify_plan(plan, method, case.visible)
                    score = score_search_plan(
                        plan, truth.true_location_after, search_utility_contract
                    )
                    scores.append(score)
                    put_back_correct = put_back == truth.true_owner_habit_location
                    if not put_back_correct:
                        per_case_error[case.visible.case_id] += 1
                    if not score.first_choice_correct:
                        per_case_search_error[case.visible.case_id] += 1
                    # Guest-day put-back error: a day the guest actually moved
                    # the object and this method's put-back missed the owner
                    # habit location.
                    if truth.true_actor == case.visible.guest_actor and not put_back_correct:
                        guest_day_put_back_error_days += 1
                    result = ActionDayResult(
                        case_id=case.visible.case_id,
                        method=method,
                        day=obs.day,
                        guest_move_day=(truth.true_actor == case.visible.guest_actor),
                        put_back_correct=put_back_correct,
                        search_plan=plan,
                        search_target=truth.true_location_after,
                        search_correct=score.first_choice_correct,
                        search_plan_kind=score.plan_kind,
                        search_plan_length=score.plan_length,
                        registered_location_count=score.registered_location_count,
                        inspected_container_count=score.inspected_container_count,
                        search_path_length=score.search_path_length,
                        search_target_found=score.target_found_in_plan,
                        search_utility_status=score.status,
                        search_utility_contract_id=score.contract_id,
                        search_cost=score.search_cost,
                        search_time_seconds=score.search_time_seconds,
                        search_unresolved_fields=score.unresolved_fields,
                    )
                    case_results.append(result)
                    day_results.append(result)
            total_days = len(case_results)
            total_put_back_errors = sum(per_case_error.values())
            total_search_errors = sum(per_case_search_error.values())
            aggregate = aggregate_search_scores(method.value, tuple(scores))
            method_reports.append(
                ActionMethodReport(
                    method=method,
                    case_count=len(cases),
                    put_back_error_rate=(total_put_back_errors / total_days if total_days else 0.0),
                    search_error_rate=aggregate.first_choice_error_rate,
                    search_target_not_found_rate=aggregate.target_not_found_rate,
                    mean_inspected_container_count=aggregate.mean_inspected_container_count,
                    mean_search_path_length=aggregate.mean_search_path_length,
                    mean_search_cost=aggregate.mean_search_cost,
                    mean_search_time_seconds=aggregate.mean_search_time_seconds,
                    search_utility_status=aggregate.status,
                    search_unresolved_fields=aggregate.unresolved_fields,
                    guest_day_put_back_error_days=guest_day_put_back_error_days,
                    total_put_back_errors=total_put_back_errors,
                    total_search_errors=total_search_errors,
                )
            )
        status = (
            SearchUtilityStatus.RESOLVED
            if method_reports
            and all(
                report.search_utility_status is SearchUtilityStatus.RESOLVED
                for report in method_reports
            )
            else SearchUtilityStatus.UNRESOLVED
        )
        diagnostic = self._legacy_diagnostic(method_reports)
        return StructureTwoActionDeathTestReport(
            protocol_version=PROTOCOL_VERSION,
            superseded_protocol_version=SUPERSEDED_PROTOCOL_VERSION,
            generator_version=self.generator.generator_version,
            location_tuple_inputs=tuple(
                ActionLocationTupleInput(
                    case_id=case.visible.case_id,
                    locations=case.visible.locations,
                )
                for case in cases
            ),
            location_tuple_digest=_location_tuple_digest(cases),
            search_utility_contract=search_utility_contract,
            search_utility_contract_id=(
                None if search_utility_contract is None else search_utility_contract.contract_id
            ),
            search_utility_status=status,
            method_reports=tuple(method_reports),
            case_results=tuple(day_results),
            legacy_diagnostic=diagnostic,
            scientific_status=diagnostic.scientific_status,
        )

    @staticmethod
    def _verify_plan(
        plan: SearchPlan, method: ActionBaselineMethod, visible: VisibleActionCase
    ) -> None:
        """Reject a plan that does not belong to the method or the case.

        A method cannot rename itself into another arm's identity, and cannot
        register containers this household never had.
        """

        if plan.method_id != method.value:
            raise ValueError(
                f"search plan claims method {plan.method_id!r} but was produced by {method.value!r}"
            )
        if set(plan.registered_locations) != set(visible.locations):
            raise ValueError("search plan registers a different location set than the case")

    @staticmethod
    def _legacy_diagnostic(reports: list[ActionMethodReport]) -> LegacyPutBackOnlyDiagnostic:
        """Compare put-back error only, and say so in the type.

        This is deliberately *not* a scientific verdict.  The frozen route makes
        cumulative action regret primary, and neither its component weights nor
        the price of a search action are registered, so nothing here is allowed
        to read as a win.
        """

        note = (
            "put-back error is one unweighted term of the frozen route's cumulative action "
            "regret; search cost is unpriced and search was not scored into this comparison, "
            "so this diagnostic cannot support a scientific or paper-level claim"
        )
        new = next(
            (report for report in reports if report.method == ActionBaselineMethod.PCHMP_CCRR_RGRC),
            None,
        )
        baselines = [
            report for report in reports if report.method != ActionBaselineMethod.PCHMP_CCRR_RGRC
        ]
        if new is None:
            comparison = "new method not run"
        elif not baselines:
            comparison = "no baselines run"
        else:
            best_baseline_put_back = min(report.put_back_error_rate for report in baselines)
            if new.put_back_error_rate < best_baseline_put_back - 1e-9:
                comparison = "new method lower put-back error than every baseline"
            elif isclose(
                new.put_back_error_rate, best_baseline_put_back, rel_tol=0.0, abs_tol=1e-9
            ):
                comparison = "new method ties the best baseline on put-back error"
            else:
                comparison = "new method higher put-back error than the best baseline"
        return LegacyPutBackOnlyDiagnostic(
            superseded_protocol_version=SUPERSEDED_PROTOCOL_VERSION,
            put_back_comparison=comparison,
            primary_utility_metric=ROUTE_A_PRIMARY_UTILITY_METRIC,
            unresolved_contract_fields=ROUTE_A_UNRESOLVED_UTILITY_FIELDS,
            note=note,
        )


def withdrawn_v0_1_search_cost(state: object, target: UUID, locations: tuple[UUID, ...]) -> int:
    """The withdrawn ``@0.1`` cost model, kept only so a test can pin the defect.

    It is never called by the evaluator.  Two things are wrong with it and both
    are load-bearing for the regression test:

    #. it guesses a method's search strategy with ``isinstance`` and falls back
       to ``list(locations)`` -- the raw tuple order -- for anything it does not
       recognise, so AMG's and DynaMem's cost moves when the tuple is permuted
       while their prediction does not;
    #. the ranking it scores is not the ranking any method emitted, so a wrong
       single-location search was charged a flat ``1`` and a failed search was
       never charged a failure penalty at all.
    """

    belief_order = list(locations)
    if isinstance(state, _PchmpCcrrRgrcMethod):
        posterior = state.state.owner_posterior()
        belief_order = sorted(
            locations,
            key=lambda location: (-posterior.get(location, 0.0), str(location)),
        )
    elif isinstance(state, (_OStarMethod, _STARMethod)):
        belief_order = sorted(
            locations,
            key=lambda location: (-state.counts.get(location, 0.0), str(location)),
        )
    for index, location in enumerate(belief_order, start=1):
        if location == target:
            return index
    return len(locations)
