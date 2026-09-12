"""Predeclared development challenges of the *existing* three-arm production path.

No private writes, replacement method, retuning, or scientific acceptance. Ordinary
production is a separately labelled interface reference, never an extra P5 warmup.
All readouts below use the already selected readout and unchanged typed decoder.
"""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import timedelta
from typing import Any

from cpswm.contracts import ObservationOutcome, ProjectTwoDatasetSplit
from cpswm.system.continual.project_one_feedback import EventRevisionKind, EventRevisionOutcome
from cpswm.system.evaluation_operations import structure_two_p5_three_arm_death_test as base
from cpswm.system.evaluation_operations.project_two_action_benchmark import _locations
from cpswm.system.evaluation_operations.structure_two_p5_direct_trace_probe import (
    _ProbeTraceSink,
    _router_features,
)
from cpswm.system.evaluation_operations.structure_two_p5_readout_posthoc_diagnostic import (
    selected_v0_6_action_readout,
)
from cpswm.system.prototype_spine import ActionReadout
from cpswm.system.reproducibility import content_sha256, content_uuid
from cpswm.system.structure_two_production_system import StructureTwoProductionSystem

ID = "window2-dynamic@0.1-development-only"
MISSING = "MISSING_PRODUCTION_CAPABILITY"
# Fixed before running: no seed search, threshold selection or expectation from outputs.
PLANS = (
    {
        "id": "stable_owner",
        "locations": [0] * 14,
        "actors": ["owner"] * 14,
        "path": "stable owner evidence -> lawful long-term commit -> surviving contribution",
        "change": "nonempty committed statistics",
        "invariant": "object, owner and public map",
        "necessary": "direct P5 committed events > 0",
    },
    {
        "id": "negative_verification",
        "locations": [0] * 6 + [None] + [0] * 7,
        "actors": ["owner"] * 14,
        "path": "positive -> negative CIAV -> positive",
        "change": "negative evidence affects a later belief or action",
        "invariant": "no invented positive transition from a negative detection",
        "necessary": "nonempty negative closure and posterior consequence",
    },
    {
        "id": "guest_handoff",
        "locations": [0] * 6 + [1] * 4 + [0] * 4,
        "actors": ["owner"] * 6 + ["guest"] * 4 + ["owner"] * 4,
        "path": "other actor displacement without owner habit change",
        "change": "actor responsibility and current location",
        "invariant": "owner habit",
        "necessary": "owner/guest paired posterior contrast",
    },
    {
        "id": "unknown_actor",
        "locations": [0] * 6 + [1] * 4 + [0] * 4,
        "actors": ["owner"] * 6 + ["unknown_actor"] * 4 + ["owner"] * 4,
        "path": "open-set actor evidence -> uncertainty without owner habit rewrite",
        "change": "unknown actor responsibility",
        "invariant": "owner identity and object",
        "necessary": "unknown evidence consumed; no silent known-actor substitution",
    },
    {
        "id": "habit_change_return",
        "locations": [0] * 6 + [1] * 4 + [0] * 4,
        "actors": ["owner"] * 14,
        "path": "stable -> new regime -> old regime reactivation",
        "change": "regime and surviving statistics",
        "invariant": "actor and object identity",
        "necessary": "nonempty regime creation and reactivation",
    },
    {
        "id": "similar_instance",
        "locations": [0] * 13 + [1],
        "actors": ["owner"] * 14,
        "path": "same-category different object instance at last input",
        "change": "instance association or explicit rejection",
        "invariant": "original instance memory must not absorb another instance",
        "necessary": "instance-specific boundary observed",
    },
)


