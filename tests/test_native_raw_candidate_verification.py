"""Complete raw target forgeries retain real q, original bindings and valid shape.

Controlled pixels/identity and fitted synthetic residuals only; no archive fit.
"""

from copy import deepcopy
from dataclasses import replace
from datetime import timedelta

import pytest
from test_native_neural_production import checkpoints as _checkpoints
from test_native_neural_production import context_for, stage
from test_native_neural_production import cpu_threads as _cpu_threads
from test_native_position_production import advance, scenario, snapshot, weight_state

from cpswm.system.native_neural_production import materialize, verify_neural_evidence
from cpswm.system.structure_two_particle_workspace import native_content_sha256

checkpoints = _checkpoints
cpu_threads = _cpu_threads


@pytest.mark.parametrize("field", ["known_ll", "unknown_ll", "aggregate", "transition"])
def test_complete_target_forgery_rejected_without_side_effect_then_legal(
    tmp_path, checkpoints, field
):
    case = scenario(tmp_path / "state.db", checkpoints)
    try:
        when = advance(case, 0, publish=False)
        joint, stream = case["joint"], case["stream"]
        initial = joint.checkpoint_state()
        produced = joint.produce(context_for(stream, when))
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
                update={key: getattr(rows[index], key) + (-2.0 if field == "transition" else 2.0)}
            )
            base = replace(base, receipts=tuple(rows))
        proof = replace(produced.neural_evidence, base_candidates=base)
        # This proves rejection is not a stale/missing q or an incomplete package.
        verify_neural_evidence(proof)
        forged = replace(
            produced,
            receipts=materialize(base, proof),
            statistics=base.statistics,
            unresolved_log_weight=base.unresolved_log_weight,
            neural_evidence=proof,
        )
        before = snapshot(case)
        producer_before = native_content_sha256(joint.checkpoint_state())
        core = stream._system.core
        ledger = core._hybrid_loop.ledger.export_state()
        with pytest.raises(ValueError, match="complete owner recomputation"):
            stage(stream, forged)
        assert snapshot(case) == before
        assert core._hybrid_loop.ledger.export_state() == ledger
        assert native_content_sha256(joint.checkpoint_state()) == producer_before
        joint.restore_state(initial)
        stream.produce_joint_posterior()
        assert core._particle_workspace.batch is not None
        assert len(case["candidate"].consumed_keys) == 1
    finally:
        case["store"].close()


def test_genuine_network_with_future_cutoff_lacks_owner_admission(tmp_path, checkpoints):
    case = scenario(tmp_path / "state.db", checkpoints)
    try:
        when = advance(case, 0, publish=False)
        joint, stream = case["joint"], case["stream"]
        initial = joint.checkpoint_state()
        future = joint.produce(context_for(stream, when + timedelta(days=1)))
        verify_neural_evidence(future.neural_evidence)
        before = snapshot(case)
        with pytest.raises(ValueError, match="not admitted by the owner"):
            stage(stream, future)
        assert snapshot(case) == before
        joint.restore_state(initial)
        stream.produce_joint_posterior()
    finally:
        case["store"].close()


@pytest.mark.parametrize(
    "attack", ["profile_none", "profile_replace", "catalogue", "missing_proof"]
)
def test_protected_profile_cannot_downgrade_current_or_historical(tmp_path, checkpoints, attack):
    case = scenario(tmp_path / "state.db", checkpoints)
    try:
        when = advance(case, 0, publish=False)
        joint, stream = case["joint"], case["stream"]
        initial = joint.checkpoint_state()
        produced = joint.produce(context_for(stream, when))
        workspace = stream._system.core._particle_workspace
        saved = deepcopy(vars(workspace))
        if attack == "profile_none":
            workspace.raw_candidate_profile = None
        elif attack == "profile_replace":
            workspace.raw_candidate_profile["arguments"]["configuration"]["enabled"] = False
        elif attack == "catalogue":
            workspace.raw_contexts.clear()
        else:
            produced = replace(produced, neural_evidence=None)
        with pytest.raises(ValueError):
            stage(stream, produced)
        vars(workspace).clear()
        vars(workspace).update(saved)
        joint.restore_state(initial)
        stream.produce_joint_posterior()
        expected = weight_state(case)
        saved = deepcopy(vars(workspace))
        if attack == "profile_none":
            workspace.raw_candidate_profile = None
        elif attack == "profile_replace":
            workspace.raw_candidate_profile["arguments"]["configuration"]["enabled"] = False
        elif attack == "catalogue":
            workspace.raw_contexts.clear()
        else:
            cluster = next(iter(workspace.input_bodies))
            workspace.input_bodies[cluster] = replace(
                workspace.input_bodies[cluster], neural_evidence=None
            )
        with pytest.raises(ValueError):
            workspace.state_payload()
        with pytest.raises(ValueError):
            stream._system.core.prepared_particle_location_marginal()
        vars(workspace).clear()
        vars(workspace).update(saved)
        assert weight_state(case) == expected
        stream._system.core.prepared_particle_location_marginal()
    finally:
        case["store"].close()


