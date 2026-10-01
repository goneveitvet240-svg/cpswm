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
from cpswm.perception_mapping.appearance_geometry_association import associate
from cpswm.perception_mapping.unity_rgbd import PROFILE, observations_from_response
from cpswm.system.appearance_geometry_position import AppearanceGeometryPositionProducer
from cpswm.system.native_neural_production import NeuralNativeProducer
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_continuous_input import ObservationDelivery

checkpoints = _checkpoints
cpu_threads = _cpu_threads
SOURCE = content_sha256("appearance-geometry-transaction-test@1")


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
    )
    models = fixture_models()
    candidate = AppearanceGeometryPositionProducer(configuration=config, **models)
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


def pair_collect(case):
    stream = case["stream"]
    camera = PublicPixelCamera(stream._scope)
    reference = issue(case)
    first = stream.execute_observation(reference, executor=camera)
    case["when"] = first.received_at + timedelta(seconds=1)
    command = issue(case)
    delivery = stream.execute_observation(command, executor=camera)
    return reference, command, delivery, camera


def test_owned_pair_branches_update_and_duplicate_is_inert(tmp_path, checkpoints, weights):
    case = make_case(tmp_path / "state.db", checkpoints, weights)
    try:
        stream = case["stream"]
        semantic, prior = semantic_state(stream), weight_state(case)
        reference, command, _delivery, camera = pair_collect(case)
        update = stream.consume_owned_position_observation(command.action_id)
        assert update.reference.action_id == reference.action_id
        assert semantic_state(stream) == semantic and weight_state(case) != prior
        diagnostic = case["candidate"].last_diagnostic
        assert diagnostic["association"]["branches"]
        assert len(diagnostic["branches"]) == len(diagnostic["association"]["branches"]) + 2
        before = state(case)
        assert stream.consume_owned_position_observation(command.action_id) == update
        assert state(case) == before and camera.calls == 2
        assert stream.joint_observation_updates() == ()
        advance(case, 2)
        assert len(case["candidate"].last_diagnostic["branches"]) == len(diagnostic["branches"])
    finally:
        case["store"].close()


def test_ambiguous_multi_candidate_unknown_and_count_normalization():
    from math import exp

    def row(key, color, xyz, category="bottle"):
        return dict(id=key, category=category, histogram=color, observation=dict(world_point_m=xyz))

    ref = [row("r1", [1.0, 0.0], [0.0, 0.0, 0.0])]
    query = [row("q1", [1.0, 0.0], [0.0, 0.0, 0.0]), row("q2", [1.0, 0.0], [0.0, 0.0, 0.0])]
    result = associate(ref, query)
    gates = [exp(b["log_gate"]) for b in result["branches"]]
    assert len(gates) == 2 and gates[0] == gates[1]
    assert sum(gates) + exp(result["unknown_log_gate"]) == pytest.approx(1.0)
    one = associate(ref, query[:1])
    assert sum(gates) == pytest.approx(exp(one["branches"][0]["log_gate"]))
    ref.append(row("r2", [1.0, 0.0], [0.0, 0.0, 0.0]))
    assert associate(ref, query)["unknown_log_gate"] == pytest.approx(result["unknown_log_gate"])
    for changed in (row("q", [0.0, 1.0], [0.0, 0.0, 0.0]), row("q", [1.0, 0.0], [3.0, 0.0, 0.0])):
        assert associate(ref, [changed])["unknown_log_gate"] > one["unknown_log_gate"]
    mismatch = associate(ref, [row("other", [1.0, 0.0], [0.0, 0.0, 0.0], "cup")])
    assert mismatch["branches"] == [] and mismatch["unknown_log_gate"] == 0.0


def test_default_collector_reference_then_query(tmp_path, checkpoints, weights):
    from test_owned_position_delivery import problem_for
    from test_owned_position_update import PositionCameraModel

    from cpswm.system.continuous_camera_collection import collect_posterior_step

    case = make_case(tmp_path / "state.db", checkpoints, weights)
    try:
        stream = case["stream"]
        before = stream.current_joint_decision_view()
        camera = PublicPixelCamera(stream._scope)
        first = collect_posterior_step(
            stream, model=PositionCameraModel(stream), executor=camera, decision_time=case["when"]
        )
        assert first.position_update_status == "REFERENCE_ONLY"
        assert stream.current_joint_decision_view() == before and not stream._position_consumptions
        second = collect_posterior_step(
            stream,
            model=PositionCameraModel(stream),
            executor=camera,
            decision_time=first.delivery.received_at + timedelta(seconds=1),
        )
        assert second.position_update_status == "QUERY_CONSUMED"
        view = stream.current_joint_decision_view()
        assert view != before and camera.calls == 2
        problem = problem_for(stream, second.delivery.received_at + timedelta(seconds=1))
        assert problem.source_belief_sha256 == view.content_sha256
        plan, _ = problem.select(view, stream._system.cause_information_planner)
        assert plan.scores
    finally:
        case["store"].close()


