import hashlib
import json
from pathlib import Path
import subprocess
import tarfile

BASE = Path(__file__).resolve().parent
ROOTS = {'w1':Path('/private/tmp/cpswm-s2-evidence-repair-window1'), 'w2':Path('/private/tmp/s2-comparison-audit-window2-20260911'), 'w3':Path('/private/tmp/s2-w3-native')}
inputs = {
 'w1':('docs/reviews/data/structure_two_window1_unified_acceptance_prep_2026-09-12T055650Z/starting_state_and_preservation.json','preserved','2a5f45947952e8d725009141716b42ac879434f3'),
 'w2':('docs/reviews/data/structure_two_comparison_dynamic_window2_2026-09-12T1500/preservation_before.json','protected_prior_files','45850dc680cb83169c3108d6a1a5455f7e069457'),
}
result = {}
for window,(name,field,commit) in inputs.items():
    rows = json.loads((ROOTS[window]/name).read_text())[field]
    mismatches = []
    for path, value in rows.items():
        expected = value['sha256'] if isinstance(value,dict) else value
        current = hashlib.sha256((ROOTS[window]/path).read_bytes()).hexdigest()
        original = hashlib.sha256(subprocess.check_output(['git','show',commit+':'+path],cwd=ROOTS[window])).hexdigest()
        if current != expected or original != expected:
            mismatches.append(path)
    result[window] = {'files':len(rows),'match_current_and_prior_git':not mismatches,'mismatches':mismatches}
e5 = ROOTS['w3']/'docs/reviews/data/w3_repair_r5_20260912T055846Z'
rows = {}
with tarfile.open(e5/'untracked_start.tar.gz') as archive:
    for member in archive:
        if member.isfile() and member.name.startswith('docs/reviews/data/w3_repair_2026-09-12_r4/'):
            rows[member.name] = hashlib.sha256(archive.extractfile(member).read()).hexdigest()
current = {str(p.relative_to(ROOTS['w3'])):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOTS['w3']/'docs/reviews/data/w3_repair_2026-09-12_r4').rglob('*') if p.is_file()}
start = json.loads((e5/'start_manifest.json').read_text())['source_hashes']
changed_tests = [name for name, expected in start.items() if name.startswith('tests/test_') and hashlib.sha256((ROOTS['w3']/name).read_bytes()).hexdigest()!=expected]
changed_configs = [name for name, expected in start.items() if name.startswith('configs/') and hashlib.sha256((ROOTS['w3']/name).read_bytes()).hexdigest()!=expected]
result['w3'] = {'r4_files':len(rows),'r4_matches_start_archive_exactly':current==rows,'existing_test_assertion_files_changed':changed_tests,'config_files_changed':changed_configs}
(BASE/'preservation_check.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
assert all(result[k]['match_current_and_prior_git'] for k in ('w1','w2'))
assert rows and current==rows and not changed_tests and not changed_configs