def fixture(template: Any, plan: dict[str, Any]) -> Any:
    """Typed legal visible records. The public catalogue is a disclosed dev condition."""
    locations = _locations(template)
    seed_step = next(
        s
        for s in template.steps
        if s.actor_evidence is not None
        and s.after is not None
        and s.after.outcome is ObservationOutcome.DETECTED
    )
    steps = []
    actors = tuple(dict.fromkeys((*template.resident_actor_keys, "unknown_actor")))
    for index, (destination, actor) in enumerate(
        zip(plan["locations"], plan["actors"], strict=True)
    ):
        when = seed_step.timestamp + timedelta(days=index)
        prefix = f"{plan['id']}:{index}"

        def uid(key: str, prefix: str = prefix) -> Any:
            return content_uuid(ID, prefix + ":" + key)

        data = seed_step.model_dump(mode="python")
        obj = seed_step.object_instance_id
        if plan["id"] == "similar_instance" and index == len(plan["locations"]) - 1:
            obj = content_uuid(ID, "same-category-second-instance")
        src = locations[1 if destination != 1 else 0]
        dst = locations[destination] if destination is not None else None
        for name, loc in (("before", src), ("after", dst)):
            record = data[name]
            record["metadata"]["record_id"] = uid(name)
            record["metadata"]["recorded_time"] = when
            record["observation_opportunity_id"] = uid(name + "-opportunity")
            record["detection_time"] = when - timedelta(minutes=1) if name == "before" else when
            record["detection_time"] = record["detection_time"] if loc else None
            record["detected_location_id"] = loc
            record["detected_object_instance_id"] = obj if loc else None
            record["outcome"] = (
                ObservationOutcome.DETECTED if loc else ObservationOutcome.NOT_OBSERVED
            )
            record["negative_evidence_strength"] = 0.0
        opportunity = data["observation_opportunity"]
        opportunity["metadata"]["record_id"] = uid("after-opportunity")
        opportunity["metadata"]["recorded_time"] = when
        opportunity["observation_action_id"] = uid("action")
        opportunity["opportunity_time"] = when
        masses = {a: (0.9 if a == actor else 0.1 / (len(actors) - 1)) for a in actors}
        evidence = data["actor_evidence"]
        evidence["metadata"]["record_id"] = uid("actor")
        evidence["metadata"]["recorded_time"] = when
        evidence["source_detection_result_id"] = uid("after")
        evidence["object_instance_id"] = obj
        evidence["evidence_time"] = when
        evidence["evidence_cluster_id"] = uid("evidence-cluster")
        evidence["actor_posterior"] = masses
        evidence["reference_actor_prior"] = masses
        data.update(
            step_id=uid("step"),
            timestamp=when,
            valid_time={"start": when, "end": when + timedelta(hours=1)},
            object_instance_id=obj,
            source_location_id=src,
            attempted_location_id=locations[0],
            observed_destination_location_id=None,
            actor_evidence=evidence if dst else None,
            mechanism_evidence=None,
            ordered_role_evidence=None,
            execution_feedback=(),
            unified_evidence=None,
            perception_frames=(),
            object_tracks=(),
        )
        steps.append(type(seed_step).model_validate(data))
    data = template.model_dump(mode="python")
    data.update(
        episode_id=content_uuid(ID, plan["id"]),
        steps=steps,
        scene_id=plan["id"],
        known_location_ids=locations,
        dataset_version=ID,
        source_uri="development-only://window2/" + plan["id"],
        source_hash=content_sha256(plan),
        provenance=(ID,),
        split=ProjectTwoDatasetSplit.TRAIN,
        contract_compatibility=None,
    )
    return type(template).model_validate(data)


def state_readout(system: Any) -> dict[str, Any]:
    """Read real surviving contributions; location error is not contamination."""
    config = selected_v0_6_action_readout()
    distributions = {}
    for name, mode in (
        ("full", config.readout),
        ("fast", ActionReadout.LATEST_OWNER_EVENT),
        ("long", ActionReadout.SURVIVING_OWNER_REVISIONS),
    ):
        dist = system.action_location_distribution(
            system.current_snapshot, readout=replace(config, readout=mode)
        )
        distributions[name] = {str(k): v for k, v in dist.items()}
    core = system.core
    contributions = [
        {
            "location": str(event.location_id),
            "owner_mass": event.owner_mass,
            "statistical_weight": event.statistical_owner_weight,
        }
        for event in core._committed_events.values()
    ]
    return {
        "distributions": distributions,
        "committed": len(contributions),
        "contributions": sorted(contributions, key=lambda v: (v["location"], v["owner_mass"])),
        "observed_owner_masses": [event.owner_mass for event in core._observed_events.values()],
        "fast_events": len(core._fast_action_events),
        "observations": core.observation_count,
        "active_regime": core.active_regime,
        "hybrid_alpha": {str(loc): core.hybrid_alpha(loc) for loc in system.locations},
    }


