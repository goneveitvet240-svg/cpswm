"""N3 adversarial tests for structure-two scheme B."""

from __future__ import annotations

import threading
from uuid import UUID, uuid4

import numpy as np
import pytest

from cpswm.system.continual import (
    ConsolidationRiskCertificate,
    DirichletRLSFusion,
    HybridConsolidationState,
    HybridLedgerError,
    HybridPromotion,
    HybridQuarantineSupersession,
    HybridReversal,
    HybridStatisticDelta,
    HybridStatisticLedger,
    StatisticKey,
)
from cpswm.world_model.grounded_search import (
    BayesianRisk,
    BridgeSupervision,
    BridgeSupervisionSource,
    ConstrainedDependencyBridge,
    ConstrainedVOISelector,
    ExactObservationAssessment,
    LearnedVOIProxy,
    MapTaskCoordinator,
    ObservationCandidate,
    TaskAction,
    TaskActionGraph,
    VersionedBeliefMap,
    VersionSwitchKind,
)

KEY = StatisticKey(
    actor_key="owner",
    object_instance_id=UUID(int=101),
    regime_id="weekday",
    parameter_block="location_residual",
    location_id=UUID(int=102),
)
AUTH = UUID(int=103)
KEY_2 = StatisticKey(
    actor_key=KEY.actor_key,
    object_instance_id=KEY.object_instance_id,
    regime_id=KEY.regime_id,
    parameter_block=KEY.parameter_block,
    location_id=UUID(int=104),
)


def _risk(*, subject, violations=()):
    return ConsolidationRiskCertificate(
        expected_task_loss=0.1,
        uncertainty_penalty=0.1,
        maximum_allowed_risk=0.5,
        exact_verifier_id="counterfactual@test",
        counterfactual_id=uuid4(),
        subject_delta_record_id=subject,
        belief_snapshot_id=uuid4(),
        map_version=1,
        hard_safety_violations=violations,
    )


def _delta(
    *,
    x=(1.0, 0.0),
    y=1.0,
    weight=1.0,
    alpha=1.0,
    watermark=0,
    event=None,
    revision=None,
    parent=None,
    cluster=None,
    dedup=None,
    state=HybridConsolidationState.PROMOTED,
    auth=AUTH,
    key=KEY,
    source_records=None,
):
    return HybridStatisticDelta.from_weighted_sample(
        x=np.asarray(x),
        y=y,
        weight=weight,
        delta_alpha=alpha,
        information_weight=weight,
        record_id=uuid4(),
        event_hypothesis_id=event or uuid4(),
        revision_id=revision or uuid4(),
        parent_revision_id=parent,
        evidence_cluster_id=cluster or uuid4(),
        semantic_dedup_id=dedup or str(uuid4()),
        source_record_ids=source_records or (uuid4(),),
        authorization_scope_id=auth,
        key=key,
        input_watermark=watermark,
        model_version="scheme-b@test",
        code_version="git:test",
        initial_state=state,
    )


def test_natural_statistics_equal_fair_batch_ridge():
    ridge = 0.25
    ledger = HybridStatisticLedger(feature_dim=2, ridge=ridge)
    samples = [((1.0, 2.0), 3.0, 0.5), ((-1.0, 1.0), -2.0, 2.0)]
    for watermark, (x, y, weight) in enumerate(samples):
        ledger.append_delta(_delta(x=x, y=y, weight=weight, watermark=watermark))

    projected = ledger.projection(KEY)
    design = np.asarray([sample[0] for sample in samples])
    targets = np.asarray([sample[1] for sample in samples])
    weights = np.diag([sample[2] for sample in samples])
    expected_a = ridge * np.eye(2) + design.T @ weights @ design
    expected_b = design.T @ weights @ targets
    assert np.allclose(projected.a, expected_a)
    assert np.allclose(projected.b, expected_b)
    assert np.allclose(projected.theta, np.linalg.solve(expected_a, expected_b))
    assert projected.alpha == pytest.approx(2.0)
    ledger.assert_cache_matches_replay(KEY)


