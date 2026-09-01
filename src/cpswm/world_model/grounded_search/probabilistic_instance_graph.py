"""S3-DG-10D probabilistic dynamic instance association graph.

An observation is associated with an existing object, a genuinely new object,
or explicit unknown.  Association evidence is accumulated in log space and an
evidence cluster can be consumed only once.  The layered map changes only after
the association posterior passes both threshold and margin gates.
"""

from __future__ import annotations

from math import exp, isclose, log
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import Field, model_validator

from cpswm.contracts.base import ContractModel, EntityRef, EntityType, EvidenceRef, Probability
from cpswm.contracts.grounded_search import DynamicObjectState, ResolutionStatus
from cpswm.contracts.likelihoods import Pose3D

from .layered_map import LayeredSemanticMap

StrictlyPositiveProbability = Annotated[float, Field(gt=0.0, le=1.0)]


class InstanceAssociationPrior(ContractModel):
    existing_instance_probabilities: dict[UUID, Probability]
    new_instance_probability: Probability
    unknown_probability: Probability

    @model_validator(mode="after")
    def _normalized(self) -> InstanceAssociationPrior:
        total = (
            sum(self.existing_instance_probabilities.values())
            + self.new_instance_probability
            + self.unknown_probability
        )
        if not isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-6):
            raise ValueError("instance association prior must sum to one")
        return self


class UnassignedDynamicObservation(ContractModel):
    observation_id: UUID = Field(default_factory=uuid4)
    evidence_cluster_id: UUID
    anchor_id: UUID
    pose: Pose3D
    point_cloud_ref: str | None = None
    visual_feature_ref: str | None = None
    evidence_refs: tuple[EvidenceRef, ...] = Field(min_length=1)


class InstanceAssociationEvidence(ContractModel):
    """Candidate-conditioned likelihoods from visual, 3D, and re-ID models."""

    existing_instance_likelihoods: dict[UUID, StrictlyPositiveProbability]
    new_instance_likelihood: StrictlyPositiveProbability
    unknown_likelihood: StrictlyPositiveProbability
    quality: Probability = 1.0
    model_version: str = Field(min_length=1)
    calibration_domain: str = Field(min_length=1)


class ProbabilisticInstanceGraphUpdate(ContractModel):
    prior: InstanceAssociationPrior
    observation: UnassignedDynamicObservation
    evidence: InstanceAssociationEvidence
    proposed_new_instance: EntityRef | None = None
    resolution_threshold: Probability = 0.80
    ambiguity_margin: Probability = 0.15
    unknown_threshold: Probability = 0.45

    @model_validator(mode="after")
    def _update_semantics(self) -> ProbabilisticInstanceGraphUpdate:
        if set(self.prior.existing_instance_probabilities) != set(
            self.evidence.existing_instance_likelihoods
        ):
            raise ValueError("instance prior and likelihoods require identical existing support")
        if self.prior.new_instance_probability > 0.0:
            if self.proposed_new_instance is None:
                raise ValueError("positive new-instance mass requires a proposed instance identity")
            if self.proposed_new_instance.entity_type is not EntityType.OBJECT_INSTANCE:
                raise ValueError("a proposed dynamic instance must be an object instance")
        elif self.proposed_new_instance is not None:
            raise ValueError("a proposed new instance requires positive prior mass")
        return self


class InstanceAssociationResult(ContractModel):
    observation_id: UUID
    evidence_cluster_id: UUID
    existing_instance_probabilities: dict[UUID, Probability]
    new_instance_probability: Probability
    unknown_probability: Probability
    resolution_status: ResolutionStatus
    resolved_instance_id: UUID | None = None
    created_new_instance: bool = False
    association_revision: int = Field(gt=0)
    map_dynamic_revision: int = Field(ge=0)
    model_version: str = Field(min_length=1)
    calibration_domain: str = Field(min_length=1)
    explanation_codes: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _result_semantics(self) -> InstanceAssociationResult:
        total = (
            sum(self.existing_instance_probabilities.values())
            + self.new_instance_probability
            + self.unknown_probability
        )
        if not isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-6):
            raise ValueError("instance association posterior must sum to one")
        if self.resolution_status is ResolutionStatus.RESOLVED:
            if self.resolved_instance_id is None:
                raise ValueError("resolved association requires an object instance")
        elif self.resolved_instance_id is not None or self.created_new_instance:
            raise ValueError("unresolved association cannot mutate an object identity")
        if (
            self.created_new_instance
            and self.resolved_instance_id in self.existing_instance_probabilities
        ):
            raise ValueError("a created instance cannot already be in the prior support")
        return self


