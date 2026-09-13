# First exact-R7-812 post-fix failure triage

Date: 2026-09-13
Mode: PC-B read-only triage
Tested commit: `23506024213d517ba4bab65d4318663163b00913`
Tested tree: `c433367468e5cae4d76a454c1b7946b9931d605c`

## Bottom line

The first exact 812-test replay is a valid, permanently retained **failed run**: **800 passed, 12 failed, 0 errors, 0 skipped** in 1,377.20 seconds (runner wall time 1,380.50 seconds).

The 12 failures separate into two mechanisms:

- **Nine immediate raw-byte identity failures** are fully explained by checkout-time LF-to-CRLF conversion across four frozen JSON artifacts. The LF control files equal the committed Git blobs and every fixed expected SHA-256. Each CRLF file differs only by one added `0D` byte per line ending; byte-normalizing CRLF back to LF reproduces the expected SHA exactly. The LF replay cleared four of these nodes and advanced the other five to a separate Windows path-separator failure that had been hidden behind the first hash check.
- **Three timing-sensitive lock failures are a repair-SHA deadline regression, not merely resource contention.** In a low-load, no-xdist comparison with the same Windows interpreter and CRLF mode, R7 `62870a3...` passed all three in 0.869/0.931/0.900 seconds, while repair `2350602...` failed all three in 1.186/1.207/1.442 seconds. This proves the one-second deadline regression. It does not by itself prove that the transaction actually waited on the foreign-owned lock, because the deadline includes all work before the handoff.

No failure currently demonstrates that any of W3-PCB-01 through W3-PCB-05 accepts its prohibited counterexample. Nine tests stop at an unrelated frozen-file byte precondition; three stop at the test harness deadline before the intended exception/outcome assertions.

## Original evidence is immutable

These first-run artifacts are not to be replaced by any later LF control or isolated rerun:

| Artifact | Size | SHA-256 |
|---|---:|---|
| `r7_exact_812_postfix_seed0.stdout.log` | 40,949 | `e52a868cb8d441cf5c3a09e612d5eb9285f5a5af5ddef65899e262a1f04fd2e9` |
| `r7_exact_812_postfix_seed0.stderr.log` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `r7_exact_812_postfix_seed0.junit.xml` | 168,047 | `30825bb4c219d940740d91914b6a249a6f472a9c0685a19151a4dbb9fb2a78d4` |
| `r7_exact_812_postfix_seed0.result.json` | 30,858 | `7a3ef81ef9ee9bdb7a5ad81d62291af0ad5250b7f3efadf5ab6df36eb3da12a3` |

The result manifest records clean and unchanged Git status, HEAD, tree, and Python-source inventory before and after the run.

## Run conditions

- Working directory: `F:\庞惟\codex\cpswm-w3-validation-2350602`
- Platform: Windows 11 `10.0.22631`
- Interpreter: CPython 3.13.5, `F:\庞惟\codex\cpswm-w3-five-boundaries-fix-20260912\.venv\Scripts\python.exe`
- Test runner: pytest 9.1.1, pytest-xdist 3.8.0, four workers
- Hash seed: `PYTHONHASHSEED=0`
- Numeric thread caps: `OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=1`, `MKL_NUM_THREADS=1`
- Selection: the 38 paths parsed from the R7 `final_812.command.json`; 812 collected tests
- Start/finish: `2026-09-12T23:02:09.093161+08:00` to `2026-09-12T23:25:09.588201+08:00`

## Per-failure classification

