"""A normal pytest rewritten cache can execute assertions from an older test.

Uses the earlier disposable fixture only. Does not forge JUnit/observations,
patch hooks, change pytest, or modify any delivered production/test source.
"""

import importlib
import json
import os
import shutil
import sys
from pathlib import Path

out = Path(sys.argv[1]).resolve()
root = Path(json.loads((out / "w1_cache_results.json").read_text())["fixture_root"])
sys.path.insert(0, str(root))
m = importlib.import_module("tools.structure_two_unified_acceptance")
test = root / "tests/test_rewritten_cache.py"
passing = 'def test_live():\n import cpswm\n assert cpswm.__version__ == "0.1.0"\n'
failing = passing.replace("0.1.0", "9.9.9")
test.write_text(passing)
stamp = test.stat().st_mtime_ns
rows = []
for label in ("seed_real_pytest_cache", "stale_assertion_accepted", "fresh_assertion_rejected"):
    if label == "stale_assertion_accepted":
        test.write_text(failing)
        os.utime(test, ns=(stamp, stamp))
    if label == "fresh_assertion_rejected":
        for path in (root / "tests/__pycache__").glob("test_rewritten_cache.*.pyc"):
            path.unlink()
    journal = m.Journal(root / m.RUN_AREA / label)
    stage = m.matrix_stage(root, journal, "matrix", ("tests/test_rewritten_cache.py",))
    frozen = m.source_snapshot(root)
    error = None
    try:
        m.run_stages(root, journal, [stage], frozen, (), environment=m.execution_environment(root))
    except ValueError as exc:
        error = str(exc)
    state = json.loads((journal.path / "state.json").read_text())
    row = {
        "case": label,
        "test_source": test.read_text(),
        "status": state["status"],
        "error": error,
        "source_unchanged": m.source_snapshot(root) == frozen,
        "test_sha256": frozen["files"]["tests/test_rewritten_cache.py"],
        "stage": state["stages"][0],
    }
    rows.append(row)
    print(json.dumps({k: v for k, v in row.items() if k != "stage"}), flush=True)
    shutil.copytree(journal.path, out / ("cache_" + label))
(out / "w1_cached_test_results.json").write_text(json.dumps(rows, indent=2) + "\n")
assert rows[0]["error"] is None
assert rows[2]["error"] is not None
