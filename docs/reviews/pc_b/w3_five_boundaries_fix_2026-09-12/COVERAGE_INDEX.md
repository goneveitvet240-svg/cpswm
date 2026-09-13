# PC-B W3 five-boundary coverage index

## Binding and claim limit

This index binds the repair-side coverage to frozen candidate commit `23506024213d517ba4bab65d4318663163b00913` (tree `c433367468e5cae4d76a454c1b7946b9931d605c`). The five-boundary production change first appears at `17220e6e22de81508a2e4e34dce81b8dccc9e44f`.

The five original counterexamples and the 47-case expansion pass at that frozen candidate, but `2350602...` is **not an acceptable final repair SHA**: it has a confirmed deadline regression in all three `test_cross_thread_lock_handoff_fails_without_waiting_for_foreign_release` variants. A lock repair, a new immutable SHA, full reruns and review by someone other than the repair author are still required. Nothing in this index signs independent acceptance, default full-joint capability, fair comparison, unified acceptance or scientific benefit.

`BOUNDARY_MATRIX.json` is the machine-readable per-case source for entrypoint, trust class, producer/consumer, R6/R7 state consequences and candidate disposition. This file indexes the exact executable coverage behind it.

## Evidence keys

| Key | Exact evidence | Result and use |
|---|---|---|
| `R6-HIST` | `docs/reviews/data/pc_b_w3_r6_independent_20260912/case_results.json`; `docs/reviews/data/pc_b_w3_r6_independent_20260912/logs/five-case-observations-r6.json`; `docs/reviews/data/pc_b_w3_r6_independent_20260912/logs/independent-adversarial-with-control.log` | Immutable R6: legal control passed; five adversarial cases failed because prohibited calls were accepted. |
| `R7-BASE` | `docs/reviews/pc_b/w3_five_boundaries_fix_2026-09-12/baseline_r7_five_seed0.junit.xml`; `baseline_r7_five_seed0.log`; `baseline_r7_historical_observer_seed0.json` | Frozen R7 `62870a3...`: 1 passed / 5 failed; all prohibited calls accepted. The observer's embedded R6 SHA is historical script text, not the R7 binding authority. |
| `ORIG-6` | `docs/reviews/pc_b/w3_five_boundaries_fix_2026-09-12/post_fix/original_six_postfix_seed0.result.json`; `original_six_postfix_seed0.junit.xml` | Candidate `2350602...`, hash seed 0: 6/6 passed, no skip/xfail. JUnit SHA-256 `ae1bea5a0d6d4d4450a89d61f5b049f11a3def6fd51b95ba83caa059bdbe0fae`. |
| `REPAIR-3SEED` | `post_fix/repair_matrix_seed0.result.json` + `.junit.xml`; `post_fix/repair_matrix_seed1.result.json` + `.junit.xml`; `post_fix/repair_matrix_seed8675309.result.json` + `.junit.xml` | Candidate `2350602...`: 47/47 passed at each of `PYTHONHASHSEED=0`, `1`, and `8675309`, no failure/error/skip/xfail. JUnit SHA-256 values: `68ecd858a8b3d86493a31818cafe51531541c51021eb9272d37e899864d6eef7`, `f5d17cf2e88723ea36faa917418f7ce06be01d82877a1ec28e9b53e5472e8f8f`, `5ce897dabcf66531675198a9d613fc73eaad357e5e5866def053f518bd8a0698`. |
| `812-CRLF` | `post_fix/r7_exact_812_postfix_seed0.result.json`; `r7_exact_812_postfix_seed0.junit.xml` | Preserved failed Windows/CRLF run: 800 passed / 12 failed. Nine failures are raw-byte checkout identities; three are the confirmed lock deadline regression. This run is not overwritten or relabelled. |
| `812-LF` | `post_fix/r7_exact_812_postfix_lf_seed0.result.json`; `r7_exact_812_postfix_lf_seed0.junit.xml` | Preserved failed Windows/LF control: 804 passed / 8 failed. Three lock failures remain; five stateful-full-joint nodes expose one Windows path-separator defect after LF fixes their earlier config-byte gate. All 812-derived nodes listed below passed individually unless explicitly marked otherwise. |
| `LOCK-DIAG` | `post_fix/lock_standalone_r7_62870a3_seed0.junit.xml`; `post_fix/lock_standalone_fix_2350602_seed0.junit.xml`; `post_fix/failure_triage.md` | Low-load/no-xdist contrast: R7 3/3 passed; candidate 0/3 passed. Final five-boundary acceptance remains pending. |

