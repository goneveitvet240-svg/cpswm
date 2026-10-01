"""Fresh-interpreter recovery of initial-anchor and middle-capture withdrawals."""
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID
import torch
from test_temporal_target_position import SOURCE, association_joint
from test_owned_position_update import semantic_state
from test_owned_rgbd_support import RGBDSupportDecoder
from run_correction_replay_comparison import OracleProducer
from cpswm.data_preflight.typed_proposal_networks import ARMS
from cpswm.system.continuous_state_store import ContinuousStateStore
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput
from cpswm.system.structure_two_joint_consumption import JointDecisionView

def recover(folder):
    config=json.loads((folder/'restore.json').read_text())
    store=ContinuousStateStore(folder/'copy.db', source_identity=SOURCE, dependency_identity=content_sha256(sys.version))
    def forbidden(*args): raise AssertionError('recovery cannot rerun semantic P5')
    try:
        stream=ContinuousEvidenceInput.resume(store,producer=OracleProducer(),context_builder=forbidden,joint_producer=association_joint(config),observation_decoder=RGBDSupportDecoder())
        assert stream.current_joint_decision_view().content_sha256==config['expected_view']
        assert semantic_state(stream)==config['expected_semantic']
        rows=store._db.execute('SELECT * FROM checkpoint').fetchall()
        try: stream.consume_owned_position_observation(UUID(config['withdrawn_action']))
        except ValueError as e: assert 'withdrawn' in str(e)
        else: raise AssertionError('withdrawn capture regained authority')
        assert store._db.execute('SELECT * FROM checkpoint').fetchall()==rows
        assert len(stream._position_withdrawals)==config['withdrawals']
        result=dict(status='PASSED',view=stream.current_joint_decision_view().content_sha256,withdrawals=config['withdrawals'],retained_captures=len(stream._joint_producer._candidate_model.consumed_keys),withdrawn_reconsumption_rejected=True,new_physical_actions=0)
        (folder/'fresh.json').write_text(json.dumps(result,indent=2))
        print(json.dumps(result),flush=True)
    finally: store.close()

def prepare(root,r1):
    root.mkdir()
    for index in (0,1):
        folder=root/str(index);folder.mkdir()
        store=ContinuousStateStore(r1/f'test_capture_withdrawal_recomp{index}'/'state.db',source_identity=SOURCE,dependency_identity=content_sha256(sys.version))
        try:
            fields=store.load()['fields'];core=fields['_system'].core;w=core._particle_workspace
            args=w.raw_candidate_profile['arguments'];models={k:v for k,v in args.items() if k!='configuration'}
            view=JointDecisionView.from_batch(runtime_id=w.runtime_id,expected_snapshot_id=core.current_snapshot.snapshot_id,batch=w.batch,records=w.records)
            config=dict(config=args['configuration'],models=models,checkpoint=str(r1/'native-neural-checkpoints0'/ARMS[1]),pin=fields['_joint_producer_state']['last_evidence'].manifest_sha256,expected_view=view.content_sha256,expected_semantic=semantic_state(SimpleNamespace(_system=fields['_system'],_advanced=fields['_advanced'])),withdrawals=len(fields['_position_withdrawals']),withdrawn_action=str(next(iter(fields['_position_withdrawals']))))
            (folder/'restore.json').write_text(json.dumps(config,indent=2))
            with sqlite3.connect(folder/'copy.db') as db:store._db.backup(db)
        finally:store.close()
        result=subprocess.run([sys.executable,__file__,'recover',str(folder)],env=dict(os.environ,PYTHONHASHSEED='73119'),capture_output=True,text=True,timeout=180)
        (folder/'child.log').write_text(result.stdout+result.stderr)
        assert result.returncode==0,(folder/'child.log').read_text()
        print(result.stdout,flush=True)

if __name__=='__main__':
    torch.set_num_threads(2)
    if sys.argv[1]=='recover':recover(Path(sys.argv[2]))
    else:prepare(Path(sys.argv[2]),Path(sys.argv[3]))