def test_source_cluster_exclusion_prevents_self_training_residual():
    ledger = HybridStatisticLedger(feature_dim=2, ridge=1.0)
    cluster_a, cluster_b = uuid4(), uuid4()
    first = _delta(x=(1.0, 0.0), y=2.0, watermark=0, cluster=cluster_a)
    second = _delta(x=(0.0, 1.0), y=5.0, watermark=1, cluster=cluster_b)
    ledger.append_delta(first)
    ledger.append_delta(second)

    full = ledger.projection(KEY)
    excluded = ledger.projection(KEY, exclude_evidence_cluster_id=cluster_b)
    assert full.b.tolist() == [2.0, 5.0]
    assert excluded.b.tolist() == [2.0, 0.0]
    assert excluded.alpha == pytest.approx(1.0)


def test_multi_key_evidence_cluster_is_promoted_atomically_and_excluded_as_a_bundle():
    ledger = HybridStatisticLedger(feature_dim=2)
    cluster, event, revision = uuid4(), uuid4(), uuid4()
    sources = (uuid4(),)
    first = _delta(
        key=KEY,
        cluster=cluster,
        event=event,
        revision=revision,
        source_records=sources,
        state=HybridConsolidationState.QUARANTINED,
        watermark=0,
    )
    second = _delta(
        key=KEY_2,
        cluster=cluster,
        event=event,
        revision=revision,
        source_records=sources,
        state=HybridConsolidationState.QUARANTINED,
        watermark=1,
    )
    ledger.append_delta(first)
    ledger.append_delta(second)
    with pytest.raises(HybridLedgerError, match="atomic promote_cluster"):
        ledger.promote(
            HybridPromotion(
                record_id=uuid4(),
                promotes_record_id=first.record_id,
                input_watermark=2,
                authorization_scope_id=AUTH,
                reason="partial promotion is forbidden",
                risk_certificate=_risk(subject=first.record_id),
            )
        )
    ledger.promote_cluster(
        evidence_cluster_id=cluster,
        promotions=(
            HybridPromotion(
                record_id=uuid4(),
                promotes_record_id=first.record_id,
                input_watermark=2,
                authorization_scope_id=AUTH,
                reason="atomic cluster promotion",
                risk_certificate=_risk(subject=first.record_id),
            ),
            HybridPromotion(
                record_id=uuid4(),
                promotes_record_id=second.record_id,
                input_watermark=2,
                authorization_scope_id=AUTH,
                reason="atomic cluster promotion",
                risk_certificate=_risk(subject=second.record_id),
            ),
        ),
    )
    assert ledger.projection(KEY).alpha == 1.0
    assert ledger.projection(KEY_2).alpha == 1.0
    assert ledger.projection(KEY, exclude_evidence_cluster_id=cluster).alpha == 0.0
    assert ledger.projection(KEY_2, exclude_evidence_cluster_id=cluster).alpha == 0.0


def test_dirichlet_base_and_rls_contextual_residual_are_fused_and_normalized():
    ledger = HybridStatisticLedger(feature_dim=2, ridge=1.0)
    cluster = uuid4()
    ledger.append_delta(_delta(x=(1.0, 0.0), y=1.0, alpha=3.0, watermark=0, cluster=cluster))
    ledger.append_delta(_delta(x=(1.0, 0.0), y=-1.0, alpha=1.0, watermark=1, key=KEY_2))
    fusion = DirichletRLSFusion()
    prediction = fusion.predict(
        ledger,
        keys=(KEY, KEY_2),
        context_features=np.asarray((1.0, 0.0)),
    )
    assert prediction[KEY.location_id].base_probability == pytest.approx(0.75)
    assert prediction[KEY_2.location_id].base_probability == pytest.approx(0.25)
    assert sum(value.fused_probability for value in prediction.values()) == pytest.approx(1.0)
    assert (
        prediction[KEY.location_id].fused_probability > prediction[KEY.location_id].base_probability
    )

    excluded = fusion.predict(
        ledger,
        keys=(KEY, KEY_2),
        context_features=np.asarray((1.0, 0.0)),
        exclude_evidence_cluster_id=cluster,
    )
    assert excluded[KEY.location_id].base_probability == 0.0
    assert excluded[KEY_2.location_id].base_probability == 1.0


