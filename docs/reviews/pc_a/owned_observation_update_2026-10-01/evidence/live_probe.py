"""Live sensor transaction on explicit controlled identity/prior fixtures, not task benefit."""
import json
from pathlib import Path
from datetime import datetime, UTC
import torch
from test_native_neural_production import checkpoints
from test_owned_position_update import make_case, semantic_state, PositionCameraModel
from cpswm.system.continuous_camera_collection import collect_posterior_step
from cpswm.system.unity_observation import UnityObservationExecutor
from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput
from test_owned_rgbd_support import RGBDSupportDecoder
from test_owned_position_delivery import problem_for
from run_correction_replay_comparison import OracleProducer

root = Path('/private/tmp/cpswm-owned-observation-evidence-20261001/live')
root.mkdir()
class Factory:
    def mktemp(self, name):
        p = root / name
        p.mkdir()
        return p

torch.set_num_threads(2)
models = checkpoints.__wrapped__(Factory())
case = make_case(root / 'state.sqlite', models)
stream = case['stream']
camera = None
try:
    camera = UnityObservationExecutor(
        python=Path('/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv-ai2thor/bin/python'),
        worker=Path('tools/unity_history_loop_worker.py').resolve(),
        binary=Path('/Users/pangwei/.ai2thor/releases/thor-OSXIntel64-f0825767cd50d69f666c7f282e54abfe58f1e917/thor-OSXIntel64-f0825767cd50d69f666c7f282e54abfe58f1e917.app/Contents/MacOS/AI2-THOR'),
        house=Path('docs/reviews/pc_a/sim_timing_control_2026-09-29/evidence/raw-examples/south-320-frozen-0/evaluator_house.json').resolve(),
        log_dir=root/'transport', household_id=stream._scope[0],session_id=stream._scope[1],trace_id=stream._scope[2],
        image_size=320,sensor_profile='rgbd_self_pose')
    before=semantic_state(stream)
    prior=stream.current_joint_decision_view()
    step=collect_posterior_step(stream,model=PositionCameraModel(stream),executor=camera,decision_time=datetime.now(UTC))
    after=stream.current_joint_decision_view()
    assert step.delivery.success and len(camera._seen)==1
    assert before==semantic_state(stream) and after!=prior
    update=stream.consume_owned_position_observation(step.command.action_id)
    assert stream.current_joint_decision_view()==after
    resumed=ContinuousEvidenceInput.resume(case['store'],producer=OracleProducer(),context_builder=case['builder'],joint_producer=case['joint'],observation_decoder=RGBDSupportDecoder())
    assert resumed.current_joint_decision_view()==after
    next_problem=problem_for(resumed,datetime.now(UTC))
    assert next_problem.source_belief_sha256==after.content_sha256
    next_plan, next_option=next_problem.select(after,resumed._system.cause_information_planner)
    report=dict(next_plan=next_plan.model_dump(mode='json'),status='passed',source_sha='d84d570d0c12ec56d5f47f699f7211ffd99422b9',command=str(step.command.action_id),action=step.command.action,logical_key=update.logical_key,semantic_unchanged=True,posterior_changed=True,duplicate_inert=True,same_process_sqlite_resume=True,physical_dispatches=len(camera._seen),prior_sha=prior.content_sha256,posterior_sha=after.content_sha256,diagnostic=case['candidate'].last_diagnostic,provenance=camera.provenance,scope='Live RGB-D only; fixed 4x4 corner candidate, identity, prior, synthetic calibration and camera utility; not natural object localization or task benefit.')
    (root/'result.json').write_text(json.dumps(report,indent=2,default=str)+'\n')
    print(json.dumps(report,default=str))
finally:
    if camera is not None: camera.close()
    case['store'].close()