def coverage_status(*, committed: int, action_differences: int, executed: int) -> str:
    """Nonempty necessary conditions cannot be satisfied by an empty all() result."""
    if min(committed, action_differences, executed) < 0:
        raise ValueError("negative coverage count")
    return "NONEMPTY_LOCAL_COVERAGE" if all((committed, action_differences, executed)) else MISSING


def run_scenes(
    template: Any, model: Any, material: Any, smoothing: float, parameter: float
) -> dict[str, Any]:
    from cpswm.system.evaluation_operations import structure_two_comparison_audit as audit
    from cpswm.system.evaluation_operations import structure_two_comparison_fairness as fair

    scenes = []
    for plan in PLANS:
        episode = fixture(template, plan)
        states = audit.make_states(episode, model, material, smoothing, parameter)
        ordinary = StructureTwoProductionSystem(
            owner_key=episode.owner_actor_key,
            object_instance_id=episode.steps[0].object_instance_id,
            locations=states[0].locations,
            authorization_scope_id=content_uuid(ID, plan["id"]),
            action_readout=selected_v0_6_action_readout(),
        )
        schedule = base._episode_schedule_commitment(episode)
        rows = []
        for index, step in enumerate(episode.steps):
            packet = base._packet_for_step(episode, step, schedule_commitment_sha256=schedule)
            outputs, posteriors, receipts = {}, [], []
            for state in states:
                before = state_readout(state.system) if state is states[0] else None
                try:
                    receipt = state.consume_matched_ciav_packet(packet, step, step_index=index)
                    posterior = state.predict_location_posteriors(packet)
                    action = audit.decode(posterior, step, index, content_uuid(ID, plan["id"]))
                    fair.check_decoded(posterior, action, step)
                    receipts.append(receipt)
                    posteriors.append(posterior)
                    outputs[state.arm.value] = {
                        "status": "RETURNED",
                        "input_sha256": packet.visible_step_sha256,
                        "closure": receipt.closure_kind,
                        "current": audit._distribution(posterior.current_location_distribution),
                        "habit": audit._distribution(posterior.owner_habit_location_distribution),
                        "search": [str(a.location_id) for a in action.search_plan],
                        "put_back": str(action.put_back_action.location_id),
                    }
                    if state is states[0]:
                        raw = state_readout(state.system)
                        fast = audit.decode(
                            audit.with_distributions(
                                posterior,
                                habit={
                                    loc: raw["distributions"]["fast"][str(loc)]
                                    for loc in state.locations
                                },
                            ),
                            step,
                            index,
                            content_uuid(ID, plan["id"]),
                        )
                        outputs[state.arm.value].update(
                            before=before,
                            after=raw,
                            fast_put_back=str(fast.put_back_action.location_id),
                            full_fast_action_difference=fast.put_back_action.location_id
                            != action.put_back_action.location_id,
                        )
                except (ValueError, KeyError, RuntimeError, AssertionError) as error:
                    outputs[state.arm.value] = {
                        "status": "REJECTED",
                        "error": str(error),
                        "error_type": type(error).__name__,
                        "input_sha256": packet.visible_step_sha256,
                    }
            contract_check = "PASS" if len(receipts) == len(states) else "INCOMPLETE_ARM_OUTPUTS"
            if len(receipts) == len(states):
                try:
                    fair.check_step(packet, step, posteriors, receipts)
                    base.verify_matched_consumption(receipts)
                except ValueError as error:
                    contract_check = str(error)
            ordinary_result: dict[str, Any]
            ordinary_before = state_readout(ordinary)
            try:
                if packet.realized_outcome is ObservationOutcome.DETECTED:
                    result = ordinary.process_transition(base._transition(episode, step, index))
                    ordinary_result = {
                        "status": "RETURNED",
                        "conclusion": result.decision.conclusion,
                        "operations": list(result.decision.statistic_operations),
                    }
                else:
                    ordinary_result = {
                        "status": "NO_TRANSITION_ENTRY",
                        "reason": "ordinary transition is not a negative-observation adapter",
                    }
            except (ValueError, KeyError, RuntimeError, AssertionError) as error:
                ordinary_result = {"status": "REJECTED", "error": str(error)}
            ordinary_result.update(before=ordinary_before, after=state_readout(ordinary))
            # Evaluator labels are constructed only after all three action attempts.
            expected_habit = states[0].locations[
                1 if plan["id"] == "habit_change_return" and 6 <= index < 10 else 0
            ]
            actual = packet.realized_detected_location_id
            ordinary_result["nonhabit_long_contribution_mass"] = sum(
                v["statistical_weight"]
                for v in ordinary_result["after"]["contributions"]
                if v["location"] != str(expected_habit)
            )
            for output in outputs.values():
                if output["status"] == "RETURNED":
                    output["search_top1_correct"] = (
                        output["search"][0] == str(actual) if actual else None
                    )
                    output["put_back_command_correct"] = output["put_back"] == str(expected_habit)
                    if "after" in output:
                        output["nonhabit_long_contribution_mass"] = sum(
                            v["statistical_weight"]
                            for v in output["after"]["contributions"]
                            if v["location"] != str(expected_habit)
                        )
                    output["execution_success"] = None
                    output["environment_state_changed"] = None
            rows.append(
                {
                    "step_index": index,
                    "contract_check": contract_check,
                    "visible": step.model_dump(mode="json"),
                    "packet": packet.model_dump(mode="json"),
                    "arms": outputs,
                    "ordinary_reference_same_visible_input": ordinary_result,
                    "evaluator_expected_habit": str(expected_habit),
                }
            )
        p5rows = [r["arms"][audit.P5] for r in rows if r["arms"][audit.P5]["status"] == "RETURNED"]
        commits = max((r["after"]["committed"] for r in p5rows), default=0)
        diffs = sum(r["full_fast_action_difference"] for r in p5rows)
        scenes.append(
            {
                "plan": plan,
                "rows": rows,
                "max_direct_p5_committed": commits,
                "full_fast_action_differences": diffs,
                "max_ordinary_reference_committed": max(
                    r["ordinary_reference_same_visible_input"]["after"]["committed"] for r in rows
                ),
                "complete_mechanism": coverage_status(
                    committed=commits, action_differences=diffs, executed=0
                ),
            }
        )
    return {
        "development_only": True,
        "id": ID,
        "plans_sha256": content_sha256(PLANS),
        "condition": "explicit common public catalogue; shared visible priors and packets",
        "controlled_contrasts": controlled_contrasts(scenes),
        "baseline_training": (
            "original TRAIN fit and independent VALIDATION selection reused; no dynamic retuning"
        ),
        "ordinary_reference": (
            "separate production compatibility path, never a fourth ranked arm or P5 warmup"
        ),
        "scenes": scenes,
        "production_boundary_probes": boundary_probes(template),
        "ciav_interface_probes": verification_probes(template),
        "feedback_interface_probes": feedback_probes(template),
        "execution": {
            "status": MISSING,
            "reason": (
                "TaskSeparatedActionEnvironment.issue_runtime_readout requires its own "
                "learned runtime; no three-arm command adapter"
            ),
        },
        "scientific_acceptance": False,
    }


