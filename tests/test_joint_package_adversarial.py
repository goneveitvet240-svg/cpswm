"""PR36 first-round executable attacks; complete forged positive paths included."""

import hashlib
import io
import json
import sys
import tarfile
import zipfile
from pathlib import Path

import cv2
import numpy as np
import pytest
import torch
from test_typed_proposal_training import data

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import build_joint_supervision_package as hocap_tool
import inspect_public_joint_evidence as public_tool

from cpswm.data_preflight.proposal_samples import export_context
from cpswm.data_preflight.proposal_trainer import load_checkpoint, save_checkpoint
from cpswm.data_preflight.typed_proposal_networks import ARMS, TypedProposalNetwork


def tar(files):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, payload in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


def complete_public_forgery(root):
    root.mkdir()
    files = {}
    poses = {"forged_object": {"subject/sequence/camera/000001": np.eye(4).tolist()}}
    ope = []
    for name in ["ope_gt", "ope_demo"]:
        payload = json.dumps(poses).encode()
        files[name + ".json"] = payload
        ope.append(
            {"name": name, "status": "downloaded", "sha256": hashlib.sha256(payload).hexdigest()}
        )
    files["ope-receipts.json"] = json.dumps(ope).encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        for role in ["giver", "taker", "interaction"]:
            z.writestr(f"Wrench_{role}_saved.csv", "Fx,Fy,Fz,Tx,Ty,Tz\n" + "0,0,-4,0,0,0\n" * 3)
        names = ["baton"] + [
            f"{r}_{j}"
            for r in ["giver", "taker"]
            for j in [
                "hip",
                "ab",
                "chest",
                "neck",
                "head",
                "LShoulder",
                "LUArm",
                "LFArm",
                "LHand",
                "RShoulder",
                "RUArm",
                "RFArm",
                "RHand",
            ]
        ]
        for name in names:
            z.writestr(f"{name}_pose_saved.csv", "x,y,z,q0,q1,q2,q3\n" + "0,0,0,1,0,0,0\n" * 3)
    payload = buffer.getvalue()
    files["rpl/one_saved_handover_New.zip"] = payload
    files["rpl/receipts.json"] = json.dumps(
        [
            {
                "path": "one_saved_handover_New.zip",
                "sha256": hashlib.sha256(payload).hexdigest(),
                "git_blob": hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest(),
            }
        ]
    ).encode()
    video = root / "temp.mp4"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 30, (32, 24))
    for _ in range(3):
        writer.write(np.zeros((24, 32, 3), dtype=np.uint8))
    writer.release()
    video_bytes = video.read_bytes()
    members, labels = {}, {}
    for trial in ["trial0000", "trial0002"]:
        prefix = f"sample_training_set/{trial}/"
        info = {"robot": "Toyota HSR", "task": "robot to human handover"}
        members[prefix + "task_info.json"] = json.dumps(info).encode()
        members[prefix + "head_cam.mp4"] = video_bytes
        arrays = {
            "head_cam_ts": np.arange(3) / 30,
            "wrench_ts": np.arange(10) / 120,
            "human_activity": np.array([0, 1, 2]),
            "robot_actions": np.array([0, 1, 2]),
            "wrench": np.ones((10, 6)),
            "wrench_resampled": np.ones((3, 6)),
        }
        for name, array in arrays.items():
            buf = io.BytesIO()
            np.save(buf, array, allow_pickle=False)
            members[prefix + name + ".npy"] = buf.getvalue()
        labels[f"training_labels/{trial}.json"] = json.dumps({**info, "outcome": 0}).encode()
    files["sample_training_set.verified.tar.gz"] = tar(members)
    files["training_labels.tar.gz"] = tar(labels)
    files["datasheet.pdf"] = b"made up author datasheet"
    files["class_names.json"] = b"{}"
    files["handover-record.json"] = json.dumps(
        {
            "files": [
                {
                    "key": n.replace(".verified", ""),
                    "checksum": "md5:" + hashlib.md5(files[n]).hexdigest(),
                }
                for n in [
                    "sample_training_set.verified.tar.gz",
                    "training_labels.tar.gz",
                    "datasheet.pdf",
                    "class_names.json",
                ]
            ]
        }
    ).encode()
    for name, payload in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)


def test_fully_forged_but_self_consistent_public_package_cannot_claim_author_provenance(tmp_path):
    source, output = tmp_path / "source", tmp_path / "output"
    complete_public_forgery(source)
    with pytest.raises(ValueError, match=r"enrolled|registry|author|source"):
        public_tool.run(source, output)
    assert not (output / "summary.json").exists()


