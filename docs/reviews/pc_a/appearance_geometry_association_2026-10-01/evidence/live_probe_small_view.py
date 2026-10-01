"""Targeted positive path after the separate 15/15 degree category-mismatch diagnostic; not a held-out evaluation."""
import json
from pathlib import Path
from datetime import datetime, UTC
import sys
import torch
from test_native_neural_production import checkpoints
from test_appearance_geometry_position import make_case
from test_owned_position_update import semantic_state, PositionCameraModel
from test_owned_position_delivery import problem_for
from cpswm.system.continuous_camera_collection import collect_posterior_step
from cpswm.system.unity_observation import UnityObservationExecutor
from cpswm.system.structure_two_particle_workspace import native_content_sha256

root = Path(sys.argv[1])
root.mkdir()
class Factory:
    def mktemp(self, name):
        path = root/name
        path.mkdir()
        return path

class Model(PositionCameraModel):
    def problem(self, *args, **kwargs):
        problem = super().problem(*args, **kwargs)
        return problem.model_copy(update={"alternatives": tuple(
            a.model_copy(update={"degrees":1.0 if kwargs["execution_history"] else 30.0}) for a in problem.alternatives
        )})

torch.set_num_threads(2)
models = checkpoints.__wrapped__(Factory())
case = make_case(root/'state.sqlite', models, Path('/private/tmp/cpswm-natural-candidate-evidence-20261001/ssdlite.pth'))
stream, camera = case['stream'], None
report = dict(source_sha=sys.argv[2], status='running', steps=[], scope='Actual RGB-D frame pair; uncalibrated association energy; controlled initial semantic anchor, actors, Gaussian/residual and camera utility. No task benefit claim.')
try:
    camera = UnityObservationExecutor(
        python=Path('/private/tmp/cpswm-ai2thor-owned-20261001/bin/python'),
        worker=Path('tools/unity_history_loop_worker.py').resolve(),
        binary=Path('/Users/pangwei/.ai2thor/releases/thor-OSXIntel64-f0825767cd50d69f666c7f282e54abfe58f1e917/thor-OSXIntel64-f0825767cd50d69f666c7f282e54abfe58f1e917.app/Contents/MacOS/AI2-THOR'),
        house=Path('docs/reviews/pc_a/sim_timing_control_2026-09-29/evidence/raw-examples/south-320-frozen-0/evaluator_house.json').resolve(),
        log_dir=root/'transport', household_id=stream._scope[0], session_id=stream._scope[1], trace_id=stream._scope[2],
        image_size=320, sensor_profile='rgbd_self_pose')
    semantic=semantic_state(stream)
    before=stream.current_joint_decision_view()
    for index in range(2):
        step=collect_posterior_step(stream,model=Model(stream),executor=camera,decision_time=datetime.now(UTC))
        report['steps'].append(dict(action_id=str(step.command.action_id), action=step.command.action,degrees=step.command.degrees,status=step.position_update_status,received_at=step.delivery.received_at.isoformat(),success=step.delivery.success))
        assert step.delivery.success
        if index==0:
            assert step.position_update_status=='REFERENCE_ONLY'
            assert stream.current_joint_decision_view()==before and not stream._position_consumptions
        else:
            assert step.position_update_status=='QUERY_CONSUMED'
    after=stream.current_joint_decision_view()
    assert semantic_state(stream)==semantic and after!=before and len(camera._seen)==2
    update=stream.consume_owned_position_observation(step.command.action_id)
    assert stream.current_joint_decision_view()==after
    problem=problem_for(stream,datetime.now(UTC))
    assert problem.source_belief_sha256==after.content_sha256
    plan,command=problem.select(after,stream._system.cause_information_planner)
    report.update(status='passed',semantic_unchanged=True,posterior_changed=True,reference_neutral=True,duplicate_inert=True,physical_dispatches=len(camera._seen),prior_sha=before.content_sha256,posterior_sha=after.content_sha256,update_sha=native_content_sha256(update),semantic=semantic,diagnostic=case['candidate'].last_diagnostic,next_plan=plan.model_dump(mode='json'),next_action=None if command is None else command.action,provenance=camera.provenance)
    (root/'restore.json').write_text(json.dumps(dict(config=case['config'],models=case['models'],checkpoint=str(case['checkpoint']),pin=case['pin'],action=str(step.command.action_id))))
except BaseException as exc:
    report.update(status='failed',error_type=type(exc).__name__,error=str(exc),physical_dispatches=0 if camera is None else len(camera._seen))
    raise
finally:
    (root/'result.json').write_text(json.dumps(report,indent=2,default=str)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in {'diagnostic','next_plan'}},default=str))
    if camera is not None: camera.close()
    case['store'].close()