def boundary_probes(template: Any) -> dict[str, Any]:
    """Public revision inputs; originals are obtained from lawful production calls."""
    episode = fixture(template, PLANS[0])
    probes: dict[str, Any] = {}
    for mode in ("correct", "retract", "duplicate", "out_of_order"):
        system = StructureTwoProductionSystem(
            owner_key=episode.owner_actor_key,
            object_instance_id=episode.steps[0].object_instance_id,
            locations=_locations(episode),
            authorization_scope_id=content_uuid(ID, mode),
            action_readout=selected_v0_6_action_readout(),
        )
        results = [
            system.process_transition(base._transition(episode, step, i))
            for i, step in enumerate(episode.steps)
        ]
        before = state_readout(system)
        chosen = results[3].event_revision_id
        committed = system.core._committed_events.get(chosen)
        detail: dict[str, Any] = {
            "input_boundary": "public production compatibility; not direct P5",
            "before": before,
            "nonempty_target": committed is not None,
        }
        try:
            if mode in ("correct", "retract"):
                if committed is None:
                    detail["status"] = MISSING
                    probes[mode] = detail
                    continue
                corrected = content_uuid(ID, mode + "-corrected")
                outcome = EventRevisionOutcome(
                    kind=EventRevisionKind(mode),
                    superseded_revision_id=chosen,
                    evidence_source_record_ids=(episode.steps[-1].after.metadata.record_id,),
                    rationale=(
                        "development interface probe; external revision outcome, "
                        "not autonomous inference"
                    ),
                    corrected_revision_id=corrected if mode == "correct" else None,
                    corrected_location_id=system.locations[1] if mode == "correct" else None,
                    corrected_owner_mass=committed.owner_mass if mode == "correct" else None,
                )
                result = system.core.apply_event_revision_outcome(outcome)
                detail.update(
                    status="RETURNED",
                    operations=list(result.statistic_operations),
                    old_committed=system.core.is_committed_revision(chosen),
                    new_committed=system.core.is_committed_revision(corrected),
                    new_quarantined=system.core.is_quarantined_revision(corrected),
                )
                after_first = state_readout(system)
                try:
                    system.core.apply_event_revision_outcome(outcome)
                    detail["repeat"] = "RETURNED"
                except (ValueError, KeyError, RuntimeError) as error:
                    detail["repeat"] = {"rejected": type(error).__name__, "error": str(error)}
                detail["repeat_semantic_unchanged"] = state_readout(system) == after_first
            else:
                index = len(episode.steps) - 1 if mode == "duplicate" else 0
                system.process_transition(base._transition(episode, episode.steps[index], index))
                detail["status"] = "RETURNED"
        except (ValueError, KeyError, RuntimeError, AssertionError) as error:
            detail.update(status="REJECTED", error_type=type(error).__name__, error=str(error))
        detail["after"] = state_readout(system)
        detail["semantic_unchanged"] = detail["after"] == before
        probes[mode] = detail
    probes["default_loop_config"] = asdict(system.core.loop_config)
    probes["default_readout"] = asdict(selected_v0_6_action_readout())
    return probes


