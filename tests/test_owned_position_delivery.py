"""Actual owner issuance and read-only descriptions on controlled RGB-D.

Synthetic residuals, identity and camera; a real small neural checkpoint executes.
No Unity, real archive inference or new natural observation authority is claimed.
PYTEST_DONT_REWRITE: fixture decoder/producer code must retain recovery bindings.
"""

import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
from math import isfinite
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import torch
from controlled_position_producer import ControlledPositionProducer, packet_binding
from run_archive_native_bridge import retract_selected
from run_correction_replay_comparison import OracleProducer, build
from structure_two_backbone_wiring_probe import BackboneWiringProbe
from test_continuous_camera_collection import SOURCES
from test_native_neural_production import checkpoints as _checkpoints
from test_native_neural_production import cpu_threads as _cpu_threads
from test_native_position_production import advance, fixture_models
from test_owned_rgbd_support import RGBDCamera, RGBDSupportDecoder
from test_unity_rgbd import packet, rewrite_packet

from cpswm.contracts.grounded_search import ObservationActionCandidate
from cpswm.data_preflight.typed_proposal_networks import ARMS
from cpswm.perception_mapping import position_observation_model as position
from cpswm.system.continuous_state_codec import StateCodec
from cpswm.system.continuous_state_store import ContinuousStateStore
from cpswm.system.joint_camera_policy import CameraAlternative, JointCameraProblem
from cpswm.system.native_neural_production import NeuralNativeProducer
from cpswm.system.owned_position_delivery import (
    describe_current_owned_rgbd,
    require_current_owned_descriptor,
)
from cpswm.system.reproducibility import content_sha256, content_uuid
from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput, ObservationDelivery
from cpswm.system.structure_two_particle_workspace import native_content_sha256

checkpoints = _checkpoints
cpu_threads = _cpu_threads
SOURCE = content_sha256("owned-rgbd-description-controlled-fixture@1")


def make_case(path, checkpoints, *, underflow=False):
    initial = BackboneWiringProbe.build(seed=171)
    selected = initial.observed_days()[0].after
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
        enabled=underflow,
    )
    models = fixture_models()
    if underflow:
        models["position_model"]["bias"] = [100.0, 0.0, 0.0]
        models["position_pin"] = position.checkpoint_sha256(models["position_model"])
    candidate = ControlledPositionProducer(configuration=config, **models)
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
        rows=rows,
        checkpoint=checkpoint,
        pin=pin,
        selected_index=0,
    )
    case["when"] = advance(case, 0) + timedelta(seconds=1)
    return case


