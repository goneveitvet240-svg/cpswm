from __future__ import annotations

import copy
import importlib
import json
import shutil
from pathlib import Path

import pytest

from cpswm.system.evaluation_operations.structure_two_evidence_versions import (
    CURRENT_DIRECTORY,
    current_evidence_context,
    historical_entries,
    require_current_output,
    verify_historical_record,
)
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_production_system import (
    build_production_assembly_manifest,
    verify_production_assembly_manifest,
)

ROOT = Path(__file__).resolve().parents[1]
NAMES = (
    "three_arm_death_test",
    "readout_posthoc_diagnostic",
    "debt_replay_confirmation",
    "readout_prior_factorial",
    "unseen_d0_holdout",
)


def _rehash(payload):
    payload["content_sha256"] = content_sha256(
        {key: value for key, value in payload.items() if key != "content_sha256"}
    )


def test_all_archives_match_their_pinned_git_records() -> None:
    entries = historical_entries(ROOT)
    assert len(entries) == 11
    for entry in entries:
        result = verify_historical_record(ROOT, entry)
        assert result["local_git_bytes_verified"]
        assert result["current_source_recomputation_verified"] is False
        assert result["first_execution_established"] is False


def test_historical_rehashed_numeric_forgery_is_not_git_evidence(tmp_path: Path) -> None:
    entry = historical_entries(ROOT)[0]
    forged = json.loads((ROOT / entry["path"]).read_text())
    forged["test_episode_metrics"][0]["put_back_errors"] += 1
    _rehash(forged)
    # Git reads still use the actual repository; only the retained file is substituted.
    path = tmp_path / "forged.json"
    path.write_text(json.dumps(forged))
    with pytest.raises(ValueError, match="not local"):
        verify_historical_record(ROOT, {**entry, "path": str(path)})
    local = ROOT / ".checkout" / f"forged-{tmp_path.name}.json"
    local.parent.mkdir(exist_ok=True)
    try:
        local.write_text(json.dumps(forged))
        with pytest.raises(ValueError, match="differs from pinned Git"):
            verify_historical_record(ROOT, {**entry, "path": str(local)})
    finally:
        local.unlink(missing_ok=True)


@pytest.mark.parametrize("name", NAMES)
def test_historical_artifact_cannot_impersonate_current(name: str) -> None:
    module = importlib.import_module(f"cpswm.system.evaluation_operations.structure_two_p5_{name}")
    payload = json.loads(
        (ROOT / f"benchmarks/structure_two/structure_two_p5_{name}_v0_1.json").read_text()
    )
    with pytest.raises(ValueError, match="lifecycle/version mismatch"):
        getattr(module, f"verify_p5_{name}")(payload, repository_root=ROOT)
    # Relabelling and rehashing cannot repair its old source binding.
    payload["evidence_context"] = current_evidence_context()
    _rehash(payload)
    with pytest.raises(ValueError, match=r"binding|identity"):
        getattr(module, f"verify_p5_{name}")(payload, repository_root=ROOT)


