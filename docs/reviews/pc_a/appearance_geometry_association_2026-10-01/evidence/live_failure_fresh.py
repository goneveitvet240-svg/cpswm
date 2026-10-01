import hashlib,json,shutil,sys
from pathlib import Path
import torch
from test_appearance_geometry_position import SOURCE, association_joint
from test_owned_position_update import semantic_state
from test_owned_rgbd_support import RGBDSupportDecoder
from run_correction_replay_comparison import OracleProducer
from cpswm.system.continuous_state_store import ContinuousStateStore
from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_particle_workspace import native_content_sha256

torch.set_num_threads(2)
root=Path('/private/tmp/cpswm-appearance-geometry-evidence-20261001/live-small-view')
original=root/'state.sqlite'
before=hashlib.sha256(original.read_bytes()).hexdigest()
shutil.copy2(original,root/'copy.db')
# The three launchers use identical pinned fixture models/configuration. Use the
# failed run's own checkpoint bytes, never a replacement trained checkpoint.
config=json.loads((root.parent/'live/restore.json').read_text())
checkpoint=root/'native-neural-checkpoints'/Path(config['checkpoint']).name
config.update(checkpoint=str(checkpoint),pin=hashlib.sha256((checkpoint/'manifest.json').read_bytes()).hexdigest())
joint=association_joint(config)
store=ContinuousStateStore(root/'copy.db',source_identity=SOURCE,dependency_identity=content_sha256(sys.version))
def unused_builder(*args): raise AssertionError('fresh failure audit cannot rerun semantic P5')
try:
 stream=ContinuousEvidenceInput.resume(store,producer=OracleProducer(),context_builder=unused_builder,joint_producer=joint,observation_decoder=RGBDSupportDecoder())
 history=stream.observation_history()
 assert len(history)==2 and all(delivery.success for _,delivery in history)
 assert not stream._position_consumptions
 view=stream.current_joint_decision_view().content_sha256
 semantic=semantic_state(stream)
 producer_state=native_content_sha256(joint.checkpoint_state())
 saved=store._db.execute('SELECT * FROM checkpoint').fetchall()
 try:
  stream.consume_owned_position_observation(history[-1][0].action_id)
 except ValueError as error:
  assert str(error)=='natural position unavailable: no_detection_candidates'
 else: raise AssertionError('empty real frame unexpectedly consumed')
 assert view==stream.current_joint_decision_view().content_sha256
 assert semantic==semantic_state(stream)
 assert producer_state==native_content_sha256(joint.checkpoint_state())
 assert saved==store._db.execute('SELECT * FROM checkpoint').fetchall()
 assert not stream._position_consumptions and stream.observation_history()==history
 assert before==hashlib.sha256(original.read_bytes()).hexdigest()
 report=dict(status='expected_failure_verified',source_sha='5a4e3a0660114b3e7bc5b2482f4d49456b825239',real_deliveries_retained=2,consumed_queries=0,posterior_unchanged=True,semantic_unchanged=True,producer_unchanged=True,sqlite_unchanged=True,original_database_sha256=before,original_database_unchanged=True,error='no_detection_candidates',view=view)
 (root/'fresh-verification.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report))
finally: store.close()
