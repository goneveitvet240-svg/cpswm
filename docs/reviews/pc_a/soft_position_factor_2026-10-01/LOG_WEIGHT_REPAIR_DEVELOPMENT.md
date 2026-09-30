# Finite log weight continuation — implementation record

Author development record, not R1/R2, B acceptance, natural calibration or archive experiment. This repair follows the blocked R2 of source `37981c3c44475b0bcbeff3379dcf90be288c49c9`; the original failed review/log remain retained. Root subsequently made documentation-only commit `000f6916a86bd6c84549ff99e65d7beeb14aa2d0`. Production changes below are not assigned a new reviewed source SHA by this document.

Worktree: `/private/tmp/cpswm-pc-a-soft-position-factor-20261001`.

Interpreter: `/private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python`.

The implementation author stopped all `src/tests/tools` writes before the final verification below. The complete 895-file Python source map is `logweight-author-source-files.json`, SHA256 `957c2a34d0ba1878c493b4ed2640d975858b29f850cc179f8169b38e706425a8`. This map includes uncommitted source and is not a formal source freeze or successful review.

## Actual correction

The original known-particle likelihood `-2465.7563115023117` is finite but exponentiates to a displayed posterior probability of zero. Reconstructing its next prior with `log(0)` lost a valid branch. Investigation found four coupled boundaries: producer prior/aggregate inheritance, neural parent active membership, workspace parent-weight validation, and workspace's requirement that displayed aggregate probability be positive.

`NativePreviousWeightEvidence` is now a concrete frozen dataclass containing complete preceding receipt terms and the original aggregate log. The owner obtains it from actual `input_bodies`, checks the input journal fingerprint and exact regenerated batch, and includes it in admitted/produced/replayed raw contexts. The consumer reconstructs it independently from the real current or historical parent chain. The producer cannot choose a mutable checkpoint as prior authority. A missing/untyped previous evidence value is rejected for the protected continuation. The optional `NativeJointContext` field adds no tail to its content hash when None, preserving the legacy hash contract in that case.

Normalized prior logs are calculated from exact binary-input Fraction sums, shifted by their exact maximum and a stable log-sum-exp denominator. Accepted branches retain finite log weights even if their display probabilities are zero; rejected support remains excluded. Known, unknown and aggregate inherit this log-domain prior. q's current active support uses accepted IDs in the actual previous batch, not all historical records or positive displayed probability. The workspace validates the same prior against original receipts. No epsilon, branch deletion, new model, likelihood/identity rule, reference choice or utility change is introduced. A normalized log outside finite float range is explicitly rejected rather than silently saturated.

The new raw profile also fixes `weight_source`, the workspace file SHA; the deep checker verifies it before mathematical reconstruction. The existing core independently fixes the whole workspace source and now includes `previous_weight_evidence` in its loaded-method anchors. Full loaded-code scanning also covers the workspace and joint-context modules.

## Runtime code identity and automatic review

The initial full self-scan exposed a separate identity-encoding issue: Python marshal's default reference flags can vary when a function's constant tuple remains referenced by execution/traceback state. A proposed patch narrowing the new workspace scan to only the new evidence methods was rejected by automatic approval review as potentially weakening runtime integrity. That proposed narrowing did not execute, was not reapplied with another tool, and is not part of the repair.

The implemented alternative preserves the complete scan and exact source/function identities. Only this scanner and workspace's local core method anchors use SHA256 of the full existing code payload encoded with explicit marshal version 2, which does not contain object-reference sharing flags. Code bytes, nested code, constants, constant types, names, line/exception tables and other existing fields are all retained. The project-wide `_code_object_sha256` and other checkpoint/execution protocol encodings are unchanged.

A targeted test demonstrated stability while a function is active, while its constant payload is held, and after release; distinct True/1, 1/1.0 and +0.0/-0.0 remain distinct. Another test creates a complete numerical prior forgery using a loaded replacement, actually computes q, checks owner rejection, restores the original function while keeping the caught exception/traceback alive, and requires successful legal publication. Its first run caught the same default-marshal issue in the core's old method anchor; the final local stable anchor correction passes without clearing the exception or dropping integrity checks.

## Files changed by the implementation author

- `src/cpswm/system/controlled_position_producer.py`
- `src/cpswm/system/native_joint_production.py`
- `src/cpswm/system/native_neural_production.py`
- `src/cpswm/system/native_raw_verification.py`
- `src/cpswm/system/prototype_spine.py`
- `src/cpswm/system/structure_two_continuous_input.py`
- `src/cpswm/system/structure_two_particle_workspace.py`
- `tests/test_native_neural_production.py` (context-construction helper only)
- New `tests/test_native_log_weight_continuation.py`

