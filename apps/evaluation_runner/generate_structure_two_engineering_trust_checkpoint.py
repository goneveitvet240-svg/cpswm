#!/usr/bin/env python3
"""Build and verify the final Structure-Two engineering trust checkpoint."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json

# Establish execution provenance before importing project dependencies.
import sys
import types
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any, Final

_bootstrap_path = (
    Path(__file__).resolve().parents[2] / "apps/evaluation_runner/structure_two_source_bootstrap.py"
)
if "_cpswm_source_bootstrap" not in sys.modules:
    _bootstrap = types.ModuleType("_cpswm_source_bootstrap")
    _bootstrap.__file__ = str(_bootstrap_path)
    sys.modules[_bootstrap.__name__] = _bootstrap
    exec(compile(_bootstrap_path.read_bytes(), str(_bootstrap_path), "exec"), _bootstrap.__dict__)
sys.modules["_cpswm_source_bootstrap"].establish(Path(__file__).resolve().parents[2])

ROOT: Final = Path(__file__).resolve().parents[2]
OUTPUT: Final = (
    ROOT / "benchmarks/structure_two/engineering_trust_checkpoint_2026_09_12_v0_3/"
    "engineering_checkpoint.json"
)
P0_MANIFEST: Final = Path("benchmarks/p0_checkpoint/content_manifest_v0_3.json")
AUDIT_RECEIPT: Final = Path(
    "benchmarks/structure_two/engineering_trust_checkpoint_2026_09_12_v0_3/"
    "engineering_audit_receipt.json"
)
AUDIT_LOG_DIRECTORY: Final = AUDIT_RECEIPT.parent / "engineering_audit_logs"
V05_AUDIT: Final = Path(
    "benchmarks/structure_two/structure_two_world_source_bundle_v0_5_compatibility_audit.json"
)
READINESS: Final = Path("benchmarks/structure_two/structure_two_v0_6_development_readiness.json")
RESULTS: Final = (
    (
        "task_7_v0_4",
        Path(
            "benchmarks/structure_two/backbone_b_repairs_2026_09_04/"
            "task_7_windowed_rejuvenation_v0_4.json"
        ),
        "b",
    ),
    (
        "task_8_v0_4",
        Path(
            "benchmarks/structure_two/backbone_b_repairs_2026_09_04/"
            "task_8_matched_three_arm_confirmatory_v0_4.json"
        ),
        "b",
    ),
    (
        "task_10_g1_v0_1",
        Path(
            "benchmarks/structure_two/engineering_trust_checkpoint_2026_09_05/"
            "task_10_budget_sweep_g1.json"
        ),
        "d0",
    ),
    (
        "task_10_g2_v0_1",
        Path(
            "benchmarks/structure_two/engineering_trust_checkpoint_2026_09_05/"
            "task_10_budget_sweep_g2.json"
        ),
        "d0",
    ),
)
BOUND_REPORTS: Final = (
    Path("docs/reviews/structure_two_evidence_entry_portability_window1_2026-09-12.md"),
    Path("docs/reviews/structure_two_evidence_repair_window1_supplement_2026-09-11.md"),
    Path("docs/reviews/structure_two_evidence_repair_window1_2026-09-11.md"),
    Path("docs/结构二/方向结构二_当前证据总表_2026-09-02.md"),
    Path("docs/experiments/structure_two_task7_windowed_rejuvenation_result_v0_4_2026-09-05.md"),
    Path(
        "docs/experiments/structure_two_task8_matched_three_arm_confirmatory_result_v0_4_2026-09-05.md"
    ),
    Path("docs/experiments/structure_two_task10_particle_budget_result_2026-09-05.md"),
    Path("docs/reviews/结构二_B_vNext第一轮科学反例与正向输出审计_2026-09-05.md"),
    Path("docs/reviews/结构二_B_vNext第二轮协议完整性证伪审计_2026-09-05.md"),
    Path("docs/结构二/方向结构二_Gate_B_v0.8_raw正式执行链协议_v1.0.md"),
    Path("docs/结构二/方向结构二_五项未决绑定解析与唯一授权DAG协议_v1.1.md"),
    Path("docs/reviews/structure_two_external_confirmation_gate_d_closure_2026-09-05.md"),
)


def _load(name: str, relative_path: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load checkpoint dependency: {relative_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["_cpswm_source_bootstrap"].guard.execute_application(module, ROOT / relative_path)
    return module


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _positive_boolean_paths(value: object, prefix: str = "") -> list[str]:
    paths: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            escaped = str(key).replace("~", "~0").replace("/", "~1")
            paths.extend(_positive_boolean_paths(item, f"{prefix}/{escaped}"))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            paths.extend(_positive_boolean_paths(item, f"{prefix}/{index}"))
    elif value is True:
        paths.append(prefix or "/")
    return paths


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"checkpoint input is not a JSON object: {path}")
    return payload


def _verify_audit_receipt(p0_manifest: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, bool]]:
    audit_runner = _load(
        "structure_two_engineering_audit_runner",
        "apps/evaluation_runner/run_structure_two_engineering_audit_receipt.py",
    )
    receipt = _load_json(ROOT / AUDIT_RECEIPT)
    unsigned = dict(receipt)
    stored_hash = unsigned.pop("content_sha256", None)
    if stored_hash != _canonical_sha256(unsigned):
        raise ValueError("engineering audit receipt content hash mismatch")
    if (
        receipt.get("protocol") != "structure-two-engineering-audit-receipt@1.1"
        or receipt.get("authority") != "CURRENT_LOCAL_TOOLCHAIN_STATE_ONLY"
    ):
        raise ValueError("engineering audit receipt protocol/authority mismatch")
    if any(
        receipt.get(field) is not False
        for field in (
            "recorded_execution_authenticity_established",
            "hermetic_toolchain_established",
            "independent_custody_established",
        )
    ):
        raise ValueError("engineering audit receipt overclaims its local recorded authority")
    manifest_file_hash = _sha256(ROOT / P0_MANIFEST)
    manifest_hash = p0_manifest.get("manifest_sha256")
    if not isinstance(manifest_hash, str):
        raise ValueError("current P0 manifest hash is missing")
    manifest_binding_fields = {
        "source_manifest_file_sha256": manifest_file_hash,
        "source_manifest_sha256": manifest_hash,
        "pre_execution_source_manifest_file_sha256": manifest_file_hash,
        "pre_execution_source_manifest_sha256": manifest_hash,
        "post_execution_source_manifest_file_sha256": manifest_file_hash,
        "post_execution_source_manifest_sha256": manifest_hash,
    }
    if receipt.get("source_manifest_path") != P0_MANIFEST.as_posix() or any(
        receipt.get(field) != value for field, value in manifest_binding_fields.items()
    ):
        raise ValueError("engineering audit receipt is stale for the current source manifest")
    environment_pre = receipt.get("pre_execution_environment")
    environment_post = receipt.get("post_execution_environment")
    if not isinstance(environment_pre, Mapping) or not isinstance(environment_post, Mapping):
        raise ValueError("engineering audit execution environment fingerprint is missing")
    if environment_pre != environment_post:
        raise ValueError("engineering audit pre/post execution environments disagree")
    audit_runner.verify_execution_environment_fingerprint(
        environment_pre,
        p0_manifest,
        repository_root=ROOT,
    )
    environment_hash = environment_pre.get("content_sha256")
    if not isinstance(environment_hash, str):
        raise ValueError("engineering audit execution environment hash is missing")
    raw_runs = receipt.get("command_runs")
    if not isinstance(raw_runs, list):
        raise ValueError("engineering audit receipt command runs missing")
    runs: dict[str, bool] = {}
    seen: set[str] = set()
    for raw in raw_runs:
        if not isinstance(raw, Mapping):
            raise ValueError("engineering audit command run malformed")
        command_id = raw.get("command_id")
        if not isinstance(command_id, str) or command_id in seen:
            raise ValueError("engineering audit command id missing or duplicated")
        seen.add(command_id)
        expected = audit_runner.COMMANDS.get(command_id)
        if expected is None or raw.get("argv") != list(expected):
            raise ValueError(f"engineering audit command substitution: {command_id}")
        expected_executable = audit_runner.command_executable_identity(
            expected, repository_root=ROOT
        )
        if (
            raw.get("source_manifest_sha256") != manifest_hash
            or raw.get("source_manifest_file_sha256") != manifest_file_hash
            or raw.get("execution_environment_sha256") != environment_hash
            or raw.get("environment_overrides")
            != audit_runner.command_environment_binding(command_id)
            or raw.get("cwd") != str(ROOT.resolve())
            or raw.get("invocation_executable") != expected_executable["invocation_executable"]
            or raw.get("resolved_executable") != expected_executable["resolved_executable"]
            or raw.get("executable_sha256") != expected_executable["executable_sha256"]
        ):
            raise ValueError(f"engineering audit command binding mismatch: {command_id}")
        try:
            started = datetime.fromisoformat(str(raw["start_timestamp"]))
            ended = datetime.fromisoformat(str(raw["end_timestamp"]))
        except (KeyError, ValueError) as error:
            raise ValueError("engineering audit timestamp malformed") from error
        if started.tzinfo is None or ended.tzinfo is None or started > ended:
            raise ValueError("engineering audit timestamp ordering invalid")
        for stream in ("stdout", "stderr"):
            relative = raw.get(f"{stream}_path")
            if not isinstance(relative, str):
                raise ValueError(f"engineering audit {stream} path missing")
            expected_relative = (AUDIT_LOG_DIRECTORY / f"{command_id}.{stream}.log").as_posix()
            if relative != expected_relative:
                raise ValueError(f"engineering audit {stream} path substitution")
            unresolved_path = ROOT / relative
            path = unresolved_path.resolve()
            if unresolved_path.is_symlink() or not path.is_relative_to(ROOT) or not path.is_file():
                raise ValueError(f"engineering audit {stream} artifact invalid")
            if raw.get(f"{stream}_sha256") != _sha256(path):
                raise ValueError(f"engineering audit {stream} hash mismatch")
        exit_code = raw.get("exit_code")
        if isinstance(exit_code, bool) or not isinstance(exit_code, int):
            raise ValueError(f"engineering audit exit code malformed: {command_id}")
        runs[command_id] = exit_code == 0
    if seen != set(audit_runner.COMMANDS):
        raise ValueError("engineering audit command coverage incomplete")
    all_passed = all(runs.values())
    if receipt.get("all_commands_passed") is not all_passed:
        raise ValueError("engineering audit aggregate disagrees with command exits")
    return receipt, runs


def _verify_inputs(*, fresh_recomputation: bool) -> tuple[list[dict[str, object]], dict[str, Any]]:
    b_runner = _load(
        "structure_two_b_checkpoint_runner",
        "apps/evaluation_runner/run_structure_two_backbone_b_repairs.py",
    )
    d0_runner = _load(
        "structure_two_d0_checkpoint_runner",
        "apps/evaluation_runner/run_structure_two_d0_evidence_checkpoint.py",
    )
    rows: list[dict[str, object]] = []
    for result_id, relative, verifier in RESULTS:
        payload = _load_json(ROOT / relative)
        if verifier == "b":
            b_runner.verify_artifact(payload, recompute=fresh_recomputation)
        else:
            command = payload.get("runner_argv")
            if not isinstance(command, list) or not all(isinstance(item, str) for item in command):
                raise ValueError("Task-10 runner argv binding is malformed")
            stored_result = payload.get("result")
            fresh = (
                d0_runner._fresh_result_for_command(command)
                if fresh_recomputation
                else stored_result
            )
            d0_runner.verify_envelope(payload, fresh_result=fresh)
        result = payload.get("result")
        if not isinstance(result, Mapping):
            raise ValueError(f"result missing from {relative}")
        positive_chain = payload.get("positive_output_trust_chain")
        if not isinstance(positive_chain, Mapping):
            raise ValueError(f"positive-output trust chain missing from {relative}")
        rows.append(
            {
                "result_id": result_id,
                "path": relative.as_posix(),
                "file_sha256": _sha256(ROOT / relative),
                "content_sha256": payload["content_sha256"],
                "positive_output_count": len(positive_chain),
                "positive_output_trust_chain_complete": True,
                "fresh_task_specific_recomputation_verified": True,
                "task_gate_passed": bool(
                    result.get("task_7_passed", result.get("task_8_passed", False))
                ),
                "definition_and_rerun_complete": bool(
                    result.get(
                        "task_7_definition_and_rerun_complete",
                        result.get(
                            "task_8_definition_and_rerun_complete",
                            result.get("task_10_definition_and_rerun_complete", False),
                        ),
                    )
                ),
                "formal_authorization": False,
            }
        )

    p0_module = _load(
        "structure_two_p0_manifest_generator",
        "apps/evaluation_runner/generate_p0_checkpoint_manifest.py",
    )
    stored_p0 = _load_json(ROOT / P0_MANIFEST)
    if stored_p0 != p0_module.build_manifest():
        raise ValueError("P0 content manifest is not current")
    p0_module.verify_manifest_snapshot(stored_p0)
    scopes = stored_p0.get("scopes")
    if (
        stored_p0.get("schema_version") != "p0-checkpoint-content-manifest@0.3"
        or not isinstance(scopes, Mapping)
        or set(scopes) != set(p0_module.REQUIRED_SCOPE_NAMES)
        or stored_p0.get("scope_contract") != p0_module.build_manifest_scope_contract()
    ):
        raise ValueError("P0 v0.3 fixture/test/toolchain scope contract is incomplete")
    for scope_name in ("test_contract", "test_fixture_contract", "toolchain_contract"):
        scope = scopes.get(scope_name)
        if not isinstance(scope, Mapping) or not isinstance(scope.get("file_count"), int):
            raise ValueError(f"P0 required scope is malformed: {scope_name}")
        if scope["file_count"] <= 0:
            raise ValueError(f"P0 required scope is empty: {scope_name}")
    return rows, stored_p0


def build_checkpoint(*, fresh_recomputation: bool = True) -> dict[str, object]:
    result_rows, p0_manifest = _verify_inputs(fresh_recomputation=fresh_recomputation)
    audit_receipt, audit_runs = _verify_audit_receipt(p0_manifest)
    v05_audit = _load_json(ROOT / V05_AUDIT)
    readiness = _load_json(ROOT / READINESS)
    if v05_audit.get("current_worktree_compatible_with_frozen_v0_5") is not False:
        raise ValueError("historical v0.5 source bundle must remain explicitly incompatible")
    if readiness.get("current_gate_b_protocol_id") != (
        "structure-two-comparator-typed-dual-gate-b@0.8"
    ):
        raise ValueError("readiness does not name current Gate-B v0.8")
    if readiness.get("current_gate_b_protocol_status") != "FROZEN_NOT_EXECUTED":
        raise ValueError("readiness current Gate-B status drift")
    if readiness.get("current_v0_8_formal_gate_b_receipt_verified") is not False:
        raise ValueError("readiness cannot claim an unexecuted Gate-B receipt")
    p5_runner = _load(
        "structure_two_evidence_repair_runner",
        "apps/evaluation_runner/run_structure_two_evidence_repair.py",
    )
    p5_inventory = p5_runner.current_evidence_inventory()
    reports = [{"path": path.as_posix(), "sha256": _sha256(ROOT / path)} for path in BOUND_REPORTS]
    required_manifest_scopes = {
        "code",
        "config",
        "data_schema",
        "split_manifest",
        "test_contract",
        "test_fixture_contract",
        "toolchain_contract",
    }
    manifest_scopes = p0_manifest["scopes"]
    fixture_test_and_toolchain_contracts_passed = (
        isinstance(manifest_scopes, Mapping)
        and set(manifest_scopes) == required_manifest_scopes
        and all(
            isinstance(manifest_scopes[name], Mapping)
            and int(manifest_scopes[name]["file_count"]) > 0
            for name in ("test_contract", "test_fixture_contract", "toolchain_contract")
        )
    )
    receipt_environment = audit_receipt["pre_execution_environment"]
    environment_fresh_verified = isinstance(receipt_environment, Mapping) and isinstance(
        receipt_environment.get("content_sha256"), str
    )
    engineering_passed = (
        all(audit_runs.values())
        and fixture_test_and_toolchain_contracts_passed
        and environment_fresh_verified
    )
    p0_adversarial_passed = audit_runs["p0_adversarial_tests"]
    payload: dict[str, object] = {
        "protocol": "structure-two-engineering-trust-checkpoint@1.1",
        "freeze_date": "2026-09-11",
        "p5_current_evidence": p5_inventory,
        "integration_requires_new_checkpoint": True,
        "authority": "CURRENT_LOCAL_TOOLCHAIN_STATE_ONLY",
        "engineering_trust_gate_definition": "CURRENT_LOCAL_RECORDED_AUDIT_ONLY",
        "current_local_recorded_audit_gate_passed": engineering_passed,
        "engineering_trust_gate_passed": engineering_passed,
        "recomputable_d0_evidence_allowed": engineering_passed,
        "recomputable_d0_scope": [row["result_id"] for row in result_rows],
        "p0_repairs": {
            "forged_complete_positive_path_closed": p0_adversarial_passed,
            "authorization_schema_config_custody_drift_closed": p0_adversarial_passed,
            "manifest_and_current_source_inventory_drift_closed": p0_adversarial_passed,
            "formal_runtime_engine_and_trace_digest_frozen": p0_adversarial_passed,
            "registry_identity_replacement_and_clone_closed": p0_adversarial_passed,
            "final_authorization_binds_policy_and_root_signature": p0_adversarial_passed,
            "caller_backdated_freshness_closed": p0_adversarial_passed,
            "test_contract_inventory_and_symlink_policy_verified": (
                fixture_test_and_toolchain_contracts_passed
            ),
            "benchmark_test_fixture_inventory_and_symlink_policy_verified": (
                fixture_test_and_toolchain_contracts_passed
            ),
            "toolchain_contract_inventory_verified": (fixture_test_and_toolchain_contracts_passed),
            "pre_post_manifest_identity_verified": True,
            "fresh_local_execution_environment_verified": environment_fresh_verified,
        },
        "audit_execution_receipt": {
            "path": AUDIT_RECEIPT.as_posix(),
            "file_sha256": _sha256(ROOT / AUDIT_RECEIPT),
            "content_sha256": audit_receipt["content_sha256"],
            "source_manifest_sha256": audit_receipt["source_manifest_sha256"],
            "pre_execution_source_manifest_sha256": audit_receipt[
                "pre_execution_source_manifest_sha256"
            ],
            "post_execution_source_manifest_sha256": audit_receipt[
                "post_execution_source_manifest_sha256"
            ],
            "execution_environment_sha256": receipt_environment["content_sha256"],
            "execution_environment_fresh_verified": environment_fresh_verified,
            "recorded_execution_authenticity_established": False,
            "hermetic_toolchain_established": False,
            "command_passes": audit_runs,
            "all_commands_passed": engineering_passed,
        },
        "task_results": result_rows,
        "p0_content_manifest": {
            "path": P0_MANIFEST.as_posix(),
            "file_sha256": _sha256(ROOT / P0_MANIFEST),
            "manifest_sha256": p0_manifest["manifest_sha256"],
            "required_scopes": sorted(required_manifest_scopes),
            "test_contract_sha256": manifest_scopes["test_contract"]["content_sha256"],
            "test_fixture_contract_sha256": manifest_scopes["test_fixture_contract"][
                "content_sha256"
            ],
            "toolchain_contract_sha256": manifest_scopes["toolchain_contract"]["content_sha256"],
            "fixture_test_and_toolchain_contracts_verified": (
                fixture_test_and_toolchain_contracts_passed
            ),
            "current_and_self_consistent": True,
        },
        "historical_v0_5_source_bundle_audit": {
            "path": V05_AUDIT.as_posix(),
            "file_sha256": _sha256(ROOT / V05_AUDIT),
            "current_file_count": v05_audit["current_file_count"],
            "current_source_bundle_sha256": v05_audit["current_source_bundle_sha256"],
            "historical_bundle_compatible_with_current_tree": False,
            "historical_evidence_rewritten": False,
        },
        "aligned_reports": reports,
        "external_confirmation": {
            "native_reproductions": 0,
            "component_cores": 6,
            "gate_a_status": "BLOCKED_BEFORE_EXECUTION",
            "gate_b_protocol": "structure-two-comparator-typed-dual-gate-b@0.8",
            "gate_b_status": "FROZEN_NOT_EXECUTED/NOT_RUN",
            "raw_formal_execution_chain_status": "REGISTERED_NOT_EXECUTED/NOT_ENROLLED",
            "combined_status": "BLOCKED_FAIL_CLOSED",
            "efficacy_interpretation_allowed": False,
        },
        "seven_operator_ablation_authorized": False,
        "external_validity_established": False,
        "recorded_execution_authenticity_established": False,
        "hermetic_toolchain_established": False,
        "independent_custody_established": False,
        "claim_boundary": (
            "Only after the local command receipt is freshly matched to the current code, config, "
            "data/schema, split-manifest, test source, benchmark test-fixture, toolchain, "
            "interpreter, executable, installed-distribution, and allowlisted-environment state "
            "may the "
            "bound Task 7 v0.4, Task 8 v0.4, and Task 10 D0 results be "
            "called recomputable D0 evidence. Task 7 and Task 8 both retain FAIL. "
            "The true gate means only that a current-local recorded audit is internally "
            "consistent; "
            "unkeyed caller-held records do not establish execution authenticity. This is not a "
            "hermetic build or independently held custody. "
            "The checkpoint does not establish external validity, formal Task-10 resolution, "
            "Gate-B execution, seven-operator efficacy, or external method superiority."
        ),
    }
    payload["positive_output_trust_chain"] = {
        path: (
            "checkpoint_content+source_bound_command_receipt+current_p0_manifest+"
            "current_source_inventory+current_test_contract+current_test_fixture_contract+"
            "current_toolchain_contract+fresh_local_execution_environment+"
            "critical_tool_module_bytes+"
            "task_artifact_positive_path_map+fresh_task_specific_recomputation+bound_reports"
        )
        for path in _positive_boolean_paths(payload)
    }
    payload["content_sha256"] = _canonical_sha256(payload)
    return payload


def verify_checkpoint(payload: Mapping[str, object], *, fresh_recomputation: bool = True) -> None:
    unsigned = dict(payload)
    stored_hash = unsigned.pop("content_sha256", None)
    if stored_hash != _canonical_sha256(unsigned):
        raise ValueError("engineering checkpoint content hash mismatch")
    expected = build_checkpoint(fresh_recomputation=fresh_recomputation)
    if payload != expected:
        raise ValueError("engineering checkpoint drift or forged positive output")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--no-fresh-recomputation", action="store_true")
    args = parser.parse_args()
    fresh = not args.no_fresh_recomputation
    if not fresh and args.verify is None:
        raise ValueError("checkpoint generation always requires fresh recomputation")
    if args.verify is not None:
        verify_checkpoint(_load_json(args.verify), fresh_recomputation=fresh)
        print(args.verify)
        return 0
    payload = build_checkpoint(fresh_recomputation=fresh)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(payload["content_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
