"""Configured producer integration, using explicit uncalibrated model fixtures.

Normal positive tests never manually stage particles: the collector calls the
producer. One complete-forgery attack deliberately prepopulates the old seam.


PYTEST_DONT_REWRITE: this module also supplies source-bound runtime model fixtures.
"""

from dataclasses import replace
from datetime import timedelta
from math import log
from uuid import UUID

import pytest
from test_continuous_camera_collection import Camera, Model
from test_continuous_state_recovery import DurableFixtureProducer, store_at
from test_structure_two_adaptive_runtime import (
    _adaptive_system_and_transition,
    _ciav_input,
    _features,
)
from test_structure_two_continuous_input import raw_for

from cpswm.system.continuous_camera_collection import collect_posterior_step
from cpswm.system.evaluation_operations.structure_two_selected_method import (
    NeuralParticleProposal,
    OrderedActorRole,
    ParticleRevisionReceipt,
    StructuredConstraint,
    StructuredWeightFactor,
    TypedParticleState,
)
from cpswm.system.native_joint_production import ProducedJointCandidates
from cpswm.system.reproducibility import content_sha256, content_uuid
from cpswm.system.structure_two_adaptive_runtime import AdaptiveExecutionContext
from cpswm.system.structure_two_conditional_updates import (
    ConditionalMeasurement,
    rebuild_conditional_state,
)
from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput, GroundedTransition
from cpswm.system.structure_two_particle_workspace import ConditionalAnalyticState


class JointFixture:
    """Deliberately assumed model; tests wiring, never empirical joint inference."""

    binding_sha256 = content_sha256("joint-fixture-priors-likelihoods-v1-not-calibrated")

    def __init__(self):
        self.calls = 0
        self.attack = None

    def checkpoint_state(self):
        return {"calls": self.calls}

    def restore_state(self, state):
        self.calls = state["calls"]

    def build_statistics(self, pid, parent, source, prior, measure, context):
        return rebuild_conditional_state(prior, (measure,))

    def produce(self, context):
        self.calls += 1
        source = context.source
        assert context.visible_prefix and source.transition.after.detection_time <= context.cutoff
        chains = [
            next(
                h
                for h in source.history_after.latest.hypotheses
                if len(h.steps) == 3 and h.responsible_actor_key == actor
            )
            for actor in ("owner", "unknown_actor")
        ]
        cluster = content_uuid("joint-fixture-cluster", source.source_id)
        statistics, receipts = {}, []
        weights = (
            {}
            if context.previous_batch is None
            else {
                x.particle_id: x.posterior_probability
                for x in context.previous_batch.particle_weights
            }
        )
        eye6 = tuple(tuple(float(i == j) for j in range(6)) for i in range(6))
        for index, chain in enumerate(chains):
            pid = content_uuid("joint-fixture-particle", (cluster, index))
            parent = next(
                (
                    x
                    for x in reversed(context.records)
                    if x.state.particle_id in weights
                    and x.state.ordered_actor_roles[0].actor_key == chain.responsible_actor_key
                ),
                None,
            )
            prior = (
                parent.statistics
                if parent
                else ConditionalAnalyticState(
                    source.locations,
                    (1.0,) * len(source.locations),
                    ((1.0, 0.0), (0.0, 1.0)),
                    (0.0, 0.0),
                    eye6,
                    (0.0,) * 6,
                )
            )
            measure = ConditionalMeasurement(
                cluster,
                (source.transition.after.metadata.record_id,),
                "fixture-assumed-rgb-pose",
                tuple(0.2 if i == index else 0.0 for i in range(len(source.locations))),
                (1.0, 0.5),
                0.3,
                0.8,
                (0.1, 0.2, 0.3, 0.0, 0.0, 0.0),
                eye6,
                eye6,
                0.6,
            )
            analytic = self.build_statistics(pid, parent, source, prior, measure, context)
            statistics[pid] = analytic
            state = TypedParticleState(
                particle_id=pid,
                parent_particle_id=parent.state.particle_id if parent else None,
                parent_revision_id=parent.state.revision_id if parent else None,
                source_snapshot_id=source.snapshot_id,
                event_hypothesis_id=chain.hypothesis_id,
                revision_id=source.history_after.latest.revision_id,
                ordered_actor_roles=tuple(
                    OrderedActorRole(role=role, actor_key=chain.responsible_actor_key)
                    for role in ("pickup_actor", "carrier", "placer")
                ),
                instance_association_key=str(source.object_instance_id)
                if index == 0
                else "unknown_instance",
                change_cause="unresolved",
                regime_decision="unresolved",
                regime_id=None,
                run_length=len(prior.evidence_cluster_ids),
                statistic_state_ref=analytic.reference,
                ledger_lineage_ref="hybrid-ledger:" + context.ledger_head_sha256,
            )
            receipt = ParticleRevisionReceipt(
                proposal=NeuralParticleProposal(
                    proposal_id=content_uuid("joint-fixture-proposal", pid),
                    evidence_cluster_id=cluster,
                    operation="branch" if parent else "preserve_unresolved",
                    source_particle_id=state.parent_particle_id,
                    source_snapshot_id=source.snapshot_id,
                    proposed_state=state,
                    proposal_log_probability=log(0.5),
                    proposer_model_version=(
                        "UNBOUND_NEURAL_MODEL"
                        if self.attack == "unbound_model"
                        else "explicit-prepared-candidates@1"
                    ),
                    proposer_code_version="fixture-v1",
                ),
                prior_log_weight=log(weights[parent.state.particle_id]) if parent else 0.0,
                transition_log_probability=0.0,
                observation_log_likelihood=0.0,
                constraints=tuple(
                    StructuredConstraint(factor=f, accepted=True, log_potential=0.0)
                    for f in StructuredWeightFactor
                    if f.value.endswith("constraint")
                ),
            )
            if index == 0:
                receipt = receipt.model_copy(
                    update={
                        "evidence_semantics": "posterior_projection_not_likelihood",
                        "source_posterior_snapshot_id": source.source_id,
                        "posterior_projection_log_factor": source.log_factor(receipt),
                    }
                )
            receipts.append(receipt)
        result = ProducedJointCandidates(
            context.content_sha256,
            source.source_id,
            source.body_sha256,
            self.binding_sha256,
            tuple(receipts),
            statistics,
            0.0,
        )
        if self.attack == "context":
            return replace(result, context_sha256="0" * 64)
        if self.attack == "source":
            return replace(result, source_posterior_id=UUID(int=999))
        if self.attack == "statistics":
            result.statistics.pop(next(iter(result.statistics)))
        if self.attack == "stale":
            r = result.receipts[0]
            result = replace(
                result,
                receipts=(
                    r.model_copy(
                        update={
                            "proposal": r.proposal.model_copy(
                                update={"source_snapshot_id": UUID(int=888)}
                            )
                        }
                    ),
                    *result.receipts[1:],
                ),
            )
        return result


