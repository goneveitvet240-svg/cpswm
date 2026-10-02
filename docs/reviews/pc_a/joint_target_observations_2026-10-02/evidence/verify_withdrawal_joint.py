"""Direct joint matrix check of the actual posterior after middle-frame withdrawal."""
import json
import sys
from pathlib import Path
import numpy as np
from test_temporal_target_position import SOURCE, fixture_models
from cpswm.system.continuous_state_store import ContinuousStateStore
from cpswm.system.native_joint_replay import consumed_schedule
from cpswm.system.reproducibility import content_sha256

store=ContinuousStateStore(Path(sys.argv[1]), source_identity=SOURCE, dependency_identity=content_sha256(sys.version))
try:
    saved=store.load(); fields=saved['fields']; workspace=fields['_system'].core._particle_workspace
    schedule=[u for u in consumed_schedule(workspace) if u.context.observation_update is not None]
    assert len(schedule)==2
    diagnostic=fields['_joint_producer_state']['candidate_state']['last_diagnostic']
    history=diagnostic['sequence']['history']; assert len(history)==1
    observations=next(iter(history.values())); assert len(observations)==2
    model=fixture_models()['position_model']
    y=np.asarray([o['world_point_m'] for o in observations])-np.asarray(model['bias'])
    h=np.tile(np.c_[np.eye(3),np.zeros((3,3))], (2,1))
    c=np.kron(.5*np.ones((2,2))+.5*np.eye(2),np.asarray(model['covariance']))
    first=schedule[0].context
    weights, aggregate=first.previous_weight_evidence.normalized_logs()
    parent=next(r for r in first.records if r.state.particle_id in weights and r.state.instance_association_key!='unknown_instance')
    j=np.asarray(parent.statistics.information); b=np.asarray(parent.statistics.information_vector)
    expected_j=j+h.T@np.linalg.solve(c,h); expected_b=b+h.T@np.linalg.solve(c,y.ravel())
    known=next(workspace.records[w.particle_id] for w in workspace.batch.particle_weights if workspace.records[w.particle_id].state.instance_association_key!='unknown_instance')
    np.testing.assert_allclose(known.statistics.information, expected_j, rtol=0,atol=1e-12)
    np.testing.assert_allclose(known.statistics.information_vector, expected_b,rtol=0,atol=1e-12)
    def density(z, mean, cov):
        d=z-mean
        return -.5*(len(z)*np.log(2*np.pi)+np.linalg.slogdet(cov)[1]+d@np.linalg.solve(cov,d))
    signal=density(y.ravel(),h@np.linalg.solve(j,b),c+h@np.linalg.solve(j,h.T))
    background=density(y.ravel(),np.zeros(6),c+np.kron(np.ones((2,2)),100*np.eye(3)))
    parent_log=weights[parent.state.particle_id]
    logs=np.array([parent_log+np.log(.8)+signal-background,parent_log+np.log(.2),*[v for k,v in weights.items() if k!=parent.state.particle_id],aggregate])
    probs=np.exp(logs-logs.max());probs/=probs.sum()
    actual=next(w.posterior_probability for w in workspace.batch.particle_weights if w.particle_id==known.state.particle_id)
    np.testing.assert_allclose(actual,probs[0],rtol=0,atol=1e-12)
    print(json.dumps(dict(status='PASSED',retained_captures=2,excluded_captures=1,known_probability=actual,direct_joint_probability=float(probs[0]),checked='actual Gaussian information, natural vector and posterior probability versus one full joint retained-prefix calculation',tolerance=1e-12)))
finally:
    store.close()
