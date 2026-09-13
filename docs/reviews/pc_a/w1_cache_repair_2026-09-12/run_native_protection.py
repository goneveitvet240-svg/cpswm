import importlib
import json
import sys
from dataclasses import replace
from pathlib import Path

root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root))
m = importlib.import_module("tools.structure_two_unified_acceptance")

j = m.Journal(root / m.RUN_AREA / sys.argv[2])
f = m.source_snapshot(root)
e = m.execution_environment(root)
s = m.matrix_stage(root, j, "window1_protection", m.W1_TESTS)
s = replace(s, argv=(*s.argv, "--basetemp=" + str(Path("/private/tmp") / ("cpswm-" + sys.argv[2]))))
m.run_stages(root, j, [s], f, (), environment=e)
print(
    json.dumps(
        {
            "journal": str(j.path),
            "status": j.value["status"],
            "counts": j.value["stages"][0]["pytest_counts"],
        }
    )
)
