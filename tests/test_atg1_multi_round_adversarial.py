"""Independent multi-round adversarial verification of the committed ATG-1."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from cpswm.system.evaluation_operations.project_one_ablation_v0_2 import (
    ProjectOneProtocolPilotManifestV2,
    ProjectOneProtocolPilotReportV2,
)
from cpswm.system.evaluation_operations.report_output import (
    ProtectedReportOutputError,
    write_report_atomic,
)
from cpswm.system.reproducibility import content_sha256

REPO = Path(__file__).resolve().parents[1]
FIXTURE = (
    REPO / "benchmarks/project_one_ablation/project_one_protocol_pilot_report_v0.2.fixture.json"
)


def _report() -> ProjectOneProtocolPilotReportV2:
    return ProjectOneProtocolPilotReportV2.model_validate_json(FIXTURE.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("comparison_id", "shift-cause-factorization"),
        ("comparison_manifest_sha256", "0" * 64),
        ("manifest_arm_sha256", "1" * 64),
        ("declared_model_version", "forged@9"),
        ("method_semantics", ["forged semantics"]),
        ("topology_binding_sha256", "2" * 64),
    ],
)
def test_round_1_each_per_arm_binding_dimension_is_fail_closed(field, value):
    payload = _report().model_dump(mode="json")
    payload["arm_results"][0][field] = value
    with pytest.raises(ValidationError):
        ProjectOneProtocolPilotReportV2.model_validate(payload)


@pytest.mark.parametrize("mutation", ["split_id", "count_redistribution"])
def test_round_2_recomputed_outer_hash_cannot_hide_stale_artifact_hash(mutation):
    payload = _report().model_dump(mode="json")
    manifest = payload["manifest"]
    if mutation == "split_id":
        manifest["split_experiment_id"] = "forged-split"
    else:
        manifest["train_case_count"] -= 1
        manifest["test_case_count"] += 1
        payload["train_case_count"] -= 1
        payload["test_case_count"] += 1
    payload["manifest_sha256"] = content_sha256(manifest)
    with pytest.raises(ValidationError, match="artifact hash"):
        ProjectOneProtocolPilotReportV2.model_validate(payload)


def test_round_3_model_copy_bypass_is_rejected_after_wire_round_trip():
    report = _report()
    invalid_result = report.arm_results[0].model_copy(
        update={"declared_model_version": "forged-via-model-copy@9"}
    )
    bypassed = report.model_copy(update={"arm_results": (invalid_result, *report.arm_results[1:])})
    with pytest.raises(ValidationError):
        ProjectOneProtocolPilotReportV2.model_validate(bypassed.model_dump(mode="json"))


def test_round_3_duplicate_tuning_id_fails_even_after_nested_rebinding():
    report = _report()
    manifest = deepcopy(report.manifest.model_dump(mode="json"))
    duplicate = manifest["comparisons"][0]["manifest"]["arms"][0]["independent_tuning_run_id"]
    manifest["comparisons"][4]["manifest"]["arms"][0]["independent_tuning_run_id"] = duplicate
    with pytest.raises(ValidationError, match="globally unique"):
        ProjectOneProtocolPilotManifestV2.model_validate(manifest)


def test_round_4_force_cannot_follow_output_symlink_into_source(tmp_path):
    protected = REPO / "pyproject.toml"
    before = protected.read_bytes()
    output_link = tmp_path / "report.json"
    output_link.symlink_to(protected)
    with pytest.raises(ProtectedReportOutputError):
        write_report_atomic(
            "{}\n",
            output_path=output_link,
            config_path=FIXTURE,
            repository_root=REPO,
            force=True,
        )
    assert protected.read_bytes() == before
