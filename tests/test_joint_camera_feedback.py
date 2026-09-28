"""Actual owned RGB feedback, exact Bayesian arithmetic, state and action consequences.

Brightness and likelihoods below are explicit test fixtures, not calibrated vision.
PYTEST_DONT_REWRITE: fixture decoder code is bound by the runtime.
"""

import hashlib
import io
from datetime import timedelta

import numpy as np
import pytest
from test_continuous_camera_collection import SOURCES
from test_continuous_state_recovery import DurableFixtureProducer, store_at
from test_native_joint_production import JointFixture
from test_structure_two_adaptive_runtime import (
    _adaptive_system_and_transition,
    _ciav_input,
    _features,
)
from test_structure_two_continuous_input import raw_for

from cpswm.contracts.grounded_search import ObservationActionCandidate
from cpswm.perception_mapping.adapters.rgbd_capture import RawModalityObservation
from cpswm.system.joint_camera_feedback import condition_view
from cpswm.system.joint_camera_policy import CameraAlternative, JointCameraProblem
from cpswm.system.reproducibility import content_sha256, content_uuid
from cpswm.system.structure_two_adaptive_runtime import AdaptiveExecutionContext
from cpswm.system.structure_two_continuous_input import (
    ContinuousEvidenceInput,
    GroundedTransition,
    ObservationDelivery,
)
from cpswm.system.structure_two_particle_workspace import native_content_sha256


class BrightnessDecoder:
    sources = SOURCES
    binding_sha256 = content_sha256("fixture-only-mean-pixel-brightness@1")

    def decode(self, observations, *, cutoff):
        assert all(x.envelope().arrival_time <= cutoff for x in observations)
        values = [
            np.load(io.BytesIO(x.payload_bytes), allow_pickle=False).mean() for x in observations
        ]
        return "bright" if max(values) > 0 else "dark"


class AbstainDecoder(BrightnessDecoder):
    binding_sha256 = content_sha256("fixture-only-abstention@1")

    def decode(self, observations, *, cutoff):
        return None


def setup(path, decoder=None, joint=None, *, feedback=True):
    system, transition = _adaptive_system_and_transition()
    ciav = _ciav_input(transition)

    def builder(system, item, when, step):
        return AdaptiveExecutionContext(
            router_features=_features(system, step=step, route="P0_FAST_LOCAL"),
            step_index=step,
            ciav_input=ciav,
        )

    backend, store = DurableFixtureProducer(), store_at(path)
    meta = transition.after.metadata
    stream = ContinuousEvidenceInput(
        system=system,
        execution_lane="registered_p5_first",
        household_id=meta.household_id,
        session_id=meta.session_id,
        trace_id=meta.trace_id,
        producer=backend,
        context_builder=builder,
        state_store=store,
        joint_producer=joint or JointFixture(),
        observation_decoder=(decoder or BrightnessDecoder()) if feedback else None,
    )
    when = ciav.opportunity_time
    ids = stream.admit((raw_for(transition),), received_at=when)
    backend.output = GroundedTransition(transition, ids, "fixture", "fixture-not-calibrated")
    stream.advance(cutoff=when)
    stream.produce_joint_posterior()
    return stream, store, transition, builder, when


def problem_for(stream, when):
    view = stream.current_joint_decision_view()
    atoms = tuple(view.verification_belief().posterior)
    terminal = {a: {b: float(a == b) for b in atoms} for a in atoms}
    alternatives = []
    for index, action in enumerate(("RotateLeft", "RotateRight")):
        target = view.atoms[index].particle_id
        likelihood = {a: 0.95 if a == target else 0.05 for a in atoms}
        candidate = ObservationActionCandidate(
            action_id=content_uuid("fixture-camera-query", (view.content_sha256, index)),
            action_type="move_viewpoint",
            label="fixture whole-atom measurement",
            observation_likelihood_model_id=SOURCES.observation_model_id,
            calibration_domain=SOURCES.calibration_domain,
            outcome_likelihoods={
                "bright": likelihood,
                "dark": {k: 1 - v for k, v in likelihood.items()},
            },
            motion_cost=0.0,
            time_cost=0.0001,
            interruption_cost=0.0,
            privacy_cost=0.0,
            safety_cost=0.0,
        )
        alternatives.append(CameraAlternative(candidate=candidate, action=action, degrees=30))
    return JointCameraProblem(
        model_sources=SOURCES,
        source_belief_sha256=view.content_sha256,
        source_observation_ids=tuple(
            x.envelope().identity.observation_id for x in stream.visible_prefix(cutoff=when)
        ),
        alternatives=tuple(alternatives),
        consolidation_decision_utilities={
            content_uuid("fixture-camera", "noop"): dict.fromkeys(atoms, 0.0)
        },
        terminal_decision_utilities=terminal,
        privacy_budget=1.0,
        minimum_net_value=0.0,
    )


