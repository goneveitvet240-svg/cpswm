import hashlib,json,sqlite3,subprocess,sys,os
from pathlib import Path
from uuid import UUID
from structure_two_backbone_wiring_probe import BackboneWiringProbe
from test_native_position_production import fixture_models
from cpswm.data_preflight.typed_proposal_networks import ARMS
root=Path('/private/tmp/cpswm-natural-candidate-evidence-20261001/live')
report=json.loads((root/'result.json').read_text())
source=root/'state.sqlite'
original=hashlib.sha256(source.read_bytes()).hexdigest()
with sqlite3.connect(source) as db, sqlite3.connect(root/'copy.db') as out:
    db.backup(out)
selected=BackboneWiringProbe.build(seed=171).observed_days()[1].after
checkpoint=root/'native-neural-checkpoints'/ARMS[1]
config=dict(semantic_record_id=str(selected.metadata.record_id),enabled=True,weights_path='/private/tmp/cpswm-natural-candidate-evidence-20261001/ssdlite.pth')
(root/'restore.json').write_text(json.dumps(dict(config=config,models=fixture_models(),checkpoint=str(checkpoint),pin=hashlib.sha256((checkpoint/'manifest.json').read_bytes()).hexdigest(),action=report['command']),indent=2)+'\n')
child=subprocess.run([sys.executable,'-c','from test_natural_candidate_position import fresh_restore; import sys; fresh_restore(sys.argv[1])',str(root)],env=dict(os.environ,PYTHONHASHSEED='102731'),timeout=180)
assert child.returncode==0
fresh=json.loads((root/'fresh.json').read_text())
assert fresh['view']==report['posterior_sha']
assert hashlib.sha256(source.read_bytes()).hexdigest()==original
result=dict(status='passed',source_database_unchanged=True,posterior_matches=True,no_sensor_executor_constructed=True,no_semantic_production=True,fresh=fresh)
(root/'fresh-verification.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
