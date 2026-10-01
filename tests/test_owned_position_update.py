"""Same semantic source, actual owner command and raw position transaction.
PYTEST_DONT_REWRITE: helpers are bound external dependencies on durable recovery.
"""

from datetime import timedelta
from uuid import UUID

import pytest
from run_correction_replay_comparison import build
from structure_two_backbone_wiring_probe import BackboneWiringProbe
from test_native_neural_production import checkpoints as _checkpoints
from test_native_neural_production import cpu_threads as _cpu_threads
from test_native_position_production import advance, fixture_models, weight_state
from test_owned_position_delivery import collect, problem_for
from test_owned_rgbd_support import RGBDSupportDecoder

from cpswm.data_preflight.typed_proposal_networks import ARMS
from cpswm.system.native_neural_production import NeuralNativeProducer
from cpswm.system.owned_position_producer import OwnedPositionProducer
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_particle_workspace import native_content_sha256

checkpoints = _checkpoints
cpu_threads = _cpu_threads
SOURCE = content_sha256("owned-position-update-controlled@1")


def make_case(path, checkpoints, *, enabled=True, selected_index=1):
    initial = BackboneWiringProbe.build(seed=171)
    selected = initial.observed_days()[selected_index].after
    config = dict(
        semantic_record_id=str(selected.metadata.record_id),
        candidate=dict(
            method="CONTROLLED_FIXED_PUBLIC_BOX", id=str(UUID(int=902)), box=[0.0, 0.0, 4.0, 4.0]
        ),
        seed_uv=[0, 0],
        enabled=enabled,
    )
    models = fixture_models()
    candidate = OwnedPositionProducer(configuration=config, **models)
    checkpoint, pin = checkpoints[ARMS[1]]
    joint = NeuralNativeProducer(candidate, checkpoint, manifest_sha256=pin)
    probe, backend, stream, store, builder = build(
        path,
        seed=171,
        source=SOURCE,
        joint_producer=joint,
        observation_decoder=RGBDSupportDecoder(),
    )
    case = dict(
        probe=probe,
        backend=backend,
        stream=stream,
        store=store,
        builder=builder,
        candidate=candidate,
        joint=joint,
        models=models,
        config=config,
        rows=(),
        checkpoint=checkpoint,
        pin=pin,
        selected_index=selected_index,
    )
    for index in range(selected_index):
        advance(case, index)
    case["when"] = advance(case, selected_index) + timedelta(seconds=1)
    return case


def semantic_state(stream):
    core = stream._system.core
    return native_content_sha256(
        (
            core.current_snapshot,
            core._event_histories,
            core._hybrid_loop.ledger.export_state(),
            stream._advanced,
        )
    )


def test_later_owned_frame_updates_same_semantics_and_duplicate_is_inert(tmp_path, checkpoints):
    case = make_case(tmp_path / "state.sqlite", checkpoints)
    try:
        stream = case["stream"]
        core = stream._system.core
        before = semantic_state(stream)
        neutral = weight_state(case)
        source = core.current_posterior_projection_source()
        command, delivery, camera = collect(case)
        update = stream.consume_owned_position_observation(command.action_id)
        assert update.received_at == delivery.received_at
        assert semantic_state(stream) == before
        assert core.current_posterior_projection_source() == source
        assert weight_state(case) != neutral
        assert len(core._particle_workspace.input_bodies) == 3
        assert stream.joint_observation_updates() == ()
        snapshot = native_content_sha256(core._particle_workspace.state_payload())
        rows = case["store"]._db.execute("SELECT * FROM checkpoint").fetchall()
        assert stream.consume_owned_position_observation(command.action_id) == update
        assert native_content_sha256(core._particle_workspace.state_payload()) == snapshot
        assert case["store"]._db.execute("SELECT * FROM checkpoint").fetchall() == rows
        assert camera.calls == 1
        view = stream.current_joint_decision_view()
        next_problem = problem_for(stream, delivery.received_at + timedelta(seconds=1))
        assert next_problem.source_belief_sha256 == view.content_sha256
    finally:
        case["store"].close()


def fresh_joint(case):
    return NeuralNativeProducer(
        OwnedPositionProducer(configuration=case["config"], **case["models"]),
        case["checkpoint"],
        manifest_sha256=case["pin"],
    )


