"""Real pinned detector with archived live pixels and controlled depth/semantics.
PYTEST_DONT_REWRITE: durable fixture dependencies retain ordinary source code.
"""

import os
from datetime import timedelta
from pathlib import Path

import numpy as np
import pytest
from run_correction_replay_comparison import build
from structure_two_backbone_wiring_probe import BackboneWiringProbe
from test_native_neural_production import checkpoints as _checkpoints
from test_native_neural_production import cpu_threads as _cpu_threads
from test_native_position_production import advance, fixture_models, weight_state
from test_natural_candidate_position import PublicPixelCamera, public_image
from test_owned_position_delivery import issue, state
from test_owned_position_update import semantic_state
from test_owned_rgbd_support import RGBDSupportDecoder
from test_unity_rgbd import event_for
from unity_rgbd_capture import rgbd_response

from cpswm.data_preflight.typed_proposal_networks import ARMS
from cpswm.perception_mapping.unity_rgbd import PROFILE, observations_from_response
from cpswm.system.native_neural_production import NeuralNativeProducer
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_continuous_input import ObservationDelivery
from cpswm.system.temporal_target_position import TemporalTargetPositionProducer

checkpoints = _checkpoints
cpu_threads = _cpu_threads
SOURCE = content_sha256("temporal-target-transaction-test@1")


@pytest.fixture(scope="module")
def weights():
    path = Path(os.environ.get("CPSWM_SSDLITE_WEIGHTS", ""))
    if not path.is_file():
        pytest.skip("explicit local pinned SSDLite weights required")
    return path.resolve()


def make_case(path, checkpoints, weights, *, enabled=True, selected_index=1):
    selected = BackboneWiringProbe.build(seed=171).observed_days()[selected_index].after
    config = dict(
        semantic_record_id=str(selected.metadata.record_id),
        enabled=enabled,
        weights_path=str(weights),
        shared_fraction=0.5,
        unknown_prior=0.2,
    )
    models = fixture_models()
    candidate = TemporalTargetPositionProducer(configuration=config, **models)
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


def capture(case, camera):
    command = issue(case)
    delivery = case["stream"].execute_observation(command, executor=camera)
    case["stream"].consume_owned_position_observation(command.action_id)
    case["when"] = delivery.received_at + timedelta(seconds=1)
    return command, delivery


def test_continuous_duplicate_pixels_and_transaction_idempotence(tmp_path, checkpoints, weights):
    case = make_case(tmp_path / "state.db", checkpoints, weights)
    try:
        stream = case["stream"]
        semantic = semantic_state(stream)
        camera = PublicPixelCamera(stream._scope)
        before = weight_state(case)
        first, _ = capture(case, camera)
        after = weight_state(case)
        assert after != before
        second, _ = capture(case, camera)
        third, _ = capture(case, camera)
        assert len(stream._position_consumptions) == 3 and camera.calls == 3
        assert semantic_state(stream) == semantic
        diagnostic = case["candidate"].last_diagnostic
        assert len(diagnostic["sequence"]["records"]) == 3
        assert all(
            n == 1 for n in diagnostic["sequence"]["records"][-1]["unique_position_counts"].values()
        )
        assert all(b["position_log_ratio"] == 0 for b in diagnostic["branches"])
        saved = state(case)
        stream.consume_owned_position_observation(first.action_id)
        stream.consume_owned_position_observation(second.action_id)
        stream.consume_owned_position_observation(third.action_id)
        assert state(case) == saved
        assert any(b["instance"] == "unknown_instance" for b in diagnostic["branches"])
    finally:
        case["store"].close()


