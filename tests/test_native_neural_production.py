"""Actual checkpoint execution at the native consumer, on declared component data."""

from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from math import exp, fsum

import pytest
import torch
from test_continuous_camera_collection import Camera, Model
from test_native_joint_production import JointFixture, setup
from test_typed_proposal_training import data

from cpswm.data_preflight.proposal_decoder import TypedProposalDistribution
from cpswm.data_preflight.proposal_trainer import save_checkpoint, train_proposer
from cpswm.data_preflight.typed_proposal_networks import ARMS
from cpswm.system.continuous_camera_collection import collect_posterior_step
from cpswm.system.native_joint_production import NativeJointContext
from cpswm.system.native_neural_production import (
    NeuralNativeProducer,
    materialize,
)
from cpswm.system.structure_two_particle_workspace import native_content_sha256


@pytest.fixture(autouse=True)
def cpu_threads():
    old = torch.get_num_threads()
    torch.set_num_threads(2)
    yield
    torch.set_num_threads(old)


@pytest.fixture(scope="module")
def checkpoints(tmp_path_factory):
    root = tmp_path_factory.mktemp("native-neural-checkpoints")
    sample, support = data()
    result = {}
    for arm in ARMS:
        model, report = train_proposer(
            arm=arm,
            samples=(sample,),
            support_provider=lambda context: support,
            seed=0,
            optimizer_steps=2,
            max_seconds=60,
            learning_rate=0.001,
            fixture_diagnostic=True,
        )
        assert report["optimizer_steps"] == 2
        path = root / arm
        result[arm] = (path, save_checkpoint(model, report, path))
    return result


def context_for(stream, when):
    core = stream._system.core
    workspace = core._particle_workspace
    return NativeJointContext(
        core.current_posterior_projection_source(),
        workspace.batch,
        tuple(workspace.records.values()),
        core._hybrid_loop.ledger.export_state().manifest.head_hash,
        stream.visible_prefix(cutoff=when),
        when,
        previous_weight_evidence=workspace.previous_weight_evidence(workspace.batch)
        if workspace.raw_candidate_profile is not None
        else None,
    )


def stage(stream, produced):
    return stream._system.core.stage_prepared_particle_candidates(
        receipts=produced.receipts,
        statistics=produced.statistics,
        unresolved_log_weight=produced.unresolved_log_weight,
        neural_evidence=produced.neural_evidence,
    )


@pytest.mark.parametrize("arm", ARMS)
def test_real_checkpoint_to_native_joint_and_camera_with_exact_enumeration(
    tmp_path, checkpoints, arm
):
    path, pin = checkpoints[arm]
    producer = NeuralNativeProducer(JointFixture(), path, manifest_sha256=pin)
    stream, store, transition, _, when = setup(tmp_path / "db", producer)
    before = stream._system.core._hybrid_loop.ledger.export_state()
    result = collect_posterior_step(
        stream,
        model=Model(stream),
        executor=Camera(transition),
        decision_time=when + timedelta(seconds=2),
    )
    assert result.command.action == "RotateLeft"
    view = stream.current_joint_decision_view()
    assert len(view.atoms) == 2 and producer.calls == 1
    workspace = stream._system.core._particle_workspace
    receipts = workspace.receipts
    assert all(
        r.proposal.proposer_model_version.startswith("typed-development-checkpoint:")
        for r in receipts
    )
    assert fsum(exp(r.proposal.proposal_log_probability) for r in receipts) == pytest.approx(
        1, abs=1e-12
    )
    # Independent target-density sum. q must cancel because this is enumeration,
    # not a stochastic draw; old divide-by-q would change this posterior.
    masses = [
        exp(
            r.prior_log_weight
            + r.transition_log_probability
            + r.observation_log_likelihood
            + r.posterior_projection_log_factor
            + fsum(c.log_potential for c in r.constraints)
        )
        for r in receipts
    ]
    total = fsum((1.0, *masses))
    assert [w.posterior_probability for w in workspace.batch.particle_weights] == pytest.approx(
        [m / total for m in masses], abs=1e-14
    )
    assert view.unresolved_probability == pytest.approx(1 / total, abs=1e-14)
    assert stream._system.core._hybrid_loop.ledger.export_state() == before
    stream.produce_joint_posterior()
    assert producer.calls == 1
    store.close()


