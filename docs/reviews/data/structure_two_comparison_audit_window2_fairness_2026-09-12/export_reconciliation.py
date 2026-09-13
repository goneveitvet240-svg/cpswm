"""Export descriptive reconciliation; authenticate source bundles with real CLIs separately.

Refuses overwrite. Positives here mean a computed comparison of files only.
"""

import copy
import json
from collections import Counter
from pathlib import Path

from cpswm.system.evaluation_operations import structure_two_comparison_audit as a

root = Path(__file__).resolve().parents[4]
out = Path(__file__).resolve().parent
old = a.load_bundle(
    root
    / "docs/reviews/data/structure_two_comparison_audit_window2_round3_2026-09-11/bundle_v3_final",
    with_attribution=True,
)
new = a.load_bundle(out / "bundle_v4", with_attribution=True)
rows = copy.deepcopy(new.rows)
for row in rows:
    row.pop("fairness_step")
control = new.attribution["common_uniform_when_amg_has_no_owner_estimate"]
prior = old.attribution["common_uniform_when_amg_has_no_owner_estimate"]
control_examples = copy.deepcopy(control["examples"])
for row in control_examples:
    row.pop("search_order_unchanged")
records = new.payload["fairness_execution"]["consumer_probe"]["returns"]
result = {
    "status": "FILE_COMPARISON_ONLY_USE_CLI_LOGS_FOR_FRESH_REPLAY",
    "old_source_schema": old.payload["verification_schema_version"],
    "new_source_schema": new.payload["verification_schema_version"],
    "source_binding_count": len(new.payload["source_bindings"]),
    "old_semantic_sha256": old.payload["semantic_steps_sha256"],
    "new_semantic_sha256": new.payload["semantic_steps_sha256"],
    "new_rows_without_added_fairness_equal_old": a._semantic_rows(rows)
    == a._semantic_rows(old.rows),
    "selection_equal": new.payload["selection"] == old.payload["selection"],
    "all_summary_fields_equal": new.payload["summary"] == old.payload["summary"],
    "retained_score_mismatches": new.payload["retained_score_mismatches"],
    "common_prior_old_new_put_back_examples_equal": control_examples == prior["examples"],
    "common_prior_search_unchanged_all": all(
        r["search_order_unchanged"] for r in control["examples"]
    ),
    "controlled_total_amg_errors": new.payload["summary"]["overall"]["errors"][a.AMG]
    - control["original_amg_errors"]
    + control["uniform_amg_errors"],
    "cold_control": {k: v for k, v in control.items() if k != "examples"},
    "p5_closures": dict(Counter(r["arms"][a.P5]["closure"] for r in new.rows)),
    "consumer_return_sample_counts": dict(Counter(r["symbol"] for r in records)),
    "fit_count": len(new.payload["fairness_execution"]["selection"]["model_fits"]),
    "total_fit_multiply_adds_head_only": sum(
        r["training_multiply_adds_head_only"]
        for r in new.payload["fairness_execution"]["selection"]["model_fits"]
    ),
    "training_access_kinds": dict(
        Counter(r["kind"] for r in new.payload["fairness_execution"]["train_access"])
    ),
    "validation_access_kinds": dict(
        Counter(r["kind"] for r in new.payload["fairness_execution"]["selection"]["access_events"])
    ),
    "training": new.payload["training"],
    "observations": new.payload["fairness"]["observations"],
    "historical_action_chain_matches": sum(
        r["matches"] for r in new.attribution["historical_action_chain_checks"]
    ),
}
with (out / "semantic_reconciliation.json").open("x") as f:
    json.dump(result, f, indent=2)
    f.write("\n")
matrix = {
    "status": "DESCRIPTIVE_EXPORT_NOT_AN_AUTHENTICITY_CERTIFICATE",
    "source_semantic_steps_sha256": new.payload["semantic_steps_sha256"],
    "bound_audit_fairness": new.payload["fairness"],
    "arms": list(a.ARMS),
    "dimensions": [
        {
            "dimension": "packet/support/cost/action",
            "source": "steps[*].fairness_step and arms",
            "rule": (
                "frozen common consumer boundary enforced; "
                "see check_step/check_receipt/check_decoded"
            ),
            "comparison_fairness": "NOT_ESTABLISHED",
        },
        {
            "dimension": "training and selection",
            "source": "audit.fairness_execution.train_access,selection",
            "actual_fit_count": result["fit_count"],
            "actual_validation_scoring_calls": result["validation_access_kinds"][
                "score_after_commit"
            ],
            "equal_training_budget": False,
        },
        {
            "dimension": "consumed evidence",
            "source": "audit.fairness_execution.consumer_probe",
            "return_sample_counts": result["consumer_return_sample_counts"],
            "equal_consumption": False,
        },
        {
            "dimension": "future support",
            "source": "steps[*].future_support_count,support_by_arm",
            "affected_steps": result["observations"]["future_support_steps"],
            "permission": "USER_DECISION_REQUIRED",
        },
        {
            "dimension": "cold default",
            "source": "attribution.common_uniform_when_amg_has_no_owner_estimate",
            "affected_steps": control["steps"],
            "formal_rule": "USER_DECISION_REQUIRED",
        },
        {
            "dimension": "SEARCH",
            "source": "steps[*].arms.current and sensitivity counterexamples",
            "equal_steps": result["observations"]["search_equal_steps"],
            "native_readout_budget": "USER_DECISION_REQUIRED",
        },
        {
            "dimension": "long memory",
            "source": (
                "steps[*].raw_state.p5_readouts.state_counts "
                "and alternative_readouts_development_only"
            ),
            "observed_commit_histogram": result["observations"]["p5_commit_counts"],
            "capability": "UNMEASURED_LEGAL_UNBLOCK_AND_LONG_MEMORY_BENEFIT",
        },
        {
            "dimension": "compute",
            "source": "bundle_v4/timing.json and selection.model_fits",
            "same_order_control": (
                "fresh episode states, three rotating repetitions, fixed two episodes"
            ),
            "host_exclusive": False,
            "performance_superiority_established": False,
        },
        {
            "dimension": "scientific validity",
            "source": "audit.signal_gate_retained_not_reselected",
            "passed": False,
            "new_confirmatory_experiment": False,
        },
    ],
}
with (out / "fairness_matrix.json").open("x") as f:
    json.dump(matrix, f, indent=2)
    f.write("\n")
print(json.dumps(result, indent=2))