def verification_probes(template: Any) -> dict[str, Any]:
    """Vary the legal CIAV result, not the runtime or private state.

    This probes the production interface outside the registered one-packet arm
    adapter: the latter makes after-location and CIAV-location equal by design.
    It is not a new shared-CIAV scientific comparison.
    """
    from cpswm.system.evaluation_operations.structure_two_p5_readout_posthoc_diagnostic import (
        ReadoutCorrectedDirectP5LocationAdapter,
    )
    from cpswm.system.structure_two_adaptive_runtime import AdaptiveExecutionContext
    from cpswm.system.structure_two_execution import verify_execution_trace

    output = {}
    for name, destination in (("same", 0), ("different", 1), ("negative", None)):
        plan = dict(
            PLANS[0],
            id="verification-" + name,
            locations=[0, destination],
            actors=["owner", "owner"],
        )
        episode = fixture(template, plan)
        adapter = ReadoutCorrectedDirectP5LocationAdapter(episode)
        primary, verification = episode.steps
        packet = base._packet_for_step(
            episode,
            verification,
            schedule_commitment_sha256=base._episode_schedule_commitment(episode),
        )
        sink = _ProbeTraceSink()
        before = state_readout(adapter.system)
        result = adapter.system.process_evaluation_direct_p5_transition(
            base._transition(episode, primary, 0),
            context=AdaptiveExecutionContext(
                router_features=_router_features(adapter.system),
                step_index=0,
                ciav_input=base._ciav_input(packet, episode, verification, adapter.locations),
            ),
            trace_sink=sink,
        )
        if sink.trace is None:
            raise AssertionError("missing actual P5 trace")
        verify_execution_trace(sink.trace)
        assert result.ciav_receipt is not None
        output[name] = {
            "primary_visible": primary.model_dump(mode="json"),
            "verification_visible": verification.model_dump(mode="json"),
            "before": before,
            "after": state_readout(adapter.system),
            "closure": sink.trace.feedback_closure_kind,
            "all_seven_invoked": sink.trace.all_seven_operators_invoked,
            "detection_outcome": result.ciav_receipt.detection.outcome,
            "detected_location": str(result.ciav_receipt.detection.detected_location_id),
        }
    return output


