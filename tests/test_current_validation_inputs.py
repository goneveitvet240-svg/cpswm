"""Orchestration boundaries use real child processes, not scientific acceptance fixtures."""

import json
import sys

import pytest
from prepare_current_validation_inputs import ARTIFACTS, consumer_environment, plan, prepare


def project(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    for name in ("pyproject.toml", "uv.lock", ".python-version"):
        (root / name).write_text("fixture\n")
    p0 = root / "benchmarks/p0_checkpoint/content_manifest_v0_3.json"
    p0.parent.mkdir(parents=True)
    p0.write_text("old index\n")
    return root


def child(code):
    return [sys.executable, "-c", code]


def install_fixture_plan(monkeypatch, root, out, *, fault=None):
    # This isolates process/state-machine behavior only. Actual project CLIs
    # are exercised separately; these bytes are never science/receipt evidence.
    write = "from pathlib import Path; p=Path(" + repr(str(out)) + "); "
    write += "; ".join(
        f"(p/{name!r}).parent.mkdir(parents=True,exist_ok=True); (p/{name!r}).write_text('fixture')"
        for name in ARTIFACTS[:-1]
    )
    commands = [("generate_fixture", child(write)), ("comparison_recompute", child("pass"))]
    if fault == "exit":
        commands.append(("failure", child("raise SystemExit(7)")))
    elif fault == "source":
        commands.append(
            ("drift", child("from pathlib import Path; Path('uv.lock').write_text('drift')"))
        )
    elif fault == "verified_input":
        commands.append(
            (
                "corrupt",
                child(
                    "from pathlib import Path; Path("
                    + repr(str(out / ARTIFACTS[0]))
                    + ").write_text('changed')"
                ),
            )
        )
    elif fault == "missing":
        commands.append(
            (
                "remove",
                child(
                    "from pathlib import Path; Path(" + repr(str(out / ARTIFACTS[4])) + ").unlink()"
                ),
            )
        )
    else:
        commands.append(("p0_validate", child("pass")))
    monkeypatch.setattr("prepare_current_validation_inputs.plan", lambda _root, _out: commands)


def test_actual_children_prepare_transfer_and_mutable_index_preservation(tmp_path, monkeypatch):
    root = project(tmp_path)
    output = tmp_path / "prepared"
    install_fixture_plan(monkeypatch, root, output)
    result = prepare(root, output)
    assert result["status"] == "PREPARED_NOT_ACCEPTED"
    assert (output / "preserved-p0.json").read_bytes() == b"old index\n"
    assert result["scope"] == "CURRENT_TEST_INPUTS_ONLY_NOT_ENGINEERING_ACCEPTANCE"
    assert all(r["exit_code"] == 0 for r in result["commands"])
    expected = consumer_environment(root, output)
    # Caller-supplied environment fields cannot redirect the consumer.
    result["environment"] = {"S2_AUDIT_BUNDLE": "/forged/elsewhere"}
    (output / "preparation.json").write_text(json.dumps(result))
    assert consumer_environment(root, output) == expected
    moved = tmp_path / "moved"
    output.rename(moved)
    assert consumer_environment(root, moved)["S2_AUDIT_BUNDLE"] == str(moved / "comparison")


@pytest.mark.parametrize(
    "fault, reason",
    [
        ("exit", "exit 7"),
        ("source", "source drift"),
        ("verified_input", "verified input changed"),
        ("missing", "missing or aliased"),
    ],
)
def test_failure_never_publishes_consumer_paths_and_retry_needs_new_directory(
    tmp_path, monkeypatch, fault, reason
):
    root = project(tmp_path)
    output = tmp_path / "prepared"
    install_fixture_plan(monkeypatch, root, output, fault=fault)
    with pytest.raises((ValueError, RuntimeError), match=reason):
        prepare(root, output)
    assert json.loads((output / "preparation.json").read_text())["status"] == "FAILED"
    assert not (output / "environment.json").exists()
    with pytest.raises(ValueError, match="did not complete"):
        consumer_environment(root, output)
    with pytest.raises(ValueError, match="new output directory"):
        prepare(root, output)


@pytest.mark.parametrize("change", ["source", "artifact", "missing", "p0", "status", "alias"])
def test_consumer_refuses_drift_and_missing_material(tmp_path, monkeypatch, change):
    root = project(tmp_path)
    output = tmp_path / "prepared"
    install_fixture_plan(monkeypatch, root, output)
    prepare(root, output)
    path = output / ARTIFACTS[0]
    if change == "source":
        (root / "uv.lock").write_text("different")
    elif change == "artifact":
        path.write_text("changed")
    elif change == "missing":
        path.unlink()
    elif change == "p0":
        (root / "benchmarks/p0_checkpoint/content_manifest_v0_3.json").write_text("changed")
    elif change == "status":
        record = json.loads((output / "preparation.json").read_text())
        record["status"] = "RUNNING"
        (output / "preparation.json").write_text(json.dumps(record))
    else:
        twin = tmp_path / "twin"
        twin.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(twin)
    with pytest.raises(ValueError):
        consumer_environment(root, output)


def test_plan_keeps_real_generate_replay_and_manifest_consumer_order(tmp_path):
    root = tmp_path / "root"
    commands = plan(root, tmp_path / "output")
    assert [n for n, _ in commands] == [
        "comparison_generate",
        "comparison_recompute",
        "attribution_generate",
        "attribution_recompute",
        "scientific_generate",
        "scientific_recompute",
        "p0_generate",
        "p0_validate",
    ]
    assert all(args[0] == str(root / ".venv/bin/python") for _, args in commands)
    assert commands[1][1][-1] == commands[3][1][-1] == "--verify"
    assert "--verify" in commands[5][1]
    assert "--no-fresh-replay" not in commands[5][1]
