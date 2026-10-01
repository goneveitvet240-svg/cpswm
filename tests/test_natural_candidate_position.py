"""Real pinned detector with archived live pixels and controlled depth/semantics.
PYTEST_DONT_REWRITE: durable fixture dependencies retain ordinary source code.
"""

import io
import os
import tarfile
from datetime import timedelta
from pathlib import Path

import numpy as np
import pytest
from run_correction_replay_comparison import build
from structure_two_backbone_wiring_probe import BackboneWiringProbe
from test_native_neural_production import checkpoints as _checkpoints
from test_native_neural_production import cpu_threads as _cpu_threads
from test_native_position_production import advance, fixture_models, weight_state
from test_owned_position_delivery import issue, state
from test_owned_position_update import semantic_state
from test_owned_rgbd_support import RGBDSupportDecoder
from test_unity_rgbd import event_for
from unity_rgbd_capture import rgbd_response

from cpswm.data_preflight.typed_proposal_networks import ARMS
from cpswm.perception_mapping.unity_rgbd import PROFILE, observations_from_response
from cpswm.system.controlled_position_producer import packet_binding
from cpswm.system.native_neural_production import NeuralNativeProducer
from cpswm.system.natural_candidate_position import (
    NaturalCandidatePositionProducer,
    candidate_readout,
)
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_continuous_input import ObservationDelivery

checkpoints = _checkpoints
cpu_threads = _cpu_threads
SOURCE = content_sha256("natural-candidate-transaction-test@1")


@pytest.fixture(scope="module")
def weights():
    path = Path(os.environ.get("CPSWM_SSDLITE_WEIGHTS", ""))
    if not path.is_file():
        pytest.skip("explicit local pinned SSDLite weights required")
    return path.resolve()


def public_image():
    path = Path(__file__).resolve().parents[1] / (
        "docs/reviews/pc_a/owned_observation_update_2026-10-01/evidence/live-transactions.tar.gz"
    )
    with tarfile.open(path) as archive:
        raw = archive.extractfile("live-local-sdk/transport/evaluator_only/sdk-events/004-rgb.npy")
        assert raw is not None
        return np.load(io.BytesIO(raw.read()), allow_pickle=False)


class PublicPixelCamera:
    def __init__(self, scope, *, empty=False, invalid=False):
        self.scope, self.empty, self.invalid, self.calls = scope, empty, invalid, 0

    def execute(self, command):
        self.calls += 1
        image = public_image()
        if self.empty:
            image = np.zeros_like(image)
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


def make_case(path, checkpoints, weights, *, enabled=True, selected_index=1):
    selected = BackboneWiringProbe.build(seed=171).observed_days()[selected_index].after
    config = dict(
        semantic_record_id=str(selected.metadata.record_id),
        enabled=enabled,
        weights_path=str(weights),
    )
    models = fixture_models()
    candidate = NaturalCandidatePositionProducer(configuration=config, **models)
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


def collect(case, **kwargs):
    command = issue(case)
    camera = PublicPixelCamera(case["stream"]._scope, **kwargs)
    delivery = case["stream"].execute_observation(command, executor=camera)
    return command, delivery, camera


def test_real_detector_candidates_update_same_semantics_and_deduplicate(
    tmp_path, checkpoints, weights
):
    case = make_case(tmp_path / "state.db", checkpoints, weights)
    try:
        stream = case["stream"]
        semantic = semantic_state(stream)
        neutral = weight_state(case)
        command, delivery, camera = collect(case)
        update = stream.consume_owned_position_observation(command.action_id)
        assert semantic_state(stream) == semantic
        assert weight_state(case) != neutral
        support = case["candidate"].last_diagnostic["natural_candidates"]
        assert support["frame"].candidates
        assert support["identity_status"] == "UNRESOLVED"
        assert not support["detector_scores_used_as_density"]
        assert support["selected"]["candidate"] in support["surface"]["candidates"]
        assert support["selected"]["seed_uv"] != [0, 0]
        expected = candidate_readout(
            delivery.observations,
            cutoff=delivery.received_at,
            weights_path=weights,
            affinity_model=case["models"]["affinity_model"],
            affinity_pin=case["models"]["affinity_pin"],
            estimator=case["models"]["position_model"]["estimator"],
            raw_sha256=packet_binding(delivery.observations)["raw_sha256"],
        )
        assert content_sha256(expected) == content_sha256(support)
        before = state(case)
        assert stream.consume_owned_position_observation(command.action_id) == update
        assert state(case) == before and camera.calls == 1
    finally:
        case["store"].close()


def natural_joint(case):
    return NeuralNativeProducer(
        NaturalCandidatePositionProducer(configuration=case["config"], **case["models"]),
        Path(case["checkpoint"]),
        manifest_sha256=case["pin"],
    )


