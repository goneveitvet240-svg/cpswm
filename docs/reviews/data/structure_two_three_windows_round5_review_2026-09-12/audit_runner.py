"""Independent review runner; never edits any delivery implementation."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

BASE = Path(__file__).resolve().parent
PY = '/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python'
ROOTS = {'w1': Path('/private/tmp/s2-review5-w1.boRzcK'), 'w2': Path('/private/tmp/s2-review5-w2.OkojBR'), 'w3': Path('/private/tmp/s2-review5-w3.o33e1p')}
ORIG = {'w1': Path('/private/tmp/cpswm-s2-evidence-repair-window1'), 'w2': Path('/private/tmp/s2-comparison-audit-window2-20260911'), 'w3': Path('/private/tmp/s2-w3-native')}
E5 = Path('docs/reviews/data/w3_repair_r5_20260912T055846Z')

def hashes(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for top in ('src', 'tests', 'configs', 'apps', 'tools') for p in sorted((root/top).rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc', '.pyo')}

if sys.argv[1] == 'snapshot':
    # Copy every file explicitly named by the delivered source manifest, then compare.
    manifest = json.loads((ORIG['w3']/E5/'delivery_source/manifest.json').read_text())
    for name, expected in manifest['source_hashes'].items():
        rel = Path(name)
        assert not rel.is_absolute() and '..' not in rel.parts
        source = ORIG['w3']/rel
        assert hashlib.sha256(source.read_bytes()).hexdigest() == expected, name
        target = ROOTS['w3']/rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    binding = {}
    for window in ROOTS:
        a, b = hashes(ORIG[window]), hashes(ROOTS[window])
        assert a == b, (window, set(a)^set(b), [k for k in a if k in b and a[k] != b[k]])
        binding[window] = {'original': str(ORIG[window]), 'snapshot': str(ROOTS[window]), 'head': subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOTS[window],text=True).strip(), 'files':a}
    (BASE/'snapshot_binding.json').write_text(json.dumps(binding,indent=2)+'\n')
    print({k:len(v['files']) for k,v in binding.items()})
elif sys.argv[1] == 'check':
    binding = json.loads((BASE/'snapshot_binding.json').read_text())
    result = {k: {'original_unchanged': hashes(ORIG[k]) == v['files'], 'snapshot_unchanged': hashes(ROOTS[k]) == v['files']} for k,v in binding.items()}
    print(json.dumps(result))
    (BASE/'source_after.json').write_text(json.dumps(result,indent=2)+'\n')
    assert all(all(v.values()) for v in result.values())
else:
    window, label = sys.argv[1:3]
    argv = [PY, *sys.argv[3:]]
    env = os.environ.copy()
    env.update(PYTHONPATH=str(ROOTS[window]/'src'), PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', VECLIB_MAXIMUM_THREADS='1')
    if window == 'w2':
        env['S2_AUDIT_BUNDLE'] = str(ROOTS[window]/'docs/reviews/data/structure_two_comparison_dynamic_window2_2026-09-12T1500/bundle_v5')
        if label == 'w2_unbound_orchestration_input':
            env.pop('S2_AUDIT_BUNDLE', None)
    if window == 'w1' and label != 'w1_40':
        argv[0] = str(ROOTS[window]/'.venv/bin/python')
        for key in ('PYTHONPATH','PYTEST_DISABLE_PLUGIN_AUTOLOAD','PYTEST_ADDOPTS','PYTEST_PLUGINS'):
            env.pop(key, None)
    record = {'argv':argv,'cwd':str(ROOTS[window]),'environment':{k:env.get(k) for k in ('PYTHONPATH','PYTEST_DISABLE_PLUGIN_AUTOLOAD','OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','VECLIB_MAXIMUM_THREADS')},'start':time.time()}
    with (BASE/(label+'.stdout.log')).open('x') as out, (BASE/(label+'.stderr.log')).open('x') as err:
        result = subprocess.run(argv,cwd=ROOTS[window],env=env,stdout=out,stderr=err)
    record.update(exit_code=result.returncode,end=time.time())
    (BASE/(label+'.command.json')).write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record))
    print((BASE/(label+'.stdout.log')).read_text()[-4000:])
    print((BASE/(label+'.stderr.log')).read_text()[-1500:])
    sys.exit(result.returncode)
