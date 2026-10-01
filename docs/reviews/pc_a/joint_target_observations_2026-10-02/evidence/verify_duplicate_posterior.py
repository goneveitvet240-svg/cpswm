"""Inspect actual accepted batches after three identical owned sensor captures."""
import json
import sys
from pathlib import Path
import numpy as np
from test_temporal_target_position import SOURCE
from cpswm.system.continuous_state_store import ContinuousStateStore
from cpswm.system.native_joint_replay import consumed_schedule
from cpswm.system.reproducibility import content_sha256

store = ContinuousStateStore(Path(sys.argv[1]), source_identity=SOURCE, dependency_identity=content_sha256(sys.version))
try:
    saved = store.load()
    workspace = saved['fields']['_system'].core._particle_workspace
    updates = [u for u in consumed_schedule(workspace) if u.context.observation_update is not None]
    assert len(updates) == 3
    states = []
    for context in [updates[1].context, updates[2].context, None]:
        evidence = workspace.previous_weight_evidence(workspace.batch) if context is None else context.previous_weight_evidence
        weights, aggregate = evidence.normalized_logs()
        rows = []
        for key, weight in weights.items():
            record = workspace.records[key]
            stats = record.statistics
            rows.append((record.state.instance_association_key, weight, np.asarray(stats.information).ravel().tolist(), list(stats.information_vector), list(stats.alpha), np.asarray(stats.a).ravel().tolist(), list(stats.b)))
        states.append((sorted(rows), aggregate))
    for value in states[1:]:
        assert len(value[0]) == len(states[0][0]) and np.isclose(value[1], states[0][1], rtol=0, atol=1e-12)
        for a,b in zip(value[0], states[0][0], strict=True):
            assert a[0] == b[0]
            for x,y in zip(a[1:], b[1:], strict=True):
                np.testing.assert_allclose(x,y,rtol=0,atol=1e-12)
    print(json.dumps(dict(status='PASSED',captures=3,checked='actual normalized log weights, aggregate, Gaussian information/vector, Dirichlet and RLS parameters',tolerance=1e-12)))
finally:
    store.close()