def test_quarantine_promote_retract_and_corrected_revision_state_machine():
    ledger = HybridStatisticLedger(feature_dim=2)
    event, first_revision = uuid4(), uuid4()
    first = _delta(
        watermark=0,
        event=event,
        revision=first_revision,
        state=HybridConsolidationState.QUARANTINED,
    )
    ledger.append_delta(first)
    assert ledger.state_of(first.record_id) == HybridConsolidationState.QUARANTINED
    assert ledger.projection(KEY).alpha == 0.0

    ledger.promote(
        HybridPromotion(
            record_id=uuid4(),
            promotes_record_id=first.record_id,
            input_watermark=1,
            authorization_scope_id=AUTH,
            reason="risk gate passed",
            risk_certificate=_risk(subject=first.record_id),
        )
    )
    assert ledger.state_of(first.record_id) == HybridConsolidationState.PROMOTED
    ledger.retract(
        HybridReversal(
            record_id=uuid4(),
            reverses_record_id=first.record_id,
            revision_id=first_revision,
            input_watermark=2,
            authorization_scope_id=AUTH,
            reason="ORRER correction",
        )
    )
    assert ledger.state_of(first.record_id) == HybridConsolidationState.RETRACTED

    corrected = _delta(
        x=(0.0, 1.0),
        y=3.0,
        watermark=3,
        event=event,
        revision=uuid4(),
        parent=first_revision,
    )
    ledger.append_delta(corrected)
    assert ledger.state_of(corrected.record_id) == HybridConsolidationState.REACTIVATED
    assert ledger.projection(KEY).b.tolist() == [0.0, 3.0]
    ledger.assert_cache_matches_replay(KEY)


def test_quarantined_revision_can_only_be_replaced_by_its_bound_successor():
    ledger = HybridStatisticLedger(feature_dim=2)
    event, old_revision, successor = uuid4(), uuid4(), uuid4()
    old = _delta(
        event=event,
        revision=old_revision,
        state=HybridConsolidationState.QUARANTINED,
        watermark=0,
    )
    ledger.append_delta(old)
    ledger.supersede_quarantined_revision(
        HybridQuarantineSupersession(
            record_id=uuid4(),
            supersedes_revision_id=old_revision,
            successor_revision_id=successor,
            event_hypothesis_id=event,
            input_watermark=1,
            authorization_scope_id=AUTH,
            reason="ORRER corrected unresolved revision",
        )
    )
    assert ledger.state_of(old.record_id) == HybridConsolidationState.RETRACTED
    with pytest.raises(HybridLedgerError, match="does not match quarantine successor"):
        ledger.append_delta(
            _delta(
                event=event,
                revision=uuid4(),
                parent=old_revision,
                watermark=2,
            )
        )
    corrected = _delta(
        event=event,
        revision=successor,
        parent=old_revision,
        watermark=2,
    )
    ledger.append_delta(corrected)
    assert ledger.state_of(corrected.record_id) == HybridConsolidationState.REACTIVATED


def test_illegal_lineage_state_and_source_operations_are_rejected():
    ledger = HybridStatisticLedger(feature_dim=2)
    quarantined = _delta(watermark=0, state=HybridConsolidationState.QUARANTINED)
    ledger.append_delta(quarantined)
    with pytest.raises(HybridLedgerError, match="only a promoted"):
        ledger.retract(
            HybridReversal(
                record_id=uuid4(),
                reverses_record_id=quarantined.record_id,
                revision_id=quarantined.revision_id,
                input_watermark=1,
                authorization_scope_id=AUTH,
                reason="illegal",
            )
        )
    with pytest.raises(HybridLedgerError, match="authorization"):
        ledger.promote(
            HybridPromotion(
                record_id=uuid4(),
                promotes_record_id=quarantined.record_id,
                input_watermark=1,
                authorization_scope_id=uuid4(),
                reason="wrong scope",
                risk_certificate=_risk(subject=quarantined.record_id),
            )
        )

    with pytest.raises(HybridLedgerError, match="risk gate rejected"):
        ledger.promote(
            HybridPromotion(
                record_id=uuid4(),
                promotes_record_id=quarantined.record_id,
                input_watermark=1,
                authorization_scope_id=AUTH,
                reason="unsafe",
                risk_certificate=_risk(
                    subject=quarantined.record_id,
                    violations=("privacy floor",),
                ),
            )
        )

    with pytest.raises(HybridLedgerError, match="bound to another delta"):
        ledger.promote(
            HybridPromotion(
                record_id=uuid4(),
                promotes_record_id=quarantined.record_id,
                input_watermark=1,
                authorization_scope_id=AUTH,
                reason="reused certificate",
                risk_certificate=_risk(subject=uuid4()),
            )
        )

    promoted = _delta(watermark=1)
    ledger.append_delta(promoted)
    with pytest.raises(HybridLedgerError, match="revision does not match"):
        ledger.retract(
            HybridReversal(
                record_id=uuid4(),
                reverses_record_id=promoted.record_id,
                revision_id=uuid4(),
                input_watermark=2,
                authorization_scope_id=AUTH,
                reason="wrong revision",
            )
        )
    with pytest.raises(HybridLedgerError, match="parent revision does not exist"):
        ledger.append_delta(_delta(watermark=2, parent=uuid4()))
    with pytest.raises(HybridLedgerError, match="duplicate evidence_cluster_id"):
        ledger.append_delta(
            _delta(watermark=2, cluster=promoted.evidence_cluster_id, dedup="new-dedup")
        )