@pytest.mark.parametrize("rho", [0.0, 0.5, 0.9])
def test_conditional_innovations_equal_direct_joint_posterior_and_density(rho):
    from cpswm.perception_mapping.position_observation_model import H
    from cpswm.perception_mapping.temporal_position import covariance, innovation, logpdf

    rng = np.random.default_rng(451)
    r = np.array([[0.4, 0.1, 0.03], [0.1, 0.6, -0.02], [0.03, -0.02, 0.5]])
    y = rng.normal(size=(5, 3))
    h = np.asarray(H)
    j0 = np.diag([2.0, 3.0, 4.0, 1.0, 1.0, 1.0])
    b0 = np.array([1.0, 2.0, 3.0, 0.0, 0.0, 0.0])
    j, b, ll = j0.copy(), b0.copy(), 0.0
    for n in range(1, len(y) + 1):
        z, a, c = innovation(y[:n], r, rho)
        ll += logpdf(z, a @ np.linalg.solve(j, b), c + a @ np.linalg.solve(j, a.T))
        j += a.T @ np.linalg.solve(c, a)
        b += a.T @ np.linalg.solve(c, z)
    full_h = np.tile(h, (len(y), 1))
    full_c = covariance(len(y), r, rho)
    assert j == pytest.approx(j0 + full_h.T @ np.linalg.solve(full_c, full_h), abs=1e-11)
    assert b == pytest.approx(b0 + full_h.T @ np.linalg.solve(full_c, y.ravel()), abs=1e-11)
    expected_ll = logpdf(
        y.ravel(), full_h @ np.linalg.solve(j0, b0), full_c + full_h @ np.linalg.solve(j0, full_h.T)
    )
    assert ll == pytest.approx(expected_ll, abs=1e-11)
    if rho:
        iid_j = j0 + len(y) * h.T @ np.linalg.solve(r, h)
        assert np.trace(j) < np.trace(iid_j)


def association_joint(case):
    return NeuralNativeProducer(
        TemporalTargetPositionProducer(configuration=case["config"], **case["models"]),
        Path(case["checkpoint"]),
        manifest_sha256=case["pin"],
    )


def fresh_restore(folder):
    import json
    import sys
    from uuid import UUID

    import torch
    from run_correction_replay_comparison import OracleProducer

    from cpswm.system.continuous_state_store import ContinuousStateStore
    from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput
    from cpswm.system.structure_two_particle_workspace import native_content_sha256

    torch.set_num_threads(2)
    folder = Path(folder)
    config = json.loads((folder / "restore.json").read_text())
    joint = association_joint(config)
    store = ContinuousStateStore(
        folder / "copy.db", source_identity=SOURCE, dependency_identity=content_sha256(sys.version)
    )

    def unused_builder(*args):
        raise AssertionError("fresh recovery must not rerun semantic P5")

    try:
        stream = ContinuousEvidenceInput.resume(
            store,
            producer=OracleProducer(),
            context_builder=unused_builder,
            joint_producer=joint,
            observation_decoder=RGBDSupportDecoder(),
        )
        update = stream.consume_owned_position_observation(UUID(config["action"]))
        before = store._db.execute("SELECT * FROM checkpoint").fetchall()
        assert stream.consume_owned_position_observation(update.action_id) == update
        assert before == store._db.execute("SELECT * FROM checkpoint").fetchall()
        (folder / "fresh.json").write_text(
            json.dumps(
                dict(
                    view=stream.current_joint_decision_view().content_sha256,
                    semantic=semantic_state(stream),
                    update=native_content_sha256(update),
                ),
                indent=2,
            )
        )
    finally:
        store.close()


@pytest.mark.parametrize("phase", ["delivered", "consumed", "replayed"])
def test_fresh_interpreter_natural_reconstruction(tmp_path, checkpoints, weights, phase):
    import json
    import sqlite3
    import subprocess
    import sys

    from test_owned_position_update import withdraw

    from cpswm.system.native_joint_replay import consumed_schedule
    from cpswm.system.structure_two_particle_workspace import native_content_sha256

    case = make_case(tmp_path / "state.db", checkpoints, weights)
    try:
        stream = case["stream"]
        camera = PublicPixelCamera(stream._scope)
        capture(case, camera)
        command = issue(case)
        stream.execute_observation(command, executor=camera)
        if phase != "delivered":
            stream.consume_owned_position_observation(command.action_id)
        if phase == "replayed":
            old = consumed_schedule(stream._system.core._particle_workspace)[0]
            advance(case, 2)
            withdraw(case, str(old.context.source.transition.after.metadata.record_id))
            stream.replay_joint_posterior()
        with sqlite3.connect(tmp_path / "copy.db") as db:
            case["store"]._db.backup(db)
        before = case["store"]._db.execute("SELECT * FROM checkpoint").fetchall()
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
            PYTHONHASHSEED="81731",
        )
        with (tmp_path / "fresh.log").open("w") as log:
            child = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from test_temporal_target_position import fresh_restore; "
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
        assert before == case["store"]._db.execute("SELECT * FROM checkpoint").fetchall()
        update = stream.consume_owned_position_observation(command.action_id)
        fresh = json.loads((tmp_path / "fresh.json").read_text())
        assert fresh == dict(
            view=stream.current_joint_decision_view().content_sha256,
            semantic=semantic_state(stream),
            update=native_content_sha256(update),
        )
        assert camera.calls == 2
    finally:
        case["store"].close()


