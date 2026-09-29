"""Content relocation cannot change the model or erase native evidence."""

import json
import os
import shutil
import subprocess
import sys
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
from test_native_joint_production import JointFixture
from test_native_neural_production import checkpoints as _checkpoints
from test_native_neural_production import cpu_threads as _threads
from test_owned_rgbd_support import RGBDSupportDecoder
from test_owned_visual_neural import setup_visual

from cpswm.data_preflight.typed_proposal_networks import ARMS
from cpswm.system import checkpoint_artifacts as artifacts
from cpswm.system.continuous_state_codec import StateCodec
from cpswm.system.native_neural_production import NeuralNativeProducer, verify_neural_evidence
from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput
from cpswm.system.structure_two_particle_workspace import native_content_sha256

checkpoints = _checkpoints
cpu_threads = _threads


def copied_checkpoint(checkpoints, directory):
    original, pin = checkpoints[ARMS[0]]
    shutil.copytree(original, directory)
    return directory, pin


def make_joint(directory, pin):
    return NeuralNativeProducer(
        JointFixture(), directory, manifest_sha256=pin, use_owned_visual_context=True
    )


def test_moved_checkpoint_restores_exact_proof_view_actions_and_ledger(tmp_path, checkpoints):
    a, pin = copied_checkpoint(checkpoints, tmp_path / "original")
    joint = make_joint(a, pin)
    stream, store, builder, _ = setup_visual(tmp_path / "state.sqlite", joint)
    try:
        stream.produce_joint_posterior()
        view = stream.current_joint_decision_view()
        state = joint.checkpoint_state()
        ledger = stream._system.core._hybrid_loop.ledger.export_state()
        before = native_content_sha256(stream._system.core._particle_workspace.state_payload())
        proof = state["last_evidence"]
        assert proof.format == "native-neural-enumeration-development@2"
        assert proof.checkpoint_artifact_id == "sha256:" + pin
        assert str(a) not in StateCodec().dumps(proof)
        b = tmp_path / "relocated"
        a.rename(b)
        assert not a.exists()
        resumed = ContinuousEvidenceInput.resume(
            store,
            producer=stream._producer,
            context_builder=builder,
            joint_producer=make_joint(b, pin),
            observation_decoder=RGBDSupportDecoder(),
        )
        assert resumed.current_joint_decision_view() == view
        assert resumed._joint_producer.checkpoint_state() == state
        assert resumed.observation_history() == stream.observation_history()
        assert resumed._system.core._hybrid_loop.ledger.export_state() == ledger
        assert (
            native_content_sha256(resumed._system.core._particle_workspace.state_payload())
            == before
        )
    finally:
        store.close()


@pytest.mark.parametrize(
    "attack",
    ["unconfigured", "path", "different_reference", "manifest", "weights", "legacy_format"],
)
def test_cached_complete_proof_cannot_bypass_artifact_configuration_or_content(
    tmp_path, checkpoints, monkeypatch, attack
):
    a, pin = copied_checkpoint(checkpoints, tmp_path / "model")
    joint = make_joint(a, pin)
    stream, store, _, _ = setup_visual(tmp_path / "db", joint)
    try:
        stream.produce_joint_posterior()
        proof = joint._last_evidence
        verify_neural_evidence(proof)  # Warm the successful numerical verifier cache.
        original = {p.name: p.read_bytes() for p in a.iterdir() if p.is_file()}
        try:
            if attack == "unconfigured":
                monkeypatch.setattr(artifacts, "_ARTIFACT_DIRECTORIES", {})
            elif attack == "path":
                proof = replace(proof, checkpoint_artifact_id=str(a))
            elif attack == "different_reference":
                proof = replace(proof, checkpoint_artifact_id="sha256:" + "a" * 64)
            elif attack == "manifest":
                (a / "manifest.json").write_bytes(original["manifest.json"] + b" ")
            elif attack == "weights":
                (a / "weights.pt").write_bytes(original["weights.pt"] + b"corrupted")
            else:
                proof = replace(proof, format="native-neural-enumeration-development@1")
            with pytest.raises(ValueError):
                verify_neural_evidence(proof)
        finally:
            for name, data in original.items():
                (a / name).write_bytes(data)
    finally:
        store.close()


