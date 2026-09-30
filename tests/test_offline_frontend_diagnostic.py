"""Driver boundaries with real controlled 8/96-frame public geometry and evaluation.

Only the historical SDK verifier process is replaced in composed tests. This is
not an empirical detector result or an independent qualification of the archive.
PYTEST_DONT_REWRITE: imported fixture detector implementation stays source-bound.
"""

import json
import os
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import diagnose_offline_frontend as task
import pytest
from test_offline_factor_capture_verifier import build_capture
from test_owned_rgbd_support import RGBDSupportDecoder

from cpswm.system.reproducibility import content_sha256

SUCCESS = dict(
    complete_twelve_house_runtime_audit=True,
    complete_asset_exposure_audit=True,
    supervision_export_performed=False,
    training_performed=False,
)


def write_json(path, value):
    path.write_text(json.dumps(value, allow_nan=False) + "\n")


def source_tree(path):
    for name in ("src", "tests", "tools"):
        (path / name).mkdir(parents=True)
    (path / "tools/collect_offline_factor_data.py").write_text("# controlled historical source\n")
    (path / "src/core.py").write_text("VALUE = 1\n")
    return path


def seal(directory):
    entries = task.inventory(directory)
    entries.pop("inventory.json", None)
    write_json(directory / "inventory.json", entries)
    return task.digest(directory / "inventory.json")


@pytest.fixture
def historical(tmp_path):
    source = source_tree(tmp_path / "historical-source")
    current = source_tree(tmp_path / "analysis-source")
    (current / "tools/new_analysis.py").write_text("# intentionally absent at capture time\n")
    directory = tmp_path / "collection"
    directory.mkdir()
    config = dict(source_files=task.source_identity(source))
    write_json(directory / "configuration.json", config)
    (directory / "raw.bin").write_bytes(b"original immutable observation")
    pin = seal(directory)
    return SimpleNamespace(
        directory=directory,
        source=source,
        current=current,
        config=config,
        kwargs=dict(
            pin=pin,
            capture_source=source,
            archive=tmp_path / "source-houses.json.gz",
            sdk_python=tmp_path / "sdk-venv/bin/python",
            binary=tmp_path / "Unity",
        ),
    )


def successful_process(*args, **kwargs):
    """Explicit SDK subprocess stand-in, never a replacement of frame evaluation."""
    return subprocess.CompletedProcess(args[0], 0, json.dumps(SUCCESS), "")


def test_historical_source_matches_original_configuration_not_new_analysis(historical, monkeypatch):
    h, calls = historical, []
    monkeypatch.setattr(task, "ROOT", h.current)

    def process(command, **kwargs):
        calls.append((command, kwargs))
        return successful_process(command, **kwargs)

    monkeypatch.setattr(task.subprocess, "run", process)
    before = task.inventory(h.directory)
    assert task.verify_historical_collection(h.directory, **h.kwargs) == (before, h.config)
    command, arguments = calls[0]
    assert command[:3] == [
        sys.executable,
        str(h.source / "tools/collect_offline_factor_data.py"),
        "--verify",
    ]
    assert command[command.index("--inventory-sha256") + 1] == h.kwargs["pin"]
    assert command[command.index("--sdk-python") + 1] == str(h.kwargs["sdk_python"])
    assert arguments["cwd"] == h.source
    assert arguments["env"]["PYTHONPATH"] == os.pathsep.join(
        str(h.source / name) for name in ("src", "tools")
    )
    assert arguments["capture_output"] and arguments["text"] and arguments["timeout"] > 0
    assert task.inventory(h.directory) == before
    with pytest.raises(ValueError, match="historical capture source"):
        task.verify_historical_collection(h.directory, **dict(h.kwargs, capture_source=h.current))
    assert len(calls) == 1


