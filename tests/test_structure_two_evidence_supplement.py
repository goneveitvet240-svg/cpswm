"""Real isolated source/CLI and inode-level adversarial regressions for W1-R1/R2/R3."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = (
    "three_arm_death_test",
    "readout_posthoc_diagnostic",
    "debt_replay_confirmation",
    "readout_prior_factorial",
    "unseen_d0_holdout",
)
RELATIVE_CURRENT = "benchmarks/structure_two/evidence_repair_supplement_2026_09_11/current_v0_3"
HISTORY = "benchmarks/structure_two/evidence_repair_2026_09_11/history/three_arm_first_failure.json"
BOOT = """
import sys, types
from pathlib import Path
root = Path.cwd()
p = root / 'apps/evaluation_runner/structure_two_source_bootstrap.py'
boot = types.ModuleType('_cpswm_source_bootstrap')
sys.modules[boot.__name__] = boot
exec(compile(p.read_bytes(), str(p), 'exec'), boot.__dict__)
boot.establish(root)
"""


@pytest.fixture
def copied(tmp_path):
    for name in ("src", "configs", "apps"):
        shutil.copytree(ROOT / name, tmp_path / name, ignore=shutil.ignore_patterns("__pycache__"))
    for name in ("pyproject.toml", "uv.lock"):
        shutil.copy2(ROOT / name, tmp_path / name)
    history = Path(HISTORY).parent
    shutil.copytree(ROOT / history, tmp_path / history)
    for name in ("three_arm_death_test", "readout_posthoc_diagnostic"):
        relative = f"benchmarks/structure_two/structure_two_p5_{name}_v0_1.json"
        shutil.copy2(ROOT / relative, tmp_path / relative)
    common = Path(
        subprocess.check_output(
            ["git", "rev-parse", "--git-common-dir"], cwd=ROOT, text=True
        ).strip()
    )
    if not common.is_absolute():
        common = ROOT / common
    return tmp_path, {
        **os.environ,
        "PYTHONPATH": str(tmp_path / "src"),
        "GIT_DIR": str(common.resolve()),
    }


def command(copied, *args):
    root, env = copied
    return subprocess.run(
        [sys.executable, *args], cwd=root, env=env, text=True, capture_output=True
    )


@pytest.mark.parametrize(
    "mode", ["ordinary", "late_import", "guard_then_change", "change_before_load"]
)
def test_execution_rejects_unbootstrapped_or_changed_loaded_source(copied, mode):
    root, _ = copied
    source = "src/cpswm/system/continual/project_one_regime_loop.py"
    mutation = (
        f"p=Path({source!r}); p.write_text(p.read_text().replace("
        "'owner_evidence_threshold: float = 0.5', "
        "'owner_evidence_threshold: float = 0.9', 1))\n"
    )
    imports = (
        "from cpswm.system.continual.project_one_regime_loop import PrototypeLoopConfig\n"
        "assert PrototypeLoopConfig().owner_evidence_threshold == 0.5\n"
    )
    if mode == "late_import":
        code = (
            "from pathlib import Path\n" + imports + mutation + "import runpy\nrunpy.run_path("
            "'apps/evaluation_runner/probe_structure_two_execution_source.py', "
            "run_name='__main__')"
        )
    elif mode == "ordinary":
        code = (
            "from pathlib import Path\n"
            + imports
            + "from cpswm.system.evaluation_operations.structure_two_p5_three_arm_death_test "
            "import _source_binding,_load_config\n"
            "_source_binding(Path.cwd(),_load_config(Path.cwd()))"
        )
    else:
        code = BOOT + (imports + mutation if mode == "guard_then_change" else mutation + imports)
        code += (
            "from cpswm.system.evaluation_operations.structure_two_p5_three_arm_death_test "
            "import _source_binding,_load_config\n_source_binding(root,_load_config(root))"
        )
    result = command(copied, "-c", code)
    assert result.returncode != 0, result.stdout
    assert any(t in result.stderr for t in ("bootstrap", "source changed")), result.stderr
    assert not list((root / RELATIVE_CURRENT).glob("*.json"))


@pytest.mark.parametrize("cache", ["absent", "valid", "stale_same_size_mtime"])
def test_formal_entry_uses_actual_frozen_semantics_despite_bytecode_cache(copied, cache):
    root, _ = copied
    source = root / "src/cpswm/system/continual/project_one_regime_loop.py"
    if cache != "absent":
        result = command(
            copied,
            "-c",
            "from cpswm.system.continual.project_one_regime_loop import PrototypeLoopConfig; "
            "print(PrototypeLoopConfig().owner_evidence_threshold)",
        )
        assert result.returncode == 0 and result.stdout.strip() == "0.5"
    expected = 0.5
    if cache == "stale_same_size_mtime":
        old = source.stat()
        source.write_text(
            source.read_text().replace(
                "owner_evidence_threshold: float = 0.5", "owner_evidence_threshold: float = 0.9", 1
            )
        )
        os.utime(source, ns=(old.st_atime_ns, old.st_mtime_ns))
        assert source.stat().st_size == old.st_size
        stale = command(
            copied,
            "-c",
            "from cpswm.system.continual.project_one_regime_loop import PrototypeLoopConfig; "
            "print(PrototypeLoopConfig().owner_evidence_threshold)",
        )
        assert (
            stale.stdout.strip() == "0.5"
        )  # The independent counterexample still really triggers.
        expected = 0.9
    result = command(copied, "apps/evaluation_runner/probe_structure_two_execution_source.py")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["loaded_owner_evidence_threshold"] == expected
    assert (
        payload["source_binding"]["execution_source"]["policy"] == "frozen-source-compile-no-pyc@1"
    )


@pytest.mark.parametrize(
    "attack",
    [
        "empty",
        "deleted",
        "renamed",
        "commit",
        "git_path",
        "path",
        "lifecycle",
        "duplicate",
        "conflict",
    ],
)
@pytest.mark.parametrize("entry", ["aggregate", "audit"])
def test_both_history_commands_reject_edited_complete_mapping_and_compatible_report(
    copied, attack, entry
):
    root, _ = copied
    path = root / "configs/project_two_experiments/structure_two_evidence_history_v0_1.json"
    config = json.loads(path.read_text())
    if attack == "empty":
        config["entries"] = []
    elif attack == "deleted":
        config["entries"].pop()
    elif attack in {"duplicate", "conflict"}:
        item = dict(config["entries"][1])
        if attack == "conflict":
            item["record_commit"] = config["entries"][0]["record_commit"]
        config["entries"].append(item)
    else:
        key = {"renamed": "id", "commit": "record_commit"}.get(attack, attack)
        config["entries"][1][key] = "unapproved-source-or-name"
    path.write_text(json.dumps(config))
    # Alter the matching report too: failure must not depend on an unchanged digest.
    report = root / "compatible-report.json"
    report.write_text(
        json.dumps(
            {
                "protocol": "structure-two-historical-local-git-audit@0.2",
                "records": config["entries"],
                "coverage": {
                    "git_byte_records_completed": len(config["entries"]),
                    "numerical_recomputations_completed": 0,
                },
            }
        )
    )
    args = (
        ["apps/evaluation_runner/run_structure_two_evidence_repair.py", "--verify-history"]
        if entry == "aggregate"
        else [
            "apps/evaluation_runner/audit_structure_two_evidence_history.py",
            "--verify",
            str(report),
        ]
    )
    result = command(copied, *args)
    assert result.returncode != 0, result.stdout
    assert "required historical identity/lifecycle mapping" in result.stderr
    assert "replay completed" not in result.stdout


@pytest.mark.parametrize(
    "case",
    [
        "new",
        "existing",
        "hardlink",
        "file_symlink",
        "directory_symlink",
        "escape",
        "verify_failure",
        "publish_failure",
        "interrupt",
        "race_target",
        "race_hardlink",
        "caller_mutates_payload",
        "race_directory",
        "source_during_verify",
        "source_after_link",
    ],
)
def test_shared_publication_preserves_real_history_and_cleans_failure(copied, case):
    root, _ = copied
    before = hashlib.sha256((root / HISTORY).read_bytes()).hexdigest()
    code = (
        BOOT
        + f"CASE={case!r}\nHISTORY={HISTORY!r}\n"
        + """