Paths in later tables are repository-relative. `post_fix/` means `docs/reviews/pc_b/w3_five_boundaries_fix_2026-09-12/post_fix/`.

## Status vocabulary

- `COVERED-REPAIR-3SEED`: the exact node passed in all three `REPAIR-3SEED` runs.
- `COVERED-ORIG-6`: the exact original node passed in the seed-0 `ORIG-6` run.
- `COVERED-812-LF`: the exact node passed inside the frozen `812-LF` run. This is an individual-node result inside an aggregate failed suite, not a full-suite pass.
- `PARTIAL`: the executable evidence covers only the stated in-memory/public contract; a broader persistence or platform claim is not established.
- `PENDING-NEW-SHA`: evidence is valid for `2350602...` but must be rerun on the eventual post-lock repair SHA.
- `NOT-ESTABLISHED`: no evidence in this campaign supports the broader claim.

Every covered row is also `PENDING-NEW-SHA` until the new frozen SHA is tested.

## Five original findings and strengthened variants

| Finding | Exact node IDs | Coverage | Evidence |
|---|---|---|---|
| Legal public control | `tests/test_structure_two_w3_r6_pc_b_review.py::test_legal_prepared_input_control_is_preserved` | Original node: `COVERED-ORIG-6`; the expanded initial/unknown/idempotent legal node below is `COVERED-REPAIR-3SEED` | `ORIG-6`, `REPAIR-3SEED` |
| W3-PCB-01, construction support | `tests/test_structure_two_w3_r6_pc_b_review.py::test_prepared_support_is_bound_to_the_constructed_world`; `tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_public_support_rebinding_fails_closed_on_every_surface[stage-foreign]`; `tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_public_support_rebinding_fails_closed_on_every_surface[stage-reordered]` | Original node: `COVERED-ORIG-6`; strengthened nodes: `COVERED-REPAIR-3SEED` | `ORIG-6`, `REPAIR-3SEED` |
| W3-PCB-02, rebound readout | `tests/test_structure_two_w3_r6_pc_b_review.py::test_prepared_readout_rejects_a_rebound_world_support`; `tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_public_support_rebinding_fails_closed_on_every_surface[readout-foreign]`; `tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_public_support_rebinding_fails_closed_on_every_surface[readout-reordered]` | Original node: `COVERED-ORIG-6`; strengthened nodes: `COVERED-REPAIR-3SEED` | `ORIG-6`, `REPAIR-3SEED` |
| W3-PCB-03, parent/child support | `tests/test_structure_two_w3_r6_pc_b_review.py::test_particle_parent_and_child_cannot_switch_world_support`; `tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_public_support_rebinding_fails_closed_on_every_surface[parent-foreign]`; `tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_public_support_rebinding_fails_closed_on_every_surface[parent-reordered]`; `tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_public_support_rebinding_fails_closed_on_every_surface[replay-foreign]`; `tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_public_support_rebinding_fails_closed_on_every_surface[replay-reordered]` | Original node: `COVERED-ORIG-6`; strengthened nodes: `COVERED-REPAIR-3SEED` | `ORIG-6`, `REPAIR-3SEED` |
| W3-PCB-04, receipt/statistic/parent cluster lineage | `tests/test_structure_two_w3_r6_pc_b_review.py::test_conditional_statistics_are_bound_to_the_receipt_cluster`; `tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_fully_resealed_false_cluster_lineage_is_rejected_and_retryable[foreign]`; `tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_fully_resealed_false_cluster_lineage_is_rejected_and_retryable[missing]`; `tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_fully_resealed_false_cluster_lineage_is_rejected_and_retryable[reordered]`; `tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_fully_resealed_false_cluster_lineage_is_rejected_and_retryable[duplicate]` | Original node: `COVERED-ORIG-6`; strengthened nodes: `COVERED-REPAIR-3SEED` | `ORIG-6`, `REPAIR-3SEED` |
| W3-PCB-05, input closure | `tests/test_structure_two_w3_r6_pc_b_review.py::test_unreferenced_statistics_cannot_enter_the_persisted_input_body`; all seven exact `test_receipt_statistic_input_closure_attacks_are_atomic` nodes listed in the next section | Original node: `COVERED-ORIG-6`; strengthened nodes: `COVERED-REPAIR-3SEED` | `ORIG-6`, `REPAIR-3SEED` |

