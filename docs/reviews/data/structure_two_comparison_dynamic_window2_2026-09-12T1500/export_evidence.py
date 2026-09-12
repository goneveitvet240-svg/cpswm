"""Descriptive export only; formal CLI logs, not this export, establish replay status."""

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
NEW = HERE / "bundle_v5"
OLD = (
    ROOT / "docs/reviews/data/structure_two_comparison_audit_window2_fairness_2026-09-12/bundle_v4"
)


def read(path):
    return json.loads(path.read_text())


def save(name, data):
    (HERE / name).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


new, old = read(NEW / "audit.json"), read(OLD / "audit.json")
attr, oldattr = read(NEW / "attribution.json"), read(OLD / "attribution.json")
d = new["dynamic_development"]
matrix = []
for scene in d["scenes"]:
    rows = scene["rows"]
    ordinary = [r["ordinary_reference_same_visible_input"]["after"] for r in rows]
    arms = {}
    for arm in rows[0]["arms"]:
        valid = [r["arms"][arm] for r in rows if r["arms"][arm]["status"] == "RETURNED"]
        arms[arm] = {
            "valid_outputs": len(valid),
            "rejected_outputs": len(rows) - len(valid),
            "search_top1_correct": sum(v["search_top1_correct"] is True for v in valid),
            "search_evaluable": sum(v["search_top1_correct"] is not None for v in valid),
            "put_back_command_correct": sum(v["put_back_command_correct"] for v in valid),
            "executed_actions": None,
            "environment_state_changes": None,
        }
    matrix.append(
        {
            "scenario": scene["plan"],
            "inputs": len(rows),
            "arms": arms,
            "direct_p5_max_committed": scene["max_direct_p5_committed"],
            "full_fast_action_differences": scene["full_fast_action_differences"],
            "ordinary_max_committed": scene["max_ordinary_reference_committed"],
            "ordinary_regime_sequence": [r["active_regime"] for r in ordinary],
            "ordinary_nonhabit_long_mass": [
                r["ordinary_reference_same_visible_input"]["nonhabit_long_contribution_mass"]
                for r in rows
            ],
            "complete_mechanism": scene["complete_mechanism"],
            "invalid_comparison_steps": [
                r["step_index"] for r in rows if r["contract_check"] != "PASS"
            ],
        }
    )
save(
    "scenario_matrix.json",
    {
        "development_only": True,
        "rows": matrix,
        "ciav": {
            k: {"closure": v["closure"], "outcome": v["detection_outcome"]}
            for k, v in d["ciav_interface_probes"].items()
        },
        "full_execution": d["execution"],
    },
)
save("contract_matrix.json", new["comparison_contract"])
save("controlled_contrasts.json", d["controlled_contrasts"])
save(
    "handoff_boundary_probes.json",
    {
        "production_revision": d["production_boundary_probes"],
        "ciav": d["ciav_interface_probes"],
        "feedback": d["feedback_interface_probes"],
    },
)
save(
    "numeric_reconciliation.json",
    {
        "old_bundle": str(OLD),
        "new_bundle": str(NEW),
        "same_d0_semantic_steps": new["semantic_steps_sha256"] == old["semantic_steps_sha256"],
        "same_d0_summary": new["summary"] == old["summary"],
        "same_selection": new["selection"] == old["selection"],
        "same_attribution": attr == oldattr,
        "retained_score_mismatches": new["retained_score_mismatches"],
        "arm_metrics": new["summary"]["arm_metrics"],
        "cold_start": attr["common_uniform_when_amg_has_no_owner_estimate"],
        "p5_state_count_histograms": attr["p5_state_count_histograms"],
        "full_fast_disagreement": attr["p5_vs_fast_put_back_disagreement_steps"],
        "search_identical": new["summary"]["search_three_arm_distribution_equal_steps"],
        "source_changes": [
            p
            for p in new["source_bindings"]
            if new["source_bindings"][p] != old["source_bindings"].get(p)
        ],
    },
)
preservation = read(HERE / "preservation_before.json")
mismatch = [
    p
    for p, h in preservation["protected_prior_files"].items()
    if hashlib.sha256((ROOT / p).read_bytes()).hexdigest() != h
]
save(
    "preservation_after.json",
    {"protected_files": len(preservation["protected_prior_files"]), "mismatches": mismatch},
)
assert not mismatch
print(
    json.dumps(
        {
            "scenes": len(matrix),
            "inputs": sum(r["inputs"] for r in matrix),
            "prior_files_unchanged": len(preservation["protected_prior_files"]),
            "same_d0_summary": new["summary"] == old["summary"],
            "same_attribution": attr == oldattr,
        }
    )
)
