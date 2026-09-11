"""Mechanism-level wiring probes for the Structure-Two backbone and seven operators.

This harness lives under ``tests/`` on purpose.  ``build_production_assembly_manifest``
hashes every file under ``src/cpswm``, so adding an audit-only module there would change
the production assembly manifest of every future run.  It is imported the same way as
``tests/ledger_evidence_fixtures.py``.

Scope and claim boundary
------------------------

This module is a *development probe*.  It drives the real
:class:`~cpswm.system.structure_two_production_system.StructureTwoProductionSystem`
entrypoints over deterministic household scenarios and reports, per scenario,
which operator calls really happened, which upstream outputs really reached
downstream consumers, and which state changes really followed.

It deliberately establishes **only** the following five evidence classes, each
reported separately and never merged:

``same_production_runtime``
    The called object identities, callable symbols, and loaded source hashes
    come from one production runtime assembly.
``algorithmic_implementation_equivalence``
    The bound callable is the operator's own registered implementation rather
    than an enclosing or composite stage.
``state_handoff_correct``
    A change confined to one upstream operator's input really changes the
    downstream operator's receipted output.
``action_affected``
    The same upstream change really changes the typed action readout.
``long_term_utility``
    Never established here.  Always reported as ``not_covered``.

It does **not** establish Task 9 four-coupling results, seven-operator
contribution ablation, router benefit, scientific superiority, or any
production authorization.  Nothing in this module may be cited as a scientific
gate result.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Final
from uuid import UUID, uuid4

from cpswm.contracts import (
    ActionOutcomeLikelihoodModel,
    DecisionContextBinding,
    DecisionSurface,
    DetectionFailureReason,
    EntityRef,
    EntityType,
    ExecutionFeedbackRecord,
    MapConsistencyRevisions,
    ObservationActionCandidate,
    ObservationActionType,
    ObservationOpportunityRecord,
    ObservationOutcome,
    RobotActionOutcome,
    RobotActionType,
    SourceType,
    TargetPresenceBeliefRef,
)
from cpswm.contracts.base import ValidTimeInterval
from cpswm.contracts.decision_context import DecisionContext
from cpswm.system.continual.project_one_feedback import FeedbackInterpretation
from cpswm.system.continual.project_one_regime_loop import (
    PrototypeLoopConfig,
    PrototypeStatisticOperation,
)
from cpswm.system.evaluation_operations.structure_two_action_death_test import (
    ActionDayObservation,
    StructureTwoActionScenarioGenerator,
    VisibleActionCase,
)
from cpswm.system.prototype_spine import ActionReadoutConfig, PrototypeTransition
from cpswm.system.reproducibility import content_sha256, content_uuid
from cpswm.system.structure_two_adaptive_runtime import (
    AdaptiveAuthorizationPolicy,
    AdaptiveCIAVRuntimeInput,
    AdaptiveExecutionContext,
    AdaptiveRouterFeatures,
    AdaptiveStepResult,
)
from cpswm.system.structure_two_execution import (
    STRUCTURE_TWO_OPERATOR_ORDER,
    StructureTwoExecutionTrace,
    TraceAbortAck,
    TraceCommitAck,
    seal_trace_abort_ack,
    seal_trace_commit_ack,
    verify_execution_trace,
)
from cpswm.system.structure_two_production_system import StructureTwoProductionSystem
from cpswm.world_model.grounded_search import (
    RealizedCIAVObservation,
    VerificationCause,
    verification_cause_hypothesis_id,
)

PROBE_ID: Final = "structure-two-backbone-wiring-probe@0.1"
STATUS: Final = "D0_MECHANISM_PROBE_ONLY"
CLAIM_BOUNDARY: Final = (
    "Mechanism-level wiring probe for the Structure-Two backbone. It establishes recorded "
    "operator invocations, real upstream-to-downstream propagation, and state/action "
    "consequences for the covered scenarios only. It does not establish Task 9 four-coupling "
    "results, seven-operator contribution ablation, router benefit, recovery equivalence, "
    "external validity, or any scientific gate pass."
)


class EvidenceClass(StrEnum):
    """The five evidence classes this audit keeps strictly separate."""

    SAME_PRODUCTION_RUNTIME = "same_production_runtime"
    ALGORITHMIC_IMPLEMENTATION_EQUIVALENCE = "algorithmic_implementation_equivalence"
    STATE_HANDOFF_CORRECT = "state_handoff_correct"
    ACTION_AFFECTED = "action_affected"
    LONG_TERM_UTILITY = "long_term_utility"


class EvidenceVerdict(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    NOT_COVERED = "not_covered"


class CIAVOutcomeKind(StrEnum):
    """The three CIAV realizations the production closure distinguishes."""

    DETECTED_SAME_LOCATION = "detected_same_location"
    DETECTED_DIFFERENT_LOCATION = "detected_different_location"
    NOT_DETECTED = "not_detected"


class ProbeTraceSink:
    """Retains the committed or aborted trace for assertion."""

    def __init__(self) -> None:
        self.trace: StructureTwoExecutionTrace | None = None
        self.aborted: StructureTwoExecutionTrace | None = None
        self.abort_reason: str | None = None

    def commit(self, trace: StructureTwoExecutionTrace, /) -> TraceCommitAck:
        verify_execution_trace(trace)
        self.trace = trace
        return seal_trace_commit_ack(trace)

    def abort(self, trace: StructureTwoExecutionTrace, /, *, reason: str) -> TraceAbortAck:
        self.trace = None
        self.aborted = trace
        self.abort_reason = reason
        return seal_trace_abort_ack(trace, reason=reason)


class FailingTraceSink(ProbeTraceSink):
    """Sink that fails on commit so rollback behaviour can be observed."""

    def commit(self, trace: StructureTwoExecutionTrace, /) -> TraceCommitAck:
        self.trace = trace
        raise RuntimeError("probe trace sink refused the commit")


@dataclass(frozen=True, slots=True)
class OperatorCallRow:
    """One receipted operator disposition, flattened for assertions."""

    sequence: int
    phase: str
    operator: str
    status: str
    mode: str
    binding_kind: str | None
    callable_symbol: str | None
    implementation_symbol: str | None
    operator_instance_id: str | None
    consumed_producers: tuple[str, ...]
    input_payload_sha256: str
    output_payload_sha256: str


def trace_rows(trace: StructureTwoExecutionTrace) -> tuple[OperatorCallRow, ...]:
    """Flatten a committed trace, resolving consumed output ids to producers."""

    producer_by_output: dict[str, str] = {}
    rows: list[OperatorCallRow] = []
    for receipt in trace.receipts:
        consumed = tuple(
            producer_by_output[output_id] for output_id in receipt.consumed_output_ids
        )
        rows.append(
            OperatorCallRow(
                sequence=receipt.sequence,
                phase=receipt.phase,
                operator=receipt.operator,
                status=receipt.status,
                mode=receipt.mode,
                binding_kind=receipt.binding_kind,
                callable_symbol=receipt.callable_symbol,
                implementation_symbol=receipt.implementation_symbol,
                operator_instance_id=receipt.operator_instance_id,
                consumed_producers=consumed,
                input_payload_sha256=receipt.input_payload_sha256,
                output_payload_sha256=receipt.output_payload_sha256,
            )
        )
        producer_by_output[receipt.output_id] = f"{receipt.phase}:{receipt.operator}"
    return tuple(rows)


def receipt_output_sha256_by_operator(
    trace: StructureTwoExecutionTrace,
    *,
    phase: str = "selected_path",
) -> dict[str, str]:
    """Output payload hash per operator for one trace phase."""

    return {
        row.operator: row.output_payload_sha256
        for row in trace_rows(trace)
        if row.phase == phase
    }


def _verification_outcome_likelihoods() -> dict[str, dict[str, float]]:
    hypotheses = tuple(verification_cause_hypothesis_id(cause) for cause in VerificationCause)
    return {
        cause.value: {
            hypothesis: float(hypothesis == verification_cause_hypothesis_id(cause))
            for hypothesis in hypotheses
        }
        for cause in VerificationCause
    }


@dataclass(slots=True)
class BackboneWiringProbe:
    """A single production runtime driven over one deterministic household case."""

    case: VisibleActionCase
    system: StructureTwoProductionSystem
    step_index: int = 0
    router_feature_overrides: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def build(
        cls,
        *,
        seed: int = 7,
        include_open_world_unknown_events: bool = False,
        unknown_event_days: tuple[int, ...] = (1,),
        duration_days: int = 32,
        observation_coverage: float = 1.0,
        action_readout: ActionReadoutConfig | None = None,
        loop_config: PrototypeLoopConfig | None = None,
    ) -> BackboneWiringProbe:
        generator = StructureTwoActionScenarioGenerator(
            duration_days=duration_days,
            observation_coverage=observation_coverage,
            include_open_world_unknown_events=include_open_world_unknown_events,
            unknown_event_days=unknown_event_days,
        )
        case = generator.generate(seed).visible
        policy = AdaptiveAuthorizationPolicy(
            policy_id=f"{PROBE_ID}:local-policy",
            memory_transition_authorized=True,
            privacy_policy_satisfied=True,
            safety_context_authorized=True,
        )
        system = StructureTwoProductionSystem(
            owner_key=case.owner_actor,
            object_instance_id=case.object_instance_id,
            locations=case.locations,
            authorization_scope_id=content_uuid(PROBE_ID, {"seed": seed, "kind": "scope"}),
            action_readout=action_readout,
            loop_config=loop_config,
            adaptive_authorization_policy=policy,
        )
        return cls(case=case, system=system)

    # ------------------------------------------------------------------
    # scenario inputs
    # ------------------------------------------------------------------

    def observed_days(self) -> tuple[ActionDayObservation, ...]:
        return tuple(
            day for day in self.case.days if day.before is not None and day.after is not None
        )

    def transition_for(
        self,
        observation: ActionDayObservation,
        *,
        actor_prior: Mapping[str, float] | None = None,
        evidence_filter: Sequence[str] = ("actor", "mechanism", "role"),
        context_key: str = "weekday|home",
        unresolved_probability: float = 0.0,
        p_visible_given_state: float = 0.9,
        p_detect_given_visible: float = 0.9,
    ) -> PrototypeTransition:
        assert observation.before is not None
        assert observation.after is not None
        available = {
            "actor": observation.actor_evidence,
            "mechanism": observation.mechanism_evidence,
            "role": observation.role_evidence,
        }
        evidence = tuple(
            available[name] for name in evidence_filter if available.get(name) is not None
        )
        prior = dict(
            actor_prior
            or {
                self.case.owner_actor: 0.4,
                self.case.guest_actor: 0.3,
                "unknown_actor": 0.3,
            }
        )
        return PrototypeTransition(
            opportunity=self._opportunity(
                observation,
                p_visible_given_state=p_visible_given_state,
                p_detect_given_visible=p_detect_given_visible,
            ),
            before=observation.before,
            after=observation.after,
            actor_prior=prior,
            evidence=evidence,  # type: ignore[arg-type]
            context_key=context_key,
            context_value=float(observation.day),
            unresolved_probability=unresolved_probability,
        )

    def _opportunity(
        self,
        observation: ActionDayObservation,
        *,
        p_visible_given_state: float = 0.9,
        p_detect_given_visible: float = 0.9,
    ) -> ObservationOpportunityRecord:
        assert observation.after is not None
        assert observation.after.detection_time is not None
        return ObservationOpportunityRecord(
            metadata=observation.after.metadata.model_copy(
                update={
                    "record_id": observation.after.observation_opportunity_id,
                    "schema_name": "cpswm.ObservationOpportunityRecord",
                }
            ),
            observation_action_id=content_uuid(
                PROBE_ID, {"day": observation.day, "kind": "opportunity"}
            ),
            opportunity_time=observation.after.detection_time,
            selected=True,
            selection_probability=0.8,
            p_visible_given_state=p_visible_given_state,
            p_detect_given_visible=p_detect_given_visible,
            likelihood_model_id=f"{PROBE_ID}:likelihood",
        )

    def ciav_input(
        self,
        transition: PrototypeTransition,
        *,
        outcome: CIAVOutcomeKind = CIAVOutcomeKind.DETECTED_DIFFERENT_LOCATION,
        owner_likelihood: float = 0.8,
        realized_cause: VerificationCause = VerificationCause.OBSERVATION,
        privacy_cost: float = 0.0,
        privacy_budget: float = 1.0,
    ) -> AdaptiveCIAVRuntimeInput:
        outcome_likelihoods = _verification_outcome_likelihoods()
        action = ObservationActionCandidate(
            action_type=ObservationActionType.MICRO_VERIFY,
            label=f"{PROBE_ID} cause probe",
            observation_likelihood_model_id=f"{PROBE_ID}:ciav",
            calibration_domain=f"{PROBE_ID}-d0",
            outcome_likelihoods=outcome_likelihoods,
            motion_cost=0.0,
            time_cost=0.0,
            interruption_cost=0.0,
            privacy_cost=privacy_cost,
            safety_cost=0.0,
        )
        detected_location = transition.after.detected_location_id
        detection_time = transition.after.detection_time
        if detected_location is None or detection_time is None:
            raise ValueError("probe CIAV input requires a detected after-observation")
        if outcome is CIAVOutcomeKind.DETECTED_SAME_LOCATION:
            expected = detected_location
        else:
            expected = next(
                location for location in self.case.locations if location != detected_location
            )
        negative = outcome is CIAVOutcomeKind.NOT_DETECTED
        detection_outcome = (
            ObservationOutcome.NOT_OBSERVED if negative else ObservationOutcome.DETECTED
        )
        failure_reason = (
            DetectionFailureReason.OCCLUDED if negative else DetectionFailureReason.NOT_APPLICABLE
        )

        def realize(_opportunity: ObservationOpportunityRecord) -> RealizedCIAVObservation:
            return RealizedCIAVObservation(
                outcome_label=realized_cause.value,
                likelihood_model_id=action.observation_likelihood_model_id,
                detection_outcome=detection_outcome,
                failure_reason=failure_reason,
            )

        guest = self.case.guest_actor
        owner = self.case.owner_actor
        remainder = max(0.0, 1.0 - owner_likelihood) / 2.0
        return AdaptiveCIAVRuntimeInput(
            actions=(action,),
            consolidation_decision_utilities=self._utilities(),
            terminal_decision_utilities=self._utilities(),
            privacy_budget=privacy_budget,
            opportunity_time=detection_time + timedelta(minutes=1),
            actor_likelihoods_by_outcome={
                label: {owner: owner_likelihood, guest: remainder, "unknown_actor": remainder}
                for label in outcome_likelihoods
            },
            expected_detected_location_id=expected,
            selection_probability=1.0,
            p_visible_given_state=1.0,
            p_detect_given_visible=1.0,
            realizer=realize,
        )

    def _utilities(self) -> dict[UUID, dict[UUID, float]]:
        hypotheses = tuple(verification_cause_hypothesis_id(cause) for cause in VerificationCause)
        return {
            hypothesis: {other: float(other == hypothesis) for other in hypotheses}
            for hypothesis in hypotheses
        }

    # ------------------------------------------------------------------
    # router features
    # ------------------------------------------------------------------

    def router_features(self, **overrides: Any) -> AdaptiveRouterFeatures:
        state = self.system.adaptive_router_state_sha256()
        policy_sha256 = self.system.adaptive_authorization_policy_sha256
        pending = self.system.pending_adaptive_debts()
        oldest_age = (
            max(self.step_index - min(item.created_step for item in pending), 0) if pending else 0
        )
        values: dict[str, Any] = {
            "source_state_sha256": state,
            "authorization_policy_sha256": policy_sha256,
            "observation_opportunity_coverage": 0.9,
            "evidence_conflict_score": 0.05,
            "provenance_dependence_score": 0.05,
            "actor_ambiguity": 0.05,
            "instance_ambiguity": 0.05,
            "unknown_mass": 0.05,
            "action_margin": 0.8,
            "pending_long_term_commit": False,
            "regime_hazard": 0.05,
            "outstanding_debt_count": len(pending),
            "oldest_debt_age": oldest_age,
            "maximum_debt_flip_bound": 0.05,
            "state_staleness": 0,
            "memory_transition_authorized": True,
            "privacy_policy_satisfied": True,
            "safety_context_authorized": True,
            "feature_extraction_cost_units": 0.1,
            "feature_source_sha256s": (state, policy_sha256),
        }
        values.update(self.router_feature_overrides)
        values.update(overrides)
        return AdaptiveRouterFeatures(**values)

    # ------------------------------------------------------------------
    # production entrypoints
    # ------------------------------------------------------------------

    def run_direct_p5(
        self,
        transition: PrototypeTransition,
        *,
        ciav_input: AdaptiveCIAVRuntimeInput | None = None,
        sink: ProbeTraceSink | None = None,
        debt_expiry_steps: int = 20,
        features: AdaptiveRouterFeatures | None = None,
    ) -> tuple[AdaptiveStepResult, ProbeTraceSink]:
        sink = sink or ProbeTraceSink()
        context = AdaptiveExecutionContext(
            router_features=features or self.router_features(),
            step_index=self.step_index,
            debt_expiry_steps=debt_expiry_steps,
            ciav_input=ciav_input or self.ciav_input(transition),
        )
        result = self.system.process_evaluation_direct_p5_transition(
            transition, context=context, trace_sink=sink
        )
        self.step_index += 1
        return result, sink

    def run_adaptive(
        self,
        transition: PrototypeTransition,
        *,
        ciav_input: AdaptiveCIAVRuntimeInput | None = None,
        sink: ProbeTraceSink | None = None,
        debt_expiry_steps: int = 20,
        features: AdaptiveRouterFeatures | None = None,
    ) -> tuple[AdaptiveStepResult, ProbeTraceSink]:
        sink = sink or ProbeTraceSink()
        context = AdaptiveExecutionContext(
            router_features=features or self.router_features(),
            step_index=self.step_index,
            debt_expiry_steps=debt_expiry_steps,
            ciav_input=ciav_input or self.ciav_input(transition),
        )
        result = self.system.process_adaptive_transition(
            transition, context=context, trace_sink=sink
        )
        self.step_index += 1
        return result, sink

    def replay_debt(
        self,
        debt_id: UUID,
        *,
        ciav_input: AdaptiveCIAVRuntimeInput,
        sink: ProbeTraceSink | None = None,
    ) -> tuple[AdaptiveStepResult, ProbeTraceSink]:
        sink = sink or ProbeTraceSink()
        result = self.system.replay_adaptive_debt(
            debt_id,
            step_index=self.step_index,
            ciav_input=ciav_input,
            trace_sink=sink,
        )
        self.step_index += 1
        return result, sink

    # ------------------------------------------------------------------
    # observable state
    # ------------------------------------------------------------------

    def observable_state_sha256(self) -> str:
        return self.system.core._execution_observable_state_sha256()

    def action_distribution(self) -> dict[UUID, float]:
        return dict(self.system.action_location_distribution(self.system.current_snapshot))

    def action_distribution_sha256(self) -> str:
        return content_sha256(
            sorted((str(key), value) for key, value in self.action_distribution().items())
        )

    def committed_revision_ids(self) -> tuple[UUID, ...]:
        return tuple(self.system.core._committed_events)

    def quarantined_revision_ids(self) -> tuple[UUID, ...]:
        return tuple(event.revision_id for event in self.system.core._quarantined_events)


class CalibratedRetractionPolicy:
    """A caller-supplied calibrated feedback policy.

    ``DefaultPrototypeFeedbackPolicy`` deliberately quarantines negative evidence and
    documents that "a caller may plug in a calibrated policy that emits RETRACT or
    CORRECT".  ``CorePrototypeSpine.process_execution_feedback`` takes that policy as
    a named argument, so this class exercises the documented production seam rather
    than bypassing it.  It owns no statistics and no write authority: it only maps a
    projected presence delta onto one of the three frozen statistic operations.
    """

    def __init__(
        self,
        *,
        retraction_delta: float = -0.2,
        corrected_location_id: UUID | None = None,
        corrected_owner_mass: float | None = None,
    ) -> None:
        self.retraction_delta = retraction_delta
        self.corrected_location_id = corrected_location_id
        self.corrected_owner_mass = corrected_owner_mass

    def interpret(self, *, feedback, projected):  # type: ignore[no-untyped-def]
        raw = feedback.diagnostics.get("source_revision_id")
        target = UUID(raw) if isinstance(raw, str) else None
        update = projected.target_presence_update
        if update is None or target is None:
            return FeedbackInterpretation(
                operation=PrototypeStatisticOperation.QUARANTINE,
                evidence_strength=0.0,
                rationale="probe policy: no citable revision or presence likelihood",
            )
        delta = update.posterior_target_present - update.prior_target_present
        if delta > self.retraction_delta:
            return FeedbackInterpretation(
                operation=PrototypeStatisticOperation.QUARANTINE,
                evidence_strength=abs(delta),
                target_revision_id=target,
                rationale="probe policy: evidence below the calibrated retraction margin",
            )
        if self.corrected_location_id is not None:
            return FeedbackInterpretation(
                operation=PrototypeStatisticOperation.CORRECT,
                evidence_strength=abs(delta),
                target_revision_id=target,
                corrected_location_id=self.corrected_location_id,
                rationale="probe policy: calibrated correction of the cited revision",
            )
        return FeedbackInterpretation(
            operation=PrototypeStatisticOperation.RETRACT,
            evidence_strength=abs(delta),
            target_revision_id=target,
            rationale="probe policy: calibrated retraction of the cited revision",
        )


def build_execution_feedback_bundle(
    probe: BackboneWiringProbe,
    *,
    revision_id: UUID,
    location_id: UUID,
    belief_snapshot_id: UUID,
    when: datetime,
    outcome_distribution: Mapping[RobotActionOutcome, float],
    present_likelihood: Mapping[RobotActionOutcome, float],
    absent_likelihood: Mapping[RobotActionOutcome, float],
    opportunity_id: UUID,
    prior_probability: float = 0.8,
    action_id: UUID | None = None,
    feedback_record_id: UUID | None = None,
    staleness_budget_seconds: float = 300.0,
) -> tuple[ExecutionFeedbackRecord, DecisionContextBinding, ActionOutcomeLikelihoodModel]:
    """Build one formal execution-feedback bundle for the production entrypoint."""

    system = probe.system
    template = probe.case.days[0].after
    assert template is not None
    metadata = template.metadata.model_copy(
        update={
            "record_id": feedback_record_id or uuid4(),
            "schema_name": "cpswm.ExecutionFeedbackRecord",
            "source_type": SourceType.ACTION,
            "recorded_time": when,
        }
    )
    feedback = ExecutionFeedbackRecord(
        metadata=metadata,
        action_id=action_id or uuid4(),
        action_type=RobotActionType.SEARCH,
        target_entity=EntityRef(
            entity_id=probe.case.object_instance_id,
            entity_type=EntityType.OBJECT_INSTANCE,
        ),
        attempted_location_id=location_id,
        valid_time=ValidTimeInterval(start=when, end=when + timedelta(minutes=1)),
        outcome_distribution=dict(outcome_distribution),
        observation_opportunity_id=opportunity_id,
        diagnostics={"source_revision_id": str(revision_id)},
    )
    revisions = MapConsistencyRevisions(
        belief_snapshot_id=belief_snapshot_id,
        projection_id=uuid4(),
        projection_version=1,
        static_map_revision=1,
        dynamic_map_revision=1,
        event_history_revision=1,
        input_watermark=1,
    )
    context = DecisionContext.create(
        decision_id=uuid4(),
        decision_time=when,
        valid_time=ValidTimeInterval(start=when, end=when + timedelta(minutes=5)),
        staleness_budget_seconds=staleness_budget_seconds,
        revisions=revisions,
        target_presence_belief=TargetPresenceBeliefRef(
            object_instance_id=probe.case.object_instance_id,
            location_id=location_id,
            belief_node_id="structure-two-backbone-probe-presence",
            belief_snapshot_id=revisions.belief_snapshot_id,
            node_content_hash="a" * 64,
            prior_probability=prior_probability,
        ),
        authorization_scope_id=system.core.authorization_scope_id,
        habit_regime_model_version=system.core.model_version,
        model_versions=(("prototype", system.core.model_version),),
        code_version="structure-two-backbone-probe",
        rationale="bind late counter-evidence to the exact committed revision",
    )
    binding = DecisionContextBinding(
        metadata=metadata.model_copy(
            update={"record_id": uuid4(), "schema_name": "cpswm.DecisionContextBinding"}
        ),
        surface=DecisionSurface.EXECUTION_FEEDBACK,
        subject_record_id=feedback.metadata.record_id,
        subject_household_id=metadata.household_id,
        subject_session_id=metadata.session_id,
        subject_trace_id=metadata.trace_id,
        decision_context=context,
    )
    likelihood = ActionOutcomeLikelihoodModel(
        action_type=RobotActionType.SEARCH,
        p_outcome_given_target_present=dict(present_likelihood),
        p_outcome_given_target_absent=dict(absent_likelihood),
        calibration_domain="structure-two-backbone-probe-search",
        model_version="structure-two-backbone-probe-search@0.1",
    )
    return feedback, binding, likelihood


NEGATIVE_SEARCH_OUTCOME: Final = {
    RobotActionOutcome.NOT_FOUND: 0.98,
    RobotActionOutcome.UNKNOWN: 0.02,
}
NEGATIVE_PRESENT_LIKELIHOOD: Final = {
    RobotActionOutcome.NOT_FOUND: 0.02,
    RobotActionOutcome.UNKNOWN: 0.98,
}
NEGATIVE_ABSENT_LIKELIHOOD: Final = {
    RobotActionOutcome.NOT_FOUND: 0.98,
    RobotActionOutcome.UNKNOWN: 0.02,
}
POSITIVE_SEARCH_OUTCOME: Final = {
    RobotActionOutcome.SUCCESS: 0.95,
    RobotActionOutcome.UNKNOWN: 0.05,
}
POSITIVE_PRESENT_LIKELIHOOD: Final = {
    RobotActionOutcome.SUCCESS: 0.99,
    RobotActionOutcome.UNKNOWN: 0.01,
}
POSITIVE_ABSENT_LIKELIHOOD: Final = {
    RobotActionOutcome.SUCCESS: 0.01,
    RobotActionOutcome.UNKNOWN: 0.99,
}


@dataclass(frozen=True, slots=True)
class ScenarioOutcome:
    """One scenario row of the mechanism matrix."""

    scenario_id: str
    expected_invariants: tuple[str, ...]
    expected_changes: tuple[str, ...]
    expected_unchanged: tuple[str, ...]
    observed: Mapping[str, Any]
    evidence: Mapping[EvidenceClass, EvidenceVerdict]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "expected_invariants": list(self.expected_invariants),
            "expected_changes": list(self.expected_changes),
            "expected_unchanged": list(self.expected_unchanged),
            "observed": dict(self.observed),
            "evidence": {key.value: value.value for key, value in self.evidence.items()},
        }


def verify_and_flatten(
    sink: ProbeTraceSink,
) -> tuple[StructureTwoExecutionTrace, tuple[OperatorCallRow, ...]]:
    """Verify the committed trace with the frozen verifier and flatten it."""

    trace = sink.trace
    if trace is None:
        raise AssertionError("probe sink did not retain a committed execution trace")
    verify_execution_trace(trace)
    return trace, trace_rows(trace)


def primary_operator_sequence(rows: Sequence[OperatorCallRow]) -> tuple[str, ...]:
    return tuple(row.operator for row in rows if row.phase == "selected_path")


def closure_operator_sequence(rows: Sequence[OperatorCallRow]) -> tuple[str, ...]:
    return tuple(row.operator for row in rows if row.phase == "feedback_closure")


__all__ = [
    "CLAIM_BOUNDARY",
    "NEGATIVE_ABSENT_LIKELIHOOD",
    "NEGATIVE_PRESENT_LIKELIHOOD",
    "NEGATIVE_SEARCH_OUTCOME",
    "POSITIVE_ABSENT_LIKELIHOOD",
    "POSITIVE_PRESENT_LIKELIHOOD",
    "POSITIVE_SEARCH_OUTCOME",
    "PROBE_ID",
    "STATUS",
    "STRUCTURE_TWO_OPERATOR_ORDER",
    "BackboneWiringProbe",
    "CIAVOutcomeKind",
    "CalibratedRetractionPolicy",
    "EvidenceClass",
    "EvidenceVerdict",
    "FailingTraceSink",
    "OperatorCallRow",
    "ProbeTraceSink",
    "ScenarioOutcome",
    "build_execution_feedback_bundle",
    "closure_operator_sequence",
    "primary_operator_sequence",
    "receipt_output_sha256_by_operator",
    "trace_rows",
    "verify_and_flatten",
]