def test_numerically_unreliable_projection_requires_replay_instead_of_clipping():
    ledger = HybridStatisticLedger(
        feature_dim=2,
        ridge=1e-12,
        max_condition_number=10.0,
    )
    ledger.append_delta(_delta(x=(1.0, 0.0), watermark=0))
    projection = ledger.projection(KEY)
    assert projection.replay_required
    assert np.isnan(projection.theta).all()


class _PayloadRiskVerifier:
    def assess(self, action, snapshot):
        nodes = snapshot.node_map()
        payload = nodes.get("target")
        door = nodes.get("door")
        if door is not None and door.payload_hash == "blocked" and action.action_id == "navigate":
            return BayesianRisk(0.0, 0.0, ("blocked path",))
        target_loss = (
            1.0
            if payload is not None
            and payload.payload_hash == "moved"
            and action.action_id == "grasp"
            else 0.0
        )
        return BayesianRisk(target_loss, 0.0)


def _task_graph():
    return TaskActionGraph(
        task_id=uuid4(),
        actions=(
            TaskAction("navigate", 0, hard_read_nodes=frozenset({"door"})),
            TaskAction("grasp", 1, hard_read_nodes=frozenset({"target"})),
            TaskAction("deliver", 2, hard_write_nodes=frozenset({"destination"})),
        ),
    )


def test_action_level_map_version_switch_replans_only_affected_suffix():
    belief_map = VersionedBeliefMap()
    old = belief_map.apply_update(
        {
            "door": ("open", 0.0),
            "target": ("present", 0.1),
            "destination": ("free", 0.0),
        }
    )
    new = belief_map.apply_update({"target": ("moved", 0.8)})
    decision = MapTaskCoordinator().evaluate_switch(
        task=_task_graph(),
        current_action_order=0,
        old_snapshot=old,
        new_snapshot=new,
        verifier=_PayloadRiskVerifier(),
    )
    assert decision.kind == VersionSwitchKind.REPLAN_SUFFIX
    assert decision.replan_from_order == 1
    assert decision.impacted_action_ids == ("grasp", "deliver")


def test_irrelevant_update_continues_but_hard_safety_change_cancels():
    belief_map = VersionedBeliefMap()
    old = belief_map.apply_update(
        {"door": ("open", 0.0), "target": ("present", 0.1), "other": ("a", 0.0)}
    )
    irrelevant = belief_map.apply_update({"other": ("b", 0.0)})
    coordinator = MapTaskCoordinator()
    continued = coordinator.evaluate_switch(
        task=_task_graph(),
        current_action_order=0,
        old_snapshot=old,
        new_snapshot=irrelevant,
        verifier=_PayloadRiskVerifier(),
    )
    assert continued.kind == VersionSwitchKind.CONTINUE

    blocked = belief_map.apply_update({"door": ("blocked", 0.0)})
    cancelled = coordinator.evaluate_switch(
        task=_task_graph(),
        current_action_order=0,
        old_snapshot=irrelevant,
        new_snapshot=blocked,
        verifier=_PayloadRiskVerifier(),
    )
    assert cancelled.kind == VersionSwitchKind.CANCEL


def test_map_batch_publication_is_atomic_under_concurrent_reads():
    belief_map = VersionedBeliefMap()
    failures: list[int] = []
    stop = threading.Event()

    def writer():
        for index in range(40):
            belief_map.apply_update(
                {
                    f"a-{index}": (str(index), 0.0),
                    f"b-{index}": (str(index), 0.0),
                }
            )
        stop.set()

    thread = threading.Thread(target=writer)
    thread.start()
    while not stop.is_set():
        snapshot = belief_map.snapshot()
        if len(snapshot.nodes) % 2:
            failures.append(snapshot.map_version)
    thread.join()
    assert failures == []
    assert len(belief_map.snapshot().nodes) == 80


