"""Summarize current raw traces without converting gaps into acceptance."""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[4]
sys.path.insert(0, str(ROOT / "src"))

from cpswm.system.reproducibility import content_sha256, content_uuid  # noqa: E402


def load_gzip_json(path: Path) -> dict[str, object]:
    body = gzip.decompress(path.read_bytes())
    for encoding in ("utf-8", "cp936"):
        try:
            return json.loads(body.decode(encoding))
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("trace", body, 0, len(body), "unsupported JSON encoding")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tv(left: dict[str, float], right: dict[str, float]) -> float:
    return 0.5 * math.fsum(abs(left[key] - right[key]) for key in left)


def top(distribution: dict[str, float]) -> str:
    return min(distribution, key=lambda key: (-distribution[key], key))


def any_nonzero(value: object) -> bool:
    if isinstance(value, (int, float)):
        return abs(float(value)) > 0.0
    if isinstance(value, list):
        return any(any_nonzero(item) for item in value)
    if isinstance(value, dict):
        return any(any_nonzero(item) for item in value.values())
    return False


def junit_summary(path: Path) -> dict[str, object]:
    root = ET.parse(path).getroot()
    cases = root.findall(".//testcase")
    failures = root.findall(".//failure")
    errors = root.findall(".//error")
    skipped = root.findall(".//skipped")
    return {
        "artifact": path.name,
        "sha256": sha256(path),
        "tests": len(cases),
        "failures": len(failures),
        "errors": len(errors),
        "skipped": len(skipped),
        "passed": len(cases) - len(failures) - len(errors) - len(skipped),
        "all_green": not (failures or errors or skipped),
        "testcases": [
            {
                "classname": case.attrib.get("classname"),
                "name": case.attrib.get("name"),
                "status": (
                    "failed"
                    if case.find("failure") is not None
                    else "error"
                    if case.find("error") is not None
                    else "skipped"
                    if case.find("skipped") is not None
                    else "passed"
                ),
            }
            for case in cases
        ],
    }


