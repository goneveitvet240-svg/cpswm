"""Controlled archive transport/detectors and synthetic residuals, actual Native.

No real 96-frame archive or real validation labels are used in these tests.
PYTEST_DONT_REWRITE: recovery binds the untouched helper source bodies.
"""

import shutil
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
import run_archive_native_bridge as bridge
from soft_position_dataset import public_readout
from test_instance_affinity_dataset import public
from test_native_neural_production import checkpoints as _checkpoints
from test_native_neural_production import cpu_threads as _cpu_threads
from test_native_position_production import fixture_models
from test_offline_frontend_evaluation import frame_args

from cpswm.data_preflight import soft_surface_position
from cpswm.data_preflight.typed_proposal_networks import ARMS
from cpswm.perception_mapping import position_observation_model as position
from cpswm.system.reproducibility import content_sha256

checkpoints = _checkpoints
cpu_threads = _cpu_threads


def inputs(tmp_path):
    args = frame_args(tmp_path)
    record = public(args)
    models = fixture_models()
    full = public_readout(record, models["affinity_model"], models["affinity_pin"])
    chosen = bridge.first_seed(record, full, models["affinity_model"], models["affinity_pin"])
    receipt = bridge.correspondence(
        record, full, models["affinity_model"], models["affinity_pin"], chosen
    )
    return record, models, full, receipt


def test_scope_time_adaptation_preserves_original_raw_and_controlled_roles(tmp_path):
    record, _, _, receipt = inputs(tmp_path)
    before = deepcopy(record["delivery"])
    probe = bridge.adapted_probe(record["delivery"])
    scope = receipt["packet"]["scope"]
    for day in probe.case.days:
        for name in ("before", "after", "actor_evidence", "mechanism_evidence", "role_evidence"):
            item = getattr(day, name)
            if item is not None:
                meta = item.metadata
                assert [str(meta.household_id), str(meta.session_id), str(meta.trace_id)] == scope
                for key in ("detection_time", "evidence_time"):
                    if getattr(item, key, None) is not None:
                        assert getattr(item, key) > record["delivery"].received_at
    assert record["delivery"] == before
    assert bridge.packet_binding(record["delivery"].observations) == receipt["packet"]
    assert len(receipt["full_sources"]) > len(receipt["single_sources"])
    assert receipt["full_seed_id"] != receipt["single_seed_id"]
    assert (
        probe.case.object_instance_id
        == bridge.BackboneWiringProbe.build(seed=171).case.object_instance_id
    )


@pytest.mark.parametrize("field", ["world_points_m", "pixels_uv", "valid", "sources"])
def test_complete_parent_neighborhood_forgery_rejected_then_legal(tmp_path, field):
    record, models, full, _ = inputs(tmp_path)
    forged = deepcopy(full)
    neighborhood = forged["neighborhoods"][0]
    if field == "world_points_m":
        neighborhood[field][0][0] += 1.0
    elif field == "pixels_uv":
        neighborhood[field] = list(reversed(neighborhood[field]))
    elif field == "valid":
        neighborhood[field][0] = not neighborhood[field][0]
    else:
        neighborhood[field] = neighborhood[field][:1]
    with pytest.raises(ValueError, match="parent public readout differs"):
        bridge.first_seed(record, forged, models["affinity_model"], models["affinity_pin"])
    assert bridge.first_seed(record, full, models["affinity_model"], models["affinity_pin"])


def test_actual_four_model_native_publication_fresh_processes_and_replay(tmp_path, checkpoints):
    record, models, _, receipt = inputs(tmp_path / "inputs")
    entries = {}
    for estimator in position.ESTIMATORS:
        for reference in position.REFERENCES:
            model = deepcopy(models["position_model"])
            model.update(
                estimator=estimator,
                reference_kind=reference,
                estimator_pin=content_sha256(
                    dict(
                        schema=soft_surface_position.SCHEMA,
                        estimator=estimator,
                        definition=soft_surface_position.DEFINITION,
                        affinity_pin=models["affinity_pin"]
                        if estimator == "soft_affinity"
                        else None,
                    )
                ),
            )
            pin = position.checkpoint_sha256(model)
            position.restore(model, pin)
            entries[estimator + "/" + reference] = dict(status="fitted", model=model, pin=pin)
    checkpoint, pin = checkpoints[ARMS[1]]
    result = bridge.run_comparison(
        tmp_path / "native",
        record=record,
        receipt=receipt,
        affinity_model=models["affinity_model"],
        affinity_pin=models["affinity_pin"],
        model_entries=entries,
        checkpoint=checkpoint,
        checkpoint_pin=pin,
        external_binding={"scope": "CONTROLLED_TEST_PACKAGE_NOT_REAL_PARENT"},
    )
    assert len(result["results"]) == 4
    for value in result["results"].values():
        assert value["status"] == "consumed" and value["replay_equals_no_factor"]
        active, control = value["arms"]["active"], value["arms"]["no_factor"]
        assert active["active"] != control["active"]
        assert active["fresh_processes"] == control["fresh_processes"] == 2
        assert np.asarray(active["active"]["known"]["information"])[3:, 3:] == pytest.approx(
            np.eye(3)
        )
        assert active["after_retraction"] == control["after_retraction"]
    fresh = tmp_path / "expected-native"
    shutil.copytree(tmp_path / "native", fresh)
    originals = bridge.inventory(tmp_path / "native")
    bridge.verify_saved_consequences(tmp_path / "native", fresh, result)
    assert bridge.inventory(tmp_path / "native") == originals
    # A complete self-rehashed saved configuration still cannot change original models.
    config_path = (
        tmp_path / "native/soft_affinity/sdk_transform_position_m/active/configuration.json"
    )
    original = config_path.read_bytes()
    changed = bridge._json(config_path)
    changed["models"]["position_model"]["bias"][0] += 1.0
    changed["models"]["position_pin"] = position.checkpoint_sha256(
        changed["models"]["position_model"]
    )
    changed["source_identity"] = content_sha256(
        {k: v for k, v in changed.items() if k != "source_identity"}
    )
    bridge.write_json(config_path, changed)
    with pytest.raises(ValueError, match="owner configuration differs"):
        bridge.verify_saved_consequences(tmp_path / "native", fresh, result)
    config_path.write_bytes(original)
    assert bridge.inventory(tmp_path / "native") == originals


