"""Adversarial regression tests for F0/A0 provenance binding.

Each test here reproduces an attack that succeeded against the pre-fix code.
They are written as attacks rather than as constraint restatements so that a
reviewer can see the failure mode directly.

Origin: `docs/reviews/F0_对抗审查报告_2026-08-19.md` findings F-1 to F-4.
"""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError
from test_f0_long_horizon_vertical_slice import (
    build_manifest,
    build_policy,
    build_routine_config,
    run_benchmark_view,
)

from cpswm.foundation.persistence_replay import AppendOnlyTransactionLog
from cpswm.foundation.runtime_orchestration.provenance import (
    DIRTY_WORKING_TREE_SUFFIX,
    UNVERSIONED_CODE_VERSION,
    RuntimeProvenanceError,
    build_replay_manifest,
    build_version_bundle,
    file_sha256,
    git_head_code_version,
    git_working_tree_dirty,
    provenance_files,
    source_tree_sha256,
    verify_replay_provenance,
)
from cpswm.system.evaluation_operations import (
    EvaluationProvenance,
    EvaluationRunner,
    evaluation_run_identity,
)
from cpswm.system.evaluation_operations.evaluator import REPOSITORY_ROOT, EvaluationReport
from cpswm.system.household_memory_benchmark import EvaluationTrack
from cpswm.system.reproducibility import content_sha256, content_uuid
from cpswm.system.synthetic_routines import SyntheticRoutineGenerator


def _git(repository: Path, *arguments: str) -> None:
    subprocess.run(["git", "-C", str(repository), *arguments], check=True, capture_output=True)


@pytest.fixture
def committed_repository(tmp_path: Path) -> Path:
    """A minimal repository whose layout mirrors the provenance file set."""

    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "apps").mkdir()
    (tmp_path / "benchmarks").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "src" / "pkg" / "core.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "apps" / "entry.py").write_text("print(VALUE)\n", encoding="utf-8")
    (tmp_path / "benchmarks" / "manifest.json").write_text('{"a": 1}\n', encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "docs" / "notes.md").write_text("scratch\n", encoding="utf-8")
    _git(tmp_path, "init", "--initial-branch=main")
    _git(tmp_path, "config", "user.email", "review@example.invalid")
    _git(tmp_path, "config", "user.name", "review")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-m", "baseline")
    return tmp_path


# --------------------------------------------------------------------------
# F-2  dirty working tree must not be reported as a clean commit
# --------------------------------------------------------------------------


def test_clean_tree_reports_a_bare_commit(committed_repository: Path):
    assert git_working_tree_dirty(committed_repository) is False
    assert not git_head_code_version(committed_repository).endswith(DIRTY_WORKING_TREE_SUFFIX)


def test_modifying_covered_source_marks_the_code_version_dirty(committed_repository: Path):
    """Pre-fix attack: edit src/, keep claiming the clean commit SHA."""

    clean = git_head_code_version(committed_repository)
    (committed_repository / "src" / "pkg" / "core.py").write_text("VALUE = 999\n", encoding="utf-8")

    dirty = git_head_code_version(committed_repository)

    assert git_working_tree_dirty(committed_repository) is True
    assert dirty != clean
    assert dirty.endswith(DIRTY_WORKING_TREE_SUFFIX)
    assert dirty.startswith(clean)


def test_untracked_covered_source_also_marks_the_tree_dirty(committed_repository: Path):
    (committed_repository / "src" / "pkg" / "injected.py").write_text("X = 1\n", encoding="utf-8")

    assert git_working_tree_dirty(committed_repository) is True


def test_uncovered_documentation_change_does_not_mark_the_tree_dirty(committed_repository: Path):
    """Documentation cannot change behaviour, so it must not raise a false alarm."""

    (committed_repository / "docs" / "notes.md").write_text("edited\n", encoding="utf-8")

    assert git_working_tree_dirty(committed_repository) is False


