"""Deterministic CHEH branch, revise, retract, and rebuild operations."""

from __future__ import annotations

from datetime import datetime
from itertools import permutations
from math import isclose
from typing import Any, TypeVar
from uuid import UUID

from pydantic import BaseModel

from cpswm.contracts import (
    ActorResponsibilityEvidence,
    EventMechanism,
    EventMechanismEvidence,
    EventType,
    ObservationDetectionResult,
    ObservationOutcome,
    RoleBindingEvidence,
    ordered_role_key,
)
from cpswm.system.reproducibility import content_sha256, content_uuid

from .contracts import (
    ActorEvidenceEndpointRole,
    EventChainHypothesis,
    EventHypothesisHistory,
    EventHypothesisRevision,
    EventHypothesisStatus,
    EventHypothesisUpdateKind,
    HiddenEventEvidence,
    HiddenEventStep,
    actor_evidence_semantic_fingerprint,
    hidden_event_evidence_semantic_fingerprint,
)

StructuredEventEvidenceT = TypeVar(
    "StructuredEventEvidenceT", EventMechanismEvidence, RoleBindingEvidence
)


class CounterfactualEventHypergraphEngine:
    """Provenance-checked heuristic CHEH slice for a location transition."""

    engine_version = "cheh@0.3"
    schema_version = "0.1.0"

    def branch(
        self,
        *,
        before: ObservationDetectionResult,
        after: ObservationDetectionResult,
        actor_prior: dict[str, float],
        unresolved_probability: float = 0.1,
        handoff_fraction: float = 0.2,
        allow_unknown_handoff_roles: bool = False,
    ) -> EventHypothesisHistory:
        before = self._revalidate_detection(before, "before")
        after = self._revalidate_detection(after, "after")
        self._validate_endpoints(before, after)
        self._validate_distribution(actor_prior, "actor_prior")
        if len(actor_prior) < 2:
            raise ValueError("CHEH branch requires at least two actor hypotheses")
        if not 0.0 <= unresolved_probability < 1.0:
            raise ValueError("unresolved_probability must be in [0, 1)")
        if not 0.0 <= handoff_fraction < 1.0:
            raise ValueError("handoff_fraction must be in [0, 1)")

        assert before.detected_object_instance_id is not None
        assert before.detected_location_id is not None
        assert before.detection_time is not None
        assert after.detected_location_id is not None
        assert after.detection_time is not None

        source_ids = (before.metadata.record_id, after.metadata.record_id)
        hypothesis_set_id = content_uuid(
            "cheh-set",
            {
                "before_detection_result": before,
                "after_detection_result": after,
                "engine_version": self.engine_version,
                "allow_unknown_handoff_roles": allow_unknown_handoff_roles,
            },
        )

        raw_chains: list[tuple[str, tuple[HiddenEventStep, ...], float, str]] = []
        for actor_key, probability in sorted(actor_prior.items()):
            raw_chains.append(
                (
                    actor_key,
                    self._direct_steps(
                        hypothesis_set_id=hypothesis_set_id,
                        actor_key=actor_key,
                        object_instance_id=before.detected_object_instance_id,
                        source_location_id=before.detected_location_id,
                        destination_location_id=after.detected_location_id,
                        interval_start=before.detection_time,
                        interval_end=after.detection_time,
                    ),
                    (1.0 - handoff_fraction) * probability,
                    "direct_relocation",
                )
            )

        role_actors = sorted(
            actor_prior
            if allow_unknown_handoff_roles
            else (actor for actor in actor_prior if actor != "unknown_actor")
        )
        for actor_key, recipient_key in permutations(role_actors, 2):
            raw_chains.append(
                (
                    recipient_key,
                    self._handoff_steps(
                        hypothesis_set_id=hypothesis_set_id,
                        actor_key=actor_key,
                        recipient_key=recipient_key,
                        object_instance_id=before.detected_object_instance_id,
                        source_location_id=before.detected_location_id,
                        destination_location_id=after.detected_location_id,
                        interval_start=before.detection_time,
                        interval_end=after.detection_time,
                    ),
                    handoff_fraction * actor_prior[actor_key] * actor_prior[recipient_key],
                    "handoff_relocation",
                )
            )

        raw_total = sum(weight for _, _, weight, _ in raw_chains)
        resolved_mass = 1.0 - unresolved_probability
        hypotheses = tuple(
            self._make_hypothesis(
                hypothesis_set_id=hypothesis_set_id,
                responsible_actor_key=responsible_actor_key,
                steps=steps,
                posterior_probability=resolved_mass * raw_weight / raw_total,
                revival_probability=raw_weight / raw_total,
                source_record_ids=source_ids,
                explanation_code=explanation_code,
            )
            for responsible_actor_key, steps, raw_weight, explanation_code in raw_chains
            if raw_weight > 0.0
        )
        revision = self._make_revision(
            hypothesis_set_id=hypothesis_set_id,
            revision_no=0,
            parent_revision_id=None,
            update_kind=EventHypothesisUpdateKind.BRANCH,
            household_id=before.metadata.household_id,
            session_id=before.metadata.session_id,
            trace_id=before.metadata.trace_id,
            object_instance_id=before.detected_object_instance_id,
            interval_start=before.detection_time,
            interval_end=after.detection_time,
            source_location_id=before.detected_location_id,
            destination_location_id=after.detected_location_id,
            source_detection_result_ids=(
                before.metadata.record_id,
                after.metadata.record_id,
            ),
            hypotheses=hypotheses,
            unresolved_probability=unresolved_probability,
            revision_evidence_record_ids=source_ids,
            revision_evidence_cluster_ids=(),
            revision_evidence_semantic_fingerprints=(),
            revision_evidence_source_detection_result_ids=(),
            revision_evidence_endpoint_roles=(),
            revision_reason="initial counterfactual event branching",
        )
        return EventHypothesisHistory(
            hypothesis_set_id=hypothesis_set_id,
            revisions=(revision,),
        )

    def revise_actor_responsibility(
        self,
        history: EventHypothesisHistory,
        evidence: ActorResponsibilityEvidence,
        *,
        retraction_threshold: float = 0.01,
    ) -> EventHypothesisHistory:
        history = self._revalidate_history(history)
        evidence = self._validate_actor_evidence(history, evidence)
        likelihood_ratios = evidence.actor_likelihood_ratios
        return self._apply_evidence_revision(
            history,
            evidence=evidence,
            hypothesis_likelihood_ratios={
                item.hypothesis_id: likelihood_ratios.get(item.responsible_actor_key, 1.0)
                for item in history.latest.hypotheses
            },
            unresolved_likelihood_ratio=likelihood_ratios.get("unknown_actor", 1.0),
            evidence_weight=evidence.effective_sample_weight,
            retraction_threshold=retraction_threshold,
            update_kind=EventHypothesisUpdateKind.REVISE,
            revision_reason="actor responsibility likelihood-ratio revision",
        )

    def revise_event_mechanism(
        self,
        history: EventHypothesisHistory,
        evidence: EventMechanismEvidence,
        *,
        retraction_threshold: float = 0.01,
    ) -> EventHypothesisHistory:
        """Revise direct/handoff alternatives from a separate mechanism factor."""

        history = self._revalidate_history(history)
        evidence = self._validate_structured_event_evidence(history, evidence)
        likelihood_ratios = evidence.mechanism_likelihood_ratios
        return self._apply_evidence_revision(
            history,
            evidence=evidence,
            hypothesis_likelihood_ratios={
                item.hypothesis_id: likelihood_ratios[EventMechanism(item.explanation_code)]
                for item in history.latest.hypotheses
            },
            unresolved_likelihood_ratio=1.0,
            evidence_weight=evidence.effective_sample_weight,
            retraction_threshold=retraction_threshold,
            update_kind=EventHypothesisUpdateKind.REVISE_MECHANISM,
            revision_reason="event mechanism likelihood-ratio revision",
        )

    def revise_role_binding(
        self,
        history: EventHypothesisHistory,
        evidence: RoleBindingEvidence,
        *,
        retraction_threshold: float = 0.01,
    ) -> EventHypothesisHistory:
        """Revise ordered handoff roles without affecting direct-chain scores."""

        history = self._revalidate_history(history)
        evidence = self._validate_structured_event_evidence(history, evidence)
        likelihood_ratios = evidence.ordered_role_likelihood_ratios
        return self._apply_evidence_revision(
            history,
            evidence=evidence,
            hypothesis_likelihood_ratios={
                item.hypothesis_id: self._role_likelihood_ratio(item, likelihood_ratios)
                for item in history.latest.hypotheses
            },
            unresolved_likelihood_ratio=1.0,
            evidence_weight=evidence.effective_sample_weight,
            retraction_threshold=retraction_threshold,
            update_kind=EventHypothesisUpdateKind.REVISE_ROLE,
            revision_reason="ordered handoff-role likelihood-ratio revision",
        )

    def reactivate_with_evidence(
        self,
        history: EventHypothesisHistory,
        evidence: HiddenEventEvidence,
        *,
        retraction_threshold: float = 0.01,
    ) -> EventHypothesisHistory:
        """Consume independent evidence and allow shadow-supported chains to return.

        The shadow ``revival_probability`` is updated on every revision, even
        while a chain is retracted.  Reactivation reallocates the original
        branch's resolved mass from this shadow distribution; it never changes
        hypothesis identity or drops the audit history.
        """

        history = self._revalidate_history(history)
        if isinstance(evidence, ActorResponsibilityEvidence):
            actor_evidence = self._validate_actor_evidence(history, evidence)
            validated: HiddenEventEvidence = actor_evidence
            actor_ratios = actor_evidence.actor_likelihood_ratios
            hypothesis_ratios = {
                item.hypothesis_id: actor_ratios.get(item.responsible_actor_key, 1.0)
                for item in history.latest.hypotheses
            }
            unresolved_ratio = actor_ratios.get("unknown_actor", 1.0)
            weight = actor_evidence.effective_sample_weight
            reason = "actor evidence reactivation"
        elif isinstance(evidence, EventMechanismEvidence):
            validated = self._validate_structured_event_evidence(history, evidence)
            mechanism_ratios = validated.mechanism_likelihood_ratios
            hypothesis_ratios = {
                item.hypothesis_id: mechanism_ratios[EventMechanism(item.explanation_code)]
                for item in history.latest.hypotheses
            }
            unresolved_ratio = 1.0
            weight = validated.effective_sample_weight
            reason = "event mechanism evidence reactivation"
        elif isinstance(evidence, RoleBindingEvidence):
            validated = self._validate_structured_event_evidence(history, evidence)
            role_ratios = validated.ordered_role_likelihood_ratios
            hypothesis_ratios = {
                item.hypothesis_id: self._role_likelihood_ratio(item, role_ratios)
                for item in history.latest.hypotheses
            }
            unresolved_ratio = 1.0
            weight = validated.effective_sample_weight
            reason = "ordered role evidence reactivation"
        else:
            raise TypeError("unsupported hidden-event evidence type")
        return self._apply_evidence_revision(
            history,
            evidence=validated,
            hypothesis_likelihood_ratios=hypothesis_ratios,
            unresolved_likelihood_ratio=unresolved_ratio,
            evidence_weight=weight,
            retraction_threshold=retraction_threshold,
            update_kind=EventHypothesisUpdateKind.REACTIVATE,
            revision_reason=reason,
            allow_reactivation=True,
        )

    def _apply_evidence_revision(
        self,
        history: EventHypothesisHistory,
        *,
        evidence: HiddenEventEvidence,
        hypothesis_likelihood_ratios: dict[UUID, float],
        unresolved_likelihood_ratio: float,
        evidence_weight: float,
        retraction_threshold: float,
        update_kind: EventHypothesisUpdateKind,
        revision_reason: str,
        allow_reactivation: bool = False,
    ) -> EventHypothesisHistory:
        if not 0.0 <= retraction_threshold < 1.0:
            raise ValueError("retraction_threshold must be in [0, 1)")
        current = history.latest
        expected_ids = {item.hypothesis_id for item in current.hypotheses}
        if set(hypothesis_likelihood_ratios) != expected_ids:
            raise ValueError("evidence likelihoods must cover every hidden-event hypothesis")
        if any(value < 0.0 for value in hypothesis_likelihood_ratios.values()):
            raise ValueError("evidence likelihood ratios cannot be negative")
        if unresolved_likelihood_ratio < 0.0:
            raise ValueError("unresolved likelihood ratio cannot be negative")

        shadow_raw = {
            item.hypothesis_id: item.revival_probability
            * hypothesis_likelihood_ratios[item.hypothesis_id] ** evidence_weight
            for item in current.hypotheses
        }
        shadow_total = sum(shadow_raw.values())
        if shadow_total <= 0.0:
            shadow = {
                item.hypothesis_id: 1.0 / len(current.hypotheses) for item in current.hypotheses
            }
        else:
            shadow = {
                hypothesis_id: value / shadow_total for hypothesis_id, value in shadow_raw.items()
            }

        reactivation_eligible = {
            item.hypothesis_id
            for item in current.hypotheses
            if item.status == EventHypothesisStatus.RETRACTED
            and hypothesis_likelihood_ratios[item.hypothesis_id] > 1.0
            and shadow[item.hypothesis_id] > item.revival_probability
        }
        if allow_reactivation and reactivation_eligible:
            branch_unresolved = history.revisions[0].unresolved_probability
            resolved_mass = 1.0 - branch_unresolved
            normalized_unresolved = branch_unresolved
            eligible = {
                item.hypothesis_id
                for item in current.hypotheses
                if item.status == EventHypothesisStatus.ACTIVE
            } | reactivation_eligible
            eligible_shadow_total = sum(shadow[hypothesis_id] for hypothesis_id in eligible)
            normalized = {
                hypothesis_id: (
                    resolved_mass * probability / eligible_shadow_total
                    if hypothesis_id in eligible
                    else 0.0
                )
                for hypothesis_id, probability in shadow.items()
            }
        else:
            raw_weights = {
                item.hypothesis_id: (
                    item.posterior_probability
                    * hypothesis_likelihood_ratios[item.hypothesis_id] ** evidence_weight
                    if item.status == EventHypothesisStatus.ACTIVE
                    else 0.0
                )
                for item in current.hypotheses
            }
            raw_unresolved = current.unresolved_probability * (
                unresolved_likelihood_ratio**evidence_weight
            )
            total = raw_unresolved + sum(raw_weights.values())
            if total <= 0.0:
                normalized_unresolved = 1.0
                normalized = {item.hypothesis_id: 0.0 for item in current.hypotheses}
            else:
                normalized_unresolved = raw_unresolved / total
                normalized = {
                    hypothesis_id: weight / total for hypothesis_id, weight in raw_weights.items()
                }

        retracted_mass = sum(
            probability for probability in normalized.values() if probability < retraction_threshold
        )
        retained = {
            hypothesis_id: (0.0 if probability < retraction_threshold else probability)
            for hypothesis_id, probability in normalized.items()
        }
        unresolved = normalized_unresolved + retracted_mass
        revised = tuple(
            item.model_copy(
                update={
                    "posterior_probability": retained[item.hypothesis_id],
                    "revival_probability": shadow[item.hypothesis_id],
                    "source_record_ids": (*item.source_record_ids, evidence.metadata.record_id),
                    "status": (
                        EventHypothesisStatus.ACTIVE
                        if retained[item.hypothesis_id] > 0.0
                        else EventHypothesisStatus.RETRACTED
                    ),
                }
            )
            for item in current.hypotheses
        )
        revision = self._make_revision_from_current(
            current,
            hypotheses=revised,
            unresolved_probability=unresolved,
            update_kind=update_kind,
            revision_evidence_record_ids=(evidence.metadata.record_id,),
            revision_evidence_cluster_ids=(evidence.evidence_cluster_id,),
            revision_evidence_semantic_fingerprints=(
                hidden_event_evidence_semantic_fingerprint(evidence),
            ),
            revision_evidence_source_detection_result_ids=(evidence.source_detection_result_id,),
            revision_evidence_endpoint_roles=(ActorEvidenceEndpointRole.DESTINATION_STATE,),
            revision_reason=revision_reason,
        )
        return history.append(revision)

    @staticmethod
    def _role_likelihood_ratio(
        hypothesis: EventChainHypothesis,
        likelihood_ratios: dict[str, float],
    ) -> float:
        if hypothesis.explanation_code == EventMechanism.DIRECT_RELOCATION.value:
            return 1.0
        return likelihood_ratios.get(
            ordered_role_key(
                hypothesis.steps[0].actor_key,
                hypothesis.responsible_actor_key,
            ),
            1.0,
        )

    def retract(
        self,
        history: EventHypothesisHistory,
        *,
        hypothesis_ids: tuple[UUID, ...],
        counterevidence: tuple[ActorResponsibilityEvidence, ...],
        reason: str,
    ) -> EventHypothesisHistory:
        history = self._revalidate_history(history)
        if not hypothesis_ids:
            raise ValueError("retract requires at least one hypothesis ID")
        if not counterevidence:
            raise ValueError("retract requires at least one counterevidence record")
        if not reason.strip():
            raise ValueError("retract reason must be non-empty")
        current = history.latest
        known = {item.hypothesis_id for item in current.hypotheses}
        unknown = set(hypothesis_ids) - known
        if unknown:
            raise ValueError("cannot retract a hypothesis outside the CHEH set")
        targeted = tuple(
            item for item in current.hypotheses if item.hypothesis_id in hypothesis_ids
        )
        if any(item.status != EventHypothesisStatus.ACTIVE for item in targeted):
            raise ValueError("cannot retract a hypothesis that is not active")

        validated_evidence = tuple(
            self._validate_actor_evidence(history, item, pending=counterevidence[:index])
            for index, item in enumerate(counterevidence)
        )
        for hypothesis in targeted:
            if not any(
                hypothesis.responsible_actor_key in item.actor_posterior
                and item.actor_posterior[hypothesis.responsible_actor_key] == 0.0
                for item in validated_evidence
            ):
                raise ValueError(
                    "retraction evidence must explicitly assign zero probability "
                    "to every targeted responsible actor"
                )

        removed_mass = sum(
            item.posterior_probability
            for item in current.hypotheses
            if item.hypothesis_id in set(hypothesis_ids)
        )
        revised = tuple(
            item.model_copy(
                update={
                    "posterior_probability": 0.0,
                    "status": EventHypothesisStatus.RETRACTED,
                    "source_record_ids": (
                        *item.source_record_ids,
                        *(evidence.metadata.record_id for evidence in validated_evidence),
                    ),
                }
            )
            if item.hypothesis_id in set(hypothesis_ids)
            else item.model_copy(
                update={
                    "source_record_ids": (
                        *item.source_record_ids,
                        *(evidence.metadata.record_id for evidence in validated_evidence),
                    )
                }
            )
            for item in current.hypotheses
        )
        revision = self._make_revision_from_current(
            current,
            hypotheses=revised,
            unresolved_probability=current.unresolved_probability + removed_mass,
            update_kind=EventHypothesisUpdateKind.RETRACT,
            revision_evidence_record_ids=tuple(
                item.metadata.record_id for item in validated_evidence
            ),
            revision_evidence_cluster_ids=tuple(
                item.evidence_cluster_id for item in validated_evidence
            ),
            revision_evidence_semantic_fingerprints=tuple(
                actor_evidence_semantic_fingerprint(item) for item in validated_evidence
            ),
            revision_evidence_source_detection_result_ids=tuple(
                item.source_detection_result_id for item in validated_evidence
            ),
            revision_evidence_endpoint_roles=tuple(
                ActorEvidenceEndpointRole.DESTINATION_STATE for _ in validated_evidence
            ),
            revision_reason=reason,
        )
        return history.append(revision)

    @staticmethod
    def rebuild(
        revisions: tuple[EventHypothesisRevision, ...],
    ) -> EventHypothesisHistory:
        if not revisions:
            raise ValueError("CHEH rebuild requires at least one revision")
        history = EventHypothesisHistory(
            hypothesis_set_id=revisions[0].hypothesis_set_id,
            revisions=revisions,
        )
        return CounterfactualEventHypergraphEngine._revalidate_history(history)

    @staticmethod
    def _revalidate_detection(
        detection: ObservationDetectionResult, label: str
    ) -> ObservationDetectionResult:
        try:
            CounterfactualEventHypergraphEngine._reject_model_copy_extras(
                detection, f"CHEH {label} endpoint"
            )
            validated = ObservationDetectionResult.model_validate(
                detection.model_dump(mode="python", round_trip=True, warnings=False)
            )
            if (
                validated.metadata.schema_name != "cpswm.ObservationDetectionResult"
                or validated.metadata.schema_version
                != CounterfactualEventHypergraphEngine.schema_version
            ):
                raise ValueError(
                    "endpoint metadata schema must be cpswm.ObservationDetectionResult@0.1.0"
                )
            return validated
        except Exception as exc:
            raise ValueError(f"invalid CHEH {label} endpoint: {exc}") from exc

    @staticmethod
    def _revalidate_history(
        history: EventHypothesisHistory,
    ) -> EventHypothesisHistory:
        try:
            CounterfactualEventHypergraphEngine._reject_model_copy_extras(history, "CHEH history")
            return EventHypothesisHistory.model_validate(
                history.model_dump(mode="python", round_trip=True, warnings=False)
            )
        except Exception as exc:
            raise ValueError(f"invalid CHEH history: {exc}") from exc

    @staticmethod
    def _validate_endpoints(
        before: ObservationDetectionResult,
        after: ObservationDetectionResult,
    ) -> None:
        if before.outcome != ObservationOutcome.DETECTED:
            raise ValueError("CHEH before endpoint must be detected")
        if after.outcome != ObservationOutcome.DETECTED:
            raise ValueError("CHEH after endpoint must be detected")
        if before.detected_object_instance_id != after.detected_object_instance_id:
            raise ValueError("CHEH endpoints must concern the same object")
        if before.detected_location_id == after.detected_location_id:
            raise ValueError("CHEH first slice requires a location transition")
        if before.detection_time is None or after.detection_time is None:
            raise ValueError("CHEH detected endpoints require times")
        if after.detection_time <= before.detection_time:
            raise ValueError("CHEH after endpoint must follow before endpoint")
        for field_name in ("household_id", "session_id", "trace_id"):
            if getattr(before.metadata, field_name) != getattr(after.metadata, field_name):
                raise ValueError(f"CHEH endpoints must share {field_name}")

    @classmethod
    def _validate_actor_evidence(
        cls,
        history: EventHypothesisHistory,
        evidence: ActorResponsibilityEvidence,
        *,
        pending: tuple[ActorResponsibilityEvidence, ...] = (),
    ) -> ActorResponsibilityEvidence:
        """Validate an evidence object and bind it to a known endpoint/context."""

        try:
            cls._reject_model_copy_extras(evidence, "actor responsibility evidence")
            evidence = ActorResponsibilityEvidence.model_validate(
                evidence.model_dump(mode="python", round_trip=True, warnings=False)
            )
        except Exception as exc:
            raise ValueError(f"invalid actor responsibility evidence: {exc}") from exc

        if (
            evidence.metadata.schema_name != "cpswm.ActorResponsibilityEvidence"
            or evidence.metadata.schema_version != cls.schema_version
        ):
            raise ValueError(
                "actor evidence metadata schema must be cpswm.ActorResponsibilityEvidence@0.1.0"
            )

        current = history.latest
        if evidence.object_instance_id != current.object_instance_id:
            raise ValueError("actor evidence object does not match CHEH hypothesis set")
        for field_name in ("household_id", "session_id", "trace_id"):
            if getattr(evidence.metadata, field_name) != getattr(current, field_name):
                raise ValueError(f"actor evidence {field_name} does not match CHEH set")

        endpoint_times = dict(
            zip(
                current.source_detection_result_ids,
                (current.interval_start, current.interval_end),
                strict=True,
            )
        )
        expected_time = endpoint_times.get(evidence.source_detection_result_id)
        if expected_time is None:
            raise ValueError("actor evidence must cite a CHEH endpoint detection")
        if evidence.evidence_time != expected_time:
            raise ValueError("actor evidence time does not match its endpoint detection")
        destination_endpoint_id = current.source_detection_result_ids[1]
        if evidence.source_detection_result_id != destination_endpoint_id:
            raise ValueError(
                "actor responsibility revision requires evidence from the CHEH "
                "destination endpoint detection"
            )

        previously_used = {
            record_id
            for revision in history.revisions
            for record_id in revision.revision_evidence_record_ids
        }
        pending_ids = {item.metadata.record_id for item in pending}
        if evidence.metadata.record_id in previously_used | pending_ids:
            raise ValueError("actor evidence record cannot be reused in CHEH revisions")
        previously_used_clusters = history.consumed_evidence_cluster_ids
        pending_clusters = {item.evidence_cluster_id for item in pending}
        if evidence.evidence_cluster_id in previously_used_clusters | pending_clusters:
            raise ValueError("correlated actor evidence cluster cannot be reused")
        fingerprint = actor_evidence_semantic_fingerprint(evidence)
        previously_used_fingerprints = history.consumed_evidence_semantic_fingerprints
        pending_fingerprints = {actor_evidence_semantic_fingerprint(item) for item in pending}
        if fingerprint in previously_used_fingerprints | pending_fingerprints:
            raise ValueError("semantic actor evidence cannot be reused")
        return evidence

    @classmethod
    def _validate_structured_event_evidence(
        cls,
        history: EventHypothesisHistory,
        evidence: StructuredEventEvidenceT,
    ) -> StructuredEventEvidenceT:
        """Validate mechanism/role evidence and bind it to the destination endpoint."""

        evidence_type = type(evidence)
        label = (
            "event mechanism evidence"
            if isinstance(evidence, EventMechanismEvidence)
            else "role-binding evidence"
        )
        expected_schema = (
            "cpswm.EventMechanismEvidence"
            if isinstance(evidence, EventMechanismEvidence)
            else "cpswm.RoleBindingEvidence"
        )
        try:
            cls._reject_model_copy_extras(evidence, label)
            evidence = evidence_type.model_validate(
                evidence.model_dump(mode="python", round_trip=True, warnings=False)
            )
        except Exception as exc:
            raise ValueError(f"invalid {label}: {exc}") from exc
        if (
            evidence.metadata.schema_name != expected_schema
            or evidence.metadata.schema_version != cls.schema_version
        ):
            raise ValueError(f"{label} metadata schema must be {expected_schema}@0.1.0")

        current = history.latest
        if evidence.object_instance_id != current.object_instance_id:
            raise ValueError(f"{label} object does not match CHEH hypothesis set")
        for field_name in ("household_id", "session_id", "trace_id"):
            if getattr(evidence.metadata, field_name) != getattr(current, field_name):
                raise ValueError(f"{label} {field_name} does not match CHEH set")
        destination_endpoint_id = current.source_detection_result_ids[1]
        if evidence.source_detection_result_id != destination_endpoint_id:
            raise ValueError(f"{label} must cite the CHEH destination endpoint")
        if evidence.evidence_time != current.interval_end:
            raise ValueError(f"{label} time does not match the destination endpoint")

        previously_used = {
            record_id
            for revision in history.revisions
            for record_id in revision.revision_evidence_record_ids
        }
        if evidence.metadata.record_id in previously_used:
            raise ValueError(f"{label} record cannot be reused")
        if evidence.evidence_cluster_id in history.consumed_evidence_cluster_ids:
            raise ValueError(f"correlated {label} cluster cannot be reused")
        fingerprint = hidden_event_evidence_semantic_fingerprint(evidence)
        if fingerprint in history.consumed_evidence_semantic_fingerprints:
            raise ValueError(f"semantic {label} cannot be reused")
        return evidence

    @classmethod
    def _reject_model_copy_extras(cls, value: object, path: str) -> None:
        """Reject live fields that Pydantic serialization would omit."""

        if isinstance(value, BaseModel):
            declared_fields = set(type(value).model_fields)
            live_fields = set(value.__dict__)
            pydantic_extras = getattr(value, "__pydantic_extra__", None) or {}
            unexpected_fields = (live_fields - declared_fields) | set(pydantic_extras)
            if unexpected_fields:
                names = ", ".join(sorted(unexpected_fields))
                raise ValueError(f"{path} contains unexpected field(s): {names}")
            for field_name in declared_fields:
                cls._reject_model_copy_extras(getattr(value, field_name), f"{path}.{field_name}")
        elif isinstance(value, dict):
            for key, nested in value.items():
                cls._reject_model_copy_extras(nested, f"{path}[{key!r}]")
        elif isinstance(value, (list, tuple)):
            for index, nested in enumerate(value):
                cls._reject_model_copy_extras(nested, f"{path}[{index}]")

    @staticmethod
    def _validate_distribution(distribution: dict[str, float], name: str) -> None:
        if not distribution or any(not key.strip() for key in distribution):
            raise ValueError(f"{name} requires non-empty actor keys")
        if any(value < 0.0 or value > 1.0 for value in distribution.values()):
            raise ValueError(f"{name} probabilities must be in [0, 1]")
        if not isclose(sum(distribution.values()), 1.0, rel_tol=0.0, abs_tol=1e-6):
            raise ValueError(f"{name} probabilities must sum to 1")

    def _direct_steps(
        self,
        *,
        hypothesis_set_id: UUID,
        actor_key: str,
        object_instance_id: UUID,
        source_location_id: UUID,
        destination_location_id: UUID,
        interval_start: datetime,
        interval_end: datetime,
    ) -> tuple[HiddenEventStep, ...]:
        specs = (
            (EventType.PICK_UP, actor_key, source_location_id, None, None),
            (EventType.CARRY, actor_key, source_location_id, destination_location_id, None),
            (EventType.PLACE, actor_key, None, destination_location_id, None),
        )
        return self._steps(
            hypothesis_set_id=hypothesis_set_id,
            signature=f"direct:{actor_key}",
            specs=specs,
            object_instance_id=object_instance_id,
            interval_start=interval_start,
            interval_end=interval_end,
        )

    def _handoff_steps(
        self,
        *,
        hypothesis_set_id: UUID,
        actor_key: str,
        recipient_key: str,
        object_instance_id: UUID,
        source_location_id: UUID,
        destination_location_id: UUID,
        interval_start: datetime,
        interval_end: datetime,
    ) -> tuple[HiddenEventStep, ...]:
        specs = (
            (EventType.PICK_UP, actor_key, source_location_id, None, None),
            (EventType.CARRY, actor_key, source_location_id, destination_location_id, None),
            (EventType.TRANSFER, actor_key, None, None, recipient_key),
            (EventType.PLACE, recipient_key, None, destination_location_id, None),
        )
        return self._steps(
            hypothesis_set_id=hypothesis_set_id,
            signature=f"handoff:{actor_key}->{recipient_key}",
            specs=specs,
            object_instance_id=object_instance_id,
            interval_start=interval_start,
            interval_end=interval_end,
        )

    @staticmethod
    def _steps(
        *,
        hypothesis_set_id: UUID,
        signature: str,
        specs: tuple[tuple[EventType, str, UUID | None, UUID | None, str | None], ...],
        object_instance_id: UUID,
        interval_start: datetime,
        interval_end: datetime,
    ) -> tuple[HiddenEventStep, ...]:
        interval = interval_end - interval_start
        steps = []
        for sequence_no, (
            event_type,
            actor_key,
            source_location_id,
            destination_location_id,
            recipient_actor_key,
        ) in enumerate(specs):
            event_time = interval_start + interval * ((sequence_no + 1) / (len(specs) + 1))
            step_payload = {
                "sequence_no": sequence_no,
                "event_type": event_type,
                "actor_key": actor_key,
                "recipient_actor_key": recipient_actor_key,
                "object_instance_id": object_instance_id,
                "source_location_id": source_location_id,
                "destination_location_id": destination_location_id,
                "event_time": event_time,
            }
            step_identity = {
                "hypothesis_set_id": hypothesis_set_id,
                "signature": signature,
                **step_payload,
            }
            steps.append(
                HiddenEventStep(
                    step_id=content_uuid("cheh-step", step_identity),
                    sequence_no=sequence_no,
                    event_type=event_type,
                    actor_key=actor_key,
                    recipient_actor_key=recipient_actor_key,
                    object_instance_id=object_instance_id,
                    source_location_id=source_location_id,
                    destination_location_id=destination_location_id,
                    event_time=event_time,
                )
            )
        return tuple(steps)

    @staticmethod
    def _make_hypothesis(
        *,
        hypothesis_set_id: UUID,
        responsible_actor_key: str,
        steps: tuple[HiddenEventStep, ...],
        posterior_probability: float,
        revival_probability: float,
        source_record_ids: tuple[UUID, ...],
        explanation_code: str,
    ) -> EventChainHypothesis:
        identity = {
            "hypothesis_set_id": hypothesis_set_id,
            "responsible_actor_key": responsible_actor_key,
            "steps": steps,
            "explanation_code": explanation_code,
        }
        return EventChainHypothesis(
            hypothesis_id=content_uuid("cheh-hypothesis", identity),
            responsible_actor_key=responsible_actor_key,
            steps=steps,
            posterior_probability=posterior_probability,
            revival_probability=revival_probability,
            status=EventHypothesisStatus.ACTIVE,
            source_record_ids=source_record_ids,
            explanation_code=explanation_code,
        )

    def _make_revision_from_current(
        self,
        current: EventHypothesisRevision,
        *,
        hypotheses: tuple[EventChainHypothesis, ...],
        unresolved_probability: float,
        update_kind: EventHypothesisUpdateKind,
        revision_evidence_record_ids: tuple[UUID, ...],
        revision_evidence_cluster_ids: tuple[UUID, ...],
        revision_evidence_semantic_fingerprints: tuple[str, ...],
        revision_evidence_source_detection_result_ids: tuple[UUID, ...],
        revision_evidence_endpoint_roles: tuple[ActorEvidenceEndpointRole, ...],
        revision_reason: str,
    ) -> EventHypothesisRevision:
        return self._make_revision(
            hypothesis_set_id=current.hypothesis_set_id,
            revision_no=current.revision_no + 1,
            parent_revision_id=current.revision_id,
            update_kind=update_kind,
            household_id=current.household_id,
            session_id=current.session_id,
            trace_id=current.trace_id,
            object_instance_id=current.object_instance_id,
            interval_start=current.interval_start,
            interval_end=current.interval_end,
            source_location_id=current.source_location_id,
            destination_location_id=current.destination_location_id,
            source_detection_result_ids=current.source_detection_result_ids,
            hypotheses=hypotheses,
            unresolved_probability=unresolved_probability,
            revision_evidence_record_ids=revision_evidence_record_ids,
            revision_evidence_cluster_ids=revision_evidence_cluster_ids,
            revision_evidence_semantic_fingerprints=(revision_evidence_semantic_fingerprints),
            revision_evidence_source_detection_result_ids=(
                revision_evidence_source_detection_result_ids
            ),
            revision_evidence_endpoint_roles=revision_evidence_endpoint_roles,
            revision_reason=revision_reason,
        )

    def _make_revision(self, **payload: Any) -> EventHypothesisRevision:
        complete_payload = {**payload, "engine_version": self.engine_version}
        return EventHypothesisRevision(
            **complete_payload,
            revision_id=content_uuid("cheh-revision", complete_payload),
            revision_content_sha256=content_sha256(complete_payload),
        )


class OpenWorldRoleConditionedReversibleEventRevisionEngine(CounterfactualEventHypergraphEngine):
    """ORRER v0.1 with open-world handoff roles and reversible thresholding."""

    engine_version = "orrer@0.1"

    def branch(
        self,
        *,
        before: ObservationDetectionResult,
        after: ObservationDetectionResult,
        actor_prior: dict[str, float],
        unresolved_probability: float = 0.1,
        handoff_fraction: float = 0.2,
        allow_unknown_handoff_roles: bool = True,
    ) -> EventHypothesisHistory:
        if not allow_unknown_handoff_roles:
            raise ValueError("ORRER requires open-world unknown handoff roles")
        return super().branch(
            before=before,
            after=after,
            actor_prior=actor_prior,
            unresolved_probability=unresolved_probability,
            handoff_fraction=handoff_fraction,
            allow_unknown_handoff_roles=True,
        )