@pytest.mark.parametrize("attack", ["external_pin", "original_bytes", "source_bytes"])
def test_historical_prerequisites_fail_before_process(historical, monkeypatch, attack):
    h = historical
    if attack == "external_pin":
        h.kwargs["pin"] = "0" * 64
    elif attack == "original_bytes":
        (h.directory / "raw.bin").write_bytes(b"changed raw observation")
    else:
        (h.source / "src/core.py").write_text("VALUE = 2\n")
    monkeypatch.setattr(task.subprocess, "run", lambda *a, **k: pytest.fail("process ran"))
    with pytest.raises(ValueError, match=r"pin differs|bytes differ"):
        task.verify_historical_collection(h.directory, **h.kwargs)


@pytest.mark.parametrize(
    "attack",
    ["nonzero", "incomplete", "trained", "numeric_bools", "extra_status", "mutation"],
)
def test_historical_process_failure_or_false_success_is_rejected(historical, monkeypatch, attack):
    h = historical

    def process(command, **kwargs):
        state = dict(SUCCESS)
        if attack == "incomplete":
            state["complete_asset_exposure_audit"] = False
        elif attack == "trained":
            state["training_performed"] = True
        elif attack == "numeric_bools":
            state = {key: int(value) for key, value in state.items()}
        elif attack == "extra_status":
            state["unregistered_override"] = True
        elif attack == "mutation":
            (h.directory / "raw.bin").write_bytes(b"mutated inside subprocess")
        return subprocess.CompletedProcess(
            command, 1 if attack == "nonzero" else 0, json.dumps(state), "controlled failure"
        )

    monkeypatch.setattr(task.subprocess, "run", process)
    with pytest.raises(ValueError, match=r"failed|complete eligible|changed"):
        task.verify_historical_collection(h.directory, **h.kwargs)


def test_cli_requires_external_pin_and_preserves_virtualenv_entrypoint(tmp_path, monkeypatch):
    sdk_entry = tmp_path / "sdk-env/bin/python"
    sdk_entry.parent.mkdir(parents=True)
    sdk_entry.symlink_to(Path(sys.executable).resolve())
    options = {
        "collection": tmp_path / "collection",
        "capture-source": tmp_path / "source",
        "archive": tmp_path / "archive",
        "sdk-python": sdk_entry,
        "binary": tmp_path / "Unity",
        "weights": tmp_path / "weights.pt",
        "output": tmp_path / "output",
        "detector": "ssdlite",
    }
    argv = ["diagnose_offline_frontend.py"]
    for key, value in options.items():
        argv.extend(["--" + key, str(value)])
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as error:
        task.main()
    assert error.value.code == 2

    class EntryObserved(Exception):
        pass

    def inspect(directory, **kwargs):
        assert kwargs["sdk_python"] == sdk_entry.absolute()
        assert kwargs["sdk_python"] != sdk_entry.resolve()
        raise EntryObserved

    monkeypatch.setattr(task, "verify_historical_collection", inspect)
    monkeypatch.setattr(sys, "argv", [*argv, "--inventory-sha256", "a" * 64])
    with pytest.raises(EntryObserved):
        task.main()


@pytest.fixture(scope="module")
def public_capture(tmp_path_factory):
    directory = tmp_path_factory.mktemp("public-inference") / "house"
    _, provenance = build_capture(directory)
    write_json(directory / "capture.json", dict(provenance=provenance))
    return directory


def test_public_only_prediction_preserves_all_rgbd_lineage_without_private_files(
    public_capture, tmp_path
):
    directory = tmp_path / "public-only"
    directory.mkdir()
    shutil.copytree(public_capture / "public", directory / "public")
    shutil.copyfile(public_capture / "capture.json", directory / "capture.json")
    rows, binding = task.predict_public_house(directory, RGBDSupportDecoder())
    assert binding == RGBDSupportDecoder.binding_sha256
    assert len(rows) == 8
    for command, delivery, frame in rows:
        geometry = frame.geometry
        envs = [raw.envelope() for raw in delivery.observations]
        assert geometry.observation_ids == tuple(env.identity.observation_id for env in envs)
        assert geometry.payload_sha256 == tuple(env.payload.payload_sha256 for env in envs)
        assert geometry.capture_receipt_sha256 == delivery.observations[0].capture_receipt_sha256
        assert geometry.camera.action_id == command.action_id
        assert [candidate.category for candidate in frame.candidates] == ["apple", "apple", "cup"]
        assert len(geometry.candidates) == 3
        assert all(len(candidate.samples) == 3 for candidate in geometry.candidates)
        assert all(candidate.world_instance_id is None for candidate in frame.candidates)
        assert geometry.identity_association is geometry.likelihood_model is None
        assert not geometry.memory_write_authorized
    assert {path.name for path in directory.iterdir()} == {"public", "capture.json"}