def test_dirty_manifest_cannot_be_replayed_from_a_clean_tree(committed_repository: Path):
    """A clean-tree manifest and a dirty-tree runtime must not verify as equal."""

    configuration = {"cfg": 1}
    clean_versions = build_version_bundle(
        committed_repository, configuration=configuration, model_versions={}
    )
    manifest = build_replay_manifest(
        AppendOnlyTransactionLog(),
        versions=clean_versions,
        schema_version="1.0.0",
        random_seed=0,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    (committed_repository / "src" / "pkg" / "core.py").write_text("VALUE = 2\n", encoding="utf-8")
    dirty_versions = build_version_bundle(
        committed_repository, configuration=configuration, model_versions={}
    )

    with pytest.raises(RuntimeProvenanceError, match=r"code_version|source_tree_sha256"):
        verify_replay_provenance(
            manifest,
            runtime_versions=dirty_versions,
            repository_root=committed_repository,
            active_configuration=configuration,
        )


# --------------------------------------------------------------------------
# F-3  provenance must cover entry points and benchmark authority assets
# --------------------------------------------------------------------------


def test_source_tree_hash_covers_entry_point_scripts(committed_repository: Path):
    """Pre-fix attack: rewrite the CLI that produced the cited evidence."""

    before = source_tree_sha256(committed_repository)
    (committed_repository / "apps" / "entry.py").write_text("print('forged')\n", encoding="utf-8")

    assert source_tree_sha256(committed_repository) != before


def test_source_tree_hash_covers_checked_in_benchmark_assets(committed_repository: Path):
    """Pre-fix attack: swap the 'trusted benchmark authority' manifest."""

    before = source_tree_sha256(committed_repository)
    (committed_repository / "benchmarks" / "manifest.json").write_text(
        '{"a": 2}\n', encoding="utf-8"
    )

    assert source_tree_sha256(committed_repository) != before


def test_source_tree_hash_ignores_documentation(committed_repository: Path):
    before = source_tree_sha256(committed_repository)
    (committed_repository / "docs" / "notes.md").write_text("edited\n", encoding="utf-8")

    assert source_tree_sha256(committed_repository) == before


def test_real_repository_provenance_covers_apps_and_benchmarks():
    covered = {
        path.relative_to(REPOSITORY_ROOT).parts[0] for path in provenance_files(REPOSITORY_ROOT)
    }

    assert {"src", "apps", "benchmarks"} <= covered


def test_provenance_never_includes_bytecode_caches():
    assert all("__pycache__" not in path.parts for path in provenance_files(REPOSITORY_ROOT))


# --------------------------------------------------------------------------
# F-4  model_versions must not verify against itself
# --------------------------------------------------------------------------


def _manifest_for(repository: Path, models: dict[str, str]):
    configuration = {"cfg": 1}
    versions = build_version_bundle(repository, configuration=configuration, model_versions=models)
    manifest = build_replay_manifest(
        AppendOnlyTransactionLog(),
        versions=versions,
        schema_version="1.0.0",
        random_seed=0,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    return manifest, versions, configuration


def test_fabricated_model_versions_are_rejected_against_a_registry(committed_repository: Path):
    """Pre-fix attack: declare a model version that never ran, anywhere."""

    fabricated = {"detector": "grounding-dino@99.9-NEVER-EXISTED"}
    manifest, versions, configuration = _manifest_for(committed_repository, fabricated)

    with pytest.raises(RuntimeProvenanceError, match="trusted registry"):
        verify_replay_provenance(
            manifest,
            runtime_versions=versions,
            repository_root=committed_repository,
            active_configuration=configuration,
            model_version_registry={"detector": "grounding-dino@1.0"},
        )


def test_registry_requires_every_registered_model_to_be_declared(committed_repository: Path):
    manifest, versions, configuration = _manifest_for(committed_repository, {})

    with pytest.raises(RuntimeProvenanceError, match="omits registered model"):
        verify_replay_provenance(
            manifest,
            runtime_versions=versions,
            repository_root=committed_repository,
            active_configuration=configuration,
            model_version_registry={"detector": "grounding-dino@1.0"},
        )


def test_matching_registry_entries_verify(committed_repository: Path):
    declared = {"detector": "grounding-dino@1.0"}
    manifest, versions, configuration = _manifest_for(committed_repository, declared)

    verify_replay_provenance(
        manifest,
        runtime_versions=versions,
        repository_root=committed_repository,
        active_configuration=configuration,
        model_version_registry=dict(declared),
    )


def test_measured_fields_are_not_seeded_from_the_caller(committed_repository: Path):
    """The measured comparison must not borrow caller-supplied values."""

    manifest, versions, configuration = _manifest_for(committed_repository, {})
    forged = versions.model_copy(update={"source_tree_sha256": "0" * 64})

    with pytest.raises(RuntimeProvenanceError, match="source_tree_sha256"):
        verify_replay_provenance(
            manifest,
            runtime_versions=forged,
            repository_root=committed_repository,
            active_configuration=configuration,
        )


# --------------------------------------------------------------------------
# F-1  evaluation reports must be bound to the code that produced them
# --------------------------------------------------------------------------


def _report() -> EvaluationReport:
    plan = SyntheticRoutineGenerator().generate(build_routine_config())
    policy = build_policy()
    return EvaluationRunner().evaluate(
        build_manifest(plan, policy),
        run_benchmark_view(plan, policy),
        track=EvaluationTrack.CONTROLLED_NOISE,
    )


def test_evaluation_report_carries_measured_code_identity():
    report = _report()

    import cpswm.system.evaluation_operations.evaluator as evaluator_module

    assert report.provenance.source_tree_sha256 == source_tree_sha256(REPOSITORY_ROOT)
    assert report.provenance.evaluator_module_sha256 == file_sha256(evaluator_module.__file__)
    assert report.provenance.code_version


def test_evaluator_module_hash_tracks_the_evaluator_source():
    import cpswm.system.evaluation_operations.evaluator as evaluator_module

    measured = EvaluationProvenance.measure()

    assert measured.evaluator_module_sha256 == file_sha256(evaluator_module.__file__)


def test_altered_evaluator_cannot_reuse_a_released_run_identity():
    """Pre-fix attack: change the metric computation, keep 'f0-evaluator@0.9'."""

    report = _report()
    released = report.provenance
    altered = released.model_copy(update={"evaluator_module_sha256": "b" * 64})
    common = dict(
        manifest_id=report.benchmark_manifest_id,
        manifest_version=report.benchmark_manifest_version,
        manifest_sha256=report.benchmark_manifest_sha256,
        simulation_run_id=report.simulation_run_id,
        simulation_content_sha256=report.simulation_content_sha256,
        track=report.track,
        evaluator_version=report.evaluator_version,
    )

    assert evaluation_run_identity(
        **common, provenance_sha256=released.content_sha256
    ) != evaluation_run_identity(**common, provenance_sha256=altered.content_sha256)


def test_report_rejects_a_swapped_provenance_block():
    report = _report()
    forged = report.provenance.model_copy(update={"source_tree_sha256": "c" * 64})

    with pytest.raises(ValueError, match=r"evaluation_run_id|evaluation_report_sha256"):
        report.model_copy(update={"provenance": forged}).model_validate(
            report.model_copy(update={"provenance": forged}).model_dump(mode="python")
        )


def test_declared_provenance_must_match_the_running_code():
    plan = SyntheticRoutineGenerator().generate(build_routine_config())
    policy = build_policy()
    lying = EvaluationProvenance.measure().model_copy(
        update={"source_tree_sha256": "d" * 64, "working_tree_clean": True}
    )

    with pytest.raises(ValueError, match="declared evaluation provenance"):
        EvaluationRunner().evaluate(
            build_manifest(plan, policy),
            run_benchmark_view(plan, policy),
            track=EvaluationTrack.CONTROLLED_NOISE,
            provenance=lying,
        )


def test_report_records_working_tree_cleanliness_honestly():
    report = _report()

    assert report.provenance.working_tree_clean is (
        not report.provenance.code_version.endswith(DIRTY_WORKING_TREE_SUFFIX)
    )


# --------------------------------------------------------------------------
# Second-round findings: attacks against the fixes themselves
# --------------------------------------------------------------------------


def test_unknown_working_tree_state_is_never_reported_as_clean(tmp_path: Path):
    """Without Git the state is unknown; 'unknown' must not collapse to 'clean'."""

    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "src" / "pkg" / "core.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")

    measured = EvaluationProvenance.measure(tmp_path)

    assert measured.code_version == UNVERSIONED_CODE_VERSION
    assert measured.working_tree_clean is None


@pytest.mark.parametrize(
    ("code_version", "working_tree_clean"),
    [
        ("git:" + "0" * 40 + DIRTY_WORKING_TREE_SUFFIX, True),
        ("git:" + "0" * 40, False),
        (UNVERSIONED_CODE_VERSION, True),
        (UNVERSIONED_CODE_VERSION, False),
    ],
)
def test_provenance_rejects_a_working_tree_claim_that_contradicts_code_version(
    code_version: str, working_tree_clean: bool
):
    with pytest.raises(ValidationError, match=r"working_tree_clean|unversioned tree"):
        EvaluationProvenance(
            code_version=code_version,
            source_tree_sha256="a" * 64,
            evaluator_module_sha256="b" * 64,
            working_tree_clean=working_tree_clean,
        )


def test_a_self_consistent_report_cannot_authenticate_its_own_provenance():
    """Documented residual limitation: self-hashes prove consistency, not origin.

    A forger who recomputes every derived field produces a report that passes
    all internal validation.  Detecting that requires signatures, which are out
    of scope; ``verify_against`` is the reviewer-side check that closes the gap
    when a checkout is available.
    """

    report = _report()
    forged_provenance = EvaluationProvenance(
        code_version="git:" + "0" * 40,
        source_tree_sha256="a" * 64,
        evaluator_module_sha256="b" * 64,
        working_tree_clean=True,
    )
    run_id = evaluation_run_identity(
        manifest_id=report.benchmark_manifest_id,
        manifest_version=report.benchmark_manifest_version,
        manifest_sha256=report.benchmark_manifest_sha256,
        simulation_run_id=report.simulation_run_id,
        simulation_content_sha256=report.simulation_content_sha256,
        track=report.track,
        evaluator_version=report.evaluator_version,
        provenance_sha256=forged_provenance.content_sha256,
    )
    payload = report.model_dump(mode="python")
    payload["provenance"] = forged_provenance
    payload["evaluation_run_id"] = run_id
    payload["metrics"] = tuple(
        metric.model_copy(
            update={
                "evaluation_run_id": run_id,
                "metric_id": content_uuid(
                    "metric",
                    {"evaluation_run_id": run_id, "name": metric.metric_name},
                ),
            }
        )
        for metric in report.metrics
    )
    payload.pop("evaluation_report_sha256")
    probe = EvaluationReport.model_construct(**payload, evaluation_report_sha256="0" * 64)
    forged = EvaluationReport(
        **payload, evaluation_report_sha256=content_sha256(probe.content_payload())
    )

    # Internal validation cannot tell the difference ...
    assert forged.provenance.code_version == "git:" + "0" * 40

    # ... but the reviewer-side check against a real checkout can.
    with pytest.raises(ValueError, match="does not match the checked-out"):
        forged.provenance.verify_against()


def test_verify_against_accepts_a_genuine_report():
    _report().provenance.verify_against()