def feedback_probes(template: Any) -> dict[str, Any]:
    """Bound action feedback into the real core. No injected feedback policy.

    Likelihoods are disclosed synthetic sensor assumptions, not calibrated D2
    costs or ground-truth access. This is an interface test, not robot execution.
    """
    from cpswm.contracts import (
        ActionOutcomeLikelihoodModel,
        DecisionContextBinding,
        DecisionSurface,
        EntityRef,
        EntityType,
        ExecutionFeedbackRecord,
        MapConsistencyRevisions,
        RobotActionOutcome,
        RobotActionType,
        SourceType,
        TargetPresenceBeliefRef,
    )
    from cpswm.contracts.base import ValidTimeInterval
    from cpswm.contracts.decision_context import DecisionContext

    output = {}
    episode = fixture(template, PLANS[0])
    for name, outcome in (
        ("success", RobotActionOutcome.SUCCESS),
        ("not_found", RobotActionOutcome.NOT_FOUND),
    ):

        def uid(key: str, name: str = name) -> Any:
            return content_uuid(ID, "feedback:" + name + ":" + key)

        system = StructureTwoProductionSystem(
            owner_key=episode.owner_actor_key,
            object_instance_id=episode.steps[0].object_instance_id,
            locations=_locations(episode),
            authorization_scope_id=uid("scope"),
            action_readout=selected_v0_6_action_readout(),
        )
        original = None
        for index, step in enumerate(episode.steps):
            transition = base._transition(episode, step, index)
            original = system.process_transition(transition)
        assert original is not None
        before = state_readout(system)
        when = episode.steps[-1].timestamp
        interval = ValidTimeInterval(start=when, end=when + timedelta(minutes=1))
        metadata = transition.after.metadata.model_copy(
            update={
                "record_id": uid("feedback"),
                "schema_name": "cpswm.ExecutionFeedbackRecord",
                "source_type": SourceType.ACTION,
                "recorded_time": when,
            }
        )
        feedback = ExecutionFeedbackRecord(
            metadata=metadata,
            action_id=uid("action"),
            action_type=RobotActionType.SEARCH,
            target_entity=EntityRef(
                entity_id=episode.steps[0].object_instance_id,
                entity_type=EntityType.OBJECT_INSTANCE,
            ),
            attempted_location_id=transition.after.detected_location_id,
            valid_time=interval,
            outcome_distribution={outcome: 0.99, RobotActionOutcome.UNKNOWN: 0.01},
            observation_opportunity_id=transition.opportunity.metadata.record_id,
            diagnostics={"source_revision_id": str(original.event_revision_id)},
        )
        revisions = MapConsistencyRevisions(
            belief_snapshot_id=system.current_snapshot.snapshot_id,
            projection_id=uid("projection"),
            projection_version=1,
            static_map_revision=1,
            dynamic_map_revision=1,
            event_history_revision=1,
            input_watermark=1,
        )
        context = DecisionContext.create(
            decision_id=uid("decision"),
            decision_time=when,
            valid_time=interval,
            staleness_budget_seconds=60,
            revisions=revisions,
            target_presence_belief=TargetPresenceBeliefRef(
                object_instance_id=episode.steps[0].object_instance_id,
                location_id=transition.after.detected_location_id,
                belief_node_id="dev-presence",
                belief_snapshot_id=revisions.belief_snapshot_id,
                node_content_hash=content_sha256(before),
                prior_probability=0.8,
            ),
            authorization_scope_id=system.core.authorization_scope_id,
            habit_regime_model_version=system.core.model_version,
            model_versions=(("prototype", system.core.model_version),),
            code_version=ID,
            rationale="development observed feedback bound to current production snapshot",
        )
        binding = DecisionContextBinding(
            metadata=metadata.model_copy(
                update={"record_id": uid("binding"), "schema_name": "cpswm.DecisionContextBinding"}
            ),
            surface=DecisionSurface.EXECUTION_FEEDBACK,
            subject_record_id=metadata.record_id,
            subject_household_id=metadata.household_id,
            subject_session_id=metadata.session_id,
            subject_trace_id=metadata.trace_id,
            decision_context=context,
        )
        probability = 0.99 if outcome is RobotActionOutcome.SUCCESS else 0.2
        likelihood = ActionOutcomeLikelihoodModel(
            action_type=RobotActionType.SEARCH,
            p_outcome_given_target_present={
                outcome: probability,
                RobotActionOutcome.UNKNOWN: 1 - probability,
            },
            p_outcome_given_target_absent={
                outcome: 1 - probability,
                RobotActionOutcome.UNKNOWN: probability,
            },
            calibration_domain="development_synthetic_not_D2",
            model_version=ID,
        )
        detail: dict[str, Any] = {
            "before": before,
            "sensor_likelihood": likelihood.model_dump(mode="json"),
        }
        try:
            result = system.core.process_execution_feedback(
                feedback=feedback, binding=binding, likelihood_model=likelihood
            )
            detail.update(
                status="RETURNED",
                operations=list(result.statistic_operations),
                presence_posterior=result.feedback_posterior_probability,
            )
            after = state_readout(system)
            try:
                system.core.process_execution_feedback(
                    feedback=feedback, binding=binding, likelihood_model=likelihood
                )
                detail["duplicate"] = "RETURNED"
            except (ValueError, KeyError, RuntimeError) as error:
                detail["duplicate"] = {"error_type": type(error).__name__, "error": str(error)}
            detail["duplicate_unchanged"] = state_readout(system) == after
        except (ValueError, KeyError, RuntimeError) as error:
            detail.update(status="REJECTED", error_type=type(error).__name__, error=str(error))
        detail["after"] = state_readout(system)
        detail["long_term_mass_delta"] = sum(detail["after"]["hybrid_alpha"].values()) - sum(
            before["hybrid_alpha"].values()
        )
        output[name] = detail
    return output