@pytest.mark.parametrize("attack", ["no_frame", "two_frames", "changed_binding", "wrong_owner"])
def test_public_prediction_rejects_incomplete_or_changed_decoder(public_capture, attack):
    class InvalidDecoder(RGBDSupportDecoder):
        def measurements(self, observations, *, cutoff):
            frames = super().measurements(observations, cutoff=cutoff)
            if attack == "no_frame":
                return ()
            if attack == "two_frames":
                return frames * 2
            if attack == "changed_binding":
                self.binding_sha256 = "f" * 64
            if attack == "wrong_owner":
                return (replace(frames[0], input_sha256="f" * 64),)
            return frames

    with pytest.raises(ValueError, match=r"exactly one|changed|differs"):
        task.predict_public_house(public_capture, InvalidDecoder())


@pytest.fixture(scope="module")
def complete_batch(tmp_path_factory):
    base = tmp_path_factory.mktemp("frontend-composed")
    source = source_tree(base / "historical-source")
    current = source_tree(base / "analysis-source")
    (current / "tools/analysis.py").write_text("# controlled analysis source identity\n")
    directory = base / "collection"
    directory.mkdir()
    instances = []
    for index in range(1, 13):
        house = directory / f"house-{index:02d}"
        _, provenance = build_capture(house)
        write_json(house / "capture.json", dict(provenance=provenance))
        event = json.loads((house / "unity-logs/evaluator_only/sdk-events/004.json").read_text())
        for obj in event["metadata"]["objects"]:
            instances.append(
                dict(
                    house_index=index,
                    split="train" if index <= 8 else "validation",
                    object_id=obj["objectId"],
                    object_type=obj["objectType"],
                    asset_id=obj["assetId"],
                    position_m=[obj["position"][key] for key in "xyz"],
                    aabb_center_m=[obj["axisAlignedBoundingBox"]["center"][key] for key in "xyz"],
                    eligible=obj["objectId"] != "floor",
                    exclusion_reasons=["controlled_non_target"]
                    if obj["objectId"] == "floor"
                    else [],
                )
            )
    write_json(directory / "runtime-partition-audit.json", dict(instances=instances))
    config = dict(source_files=task.source_identity(source))
    write_json(directory / "configuration.json", config)
    pin = seal(directory)
    return SimpleNamespace(
        directory=directory, source=source, current=current, config=config, pin=pin
    )


def decoder_factory_with_empty_first_house(events):
    house_number = 0

    def factory(scope):
        nonlocal house_number
        house_number += 1
        empty = house_number == 1

        class ObservedDecoder(RGBDSupportDecoder):
            def measurements(self, observations, *, cutoff):
                assert len(observations) == 3
                for raw in observations:
                    env = raw.envelope()
                    assert (
                        env.identity.household_id,
                        env.identity.session_id,
                        env.identity.trace_id,
                    ) == scope
                frames = super().measurements(observations, cutoff=cutoff)
                events.append("inference")
                return tuple(replace(frame, candidates=()) for frame in frames) if empty else frames

        return ObservedDecoder()

    return factory


def run_composed(batch, monkeypatch):
    events = []
    factory = decoder_factory_with_empty_first_house(events)
    read_json, evaluate = task._json, task.evaluate_frame

    def checked_read(path):
        if path.name == "runtime-partition-audit.json" or "evaluator_only" in path.parts:
            assert events.count("inference") == 96
        return read_json(path)

    def checked_evaluate(*args, **kwargs):
        assert events.count("inference") == 96
        events.append("evaluation")
        return evaluate(*args, **kwargs)

    # These wrappers call the real JSON reader, evaluation, geometry and summary.
    with monkeypatch.context() as patch:
        patch.setattr(task, "ROOT", batch.current)
        patch.setattr(task, "_json", checked_read)
        patch.setattr(task, "evaluate_frame", checked_evaluate)
        documents = task.diagnose(
            batch.directory,
            decoder_factory=factory,
            input_inventory=task.inventory(batch.directory),
            capture_config=batch.config,
            detector_kind="explicit-controlled-fixture",
        )
    assert events == ["inference"] * 96 + ["evaluation"] * 96
    return documents


