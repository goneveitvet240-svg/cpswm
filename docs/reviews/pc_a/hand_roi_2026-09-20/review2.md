# Independent component review 2

Reviewed implementation: `2de22e8a60687944166913fc15d45d38d2beee46`.
Reviewer did not read review 1. Production files were read only; this report is the only repository file written by this reviewer.

Verdict: changes required for ROI checkpoint provenance. This is a component review, not computer B replication, natural P5 acceptance, calibrated contact/role validation, or scientific-benefit evidence.

## Finding: P2 — legal-region substitution and impossible regional cardinality survive restore

`src/cpswm/perception_mapping/natural_hands.py:282-294` validates that candidate region IDs belong to the expected crop set, but does not validate the candidate UUID derivation or per-region count. `NaturalVisionEvidenceProducer.restore_state` calls this validator and then accepts both mutations below:

1. Starting from a legal two-region frame, change the full-frame hand's `region_id` to the other legal person ROI, retaining its original candidate UUID and landmarks. Restore succeeds, although `infer_with_visual` would derive that UUID from the original region.
2. Starting from the same legal checkpoint with `num_hands=4`, replace hands with five unique-UUID candidates assigned to the same legal region. Restore succeeds, although inference explicitly rejects more than four candidates in any region.

Both attacks preserve the raw prefix, visual-source digest, region inventory, and all expected source metadata. They therefore exercise a complete otherwise-valid path rather than a malformed unknown-region negative. Derived measurement validation uses the same incomplete validator. This permits impossible producer states and incorrect crop provenance to persist across recovery; it does not itself create a semantic transition.

Recommended fix: validate each region's candidate count and deterministic UUID sequence against `uuid5(region_id, f"hand:{HAND_MODEL_SHA256}:{index}")`; preserve legal empty regions and overlapping regional observations. Add atomic restore rejection tests for both cases. Do not present deterministic IDs or hashes as proof that arbitrary landmark values were produced by the model.

## Independent checks

Executed with this worktree's `.venv`:

```sh
.venv/bin/pytest -q tests/test_hand_person_regions.py tests/test_natural_hands.py tests/test_hand_object_evidence.py tests/test_natural_vision.py tests/test_archive_media_timeline.py tests/test_core4d_range_reader.py tests/test_continuous_state_recovery.py tests/test_structure_two_continuous_input.py tests/test_structure_two_raw_rgbd_ingress.py
```

Result: 127 tests passed, no skipped or failed tests (exit 0). Count correction: the initial report incorrectly said 130 because a later collection command saw the three newly added fix tests; the original completed run emitted 127 passing test markers. The fixed-version run below uses an explicit final summary and is counted separately. These tests overlap other review suites and must not be added as independent coverage totals.

Ten additional direct boundary checks passed: five source/time/dimension/archive-timeline mutations rejected; four NaN/invalid-box/invalid-score cases rejected; top-four person selection remained deterministic under reversal of equal-score input candidates. The two forged checkpoint cases above were accepted and constitute the finding.

Inspection confirms ROI proposals originate from same-observation visual detections, coordinates map back to the original model-visible frame, full-frame fallback remains present, and overlap is explicitly retained as multiple regional observations rather than declared unique hands. Producer batching remains staged before state assignment. No author-mask loading is introduced into the model path.

The segmentation acquisition tool writes bounded selected NPZ members plus ZIP metadata to a separate output lane and does not unpickle or infer mask alignment. It explicitly records that the full archive SHA has not been verified. The evaluator-lane destination is a caller convention, not an access-control boundary. Actual download contents, frame semantics, source authenticity beyond recorded range/CRC/hash consistency, and real-video improvement were not independently established by this review.


## Fixed-version independent recheck

Fixed implementation: `6b8a9a0bcdee4a34091e130531a3c1c3a6223a0c` (HEAD verified; production working-tree diff empty).

The original P2 finding is resolved for the reviewed producer-state invariants. The validator now reconstructs region order and per-region UUID/index sequences and enforces the configured regional capacity. I independently replayed both original attacks; legal-region substitution and five-in-one-region with capacity four are rejected. Reversed candidate ordering is also rejected. Each rejection leaves producer state unchanged.

Four positive controls restored successfully: original complete regional output, no candidates in any region, only person-region candidates, and only full-frame-region candidates. Empty regions and legitimate overlapping observations therefore remain allowed.

Reran the same nine test files above with `.venv/bin/pytest -q -o addopts=''`: **130 passed in 32.63s, 0 skipped, 0 failed**, exit 0. These are 127 prior tests plus the three new impossible-history regression cases. Seven separate direct replays (three rejection/atomicity checks and four legal restores) also passed; these are reviewer probes, not additional pytest coverage.

Final scoped verdict: no remaining blocker found in this component change after the fix. Original findings remain above as audit history. This does not authenticate arbitrary self-consistent checkpoint landmark values against original model execution, establish mask alignment, prove improved real hand accuracy, or close natural P5 / computer B / scientific-benefit gates. Neither another review nor its findings were read.

## Final delivery SHA binding

Final implementation: `e0e572baf602c0e75bf834fd8e9f2aabe62da90b`. Independently verified HEAD and the full diff from `6b8a9a0bcdee4a34091e130531a3c1c3a6223a0c`: exactly one file and one replacement, adding local variable annotation `expected_candidates: list[tuple[UUID, UUID]] = []`. No runtime logic or test changes occur in this diff. The scoped review verdict therefore applies to this final SHA by inspected equivalence. The 130-test execution remains explicitly bound to `6b8a9a0`; no unnecessary repeat or new test-run claim is made. The lead agent's mypy / real-input runs are separate evidence and were not independently executed here.