The first three rows invoke public methods but prepare the attack by rebinding the non-private `core.locations` instance field. The last two rows modify only caller-owned, schema-valid DTOs/mappings. Direct private-state corruption tests below are a third, stronger trust class and do not replace these original public-boundary cases.

## Required Stage 2 coverage

### Legal initial, multigeneration, unknown support, paired reorder and repeat

All of these are `COVERED-REPAIR-3SEED` under `REPAIR-3SEED`:

```text
tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_legal_initial_unknown_unresolved_and_idempotent_replay
tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_legal_zero_increment_second_generation_still_appends_cluster
tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_legal_location_alpha_pair_reordering_preserves_the_marginal
tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_legal_siblings_may_share_one_statistic_object_and_reference
tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_one_posterior_source_may_weight_multiple_siblings_in_one_batch
tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_one_posterior_source_cannot_be_recounted_in_a_later_batch
tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_conditional_state_copy_is_content_based_not_object_identity_based
```

The initial control explicitly checks `unknown_instance`, `unknown_actor`, positive unresolved mass, total mass one and identical-call idempotency. The second-generation control checks the ordered cluster append even when every natural parameter has zero increment. The reorder control pairs each location with its alpha before reversing both sequences.

### Fully resealed false inputs and closure variants

The four exact lineage variants are listed in the five-finding table. The exact closure nodes, all `COVERED-REPAIR-3SEED`, are:

```text
tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_receipt_statistic_input_closure_attacks_are_atomic[extra-closure|unreferenced|statistic]
tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_receipt_statistic_input_closure_attacks_are_atomic[missing-closure|missing|statistic]
tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_receipt_statistic_input_closure_attacks_are_atomic[both-closure|missing|unreferenced|statistic]
tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_receipt_statistic_input_closure_attacks_are_atomic[duplicate_particle-duplicate particle|unique]
tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_receipt_statistic_input_closure_attacks_are_atomic[duplicate_proposal-duplicate proposal|unique]
tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_receipt_statistic_input_closure_attacks_are_atomic[mixed_snapshot-snapshot]
tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_receipt_statistic_input_closure_attacks_are_atomic[mixed_cluster-cluster]
tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_statistics_mapping_duplicate_items_are_rejected_before_persistence
```

The lineage helper recomputes the complete `ConditionalAnalyticState.reference` and reseals the public `statistic_state_ref`; it is not merely a stale-hash test. The duplicate-cluster variant deliberately bypasses the dataclass constructor to exercise persisted boundary validation, while the public schema-valid foreign/missing/reordered cases remain separately visible.

The earlier R6/R7 support-reseal matrix also passes individually in `812-LF`:

```text
tests/test_structure_two_w3_round6_prepared_boundary.py::test_fully_resealed_support_attacks_roll_back_and_retry[0-foreign]
tests/test_structure_two_w3_round6_prepared_boundary.py::test_fully_resealed_support_attacks_roll_back_and_retry[0-mixed]
tests/test_structure_two_w3_round6_prepared_boundary.py::test_fully_resealed_support_attacks_roll_back_and_retry[0-subset]
tests/test_structure_two_w3_round6_prepared_boundary.py::test_fully_resealed_support_attacks_roll_back_and_retry[0-duplicate]
tests/test_structure_two_w3_round6_prepared_boundary.py::test_fully_resealed_support_attacks_roll_back_and_retry[1-foreign]
tests/test_structure_two_w3_round6_prepared_boundary.py::test_fully_resealed_support_attacks_roll_back_and_retry[1-mixed]
tests/test_structure_two_w3_round6_prepared_boundary.py::test_fully_resealed_support_attacks_roll_back_and_retry[1-subset]
tests/test_structure_two_w3_round6_prepared_boundary.py::test_fully_resealed_support_attacks_roll_back_and_retry[1-duplicate]
```

### Caller alias and time-of-check/time-of-use attacks

All are `COVERED-REPAIR-3SEED` under `REPAIR-3SEED`:

```text
tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_caller_alias_mutation_before_acceptance_is_revalidated_atomically
tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_caller_alias_mutation_after_acceptance_cannot_change_or_block_replay
tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_statistics_mapping_toctou_is_bound_to_one_detached_snapshot
tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_statistics_mapping_duplicate_items_are_rejected_before_persistence
tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_legal_siblings_may_share_one_statistic_object_and_reference
tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_conditional_state_copy_is_content_based_not_object_identity_based
```

The before-acceptance attack mutates a shared caller object while receipts retain old references and verifies rejection without effects. The after-acceptance attack mutates/clears all caller aliases and verifies both stable readout and equivalent-input replay. The TOCTOU mapping permits only one `items()` read and mutates itself after yielding the detached rows.

### Stale parent, cross-runtime state, invalidation/reuse and repeated consumption

| Contract | Exact node IDs | Status / evidence |
|---|---|---|
| Parent and replay cannot cross rebound support | `tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_public_support_rebinding_fails_closed_on_every_surface[parent-foreign]`; `[parent-reordered]`; `[replay-foreign]`; `[replay-reordered]` with the same exact prefix | `COVERED-REPAIR-3SEED`, `REPAIR-3SEED` |
| Foreign runtime records cannot be transplanted even if the current snapshot ID is substituted | `tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_cross_runtime_record_transplant_is_rejected_even_with_current_batch_snapshot` | `COVERED-REPAIR-3SEED`, `REPAIR-3SEED` |
| A corrected/revoked revision invalidates prepared parents and refuses an unbound full replay | `tests/test_structure_two_w3_native_particles.py::test_public_correction_invalidates_native_parent_and_refuses_unselected_replay` | `COVERED-812-LF`, `812-LF` |
| A stale prepared snapshot is not exposed as current after the real timeline advances | `tests/test_structure_two_w3_native_particles.py::test_native_cross_step_ancestry_and_actual_log_q_consumer` | `COVERED-812-LF`, `812-LF` |
| A posterior source cannot be recounted in a later batch | `tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_one_posterior_source_cannot_be_recounted_in_a_later_batch`; `tests/test_structure_two_w3_native_posterior_projection.py::test_same_posterior_cannot_be_recounted_under_a_new_candidate_cluster` | First: `COVERED-REPAIR-3SEED`; second: `COVERED-812-LF` |
| Complete producer-dependency resealing cannot substitute another source | `tests/test_structure_two_w3_native_posterior_projection.py::test_complete_resealing_cannot_replace_actual_producer_dependencies[posterior]`; `[parent]`; `[rekey]`; `[context]`; `[world]` with the same exact prefix | `COVERED-812-LF`, `812-LF` |

The compact bracket notation in this table means the exact prefix printed before each bracket plus exactly the listed parameter ID; no wildcard result is claimed.

### Checkpoint, restoration and replay consistency