def test_real_parent_history_neutral_steps_and_dictionary_order(tmp_path, checkpoints):
    case = scenario(tmp_path / "state.db", checkpoints, selected_index=1)
    try:
        advance(case, 0)
        advance(case, 1)
        learned = weight_state(case)
        when = advance(case, 2, publish=False)
        joint, stream = case["joint"], case["stream"]
        initial = joint.checkpoint_state()
        produced = joint.produce(context_for(stream, when))
        base = produced.neural_evidence.base_candidates
        assert all(r.observation_log_likelihood == 0.0 for r in base.receipts)
        changed = base.receipts[0].model_copy(update={"observation_log_likelihood": 2.0})
        forged_base = replace(base, receipts=(changed, *base.receipts[1:]))
        proof = replace(produced.neural_evidence, base_candidates=forged_base)
        verify_neural_evidence(proof)
        forged = replace(produced, neural_evidence=proof, receipts=materialize(forged_base, proof))
        before = snapshot(case)
        with pytest.raises(ValueError, match="complete owner recomputation"):
            stage(stream, forged)
        assert snapshot(case) == before
        joint.restore_state(initial)
        stream.produce_joint_posterior()
        neutral = weight_state(case)
        for key in (False, True):
            assert neutral[key][0] == pytest.approx(learned[key][0], abs=1e-14)
            assert neutral[key][1:] == learned[key][1:]
        assert neutral["aggregate"] == pytest.approx(learned["aggregate"], abs=1e-14)
        workspace = stream._system.core._particle_workspace
        workspace.records = dict(reversed(tuple(workspace.records.items())))
        stream._system.core.prepared_particle_location_marginal()
        assert weight_state(case) == neutral
    finally:
        case["store"].close()


def test_loaded_raw_verifier_replacement_fails_before_cache_or_target_acceptance(
    tmp_path, checkpoints, monkeypatch
):
    from cpswm.system import native_raw_verification

    case = scenario(tmp_path / "state.db", checkpoints)
    try:
        when = advance(case, 0, publish=False)
        joint, stream = case["joint"], case["stream"]
        initial = joint.checkpoint_state()
        produced = joint.produce(context_for(stream, when))
        before = snapshot(case)
        with monkeypatch.context() as patch:
            patch.setattr(native_raw_verification, "verify_raw_base", lambda *args: None)
            with pytest.raises(ValueError, match="loaded implementation changed"):
                stage(stream, produced)
        assert snapshot(case) == before
        joint.restore_state(initial)
        stream.produce_joint_posterior()
    finally:
        case["store"].close()


def test_registration_failure_retains_durable_pending_and_recovers(
    tmp_path, checkpoints, monkeypatch
):
    from run_correction_replay_comparison import OracleProducer
    from test_native_position_production import fresh_joint

    from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput

    case = scenario(tmp_path / "state.db", checkpoints)
    try:
        stream = case["stream"]
        contexts = []
        original_builder = case["builder"]

        def capture_context(*args):
            context = original_builder(*args)
            contexts.append(deepcopy(context))
            return context

        stream._context_builder = capture_context

        def fail(self, **kwargs):
            raise RuntimeError("injected raw admission failure")

        with monkeypatch.context() as patch:
            patch.setattr(ContinuousEvidenceInput, "_admit_current_raw_context", fail)
            with pytest.raises(RuntimeError, match="injected raw admission failure"):
                advance(case, 0, publish=False)
        assert stream._pending_step is not None and stream._durability_failed
        assert not stream._advanced
        assert not stream._system.core._particle_workspace.raw_contexts
        with pytest.raises(RuntimeError, match=r"pending P5|durable state failed"):
            stream.produce_joint_posterior()
        # Resume the persisted pending P5 epoch, without claiming physical rollback.
        joint = fresh_joint(case)
        resumed = ContinuousEvidenceInput.resume(
            case["store"],
            producer=OracleProducer(),
            context_builder=lambda *args: deepcopy(contexts[0]),
            joint_producer=joint,
        )
        cutoff = resumed._pending_step["cutoff"]
        effects = case["store"]._db.execute("SELECT count(*) FROM effects").fetchone()[0]
        resumed.advance(cutoff=cutoff)
        resumed.produce_joint_posterior()
        assert resumed._pending_step is None
        assert len(joint._candidate_model.consumed_keys) == 1
        assert case["store"]._db.execute("SELECT count(*) FROM effects").fetchone()[0] == effects
        assert resumed.current_joint_decision_view().atoms
    finally:
        case["store"].close()


