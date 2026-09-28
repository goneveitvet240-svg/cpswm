"""Second attack surface: multi-step correction, real checkpoint recovery and roots."""

from dataclasses import replace

import pytest
from test_native_joint_full_replay import corrected
from test_native_joint_production import JointFixture, setup
from test_native_neural_production import checkpoints as _checkpoint_fixture
from test_native_neural_production import context_for, stage
from test_native_neural_production import cpu_threads as _thread_fixture

from cpswm.data_preflight.typed_proposal_networks import ARMS
from cpswm.system.evaluation_operations.structure_two_selected_method import (
    ParticleProposalOperation,
)
from cpswm.system.native_neural_production import NeuralNativeProducer
from cpswm.system.structure_two_particle_workspace import native_content_sha256

checkpoints = _checkpoint_fixture
cpu_threads = _thread_fixture


class OpenWorldJointFixture(JointFixture):
    """The controlled candidate model explicitly retains the unresolved operation."""

    def produce(self, context):
        base = super().produce(context)
        receipts = tuple(
            r.model_copy(
                update={
                    "proposal": r.proposal.model_copy(
                        update={
                            "operation": ParticleProposalOperation.PRESERVE_UNRESOLVED,
                        }
                    )
                }
            )
            if r.proposal.proposed_state.instance_association_key == "unknown_instance"
            else r
            for r in base.receipts
        )
        return replace(base, receipts=receipts)


def test_neural_full_history_correction_restores_exact_joint_state(tmp_path, checkpoints):
    from run_correction_replay_comparison import OracleProducer

    from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput

    path, pin = checkpoints[ARMS[1]]
    joint = NeuralNativeProducer(OpenWorldJointFixture(), path, manifest_sha256=pin)
    _, _, stream, store, builder, _, before = corrected(tmp_path / "online.db", joint)
    try:
        core = stream._system.core
        assert joint.calls == 12
        ledger = core._hybrid_loop.ledger.export_state()
        with pytest.raises(ValueError):
            stream.current_joint_decision_view()
        stream.replay_joint_posterior()
        after = stream.current_joint_decision_view()
        assert joint.calls == 11 and after != before
        assert all(len(a.statistics.evidence_cluster_ids) == 11 for a in after.atoms)
        assert core._hybrid_loop.ledger.export_state() == ledger
        restored_joint = NeuralNativeProducer(OpenWorldJointFixture(), path, manifest_sha256=pin)
        restored = ContinuousEvidenceInput.resume(
            store, producer=OracleProducer(), context_builder=builder, joint_producer=restored_joint
        )
        assert restored.current_joint_decision_view() == after
        assert restored_joint.checkpoint_state() == joint.checkpoint_state()
        # Representation order is not update order. The ancestor graph defines it.
        workspace = restored._system.core._particle_workspace
        workspace.records = dict(reversed(tuple(workspace.records.items())))
        workspace.input_journal = dict(reversed(tuple(workspace.input_journal.items())))
        workspace.input_bodies = dict(reversed(tuple(workspace.input_bodies.items())))
        assert restored.current_joint_decision_view() == after
    finally:
        store.close()


def test_other_real_checkpoint_cannot_self_reseal_as_configured_model(tmp_path, checkpoints):
    path, pin = checkpoints[ARMS[0]]
    good = NeuralNativeProducer(JointFixture(), path, manifest_sha256=pin)
    stream, store, _, _, when = setup(tmp_path / "db", good)
    other_path, other_pin = checkpoints[ARMS[1]]
    other = NeuralNativeProducer(JointFixture(), other_path, manifest_sha256=other_pin)
    forged = other.produce(context_for(stream, when))
    core = stream._system.core
    state = native_content_sha256(core._particle_workspace.state_payload())
    with pytest.raises(ValueError, match="configured producer"):
        stage(stream, forged)
    assert native_content_sha256(core._particle_workspace.state_payload()) == state
    with pytest.raises(ValueError, match="cannot replace"):
        core.configure_native_joint_dependency(other.binding_sha256)
    stage(stream, good.produce(context_for(stream, when)))
    assert core.prepared_particle_location_marginal()
    store.close()


def test_changed_context_with_valid_neural_probabilities_cannot_publish(tmp_path, checkpoints):
    path, pin = checkpoints[ARMS[0]]
    producer = NeuralNativeProducer(JointFixture(), path, manifest_sha256=pin)
    stream, store, _, _, when = setup(tmp_path / "db", producer)
    actual = context_for(stream, when)
    # Recompute the whole proposal/probability package under another ledger view.
    forged_context = replace(actual, ledger_head_sha256="d" * 64)
    forged = producer.produce(forged_context)
    before = native_content_sha256(stream._system.core._particle_workspace.state_payload())
    with pytest.raises(ValueError):
        stage(stream, forged)
    assert native_content_sha256(stream._system.core._particle_workspace.state_payload()) == before
    store.close()


def test_loaded_verifier_replacement_cannot_publish_a_complete_forgery(
    tmp_path, checkpoints, monkeypatch
):
    import torch

    import cpswm.system.native_neural_production as module
    from cpswm.data_preflight.proposal_decoder import TypedProposalDistribution

    path, pin = checkpoints[ARMS[0]]
    producer = NeuralNativeProducer(JointFixture(), path, manifest_sha256=pin)
    stream, store, _, _, when = setup(tmp_path / "db", producer)
    original = producer.produce(context_for(stream, when))
    proof = original.neural_evidence
    d = TypedProposalDistribution(
        context=proof.context,
        runtime_candidates=proof.support,
        scorer=lambda context, axis, prefix, choices, **kwargs: torch.zeros(len(choices)),
    )
    proof = replace(proof, scored=tuple(d.decode(k) for k in d.target_sha256s))
    forged = replace(
        original, neural_evidence=proof, receipts=module.materialize(proof.base_candidates, proof)
    )
    assert proof.scored != original.neural_evidence.scored
    before = native_content_sha256(stream._system.core._particle_workspace.state_payload())

    def bypass(evidence):
        return None

    try:
        with monkeypatch.context() as patch:
            patch.setattr(module.verify_neural_evidence, "__code__", bypass.__code__)
            with pytest.raises(ValueError, match=r"implementation|loaded|source"):
                stage(stream, forged)
        assert (
            native_content_sha256(stream._system.core._particle_workspace.state_payload()) == before
        )
        stage(stream, original)
        assert stream._system.core.prepared_particle_location_marginal()
    finally:
        store.close()