@pytest.mark.parametrize(
    "fault",
    ["admission", "published", "association_gate", "position", "unknown", "aggregate", "statistic"],
)
def test_rollback_and_complete_forgery_with_real_neural_proof(
    tmp_path, checkpoints, weights, fault
):
    import sys

    from cpswm.system.native_neural_production import verify_neural_evidence
    from cpswm.system.temporal_target_position import TemporalTargetPositionProducer

    case = make_case(tmp_path / "state.db", checkpoints, weights)
    try:
        stream = case["stream"]
        camera = PublicPixelCamera(stream._scope)
        capture(case, camera)
        command = issue(case)
        delivery = stream.execute_observation(command, executor=camera)
        before = state(case)
        attacked, proofs = [], []
        boundary = {
            "admission": "_register_native_raw_context",
            "published": "_cancel_stale_joint_commands",
        }.get(fault)

        def attack(frame, event, value):
            if event != "return":
                return
            if boundary and frame.f_code.co_name == boundary:
                attacked.append(True)
                raise RuntimeError("injected association transaction failure")
            if (
                frame.f_code is TemporalTargetPositionProducer.produce.__code__
                and frame.f_locals.get("self") is case["candidate"]
                and not attacked
            ):
                # Corrupt a complete target base BEFORE the genuine neural q proof.
                receipts = list(value.receipts)
                if fault == "statistic":
                    from dataclasses import replace

                    idx = next(
                        i
                        for i, r in enumerate(receipts)
                        if r.proposal.proposed_state.instance_association_key != "unknown_instance"
                    )
                    receipt = receipts[idx]
                    particle = receipt.proposal.proposed_state
                    analytic = value.statistics[particle.particle_id]
                    changed = replace(
                        analytic,
                        information_vector=(
                            analytic.information_vector[0] + 1.0,
                            *analytic.information_vector[1:],
                        ),
                    )
                    value.statistics[particle.particle_id] = changed
                    receipts[idx] = receipt.model_copy(
                        update={
                            "proposal": receipt.proposal.model_copy(
                                update={
                                    "proposed_state": particle.model_copy(
                                        update={"statistic_state_ref": changed.reference}
                                    )
                                }
                            )
                        }
                    )
                    object.__setattr__(value, "receipts", tuple(receipts))
                elif fault == "aggregate":
                    object.__setattr__(
                        value, "unresolved_log_weight", value.unresolved_log_weight + 1.0
                    )
                else:
                    idx = next(
                        i
                        for i, r in enumerate(receipts)
                        if (
                            r.proposal.proposed_state.instance_association_key == "unknown_instance"
                        )
                        == (fault == "unknown")
                    )
                    field = (
                        "transition_log_probability"
                        if fault == "association_gate"
                        else "observation_log_likelihood"
                    )
                    receipts[idx] = receipts[idx].model_copy(
                        update={field: getattr(receipts[idx], field) - 1.0}
                    )
                    object.__setattr__(value, "receipts", tuple(receipts))
                attacked.append(True)
            if (
                frame.f_code is NeuralNativeProducer.produce.__code__
                and frame.f_locals.get("self") is case["joint"]
                and value is not None
            ):
                verify_neural_evidence(value.neural_evidence)
                proofs.append(True)

        original = sys.getprofile()
        sys.setprofile(attack)
        try:
            with pytest.raises(
                (RuntimeError, ValueError),
                match=r"injected association|complete owner recomputation",
            ):
                stream.consume_owned_position_observation(command.action_id)
        finally:
            sys.setprofile(original)
        assert attacked
        if not boundary:
            assert proofs == [True]
        assert state(case) == before and len(stream._position_consumptions) == 1
        assert stream.observation_history()[-1][1] == delivery
        stream.consume_owned_position_observation(command.action_id)
        assert camera.calls == 2
    finally:
        case["store"].close()