def test_all_unavailable_are_recorded_without_replacement_or_checkpoint_loading(tmp_path):
    record, models, _, receipt = inputs(tmp_path / "inputs")
    entries = {
        e + "/" + r: dict(status="fit_failed", reason="controlled rank deficient fixture")
        for e in position.ESTIMATORS
        for r in position.REFERENCES
    }
    result = bridge.run_comparison(
        tmp_path / "unavailable",
        record=record,
        receipt=receipt,
        affinity_model=models["affinity_model"],
        affinity_pin=models["affinity_pin"],
        model_entries=entries,
        checkpoint=tmp_path / "not-loaded",
        checkpoint_pin="a" * 64,
        external_binding={"scope": "CONTROLLED_TEST_PACKAGE_NOT_REAL_PARENT"},
    )
    assert len(result["results"]) == 4
    assert all(
        v["status"] == "unavailable" and not v["replacement_created"]
        for v in result["results"].values()
    )


@pytest.mark.parametrize("changed", ["collection", "affinity", "frontend", "source"])
def test_ancestor_change_rejected_and_legal_bytes_recover(tmp_path, changed):
    def source(name):
        root = tmp_path / name
        (root / "src").mkdir(parents=True)
        (root / "src/a.py").write_text("x = 1\n")
        return root

    args = SimpleNamespace(
        collection=tmp_path / "collection", capture_source=source("capture-source")
    )
    args.collection.mkdir()
    bridge.write_json(
        args.collection / "configuration.json",
        {"source_files": bridge.source_identity(args.capture_source)},
    )
    (args.collection / "raw.json").write_text('{"raw": true}\n')
    bridge.write_json(args.collection / "inventory.json", bridge.inventory(args.collection))
    args.inventory_sha256 = bridge.digest(args.collection / "inventory.json")
    binding = {"collection_inventory_sha256": args.inventory_sha256}
    for key in ("controls", "affinity"):
        root = tmp_path / key
        (root / "experiment").mkdir(parents=True)
        (root / "experiment/model.json").write_text("{}\n")
        (root / "case-results.json").write_text("[]\n")
        setattr(args, key + "_results", root)
        src = source(key + "-source")
        setattr(args, key + "_source", src)
        pin = bridge.digest(root / "case-results.json")
        setattr(args, key + "_ledger_sha256", pin)
        binding[key] = dict(
            ledger_sha256=pin,
            output_files=bridge.inventory(root / "experiment"),
            source_files=bridge.source_identity(src),
        )
    args.frontends = tmp_path / "frontends"
    args.frontends.mkdir()
    (args.frontends / "case-results.json").write_text("[]\n")
    args.frontend_ledger_sha256 = bridge.digest(args.frontends / "case-results.json")
    args.frontend_source = source("frontend-source")
    files = {}
    for method in ("fasterrcnn", "ssdlite"):
        folder = args.frontends / method
        folder.mkdir()
        (folder / "public.json").write_text("[]\n")
        files[method] = bridge.inventory(folder)
    binding["frontends"] = dict(
        ledger_sha256=args.frontend_ledger_sha256,
        source_files=bridge.source_identity(args.frontend_source),
        files=files,
    )
    bundle = SimpleNamespace(report={"parent_binding": binding})
    bridge.verify_ancestors(args, bundle)
    path = {
        "collection": args.collection / "raw.json",
        "affinity": args.affinity_results / "experiment/model.json",
        "frontend": args.frontends / "ssdlite/public.json",
        "source": args.affinity_source / "src/a.py",
    }[changed]
    original = path.read_bytes()
    path.write_bytes(original + b" ")
    with pytest.raises(ValueError, match="ancestor"):
        bridge.verify_ancestors(args, bundle)
    path.write_bytes(original)
    bridge.verify_ancestors(args, bundle)


@pytest.mark.parametrize("value", [True, False])
def test_saved_configuration_json_boolean_cannot_be_replaced_by_equal_integer(tmp_path, value):
    saved, fresh = tmp_path / "saved", tmp_path / "fresh"
    for root in (saved, fresh):
        (root / "model/active").mkdir(parents=True)
        bridge.write_json(root / "visible-case.json", {})
        bridge.write_json(root / "public-correspondence.json", {})
        bridge.write_json(
            root / "model/active/configuration.json", {"configuration": {"enabled": value}}
        )
    bridge.write_json(
        saved / "model/active/configuration.json", {"configuration": {"enabled": int(value)}}
    )
    before = bridge.inventory(saved)
    # The complete parsed JSON comparison must reject before opening any database.
    with pytest.raises(ValueError, match="owner configuration differs"):
        bridge.verify_saved_consequences(
            saved, fresh, {"results": {"model": {"status": "consumed"}}}
        )
    assert bridge.inventory(saved) == before