def test_fresh_process_resume_without_constructing_another_stream(tmp_path, checkpoints):
    import json
    import subprocess
    import sys
    from pathlib import Path

    case = scenario(tmp_path / "resume.db", checkpoints)
    try:
        advance(case, 0)
        advance(case, 1)
        stream = case["stream"]
        config = dict(
            db=str(tmp_path / "resume.db"),
            configuration=case["config"],
            models=case["models"],
            checkpoint=str(case["checkpoint"]),
            pin=case["pin"],
            expected_view=native_content_sha256(stream.current_joint_decision_view()),
            expected_state=native_content_sha256(case["joint"].checkpoint_state()),
            expected_workspace=snapshot(case),
            expected_ledger=native_content_sha256(
                stream._system.core._hybrid_loop.ledger.export_state()
            ),
        )
        target = tmp_path / "original-config.json"
        target.write_text(json.dumps(config))
        case["store"].close()
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), str(target)],
            text=True,
            capture_output=True,
            timeout=90,
        )
        (tmp_path / "fresh-process.log").write_text(result.stdout + result.stderr)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "pure-resume-and-next-neutral: PASS" in result.stdout
    finally:
        case["store"].close()


def _fresh_resume_worker(config_path):
    import json
    import sys
    from pathlib import Path

    import torch
    from controlled_position_producer import ControlledPositionProducer
    from run_correction_replay_comparison import OracleProducer
    from structure_two_backbone_wiring_probe import BackboneWiringProbe, CIAVOutcomeKind

    from cpswm.system.continuous_state_codec import runtime_types
    from cpswm.system.continuous_state_store import ContinuousStateStore
    from cpswm.system.native_neural_production import NeuralNativeProducer
    from cpswm.system.reproducibility import content_sha256
    from cpswm.system.structure_two_adaptive_runtime import AdaptiveExecutionContext
    from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput

    # No call to scenario/build or ContinuousEvidenceInput.__init__ in this process.
    assert "cpswm.system.native_raw_verification.RawCandidateAuthority" in runtime_types()
    cfg = json.loads(Path(config_path).read_text())
    torch.set_num_threads(2)
    candidate = ControlledPositionProducer(configuration=cfg["configuration"], **cfg["models"])
    joint = NeuralNativeProducer(candidate, Path(cfg["checkpoint"]), manifest_sha256=cfg["pin"])
    probe = BackboneWiringProbe.build(seed=171)

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

    store = ContinuousStateStore(
        Path(cfg["db"]),
        source_identity=content_sha256("controlled-position-test"),
        dependency_identity=content_sha256(sys.version),
    )
    try:
        resumed = ContinuousEvidenceInput.resume(
            store, producer=OracleProducer(), context_builder=builder, joint_producer=joint
        )
        case = dict(
            stream=resumed,
            store=store,
            probe=probe,
            backend=resumed._producer,
            joint=joint,
            candidate=candidate,
            selected_index=0,
        )
        assert native_content_sha256(resumed.current_joint_decision_view()) == cfg["expected_view"]
        assert native_content_sha256(joint.checkpoint_state()) == cfg["expected_state"]
        assert snapshot(case) == cfg["expected_workspace"]
        assert (
            native_content_sha256(resumed._system.core._hybrid_loop.ledger.export_state())
            == cfg["expected_ledger"]
        )
        before = joint.checkpoint_state()
        resumed.produce_joint_posterior()
        assert joint.checkpoint_state() == before
        previous = weight_state(case)
        advance(case, 2)
        now = weight_state(case)
        for key in (False, True):
            assert abs(now[key][0] - previous[key][0]) < 1e-14
            assert now[key][1:] == previous[key][1:]
        assert len(candidate.consumed_keys) == 1
        print("pure-resume-and-next-neutral: PASS")
    finally:
        store.close()


if __name__ == "__main__":
    import sys

    _fresh_resume_worker(sys.argv[1])