def problem_for(stream, when):
    view = stream.current_joint_decision_view()
    atoms = tuple(view.verification_belief().posterior)
    target = max(view.atoms, key=lambda atom: atom.probability).particle_id
    likelihood = {a: 0.95 if a == target else 0.05 for a in atoms}
    candidate = ObservationActionCandidate(
        action_id=content_uuid("descriptor-controlled-question", view.content_sha256),
        action_type="move_viewpoint",
        label="controlled descriptor test",
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
    return JointCameraProblem(
        model_sources=SOURCES,
        source_belief_sha256=view.content_sha256,
        source_observation_ids=tuple(
            r.envelope().identity.observation_id for r in stream.visible_prefix(cutoff=when)
        ),
        alternatives=(CameraAlternative(candidate=candidate, action="RotateRight", degrees=30),),
        consolidation_decision_utilities={
            content_uuid("descriptor", "noop"): dict.fromkeys(atoms, 0.0)
        },
        terminal_decision_utilities={a: {b: float(a == b) for b in atoms} for a in atoms},
        privacy_budget=1.0,
        minimum_net_value=0.0,
    )


def issue(case):
    stream, when = case["stream"], case["when"]
    _, command = stream.prepare_posterior_observation(problem_for(stream, when), decision_time=when)
    assert command is not None
    return command


def collect(case):
    command = issue(case)
    camera = RGBDCamera(case["stream"]._scope)
    delivery = case["stream"].execute_observation(command, executor=camera)
    assert camera.calls == 1
    return command, delivery, camera


def state(case):
    stream, store = case["stream"], case["store"]
    core = stream._system.core
    return (
        native_content_sha256(core._particle_workspace.state_payload()),
        native_content_sha256(core._hybrid_loop.ledger.export_state()),
        native_content_sha256(case["joint"].checkpoint_state()),
        StateCodec().dumps(
            (
                stream._raw,
                stream._observation_commands,
                stream._observation_status,
                stream._observation_native_origins,
                stream._advanced,
            )
        ),
        store._db.execute("SELECT * FROM checkpoint").fetchall(),
        stream._last_arrival,
        stream._last_cutoff,
        stream._busy,
    )


def profile(call):
    counts = Counter()

    def trace(frame, event, _arg):
        if event == "call" and frame.f_code.co_name in {
            "score_support",
            "produce",
            "condition",
            "decode",
            "measurements",
            "execute",
            "save",
        }:
            counts[frame.f_globals.get("__name__", "") + "." + frame.f_code.co_name] += 1

    sys.setprofile(trace)
    try:
        result = call()
    finally:
        sys.setprofile(None)
    return result, dict(counts)


def test_actual_owner_rgbd_description_full_parent_no_side_effects(tmp_path, checkpoints):
    case = make_case(tmp_path / "state.db", checkpoints)
    try:
        command, delivery, camera = collect(case)
        before = state(case)
        descriptor, first = profile(
            lambda: describe_current_owned_rgbd(case["stream"], command.action_id)
        )
        again, warm = profile(lambda: require_current_owned_descriptor(case["stream"], descriptor))
        (tmp_path / "guard-counts.json").write_text(
            json.dumps(dict(first=first, warm=warm), indent=2)
        )
        assert again == descriptor and state(case) == before and camera.calls == 1
        assert descriptor.camera.action_id == command.action_id
        assert [r.observation_id for r in descriptor.members] == [
            r.envelope().identity.observation_id for r in delivery.observations
        ]
        assert len(descriptor.parent_log_weights) == 2
        assert (
            descriptor.parent_input_sha256
            == case["stream"]._system.core._particle_input_anchors[descriptor.evidence_cluster_id]
        )
        assert descriptor.posterior_updated is False and descriptor.consumption_authority is False
        for counts in (first, warm):
            assert not any(
                k.rsplit(".", 1)[-1] in {"measurements", "execute", "save"}
                or k
                in {
                    "test_joint_camera_feedback.decode",
                    "test_owned_rgbd_support.decode",
                }
                for k in counts
            )
    finally:
        case["store"].close()


def test_complete_resealed_descriptors_rejected_then_legal(tmp_path, checkpoints):
    case = make_case(tmp_path / "state.db", checkpoints)
    try:
        command, _, _ = collect(case)
        original = describe_current_owned_rgbd(case["stream"], command.action_id)
        before = state(case)
        fake_member = replace(original.members[0], payload_sha256="1" * 64)
        candidates = [
            replace(
                original,
                members=(fake_member, *original.members[1:]),
                delivery_sha256=content_sha256(fake_member),
            ),
            replace(original, source_id=uuid4(), source_body_sha256="1" * 64),
            replace(original, parent_input_sha256="2" * 64, parent_log_weights=((uuid4(), -1.0),)),
            replace(original, scope=(uuid4(), *original.scope[1:])),
            replace(original, received_at=original.received_at + timedelta(seconds=1)),
            replace(original, consumption_authority=0),
            replace(original, posterior_updated=True),
            replace(original, members=list(original.members)),
            replace(original, camera=original.camera.model_copy(update={"width": True})),
            replace(original, implementation_sha256="9" * 64),
        ]
        for fake in candidates:
            assert len(fake.content_sha256) == 64  # Full self-resealed value, not a missing hash.
            with pytest.raises(ValueError, match="descriptor differs"):
                require_current_owned_descriptor(case["stream"], fake)
            assert state(case) == before
        for value in (str(command.action_id), 1, True):
            with pytest.raises(ValueError, match="exact UUID"):
                describe_current_owned_rgbd(case["stream"], value)
        with pytest.raises(ValueError, match="invalid descriptor type"):
            require_current_owned_descriptor(case["stream"], original.__dict__)
        assert require_current_owned_descriptor(case["stream"], original) == original
        assert state(case) == before
    finally:
        case["store"].close()


def test_archive_unmodeled_pending_failed_and_future_input_rejected(tmp_path, checkpoints):
    case = make_case(tmp_path / "state.db", checkpoints)
    try:
        stream = case["stream"]
        # This raw capture was actually admitted to the protected owner but never issued.
        with pytest.raises(ValueError, match="not issued"):
            describe_current_owned_rgbd(stream, UUID(int=901))
        command = issue(case)
        with pytest.raises(ValueError, match="successful RGB-D"):
            describe_current_owned_rgbd(stream, command.action_id)

        class FailedCamera:
            def execute(self, cmd):
                return ObservationDelivery(
                    cmd.action_id,
                    (),
                    False,
                    "controlled failure",
                    cmd.decision_time + timedelta(seconds=1),
                )

        stream.execute_observation(command, executor=FailedCamera())
        with pytest.raises(ValueError, match="successful RGB-D"):
            describe_current_owned_rgbd(stream, command.action_id)
        # Restore only for separate attack variants below; no replacement is called legal.
        delivered_rows, received = packet(
            action=command.action_id,
            scope=stream._scope,
            capture=command.decision_time + timedelta(seconds=1),
        )
        old = stream._observation_status[command.action_id]
        stream._observation_status[command.action_id] = ObservationDelivery(
            command.action_id, delivered_rows, True, "", received
        )
        with pytest.raises(ValueError, match=r"received history|original owner"):
            describe_current_owned_rgbd(stream, command.action_id)
        stream._observation_status[command.action_id] = old
        when = stream._last_arrival + timedelta(seconds=1)
        plain = stream.prepare_observation(
            action="Pass",
            degrees=0,
            reason="controlled direct command",
            source_ids=command.source_ids,
            decision_time=when,
        )
        stream.execute_observation(plain, executor=RGBDCamera(stream._scope))
        with pytest.raises(ValueError, match="modeled owner"):
            describe_current_owned_rgbd(stream, plain.action_id)
    finally:
        case["store"].close()


def test_complete_delivery_replacement_pairing_and_legal_recovery(tmp_path, checkpoints):
    case = make_case(tmp_path / "state.db", checkpoints)
    try:
        command, delivery, _ = collect(case)
        stream = case["stream"]
        original = describe_current_owned_rgbd(stream, command.action_id)
        before = state(case)
        rewritten = rewrite_packet(delivery.observations, pose_changes={"yaw_degrees": 23.0})
        for fake in (
            replace(delivery, observations=rewritten),
            replace(delivery, observations=tuple(reversed(delivery.observations))),
            replace(delivery, observations=(delivery.observations[0],) * 3),
            replace(delivery, success=1),
            replace(delivery, received_at=delivery.received_at + timedelta(seconds=1)),
        ):
            stream._observation_status[command.action_id] = fake
            with pytest.raises(ValueError):
                describe_current_owned_rgbd(stream, command.action_id)
            stream._observation_status[command.action_id] = delivery
        # Coherent wrong depth unit on both raw holders still fails the strict RGB-D contract.
        bad = tuple(
            replace(r, depth_unit="cm") if i == 1 else r
            for i, r in enumerate(delivery.observations)
        )
        stream._observation_status[command.action_id] = replace(delivery, observations=bad)
        key = bad[1].envelope().identity.observation_id
        saved_raw = stream._raw[key]
        stream._raw[key] = bad[1]
        with pytest.raises(ValueError, match="units"):
            describe_current_owned_rgbd(stream, command.action_id)
        stream._raw[key] = saved_raw
        stream._observation_status[command.action_id] = delivery
        assert require_current_owned_descriptor(stream, original) == original
        assert state(case) == before
    finally:
        case["store"].close()


def test_new_semantic_source_and_feedback_prior_are_stale(tmp_path, checkpoints):
    case = make_case(tmp_path / "state.db", checkpoints)
    try:
        command, delivery, _ = collect(case)
        stream = case["stream"]
        original = describe_current_owned_rgbd(stream, command.action_id)
        # Second modeled command is genuinely issued from the updated camera-feedback view.
        case["when"] = delivery.received_at + timedelta(seconds=1)
        second, _, _ = collect(case)
        with pytest.raises(ValueError, match="unchanged native-base"):
            describe_current_owned_rgbd(stream, second.action_id)
        advance(case, 1, publish=False)
        with pytest.raises(ValueError, match=r"source changed|stale"):
            require_current_owned_descriptor(stream, original)
        stream.produce_joint_posterior()
        with pytest.raises(ValueError, match="stale"):
            require_current_owned_descriptor(stream, original)
        old_runtime = stream._system.core._particle_workspace.runtime_id
        retract_selected(case, case["native_selected_record_id"])
        assert stream._system.core._particle_workspace.runtime_id != old_runtime
        with pytest.raises(ValueError, match="stale"):
            require_current_owned_descriptor(stream, original)
    finally:
        case["store"].close()


def fresh_restore(folder):
    """Real new process: do not construct another ContinuousEvidenceInput first."""
    torch.set_num_threads(2)
    folder = Path(folder)
    config = json.loads((folder / "restore.json").read_text())
    candidate = ControlledPositionProducer(configuration=config["config"], **config["models"])
    joint = NeuralNativeProducer(
        candidate, Path(config["checkpoint"]), manifest_sha256=config["pin"]
    )
    store = ContinuousStateStore(
        folder / "copy.db", source_identity=SOURCE, dependency_identity=content_sha256(sys.version)
    )

    def unused_builder(*_args):
        raise AssertionError("read-only recovery must not advance P5")

    try:
        stream, restore_counts = profile(
            lambda: ContinuousEvidenceInput.resume(
                store,
                producer=OracleProducer(),
                context_builder=unused_builder,
                joint_producer=joint,
                observation_decoder=RGBDSupportDecoder(),
            )
        )
        expected = StateCodec().loads((folder / "expected.json").read_text())
        db_before = store._db.execute("SELECT * FROM checkpoint").fetchall()
        value, first = profile(lambda: require_current_owned_descriptor(stream, expected))
        again, warm = profile(lambda: require_current_owned_descriptor(stream, expected))
        assert value == again == expected
        assert store._db.execute("SELECT * FROM checkpoint").fetchall() == db_before
        (folder / "fresh-result.json").write_text(
            json.dumps(
                dict(
                    descriptor=value.content_sha256, resume=restore_counts, first=first, warm=warm
                ),
                indent=2,
            )
        )
    finally:
        store.close()


def test_zero_display_mass_and_real_fresh_sqlite_descriptor(tmp_path, checkpoints):
    case = make_case(tmp_path / "state.db", checkpoints, underflow=True)
    command, _, _ = collect(case)
    before = state(case)
    descriptor = describe_current_owned_rgbd(case["stream"], command.action_id)
    workspace = case["stream"]._system.core._particle_workspace
    zeros = {
        row.particle_id
        for row in workspace.batch.particle_weights
        if row.posterior_probability == 0.0
    }
    assert zeros
    logs = dict(descriptor.parent_log_weights)
    assert zeros <= logs.keys() and all(isfinite(logs[k]) and logs[k] < -745 for k in zeros)
    assert state(case) == before
    (tmp_path / "restore.json").write_text(
        json.dumps(
            dict(
                config=case["config"],
                models=case["models"],
                checkpoint=str(case["checkpoint"]),
                pin=case["pin"],
            )
        )
    )
    (tmp_path / "expected.json").write_text(StateCodec().dumps(descriptor))
    case["store"].close()
    original = sha256((tmp_path / "state.db").read_bytes()).hexdigest()
    shutil.copy2(tmp_path / "state.db", tmp_path / "copy.db")
    env = os.environ.copy()
    root = Path(__file__).resolve().parents[1]
    env["PYTHONPATH"] = os.pathsep.join(str(root / p) for p in ("src", "tests", "tools"))
    with (tmp_path / "fresh.log").open("w") as log:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from test_owned_position_delivery import fresh_restore; "
                "import sys; fresh_restore(sys.argv[1])",
                str(tmp_path),
            ],
            cwd=root,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            timeout=180,
            check=False,
        )
    assert result.returncode == 0, (tmp_path / "fresh.log").read_text()
    assert (
        json.loads((tmp_path / "fresh-result.json").read_text())["descriptor"]
        == descriptor.content_sha256
    )
    assert sha256((tmp_path / "state.db").read_bytes()).hexdigest() == original