| # | Test | Observed failure | Classification | State consequence |
|---:|---|---|---|---|
| 1 | `test_cross_thread_lock_handoff_fails_without_waiting_for_foreign_release[core]` | Caller still alive after 1.0 s; case time 1.284 s | Confirmed repair-SHA deadline regression | Cleanup released worker and joined both threads; the test did not reach its normal rollback fingerprint assertion because the deadline assertion failed. The isolated repair replay also failed. |
| 2 | `test_cross_thread_lock_handoff_fails_without_waiting_for_foreign_release[wrapper]` | Caller still alive after 1.0 s; case time 1.258 s | Confirmed repair-SHA deadline regression | Same harness-level consequence as #1; isolated repair replay also failed. |
| 3 | `test_cross_thread_lock_handoff_fails_without_waiting_for_foreign_release[ccrr]` | Caller still alive after 1.0 s; case time 1.483 s | Confirmed repair-SHA deadline regression | Same harness-level consequence as #1; isolated repair replay also failed. |
| 4 | `test_replay_config_is_engineering_only_and_keeps_coverage_limits_explicit` | `bound P5 post-hoc result identity drifted` | CRLF/raw-byte identity | `_load_config` rejected before replay; no production transition or mutation occurred. |
| 5 | `test_artifact_numeric_forgery_fails_fresh_recomputation` | `bound P5 post-hoc result identity drifted` | CRLF/raw-byte identity | Fixture construction stopped before the intended forgery/recomputation check; no production mutation occurred. |
| 6 | `test_clarifying_the_forgetting_contract_did_not_move_the_receipt_hashes` | actual `f842...` vs fixed `eff5...` | CRLF/raw-byte identity | Read-only file-hash assertion only. |
| 7 | `test_design_freezes_disjoint_train_validation_and_holdout` | `neural proposal sealed seed hash mismatch` | CRLF/raw-byte identity | Sealed seeds rejected before design assertions; read-only load. |
| 8 | `test_checked_in_route_c_artifact_is_honest_and_verifiable` | `stateful full-joint source binding mismatch for config` | CRLF/raw-byte identity | Artifact verification rejected at source binding; no runtime execution. |
| 9 | `test_round_two_embedded_receipt_forgery_is_rejected` | expected later receipt mismatch, got earlier config source mismatch | CRLF/raw-byte identity shadows intended adversarial assertion | The forged object was still rejected, but for the checkout precondition rather than the intended receipt check. |
| 10 | `test_round_two_paired_action_deletion_is_rejected_even_when_rehashed` | expected paired-action mismatch, got earlier config source mismatch | CRLF/raw-byte identity shadows intended adversarial assertion | The forged object was still rejected before the intended branch. |
| 11 | `test_round_two_claim_boundary_and_source_substitution_are_rejected` | expected weakened-gate mismatch, got earlier config source mismatch | CRLF/raw-byte identity shadows intended adversarial assertion | The weakened object was still rejected before the intended branch. |
| 12 | `test_round_two_fresh_replay_detects_forged_but_self_consistent_provenance` | `stateful full-joint source binding mismatch for config` | CRLF/raw-byte identity shadows intended replay assertion | Verification stopped before fresh replay. |

