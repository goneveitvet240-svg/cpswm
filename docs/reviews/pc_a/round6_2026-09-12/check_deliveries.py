"""Read-only checks of worker evidence; explicitly not a historical re-execution."""

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

out = Path(__file__).resolve().parent
w2 = Path("/private/tmp/cpswm-pc-a-review6-w2.pfIMZc")
w3 = Path("/private/tmp/cpswm-pc-a-review6-w3.3ZZ6oR")
old = Path("/private/tmp/s2-review5-w3.o33e1p")
e3 = Path("/private/tmp/s2-w3-native/docs/reviews/data/w3_repair_r6_20260912T084200Z")


def check(root, mapping):
    errors = []
    for name, digest in mapping.items():
        path = root / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            errors.append(name)
    return {"files": len(mapping), "mismatches": errors}


inv = json.loads(
    (w2 / "docs/reviews/data/structure_two_window2_handoff_2026-09-12/inventory.json").read_text()
)
bundle = w2 / "docs/reviews/data/structure_two_comparison_dynamic_window2_2026-09-12T1500/bundle_v5"
audit = json.loads((bundle / "audit.json").read_text())
results = {
    "w2_preservation": check(w2, inv["preserved_file_sha256"]),
    "w2_source_bindings": check(w2, audit["source_bindings"]),
    "w2_bundle": check(bundle, inv["bundle_sha256"]),
    "w3_final_source": check(w3, json.loads((e3 / "final_source/manifest.json").read_text())),
    "w3_r5_baseline_source": check(
        old, json.loads((e3 / "baseline_reconstruction.json").read_text())["source_hashes"]
    ),
}
failure_lists = []
for name in ("w3_affected50", "w3_baseline50"):
    log = (out / (name + ".stdout.log")).read_text()
    cases = sorted(re.findall(r"^(?:FAILED|ERROR) tests/[^\n]+", log, re.M))
    failure_lists.append(cases)
    results[name] = {
        "failures": cases,
        "summary": log.strip().splitlines()[-1],
        "missing_model": "structure_two_neural_amortized_model_v0_1.json" in log,
        "exception_types": sorted(set(re.findall(r"^E\s+([A-Za-z]+Error):", log, re.M))),
    }
results["affected_failure_cases_equal"] = (
    failure_lists[0] == failure_lists[1] and len(failure_lists[0]) == 17
)
run = Path(
    "/private/tmp/s2-w1-r5-local-integration-20260912T084136Z/docs/reviews/data/structure_two_unified_acceptance_runs/real_comparison_chain_accepted"
)
state = json.loads((run / "state.json").read_text())
xml = ET.parse(run / "window2_comparison_and_forgery.xml").getroot()
cases = list(xml.iter("testcase"))
results["w1_worker_chain_read_only"] = {
    "run": str(run),
    "not_reexecuted_this_review": True,
    "state_sha256": hashlib.sha256((run / "state.json").read_bytes()).hexdigest(),
    "status": state["status"],
    "scientific_gate": state["scientific_gate"],
    "stages": [
        {
            "name": r.get("name"),
            "exit_code": r.get("exit_code"),
            "status": r.get("status"),
            "pytest_counts": r.get("pytest_counts"),
        }
        for r in state["stages"]
    ],
    "testcases": len(cases),
    "bad_testcases": sum(
        any(c.find(k) is not None for k in ("failure", "error", "skipped")) for c in cases
    ),
}
(out / "delivery_checks.json").write_text(json.dumps(results, indent=2) + "\n")
print(json.dumps(results, indent=2))
assert all(
    not results[k]["mismatches"]
    for k in (
        "w2_preservation",
        "w2_source_bindings",
        "w2_bundle",
        "w3_final_source",
        "w3_r5_baseline_source",
    )
)
assert results["affected_failure_cases_equal"]