@pytest.mark.parametrize("remove_selected", [True, False])
def test_pair_retraction_and_replay_preserve_full_branch_lineage(
    tmp_path, checkpoints, weights, remove_selected
):
    from test_owned_position_update import withdraw

    from cpswm.system.native_joint_replay import consumed_schedule

    case = make_case(
        tmp_path / "state.db", checkpoints, weights, selected_index=0 if remove_selected else 1
    )
    try:
        stream = case["stream"]
        initial = consumed_schedule(stream._system.core._particle_workspace)
        camera = PublicPixelCamera(stream._scope)
        capture(case, camera)
        command = issue(case)
        stream.execute_observation(command, executor=camera)
        update = stream.consume_owned_position_observation(command.action_id)
        branches = len(case["candidate"].last_diagnostic["branches"])
        for index in range(case["selected_index"] + 1, 3):
            advance(case, index)
        withdraw(
            case,
            case["native_selected_record_id"]
            if remove_selected
            else str(initial[0].context.source.transition.after.metadata.record_id),
        )
        before = semantic_state(stream)
        stream.replay_joint_posterior()
        assert semantic_state(stream) == before and camera.calls == 2
        schedule = consumed_schedule(stream._system.core._particle_workspace)
        if remove_selected:
            assert all(x.context.observation_update is None for x in schedule)
            assert not case["candidate"].consumed_keys
            with pytest.raises(ValueError, match="withdrawn"):
                stream.consume_owned_position_observation(command.action_id)
        else:
            assert [
                x.context.observation_update for x in schedule if x.context.observation_update
            ] == list(stream._position_consumptions.values())
            assert len(case["candidate"].last_diagnostic["branches"]) == branches
            assert stream.consume_owned_position_observation(command.action_id) == update
    finally:
        case["store"].close()


class VaryingDepthCamera(PublicPixelCamera):
    def execute(self, command):
        self.calls += 1
        image = public_image()
        h, w = image.shape[:2]
        event = event_for()
        event.frame = image
        event.depth_frame = np.full((h, w), 1.99 + self.calls * 0.02, dtype=np.float32)
        event.metadata.update(screenWidth=w, screenHeight=h, fov=60.0)
        capture_time = command.decision_time + timedelta(seconds=1)
        response = rgbd_response(str(command.action_id), event)
        response["capture_time"] = capture_time.isoformat()
        when = capture_time + timedelta(seconds=1)
        rows = observations_from_response(
            response,
            action_id=command.action_id,
            scope=self.scope,
            arrival=when,
            provenance=dict(
                worker="a" * 64,
                unity="b" * 64,
                house="c" * 64,
                capture_configuration=content_sha256((PROFILE, w, h, 60.0, 0.1, 20.0, False)),
            ),
        )
        return ObservationDelivery(command.action_id, rows, True, "", when)


def test_new_correlated_depth_and_loss_preserve_unknown(tmp_path, checkpoints, weights):
    case = make_case(tmp_path / "state.db", checkpoints, weights)
    try:
        stream = case["stream"]
        camera = VaryingDepthCamera(stream._scope)
        from test_owned_position_update import PositionCameraModel

        from cpswm.system.continuous_camera_collection import collect_posterior_step

        views = []
        for _ in range(3):
            step = collect_posterior_step(
                stream,
                model=PositionCameraModel(stream),
                executor=camera,
                decision_time=case["when"],
            )
            assert step.position_update_status == "QUERY_CONSUMED"
            case["when"] = step.delivery.received_at + timedelta(seconds=1)
            views.append(stream.current_joint_decision_view().content_sha256)
        assert len(set(views)) == 3
        d = case["candidate"].last_diagnostic
        assert any(b["position"]["prefix_length"] == 3 for b in d["branches"] if b["position"])
        count = len(d["branches"])
        capture(case, PublicPixelCamera(stream._scope, empty=True))
        d = case["candidate"].last_diagnostic
        assert len(d["branches"]) == count
        assert d["sequence"]["records"][-1]["status"] == "UNKNOWN"
        assert all(b["position_log_ratio"] == 0 for b in d["branches"])
    finally:
        case["store"].close()


