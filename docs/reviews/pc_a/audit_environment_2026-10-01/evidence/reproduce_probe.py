"""Real read-only command checks in an isolated worktree; not audit acceptance."""
from pathlib import Path
from datetime import datetime, UTC
import hashlib, importlib.util, json, subprocess, sys

root = Path('/private/tmp/cpswm-pc-a-audit-environment-20261001')
output = Path(__file__).parent / 'audit-environment'
output.mkdir(exist_ok=True)
phase = sys.argv[1]
script = root / 'apps/evaluation_runner/run_structure_two_engineering_audit_receipt.py'
spec = importlib.util.spec_from_file_location('actual_audit_command', script)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
source = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
          for directory in ('src', 'apps', 'tests', 'tools')
          for p in (root / directory).rglob('*.py')}
sites = root / '.venv/lib/python3.13/site-packages'
def metadata():
    return {str(p.relative_to(sites)): hashlib.sha256(p.read_bytes()).hexdigest()
            for d in sites.glob('*.dist-info') for p in d.rglob('*') if p.is_file()}
before = metadata()
rows = []
def execute(name, command, expected):
    identity, start, end, completed = module._execute_audit_command('uv_frozen_offline_check', command)
    (output / (phase + '-' + name + '.stdout.log')).write_bytes(completed.stdout)
    (output / (phase + '-' + name + '.stderr.log')).write_bytes(completed.stderr)
    rows.append(dict(name=name, argv=command, identity=identity, start=start, end=end,
                     exit_code=completed.returncode, expected_exit_code=expected))
    assert completed.returncode == expected, (name, completed.stderr.decode())

command = module.COMMANDS['uv_frozen_offline_check']
try:
    execute('legitimate', command, 0)
    if phase == 'review1':
        execute('legacy-dev-only', ('uv', 'sync', '--frozen', '--offline', '--check', '--extra', 'dev', '--no-cache'), 1)
    elif phase == 'review2':
        # Quarantine only metadata of an isolated development environment.
        # --check must reject the missing required dependency without installing it.
        candidates = list(sites.glob('transformers-*.dist-info'))
        assert len(candidates) == 1
        original = candidates[0]
        quarantined = output / (original.name + '.quarantined')
        assert not quarantined.exists()
        original.rename(quarantined)
        try:
            execute('required-dependency-missing', command, 1)
            assert not original.exists()
        finally:
            quarantined.rename(original)
        execute('restored-legitimate', command, 0)
    else:
        raise ValueError(phase)
finally:
    source_after = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for directory in ('src', 'apps', 'tests', 'tools')
                    for p in (root / directory).rglob('*.py')}
    record = dict(scope='DEPENDENCY_CONTRACT_ONLY_NOT_FULL_AUDIT', phase=phase,
                  commit=subprocess.check_output(['git','rev-parse','HEAD'], cwd=root, text=True).strip(),
                  finished_at=datetime.now(UTC).isoformat(), rows=rows,
                  source_unchanged=source==source_after, source_files=source,
                  distribution_metadata_unchanged=before==metadata())
    (output / (phase + '.json')).write_text(json.dumps(record, indent=2)+'\n')
    assert record['source_unchanged'] and record['distribution_metadata_unchanged']
print(phase, 'passed', len(rows), 'real commands')
