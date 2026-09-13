from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "apps/evaluation_runner/generate_structure_two_engineering_trust_checkpoint.py"
SPEC = importlib.util.spec_from_file_location("structure_two_engineering_trust_checkpoint", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
AUDIT_SCRIPT = ROOT / "apps/evaluation_runner/run_structure_two_engineering_audit_receipt.py"
AUDIT_SPEC = importlib.util.spec_from_file_location(
    "structure_two_engineering_audit_receipt_tests", AUDIT_SCRIPT
)
assert AUDIT_SPEC is not None and AUDIT_SPEC.loader is not None
AUDIT_MODULE = importlib.util.module_from_spec(AUDIT_SPEC)
AUDIT_SPEC.loader.exec_module(AUDIT_MODULE)


def _stored() -> dict[str, object]:
    return json.loads(MODULE.OUTPUT.read_text(encoding="utf-8"))


def test_checkpoint_is_current_without_repeating_the_expensive_fresh_run() -> None:
    stored = _stored()
    MODULE.verify_checkpoint(stored, fresh_recomputation=False)
    assert stored["protocol"] == "structure-two-engineering-trust-checkpoint@1.1"
    assert stored["engineering_trust_gate_passed"] is True
    assert stored["recomputable_d0_evidence_allowed"] is True
    assert stored["seven_operator_ablation_authorized"] is False
    assert stored["external_confirmation"]["combined_status"] == "BLOCKED_FAIL_CLOSED"
    assert len(stored["task_results"]) == 4
    assert all(row["positive_output_trust_chain_complete"] for row in stored["task_results"])


def test_checkpoint_rejects_forged_but_fully_rehashed_positive_scope() -> None:
    stored = _stored()
    MODULE.verify_checkpoint(stored, fresh_recomputation=False)
    stored["seven_operator_ablation_authorized"] = True
    stored["positive_output_trust_chain"]["/seven_operator_ablation_authorized"] = (
        "checkpoint_content+source_bound_command_receipt+current_p0_manifest+"
        "current_source_inventory+current_test_contract+current_test_fixture_contract+"
        "current_toolchain_contract+fresh_local_execution_environment+"
        "critical_tool_module_bytes+"
        "task_artifact_positive_path_map+fresh_task_specific_recomputation+bound_reports"
    )
    unsigned = dict(stored)
    unsigned.pop("content_sha256")
    stored["content_sha256"] = MODULE._canonical_sha256(unsigned)
    with pytest.raises(ValueError, match="drift or forged"):
        MODULE.verify_checkpoint(stored, fresh_recomputation=False)


def test_audit_receipt_rejects_rehashed_success_with_a_failed_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt = json.loads((ROOT / MODULE.AUDIT_RECEIPT).read_text(encoding="utf-8"))
    p0 = json.loads((ROOT / MODULE.P0_MANIFEST).read_text(encoding="utf-8"))
    MODULE._verify_audit_receipt(p0)
    receipt["command_runs"][0]["exit_code"] = 1
    # The attacker retains the positive aggregate and repairs the unkeyed content hash.
    unsigned = dict(receipt)
    unsigned.pop("content_sha256")
    receipt["content_sha256"] = MODULE._canonical_sha256(unsigned)
    forged = tmp_path / "forged-engineering-audit-receipt.json"
    forged.write_text(json.dumps(receipt), encoding="utf-8")
    monkeypatch.setattr(MODULE, "AUDIT_RECEIPT", forged)
    with pytest.raises(ValueError, match="aggregate disagrees"):
        MODULE._verify_audit_receipt(p0)


def test_checkpoint_scope_contains_only_current_task_versions() -> None:
    assert _stored()["recomputable_d0_scope"] == [
        "task_7_v0_4",
        "task_8_v0_4",
        "task_10_g1_v0_1",
        "task_10_g2_v0_1",
    ]


def test_checkpoint_positive_chain_includes_test_toolchain_and_environment() -> None:
    stored = _stored()
    manifest = stored["p0_content_manifest"]
    assert manifest["required_scopes"] == [
        "code",
        "config",
        "data_schema",
        "split_manifest",
        "test_contract",
        "test_fixture_contract",
        "toolchain_contract",
    ]
    assert manifest["fixture_test_and_toolchain_contracts_verified"] is True
    assert stored["audit_execution_receipt"]["execution_environment_fresh_verified"] is True
    assert stored["current_local_recorded_audit_gate_passed"] is True
    assert stored["recorded_execution_authenticity_established"] is False
    assert stored["hermetic_toolchain_established"] is False
    assert all(
        "current_test_contract+current_test_fixture_contract+current_toolchain_contract+"
        "fresh_local_execution_environment" in chain
        for chain in stored["positive_output_trust_chain"].values()
    )


def test_local_environment_fingerprint_is_fresh_and_does_not_store_raw_env() -> None:
    p0 = json.loads((ROOT / MODULE.P0_MANIFEST).read_text(encoding="utf-8"))
    fingerprint = AUDIT_MODULE.build_execution_environment_fingerprint(p0)
    AUDIT_MODULE.verify_execution_environment_fingerprint(fingerprint, p0)
    assert fingerprint["python"]["resolved_interpreter"] == str(
        Path(sys.executable).resolve(strict=True)
    )
    assert fingerprint["python"]["interpreter_invocation_path"] == str(
        Path(sys.executable).resolve(strict=True)
    )
    assert fingerprint["python"]["interpreter_invocation_path_policy"] == "CANONICAL_RESOLVED_PATH"
    assert set(fingerprint["tools"]) == {"pytest", "mypy", "ruff", "git", "uv"}
    assert set(fingerprint["critical_python_modules"]) == {
        "pytest_public",
        "pytest_engine",
        "pytest_xdist",
        "mypy_entrypoint",
    }
    assert all(
        row["package_file_count"] > 0
        and len(row["module_file_sha256"]) == 64
        and len(row["package_content_sha256"]) == 64
        for row in fingerprint["critical_python_modules"].values()
    )
    assert fingerprint["installed_distributions"]["count"] > 0
    virtual_environment = fingerprint["sensitive_environment_allowlist"]["VIRTUAL_ENV"]
    assert virtual_environment["state"] == "effective"
    for row in fingerprint["sensitive_environment_allowlist"].values():
        assert set(row) in ({"state"}, {"state", "value_sha256"})
        assert "value" not in row


def test_effective_virtual_environment_is_alias_stable_but_target_sensitive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    p0 = json.loads((ROOT / MODULE.P0_MANIFEST).read_text(encoding="utf-8"))
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    inferred = AUDIT_MODULE.build_execution_environment_fingerprint(p0)
    monkeypatch.setenv("VIRTUAL_ENV", sys.prefix)
    explicit_same = AUDIT_MODULE.build_execution_environment_fingerprint(p0)
    monkeypatch.setenv("VIRTUAL_ENV", str(tmp_path / "different-environment"))
    explicit_different = AUDIT_MODULE.build_execution_environment_fingerprint(p0)

    assert inferred == explicit_same
    assert inferred["content_sha256"] != explicit_different["content_sha256"]


def test_audit_matrix_contains_frozen_offline_uv_environment_check() -> None:
    assert AUDIT_MODULE.COMMANDS["uv_frozen_offline_check"] == (
        "uv",
        "sync",
        "--frozen",
        "--offline",
        "--check",
        "--extra",
        "dev",
        "--no-cache",
    )
    for command_id in ("p0_adversarial_tests", "core_pytest"):
        assert "--confcutdir=." in AUDIT_MODULE.NATIVE_PYTEST_ARGUMENTS[command_id]
        assert AUDIT_MODULE.COMMANDS[command_id] == (
            ".venv/bin/python",
            "tools/structure_two_unified_acceptance.py",
            "--native-audit-command",
            command_id,
        )
        binding = AUDIT_MODULE.command_environment_binding(command_id)
        assert set(binding) == {
            "PYTEST_ADDOPTS",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
            "PYTEST_PLUGINS",
            "PYTHONHASHSEED",
            "PYTHONPATH",
        }
    # Freeze the complete command, including explicit plugin loading and the
    # reporting override; a positional slice missed the rest of this contract.
    assert AUDIT_MODULE.NATIVE_PYTEST_ARGUMENTS["core_pytest"] == (
        "-o",
        "addopts=",
        "-p",
        "xdist.plugin",
        "-n",
        "auto",
        "--dist=worksteal",
        "-q",
        "--confcutdir=.",
        "--ignore=tests/test_structure_two_engineering_trust_checkpoint.py",
    )


def test_receipt_rows_bind_manifest_cwd_executable_and_controlled_pytest_env() -> None:
    receipt = json.loads((ROOT / MODULE.AUDIT_RECEIPT).read_text(encoding="utf-8"))
    p0 = json.loads((ROOT / MODULE.P0_MANIFEST).read_text(encoding="utf-8"))
    MODULE._verify_audit_receipt(p0)
    assert receipt["recorded_execution_authenticity_established"] is False
    assert receipt["hermetic_toolchain_established"] is False
    for row in receipt["command_runs"]:
        expected_identity = AUDIT_MODULE.command_executable_identity(
            AUDIT_MODULE.COMMANDS[row["command_id"]]
        )
        assert row["source_manifest_sha256"] == p0["manifest_sha256"]
        assert row["cwd"] == str(ROOT.resolve())
        assert row["resolved_executable"] == expected_identity["resolved_executable"]
        assert row["executable_sha256"] == expected_identity["executable_sha256"]
        assert row["environment_overrides"] == AUDIT_MODULE.command_environment_binding(
            row["command_id"]
        )


def test_rehashed_environment_fingerprint_substitution_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt = json.loads((ROOT / MODULE.AUDIT_RECEIPT).read_text(encoding="utf-8"))
    p0 = json.loads((ROOT / MODULE.P0_MANIFEST).read_text(encoding="utf-8"))
    MODULE._verify_audit_receipt(p0)
    for key in ("pre_execution_environment", "post_execution_environment"):
        receipt[key]["python"]["platform"] = "forged-platform"
        unsigned_environment = dict(receipt[key])
        unsigned_environment.pop("content_sha256")
        receipt[key]["content_sha256"] = MODULE._canonical_sha256(unsigned_environment)
    forged_environment_hash = receipt["pre_execution_environment"]["content_sha256"]
    for row in receipt["command_runs"]:
        row["execution_environment_sha256"] = forged_environment_hash
    unsigned_receipt = dict(receipt)
    unsigned_receipt.pop("content_sha256")
    receipt["content_sha256"] = MODULE._canonical_sha256(unsigned_receipt)
    forged = tmp_path / "forged-environment-receipt.json"
    forged.write_text(json.dumps(receipt), encoding="utf-8")
    monkeypatch.setattr(MODULE, "AUDIT_RECEIPT", forged)
    with pytest.raises(ValueError, match="fingerprint is stale"):
        MODULE._verify_audit_receipt(p0)


def test_rehashed_executable_replacement_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt = json.loads((ROOT / MODULE.AUDIT_RECEIPT).read_text(encoding="utf-8"))
    p0 = json.loads((ROOT / MODULE.P0_MANIFEST).read_text(encoding="utf-8"))
    MODULE._verify_audit_receipt(p0)
    replacement = tmp_path / "pytest-replacement"
    replacement.write_bytes(b"not the audited pytest executable\n")
    run = receipt["command_runs"][0]
    run["resolved_executable"] = str(replacement)
    run["executable_sha256"] = hashlib.sha256(replacement.read_bytes()).hexdigest()
    unsigned = dict(receipt)
    unsigned.pop("content_sha256")
    receipt["content_sha256"] = MODULE._canonical_sha256(unsigned)
    forged = tmp_path / "forged-executable-receipt.json"
    forged.write_text(json.dumps(receipt), encoding="utf-8")
    monkeypatch.setattr(MODULE, "AUDIT_RECEIPT", forged)
    with pytest.raises(ValueError, match="command binding mismatch"):
        MODULE._verify_audit_receipt(p0)


def _resign_manifest_after_test_change(manifest: dict[str, object]) -> None:
    scope = manifest["scopes"]["test_contract"]
    scope["files"][0]["sha256"] = hashlib.sha256(b"changed test bytes").hexdigest()
    aggregate = hashlib.sha256()
    for entry in scope["files"]:
        aggregate.update(entry["path"].encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(entry["sha256"].encode("ascii"))
        aggregate.update(b"\n")
    scope["content_sha256"] = aggregate.hexdigest()
    unsigned = dict(manifest)
    unsigned.pop("manifest_sha256")
    manifest["manifest_sha256"] = MODULE._canonical_sha256(unsigned)


def test_test_and_manifest_resign_rejects_old_receipt_and_old_checkpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_checkpoint = _stored()
    MODULE.verify_checkpoint(old_checkpoint, fresh_recomputation=False)
    result_rows, current_manifest = MODULE._verify_inputs(fresh_recomputation=False)
    resigned_manifest = json.loads(json.dumps(current_manifest))
    _resign_manifest_after_test_change(resigned_manifest)
    manifest_path = tmp_path / "content_manifest_v0_3.json"
    manifest_path.write_text(json.dumps(resigned_manifest), encoding="utf-8")
    monkeypatch.setattr(MODULE, "P0_MANIFEST", manifest_path)

    with pytest.raises(ValueError, match="stale for the current source manifest"):
        MODULE._verify_audit_receipt(resigned_manifest)

    resigned_receipt = json.loads(
        (
            ROOT / "benchmarks/structure_two/engineering_trust_checkpoint_2026_09_12_v0_3/"
            "engineering_audit_receipt.json"
        ).read_text(encoding="utf-8")
    )
    manifest_file_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    manifest_hash = resigned_manifest["manifest_sha256"]
    resigned_receipt["source_manifest_path"] = manifest_path.as_posix()
    for field in (
        "source_manifest_sha256",
        "pre_execution_source_manifest_sha256",
        "post_execution_source_manifest_sha256",
    ):
        resigned_receipt[field] = manifest_hash
    for field in (
        "source_manifest_file_sha256",
        "pre_execution_source_manifest_file_sha256",
        "post_execution_source_manifest_file_sha256",
    ):
        resigned_receipt[field] = manifest_file_hash
    for row in resigned_receipt["command_runs"]:
        row["source_manifest_sha256"] = manifest_hash
        row["source_manifest_file_sha256"] = manifest_file_hash
    unsigned_receipt = dict(resigned_receipt)
    unsigned_receipt.pop("content_sha256")
    resigned_receipt["content_sha256"] = MODULE._canonical_sha256(unsigned_receipt)
    receipt_path = tmp_path / "engineering_audit_receipt.json"
    receipt_path.write_text(json.dumps(resigned_receipt), encoding="utf-8")
    monkeypatch.setattr(MODULE, "AUDIT_RECEIPT", receipt_path)
    monkeypatch.setattr(
        MODULE,
        "_verify_inputs",
        lambda *, fresh_recomputation: (result_rows, resigned_manifest),
    )
    with pytest.raises(ValueError, match="drift or forged"):
        MODULE.verify_checkpoint(old_checkpoint, fresh_recomputation=False)


def test_checkpoint_cannot_be_generated_with_fresh_recomputation_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--no-fresh-recomputation"])
    with pytest.raises(ValueError, match="generation always requires"):
        MODULE.main()


def test_checkpoint_binds_all_current_p5_replays_without_promoting_history() -> None:
    stored = _stored()
    rows = stored["p5_current_evidence"]
    assert {row["experiment"] for row in rows} == {
        "three_arm_death_test",
        "readout_posthoc_diagnostic",
        "debt_replay_confirmation",
        "readout_prior_factorial",
        "unseen_d0_holdout",
    }
    assert stored["integration_requires_new_checkpoint"] is True
    for row in rows:
        assert row["verification_command_id"] == "p5_evidence_current"
        assert row["evidence_context"]["lifecycle"] == "POST_OPEN_CURRENT_SOURCE_REPLAY"
        assert row["evidence_context"]["first_execution_established"] is False
        assert row["evidence_context"]["previously_unseen_established"] is False
        assert row["evidence_context"]["confirmatory"] is False
        assert len(row["file_sha256"]) == len(row["content_sha256"]) == 64
    assert AUDIT_MODULE.COMMANDS["p5_evidence_current"] == (
        ".venv/bin/python",
        "apps/evaluation_runner/run_structure_two_evidence_repair.py",
        "--verify-current",
    )


def test_audit_preserves_venv_invocation_while_hashing_resolved_python() -> None:
    import subprocess

    identity = AUDIT_MODULE.command_executable_identity((".venv/bin/python",))
    assert identity["invocation_executable"] == str(ROOT / ".venv/bin/python")
    assert Path(identity["resolved_executable"]) == (ROOT / ".venv/bin/python").resolve()
    completed = subprocess.run(
        [
            identity["invocation_executable"],
            "-c",
            "import sys,cpswm; print(sys.prefix)",
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert Path(completed.stdout.strip()) == ROOT / ".venv"
    assert all(argv[-1] == "--version" for argv in AUDIT_MODULE.TOOL_VERSION_COMMANDS.values())
