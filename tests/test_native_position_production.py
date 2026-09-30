"""Actual native publication/replay of controlled pixels, identity and priors.

Neural checkpoints really execute. Synthetic training residuals and a constant
affinity fixture are not the 96-frame experiment or calibrated natural identity.
PYTEST_DONT_REWRITE: producer fixtures below participate in bound recovery.
"""

from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from math import exp, log, pi
from uuid import UUID

import numpy as np
import pytest
from controlled_position_producer import ControlledPositionProducer, packet_binding
from run_correction_replay_comparison import (
    NEGATIVE_ABSENT_LIKELIHOOD,
    NEGATIVE_PRESENT_LIKELIHOOD,
    NEGATIVE_SEARCH_OUTCOME,
    OracleProducer,
    apply_feedback,
    build,
    build_execution_feedback_bundle,
    raw_for,
)
from structure_two_backbone_wiring_probe import BackboneWiringProbe
from test_native_neural_production import checkpoints as _checkpoints
from test_native_neural_production import context_for, stage
from test_native_neural_production import cpu_threads as _cpu_threads
from test_position_observation_model import training_arrays
from test_soft_surface_position import controlled_model
from test_unity_rgbd import packet, rewrite_packet

from cpswm.data_preflight.soft_surface_position import DEFINITION, DOMAIN, SCHEMA
from cpswm.data_preflight.typed_proposal_networks import ARMS
from cpswm.perception_mapping import position_observation_model as position
from cpswm.system.native_neural_production import NeuralNativeProducer
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput, GroundedTransition
from cpswm.system.structure_two_particle_workspace import native_content_sha256

checkpoints = _checkpoints
cpu_threads = _cpu_threads


def fixture_models():
    affinity = controlled_model()
    apin = content_sha256(affinity)
    estimator_pin = content_sha256(
        dict(
            schema=SCHEMA,
            estimator="soft_affinity",
            definition=DEFINITION,
            affinity_pin=apin,
        )
    )
    _, members = training_arrays()
    residuals = np.sqrt(2.5) * np.vstack((np.eye(3), -np.eye(3)))
    model = position.fit(
        residuals,
        members,
        estimator="soft_affinity",
        reference_kind="sdk_transform_position_m",
        domain_id=DOMAIN,
        estimator_pin=estimator_pin,
    )
    return dict(
        affinity_model=affinity,
        affinity_pin=apin,
        position_model=model,
        position_pin=position.checkpoint_sha256(model),
    )


def scenario(path, checkpoints, *, enabled=True, selected_index=0):
    # Scenario UUIDs are fixed by seed; we bind before any pixels/outputs are used.
    initial = BackboneWiringProbe.build(seed=171)
    selected = initial.observed_days()[selected_index].after
    meta = selected.metadata
    rows, _ = packet(
        action=UUID(int=901),
        scope=(meta.household_id, meta.session_id, meta.trace_id),
        capture=selected.detection_time - timedelta(seconds=2),
    )
    config = dict(
        semantic_record_id=str(meta.record_id),
        packet=packet_binding(rows),
        candidate=dict(
            method="CONTROLLED_FIXED_PUBLIC_BOX", id=str(UUID(int=902)), box=[0.0, 0.0, 4.0, 4.0]
        ),
        seed_uv=[0, 0],
        enabled=enabled,
    )
    models = fixture_models()
    candidate = ControlledPositionProducer(configuration=config, **models)
    checkpoint, pin = checkpoints[ARMS[1]]
    joint = NeuralNativeProducer(candidate, checkpoint, manifest_sha256=pin)
    probe, backend, stream, store, builder = build(
        path,
        seed=171,
        source=content_sha256("controlled-position-test"),
        joint_producer=joint,
    )
    assert probe.observed_days()[selected_index].after.metadata.record_id == meta.record_id
    return dict(
        probe=probe,
        backend=backend,
        stream=stream,
        store=store,
        builder=builder,
        candidate=candidate,
        joint=joint,
        models=models,
        config=config,
        rows=rows,
        checkpoint=checkpoint,
        pin=pin,
        selected_index=selected_index,
    )