def test_belief_snapshot_hash_rejects_forged_content():
    snapshot = VersionedBeliefMap().apply_update({"target": ("present", 0.1)})
    with pytest.raises(ValueError, match="content hash mismatch"):
        type(snapshot)(
            snapshot_id=snapshot.snapshot_id,
            map_version=snapshot.map_version,
            nodes=snapshot.nodes,
            content_hash="0" * 64,
        )


def test_hard_bridge_edge_cannot_be_deleted_and_soft_labels_expand_candidates():
    hard = BridgeSupervision(
        action_id="grasp",
        belief_node_id="target",
        relevant=True,
        confidence=1.0,
        source=BridgeSupervisionSource.SYMBOLIC_RULE,
        source_record_id=uuid4(),
        hard_rule=True,
    )
    bridge = ConstrainedDependencyBridge([hard])
    bridge.add_supervision(
        BridgeSupervision(
            action_id="grasp",
            belief_node_id="unexpected-container",
            relevant=True,
            confidence=0.9,
            source=BridgeSupervisionSource.ACTIVE_INTERVENTION,
            source_record_id=uuid4(),
        )
    )
    assert bridge.candidates("grasp", soft_threshold=0.8) == {
        "target",
        "unexpected-container",
    }
    bridge.add_supervision(
        BridgeSupervision(
            action_id="grasp",
            belief_node_id="unexpected-container",
            relevant=False,
            confidence=1.0,
            source=BridgeSupervisionSource.RGRC_REVISION,
            source_record_id=uuid4(),
        )
    )
    assert bridge.candidates("grasp", soft_threshold=0.8) == {"target"}
    with pytest.raises(ValueError, match="cannot be deleted"):
        bridge.add_supervision(
            BridgeSupervision(
                action_id="grasp",
                belief_node_id="target",
                relevant=False,
                confidence=1.0,
                source=BridgeSupervisionSource.SYMBOLIC_RULE,
                source_record_id=uuid4(),
                hard_rule=True,
            )
        )


def test_explicit_dependency_bridge_participates_in_version_switch():
    belief_map = VersionedBeliefMap()
    old = belief_map.apply_update({"unexpected": ("old", 0.0)})
    new = belief_map.apply_update({"unexpected": ("new", 1.0)})
    task = TaskActionGraph(task_id=uuid4(), actions=(TaskAction("inspect", 0),))
    bridge = ConstrainedDependencyBridge(
        [
            BridgeSupervision(
                action_id="inspect",
                belief_node_id="unexpected",
                relevant=True,
                confidence=1.0,
                source=BridgeSupervisionSource.SYMBOLIC_RULE,
                source_record_id=uuid4(),
                hard_rule=True,
            )
        ]
    )

    class _Verifier:
        def assess(self, action, snapshot):
            del action
            loss = 1.0 if snapshot.node_map()["unexpected"].payload_hash == "new" else 0.0
            return BayesianRisk(loss, 0.0)

    decision = MapTaskCoordinator().evaluate_switch(
        task=task,
        current_action_order=0,
        old_snapshot=old,
        new_snapshot=new,
        verifier=_Verifier(),
        dependency_bridge=bridge,
    )
    assert decision.kind == VersionSwitchKind.REPLAN_SUFFIX


class _OfflineProxy:
    def predict_risk_reduction(self, candidate, belief_snapshot, task_graph):
        del belief_snapshot, task_graph
        return 100.0 if candidate.action_id == "unsafe" else 5.0


class _ExactObservationVerifier:
    def assess(self, candidate, belief_snapshot, task_graph):
        del belief_snapshot, task_graph
        if candidate.action_id == "unsafe":
            return ExactObservationAssessment(100.0, ("privacy floor",))
        return ExactObservationAssessment(4.0)


def test_learned_voi_proxy_cannot_bypass_exact_risk_verifier():
    snapshot = VersionedBeliefMap().snapshot()
    task = _task_graph()
    proxy = LearnedVOIProxy(_OfflineProxy(), feature_dim=2)
    unsafe = ObservationCandidate("unsafe", (1.0, 0.0), 0.0)
    safe = ObservationCandidate("safe", (0.0, 1.0), 1.0)
    choice = ConstrainedVOISelector().choose(
        [unsafe, safe],
        proxy=proxy,
        exact_verifier=_ExactObservationVerifier(),
        belief_snapshot=snapshot,
        task_graph=task,
    )
    assert choice.candidate == safe
    assert choice.rejected_action_ids == ("unsafe",)
