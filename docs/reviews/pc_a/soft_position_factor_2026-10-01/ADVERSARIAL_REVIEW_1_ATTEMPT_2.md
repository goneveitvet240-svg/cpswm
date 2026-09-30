# Raw factor repair — adversarial review 1

**PASS within the bounded engineering scope below.** No new blocking defect was found against frozen SHA `37981c3c44475b0bcbeff3379dcf90be288c49c9`. This author-assisted A review permits the next sequential review; it is not B independent acceptance or permission to bypass R2.

- Worktree: `/private/tmp/cpswm-pc-a-soft-position-factor-20261001`.
- Source identity: all 894 Python files matched `frozen-source.json` before and after both executions; HEAD matched the frozen SHA and `git status --porcelain` was empty. Frozen-record SHA-256: `f03633c495247e93987b1bda316c3f83ea83813113c3ecba033ea142b0969e0c`.
- Reviewer involvement: this agent previously implemented the residual model and controlled numerical diagnostic, and authored some earlier tests. The raw owner-verification repair was implemented by another A agent. This is an auxiliary adversarial review with author overlap, not an independent account/machine review.
- No production, test, or tool source was edited during this review. No Unity process or real 96-frame experiment was started. All new evidence is under `RepairR1`; old `R1` originals remained byte-identical.

## Executed evidence

| Execution | Result | Evidence |
|---|---|---|
| Bounded native, numerical, recovery and action matrix | **49 passed in 322.59 s**, exit 0 | `RepairR1/formal-targeted-01.log` and `.json` |
| Current complete controlled CLI run | Exit 0; 4 fitted position models, 96 frames, 302 saved files | `RepairR1/CLI/legal-run-01.log` |
| Complete four-model and downstream numerical forgery, current CLI `--verify` | Exit 1, specifically `fresh trained outputs differ` after all 96 readouts and all 4 fits | `RepairR1/CLI/complete-forgery-rejected.log` |
| Legal fresh verification after the forgery | Exit 0; all 302 original output files unchanged | `RepairR1/CLI/legal-recovery-verify.log` |
| Re-signed candidate-deletion cache with original external frontend pin | Exit 1 at the historical subprocess's original ledger-pin check; original outputs and attack cache unchanged | `RepairR1/CLI/candidate-deletion-original-pin.log` and `.json` |

The actual current CLI exit sequence was **[0, 1, 0, 1]**. `RepairR1/CLI/final-result.json` records the source check, old-directory integrity, counts and outcomes. The four native/CLI commands are not added to the pytest count.

Commands were launched with the shared Python at `/private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python`. `OPENBLAS_NUM_THREADS=1` and absolute `PYTHONPATH` entries for this worktree's `src`, `tests`, and `tools` were used. The complete argv, cwd, environment, exit status, duration and log digest are retained in `formal-targeted-01.json`, `CLI/execution-cases.json`, `CLI/complete-forgery-cases.json` and `CLI/candidate-deletion-original-pin.json`.

Reproduction entry points:

```text
python SO/RepairR1/run_formal_targeted.py
python SO/RepairR1/prepare_cli_reuse.py
python SO/RepairR1/run_formal_cli.py
```

Here `SO` is `/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/output/soft-position-factor-20261001`; use the Python above. These runners preserve attempts and expect unused output names. The pytest runner explicitly supplies `-c /private/tmp/cpswm-pc-a-soft-position-factor-20261001/pyproject.toml -o addopts= -q` and the exact 13 target entries. Do not overwrite this sealed run when repeating it.

## Native acceptance and consequential outputs

The 49-case set consists of 12 external cases, all 18 cases in `test_native_raw_candidate_verification.py`, all 11 cases in `test_native_position_production.py`, and 8 parameter-expanded cases from the residual-matrix, model-pin, full-replay, neural-recovery, RGB-D ownership and posterior-projection tests.

