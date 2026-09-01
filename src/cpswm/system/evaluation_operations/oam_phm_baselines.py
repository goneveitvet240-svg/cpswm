"""WP0 baseline harness for the OAM-PHM substructure.

`OAM-PHM §9.1` lists the baselines every OAM-PHM claim must clear before it can
be called a contribution, and `§9.4` fixes the fairness rules.  Without a
runnable floor, `§12.1` completion condition 8 (*"relative to independently
tuned O-STaR and strong combined baselines, produce action- or utility-level
gains"*) cannot be evaluated, and neither can `§12.2` stop condition 1
(*"strong combined baselines match the candidate method after independent
tuning"*).

Two properties are enforced structurally rather than by convention:

* **No truth access.**  A baseline is handed a :class:`SymbolicSimulationResult`
  — the robot-visible stream — and nothing else.  Ground truth lives behind the
  capability gate in the privileged view and is only ever read by the scorer.
* **Identical inputs.**  :func:`compare_baselines` feeds every entry the same
  run and the same query set, so a difference in score cannot come from a
  difference in information (`§9.4` rule 1 and rule 6).

Baselines that depend on capabilities still suspended by the F0 review gate are
registered with an explicit status instead of being silently omitted, so the
registry always shows what is missing rather than only what exists.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import datetime, timedelta
from enum import StrEnum
from itertools import pairwise
from math import log
from time import perf_counter
from typing import Protocol, runtime_checkable
from uuid import UUID

import numpy as np
from pydantic import Field, model_validator

from cpswm.contracts import ObservationOutcome
from cpswm.contracts.base import ContractModel, Probability
from cpswm.system.continual.rls import RecursiveLeastSquares, RLSConfig
from cpswm.system.reproducibility import content_sha256
from cpswm.system.world_model_simulator import SymbolicSimulationResult

#: Mass reserved for unseen locations so held-out truth never yields -inf NLL.
DEFAULT_SMOOTHING = 1e-3


class BaselineStatus(StrEnum):
    """Why a `§9.1` baseline is or is not runnable today."""

    IMPLEMENTED = "implemented"
    #: Blocked by the F0 review gate (multi-person / guest / handover / change).
    GATED_BY_REVIEW = "gated_by_review"
    #: Requires a faithful reimplementation of an external published system.
    EXTERNAL_REIMPLEMENTATION_REQUIRED = "external_reimplementation_required"


class LocationQuery(ContractModel):
    """Ask where one object instance is at one point in time."""

    object_instance_id: UUID
    query_time: datetime


class LocationBeliefPrediction(ContractModel):
    """A normalised belief over candidate locations for one query."""

    query: LocationQuery
    location_posterior: dict[UUID, Probability] = Field(min_length=1)
    baseline_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_posterior(self) -> LocationBeliefPrediction:
        total = sum(self.location_posterior.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError("location_posterior must sum to one")
        return self

    def probability_of(self, location_id: UUID) -> float:
        return self.location_posterior.get(location_id, 0.0)

    @property
    def top1_location_id(self) -> UUID:
        # Ties break on UUID so the same input always yields the same ranking.
        return max(
            sorted(self.location_posterior),
            key=lambda location_id: self.location_posterior[location_id],
        )


class LocationBeliefBaseline(Protocol):
    """The complete interface a baseline may use: the visible stream only."""

    baseline_version: str

    def predict(
        self, run: SymbolicSimulationResult, query: LocationQuery
    ) -> LocationBeliefPrediction: ...


class IdentityKind(StrEnum):
    """Entity namespaces that must be mapped at the evaluator boundary."""

    OBJECT = "object"
    LOCATION = "location"


class IdentityMappingEntry(ContractModel):
    """One evaluator-owned mapping from privileged identity to visible track."""

    identity_kind: IdentityKind
    gt_entity_id: UUID
    perceived_track_id: UUID


class F0ExactBijectionIdentityMapping(ContractModel):
    """F0-only exact bijection used by scoring, never by a baseline.

    This contract deliberately does not claim to model B1/D2 tracker
    fragmentation, merges, unknowns, or time-varying association.
    """

    mapping_version: str = Field(min_length=1)
    entries: tuple[IdentityMappingEntry, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_bijection(self) -> F0ExactBijectionIdentityMapping:
        gt_keys = [(entry.identity_kind, entry.gt_entity_id) for entry in self.entries]
        track_keys = [(entry.identity_kind, entry.perceived_track_id) for entry in self.entries]
        if len(gt_keys) != len(set(gt_keys)):
            raise ValueError("identity mapping contains duplicate ground-truth identities")
        if len(track_keys) != len(set(track_keys)):
            raise ValueError("identity mapping must be bijective within each identity kind")
        return self

    def track_id(self, identity_kind: IdentityKind, gt_entity_id: UUID) -> UUID:
        for entry in self.entries:
            if entry.identity_kind == identity_kind and entry.gt_entity_id == gt_entity_id:
                return entry.perceived_track_id
        raise KeyError(
            f"no {identity_kind.value} track mapping for ground-truth entity {gt_entity_id}"
        )

    @property
    def content_sha256(self) -> str:
        return content_sha256(self)


# Compatibility alias: callers should migrate to the explicit F0 name.
IdentityMappingContract = F0ExactBijectionIdentityMapping


class IdentityAssociationStatus(StrEnum):
    MATCHED = "matched"
    FRAGMENT = "fragment"
    MERGE = "merge"
    UNMATCHED_GT = "unmatched_gt"
    UNKNOWN_TRACK = "unknown_track"


class TemporalIdentityAssociation(ContractModel):
    """One evaluator-side B1/D2 association hypothesis over a validity interval."""

    identity_kind: IdentityKind
    gt_entity_id: UUID | None = None
    perceived_track_id: UUID | None = None
    valid_from: datetime
    valid_until: datetime | None = None
    association_probability: Probability
    status: IdentityAssociationStatus

    @model_validator(mode="after")
    def validate_association(self) -> TemporalIdentityAssociation:
        if self.valid_until is not None and self.valid_until <= self.valid_from:
            raise ValueError("identity association validity interval must be positive")
        if self.status == IdentityAssociationStatus.UNKNOWN_TRACK:
            if self.perceived_track_id is None or self.gt_entity_id is not None:
                raise ValueError("unknown track requires only a perceived track id")
        elif self.status == IdentityAssociationStatus.UNMATCHED_GT:
            if self.gt_entity_id is None or self.perceived_track_id is not None:
                raise ValueError("unmatched ground truth requires only a GT entity id")
        elif self.gt_entity_id is None or self.perceived_track_id is None:
            raise ValueError("matched/fragment/merge association requires both identities")
        return self


class TemporalIdentityAssociationContract(ContractModel):
    """B1/D2-capable many-to-many, time-varying identity association contract."""

    mapping_version: str = Field(min_length=1)
    associations: tuple[TemporalIdentityAssociation, ...] = Field(min_length=1)

    @property
    def content_sha256(self) -> str:
        return content_sha256(self)


class HeadConstructionMode(StrEnum):
    NATIVE_DUAL_HEAD = "native_dual_head"
    DERIVED_EMPIRICAL_REFERENCE_HEAD = "derived_empirical_reference_head"
    EXPLICIT_COMPOSITE_BASELINE = "explicit_composite_baseline"


class PredictionComputeReceipt(ContractModel):
    """Per-query accounting supplied by the adapter boundary."""

    adapter_invocations: int = Field(default=1, gt=0)
    component_model_invocations: int | None = Field(default=None, ge=0)
    processed_observations: int | None = Field(default=None, ge=0)


class LocationDistributionPrediction(ContractModel):
    """Separate fast current-state and slow habitual location distributions."""

    query: LocationQuery
    current_belief: dict[UUID, Probability] = Field(min_length=1)
    habitual_distribution: dict[UUID, Probability] = Field(min_length=1)
    baseline_version: str = Field(min_length=1)
    head_construction: HeadConstructionMode
    habitual_head_version: str = Field(min_length=1)
    compute_receipt: PredictionComputeReceipt

    @model_validator(mode="after")
    def validate_distributions(self) -> LocationDistributionPrediction:
        for name, distribution in (
            ("current_belief", self.current_belief),
            ("habitual_distribution", self.habitual_distribution),
        ):
            if abs(sum(distribution.values()) - 1.0) > 1e-6:
                raise ValueError(f"{name} must sum to one")
        if set(self.current_belief) != set(self.habitual_distribution):
            raise ValueError("current and habitual distributions must use identical support")
        return self


@runtime_checkable
class LocationDistributionBaseline(Protocol):
    """Native two-head baseline implemented by OAM-PHM or an external adapter."""

    baseline_version: str

    def predict_distributions(
        self, run: SymbolicSimulationResult, query: LocationQuery
    ) -> LocationDistributionPrediction: ...


class BaselineParameterCandidate(ContractModel):
    """One immutable hyperparameter candidate owned by one adapter."""

    candidate_id: str = Field(min_length=1)
    parameters: dict[str, float]


class BaselineAdapter(Protocol):
    """Adapter boundary for internal, O-STaR, STREAK, and future baselines."""

    adapter_id: str
    adapter_version: str

    def candidates(self) -> tuple[BaselineParameterCandidate, ...]: ...

    def build(
        self, candidate: BaselineParameterCandidate
    ) -> LocationBeliefBaseline | LocationDistributionBaseline: ...


class GridBaselineAdapter:
    """Small concrete adapter for deterministic numeric parameter grids."""

    def __init__(
        self,
        *,
        adapter_id: str,
        adapter_version: str,
        factory: Callable[..., LocationBeliefBaseline | LocationDistributionBaseline],
        parameter_candidates: tuple[BaselineParameterCandidate, ...],
    ) -> None:
        if not adapter_id or not adapter_version:
            raise ValueError("baseline adapter id and version must be non-empty")
        if not parameter_candidates:
            raise ValueError("a baseline adapter requires at least one parameter candidate")
        candidate_ids = [candidate.candidate_id for candidate in parameter_candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("baseline parameter candidate ids must be unique")
        self.adapter_id = adapter_id
        self.adapter_version = adapter_version
        self._factory = factory
        self._candidates = parameter_candidates

    def candidates(self) -> tuple[BaselineParameterCandidate, ...]:
        return self._candidates

    def build(
        self, candidate: BaselineParameterCandidate
    ) -> LocationBeliefBaseline | LocationDistributionBaseline:
        if candidate not in self._candidates:
            raise ValueError("adapter may only build one of its declared candidates")
        return self._factory(**candidate.parameters)


class TuningObjective(StrEnum):
    CURRENT_NLL = "current_nll"
    HABITUAL_CROSS_ENTROPY = "habitual_cross_entropy"
    JOINT_NLL = "joint_nll"


class IndependentTuningProtocol(ContractModel):
    """Content-bound adapter-specific tuning protocol."""

    protocol_id: str = Field(min_length=1)
    adapter_id: str = Field(min_length=1)
    tuning_split_id: str = Field(min_length=1)
    evaluation_split_id: str = Field(min_length=1)
    tuning_dataset_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluation_dataset_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    tuning_truth_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluation_truth_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    tuning_group_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluation_group_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    tuning_identity_mapping_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluation_identity_mapping_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    frozen_candidate_grid_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    objective: TuningObjective
    max_trials: int = Field(gt=0)
    random_seed: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_split_separation(self) -> IndependentTuningProtocol:
        if self.tuning_split_id == self.evaluation_split_id:
            raise ValueError("tuning and evaluation split ids must be different")
        if self.tuning_dataset_content_sha256 == self.evaluation_dataset_content_sha256:
            raise ValueError("tuning and evaluation dataset content hashes must be different")
        if self.tuning_truth_manifest_sha256 == self.evaluation_truth_manifest_sha256:
            raise ValueError("tuning and evaluation truth manifests must be different")
        return self


class ComputeBudgetUnit(StrEnum):
    ADAPTER_INVOCATION = "adapter_invocation"
    COMPONENT_MODEL_INVOCATION = "component_model_invocation"
    PROCESSED_OBSERVATION = "processed_observation"


class BaselinePerformanceBudget(ContractModel):
    """Declared compute unit plus a post-hoc wall-time compliance threshold."""

    max_queries: int = Field(gt=0)
    compute_unit: ComputeBudgetUnit
    max_compute_units: int = Field(gt=0)
    wall_time_compliance_seconds: float | None = Field(default=None, gt=0.0)
    hardware_profile: str = Field(min_length=1)


class BaselineResourceUsage(ContractModel):
    query_count: int = Field(ge=0)
    adapter_invocations: int = Field(ge=0)
    component_model_invocations: int | None = Field(default=None, ge=0)
    processed_observations: int | None = Field(default=None, ge=0)
    wall_seconds: float = Field(ge=0.0)
    hardware_profile: str = Field(min_length=1)
    wall_time_check_kind: str = "posthoc_compliance_check_not_hard_timeout"


class DualDistributionScore(ContractModel):
    """Current-state and long-term-habit scores reported without pooling them."""

    baseline_version: str = Field(min_length=1)
    current_top1_accuracy: float | None = Field(ge=0.0, le=1.0)
    current_mean_negative_log_likelihood: float | None = Field(default=None, ge=0.0)
    habitual_mean_cross_entropy: float | None = Field(default=None, ge=0.0)
    habitual_mean_total_variation: float | None = Field(default=None, ge=0.0, le=1.0)
    time_grid_query_count: int = Field(ge=0)
    episode_cluster_count: int = Field(ge=0)
    household_cluster_count: int = Field(ge=0)
    object_cluster_count: int = Field(ge=0)
    event_cluster_count: int = Field(ge=0)
    habitual_truth_target: str = Field(min_length=1)
    head_construction: HeadConstructionMode
    habitual_head_version: str = Field(min_length=1)
    resource_usage: BaselineResourceUsage

    @property
    def sample_count(self) -> int:
        """Compatibility view; not a claim of statistical independence."""

        return self.time_grid_query_count


class TuningTrial(ContractModel):
    candidate: BaselineParameterCandidate
    objective_value: float
    score: DualDistributionScore


class BaselineTuningSelection(ContractModel):
    protocol: IndependentTuningProtocol
    adapter_version: str = Field(min_length=1)
    selected_candidate: BaselineParameterCandidate
    trials: tuple[TuningTrial, ...] = Field(min_length=1)


class CertifiedBaselineTuningSelection(ContractModel):
    """Authority-certified result of tuning on the bound development content."""

    selection: BaselineTuningSelection
    authority_hmac_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class LocationTruthChange(ContractModel):
    """Evaluator-side location change projected from privileged truth."""

    event_time: datetime
    event_group_id: UUID
    object_gt_entity_id: UUID
    location_gt_entity_id: UUID


class QueryGridSpec(ContractModel):
    """Dense temporal query grid, replacing one query per placement."""

    cadence: timedelta
    lead_time: timedelta = timedelta(hours=1)
    max_queries: int = Field(default=10_000, gt=3)

    @model_validator(mode="after")
    def validate_intervals(self) -> QueryGridSpec:
        if self.cadence <= timedelta(0):
            raise ValueError("query cadence must be positive")
        if self.lead_time < timedelta(0):
            raise ValueError("query lead time must be non-negative")
        return self


class HabitualTruthTarget(StrEnum):
    CUMULATIVE_EMPIRICAL_PLACEMENT_DISTRIBUTION = "cumulative_empirical_placement_distribution"
    LATENT_ROUTINE_HABIT = "latent_routine_habit"
    REGIME_CONDITIONED_HABIT = "regime_conditioned_habit"
    EXCEPTION_EXCLUDED_SENSITIVITY = "exception_excluded_sensitivity"


class QueryGroupBinding(ContractModel):
    episode_group_id: UUID
    household_group_id: UUID
    object_group_id: UUID
    event_group_id: UUID


class ExpandedLocationQuerySet(ContractModel):
    split_id: str = Field(min_length=1)
    source_dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    truth_source_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    habitual_truth_target: HabitualTruthTarget
    queries: tuple[LocationQuery, ...] = Field(min_length=4)
    current_truth_gt_ids: tuple[UUID, ...] = Field(min_length=4)
    habitual_truth_gt_distributions: tuple[dict[UUID, Probability], ...] = Field(min_length=4)
    group_bindings: tuple[QueryGroupBinding, ...] = Field(min_length=4)

    @model_validator(mode="after")
    def validate_alignment(self) -> ExpandedLocationQuerySet:
        size = len(self.queries)
        if not (
            len(self.current_truth_gt_ids) == size
            and len(self.habitual_truth_gt_distributions) == size
            and len(self.group_bindings) == size
        ):
            raise ValueError("expanded queries require aligned current and habitual truth")
        for query, group in zip(self.queries, self.group_bindings, strict=True):
            if query.object_instance_id != group.object_group_id:
                raise ValueError("query object track must match its object group id")
        for distribution in self.habitual_truth_gt_distributions:
            if abs(sum(distribution.values()) - 1.0) > 1e-6:
                raise ValueError("habitual truth distributions must sum to one")
        return self

    @property
    def dataset_content_sha256(self) -> str:
        return content_sha256(
            {
                "source_dataset_sha256": self.source_dataset_sha256,
                "queries": self.queries,
                "group_bindings": self.group_bindings,
            }
        )

    @property
    def truth_manifest_sha256(self) -> str:
        return content_sha256(
            {
                "truth_source_manifest_sha256": self.truth_source_manifest_sha256,
                "habitual_truth_target": self.habitual_truth_target,
                "current_truth_gt_ids": self.current_truth_gt_ids,
                "habitual_truth_gt_distributions": self.habitual_truth_gt_distributions,
            }
        )

    @property
    def group_manifest_sha256(self) -> str:
        return content_sha256(self.group_bindings)

    @property
    def sample_fingerprints(self) -> tuple[str, ...]:
        return tuple(
            content_sha256(
                {
                    "query": query,
                    "current_truth": current,
                    "habitual_truth": habitual,
                }
            )
            for query, current, habitual in zip(
                self.queries,
                self.current_truth_gt_ids,
                self.habitual_truth_gt_distributions,
                strict=True,
            )
        )


class SplitDisjointnessAudit(ContractModel):
    tuning_dataset_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluation_dataset_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    overlapping_episode_group_ids: tuple[UUID, ...]
    overlapping_household_group_ids: tuple[UUID, ...]
    overlapping_object_group_ids: tuple[UUID, ...]
    overlapping_event_group_ids: tuple[UUID, ...]
    overlapping_sample_fingerprints: tuple[str, ...]
    passed: bool

    @model_validator(mode="after")
    def validate_passed(self) -> SplitDisjointnessAudit:
        overlaps = (
            self.overlapping_episode_group_ids
            or self.overlapping_household_group_ids
            or self.overlapping_object_group_ids
            or self.overlapping_event_group_ids
            or self.overlapping_sample_fingerprints
        )
        if self.passed == bool(overlaps):
            raise ValueError("disjointness audit passed flag disagrees with overlap evidence")
        return self


def candidate_grid_sha256(adapter: BaselineAdapter) -> str:
    """Freeze both adapter identity and the complete declared candidate grid."""

    return content_sha256(
        {
            "adapter_id": adapter.adapter_id,
            "adapter_version": adapter.adapter_version,
            "candidates": adapter.candidates(),
        }
    )


def audit_split_disjointness(
    tuning: ExpandedLocationQuerySet,
    evaluation: ExpandedLocationQuerySet,
) -> SplitDisjointnessAudit:
    def values(query_set: ExpandedLocationQuerySet, field: str) -> set[UUID]:
        return {getattr(binding, field) for binding in query_set.group_bindings}

    episode_overlap = values(tuning, "episode_group_id") & values(evaluation, "episode_group_id")
    household_overlap = values(tuning, "household_group_id") & values(
        evaluation, "household_group_id"
    )
    object_overlap = values(tuning, "object_group_id") & values(evaluation, "object_group_id")
    event_overlap = values(tuning, "event_group_id") & values(evaluation, "event_group_id")
    sample_overlap = set(tuning.sample_fingerprints) & set(evaluation.sample_fingerprints)
    passed = not any(
        (episode_overlap, household_overlap, object_overlap, event_overlap, sample_overlap)
    )
    return SplitDisjointnessAudit(
        tuning_dataset_content_sha256=tuning.dataset_content_sha256,
        evaluation_dataset_content_sha256=evaluation.dataset_content_sha256,
        overlapping_episode_group_ids=tuple(sorted(episode_overlap)),
        overlapping_household_group_ids=tuple(sorted(household_overlap)),
        overlapping_object_group_ids=tuple(sorted(object_overlap)),
        overlapping_event_group_ids=tuple(sorted(event_overlap)),
        overlapping_sample_fingerprints=tuple(sorted(sample_overlap)),
        passed=passed,
    )


_SEALED_EVALUATION_CONSTRUCTOR = object()


class SealedEvaluationQuerySet:
    """Opaque evaluation data released only by its issuing split authority."""

    __slots__ = ("_authority_hmac_sha256", "_protocol_id", "_query_set")

    def __init__(
        self,
        query_set: ExpandedLocationQuerySet,
        *,
        protocol_id: str,
        authority_hmac_sha256: str,
        _constructor_token: object,
    ) -> None:
        if _constructor_token is not _SEALED_EVALUATION_CONSTRUCTOR:
            raise PermissionError("sealed evaluation sets may only be issued by an authority")
        self._query_set = query_set
        self._protocol_id = protocol_id
        self._authority_hmac_sha256 = authority_hmac_sha256

    @property
    def protocol_id(self) -> str:
        return self._protocol_id

    @property
    def dataset_content_sha256(self) -> str:
        return self._query_set.dataset_content_sha256


class OAMSplitAuthority:
    """Independent issuer for content-bound OAM-PHM tuning/evaluation splits."""

    def __init__(self, secret: bytes | None = None) -> None:
        self._secret = secret or secrets.token_bytes(32)

    def _hmac(self, payload: object) -> str:
        return hmac.new(
            self._secret,
            content_sha256(payload).encode("ascii"),
            hashlib.sha256,
        ).hexdigest()

    def prepare_protocol(
        self,
        *,
        protocol_id: str,
        adapter: BaselineAdapter,
        tuning_queries: ExpandedLocationQuerySet,
        evaluation_queries: ExpandedLocationQuerySet,
        tuning_identity_mapping: F0ExactBijectionIdentityMapping,
        evaluation_identity_mapping: F0ExactBijectionIdentityMapping,
        objective: TuningObjective,
        max_trials: int,
        random_seed: int,
    ) -> tuple[IndependentTuningProtocol, SealedEvaluationQuerySet, SplitDisjointnessAudit]:
        audit = audit_split_disjointness(tuning_queries, evaluation_queries)
        if not audit.passed:
            raise ValueError("tuning/evaluation split disjointness audit failed")
        protocol = IndependentTuningProtocol(
            protocol_id=protocol_id,
            adapter_id=adapter.adapter_id,
            tuning_split_id=tuning_queries.split_id,
            evaluation_split_id=evaluation_queries.split_id,
            tuning_dataset_content_sha256=tuning_queries.dataset_content_sha256,
            evaluation_dataset_content_sha256=evaluation_queries.dataset_content_sha256,
            tuning_truth_manifest_sha256=tuning_queries.truth_manifest_sha256,
            evaluation_truth_manifest_sha256=evaluation_queries.truth_manifest_sha256,
            tuning_group_manifest_sha256=tuning_queries.group_manifest_sha256,
            evaluation_group_manifest_sha256=evaluation_queries.group_manifest_sha256,
            tuning_identity_mapping_sha256=tuning_identity_mapping.content_sha256,
            evaluation_identity_mapping_sha256=evaluation_identity_mapping.content_sha256,
            frozen_candidate_grid_sha256=candidate_grid_sha256(adapter),
            objective=objective,
            max_trials=max_trials,
            random_seed=random_seed,
        )
        signed_core = {
            "protocol": protocol,
            "evaluation_queries": evaluation_queries,
            "evaluation_identity_mapping_sha256": evaluation_identity_mapping.content_sha256,
        }
        sealed = SealedEvaluationQuerySet(
            evaluation_queries,
            protocol_id=protocol.protocol_id,
            authority_hmac_sha256=self._hmac(signed_core),
            _constructor_token=_SEALED_EVALUATION_CONSTRUCTOR,
        )
        return protocol, sealed, audit

    def unseal(
        self,
        sealed: SealedEvaluationQuerySet,
        *,
        certified_selection: CertifiedBaselineTuningSelection,
        adapter: BaselineAdapter,
        evaluation_identity_mapping: F0ExactBijectionIdentityMapping,
    ) -> ExpandedLocationQuerySet:
        selection = certified_selection.selection
        if not hmac.compare_digest(
            certified_selection.authority_hmac_sha256,
            self._hmac({"certified_tuning_selection": selection}),
        ):
            raise PermissionError("tuning selection failed authority certification")
        protocol = selection.protocol
        if sealed.protocol_id != protocol.protocol_id:
            raise PermissionError("sealed evaluation set belongs to a different protocol")
        if candidate_grid_sha256(adapter) != protocol.frozen_candidate_grid_sha256:
            raise PermissionError("candidate grid changed after protocol freeze")
        if (
            evaluation_identity_mapping.content_sha256
            != protocol.evaluation_identity_mapping_sha256
        ):
            raise PermissionError("evaluation identity mapping changed after protocol freeze")
        query_set = sealed._query_set
        # The audit was required to pass at issuance; the signed core binds the
        # full evaluation data plus the protocol's dataset/truth/group hashes.
        signed_core = {
            "protocol": protocol,
            "evaluation_queries": query_set,
            "evaluation_identity_mapping_sha256": evaluation_identity_mapping.content_sha256,
        }
        if not hmac.compare_digest(
            sealed._authority_hmac_sha256,
            self._hmac(signed_core),
        ):
            raise PermissionError("sealed evaluation content failed authority verification")
        if (
            query_set.dataset_content_sha256 != protocol.evaluation_dataset_content_sha256
            or query_set.truth_manifest_sha256 != protocol.evaluation_truth_manifest_sha256
            or query_set.group_manifest_sha256 != protocol.evaluation_group_manifest_sha256
        ):
            raise PermissionError("sealed evaluation hashes do not match the frozen protocol")
        return query_set

    def certify_tuning_selection(
        self,
        selection: BaselineTuningSelection,
        *,
        adapter: BaselineAdapter,
        tuning_queries: ExpandedLocationQuerySet,
        tuning_identity_mapping: F0ExactBijectionIdentityMapping,
    ) -> CertifiedBaselineTuningSelection:
        protocol = selection.protocol
        if protocol.adapter_id != adapter.adapter_id:
            raise PermissionError("selection protocol belongs to a different adapter")
        if selection.adapter_version != adapter.adapter_version:
            raise PermissionError("selection adapter version does not match certification request")
        declared_candidates = adapter.candidates()
        trial_candidates = tuple(trial.candidate for trial in selection.trials)
        if trial_candidates != declared_candidates:
            raise PermissionError("selection trials do not cover the frozen candidate grid")
        expected_selected = min(
            selection.trials,
            key=lambda trial: (trial.objective_value, trial.candidate.candidate_id),
        ).candidate
        if selection.selected_candidate != expected_selected:
            raise PermissionError("selected candidate is not the recorded objective minimum")
        if candidate_grid_sha256(adapter) != protocol.frozen_candidate_grid_sha256:
            raise PermissionError("selection candidate grid does not match frozen protocol")
        if (
            tuning_queries.dataset_content_sha256 != protocol.tuning_dataset_content_sha256
            or tuning_queries.truth_manifest_sha256 != protocol.tuning_truth_manifest_sha256
            or tuning_queries.group_manifest_sha256 != protocol.tuning_group_manifest_sha256
        ):
            raise PermissionError("selection tuning content does not match frozen protocol")
        if tuning_identity_mapping.content_sha256 != protocol.tuning_identity_mapping_sha256:
            raise PermissionError("selection identity mapping does not match frozen protocol")
        return CertifiedBaselineTuningSelection(
            selection=selection,
            authority_hmac_sha256=self._hmac({"certified_tuning_selection": selection}),
        )


class BaselineScore(ContractModel):
    """Scores for one baseline over one query set."""

    baseline_version: str = Field(min_length=1)
    top1_accuracy: float | None = Field(ge=0.0, le=1.0)
    mean_negative_log_likelihood: float | None = Field(default=None, ge=0.0)
    sample_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_zero_sample_semantics(self) -> BaselineScore:
        # Mirrors the F0 evaluator: no samples means undefined, not zero.
        if self.sample_count == 0 and (
            self.top1_accuracy is not None or self.mean_negative_log_likelihood is not None
        ):
            raise ValueError("a zero-sample score must leave both metrics undefined")
        if self.sample_count > 0 and self.top1_accuracy is None:
            raise ValueError("a scored baseline must report top-1 accuracy")
        return self


class BaselineRegistryEntry(ContractModel):
    """One `§9.1` row, with its runnable status recorded either way."""

    name: str = Field(min_length=1)
    status: BaselineStatus
    baseline_version: str | None = None
    note: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_version_presence(self) -> BaselineRegistryEntry:
        implemented = self.status == BaselineStatus.IMPLEMENTED
        if implemented and not self.baseline_version:
            raise ValueError("an implemented baseline must declare a version")
        if not implemented and self.baseline_version:
            raise ValueError("a non-implemented baseline must not declare a version")
        return self


def _detected_history(
    run: SymbolicSimulationResult, object_instance_id: UUID, before: datetime
) -> list[tuple[datetime, UUID]]:
    """Return ``(time, location)`` for detections strictly before ``before``.

    Only ``DETECTED`` outcomes carry identity and location, so a missed or
    ambiguous observation cannot contribute a location here by construction.
    """

    history = [
        (result.detection_time, result.detected_location_id)
        for result in run.detection_results
        if result.outcome == ObservationOutcome.DETECTED
        and result.detected_object_instance_id == object_instance_id
        and result.detection_time is not None
        and result.detected_location_id is not None
        and result.detection_time < before
    ]
    return sorted(history)


def _candidate_locations(run: SymbolicSimulationResult) -> tuple[UUID, ...]:
    """Every location the visible stream mentions, plus the known start."""

    seen = {
        result.detected_location_id
        for result in run.detection_results
        if result.detected_location_id is not None
    }
    seen.add(run.initial_target_location_id)
    return tuple(sorted(seen))


def _smoothed(
    weights: dict[UUID, float], candidates: tuple[UUID, ...], smoothing: float
) -> dict[UUID, Probability]:
    total_weight = sum(weights.values())
    uniform = smoothing / len(candidates)
    if total_weight <= 0.0:
        return dict.fromkeys(candidates, 1.0 / len(candidates))
    posterior = {
        location_id: uniform + (1.0 - smoothing) * weights.get(location_id, 0.0) / total_weight
        for location_id in candidates
    }
    normaliser = sum(posterior.values())
    return {location_id: value / normaliser for location_id, value in posterior.items()}


class LastSeenLocationBaseline:
    """`§9.1` *last observation / last seen*: trust the newest detection.

    This is the floor every memory claim must clear.  It has no notion of
    persistence, so it is exactly wrong in the way the substructure is about:
    an object seen once in an anomalous place stays there forever.
    """

    baseline_version = "oam-phm-last-seen@0.1"

    def __init__(self, smoothing: float = DEFAULT_SMOOTHING) -> None:
        self.smoothing = smoothing

    def predict(
        self, run: SymbolicSimulationResult, query: LocationQuery
    ) -> LocationBeliefPrediction:
        candidates = _candidate_locations(run)
        history = _detected_history(run, query.object_instance_id, query.query_time)
        weights: dict[UUID, float] = {}
        if history:
            weights[history[-1][1]] = 1.0
        else:
            weights[run.initial_target_location_id] = 1.0
        return LocationBeliefPrediction(
            query=query,
            location_posterior=_smoothed(weights, candidates, self.smoothing),
            baseline_version=self.baseline_version,
        )

    def predict_distributions(
        self, run: SymbolicSimulationResult, query: LocationQuery
    ) -> LocationDistributionPrediction:
        current = self.predict(run, query).location_posterior
        candidates = _candidate_locations(run)
        history = _detected_history(run, query.object_instance_id, query.query_time)
        counts = Counter(location_id for _, location_id in history)
        habitual = _smoothed(
            {key: float(value) for key, value in counts.items()}
            or {run.initial_target_location_id: 1.0},
            candidates,
            self.smoothing,
        )
        return LocationDistributionPrediction(
            query=query,
            current_belief=current,
            habitual_distribution=habitual,
            baseline_version=self.baseline_version,
            head_construction=HeadConstructionMode.NATIVE_DUAL_HEAD,
            habitual_head_version="last-seen-cumulative-frequency@0.1",
            compute_receipt=PredictionComputeReceipt(component_model_invocations=1),
        )


class HouseholdFrequencyPriorBaseline:
    """`§9.1` *household frequency prior*: one pooled distribution, no person.

    Deliberately household-level.  `§2.2` names person conditioning as one of
    the boundaries OAM-PHM must cross, so the pooled version is the comparison
    that makes crossing it measurable.
    """

    baseline_version = "oam-phm-household-frequency@0.1"

    def __init__(self, smoothing: float = DEFAULT_SMOOTHING) -> None:
        self.smoothing = smoothing

    def predict(
        self, run: SymbolicSimulationResult, query: LocationQuery
    ) -> LocationBeliefPrediction:
        candidates = _candidate_locations(run)
        history = _detected_history(run, query.object_instance_id, query.query_time)
        counts = Counter(location_id for _, location_id in history)
        weights = {location_id: float(count) for location_id, count in counts.items()}
        if not weights:
            weights = {run.initial_target_location_id: 1.0}
        return LocationBeliefPrediction(
            query=query,
            location_posterior=_smoothed(weights, candidates, self.smoothing),
            baseline_version=self.baseline_version,
        )

    def predict_distributions(
        self, run: SymbolicSimulationResult, query: LocationQuery
    ) -> LocationDistributionPrediction:
        distribution = self.predict(run, query).location_posterior
        return LocationDistributionPrediction(
            query=query,
            current_belief=distribution,
            habitual_distribution=distribution,
            baseline_version=self.baseline_version,
            head_construction=HeadConstructionMode.NATIVE_DUAL_HEAD,
            habitual_head_version="household-frequency-native@0.1",
            compute_receipt=PredictionComputeReceipt(component_model_invocations=1),
        )


class MarkovTransitionBaseline:
    """`§9.1` *Markov transition model*: propagate from the last detection.

    Transitions are counted between consecutive detections of the same object.
    With a single observed transition the estimate is degenerate; that is the
    point — it shows how little a first-order model extracts from sparse,
    selectively sampled observation streams.
    """

    baseline_version = "oam-phm-markov-transition@0.1"

    def __init__(self, smoothing: float = DEFAULT_SMOOTHING) -> None:
        self.smoothing = smoothing

    def predict(
        self, run: SymbolicSimulationResult, query: LocationQuery
    ) -> LocationBeliefPrediction:
        candidates = _candidate_locations(run)
        history = _detected_history(run, query.object_instance_id, query.query_time)
        if not history:
            weights = {run.initial_target_location_id: 1.0}
            return LocationBeliefPrediction(
                query=query,
                location_posterior=_smoothed(weights, candidates, self.smoothing),
                baseline_version=self.baseline_version,
            )
        transitions: dict[UUID, Counter[UUID]] = defaultdict(Counter)
        for (_, source), (_, destination) in pairwise(history):
            transitions[source][destination] += 1
        current = history[-1][1]
        outgoing = transitions.get(current)
        if outgoing:
            weights = {location_id: float(count) for location_id, count in outgoing.items()}
        else:
            # No observed transition out of here: staying put is the only
            # evidence-backed hypothesis, and smoothing carries the rest.
            weights = {current: 1.0}
        return LocationBeliefPrediction(
            query=query,
            location_posterior=_smoothed(weights, candidates, self.smoothing),
            baseline_version=self.baseline_version,
        )

    def predict_distributions(
        self, run: SymbolicSimulationResult, query: LocationQuery
    ) -> LocationDistributionPrediction:
        current = self.predict(run, query).location_posterior
        candidates = _candidate_locations(run)
        history = _detected_history(run, query.object_instance_id, query.query_time)
        destination_counts = Counter(destination for _, destination in history[1:])
        habitual = _smoothed(
            {key: float(value) for key, value in destination_counts.items()}
            or {run.initial_target_location_id: 1.0},
            candidates,
            self.smoothing,
        )
        return LocationDistributionPrediction(
            query=query,
            current_belief=current,
            habitual_distribution=habitual,
            baseline_version=self.baseline_version,
            head_construction=HeadConstructionMode.NATIVE_DUAL_HEAD,
            habitual_head_version="markov-destination-frequency@0.1",
            compute_receipt=PredictionComputeReceipt(component_model_invocations=1),
        )


class RLSDecayedFrequencyBaseline:
    """Prototype: decayed location-frequency baseline driven by RLS updates.

    This is an OAM-PHM-ready experiment baseline. It intentionally keeps the
    same visible-stream only contract as all other WP0 baselines and does not
    access privileged truth.
    """

    baseline_version = "oam-phm-rls-decayed-frequency@0.1"

    def __init__(
        self,
        *,
        smoothing: float = DEFAULT_SMOOTHING,
        forgetting_factor: float = 0.98,
        ridge: float = 1e-6,
        prior_scale: float = 1e4,
    ) -> None:
        self.smoothing = smoothing
        self.forgetting_factor = forgetting_factor
        self.ridge = ridge
        self.prior_scale = prior_scale

        if not (0.0 < self.forgetting_factor <= 1.0):
            raise ValueError("forgetting_factor must be in (0, 1]")

    def _one_hot(self, index: int, size: int) -> np.ndarray:
        vector = np.zeros(size, dtype=float)
        vector[index] = 1.0
        return vector

    def predict(
        self, run: SymbolicSimulationResult, query: LocationQuery
    ) -> LocationBeliefPrediction:
        candidates = _candidate_locations(run)
        history = _detected_history(run, query.object_instance_id, query.query_time)

        if not candidates:
            raise ValueError("no candidate locations available")

        if not history:
            weights = {run.initial_target_location_id: 1.0}
            return LocationBeliefPrediction(
                query=query,
                location_posterior=_smoothed(weights, candidates, self.smoothing),
                baseline_version=self.baseline_version,
            )

        size = len(candidates)
        index_by_location = {location_id: idx for idx, location_id in enumerate(candidates)}
        models = {
            location_id: RecursiveLeastSquares(
                RLSConfig(
                    feature_dim=size,
                    forgetting_factor=self.forgetting_factor,
                    ridge=self.ridge,
                    prior_scale=self.prior_scale,
                )
            )
            for location_id in candidates
        }

        for _, observed_location in history:
            if observed_location not in index_by_location:
                continue
            observed_idx = index_by_location[observed_location]
            for location_id in candidates:
                x = self._one_hot(index_by_location[location_id], size)
                y = 1.0 if index_by_location[location_id] == observed_idx else 0.0
                models[location_id].update(x, y, gate=1.0, forgetting_factor=self.forgetting_factor)

        weights = {}
        for location_id in candidates:
            x = self._one_hot(index_by_location[location_id], size)
            score = models[location_id].predict(x)
            weights[location_id] = float(1.0 / (1.0 + np.exp(-score)))

        return LocationBeliefPrediction(
            query=query,
            location_posterior=_smoothed(weights, candidates, self.smoothing),
            baseline_version=self.baseline_version,
        )


#: `§9.1` in full.  Entries that cannot run today say so, so that a reader can
#: never mistake "not compared" for "compared and beaten".
SECTION_9_1_REGISTRY: tuple[BaselineRegistryEntry, ...] = (
    BaselineRegistryEntry(
        name="last observation / last seen",
        status=BaselineStatus.IMPLEMENTED,
        baseline_version=LastSeenLocationBaseline.baseline_version,
        note="Visible-stream only; no persistence model.",
    ),
    BaselineRegistryEntry(
        name="household frequency prior",
        status=BaselineStatus.IMPLEMENTED,
        baseline_version=HouseholdFrequencyPriorBaseline.baseline_version,
        note="Pooled over the household; deliberately not person-conditioned.",
    ),
    BaselineRegistryEntry(
        name="Markov transition model",
        status=BaselineStatus.IMPLEMENTED,
        baseline_version=MarkovTransitionBaseline.baseline_version,
        note="First-order transitions counted between consecutive detections.",
    ),
    BaselineRegistryEntry(
        name="person-conditioned frequency prior",
        status=BaselineStatus.GATED_BY_REVIEW,
        note=(
            "Needs the multi-person track the F0 review gate still suspends; "
            "see f0-evaluation-foundation-blocker-closure.md."
        ),
    ),
    BaselineRegistryEntry(
        name="O-STaR faithful reproduction",
        status=BaselineStatus.EXTERNAL_REIMPLEMENTATION_REQUIRED,
        note="OAM-PHM §9.4 rule 2 requires independently tuned w_hit/w_miss/gamma.",
    ),
    BaselineRegistryEntry(
        name="O-STaR + independently retuned parameters",
        status=BaselineStatus.EXTERNAL_REIMPLEMENTATION_REQUIRED,
        note="Depends on the faithful reproduction above.",
    ),
    BaselineRegistryEntry(
        name="O-STaR + stronger but matched perception",
        status=BaselineStatus.EXTERNAL_REIMPLEMENTATION_REQUIRED,
        note="Requires the B1 real-perception track.",
    ),
    BaselineRegistryEntry(
        name="STREAK-style continual relocation model",
        status=BaselineStatus.EXTERNAL_REIMPLEMENTATION_REQUIRED,
        note="Continual relocation learning under household context drift.",
    ),
    BaselineRegistryEntry(
        name="full OAM-PHM",
        status=BaselineStatus.GATED_BY_REVIEW,
        note="Requires WP2-WP6; the review gate suspends WP3 and WP5.",
    ),
    BaselineRegistryEntry(
        name="oracle identity / actor / event / location upper bounds",
        status=BaselineStatus.GATED_BY_REVIEW,
        note="Per-dimension oracle tracks are still an open S3-1/F0 deliverable.",
    ),
)


def registry_status_counts() -> dict[BaselineStatus, int]:
    return dict(Counter(entry.status for entry in SECTION_9_1_REGISTRY))


def score_baseline(
    baseline: LocationBeliefBaseline,
    run: SymbolicSimulationResult,
    queries: tuple[LocationQuery, ...],
    truth_locations: tuple[UUID, ...],
) -> BaselineScore:
    """Score one baseline. ``truth_locations`` is evaluator-side only.

    The baseline never receives ``truth_locations``; it only ever sees ``run``.
    """

    if len(queries) != len(truth_locations):
        raise ValueError("each query requires exactly one truth location")
    if not queries:
        return BaselineScore(
            baseline_version=baseline.baseline_version,
            top1_accuracy=None,
            mean_negative_log_likelihood=None,
            sample_count=0,
        )
    hits = 0
    total_negative_log_likelihood = 0.0
    for query, truth_location_id in zip(queries, truth_locations, strict=True):
        prediction = baseline.predict(run, query)
        if prediction.baseline_version != baseline.baseline_version:
            raise ValueError("baseline returned a prediction under a different version")
        if prediction.top1_location_id == truth_location_id:
            hits += 1
        probability = prediction.probability_of(truth_location_id)
        if probability <= 0.0:
            raise ValueError(
                "baseline assigned zero probability to a truth location; "
                "smoothing must keep every candidate reachable"
            )
        total_negative_log_likelihood -= log(probability)
    return BaselineScore(
        baseline_version=baseline.baseline_version,
        top1_accuracy=hits / len(queries),
        mean_negative_log_likelihood=total_negative_log_likelihood / len(queries),
        sample_count=len(queries),
    )


def compare_baselines(
    baselines: tuple[LocationBeliefBaseline, ...],
    run: SymbolicSimulationResult,
    queries: tuple[LocationQuery, ...],
    truth_locations: tuple[UUID, ...],
) -> tuple[BaselineScore, ...]:
    """Score every baseline on identical inputs (`§9.4` rules 1 and 6)."""

    versions = [baseline.baseline_version for baseline in baselines]
    if len(versions) != len(set(versions)):
        raise ValueError("baseline versions must be unique within one comparison")
    return tuple(score_baseline(baseline, run, queries, truth_locations) for baseline in baselines)


def build_expanded_location_query_grid(
    *,
    truth_changes: tuple[LocationTruthChange, ...],
    object_gt_entity_id: UUID,
    identity_mapping: F0ExactBijectionIdentityMapping,
    split_id: str,
    source_dataset_sha256: str,
    truth_source_manifest_sha256: str,
    episode_group_id: UUID,
    household_group_id: UUID,
    end_time: datetime,
    spec: QueryGridSpec,
) -> ExpandedLocationQuerySet:
    """Build dense current-state and empirical-habit truth on a fixed time grid.

    Ground truth is projected into this function by the evaluator.  Returned
    queries contain only the visible object track id; privileged location ids
    remain in the two truth vectors and are converted only inside the scorer.
    """

    relevant = sorted(
        (change for change in truth_changes if change.object_gt_entity_id == object_gt_entity_id),
        key=lambda change: change.event_time,
    )
    if not relevant:
        raise ValueError("query grid requires at least one truth location change")
    if end_time <= relevant[0].event_time:
        raise ValueError("query grid end_time must follow the first truth change")

    object_track_id = identity_mapping.track_id(IdentityKind.OBJECT, object_gt_entity_id)
    queries: list[LocationQuery] = []
    current_truth: list[UUID] = []
    habitual_truth: list[dict[UUID, Probability]] = []
    group_bindings: list[QueryGroupBinding] = []
    query_time = relevant[0].event_time + spec.lead_time
    while query_time < end_time:
        history = [change for change in relevant if change.event_time <= query_time]
        if history:
            counts = Counter(change.location_gt_entity_id for change in history)
            total = sum(counts.values())
            queries.append(LocationQuery(object_instance_id=object_track_id, query_time=query_time))
            current_truth.append(history[-1].location_gt_entity_id)
            habitual_truth.append(
                {location_gt_id: count / total for location_gt_id, count in sorted(counts.items())}
            )
            group_bindings.append(
                QueryGroupBinding(
                    episode_group_id=episode_group_id,
                    household_group_id=household_group_id,
                    object_group_id=object_track_id,
                    event_group_id=history[-1].event_group_id,
                )
            )
        if len(queries) > spec.max_queries:
            raise ValueError(
                "expanded query grid exceeds max_queries; increase cadence or declare a larger cap"
            )
        query_time += spec.cadence

    if len(queries) < 4:
        raise ValueError("expanded query grid must contain more than the legacy three queries")
    return ExpandedLocationQuerySet(
        split_id=split_id,
        source_dataset_sha256=source_dataset_sha256,
        truth_source_manifest_sha256=truth_source_manifest_sha256,
        habitual_truth_target=HabitualTruthTarget.CUMULATIVE_EMPIRICAL_PLACEMENT_DISTRIBUTION,
        queries=tuple(queries),
        current_truth_gt_ids=tuple(current_truth),
        habitual_truth_gt_distributions=tuple(habitual_truth),
        group_bindings=tuple(group_bindings),
    )


def predict_current_and_habitual(
    baseline: LocationBeliefBaseline | LocationDistributionBaseline,
    run: SymbolicSimulationResult,
    query: LocationQuery,
) -> LocationDistributionPrediction:
    """Expose native dual heads or an explicitly labelled shared reference head.

    A legacy single-head model is *not* presented as having learned a habitual
    head.  Its second output is a fixed derived empirical reference whose
    smoothing is independent of the candidate baseline's tuned parameters.
    """

    if isinstance(baseline, LocationDistributionBaseline):
        prediction = baseline.predict_distributions(run, query)
        if prediction.baseline_version != baseline.baseline_version:
            raise ValueError("baseline returned a prediction under a different version")
        return prediction

    current = baseline.predict(run, query)
    habitual = HouseholdFrequencyPriorBaseline(smoothing=DEFAULT_SMOOTHING).predict(run, query)
    return LocationDistributionPrediction(
        query=query,
        current_belief=current.location_posterior,
        habitual_distribution=habitual.location_posterior,
        baseline_version=baseline.baseline_version,
        head_construction=HeadConstructionMode.DERIVED_EMPIRICAL_REFERENCE_HEAD,
        habitual_head_version="derived-household-frequency-reference@0.1",
        compute_receipt=PredictionComputeReceipt(
            adapter_invocations=1,
            component_model_invocations=2,
            processed_observations=None,
        ),
    )


def score_baseline_distributions(
    baseline: LocationBeliefBaseline | LocationDistributionBaseline,
    run: SymbolicSimulationResult,
    query_set: ExpandedLocationQuerySet,
    identity_mapping: F0ExactBijectionIdentityMapping,
    *,
    performance_budget: BaselinePerformanceBudget | None = None,
) -> DualDistributionScore:
    """Score current belief and habitual distribution as distinct targets."""

    query_count = len(query_set.queries)
    if performance_budget is not None and query_count > performance_budget.max_queries:
        raise ValueError("query count exceeds the declared baseline performance budget")

    current_hits = 0
    current_nll = 0.0
    habitual_cross_entropy = 0.0
    habitual_total_variation = 0.0
    adapter_invocations = 0
    component_model_invocations = 0
    processed_observations = 0
    component_count_known = True
    observation_count_known = True
    head_construction: HeadConstructionMode | None = None
    habitual_head_version: str | None = None
    started = perf_counter()
    for query, current_gt_id, habit_gt in zip(
        query_set.queries,
        query_set.current_truth_gt_ids,
        query_set.habitual_truth_gt_distributions,
        strict=True,
    ):
        prediction = predict_current_and_habitual(baseline, run, query)
        if prediction.baseline_version != baseline.baseline_version:
            raise ValueError("baseline returned a prediction under a different version")
        if head_construction is None:
            head_construction = prediction.head_construction
            habitual_head_version = prediction.habitual_head_version
        elif (
            prediction.head_construction != head_construction
            or prediction.habitual_head_version != habitual_head_version
        ):
            raise ValueError("baseline changed head construction within one evaluation")
        adapter_invocations += prediction.compute_receipt.adapter_invocations
        if prediction.compute_receipt.component_model_invocations is None:
            component_count_known = False
        else:
            component_model_invocations += prediction.compute_receipt.component_model_invocations
        if prediction.compute_receipt.processed_observations is None:
            observation_count_known = False
        else:
            processed_observations += prediction.compute_receipt.processed_observations
        current_track_id = identity_mapping.track_id(IdentityKind.LOCATION, current_gt_id)
        current_top1 = max(
            sorted(prediction.current_belief), key=prediction.current_belief.__getitem__
        )
        current_hits += int(current_top1 == current_track_id)
        current_probability = prediction.current_belief.get(current_track_id, 0.0)
        if current_probability <= 0.0:
            raise ValueError("current belief assigned zero probability to mapped truth")
        current_nll -= log(current_probability)

        mapped_habit = {
            identity_mapping.track_id(IdentityKind.LOCATION, gt_id): probability
            for gt_id, probability in habit_gt.items()
        }
        support = set(mapped_habit) | set(prediction.habitual_distribution)
        for track_id, truth_probability in mapped_habit.items():
            predicted_probability = prediction.habitual_distribution.get(track_id, 0.0)
            if truth_probability > 0.0 and predicted_probability <= 0.0:
                raise ValueError("habitual distribution assigned zero probability to mapped truth")
            habitual_cross_entropy -= truth_probability * log(predicted_probability)
        habitual_total_variation += 0.5 * sum(
            abs(
                mapped_habit.get(track_id, 0.0)
                - prediction.habitual_distribution.get(track_id, 0.0)
            )
            for track_id in support
        )

    elapsed = perf_counter() - started
    component_total = component_model_invocations if component_count_known else None
    observation_total = processed_observations if observation_count_known else None
    if performance_budget is not None:
        measured_by_unit = {
            ComputeBudgetUnit.ADAPTER_INVOCATION: adapter_invocations,
            ComputeBudgetUnit.COMPONENT_MODEL_INVOCATION: component_total,
            ComputeBudgetUnit.PROCESSED_OBSERVATION: observation_total,
        }
        measured = measured_by_unit[performance_budget.compute_unit]
        if measured is None:
            raise ValueError(
                f"baseline did not report {performance_budget.compute_unit.value} usage"
            )
        if measured > performance_budget.max_compute_units:
            raise ValueError("measured compute exceeds the declared baseline budget")
    if (
        performance_budget is not None
        and performance_budget.wall_time_compliance_seconds is not None
        and elapsed > performance_budget.wall_time_compliance_seconds
    ):
        raise RuntimeError("baseline failed the post-hoc wall-time compliance check")
    groups = query_set.group_bindings
    assert head_construction is not None and habitual_head_version is not None
    return DualDistributionScore(
        baseline_version=baseline.baseline_version,
        current_top1_accuracy=current_hits / query_count,
        current_mean_negative_log_likelihood=current_nll / query_count,
        habitual_mean_cross_entropy=habitual_cross_entropy / query_count,
        habitual_mean_total_variation=habitual_total_variation / query_count,
        time_grid_query_count=query_count,
        episode_cluster_count=len({group.episode_group_id for group in groups}),
        household_cluster_count=len({group.household_group_id for group in groups}),
        object_cluster_count=len({group.object_group_id for group in groups}),
        event_cluster_count=len({group.event_group_id for group in groups}),
        habitual_truth_target=query_set.habitual_truth_target.value,
        head_construction=head_construction,
        habitual_head_version=habitual_head_version,
        resource_usage=BaselineResourceUsage(
            query_count=query_count,
            adapter_invocations=adapter_invocations,
            component_model_invocations=component_total,
            processed_observations=observation_total,
            wall_seconds=elapsed,
            hardware_profile=(
                performance_budget.hardware_profile
                if performance_budget is not None
                else "unspecified-no-matched-compute-claim"
            ),
        ),
    )


def tune_baseline_adapter(
    *,
    adapter: BaselineAdapter,
    protocol: IndependentTuningProtocol,
    run: SymbolicSimulationResult,
    tuning_queries: ExpandedLocationQuerySet,
    identity_mapping: F0ExactBijectionIdentityMapping,
    performance_budget: BaselinePerformanceBudget | None = None,
) -> BaselineTuningSelection:
    """Tune exactly one adapter without consulting its sealed evaluation split."""

    if protocol.adapter_id != adapter.adapter_id:
        raise ValueError("tuning protocol adapter_id does not match the baseline adapter")
    if tuning_queries.split_id != protocol.tuning_split_id:
        raise ValueError("query set is not the tuning split declared by the protocol")
    if (
        tuning_queries.dataset_content_sha256 != protocol.tuning_dataset_content_sha256
        or tuning_queries.truth_manifest_sha256 != protocol.tuning_truth_manifest_sha256
        or tuning_queries.group_manifest_sha256 != protocol.tuning_group_manifest_sha256
    ):
        raise ValueError("tuning query content does not match the frozen protocol")
    if identity_mapping.content_sha256 != protocol.tuning_identity_mapping_sha256:
        raise ValueError("tuning identity mapping does not match the frozen protocol")
    if candidate_grid_sha256(adapter) != protocol.frozen_candidate_grid_sha256:
        raise ValueError("adapter candidate grid does not match the frozen protocol")
    candidates = adapter.candidates()
    if len(candidates) > protocol.max_trials:
        raise ValueError("adapter candidate grid exceeds its independently declared trial budget")

    trials: list[TuningTrial] = []
    for candidate in candidates:
        baseline = adapter.build(candidate)
        if (
            not isinstance(baseline, LocationDistributionBaseline)
            and protocol.objective != TuningObjective.CURRENT_NLL
        ):
            raise ValueError(
                "derived empirical reference heads cannot tune habitual or joint objectives"
            )
        score = score_baseline_distributions(
            baseline,
            run,
            tuning_queries,
            identity_mapping,
            performance_budget=performance_budget,
        )
        if protocol.objective == TuningObjective.CURRENT_NLL:
            objective = score.current_mean_negative_log_likelihood
        elif protocol.objective == TuningObjective.HABITUAL_CROSS_ENTROPY:
            objective = score.habitual_mean_cross_entropy
        else:
            current = score.current_mean_negative_log_likelihood
            habitual = score.habitual_mean_cross_entropy
            objective = None if current is None or habitual is None else current + habitual
        if objective is None:
            raise ValueError("tuning objective is undefined on an empty query set")
        trials.append(TuningTrial(candidate=candidate, objective_value=objective, score=score))
    selected = min(trials, key=lambda trial: (trial.objective_value, trial.candidate.candidate_id))
    return BaselineTuningSelection(
        protocol=protocol,
        adapter_version=adapter.adapter_version,
        selected_candidate=selected.candidate,
        trials=tuple(trials),
    )


def evaluate_tuned_baseline(
    *,
    adapter: BaselineAdapter,
    certified_selection: CertifiedBaselineTuningSelection,
    run: SymbolicSimulationResult,
    sealed_evaluation: SealedEvaluationQuerySet,
    split_authority: OAMSplitAuthority,
    identity_mapping: F0ExactBijectionIdentityMapping,
    performance_budget: BaselinePerformanceBudget | None = None,
) -> DualDistributionScore:
    """Evaluate a frozen selection only on its predeclared sealed split."""

    selection = certified_selection.selection
    if selection.protocol.adapter_id != adapter.adapter_id:
        raise ValueError("tuning selection belongs to a different baseline adapter")
    if selection.adapter_version != adapter.adapter_version:
        raise ValueError("tuning selection belongs to a different adapter version")
    evaluation_queries = split_authority.unseal(
        sealed_evaluation,
        certified_selection=certified_selection,
        adapter=adapter,
        evaluation_identity_mapping=identity_mapping,
    )
    return score_baseline_distributions(
        adapter.build(selection.selected_candidate),
        run,
        evaluation_queries,
        identity_mapping,
        performance_budget=performance_budget,
    )


def default_baseline_adapters() -> tuple[BaselineAdapter, ...]:
    """Adapters and independent search spaces for the three runnable floor models."""

    grid = tuple(
        BaselineParameterCandidate(
            candidate_id=f"smoothing-{smoothing:g}", parameters={"smoothing": smoothing}
        )
        for smoothing in (1e-4, 1e-3, 1e-2)
    )
    return (
        GridBaselineAdapter(
            adapter_id="last-seen",
            adapter_version="last-seen-adapter@0.1",
            factory=LastSeenLocationBaseline,
            parameter_candidates=grid,
        ),
        GridBaselineAdapter(
            adapter_id="household-frequency",
            adapter_version="household-frequency-adapter@0.1",
            factory=HouseholdFrequencyPriorBaseline,
            parameter_candidates=grid,
        ),
        GridBaselineAdapter(
            adapter_id="markov-transition",
            adapter_version="markov-transition-adapter@0.1",
            factory=MarkovTransitionBaseline,
            parameter_candidates=grid,
        ),
    )


def default_baselines() -> tuple[LocationBeliefBaseline, ...]:
    """The `§9.1` entries that are runnable under the current review gate."""

    return (
        LastSeenLocationBaseline(),
        HouseholdFrequencyPriorBaseline(),
        MarkovTransitionBaseline(),
    )


def experimental_baselines() -> tuple[LocationBeliefBaseline, ...]:
    """Research-only baselines that are not part of the mandatory `§9.1` floor."""

    return (RLSDecayedFrequencyBaseline(),)
