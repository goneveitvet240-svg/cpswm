# Controlled helper binding follow-up

Implementation-author follow-up, not R1/R2 or independent acceptance. The predecessor's complete combination failed a legitimate first publication: `logweight-final-validation-01.log` records 170 passed / 1 failed in 497.05 seconds, with all 895 source files unchanged. The failure occurred in `ControlledPositionProducer._content_binding`, before that external Decimal test changed any receipt. The original result remains a blocker for that source; its failure is not reclassified as a harness problem.

The author then stopped all `src/tests/tools` writes again after the change and targeted checks described here. Root owns the complete combination rerun and the subsequent new-source two-review gate. No actual archive/Unity run or new scientific training took place in this follow-up.

## Diagnosis and its limit

The controlled producer's five-helper scan and own-module function scan still used the original `_code_object_sha256` default marshal encoding. Earlier workspace tests had directly demonstrated execution/traceback-reference instability in that encoding. However, **the particular member responsible for the 171-case failure was not captured**. This note does not claim that failure has been traced to a named helper, nor that the same mechanism has been conclusively established for it.

Bounded additional diagnostics before editing the producer:

- `HelperBindingRepair/probe_helper_binding.py` used a read-only profiler without replacing production functions. Twenty successive legitimate first publications using the previously executed Perceiver checkpoint succeeded; 820 `implementation_binding` returns showed no variation. `probe-01.log` / `probe-01/summary.json` retain this negative result, exit 0.
- `HelperBindingRepair/probe_active_helpers.py` traced actual synthetic fit/readout helper execution without replacing functions. 22,052 line/call/return checks showed no default-hash variation in that run. `active-01.log` / `active-01/result.json` retain this negative result, exit 0.
- Simpler read-only tuple/full-payload retention probes likewise did not isolate a changing member; their output is in the tool session. They are not reported as a successful reproduction.

Root explicitly bounded further search and authorized a local encoding normalization followed by complete regression, while retaining this unresolved attribution. The independent reviewer also found no static evidence of a leaked test monkeypatch; that does not prove a unique runtime cause.

## Local correction and preserved checks

Only `src/cpswm/system/controlled_position_producer.py` and `tests/test_native_log_weight_continuation.py` changed relative to the previous author stop-writes map.

The producer now uses `_helper_code_sha256`, SHA256 of the full existing `_code_object_payload` encoded with explicit marshal version 2, in both its five-module member scan and its own-module global function scan. It keeps all previous functions, class methods/properties, source-file bytes, and fixed H/config/schema/scope/domain/estimator/constants. The new helper itself is covered by the own-module scan and source binding. No member or check was removed. The generic `python_dependency_implementation_binding`, project-wide `_code_object_sha256`, checkpoint weight format, proposal architecture and numerical model remain unchanged.

This is a local, type-exact identity encoding for the declared controlled producer, consistent with the already tested workspace-local stable encoding. New source must be frozen/reviewed; old runtime bindings are not called compatible merely because weights are reused.

## Executed checks on the follow-up source

Interpreter: `/private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python`.

Worktree: `/private/tmp/cpswm-pc-a-soft-position-factor-20261001`.

All pytest executions below used `PYTHONPATH=src:tests:tools OPENBLAS_NUM_THREADS=1`, `-m pytest -c pyproject.toml -o addopts= -q`.

1. `tests/test_native_log_weight_continuation.py -k 'original_helper or helper_full or full_code'` plus the external Decimal file in the selection: **4 passed, 13 deselected, 9.52 seconds, exit 0**. The `-k` filter deselected the four external Decimal cases, so this run does not claim them. Exact saved log: `HelperBindingRepair/tests-01.log`; explicit basetemp: `HelperBindingRepair/tests-01`.
2. The external file `LogWeightValidation/test_independent_log_arithmetic.py` alone, without `-k`: **4 passed, 6.95 seconds, exit 0**. Exact saved log: `HelperBindingRepair/decimal-01.log`; basetemp `HelperBindingRepair/decimal-01`.
3. Ruff check and format-check on all nine total changed files returned exit 0; all nine were formatted. `git diff --check` also returned exit 0. Raw tool output remains in the tool session. One intermediate Ruff invocation stopped on import order/formatting before running any test; it was corrected first.

The four targeted cases exercise type distinctions (True/1, 1/1.0, +0.0/-0.0), retain full original helper payloads during actual `position.condition`, and reject complete real-q forgeries after changing helper code or H. Those forgery tests restore the original helper while retaining the caught exception's traceback and require legal publication afterward. They do not claim the rejection necessarily occurs at a unique innermost scanner rather than an earlier original producer-binding guard.

The legal active/neutral test checked all **116 original helper members**, retained their complete payloads, and performed **258 active `position.condition` line checks**. Full payload evidence is saved at:

`HelperBindingRepair/tests-01/test_original_helper_payloads_0/helper-payloads.json`

SHA256: `5a16b43952663eeb1e123e9995f86ccff8ec4a87b0b524214d863d9d4515b33d`.

It contains the original complete version-2 payloads and an actual active condition payload, with exact before/after equality. This is positive stability evidence for the tested execution, not a stored reproduction of the original 171-case drift.

The external Decimal cases include real ordinary initial publication followed by detached arithmetic probes for underflow/common offsets/finite-range rejection. Artificial receipt changes are not owner-admitted new factors. Their independent formula authorship is distinct from this author executing them.

## Final source and handoff

`HelperBindingRepair/author-source-files.json` records all 895 Python files under `src/tests/tools`, based on local HEAD `000f6916a86bd6c84549ff99e65d7beeb14aa2d0` plus the uncommitted repair. Its SHA256 is `d5dc8937a87a5787d4c3876929dfec3d5e9e4b6bd931d27c426795ba88e5e8ee`. This is an author source map, not a reviewed source commit.

The added tests increase the original complete combination from 171 to an expected 174 cases. The complete combination must actually pass after this source change; eight author-targeted passes do not replace it. Formal sequential R1/R2 must then bind the new frozen source. Actual archive→Native bridge work remains unstarted, with historical Transformer execution carrier, both position references and both estimators retained according to root's subsequent plan.