@pytest.mark.parametrize(
    "name,kwargs",
    [
        ("test_complete_target_forgery_rolls_back_then_legal_retry", {"field": field})
        for field in ("known_ll", "unknown_ll", "aggregate", "transition")
    ]
    + [
        ("test_failure_rolls_back_computation_but_keeps_delivery_and_retry", {"boundary": boundary})
        for boundary in ("admission", "published")
    ]
    + [
        (
            "test_replay_retains_each_update_or_removes_its_semantic_dependency",
            {"remove_selected": value},
        )
        for value in (False, True)
    ],
)
def test_existing_transaction_attacks_with_real_natural_candidates(
    tmp_path, checkpoints, weights, monkeypatch, name, kwargs
):
    # Reuse transaction assertions, only adapt fixture constructors and camera.
    # No production function, verifier or model is replaced.
    import test_owned_position_update as matrix

    with monkeypatch.context() as patch:
        patch.setattr(
            matrix,
            "make_case",
            lambda path, checkpoints, **opts: make_case(path, checkpoints, weights, **opts),
        )
        patch.setattr(matrix, "collect", collect)
        patch.setattr(matrix, "fresh_joint", natural_joint)
        getattr(matrix, name)(tmp_path, checkpoints, **kwargs)


@pytest.mark.parametrize(
    "empty,invalid,reason",
    [(True, False, "no_detection_candidates"), (False, True, "no_valid_candidate_depth")],
)
def test_unavailable_support_preserves_delivery_and_all_state(
    tmp_path, checkpoints, weights, empty, invalid, reason
):
    case = make_case(tmp_path / "state.db", checkpoints, weights)
    try:
        command, delivery, camera = collect(case, empty=empty, invalid=invalid)
        before = state(case)
        with pytest.raises(ValueError, match=reason):
            case["stream"].consume_owned_position_observation(command.action_id)
        assert state(case) == before
        assert case["stream"].observation_history()[-1][1] == delivery
        assert case["stream"]._position_consumptions == {} and camera.calls == 1
        # A later usable capture can still be issued: failure was not counted.
        case["when"] = delivery.received_at + timedelta(seconds=1)
        command, _, second = collect(case)
        case["stream"].consume_owned_position_observation(command.action_id)
        assert second.calls == 1
    finally:
        case["store"].close()


def test_natural_profile_default_collector_updates_and_drives_next_decision(
    tmp_path, checkpoints, weights
):
    from test_owned_position_delivery import problem_for
    from test_owned_position_update import PositionCameraModel

    from cpswm.system.continuous_camera_collection import collect_posterior_step

    case = make_case(tmp_path / "state.db", checkpoints, weights)
    try:
        stream = case["stream"]
        before = semantic_state(stream)
        prior = stream.current_joint_decision_view()
        camera = PublicPixelCamera(stream._scope)
        step = collect_posterior_step(
            stream, model=PositionCameraModel(stream), executor=camera, decision_time=case["when"]
        )
        view = stream.current_joint_decision_view()
        assert semantic_state(stream) == before and view != prior
        problem = problem_for(stream, step.delivery.received_at + timedelta(seconds=1))
        assert problem.source_belief_sha256 == view.content_sha256
        plan, _ = problem.select(view, stream._system.cause_information_planner)
        assert plan.scores and camera.calls == 1
    finally:
        case["store"].close()


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
    joint = natural_joint(config)
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
        command, _, camera = collect(case)
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
                    "from test_natural_candidate_position import fresh_restore; "
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
        assert camera.calls == 1
    finally:
        case["store"].close()


def test_complete_forged_natural_readout_with_valid_neural_proof_rejected(
    tmp_path, checkpoints, weights
):
    import sys

    from cpswm.system import natural_candidate_position as natural
    from cpswm.system.native_neural_production import verify_neural_evidence

    case = make_case(tmp_path / "state.db", checkpoints, weights)
    try:
        command, delivery, camera = collect(case)
        before = state(case)
        attacked = []
        proofs = []

        def attack(frame, event, value):
            if event != "return":
                return
            if frame.f_code is natural.candidate_readout.__code__ and not attacked:
                selected = value["selected"]["observation"]
                selected["world_point_m"][0] += 2.0
                for row in value["surface"]["observations"]:
                    if (
                        row["measurement_id"] == selected["measurement_id"]
                        and row["estimator"] == selected["estimator"]
                    ):
                        row["world_point_m"] = list(selected["world_point_m"])
                attacked.append(True)
            if (
                frame.f_code is NeuralNativeProducer.produce.__code__
                and frame.f_locals.get("self") is case["joint"]
            ):
                verify_neural_evidence(value.neural_evidence)
                proofs.append(True)

        original = sys.getprofile()
        sys.setprofile(attack)
        try:
            with pytest.raises(ValueError, match="complete owner recomputation"):
                case["stream"].consume_owned_position_observation(command.action_id)
        finally:
            sys.setprofile(original)
        assert attacked == proofs == [True]
        assert state(case) == before
        assert case["stream"].observation_history()[-1][1] == delivery
        case["stream"].consume_owned_position_observation(command.action_id)
        assert camera.calls == 1
    finally:
        case["store"].close()


def test_loaded_selection_replacement_rejected_before_update_then_recovers(
    tmp_path, checkpoints, weights, monkeypatch
):
    from cpswm.system import natural_candidate_position as natural

    case = make_case(tmp_path / "state.db", checkpoints, weights)
    try:
        command, _, camera = collect(case)
        before = state(case)
        with monkeypatch.context() as patch:
            patch.setattr(natural, "candidate_readout", lambda *args, **kwargs: {})
            with pytest.raises(
                ValueError, match=r"dependency changed|implementation|producer dependency"
            ):
                case["stream"].consume_owned_position_observation(command.action_id)
        assert state(case) == before
        case["stream"].consume_owned_position_observation(command.action_id)
        assert camera.calls == 1
    finally:
        case["store"].close()