def withdraw(case, selected_id):
    from run_correction_replay_comparison import (
        NEGATIVE_ABSENT_LIKELIHOOD,
        NEGATIVE_PRESENT_LIKELIHOOD,
        NEGATIVE_SEARCH_OUTCOME,
        apply_feedback,
        build_execution_feedback_bundle,
    )

    core = case["stream"]._system.core
    targets = [
        (rid, e)
        for rid, e in core._committed_events.items()
        if str(e.source_record_id) == selected_id
    ]
    assert len(targets) == 1, (
        selected_id,
        [str(e.source_record_id) for e in core._committed_events.values()],
    )
    bundles = [
        build_execution_feedback_bundle(
            case["probe"],
            revision_id=rid,
            location_id=e.location_id,
            belief_snapshot_id=e.belief_snapshot_id,
            when=e.evidence.event_time,
            opportunity_id=e.evidence.observation_opportunity_id,
            outcome_distribution=NEGATIVE_SEARCH_OUTCOME,
            present_likelihood=NEGATIVE_PRESENT_LIKELIHOOD,
            absent_likelihood=NEGATIVE_ABSENT_LIKELIHOOD,
        )
        for rid, e in targets
    ]
    result = apply_feedback(
        case["stream"],
        bundles,
        case["probe"].observed_days()[3].after.detection_time + timedelta(hours=2),
    )
    assert all("retract" in row["operations"] for row in result)
    assert all(rid not in core._observed_events for rid, _ in targets)


@pytest.mark.parametrize("remove_selected", [True, False])
def test_replay_retains_each_update_or_removes_its_semantic_dependency(
    tmp_path, checkpoints, remove_selected
):
    case = make_case(
        tmp_path / "state.sqlite", checkpoints, selected_index=0 if remove_selected else 1
    )
    try:
        stream = case["stream"]
        core = stream._system.core
        from cpswm.system.native_joint_replay import consumed_schedule

        source_ids = [
            str(u.context.source.transition.after.metadata.record_id)
            for u in consumed_schedule(core._particle_workspace)
        ]
        command, delivery, camera = collect(case)
        update = stream.consume_owned_position_observation(command.action_id)
        for index in range(case["selected_index"] + 1, 3):
            advance(case, index)
        withdraw(case, case["native_selected_record_id"] if remove_selected else source_ids[0])
        before = semantic_state(stream)
        stream.replay_joint_posterior()
        assert semantic_state(stream) == before
        assert camera.calls == 1
        workspace = core._particle_workspace
        assert len(workspace.input_bodies) == (2 if remove_selected else 3)
        assert len(workspace.posterior_sources) == 2
        schedule = consumed_schedule(workspace)
        if remove_selected:
            assert case["candidate"].consumed_keys == []
            with pytest.raises(ValueError, match="withdrawn"):
                stream.consume_owned_position_observation(command.action_id)
            assert weight_state(case)["aggregate"] == pytest.approx(1 / 3)
        else:
            assert schedule[0].revision_id == schedule[1].revision_id
            assert schedule[0].logical_key != schedule[1].logical_key
            assert schedule[1].context.observation_update == update
            assert schedule[0].context.cutoff < schedule[1].context.cutoff == delivery.received_at
            assert all(
                r.envelope().capture_time <= schedule[0].context.cutoff
                for r in schedule[0].context.visible_prefix
            )
            assert stream.consume_owned_position_observation(command.action_id) == update
            # Last retained semantic update is neutral, but A remains consumed.
            assert not case["candidate"].last_diagnostic["active"]
            assert len(case["candidate"].consumed_keys) == 1
            assert weight_state(case)["aggregate"] != pytest.approx(1 / 3)
        from run_correction_replay_comparison import OracleProducer

        from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput

        resumed = ContinuousEvidenceInput.resume(
            case["store"],
            producer=OracleProducer(),
            context_builder=case["builder"],
            joint_producer=fresh_joint(case),
            observation_decoder=RGBDSupportDecoder(),
        )
        assert resumed.current_joint_decision_view() == stream.current_joint_decision_view()
    finally:
        case["store"].close()