def setup(path, joint=None):
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
        joint_producer=joint,
    )
    when = ciav.opportunity_time
    ids = stream.admit((raw_for(transition),), received_at=when)
    backend.output = GroundedTransition(transition, ids, "fixture", "fixture-not-calibrated")
    stream.advance(cutoff=when)
    assert stream._system.core._particle_workspace.batch is None
    return stream, store, transition, builder, when


def test_collector_automatically_builds_joint_and_executes_without_manual_stage(tmp_path):
    producer = JointFixture()
    stream, store, transition, _, when = setup(tmp_path / "db", producer)
    ledger = stream._system.core._hybrid_loop.ledger.export_state()
    model, camera = Model(stream), Camera(transition)
    result = collect_posterior_step(
        stream, model=model, executor=camera, decision_time=when + timedelta(seconds=2)
    )
    assert producer.calls == camera.calls == 1 and result.command.action == "RotateLeft"
    assert len(stream.current_joint_decision_view().atoms) == 2
    assert len(stream.visible_prefix(cutoff=result.delivery.received_at)) == 2
    assert stream._system.core._hybrid_loop.ledger.export_state() == ledger
    stream.produce_joint_posterior()
    assert producer.calls == 1
    store.close()


@pytest.mark.parametrize("attack", ["source", "statistics", "stale", "context", "unbound_model"])
def test_rejected_production_restores_producer_and_does_not_publish_or_change_ledger(
    tmp_path, attack
):
    producer = JointFixture()
    producer.attack = attack
    stream, store, _, _, _ = setup(tmp_path / "db", producer)
    before = stream._system.core.semantic_memory_identity()
    with pytest.raises(ValueError):
        stream.produce_joint_posterior()
    assert stream._system.core.semantic_memory_identity() == before and producer.calls == 0
    assert stream._system.core._particle_workspace.batch is None
    producer.attack = None
    stream.produce_joint_posterior()
    assert len(stream.current_joint_decision_view().atoms) == 2 and producer.calls == 1
    store.close()


def test_producer_checkpoint_and_artifact_binding_survive_recovery(tmp_path):
    path = tmp_path / "db"
    producer = JointFixture()
    stream, store, _, builder, _ = setup(path, producer)
    stream.produce_joint_posterior()
    old = stream.current_joint_decision_view()
    store.close()
    store = store_at(path)
    with pytest.raises(ValueError, match="joint producer dependency"):
        ContinuousEvidenceInput.resume(
            store, producer=DurableFixtureProducer(), context_builder=builder
        )
    bad = JointFixture()
    bad.binding_sha256 = "0" * 64
    with pytest.raises(ValueError, match="joint producer dependency"):
        ContinuousEvidenceInput.resume(
            store, producer=DurableFixtureProducer(), context_builder=builder, joint_producer=bad
        )
    new = JointFixture()
    restored = ContinuousEvidenceInput.resume(
        store, producer=DurableFixtureProducer(), context_builder=builder, joint_producer=new
    )
    restored.produce_joint_posterior()
    assert new.calls == 1 and restored.current_joint_decision_view() == old
    new.binding_sha256 = "0" * 64
    with pytest.raises(ValueError, match="dependency changed"):
        restored.produce_joint_posterior()
    store.close()