1. **Original failure family:** complete known and unknown observation likelihood, aggregate unresolved mass, and transition-weight changes were tested under the original configured producer. The forged packet carries a coherent base proof and materialized receipts. The genuine neural checkpoint still verifies q; it no longer legitimizes changed target factors. The raw verifier rejects at `raw candidate base differs from complete owner recomputation`, before publication or state changes. The action harness separately exercises known-likelihood and aggregate attacks.
2. **All five sufficient-statistic blocks:** `information`, `information_vector`, `alpha`, `a`, and `b` were individually altered, references rebound, and q actually rescored through the pinned network. `actual_q_verified=true` precedes each rejection. Workspace, producer and ledger stay unchanged and the legal path recovers. These are numerical attacks, not merely malformed-shape or outer-hash checks.
3. **Original inputs and implementation:** depth, camera pose, complete rebound raw packets, altered context, wrong observation H, helper/producer implementation and loaded raw-verifier replacement are rejected under the original binding. Position-model bias and covariance substitutions remain valid under their own new pins and change results, but the original external model pin rejects them. The independent closed-form test checks pre-update Gaussian density and conditional update.
4. **Owner/source/cutoff and actual prior:** a genuine-network future-context proposal cannot acquire admission using a newly created foreign authority; direct stage rejects it. A three-step history with the observed frame selected at index 1 consumes once, later neutral steps retain weights/statistics, and record-dictionary reordering is harmless. Consumed state comes from actual predecessor sources. Profile, catalogue or proof deletion cannot downgrade a protected current/historical record to a legacy path.
5. **Current and historical action boundaries:** wrong current proposals do not yield a readable current decision or any camera call. After legal recovery through the ordinary collector, `RotateLeft` executes once; redispatch is rejected. For a fully rewritten noncurrent input body, proof, receipts and associated fingerprints, direct deep validation reaches the mathematical raw-recomputation rejection. Current reads, new command preparation and an already-READY command's collector dispatch all refuse the corrupted history; camera count remains zero. Restoring the original workspace permits that same READY command to execute once, without changing the semantic ledger.
6. **Normal collector positive path:** without manual posterior publication, a decision cutoff later than the initial P5 cutoff works when semantic inference returns `None`; one command is published and executed. Source tests also cover duplicate semantic output, genuinely empty initial source state, and rejection when an owned source was secretly removed. The earlier discovered collector regression is therefore directly rerun, not bypassed by manual publication.
7. **Persistence, replay and failure:** both a fresh-process persisted-configuration worker and a pure resume worker pass. The latter constructs no temporary `ContinuousEvidenceInput` and verifies runtime type registration, exact view/producer/workspace/ledger, idempotence, and the next neutral step. SQLite tests retain real weights and all statistics; retraction/full replay matches the no-factor state; partial-generation failure restores owned state. Injected raw-admission failure retains a durable pending P5 step and recovers without duplicating stored effects. Posterior projection still refuses recounting the same posterior under a new cluster.

The external cases' `result.json` files under `RepairR1/formal-targeted-01` record the precise rejection and consequences. In particular, the historical tests state `whole_descendant_history_resigned=false`; their direct deep-check result must not be inflated into a test of an entirely regenerated malicious descendant history.

## Controlled CLI coverage

The new controlled package was copied from the old sealed R1 originals into a fresh directory. Its parent outputs were rebuilt against the current source inventory; fixed historical wrappers explicitly identify themselves as controlled and report `official_sdk_history_validated=false`, `unity_started=false`. The CLI itself performs the actual current public surface readout, four train-only residual fits, corrections, reporting, numerical diagnostic and output verification.

The forgery replaces all four valid restorable model biases, all 96 corrected outputs, the consumption diagnostic, per-house/split statistics and report, and recomputes the complete output ledger. Verification proceeds through the same input pipeline and all four refits, then rejects the forged numerical results. Original legal outputs subsequently reproduce exactly. This establishes that valid model self-signatures and internally consistent result files do not prove training provenance.

The original-pin attack rebinds candidate content and byte summaries in a copied frontend cache while keeping its original external ledger pin. It is rejected at that pin. Its broader semantic summary consistency was deliberately not asserted, so this case is pin/exit-boundary evidence, not an additional complete semantic-forgery claim.

The CLI's four trained models and the native test fixture models are separate controlled executions. This review does not claim that a model trained on the real archived 96 frames has already traversed native owner publication and action consumption.

## Retained failures and remaining limits

- The original `493e05720f066c5db7173502d03b245bf74b6d43` review failure remains preserved under `R2`; its accepted complete likelihood/aggregate forgeries are not relabeled as passes. This report applies only to the new frozen SHA.
- Pre-freeze preparation attempt `RepairR1/dev-first-collector-01.log` failed collection because the explicit worktree pytest configuration was missing; `dev-first-collector-02.log` exposed the genuine later-cutoff collector ownership defect. Both attempts remain. The final formal run uses explicit `-c` and passes that normal collector path. There were no unexpected failures in the formal 49-case or ordered CLI run.
- Protection is the closed **canonical controlled-position raw profile**. Legacy/noncanonical candidate contracts are not universally upgraded by this repair. Torch-optional legacy collection is covered as a compatibility case.
- The historical body attack does not re-sign every descendant and does not replace trusted core/owner anchors. Arbitrary simultaneous replacement of the trusted process, source and all external pins is outside this acceptance boundary.
- The pending-admission failure test resumes within the test process; the separate pure fresh-process test uses a completed checkpoint. This is not the complete cross-product of injected crashes, all pending stages, independent processes and physical effects.
- Camera, association, utility and SDK data are controlled fixtures. The action tests establish refusal and exactly-once recovery, not better action utility, natural identity association, residual calibration, long-horizon performance or an actual Unity closed loop. Existing classification/active-clarification research choices and formal reference selection are unchanged.
- The same-semantic-source/new-capture transaction and per-cluster replay extension remain future work. Real neighboring frames are not assumed independent evidence and are not multiplied repeatedly by this review.
- Root's earlier 859-case regression and final 97-case validation are separate supporting records; they were not re-counted as this review's 49 executed tests.

Evidence hashes, final source integrity and exact scoped outcomes are in `RepairR1/evidence-manifest.json`. Sequential R2 remains required before the real archived experiment resumes.