def advance(case, index, *, publish=True):
    probe, stream, backend = case["probe"], case["stream"], case["backend"]
    transition = probe.transition_for(probe.observed_days()[index])
    when = transition.after.detection_time + timedelta(minutes=1)
    raw = (raw_for(transition, index),)
    if index == case["selected_index"]:
        raw = (*raw, *case["rows"])
    ids = stream.admit(raw, received_at=when)
    backend.output = GroundedTransition(
        transition, ids, "CONTROLLED_ORACLE_V1", "ASSUMED_NOT_EMPIRICAL"
    )
    stream.advance(cutoff=when)
    if index == case["selected_index"]:
        case["native_selected_record_id"] = str(
            stream._system.core.current_posterior_projection_source().transition.after.metadata.record_id
        )
    if publish:
        stream.produce_joint_posterior()
    backend.output = None
    return when


def snapshot(case):
    return native_content_sha256(case["stream"]._system.core._particle_workspace.state_payload())


def weight_state(case):
    workspace = case["stream"]._system.core._particle_workspace
    result = {}
    for weight in workspace.batch.particle_weights:
        record = workspace.records[weight.particle_id]
        key = record.state.instance_association_key == "unknown_instance"
        result[key] = (
            weight.posterior_probability,
            record.statistics.information,
            record.statistics.information_vector,
            record.statistics.alpha,
            record.statistics.a,
            record.statistics.b,
        )
    result["aggregate"] = workspace.batch.unresolved_probability
    return result


def fresh_joint(case):
    candidate = ControlledPositionProducer(configuration=case["config"], **case["models"])
    return NeuralNativeProducer(candidate, case["checkpoint"], manifest_sha256=case["pin"])


def test_publishes_preupdate_density_full_state_and_single_information_increment(
    tmp_path, checkpoints
):
    case = scenario(tmp_path / "state.db", checkpoints)
    try:
        advance(case, 0)
        stream, candidate = case["stream"], case["candidate"]
        workspace = stream._system.core._particle_workspace
        diag = candidate.last_diagnostic
        assert diag["configured_record_id"] == case["config"]["semantic_record_id"]
        assert diag["native_before_record_id"] == diag["configured_record_id"]
        assert diag["native_after_record_id"] == case["native_selected_record_id"]
        assert diag["mapping"] == "controlled-ciav-before"
        point = np.asarray(diag["public_observation"]["world_point_m"])
        known = -0.5 * (3 * log(2 * pi * 2) + point @ point / 2)
        unknown = -0.5 * (3 * log(2 * pi * 100) + point @ point / 100)
        assert diag["known"]["observation_log_likelihood"] == pytest.approx(known)
        assert diag["unknown_log_likelihood"] == pytest.approx(unknown)
        assert np.asarray(diag["known"]["predictive_covariance"]) == pytest.approx(np.eye(3) * 2)
        masses = np.asarray([exp(known), exp(unknown), exp(unknown)])
        expected = masses / masses.sum()
        state = weight_state(case)
        assert [state[False][0], state[True][0], state["aggregate"]] == pytest.approx(expected)
        assert np.asarray(state[False][1]) == pytest.approx(np.diag([2, 2, 2, 1, 1, 1]))
        assert np.asarray(state[False][2]) == pytest.approx(np.r_[point, [0, 0, 0]])
        assert np.asarray(state[True][1]) == pytest.approx(np.eye(6))
        for receipt in workspace.receipts:
            assert receipt.evidence_semantics == "raw_observation_likelihood"
            assert receipt.source_posterior_snapshot_id is None
            assert receipt.posterior_projection_log_factor == 0
            assert receipt.proposal.proposal_log_probability == receipt.integration_log_weight
        ledger = native_content_sha256(stream._system.core._hybrid_loop.ledger.export_state())
        before, calls = snapshot(case), candidate.calls
        stream.produce_joint_posterior()
        assert snapshot(case) == before and candidate.calls == calls
        # The image remains visible during later semantic steps but is not reused.
        advance(case, 1)
        after = weight_state(case)
        for key in (False, True):
            assert after[key][0] == pytest.approx(state[key][0])
            assert after[key][1:] == state[key][1:]
        assert after["aggregate"] == pytest.approx(state["aggregate"])
        assert len(candidate.consumed_keys) == 1 and not candidate.last_diagnostic["active"]
        # Publication itself never writes a second semantic ledger contribution.
        before = native_content_sha256(stream._system.core._hybrid_loop.ledger.export_state())
        stream.produce_joint_posterior()
        assert (
            native_content_sha256(stream._system.core._hybrid_loop.ledger.export_state()) == before
        )
        assert ledger  # day advancement may legitimately change the semantic ledger.
    finally:
        case["store"].close()