def test_non_neural_collection_keeps_torch_optional(tmp_path):
    import subprocess
    import sys

    script = r"""
import builtins, sys
from pathlib import Path
original_import = builtins.__import__
def blocked(name, *args, **kwargs):
    if name == "torch" or name.startswith("torch."):
        raise ImportError("torch deliberately unavailable")
    return original_import(name, *args, **kwargs)
builtins.__import__ = blocked
from run_correction_replay_comparison import build
from test_native_joint_production import JointFixture
from cpswm.system.reproducibility import content_sha256
for name, joint in (("none", None), ("legacy", JointFixture())):
    _, _, stream, store, _ = build(Path(sys.argv[1]) / (name + ".db"), seed=171,
        source=content_sha256("no-torch-compatibility"), joint_producer=joint)
    assert stream._system.core._particle_workspace.raw_candidate_profile is None
    store.close()
assert "torch" not in sys.modules
print("none-and-legacy-without-torch: PASS")
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)], text=True, capture_output=True, timeout=30
    )
    (tmp_path / "no-torch.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "none-and-legacy-without-torch: PASS" in result.stdout


@pytest.mark.parametrize("semantic_output", ["none", "duplicate"])
def test_first_normal_collector_owns_later_epoch_and_executes_once(
    tmp_path, checkpoints, semantic_output
):
    from test_continuous_camera_collection import Model
    from test_owned_rgbd_support import RGBDCamera

    from cpswm.system.continuous_camera_collection import collect_posterior_step

    case = scenario(tmp_path / "collector.db", checkpoints)
    try:
        stream = case["stream"]
        when = advance(case, 0, publish=False)
        if semantic_output == "duplicate":
            # Reuse the actual original delivered semantic output, not a new item.
            case["backend"].output = deepcopy(case["store"].load()["producer_state"]["output"])
        else:
            assert case["backend"].output is None
        assert stream._system.core._particle_workspace.batch is None
        assert case["joint"].calls == 0
        model, camera = Model(stream), RGBDCamera(stream._scope)
        before_ledger = stream._system.core._hybrid_loop.ledger.export_state()
        result = collect_posterior_step(
            stream, model=model, executor=camera, decision_time=when + timedelta(seconds=1)
        )
        assert result.command is not None and result.delivery.success
        assert camera.calls == model.calls == case["joint"].calls == 1
        assert len(stream.observation_history()) == len(case["candidate"].consumed_keys) == 1
        assert len(stream._advanced) == 1
        assert stream.current_joint_decision_view().atoms
        assert stream._system.core._hybrid_loop.ledger.export_state() == before_ledger
        # Another real owner advance does not reapply an already published factor.
        previous = weight_state(case)
        producer_state = case["joint"].checkpoint_state()
        stream.advance(cutoff=result.delivery.received_at + timedelta(seconds=1))
        stream.produce_joint_posterior()
        assert weight_state(case) == previous
        assert case["joint"].checkpoint_state() == producer_state
        assert camera.calls == model.calls == case["joint"].calls == 1
        assert len(stream._advanced) == 1
    finally:
        case["store"].close()


def test_insufficient_initial_semantics_keeps_empty_source_catalogue(tmp_path, checkpoints):
    case = scenario(tmp_path / "initial.db", checkpoints)
    try:
        stream = case["stream"]
        when = max(row.envelope().arrival_time for row in case["rows"])
        stream.admit(case["rows"], received_at=when)
        receipt = stream.advance(cutoff=when)
        assert receipt.status == "INSUFFICIENT_SEMANTIC_EVIDENCE"
        workspace = stream._system.core._particle_workspace
        assert not workspace.posterior_sources and not workspace.raw_contexts
        assert not stream._system.core._particle_posterior_source_anchors
        assert not stream._advanced and case["joint"].calls == 0
        assert stream._last_cutoff == when
    finally:
        case["store"].close()


def test_no_semantic_advance_cannot_hide_removed_owned_source(tmp_path, checkpoints):
    case = scenario(tmp_path / "removed-source.db", checkpoints)
    try:
        stream = case["stream"]
        when = advance(case, 0, publish=False)
        workspace = stream._system.core._particle_workspace
        original = dict(workspace.posterior_sources)
        workspace.posterior_sources.clear()
        try:
            with pytest.raises(ValueError, match="posterior producer sources differ"):
                stream.advance(cutoff=when + timedelta(seconds=1))
            assert stream._last_cutoff == when
        finally:
            workspace.posterior_sources = original
        stream.advance(cutoff=when + timedelta(seconds=1))
        stream.produce_joint_posterior()
        assert case["joint"].calls == 1
    finally:
        case["store"].close()
