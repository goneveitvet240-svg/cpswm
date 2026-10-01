"""Natural owned continuous transactions; controlled semantics and utility."""
import json
import sys
import sqlite3
from datetime import datetime, UTC
from pathlib import Path
import torch
from test_native_neural_production import checkpoints
from test_temporal_target_position import make_case
from test_owned_position_update import PositionCameraModel, semantic_state
from cpswm.system.continuous_camera_collection import collect_posterior_step
from cpswm.system.unity_observation import UnityObservationExecutor

root = Path(sys.argv[1]); root.mkdir()
class Factory:
    def mktemp(self, name):
        path = root/name; path.mkdir(); return path
class Model(PositionCameraModel):
    def problem(self, *args, **kwargs):
        p = super().problem(*args, **kwargs)
        angle = 30. if not self.stream._position_consumptions else 1.
        return p.model_copy(update={"alternatives": tuple(a.model_copy(update={"degrees":angle}) for a in p.alternatives)})
torch.set_num_threads(2)
case = make_case(root/'state.sqlite', checkpoints.__wrapped__(Factory()), Path('/private/tmp/cpswm-natural-candidate-evidence-20261001/ssdlite.pth'))
stream=case['stream']; camera=None
report=dict(source_commit='ccccacc8ced5245ee6c38b2466632bac37d37cd0', status='RUNNING', scope='Live RGB-D continuous Native transactions; controlled initial semantics, prior, residual, utility; not a task-benefit result.', steps=[])
try:
    camera=UnityObservationExecutor(python=Path('/private/tmp/cpswm-ai2thor-owned-20261001/bin/python'),worker=Path('tools/unity_target_sequence_worker.py').resolve(),binary=Path('/Users/pangwei/.ai2thor/releases/thor-OSXIntel64-f0825767cd50d69f666c7f282e54abfe58f1e917/thor-OSXIntel64-f0825767cd50d69f666c7f282e54abfe58f1e917.app/Contents/MacOS/AI2-THOR'),house=Path('docs/reviews/pc_a/sim_timing_control_2026-09-29/evidence/raw-examples/south-320-frozen-0/evaluator_house.json').resolve(),log_dir=root/'transport',household_id=stream._scope[0],session_id=stream._scope[1],trace_id=stream._scope[2],image_size=320,sensor_profile='rgbd_self_pose')
    semantic=semantic_state(stream)
    for i in range(4):
        prior=stream.current_joint_decision_view().content_sha256
        step=collect_posterior_step(stream,model=Model(stream),executor=camera,decision_time=datetime.now(UTC))
        if step.command is None:
            report['stop_plan']=step.plan.model_dump(mode='json')
            report['stopped_at_iteration']=i
            report['status']='STOPPED_BY_POLICY'
            break
        assert step.delivery.success
        last_action=step.command.action_id
        diagnostic=case['candidate'].last_diagnostic
        report['steps'].append(dict(index=i,action_id=str(step.command.action_id),degrees=step.command.degrees,position_status=step.position_update_status,prior=prior,posterior=stream.current_joint_decision_view().content_sha256,diagnostic=diagnostic))
        assert len(stream._position_consumptions)==i+1
        (root/'result.json').write_text(json.dumps(report,indent=2,default=str))
        print(json.dumps(dict(index=i,accepted=i+1,status=diagnostic['sequence']['records'][-1]['status'],counts=diagnostic['sequence']['records'][-1]['unique_position_counts'])),flush=True)
    assert semantic_state(stream)==semantic
    view=stream.current_joint_decision_view()
    stream.consume_owned_position_observation(last_action)
    assert stream.current_joint_decision_view()==view
    with sqlite3.connect(root/'copy.db') as db: case['store']._db.backup(db)
    (root/'restore.json').write_text(json.dumps(dict(config=case['config'],models=case['models'],checkpoint=str(case['checkpoint']),pin=case['pin'],action=str(last_action))))
    report.update(status='PASSED' if len(report['steps'])==4 else 'STOPPED_BY_POLICY',semantic_unchanged=True,duplicate_inert=True,physical_dispatches=len(camera._seen),semantic=semantic,final_view=view.content_sha256,provenance=camera.provenance)
except BaseException as e:
    report.update(status='FAILED',error_type=type(e).__name__,error=str(e))
    raise
finally:
    (root/'result.json').write_text(json.dumps(report,indent=2,default=str))
    if camera: camera.close()
    case['store'].close()