class Camera:
    def __init__(self, transition, *, bright=False, success=True):
        self.transition, self.bright, self.success = transition, bright, success
        self.calls = 0

    def execute(self, command):
        self.calls += 1
        when = command.decision_time + timedelta(seconds=1)
        if not self.success:
            return ObservationDelivery(
                command.action_id, (), False, "fixture failed execution", when
            )
        raw = raw_for(self.transition, capture=when)
        if self.bright:
            buffer = io.BytesIO()
            np.save(buffer, np.ones((4, 4, 3), dtype=np.uint8), allow_pickle=False)
            data = buffer.getvalue()
            env = raw.envelope()
            env = env.model_copy(
                update={
                    "payload": env.payload.model_copy(
                        update={
                            "payload_sha256": hashlib.sha256(data).hexdigest(),
                            "size_bytes": len(data),
                        }
                    )
                }
            )
            raw = RawModalityObservation(
                env.model_dump_json(), data, content_sha256("bright"), None
            )
        return ObservationDelivery(command.action_id, (raw,), True, "", when)


def execute(stream, transition, when, *, bright=False, success=True):
    problem = problem_for(stream, when)
    before = stream.current_joint_decision_view()
    _, command = stream.prepare_posterior_observation(problem, decision_time=when)
    assert command is not None
    camera = Camera(transition, bright=bright, success=success)
    delivery = stream.execute_observation(command, executor=camera)
    return before, problem, command, delivery, camera


@pytest.mark.parametrize("bright", [False, True])
def test_owned_pixels_change_joint_view_by_exact_bayes_without_native_or_ledger_write(
    tmp_path, bright
):
    stream, store, transition, _, start = setup(tmp_path / "db")
    core = stream._system.core
    native = native_content_sha256(core._particle_workspace.state_payload())
    ledger = core._hybrid_loop.ledger.export_state()
    before, problem, command, _, camera = execute(
        stream, transition, start + timedelta(seconds=2), bright=bright
    )
    after = stream.current_joint_decision_view()
    option = next(x for x in problem.alternatives if x.action == command.action)
    likelihood = option.candidate.outcome_likelihoods["bright" if bright else "dark"]
    prior = before.verification_belief().posterior
    z = sum(prior[k] * likelihood[k] for k in prior)
    expected = {k: prior[k] * likelihood[k] / z for k in prior}
    assert after.verification_belief().posterior == pytest.approx(expected)
    assert after != before and len(after.observation_evidence) == 1
    assert stream.current_joint_decision_view() == after  # pure re-read, not a second update
    updates = stream.joint_observation_updates()
    assert len(updates) == 1 and updates[0].marginal_likelihood == pytest.approx(z)
    assert native_content_sha256(core._particle_workspace.state_payload()) == native
    assert core._hybrid_loop.ledger.export_state() == ledger and camera.calls == 1
    store.close()


def test_negative_measurement_changes_next_selected_action(tmp_path):
    stream, store, transition, _, start = setup(tmp_path / "db")
    before, _, command, delivery, _ = execute(stream, transition, start + timedelta(seconds=2))
    when = delivery.received_at + timedelta(seconds=1)
    next_problem = problem_for(stream, when)
    _, next_command = stream.prepare_posterior_observation(next_problem, decision_time=when)
    assert next_command is not None and next_command.action != command.action
    assert (
        stream.current_joint_decision_view().verification_belief().posterior
        != before.verification_belief().posterior
    )
    store.close()


@pytest.mark.parametrize("mode", ["failure", "abstain"])
def test_failed_or_abstaining_measurement_retains_probabilities_and_records_lineage(tmp_path, mode):
    decoder = AbstainDecoder() if mode == "abstain" else BrightnessDecoder()
    stream, store, transition, _, start = setup(tmp_path / "db", decoder)
    before, _, _, _, _ = execute(
        stream, transition, start + timedelta(seconds=2), success=mode != "failure"
    )
    after = stream.current_joint_decision_view()
    assert after.verification_belief().posterior == before.verification_belief().posterior
    assert len(after.observation_evidence) == 1
    update = stream.joint_observation_updates()[0]
    assert update.outcome is None and update.marginal_likelihood is None
    store.close()