The production checkpoint exercised here is the in-memory revision-transaction snapshot used to roll the existing workspace object back. This campaign does **not** establish a public disk serializer, a process-restart restore protocol, or a cross-machine checkpoint format for prepared particles.

`COVERED-REPAIR-3SEED` under `REPAIR-3SEED`:

```text
tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_actual_advance_return_interruption_rolls_back_and_is_retryable[0-RuntimeError]
tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_actual_advance_return_interruption_rolls_back_and_is_retryable[0-KeyboardInterrupt]
tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_actual_advance_return_interruption_rolls_back_and_is_retryable[1-RuntimeError]
tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_actual_advance_return_interruption_rolls_back_and_is_retryable[1-KeyboardInterrupt]
tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_public_support_rebinding_fails_closed_on_every_surface[replay-foreign]
tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_public_support_rebinding_fails_closed_on_every_surface[replay-reordered]
tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_caller_alias_mutation_after_acceptance_cannot_change_or_block_replay
```

`COVERED-812-LF` under `812-LF`:

```text
tests/test_structure_two_w3_round6_prepared_boundary.py::test_stable_readout_validation_interruption_restores_all_instances[0-RuntimeError]
tests/test_structure_two_w3_round6_prepared_boundary.py::test_stable_readout_validation_interruption_restores_all_instances[0-KeyboardInterrupt]
tests/test_structure_two_w3_round6_prepared_boundary.py::test_stable_readout_validation_interruption_restores_all_instances[1-RuntimeError]
tests/test_structure_two_w3_round6_prepared_boundary.py::test_stable_readout_validation_interruption_restores_all_instances[1-KeyboardInterrupt]
tests/test_structure_two_w3_native_posterior_projection.py::test_consumption_interrupt_restores_dependency_journal_and_retries[RuntimeError]
tests/test_structure_two_w3_native_posterior_projection.py::test_consumption_interrupt_restores_dependency_journal_and_retries[KeyboardInterrupt]
```

Disposition: in-memory rollback, workspace object identity, support checks and evidence-consumption journal restoration are covered; external serialized checkpoint/restart is `NOT-ESTABLISHED`.

### Persisted-state revalidation and direct private-state defence in depth

These tests assume an attacker can directly modify underscore-prefixed workspace state after acceptance. They are not public-input substitutes for the five original findings. All are `COVERED-REPAIR-3SEED`:

```text
tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_direct_private_single_field_tampering_fails_closed[support_hash]
tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_direct_private_single_field_tampering_fails_closed[record_statistic]
tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_persisted_workspace_tampering_blocks_semantic_readout[journal_digest]
tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_persisted_workspace_tampering_blocks_semantic_readout[journal_body]
tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_persisted_workspace_tampering_blocks_semantic_readout[batch]
tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_persisted_workspace_tampering_blocks_semantic_readout[receipts]
tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_persisted_workspace_tampering_blocks_semantic_readout[consumption]
tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_persisted_cross_relations_are_rechecked_on_direct_readout[delete_historical_record]
tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_persisted_cross_relations_are_rechecked_on_direct_readout[inject_orphan_record]
tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_persisted_cross_relations_are_rechecked_on_direct_readout[reseal_source_frame]
tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_persisted_cross_relations_are_rechecked_on_direct_readout[empty_chain_history]
tests/dual_pc_review/test_w3_five_boundaries_repair.py::test_persisted_cross_relations_are_rechecked_on_direct_readout[clear_projection_consumption]
```

The semantic-readout cases also verify that the long-term ledger export digest does not change on rejection. Test-only restoration of deliberately corrupted private objects is explicitly separated from product recovery semantics.

### Legal cancellation recovery, correction, retraction and readout

The exact 812 LF control passed these public-path nodes:

