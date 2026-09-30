"""Contract tests use an explicit tiny stand-in historical CLI, not real refitting."""

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import verified_position_parent as parent
from diagnose_offline_frontend import inventory, source_identity


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True))


def _fixture(tmp_path, *, failed=False):
    source = tmp_path / "historical"
    script = source / "tools/run_soft_position_development.py"
    script.parent.mkdir(parents=True)
    script.write_text('import sys\nassert "--verify" in sys.argv\nraise SystemExit(0)\n')
    root = tmp_path / "results"
    exp = root / "experiment"
    for name in parent.COMBINATIONS:
        _write(exp / f"models/{name}.json", {"fixture": True, "name": name})
        _write(exp / f"training/{name}/members.json", [])
        (exp / f"training/{name}/residuals.npy").write_bytes(b"explicit fixture, not numpy")
    for i in range(96):
        for kind in ("public", "labels", "corrected"):
            _write(exp / f"frames/{i:03d}/{kind}.json", {"ordinal": i, "kind": kind})
    _write(exp / "controlled-position-consumption.json", {"fixture": True})
    report = dict(
        schema="soft-surface-position-development@1",
        source_files=source_identity(source),
        members=inventory(exp),
        training_attempted=True,
        models_fitted=0 if failed else 4,
        training_performed=not failed,
        model_status={
            n: {"status": "fit_failed" if failed else "fitted"} for n in parent.COMBINATIONS
        },
        frames=[
            dict(
                house_index=i // 8 + 1,
                split="train" if i < 64 else "validation",
                prefix=f"frames/{i:03d}",
                action_id=f"explicit-fixture-{i}",
            )
            for i in range(96)
        ],
        parent_binding={
            k: {"ledger_sha256": "a" * 64} for k in ("controls", "affinity", "frontends")
        }
        | {"collection_inventory_sha256": "a" * 64},
    )
    report.update(
        {
            k: False
            for k in (
                "runtime_authority",
                "calibrated",
                "natural_factor_completed",
                "world_identity_assigned",
                "formal_position_reference_selected",
                "orientation_observed",
            )
        }
    )
    _write(exp / "report.json", report)
    cases = [
        dict(
            phase=p,
            exit_code=0,
            source_sha="b" * 40,
            output_sha256=inventory(exp),
            argv=["DO-NOT-EXECUTE", str(tmp_path / "unauthorized-file")],
        )
        for p in ("run", "verify")
    ]
    _write(root / "case-results.json", cases)
    args = SimpleNamespace(
        parent_position_results=root,
        parent_position_source=source,
        parent_position_ledger_sha256=parent.digest(root / "case-results.json"),
    )
    import sys

    for name in parent.PATH_ARGUMENTS:
        setattr(
            args,
            name,
            Path(sys.executable)
            if name in ("historical_python", "sdk_python")
            else tmp_path / name,
        )
    for name in parent.PIN_ARGUMENTS:
        setattr(args, name, "a" * 64)
    return args


@pytest.mark.parametrize("failed", [False, True])
def test_valid_parent_and_readonly_copies(tmp_path, failed):
    args = _fixture(tmp_path, failed=failed)
    bundle = parent.verify_position_parent(args)
    assert len(bundle.binding["output_files"]) == 302
    assert bundle.load_json("frames/000/public.json")["ordinal"] == 0
    report = bundle.report
    report["models_fitted"] = 99
    binding = bundle.binding
    binding["output_files"].clear()
    bundle.assert_unchanged()
    assert bundle.report["models_fitted"] == (0 if failed else 4)
    assert not (tmp_path / "unauthorized-file").exists()


@pytest.mark.parametrize(
    "name",
    [
        "../case-results.json",
        "/report.json",
        "frames//000/public.json",
        "training/soft_affinity/sdk_aabb_center_m/residuals.npy",
        "missing.json",
    ],
)
def test_only_exact_pinned_json_members(tmp_path, name):
    bundle = parent.verify_position_parent(_fixture(tmp_path))
    with pytest.raises(ValueError):
        bundle.load_json(name)


def test_persisted_member_and_source_changes_rejected(tmp_path):
    bundle = parent.verify_position_parent(_fixture(tmp_path))
    path = bundle.experiment / "frames/000/public.json"
    original = path.read_bytes()
    _write(path, {"ordinal": 17})
    with pytest.raises(ValueError, match="member changed"):
        bundle.load_json("frames/000/public.json")
    with pytest.raises(ValueError, match="output members"):
        bundle.assert_unchanged()
    path.write_bytes(original)
    script = bundle.source / "tools/run_soft_position_development.py"
    script.write_text(script.read_text() + "# changed\n")
    with pytest.raises(ValueError, match="source"):
        bundle.assert_unchanged()


def test_complete_self_reseal_cannot_replace_external_ledger_pin(tmp_path):
    args = _fixture(tmp_path)
    exp = args.parent_position_results / "experiment"
    _write(exp / "models/soft_affinity/sdk_aabb_center_m.json", {"forged": True})
    report = json.loads((exp / "report.json").read_text())
    report["members"] = {k: v for k, v in inventory(exp).items() if k != "report.json"}
    _write(exp / "report.json", report)
    ledger = args.parent_position_results / "case-results.json"
    cases = json.loads(ledger.read_text())
    for case in cases:
        case["output_sha256"] = inventory(exp)
    _write(ledger, cases)
    with pytest.raises(ValueError, match="ledger pin"):
        parent.verify_position_parent(args)


def test_fresh_failure_is_not_ignored(tmp_path):
    args = _fixture(tmp_path)
    script = args.parent_position_source / "tools/run_soft_position_development.py"
    script.write_text("raise SystemExit(3)\n")
    exp = args.parent_position_results / "experiment"
    report = json.loads((exp / "report.json").read_text())
    report["source_files"] = source_identity(args.parent_position_source)
    _write(exp / "report.json", report)
    ledger = args.parent_position_results / "case-results.json"
    cases = json.loads(ledger.read_text())
    for c in cases:
        c["output_sha256"] = inventory(exp)
    _write(ledger, cases)
    args.parent_position_ledger_sha256 = parent.digest(ledger)
    with pytest.raises(ValueError, match="fresh refit failed"):
        parent.verify_position_parent(args)


def test_ancestor_pin_mismatch_precedes_replay(tmp_path):
    args = _fixture(tmp_path)
    args.affinity_ledger_sha256 = "c" * 64
    with pytest.raises(ValueError, match="ancestor external pins"):
        parent.verify_position_parent(args)


def test_symlink_member_cannot_be_loaded(tmp_path):
    bundle = parent.verify_position_parent(_fixture(tmp_path))
    path = bundle.experiment / "frames/000/public.json"
    raw = path.read_bytes()
    path.unlink()
    target = tmp_path / "same-bytes.json"
    target.write_bytes(raw)
    path.symlink_to(target)
    with pytest.raises(ValueError, match="symlink"):
        bundle.load_json("frames/000/public.json")
    with pytest.raises(ValueError, match="symlink"):
        bundle.assert_unchanged()


def test_arguments_build_fixed_entry_not_ledger_command(tmp_path):
    args = _fixture(tmp_path)
    command = parent._historical_command(
        args, args.parent_position_source, args.parent_position_results
    )
    assert command[1] == str(args.parent_position_source / "tools/run_soft_position_development.py")
    assert command[-1] == "--verify"
    assert "--output" in command
    parser = argparse.ArgumentParser()
    parent.add_parent_arguments(parser)
    assert len([a for a in parser._actions if a.required]) == 19
