import importlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root))
m = importlib.import_module("tools.structure_two_unified_acceptance")

j = m.Journal(root / m.RUN_AREA / sys.argv[2])
env = m.execution_environment(root)
frozen = m.source_snapshot(root)
if sys.argv[3] == "smoke":
    plan = [m.matrix_stage(root, j, "actual_test", ("tests/test_launcher_identity_probe.py",))]
else:
    plan = m.comparison_plan(root, j)
print(
    json.dumps(
        {
            "label": "ISOLATED_LOCAL_ENGINEERING_INTEGRATION_NOT_UNIFIED_ACCEPTANCE",
            "source_before": frozen,
            "environment": env,
            "journal": str(j.path),
            "stages": [s.name for s in plan],
        }
    ),
    flush=True,
)
m.run_stages(root, j, plan, frozen, (), environment=env)
print(
    json.dumps(
        {
            "status": j.value["status"],
            "counts": {s["name"]: s.get("pytest_counts") for s in j.value["stages"]},
        }
    ),
    flush=True,
)