```text
tests/test_structure_two_w3_deferred_cancellation.py::test_public_cancellation_restores_full_nonempty_parent_and_preserves_new_observation[core-0]
tests/test_structure_two_w3_deferred_cancellation.py::test_public_cancellation_restores_full_nonempty_parent_and_preserves_new_observation[core-1]
tests/test_structure_two_w3_deferred_cancellation.py::test_public_cancellation_restores_full_nonempty_parent_and_preserves_new_observation[core-2]
tests/test_structure_two_w3_deferred_cancellation.py::test_public_cancellation_restores_full_nonempty_parent_and_preserves_new_observation[production_wrapper-0]
tests/test_structure_two_w3_deferred_cancellation.py::test_public_cancellation_restores_full_nonempty_parent_and_preserves_new_observation[production_wrapper-1]
tests/test_structure_two_w3_deferred_cancellation.py::test_public_cancellation_restores_full_nonempty_parent_and_preserves_new_observation[production_wrapper-2]
tests/test_structure_two_w3_deferred_cancellation.py::test_restored_parent_can_be_corrected_again_then_retracted_without_resurrection
tests/test_structure_two_w3_deferred_cancellation.py::test_cancellation_semantics_reproduce_with_distinct_execution_lineage[cancel]
tests/test_structure_two_w3_deferred_cancellation.py::test_cancellation_semantics_reproduce_with_distinct_execution_lineage[correct]
tests/test_structure_two_w3_deferred_cancellation.py::test_cancellation_semantics_reproduce_with_distinct_execution_lineage[retract]
tests/test_structure_two_w3_deferred_cancellation.py::test_cancellation_restores_original_nonempty_derived_bundle_without_fresh_authority
```

The interruption/retry nodes below cover each actual cancellation stage with both exception classes; every exact node passed in `812-LF`:

```text
tests/test_structure_two_w3_deferred_cancellation.py::test_real_cancellation_interruption_restores_pending_transaction_and_can_retry[RuntimeError-cancellation_lineage]
tests/test_structure_two_w3_deferred_cancellation.py::test_real_cancellation_interruption_restores_pending_transaction_and_can_retry[RuntimeError-hybrid]
tests/test_structure_two_w3_deferred_cancellation.py::test_real_cancellation_interruption_restores_pending_transaction_and_can_retry[RuntimeError-dirichlet]
tests/test_structure_two_w3_deferred_cancellation.py::test_real_cancellation_interruption_restores_pending_transaction_and_can_retry[RuntimeError-rls]
tests/test_structure_two_w3_deferred_cancellation.py::test_real_cancellation_interruption_restores_pending_transaction_and_can_retry[RuntimeError-cancellation_replay]
tests/test_structure_two_w3_deferred_cancellation.py::test_real_cancellation_interruption_restores_pending_transaction_and_can_retry[KeyboardInterrupt-cancellation_lineage]
tests/test_structure_two_w3_deferred_cancellation.py::test_real_cancellation_interruption_restores_pending_transaction_and_can_retry[KeyboardInterrupt-hybrid]
tests/test_structure_two_w3_deferred_cancellation.py::test_real_cancellation_interruption_restores_pending_transaction_and_can_retry[KeyboardInterrupt-dirichlet]
tests/test_structure_two_w3_deferred_cancellation.py::test_real_cancellation_interruption_restores_pending_transaction_and_can_retry[KeyboardInterrupt-rls]
tests/test_structure_two_w3_deferred_cancellation.py::test_real_cancellation_interruption_restores_pending_transaction_and_can_retry[KeyboardInterrupt-cancellation_replay]
```

This establishes continued correction/retraction/semantic validation after a legal cancellation recovery on the frozen candidate. It does not turn the prepared-particle seam into a bound full-replay implementation: invalidated particle ancestry still fails closed when the selected replay kernel is absent.

### Failure injection, full rollback and legal retry

The four `test_actual_advance_return_interruption_rolls_back_and_is_retryable` nodes listed above inject after the real `NativeParticleWorkspace.advance` return at initial and second-generation boundaries with `RuntimeError` and `KeyboardInterrupt`; all pass in all three hash-seed runs.

The older public-boundary interruption pair also passed individually in `812-LF`:

