"""Evaluation-only direct-P5 bring-up with a typed action readout.

This module is deliberately an engineering probe, not the P5 death test.  It
establishes that a debt-free evaluator can run the real production P5 plan
without changing the production router, validate all seven operator calls and
their consumption graph, and pass P5 state through the one shared typed
SEARCH/PUT_BACK decoder.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from datetime import timedelta
from pathlib import Path
from typing import Any, Final
from uuid import UUID

from cpswm.contracts import (
    ObservationActionCandidate,
    ObservationActionType,
    ObservationOpportunityRecord,
    ObservationOutcome,
)
from cpswm.system.evaluation_operations.structure_two_action_death_test import (
    StructureTwoActionScenarioGenerator,
)
from cpswm.system.evaluation_operations.structure_two_action_utility_construct_gate import (
    ConstructActionKind,
    LocationProbability,
    TaskSeparatedActionReadout,
    TypedRouteCAction,
    decode_task_separated_actions,
)
from cpswm.system.prototype_spine import PrototypeTransition
from cpswm.system.reproducibility import content_sha256, content_uuid
from cpswm.system.structure_two_adaptive_runtime import (
    EVALUATION_DIRECT_P5_REASON,
    AdaptiveAuthorizationPolicy,
    AdaptiveCIAVRuntimeInput,
    AdaptiveExecutionContext,
    AdaptivePathSelectionReceipt,
    AdaptiveRouterFeatures,
    select_adaptive_path,
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

SCHEMA_VERSION: Final = "0.1.0"
PROTOCOL_ID: Final = "structure-two-p5-direct-trace-probe@0.1"
STATUS: Final = "D0_ENGINEERING_BRINGUP_ONLY"
DEFAULT_CONFIG: Final = Path(
    "configs/project_two_experiments/structure_two_p5_direct_trace_probe_v0_1.json"
)
DEFAULT_DECISION_RECORD: Final = Path(
    "configs/project_two_experiments/structure_two_p5_first_decision_v0_1.json"
)
DEFAULT_OUTPUT: Final = Path(
    "benchmarks/structure_two/structure_two_p5_direct_trace_probe_v0_1.json"
)
CLAIM_BOUNDARY: Final = (
    "This D0 engineering probe establishes an isolated evaluation-only call into the real "
    "production P5 path, a validated seven-operator invocation and consumption trace, and "
    "one shared typed SEARCH/PUT_BACK decoder call. It does not establish cross-arm CIAV "
    "matching, action benefit, scientific superiority, Task 7/8/9 success, or production "
    "router policy quality."
)
EXPECTED_CIAV_MATCHING_POLICY: Final = {
    "comparison_arms_must_share_registered_action_candidates": True,
    "comparison_arms_must_share_observation_outcome_and_visibility_costs": True,
    "comparison_arms_must_share_privacy_budget": True,
    "single_arm_probe_establishes_cross_arm_matching": False,
}
DECODER_MODULE: Final = Path(
    "src/cpswm/system/evaluation_operations/structure_two_action_utility_construct_gate.py"
)
ADAPTIVE_RUNTIME_MODULE: Final = Path("src/cpswm/system/structure_two_adaptive_runtime.py")
PRODUCTION_SYSTEM_MODULE: Final = Path("src/cpswm/system/structure_two_production_system.py")


class _ProbeTraceSink:
    def __init__(self) -> None:
        self.trace: StructureTwoExecutionTrace | None = None

    def commit(self, trace: StructureTwoExecutionTrace, /) -> TraceCommitAck:
        verify_execution_trace(trace)
        self.trace = trace
        return seal_trace_commit_ack(trace)

    def abort(self, trace: StructureTwoExecutionTrace, /, *, reason: str) -> TraceAbortAck:
        self.trace = None
        return seal_trace_abort_ack(trace, reason=reason)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utilities() -> dict[UUID, dict[UUID, float]]:
    hypotheses = tuple(verification_cause_hypothesis_id(cause) for cause in VerificationCause)
    return {
        decision: {hypothesis: 1.0 if decision == hypothesis else 0.0 for hypothesis in hypotheses}
        for decision in hypotheses
    }


def _build_ciav_input(transition: PrototypeTransition) -> AdaptiveCIAVRuntimeInput:
    hypotheses = tuple(verification_cause_hypothesis_id(cause) for cause in VerificationCause)
    outcome_likelihoods = {
        cause.value: {
            hypothesis: float(hypothesis == verification_cause_hypothesis_id(cause))
            for hypothesis in hypotheses
        }
        for cause in VerificationCause
    }
    action = ObservationActionCandidate(
        action_type=ObservationActionType.MICRO_VERIFY,
        label="evaluation-only direct P5 cause probe",
        observation_likelihood_model_id="structure-two-p5-direct-probe@0.1",
        calibration_domain="structure-two-p5-direct-probe-d0",
        outcome_likelihoods=outcome_likelihoods,
        motion_cost=0.0,
        time_cost=0.0,
        interruption_cost=0.0,
        privacy_cost=0.0,
        safety_cost=0.0,
    )
    realized_outcome = VerificationCause.OBSERVATION.value

    def realize(_opportunity: ObservationOpportunityRecord) -> RealizedCIAVObservation:
        return RealizedCIAVObservation(
            outcome_label=realized_outcome,
            likelihood_model_id=action.observation_likelihood_model_id,
            detection_outcome=ObservationOutcome.DETECTED,
        )

    detected = transition.after.detected_location_id
    detection_time = transition.after.detection_time
    if detected is None or detection_time is None:
        raise ValueError("direct P5 probe requires a detected after-observation")
    expected = next(
        location
        for location in (
            transition.before.detected_location_id,
            transition.after.detected_location_id,
        )
        if location is not None and location != detected
    )
    return AdaptiveCIAVRuntimeInput(
        actions=(action,),
        consolidation_decision_utilities=_utilities(),
        terminal_decision_utilities=_utilities(),
        privacy_budget=1.0,
        opportunity_time=detection_time + timedelta(minutes=1),
        actor_likelihoods_by_outcome={
            outcome: {"owner": 0.8, "guest": 0.2, "unknown_actor": 0.2}
            for outcome in outcome_likelihoods
        },
        expected_detected_location_id=expected,
        selection_probability=1.0,
        p_visible_given_state=1.0,
        p_detect_given_visible=1.0,
        realizer=realize,
    )


def _build_probe(
    seed: int,
) -> tuple[
    StructureTwoProductionSystem,
    PrototypeTransition,
    tuple[UUID, ...],
    UUID,
]:
    case = StructureTwoActionScenarioGenerator().generate(seed).visible
    observation = next(
        item for item in case.days if item.before is not None and item.after is not None
    )
    assert observation.before is not None
    assert observation.after is not None
    assert observation.after.detection_time is not None
    opportunity = ObservationOpportunityRecord(
        metadata=observation.after.metadata.model_copy(
            update={
                "record_id": observation.after.observation_opportunity_id,
                "schema_name": "cpswm.ObservationOpportunityRecord",
            }
        ),
        observation_action_id=content_uuid(PROTOCOL_ID, {"seed": seed, "kind": "opportunity"}),
        opportunity_time=observation.after.detection_time,
        selected=True,
        selection_probability=0.8,
        p_visible_given_state=0.9,
        p_detect_given_visible=0.9,
        likelihood_model_id="structure-two-p5-direct-probe@0.1",
    )
    evidence = tuple(
        item
        for item in (
            observation.actor_evidence,
            observation.mechanism_evidence,
            observation.role_evidence,
        )
        if item is not None
    )
    policy = AdaptiveAuthorizationPolicy(
        policy_id="structure-two-p5-direct-probe-local-policy",
        memory_transition_authorized=True,
        privacy_policy_satisfied=True,
        safety_context_authorized=True,
    )
    system = StructureTwoProductionSystem(
        owner_key=case.owner_actor,
        object_instance_id=case.object_instance_id,
        locations=case.locations,
        authorization_scope_id=content_uuid(
            PROTOCOL_ID, {"seed": seed, "kind": "authorization-scope"}
        ),
        adaptive_authorization_policy=policy,
    )
    transition = PrototypeTransition(
        opportunity=opportunity,
        before=observation.before,
        after=observation.after,
        actor_prior={case.owner_actor: 0.4, case.guest_actor: 0.3, "unknown_actor": 0.3},
        evidence=evidence,
        context_key="weekday|home",
        context_value=float(observation.day),
    )
    return system, transition, tuple(case.locations), case.object_instance_id


def _router_features(system: StructureTwoProductionSystem) -> AdaptiveRouterFeatures:
    state = system.adaptive_router_state_sha256()
    policy_sha256 = system.adaptive_authorization_policy_sha256
    return AdaptiveRouterFeatures(
        source_state_sha256=state,
        authorization_policy_sha256=policy_sha256,
        observation_opportunity_coverage=0.9,
        evidence_conflict_score=0.05,
        provenance_dependence_score=0.05,
        actor_ambiguity=0.05,
        instance_ambiguity=0.05,
        unknown_mass=0.05,
        action_margin=0.8,
        pending_long_term_commit=False,
        regime_hazard=0.05,
        outstanding_debt_count=0,
        oldest_debt_age=0,
        maximum_debt_flip_bound=0.05,
        state_staleness=0,
        memory_transition_authorized=True,
        privacy_policy_satisfied=True,
        safety_context_authorized=True,
        feature_extraction_cost_units=0.1,
        feature_source_sha256s=(state, policy_sha256),
    )


def _trace_rows(trace: StructureTwoExecutionTrace) -> list[dict[str, Any]]:
    producer_by_output: dict[str, str] = {}
    rows: list[dict[str, Any]] = []
    for receipt in trace.receipts:
        consumed = [producer_by_output[output_id] for output_id in receipt.consumed_output_ids]
        label = f"{receipt.sequence}:{receipt.phase}:{receipt.operator}"
        rows.append(
            {
                "sequence": receipt.sequence,
                "phase": receipt.phase,
                "operator": receipt.operator,
                "status": receipt.status,
                "callable_symbol": receipt.callable_symbol,
                "operator_instance_id": receipt.operator_instance_id,
                "invocation_id": receipt.invocation_id,
                "consumes": consumed,
                "input_payload_sha256": receipt.input_payload_sha256,
                "output_payload_sha256": receipt.output_payload_sha256,
            }
        )
        producer_by_output[receipt.output_id] = label
    return rows


def _unsigned(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {key: copy.deepcopy(value) for key, value in payload.items() if key != "content_sha256"}


def _semantic_projection(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "normal_router_path": payload["normal_router_selection"]["selected_path_id"],
        "direct_path": payload["direct_p5_selection"]["selected_path_id"],
        "direct_reason": payload["direct_p5_selection"]["reasons"],
        "trace_rows": [
            {
                "sequence": row["sequence"],
                "phase": row["phase"],
                "operator": row["operator"],
                "status": row["status"],
                "callable_symbol": row["callable_symbol"],
                "consumes": row["consumes"],
            }
            for row in payload["operator_call_consumption_trace"]
        ],
        "typed_readout": {
            "search_distribution": payload["typed_readout"]["search_distribution"],
            "put_back_distribution": payload["typed_readout"]["put_back_distribution"],
            "search_plan": [
                (row["kind"], row["location_id"]) for row in payload["typed_readout"]["search_plan"]
            ],
            "put_back": (
                payload["typed_readout"]["selected_put_back_action"]["kind"],
                payload["typed_readout"]["selected_put_back_action"]["location_id"],
            ),
        },
        "gate_checks": payload["gate_checks"],
    }


def run_p5_direct_trace_probe(*, repository_root: Path) -> dict[str, Any]:
    root = repository_root.resolve()
    config_path = root / DEFAULT_CONFIG
    config = json.loads(config_path.read_text(encoding="utf-8"))
    expected_config_keys = {
        "schema_version",
        "protocol_id",
        "status",
        "seed",
        "direct_path_id",
        "required_typed_actions",
        "require_full_feedback_closure",
        "normal_router_must_remain_p0_for_probe_features",
        "ciav_matching_policy",
        "claim_boundary",
    }
    if (
        set(config) != expected_config_keys
        or config.get("schema_version") != SCHEMA_VERSION
        or config.get("protocol_id") != PROTOCOL_ID
        or config.get("status") != STATUS
        or config.get("direct_path_id") != "P5_FULL_EAGER"
        or config.get("required_typed_actions") != ["SEARCH", "PUT_BACK"]
        or config.get("require_full_feedback_closure") is not True
        or config.get("normal_router_must_remain_p0_for_probe_features") is not True
        or config.get("ciav_matching_policy") != EXPECTED_CIAV_MATCHING_POLICY
        or config.get("claim_boundary") != CLAIM_BOUNDARY
    ):
        raise ValueError("direct P5 trace probe configuration identity drifted")
    seed = config.get("seed")
    if type(seed) is not int or seed < 0:
        raise ValueError("direct P5 trace probe seed must be a non-negative integer")

    system, transition, locations, object_instance_id = _build_probe(seed)
    features = _router_features(system)
    ciav_input = _build_ciav_input(transition)
    normal_selection = select_adaptive_path(
        features,
        ciav_runtime_input_available=True,
        debt_expiry_steps=20,
    )
    if normal_selection.selected_path_id != "P0_SAFE_DEFERRED":
        raise RuntimeError("probe features no longer isolate direct P5 from production routing")
    context = AdaptiveExecutionContext(
        router_features=features,
        step_index=0,
        debt_expiry_steps=20,
        ciav_input=ciav_input,
    )
    sink = _ProbeTraceSink()
    result = system.process_evaluation_direct_p5_transition(
        transition,
        context=context,
        trace_sink=sink,
    )
    trace = sink.trace
    if trace is None:
        raise RuntimeError("direct P5 trace sink did not retain the committed trace")
    verify_execution_trace(trace)

    detected = transition.after.detected_location_id
    if detected is None:
        raise ValueError("probe transition lacks a detected location")
    search_distribution = {location: float(location == detected) for location in locations}
    put_back_distribution = system.action_location_distribution(system.current_snapshot)
    run_execution_id = content_uuid(PROTOCOL_ID, {"seed": seed, "kind": "typed-readout"})
    readout = decode_task_separated_actions(
        target_object_id=object_instance_id,
        step_index=0,
        run_execution_id=run_execution_id,
        source_update_id=transition.after.metadata.record_id,
        visible_observation=transition.after.model_dump(mode="json"),
        belief_state_sha256=system.adaptive_router_state_sha256(),
        search_distribution=search_distribution,
        put_back_distribution=put_back_distribution,
    )
    rows = _trace_rows(trace)
    checks = {
        "normal_router_unchanged_and_selects_p0": normal_selection.selected_path_id
        == "P0_SAFE_DEFERRED",
        "direct_receipt_is_explicitly_evaluation_only": result.path_selection.reasons
        == (EVALUATION_DIRECT_P5_REASON,),
        "real_production_p5_plan_executed": trace.plan.plan_id == "P5_FULL_EAGER",
        "all_seven_primary_operators_invoked": trace.all_seven_operators_invoked,
        "ciav_invoked": trace.ciav_invoked,
        "full_feedback_closure_executed": trace.feedback_closure_kind == "full_transition",
        "primary_operator_order_exact": tuple(row["operator"] for row in rows[:7])
        == STRUCTURE_TWO_OPERATOR_ORDER,
        "shared_decoder_emitted_search": all(
            action.kind is ConstructActionKind.SEARCH for action in readout.search_plan
        ),
        "shared_decoder_emitted_put_back": readout.put_back_action.kind
        is ConstructActionKind.PUT_BACK,
    }
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "protocol_id": PROTOCOL_ID,
        "status": STATUS,
        "source_binding": {
            "configuration_path": DEFAULT_CONFIG.as_posix(),
            "configuration_sha256": _file_sha256(config_path),
            "decision_record_path": DEFAULT_DECISION_RECORD.as_posix(),
            "decision_record_sha256": _file_sha256(root / DEFAULT_DECISION_RECORD),
            "probe_module_sha256": _file_sha256(Path(__file__).resolve()),
            "decoder_module_path": DECODER_MODULE.as_posix(),
            "decoder_module_sha256": _file_sha256(root / DECODER_MODULE),
            "adaptive_runtime_module_path": ADAPTIVE_RUNTIME_MODULE.as_posix(),
            "adaptive_runtime_module_sha256": _file_sha256(root / ADAPTIVE_RUNTIME_MODULE),
            "production_system_module_path": PRODUCTION_SYSTEM_MODULE.as_posix(),
            "production_system_module_sha256": _file_sha256(root / PRODUCTION_SYSTEM_MODULE),
        },
        "normal_router_selection": normal_selection.model_dump(mode="json"),
        "direct_p5_selection": result.path_selection.model_dump(mode="json"),
        "ciav_input_sha256": ciav_input.content_sha256,
        "ciav_matching_status": {
            "policy_frozen": config["ciav_matching_policy"],
            "cross_arm_matching_established": False,
            "reason": "single-arm bring-up cannot prove cross-arm information/cost equality",
        },
        "execution_trace": trace.model_dump(mode="json"),
        "operator_call_consumption_trace": rows,
        "typed_decoder": {
            "callable_symbol": (
                "cpswm.system.evaluation_operations."
                "structure_two_action_utility_construct_gate.decode_task_separated_actions"
            ),
            "shared_across_future_comparison_arms": True,
        },
        "typed_readout": readout.to_dict(),
        "gate_checks": checks,
        "engineering_bringup_passed": all(checks.values()),
        "cross_arm_ciav_matching_established": False,
        "action_benefit_established": False,
        "scientific_superiority_established": False,
        "task_7_8_9_passed": False,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    return {**payload, "content_sha256": content_sha256(payload)}


def verify_p5_direct_trace_probe(
    payload: Mapping[str, Any],
    *,
    repository_root: Path,
    fresh_recompute: bool = True,
) -> None:
    required = {
        "schema_version",
        "protocol_id",
        "status",
        "source_binding",
        "normal_router_selection",
        "direct_p5_selection",
        "ciav_input_sha256",
        "ciav_matching_status",
        "execution_trace",
        "operator_call_consumption_trace",
        "typed_decoder",
        "typed_readout",
        "gate_checks",
        "engineering_bringup_passed",
        "cross_arm_ciav_matching_established",
        "action_benefit_established",
        "scientific_superiority_established",
        "task_7_8_9_passed",
        "claim_boundary",
        "content_sha256",
    }
    if set(payload) != required:
        raise ValueError("direct P5 trace probe artifact schema drifted")
    if (
        payload["schema_version"] != SCHEMA_VERSION
        or payload["protocol_id"] != PROTOCOL_ID
        or payload["status"] != STATUS
        or payload["claim_boundary"] != CLAIM_BOUNDARY
    ):
        raise ValueError("direct P5 trace probe artifact identity drifted")
    for field in (
        "cross_arm_ciav_matching_established",
        "action_benefit_established",
        "scientific_superiority_established",
        "task_7_8_9_passed",
    ):
        if payload[field] is not False:
            raise ValueError("direct P5 bring-up promoted an unauthorized claim")
    if payload["content_sha256"] != content_sha256(_unsigned(payload)):
        raise ValueError("direct P5 trace probe artifact hash mismatch")

    root = repository_root.resolve()
    source = payload["source_binding"]
    expected_source = {
        "configuration_path": DEFAULT_CONFIG.as_posix(),
        "configuration_sha256": _file_sha256(root / DEFAULT_CONFIG),
        "decision_record_path": DEFAULT_DECISION_RECORD.as_posix(),
        "decision_record_sha256": _file_sha256(root / DEFAULT_DECISION_RECORD),
        "probe_module_sha256": _file_sha256(Path(__file__).resolve()),
        "decoder_module_path": DECODER_MODULE.as_posix(),
        "decoder_module_sha256": _file_sha256(root / DECODER_MODULE),
        "adaptive_runtime_module_path": ADAPTIVE_RUNTIME_MODULE.as_posix(),
        "adaptive_runtime_module_sha256": _file_sha256(root / ADAPTIVE_RUNTIME_MODULE),
        "production_system_module_path": PRODUCTION_SYSTEM_MODULE.as_posix(),
        "production_system_module_sha256": _file_sha256(root / PRODUCTION_SYSTEM_MODULE),
    }
    if source != expected_source:
        raise ValueError("direct P5 trace probe source binding mismatch")
    normal = AdaptivePathSelectionReceipt.model_validate(payload["normal_router_selection"])
    direct = AdaptivePathSelectionReceipt.model_validate(payload["direct_p5_selection"])
    trace = StructureTwoExecutionTrace.model_validate(payload["execution_trace"])
    verify_execution_trace(trace)
    if normal.selected_path_id != "P0_SAFE_DEFERRED":
        raise ValueError("probe no longer demonstrates unchanged normal routing")
    if direct.selected_path_id != "P5_FULL_EAGER" or direct.reasons != (
        EVALUATION_DIRECT_P5_REASON,
    ):
        raise ValueError("probe lacks an evaluation-only direct-P5 receipt")
    if trace.adaptive_path_selection_receipt_sha256 != direct.receipt_sha256:
        raise ValueError("execution trace is not bound to the direct-P5 receipt")
    if trace.adaptive_ciav_input_sha256 != payload["ciav_input_sha256"]:
        raise ValueError("execution trace is not bound to the declared CIAV input")

    rows = payload["operator_call_consumption_trace"]
    if not isinstance(rows, list) or rows != _trace_rows(trace):
        raise ValueError("operator call/consumption projection differs from the sealed trace")
    typed = payload["typed_readout"]
    search_actions = [TypedRouteCAction.from_mapping(row) for row in typed["search_plan"]]
    put_back = TypedRouteCAction.from_mapping(typed["selected_put_back_action"])
    if (
        not search_actions
        or any(action.kind is not ConstructActionKind.SEARCH for action in search_actions)
        or put_back.kind is not ConstructActionKind.PUT_BACK
        or any(
            action.information_set_sha256 != put_back.information_set_sha256
            for action in search_actions
        )
    ):
        raise ValueError("shared typed decoder output is inconsistent")
    parsed_readout = TaskSeparatedActionReadout(
        step_index=typed["step_index"],
        run_execution_id=UUID(typed["run_execution_id"]),
        source_update_id=UUID(typed["source_update_id"]),
        observation_commitment_sha256=typed["observation_commitment_sha256"],
        belief_state_sha256=typed["belief_state_sha256"],
        information_set_sha256=typed["information_set_sha256"],
        search_distribution=tuple(
            LocationProbability(UUID(location), probability)
            for location, probability in typed["search_distribution"].items()
        ),
        put_back_distribution=tuple(
            LocationProbability(UUID(location), probability)
            for location, probability in typed["put_back_distribution"].items()
        ),
        search_plan=tuple(search_actions),
        put_back_action=put_back,
        truth_accessed_before_action_commit=typed["truth_accessed_before_action_commit"],
    )
    if parsed_readout.to_dict() != typed:
        raise ValueError("typed readout is not in canonical shared-decoder form")
    checks = payload["gate_checks"]
    if (
        not isinstance(checks, Mapping)
        or not checks
        or any(value is not True for value in checks.values())
    ):
        raise ValueError("direct P5 trace probe gate checks are not all satisfied")
    if payload["engineering_bringup_passed"] is not True:
        raise ValueError("passing direct P5 trace probe was not marked as passed")
    if fresh_recompute:
        fresh = run_p5_direct_trace_probe(repository_root=root)
        if _semantic_projection(payload) != _semantic_projection(fresh):
            raise ValueError("fresh direct P5 semantic recomputation disagrees with artifact")


__all__ = [
    "CLAIM_BOUNDARY",
    "DEFAULT_CONFIG",
    "DEFAULT_OUTPUT",
    "PROTOCOL_ID",
    "run_p5_direct_trace_probe",
    "verify_p5_direct_trace_probe",
]