## Executed development checks

All pytest commands used the interpreter above from the worktree, with `PYTHONPATH=src:tests:tools OPENBLAS_NUM_THREADS=1`, `-m pytest -c pyproject.toml -o addopts= -q`. The test fixture really trains/executes its existing small neural checkpoints and uses synthetic position/affinity/pixel/identity cases. These runs do not train on the actual 96-frame archive, run its detector, or start Unity.

| Log | Actual outcome | Meaning |
| --- | --- | --- |
| `logweight-original-positive-01.log` | 1 passed in 6.77s, exit 0 | Original external R2 finite-density failure passed after first arithmetic changes; before later integrity/aggregate adjustments |
| `logweight-targeted-01.log` | 8 failed in 6.95s, exit 1 | Retained full self-scan encoding failures; not arithmetic acceptance |
| `logweight-targeted-02.log` | 5 passed, 3 failed in 44.58s, exit 1 | Known-underflow continuation/recovery/replay passed; newly tested unknown+aggregate underflow exposed display-mass positivity check |
| `logweight-targeted-03.log` | 9 passed in 79.98s, exit 0 | Eight new cases plus original external R2 stress; before final local core code-identity adjustment |
| `logweight-code-integrity-01.log` | 1 failed, 1 passed, 8 deselected in 5.95s, exit 1 | Retained traceback prevented legal recovery under original core marshal anchor |
| `logweight-code-integrity-02.log` | 2 passed, 8 deselected in 6.31s, exit 0 | Full typed-code stability and caught-traceback legal recovery after final anchor correction |
| `logweight-final-targeted-01.log` | 16 passed in 89.32s, exit 0 | Final unchanged-source combined regression |

Ruff `check` on all nine changed files returned exit 0, `format --check` reported all nine formatted, and `git diff --check` returned exit 0. These original outputs are visible in the tool session; no separate historical raw log is claimed. Two intermediate Ruff commands initially stopped on a generator-style warning and an unused import respectively, before any chained pytest execution; both were corrected before the recorded successful runs. An attempted patch append failed context matching and did not edit the file. No failed test/log above was overwritten.

The exact final pytest selection is:

```text
tests/test_native_log_weight_continuation.py
tests/test_native_raw_candidate_verification.py::test_loaded_raw_verifier_replacement_fails_before_cache_or_target_acceptance
tests/test_structure_two_w3_native_particles.py::test_native_cross_step_ancestry_and_actual_log_q_consumer
tests/test_native_joint_production.py::test_two_semantic_steps_automatically_extend_real_ancestry_and_three_blocks
tests/test_structure_two_selected_method.py::test_clarifying_the_forgetting_contract_did_not_move_the_receipt_hashes
tests/test_structure_two_selected_method.py::test_particle_revision_normalizes_with_unresolved_and_zeroes_rejected_particle
/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/output/soft-position-factor-20261001/RepairR2/test_finite_log_weight_continuation.py
```

Final actual count: 16 (10 new cases, five existing compatibility points, original external numerical positive path), exit 0 in 89.32 seconds. After execution, all 895 Python files were reread and matched the stop-writes source map exactly. `logweight-author-final-verification.json` records this comparison and the final log SHA256 `1111eb2aebf9602f57701038716a8042b9512d794261b4b7d2fc92d17a85ea91`. The later root-owned independent Decimal verification and broader regressions are separate and are not claimed as executed here.

## Coverage boundary and next handoff

This author coverage targets the canonical controlled producer, complete accepted receipts, actual known/unknown/aggregate underflow, actual neural scoring/publication, two neutral steps without duplicate information, fresh-process SQLite recovery followed by a neutral step, and withdrawal/replay matching a paired no-factor control. It also includes complete self-consistent prior evidence substitution and loaded mathematical replacement, owner rejection without workspace change, and legal recovery.

It does not establish natural instance association, empirical calibration, a formal position reference, action benefit, archive bridge completion or multi-capture owner updates. The broad legacy/core/action/crash cross-product and formal new-source adversarial reviews remain separate obligations. Existing sealed outputs are not migrated or reinterpreted as same-source recovery. Root must freeze the actual final source and restart sequential R1/R2 before any actual archive experiment.
