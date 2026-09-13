# B6 commands and immutable outcomes

All commands used `1d24099a025c9d7c00a59e4c78c593703924b0eb` source blobs in
`/workspace/scratch/b158d995e8cc/cpswm_b6_snapshot`.

## Remote and source identity

```bash
git fetch origin --prune
```

Exit 128 from the scratch root: it is not a Git worktree. GitHub connector reads independently
confirmed delivery commit `2a7a547fba30412d9349605aff3a7df7c60d6b3a` and actual code commit
`1d24099a025c9d7c00a59e4c78c593703924b0eb`. The recursive Git tree was recorded as
`REMOTE_TREE_MANIFEST.json`; all 313 materialized `src/` blobs matched it.

## Requested pytest command

```bash
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 OMP_NUM_THREADS=1 \
PYTHONPATH=src python -m pytest -o addopts= -p no:cacheprovider -q \
  tests/test_structure_two_joint_consumption_components.py \
  tests/test_structure_two_ciav.py \
  tests/test_structure_two_ciav_negative_observation_layers.py \
  tests/test_structure_two_w3_native_posterior_projection.py \
  tests/test_project_two_ciav_interactive_development.py \
  tests/test_project_two_ciav_break_even.py
```

Exit 1 before collection: `No module named pytest`. Raw output is in `PYTEST_UNAVAILABLE.log`.

## Direct compatibility execution

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 PYTHONPATH=src:tests:. \
python tools/b6_direct_test_runner.py \
  docs/reviews/pc_b/b6_joint_audit_2026-09-13/run_direct_01
```

Exit 0, 85 collected / 85 passed / 0 failed / 0 not run, 137.760 seconds. This is explicitly a
small compatibility runner, not pytest. It expands only the frozen parametrizations and fixture
surface used by these six modules. JSON and JUnit are preserved in `run_direct_01/`.

## Independent mathematical and adversarial audit

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 PYTHONPATH=src:tests:. \
python tools/b6_independent_adversarial_audit.py \
  docs/reviews/pc_b/b6_joint_audit_2026-09-13/run_adversarial_03
```

Exit 1 by design: 0 runner errors and four confirmed findings encoded as JUnit failures. JSON and
JUnit are preserved in `run_adversarial_03/`. Earlier `run_adversarial_01/` and
`run_adversarial_02/` remain preserved and are not the final evidence set; run 01 exposed the cold
import failure while the first runner ordering still prevented the remaining arithmetic checks.

