"""New public-boundary probes; no production state injection or code substitution."""
from dataclasses import replace
import json
from pathlib import Path
import sys
from uuid import UUID, uuid4

root = Path(sys.argv[1]).resolve()
sys.path[:0] = [str(root/'src'), str(root/'tests')]
import test_structure_two_formal_revision_lineage as old
from test_structure_two_w3_native_particles import candidates
from test_structure_two_w3_round5_boundaries import direct_outcome
from cpswm.system.reproducibility import content_sha256
from cpswm.system.evaluation_operations.structure_two_selected_method import ParticleRevisionReceipt

def probe(kind):
    core = old._legacy_history(1).system.core
    args = candidates(core)
    first = args['receipts'][0]
    pid = first.proposal.proposed_state.particle_id
    if kind in ('foreign_location', 'alpha_overflow'):
        analytic = args['statistics'][pid]
        analytic = replace(analytic, **({'locations':tuple(UUID(int=90000+i) for i in range(4))} if kind == 'foreign_location' else {'alpha':(1e308,)*4}))
        args['statistics'][pid] = analytic
        raw = first.model_dump()
        raw['proposal']['proposed_state']['statistic_state_ref'] = analytic.reference
        args['receipts'] = (ParticleRevisionReceipt.model_validate(raw), args['receipts'][1])
    if kind in ('foreign_posterior', 'weight_overflow'):
        raw = first.model_dump()
        if kind == 'foreign_posterior':
            raw.update(evidence_semantics='posterior_projection_not_likelihood', source_posterior_snapshot_id=uuid4(), posterior_projection_log_factor=10.0)
        else:
            raw['proposal']['proposal_log_probability'] = -1e308
            raw['observation_log_likelihood'] = 1e308
        args['receipts'] = (ParticleRevisionReceipt.model_validate(raw), args['receipts'][1])
    before_ledger = content_sha256(core._hybrid_loop.ledger.export_state())
    before_action = core.action_location_distribution(core.current_snapshot)
    before = core._execution_observable_state_sha256()
    result = {'case':kind, 'source': str(sys.modules[type(core).__module__].__file__)}
    try:
        batch = core.stage_prepared_particle_candidates(**args)
        dist, unresolved = core.prepared_particle_location_marginal()
        result.update(status='RETURNED', weights=[p.posterior_probability for p in batch.particle_weights], probabilities={str(k):v for k,v in dist.items()}, unresolved=unresolved, total=sum(dist.values())+unresolved, outside_support=[str(k) for k in dist if k not in core.locations], claimed_posterior_source=str(args['receipts'][0].source_posterior_snapshot_id), current_snapshot=str(core.current_snapshot.snapshot_id))
    except Exception as error:
        result.update(status='REJECTED', error=f'{type(error).__name__}: {error}', state_unchanged=core._execution_observable_state_sha256()==before)
    result.update(ledger_unchanged=content_sha256(core._hybrid_loop.ledger.export_state())==before_ledger, default_action_unchanged=core.action_location_distribution(core.current_snapshot)==before_action)
    return result

def direct_rollback():
    probe = old._legacy_history()
    core = probe.system.core
    target = list(core._committed_events)[3]
    result = direct_outcome(core,target,False,core._committed_events[target].owner_mass)
    before = core._execution_observable_state_sha256()
    identities = (id(core._hybrid_loop.ledger), id(core._automatic_regimes.ccrr), id(core._automatic_regimes.bocpd), id(core._particle_workspace))
    try:
        core.apply_event_revision_outcome(result)
        status='RETURNED'
    except ValueError as error:
        status=str(error)
    return {'status':status, 'complete_observable_unchanged':core._execution_observable_state_sha256()==before, 'operator_instances_unchanged':identities==(id(core._hybrid_loop.ledger), id(core._automatic_regimes.ccrr), id(core._automatic_regimes.bocpd), id(core._particle_workspace)), 'old_still_committed':target in core._committed_events, 'new_absent':result.corrected_revision_id not in core._observed_events}

print(json.dumps({'direct_rollback':direct_rollback(), 'prepared':[probe(k) for k in ('control','foreign_location','alpha_overflow','foreign_posterior','weight_overflow')]},indent=2,allow_nan=False))
