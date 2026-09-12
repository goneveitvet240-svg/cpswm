"""Natural copied-venv console-entry mismatch, using the real stage engine."""
import importlib.util
import json
from pathlib import Path
import sys
import uuid

root = Path(sys.argv[1]).resolve()
spec = importlib.util.spec_from_file_location('independent_coordinator', root/'tools/structure_two_unified_acceptance.py')
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
environment = module.execution_environment(root)
journal = module.Journal(root/module.RUN_AREA/('independent_launcher_'+uuid.uuid4().hex))
frozen = module.source_snapshot(root)
stage = module.Stage('launcher', (str(root/'.venv/bin/pytest'), '-o', 'addopts=', '-q', '-s', '--confcutdir=.', '--junitxml='+str(journal.path/'launcher.xml'), 'tests/test_structure_two_unified_acceptance.py::test_real_cli_without_unified_root_can_only_record_waiting'), 'launcher.xml')
module.run_stages(root,journal,[stage],frozen,(),environment=environment)
lines = (journal.path/'launcher.stdout.log').read_text().splitlines()
child = next(json.loads(line) for line in lines if line.startswith('{"argv"'))
print(json.dumps({'preflight_prefix':environment['prefix'], 'preflight_executable':environment['executable'], 'pytest_script_shebang':(root/'.venv/bin/pytest').read_text().splitlines()[0], 'actual_pytest_sys_executable_from_test':child['argv'][0], 'journal_status':journal.value['status'], 'pytest_counts':journal.value['stages'][0]['pytest_counts'], 'journal':str(journal.path), 'boundary':'isolated real stage engine, not a complete unified acceptance run'},indent=2))