@pytest.mark.parametrize("name", NAMES)
def test_rehashed_complete_numeric_forgery_reaches_and_fails_recomputation(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = importlib.import_module(f"cpswm.system.evaluation_operations.structure_two_p5_{name}")
    genuine = json.loads((ROOT / module.DEFAULT_OUTPUT).read_text())
    forged = copy.deepcopy(genuine)
    scope = forged["data_scope"]
    key = next(k for k, v in scope.items() if type(v) is int and v > 0)
    scope[key] += 1
    _rehash(forged)
    called = []

    def recompute(*, repository_root):
        called.append(repository_root)
        return genuine

    # This unit test isolates each verifier's equality boundary. The required
    # p5_evidence_current audit command separately executes all five real runners.
    monkeypatch.setattr(module, f"run_p5_{name}", recompute)
    with pytest.raises(ValueError, match="recomputation disagrees"):
        getattr(module, f"verify_p5_{name}")(forged, repository_root=ROOT)
    assert called == [ROOT]


@pytest.mark.parametrize("name", NAMES)
def test_current_output_cannot_overwrite_legacy_or_first_open(name: str) -> None:
    with pytest.raises(ValueError, match="versioned current"):
        require_current_output(
            ROOT, Path(f"benchmarks/structure_two/structure_two_p5_{name}_v0_1.json")
        )
    with pytest.raises(ValueError, match="versioned current"):
        require_current_output(ROOT, CURRENT_DIRECTORY / ".." / "history" / "replacement.json")
    assert require_current_output(ROOT, CURRENT_DIRECTORY / "safe.json").is_relative_to(ROOT)


@pytest.mark.parametrize("mutation", ["replace", "add", "delete", "lock", "symlink"])
def test_complete_transitive_binding_detects_source_inventory_changes(
    tmp_path: Path, mutation: str
) -> None:
    shutil.copytree(ROOT / "src", tmp_path / "src", ignore=shutil.ignore_patterns("__pycache__"))
    for name in ("pyproject.toml", "uv.lock"):
        shutil.copy2(ROOT / name, tmp_path / name)
    original = build_production_assembly_manifest(tmp_path)
    source = tmp_path / "src/cpswm/system/continual/project_one_regime_loop.py"
    if mutation == "replace":
        source.write_text(source.read_text() + "\n# source substitution\n")
    elif mutation == "add":
        (source.parent / "injected_dependency.py").write_text("INJECTED = True\n")
    elif mutation == "delete":
        (
            tmp_path / "src/cpswm/system/evaluation_operations/structure_two_evidence_versions.py"
        ).unlink()
    elif mutation == "lock":
        lock = tmp_path / "uv.lock"
        lock.write_text(lock.read_text() + "\n# environment substitution\n")
    else:
        source.unlink()
        source.symlink_to(ROOT / source.relative_to(tmp_path))
    with pytest.raises(ValueError, match=r"manifest mismatch|local regular|not repository-local"):
        verify_production_assembly_manifest(original, tmp_path)


def test_imported_runtime_cannot_rebind_itself_to_replaced_source(tmp_path: Path) -> None:
    import os
    import subprocess
    import sys

    shutil.copytree(ROOT / "src", tmp_path / "src", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(ROOT / "configs", tmp_path / "configs")
    for name in ("pyproject.toml", "uv.lock"):
        shutil.copy2(ROOT / name, tmp_path / name)
    code = """
from pathlib import Path
from cpswm.system.evaluation_operations.structure_two_evidence_versions import (
    require_execution_source,
)
root = Path.cwd()
require_execution_source(root)
p = root / 'src/cpswm/system/continual/project_one_regime_loop.py'
p.write_text(p.read_text() + '\\n# replaced after import\\n')
try:
    require_execution_source(root)
except ValueError as error:
    assert 'changed since process import' in str(error)
else:
    raise AssertionError('cached runtime silently rebound to changed source')
"""
    subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(tmp_path / "src")},
        check=True,
        capture_output=True,
    )


@pytest.mark.parametrize("target", ["dataset", "failure_and_expected_hash"])
def test_frozen_inputs_reject_joint_payload_and_expected_hash_rewrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    from cpswm.system.evaluation_operations import structure_two_evidence_versions as versions

    shutil.copytree(ROOT / "configs", tmp_path / "configs")
    benchmark = tmp_path / "benchmarks/structure_two"
    benchmark.mkdir(parents=True)
    for name in ("three_arm_death_test", "readout_posthoc_diagnostic"):
        filename = f"structure_two_p5_{name}_v0_1.json"
        shutil.copy2(ROOT / "benchmarks/structure_two" / filename, benchmark / filename)
    real_git_bytes = versions.git_bytes
    monkeypatch.setattr(
        versions, "git_bytes", lambda root, commit, path: real_git_bytes(ROOT, commit, path)
    )
    versions.require_frozen_p5_inputs(tmp_path)
    if target == "dataset":
        path = tmp_path / "configs/project_two_datasets/d0_unseen_p5_holdout_v0_6.json"
        payload = json.loads(path.read_text())
        payload["test_seed_start"] = 99999
        path.write_text(json.dumps(payload))
    else:
        import hashlib

        path = benchmark / "structure_two_p5_three_arm_death_test_v0_1.json"
        payload = json.loads(path.read_text())
        payload["test_episode_metrics"][0]["put_back_errors"] = 0
        _rehash(payload)
        path.write_text(json.dumps(payload))
        config = (
            tmp_path / "configs/project_two_experiments/"
            "structure_two_p5_readout_posthoc_diagnostic_v0_1.json"
        )
        declaration = json.loads(config.read_text())
        declaration["trigger"]["retained_failed_result_file_sha256"] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        declaration["trigger"]["retained_failed_result_content_sha256"] = payload["content_sha256"]
        config.write_text(json.dumps(declaration))
    with pytest.raises(ValueError, match="frozen P5 input differs"):
        versions.require_frozen_p5_inputs(tmp_path)