@pytest.mark.parametrize("attack", ["depth", "pose", "context", "rebound_packet"])
def test_complete_public_forgery_rejected_then_legal_native_recovery(tmp_path, checkpoints, attack):
    case = scenario(tmp_path / "attack.db", checkpoints)
    try:
        when = advance(case, 0, publish=False)
        context = context_for(case["stream"], when)
        before = snapshot(case)
        state = case["joint"].checkpoint_state()
        if attack == "context":
            # Real scores and complete raw receipts for the wrong ledger context.
            forged = case["joint"].produce(replace(context, ledger_head_sha256="d" * 64))
            with pytest.raises(ValueError):
                stage(case["stream"], forged)
            case["joint"].restore_state(state)
        else:
            rows = rewrite_packet(
                case["rows"],
                depth=np.full((4, 4), 5.0, dtype=np.float32) if attack != "pose" else None,
                pose_changes={"position_m": [20.0, 30.0, 40.0]} if attack == "pose" else None,
            )
            mapping = {row.envelope().identity.observation_id: row for row in rows}
            forged_context = replace(
                context,
                visible_prefix=tuple(
                    mapping.get(row.envelope().identity.observation_id, row)
                    for row in context.visible_prefix
                ),
            )
            if attack == "rebound_packet":
                config = deepcopy(case["config"])
                config["packet"] = packet_binding(rows)
                other = NeuralNativeProducer(
                    ControlledPositionProducer(configuration=config, **case["models"]),
                    case["checkpoint"],
                    manifest_sha256=case["pin"],
                )
                forged = other.produce(forged_context)
                with pytest.raises(ValueError):
                    stage(case["stream"], forged)
            else:
                with pytest.raises(ValueError, match="raw packet differs"):
                    case["joint"].produce(forged_context)
        assert snapshot(case) == before
        case["stream"].produce_joint_posterior()
        assert case["stream"].current_joint_decision_view().atoms
        assert len(case["candidate"].consumed_keys) == 1
    finally:
        case["store"].close()


def test_sqlite_new_producer_restores_actual_weights_statistics_and_deduplication(
    tmp_path, checkpoints
):
    case = scenario(tmp_path / "resume.db", checkpoints)
    try:
        advance(case, 0)
        joint = fresh_joint(case)
        resumed = ContinuousEvidenceInput.resume(
            case["store"],
            producer=OracleProducer(),
            context_builder=case["builder"],
            joint_producer=joint,
        )
        assert resumed.current_joint_decision_view() == case["stream"].current_joint_decision_view()
        assert joint.checkpoint_state() == case["joint"].checkpoint_state()
        before = joint.checkpoint_state()
        resumed.produce_joint_posterior()
        assert joint.checkpoint_state() == before
    finally:
        case["store"].close()


def test_retraction_full_replay_matches_no_factor_and_survives_sqlite(tmp_path, checkpoints):
    case = scenario(tmp_path / "replay.db", checkpoints, selected_index=0)
    control = scenario(tmp_path / "control.db", checkpoints, enabled=False, selected_index=0)
    try:
        for row in (case, control):
            for index in range(3):
                advance(row, index)
        assert weight_state(case) != weight_state(control)
        for row in (case, control):
            core = row["stream"]._system.core
            targets = [
                (rid, event)
                for rid, event in core._committed_events.items()
                if str(event.source_record_id) == row["native_selected_record_id"]
            ]
            assert len(targets) == 1, "the fixed source must actually be retractable"
            bundles = [
                build_execution_feedback_bundle(
                    row["probe"],
                    revision_id=rid,
                    location_id=event.location_id,
                    belief_snapshot_id=event.belief_snapshot_id,
                    when=event.evidence.event_time,
                    opportunity_id=event.evidence.observation_opportunity_id,
                    outcome_distribution=NEGATIVE_SEARCH_OUTCOME,
                    present_likelihood=NEGATIVE_PRESENT_LIKELIHOOD,
                    absent_likelihood=NEGATIVE_ABSENT_LIKELIHOOD,
                )
                for rid, event in targets
            ]
            apply_feedback(
                row["stream"],
                bundles,
                row["probe"].observed_days()[2].after.detection_time + timedelta(hours=2),
            )
            assert all(rid not in core._observed_events for rid, _ in targets)
            with pytest.raises(ValueError):
                row["stream"].current_joint_decision_view()
            ledger = native_content_sha256(core._hybrid_loop.ledger.export_state())
            row["stream"].replay_joint_posterior()
            assert native_content_sha256(core._hybrid_loop.ledger.export_state()) == ledger
            assert row["candidate"].consumed_keys == []
            assert len(row["stream"].visible_prefix(cutoff=row["stream"]._last_cutoff)) >= 3
        assert weight_state(case) == weight_state(control)
        joint = fresh_joint(case)
        resumed = ContinuousEvidenceInput.resume(
            case["store"],
            producer=OracleProducer(),
            context_builder=case["builder"],
            joint_producer=joint,
        )
        assert resumed.current_joint_decision_view() == case["stream"].current_joint_decision_view()
        assert joint.checkpoint_state() == case["joint"].checkpoint_state()
    finally:
        case["store"].close()
        control["store"].close()


