# B4 two-round adversarial audit

## 修复回归状态

已在隔离快照完成第一项修复：`advance()` 现在会重新执行候选链 schema
校验，在构造记录前校验其与运行时 `source_frame` 的精确一致性，并仅保存
脱离调用者别名的运行时来源副本。修复后同一伪造攻击得到提交前
`ValueError: candidate event chain differs from its runtime source history`，
记录和状态均未新增，随后合法提交仍可成功。

第二项导入循环未越界修改：最小修复点是
`src/cpswm/system/evaluation_operations/__init__.py` 的 eager benchmark
re-export，但该文件不属于当前 B4 明确允许的三个生产文件，已交由集成/A
确认后处理。

## Frozen target and method

* Target branch / commit: `codex/pc-b-w3-five-boundaries-fix-20260912` at
  `c366cad0a92593bb2c4c44db7e8d3408a2b5cc9c`.
* Checked production blobs: `prototype_spine.py` =
  `79404723eae0d68f4cd8bdb1a7a0fba74b42d214`,
  `structure_two_particle_workspace.py` =
  `1e1d6389c7623bc0562ff7b723a6dd89b79423a3`, and
  `structure_two_semantic_identity.py` =
  `18de28509f4e6fc7a37f6e5c045c1883b4893f9a`.
* Platform: Linux 6.18.35 x86_64, CPython 3.12.14.  This is a separate Linux
  audit environment, not a replacement for the required Windows/CRLF result.
* Command and raw machine-readable evidence:

  ```bash
  PYTHONPATH=src:tests python tools/pc_b_two_round_adversarial_audit.py \
    --output docs/reviews/pc_b/b4_b9_followup_2026-09-13/\
two_round_adversarial_audit_after_fix_linux_py312.json
  ```

The tool uses the frozen real production fixture for its legal control.  It
does not patch production files, reduce validation, or use a final output to
manufacture an expected answer.  `pytest` is not installed in this isolated
environment, so the tool contains a minimal import-only decorator shim; it is
not a substitute for the project test runner.

## Round 1 — forged source lineage at the public workspace boundary

**Status: confirmed bug (high), locally repaired.**

The legal control calls `NativeParticleWorkspace.advance` with real receipts,
statistics, a runtime history and source frame.  It returns two particles and
`state_payload()` succeeds.

The attack replaces only one `EventChainHypothesis` passed in `chains` with a
new, schema-valid object that retains its hypothesis UUID and all actor roles,
but changes `explanation_code`.  The source frame still holds the genuine
chain.  This is a non-no-op fully resealed mismatch.

Observed result:

1. `advance()` returns successfully and writes two records plus one journal
   entry.
2. `state_payload()` then raises `ValueError: prepared particle event-chain
   history differs from its source`.
3. A subsequent legal call via `CorePrototypeSpine.stage_prepared_particle_candidates`
   raises the same exception; the runtime is poisoned until private state is
   manually repaired.

The immediate cause is that `advance()` checks only the caller-supplied
`chains[state.event_hypothesis_id]` for existence and roles
([workspace lines 665–685](../../../../src/cpswm/system/structure_two_particle_workspace.py)),
then stores that object ([lines 728–734](../../../../src/cpswm/system/structure_two_particle_workspace.py)).
The comparison against the runtime-owned history occurs only later in
`_validate_record_binding()` during readout.  Although the core wrapper builds
its own chain mapping and rolls back on errors, `advance()` is a public method
and must not leave invalid persistent state when invoked directly.

Recommended minimal repair: before adding any `NativeParticleRecord`, obtain
the chain with the candidate UUID from `source_frame`'s typed history, require
one exact match, and require the supplied `chains` object to equal it.  Keep
the check before the final multi-field assignment, so a rejected direct call
has no mutation.  This repair is now implemented, with a dedicated pytest
regression and legal nonempty control in
`tests/dual_pc_review/test_pc_b_two_round_adversarial_audit.py`.

Post-fix observation: the attack is rejected before mutation; both records and
journal counts remain zero; `state_payload()` remains valid; and the subsequent
legal core stage succeeds.  The audit-only direct-function runner reports
`3 passed` for the attack, legal-control and post-acceptance caller-alias
mutation pytest functions.  This does not
replace the required Windows/CRLF full-suite rerun.

An additional direct-function affected-set run reports `20 passed`: legal
cross-step ancestry, log-q/constraint consumption, fourteen public-boundary
rejections, two interruption/rollback cases, correction invalidation, and
semantic identity.  It emitted only the expected Pydantic serialization
warnings from deliberately malformed negative fixtures.  Because this
container has no pytest installation, these are explicitly runner results,
not a pytest/JUnit claim.

## Round 2 — clean-interpreter bootstrap order

**Status: confirmed bug (medium/high availability).**

Two fresh interpreters were used so module caches cannot mask the result.

| Invocation | Exit | Result |
| --- | ---: | --- |
| `import cpswm.system.prototype_spine` | 1 | circular-import `ImportError` for partially initialised `ActionReadout` |
| import `structure_two_selected_method`, then `prototype_spine` | 0 | prints `CorePrototypeSpine` |

`prototype_spine.py` imports a submodule of `evaluation_operations` at line 86.
Python first executes the package initializer, whose eager re-export imports
`project_two_action_benchmark` ([initializer lines 262–271](../../../../src/cpswm/system/evaluation_operations/__init__.py)).
That module imports `ActionReadout` back from the partially initialised
`prototype_spine` ([benchmark lines 94–99](../../../../src/cpswm/system/evaluation_operations/project_two_action_benchmark.py)).

The result is a hidden import-order contract: the core cannot serve as a direct
startup entrypoint, although a previous import accidentally makes it work.
Recommended repair: eliminate the package-initializer cycle—e.g. move
`ParticleRevision*` contracts to a dependency-neutral module or stop eagerly
importing the benchmark from `evaluation_operations.__init__`.  Add a subprocess
test for direct core import and retain the selected-method-first control.

## Scope and next owner

Only `src/cpswm/system/structure_two_particle_workspace.py` was changed in
production scope.  No shared integration branch, A-owned branch, threshold or
scientific criterion was changed.  The cold-import defect remains documented
for A/integration because its minimal repair point is outside the three-file
B4 production boundary.  B should still rerun the original six, the three-seed
47/47 matrix, affected workspace tests, and full CRLF 812 in the mandated
Windows environment before integration acceptance.
