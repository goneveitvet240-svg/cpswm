"""Two structurally consistent mutations of the completed run, physics required."""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

root = Path(__file__).resolve().parents[4]
source = root.parent / "runs/pi05-full-episode-20261024-03"
results = []
for case in ("early_success", "changed_action_and_policy_output"):
    with tempfile.TemporaryDirectory(prefix="cpswm-full-negative-") as temporary:
        run = Path(temporary) / "run"
        shutil.copytree(source, run)
        journal = json.loads((run / "journal.json").read_text())
        summary = json.loads((run / "summary.json").read_text())
        if case == "early_success":
            journal = [
                x for x in journal if not (x.get("event") == "executed_action" and x["tick"] == 117)
            ]
            next(x for x in journal if x.get("event") == "executed_action" and x["tick"] == 116)[
                "task_success_evaluator_only"
            ] = True
            summary.update(steps=117, first_success_step_evaluator_only=117)
            expected = "env.evaluator_success == item"
        else:
            item = next(x for x in journal if x.get("event") == "executed_action")
            item["action"][0] += 0.25
            path = run / "policy_output_00000.npz"
            with np.load(path) as data:
                actions = data["actions"].copy()
            actions[0, 0] = item["action"][0]
            np.savez_compressed(path, actions=actions)
            expected = "Mismatched elements: 3 / 3"
        (run / "journal.json").write_text(json.dumps(journal))
        (run / "summary.json").write_text(json.dumps(summary))
        sys.path.insert(0, str(root / "tools"))
        from verify_pi05_full_episode import validate_records

        validate_records(json.loads((run / "manifest.json").read_text()), summary, journal)
        result = subprocess.run(
            [
                sys.executable,
                str(root / "tools/simulation_python.py"),
                str(root / "tools/verify_pi05_full_episode.py"),
                str(run),
                "--output",
                str(Path(temporary) / "verification.json"),
            ],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0 and "AssertionError" in result.stderr
        assert expected in result.stderr, result.stderr[-3000:]
        results.append(
            {
                "case": case,
                "record_contract": "accepted",
                "physics_replay": "rejected",
                "expected_failure_site": expected,
                "exit_code": result.returncode,
            }
        )
payload = {
    "scope": "partial coherent-record corruption; not arbitrary forgery authentication",
    "cases": results,
}
Path(sys.argv[1]).write_text(json.dumps(payload, indent=2) + "\n")
print(json.dumps(payload, indent=2))