@pytest.mark.parametrize("index", [0, 1])
def test_capture_withdrawal_recomputes_suffix_and_keeps_acquisition(
    tmp_path, checkpoints, weights, index
):
    from run_correction_replay_comparison import OracleProducer

    from cpswm.system.native_joint_replay import consumed_schedule
    from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput

    case = make_case(tmp_path / "state.db", checkpoints, weights)
    try:
        stream = case["stream"]
        camera = VaryingDepthCamera(stream._scope)
        commands = [capture(case, camera)[0] for _ in range(3)]
        semantic = semantic_state(stream)
        physical = stream.observation_history()
        raw = dict(stream._raw)
        stream.withdraw_owned_position_observation(
            commands[index].action_id, reason="controlled withdrawal test"
        )
        assert semantic_state(stream) == semantic
        assert stream.observation_history() == physical and stream._raw == raw and camera.calls == 3
        updates = [
            u.context.observation_update
            for u in consumed_schedule(stream._system.core._particle_workspace)
            if u.context.observation_update
        ]
        assert len(updates) == (0 if index == 0 else 2)
        assert len(case["candidate"].consumed_keys) == len(updates)
        if index:
            assert [u.action_id for u in updates] == [commands[0].action_id, commands[2].action_id]
            assert any(
                b["position"]["prefix_length"] == 2
                for b in case["candidate"].last_diagnostic["branches"]
                if b["position"]
            )
        before = state(case)
        stream.withdraw_owned_position_observation(
            commands[index].action_id, reason="controlled withdrawal test"
        )
        assert state(case) == before
        with pytest.raises(ValueError, match="withdrawn"):
            stream.consume_owned_position_observation(commands[index].action_id)
        resumed = ContinuousEvidenceInput.resume(
            case["store"],
            producer=OracleProducer(),
            context_builder=case["builder"],
            joint_producer=association_joint(case),
            observation_decoder=RGBDSupportDecoder(),
        )
        assert resumed.current_joint_decision_view() == stream.current_joint_decision_view()
        with pytest.raises(ValueError, match="conflicts"):
            resumed.withdraw_owned_position_observation(
                commands[index].action_id, reason="changed reason"
            )
    finally:
        case["store"].close()


def test_middle_withdrawal_failure_rolls_back_tombstone_and_replay(tmp_path, checkpoints, weights):
    import sys

    case = make_case(tmp_path / "state.db", checkpoints, weights)
    try:
        stream = case["stream"]
        camera = VaryingDepthCamera(stream._scope)
        commands = [capture(case, camera)[0] for _ in range(2)]
        before = state(case)

        def fault(frame, event, value):
            if event == "return" and frame.f_code.co_name == "_cancel_stale_joint_commands":
                raise RuntimeError("withdrawal replay fault")

        old = sys.getprofile()
        sys.setprofile(fault)
        try:
            with pytest.raises(RuntimeError, match="withdrawal replay fault"):
                stream.withdraw_owned_position_observation(
                    commands[1].action_id, reason="test rollback"
                )
        finally:
            sys.setprofile(old)
        assert state(case) == before
        assert (
            not stream._position_withdrawals
            and not stream._system.core._particle_observation_withdrawals
        )
        stream.withdraw_owned_position_observation(commands[1].action_id, reason="test rollback")
        assert camera.calls == 2 and len(case["candidate"].consumed_keys) == 1
    finally:
        case["store"].close()


@pytest.mark.parametrize("committed", [False, True])
def test_sqlite_uncertainty_requires_recovery_without_repeating_camera(
    tmp_path, checkpoints, weights, monkeypatch, committed
):
    from run_correction_replay_comparison import OracleProducer

    from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput

    case = make_case(tmp_path / "state.db", checkpoints, weights)
    try:
        stream, store = case["stream"], case["store"]
        camera = VaryingDepthCamera(stream._scope)
        capture(case, camera)
        command = issue(case)
        delivery = stream.execute_observation(command, executor=camera)
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
            joint_producer=association_joint(case),
            observation_decoder=RGBDSupportDecoder(),
        )
        assert len(resumed._position_consumptions) == (2 if committed else 1)
        assert resumed.observation_history()[-1][1] == delivery
        resumed.consume_owned_position_observation(command.action_id)
        assert len(resumed._position_consumptions) == 2 and camera.calls == 2
    finally:
        case["store"].close()


def test_loaded_tracker_alias_is_bound(tmp_path, checkpoints, weights, monkeypatch):
    from cpswm.perception_mapping import natural_target_sequence

    case = make_case(tmp_path / "state.db", checkpoints, weights)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(natural_target_sequence, "InitializedPixelTargetTracker", object)
            with pytest.raises(ValueError, match="alias changed"):
                case["candidate"].binding_sha256
        assert case["candidate"].binding_sha256
    finally:
        case["store"].close()