def test_all_twelve_houses_predict_before_private_evaluation_and_preserve_populations(
    complete_batch, monkeypatch, tmp_path
):
    batch = complete_batch
    monkeypatch.setattr(task.subprocess, "run", successful_process)
    before, config = task.verify_historical_collection(
        batch.directory,
        pin=batch.pin,
        capture_source=batch.source,
        archive=tmp_path / "archive",
        sdk_python=tmp_path / "sdk-env/bin/python",
        binary=tmp_path / "Unity",
    )
    assert before == task.inventory(batch.directory) and config == batch.config
    documents = run_composed(batch, monkeypatch)
    public, report = documents["public"], documents["report"]
    assert len(public) == len(report["frames"]) == 96
    assert report["capture_source_files"] == batch.config["source_files"]
    assert report["diagnostic_source_files"] == task.source_identity(batch.current)
    assert report["collection_inventory_sha256"] == batch.pin
    assert report["public_predictions_sha256"] == content_sha256(public)
    assert all(
        not report[key]
        for key in (
            "automatic_identity_assignment",
            "semantic_category_mapping",
            "formal_position_reference_selected",
            "training_performed",
            "calibration_performed",
            "observation_likelihood_written",
            "online_memory_write",
            "independent_label_custody",
        )
    )
    overall = report["summary"]["overall"]
    assert overall["frames"] == 96 and overall["houses"] == list(range(1, 13))
    assert (
        overall["unique_rgb"] == overall["unique_depth"] == overall["unique_geometry_inputs"] == 8
    )
    all_rows, eligible = overall["all_instances"], overall["eligible_instances"]
    assert all_rows["frames_without_candidates"] == 8
    assert all_rows["candidates"] == 264
    assert all_rows["instance_frames"] == 288
    assert all_rows["visible_instance_frames"] == 96
    assert all_rows["invisible_instance_frames"] == 192
    assert all_rows["unique_instances"] == 36 and eligible["unique_instances"] == 24
    assert all_rows["candidate_instance_pairs"] == 792
    assert all_rows["positive_overlap_pairs"] == 176
    assert all_rows["zero_overlap_pairs"] == 616
    assert report["summary"]["by_split"]["train"]["frames"] == 64
    assert report["summary"]["by_split"]["validation"]["frames"] == 32
    for prediction, evaluated in zip(public, report["frames"], strict=True):
        geometry = prediction["frame"]["geometry"]
        assert (
            prediction["command"]["action_id"]
            == evaluated["action_id"]
            == geometry["camera"]["action_id"]
        )
        assert geometry["camera"]["rgb_sha256"] == evaluated["rgb_sha256"]
        assert geometry["camera"]["depth_sha256"] == evaluated["depth_sha256"]
        assert {row["object_id"] for row in evaluated["instances"]} == {"a", "b", "floor"}
        assert all(len(candidate["overlaps"]) == 3 for candidate in evaluated["candidates"])
    output = tmp_path / "saved"
    task.save_or_verify(output, documents, verify=False)
    fresh = run_composed(batch, monkeypatch)
    task.save_or_verify(output, fresh, verify=True)
    for name in ("public", "report", "inputs"):
        path = output / f"{name}.json"
        original = path.read_bytes()
        write_json(path, [] if name == "public" else {"forged_complete": True})
        with pytest.raises(ValueError, match=f"fresh {name} differs"):
            task.save_or_verify(output, fresh, verify=True)
        path.write_bytes(original)
    for name in ("public", "report"):
        path = output / f"{name}.json"
        original = path.read_bytes()
        forged = json.loads(original)
        if name == "public":
            forged[0]["frame"]["geometry"]["memory_write_authorized"] = 0
        else:
            forged["training_performed"] = 0
        assert forged == fresh[name]  # Python equality alone wrongly equates bool and int.
        write_json(path, forged)
        with pytest.raises(ValueError, match=f"fresh {name} differs"):
            task.save_or_verify(output, fresh, verify=True)
        path.write_bytes(original)
    (output / "extra.json").write_text("{}")
    with pytest.raises(ValueError, match="file inventory differs"):
        task.save_or_verify(output, fresh, verify=True)
    (output / "extra.json").unlink()
    task.save_or_verify(output, fresh, verify=True)
    assert task.inventory(batch.directory) == before


