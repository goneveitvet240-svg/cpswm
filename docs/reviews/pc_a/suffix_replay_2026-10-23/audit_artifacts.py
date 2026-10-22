"""Bounded negative checks against a copy of a recorded goal-loop run."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[4]
    verifier = root / "tools/verify_libero_goal_run.py"
    results = []
    cases = (
        "unchanged",
        "changed_prompt",
        "changed_action",
        "missing_physics",
        "promoted_feedback",
        "promoted_pi05",
        "forged_pi05_without_provenance",
        "cache_count",
        "cache_state",
        "replay_mode",
        "omit_cache_source",
    )
    with tempfile.TemporaryDirectory(prefix="cpswm-goal-audit-") as temporary:
        for case in cases:
            target = Path(temporary) / case
            shutil.copytree(args.run, target)
            path = target / "journal.json"
            journal = json.loads(path.read_text())
            if case == "changed_prompt":
                inference = next(e for e in journal if e["event"] == "policy_inference")
                inference["plan"]["prompt"] = "put the black bowl on the plate"
            elif case == "changed_action":
                action = next(e for e in journal if e["event"] == "executed_action")
                action["action"][0] += 0.1
            elif case == "missing_physics":
                index = next(i for i, e in enumerate(journal) if e["event"] == "executed_action")
                del journal[index]
            elif case == "promoted_feedback":
                feedback = next(
                    e
                    for e in journal
                    if e["event"] == "core_rpc" and e["request"]["operation"] == "feedback"
                )
                feedback["receipt"]["audit"]["queue_history"][-1]["feedback"]["status"] = (
                    "succeeded"
                )
            manifest_path = target / "manifest.json"
            summary_path = target / "summary.json"
            manifest = json.loads(manifest_path.read_text())
            summary = json.loads(summary_path.read_text())
            if case in {"promoted_pi05", "forged_pi05_without_provenance"}:
                summary["pi05_inference_executed"] = True
                if case == "forged_pi05_without_provenance":
                    manifest["arguments"]["policy"] = "pi05-local"
            elif case in {"cache_count", "cache_state"}:
                rpc = next(e for e in journal if e["event"] == "core_rpc")
                receipt = rpc["receipt"]["audit"]["semantic_memory"]["last_replay"]
                if case == "cache_count":
                    receipt["target_score_evaluations"] += 24
                else:
                    receipt["state_sha256"] = "0" * 64
            elif case == "replay_mode":
                manifest["arguments"]["memory_replay"] = "full"
            elif case == "omit_cache_source":
                del manifest["sources"]["src/cpswm/simulation/suffix_memory.py"]
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
            summary_path.write_text(json.dumps(summary, indent=2) + "\n")
            path.write_text(json.dumps(journal, indent=2) + "\n")
            result = subprocess.run(
                [sys.executable, str(verifier), str(target)],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
            passed = result.returncode == 0 if case == "unchanged" else result.returncode != 0
            results.append(
                {
                    "case": case,
                    "expected_result_observed": passed,
                    "exit_code": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                }
            )
    args.output.write_text(
        json.dumps(
            {
                "status": "PASS" if all(r["expected_result_observed"] for r in results) else "FAIL",
                "cases": results,
                "scope": "ten corruptions and one legal run; partial consistency coverage",
                "not_claimed": "authentication or detection of arbitrary consistent fabrication",
            },
            indent=2,
        )
        + "\n"
    )
    if not all(r["expected_result_observed"] for r in results):
        raise SystemExit(1)
    print("1 legal run accepted; 10 corrupted copies rejected")


if __name__ == "__main__":
    main()