```text
tests/test_structure_two_w3_native_particles.py::test_actual_prepared_call_interruption_is_atomic_and_retryable[RuntimeError]
tests/test_structure_two_w3_native_particles.py::test_actual_prepared_call_interruption_is_atomic_and_retryable[KeyboardInterrupt]
```

The cancellation-stage and posterior-consumption interruption nodes in the preceding sections extend rollback evidence to dependency journals, Hybrid/Dirichlet/RLS state and cancellation replay. The known cross-thread deadline regression is a separate failed contract, not hidden by these passes.

### Extreme finite numbers and total probability mass

Every `REPAIR-3SEED` legal/retry helper calls the prepared marginal and asserts total mass one plus positive unresolved mass. Independent extreme-number reference coverage passed individually in `812-LF`:

```text
tests/test_structure_two_w3_round6_prepared_boundary.py::test_shared_extreme_log_offset_preserves_small_relative_evidence
tests/test_structure_two_w3_round6_prepared_boundary.py::test_public_finite_cancellation_is_consumable[-1e+308-0.0--1e+308-0.0]
tests/test_structure_two_w3_round6_prepared_boundary.py::test_public_finite_cancellation_is_consumable[-1e+308-1e+308--1e+308-1e+308]
```

The exact independent-decimal reference family passed for both `rejected=False` and `rejected=True`, with each of these seven parameter IDs:

```text
tests/test_structure_two_w3_round6_prepared_boundary.py::test_weights_match_independent_decimal_reference[False-0.0--1e+308--1e+308-0.0]
tests/test_structure_two_w3_round6_prepared_boundary.py::test_weights_match_independent_decimal_reference[False-1e+308--1e+308--1e+308-1e+308]
tests/test_structure_two_w3_round6_prepared_boundary.py::test_weights_match_independent_decimal_reference[False--1e+308--1e+308-0.0-0.0]
tests/test_structure_two_w3_round6_prepared_boundary.py::test_weights_match_independent_decimal_reference[False-700.0--1.0--700.0-0.0]
tests/test_structure_two_w3_round6_prepared_boundary.py::test_weights_match_independent_decimal_reference[False--700.0--1.0-0.0-0.0]
tests/test_structure_two_w3_round6_prepared_boundary.py::test_weights_match_independent_decimal_reference[False-1e-300--1e-300--1e-300-0.0]
tests/test_structure_two_w3_round6_prepared_boundary.py::test_weights_match_independent_decimal_reference[False-0.0-0.0-0.0--1e+308]
tests/test_structure_two_w3_round6_prepared_boundary.py::test_weights_match_independent_decimal_reference[True-0.0--1e+308--1e+308-0.0]
tests/test_structure_two_w3_round6_prepared_boundary.py::test_weights_match_independent_decimal_reference[True-1e+308--1e+308--1e+308-1e+308]
tests/test_structure_two_w3_round6_prepared_boundary.py::test_weights_match_independent_decimal_reference[True--1e+308--1e+308-0.0-0.0]
tests/test_structure_two_w3_round6_prepared_boundary.py::test_weights_match_independent_decimal_reference[True-700.0--1.0--700.0-0.0]
tests/test_structure_two_w3_round6_prepared_boundary.py::test_weights_match_independent_decimal_reference[True--700.0--1.0-0.0-0.0]
tests/test_structure_two_w3_round6_prepared_boundary.py::test_weights_match_independent_decimal_reference[True-1e-300--1e-300--1e-300-0.0]
tests/test_structure_two_w3_round6_prepared_boundary.py::test_weights_match_independent_decimal_reference[True-0.0-0.0-0.0--1e+308]
```

The numeric-failure family also passed for both generation steps `0` and `1`, each with exact parameter IDs `positive_overflow`, `negative_overflow`, `unresolved_underflow`, `nan`, `positive_inf`, and `negative_inf`:

