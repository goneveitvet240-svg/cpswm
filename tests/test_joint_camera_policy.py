"""Production-path wiring with labeled fixtures; no physical calibration claim."""

from datetime import timedelta
from uuid import UUID

import pytest
from test_continuous_state_recovery import DurableFixtureProducer, store_at
from test_structure_two_adaptive_runtime import (
    _adaptive_system_and_transition,
    _ciav_input,
    _features,
)
from test_structure_two_continuous_input import raw_for
from test_structure_two_w3_native_posterior_projection import projected

from cpswm.contracts.grounded_search import ObservationActionCandidate
from cpswm.system.joint_camera_policy import CameraAlternative, JointCameraProblem
from cpswm.system.structure_two_adaptive_runtime import AdaptiveExecutionContext
from cpswm.system.structure_two_continuous_input import (
    ContinuousEvidenceInput,
    GroundedTransition,
    ObservationDelivery,
)


def p5_setup(path):
    system, transition = _adaptive_system_and_transition()
    ciav = _ciav_input(transition)

    def builder(system, item, when, step):
        return AdaptiveExecutionContext(
            router_features=_features(system, step=step, route="P0_FAST_LOCAL"),
            step_index=step,
            ciav_input=ciav,
        )

    meta = transition.after.metadata
    backend = DurableFixtureProducer()
    store = store_at(path)
    stream = ContinuousEvidenceInput(
        system=system,
        execution_lane="registered_p5_first",
        context_builder=builder,
        household_id=meta.household_id,
        session_id=meta.session_id,
        trace_id=meta.trace_id,
        producer=backend,
        state_store=store,
    )
    when = ciav.opportunity_time
    ids = stream.admit((raw_for(transition),), received_at=when)
    backend.output = GroundedTransition(transition, ids, "fixture", "fixture-not-calibrated")
    receipt = stream.advance(cutoff=when)
    assert receipt.result.path_selection.selected_path_id == "P5_FULL_EAGER"
    assert receipt.result.ciav_receipt is not None
    core = system.core
    core.stage_prepared_particle_candidates(**projected(core))
    return stream, store, transition, builder, when


def problem_for(stream, when, informative=True):
    view = stream.current_joint_decision_view()
    atoms = tuple(view.verification_belief().posterior)
    terminal = {a: {b: float(a == b) for b in atoms} for a in atoms}
    consolidation = {UUID(int=999): dict.fromkeys(atoms, 0.0)}

    def candidate(informative):
        likelihoods = (
            {str(a): {b: float(a == b) for b in atoms} for a in atoms}
            if informative
            else {"yes": dict.fromkeys(atoms, 0.5), "no": dict.fromkeys(atoms, 0.5)}
        )
        return ObservationActionCandidate(
            action_type="move_viewpoint",
            label="explicit fixture camera model",
            observation_likelihood_model_id="fixture-not-empirically-calibrated",
            calibration_domain="component-test",
            outcome_likelihoods=likelihoods,
            motion_cost=0.0,
            time_cost=0.01,
            interruption_cost=0.0,
            privacy_cost=0.0,
            safety_cost=0.0,
        )

    return JointCameraProblem(
        source_belief_sha256=view.content_sha256,
        source_observation_ids=tuple(
            x.envelope().identity.observation_id for x in stream.visible_prefix(cutoff=when)
        ),
        alternatives=(
            CameraAlternative(candidate=candidate(False), action="RotateRight", degrees=30),
            CameraAlternative(candidate=candidate(informative), action="RotateLeft", degrees=30),
        ),
        consolidation_decision_utilities=consolidation,
        terminal_decision_utilities=terminal,
        privacy_budget=1.0,
        minimum_net_value=0.0,
    )


def test_p5_posterior_selects_executes_and_recovers_same_input_history(tmp_path):
    path = tmp_path / "policy.db"
    stream, store, transition, builder, start = p5_setup(path)
    when = start + timedelta(seconds=2)
    problem = problem_for(stream, when)
    plan, command = stream.prepare_posterior_observation(problem, decision_time=when)
    assert plan.should_act and command.action == "RotateLeft"
    assert (
        JointCameraProblem.model_validate_json(command.reason.removeprefix("joint-ciav@1:"))
        == problem
    )

    class Camera:
        calls = 0

        def execute(self, command):
            self.calls += 1
            # This is a transport fixture: no claim that black pixels are natural input.
            received = command.decision_time + timedelta(seconds=1)
            return ObservationDelivery(
                command.action_id,
                (raw_for(transition, capture=received),),
                True,
                "",
                received,
            )

    camera = Camera()
    received = stream.execute_observation(command, executor=camera)
    assert len(stream.visible_prefix(cutoff=received.received_at)) == 2
    store.close()
    store = store_at(path)
    recovered = ContinuousEvidenceInput.resume(
        store, producer=DurableFixtureProducer(), context_builder=builder
    )
    assert recovered._system.core is recovered._system._assembly_components[0]
    owned = recovered._observation_commands[command.action_id][0]
    assert owned.reason == command.reason
    with pytest.raises(ValueError, match="already dispatched"):
        recovered.execute_observation(owned, executor=camera)
    assert camera.calls == 1
    assert len(recovered.visible_prefix(cutoff=received.received_at)) == 2
    store.close()


def test_no_value_stops_and_stale_problem_does_not_fall_back_to_scan(tmp_path):
    stream, store, _, _, start = p5_setup(tmp_path / "policy.db")
    when = start + timedelta(seconds=2)
    problem = problem_for(stream, when, informative=False)
    plan, command = stream.prepare_posterior_observation(problem, decision_time=when)
    assert not plan.should_act and command is None
    with pytest.raises(ValueError, match="another joint"):
        stream.prepare_posterior_observation(
            problem.model_copy(update={"source_belief_sha256": "0" * 64}), decision_time=when
        )
    assert not stream._observation_commands
    store.close()


def test_unseen_policy_dependencies_do_not_issue_a_command(tmp_path):
    stream, store, _, _, start = p5_setup(tmp_path / "policy.db")
    when = start + timedelta(seconds=2)
    problem = problem_for(stream, when)
    with pytest.raises(ValueError, match="unseen"):
        stream.prepare_posterior_observation(
            problem.model_copy(update={"source_observation_ids": (UUID(int=123456),)}),
            decision_time=when,
        )
    assert not stream._observation_commands
    store.close()