The five stateful cases (#8-#12) have one immediate root cause and are not five independent defects: `verify_stateful_full_joint_result` checks the config source binding before the later positive/adversarial conditions.

## Windows/CRLF versus LF control

Both validation worktrees are clean, point to the same commit and tree, and have LF index blobs. The repository has no `.gitattributes`; the effective Git configuration reports `core.autocrlf=true`.

| Frozen file | Fixed/LF SHA-256 | Windows CRLF SHA-256 | HEAD blob | LF / CRLF endings | Result |
|---|---|---|---|---:|---|
| P5 post-hoc result | `98dcb3c35b15f41a523645ef3b9d3415e682882ec980539a337110bdc267658c` | `29c2cec22689e0a0bad8980560cd5f4abfe535556dc315c8a3b27710b00284ec` | `5bb3cc23c133acfb912c39dcb0f45df43452b71e` | 3,706 / 3,706 | CRLF adds 3,706 bytes; normalization exactly restores fixed SHA. |
| Selected-method receipt | `eff5e472346209053fe867e2ab53fdc455861e1e20125f192e6993e33bb33951` | `f842fe192d691356cb32fc76fde7695744e58ddf34ff6d6a00633529622fa982` | `a97e97ef4da9de3cdafcd9e21045f9ffb8ed243c` | 71 / 71 | CRLF adds 71 bytes; normalization exactly restores fixed SHA. |
| Neural sealed seeds | `c55e8cc470c08bfdb252fc24b825ff16e2bd55f71b82f9068cbfa2aa14b7dcf9` | `ff73dbedd4264952de984a12a39ad24776e5b4cc3d3221fc04bbedb8d9c0a8ca` | `4b09749b67cb0f525acf289c9c44a00f7840f0bd` | 6 / 6 | CRLF adds 6 bytes; normalization exactly restores fixed SHA. |
| Stateful full-joint config | `cce07302db4b73720701fe026fa29310ac068e45ad0e5f817bab7b660f4c0469` | `5ab102ef39b3eec371d4fbe645afbd9d486ee741d5d48cee6402b2f6e145e73d` | `2931d590d809dccb259e1f6d9d49685fdae69aea` | 69 / 69 | CRLF adds 69 bytes; normalization exactly restores fixed SHA. |

For all four files:

1. The LF-control raw SHA equals the fixed expected SHA.
2. The LF-control raw Git object ID equals `HEAD:<path>`.
3. The CRLF raw SHA does not equal the fixed expected SHA.
4. The CRLF size increase equals its CRLF count.
5. There are no bare CR bytes or mixed line endings.
6. Converting only CRLF pairs to LF yields the exact LF-control/fixed SHA.

Therefore the nine first-run hash-chain failures share the same immediate root mechanism: Git checkout transformed sealed LF bytes into CRLF while the verifier compared raw bytes to LF-era fixed identities. The detailed machine-readable measurements are in `windows_lf_comparison.json`.

## Exact LF 812 control and the five deeper Windows failures

The separate LF replay used the same commit, interpreter, 38-path selection, four workers, hash seed, and numeric thread caps. It produced **804 passed / 8 failed / 0 error / 0 skipped** in 1,382.52 JUnit seconds (runner wall time 1,386.57 seconds). It is a separate failed control and does not replace the first CRLF run.

| Artifact | Size | SHA-256 |
|---|---:|---|
| `r7_exact_812_postfix_lf_seed0.stdout.log` | 29,919 | `3fc494cffd11c38da07010d675d36854fb43a2bf6a50738bdd0569a5b0dc1e60` |
| `r7_exact_812_postfix_lf_seed0.stderr.log` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `r7_exact_812_postfix_lf_seed0.junit.xml` | 157,731 | `a712ed07dc636ba6c5728f628b2af064b9c1c38ccf40c0010224e5166ed504b1` |
| `r7_exact_812_postfix_lf_seed0.result.json` | 30,905 | `9354869035fe1099c2dcdedda8040bd56848e4e8cc7f73489ec43728ec0c14f0` |

The P5 pair, selected-method receipt, and neural sealed-seed test all passed after LF restoration: four failures disappeared. The same five stateful nodes still failed, but their immediate error changed from `source binding mismatch for config` to `source path substitution for implementation`. This establishes that they advanced beyond the corrected config-byte check.

The runtime import probe excludes accidental reuse of the main CRLF editable source:

- Loaded module: `F:\庞惟\codex\cpswm-w3-validation-lf-2350602\src\cpswm\system\evaluation_operations\structure_two_stateful_full_joint.py`
- `str(module_path.relative_to(root))`: `src\cpswm\system\evaluation_operations\structure_two_stateful_full_joint.py`
- `.as_posix()` and frozen value: `src/cpswm/system/evaluation_operations/structure_two_stateful_full_joint.py`

Thus the remaining five are one cross-platform path-representation defect: Windows `str(Path)` produces backslashes, while the frozen source binding is POSIX-form and the verifier performs direct string equality. The positive artifact test and four adversarial tests all stop at this shared earlier check; their later intended conditions remain unexercised in the LF control.

## Lock-case assessment

The lock test source and the direct execution, production-system, and adaptive-runtime lock files are byte-identical between R7 (`62870a3a...`) and the tested repair commit. The shared `prototype_spine.py` changed. The test starts a caller thread, then gives it a one-second total deadline that includes ordinary transition setup, trace construction, sink handoff, scheduling of a second worker, and detection/abort.

The low-load comparison used the same CPython 3.13.5 executable, Windows CRLF checkout, `PYTHONHASHSEED=0`, one-thread numeric caps, disabled pytest cache, and no xdist:

| Frozen SHA | Result | Per-case JUnit seconds: core / wrapper / ccrr | Process wall time |
|---|---|---|---:|
| R7 `62870a3a38fce882b25d8d77f1d0526cca6fbc14` | 3 passed / 0 failed | 0.869 / 0.931 / 0.900 | 9.171 s |
| Repair `23506024213d517ba4bab65d4318663163b00913` | 0 passed / 3 failed | 1.186 / 1.207 / 1.442 | 10.959 s |

The exact common pytest selection was:

```text
python -m pytest -o addopts= -q -ra -p no:cacheprovider --basetemp=<unique-run-scratch>/basetemp --junitxml=<unique-run-output>.junit.xml -k test_cross_thread_lock_handoff_fails_without_waiting_for_foreign_release tests/test_structure_two_execution_interface.py
```

The absolute argv arrays, environment, worktree paths, commits, trees, start/finish times, and output identities are in `windows_lf_comparison.json`. Standalone evidence is preserved separately:

| Artifact | Size | SHA-256 |
|---|---:|---|
| `lock_standalone_r7_62870a3_seed0.stdout.log` | 115 | `666c7443e3cf22eb559c3732b3cdd8652847f6346f3c43826d051e790f5e3875` |
| `lock_standalone_r7_62870a3_seed0.stderr.log` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `lock_standalone_r7_62870a3_seed0.junit.xml` | 752 | `afc9f5d6b9c5777d4ae82ba9b2c7009deddf732e43ac51bfecc12978a05a1950` |
| `lock_standalone_fix_2350602_seed0.stdout.log` | 8,143 | `46df00490ab8e8c7f7c59dc85f92c85a1d143939b76268d238246995c5997443` |
| `lock_standalone_fix_2350602_seed0.stderr.log` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `lock_standalone_fix_2350602_seed0.junit.xml` | 8,729 | `55904240a658d65d004d01c7fc854010424b06bbb1297c6e1e27b30f033cafe6` |

This rejects the “resource contention only” explanation and confirms a repair-SHA timing/performance regression against the one-second contract. It does **not** by itself prove that the caller truly waited for the foreign lock: the total deadline can also expire because the repair path reaches the handoff too slowly. No test threshold was relaxed.

## Current triage disposition

- Confirmed prohibited-counterexample acceptance regressions in W3-PCB-01..05: **0 observed**.
- Confirmed repair-SHA deadline/timing regressions: **3**.
- First-run immediate CRLF raw-byte identity failures: **9** across four files.
- Additional Windows path-separator portability failure exposed by LF: **1 root cause affecting 5 nodes**.
- Resource-contention-only classification for the lock failures: **rejected by the low-load R7/repair contrast**.
- Evidence authorization: both exact-812 runs remain **FAIL** and neither may be relabeled or overwritten; the standalone runs are diagnostic evidence only.
