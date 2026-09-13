import hashlib
import json
from pathlib import Path
import shutil

BASE = Path(__file__).resolve().parent
SOURCE = Path('/private/var/folders/x2/000r8p0n6s393lj2sg8wk5f40000gn/T/pytest-of-pangwei/pytest-1707')
KEEP = {'adversarial_matrix.json','adversarial_cli.log','r1_file_consistency_only.log','fairness_forgery_matrix.json','fairness_forgery_cli.log','matrix.json','dynamic_forgery_cli.log','fresh_identifier_late_input.json'}
index = {}
for p in SOURCE.rglob('*'):
    if not p.is_file() or p.is_symlink():
        continue
    if p.name not in KEEP and not ('source-evidence' in p.parts and p.suffix in ('.json','.log')):
        continue
    rel = p.relative_to(SOURCE)
    target = BASE/'w2_retained'/rel
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():
        assert target.read_bytes()==p.read_bytes(), str(p)
    else:
        shutil.copy2(p,target)
    index[str(rel)]={'original':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
summary = {}
for p in (BASE/'w2_retained').rglob('*.json'):
    if p.name in {'adversarial_matrix.json','fairness_forgery_matrix.json','matrix.json'}:
        raw=json.loads(p.read_text())
        result=raw.get('result',{})
        if not isinstance(result,dict) or not result.get('results'):
            continue
        summary[p.name]={'path':str(p),'cases':len(raw.get('cases',[])), 'positive':result['results'][0]['status'], 'rejected':sum(r['status']=='REJECTED' for r in result['results']), 'failures':[r for r in result['results'][1:] if r['status']!='REJECTED']}
(BASE/'w2_retained_index.json').write_text(json.dumps({'files':index,'matrices':summary},indent=2)+'\n')
print(json.dumps({'retained_files':len(index),'matrices':summary},indent=2))