def connection_rows(runs: dict[str, dict[str, object]]) -> dict[str, object]:
    base = runs["base"]
    output: dict[str, object] = {}
    for name, trace in runs.items():
        calls = trace["calls"]
        counts = Counter(row["operator"] for row in calls)

        def rows(operator: str, source_calls=calls):
            return [row for row in source_calls if row["operator"] == operator]

        branches = {content_sha256(row["output"]) for row in rows("orrer")}
        cf_outputs = {content_sha256(row["output"]) for row in rows("cf_bocpd")}
        decisions = {content_sha256(row["output"]) for row in rows("ccrr")}
        matched_orrer = sum(
            content_sha256(row["input"]["history"]) in branches for row in rows("pchmp")
        )
        matched_cf = sum(
            content_sha256(row["output"]["snapshot"]) in cf_outputs
            for row in rows("cause_router")
        )
        matched_ccrr = sum(
            row["output"]["ccrr_decision"] is not None
            and content_sha256(row["output"]["ccrr_decision"]) in decisions
            for row in rows("cause_router")
        )
        plans = {
            row["output"]["selected_action_id"]
            for row in rows("ciav")
            if row["output"]["should_act"]
        }
        matched_plan = sum(
            row["input"]["action"]["action_id"] in plans for row in rows("verification")
        )
        closure_ids = {
            str(
                content_uuid(
                    "adaptive-ciav-canonical-detection",
                    {
                        "ciav_detection_id": row["output"]["detection"]["metadata"][
                            "record_id"
                        ],
                        "opportunity_id": row["output"]["opportunity"]["metadata"][
                            "record_id"
                        ],
                    },
                )
            )
            for row in rows("verification")
        }
        matched_closure = sum(
            row["input"]["after"]["metadata"]["record_id"] in closure_ids
            for row in rows("orrer")
        )
        comparable = list(zip(base["steps"], trace["steps"], strict=True))
        rgrc_deltas = [
            delta for row in rows("rgrc") for delta in row["input"]["deltas"]
        ]
        final_action = trace["steps"][-1]["action"]
        base_final_action = base["steps"][-1]["action"]
        output[name] = {
            "completed": trace["completed"],
            "call_counts": dict(counts),
            "actual_content_handoffs": {
                "orrer_output_to_pchmp_input": matched_orrer,
                "cf_output_to_cause_router_snapshot": matched_cf,
                "ccrr_output_to_cause_router_decision": matched_ccrr,
                "ciav_selected_action_to_executor": matched_plan,
                "verified_detection_to_orrer_closure": matched_closure,
            },
            "max_action_distribution_tv_vs_base": max(
                tv(left["action"], right["action"]) for left, right in comparable
            ),
            "final_action_tv_vs_base": tv(base_final_action, final_action),
            "final_top1": top(final_action),
            "final_top1_changed_vs_base": top(final_action) != top(base_final_action),
            "top1_changed_step_count_vs_base": sum(
                top(left["action"]) != top(right["action"])
                for left, right in comparable
            ),
            "max_hybrid_alpha_absolute_change_vs_base": max(
                abs(left["owner_mass"][key] - right["owner_mass"][key])
                for left, right in comparable
                for key in left["owner_mass"]
            ),
            "final_committed": trace["steps"][-1]["committed"],
            "changed_count_or_regime_steps": sum(
                left["committed"] != right["committed"]
                or left["active_regime"] != right["active_regime"]
                for left, right in comparable
            ),
            "ccrr_decision_kinds": [row["output"]["kind"] for row in rows("ccrr")],
            "rb_blocks": {
                "dirichlet_delta_alpha_nonzero": any(
                    any_nonzero(delta["delta_alpha"]) for delta in rgrc_deltas
                ),
                "rls_delta_A_or_b_nonzero": any(
                    any_nonzero(delta["delta_a"]) or any_nonzero(delta["delta_b"])
                    for delta in rgrc_deltas
                ),
                "information_delta_lambda_or_xi_nonzero": any(
                    any_nonzero(delta["delta_information"])
                    or any_nonzero(delta["delta_information_vector"])
                    for delta in rgrc_deltas
                ),
            },
            "default_joint_particle_counts": [
                step["default_joint_particles"] for step in trace["steps"]
            ],
        }
    return output