def test_conditioning_rejects_missing_unknown_and_impossible_outcome(tmp_path):
    stream, store, _, _, _ = setup(tmp_path / "db")
    view = stream.current_joint_decision_view()
    prior = view.verification_belief().posterior
    with pytest.raises(ValueError, match="every full joint"):
        condition_view(view, {a.particle_id: 1.0 for a in view.atoms}, evidence_sha256="a" * 64)
    with pytest.raises(ValueError, match="impossible"):
        condition_view(view, dict.fromkeys(prior, 0.0), evidence_sha256="a" * 64)
    once, _ = condition_view(view, dict.fromkeys(prior, 0.5), evidence_sha256="a" * 64)
    with pytest.raises(ValueError, match="duplicate"):
        condition_view(once, None, evidence_sha256="a" * 64)
    store.close()


def test_decoder_source_change_rejected_before_physical_action(tmp_path):
    decoder = BrightnessDecoder()
    stream, store, transition, _, start = setup(tmp_path / "db", decoder)
    when = start + timedelta(seconds=2)
    problem = problem_for(stream, when)
    _, command = stream.prepare_posterior_observation(problem, decision_time=when)
    decoder.binding_sha256 = "0" * 64
    camera = Camera(transition)
    with pytest.raises(ValueError, match="decoder dependency changed"):
        stream.execute_observation(command, executor=camera)
    assert camera.calls == 0
    store.close()


def test_recovery_recomputes_same_pixels_and_never_redispatches(tmp_path):
    path = tmp_path / "db"
    stream, store, transition, builder, start = setup(path)
    _, _, command, _, camera = execute(stream, transition, start + timedelta(seconds=2))
    view = stream.current_joint_decision_view()
    updates = stream.joint_observation_updates()
    store.close()
    store = store_at(path)
    with pytest.raises(ValueError, match="decoder dependency"):
        ContinuousEvidenceInput.resume(
            store,
            producer=DurableFixtureProducer(),
            context_builder=builder,
            joint_producer=JointFixture(),
        )
    restored = ContinuousEvidenceInput.resume(
        store,
        producer=DurableFixtureProducer(),
        context_builder=builder,
        joint_producer=JointFixture(),
        observation_decoder=BrightnessDecoder(),
    )
    assert (
        restored.current_joint_decision_view() == view
        and restored.joint_observation_updates() == updates
    )
    owned = restored._observation_commands[command.action_id][0]
    with pytest.raises(ValueError, match="already dispatched"):
        restored.execute_observation(owned, executor=camera)
    assert camera.calls == 1
    store.close()


def test_full_resealed_wrong_delivery_pixels_fail_owned_evidence_check(tmp_path):
    stream, store, transition, _, start = setup(tmp_path / "db")
    _, _, command, delivery, _ = execute(stream, transition, start + timedelta(seconds=2))
    expected = stream.current_joint_decision_view()
    replacement = Camera(transition, bright=True).execute(command)
    stream._observation_status[command.action_id] = replacement
    with pytest.raises(ValueError, match="owned post-action"):
        stream.current_joint_decision_view()
    stream._observation_status[command.action_id] = delivery
    assert stream.current_joint_decision_view() == expected
    store.close()


def test_loaded_decoder_replacement_rejected_even_with_original_source_bytes(tmp_path, monkeypatch):
    stream, store, transition, _, start = setup(tmp_path / "db")
    execute(stream, transition, start + timedelta(seconds=2))

    def forged(self, observations, *, cutoff):
        return "bright"

    monkeypatch.setattr(BrightnessDecoder.decode, "__code__", forged.__code__)
    with pytest.raises(ValueError, match="decoder dependency changed"):
        stream.current_joint_decision_view()
    store.close()


def test_dictionary_permutation_retains_two_actual_measurements(tmp_path):
    stream, store, transition, _, start = setup(tmp_path / "db")
    _, _, _, delivery, _ = execute(stream, transition, start + timedelta(seconds=2))
    execute(stream, transition, delivery.received_at + timedelta(seconds=1), bright=True)
    expected = stream.current_joint_decision_view()
    assert len(expected.observation_evidence) == 2
    for name in ("_observation_commands", "_observation_status", "_raw"):
        setattr(stream, name, dict(reversed(tuple(getattr(stream, name).items()))))
    assert stream.current_joint_decision_view() == expected
    store.close()