@pytest.mark.parametrize("boundary", ["admission", "published"])
def test_failure_rolls_back_computation_but_keeps_delivery_and_retry(
    tmp_path, checkpoints, boundary
):
    import sys
    from copy import deepcopy

    from test_owned_position_delivery import state

    case = make_case(tmp_path / "state.sqlite", checkpoints)
    try:
        stream = case["stream"]
        command, delivery, camera = collect(case)
        before = state(case)
        core = stream._system.core
        extra = deepcopy((core._particle_observation_update_anchors, stream._position_consumptions))
        name = (
            "_register_native_raw_context"
            if boundary == "admission"
            else "_cancel_stale_joint_commands"
        )

        def fault(frame, event, arg):
            if event == "return" and frame.f_code.co_name == name:
                raise RuntimeError("injected owned transaction fault")

        prior = sys.getprofile()
        sys.setprofile(fault)
        try:
            with pytest.raises(RuntimeError, match="injected owned"):
                stream.consume_owned_position_observation(command.action_id)
        finally:
            sys.setprofile(prior)
        assert state(case) == before
        assert (core._particle_observation_update_anchors, stream._position_consumptions) == extra
        assert stream.observation_history()[-1][1] == delivery
        stream.consume_owned_position_observation(command.action_id)
        assert camera.calls == 1
    finally:
        case["store"].close()


def fresh_restore(folder):
    """Fresh interpreter first operation is SQLite recovery, no replacement stream."""
    import json
    import sys
    from pathlib import Path

    import torch
    from run_correction_replay_comparison import OracleProducer

    from cpswm.system.continuous_state_store import ContinuousStateStore
    from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput

    torch.set_num_threads(2)
    folder = Path(folder)
    config = json.loads((folder / "restore.json").read_text())
    joint = NeuralNativeProducer(
        OwnedPositionProducer(configuration=config["config"], **config["models"]),
        Path(config["checkpoint"]),
        manifest_sha256=config["pin"],
    )
    store = ContinuousStateStore(
        folder / "copy.db", source_identity=SOURCE, dependency_identity=content_sha256(sys.version)
    )

    def unused_builder(*args):
        raise AssertionError("recovery must not rerun semantic P5")

    try:
        stream = ContinuousEvidenceInput.resume(
            store,
            producer=OracleProducer(),
            context_builder=unused_builder,
            joint_producer=joint,
            observation_decoder=RGBDSupportDecoder(),
        )
        action = UUID(config["action"])
        update = stream.consume_owned_position_observation(action)
        before = store._db.execute("SELECT * FROM checkpoint").fetchall()
        assert stream.consume_owned_position_observation(action) == update
        assert store._db.execute("SELECT * FROM checkpoint").fetchall() == before
        (folder / "fresh-result.json").write_text(
            json.dumps(
                dict(
                    view=stream.current_joint_decision_view().content_sha256,
                    update=native_content_sha256(update),
                    semantic=semantic_state(stream),
                    calls=joint.calls,
                ),
                indent=2,
            )
        )
    finally:
        store.close()


@pytest.mark.parametrize("phase", ["delivered", "consumed", "replayed"])
def test_fresh_process_recovers_and_retries_without_new_sensor_or_semantic_work(
    tmp_path, checkpoints, phase
):
    import json
    import os
    import sqlite3
    import subprocess
    import sys
    from pathlib import Path

    case = make_case(tmp_path / "state.db", checkpoints)
    try:
        stream = case["stream"]
        command, _, camera = collect(case)
        if phase != "delivered":
            stream.consume_owned_position_observation(command.action_id)
        if phase == "replayed":
            from cpswm.system.native_joint_replay import consumed_schedule

            source_ids = [
                str(u.context.source.transition.after.metadata.record_id)
                for u in consumed_schedule(stream._system.core._particle_workspace)
            ]
            advance(case, 2)
            withdraw(case, source_ids[0])
            stream.replay_joint_posterior()
        with sqlite3.connect(tmp_path / "copy.db") as copy_db:
            case["store"]._db.backup(copy_db)
        original = case["store"]._db.execute("SELECT * FROM checkpoint").fetchall()
        (tmp_path / "restore.json").write_text(
            json.dumps(
                dict(
                    config=case["config"],
                    models=case["models"],
                    checkpoint=str(case["checkpoint"]),
                    pin=case["pin"],
                    action=str(command.action_id),
                )
            )
        )
        root = Path(__file__).resolve().parents[1]
        env = dict(
            os.environ,
            PYTHONPATH=os.pathsep.join(str(root / p) for p in ("src", "tests", "tools")),
            PYTHONHASHSEED="8675309",
        )
        with (tmp_path / "fresh.log").open("w") as log:
            child = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from test_owned_position_update import fresh_restore; "
                    "import sys; fresh_restore(sys.argv[1])",
                    str(tmp_path),
                ],
                cwd=root,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=180,
            )
        assert child.returncode == 0, (tmp_path / "fresh.log").read_text()
        assert case["store"]._db.execute("SELECT * FROM checkpoint").fetchall() == original
        update = stream.consume_owned_position_observation(command.action_id)
        result = json.loads((tmp_path / "fresh-result.json").read_text())
        assert result["view"] == stream.current_joint_decision_view().content_sha256
        assert result["update"] == native_content_sha256(update)
        assert result["semantic"] == semantic_state(stream)
        assert result["calls"] == case["joint"].calls
        assert camera.calls == 1
    finally:
        case["store"].close()