def contract_matrix(root: Any) -> dict[str, Any]:
    import json

    path = (
        "configs/project_two_experiments/structure_two_final_utility_guardrail_external_va"
        "lidation_protocol_v0_1.json"
    )
    final = json.loads((root / path).read_text())
    return {
        "final_frozen_protocol": {
            "path": path,
            "sha256": content_sha256(final),
            "status": final["status"],
            "primary_utility": final["primary_utility"],
            "full_rerun_equivalence": final["full_rerun_equivalence"],
            "applied_to_this_development_experiment": False,
        },
        "rows": [
            {
                "dimension": "map_and_prefix_support",
                "classification": "尚未决定",
                "current": (
                    "D0 _locations scans full episode when known catalogue absent; all "
                    "arms share it"
                ),
                "basis": (
                    "project_two_action_benchmark._locations; fairness per-step future_support"
                ),
                "options": ["explicit common public map", "common causal prefix catalogue"],
                "minimal_discriminator": (
                    "same visible prefix; vary only later unseen location; compare early actions"
                ),
                "impact": (
                    "future support changes normalization and ties; information matching "
                    "alone is insufficient"
                ),
            },
            {
                "dimension": "missing_owner_prior",
                "classification": "尚未决定",
                "current": (
                    "P5 uniform versus AMG last detected fallback; frozen diagnostic "
                    "decoder unchanged"
                ),
                "basis": (
                    "AMGLocationAdapter.predict_location_posteriors; retained attribution "
                    "cold-start control"
                ),
                "options": [
                    "common explicit prior",
                    "retain method-specific defaults and report cold-start stratum",
                ],
                "minimal_discriminator": (
                    "same no-owner prefix, fixed supports/decoder; already-opened cold- "
                    "start control"
                ),
                "impact": (
                    "17-step retained difference is explained by this default, not full "
                    "memory contribution"
                ),
            },
            {
                "dimension": "visible_evidence_and_features",
                "classification": "已冻结",
                "current": (
                    "common packet and visible step; actual consumers differ in "
                    "actor/role/temporal features"
                ),
                "basis": (
                    "three-arm method decision; fairness_execution.consumer_probe and "
                    "dynamic visible/arms"
                ),
                "limitation": (
                    "equal information permissions do not mean equal feature extraction or capacity"
                ),
            },
            {
                "dimension": "split_access_and_tuning",
                "classification": "已冻结",
                "current": (
                    "TRAIN labels -> independent learned/AMG VALIDATION PUT_BACK grids -> "
                    "opened TEST scoring"
                ),
                "basis": (
                    "three-arm split_policy; fairness_execution.train_access/selection; "
                    "existing SplitAccess"
                ),
                "limitation": (
                    "dynamic scenarios reuse selected baselines without retuning: "
                    "sensitivity only, not ranked superiority"
                ),
            },
            {
                "dimension": "typed_decoder_and_task_semantics",
                "classification": "已冻结",
                "current": (
                    "shared typed decoder, lexical UUID ties; SEARCH current location, "
                    "PUT_BACK owner habit"
                ),
                "basis": (
                    "three-arm typed_actions; TypedLocationPosterior.decode; fairness.check_decoded"
                ),
                "limitation": (
                    "common detected-current adapter erases native SEARCH differences; "
                    "changing it requires protocol decision"
                ),
            },
            {
                "dimension": "ciav_schedule_cost_privacy",
                "classification": "已冻结",
                "current": (
                    "one exogenous micro_verify; shared result before action; zero "
                    "component costs, privacy budget 1"
                ),
                "basis": "three-arm shared_ciav; actual packet/receipt checks",
                "limitation": (
                    "interface secondary-verification probes separate from registered "
                    "comparison; zero cost is not net utility"
                ),
            },
            {
                "dimension": "target_instance_binding",
                "classification": "实现违反合同",
                "current": (
                    "single-instance arm adapters may still target episode first object "
                    "after another object arrives"
                ),
                "basis": "dynamic similar_instance last row; fairness target-instance rejection",
                "repair_scope": (
                    "window2 refuses mismatched posteriors; multi-instance production "
                    "routing remains missing"
                ),
            },
            {
                "dimension": "capacity_training_online_latency",
                "classification": "尚未决定",
                "current": (
                    "framework Task 8 requires matched budgets; concrete P5 diagnosis "
                    "capacity/compute matching is not fixed"
                ),
                "basis": (
                    "framework Task 8; training parameter/compute counters; timing scoped "
                    "hardware record"
                ),
                "options": [
                    "fixed compute/latency matched capacity",
                    "frozen PCT-online-compute Pareto with multiple declared budgets",
                ],
                "minimal_discriminator": (
                    "isolated host, independent validation tuning under each common numeric budget"
                ),
                "impact": (
                    "do not infer equal compute from shared packets or claim speed from "
                    "concurrent wall time"
                ),
            },
            {
                "dimension": "final_scientific_utility",
                "classification": "已冻结",
                "current": (
                    "PCT and contamination/recovery/safety/privacy plus equivalence "
                    "requirements frozen, not run"
                ),
                "basis": path,
                "limitation": (
                    "D2 pilot numeric durations and authorization/gates remain pending; "
                    "metric not reopened"
                ),
            },
        ],
        "scientific_fairness_established": False,
    }