@pytest.mark.parametrize(
    "attack", ["probabilities", "measure", "ancestor", "weights", "proof_omitted"]
)
def test_complete_forged_neural_outputs_rejected_before_native_mutation(
    tmp_path, checkpoints, attack
):
    path, pin = checkpoints[ARMS[0]]
    producer = NeuralNativeProducer(JointFixture(), path, manifest_sha256=pin)
    stream, store, _, _, when = setup(tmp_path / "db", producer)
    produced = producer.produce(context_for(stream, when))
    evidence = produced.neural_evidence
    if attack == "probabilities":
        context, support = evidence.context, evidence.support
        d = TypedProposalDistribution(
            context=context,
            runtime_candidates=support,
            scorer=lambda context, axis, prefix, choices, **kwargs: torch.zeros(len(choices)),
        )
        evidence = replace(evidence, scored=tuple(d.decode(k) for k in d.target_sha256s))
        produced = replace(
            produced,
            neural_evidence=evidence,
            receipts=materialize(evidence.base_candidates, evidence),
        )
    elif attack == "measure":
        produced = replace(
            produced,
            receipts=tuple(
                r.model_copy(update={"integration_log_weight": 0.0}) for r in produced.receipts
            ),
        )
    elif attack == "ancestor":
        evidence = replace(
            evidence, base_candidates=replace(evidence.base_candidates, context_sha256="0" * 64)
        )
        produced = replace(produced, neural_evidence=evidence)
    elif attack == "weights":
        # A self-consistent changed receipt still differs from the executed proof.
        r = produced.receipts[0]
        produced = replace(
            produced,
            receipts=(
                r.model_copy(update={"transition_log_probability": -1.0}),
                *produced.receipts[1:],
            ),
        )
    else:
        produced = replace(produced, neural_evidence=None)
    core = stream._system.core
    before = native_content_sha256(core._particle_workspace.state_payload())
    ledger = core._hybrid_loop.ledger.export_state()
    with pytest.raises(ValueError):
        stage(stream, produced)
    assert native_content_sha256(core._particle_workspace.state_payload()) == before
    assert core._hybrid_loop.ledger.export_state() == ledger
    assert core._particle_workspace.batch is None
    store.close()


def test_prepared_candidate_cannot_add_an_unverified_quadrature_coefficient(tmp_path):
    producer = JointFixture()
    stream, store, _, _, when = setup(tmp_path / "db", producer)
    produced = producer.produce(context_for(stream, when))
    produced = replace(
        produced,
        receipts=tuple(
            r.model_copy(update={"integration_log_weight": -1}) for r in produced.receipts
        ),
    )
    with pytest.raises(ValueError, match="integration measure"):
        stage(stream, produced)
    assert stream._system.core._particle_workspace.batch is None
    store.close()


def test_real_network_scores_for_forged_visible_input_do_not_authorize_publication(
    tmp_path, checkpoints
):
    path, pin = checkpoints[ARMS[1]]
    producer = NeuralNativeProducer(JointFixture(), path, manifest_sha256=pin)
    stream, store, _, _, when = setup(tmp_path / "db", producer)
    original = producer.produce(context_for(stream, when))
    proof = original.neural_evidence
    actual = proof.context.visible.detections[0]
    alternative = next(
        loc.location_entity_id
        for loc in proof.context.location_support
        if loc.location_entity_id is not None
        and loc.location_entity_id != actual.detected_location_id
    )
    fake_detection = actual.model_copy(update={"detected_location_id": alternative})
    fake_context = proof.context.model_copy(
        update={
            "visible": proof.context.visible.model_copy(update={"detections": (fake_detection,)})
        }
    )
    scored = producer._session.score_support(context=fake_context, support=proof.support)
    proof = replace(proof, context=fake_context, scored=scored)
    forged = replace(
        original, neural_evidence=proof, receipts=materialize(proof.base_candidates, proof)
    )
    core = stream._system.core
    before = native_content_sha256(core._particle_workspace.state_payload())
    with pytest.raises(ValueError, match="actual native history"):
        stage(stream, forged)
    assert native_content_sha256(core._particle_workspace.state_payload()) == before
    stage(stream, original)
    assert core.prepared_particle_location_marginal()
    store.close()


def test_changed_complete_stored_proof_is_rechecked_after_its_hashes_are_resealed(
    tmp_path, checkpoints
):
    from cpswm.system.evaluation_operations.structure_two_selected_method import (
        normalize_particle_revisions,
    )

    path, pin = checkpoints[ARMS[0]]
    producer = NeuralNativeProducer(JointFixture(), path, manifest_sha256=pin)
    stream, store, _, _, _ = setup(tmp_path / "db", producer)
    stream.produce_joint_posterior()
    original = stream.current_joint_decision_view()
    workspace = stream._system.core._particle_workspace
    cluster = workspace.batch.evidence_cluster_id
    body = workspace.input_bodies[cluster]
    proof = body.neural_evidence
    d = TypedProposalDistribution(
        context=proof.context,
        runtime_candidates=proof.support,
        scorer=lambda context, axis, prefix, choices, **kwargs: torch.zeros(len(choices)),
    )
    proof = replace(proof, scored=tuple(d.decode(k) for k in d.target_sha256s))
    changed_receipts = materialize(proof.base_candidates, proof)
    forged = replace(body, neural_evidence=proof, receipts=changed_receipts)
    # Rebuild every public consistency hash and numeric batch, not just one field.
    before = deepcopy(workspace.__dict__)
    try:
        fingerprint = native_content_sha256(forged)
        workspace.input_bodies[cluster] = forged
        workspace.input_journal[cluster] = fingerprint
        workspace.receipts = changed_receipts
        workspace.batch = normalize_particle_revisions(
            changed_receipts, unresolved_log_weight=body.unresolved_log_weight
        )
        workspace.records = {
            key: replace(record, input_fingerprint_sha256=fingerprint)
            for key, record in workspace.records.items()
        }
        with pytest.raises(ValueError, match="checkpoint recomputation"):
            workspace.state_payload()
        with pytest.raises(ValueError):
            stream.current_joint_decision_view()
    finally:
        workspace.__dict__.clear()
        workspace.__dict__.update(before)
    assert stream.current_joint_decision_view() == original
    store.close()
