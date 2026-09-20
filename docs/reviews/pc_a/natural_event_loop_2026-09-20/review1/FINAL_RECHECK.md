# Independent round-1 findings: fixed-source recheck

Rechecked production commit: `288b429a7d1e1d7f22f282ded333eedcf41957bc` in `/private/tmp/cpswm-pc-a-natural-event-loop-20260920`. Original `REPORT.md` is retained. Scope remains pixel-evidence restoration and the two original P2 findings; this is not full natural P5 or five-task acceptance.

## Independent results

1. Inspected the new staged restore implementation. State is deep-copied and validated before assignments; restored RGB/visual/hand histories require matching coverage, causal times, identity, raw hashes, capture receipts, dimensions, model bindings and constrained semantic status. Interactions are recomputed and compared before commit.
2. Independently adapted the original three reproductions to assert rejection and whole-state equality (`recheck_checkpoint.py`). Missing hand frames, mixed observation/model identity, and the missing-visual-field/partial-interaction case all raise ValueError with unchanged state. Legal restore and repeated-prefix idempotence pass.
3. Independently ran 66 tests: `tests/test_natural_hands.py` (20), `tests/test_continuous_state_recovery.py` (13), `tests/test_natural_vision.py` (23), `tests/test_natural_event_coverage.py` (10). All pass, exit 0. This includes the added 13 malformed-checkpoint cases.
4. Independently executed the actual six-frame recovery tool on the pinned additional dataset and existing Faster R-CNN / MediaPipe artifacts. The first ordinary-sandbox run terminated at MediaPipe native initialization (exit 134, Metal service unavailable); it did not reach recovery assertions. One authorized unsandboxed rerun completed, exit 0. No production or dataset files were modified by the reviewer.

Actual rerun output: `/private/tmp/cpswm-natural-review1/real-recovery-recheck-unsandboxed/summary.json` and `resume.sqlite`.

- 6 contiguous raw RGB-D frames, interruption after 3.
- SQLite closed and reopened; actual models reconstructed.
- Uninterrupted vs restored visual and hand candidates exactly equal.
- 6 hand candidates; 0 semantic transitions; 0 physical actions.
- Source unchanged during run.
- Raw manifest SHA256: `0b8d5fe14d6416f1afe6fcf93e95166291aab9ec234a83f2dc4aa69019632250`.
- `natural_vision.py` SHA256: `db8d12210bf590898e00581f980cae16fdddd8265be9c45a7d458e009240d083`.
- `natural_hands.py` SHA256: `13ca229121b8f66faeda5beadec403600f03266c93760b0810c306ab6cad2586`.
- `check_natural_hand_recovery.py` SHA256: `4096a3565ee604a39159ac5198c243f4acfafbcb39990efa33d1c6c741df950c`.

## Disposition and limits

Both original P2 findings are resolved for the tested malformed-state cases on this fixed source. No additional blocking finding arose in this focused recheck. Passing component persistence does not establish calibration, contact/release, actor identity, natural semantic correction, memory rollback, changed physical action, or independent B-computer acceptance. The new evaluator tool is outside this recheck and assigned to the other independent reviewer. This check does not claim adversarial authenticity of fully rewritten payloads and all external trust pins, nor full coverage of every possible malformed Python object.
