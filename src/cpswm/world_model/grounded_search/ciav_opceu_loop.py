"""Runtime bridge from CIAV action selection to canonical OPCEU evidence.

The bridge deliberately separates the pre-outcome observation opportunity from
the callback that realizes an observation.  Evaluation code may read hidden
truth inside that callback, but only after the selected action, likelihood
model, propensity, and provenance scope have been frozen in an opportunity
record.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isclose, isfinite
from uuid import UUID

from cpswm.contracts import (
    BaseRecordMetadata,
    DetectionFailureReason,
    EvidenceFactorConsumptionTrace,
    EvidenceFactorKind,
    EvidenceFactorOperator,
    EvidenceFactorReceipt,
    EvidenceFactorSourceSemantics,
    EvidenceProductionMode,
    MissingnessMechanism,
    ObservationActionCandidate,
    ObservationDetectionResult,
    ObservationMechanismEnvelope,
    ObservationOpportunityRecord,
    ObservationOutcome,
    OcclusionState,
    OpenSetEvidenceSupport,
    PrivacyScope,
    PropensityRecord,
    SourceType,
    UnifiedEvidenceContract,
    ValidTimeInterval,
)
from cpswm.system.reproducibility import content_sha256, content_uuid


@dataclass(frozen=True, slots=True)
class RealizedCIAVObservation:
    """Robot-visible result returned after an opportunity has been frozen."""

    outcome_label: str
    likelihood_model_id: str
    detection_outcome: ObservationOutcome
    failure_reason: DetectionFailureReason = DetectionFailureReason.NOT_APPLICABLE
    occlusion_state: OcclusionState = OcclusionState.CLEAR


@dataclass(frozen=True, slots=True)
class CIAVOPCEUReceipt:
    opportunity: ObservationOpportunityRecord
    detection: ObservationDetectionResult
    evidence: UnifiedEvidenceContract
    mechanism: ObservationMechanismEnvelope
    produced_factor: EvidenceFactorReceipt
    consumed_factor: EvidenceFactorReceipt
    posterior_summary: EvidenceFactorReceipt
    outcome_label: str


class CIAVOPCEUObservationLoop:
    """Materialize one selected CIAV action as OPCEU evidence and trace it."""

    def __init__(self, trace: EvidenceFactorConsumptionTrace | None = None) -> None:
        self.trace = trace or EvidenceFactorConsumptionTrace()

    @staticmethod
    def _metadata(
        *,
        record_kind: str,
        identity_payload: Mapping[str, object],
        household_id: UUID,
        session_id: UUID,
        trace_id: UUID,
        recorded_time: datetime,
        model_version: str,
    ) -> BaseRecordMetadata:
        return BaseRecordMetadata(
            record_id=content_uuid(record_kind, identity_payload),
            schema_name=record_kind,
            schema_version="0.1.0",
            household_id=household_id,
            session_id=session_id,
            recorded_time=recorded_time,
            source_type=SourceType.SIMULATION,
            source_id="D0-ciav-opceu-observation-loop",
            model_version=model_version,
            privacy_scope=PrivacyScope.RESEARCH_DEIDENTIFIED,
            trace_id=trace_id,
        )

    def execute_selected_action(
        self,
        *,
        action: ObservationActionCandidate,
        update_id: UUID,
        household_id: UUID,
        session_id: UUID,
        trace_id: UUID,
        opportunity_time: datetime,
        object_instance_id: UUID,
        actor_keys: Sequence[str],
        actor_prior: Mapping[str, float],
        actor_likelihoods_by_outcome: Mapping[str, Mapping[str, float]],
        location_keys: Sequence[str],
        expected_detected_location_id: UUID,
        selection_probability: float,
        p_visible_given_state: float,
        p_detect_given_visible: float,
        realizer: Callable[[ObservationOpportunityRecord], RealizedCIAVObservation],
    ) -> CIAVOPCEUReceipt:
        """Execute only an already-selected action; the callback runs second."""

        actors = tuple(dict.fromkeys((*actor_keys, "unknown_actor")))
        locations = tuple(dict.fromkeys((*location_keys, "unknown_location")))
        if set(actor_prior) != set(actors):
            raise ValueError("CIAV actor prior must exactly cover the open actor support")
        if any(not isfinite(value) or value < 0.0 for value in actor_prior.values()) or not isclose(
            sum(actor_prior.values()), 1.0, rel_tol=0.0, abs_tol=1e-6
        ):
            raise ValueError("CIAV actor prior must be a normalized finite distribution")
        if set(actor_likelihoods_by_outcome) != set(action.outcome_likelihoods):
            raise ValueError("CIAV actor likelihood table must cover every registered outcome")
        for likelihoods in actor_likelihoods_by_outcome.values():
            if set(likelihoods) != set(actors):
                raise ValueError("CIAV actor likelihood must exactly cover the open actor support")
            if any(
                not isfinite(value) or not 0.0 <= value <= 1.0 for value in likelihoods.values()
            ):
                raise ValueError("CIAV actor likelihood values must lie in [0, 1]")
        actor_likelihood_table_sha256 = content_sha256(
            {
                outcome: dict(sorted(likelihoods.items()))
                for outcome, likelihoods in sorted(actor_likelihoods_by_outcome.items())
            },
        )
        support = OpenSetEvidenceSupport(
            actor_keys=actors,
            object_instance_ids=(object_instance_id,),
            location_keys=locations,
            mechanism_keys=("ciav_micro_verification", "unknown_mechanism"),
        )
        identity = {
            "update_id": update_id,
            "action_id": action.action_id,
            "opportunity_time": opportunity_time,
            "likelihood_model_id": action.observation_likelihood_model_id,
            "actor_likelihood_table_sha256": actor_likelihood_table_sha256,
        }
        opportunity = ObservationOpportunityRecord(
            metadata=self._metadata(
                record_kind="ciav-observation-opportunity",
                identity_payload=identity,
                household_id=household_id,
                session_id=session_id,
                trace_id=trace_id,
                recorded_time=opportunity_time,
                model_version=action.observation_likelihood_model_id,
            ),
            observation_action_id=action.action_id,
            opportunity_time=opportunity_time,
            selected=True,
            selection_probability=selection_probability,
            p_visible_given_state=p_visible_given_state,
            p_detect_given_visible=p_detect_given_visible,
            likelihood_model_id=action.observation_likelihood_model_id,
        )

        # This is the only call that may consult evaluator truth in a simulator.
        realized = realizer(opportunity)
        if realized.likelihood_model_id != action.observation_likelihood_model_id:
            raise ValueError("CIAV realizer used a different likelihood model")
        if realized.outcome_label not in action.outcome_likelihoods:
            raise ValueError("CIAV realizer returned an unregistered outcome")
        if str(expected_detected_location_id) not in locations:
            raise ValueError("CIAV visible location is outside the frozen location support")
        actor_likelihoods = actor_likelihoods_by_outcome[realized.outcome_label]
        actor_unnormalized = {
            actor: actor_prior[actor] * actor_likelihoods[actor] for actor in actors
        }
        actor_total = sum(actor_unnormalized.values())
        if actor_total <= 0.0:
            raise ValueError("CIAV actor likelihood has zero probability under the frozen prior")
        actor_posterior = {
            actor: value / actor_total for actor, value in actor_unnormalized.items()
        }
        detected = realized.detection_outcome is ObservationOutcome.DETECTED
        detection = ObservationDetectionResult(
            metadata=self._metadata(
                record_kind="ciav-observation-detection",
                identity_payload={**identity, "outcome": realized.outcome_label},
                household_id=household_id,
                session_id=session_id,
                trace_id=trace_id,
                recorded_time=opportunity_time,
                model_version=action.observation_likelihood_model_id,
            ),
            observation_opportunity_id=opportunity.metadata.record_id,
            outcome=realized.detection_outcome,
            detected_object_instance_id=(object_instance_id if detected else None),
            detected_location_id=expected_detected_location_id if detected else None,
            detection_time=opportunity_time if detected else None,
        )
        evidence_cluster_id = content_uuid("ciav-evidence-cluster", identity)
        valid_time = ValidTimeInterval(
            start=opportunity_time,
            end=opportunity_time + timedelta(microseconds=1),
        )
        evidence = UnifiedEvidenceContract(
            metadata=self._metadata(
                record_kind="ciav-unified-evidence",
                identity_payload={**identity, "outcome": realized.outcome_label},
                household_id=household_id,
                session_id=session_id,
                trace_id=trace_id,
                recorded_time=opportunity_time,
                model_version=action.observation_likelihood_model_id,
            ),
            valid_time=valid_time,
            object_instance_id=object_instance_id,
            object_posterior={
                str(object_instance_id): 1.0,
                "unknown_object": 0.0,
            },
            location_posterior={
                **dict.fromkeys(locations, 0.0),
                str(expected_detected_location_id): 1.0 if detected else 0.0,
                "unknown_location": 0.0 if detected else 1.0,
            },
            detected_object_key=str(object_instance_id) if detected else None,
            detected_location_key=str(expected_detected_location_id) if detected else None,
            actor_posterior=actor_posterior,
            observation_opportunity=opportunity,
            selected_for_observation=True,
            selection_probability=selection_probability,
            field_of_view_coverage=p_visible_given_state,
            occlusion_state=realized.occlusion_state,
            detection_outcome=realized.detection_outcome,
            detection_failure_reason=realized.failure_reason,
            production_mode=EvidenceProductionMode.DIRECT,
            evidence_cluster_id=evidence_cluster_id,
            correlation_group_id=f"ciav:{update_id}",
            effective_sample_weight=1.0,
            open_set_support=support,
        )
        mechanism = ObservationMechanismEnvelope(
            metadata=self._metadata(
                record_kind="ciav-observation-mechanism",
                identity_payload={**identity, "outcome": realized.outcome_label},
                household_id=household_id,
                session_id=session_id,
                trace_id=trace_id,
                recorded_time=opportunity_time,
                model_version=action.observation_likelihood_model_id,
            ),
            opportunity=opportunity,
            detection=detection,
            missingness_mechanism=MissingnessMechanism.MNAR,
            conditioning_covariates=("cause_posterior", "owner_prior", "privacy_budget"),
            propensity=PropensityRecord(
                mode="ciav-selected-policy-propensity-no-ipw",
                raw_propensity=selection_probability,
                applied_weight=1.0,
            ),
            residual_bias_note=(
                "CIAV selection depends on the latent-cause belief; no unbiased IPW claim is made."
            ),
        )

        factor_id = f"opceu:{evidence.metadata.record_id}"
        source_record_ids = (
            opportunity.metadata.record_id,
            detection.metadata.record_id,
            evidence.metadata.record_id,
            mechanism.metadata.record_id,
        )
        produced = self.trace.produce_factor(
            update_id=update_id,
            evidence_cluster_id=evidence_cluster_id,
            evidence_record_ids=source_record_ids,
            operator=EvidenceFactorOperator.OPCEU,
            factor_id=factor_id,
            factor_kind=EvidenceFactorKind.OBSERVATION_LIKELIHOOD,
            source_semantics=EvidenceFactorSourceSemantics.RAW_OBSERVATION_EVIDENCE,
            source_record_payloads={
                opportunity.metadata.record_id: opportunity.model_dump(mode="python"),
                detection.metadata.record_id: detection.model_dump(mode="python"),
                evidence.metadata.record_id: evidence.model_dump(mode="python"),
                mechanism.metadata.record_id: mechanism.model_dump(mode="python"),
            },
            likelihood_model_id=action.observation_likelihood_model_id,
            idempotency_key=f"produce:{factor_id}",
        )
        # The likelihood this loop consumes is consumed into its *own* local actor
        # posterior, which is what ``CIAVOPCEUReceipt.evidence.actor_posterior``
        # carries.  Whether that local posterior ever reaches the fast-action owner
        # posterior depends on the caller's closure branch: only a same-location
        # detected observation runs ``apply_fast_action_verification``.  The frozen
        # pre-death protocol records that "a negative CIAV observation does not yet
        # enter a complete downstream closure", so the target distribution is named
        # for the distribution this loop actually writes, not for a downstream store
        # it does not own.
        target = f"ciav-local-actor-posterior:{update_id}"
        consumed = self.trace.consume_factor(
            update_id=update_id,
            evidence_cluster_id=evidence_cluster_id,
            evidence_record_ids=source_record_ids,
            operator=EvidenceFactorOperator.CIAV,
            factor_id=f"consume:{factor_id}:{target}",
            factor_kind=EvidenceFactorKind.OBSERVATION_LIKELIHOOD,
            source_factor_ids=(factor_id,),
            target_distribution_id=target,
            likelihood_model_id=action.observation_likelihood_model_id,
            consumed_as_likelihood=True,
            idempotency_key=f"consume:{factor_id}:{target}",
        )
        summary_id = f"posterior:{target}"
        summary = self.trace.derive_factor(
            update_id=update_id,
            evidence_cluster_id=evidence_cluster_id,
            evidence_record_ids=source_record_ids,
            operator=EvidenceFactorOperator.CIAV,
            factor_id=summary_id,
            factor_kind=EvidenceFactorKind.POSTERIOR_SUMMARY,
            source_factor_ids=(factor_id,),
            target_distribution_id=target,
            likelihood_model_id=action.observation_likelihood_model_id,
            idempotency_key=f"derive:{summary_id}",
        )
        return CIAVOPCEUReceipt(
            opportunity=opportunity,
            detection=detection,
            evidence=evidence,
            mechanism=mechanism,
            produced_factor=produced,
            consumed_factor=consumed,
            posterior_summary=summary,
            outcome_label=realized.outcome_label,
        )


__all__ = [
    "CIAVOPCEUObservationLoop",
    "CIAVOPCEUReceipt",
    "RealizedCIAVObservation",
]