def test_fully_rebuilt_packet_and_owner_subgraph_cannot_replace_accepted_delivery(
    tmp_path, checkpoints
):
    from dataclasses import replace

    from test_owned_position_delivery import state
    from test_unity_rgbd import rewrite_packet

    case = make_case(tmp_path / "state.db", checkpoints)
    try:
        stream = case["stream"]
        command, delivery, camera = collect(case)
        originals = dict(stream._raw)
        forged = rewrite_packet(
            delivery.observations, pose_changes={"position_m": [100.0, 200.0, 300.0]}
        )
        stream._observation_status[command.action_id] = replace(delivery, observations=forged)
        for raw in forged:
            stream._raw[raw.envelope().identity.observation_id] = raw
        before = state(case)
        with pytest.raises(ValueError, match="original issue/delivery"):
            stream.consume_owned_position_observation(command.action_id)
        assert state(case) == before
        stream._raw = originals
        stream._observation_status[command.action_id] = delivery
        stream.consume_owned_position_observation(command.action_id)
        assert camera.calls == 1
    finally:
        case["store"].close()


def test_second_real_capture_is_retained_but_explicitly_unsupported(tmp_path, checkpoints):
    from test_owned_position_delivery import state

    case = make_case(tmp_path / "state.db", checkpoints)
    try:
        stream = case["stream"]
        first, delivery, _ = collect(case)
        stream.consume_owned_position_observation(first.action_id)
        case["when"] = delivery.received_at + timedelta(seconds=1)
        second, second_delivery, _ = collect(case)
        before = state(case)
        with pytest.raises(ValueError, match="second measurement unsupported"):
            stream.consume_owned_position_observation(second.action_id)
        assert state(case) == before
        assert stream.observation_history()[-1][1] == second_delivery
    finally:
        case["store"].close()


def test_closed_form_weights_statistics_and_no_factor_control(tmp_path, checkpoints):
    import math

    import numpy as np

    case = make_case(tmp_path / "active.db", checkpoints)
    control = make_case(tmp_path / "control.db", checkpoints, enabled=False)
    try:
        for item in (case, control):
            command, _, _ = collect(item)
            item["stream"].consume_owned_position_observation(command.action_id)
        diagnostic = case["candidate"].last_diagnostic
        point = np.array(diagnostic["public_observation"]["world_point_m"])
        model = case["models"]["position_model"]
        residual = point - np.array(model["bias"])
        covariance = np.array(model["covariance"])
        predictive = np.eye(3) + covariance
        # Independent direct density/information arithmetic; no condition helper.
        known = -0.5 * (
            3 * math.log(2 * math.pi)
            + np.linalg.slogdet(predictive)[1]
            + residual @ np.linalg.solve(predictive, residual)
        )
        unknown = -0.5 * (3 * math.log(2 * math.pi * 100) + point @ point / 100)
        logs = np.array([known, unknown, unknown])
        probs = np.exp(logs - logs.max())
        probs /= probs.sum()
        state = weight_state(case)
        assert [state[False][0], state[True][0], state["aggregate"]] == pytest.approx(probs)
        precision = np.eye(6)
        precision[:3, :3] += np.linalg.inv(covariance)
        eta = np.zeros(6)
        eta[:3] = np.linalg.solve(covariance, residual)
        assert np.allclose(state[False][1], precision)
        assert np.allclose(state[False][2], eta)
        assert np.allclose(state[True][1], np.eye(6))
        assert np.allclose(state[True][2], 0)
        neutral = weight_state(control)
        assert [neutral[False][0], neutral[True][0], neutral["aggregate"]] == pytest.approx(
            [1 / 3] * 3
        )
        assert state[False][3:] == neutral[False][3:]
    finally:
        case["store"].close()
        control["store"].close()


class PositionCameraModel:
    from test_continuous_camera_collection import SOURCES as sources

    def __init__(self, stream):
        self.stream = stream

    def problem(self, view, visible_prefix, *, decision_time, execution_history):
        assert view == self.stream.current_joint_decision_view()
        return problem_for(self.stream, decision_time)


