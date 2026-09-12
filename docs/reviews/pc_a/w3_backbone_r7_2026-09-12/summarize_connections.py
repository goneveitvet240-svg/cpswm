"""Calculate actual content handoffs and numerical effects without acceptance inflation."""

import importlib
import json
import math
import sys
from collections import Counter
from pathlib import Path

root = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(root / "src"))
content_sha256 = importlib.import_module("cpswm.system.reproducibility").content_sha256
content_uuid = importlib.import_module("cpswm.system.reproducibility").content_uuid

out = Path(__file__).resolve().parent
runs = {
    name: json.loads((out / f"continuous_final_{name}.json").read_text())
    for name in ["base", "null", "opceu", "orrer", "pchmp", "identity", "ciav", "openworld"]
}
base = runs["base"]
rows = {}
for name, run in runs.items():
    assert run["completed"] and run["source_before"] == run["source_after"]
    assert run["source_before"] == base["source_before"]
    calls = run["calls"]
    counts = Counter(r["operator"] for r in calls)

    def rr(operator, calls=calls):
        return [r for r in calls if r["operator"] == operator]

    branches = {content_sha256(r["output"]) for r in rr("orrer")}
    cf = {content_sha256(r["output"]) for r in rr("cf_bocpd")}
    decisions = {content_sha256(r["output"]) for r in rr("ccrr")}
    matched_orrer = sum(content_sha256(r["input"]["history"]) in branches for r in rr("pchmp"))
    matched_cf = sum(content_sha256(r["output"]["snapshot"]) in cf for r in rr("cause_router"))
    matched_ccrr = sum(
        r["output"]["ccrr_decision"] is not None
        and content_sha256(r["output"]["ccrr_decision"]) in decisions
        for r in rr("cause_router")
    )
    plans = {r["output"]["selected_action_id"] for r in rr("ciav") if r["output"]["should_act"]}
    matched_plan = sum(r["input"]["action"]["action_id"] in plans for r in rr("verification"))
    closure_ids = {
        str(
            content_uuid(
                "adaptive-ciav-canonical-detection",
                {
                    "ciav_detection_id": r["output"]["detection"]["metadata"]["record_id"],
                    "opportunity_id": r["output"]["opportunity"]["metadata"]["record_id"],
                },
            )
        )
        for r in rr("verification")
    }
    matched_closure = sum(
        r["input"]["after"]["metadata"]["record_id"] in closure_ids for r in rr("orrer")
    )
    alpha_delta = [d["delta_alpha"] for r in rr("rgrc") for d in r["input"]["deltas"]]

    def tv(left, right):
        return 0.5 * math.fsum(abs(left[k] - right[k]) for k in left)

    comparable = list(zip(base["steps"], run["steps"], strict=True))
    rows[name] = {
        "call_counts": dict(counts),
        "actual_content_handoffs": {
            "orrer_output_to_pchmp_input": matched_orrer,
            "cf_output_to_cause_router_output_snapshot": matched_cf,
            "ccrr_output_to_cause_router_decision": matched_ccrr,
            "ciav_selected_action_to_executor": matched_plan,
            "verified_detection_to_orrer_closure": matched_closure,
        },
        "max_action_distribution_tv_vs_base": max(
            tv(a["action"], b["action"]) for a, b in comparable
        ),
        "max_hybrid_alpha_absolute_change_vs_base": max(
            abs(a["owner_mass"][k] - b["owner_mass"][k])
            for a, b in comparable
            for k in a["owner_mass"]
        ),
        "final_committed": run["steps"][-1]["committed"],
        "final_action": run["steps"][-1]["action"],
        "changed_count_or_regime_steps": sum(
            a["committed"] != b["committed"] or a["active_regime"] != b["active_regime"]
            for a, b in comparable
        ),
        "ccrr_decision_kinds": [r["output"]["kind"] for r in rr("ccrr")],
        "nonzero_real_rgrc_deltas": sum(x > 0 for x in alpha_delta),
        "default_joint_particles_at_every_step": [
            s["default_joint_particles"] for s in run["steps"]
        ],
        "all_three_default_conditional_increments_nonzero": any(
            any(abs(x) > 0 for row in d["delta_information"] for x in row)
            for r in rr("rgrc")
            for d in r["input"]["deltas"]
        ),
        "continuous_completed": True,
    }
    assert matched_orrer == counts["pchmp"] > 0
    assert matched_cf == counts["cause_router"] > 0
    assert matched_plan == counts["verification"] == 1
    assert rows[name]["nonzero_real_rgrc_deltas"] > 0
    assert all(s["default_joint_particles"] == 0 for s in run["steps"])
# This is the already-used numerical null-control tolerance, not a scientific threshold.
assert rows["null"]["max_action_distribution_tv_vs_base"] < 1e-9
assert rows["null"]["max_hybrid_alpha_absolute_change_vs_base"] < 1e-9
assert rows["null"]["changed_count_or_regime_steps"] == 0
result = {
    "variants": rows,
    "default_full_joint_backbone_operational": False,
    "seven_native_sequential_operators_executed": all(
        rows["base"]["call_counts"].get(k, 0) > 0
        for k in ["opceu", "orrer", "pchmp", "cf_bocpd", "ccrr", "rgrc", "ciav"]
    ),
    "full_joint_causal_collaboration_verified": False,
    "scientific_benefit_verified": False,
    "limits": [
        "continuous synthetic native execution; no real-robot claim",
        "CIAV receives a cause belief, not a full particle posterior",
        "information natural-parameter increments remain zero on ordinary owner placements",
        (
            "does not establish every operator isolated causal effect "
            "or every decoded task-action change"
        ),
    ],
}
with (out / "connection_matrix.json").open("x") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print(
    json.dumps(
        {
            k: {
                "TV": v["max_action_distribution_tv_vs_base"],
                "alpha_delta": v["max_hybrid_alpha_absolute_change_vs_base"],
                "committed": v["final_committed"],
            }
            for k, v in rows.items()
        },
        indent=2,
    )
)