def controlled_contrasts(scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compare outcomes, not opaque state digests; do not relax replay tolerances."""
    by_id = {s["plan"]["id"]: s for s in scenes}
    rows = []
    for left_id, right_id, changed in (
        ("guest_handoff", "habit_change_return", "actor evidence/prior only"),
        ("unknown_actor", "habit_change_return", "actor evidence/prior only"),
        ("stable_owner", "negative_verification", "one nondetection instead of detection"),
    ):
        left, right = by_id[left_id], by_id[right_id]
        if len(left["rows"]) != len(right["rows"]):
            raise ValueError("controlled contrast history lengths differ")
        for index, (a, b) in enumerate(zip(left["rows"], right["rows"], strict=True)):
            arms = {}
            for arm, av in a["arms"].items():
                bv = b["arms"][arm]
                if av["status"] != "RETURNED" or bv["status"] != "RETURNED":
                    arms[arm] = {"status": "NOT_COMPARABLE"}
                    continue
                arms[arm] = {
                    "habit_total_variation": 0.5
                    * sum(abs(av["habit"][k] - bv["habit"][k]) for k in av["habit"]),
                    "current_total_variation": 0.5
                    * sum(abs(av["current"][k] - bv["current"][k]) for k in av["current"]),
                    "put_back_changed": av["put_back"] != bv["put_back"],
                    "search_changed": av["search"] != bv["search"],
                }
            rows.append(
                {
                    "left": left_id,
                    "right": right_id,
                    "step_index": index,
                    "intervention": changed,
                    "arms": arms,
                }
            )
    return rows