def test_actual_collector_runs_new_update_without_a_new_semantic_transition(tmp_path, checkpoints):
    from test_owned_rgbd_support import RGBDCamera

    from cpswm.system.continuous_camera_collection import collect_posterior_step

    case = make_case(tmp_path / "state.db", checkpoints)
    try:
        stream = case["stream"]
        before = semantic_state(stream)
        prior = stream.current_joint_decision_view()
        camera = RGBDCamera(stream._scope)
        step = collect_posterior_step(
            stream, model=PositionCameraModel(stream), executor=camera, decision_time=case["when"]
        )
        assert step.delivery.success and camera.calls == 1
        assert semantic_state(stream) == before
        assert step.command.action_id in stream._position_consumptions
        assert stream.current_joint_decision_view() != prior
    finally:
        case["store"].close()


@pytest.mark.parametrize("committed", [False, True])
def test_sqlite_uncertainty_requires_recovery_without_repeating_camera(
    tmp_path, checkpoints, monkeypatch, committed
):
    from run_correction_replay_comparison import OracleProducer

    from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput

    case = make_case(tmp_path / "state.db", checkpoints)
    try:
        stream, store = case["stream"], case["store"]
        command, delivery, camera = collect(case)
        original_save = store.save

        def fail(state):
            if committed:
                original_save(state)
            raise OSError("injected SQLite boundary")

        with monkeypatch.context() as patch:
            patch.setattr(store, "save", fail)
            with pytest.raises(OSError, match="SQLite boundary"):
                stream.consume_owned_position_observation(command.action_id)
        assert stream._durability_failed
        with pytest.raises(RuntimeError, match="recover"):
            stream.consume_owned_position_observation(command.action_id)
        resumed = ContinuousEvidenceInput.resume(
            store,
            producer=OracleProducer(),
            context_builder=case["builder"],
            joint_producer=fresh_joint(case),
            observation_decoder=RGBDSupportDecoder(),
        )
        assert bool(resumed._position_consumptions) is committed
        assert resumed.observation_history()[-1][1] == delivery
        resumed.consume_owned_position_observation(command.action_id)
        assert len(resumed._position_consumptions) == 1 and camera.calls == 1
    finally:
        case["store"].close()


@pytest.mark.parametrize("field", ["known_ll", "unknown_ll", "aggregate", "transition"])
def test_complete_target_forgery_rolls_back_then_legal_retry(tmp_path, checkpoints, field):
    import sys
    from dataclasses import replace

    from test_owned_position_delivery import state

    from cpswm.system.native_neural_production import materialize, verify_neural_evidence

    case = make_case(tmp_path / "state.sqlite", checkpoints)
    try:
        stream = case["stream"]
        command, delivery, camera = collect(case)
        before = state(case)
        attacked = []

        def attack(frame, event, produced):
            if (
                event != "return"
                or frame.f_code is not NeuralNativeProducer.produce.__code__
                or frame.f_locals.get("self") is not case["joint"]
                or attacked
            ):
                return
            base = produced.neural_evidence.base_candidates
            if field == "aggregate":
                base = replace(base, unresolved_log_weight=base.unresolved_log_weight + 2.0)
            else:
                index = int(field == "unknown_ll")
                key = (
                    "transition_log_probability"
                    if field == "transition"
                    else "observation_log_likelihood"
                )
                rows = list(base.receipts)
                rows[index] = rows[index].model_copy(
                    update={key: getattr(rows[index], key) + (-2 if field == "transition" else 2)}
                )
                base = replace(base, receipts=tuple(rows))
            proof = replace(produced.neural_evidence, base_candidates=base)
            verify_neural_evidence(proof)
            attacked.append(True)
            for key, value in dict(
                receipts=materialize(base, proof),
                statistics=base.statistics,
                unresolved_log_weight=base.unresolved_log_weight,
                neural_evidence=proof,
            ).items():
                object.__setattr__(produced, key, value)

        prior = sys.getprofile()
        sys.setprofile(attack)
        try:
            with pytest.raises(ValueError, match="complete owner recomputation"):
                stream.consume_owned_position_observation(command.action_id)
        finally:
            sys.setprofile(prior)
        assert attacked == [True]
        assert state(case) == before
        assert stream._position_consumptions == {}
        assert stream._system.core._particle_observation_update_anchors == {}
        assert stream.observation_history()[-1][1] == delivery
        stream.consume_owned_position_observation(command.action_id)
        assert camera.calls == 1
    finally:
        case["store"].close()