def test_cli_verify_reinfers_before_rejecting_changed_public_report_or_extra_file(
    complete_batch, monkeypatch, tmp_path
):
    batch, output = complete_batch, tmp_path / "cli-output"
    monkeypatch.setattr(task, "ROOT", batch.current)
    monkeypatch.setattr(task.subprocess, "run", successful_process)
    argv = ["diagnose_offline_frontend.py"]
    for key, value in dict(
        collection=batch.directory,
        capture_source=batch.source,
        archive=tmp_path / "archive",
        sdk_python=tmp_path / "sdk-env/bin/python",
        binary=tmp_path / "Unity",
        weights=tmp_path / "controlled-decoder-no-weights",
        output=output,
        detector="ssdlite",
        inventory_sha256=batch.pin,
    ).items():
        argv.extend(["--" + key.replace("_", "-"), str(value)])

    def invoke(*, verify):
        events = []
        factory = decoder_factory_with_empty_first_house(events)
        monkeypatch.setattr(task, "make_decoder", lambda weights, kind, scope: factory(scope))
        monkeypatch.setattr(sys, "argv", [*argv, *(["--verify"] if verify else [])])
        try:
            task.main()
        finally:
            # Even a forged saved output is checked against all 96 fresh inferences.
            assert events == ["inference"] * 96

    invoke(verify=False)
    invoke(verify=True)
    for name in ("public", "report"):
        path = output / f"{name}.json"
        original = path.read_bytes()
        forged = json.loads(original)
        report_path = output / "report.json"
        saved_report = report_path.read_bytes()
        if name == "public":
            # Preserve a complete prediction and coherently update its saved report hash.
            forged[8]["frame"]["frame"]["candidates"][0]["detector_score"] = 0.95
            forged[8]["frame"]["candidates"][0]["detector_score_uncalibrated"] = 0.95
            rewritten_report = json.loads(saved_report)
            rewritten_report["public_predictions_sha256"] = content_sha256(forged)
            write_json(report_path, rewritten_report)
        else:
            # Complete, parseable result with an unearned scientific authority claim.
            forged["formal_position_reference_selected"] = True
        write_json(path, forged)
        with pytest.raises(ValueError, match=f"fresh {name} differs"):
            invoke(verify=True)
        assert path.read_bytes() != original  # Verification never overwrites the evidence.
        path.write_bytes(original)
        report_path.write_bytes(saved_report)
    extra = output / "extra.json"
    extra.write_text("{}")
    with pytest.raises(ValueError, match="file inventory differs"):
        invoke(verify=True)
    assert extra.read_text() == "{}"


def test_input_and_saved_diagnosis_symlinks_are_not_accepted(tmp_path):
    original = tmp_path / "original"
    original.mkdir()
    (original / "raw.bin").write_bytes(b"raw")
    linked = tmp_path / "linked"
    linked.symlink_to(original, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink input directory"):
        task.inventory(linked)
    (original / "alias.bin").symlink_to(original / "raw.bin")
    with pytest.raises(ValueError, match="symlink input entry"):
        task.inventory(original)
    output = tmp_path / "output"
    documents = dict(public=[], report={}, inputs={})
    task.save_or_verify(output, documents, verify=False)
    (output / "public.json").unlink()
    (output / "public.json").symlink_to(output / "report.json")
    with pytest.raises(ValueError, match="file inventory differs"):
        task.save_or_verify(output, documents, verify=True)