@pytest.mark.parametrize("attack", ["orientation_H", "helper_code", "producer_code"])
def test_loaded_complete_forgery_cannot_publish_under_original_binding(
    tmp_path, checkpoints, monkeypatch, attack
):
    case = scenario(tmp_path / "loaded.db", checkpoints)
    try:
        when = advance(case, 0, publish=False)
        context = context_for(case["stream"], when)
        before = snapshot(case)
        ledger = native_content_sha256(
            case["stream"]._system.core._hybrid_loop.ledger.export_state()
        )
        with monkeypatch.context() as patch:
            if attack == "orientation_H":
                patch.setattr(
                    position,
                    "H",
                    tuple(
                        tuple(float(column == row + 3) for column in range(6)) for row in range(3)
                    ),
                )
            elif attack == "helper_code":
                # Still produces a valid full covariance/model/update; the code
                # is changed in memory without changing its source file bytes.
                original = position.condition

                def changed(*args, **kwargs):
                    measurement, diagnostic = original(*args, **kwargs)
                    return replace(measurement, information_weight=0.5), diagnostic

                patch.setattr(position, "condition", changed)
            else:
                original = ControlledPositionProducer._public

                def changed(self, context):
                    result = original(self, context)
                    result["world_point_m"] = [value + 1.0 for value in result["world_point_m"]]
                    return result

                patch.setattr(ControlledPositionProducer, "_public", changed)
            # New fully bound attacker with real neural scores, receipts and
            # statistics. Self-signing the modified implementation is insufficient.
            attacker = fresh_joint(case)
            forged = attacker.produce(context)
            with pytest.raises(ValueError):
                stage(case["stream"], forged)
            with pytest.raises(ValueError):
                case["joint"].produce(context)
        assert snapshot(case) == before
        assert (
            native_content_sha256(case["stream"]._system.core._hybrid_loop.ledger.export_state())
            == ledger
        )
        case["stream"].produce_joint_posterior()
        assert case["stream"].current_joint_decision_view().atoms
    finally:
        case["store"].close()


def test_before_record_mapping_is_only_for_explicit_controlled_ciav_closure(tmp_path, checkpoints):
    case = scenario(tmp_path / "mapping.db", checkpoints)
    try:
        when = advance(case, 0, publish=False)
        context = context_for(case["stream"], when)
        source = context.source
        assert (
            str(source.transition.before.metadata.record_id) == case["config"]["semantic_record_id"]
        )
        after = source.transition.after.model_copy(
            update={
                "metadata": source.transition.after.metadata.model_copy(
                    update={"source_id": "ordinary-observation"}
                ),
            }
        )
        ordinary = replace(source, transition=replace(source.transition, after=after))
        ordinary = replace(ordinary, body_sha256=native_content_sha256(ordinary.body()))
        ordinary.validate_content()
        attacker = fresh_joint(case)
        forged = attacker.produce(replace(context, source=ordinary))
        assert not attacker._candidate_model.last_diagnostic["active"]
        assert all(receipt.observation_log_likelihood == 0.0 for receipt in forged.receipts)
        before = snapshot(case)
        with pytest.raises(ValueError):
            stage(case["stream"], forged)
        assert snapshot(case) == before
        case["stream"].produce_joint_posterior()
        assert case["candidate"].last_diagnostic["active"]
    finally:
        case["store"].close()
