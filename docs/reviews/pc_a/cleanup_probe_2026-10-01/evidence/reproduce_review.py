from pathlib import Path
from datetime import datetime, UTC
import json, os, subprocess, sys, time

root=Path('/private/tmp/cpswm-pc-a-cleanup-probe-20261001')
out=Path(__file__).parent/'cleanup-probe'
sys.path.insert(0,str(root/'tools'))
from prepare_current_validation_inputs import source_inventory
phase=sys.argv[1];before=source_inventory(root)
if phase=='review1':
    nodes=['tests/test_cleanup_group_probe.py','tests/test_structure_two_unified_dependencies.py::test_actual_foreign_worker_interpreter_refused']
elif phase=='review2':
    assert json.loads((out/'review1.json').read_text())['exit_code']==0
    nodes=['tests/test_structure_two_unified_dependencies.py','tests/test_structure_two_unified_acceptance.py::test_interruption_kills_descendants_even_when_group_leader_exits']
else:raise ValueError(phase)
command=[sys.executable,'-m','pytest','-o','addopts=','-q',*nodes,'--basetemp='+str(out/(phase+'-cases'))]
record=dict(phase=phase,scope='IMPLEMENTER_A_REVIEW_NOT_COMPLETE_REGRESSION',argv=command,started_at=datetime.now(UTC).isoformat(),commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),source_before=before)
start=time.monotonic()
with (out/(phase+'.log')).open('w') as log:
    completed=subprocess.run(command,cwd=root,stdout=log,stderr=subprocess.STDOUT,env=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1'))
record.update(exit_code=completed.returncode,elapsed_seconds=time.monotonic()-start,source_unchanged=before==source_inventory(root))
(out/(phase+'.json')).write_text(json.dumps(record,indent=2)+'\n')
assert record['source_unchanged'];print(phase,completed.returncode,record['elapsed_seconds']);raise SystemExit(completed.returncode)
