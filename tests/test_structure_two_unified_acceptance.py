"""Exercise the real coordinator engine; fixture stages confer no scientific authority.

Small repositories below test execution, fail-closed progress and process cleanup.
They deliberately do not stand in for the full three-window experiment matrices.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import py_compile
import shutil
import signal
import subprocess
import sys
import time
import uuid
from contextlib import suppress
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/structure_two_unified_acceptance.py"
MODULE = "tools.structure_two_unified_acceptance"
RUN_AREA = Path("docs/reviews/data/structure_two_unified_acceptance_runs")
SPEC = importlib.util.spec_from_file_location("_unified_acceptance_regression", TOOL)
assert SPEC is not None and SPEC.loader is not None
coordinator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = coordinator
SPEC.loader.exec_module(coordinator)


def command(argv, *, cwd, timeout=45, env=None):
    result = subprocess.run(argv, cwd=cwd, text=True, capture_output=True, timeout=timeout, env=env)
    print(
        json.dumps(
            {
                "argv": list(argv),
                "cwd": str(cwd),
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        ),
        flush=True,
    )
    return result


@pytest.fixture
def tree(tmp_path):
    root = (tmp_path / "checkout").resolve()
    root.mkdir()
    for args in (
        ("init", "-q"),
        ("config", "user.email", "fixture@example.invalid"),
        ("config", "user.name", "Coordinator regression fixture"),
    ):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    (root / "implementation.py").write_text("VALUE = 1\n")
    subprocess.run(["git", "-C", str(root), "add", "implementation.py"], check=True)
    subprocess.run(
        ["git", "-C", str(root), "commit", "-qm", "Pin fixture implementation"], check=True
    )
    return root


def setup_run(root, name="run"):
    excluded = (Path("runs"),)
    journal = coordinator.Journal(root / "runs" / name)
    return journal, coordinator.source_snapshot(root, excluded), excluded


def stage(name, code, junit=None):
    return coordinator.Stage(name, (sys.executable, "-c", code), junit)


def state(journal):
    return json.loads((journal.path / "state.json").read_text())


def test_legal_stages_execute_in_order_and_preserve_complete_hashed_logs(tree):
    journal, frozen, excluded = setup_run(tree)
    code = (
        "from pathlib import Path; import sys; "
        "p=Path('runs/order'); p.write_text(p.read_text()+'one\\n' if p.exists() "
        "else 'one\\n'); print('x'*12000); print('first stderr',file=sys.stderr)"
    )
    second = (
        "from pathlib import Path; p=Path('runs/order'); "
        "assert p.read_text()=='one\\n'; p.write_text(p.read_text()+'two\\n')"
    )
    coordinator.run_stages(
        tree, journal, [stage("first", code), stage("second", second)], frozen, excluded
    )
    result = state(journal)
    assert result["status"] == "STAGES_COMPLETED_NOT_AUTHORIZATION"
    assert result["scientific_gate"] == "NOT_PASSED"
    assert result["ablation_authorized"] is False
    assert result["source_before"] == result["source_after"] == frozen
    assert (tree / "runs/order").read_text() == "one\ntwo\n"
    assert [row["name"] for row in result["stages"]] == ["first", "second"]
    assert all(row["exit_code"] == 0 and row["status"] == "COMPLETED" for row in result["stages"])
    assert (journal.path / "first.stdout.log").read_text() == "x" * 12000 + "\n"
    assert (journal.path / "first.stderr.log").read_text() == "first stderr\n"
    for row in result["stages"]:
        for stream in ("stdout", "stderr"):
            saved = row[stream]
            assert (
                saved["sha256"]
                == hashlib.sha256((journal.path / saved["path"]).read_bytes()).hexdigest()
            )


def test_preexisting_green_artifact_does_not_skip_real_subprocess(tree):
    journal, frozen, excluded = setup_run(tree)
    (tree / "runs/green.json").write_text('{"passed": true}')
    coordinator.run_stages(
        tree,
        journal,
        [stage("actual", "from pathlib import Path; Path('runs/executed').write_text('actual')")],
        frozen,
        excluded,
    )
    assert (tree / "runs/executed").read_text() == "actual"
    assert len(state(journal)["stages"]) == 1


@pytest.mark.parametrize("mutation", ["tracked", "untracked", "head"])
def test_source_changed_before_start_refuses_even_with_green_artifact(tree, mutation):
    journal, frozen, excluded = setup_run(tree)
    (tree / "runs/green.json").write_text('{"passed": true}')
    if mutation == "tracked":
        (tree / "implementation.py").write_text("VALUE = 2\n")
    elif mutation == "untracked":
        (tree / "extra.py").write_text("VALUE = 2\n")
    else:
        subprocess.run(
            ["git", "-C", str(tree), "commit", "--allow-empty", "-qm", "new"], check=True
        )
    with pytest.raises(ValueError, match="SOURCE_CHANGED"):
        coordinator.run_stages(
            tree,
            journal,
            [stage("forbidden", "from pathlib import Path; Path('runs/downstream').touch()")],
            frozen,
            excluded,
        )
    assert state(journal)["status"] == "FAILED"
    assert state(journal)["stages"] == []
    assert not (tree / "runs/downstream").exists()


def test_zero_exit_and_green_file_cannot_hide_source_change_during_stage(tree):
    journal, frozen, excluded = setup_run(tree)
    stages = [
        stage(
            "mutate",
            "from pathlib import Path; Path('implementation.py').write_text('VALUE = 2\\n'); "
            "Path('runs/green.json').write_text('{\"passed\": true}')",
        ),
        stage("downstream", "raise AssertionError('must never execute')"),
    ]
    with pytest.raises(ValueError, match="SOURCE_CHANGED"):
        coordinator.run_stages(tree, journal, stages, frozen, excluded)
    result = state(journal)
    assert result["status"] == "FAILED"
    assert len(result["stages"]) == 1
    assert result["stages"][0]["exit_code"] == 0
    assert result["stages"][0]["status"] == "FAILED"
    assert result["source_after_failure"] != frozen


def test_failed_stage_cannot_be_hidden_by_downstream_green_files(tree):
    journal, frozen, excluded = setup_run(tree)
    (tree / "runs/checkpoint.json").write_text('{"passed": true}')
    stages = [
        stage("broken", "import sys; print('failure diagnostic',file=sys.stderr); sys.exit(7)"),
        stage("downstream", "from pathlib import Path; Path('runs/downstream').touch()"),
    ]
    with pytest.raises(ValueError, match="STAGE_FAILED"):
        coordinator.run_stages(tree, journal, stages, frozen, excluded)
    result = state(journal)
    assert result["status"] == "FAILED"
    assert result["stages"][0]["exit_code"] == 7
    assert result["stages"][0]["status"] == "FAILED"
    assert (journal.path / "broken.stderr.log").read_text() == "failure diagnostic\n"
    assert len(result["stages"]) == 1
    assert not (tree / "runs/downstream").exists()


def test_retry_requires_new_directory_and_executes_whole_sequence_again(tree):
    first, frozen, excluded = setup_run(tree, "first")
    commands = [
        stage(
            name,
            f"from pathlib import Path; p=Path('runs/count'); "
            f"p.write_text((p.read_text() if p.exists() else '')+{name!r})",
        )
        for name in ("a", "b")
    ]
    coordinator.run_stages(tree, first, commands, frozen, excluded)
    original_state = (first.path / "state.json").read_bytes()
    with pytest.raises(FileExistsError):
        coordinator.Journal(first.path)
    assert (first.path / "state.json").read_bytes() == original_state
    second, second_frozen, second_excluded = setup_run(tree, "second")
    coordinator.run_stages(tree, second, commands, second_frozen, second_excluded)
    assert (tree / "runs/count").read_text() == "abab"
    assert [row["name"] for row in state(second)["stages"]] == ["a", "b"]


@pytest.mark.parametrize(
    "xml",
    [
        "<testsuites><testsuite tests='0'/></testsuites>",
        "<testsuites><testsuite><testcase><skipped/></testcase></testsuite></testsuites>",
        "<testsuites><testsuite><testcase><skipped type='pytest.xfail'>known</skipped>"
        "</testcase></testsuite></testsuites>",
        "<testsuites><testsuite><testcase><failure>bad</failure></testcase></testsuite></testsuites>",
        "<testsuites><testsuite><testcase><error>bad</error></testcase></testsuite></testsuites>",
    ],
    ids=["empty", "skipped", "xfailed", "failed", "error"],
)
def test_zero_exit_cannot_hide_absent_or_incomplete_required_test_matrix(tree, xml):
    journal, frozen, excluded = setup_run(tree)
    write_xml = (
        f"from pathlib import Path; Path({str(journal.path / 'matrix.xml')!r}).write_text({xml!r})"
    )
    with pytest.raises(ValueError, match="absent, failed, skipped or xfailed"):
        coordinator.run_stages(
            tree, journal, [stage("matrix", write_xml, "matrix.xml")], frozen, excluded
        )
    assert state(journal)["status"] == "FAILED"
    assert state(journal)["stages"][0]["exit_code"] == 0


def test_real_pytest_junit_positive_has_actual_nonempty_test_count(tree):
    test_path = tree / "test_fixture_contract.py"
    test_path.write_text("def test_fixture_arithmetic():\n    assert 2 + 3 == 5\n")
    journal, frozen, excluded = setup_run(tree)
    matrix = coordinator.Stage(
        "real_pytest",
        (
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-o",
            "addopts=",
            "--confcutdir=" + str(tree),
            "--junitxml=" + str(journal.path / "matrix.xml"),
            str(test_path),
        ),
        "matrix.xml",
    )
    coordinator.run_stages(tree, journal, [matrix], frozen, excluded)
    row = state(journal)["stages"][0]
    assert row["pytest_counts"] == {"total": 1, "failure": 0, "error": 0, "skipped": 0}
    assert state(journal)["status"] == "STAGES_COMPLETED_NOT_AUTHORIZATION"


@pytest.mark.parametrize(
    "body",
    ["pytest.skip('fixture skip')", "pytest.xfail('fixture xfail')"],
    ids=["actual_skip", "actual_xfail"],
)
def test_real_pytest_zero_exit_with_incomplete_matrix_is_rejected(tree, body):
    test_path = tree / "test_fixture_incomplete.py"
    test_path.write_text(f"import pytest\ndef test_fixture_incomplete():\n    {body}\n")
    journal, frozen, excluded = setup_run(tree)
    matrix = coordinator.Stage(
        "actual_incomplete",
        (
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-o",
            "addopts=",
            "--confcutdir=" + str(tree),
            "--junitxml=" + str(journal.path / "matrix.xml"),
            str(test_path),
        ),
        "matrix.xml",
    )
    with pytest.raises(ValueError, match="absent, failed, skipped or xfailed"):
        coordinator.run_stages(tree, journal, [matrix], frozen, excluded)
    saved = state(journal)
    assert saved["status"] == "FAILED"
    assert saved["stages"][0]["exit_code"] == 0
    assert saved["stages"][0]["pytest_counts"]["total"] == 1
    assert saved["stages"][0]["pytest_counts"]["skipped"] == 1


@pytest.mark.parametrize("mutation", ["rewrite_rehash", "delete_member", "add_member"])
def test_downstream_green_stage_cannot_replace_frozen_artifact_bundle(tree, mutation):
    journal, frozen, excluded = setup_run(tree)
    produce = (
        "import json,hashlib; from pathlib import Path; "
        "p=Path('runs/bundle'); p.mkdir(); "
        "v={'value': 1}; v['sha256']=hashlib.sha256(json.dumps(v).encode()).hexdigest(); "
        "(p/'result.json').write_text(json.dumps(v))"
    )
    changes = {
        "rewrite_rehash": (
            "import json,hashlib; from pathlib import Path; v={'value': 999}; "
            "v['sha256']=hashlib.sha256(json.dumps(v).encode()).hexdigest(); "
            "Path('runs/bundle/result.json').write_text(json.dumps(v))"
        ),
        "delete_member": "from pathlib import Path; Path('runs/bundle/result.json').unlink()",
        "add_member": "from pathlib import Path; Path('runs/bundle/new.json').write_text('{}')",
    }
    stages = [
        coordinator.Stage(
            "produce", (sys.executable, "-c", produce), freeze_outputs=("runs/bundle",)
        ),
        stage("green_but_replaced", changes[mutation] + "; print('PASSED')"),
        stage("forbidden_downstream", "raise AssertionError('cannot reach')"),
    ]
    with pytest.raises(ValueError, match="VERIFIED_ARTIFACT_CHANGED"):
        coordinator.run_stages(tree, journal, stages, frozen, excluded)
    saved = state(journal)
    assert saved["status"] == "FAILED"
    assert [item["name"] for item in saved["stages"]] == ["produce", "green_but_replaced"]
    assert saved["stages"][1]["exit_code"] == 0
    assert saved["stages"][1]["status"] == "FAILED"
    assert (journal.path / "green_but_replaced.stdout.log").read_text() == "PASSED\n"


def test_legitimate_frozen_bundle_is_usable_by_later_actual_stage(tree):
    journal, frozen, excluded = setup_run(tree)
    stages = [
        coordinator.Stage(
            "produce",
            (
                sys.executable,
                "-c",
                "from pathlib import Path; Path('runs/bundle.json').write_text('{\"value\": 1}')",
            ),
            freeze_outputs=("runs/bundle.json",),
        ),
        stage(
            "verify",
            "import json; from pathlib import Path; "
            "assert json.loads(Path('runs/bundle.json').read_text())['value']==1",
        ),
    ]
    coordinator.run_stages(tree, journal, stages, frozen, excluded)
    assert state(journal)["status"] == "STAGES_COMPLETED_NOT_AUTHORIZATION"


def launch_engine(root, code):
    """Launch the shared engine in a fresh process, not a test replacement engine."""
    harness = (
        "import importlib.util, pathlib, signal, sys; "
        f"s=importlib.util.spec_from_file_location('real_coordinator',{str(TOOL)!r}); "
        "m=importlib.util.module_from_spec(s); sys.modules[s.name]=m; s.loader.exec_module(m); "
        "signal.signal(signal.SIGINT,m.interrupted); signal.signal(signal.SIGTERM,m.interrupted); "
        "root=pathlib.Path.cwd(); j=m.Journal(root/'runs'/'interrupt'); "
        "excluded=(pathlib.Path('runs'),); frozen=m.source_snapshot(root,excluded); "
        f"m.run_stages(root,j,[m.Stage('worker',(sys.executable,'-c',{code!r}))],frozen,excluded)"
    )
    output = (root / "engine.stdout.log").open("wb")
    error = (root / "engine.stderr.log").open("wb")
    # The harness streams exist before its source snapshot and remain byte-stable
    # until after stage failure; they are outside the fixture's runtime inputs.
    (root / ".gitignore").write_text("engine.*.log\n")
    proc = subprocess.Popen([sys.executable, "-c", harness], cwd=root, stdout=output, stderr=error)
    output.close()
    error.close()
    return proc


def await_path(path, proc, timeout=10):
    deadline = time.monotonic() + timeout
    while not path.exists():
        if proc.poll() is not None:
            pytest.fail(f"fixture process exited {proc.returncode}: {path}")
        if time.monotonic() > deadline:
            pytest.fail(f"fixture process never became ready: {path}")
        time.sleep(0.03)


@pytest.mark.parametrize("interrupt_signal", [signal.SIGINT, signal.SIGTERM])
def test_interruption_kills_descendants_even_when_group_leader_exits(tree, interrupt_signal):
    child = (
        "import signal,time; from pathlib import Path; "
        "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
        "Path('runs/child_ready').touch(); time.sleep(7); Path('runs/late_write').touch()"
    )
    worker = (
        "import subprocess,sys,time; "
        f"subprocess.Popen([sys.executable,'-c',{child!r}]); time.sleep(60)"
    )
    proc = launch_engine(tree, worker)
    try:
        await_path(tree / "runs/child_ready", proc)
        started = time.monotonic()
        proc.send_signal(interrupt_signal)
        proc.wait(timeout=12)
        result = json.loads((tree / "runs/interrupt/state.json").read_text())
        assert proc.returncode != 0
        assert result["status"] == "INTERRUPTED"
        assert result["stages"][0]["status"] == "INTERRUPTED"
        time.sleep(max(0, 7.5 - (time.monotonic() - started)))
        assert not (tree / "runs/late_write").exists(), (
            "surviving descendant wrote after interruption"
        )
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        journal_path = tree / "runs/interrupt/state.json"
        if journal_path.exists():
            rows = json.loads(journal_path.read_text()).get("stages", [])
            if rows and rows[0].get("pid"):
                with suppress(ProcessLookupError):
                    os.killpg(rows[0]["pid"], signal.SIGKILL)


def test_sigkill_remains_incomplete_and_inspection_never_resumes(tree):
    proc = launch_engine(
        tree, "from pathlib import Path; import time; Path('runs/ready').touch(); time.sleep(60)"
    )
    worker_pid = None
    try:
        await_path(tree / "runs/ready", proc)
        path = tree / "runs/interrupt/state.json"
        worker_pid = json.loads(path.read_text())["stages"][0]["pid"]
        proc.kill()
        proc.wait(timeout=5)
        before = path.read_bytes()
        inspected = command(
            [sys.executable, str(TOOL), "--inspect-run", str(path.parent)], cwd=ROOT
        )
        assert inspected.returncode == 0, inspected.stderr
        payload = json.loads(inspected.stdout)
        assert payload["status"] == "INCOMPLETE_RUN"
        assert payload["recorded_status"] == "RUNNING"
        assert payload["reusable_execution_proof"] is False
        assert path.read_bytes() == before
        with pytest.raises(FileExistsError):
            coordinator.Journal(path.parent)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        if worker_pid is not None:
            with suppress(ProcessLookupError):
                os.killpg(worker_pid, signal.SIGKILL)


def test_real_cli_rejects_declared_root_different_from_executing_checkout(tmp_path):
    run = ROOT / RUN_AREA / ("fixture_wrong_root_" + uuid.uuid4().hex)
    result = command(
        [sys.executable, str(TOOL), "--run-dir", str(run), "--unified-root", str(tmp_path)],
        cwd=ROOT,
    )
    assert result.returncode != 0
    assert "declared unified root differs" in result.stderr
    assert json.loads((run / "state.json").read_text())["status"] == "FAILED"


def test_real_cli_without_unified_root_can_only_record_waiting():
    run = ROOT / RUN_AREA / ("fixture_waiting_" + uuid.uuid4().hex)
    result = command([sys.executable, str(TOOL), "--run-dir", str(run)], cwd=ROOT, timeout=90)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "WAITING_UNIFIED_SOURCE"
    saved = json.loads((run / "state.json").read_text())
    assert saved["status"] == "WAITING_UNIFIED_SOURCE"
    assert saved["scientific_gate"] == "NOT_PASSED"
    assert saved["ablation_authorized"] is False
    assert saved["stages"] == []
    assert saved["root"] == str(ROOT)
    assert saved["environment_before"]["version"].startswith("3.13.")
    assert Path(saved["environment_before"]["prefix"]).resolve() == (ROOT / ".venv").resolve()


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("PYTEST_ADDOPTS", "-k nonexistent_case"),
        ("PYTEST_ADDOPTS", "--deselect=tests/test_required.py::test_required"),
        ("PYTEST_PLUGINS", "foreign_selection_plugin"),
        ("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1"),
        ("PYTHONOPTIMIZE", "1"),
    ],
)
def test_real_cli_refuses_environment_that_can_suppress_required_verification(name, value):
    run = ROOT / RUN_AREA / ("fixture_unsafe_env_" + uuid.uuid4().hex)
    result = command(
        [sys.executable, str(TOOL), "--run-dir", str(run)],
        cwd=ROOT,
        env={**os.environ, name: value},
    )
    assert result.returncode != 0
    assert (
        "unsafe test/import environment" in result.stderr or "plugin suppression" in result.stderr
    )
    assert json.loads((run / "state.json").read_text())["status"] == "FAILED"


@pytest.mark.parametrize("launch", ["file", "module"])
def test_real_cli_entry_accepts_current_code_and_legal_unchecked_cache(tmp_path, launch):
    tool = tmp_path / "tools/structure_two_unified_acceptance.py"
    tool.parent.mkdir()
    tool.write_bytes(TOOL.read_bytes())
    cache = Path(
        py_compile.compile(
            str(tool), doraise=True, invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH
        )
    )
    before = cache.read_bytes()
    recorded = tmp_path / "recorded"
    recorded.mkdir()
    (recorded / "state.json").write_text('{"status": "STARTING"}')
    entry = [str(tool)] if launch == "file" else ["-m", MODULE]
    result = command([sys.executable, *entry, "--inspect-run", str(recorded)], cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "INCOMPLETE_RUN"
    assert cache.read_bytes() == before


def test_real_cli_stale_unchecked_entry_cannot_claim_restored_source(tmp_path):
    tool = tmp_path / "tools/structure_two_unified_acceptance.py"
    tool.parent.mkdir()
    current = TOOL.read_bytes()
    stale = current.replace(
        b"parser = argparse.ArgumentParser(description=__doc__)",
        b"print('old entry reached parser'); parser = argparse.ArgumentParser(description=__doc__)",
    )
    assert stale != current
    tool.write_bytes(stale)
    cache = Path(
        py_compile.compile(
            str(tool), doraise=True, invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH
        )
    )
    before = cache.read_bytes()
    tool.write_bytes(current)
    run = tmp_path / RUN_AREA / "stale"
    result = command([sys.executable, "-m", MODULE, "--run-dir", str(run)], cwd=tmp_path)
    assert result.returncode != 0
    assert "executing coordinator entry differs from declared source" in result.stderr
    assert "old entry reached parser" not in result.stdout
    assert not run.exists()
    assert cache.read_bytes() == before


def test_required_plan_keeps_actual_generation_before_fresh_verification(tree):
    journal, _, _ = setup_run(tree)
    closure = {role: ["tests/test_closure.py::test_" + role] for role in coordinator.CLOSURE_ROLES}
    for path in (
        *coordinator.W1_TESTS,
        *coordinator.W2_TESTS,
        *coordinator.W3_TESTS,
        "tests/test_closure.py",
        "tests/test_structure_two_engineering_trust_checkpoint.py",
    ):
        target = tree / path.split("::")[0]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()
    layout = {
        key: "new/" + key + ".json" for key in ("history", "checkpoint", "p0", "v05", "receipt")
    }
    layout["p5"] = {name: "new/" + name + ".json" for name in coordinator.NAMES}
    plan = coordinator.build_plan(tree, journal, layout, closure)
    names = [item.name for item in plan]
    for before, after in (
        ("comparison_generate", "comparison_recompute"),
        ("attribution_generate", "attribution_recompute"),
        ("five_generate", "five_recompute"),
        ("history_generate", "history_recompute"),
        ("p0_generate", "native_engineering_matrix"),
        ("native_engineering_matrix", "checkpoint_generate_fresh"),
        ("checkpoint_generate_fresh", "checkpoint_verify_fresh"),
        ("checkpoint_verify_fresh", "checkpoint_adversarial"),
    ):
        assert names.index(before) < names.index(after)
    assert len(names) == len(set(names))
    assert all("--no-fresh-recomputation" not in item.argv for item in plan)
    assert all("--skip" not in item.argv for item in plan)
    assert coordinator.W2_TESTS and coordinator.W3_TESTS
    for name in (
        "window1_protection",
        "window2_comparison_and_forgery",
        "window3_revision_and_backbone",
    ):
        assert next(item for item in plan if item.name == name).junit is not None
    for name in (
        "comparison_generate",
        "attribution_generate",
        "attribution_recompute",
        "five_generate",
        "history_generate",
        "v05_compatibility",
        "p0_generate",
        "native_engineering_matrix",
        "checkpoint_generate_fresh",
    ):
        assert next(item for item in plan if item.name == name).freeze_outputs


@pytest.mark.parametrize("closure", [{}, {"public_revision_atomicity": []}])
def test_plan_refuses_empty_or_incomplete_round_four_closure(tree, closure):
    journal, _, _ = setup_run(tree)
    with pytest.raises(ValueError, match="closure"):
        coordinator.build_plan(tree, journal, {}, closure)


def test_plan_refuses_one_test_reused_for_distinct_closure_roles(tree):
    journal, _, _ = setup_run(tree)
    closure = {role: ["tests/test_closure.py::test_one"] for role in coordinator.CLOSURE_ROLES}
    with pytest.raises(ValueError, match="distinct reviewed tests"):
        coordinator.build_plan(tree, journal, {}, closure)


def test_real_native_probe_requires_exactly_five_experiments(tmp_path):
    copied = tmp_path / "native_probe_checkout"
    for name in ("src", "apps", "configs"):
        shutil.copytree(ROOT / name, copied / name, ignore=shutil.ignore_patterns("__pycache__"))
    for name in ("conftest.py", "pyproject.toml", "uv.lock"):
        shutil.copy2(ROOT / name, copied / name)
    positive = command([sys.executable, "-c", coordinator.NATIVE_LAYOUT_CODE], cwd=copied)
    assert positive.returncode == 0, positive.stderr
    payload = json.loads(positive.stdout)
    assert payload["root"] == str(copied)
    assert set(payload["p5"]) == set(coordinator.NAMES)
    entry = copied / "apps/evaluation_runner/run_structure_two_evidence_repair.py"
    original = entry.read_bytes()
    mutation = original.replace(b'    "unseen_d0_holdout",\n', b"", 1)
    assert mutation != original
    entry.write_bytes(mutation)
    negative = command([sys.executable, "-c", coordinator.NATIVE_LAYOUT_CODE], cwd=copied)
    assert negative.returncode != 0
    assert "native output/consumer contract mismatch" in negative.stderr
    assert '"p5"' not in negative.stdout