def operator_matrix(
    base: dict[str, object], variants: dict[str, object], metrics: dict[str, object]
) -> dict[str, object]:
    calls = base["calls"]

    def specimen(name: str) -> dict[str, object]:
        matching = [item for item in calls if item["operator"] == name]
        row = matching[0]
        phases_by_instance: dict[str, set[str]] = {}
        for item in matching:
            phases_by_instance.setdefault(str(item["instance_id"]), set()).add(item["phase"])
        return {
            "instance_id": row["instance_id"],
            "unique_instance_count_in_base_trace": len(
                {item["instance_id"] for item in matching}
            ),
            "phases_by_process_local_instance_id": {
                key: sorted(value) for key, value in phases_by_instance.items()
            },
            "implementation": row["implementation"],
            "source_sha256": row["source_sha256"],
            "real_input_keys": sorted(row["input"]),
            "real_output_keys": (
                sorted(row["output"]) if isinstance(row["output"], dict) else []
            ),
        }

    shared = {
        "acceptance_class": "engineering causal diagnostic only",
        "scientific_benefit": False,
    }
    return {
        "OPCEU": {
            **shared,
            **specimen("opceu"),
            "binding_kind": "direct_operator_callable",
            "output_and_consumer": (
                "propensity correction -> event/statistic weight -> "
                "RGRC alpha/ledger -> action readout"
            ),
            "legal_control": (
                "context key not read by OPCEU; causal-matrix null test requires unchanged readout"
            ),
            "public_intervention": "p_visible_given_state=0.35",
            "numeric_consequence": variants["opceu"],
        },
        "ORRER_CHEH": {
            **shared,
            **specimen("orrer"),
            "binding_kind": "direct_operator_callable",
            "output_and_consumer": "event history -> exact content consumed by PCHMP",
            "legal_control": "same inputs reproduce the same semantic hypothesis set",
            "public_intervention": "unresolved_probability=0.4",
            "numeric_consequence": variants["orrer"],
        },
        "PCHMP": {
            **shared,
            **specimen("pchmp"),
            "binding_kind": "direct_operator_callable",
            "output_and_consumer": (
                "actor posterior + native source -> primary statistic/readout; "
                "explicit native projection "
                "exists, but default workspace creates no joint particles"
            ),
            "legal_control": "same evidence reordered; semantic values equal within 1e-9",
            "public_intervention": "evidence_filter removes mechanism evidence",
            "numeric_consequence": variants["pchmp"],
        },
        "CF_BOCPD": {
            **shared,
            **specimen("cf_bocpd"),
            "binding_kind": "direct_operator_callable",
            "output_and_consumer": (
                "cause snapshot -> actual cause router -> CCRR; "
                "CIAV later reads current cause belief"
            ),
            "legal_control_and_public_intervention": metrics["cf_bocpd"],
            "continuous_history_observation": {
                "base_ccrr_decisions": variants["base"]["ccrr_decision_kinds"]
            },
        },
        "CCRR": {
            **shared,
            **specimen("ccrr"),
            "binding_kind": "composite_operator_stage",
            "output_and_consumer": (
                "stay/create/reactivate/unresolved decision -> quarantine/promotion routing -> RGRC"
            ),
            "legal_control_and_public_intervention": metrics["ccrr"],
        },
        "RGRC": {
            **shared,
            **specimen("rgrc"),
            "binding_kind": "enclosing_runtime_stage",
            "output_and_consumer": (
                "single HybridStatisticLedger -> Dirichlet/RLS/information projections "
                "-> action readout; "
                "feedback revision retracts/replaces on the same ledger"
            ),
            "legal_control_and_public_intervention": metrics["rgrc"],
            "observed_rb_blocks": variants["base"]["rb_blocks"],
        },
        "CIAV": {
            **shared,
            **specimen("ciav"),
            "binding_kind": "adaptive_composite_stage",
            "output_and_consumer": (
                "selected action -> actual executor -> verified detection -> "
                "ORRER/PCHMP closure -> "
                "feedback revision -> RGRC -> subsequent action"
            ),
            "legal_control": (
                "privacy-blocked action is a legal no-op; "
                "negative detection has no feedback closure"
            ),
            "public_intervention": "same-location actor likelihood 0.95 vs 0.05",
            "numeric_consequence": metrics["ciav"],
            "critical_gap": "real input is StructureTwoCauseBelief, not full particle posterior",
        },
    }


