# Independent review round 1

Reviewer: semantic_review_round1 (independent subagent).

Initial reviewed source: `269b87374474f8f10eb9f54816b1f948fc199436`, base `a41e3a5`.
Scope: all nine changed production, CLI and test files, and adjacent conditional arithmetic, pose geometry, joint posterior consumer and durable observation dispatch boundaries. No production/test files were modified by this reviewer. The three additional probes in this directory are synthetic/component tests only.

## Evidence and source binding

The original three test modules passed (20 tests). A subsequent 23-test run in the shared worktree passed, but the working tree changed during review; that run is NOT used as fixed-source evidence.

The reviewer independently exported `git archive 269b87374474f8f10eb9f54816b1f948fc199436` to `/private/tmp/cpswm-semantic-round1-frozen-269b873`, copied the three independent probes to its tests directory, and reran with a separate fresh `PYTHONPYCACHEPREFIX`. Result: **23 passed in 4.87 seconds**. The first attempt to import probes from the other worktree was rejected by the existing foreign-entry bootstrap; moving the probe into the frozen export resolved that expected source isolation failure.

```sh
PYTHONPATH=src:tests PYTHONPYCACHEPREFIX=/private/tmp/cpswm-round1-archive-pyc /private/tmp/cpswm-pc-a-semantic-production-20260915/.venv/bin/python -m pytest -q -o addopts='' tests/test_pose_observation_model.py tests/test_proposal_learning.py tests/test_joint_camera_policy.py tests/test_independent_round1_probes.py
```

Independent additions checked:

1. A known non-diagonal 6D error transform retains off-diagonal covariance and gives the analytic held-out Gaussian density.
2. A READY posterior-selected observation command survives persistence/recovery, preserves its native belief hash, executes once, and rejects repeat dispatch.
3. The compatible-set objective agrees with a direct probability calculation using normalized softmax outputs and backpropagates through both selected logits and their normalizers.

## Findings within this review

No independently reproduced production defect in the exercised scope. This is partial component coverage, not a whole-project approval. The second independent reviewer subsequently reported three additional defects to the main agent; this review's initial green matrix does not invalidate them or close their repair obligations.

The implementation uses full native joint atoms for action value and binds the problem to their source hash. It rejects unknown raw dependencies, stale decision inputs, and no-value actions rather than silently issuing a fixed scan. Existing recovery and correction tests establish recomputation of the retained conditional sufficient statistics and persistence of the same issued command.

The pose model is a local additive measurement error model. Its covariance fit and held-out likelihood arithmetic work on exercised fixtures; this does not establish empirical calibration, orientation multimodality handling, or a pixel-to-pose estimator. Other conditional block weights remain supplied by a separate model.

The proposal loss binds six proposal-operation values, parent and seven axes through the existing nine-factor ordering. The supplied values must already be selected conditional log probabilities of the complete generative model. The function itself does not implement that generator or certify the training distribution.

## Open capability boundaries

- `PoseConditionalHistory` is currently reached only by tests; the pose-fitting CLI reaches `GaussianPoseObservationModel`. No default natural person/object producer calls the conditional history into the unified native runtime. Returning the existing conditional-state type establishes compatibility, not end-to-end production consumption.
- The loss is exercised by tests; no actual architecture, sampler, trained weights or training results are delivered by this patch.
- `prepare_posterior_observation` is a production entry point used by fixtures. The test prepares a native posterior with explicit fixture candidates and likelihood/utility tables. No independently calibrated outcome model is provided.
- The camera test executes and admits a new raw observation, but does not advance that feedback through real semantic inference, retract a mistaken memory, and demonstrate a changed next decision within the same run.
- No natural semantic candidate production, real calibration, Task 7 five-arm comparison, full-lifecycle cost comparison or external B-machine acceptance follows from this review.

## Final shared-source repair revalidation

Final reviewed production/test source: **`0e3848f48f75cfed3d685e7b9a3e16856c277b98`**. The initial review above is retained as historical evidence; this section binds the repaired batch to the same final source supplied to both independent reviewers.

The reviewer read the complete repair diff and independently exported this commit to `/private/tmp/cpswm-semantic-round1-frozen-0e3848f`. The three independent probes were copied into this export's test directory; production files came exclusively from the archived commit. A separate new bytecode-cache prefix was used. Command:

```sh
PYTHONPATH=src:tests PYTHONPYCACHEPREFIX=/private/tmp/cpswm-round1-final-0e3848f-pyc /private/tmp/cpswm-pc-a-semantic-production-20260915/.venv/bin/python -m pytest -q -o addopts='' tests/test_pose_observation_model.py tests/test_proposal_learning.py tests/test_joint_camera_policy.py tests/test_independent_round1_probes.py
```

Result: **26 passed in 5.70 seconds** (23 permanent batch tests, including the three repair regressions, plus this reviewer's three probes).

Repair assessment:

- Posterior-tagged observation dispatch recomputes the model choice against the current native joint view and compares action, degrees and raw dependencies before calling the executor. It holds the core execution lock throughout the decision check and dispatch. The wrong-action regression confirms the executor is not called, and the independent READY-command recovery probe still executes the legitimate selected action once.
- Pose reference compatibility now uses the existing physical residual calculation, preserving object, epoch and frame constraints while accepting quaternion sign equivalence. Its new legal-input regression and the existing incompatible-input/atomicity cases pass.
- Pose-label differences and evaluation metric arithmetic reject overflow/nonfinite results. The finite-large-input regression rejects the invalid evaluation, while the independent non-diagonal covariance test still reproduces the finite analytic likelihood.

**Disposition: this batch's exercised component paths and the three specified repairs pass independent round-1 revalidation on the final source.** No additional reproducible defect was found within that scope. This is not complete semantic-loop acceptance, empirical calibration, training completion, formal comparison acceptance, or independent Windows/B-machine acceptance. The open capability boundaries listed above remain unchanged.


### Evidence packaging note (A, after review)

The independently executed probe is archived verbatim as `test_independent_probes.py.txt` to preserve its exact bytes. To repeat the historical commands above, copy this artifact to a temporary directory as `test_independent_probes.py`; keep `PYTHONPATH` pointing to the selected fixed source and tests. No test assertion or production source changed during packaging. SHA256: `ac4956597534aa2370fc8b6540f0a374ea12bc0d2c8026426f9236458fe0f69e`. The pre-packaging probe has formatting/unused-variable lint findings; those archival findings do not alter its test results.
