"""Controlled montage, real pinned detector, two actual Native transactions."""
import json
import sys
from pathlib import Path
import torch
from test_native_neural_production import checkpoints
from test_temporal_target_position import make_case, capture
from test_appearance_geometry_position import MontageCamera

root=Path(sys.argv[1]);root.mkdir()
class Factory:
    def mktemp(self,name):
        p=root/name;p.mkdir();return p

torch.set_num_threads(2)
case=make_case(root/'state.db',checkpoints.__wrapped__(Factory()),Path('/private/tmp/cpswm-natural-candidate-evidence-20261001/ssdlite.pth'))
report=dict(status='RUNNING',scope='controlled montage and depth, real pinned detector and Native transactions; not natural multi-object task success',steps=[])
try:
    stream=case['stream'];camera=MontageCamera(stream._scope)
    for i in range(2):
        capture(case,camera)
        d=case['candidate'].last_diagnostic
        known=[b for b in d['branches'] if b['instance']!='unknown_instance']
        assert len(known)>=2 and len({b['query_id'] for b in known})==len(known)
        workspace=stream._system.core._particle_workspace
        assert len(workspace.batch.particle_weights)==len(known)+2
        assert workspace.batch.unresolved_probability>0
        known_keys={b['particle_id'] for b in known}
        assert all(w.posterior_probability>0 for w in workspace.batch.particle_weights if str(w.particle_id) in known_keys)
        if i:
            assert all(b['position_log_ratio']==0 for b in d['branches'])
        report['steps'].append(dict(index=i,known_hypotheses=len(known),diagnostic=d,view=stream.current_joint_decision_view().content_sha256))
    report.update(status='PASSED',captures=camera.calls)
finally:
    (root/'result.json').write_text(json.dumps(report,indent=2,default=str))
    print(json.dumps({k:v for k,v in report.items() if k!='steps'}))
    case['store'].close()
