import hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
root=Path(sys.argv[1])
source=root/'state.sqlite'
before=hashlib.sha256(source.read_bytes()).hexdigest()
shutil.copy2(source,root/'copy.db')
env=dict(os.environ,PYTHONPATH=os.pathsep.join(str(Path.cwd()/p) for p in ('src','tests','tools')),PYTHONHASHSEED='9217')
with (root/'fresh.log').open('w') as log:
 result=subprocess.run([sys.executable,'-c','from test_appearance_geometry_position import fresh_restore; import sys; fresh_restore(sys.argv[1])',str(root)],cwd=Path.cwd(),env=env,stdout=log,stderr=subprocess.STDOUT,timeout=180)
assert result.returncode==0,(root/'fresh.log').read_text()
report=json.loads((root/'result.json').read_text())
fresh=json.loads((root/'fresh.json').read_text())
assert fresh==dict(view=report['posterior_sha'],semantic=report['semantic'],update=report['update_sha'])
assert hashlib.sha256(source.read_bytes()).hexdigest()==before
out=dict(status='passed',source_sha=report['source_sha'],original_database_sha256=before,original_database_unchanged=True,fresh=fresh)
(root/'fresh-verification.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out))