def test_bad_relocation_registration_cannot_replace_a_good_mapping(tmp_path, checkpoints):
    a, pin = copied_checkpoint(checkpoints, tmp_path / "good")
    joint = make_joint(a, pin)
    stream, store, _, _ = setup_visual(tmp_path / "db", joint)
    try:
        stream.produce_joint_posterior()
        proof = joint._last_evidence
        b = tmp_path / "corrupted"
        shutil.copytree(a, b)
        (b / "weights.pt").write_bytes(b"not the configured model")
        with pytest.raises(ValueError, match="weights"):
            artifacts.register_checkpoint_artifact(b, manifest_sha256=pin)
        assert (
            artifacts.resolve_checkpoint_artifact(proof.checkpoint_artifact_id, manifest_sha256=pin)
            == a.resolve()
        )
        verify_neural_evidence(proof)
    finally:
        store.close()


def test_new_process_relocates_source_and_model_without_reading_original_checkout(
    tmp_path, checkpoints
):
    root = Path(__file__).resolve().parents[1]
    a, pin = copied_checkpoint(checkpoints, tmp_path / "model-original")
    joint = make_joint(a, pin)
    stream, store, _, _ = setup_visual(tmp_path / "state.sqlite", joint)
    stream.produce_joint_posterior()
    expected = tmp_path / "expected.json"
    expected.write_text(
        StateCodec().dumps(
            (
                stream.current_joint_decision_view(),
                stream.observation_history(),
                stream._system.core._hybrid_loop.ledger.export_state(),
                joint.checkpoint_state(),
            )
        )
    )
    config = {
        "pin": pin,
        "source": store.source_identity,
        "dependencies": store.dependency_identity,
    }
    (tmp_path / "config.json").write_text(json.dumps(config))
    store.close()
    b = tmp_path / "model-relocated"
    a.rename(b)
    relocated = tmp_path / "checkout"
    for directory in ("src", "tests", "tools"):
        shutil.copytree(
            root / directory,
            relocated / directory,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    code = """
import sys,os,json
from pathlib import Path
old=Path(sys.argv[1]).resolve();base=Path(sys.argv[2]);reads=[]
# An editable installation leaves the old src path in the shared interpreter.
# Configure this child for the relocated source before dependency/plugin scans;
# keep the audit prohibition on every original-checkout read below.
sys.path=[p for p in sys.path if not Path(p or os.curdir).resolve().is_relative_to(old)]
def audit(event,args):
    if event=='open' and isinstance(args[0],(str,bytes)):
        p=Path(os.fsdecode(args[0])).resolve()
        if p.is_relative_to(old):
            reads.append(str(p));raise AssertionError('original checkout read: '+str(p))
sys.addaudithook(audit)
import torch
torch.set_num_threads(2)
from test_continuous_state_recovery import DurableFixtureProducer
from test_native_joint_production import JointFixture
from test_owned_rgbd_support import RGBDSupportDecoder
from cpswm.system.continuous_state_codec import StateCodec
from cpswm.system.continuous_state_store import ContinuousStateStore
from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput
from cpswm.system.structure_two_joint_consumption import JointDecisionView
from cpswm.system.native_neural_production import NeuralNativeProducer
config=json.loads((base/'config.json').read_text())
joint=NeuralNativeProducer(JointFixture(),base/'model-relocated',manifest_sha256=config['pin'],use_owned_visual_context=True)
store=ContinuousStateStore(base/'state.sqlite',source_identity=config['source'],dependency_identity=config['dependencies'])
def no_reexecution(*args,**kwargs):raise AssertionError('restore replayed semantic input')
try:
    stream=ContinuousEvidenceInput.resume(store,producer=DurableFixtureProducer(),context_builder=no_reexecution,joint_producer=joint,observation_decoder=RGBDSupportDecoder())
    actual=(stream.current_joint_decision_view(),stream.observation_history(),stream._system.core._hybrid_loop.ledger.export_state(),joint.checkpoint_state())
    assert actual==StateCodec().loads((base/'expected.json').read_text())
    assert not reads
finally:store.close()
print('EXACT_RESTORATION_NO_ORIGINAL_CHECKOUT_READS')
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(root), str(tmp_path)],
        cwd=relocated,
        env=dict(
            os.environ,
            PYTHONPATH=os.pathsep.join(str(relocated / d) for d in ("src", "tests", "tools")),
        ),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "EXACT_RESTORATION_NO_ORIGINAL_CHECKOUT_READS" in result.stdout


def test_complete_probability_forgery_still_fails_after_relocation(tmp_path, checkpoints):
    import torch

    from cpswm.data_preflight.proposal_decoder import TypedProposalDistribution

    a, pin = copied_checkpoint(checkpoints, tmp_path / "old")
    joint = make_joint(a, pin)
    stream, store, _, _ = setup_visual(tmp_path / "db", joint)
    try:
        stream.produce_joint_posterior()
        proof = deepcopy(joint._last_evidence)
        b = tmp_path / "new"
        a.rename(b)
        make_joint(b, pin)
        d = TypedProposalDistribution(
            context=proof.context,
            runtime_candidates=proof.support,
            scorer=lambda context, axis, prefix, choices, **kwargs: torch.zeros(len(choices)),
        )
        forged = replace(proof, scored=tuple(d.decode(k) for k in d.target_sha256s))
        with pytest.raises(ValueError, match="checkpoint recomputation"):
            verify_neural_evidence(forged)
        verify_neural_evidence(proof)
    finally:
        store.close()


def test_loaded_locator_bypass_cannot_publish_a_valid_score_with_false_reference(
    tmp_path, checkpoints, monkeypatch
):
    from test_native_neural_production import stage
    from test_owned_visual_neural import produced_visual

    import cpswm.system.native_neural_production as native

    a, pin = copied_checkpoint(checkpoints, tmp_path / "model")
    joint = make_joint(a, pin)
    stream, store, _, when = setup_visual(tmp_path / "db", joint)
    try:
        _, good = produced_visual(stream, joint, when)
        forged = replace(
            good,
            neural_evidence=replace(
                good.neural_evidence, checkpoint_artifact_id="/untrusted/model"
            ),
        )
        before = native_content_sha256(stream._system.core._particle_workspace.state_payload())
        with monkeypatch.context() as patch:
            patch.setattr(native, "resolve_checkpoint_artifact", lambda *args, **kwargs: a)
            with pytest.raises(ValueError, match=r"implementation|imported"):
                stage(stream, forged)
        assert (
            native_content_sha256(stream._system.core._particle_workspace.state_payload()) == before
        )
        stage(stream, good)
    finally:
        store.close()


def test_relocation_replay_keeps_exact_native_history_not_only_marginals(tmp_path, checkpoints):
    import sqlite3

    from run_correction_replay_comparison import OracleProducer
    from test_native_joint_full_replay import corrected
    from test_native_neural_recovery import OpenWorldJointFixture

    from cpswm.system.continuous_state_store import ContinuousStateStore

    a, pin = copied_checkpoint(checkpoints, tmp_path / "model-original")
    joint = NeuralNativeProducer(OpenWorldJointFixture(), a, manifest_sha256=pin)
    _, _, original, store, builder, _, _ = corrected(tmp_path / "original.sqlite", joint)
    replica = tmp_path / "relocated.sqlite"
    try:
        ids = (store.source_identity, store.dependency_identity)
        with sqlite3.connect(replica) as target:
            store._db.backup(target)
        original.replay_joint_posterior()
        view = original.current_joint_decision_view()
        workspace = native_content_sha256(original._system.core._particle_workspace.state_payload())
        expected = joint.checkpoint_state()
        ledger = original._system.core._hybrid_loop.ledger.export_state()
    finally:
        store.close()
    b = tmp_path / "model-relocated"
    a.rename(b)
    store = ContinuousStateStore(replica, source_identity=ids[0], dependency_identity=ids[1])
    try:
        relocated_joint = NeuralNativeProducer(OpenWorldJointFixture(), b, manifest_sha256=pin)
        resumed = ContinuousEvidenceInput.resume(
            store,
            producer=OracleProducer(),
            context_builder=builder,
            joint_producer=relocated_joint,
        )
        resumed.replay_joint_posterior()
        assert resumed.current_joint_decision_view() == view
        assert (
            native_content_sha256(resumed._system.core._particle_workspace.state_payload())
            == workspace
        )
        assert relocated_joint.checkpoint_state() == expected and relocated_joint.calls == 11
        assert resumed._system.core._hybrid_loop.ledger.export_state() == ledger
    finally:
        store.close()
