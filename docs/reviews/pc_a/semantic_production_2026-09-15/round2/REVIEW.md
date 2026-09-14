# Independent review round 2 — semantic production preparation

Initial fixed source: `269b87374474f8f10eb9f54816b1f948fc199436`; base `a41e3a5`.
Reviewer inspected the nine-file production/test diff and relevant existing consumers. No round-1 result was read. This is an independent component review, not B-machine acceptance or complete semantic-loop acceptance.

## Initial result: changes required

1. **P1 — complete counterfeit model-decision reason can dispatch the opposite action.** `ContinuousEvidenceInput.execute_observation` validates `JointCameraProblem.source_belief_sha256` but does not verify that the command's action, degrees and source IDs correspond to the model's selected alternative. The public fixed-camera issuer accepts an arbitrary `joint-ciav@1:` reason. The probe obtains a valid current problem that selects RotateLeft, issues RotateRight through `prepare_observation` with that complete problem as the reason, and observes successful dispatch. No private-state mutation or forged command identity is needed. Recompute and bind the decision before dispatch, or reserve the provenance tag behind a separately recorded issuer capability.
2. **P2 — equivalent quaternion references rejected.** `PoseConditionalHistory._rebuild` compares Pydantic reference equality, despite calibration chart/residual code explicitly treating q and -q as equivalent. Replacing the reference quaternion with its sign inverse rejects a physically identical valid input before consumption. Compare normalized physical reference, preserving object/frame/epoch/translation requirements.
3. **P2 — finite held-out inputs can produce nonfinite calibration metrics.** `GaussianPoseObservationModel.evaluate` accepts finite translation 1e200 and returns infinite NLL, squared Mahalanobis and position RMSE after multiplication/square overflow. Reject nonfinite statistics before returning/writing a report; fitting already has a related guard.

## Reproduction and actual coverage

Probe file: `test_independent_round2.py` in this directory.

```
PYTHONPATH=src:tests .venv/bin/python -m pytest -q tests/test_joint_camera_policy.py tests/test_pose_observation_model.py tests/test_proposal_learning.py docs/reviews/pc_a/semantic_production_2026-09-15/round2/test_independent_round2.py --tb=short
```

Initial run with the first three independent probes: **21 passed / 2 failed**. Existing tests all passed. Failures: opposite-action reason forgery; equivalent-quaternion reference.

Second run of six independent probes alone: **3 passed / 3 failed**. Third failure: finite held-out overflow. Passed: prepared model command survives durable recovery and executes; very large invalid RLS update leaves both state and retained inputs unchanged; actual nonuniform native posterior and prohibitively costly options produce no command. Recovery test executes only once after recovery using the owned command. Existing tests additionally cover post-dispatch duplicate rejection, source hash mismatch, no-information stop, unseen source IDs, three-block calculation, correction/retraction recomputation and full-target loss gradients.

Observed initial failure output:

```
test_forged_policy_reason_cannot_execute_opposite_decision: Failed: DID NOT RAISE ValueError
test_equivalent_quaternion_reference_accepted: ValueError: retained pose input changed reference, object or epoch
test_finite_heldout_pose_overflow_is_rejected: Failed: DID NOT RAISE ValueError
RuntimeWarning: overflow encountered in multiply (mahalanobis)
RuntimeWarning: overflow encountered in square (position_rmse_m)
```

## Limits

No independently authenticated real labels, pixel-to-role/pose producer, learned decoder/sampler, calibrated camera outcome model, real-environment semantic loop, scientific comparison, long-duration test or concurrent dispatch race was verified. The Gaussian fitting boundary explicitly reports unauthenticated sources; arbitrary strings/hashes here do not become evidence of real data. Existing fixtures use a manually staged native posterior; the action tests establish the decision/execution connection only. Repair-side tests cannot justify full training completion or method superiority.

A subsequent source SHA requires explicit fresh verification; the initial results above remain tied to the initial source.

## Final common-source re-verification

Fixed production/test source: **`0e3848f48f75cfed3d685e7b9a3e16856c277b98`**.

Independently exported this exact commit with `git archive` into `/private/tmp/cpswm-semantic-round2-fixed-ym7bsrfh`, copied only this reviewer's unchanged six-probe file into the export, and ran the exported source/tests with a fresh bytecode cache `/private/tmp/cpswm-semantic-round2-pycache-lvs4hmsn` and pytest cache provider disabled. Source imports used the export's `src` and `tests` directories; Python dependencies used the requested worktree `.venv`.

**29 passed in 6.44 seconds: 23 production regression cases + 6 independent review probes.** Exact command, paths, probe SHA256 and output are preserved in `final_fixed_source_verification.txt`.

Read the corrective source diff independently. Before dispatch, the runtime now retains the core execution lock, recomputes selection from the current native joint view and retained problem, and compares action, angle and source IDs. Equivalent reference orientation now goes through physical pose residual comparison while retaining object/frame/UTC-epoch checks. Calibration evaluation raises on floating-point overflow and rejects nonfinite returned metrics; label residual subtraction also rejects overflow.

All three initially reproduced defects are resolved on this common source. **No remaining blocking finding within the reviewed component scope.** The original failures above remain historical evidence, not the final result. This is the second independent component review of this batch; it does not establish complete real semantic-loop acceptance, full-backbone training completion, comparison superiority, or B-machine acceptance. Concurrency was addressed by source inspection of lock scope; no independent concurrent-thread stress test was run.


### Evidence packaging note (A, after review)

The independently executed probe is archived verbatim as `test_independent_round2.py.txt` to preserve its exact bytes. To repeat the historical commands above, copy this artifact to a temporary directory as `test_independent_round2.py`; keep `PYTHONPATH` pointing to the selected fixed source and tests. No test assertion or production source changed during packaging. SHA256: `98b143fbf26a5f5b764cf0f2be17faa9255b844894088c4114e5fee536d3f5fd`. The pre-packaging probe has formatting/unused-variable lint findings; those archival findings do not alter its test results.
