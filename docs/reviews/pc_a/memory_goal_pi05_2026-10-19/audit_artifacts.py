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
                "scope": "four corruptions and one legal run; partial consistency coverage",
                "not_claimed": "authentication or detection of arbitrary consistent fabrication",
            },
            indent=2,
        )
        + "\n"
    )
    if not all(r["expected_result_observed"] for r in results):
        raise SystemExit(1)
    print("1 legal run accepted; 4 corrupted copies rejected")


if __name__ == "__main__":
    main()