import hashlib, json, os
from cpswm.system.evaluation_operations.structure_two_evidence_versions import CURRENT_DIRECTORY
from cpswm.system.evaluation_operations.structure_two_evidence_publication import (
    publish_verified_json,
)
from cpswm.system.reproducibility import content_sha256
history = root / HISTORY
original = history.read_bytes()
target = root / CURRENT_DIRECTORY / 'boundary.json'
target.parent.mkdir(parents=True)
body = {'boundary_test_only': True, 'value': 7}
payload = {**body, 'content_sha256': content_sha256(body)}
def verify(value):
    assert value == payload and value['value'] == 7
    if CASE == 'verify_failure': raise ValueError('verification failed')
    if CASE == 'source_during_verify': mutate_source()
    if CASE == 'caller_mutates_payload': payload['value'] = 99
def mutate_source():
    p = root / 'src/cpswm/system/continual/project_one_regime_loop.py'
    p.write_text(p.read_text() + '\\n# concurrent change\\n')
if CASE == 'existing': target.write_text('sealed old bytes')
if CASE == 'hardlink': os.link(history, target)
if CASE == 'file_symlink': target.symlink_to(history)
if CASE == 'directory_symlink':
    target.parent.rmdir(); target.parent.symlink_to(history.parent, target_is_directory=True)