def main() -> int:
    env = json.loads((OUT / "environment_and_source_binding.json").read_text(encoding="utf-8"))
    commands = json.loads((OUT / "commands.json").read_text(encoding="utf-8"))
    gaps = json.loads((OUT / "capability_gaps.json").read_text(encoding="utf-8"))
    metrics = json.loads((OUT / "operator_metrics.json").read_text(encoding="utf-8"))
    traces = {
        name: load_gzip_json(OUT / f"continuous_current_{name}.json.gz")
        for name in ("base", "null", "opceu", "orrer", "pchmp", "identity", "ciav", "openworld")
    }
    variants = connection_rows(traces)
    junits = {
        path.stem: junit_summary(path)
        for path in sorted(OUT.glob("pytest_*.xml"))
    }
    scenario_matrix = {
        "stable_habit": {
            "status": "EXECUTED",
            "evidence": ["continuous base stable prefix", "CF-BOCPD null control"],
        },
        "habit_change_and_reactivation": {
            "status": "EXECUTED",
            "evidence": variants["base"]["ccrr_decision_kinds"],
        },
        "multi_person_handoff": {
            "status": "PARTIAL_EXECUTED",
            "evidence": (
                "owner/guest/unknown prior and ORRER handoff role "
                "enumeration/revival tests; no claim "
                "that every continuous event's hidden truth is a handoff"
            ),
        },
        "similar_physical_instances": {
            "status": "MISSING_FROM_DEFAULT_HISTORY",
            "evidence": (
                "Direction-Three oracle contract test is reference-only; "
                "current BackboneWiringProbe "
                "owns one object_instance_id and cannot establish default-path discrimination"
            ),
        },
        "unknown_person": {
            "status": "EXECUTED",
            "evidence": "open-world trace plus unknown actor support tests",
        },
        "unknown_location": {
            "status": "MISSING_FROM_DEFAULT_ACTION_SUPPORT",
            "evidence": (
                "default action support contains registered UUID locations; "
                "no explicit unknown-location "
                "candidate is consumed by the default joint path"
            ),
        },
        "negative_observation": {
            "status": "EXECUTED_CORRECT_NO_OP_WITH_OPEN_CONSUMER_GAP",
            "evidence": (
                "seven primary receipts, no closure/commit; "
                "CIAV actor posterior differs but is discarded"
            ),
        },
        "late_correction": {
            "status": "EXECUTED",
            "evidence": "continuous late_feedback_correction plus real feedback loop test",
        },
        "defer_and_debt_recovery": {
            "status": "EXECUTED",
            "evidence": "public P0 deferral, expired debt replay, exactly-once refusal",
        },
        "cancel_and_recovery": {
            "status": "EXECUTED_PROCESS_LOCAL",
            "evidence": (
                "public cancellation and injected interruption/retry; "
                "not cross-process power-loss recovery"
            ),
        },
        "one_runtime_covers_every_required_scenario": {
            "status": "NOT_ESTABLISHED",
            "evidence": (
                "continuous history covers stable/change/open-world/late correction; "
                "negative, debt, "
                "cancellation and similar-instance cases remain separate scenario runs"
            ),
        },
    }
    payload = {
        "classification": "engineering causal diagnostic; not scientific acceptance",
        "git_head": env["git_head"],
        "last_commit_touching_src": env["last_commit_touching_src"],
        "source_unchanged": env["source_unchanged"] and metrics["source_unchanged"],
        "continuous_variants": variants,
        "operator_matrix": operator_matrix(traces["base"], variants, metrics),
        "scenario_matrix": scenario_matrix,
        "junit": junits,
        "capability_gaps": gaps,
        "commands_all_as_expected": commands["all_command_outcomes_as_expected"],
        "claims": {
            "seven_operators_executed_on_native_sequential_path": all(
                variants["base"]["call_counts"].get(name, 0) > 0
                for name in ("opceu", "orrer", "pchmp", "cf_bocpd", "ccrr", "rgrc", "ciav")
            ),
            "default_full_joint_backbone_operational": False,
            "full_joint_causal_collaboration_verified": False,
            "scientific_benefit_verified": False,
            "real_robot_execution_verified": False,
        },
        "raw_artifacts": {
            name: {
                "path": f"continuous_current_{name}.json.gz",
                "sha256": sha256(OUT / f"continuous_current_{name}.json.gz"),
            }
            for name in traces
        },
    }
    (OUT / "connection_and_scenario_matrix.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    summary = {
        "command": [str(Path(sys.executable).resolve()), str(Path(__file__).resolve())],
        "cwd": str(ROOT),
        "git_head": payload["git_head"],
        "last_commit_touching_src": payload["last_commit_touching_src"],
        "output": "connection_and_scenario_matrix.json",
        "output_sha256": sha256(OUT / "connection_and_scenario_matrix.json"),
        "exit_code": 0,
    }
    (OUT / "summarize_diagnostic.command.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "seven_executed": payload["claims"][
                    "seven_operators_executed_on_native_sequential_path"
                ],
                "default_full_joint": False,
                "scenario_gaps": [
                    name
                    for name, item in scenario_matrix.items()
                    if item["status"].startswith("MISSING")
                    or item["status"] == "NOT_ESTABLISHED"
                ],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
