"""Actual entry code and real cross-directory historical replay regressions."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import py_compile
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ENTRY = "apps/evaluation_runner/probe_structure_two_execution_source.py"
MODULE = "apps.evaluation_runner.probe_structure_two_execution_source"
AUDIT = "apps/evaluation_runner/audit_structure_two_evidence_history.py"
HISTORY = "benchmarks/structure_two/evidence_repair_2026_09_11/history"


def source_copy(root: Path) -> tuple[Path, dict]:
    for name in ("src", "apps", "configs"):
        shutil.copytree(ROOT / name, root / name, ignore=shutil.ignore_patterns("__pycache__"))
    for name in ("conftest.py", "pyproject.toml", "uv.lock"):
        shutil.copy2(ROOT / name, root / name)
    shutil.copytree(ROOT / HISTORY, root / HISTORY)
    for name in ("three_arm_death_test", "readout_posthoc_diagnostic"):
        path = Path(f"benchmarks/structure_two/structure_two_p5_{name}_v0_1.json")
        shutil.copy2(ROOT / path, root / path)
    common = subprocess.check_output(
        ["git", "rev-parse", "--git-common-dir"], cwd=ROOT, text=True
    ).strip()
    return root, {
        **os.environ,
        "PYTHONPATH": str(root / "src"),
        "GIT_DIR": str((ROOT / common).resolve()),
    }


def run(tree, *args):
    root, env = tree
    result = subprocess.run(
        [sys.executable, *args], cwd=root, env=env, capture_output=True, text=True
    )
    print(
        json.dumps(
            {
                "argv": result.args,
                "cwd": str(root),
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        ),
        flush=True,
    )
    return result


@pytest.mark.parametrize("launch", ["file", "module", "runpy", "spawn_file", "spawn_module"])
@pytest.mark.parametrize("cache", ["absent", "valid_timestamp", "valid_unchecked"])
def test_real_supported_entries_and_spawn_keep_loaded_semantics(tmp_path, launch, cache):
    tree = source_copy(tmp_path)
    entry = tmp_path / ENTRY
    if cache != "absent":
        py_compile.compile(
            str(entry),
            doraise=True,
            invalidation_mode=(
                py_compile.PycInvalidationMode.UNCHECKED_HASH
                if cache == "valid_unchecked"
                else py_compile.PycInvalidationMode.TIMESTAMP
            ),
        )
    args = [ENTRY] if launch in {"file", "spawn_file"} else ["-m", MODULE]
    if launch == "runpy":
        args = ["-c", f"import runpy; runpy.run_module({MODULE!r},run_name='__main__')"]
    if launch.startswith("spawn_"):
        args.append("--spawn")
    result = run(tree, *args)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["loaded_owner_evidence_threshold"] == 0.5
    assert payload["source_binding"]["execution_source"]["policy"] == (
        "frozen-source-and-entry-compile@2"
    )
    assert "stale_entry_executed" not in payload
    if launch.startswith("spawn_"):
        assert payload["pid"] != payload["parent_pid"]


@pytest.mark.parametrize("cache", ["unchecked", "same_size_mtime", "foreign_filename"])
@pytest.mark.parametrize("spawn", [False, True])
def test_module_entry_rejects_actual_old_or_foreign_code_before_source_claim(
    tmp_path, cache, spawn
):
    tree = source_copy(tmp_path)
    entry = tmp_path / ENTRY
    original, stat = entry.read_bytes(), entry.stat()
    # Change nested code; the foreign-cache case also carries a foreign filename.
    entry.write_bytes(original.replace(b'"diagnostic_only": True', b'"diagnostic_only": None'))
    os.utime(entry, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    assert entry.stat().st_size == stat.st_size
    pyc = py_compile.compile(
        str(entry),
        doraise=True,
        dfile="/foreign/root/" + ENTRY if cache == "foreign_filename" else None,
        invalidation_mode=(
            py_compile.PycInvalidationMode.TIMESTAMP
            if cache == "same_size_mtime"
            else py_compile.PycInvalidationMode.UNCHECKED_HASH
        ),
    )
    cache_bytes = Path(pyc).read_bytes()
    entry.write_bytes(original)
    os.utime(entry, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    result = run(tree, "-m", MODULE, *(["--spawn"] if spawn else []))
    assert result.returncode != 0, result.stdout
    assert "formal bootstrap" in result.stderr and "entry" in result.stderr
    assert "source_binding" not in result.stdout
    assert entry.read_bytes() == original and Path(pyc).read_bytes() == cache_bytes
    assert not list(tmp_path.glob("benchmarks/**/current_v0_4/*.json"))
    # File entry executes current source despite the same intact bad cache.
    positive = run(tree, ENTRY)
    assert positive.returncode == 0, positive.stderr
    assert json.loads(positive.stdout)["diagnostic_only"] is True


@pytest.mark.parametrize("kind", ["string", "foreign_file", "entry_changed_during_execution"])
def test_unsupported_entry_and_execution_drift_cannot_claim_current_source(tmp_path, kind):
    tree = source_copy(tmp_path)
    if kind == "entry_changed_during_execution":
        code = (
            f"import runpy; m=runpy.run_path({ENTRY!r},run_name='verified_probe'); "
            f"from pathlib import Path; p=Path({ENTRY!r}); "
            "p.write_text(p.read_text()+'\\n# changed during execution\\n'); m['probe']()"
        )
    else:
        code = (
            "import sys,types; from pathlib import Path; "
            "root=Path.cwd(); p=root/'apps/evaluation_runner/structure_two_source_bootstrap.py'; "
            "b=types.ModuleType('_cpswm_source_bootstrap'); sys.modules[b.__name__]=b; "
            "exec(compile(p.read_bytes(),str(p),'exec'),b.__dict__); b.establish(root)"
        )
    args = ["-c", code]
    if kind == "foreign_file":
        foreign = tmp_path / "unapproved.py"
        foreign.write_text(code)
        args = [str(foreign)]
    result = run(tree, *args)
    assert result.returncode != 0 and not result.stdout
    assert "entry" in result.stderr or "source changed" in result.stderr


def test_full_history_replay_and_report_verification_across_roots(tmp_path):
    first = source_copy(tmp_path / "first")
    second = source_copy(tmp_path / "second")
    report_path = first[0] / "sealed-history.json"
    before = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (first[0] / HISTORY).glob("*.json")
    }
    generated = run(
        first,
        AUDIT,
        "--recompute-first-failure",
        "--recompute-failed-replay",
        "--output",
        str(report_path),
    )
    assert generated.returncode == 0, generated.stderr
    report = json.loads(report_path.read_text())
    verified = run(second, AUDIT, "--verify", str(report_path))
    assert verified.returncode == 0, verified.stderr
    assert "1 required full failed replay completed" in verified.stdout
    expected_rows = [json.loads(line) for line in verified.stdout.splitlines()[:-1]]
    assert expected_rows == report["records"]
    assert report["coverage"] == {
        "git_byte_records_completed": 11,
        "source_snapshots_recoverable": 4,
        "numerical_recomputations_completed": 1,
        "required_replay_requested": True,
    }
    error = next(
        row["source_import_error"] for row in report["records"] if row["source_import_error"]
    )
    assert "Traceback (most recent call last):" in error and "ImportError:" in error
    assert "RegimeStage" in error and "<audit-source>/apps/" in error
    assert str(first[0]) not in error and str(second[0]) not in error
    assert "<historical-source:557ff9ceec267e1f37ebbdc3a27a9364b8b482b8>" in error

    # Compare real, fully replayed reports through the production comparator in a
    # fresh process. No fake expected result or numeric-recomputation replacement.
    for attack in (
        "error_type",
        "error_content",
        "traceback",
        "source",
        "record",
        "coverage",
        "replay",
        "boolean_count",
        "unknown_path",
    ):
        forged = copy.deepcopy(report)
        row = next(row for row in forged["records"] if row["source_import_error"])
        if attack == "error_type":
            row["source_import_error"] = row["source_import_error"].replace(
                "ImportError:", "RuntimeError:"
            )
        elif attack == "error_content":
            row["source_import_error"] = row["source_import_error"].replace(
                "RegimeStage", "OtherMissingSymbol"
            )
        elif attack == "traceback":
            row["source_import_error"] = row["source_import_error"].replace(
                "in exec_module", "in foreign_loader"
            )
        elif attack == "unknown_path":
            row["source_import_error"] += " /unrelated/execution/root"
        elif attack == "source":
            forged["audit_execution_source"]["inventory_sha256"] = "0" * 64
        elif attack == "record":
            row["record_commit"] = "0" * 40
        elif attack == "coverage":
            forged["coverage"]["git_byte_records_completed"] = 10
        elif attack == "boolean_count":
            forged["coverage"]["numerical_recomputations_completed"] = True
        else:
            next(r for r in forged["records"] if r["numerical_recomputation_performed"])[
                "numerical_recomputation_performed"
            ] = False
        candidate = second[0] / (attack + ".json")
        candidate.write_text(json.dumps(forged))
        result = run(
            second,
            "-c",
            "import runpy,json; from pathlib import Path; "
            f"m=runpy.run_path({AUDIT!r},run_name='history_compare'); "
            "m['verify_history_report']("
            f"json.loads(Path({str(candidate)!r}).read_text()),"
            f"json.loads(Path({str(report_path)!r}).read_text()))",
        )
        assert result.returncode != 0 and "differs from fresh snapshot/replay" in result.stderr, (
            attack
        )
    # Actual source replacement also changes report identity despite identical
    # historic Git snapshots. This runs the true CLI and required full replay.
    source = second[0] / "src/cpswm/system/continual/project_one_regime_loop.py"
    original_source = source.read_bytes()
    source.write_bytes(original_source + b"\nREVIEW_SOURCE_REPLACEMENT = True\n")
    changed_source = run(second, AUDIT, "--verify", str(report_path))
    assert changed_source.returncode != 0
    assert "differs from fresh snapshot/replay" in changed_source.stderr
    changed_rows = [json.loads(line) for line in changed_source.stdout.splitlines()]
    assert sum(row["numerical_recomputation_performed"] for row in changed_rows) == 1
    source.write_bytes(original_source)
    # Replace a retained record and repair its outer self-hash; pinned Git bytes
    # must still reject it through the real CLI, before any success declaration.
    history_config = json.loads(
        (
            second[0] / "configs/project_two_experiments/structure_two_evidence_history_v0_1.json"
        ).read_text()
    )
    retained = second[0] / history_config["entries"][0]["path"]
    original_record = retained.read_bytes()
    changed = json.loads(original_record)
    changed["test_episode_metrics"][0]["put_back_errors"] += 1
    from cpswm.system.reproducibility import content_sha256

    changed["content_sha256"] = content_sha256(
        {k: v for k, v in changed.items() if k != "content_sha256"}
    )
    retained.write_text(json.dumps(changed))
    substituted_record = run(second, AUDIT, "--verify", str(report_path))
    assert substituted_record.returncode != 0
    assert "differs from pinned Git record" in substituted_record.stderr
    assert "replay completed" not in substituted_record.stdout
    retained.write_bytes(original_record)
    assert before == {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (first[0] / HISTORY).glob("*.json")
    }


def test_reviewed_v0_3_outputs_remain_exact_and_cannot_be_current():
    import importlib

    directory = ROOT / "benchmarks/structure_two/evidence_repair_supplement_2026_09_11/current_v0_3"
    paths = list(directory.glob("*.json"))
    assert len(paths) == 5
    for path in paths:
        old = subprocess.check_output(
            [
                "git",
                "show",
                "816a88b242c24b9c6ace6021bba23e4b5b8b526e:" + path.relative_to(ROOT).as_posix(),
            ],
            cwd=ROOT,
        )
        assert path.read_bytes() == old
        name = path.stem.removesuffix("_v0_3")
        module = importlib.import_module("cpswm.system.evaluation_operations." + name)
        with pytest.raises(ValueError, match="lifecycle/version mismatch"):
            getattr(module, "verify_p5_" + name.removeprefix("structure_two_p5_"))(
                json.loads(old), repository_root=ROOT
            )


@pytest.mark.parametrize(
    "entry",
    [
        ENTRY,
        AUDIT,
        "apps/evaluation_runner/run_structure_two_evidence_repair.py",
        "apps/evaluation_runner/generate_structure_two_engineering_trust_checkpoint.py",
        *(
            f"apps/evaluation_runner/run_structure_two_p5_{name}.py"
            for name in (
                "three_arm_death_test",
                "readout_posthoc_diagnostic",
                "debt_replay_confirmation",
                "readout_prior_factorial",
                "unseen_d0_holdout",
            )
        ),
    ],
)
def test_every_formal_module_rejects_stale_entry_then_accepts_current_file(tmp_path, entry):
    tree = source_copy(tmp_path)
    path = tmp_path / entry
    original = path.read_bytes()
    path.write_bytes(original + b"\nraise RuntimeError('stale entry reached end')\n")
    py_compile.compile(
        str(path), doraise=True, invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH
    )
    path.write_bytes(original)
    result = run(tree, "-m", entry.removesuffix(".py").replace("/", "."), "--help")
    assert result.returncode != 0 and "executing entry differs" in result.stderr
    assert not result.stdout
    positive = run(tree, entry, "--help")
    assert positive.returncode == 0 and "usage:" in positive.stdout, positive.stderr


def test_bootstrap_changed_between_execution_and_source_freeze_is_rejected(tmp_path):
    tree = source_copy(tmp_path)
    bootstrap = "apps/evaluation_runner/structure_two_source_bootstrap.py"
    # Retain a genuinely executed bootstrap, then alter its implementation before
    # the real formal entry freezes disk source. No method or receipt is replaced.
    code = (
        "import sys,types,runpy; from pathlib import Path; "
        f"p=Path({bootstrap!r}); original=p.read_bytes(); "
        "b=types.ModuleType('_cpswm_source_bootstrap'); sys.modules[b.__name__]=b; "
        "exec(compile(original,str(p.resolve()),'exec'),b.__dict__); "
        "p.write_bytes(original+b'\\nNEW_BOOTSTRAP_SEMANTICS = True\\n'); "
        f"runpy.run_path({ENTRY!r},run_name='__main__')"
    )
    result = run(tree, "-c", code)
    assert result.returncode != 0 and "executing loader differs" in result.stderr
    assert not result.stdout