if CASE == 'escape': target = target.parent / '..' / '..' / 'escape.json'
link = os.link
def racing_link(*args, **kwargs):
    if CASE == 'publish_failure': raise OSError('publication failure')
    if CASE == 'interrupt': raise KeyboardInterrupt()
    if CASE == 'race_target': os.symlink(history, target)
    if CASE == 'race_hardlink': link(history, target)
    if CASE == 'race_directory':
        target.parent.rename(root / 'moved-parent')
        target.parent.symlink_to(history.parent, target_is_directory=True)
    result = link(*args, **kwargs)
    if CASE == 'source_after_link': mutate_source()
    return result
os.link = racing_link
try:
    output = publish_verified_json(root, target, payload, verify=verify)
except (ValueError, OSError, KeyboardInterrupt) as error:
    assert CASE not in {'new', 'caller_mutates_payload'}, repr(error)
    print(json.dumps({'case': CASE, 'rejected': True, 'reason': str(error)}))
else:
    assert CASE in {'new', 'caller_mutates_payload'}
    assert json.loads(output.read_text()) == {**body, 'content_sha256': content_sha256(body)}
    print(json.dumps({'case': CASE, 'published': True}))
assert history.read_bytes() == original
if CASE == 'existing': assert target.read_text() == 'sealed old bytes'
assert not list(root.rglob('.partial-*'))
if CASE == 'race_directory': assert not list((root / 'moved-parent').glob('*.json'))
"""
    )
    result = command(copied, "-c", code)
    assert result.returncode == 0, result.stdout + result.stderr
    assert hashlib.sha256((root / HISTORY).read_bytes()).hexdigest() == before


@pytest.mark.parametrize("name", [*EXPERIMENTS, "aggregate"])
def test_real_generation_entries_refuse_existing_hardlinked_outputs(copied, name):
    root, _ = copied
    history = root / HISTORY
    before = history.read_bytes()
    parent = root / RELATIVE_CURRENT
    parent.mkdir(parents=True)
    for experiment in EXPERIMENTS:
        os.link(history, parent / f"structure_two_p5_{experiment}_v0_3.json")
    args = (
        ["apps/evaluation_runner/run_structure_two_evidence_repair.py", "--generate-current"]
        if name == "aggregate"
        else [
            f"apps/evaluation_runner/run_structure_two_p5_{name}.py",
            "--repository-root",
            str(root),
        ]
    )
    result = command(copied, *args)
    assert result.returncode != 0, result.stdout
    assert "sealed current output already exists" in result.stderr
    assert history.read_bytes() == before


def test_reviewed_v0_2_and_eleven_archives_remain_exact_git_bytes():
    config = json.loads(
        (
            ROOT / "configs/project_two_experiments/structure_two_evidence_history_v0_1.json"
        ).read_text()
    )
    paths = [entry["path"] for entry in config["entries"]]
    paths.extend(
        p.relative_to(ROOT).as_posix()
        for p in (ROOT / "benchmarks/structure_two/evidence_repair_2026_09_11/current").glob(
            "*.json"
        )
    )
    assert len(paths) == 16
    for relative in paths:
        original = subprocess.check_output(
            ["git", "show", "91dbdc57968071be29976d1a7b99de51d9288cdd:" + relative], cwd=ROOT
        )
        assert (ROOT / relative).read_bytes() == original


@pytest.mark.parametrize("name", EXPERIMENTS)
def test_sealed_v0_2_cannot_be_presented_as_current_v0_3(name):
    import importlib

    module = importlib.import_module(f"cpswm.system.evaluation_operations.structure_two_p5_{name}")
    path = (
        ROOT
        / "benchmarks/structure_two/evidence_repair_2026_09_11/current"
        / f"structure_two_p5_{name}_v0_2.json"
    )
    with pytest.raises(ValueError, match="lifecycle/version mismatch"):
        getattr(module, f"verify_p5_{name}")(json.loads(path.read_text()), repository_root=ROOT)


def test_sources_only_history_report_honestly_records_no_recomputation(copied):
    root, _ = copied
    result = command(
        copied,
        "apps/evaluation_runner/audit_structure_two_evidence_history.py",
        "--output",
        "sources-only.json",
    )
    assert result.returncode == 0, result.stderr
    report = json.loads((root / "sources-only.json").read_text())
    assert report["coverage"]["git_byte_records_completed"] == 11
    assert report["coverage"]["numerical_recomputations_completed"] == 0
    assert report["coverage"]["required_replay_requested"] is False
    assert "replay completed" not in result.stdout
    # The formal completion guard cannot convert a sources-only report into success.
    code = (
        BOOT
        + """
import importlib.util, json
p = root / 'apps/evaluation_runner/audit_structure_two_evidence_history.py'
spec = importlib.util.spec_from_file_location('history_completion', p)
module = importlib.util.module_from_spec(spec)
boot.guard.execute_application(module, p)
module.require_completed_replay(json.loads((root / 'sources-only.json').read_text()))
"""
    )
    result = command(copied, "-c", code)
    assert result.returncode != 0
    assert "required historical failed replay did not actually complete" in result.stderr