```text
tests/test_structure_two_w3_round6_prepared_boundary.py::test_numeric_failure_is_explicit_atomic_and_retryable[0-positive_overflow]
tests/test_structure_two_w3_round6_prepared_boundary.py::test_numeric_failure_is_explicit_atomic_and_retryable[0-negative_overflow]
tests/test_structure_two_w3_round6_prepared_boundary.py::test_numeric_failure_is_explicit_atomic_and_retryable[0-unresolved_underflow]
tests/test_structure_two_w3_round6_prepared_boundary.py::test_numeric_failure_is_explicit_atomic_and_retryable[0-nan]
tests/test_structure_two_w3_round6_prepared_boundary.py::test_numeric_failure_is_explicit_atomic_and_retryable[0-positive_inf]
tests/test_structure_two_w3_round6_prepared_boundary.py::test_numeric_failure_is_explicit_atomic_and_retryable[0-negative_inf]
tests/test_structure_two_w3_round6_prepared_boundary.py::test_numeric_failure_is_explicit_atomic_and_retryable[1-positive_overflow]
tests/test_structure_two_w3_round6_prepared_boundary.py::test_numeric_failure_is_explicit_atomic_and_retryable[1-negative_overflow]
tests/test_structure_two_w3_round6_prepared_boundary.py::test_numeric_failure_is_explicit_atomic_and_retryable[1-unresolved_underflow]
tests/test_structure_two_w3_round6_prepared_boundary.py::test_numeric_failure_is_explicit_atomic_and_retryable[1-nan]
tests/test_structure_two_w3_round6_prepared_boundary.py::test_numeric_failure_is_explicit_atomic_and_retryable[1-positive_inf]
tests/test_structure_two_w3_round6_prepared_boundary.py::test_numeric_failure_is_explicit_atomic_and_retryable[1-negative_inf]
```

These are `COVERED-812-LF`; the aggregate 812 suite remains failed for unrelated, explicitly retained failures.

## Hash seeds, ordering and platform limits

- The complete 47-node repair matrix ran under `PYTHONHASHSEED=0`, `1`, and `8675309`; each run collected and passed the same 47 exact nodes with no skips or xfails.
- The repair matrix includes multigeneration sequencing, initial/readout/parent/replay surface order, paired-location reorder, reversed lineage, post-acceptance alias mutation and a self-mutating mapping. It is deterministic adversarial coverage, not a claim of randomized property-based stress.
- The exact 812 replay and its Windows/LF control used hash seed 0. The suite also contains `test_real_projection_consumes_under_independent_python_hash_seeds[5]` and `[11]`, both of which passed individually, but those two cases do not replace the complete three-seed matrix.
- Execution is Windows 11 / CPython 3.13.5. The LF control changes checkout bytes, not the operating system. WSL was unavailable, so no Linux execution claim is made.
- CRLF and LF exact-812 runs are both retained failures. The LF run clears four raw-byte-gated nodes, exposes five Windows separator failures, and retains the same three lock deadline failures. See `post_fix/windows_lf_comparison.json` and `post_fix/failure_triage.md`.

## Gaps that remain explicit

1. `2350602...` cannot be the final accepted repair because the three lock-handoff deadline nodes regress relative to R7. No timeout was relaxed.
2. A new post-lock commit/tree and all corresponding original-six, three-seed expansion and exact-812 evidence are not yet available in this index.
3. No repair author may self-sign independent review; another reviewer must run the frozen final candidate.
4. Prepared-particle checkpoint evidence is limited to in-memory transaction capture/restore and replay journals. Disk serialization, process restart and cross-machine restore are `NOT-ESTABLISHED`.
5. No WSL/Linux run occurred. Windows/LF is an end-of-line control, not a second platform.
6. The public prepared seam still declares no selected full replay kernel after particle ancestry invalidation and no default complete prepared-batch proposer. This security repair does not fill those capability gaps.
7. The three hash seeds are reproducibility/ordering controls. No unbounded or randomized stress campaign, failure-sequence shrinker or formal proof is claimed.