def association_joint(case):
    return NeuralNativeProducer(
        AppearanceGeometryPositionProducer(configuration=case["config"], **case["models"]),
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
        _, command, _, camera = pair_collect(case)
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
                    "from test_appearance_geometry_position import fresh_restore; "
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
    "fault", ["admission", "published", "association_gate", "position", "unknown", "aggregate"]
)
def test_rollback_and_complete_forgery_with_real_neural_proof(
    tmp_path, checkpoints, weights, fault
):
    import sys

    from cpswm.system.appearance_geometry_position import AppearanceGeometryPositionProducer
    from cpswm.system.native_neural_production import verify_neural_evidence

    case = make_case(tmp_path / "state.db", checkpoints, weights)
    try:
        stream = case["stream"]
        _, command, delivery, camera = pair_collect(case)
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
                frame.f_code is AppearanceGeometryPositionProducer.produce.__code__
                and frame.f_locals.get("self") is case["candidate"]
                and not attacked
            ):
                # Corrupt a complete target base BEFORE the genuine neural q proof.
                receipts = list(value.receipts)
                if fault == "aggregate":
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
        assert state(case) == before and not stream._position_consumptions
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
        _, command, _, camera = pair_collect(case)
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
            ] == [update]
            assert len(case["candidate"].last_diagnostic["branches"]) == branches
            assert stream.consume_owned_position_observation(command.action_id) == update
    finally:
        case["store"].close()


def test_original_reference_tamper_and_missing_reference_fail_closed(
    tmp_path, checkpoints, weights
):
    from dataclasses import replace

    case = make_case(tmp_path / "state.db", checkpoints, weights)
    try:
        stream = case["stream"]
        camera = PublicPixelCamera(stream._scope)
        reference = issue(case)
        delivery = stream.execute_observation(reference, executor=camera)
        before = state(case)
        with pytest.raises(ValueError, match="earlier owned reference"):
            stream.consume_owned_position_observation(reference.action_id)
        assert state(case) == before
        case["when"] = delivery.received_at + timedelta(seconds=1)
        query = issue(case)
        stream.execute_observation(query, executor=camera)
        before = state(case)
        stream._observation_status[reference.action_id] = replace(
            delivery, received_at=delivery.received_at + timedelta(microseconds=1)
        )
        with pytest.raises(ValueError, match="original issue/delivery acceptance"):
            stream.consume_owned_position_observation(query.action_id)
        stream._observation_status[reference.action_id] = delivery
        assert state(case) == before
        stream.consume_owned_position_observation(query.action_id)
    finally:
        case["store"].close()


def test_loaded_appearance_alias_change_rejected_then_recovers(
    tmp_path, checkpoints, weights, monkeypatch
):
    import cpswm.perception_mapping.appearance_geometry_association as module

    case = make_case(tmp_path / "state.db", checkpoints, weights)
    try:
        _, query, _, _ = pair_collect(case)
        before = state(case)
        with monkeypatch.context() as patch:
            patch.setattr(module, "decode_rgb", lambda *a, **kw: None)
            with pytest.raises(ValueError, match="alias changed"):
                case["stream"].consume_owned_position_observation(query.action_id)
        assert state(case) == before
        case["stream"].consume_owned_position_observation(query.action_id)
    finally:
        case["store"].close()


class MontageCamera:
    def __init__(self, scope, *, empty=False, invalid=False):
        self.scope, self.empty, self.invalid, self.calls = scope, empty, invalid, 0

    def execute(self, command):
        self.calls += 1
        image = public_image()
        if self.empty:
            image = np.zeros_like(image)
        image = image.copy()
        crop = image[80:175, 62:110].copy()
        for x in (15, 180):
            image[60:155, x : x + 48] = crop
        h, w = image.shape[:2]
        event = event_for()
        event.frame = image
        event.depth_frame = np.full((h, w), 0.0 if self.invalid else 1.99, dtype=np.float32)
        event.metadata.update(screenWidth=w, screenHeight=h, fov=60.0)
        capture = command.decision_time + timedelta(seconds=1)
        response = rgbd_response(str(command.action_id), event)
        response["capture_time"] = capture.isoformat()
        when = capture + timedelta(seconds=1)
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