def test_hocap_package_rechecks_earlier_subset_before_publication(tmp_path, monkeypatch):
    roots = [tmp_path / str(i) for i in range(2)]
    digest = hashlib.sha256(b"original").hexdigest()
    for root in roots:
        root.mkdir()
        (root / "source.dat").write_bytes(b"original")
    spec = tmp_path / "spec.json"
    spec.write_text(
        json.dumps(
            {
                "hocap_subsets": [
                    {
                        "root": str(r),
                        "raw_sha256": digest,
                        "annotation_sha256": digest,
                        "receipts_sha256": digest,
                    }
                    for r in roots
                ]
            }
        )
    )

    def assemble(root, **kwargs):
        i = roots.index(root)
        if i == 1:
            (roots[0] / "source.dat").write_bytes(b"substituted after first subset")
        return {
            "model_inputs": [
                {"sequence_id": f"subject_5/seq{i}", "camera_id": "camera", "frame_index": 0}
            ],
            "evaluator_only": [{"objects": [{"visible_mask_pixels": 1, "cross_file_max_abs": 0}]}],
            "source_files": {"source.dat": digest},
            "source_unchanged": True,
            "blockers": [],
        }

    monkeypatch.setattr(hocap_tool, "assemble_subset", assemble)
    with pytest.raises(ValueError, match=r"source|changed"):
        hocap_tool.run(spec, tmp_path / "output")


def test_prepared_scorer_rejects_tensor_write_that_preserves_version_counter():
    sample, support = data()
    old_threads = torch.get_num_threads()
    torch.set_num_threads(2)
    try:
        model = TypedProposalNetwork(ARMS[0]).eval()
        scorer = model.prepare(sample.runtime_context(), support)
        before = tuple(p._version for p in model.parameters())
        model.byte_embedding.weight.data.add_(0.7)
        assert tuple(p._version for p in model.parameters()) == before
        with pytest.raises(ValueError, match=r"model|parameter|optimizer"):
            scorer(
                export_context(sample.runtime_context()),
                "operation",
                (),
                tuple(sorted({t.operation.value for t in support})),
                runtime_candidates=support,
            )
    finally:
        torch.set_num_threads(old_threads)


@pytest.mark.parametrize("kind", ["nonfinite", "wrong_dtype"])
def test_checkpoint_rejects_fully_rehashed_invalid_weight_payload(tmp_path, kind):
    model = TypedProposalNetwork(ARMS[0]).eval()
    directory = tmp_path / "model"
    save_checkpoint(model, {"track": "COMPONENT_FIXTURE_ONLY"}, directory)
    weights = torch.load(directory / "weights.pt", weights_only=True)
    key = next(iter(weights))
    if kind == "nonfinite":
        weights[key].fill_(float("nan"))
    else:
        weights[key] = weights[key].to(torch.float64)
    torch.save(weights, directory / "weights.pt")
    manifest = json.loads((directory / "manifest.json").read_text())
    manifest["weights_sha256"] = hashlib.sha256((directory / "weights.pt").read_bytes()).hexdigest()
    blob = json.dumps(manifest).encode()
    (directory / "manifest.json").write_bytes(blob)
    with pytest.raises(ValueError, match=r"finite|dtype|tensor|parameter"):
        load_checkpoint(directory, manifest_sha256=hashlib.sha256(blob).hexdigest())


@pytest.mark.parametrize("during", ["prepare", "score"])
def test_parameter_swap_inside_forward_hook_cannot_publish_mixed_model_output(during):
    sample, support = data()
    old_threads = torch.get_num_threads()
    torch.set_num_threads(2)
    handle = None
    try:
        model = TypedProposalNetwork(ARMS[1]).eval()
        scorer = None if during == "prepare" else model.prepare(sample.runtime_context(), support)
        module = model.leaf_encoder if during == "prepare" else model.head

        def mutate(module, args, result):
            model.byte_embedding.weight.data.mul_(1.1)

        handle = module.register_forward_hook(mutate)
        with pytest.raises(ValueError, match="parameters changed"):
            if scorer is None:
                model.prepare(sample.runtime_context(), support)
            else:
                scorer(
                    export_context(sample.runtime_context()),
                    "operation",
                    (),
                    tuple(sorted({t.operation.value for t in support})),
                    runtime_candidates=support,
                )
    finally:
        if handle:
            handle.remove()
        torch.set_num_threads(old_threads)


def test_conditional_replay_detaches_model_mutation_and_still_preserves_original_history():
    from uuid import UUID

    from test_conditional_revision_replay import Recomputed, history

    journal = history()
    original = journal.content_sha256

    class MutatingInput(Recomputed):
        def recompute(self, step, state):
            # Even a model that mutates its passed-in view cannot change the
            # source history or its prior. Its returned valid measurement is
            # still only a declared model observation, not empirical truth.
            object.__setattr__(state, "alpha", (100.0, 100.0))
            object.__setattr__(step, "input_sha256", "f" * 64)
            return step.measurement

    result = journal.replay(
        particle_id=UUID(int=102),
        revoked_revision_ids=frozenset({UUID(int=201)}),
        expected_history_sha256=original,
        model=MutatingInput(),
    )
    assert journal.content_sha256 == original and result.state.alpha == (3.0, 1.0)
    assert not result.native_publication_authority and not result.ledger_write_authority