def test_missing_joint_model_preserves_explicit_unavailable_state(tmp_path):
    stream, store, _, _, _ = setup(tmp_path / "db")
    stream.produce_joint_posterior()
    with pytest.raises(ValueError, match="stale or missing"):
        stream.current_joint_decision_view()
    store.close()


def test_failed_checkpoint_requires_recovery_before_any_joint_action(tmp_path, monkeypatch):
    path = tmp_path / "db"
    producer = JointFixture()
    stream, store, _, builder, _ = setup(path, producer)

    def fail(_state):
        raise OSError("injected disk write failure")

    monkeypatch.setattr(store, "save", fail)
    with pytest.raises(OSError, match="disk write"):
        stream.produce_joint_posterior()
    with pytest.raises(RuntimeError, match="durable state failed"):
        stream.current_joint_decision_view()
    store.close()
    fresh_store = store_at(path)
    fresh_producer = JointFixture()
    restored = ContinuousEvidenceInput.resume(
        fresh_store,
        producer=DurableFixtureProducer(),
        context_builder=builder,
        joint_producer=fresh_producer,
    )
    assert restored._system.core._particle_workspace.batch is None
    restored.produce_joint_posterior()
    assert fresh_producer.calls == 1 and len(restored.current_joint_decision_view().atoms) == 2
    fresh_store.close()


def test_invalidated_native_revision_is_not_cleared_to_make_planning_succeed(tmp_path):
    producer = JointFixture()
    stream, store, _, _, _ = setup(tmp_path / "db", producer)
    stream.produce_joint_posterior()
    workspace = stream._system.core._particle_workspace
    ids = {r.state.revision_id for r in workspace.records.values()}
    workspace.invalidate_revisions(ids)
    with pytest.raises(ValueError, match="full particle revision replay"):
        stream.produce_joint_posterior()
    assert producer.calls == 1 and workspace.invalidated_revisions == ids
    store.close()


def test_two_semantic_steps_automatically_extend_real_ancestry_and_three_blocks(tmp_path):
    from structure_two_backbone_wiring_probe import BackboneWiringProbe, CIAVOutcomeKind

    probe = BackboneWiringProbe.build(seed=7)
    meta = probe.observed_days()[0].after.metadata
    joint, backend, store = JointFixture(), DurableFixtureProducer(), store_at(tmp_path / "db")

    def builder(system, item, when, step):
        probe.system = system
        probe.step_index = step
        return AdaptiveExecutionContext(
            router_features=probe.router_features(),
            step_index=step,
            ciav_input=probe.ciav_input(
                item.transition, outcome=CIAVOutcomeKind.DETECTED_DIFFERENT_LOCATION
            ),
        )

    stream = ContinuousEvidenceInput(
        system=probe.system,
        execution_lane="registered_p5_first",
        household_id=meta.household_id,
        session_id=meta.session_id,
        trace_id=meta.trace_id,
        producer=backend,
        context_builder=builder,
        state_store=store,
        joint_producer=joint,
    )
    previous = set()
    for index, day in enumerate(probe.observed_days()[:2]):
        transition = probe.transition_for(day)
        when = transition.after.detection_time + timedelta(minutes=1)
        ids = stream.admit((raw_for(transition),), received_at=when)
        backend.output = GroundedTransition(transition, ids, "oracle", "assumed-not-calibrated")
        stream.advance(cutoff=when)
        if index:
            with pytest.raises(ValueError, match="source changed"):
                stream.current_joint_decision_view()
        stream.produce_joint_posterior()
        view = stream.current_joint_decision_view()
        records = stream._system.core._particle_workspace.records
        for atom in view.atoms:
            record = records[atom.particle_id]
            assert len(record.statistics.information_vector) == 6
            assert len(record.statistics.evidence_cluster_ids) == index + 1
            assert record.statistics.a[0][0] > 1
            if index:
                assert record.state.parent_particle_id in previous
        previous = {a.particle_id for a in view.atoms}
        if index == 0:
            store.close()
            store = store_at(tmp_path / "db")
            joint, backend = JointFixture(), DurableFixtureProducer()
            stream = ContinuousEvidenceInput.resume(
                store, producer=backend, context_builder=builder, joint_producer=joint
            )
            assert joint.calls == 1
    assert joint.calls == 2
    store.close()


def test_complete_manually_staged_batch_cannot_impersonate_configured_production(tmp_path):
    from test_structure_two_w3_native_posterior_projection import projected

    producer = JointFixture()
    stream, store, _, _, _ = setup(tmp_path / "db", producer)
    # Adversarial prepopulation: valid complete legacy prepared input, but not
    # published by this configured producer. No normal positive uses this seam.
    stream._system.core.stage_prepared_particle_candidates(**projected(stream._system.core))
    for operation in (stream.produce_joint_posterior, stream.current_joint_decision_view):
        with pytest.raises(ValueError, match="not published by the configured joint producer"):
            operation()
    assert producer.calls == 0 and not stream.observation_history()
    store.close()
