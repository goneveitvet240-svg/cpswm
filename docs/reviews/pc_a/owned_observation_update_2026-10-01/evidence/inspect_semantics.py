import sys,json
from pathlib import Path
sys.path[:0]=[str(Path.cwd()/p) for p in ('src','tests','tools')]
import torch
torch.set_num_threads(2)
from test_owned_position_update import make_case,collect,advance,checkpoints
root=Path('/private/tmp/cpswm-owned-observation-evidence-20261001/inspect-semantics'); root.mkdir(exist_ok=True)
class Factory:
 def mktemp(self,name):
  p=root/name;p.mkdir(exist_ok=True);return p
pins=checkpoints.__wrapped__(Factory())
c=make_case(root/'state.db',pins)
try:
 s=c['stream'];core=s._system.core
 cmd,_,_=collect(c);s.consume_owned_position_observation(cmd.action_id)
 advance(c,2)
 def event(e): return {'record':str(e.source_record_id),'revision':str(e.revision_id),'time':str(e.evidence.event_time),'belief':str(e.belief_snapshot_id)}
 info={'configured':c['config'],'selected':c['native_selected_record_id'],
  'sources':[{'after':str(v.transition.after.metadata.record_id),'before':str(v.transition.before.metadata.record_id) if v.transition.before else None,'revision':str(v.history_after.latest.revision_id),'time':str(v.transition.after.detection_time)} for v in core._particle_workspace.posterior_sources.values()],
  'committed':[event(e) for e in core._committed_events.values()],
  'observed':[event(e)|{'bindings':str(core.published_revision_bindings(rid))} for rid,e in core._observed_events.items()]}
 (root/'inspection.json').write_text(json.dumps(info,indent=2)+'\n');print(json.dumps(info,indent=2))
finally:c['store'].close()