def test_multiple_real_detector_branches_reach_native_weights_and_pose(
    tmp_path, checkpoints, weights
):
    from math import exp

    case = make_case(tmp_path / "state.db", checkpoints, weights)
    try:
        stream = case["stream"]
        camera = MontageCamera(stream._scope)
        ref = issue(case)
        first = stream.execute_observation(ref, executor=camera)
        case["when"] = first.received_at + timedelta(seconds=1)
        query = issue(case)
        stream.execute_observation(query, executor=camera)
        stream.consume_owned_position_observation(query.action_id)
        diagnostic = case["candidate"].last_diagnostic
        assert len(diagnostic["association"]["branches"]) >= 2
        known = [b for b in diagnostic["branches"] if b["position"] is not None]
        assert len(known) >= 2 and len({b["query_id"] for b in known}) == len(known)
        workspace = stream._system.core._particle_workspace
        assert len(workspace.batch.particle_weights) == len(known) + 2
        records = {str(k): r for k, r in workspace.records.items()}
        assert len({records[b["particle_id"]].statistics.reference for b in known}) >= 2
        # Independent full target sum checks q cancellation and unknown accounting.
        terms = [
            r.prior_log_weight + r.transition_log_probability + r.observation_log_likelihood
            for r in workspace.receipts
        ]
        top = max([diagnostic["aggregate_log_weight"], *terms])
        masses = [exp(t - top) for t in terms]
        aggregate = exp(diagnostic["aggregate_log_weight"] - top)
        total = sum(masses) + aggregate
        assert [w.posterior_probability for w in workspace.batch.particle_weights] == pytest.approx(
            [m / total for m in masses]
        )
        assert stream.current_joint_decision_view().unresolved_probability == pytest.approx(
            aggregate / total
        )
    finally:
        case["store"].close()


def test_complete_resealed_association_readout_rejected(tmp_path, checkpoints, weights):
    import sys
    from math import exp, log

    from cpswm.perception_mapping import appearance_geometry_association as module
    from cpswm.system.native_neural_production import verify_neural_evidence

    case = make_case(tmp_path / "state.db", checkpoints, weights)
    try:
        _, query, _, camera = pair_collect(case)
        before = state(case)
        attacked, proofs = [], []

        def attack(frame, event, value):
            if event != "return":
                return
            if frame.f_code is module.associate.__code__ and not attacked:
                # A normalized plausible gate, not malformed or incomplete input.
                values = [b["log_gate"] + 0.7 for b in value["branches"]]
                z = log(sum(exp(v) for v in values) + exp(value["unknown_log_gate"]))
                for b, v in zip(value["branches"], values, strict=True):
                    b["log_gate"] = v - z
                value["unknown_log_gate"] -= z
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
            with pytest.raises(ValueError, match="complete owner recomputation"):
                case["stream"].consume_owned_position_observation(query.action_id)
        finally:
            sys.setprofile(original)
        assert attacked == proofs == [True] and state(case) == before
        case["stream"].consume_owned_position_observation(query.action_id)
        assert camera.calls == 2
    finally:
        case["store"].close()


@pytest.mark.parametrize("invalid_reference", [False, True])
def test_reference_depth_and_disabled_control_do_not_invent_position(
    tmp_path, checkpoints, weights, invalid_reference
):
    case = make_case(tmp_path / "state.db", checkpoints, weights, enabled=invalid_reference)
    try:
        stream = case["stream"]
        prior = weight_state(case)
        ref = issue(case)
        first = stream.execute_observation(
            ref, executor=PublicPixelCamera(stream._scope, invalid=invalid_reference)
        )
        case["when"] = first.received_at + timedelta(seconds=1)
        query = issue(case)
        stream.execute_observation(query, executor=PublicPixelCamera(stream._scope))
        stream.consume_owned_position_observation(query.action_id)
        diagnostic = case["candidate"].last_diagnostic
        assert all(b["position"] is None for b in diagnostic["branches"])
        assert all(
            r.transition_log_probability == 0.0
            for r in stream._system.core._particle_workspace.receipts
        )
        assert weight_state(case)["aggregate"] == pytest.approx(prior["aggregate"])
        if invalid_reference:
            assert diagnostic["association"]["branches"] == []
            assert diagnostic["association"]["unknown_log_gate"] == 0.0
        else:
            assert diagnostic["association"] is None and not diagnostic["active"]
    finally:
        case["store"].close()


def test_resealed_original_reference_payload_is_not_accepted(tmp_path, checkpoints, weights):
    from dataclasses import replace

    from test_unity_rgbd import rewrite_packet

    case = make_case(tmp_path / "state.db", checkpoints, weights)
    try:
        stream = case["stream"]
        reference, query, _, _ = pair_collect(case)
        delivery = stream._observation_status[reference.action_id]
        original_raw = dict(stream._raw)
        forged = rewrite_packet(
            delivery.observations, pose_changes={"position_m": [100.0, 200.0, 300.0]}
        )
        stream._observation_status[reference.action_id] = replace(delivery, observations=forged)
        for raw in forged:
            stream._raw[raw.envelope().identity.observation_id] = raw
        before = state(case)
        with pytest.raises(ValueError, match="original issue/delivery"):
            stream.consume_owned_position_observation(query.action_id)
        assert state(case) == before
        stream._raw = original_raw
        stream._observation_status[reference.action_id] = delivery
        stream.consume_owned_position_observation(query.action_id)
    finally:
        case["store"].close()
