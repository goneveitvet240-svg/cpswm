"""Read real archived posterior before loading any evaluator-only geometry.

Retrospective readout diagnostic, not a predeclared matched-task experiment.
"""
import argparse
import json
import importlib.util
import shutil
import sys
from pathlib import Path
from uuid import UUID

import torch
import numpy as np
from cpswm.perception_mapping.unity_rgbd import decode_unity_rgbd
from cpswm.system.native_joint_replay import consumed_schedule
from run_correction_replay_comparison import OracleProducer
from test_owned_rgbd_support import RGBDSupportDecoder
from test_temporal_target_position import SOURCE, association_joint

from cpswm.system.continuous_state_store import ContinuousStateStore
from cpswm.system.reproducibility import content_sha256, content_uuid
from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput
# Readout sidecar is explicit; inference may run on its original frozen source.
report_path = Path(__file__).resolve().parents[5] / 'src/cpswm/system/target_position_report.py'
spec = importlib.util.spec_from_file_location('cpswm.system.target_position_report', report_path)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
from cpswm.system.target_position_report import (
    EvaluationTruth, ReportTask, assess_report, report_from_view, verify_report, report_owned_temporal_target,
)


def run(source, output, evaluator_instance):
    output.mkdir(parents=True, exist_ok=False)
    config = json.loads((source / 'restore.json').read_text())
    shutil.copy2(source / 'copy.db', output / 'copy.db')
    store = ContinuousStateStore(output / 'copy.db', source_identity=SOURCE,
                                 dependency_identity=content_sha256(sys.version))
    def forbidden(*args):
        raise AssertionError('readout cannot rerun semantic P5')
    try:
        stream = ContinuousEvidenceInput.resume(
            store, producer=OracleProducer(), context_builder=forbidden,
            joint_producer=association_joint(config), observation_decoder=RGBDSupportDecoder(),
        )
        before = store._db.execute('SELECT * FROM checkpoint').fetchall()
        view = stream.current_joint_decision_view()
        producer = stream._joint_producer._candidate_model
        captures = producer._captures
        ids = tuple(UUID(k) for c in captures for k in c.packet['observation_ids'])
        schedule = [u.context for u in consumed_schedule(stream._system.core._particle_workspace)
                    if u.context is not None and u.context.observation_update is not None]
        context = schedule[-1]
        lookup = {str(r.envelope().identity.observation_id):r for r in context.visible_prefix}
        camera, _ = decode_unity_rgbd(tuple(lookup[k] for k in captures[-1].packet['observation_ids']),
                                    cutoff=captures[-1].received_at)
        task = ReportTask(
            task_id=content_uuid('retrospective-report-readout', view.content_sha256),
            scene_id=camera.scene_sha256, frame_id=camera.world_frame,
            target_description='previous bottle diagnostic; controlled initial semantic anchor',
            valid_at=camera.capture_time,
            initial_input_sha256=captures[0].packet['raw_sha256'],
            allowed_actions_sha256=content_sha256('archived RotateRight 30deg; no new actions'),
            action_budget=4, position_origin_m=(0., 0., 0.),
        )
        reports = [report_owned_temporal_target(stream, task, particle_id=a.particle_id)
                   for a in view.atoms]
        for report in reports:
            verify_report(task, view, report, observation_ids=ids)
        winner = max([(a.probability, str(a.particle_id), a.particle_id) for a in view.atoms]
                     + [(view.unresolved_probability, str(view.unresolved_id), view.unresolved_id)])
        selected = report_from_view(task, view, particle_id=winner[2], observation_ids=ids)
        public = dict(task=task.model_dump(mode='json'),
                      reports=[r.model_dump(mode='json') for r in reports],
                      selected_classification_baseline=selected.model_dump(mode='json'),
                      all_probabilities={str(a.particle_id):a.probability for a in view.atoms},
                      unresolved_probability=view.unresolved_probability,
                      anchor_mapping=producer._branches)
        (output/'public-reports.json').write_text(json.dumps(public,indent=2))
        # The inference/readout above never receives this evaluator metadata.
        annotation_path=source/'transport/evaluator_only/sdk-events/004.json'
        annotation=json.loads(annotation_path.read_text())
        obj=next(o for o in annotation['metadata']['objects'] if o['objectId']==evaluator_instance)
        corners=obj['axisAlignedBoundingBox']['cornerPoints']
        lower=tuple(min(p[i] for p in corners) for i in range(3))
        upper=tuple(max(p[i] for p in corners) for i in range(3))
        scores=[]
        for report in reports:
            truth = None if report.status!='reported' else EvaluationTruth(
                task_sha256=task.digest, report_sha256=report.digest,
                annotation_artifact_sha256=content_sha256(annotation),
                target_instance_id=evaluator_instance,
                reported_instance_id=None, lower_m=lower, upper_m=upper,
            )
            scores.append(assess_report(task,report,truth).model_dump(mode='json'))
        assert store._db.execute('SELECT * FROM checkpoint').fetchall()==before
        first = schedule[0]
        weights, _ = first.previous_weight_evidence.normalized_logs()
        parents = [r for r in first.records if r.state.particle_id in weights
                   and r.state.instance_association_key!='unknown_instance']
        model = config['models']['position_model']
        h = np.c_[np.eye(3),np.zeros((3,3))]
        rho = config['config']['shared_fraction']
        stationary = []
        for parent in parents:
            j = np.asarray(parent.statistics.information)
            b = np.asarray(parent.statistics.information_vector)
            for anchor, measurements in producer.last_diagnostic['sequence']['history'].items():
                y = np.asarray(measurements[0]['world_point_m'])-np.asarray(model['bias'])
                rows=[]
                for n in (1,2,4,10,100):
                    eff=n/(1+(n-1)*rho)
                    noise_inverse=eff*np.linalg.inv(np.asarray(model['covariance']))
                    mean=np.linalg.solve(j+h.T@noise_inverse@h,b+h.T@noise_inverse@y)[:3]
                    rows.append(dict(n=n,effective_iid_count=eff,mean_m=mean.tolist()))
                noise_inverse=np.linalg.inv(rho*np.asarray(model['covariance']))
                limit=np.linalg.solve(j+h.T@noise_inverse@h,b+h.T@noise_inverse@y)[:3]
                stationary.append(dict(parent=str(parent.state.particle_id),anchor=anchor,
                    prior_mean_m=np.linalg.solve(j,b)[:3].tolist(),
                    prior_precision=j.tolist(),measured_point_m=y.tolist(),
                    repeated_near_stationary_measurement=rows,limit_mean_m=limit.tolist(),
                    limit_in_target_aabb=all(lo<=x<=hi for x,lo,hi in zip(limit,lower,upper))))
        result=dict(
            status='READOUT_VERIFIED', scope='retrospective geometry diagnostic only',
            posterior_sha256=view.content_sha256, database_unchanged=True, new_actions=0,
            evaluator_target=evaluator_instance, lower_m=lower, upper_m=upper,
            natural_identity_adjudicated=False,
            stationary_model_diagnostic=stationary,
            stationary_diagnostic_scope='hypothetical distinct correlated captures of same point; byte-identical captures would add no evidence',
            selected_classification_baseline=next((s for s in scores if s['report_sha256']==selected.digest),assess_report(task,selected,None).model_dump(mode='json')),
            all_hypothesis_scores=scores,
        )
        (output/'result.json').write_text(json.dumps(result,indent=2))
        print(json.dumps(result),flush=True)
    finally:
        store.close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--evaluator-instance',required=True)
    args=p.parse_args();torch.set_num_threads(2)
    run(args.source,args.output,args.evaluator_instance)