class ProbabilisticDynamicInstanceGraph:
    """Append-only association edges with gated dynamic-map projection."""

    def __init__(self, layered_map: LayeredSemanticMap | None = None) -> None:
        self._map = layered_map or LayeredSemanticMap()
        self._instances: dict[UUID, EntityRef] = {}
        self._consumed_clusters: set[UUID] = set()
        self._history: list[InstanceAssociationResult] = []

    @property
    def layered_map(self) -> LayeredSemanticMap:
        return self._map

    @property
    def history(self) -> tuple[InstanceAssociationResult, ...]:
        return tuple(self._history)

    def register_instance(self, state: DynamicObjectState) -> None:
        entity_id = state.object_instance.entity_id
        if entity_id in self._instances:
            raise ValueError("dynamic instance is already registered")
        self._map.upsert_dynamic_object(state)
        self._instances[entity_id] = state.object_instance

    def update(self, update: ProbabilisticInstanceGraphUpdate) -> InstanceAssociationResult:
        update = ProbabilisticInstanceGraphUpdate.model_validate(update.model_dump(mode="python"))
        cluster_id = update.observation.evidence_cluster_id
        if cluster_id in self._consumed_clusters:
            raise ValueError("one evidence cluster cannot create duplicate association evidence")
        if set(update.prior.existing_instance_probabilities) != set(self._instances):
            raise ValueError("instance association prior must cover the registered graph nodes")
        proposed = update.proposed_new_instance
        if proposed is not None and proposed.entity_id in self._instances:
            raise ValueError("proposed new instance already exists in the graph")

        anchor = self._map.static_anchor(update.observation.anchor_id)
        if update.observation.pose.frame_id != anchor.frame_id:
            raise ValueError("instance observation pose frame must match the static anchor")

        weighted_logs: dict[tuple[str, UUID | None], float] = {}
        for instance_id, prior in update.prior.existing_instance_probabilities.items():
            weighted_logs[("existing", instance_id)] = self._weighted_log_score(
                prior,
                update.evidence.existing_instance_likelihoods[instance_id],
                update.evidence.quality,
            )
        weighted_logs[("new", None)] = self._weighted_log_score(
            update.prior.new_instance_probability,
            update.evidence.new_instance_likelihood,
            update.evidence.quality,
        )
        weighted_logs[("unknown", None)] = self._weighted_log_score(
            update.prior.unknown_probability,
            update.evidence.unknown_likelihood,
            update.evidence.quality,
        )
        finite_scores = [value for value in weighted_logs.values() if value != float("-inf")]
        if not finite_scores:
            raise ValueError("instance association update has zero probability mass")
        maximum = max(finite_scores)
        unnormalized = {
            key: (0.0 if value == float("-inf") else exp(value - maximum))
            for key, value in weighted_logs.items()
        }
        normalizer = sum(unnormalized.values())
        posterior = {key: value / normalizer for key, value in unnormalized.items()}
        existing_posterior = {
            instance_id: posterior[("existing", instance_id)] for instance_id in self._instances
        }
        new_probability = posterior[("new", None)]
        unknown_probability = posterior[("unknown", None)]
        ranked = sorted(posterior.items(), key=lambda item: item[1], reverse=True)
        (best_kind, best_id), best_probability = ranked[0]
        second_probability = ranked[1][1] if len(ranked) > 1 else 0.0
        margin = best_probability - second_probability

        resolved_instance_id: UUID | None = None
        created_new = False
        if best_kind == "unknown" and (
            unknown_probability >= update.unknown_threshold
            or unknown_probability >= max(new_probability, *existing_posterior.values(), 0.0)
        ):
            status = ResolutionStatus.UNKNOWN
            explanation = ("association_unknown_mass_high",)
        elif best_probability < update.resolution_threshold or margin < update.ambiguity_margin:
            status = ResolutionStatus.AMBIGUOUS
            explanation = ("association_threshold_or_margin_not_met",)
        else:
            status = ResolutionStatus.RESOLVED
            if best_kind == "existing":
                assert best_id is not None
                resolved_instance_id = best_id
                entity = self._instances[best_id]
                explanation = ("existing_instance_association_resolved",)
            elif best_kind == "new":
                assert proposed is not None
                resolved_instance_id = proposed.entity_id
                entity = proposed
                created_new = True
                explanation = ("new_instance_association_resolved",)
            else:  # guarded by the unknown branch above
                raise RuntimeError("unknown association cannot be resolved as a hard instance")
            state = DynamicObjectState(
                object_instance=entity,
                anchor_id=update.observation.anchor_id,
                pose=update.observation.pose,
                point_cloud_ref=update.observation.point_cloud_ref,
                visual_feature_ref=update.observation.visual_feature_ref,
                state_probability=best_probability,
                evidence_refs=update.observation.evidence_refs,
            )
            self._map.upsert_dynamic_object(state)
            if created_new:
                self._instances[entity.entity_id] = entity

        result = InstanceAssociationResult(
            observation_id=update.observation.observation_id,
            evidence_cluster_id=cluster_id,
            existing_instance_probabilities=existing_posterior,
            new_instance_probability=new_probability,
            unknown_probability=unknown_probability,
            resolution_status=status,
            resolved_instance_id=resolved_instance_id,
            created_new_instance=created_new,
            association_revision=len(self._history) + 1,
            map_dynamic_revision=self._map.dynamic_revision,
            model_version=update.evidence.model_version,
            calibration_domain=update.evidence.calibration_domain,
            explanation_codes=explanation,
        )
        self._history.append(result)
        self._consumed_clusters.add(cluster_id)
        return result

    @staticmethod
    def _weighted_log_score(prior: float, likelihood: float, quality: float) -> float:
        if prior == 0.0:
            return float("-inf")
        return log(prior) + quality * log(likelihood)
